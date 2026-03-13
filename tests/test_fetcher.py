from __future__ import annotations

from typing import Any
from unittest.mock import patch

from notion_meeting_sync.fetcher import MeetingDocument, fetch_and_convert, generate_filename
from notion_meeting_sync.poller import PageInfo

RAW_MEETING_MARKDOWN = """<meeting-notes>
**상품 프라이싱 논의 미팅**
<summary>
회의 요약 내용
</summary>
<notes>
주요 논의 사항
</notes>
<transcript>
전체 대화 내용
</transcript>
</meeting-notes>
"""


def build_page_info(
    *,
    title: str = "상품 프라이싱 논의 미팅",
    categories: list[str] | None = None,
) -> PageInfo:
    return PageInfo(
        page_id="page-123",
        title=title,
        date="2026-03-12",
        categories=categories if categories is not None else ["TA"],
        attendees=["홍길동", "김철수"],
        created_time="2026-03-13T12:34:56.789Z",
        last_edited_time="2026-03-13T12:40:00.000Z",
    )


class FakeClient:
    def __init__(
        self,
        *,
        markdown: str | None = RAW_MEETING_MARKDOWN,
        blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        self.markdown = markdown
        self.blocks = blocks or [{"id": "block-1"}]
        self.retrieve_calls: list[str] = []
        self.fetch_calls: list[str] = []

    def retrieve_markdown(self, page_id: str) -> str | None:
        self.retrieve_calls.append(page_id)
        return self.markdown

    def fetch_children(self, block_id: str) -> list[dict[str, Any]] | None:
        self.fetch_calls.append(block_id)
        return self.blocks


def test_generate_filename_with_category() -> None:
    file_name = generate_filename(build_page_info())

    assert file_name == "2026-03-12-TA-상품-프라이싱-논의-미팅.md"


def test_generate_filename_without_category() -> None:
    file_name = generate_filename(build_page_info(title="제목 없는 미팅", categories=[]))

    assert file_name == "2026-03-12-GENERAL-제목-없는-미팅.md"


def test_generate_filename_removes_special_chars() -> None:
    file_name = generate_filename(build_page_info(title="미팅 제목!!!"))

    assert file_name == "2026-03-12-TA-미팅-제목.md"


def test_fetch_and_convert_pipeline() -> None:
    page_info = build_page_info()
    client = FakeClient()

    with patch("notion_meeting_sync.fetcher._create_client", return_value=client):
        document = fetch_and_convert(page_info)

    assert isinstance(document, MeetingDocument)
    assert document.file_name == "2026-03-12-TA-상품-프라이싱-논의-미팅.md"
    assert document.metadata.title == page_info.title
    assert document.metadata.date == page_info.date
    assert document.metadata.categories == page_info.categories
    assert document.metadata.attendees == page_info.attendees
    assert document.metadata.page_id == page_info.page_id
    assert 'title: "상품 프라이싱 논의 미팅"' in document.markdown_content
    assert "## 요약 (Summary)" in document.markdown_content
    assert "회의 요약 내용" in document.markdown_content
    assert client.retrieve_calls == [page_info.page_id]
    assert client.fetch_calls == []


def test_fetch_and_convert_fallback() -> None:
    page_info = build_page_info()
    client = FakeClient(markdown=None, blocks=[{"id": "block-1"}])

    with (
        patch("notion_meeting_sync.fetcher._create_client", return_value=client),
        patch("notion_meeting_sync.fetcher._blocks_to_markdown", return_value=RAW_MEETING_MARKDOWN) as to_markdown,
    ):
        document = fetch_and_convert(page_info)

    assert document.file_name == "2026-03-12-TA-상품-프라이싱-논의-미팅.md"
    assert client.retrieve_calls == [page_info.page_id]
    assert client.fetch_calls == [page_info.page_id]
    to_markdown.assert_called_once_with([{"id": "block-1"}])
    assert "## 회의 내용 (Notes)" in document.markdown_content
