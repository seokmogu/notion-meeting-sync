from __future__ import annotations

from collections.abc import Iterator
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from notion_meeting_sync.state import SyncState


@pytest.fixture
def temp_state_file() -> Iterator[Path]:
    """Create a temporary directory and return path to state file (not created yet)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir) / "state.json"
        yield temp_path


@pytest.fixture
def sync_state(temp_state_file: Path) -> SyncState:
    """Create a SyncState instance with a temporary file."""
    return SyncState(state_file=temp_state_file)


class TestSyncStateInitialization:
    """Test state file creation and initialization."""

    def test_state_file_created_on_first_access(self, temp_state_file: Path) -> None:
        """State file should be auto-created with empty structure."""
        assert not temp_state_file.exists()
        state = SyncState(state_file=temp_state_file)
        # Trigger file creation by accessing state
        _ = state.get_last_poll_time()
        assert temp_state_file.exists()

    def test_state_file_has_correct_structure(self, temp_state_file: Path) -> None:
        """State file should have correct initial structure."""
        state = SyncState(state_file=temp_state_file)
        _ = state.get_last_poll_time()

        data = json.loads(temp_state_file.read_text(encoding="utf-8"))
        assert "last_poll_time" in data
        assert "synced_pages" in data
        assert "failed_pushes" in data
        assert data["last_poll_time"] is None
        assert data["synced_pages"] == {}
        assert data["failed_pushes"] == []

    def test_state_directory_created_if_missing(self) -> None:
        """Parent directory should be auto-created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "subdir" / "state.json"
            assert not state_file.parent.exists()
            state = SyncState(state_file=state_file)
            _ = state.get_last_poll_time()
            assert state_file.parent.exists()


class TestPageTracking:
    """Test synced page tracking."""

    def test_is_synced_returns_false_for_unsynced_page(self, sync_state: SyncState) -> None:
        """is_synced should return False for pages not in state."""
        assert not sync_state.is_synced("page-123")

    def test_mark_synced_adds_page(self, sync_state: SyncState) -> None:
        """mark_synced should add page to synced_pages."""
        metadata = {
            "title": "상품 프라이싱 논의 미팅",
            "file_path": "team/meetings/TA-2026-03-12-상품-프라이싱-논의-미팅.md",
            "last_edited_time": "2026-03-12T07:02:00Z",
        }
        sync_state.mark_synced("page-123", metadata)
        assert sync_state.is_synced("page-123")

    def test_mark_synced_stores_metadata(self, sync_state: SyncState) -> None:
        """mark_synced should store all metadata fields."""
        metadata = {
            "title": "상품 프라이싱 논의 미팅",
            "file_path": "team/meetings/TA-2026-03-12-상품-프라이싱-논의-미팅.md",
            "last_edited_time": "2026-03-12T07:02:00Z",
        }
        sync_state.mark_synced("page-123", metadata)

        # Reload state from file to verify persistence
        state = SyncState(state_file=sync_state.state_file)
        assert state.is_synced("page-123")

    def test_mark_synced_sets_synced_at_timestamp(self, sync_state: SyncState) -> None:
        """mark_synced should set synced_at timestamp."""
        metadata = {
            "title": "Test Page",
            "file_path": "test.md",
            "last_edited_time": "2026-03-12T07:02:00Z",
        }
        before = datetime.now().isoformat()
        sync_state.mark_synced("page-123", metadata)
        after = datetime.now().isoformat()

        payload = json.loads(sync_state.state_file.read_text(encoding="utf-8"))
        synced_at = payload["synced_pages"]["page-123"]["synced_at"]
        assert before <= synced_at <= after

    def test_multiple_pages_can_be_synced(self, sync_state: SyncState) -> None:
        """Multiple pages should be trackable independently."""
        metadata1 = {
            "title": "Page 1",
            "file_path": "page1.md",
            "last_edited_time": "2026-03-12T07:02:00Z",
        }
        metadata2 = {
            "title": "Page 2",
            "file_path": "page2.md",
            "last_edited_time": "2026-03-12T08:00:00Z",
        }
        sync_state.mark_synced("page-1", metadata1)
        sync_state.mark_synced("page-2", metadata2)

        assert sync_state.is_synced("page-1")
        assert sync_state.is_synced("page-2")


class TestPollTime:
    """Test last poll time tracking."""

    def test_get_last_poll_time_returns_none_initially(self, sync_state: SyncState) -> None:
        """get_last_poll_time should return None initially."""
        assert sync_state.get_last_poll_time() is None

    def test_update_poll_time_sets_timestamp(self, sync_state: SyncState) -> None:
        """update_poll_time should set last_poll_time."""
        before = datetime.now().isoformat()
        sync_state.update_poll_time()
        after = datetime.now().isoformat()

        poll_time = sync_state.get_last_poll_time()
        assert poll_time is not None
        assert before <= poll_time <= after

    def test_poll_time_persists_across_instances(self, sync_state: SyncState) -> None:
        """Poll time should persist when reloading state."""
        sync_state.update_poll_time()
        poll_time_1 = sync_state.get_last_poll_time()

        # Create new instance with same file
        state2 = SyncState(state_file=sync_state.state_file)
        poll_time_2 = state2.get_last_poll_time()

        assert poll_time_1 == poll_time_2


class TestFailedPushes:
    """Test failed push tracking."""

    def test_get_failed_pushes_returns_empty_list_initially(self, sync_state: SyncState) -> None:
        """get_failed_pushes should return empty list initially."""
        assert sync_state.get_failed_pushes() == []

    def test_add_failed_push_records_error(self, sync_state: SyncState) -> None:
        """add_failed_push should record page and error."""
        sync_state.add_failed_push("page-123", "Connection timeout")
        failed = sync_state.get_failed_pushes()

        assert len(failed) == 1
        assert failed[0]["page_id"] == "page-123"
        assert failed[0]["error"] == "Connection timeout"

    def test_failed_push_has_timestamp(self, sync_state: SyncState) -> None:
        """Failed push should include timestamp."""
        before = datetime.now().isoformat()
        sync_state.add_failed_push("page-123", "Error")
        after = datetime.now().isoformat()

        failed = sync_state.get_failed_pushes()
        assert "timestamp" in failed[0]
        assert before <= failed[0]["timestamp"] <= after

    def test_multiple_failed_pushes(self, sync_state: SyncState) -> None:
        """Multiple failed pushes should be tracked."""
        sync_state.add_failed_push("page-1", "Error 1")
        sync_state.add_failed_push("page-2", "Error 2")

        failed = sync_state.get_failed_pushes()
        assert len(failed) == 2

    def test_clear_failed_push_removes_entry(self, sync_state: SyncState) -> None:
        """clear_failed_push should remove specific failed push."""
        sync_state.add_failed_push("page-1", "Error 1")
        sync_state.add_failed_push("page-2", "Error 2")

        sync_state.clear_failed_push("page-1")
        failed = sync_state.get_failed_pushes()

        assert len(failed) == 1
        assert failed[0]["page_id"] == "page-2"

    def test_clear_failed_push_nonexistent_page(self, sync_state: SyncState) -> None:
        """clear_failed_push should handle nonexistent page gracefully."""
        sync_state.add_failed_push("page-1", "Error")
        sync_state.clear_failed_push("page-999")  # Should not raise

        failed = sync_state.get_failed_pushes()
        assert len(failed) == 1

    def test_failed_pushes_persist_across_instances(self, sync_state: SyncState) -> None:
        """Failed pushes should persist when reloading state."""
        sync_state.add_failed_push("page-123", "Error")

        state2 = SyncState(state_file=sync_state.state_file)
        failed = state2.get_failed_pushes()

        assert len(failed) == 1
        assert failed[0]["page_id"] == "page-123"


class TestFilePersistence:
    """Test that state persists correctly to file."""

    def test_state_persists_to_file(self, temp_state_file: Path) -> None:
        """All state changes should persist to file."""
        state1 = SyncState(state_file=temp_state_file)
        state1.update_poll_time()
        state1.mark_synced(
            "page-1",
            {
                "title": "Test",
                "file_path": "test.md",
                "last_edited_time": "2026-03-12T07:02:00Z",
            },
        )
        state1.add_failed_push("page-2", "Error")

        # Load fresh instance
        state2 = SyncState(state_file=temp_state_file)
        assert state2.get_last_poll_time() is not None
        assert state2.is_synced("page-1")
        assert len(state2.get_failed_pushes()) == 1

    def test_concurrent_read_access(self, sync_state: SyncState) -> None:
        """Multiple readers should work concurrently."""
        sync_state.update_poll_time()

        state2 = SyncState(state_file=sync_state.state_file)
        state3 = SyncState(state_file=sync_state.state_file)

        # All should be able to read
        assert state2.get_last_poll_time() is not None
        assert state3.get_last_poll_time() is not None
