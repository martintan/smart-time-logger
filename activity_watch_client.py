#!/usr/bin/env python3
"""
ActivityWatch Client
Client for interacting with ActivityWatch API
"""

import os
from datetime import datetime, timezone
from typing import Dict, List, Any
import requests
from rich.console import Console

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

