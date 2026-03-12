from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from notion_meeting_sync.config import Settings
from notion_meeting_sync.converter import MeetingMetadata, convert_meeting_page
from notion_meeting_sync.poller import PageInfo


class MarkdownRetrievalClient(Protocol):
    def retrieve_markdown(self, page_id: str) -> str | None: ...

    def fetch_children(self, block_id: str) -> list[dict[str, Any]] | None: ...


@dataclass(slots=True)
class MeetingDocument:
    markdown_content: str
    file_name: str
    metadata: MeetingMetadata


type ClientFactory = Callable[..., MarkdownRetrievalClient]
type MarkdownRenderer = Callable[[list[dict[str, Any]]], str]
type SettingsFactory = Callable[[], Settings]


def fetch_and_convert(page_info: PageInfo) -> MeetingDocument:
    _ensure_notes_ready(page_info)
    client = _create_client()
    raw_markdown = _retrieve_raw_markdown(client, page_info.page_id)
    metadata = _build_metadata(page_info)
    markdown_content = convert_meeting_page(raw_markdown, metadata)
    file_name = generate_filename(page_info)
    return MeetingDocument(markdown_content=markdown_content, file_name=file_name, metadata=metadata)


def generate_filename(page_info: PageInfo) -> str:
    category = _category_prefix(page_info.categories)
    title_slug = _slugify_title(page_info.title)
    return f"{category}-{page_info.date}-{title_slug}.md"


def _create_client() -> MarkdownRetrievalClient:
    settings = _load_settings()
    client_module = importlib.import_module("notion_native_toolkit.client")
    client_class = getattr(client_module, "NotionApiClient")
    client_factory = cast(ClientFactory, client_class)
    return client_factory(token=settings.notion_token)


def _load_settings() -> Settings:
    settings_factory = cast(SettingsFactory, Settings)
    return settings_factory()


def _retrieve_raw_markdown(client: MarkdownRetrievalClient, page_id: str) -> str:
    raw_markdown = client.retrieve_markdown(page_id)
    if raw_markdown is not None:
        return raw_markdown

    blocks = client.fetch_children(page_id)
    if blocks is None:
        raise RuntimeError(f"Unable to retrieve page content for Notion page '{page_id}'.")

    return _blocks_to_markdown(blocks)


def _blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    markdown_module = importlib.import_module("notion_native_toolkit.markdown")
    renderer = getattr(markdown_module, "notion_blocks_to_markdown")
    markdown_renderer = cast(MarkdownRenderer, renderer)
    return markdown_renderer(blocks)


def _build_metadata(page_info: PageInfo) -> MeetingMetadata:
    return MeetingMetadata(
        title=page_info.title,
        date=page_info.date,
        categories=page_info.categories,
        attendees=page_info.attendees,
        page_id=page_info.page_id,
    )


def _ensure_notes_ready(page_info: PageInfo) -> None:
    transcription_status = getattr(page_info, "transcription_status", "notes_ready")
    if transcription_status != "notes_ready":
        raise ValueError(f"Page '{page_info.page_id}' is not ready for sync: {transcription_status}")


def _category_prefix(categories: list[str]) -> str:
    for category in categories:
        cleaned = category.strip()
        if cleaned:
            return cleaned
    return "GENERAL"


def _slugify_title(title: str) -> str:
    sanitized = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    hyphenated = re.sub(r"\s+", "-", sanitized.strip())
    collapsed = re.sub(r"-{2,}", "-", hyphenated)
    slug = collapsed.strip("-")
    if slug:
        return slug
    return "untitled"


__all__ = ["MeetingDocument", "fetch_and_convert", "generate_filename"]
