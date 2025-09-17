"""
Timeline processor for ActivityWatch data
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from litellm import completion
from rich.console import Console

from entry import TimeEntryList

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
        self.model = model or os.getenv("LLM_MODEL", "gpt-5-nano")
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
