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
import pyperclip
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.table import Table

from activity_watch_client import ActivityWatchClient
from entry import TimeEntry
from timeline_processor import TimelineProcessor
from toggl_client import TogglClient

load_dotenv()

console = Console()
SNAPSHOT_ENABLED = False
STATE_DIR = Path.home() / ".smart-time-logger"
TIMELINE_FILE = STATE_DIR / "timeline_snapshot.json"
CTRL_T_TRIGGER = "__CTRL_T__"


def _time_window() -> tuple[datetime, datetime]:
    now = datetime.now()
    start_hour = int(os.getenv("WORK_DAY_START_HOUR", "0"))
    end_hour = int(os.getenv("WORK_DAY_END_HOUR", "4"))
    rounded_now = now.replace(minute=0, second=0, microsecond=0)
    if rounded_now.hour < end_hour:
        start = (rounded_now - timedelta(days=1)).replace(hour=start_hour, minute=0, second=0, microsecond=0)
    else:
        start = rounded_now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    return start, now


def _load_previous_events() -> List[Dict]:
    if not SNAPSHOT_ENABLED or not TIMELINE_FILE.exists():
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


def _prompt_user_decision(token_estimate: Optional[int], full_prompt: Optional[str]) -> bool:
    """Prompt the user for next action. Returns True if consolidation should run."""

    console.print("[bold green]Command input ready[/bold green]")

    if token_estimate is not None:
        token_display = f"{token_estimate:,}"
        summary = f"Process this timeline with the LLM (~{token_display} input tokens)."
    else:
        summary = "Process this timeline with the LLM."

    instructions_parts = ["Ctrl+T = run now"]
    if full_prompt:
        instructions_parts.append("Ctrl+Y = copy prompt")
    instructions_parts.append("Enter = submit command")
    instructions_parts.append("Blank = skip")
    instructions = " • ".join(instructions_parts)

    toolbar_html = HTML(f"<style fg='ansigray'>{summary}</style> | " f"<style fg='ansigray'>{instructions}</style>")

    session = PromptSession()
    bindings = KeyBindings()

    @bindings.add("c-t")
    def _trigger(event):
        event.app.exit(result=CTRL_T_TRIGGER)

    @bindings.add("c-y")
    def _copy(event):
        def _notify(message: str, style: str) -> None:
            console.print(f"[{style}]{message}[/{style}]")

        if not full_prompt:
            run_in_terminal(lambda: _notify("No prompt available to copy.", "yellow"))
            return

        def _copy_and_notify() -> None:
            try:
                pyperclip.copy(full_prompt)
                _notify("Copied LLM prompt to system clipboard.", "green")
            except Exception as err:  # pragma: no cover - environment dependent
                clipboard = getattr(event.app, "clipboard", None)
                if clipboard is None:
                    _notify(f"Unable to copy prompt: {err}", "yellow")
                    return
                try:
                    clipboard.set_text(full_prompt)
                    _notify("Copied LLM prompt to clipboard.", "green")
                except Exception as inner_err:  # pragma: no cover
                    _notify(f"Unable to copy prompt: {inner_err}", "yellow")

        run_in_terminal(_copy_and_notify)

    user_input = session.prompt(
        HTML("<ansigray>> </ansigray>"),
        key_bindings=bindings,
        bottom_toolbar=lambda: toolbar_html,
    )

    if user_input == CTRL_T_TRIGGER:
        console.print("[green]Ctrl+T detected. Proceeding with consolidation.[/green]")
        return True

    command = user_input.strip()
    if not command:
        return False

    lowered = command.lower()
    if lowered in {"y", "yes", "run", "process", "proceed", "go", "start", "do it"}:
        return True
    if lowered in {"n", "no", "skip", "cancel", "stop", "abort"}:
        return False

    console.print(f"[yellow]Captured command:[/yellow] {command}")
    return click.confirm("Run the LLM with this timeline now?", default=True)


@click.command()
def main() -> None:
    console.print("[bold cyan]Processing ActivityWatch timeline...[/bold cyan]")
    if SNAPSHOT_ENABLED:
        STATE_DIR.mkdir(parents=True, exist_ok=True)

    client = ActivityWatchClient()
    if not client.test_connection():
        raise click.ClickException("Unable to reach ActivityWatch. Ensure it is running and accessible.")

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
        console.print("[yellow]No timeline events were returned for the selected range.[/yellow]")
        return

    if SNAPSHOT_ENABLED:
        previous_events = _load_previous_events()
        previous_keys = {_event_key(event) for event in previous_events}
        new_events = [event for event in all_events if _event_key(event) not in previous_keys]

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
            console.print(f"[green]Detected {len(new_events)} new event(s) since the last run.[/green]")
        else:
            console.print("[green]Stored the first ActivityWatch snapshot for future comparisons.[/green]")
        console.print(f"Snapshot saved to {TIMELINE_FILE}")
    else:
        console.print("[dim]Snapshot persistence disabled. Skipping comparison and storage.[/dim]")

    toggl_entries: List[Dict] = []
    try:
        toggl_client = TogglClient()
        toggl_entries = toggl_client.get_time_entries(start.date().isoformat(), end.date().isoformat())
        console.print(f"Loaded {len(toggl_entries)} Toggl time entries for context.")
    except ValueError as err:
        console.print(f"[yellow]Toggl unavailable: {err}[/yellow]")
    except Exception as err:  # pragma: no cover - defensive; requests errors propagate here
        console.print(f"[yellow]Failed to fetch Toggl entries: {err}[/yellow]")

    processor = TimelineProcessor()
    prompt_text = processor.build_prompt(all_events, toggl_entries)
    token_estimate = processor.estimate_input_tokens(all_events, toggl_entries, start, end, prompt=prompt_text)
    proceed = _prompt_user_decision(token_estimate, prompt_text)
    if not proceed:
        console.print("LLM processing skipped.")
        return

    console.print(f"[bold cyan]Running {processor.model} to consolidate {len(all_events)} events...[/bold cyan]")
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
    console.print("[green]Timeline processing complete. Review the entries above before syncing elsewhere.[/green]")


if __name__ == "__main__":
    main()
