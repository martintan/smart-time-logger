"""
Timeline processor for ActivityWatch data
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Protocol, Sequence, runtime_checkable

from litellm import completion
from litellm.utils import token_counter
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


@runtime_checkable
class _ChoiceMessage(Protocol):
    content: Optional[str]


@runtime_checkable
class _Choice(Protocol):
    message: Optional[_ChoiceMessage]
    content: Optional[str]


@runtime_checkable
class _CompletionResponse(Protocol):
    choices: Sequence[_Choice]


class TimelineProcessor:
    """Process timeline data using LLM"""

    def __init__(self, model: Optional[str] = None, min_duration_minutes: Optional[int] = None):
        self.model = model or os.getenv("LLM_MODEL", "gpt-5-nano")
        self.min_duration_minutes = min_duration_minutes or int(os.getenv("MIN_ACTIVITY_DURATION_MINUTES", "5"))
        self.merge_gap_seconds = int(os.getenv("EVENT_MERGE_GAP_SECONDS", "180"))
        self.max_merge_gap = max(self.merge_gap_seconds, 0)

    def compress_events(self, timeline_data: List[Dict]) -> List[Dict]:
        """Aggregate successive events with matching context to shrink token usage."""

        # Canonicalise the raw ActivityWatch records so structurally identical events
        # generate the same signature regardless of noisy metadata ordering.
        if not timeline_data:
            return []

        normalized: List[Dict] = []
        for event in timeline_data:
            if not isinstance(event, dict):
                continue

            timestamp_raw = event.get("timestamp")
            if not isinstance(timestamp_raw, str):
                continue

            normalized_ts = timestamp_raw.replace("Z", "+00:00")
            try:
                start_dt = datetime.fromisoformat(normalized_ts)
            except ValueError:
                continue

            duration_raw = event.get("duration", 0)
            if isinstance(duration_raw, (int, float)):
                duration_seconds = max(float(duration_raw), 0.0)
            else:
                duration_seconds = 0.0

            raw_data = event.get("data")
            if isinstance(raw_data, dict):
                data_blob: Dict[str, object] = raw_data
            else:
                data_blob = {}

            trimmed_data: Dict[str, object] = {}
            for key, value in data_blob.items():
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                if value == [] or value == {}:
                    continue
                trimmed_data[key] = value

            bucket_id = event.get("bucket_id") or trimmed_data.get("bucket_id")
            if bucket_id:
                trimmed_data.setdefault("_bucket", bucket_id)

            signature_payload: Dict[str, object] = {"bucket": bucket_id, "data": trimmed_data}
            try:
                signature = json.dumps(signature_payload, sort_keys=True, default=str)
            except TypeError:
                continue

            end_dt = start_dt + timedelta(seconds=duration_seconds)

            normalized.append(
                {
                    "start": start_dt,
                    "end": end_dt if duration_seconds else start_dt,
                    "duration": duration_seconds,
                    "data": trimmed_data,
                    "signature": signature,
                    "bucket_id": bucket_id,
                    "first_id": event.get("id"),
                    "last_id": event.get("id"),
                    "count": 1,
                }
            )

        if not normalized:
            return []

        normalized.sort(key=lambda item: item["start"])

        compressed: List[Dict] = []
        current = normalized[0]

        for item in normalized[1:]:
            # Merge adjacent events when their signature matches and the idle gap is
            # less than the configured tolerance, effectively coalescing bursts of
            # identical work into one span.
            if current["signature"] == item["signature"]:
                gap_seconds = (item["start"] - current["end"]).total_seconds()
                if gap_seconds < 0:
                    gap_seconds = 0.0
                if gap_seconds <= self.max_merge_gap:
                    current["duration"] += item["duration"]
                    if item["end"] > current["end"]:
                        current["end"] = item["end"]
                    if item["start"] > current["end"]:
                        current["end"] = item["start"]
                    current["count"] += 1
                    if item.get("last_id") is not None:
                        current["last_id"] = item["last_id"]
                    continue

            compressed.append(current)
            current = item

        compressed.append(current)

        result: List[Dict] = []
        for item in compressed:
            duration_span = (item["end"] - item["start"]).total_seconds()
            duration_value = max(item["duration"], duration_span)
            event_data = dict(item["data"])

            # Attach summary metadata so the prompt still conveys how many samples
            # were merged and where the block ends.
            if item["count"] > 1:
                event_data.setdefault("_merged_events", item["count"])
            if item.get("last_id") and item.get("first_id") != item.get("last_id"):
                event_data.setdefault("_last_id", item["last_id"])

            result_event: Dict[str, object] = {
                "id": item.get("first_id", 0),
                "timestamp": item["start"].isoformat(),
                "duration": round(duration_value, 3),
                "data": event_data,
            }

            if item.get("bucket_id"):
                result_event["bucket_id"] = item["bucket_id"]

            if duration_span > 0:
                event_data.setdefault("_end", item["end"].isoformat())

            result.append(result_event)

        return result

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

    @staticmethod
    def _extract_choice_content(candidate: object) -> Optional[str]:
        if isinstance(candidate, dict):
            choices_value = candidate.get("choices")
            if isinstance(choices_value, list) and choices_value:
                first_choice = choices_value[0]
                if isinstance(first_choice, dict):
                    message_candidate = first_choice.get("message")
                    if isinstance(message_candidate, dict):
                        content_value = message_candidate.get("content")
                        if isinstance(content_value, str):
                            return content_value
                    content_fallback = first_choice.get("content")
                    if isinstance(content_fallback, str):
                        return content_fallback
                if isinstance(first_choice, str):
                    return first_choice

        if isinstance(candidate, _CompletionResponse):
            choices_seq = candidate.choices
            if choices_seq:
                first_choice = choices_seq[0]
                message_obj = first_choice.message
                if isinstance(message_obj, _ChoiceMessage):
                    message_content = message_obj.content
                    if isinstance(message_content, str):
                        return message_content
                choice_content = first_choice.content
                if isinstance(choice_content, str):
                    return choice_content

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
            content_text = self._extract_choice_content(response)
            if content_text is None:
                console.print("[red]LLM response did not include message content.[/red]")
                return None
            json_response = json.loads(content_text)
            if "entries" in json_response:
                return TimeEntryList.model_validate(json_response)
            if isinstance(json_response, list):
                return TimeEntryList(entries=json_response)
            console.print("[red]Unexpected response format from LLM[/red]")
            return None
        except Exception as err:
            console.print(f"[red]Error processing with LLM: {err}[/red]")
            return None
