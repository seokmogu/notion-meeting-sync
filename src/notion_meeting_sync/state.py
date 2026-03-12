from __future__ import annotations

import fcntl
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SyncState:
    """Manages synchronization state for Notion meeting pages.

    Tracks which pages have been synced, last poll time, and failed push attempts.
    Uses file-based JSON storage with fcntl locking for concurrent access safety.
    """

    def __init__(self, state_file: Path | None = None) -> None:
        """Initialize SyncState with optional custom state file path.

        Args:
            state_file: Path to state JSON file. Defaults to ~/.config/notion-meeting-sync/state.json
        """
        if state_file is None:
            state_file = Path.home() / ".config" / "notion-meeting-sync" / "state.json"

        self.state_file = state_file
        self._ensure_state_file_exists()

    def _ensure_state_file_exists(self) -> None:
        """Create state file and parent directory if they don't exist."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.state_file.exists():
            initial_state: dict[str, Any] = {
                "last_poll_time": None,
                "synced_pages": {},
                "failed_pushes": [],
            }
            self._write_state(initial_state)

    def _load_state(self) -> dict[str, Any]:
        """Load state from file with exclusive lock.

        Returns:
            State dictionary with last_poll_time, synced_pages, and failed_pushes.
        """
        if not self.state_file.exists():
            return {
                "last_poll_time": None,
                "synced_pages": {},
                "failed_pushes": [],
            }

        with self.state_file.open("r+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
            try:
                content = f.read()
                if not content:
                    return {
                        "last_poll_time": None,
                        "synced_pages": {},
                        "failed_pushes": [],
                    }
                return json.loads(content)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _write_state(self, state: dict[str, Any]) -> None:
        """Write state to file with exclusive lock.

        Uses atomic write pattern: write to temp file, then rename.

        Args:
            state: State dictionary to write.
        """
        # Ensure file exists for locking
        if not self.state_file.exists():
            self.state_file.touch()

        with self.state_file.open("r+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock for writing
            try:
                f.seek(0)
                json.dump(state, f, indent=2, ensure_ascii=False)
                f.truncate()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def is_synced(self, page_id: str) -> bool:
        """Check if a page has been synced.

        Args:
            page_id: Notion page ID.

        Returns:
            True if page is in synced_pages, False otherwise.
        """
        state = self._load_state()
        return page_id in state.get("synced_pages", {})

    def mark_synced(self, page_id: str, metadata: dict[str, str]) -> None:
        """Mark a page as synced with metadata.

        Args:
            page_id: Notion page ID.
            metadata: Dictionary with title, file_path, last_edited_time.
        """
        state = self._load_state()
        synced_pages = state.get("synced_pages", {})

        synced_pages[page_id] = {
            "title": metadata.get("title", ""),
            "file_path": metadata.get("file_path", ""),
            "last_edited_time": metadata.get("last_edited_time", ""),
            "synced_at": datetime.now().isoformat(),
        }

        state["synced_pages"] = synced_pages
        self._write_state(state)

    def get_last_poll_time(self) -> str | None:
        """Get the last poll time.

        Returns:
            ISO 8601 timestamp string or None if never polled.
        """
        state = self._load_state()
        return state.get("last_poll_time")

    def update_poll_time(self) -> None:
        """Update last poll time to current time."""
        state = self._load_state()
        state["last_poll_time"] = datetime.now().isoformat()
        self._write_state(state)

    def add_failed_push(self, page_id: str, error: str) -> None:
        """Record a failed push attempt.

        Args:
            page_id: Notion page ID.
            error: Error message describing the failure.
        """
        state = self._load_state()
        failed_pushes = state.get("failed_pushes", [])

        failed_pushes.append(
            {
                "page_id": page_id,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            }
        )

        state["failed_pushes"] = failed_pushes
        self._write_state(state)

    def get_failed_pushes(self) -> list[dict[str, str]]:
        """Get all failed push attempts.

        Returns:
            List of failed push records with page_id, error, and timestamp.
        """
        state = self._load_state()
        return state.get("failed_pushes", [])

    def clear_failed_push(self, page_id: str) -> None:
        """Remove a failed push record for a specific page.

        Args:
            page_id: Notion page ID to clear from failed pushes.
        """
        state = self._load_state()
        failed_pushes = state.get("failed_pushes", [])

        # Filter out the page_id
        state["failed_pushes"] = [fp for fp in failed_pushes if fp.get("page_id") != page_id]

        self._write_state(state)
