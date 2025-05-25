from typing import List, Optional

from pydantic import BaseModel, Field


class TimeEntry(BaseModel):
    description: str = Field(
        ..., description="Concise summary of the primary activity."
    )
    start_date: str = Field(
        ...,
        description="Start date in YYYY-MM-DD format.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    start_time: str = Field(
        ...,
        description="Start time in HH:MM:SS format (24-hour).",
        pattern=r"^\d{2}:\d{2}:\d{2}$",
    )
    end_date: str = Field(
        ...,
        description="End date in YYYY-MM-DD format.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    end_time: str = Field(
        ...,
        description="End time in HH:MM:SS format (24-hour).",
        pattern=r"^\d{2}:\d{2}:\d{2}$",
    )
    duration: str = Field(
        ..., description="Duration in HH:MM:SS format.", pattern=r"^\d{2}:\d{2}:\d{2}$"
    )
    project: Optional[str] = Field(
        None, description="Inferred project name, if applicable."
    )
    task: Optional[str] = Field(
        None, description="Inferred task name or ID, if applicable."
    )


class TimeEntryList(BaseModel):
    entries: List[TimeEntry]
