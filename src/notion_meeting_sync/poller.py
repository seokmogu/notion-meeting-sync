from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import importlib
from typing import Any, Protocol, cast

from notion_meeting_sync.config import Settings


class DatabaseQueryClient(Protocol):
    def query_database(
        self,
        database_id: str,
        payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]] | None: ...


@dataclass(slots=True)
class PageInfo:
    page_id: str
    title: str
    date: str
    categories: list[str]
    attendees: list[str]
    created_time: str
    last_edited_time: str


class NotionPoller:
    def __init__(self, settings: Settings, client: DatabaseQueryClient | None = None) -> None:
        self.settings = settings
        self.client = client or _create_notion_client(settings.notion_token)

    def poll_new_pages(self, since: datetime | None) -> list[PageInfo]:
        payload: dict[str, Any] = {
            "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
            "page_size": 100,
        }
        if since is not None:
            payload["filter"] = {
                "timestamp": "created_time",
                "created_time": {"after": _format_notion_timestamp(since)},
            }

        rows = self.client.query_database(self.settings.notion_database_id, payload)
        if rows is None:
            return []

        pages: list[PageInfo] = []
        for row in rows:
            page_info = _parse_page_info(row)
            if page_info is not None:
                pages.append(page_info)
        return pages


def _format_notion_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _create_notion_client(token: str) -> DatabaseQueryClient:
    client_module = importlib.import_module("notion_native_toolkit.client")
    client_class = getattr(client_module, "NotionApiClient")
    return cast(DatabaseQueryClient, client_class(token=token))


def _parse_page_info(row: dict[str, Any]) -> PageInfo | None:
    page_id = row.get("id")
    created_time = row.get("created_time")
    last_edited_time = row.get("last_edited_time")
    properties = _as_dict(row.get("properties"))

    if not isinstance(page_id, str):
        return None
    if not isinstance(created_time, str):
        return None
    if not isinstance(last_edited_time, str):
        return None
    if properties is None:
        return None

    return PageInfo(
        page_id=page_id,
        title=_extract_title(properties),
        date=_extract_date(properties),
        categories=_extract_categories(properties),
        attendees=_extract_attendees(properties),
        created_time=created_time,
        last_edited_time=last_edited_time,
    )


def _extract_title(properties: dict[str, Any]) -> str:
    title_property = _as_dict(properties.get("Meeting name"))
    if title_property is None:
        return ""

    title_items = title_property.get("title")
    if not isinstance(title_items, list):
        return ""
    title_items = cast(list[object], title_items)

    fragments: list[str] = []
    for item_value in title_items:
        item = _as_dict(item_value)
        if item is None:
            continue
        plain_text = item.get("plain_text")
        if isinstance(plain_text, str):
            fragments.append(plain_text)
    return "".join(fragments).strip()


def _extract_date(properties: dict[str, Any]) -> str:
    date_property = _as_dict(properties.get("Date"))
    if date_property is None:
        return ""

    date_value = _as_dict(date_property.get("date"))
    if date_value is None:
        return ""

    start = date_value.get("start")
    if not isinstance(start, str):
        return ""
    return start


def _extract_categories(properties: dict[str, Any]) -> list[str]:
    category_property = _as_dict(properties.get("Category"))
    if category_property is None:
        return []

    options = category_property.get("multi_select")
    if not isinstance(options, list):
        return []
    options = cast(list[object], options)

    categories: list[str] = []
    for option_value in options:
        option = _as_dict(option_value)
        if option is None:
            continue
        name = option.get("name")
        if isinstance(name, str):
            categories.append(name)
    return categories


def _extract_attendees(properties: dict[str, Any]) -> list[str]:
    attendees_property = _as_dict(properties.get("Attendees"))
    if attendees_property is None:
        return []

    people = attendees_property.get("people")
    if not isinstance(people, list):
        return []
    people = cast(list[object], people)

    attendees: list[str] = []
    for person_value in people:
        person = _as_dict(person_value)
        if person is None:
            continue
        name = person.get("name")
        if isinstance(name, str):
            attendees.append(name)
    return attendees


def _as_dict(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, Any], value)


__all__ = ["NotionPoller", "PageInfo"]
