import re

from notion_meeting_sync.converter import MeetingMetadata, convert_meeting_page

REAL_MEETING_RAW = """<meeting-notes readOnlyViewMeetingNoteUrl="https://www.notion.so/meeting">
**상품 프라이싱 논의 미팅**
<summary>
### 액션 아이템
- [ ] 항목1[^https://example.com/action]
### 확정 사항
- 항목2
</summary>
<notes>
### Agenda
- 아젠다1
### Notes
내용...
</notes>
<transcript>
화자 A: 오늘 안건을 정리하겠습니다.
화자 B: 가격 정책은 다음 주부터 반영합니다.
</transcript>
</meeting-notes><empty-block/>
[^https://example.com/action]: https://example.com/action
"""

OMITTED_TRANSCRIPT_RAW = """<meeting-notes>
**상품 프라이싱 논의 미팅**
<summary>
### 액션 아이템
- [ ] 항목1
</summary>
<notes>
### Notes
논의 내용
</notes>
<transcript>
Transcript omitted. Use the view tool...
</transcript>
</meeting-notes>
"""

EMPTY_SUMMARY_RAW = """<meeting-notes>
**요약 없는 미팅**
<summary>

</summary>
<notes>
### Notes
요약이 없는 회의입니다.
</notes>
<transcript>
실제 트랜스크립트
</transcript>
</meeting-notes>
"""

PLAIN_MARKDOWN_RAW = """**일반 미팅 제목**

일반 마크다운 본문입니다.
- 체크 포인트
"""


def build_metadata() -> MeetingMetadata:
    return MeetingMetadata(
        title="메타데이터 제목",
        date="2026-03-12",
        categories=["TA"],
        attendees=["홍길동", "김철수"],
        page_id="3217d832-2b04-8011-ae5c-e7b6b598bd7e",
    )


def test_convert_meeting_page_generates_frontmatter() -> None:
    converted = convert_meeting_page(REAL_MEETING_RAW, build_metadata())

    assert converted.startswith("---\n")
    assert 'title: "상품 프라이싱 논의 미팅"' in converted
    assert "date: 2026-03-12" in converted
    assert "category: [TA]" in converted
    assert "attendees: [홍길동, 김철수]" in converted
    assert 'notion_page_id: "3217d832-2b04-8011-ae5c-e7b6b598bd7e"' in converted
    assert re.search(r'synced_at: "\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"', converted)


def test_convert_meeting_page_extracts_summary_section() -> None:
    converted = convert_meeting_page(REAL_MEETING_RAW, build_metadata())

    assert "## 요약 (Summary)" in converted
    assert "### 액션 아이템" in converted
    assert "- [ ] 항목1" in converted
    assert "### 확정 사항" in converted
    assert "[^https://example.com/action]" not in converted
    assert "<summary>" not in converted


def test_convert_meeting_page_extracts_notes_section() -> None:
    converted = convert_meeting_page(REAL_MEETING_RAW, build_metadata())

    assert "## 회의 내용 (Notes)" in converted
    assert "### Agenda" in converted
    assert "- 아젠다1" in converted
    assert "### Notes" in converted
    assert "내용..." in converted
    assert "<notes>" not in converted


def test_convert_meeting_page_extracts_transcript_section() -> None:
    converted = convert_meeting_page(REAL_MEETING_RAW, build_metadata())

    assert "## 트랜스크립트 (Transcript)" in converted
    assert "화자 A: 오늘 안건을 정리하겠습니다." in converted
    assert "화자 B: 가격 정책은 다음 주부터 반영합니다." in converted
    assert "<transcript>" not in converted


def test_convert_meeting_page_replaces_omitted_transcript_notice() -> None:
    converted = convert_meeting_page(OMITTED_TRANSCRIPT_RAW, build_metadata())

    assert "## 트랜스크립트 (Transcript)" in converted
    assert "트랜스크립트 생략" in converted
    assert "Transcript omitted. Use the view tool..." not in converted


def test_convert_meeting_page_handles_empty_summary() -> None:
    converted = convert_meeting_page(EMPTY_SUMMARY_RAW, build_metadata())

    assert "# 요약 없는 미팅" in converted
    assert "## 요약 (Summary)" in converted
    assert "## 회의 내용 (Notes)" in converted
    assert "요약이 없는 회의입니다." in converted


def test_convert_meeting_page_handles_plain_markdown_without_tags() -> None:
    converted = convert_meeting_page(PLAIN_MARKDOWN_RAW, build_metadata())

    assert 'title: "일반 미팅 제목"' in converted
    assert "# 일반 미팅 제목" in converted
    assert "## 회의 내용 (Notes)" in converted
    assert "일반 마크다운 본문입니다." in converted
    assert "- 체크 포인트" in converted
    assert "<meeting-notes" not in converted
