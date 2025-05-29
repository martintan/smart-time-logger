"""
Tool functions for ActivityWatch Timeline Processor
"""

import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from smolagents import tool

from activity_watch_client import ActivityWatchClient
from entry import TimeEntry
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
def initialize_clients(aw_url: Optional[str] = None) -> str:
    """Initialize ActivityWatch, Toggl clients and timeline processor. This should be called first before using other functions.

    Args:
        aw_url: ActivityWatch server URL (default: from env or localhost:5600)
    """
    global _aw_client, _toggl_client, _processor

    # Initialize clients
    _aw_client = ActivityWatchClient(aw_url) if aw_url else ActivityWatchClient()
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
def fetch_time_entries(
    date: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> str:
    """Fetch existing Toggl time entries for a specific time range. Must call initialize_clients first.

    Args:
        date: Date in YYYY-MM-DD format (default: today)
        start_time: Start time in HH:MM format (default: work day start)
        end_time: End time in HH:MM format (default: current time)
    """
    global _toggl_client

    if date is None:
        # Use today's date range
        start_date, end_date = get_today_date_range()
    else:
        # Use specified date
        start_date = end_date = date

    # Initialize variables for potential use in filtering
    base_date = None
    start_time_obj = None
    end_time_obj = None
    start_datetime = None
    end_datetime = None

    # If specific times are provided, we need to construct the full datetime range
    if start_time or end_time:

        try:
            # Parse the date
            base_date = datetime.strptime(date or start_date, "%Y-%m-%d").date()

            # Parse start time
            if start_time:
                start_time_obj = datetime.strptime(start_time, "%H:%M").time()
                start_datetime = datetime.combine(base_date, start_time_obj)
            else:
                # Use work day start
                work_day_start, _ = get_today_time_range()
                start_datetime = work_day_start.replace(
                    year=base_date.year, month=base_date.month, day=base_date.day
                )

            # Parse end time
            if end_time:
                end_time_obj = datetime.strptime(end_time, "%H:%M").time()
                end_datetime = datetime.combine(base_date, end_time_obj)

                # Handle case where end time is next day (e.g., 21:00 to 01:30)
                if start_datetime is not None and end_datetime < start_datetime:
                    end_datetime = end_datetime.replace(day=base_date.day + 1)
            else:
                # Use current time or work day end
                _, work_day_end = get_today_time_range()
                end_datetime = work_day_end.replace(
                    year=base_date.year, month=base_date.month, day=base_date.day
                )

            # Convert back to date strings for the API
            if start_datetime is not None:
                start_date = start_datetime.strftime("%Y-%m-%d")
            if end_datetime is not None:
                end_date = end_datetime.strftime("%Y-%m-%d")

        except ValueError as e:
            return f"❌ Error parsing time format: {e}. Use HH:MM format for times and YYYY-MM-DD for date."

    toggl_entries = []

    if _toggl_client:
        time_range_desc = f"{date or 'today'}"
        if start_time or end_time:
            time_range_desc += (
                f" from {start_time or 'work start'} to {end_time or 'current time'}"
            )

        console.print(
            f"\n[bold]Fetching Toggl time entries for {time_range_desc}...[/bold]"
        )
        try:
            with console.status("[bold green]Fetching Toggl entries..."):
                toggl_entries = _toggl_client.get_time_entries(start_date, end_date)

            # Filter entries by specific time range if provided
            if (start_time or end_time) and toggl_entries:
                filtered_entries = []
                for entry in toggl_entries:
                    # Parse entry time and check if it falls within the specified range
                    try:
                        entry_start = datetime.fromisoformat(
                            entry.get("start", "").replace("Z", "+00:00")
                        )
                        entry_end = (
                            datetime.fromisoformat(
                                entry.get("stop", "").replace("Z", "+00:00")
                            )
                            if entry.get("stop")
                            else None
                        )

                        # Convert to local time for comparison
                        entry_start_local = entry_start.astimezone()

                        # Check if entry overlaps with specified time range
                        if (
                            start_time
                            and base_date is not None
                            and start_time_obj is not None
                        ):
                            range_start = datetime.combine(
                                base_date, start_time_obj
                            ).replace(tzinfo=entry_start_local.tzinfo)
                            if entry_start_local < range_start:
                                continue

                        if (
                            end_time
                            and entry_end
                            and base_date is not None
                            and end_time_obj is not None
                        ):
                            range_end = datetime.combine(
                                base_date, end_time_obj
                            ).replace(tzinfo=entry_start_local.tzinfo)
                            if (
                                end_datetime is not None
                                and start_datetime is not None
                                and end_datetime < start_datetime
                            ):  # Next day case
                                range_end = range_end.replace(day=base_date.day + 1)
                            entry_end_local = entry_end.astimezone()
                            if entry_end_local > range_end:
                                continue

                        filtered_entries.append(entry)
                    except (ValueError, KeyError):
                        # If we can't parse the entry time, include it to be safe
                        filtered_entries.append(entry)

                toggl_entries = filtered_entries

            console.print(
                f"[green]✓ Found {len(toggl_entries)} time entries for {time_range_desc}[/green]"
            )
            return (
                f"✓ Found {len(toggl_entries)} Toggl time entries for {time_range_desc}"
            )
        except Exception as e:
            console.print(f"[red]Error fetching Toggl entries: {e}[/red]")
            console.print(
                "[yellow]Continuing without existing time entries...[/yellow]"
            )
            return f"❌ Error fetching Toggl entries: {e}"
    else:
        return "⚠ Toggl client not available - continuing without existing time entries"


@tool
def create_time_entries(
    entries: List[TimeEntry],
) -> str:
    """Create time entries in Toggl workspace from processed timeline results. Must call initialize_clients first.
    
    Args:
        entries: List of TimeEntry objects to create in Toggl workspace.
                Each entry should have: description, start_date, start_time, end_date, end_time, duration, 
                and optionally project and task.
    """
    global _toggl_client
    
    if _toggl_client is None:
        return "❌ Error: Toggl client not initialized. Call initialize_clients first."
    
    try:
        from datetime import datetime, timezone
        
        if not entries:
            return "❌ Error: No entries provided to create."
        
        console.print(f"\n[bold]Creating {len(entries)} time entries in Toggl...[/bold]")
        
        created_entries = []
        failed_entries = []
        
        with console.status("[bold green]Creating Toggl entries..."):
            for i, entry in enumerate(entries):
                try:
                    # Extract required fields from TimeEntry object
                    description = entry.description
                    start_date = entry.start_date
                    start_time = entry.start_time
                    end_date = entry.end_date
                    end_time = entry.end_time
                    duration_str = entry.duration
                    
                    if not all([description, start_date, start_time, duration_str]):
                        failed_entries.append(f"Entry {i+1}: Missing required fields")
                        continue
                    
                    # Parse start datetime
                    start_datetime_str = f"{start_date} {start_time}"
                    try:
                        start_datetime = datetime.strptime(start_datetime_str, "%Y-%m-%d %H:%M:%S")
                        # Convert to UTC ISO format
                        start_datetime_utc = start_datetime.replace(tzinfo=timezone.utc)
                        start_iso = start_datetime_utc.isoformat()
                    except ValueError as e:
                        failed_entries.append(f"Entry {i+1}: Invalid datetime format - {e}")
                        continue
                    
                    # Parse duration from HH:MM:SS format to seconds
                    try:
                        time_parts = duration_str.split(":")
                        if len(time_parts) == 3:
                            hours, minutes, seconds = map(int, time_parts)
                            duration_seconds = hours * 3600 + minutes * 60 + seconds
                        else:
                            failed_entries.append(f"Entry {i+1}: Invalid duration format '{duration_str}'. Expected HH:MM:SS")
                            continue
                    except (ValueError, IndexError) as e:
                        failed_entries.append(f"Entry {i+1}: Duration parsing error - {e}")
                        continue
                    
                    # Look up project ID if project name provided
                    project_id = None
                    project_name = entry.project
                    if project_name:
                        project = _toggl_client.find_project_by_name(project_name)
                        if project:
                            project_id = project["id"]
                        else:
                            console.print(f"[yellow]Warning: Project '{project_name}' not found for entry {i+1}[/yellow]")
                    
                    # Create the time entry
                    created_entry = _toggl_client.create_time_entry(
                        description=description,
                        start=start_iso,
                        duration=duration_seconds,
                        project_id=project_id,
                    )
                    
                    created_entries.append(created_entry)
                    console.print(f"✓ Created entry {i+1}: {description} ({duration_str})")
                    
                except Exception as e:
                    failed_entries.append(f"Entry {i+1}: {str(e)}")
                    console.print(f"[red]✗ Failed to create entry {i+1}: {e}[/red]")
        
        # Summary
        success_count = len(created_entries)
        failure_count = len(failed_entries)
        
        console.print(f"\n[green]✓ Successfully created {success_count} time entries[/green]")
        if failure_count > 0:
            console.print(f"[red]✗ Failed to create {failure_count} time entries[/red]")
            for failure in failed_entries:
                console.print(f"  [red]• {failure}[/red]")
        
        result_summary = f"✓ Created {success_count} time entries in Toggl"
        if failure_count > 0:
            result_summary += f" ({failure_count} failed)"
            for failure in failed_entries:
                result_summary += f"\n• {failure}"
        
        return result_summary
        
    except Exception as e:
        console.print(f"[red]Error creating time entries: {e}[/red]")
        return f"❌ Error creating time entries: {e}"


@tool
def process_timeline_with_llm() -> str:
    """Process timeline data with LLM to generate consolidated time entries. Must call initialize_clients, fetch_timeline_data, and fetch_time_entries first."""
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
        start_date_local, start_time_local = convert_time_to_local(
            entry.start_date, entry.start_time
        )
        end_date_local, end_time_local = convert_time_to_local(
            entry.end_date, entry.end_time
        )

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
def run_full_workflow(
    model: Optional[str] = None,
    aw_url: Optional[str] = None,
    output_file: Optional[str] = None,
    min_duration: Optional[int] = None,
) -> str:
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
        init_str = str(init_result)
        if "❌" in init_str:
            return init_str

        # Set model and min duration if provided
        global _processor
        if model and _processor:
            _processor.model = model
        if min_duration and _processor:
            _processor.min_duration_minutes = min_duration

        # Test connection
        conn_result = test_connection()
        conn_str = str(conn_result)
        if "❌" in conn_str:
            return conn_str

        # Get buckets
        buckets_result = get_and_display_buckets()
        buckets_str = str(buckets_result)
        if "❌" in buckets_str:
            return buckets_str

        # Display time range
        time_result = display_time_range()

        # Fetch timeline data
        timeline_result = fetch_timeline_data()
        timeline_str = str(timeline_result)
        if "❌" in timeline_str:
            return timeline_str

        # Fetch Toggl entries
        toggl_result = fetch_time_entries()

        # Process with LLM
        process_result = process_timeline_with_llm()
        process_str = str(process_result)
        if "❌" in process_str:
            return process_str

        # Display results
        display_result = display_results()

        # Save if output file specified
        save_result = ""
        if output_file:
            save_result = save_results(output_file)

        return f"✓ Complete workflow executed successfully!\n\n{init_str}\n{conn_str}\n{buckets_str}\n{str(time_result)}\n{timeline_str}\n{str(toggl_result)}\n{process_str}\n{str(display_result)}\n{str(save_result)}"

    except Exception as e:
        return f"❌ Error in workflow: {e}"
