#!/usr/bin/env python3
"""
ActivityWatch Timeline Processor
A CLI tool to fetch timeline data from ActivityWatch API and process it with LLM
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import click
from dotenv import load_dotenv
from litellm import completion
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from activity_watch_client import ActivityWatchClient

load_dotenv()

console = Console()


class TimelineProcessor:
    """Process timeline data using LLM"""

    def __init__(self, model: str = None):
        self.model = model or os.getenv("LLM_MODEL", "gpt-4.1")

    def consolidate_timeline(
        self, timeline_data: List[Dict], start_time: datetime, end_time: datetime
    ) -> str:
        """Use LLM to consolidate and summarize timeline data"""

        # Prepare the timeline data for the LLM
        formatted_events = []
        for event in timeline_data:
            timestamp = datetime.fromisoformat(
                event["timestamp"].replace("Z", "+00:00")
            )
            duration = event.get("duration", 0)
            data = event.get("data", {})

            # Format event info
            event_info = {
                "time": timestamp.strftime("%H:%M:%S"),
                "duration_seconds": duration,
                "duration_minutes": round(duration / 60, 1),
                "data": data,
            }
            formatted_events.append(event_info)

        # Create prompt for LLM
        prompt = f"""
You are a time tracking assistant. I have raw activity data from ActivityWatch for the time period {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}.

Please analyze this timeline data and consolidate it into clean, grouped time blocks that would be suitable for inputting into a time tracking platform. 

Guidelines:
1. Group similar activities together
2. Ignore very short activities (< 2 minutes) unless they're significant
3. Focus on productive work activities
4. Create clear, descriptive labels for each time block
5. Merge fragmented time spent on the same application/task
6. Provide start time, end time, duration, and activity description for each block

Here's the raw timeline data:
{json.dumps(formatted_events, indent=2)}

Please respond with a clean, structured summary of time blocks in the following JSON format:
{{
  "summary": "Brief overview of the time period",
  "time_blocks": [
    {{
      "start_time": "HH:MM",
      "end_time": "HH:MM", 
      "duration_minutes": X,
      "activity": "Clear description of what was being done",
      "category": "Work/Break/Communication/etc"
    }}
  ],
  "total_tracked_time": "X minutes"
}}
"""

        try:
            response = completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            return response.choices[0].message.content
        except Exception as e:
            console.print(f"[red]Error processing with LLM: {e}[/red]")
            return None


def get_time_choices() -> List[datetime]:
    """Generate list of 2-hour gapped timestamps for current work day"""
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

    choices = []
    time_choice = current_hour

    # Go back in 2-hour increments until we reach start of relevant work day
    while time_choice >= work_day_start:
        choices.append(time_choice)
        time_choice = time_choice - timedelta(hours=2)

    # Add start of work day if not already included
    if work_day_start not in choices:
        choices.append(work_day_start)

    return choices


def display_time_choices(choices: List[datetime]) -> datetime:
    """Display time choices and get user selection"""
    console.print(
        "\n[bold cyan]Select a starting time (rounded to the hour):[/bold cyan]"
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Option", style="dim", width=6)
    table.add_column("Date & Time", style="cyan")
    table.add_column("Relative", style="green")

    for i, choice in enumerate(choices):
        now = datetime.now()
        diff = now - choice

        if diff.total_seconds() < 3600:
            relative = "Current hour"
        elif diff.days == 0:
            hours = int(diff.total_seconds() // 3600)
            relative = f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            relative = f"{diff.days} day{'s' if diff.days != 1 else ''} ago"

        table.add_row(str(i + 1), choice.strftime("%Y-%m-%d %H:%M"), relative)

    console.print(table)

    while True:
        try:
            selection = Prompt.ask("\nEnter option number", default="1")
            index = int(selection) - 1
            if 0 <= index < len(choices):
                return choices[index]
            else:
                console.print("[red]Invalid option. Please try again.[/red]")
        except ValueError:
            console.print("[red]Please enter a valid number.[/red]")


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
def main(model: str, aw_url: str, output: Optional[str]):
    """ActivityWatch Timeline Processor CLI"""

    console.print("[bold green]ActivityWatch Timeline Processor[/bold green]")
    console.print("=" * 50)

    # Initialize clients
    aw_client = ActivityWatchClient(aw_url)
    processor = TimelineProcessor(model)

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

    # Get time selection
    time_choices = get_time_choices()
    start_time = display_time_choices(time_choices)
    end_time = datetime.now()  # Local timezone

    duration_timedelta = end_time - start_time
    duration_hours = duration_timedelta.total_seconds() / 3600

    console.print("\n[bold]Selected time range:[/bold]")
    console.print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M')}")
    console.print(f"End: {end_time.strftime('%Y-%m-%d %H:%M')}")
    console.print(f"Duration: {duration_hours:.1f} hour(s)")

    if not Confirm.ask("\nProceed with fetching timeline data?"):
        console.print("Cancelled.")
        sys.exit(0)

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

    # Process with LLM
    if not Confirm.ask("Process timeline with LLM?"):
        console.print("Timeline data fetched but not processed.")
        sys.exit(0)

    console.print(f"\n[bold]Processing timeline with {model}...[/bold]")

    with console.status("[bold green]LLM processing timeline..."):
        result = processor.consolidate_timeline(all_events, start_time, end_time)

    if result:
        console.print("\n[bold green]✓ Timeline processed successfully![/bold green]")
        console.print("\n" + "=" * 50)
        console.print("[bold cyan]Processed Timeline:[/bold cyan]")
        console.print(result)

        # Save to file if requested
        if output:
            try:
                with open(output, "w") as f:
                    f.write(result)
                console.print(f"\n[green]✓ Results saved to {output}[/green]")
            except Exception as e:
                console.print(f"[red]Error saving to file: {e}[/red]")
    else:
        console.print("[red]Failed to process timeline with LLM[/red]")


if __name__ == "__main__":
    main()
