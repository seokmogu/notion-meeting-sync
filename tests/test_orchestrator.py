from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from notion_meeting_sync.config import Settings
from notion_meeting_sync.converter import MeetingMetadata
from notion_meeting_sync.fetcher import MeetingDocument
from notion_meeting_sync.orchestrator import SyncOrchestrator
from notion_meeting_sync.poller import PageInfo
from notion_meeting_sync.publisher import PublishResult


def build_settings(tmp_path: Path, *, dry_run: bool = False) -> Settings:
    return Settings(
        notion_token="test-token",
        notion_database_id="database-123",
        git_repo_path=tmp_path / "repo",
        meetings_dir="team/meetings",
        state_file=tmp_path / "state.json",
        dry_run=dry_run,
    )


def build_page_info(page_id: str = "page-123", title: str = "상품 프라이싱 논의 미팅") -> PageInfo:
    return PageInfo(
        page_id=page_id,
        title=title,
        date="2026-03-12",
        categories=["TA"],
        attendees=["홍길동", "김철수"],
        created_time="2026-03-13T12:34:56.789Z",
        last_edited_time="2026-03-13T12:40:00.000Z",
    )


def build_document(file_name: str = "TA-2026-03-12-상품-프라이싱-논의-미팅") -> MeetingDocument:
    return MeetingDocument(
        markdown_content="# Meeting\n\nContent",
        file_name=file_name,
        metadata=MeetingMetadata(
            title="상품 프라이싱 논의 미팅",
            date="2026-03-12",
            categories=["TA"],
            attendees=["홍길동", "김철수"],
            page_id="page-123",
        ),
    )


def create_orchestrator(tmp_path: Path) -> tuple[SyncOrchestrator, MagicMock, MagicMock, MagicMock]:
    settings = build_settings(tmp_path)
    state = MagicMock()
    poller = MagicMock()
    publisher = MagicMock()

    with (
        patch("notion_meeting_sync.orchestrator.SyncState", return_value=state),
        patch("notion_meeting_sync.orchestrator.NotionPoller", return_value=poller),
        patch("notion_meeting_sync.orchestrator.GitPublisher", return_value=publisher),
    ):
        from notion_meeting_sync.orchestrator import SyncOrchestrator

        orchestrator = SyncOrchestrator(settings)

    return orchestrator, state, poller, publisher


def test_sync_page_success(tmp_path: Path) -> None:
    orchestrator, state, _, publisher = create_orchestrator(tmp_path)
    page_info = build_page_info()
    document = build_document()
    publish_result = PublishResult(success=True, file_path=tmp_path / "repo" / "team/meetings" / document.file_name)

    state.is_synced.return_value = False
    publisher.publish.return_value = publish_result

    with patch("notion_meeting_sync.orchestrator.fetch_and_convert", return_value=document) as fetch_and_convert:
        success = orchestrator.sync_page(page_info)

    assert success is True
    fetch_and_convert.assert_called_once_with(page_info)
    publisher.publish.assert_called_once_with(
        document.file_name,
        document.markdown_content,
        f"docs: add meeting notes {document.file_name}",
    )
    state.mark_synced.assert_called_once_with(
        page_info.page_id,
        {
            "title": page_info.title,
            "file_path": str(publish_result.file_path),
            "last_edited_time": page_info.last_edited_time,
        },
    )
    state.clear_failed_push.assert_called_once_with(page_info.page_id)
    state.add_failed_push.assert_not_called()


def test_sync_page_already_synced(tmp_path: Path) -> None:
    orchestrator, state, _, publisher = create_orchestrator(tmp_path)
    page_info = build_page_info()
    state.is_synced.return_value = True

    with patch("notion_meeting_sync.orchestrator.fetch_and_convert") as fetch_and_convert:
        success = orchestrator.sync_page(page_info)

    assert success is True
    fetch_and_convert.assert_not_called()
    publisher.publish.assert_not_called()
    state.mark_synced.assert_not_called()


def test_sync_page_publish_failure_records_failed_push(tmp_path: Path) -> None:
    orchestrator, state, _, publisher = create_orchestrator(tmp_path)
    page_info = build_page_info()
    document = build_document()

    state.is_synced.return_value = False
    publisher.publish.return_value = PublishResult(
        success=False,
        file_path=tmp_path / "repo" / "team/meetings" / document.file_name,
        error="push failed",
    )

    with patch("notion_meeting_sync.orchestrator.fetch_and_convert", return_value=document):
        success = orchestrator.sync_page(page_info)

    assert success is False
    state.mark_synced.assert_not_called()
    state.add_failed_push.assert_called_once()
    recorded_error = state.add_failed_push.call_args.args[1]
    assert "push failed" in recorded_error
    assert document.file_name in recorded_error


def test_run_catchup_sync_collects_stats(tmp_path: Path) -> None:
    orchestrator, state, poller, _ = create_orchestrator(tmp_path)
    synced_page = build_page_info("page-synced", "Synced")
    skipped_page = build_page_info("page-skipped", "Skipped")
    failed_page = build_page_info("page-failed", "Failed")
    since = datetime(2026, 3, 13, 0, 0, tzinfo=UTC)

    state.get_last_poll_time.return_value = since.isoformat()
    state.is_synced.side_effect = lambda page_id: page_id == "page-skipped"  # type: ignore[arg-type]
    state.get_failed_pushes.return_value = []
    poller.poll_new_pages.return_value = [synced_page, skipped_page, failed_page]
    orchestrator.sync_page = MagicMock(side_effect=[True, False])

    stats = orchestrator.run_catchup_sync()

    assert stats == {"synced": 1, "failed": 1, "skipped": 1}
    assert poller.poll_new_pages.call_args_list[0].args[0] == since
    assert orchestrator.sync_page.call_args_list == [call(synced_page), call(failed_page)]
    state.update_poll_time.assert_called_once_with()


def test_run_catchup_sync_full_ignores_last_poll_time(tmp_path: Path) -> None:
    orchestrator, state, poller, _ = create_orchestrator(tmp_path)

    state.get_last_poll_time.return_value = "2026-03-13T00:00:00+00:00"
    state.get_failed_pushes.return_value = []
    poller.poll_new_pages.return_value = []
    orchestrator.sync_page = MagicMock()

    stats = orchestrator.run_catchup_sync(full=True)

    assert stats == {"synced": 0, "failed": 0, "skipped": 0}
    assert poller.poll_new_pages.call_args_list == [call(None)]


def test_run_catchup_sync_retries_failed_pushes(tmp_path: Path) -> None:
    orchestrator, state, poller, _ = create_orchestrator(tmp_path)
    fresh_page = build_page_info("page-fresh", "Fresh")
    retry_page = build_page_info("page-retry", "Retry")

    state.get_last_poll_time.return_value = None
    state.is_synced.return_value = False
    state.get_failed_pushes.return_value = [
        {"page_id": "page-retry", "error": "push failed", "timestamp": "2026-03-13T12:00:00+00:00"}
    ]
    poller.poll_new_pages.side_effect = [[fresh_page], [fresh_page, retry_page]]
    orchestrator.sync_page = MagicMock(side_effect=[True, True])

    stats = orchestrator.run_catchup_sync()

    assert stats == {"synced": 2, "failed": 0, "skipped": 0}
    assert poller.poll_new_pages.call_args_list == [call(None), call(None)]
    assert orchestrator.sync_page.call_args_list == [call(fresh_page), call(retry_page)]
