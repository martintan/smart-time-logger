#!/usr/bin/env python3
"""
ActivityWatch Timeline Processor
A CLI tool to fetch timeline data from ActivityWatch API and process it with LLM
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import click
from dotenv import load_dotenv
from litellm import completion
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from activity_watch_client import ActivityWatchClient
from entry import TimeEntryList
from toggl_client import TogglClient

load_dotenv()

console = Console()

# Template for the full LLM prompt
FULL_PROMPT_TEMPLATE = """
{base_prompt}

**Configuration:**
- Minimum Activity Duration: {min_duration_minutes} minutes (ignore consolidated blocks shorter than this)

**User's Context:**
{user_context}

**Existing Toggl Time Entries (JSON Array):**
{toggl_entries}

**ActivityWatch Time Entries (JSON Array):**
{timeline_data}
""".strip()


class TimelineProcessor:
    """Process timeline data using LLM"""

    def __init__(self, model: str = None, min_duration_minutes: int = None):
        self.model = model or os.getenv("LLM_MODEL", "gpt-4.1")
        self.min_duration_minutes = min_duration_minutes or int(
            os.getenv("MIN_ACTIVITY_DURATION_MINUTES", "5")
        )

    def consolidate_timeline(
        self,
        timeline_data: List[Dict],
        toggl_entries: List[Dict],
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[TimeEntryList]:
        """Use LLM to consolidate and summarize timeline data"""

        # Read the prompt from INFER_TIME_ENTRY_LOGGING.md
        try:
            with open("INFER_TIME_ENTRY_LOGGING.md", "r") as f:
                base_prompt = f.read()
        except FileNotFoundError:
            console.print("[red]INFER_TIME_ENTRY_LOGGING.md file not found[/red]")
            return None

        # Read optional user context from ACTIVITY.md
        user_context = ""
        try:
            with open("ACTIVITY.md", "r") as f:
                user_context = f.read()
        except FileNotFoundError:
            user_context = "No additional user context provided."

        # Prepare the timeline data in the format expected by the prompt
        formatted_events = []
        for event in timeline_data:
            # Keep the original structure as specified in the prompt
            formatted_event = {
                "id": event.get("id", 0),
                "timestamp": event["timestamp"],
                "duration": event.get("duration", 0),
                "data": event.get("data", {}),
            }
            formatted_events.append(formatted_event)

        # Create the full prompt with user context, toggl entries, and activity watch data
        full_prompt = FULL_PROMPT_TEMPLATE.format(
            base_prompt=base_prompt,
            min_duration_minutes=self.min_duration_minutes,
            user_context=user_context,
            toggl_entries=json.dumps(toggl_entries, indent=2),
            timeline_data=json.dumps(formatted_events, indent=2),
        )

        try:
            response = completion(
                model=self.model,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            # Parse the JSON response and validate it with TimeEntryList
            json_response = json.loads(response.choices[0].message.content)

            # Convert to TimeEntryList format if needed
            if "entries" in json_response:
                return TimeEntryList.model_validate(json_response)
            elif isinstance(json_response, list):
                return TimeEntryList(entries=json_response)
            else:
                console.print(f"[red]Unexpected response format from LLM[/red]")
                return None

        except Exception as e:
            console.print(f"[red]Error processing with LLM: {e}[/red]")
            return None


def get_today_date_range() -> Tuple[str, str]:
    """Get today's date range in ISO format using same logic as get_time_choices"""
    now = datetime.now()  # Local timezone
    current_hour = now.replace(minute=0, second=0, microsecond=0)

    # Get work day configuration from environment
    day_start_hour = int(os.getenv("WORK_DAY_START_HOUR", "0"))  # Default: midnight
    day_end_hour = int(os.getenv("WORK_DAY_END_HOUR", "4"))  # Default: 4 AM next day

    # Determine the earliest time to include based on current time and work day boundaries
    if current_hour.hour < day_end_hour:
        # Current time is within extended work day (e.g., 1:30 AM)
        # Include times from yesterday's work day start
        work_day_start = (current_hour - timedelta(days=1)).replace(
            hour=day_start_hour, minute=0, second=0, microsecond=0
        )
    else:
        # Current time is in new work day (e.g., 10 AM)
        # Only include times from today's work day start
        work_day_start = current_hour.replace(
            hour=day_start_hour, minute=0, second=0, microsecond=0
        )

    # End time is current time
    work_day_end = now

    # Return ISO date strings
    start_date = work_day_start.strftime("%Y-%m-%d")
    end_date = work_day_end.strftime("%Y-%m-%d")

    return start_date, end_date


def get_today_time_range() -> Tuple[datetime, datetime]:
    """Get today's time range as datetime objects using same logic as get_time_choices"""
    now = datetime.now()  # Local timezone
    current_hour = now.replace(minute=0, second=0, microsecond=0)

    # Get work day configuration from environment
    day_start_hour = int(os.getenv("WORK_DAY_START_HOUR", "0"))  # Default: midnight
    day_end_hour = int(os.getenv("WORK_DAY_END_HOUR", "4"))  # Default: 4 AM next day

    # Determine the earliest time to include based on current time and work day boundaries
    if current_hour.hour < day_end_hour:
        # Current time is within extended work day (e.g., 1:30 AM)
        # Include times from yesterday's work day start
        work_day_start = (current_hour - timedelta(days=1)).replace(
            hour=day_start_hour, minute=0, second=0, microsecond=0
        )
    else:
        # Current time is in new work day (e.g., 10 AM)
        # Only include times from today's work day start
        work_day_start = current_hour.replace(
            hour=day_start_hour, minute=0, second=0, microsecond=0
        )

    # End time is current time
    work_day_end = now

    return work_day_start, work_day_end


@click.command()
@click.option(
    "--model", default=None, help="LLM model to use (default: from env or gpt-4)"
)
@click.option(
    "--aw-url",
    default=None,
    help="ActivityWatch server URL (default: from env or localhost:5600)",
)
@click.option("--output", "-o", help="Output file to save results (optional)")
@click.option(
    "--min-duration",
    default=None,
    type=int,
    help="Minimum activity duration in minutes to consider (default: 5)",
)
def main(model: str, aw_url: str, output: Optional[str], min_duration: Optional[int]):
    """ActivityWatch Timeline Processor CLI"""

    console.print("[bold green]ActivityWatch Timeline Processor[/bold green]")
    console.print("=" * 50)

    # Initialize clients
    aw_client = ActivityWatchClient(aw_url)
    processor = TimelineProcessor(model, min_duration)

    # Initialize Toggl client (optional, will skip if no API token)
    toggl_client = None
    try:
        toggl_client = TogglClient()
        console.print("[green]✓ Toggl client initialized[/green]")
    except ValueError as e:
        console.print(f"[yellow]⚠ Toggl client not available: {e}[/yellow]")
        console.print("[yellow]Continuing without existing time entries...[/yellow]")

    # Test connection
    console.print("Testing connection to ActivityWatch...")
    if not aw_client.test_connection():
        console.print(f"[red]Could not connect to ActivityWatch at {aw_url}[/red]")
        console.print("Make sure ActivityWatch is running and accessible.")
        sys.exit(1)

    console.print("[green]✓ Connected to ActivityWatch[/green]")

    # Get available buckets
    console.print("\nFetching available buckets...")
    buckets = aw_client.get_buckets()

    if not buckets:
        console.print("[red]No buckets found or error fetching buckets[/red]")
        sys.exit(1)

    console.print(f"[green]✓ Found {len(buckets)} bucket(s)[/green]")

    # Display buckets
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Bucket ID", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Hostname", style="yellow")

    for bucket_id, bucket_info in buckets.items():
        table.add_row(
            bucket_id,
            bucket_info.get("type", "Unknown"),
            bucket_info.get("hostname", "Unknown"),
        )

    console.print("\n[bold]Available buckets:[/bold]")
    console.print(table)

    # Automatically use today's time range
    start_date, end_date = get_today_date_range()
    start_time, end_time = get_today_time_range()

    duration_timedelta = end_time - start_time
    duration_hours = duration_timedelta.total_seconds() / 3600

    console.print("\n[bold]Processing time range for today:[/bold]")
    console.print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M')}")
    console.print(f"End: {end_time.strftime('%Y-%m-%d %H:%M')}")
    console.print(f"Duration: {duration_hours:.1f} hour(s)")

    # Fetch timeline data from all buckets
    console.print("\n[bold]Fetching timeline data...[/bold]")
    all_events = []

    with console.status("[bold green]Fetching events from buckets..."):
        for bucket_id in buckets.keys():
            events = aw_client.get_events(bucket_id, start_time, end_time)
            if events:
                console.print(f"✓ {bucket_id}: {len(events)} events")
                all_events.extend(events)
            else:
                console.print(f"- {bucket_id}: No events")

    if not all_events:
        console.print(
            "[yellow]No timeline data found for the selected time period.[/yellow]"
        )
        sys.exit(0)

    console.print(f"\n[green]Total events collected: {len(all_events)}[/green]")

    # Fetch existing Toggl time entries for today
    toggl_entries = []
    if toggl_client:
        console.print("\n[bold]Fetching existing Toggl time entries...[/bold]")
        try:
            with console.status("[bold green]Fetching Toggl entries..."):
                toggl_entries = toggl_client.get_time_entries(start_date, end_date)
            console.print(
                f"[green]✓ Found {len(toggl_entries)} existing time entries[/green]"
            )
        except Exception as e:
            console.print(f"[red]Error fetching Toggl entries: {e}[/red]")
            console.print(
                "[yellow]Continuing without existing time entries...[/yellow]"
            )

    # Process with LLM
    if not Confirm.ask("Process timeline with LLM?"):
        console.print("Timeline data fetched but not processed.")
        sys.exit(0)

    console.print(f"\n[bold]Processing timeline with {processor.model}...[/bold]")

    with console.status("[bold green]LLM processing timeline..."):
        result = processor.consolidate_timeline(
            all_events, toggl_entries, start_time, end_time
        )

    if result:
        console.print("\n[bold green]✓ Timeline processed successfully![/bold green]")
        console.print("\n" + "=" * 50)
        console.print("[bold cyan]Processed Timeline:[/bold cyan]")

        # Display the structured results
        for entry in result.entries:
            console.print(f"\n[cyan]{entry.description}[/cyan]")
            console.print(
                f"  Time: {entry.start_date} {entry.start_time} - {entry.end_date} {entry.end_time}"
            )
            console.print(f"  Duration: {entry.duration}")
            if entry.project:
                console.print(f"  Project: {entry.project}")
            if entry.task:
                console.print(f"  Task: {entry.task}")

        # Save to file if requested
        if output:
            try:
                with open(output, "w") as f:
                    f.write(result.model_dump_json(indent=2))
                console.print(f"\n[green]✓ Results saved to {output}[/green]")
            except Exception as e:
                console.print(f"[red]Error saving to file: {e}[/red]")
    else:
        console.print("[red]Failed to process timeline with LLM[/red]")


if __name__ == "__main__":
    main()
