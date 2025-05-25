#!/usr/bin/env python3
"""
ActivityWatch Timeline Processor
A CLI tool to fetch timeline data from ActivityWatch API and process it with LLM
"""

import argparse
import json
import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import requests
from litellm import completion
import click
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import print as rprint
from dotenv import load_dotenv

load_dotenv()

console = Console()


class ActivityWatchClient:
    """Client for interacting with ActivityWatch API"""

    def __init__(self, base_url: str = None):
        self.base_url = (
            base_url or os.getenv("AW_SERVER_URL", "http://localhost:5600")
        ).rstrip("/")
        self.api_url = f"{self.base_url}/api/0"

    def test_connection(self) -> bool:
        """Test connection to ActivityWatch server"""
        try:
            response = requests.get(f"{self.api_url}/info", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def get_buckets(self) -> Dict[str, Any]:
        """Get all available buckets"""
        try:
            response = requests.get(f"{self.api_url}/buckets")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error fetching buckets: {e}[/red]")
            return {}

    def get_events(
        self,
        bucket_id: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> List[Dict]:
        """Get events from a specific bucket within time range"""
        try:
            # Convert to UTC and format as ISO8601
            start_utc = start_time.astimezone(timezone.utc)
            end_utc = end_time.astimezone(timezone.utc)

            params = {
                "start": start_utc.isoformat().replace("+00:00", "Z"),
                "end": end_utc.isoformat().replace("+00:00", "Z"),
                "limit": limit,
            }

            url = f"{self.api_url}/buckets/{bucket_id}/events"
            param_string = "&".join([f"{k}={v}" for k, v in params.items()])
            curl_cmd = f'curl "{url}?{param_string}"'
            console.print(f"[dim]DEBUG CURL: {curl_cmd}[/dim]")

            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error fetching events from {bucket_id}: {e}[/red]")
            return []


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


def get_time_choices(hours_back: int = 48) -> List[datetime]:
    """Generate list of 2-hour gapped timestamps for user selection"""
    now = datetime.now()  # Local timezone
    current_hour = now.replace(minute=0, second=0, microsecond=0)

    choices = []
    for i in range(0, hours_back + 1, 2):  # Step by 2 hours
        time_choice = current_hour - timedelta(hours=i)
        choices.append(time_choice)

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
    time_choices = get_time_choices(48)
    start_time = display_time_choices(time_choices)
    end_time = datetime.now()  # Local timezone

    duration_timedelta = end_time - start_time
    duration_hours = duration_timedelta.total_seconds() / 3600

    console.print(f"\n[bold]Selected time range:[/bold]")
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
