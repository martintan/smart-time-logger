"""
Tool functions for ActivityWatch Timeline Processor
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from rich.console import Console
from rich.table import Table
from smolagents import tool

from activity_watch_client import ActivityWatchClient
from timeline_processor import TimelineProcessor
from toggl_client import TogglClient

console = Console()

# Global variables to store initialized clients
_aw_client = None
_toggl_client = None
_processor = None
_last_result = None


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


def convert_time_to_local(date_str: str, time_str: str) -> Tuple[str, str]:
    """Convert UTC time to local timezone for display"""
    try:
        # Parse the date and time
        dt_str = f"{date_str} {time_str}"
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        
        # Assume the time is in UTC and convert to local
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone()
        
        # Return local date and time strings
        return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        # If conversion fails, return original values
        return date_str, time_str


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


@tool
def initialize_clients(aw_url: str = None) -> str:
    """Initialize ActivityWatch, Toggl clients and timeline processor. This should be called first before using other functions.
    
    Args:
        aw_url: ActivityWatch server URL (default: from env or localhost:5600)
    """
    global _aw_client, _toggl_client, _processor
    
    # Initialize clients
    _aw_client = ActivityWatchClient(aw_url)
    _processor = TimelineProcessor()

    # Initialize Toggl client (optional, will skip if no API token)
    _toggl_client = None
    try:
        _toggl_client = TogglClient()
        console.print("[green]✓ Toggl client initialized[/green]")
        toggl_status = "✓ Toggl client initialized"
    except ValueError as e:
        console.print(f"[yellow]⚠ Toggl client not available: {e}[/yellow]")
        console.print("[yellow]Continuing without existing time entries...[/yellow]")
        toggl_status = f"⚠ Toggl client not available: {e}"

    return f"✓ ActivityWatch client initialized\n{toggl_status}\n✓ Timeline processor initialized"


@tool
def test_connection() -> str:
    """Test connection to ActivityWatch server. Must call initialize_clients first."""
    global _aw_client
    if _aw_client is None:
        return "❌ Error: Clients not initialized. Call initialize_clients first."
    
    console.print("Testing connection to ActivityWatch...")
    if not _aw_client.test_connection():
        console.print(f"[red]Could not connect to ActivityWatch[/red]")
        console.print("Make sure ActivityWatch is running and accessible.")
        return "❌ Could not connect to ActivityWatch. Make sure ActivityWatch is running and accessible."

    console.print("[green]✓ Connected to ActivityWatch[/green]")
    return "✓ Connected to ActivityWatch"


@tool
def get_and_display_buckets() -> str:
    """Get available ActivityWatch buckets and display them. Must call initialize_clients first."""
    global _aw_client
    if _aw_client is None:
        return "❌ Error: Clients not initialized. Call initialize_clients first."
        
    console.print("\nFetching available buckets...")
    buckets = _aw_client.get_buckets()

    if not buckets:
        console.print("[red]No buckets found or error fetching buckets[/red]")
        return "❌ No buckets found or error fetching buckets"

    console.print(f"[green]✓ Found {len(buckets)} bucket(s)[/green]")

    # Display buckets
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Bucket ID", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Hostname", style="yellow")

    bucket_info_str = ""
    for bucket_id, bucket_info in buckets.items():
        bucket_type = bucket_info.get("type", "Unknown")
        hostname = bucket_info.get("hostname", "Unknown")
        bucket_info_str += f"{bucket_id} ({bucket_type}, {hostname})\n"
        table.add_row(bucket_id, bucket_type, hostname)

    console.print("\n[bold]Available buckets:[/bold]")
    console.print(table)
    return f"✓ Found {len(buckets)} bucket(s):\n{bucket_info_str}"


@tool
def display_time_range() -> str:
    """Display today's time range that will be processed."""
    start_date, end_date = get_today_date_range()
    start_time, end_time = get_today_time_range()

    duration_timedelta = end_time - start_time
    duration_hours = duration_timedelta.total_seconds() / 3600

    console.print("\n[bold]Processing time range for today:[/bold]")
    console.print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M')}")
    console.print(f"End: {end_time.strftime('%Y-%m-%d %H:%M')}")
    console.print(f"Duration: {duration_hours:.1f} hour(s)")
    
    return f"Time range for today:\nStart: {start_time.strftime('%Y-%m-%d %H:%M')}\nEnd: {end_time.strftime('%Y-%m-%d %H:%M')}\nDuration: {duration_hours:.1f} hour(s)"


@tool
def fetch_timeline_data() -> str:
    """Fetch timeline data from all ActivityWatch buckets for today's time range. Must call initialize_clients and get_and_display_buckets first."""
    global _aw_client
    if _aw_client is None:
        return "❌ Error: Clients not initialized. Call initialize_clients first."
    
    # Get buckets and time range
    buckets = _aw_client.get_buckets()
    if not buckets:
        return "❌ No buckets available"
    
    start_time, end_time = get_today_time_range()
    
    console.print("\n[bold]Fetching timeline data...[/bold]")
    all_events = []
    events_summary = ""

    with console.status("[bold green]Fetching events from buckets..."):
        for bucket_id in buckets.keys():
            events = _aw_client.get_events(bucket_id, start_time, end_time)
            if events:
                console.print(f"✓ {bucket_id}: {len(events)} events")
                events_summary += f"✓ {bucket_id}: {len(events)} events\n"
                all_events.extend(events)
            else:
                console.print(f"- {bucket_id}: No events")
                events_summary += f"- {bucket_id}: No events\n"

    if not all_events:
        console.print(
            "[yellow]No timeline data found for the selected time period.[/yellow]"
        )
        return "❌ No timeline data found for the selected time period."

    console.print(f"\n[green]Total events collected: {len(all_events)}[/green]")
    return f"✓ Timeline data fetched successfully:\n{events_summary}Total events collected: {len(all_events)}"


@tool
def fetch_toggl_entries() -> str:
    """Fetch existing Toggl time entries for today. Must call initialize_clients first."""
    global _toggl_client
    
    start_date, end_date = get_today_date_range()
    toggl_entries = []
    
    if _toggl_client:
        console.print("\n[bold]Fetching existing Toggl time entries...[/bold]")
        try:
            with console.status("[bold green]Fetching Toggl entries..."):
                toggl_entries = _toggl_client.get_time_entries(start_date, end_date)
            console.print(
                f"[green]✓ Found {len(toggl_entries)} existing time entries[/green]"
            )
            return f"✓ Found {len(toggl_entries)} existing Toggl time entries"
        except Exception as e:
            console.print(f"[red]Error fetching Toggl entries: {e}[/red]")
            console.print(
                "[yellow]Continuing without existing time entries...[/yellow]"
            )
            return f"❌ Error fetching Toggl entries: {e}"
    else:
        return "⚠ Toggl client not available - continuing without existing time entries"


@tool
def process_timeline_with_llm() -> str:
    """Process timeline data with LLM to generate consolidated time entries. Must call initialize_clients, fetch_timeline_data, and fetch_toggl_entries first."""
    global _aw_client, _toggl_client, _processor
    
    if _aw_client is None or _processor is None:
        return "❌ Error: Clients not initialized. Call initialize_clients first."
    
    # Get the required data
    buckets = _aw_client.get_buckets()
    if not buckets:
        return "❌ No buckets available"
        
    start_time, end_time = get_today_time_range()
    start_date, end_date = get_today_date_range()
    
    # Fetch timeline data
    all_events = []
    for bucket_id in buckets.keys():
        events = _aw_client.get_events(bucket_id, start_time, end_time)
        if events:
            all_events.extend(events)
    
    if not all_events:
        return "❌ No timeline data available to process"
        
    # Fetch Toggl entries
    toggl_entries = []
    if _toggl_client:
        try:
            toggl_entries = _toggl_client.get_time_entries(start_date, end_date)
        except Exception as e:
            pass  # Continue without Toggl entries
    
    console.print(f"\n[bold]Processing timeline with {_processor.model}...[/bold]")

    with console.status("[bold green]LLM processing timeline..."):
        result = _processor.consolidate_timeline(
            all_events, toggl_entries, start_time, end_time
        )
    
    if result:
        # Store result globally for display function
        global _last_result
        _last_result = result
        return f"✓ Timeline processed successfully! Found {len(result.entries)} consolidated time entries."
    else:
        return "❌ Failed to process timeline with LLM"


@tool
def display_results() -> str:
    """Display the processed timeline results. Must call process_timeline_with_llm first."""
    global _last_result
    
    if _last_result is None:
        return "❌ No results to display. Call process_timeline_with_llm first."
    
    console.print("\n[bold green]✓ Timeline processed successfully![/bold green]")
    console.print("\n" + "=" * 50)
    console.print("[bold cyan]Processed Timeline:[/bold cyan]")

    results_text = ""
    
    # Display the structured results
    for entry in _last_result.entries:
        console.print(f"\n[cyan]{entry.description}[/cyan]")
        
        # Convert times to local timezone for display
        start_date_local, start_time_local = convert_time_to_local(entry.start_date, entry.start_time)
        end_date_local, end_time_local = convert_time_to_local(entry.end_date, entry.end_time)
        
        time_display = f"  Time: {start_date_local} {start_time_local} - {end_date_local} {end_time_local}"
        duration_display = f"  Duration: {entry.duration}"
        
        console.print(time_display)
        console.print(duration_display)
        
        results_text += f"\n{entry.description}\n{time_display}\n{duration_display}\n"
        
        if entry.project:
            project_display = f"  Project: {entry.project}"
            console.print(project_display)
            results_text += f"{project_display}\n"
        if entry.task:
            task_display = f"  Task: {entry.task}"
            console.print(task_display)
            results_text += f"{task_display}\n"

    return f"✓ Displayed {len(_last_result.entries)} time entries:{results_text}"


@tool
def save_results(output_file: str) -> str:
    """Save the processed timeline results to a JSON file. Must call process_timeline_with_llm first.
    
    Args:
        output_file: Path to the output JSON file where results will be saved
    """
    global _last_result
    
    if _last_result is None:
        return "❌ No results to save. Call process_timeline_with_llm first."
    
    try:
        with open(output_file, "w") as f:
            f.write(_last_result.model_dump_json(indent=2))
        console.print(f"\n[green]✓ Results saved to {output_file}[/green]")
        return f"✓ Results saved to {output_file}"
    except Exception as e:
        console.print(f"[red]Error saving to file: {e}[/red]")
        return f"❌ Error saving to file: {e}"


@tool
def run_full_workflow(model: str = None, aw_url: str = None, output_file: str = None, min_duration: int = None) -> str:
    """Run the complete timeline processing workflow from start to finish.
    
    Args:
        model: LLM model to use (default: from env or gpt-4o)
        aw_url: ActivityWatch server URL (default: from env or localhost:5600)
        output_file: Path to save results JSON file (optional)
        min_duration: Minimum activity duration in minutes to consider (default: 5)
    """
    try:
        # Initialize clients
        init_result = initialize_clients(aw_url)
        if "❌" in init_result:
            return init_result
        
        # Set model and min duration if provided
        global _processor
        if model and _processor:
            _processor.model = model
        if min_duration and _processor:
            _processor.min_duration_minutes = min_duration
        
        # Test connection
        conn_result = test_connection()
        if "❌" in conn_result:
            return conn_result
        
        # Get buckets
        buckets_result = get_and_display_buckets()
        if "❌" in buckets_result:
            return buckets_result
        
        # Display time range
        time_result = display_time_range()
        
        # Fetch timeline data
        timeline_result = fetch_timeline_data()
        if "❌" in timeline_result:
            return timeline_result
        
        # Fetch Toggl entries
        toggl_result = fetch_toggl_entries()
        
        # Process with LLM
        process_result = process_timeline_with_llm()
        if "❌" in process_result:
            return process_result
        
        # Display results
        display_result = display_results()
        
        # Save if output file specified
        save_result = ""
        if output_file:
            save_result = save_results(output_file)
        
        return f"✓ Complete workflow executed successfully!\n\n{init_result}\n{conn_result}\n{buckets_result}\n{time_result}\n{timeline_result}\n{toggl_result}\n{process_result}\n{display_result}\n{save_result}"
        
    except Exception as e:
        return f"❌ Error in workflow: {e}"