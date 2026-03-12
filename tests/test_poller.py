from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from notion_meeting_sync.config import Settings
from notion_meeting_sync.poller import NotionPoller, PageInfo


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        notion_token="test-token",
        notion_database_id="database-123",
        git_repo_path=tmp_path / "repo",
        state_file=tmp_path / "state.json",
    )


def build_page_row(
    page_id: str = "page-123",
    title: str = "상품 프라이싱 논의 미팅",
    meeting_date: str = "2026-03-12",
    categories: list[str] | None = None,
    attendees: list[str] | None = None,
    created_time: str = "2026-03-13T12:34:56.789Z",
    last_edited_time: str = "2026-03-13T12:40:00.000Z",
) -> dict[str, object]:
    return {
        "id": page_id,
        "created_time": created_time,
        "last_edited_time": last_edited_time,
        "properties": {
            "Meeting name": {"title": [{"plain_text": title}]},
            "Date": {"date": {"start": meeting_date}},
            "Category": {"multi_select": [{"name": name} for name in (categories or ["TA", "Adelaide"])]},
            "Attendees": {"people": [{"name": name} for name in (attendees or ["홍길동", "김철수"])]},
        },
    }


class RecordingClient:
    def __init__(self, rows: list[dict[str, object]] | None) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def query_database(
        self,
        database_id: str,
        payload: dict[str, object] | None = None,
    ) -> list[dict[str, object]] | None:
        self.calls.append((database_id, payload))
        return self.rows


class PaginatedClient:
    def __init__(self, responses: Sequence[dict[str, object]]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def call(
        self,
        method: str,
        endpoint: str,
        data: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        self.calls.append((method, endpoint, data or {}))
        response = self._responses[self._index]
        self._index += 1
        return response

    def query_database(
        self,
        database_id: str,
        payload: dict[str, object] | None = None,
    ) -> list[dict[str, object]] | None:
        rows: list[dict[str, object]] = []
        cursor: str | None = None
        base_payload = payload.copy() if payload else {}
        base_payload["page_size"] = 100

        while True:
            query_payload = base_payload.copy()
            if cursor:
                query_payload["start_cursor"] = cursor

            response = self.call("POST", f"databases/{database_id}/query", query_payload)
            if response is None:
                return None

            results = response.get("results")
            if not isinstance(results, list):
                return None
            results = cast(list[object], results)

            for item in results:
                if not isinstance(item, dict):
                    return None
                rows.append(cast(dict[str, object], item))

            if not response.get("has_more"):
                return rows

            next_cursor = response.get("next_cursor")
            if next_cursor is None:
                return rows
            if not isinstance(next_cursor, str):
                return None
            cursor = next_cursor


def test_poll_new_pages_extracts_page_info(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    client = RecordingClient([build_page_row()])
    poller = NotionPoller(settings, client=client)

    pages = poller.poll_new_pages(since=None)

    assert pages == [
        PageInfo(
            page_id="page-123",
            title="상품 프라이싱 논의 미팅",
            date="2026-03-12",
            categories=["TA", "Adelaide"],
            attendees=["홍길동", "김철수"],
            created_time="2026-03-13T12:34:56.789Z",
            last_edited_time="2026-03-13T12:40:00.000Z",
        )
    ]
    assert client.calls == [
        (
            "database-123",
            {
                "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
                "page_size": 100,
            },
        )
    ]


def test_poll_handles_pagination(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    client = PaginatedClient(
        [
            {
                "results": [build_page_row(page_id="page-1")],
                "has_more": True,
                "next_cursor": "cursor-1",
            },
            {
                "results": [build_page_row(page_id="page-2")],
                "has_more": False,
                "next_cursor": None,
            },
        ]
    )
    poller = NotionPoller(settings, client=client)
    pages = poller.poll_new_pages(since=None)

    assert [page.page_id for page in pages] == ["page-1", "page-2"]
    assert client.calls[0] == (
        "POST",
        "databases/database-123/query",
        {
            "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
            "page_size": 100,
        },
    )
    assert client.calls[1] == (
        "POST",
        "databases/database-123/query",
        {
            "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
            "page_size": 100,
            "start_cursor": "cursor-1",
        },
    )


def test_poll_with_since_filter(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    client = RecordingClient([])
    poller = NotionPoller(settings, client=client)
    since = datetime(2026, 3, 13, 0, 0, tzinfo=UTC)

    pages = poller.poll_new_pages(since=since)

    assert pages == []
    assert client.calls == [
        (
            "database-123",
            {
                "filter": {
                    "timestamp": "created_time",
                    "created_time": {"after": "2026-03-13T00:00:00.000Z"},
                },
                "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
                "page_size": 100,
            },
        )
    ]


def test_poll_extracts_properties(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    client = RecordingClient(
        [
            {
                "id": "page-789",
                "created_time": "2026-03-13T12:34:56.789Z",
                "last_edited_time": "2026-03-13T12:35:56.789Z",
                "properties": {
                    "Meeting name": {"title": [{"plain_text": "Sprint "}, {"plain_text": "Retro"}]},
                    "Date": {"date": {"start": "2026-03-14"}},
                    "Category": {"multi_select": [{"name": "TA"}, {"name": "Adelaide"}]},
                    "Attendees": {"people": [{"name": "홍길동"}, {"name": None}]},
                },
            }
        ]
    )
    poller = NotionPoller(settings, client=client)

    pages = poller.poll_new_pages(since=None)

    assert len(pages) == 1
    assert pages[0].title == "Sprint Retro"
    assert pages[0].date == "2026-03-14"
    assert pages[0].categories == ["TA", "Adelaide"]
    assert pages[0].attendees == ["홍길동"]
