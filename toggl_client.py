import os
import requests
from typing import Dict, List, Optional, Any


class TogglClient:
    """Simple Toggl Track API client for basic time tracking operations."""

    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize Toggl client.

        Args:
            api_token: Toggl API token. If not provided, will look for TOGGL_API_TOKEN env var.
        """
        self.api_token = api_token or os.getenv("TOGGL_API_TOKEN")
        if not self.api_token:
            raise ValueError(
                "Toggl API token is required. Set TOGGL_API_TOKEN environment variable or pass api_token parameter."
            )

        self.base_url = "https://api.track.toggl.com/api/v9"
        self.session = requests.Session()
        self.session.auth = (self.api_token, "api_token")
        self.session.headers.update({"Content-Type": "application/json"})

        # Cache for user info
        self._user_info = None
        self._workspace_id = None

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make HTTP request to Toggl API."""
        url = f"{self.base_url}/{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_current_user(self) -> Dict[str, Any]:
        """Get current user information including workspace details."""
        if self._user_info is None:
            self._user_info = self._make_request("GET", "me")
            # Cache the workspace ID for convenience
            if self._user_info.get("default_workspace_id"):
                self._workspace_id = self._user_info["default_workspace_id"]
        return self._user_info

    @property
    def workspace_id(self) -> int:
        """Get the user's default workspace ID."""
        if self._workspace_id is None:
            user_info = self.get_current_user()
            self._workspace_id = user_info["default_workspace_id"]
        return self._workspace_id

    def get_time_entries(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get time entries for the current user.

        Args:
            start_date: Start date in ISO format (YYYY-MM-DD). Defaults to today.
            end_date: End date in ISO format (YYYY-MM-DD). Defaults to today.

        Returns:
            List of time entries.
        """
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        return self._make_request("GET", "me/time_entries", params=params)

    def create_time_entry(
        self,
        description: str,
        start: str,
        duration: int,
        project_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new time entry.

        Args:
            description: Description of the time entry.
            start: Start time in ISO format (e.g., "2023-01-01T09:00:00Z").
            duration: Duration in seconds.
            project_id: Optional project ID.
            tag_ids: Optional list of tag IDs.

        Returns:
            Created time entry data.
        """
        data = {
            "description": description,
            "start": start,
            "duration": duration,
            "workspace_id": self.workspace_id,
            "created_with": "smart-time-logger",
        }

        if project_id:
            data["project_id"] = project_id
        if tag_ids:
            data["tag_ids"] = tag_ids

        return self._make_request(
            "POST", f"workspaces/{self.workspace_id}/time_entries", json=data
        )

    def get_projects(self) -> List[Dict[str, Any]]:
        """Get all projects in the workspace."""
        try:
            return self._make_request("GET", f"workspaces/{self.workspace_id}/projects")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return []  # No projects found
            raise

    def get_tags(self) -> List[Dict[str, Any]]:
        """Get all tags in the workspace."""
        try:
            return self._make_request("GET", f"workspaces/{self.workspace_id}/tags")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return []  # No tags found
            raise

    def find_project_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a project by name (case-insensitive)."""
        projects = self.get_projects()
        name_lower = name.lower()
        for project in projects:
            if project["name"].lower() == name_lower:
                return project
        return None

    def find_tag_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a tag by name (case-insensitive)."""
        tags = self.get_tags()
        name_lower = name.lower()
        for tag in tags:
            if tag["name"].lower() == name_lower:
                return tag
        return None
