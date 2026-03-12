from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Final

TITLE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:<meeting-notes\b[^>]*>\s*)?\*\*(?P<title>.+?)\*\*",
    re.DOTALL,
)
OMITTED_TRANSCRIPT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*Transcript omitted\. Use the view tool.*$",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(slots=True)
class MeetingMetadata:
    title: str
    date: date | str
    categories: list[str]
    attendees: list[str]
    page_id: str
    synced_at: datetime | str | None = None


def convert_meeting_page(raw_markdown: str, metadata: MeetingMetadata) -> str:
    cleaned_raw_markdown = _remove_global_artifacts(raw_markdown)
    title = _extract_title(cleaned_raw_markdown, metadata.title)
    summary = _extract_section(cleaned_raw_markdown, "summary")
    notes = _extract_section(cleaned_raw_markdown, "notes")
    transcript = _extract_section(cleaned_raw_markdown, "transcript")

    if not summary and not notes and not transcript:
        notes = _extract_plain_notes(cleaned_raw_markdown)

    transcript_content = _normalize_transcript(transcript)

    parts = [
        _build_frontmatter(title, metadata),
        f"# {title}",
        _render_section("## 요약 (Summary)", summary),
        _render_section("## 회의 내용 (Notes)", notes),
        _render_section("## 트랜스크립트 (Transcript)", transcript_content),
    ]
    return "\n\n".join(parts).strip() + "\n"


def _build_frontmatter(title: str, metadata: MeetingMetadata) -> str:
    date_value = _format_date(metadata.date)
    synced_at_value = _format_synced_at(metadata.synced_at)
    categories = _format_yaml_list(metadata.categories)
    attendees = _format_yaml_list(metadata.attendees)

    return "\n".join(
        [
            "---",
            f'title: "{_escape_yaml_string(title)}"',
            f"date: {date_value}",
            f"category: {categories}",
            f"attendees: {attendees}",
            f'notion_page_id: "{_escape_yaml_string(metadata.page_id)}"',
            f'synced_at: "{synced_at_value}"',
            "---",
        ]
    )


def _extract_title(raw_markdown: str, fallback: str) -> str:
    match = TITLE_PATTERN.search(raw_markdown)
    if match is None:
        return fallback.strip()
    return match.group("title").strip()


def _extract_section(raw_markdown: str, tag: str) -> str:
    pattern = re.compile(rf"<{tag}>(.*?)</{tag}>", re.DOTALL | re.IGNORECASE)
    match = pattern.search(raw_markdown)
    if match is None:
        return ""
    return _clean_markdown_text(match.group(1))


def _extract_plain_notes(raw_markdown: str) -> str:
    plain_markdown = re.sub(r"</?meeting-notes\b[^>]*>", "", raw_markdown, flags=re.IGNORECASE)
    plain_markdown = re.sub(r"^\s*\*\*.+?\*\*\s*", "", plain_markdown, count=1, flags=re.DOTALL)
    return _clean_markdown_text(plain_markdown)


def _normalize_transcript(transcript: str) -> str:
    if not transcript:
        return "트랜스크립트 생략"
    if OMITTED_TRANSCRIPT_PATTERN.match(transcript):
        return "트랜스크립트 생략"
    return transcript


def _remove_global_artifacts(raw_markdown: str) -> str:
    without_empty_blocks = re.sub(r"<empty-block\s*/>", "", raw_markdown, flags=re.IGNORECASE)
    without_footnotes = re.sub(
        r"^\[\^https?://[^\]]+\]:\s*https?://\S+\s*$",
        "",
        without_empty_blocks,
        flags=re.MULTILINE,
    )
    return without_footnotes.strip()


def _clean_markdown_text(text: str) -> str:
    cleaned = re.sub(r"<empty-block\s*/>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[\^https?://[^\]]+\]", "", cleaned)
    cleaned = re.sub(r"^\[\^https?://[^\]]+\]:\s*https?://\S+\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _render_section(heading: str, content: str) -> str:
    if not content:
        return heading
    return f"{heading}\n\n{content}"


def _format_date(value: date | str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return value


def _format_synced_at(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str):
        return value
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return f"[{', '.join(_escape_yaml_flow_value(value) for value in values)}]"


def _escape_yaml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _escape_yaml_flow_value(value: str) -> str:
    if re.search(r"[:,\[\]{}]", value):
        return f'"{_escape_yaml_string(value)}"'
    return value


__all__ = ["MeetingMetadata", "convert_meeting_page"]
