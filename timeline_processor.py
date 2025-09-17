"""
Timeline processor for ActivityWatch data
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from litellm import completion, token_counter
from rich.console import Console

from entry import TimeEntryList

console = Console()

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
        self.min_duration_minutes = min_duration_minutes or int(os.getenv("MIN_ACTIVITY_DURATION_MINUTES", "5"))

    def _build_prompt(
        self,
        timeline_data: List[Dict],
        toggl_entries: List[Dict],
    ) -> Optional[str]:
        """Construct the prompt combining static instructions and captured events."""
        try:
            with open("INFER_TIME_ENTRY_LOGGING.md", "r", encoding="utf-8") as fh:
                base_prompt = fh.read()
        except FileNotFoundError:
            console.print("[red]INFER_TIME_ENTRY_LOGGING.md file not found[/red]")
            return None

        try:
            with open("ACTIVITY.md", "r", encoding="utf-8") as fh:
                user_context = fh.read()
        except FileNotFoundError:
            user_context = "No additional user context provided."

        formatted_events: List[Dict] = []
        for event in timeline_data:
            formatted_events.append(
                {
                    "id": event.get("id", 0),
                    "timestamp": event.get("timestamp"),
                    "duration": event.get("duration", 0),
                    "data": event.get("data", {}),
                }
            )

        return FULL_PROMPT_TEMPLATE.format(
            base_prompt=base_prompt,
            min_duration_minutes=self.min_duration_minutes,
            user_context=user_context,
            toggl_entries=json.dumps(toggl_entries, indent=2),
            timeline_data=json.dumps(formatted_events, indent=2),
        )

    def build_prompt(
        self,
        timeline_data: List[Dict],
        toggl_entries: List[Dict],
    ) -> Optional[str]:
        """Expose prompt construction to callers."""

        return self._build_prompt(timeline_data, toggl_entries)

    def estimate_input_tokens(
        self,
        timeline_data: List[Dict],
        toggl_entries: List[Dict],
        start_time: datetime,
        end_time: datetime,
        prompt: Optional[str] = None,
    ) -> Optional[int]:
        """Estimate the number of tokens sent to the LLM."""
        prompt_text = prompt or self._build_prompt(timeline_data, toggl_entries)
        if prompt_text is None:
            return None

        try:
            usage = token_counter(
                model=self.model,
                messages=[{"role": "user", "content": prompt_text}],
            )
        except Exception as err:  # pragma: no cover - runtime env specific
            console.print(f"[yellow]Unable to estimate token usage: {err}[/yellow]")
            return None

        if isinstance(usage, int):
            return usage
        if isinstance(usage, dict):
            for key in ("input_tokens", "prompt_tokens", "token_count", "total_tokens"):
                value = usage.get(key)
                if isinstance(value, (int, float)):
                    return int(value)
            nested = usage.get("usage")
            if isinstance(nested, dict):
                for key in ("input_tokens", "prompt_tokens", "total_tokens"):
                    value = nested.get(key)
                    if isinstance(value, (int, float)):
                        return int(value)
        return None

    def consolidate_timeline(
        self,
        timeline_data: List[Dict],
        toggl_entries: List[Dict],
        start_time: datetime,
        end_time: datetime,
    ) -> Optional[TimeEntryList]:
        """Use LLM to consolidate and summarize timeline data"""
        prompt = self._build_prompt(timeline_data, toggl_entries)
        if prompt is None:
            return None

        try:
            response = completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=1,
                response_format={"type": "json_object"},
            )
            json_response = json.loads(response.choices[0].message.content)
            if "entries" in json_response:
                return TimeEntryList.model_validate(json_response)
            if isinstance(json_response, list):
                return TimeEntryList(entries=json_response)
            console.print("[red]Unexpected response format from LLM[/red]")
            return None
        except Exception as err:
            console.print(f"[red]Error processing with LLM: {err}[/red]")
            return None
