#!/usr/bin/env python3
"""
ActivityWatch Timeline Processor CLI

On startup this script fetches ActivityWatch timeline data, stores a snapshot
under ~/.smart-time-logger, reports whether any new events were found compared to
the previous run, and optionally processes the data with an LLM to create
consolidated time entries.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from activity_watch_client import ActivityWatchClient
from entry import TimeEntry
from timeline_processor import TimelineProcessor
from toggl_client import TogglClient

load_dotenv()

console = Console()
STATE_DIR = Path.home() / ".smart-time-logger"
TIMELINE_FILE = STATE_DIR / "timeline_snapshot.json"


def _time_window() -> tuple[datetime, datetime]:
    now = datetime.now()
    start_hour = int(os.getenv("WORK_DAY_START_HOUR", "0"))
    end_hour = int(os.getenv("WORK_DAY_END_HOUR", "4"))
    rounded_now = now.replace(minute=0, second=0, microsecond=0)
    if rounded_now.hour < end_hour:
        start = (rounded_now - timedelta(days=1)).replace(
            hour=start_hour, minute=0, second=0, microsecond=0
        )
    else:
        start = rounded_now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    return start, now


def _load_previous_events() -> List[Dict]:
    if not TIMELINE_FILE.exists():
        return []
    try:
        with TIMELINE_FILE.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw.get("events", [])
    except (json.JSONDecodeError, OSError, AttributeError):
        return []


def _event_key(event: Dict) -> str:
    if not isinstance(event, dict):
        return str(event)
    if "id" in event:
        return f"id:{event['id']}"
    timestamp = event.get("timestamp", "?")
    data_blob = json.dumps(event.get("data", {}), sort_keys=True, default=str)
    return f"ts:{timestamp}|data:{data_blob}"


@click.command()
@click.option("--model", default=None, help="Override LLM model (default: gpt-5-nano)")
@click.option(
    "--aw-url",
    default=None,
    help="ActivityWatch server URL (default: AW_SERVER_URL env or http://localhost:5600)",
)
@click.option(
    "--min-duration",
    default=None,
    type=int,
    help="Minimum activity duration (minutes) for consolidation (default: env or 5)",
)
@click.option(
    "--skip-llm",
    is_flag=True,
    help="Fetch and store timeline data without running the LLM step",
)
def main(
    model: Optional[str],
    aw_url: Optional[str],
    min_duration: Optional[int],
    skip_llm: bool,
) -> None:
    console.print("[bold cyan]Processing ActivityWatch timeline...[/bold cyan]")
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    client = ActivityWatchClient(aw_url)
    if not client.test_connection():
        raise click.ClickException(
            "Unable to reach ActivityWatch. Ensure it is running and accessible."
        )

    start, end = _time_window()
    console.print(
        f"Collecting events from {start.isoformat(sep=' ', timespec='minutes')}"
        f" to {end.isoformat(sep=' ', timespec='minutes')}"
    )

    buckets = client.get_buckets()
    if not buckets:
        console.print("[yellow]No ActivityWatch buckets found.[/yellow]")
        return

    all_events: List[Dict] = []
    with console.status("[bold green]Fetching ActivityWatch data..."):
        for bucket_id in sorted(buckets.keys()):
            events = client.get_events(bucket_id, start, end)
            if events:
                console.print(f"• {bucket_id}: {len(events)} events")
                all_events.extend(events)
            else:
                console.print(f"• {bucket_id}: no events")

    if not all_events:
        console.print(
            "[yellow]No timeline events were returned for the selected range.[/yellow]"
        )
        return

    previous_events = _load_previous_events()
    previous_keys = {_event_key(event) for event in previous_events}
    new_events = [
        event for event in all_events if _event_key(event) not in previous_keys
    ]

    snapshot = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "event_count": len(all_events),
        "events": all_events,
    }
    with TIMELINE_FILE.open("w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2)

    if previous_events:
        console.print(
            f"[green]Detected {len(new_events)} new event(s) since the last run.[/green]"
        )
    else:
        console.print(
            "[green]Stored the first ActivityWatch snapshot for future comparisons.[/green]"
        )
    console.print(f"Snapshot saved to {TIMELINE_FILE}")

    if skip_llm:
        console.print("Skipping LLM processing as requested.")
        return

    proceed = click.confirm(
        "Process this timeline with the LLM to generate condensed time entries?",
        default=True,
    )
    if not proceed:
        console.print("LLM processing skipped.")
        return

    toggl_entries: List[Dict] = []
    try:
        toggl_client = TogglClient()
        toggl_entries = toggl_client.get_time_entries(
            start.date().isoformat(), end.date().isoformat()
        )
        console.print(f"Loaded {len(toggl_entries)} Toggl time entries for context.")
    except ValueError as err:
        console.print(f"[yellow]Toggl unavailable: {err}[/yellow]")
    except (
        Exception
    ) as err:  # pragma: no cover - defensive; requests errors propagate here
        console.print(f"[yellow]Failed to fetch Toggl entries: {err}[/yellow]")

    processor = TimelineProcessor(
        model=model or "gpt-5-nano", min_duration_minutes=min_duration
    )
    console.print(
        f"[bold cyan]Running {processor.model} to consolidate {len(all_events)} events...[/bold cyan]"
    )
    result = processor.consolidate_timeline(all_events, toggl_entries, start, end)
    if not result:
        console.print("[red]LLM processing did not return any time entries.[/red]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Description", style="cyan")
    table.add_column("Start", style="green")
    table.add_column("End", style="green")
    table.add_column("Duration", style="yellow")
    table.add_column("Project", style="blue")

    for entry in result.entries:
        if isinstance(entry, TimeEntry):
            project = entry.project or "-"
            table.add_row(
                entry.description,
                f"{entry.start_date} {entry.start_time}",
                f"{entry.end_date} {entry.end_time}",
                entry.duration,
                project,
            )
    console.print(table)
    console.print(
        "[green]Timeline processing complete. Review the entries above before syncing elsewhere.[/green]"
    )


if __name__ == "__main__":
    main()
