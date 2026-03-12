from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from fastapi.testclient import TestClient

from notion_meeting_sync.config import Settings
from notion_meeting_sync.poller import PageInfo
from notion_meeting_sync.state import SyncState
from notion_meeting_sync.webhook import create_app


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        notion_token="test-token",
        notion_database_id="database-123",
        webhook_secret="super-secret",
        git_repo_path=tmp_path / "repo",
        state_file=tmp_path / "state.json",
    )


def build_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def build_event(event_type: str = "page.created", page_id: str = "page-123") -> dict[str, object]:
    return {
        "id": "event-123",
        "type": event_type,
        "timestamp": "2026-03-13T12:34:56.789Z",
        "workspace_id": "workspace-123",
        "subscription_id": "subscription-123",
        "entity": {"id": page_id, "type": "page"},
        "data": {"parent": {"id": "database-123", "type": "database"}},
        "attempt_number": 1,
    }


def test_valid_page_created_signature(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    state = SyncState(settings.state_file)
    synced_page_ids: list[str] = []

    def sync_page(page_info: PageInfo) -> None:
        synced_page_ids.append(page_info.page_id)

    app = create_app(settings=settings, state=state, sync_page=sync_page)
    client = TestClient(app)
    payload = build_event()
    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/webhook/notion",
        content=body,
        headers={"X-Notion-Signature": build_signature(body, settings.webhook_secret)},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "page_id": "page-123"}
    assert synced_page_ids == ["page-123"]


def test_invalid_signature_rejected(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    state = SyncState(settings.state_file)
    synced_page_ids: list[str] = []

    def sync_page(page_info: PageInfo) -> None:
        synced_page_ids.append(page_info.page_id)

    app = create_app(settings=settings, state=state, sync_page=sync_page)
    client = TestClient(app)
    payload = build_event()
    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/webhook/notion",
        content=body,
        headers={"X-Notion-Signature": "sha256=invalid"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid Notion signature"}
    assert synced_page_ids == []


def test_ignore_non_page_created_events(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    state = SyncState(settings.state_file)
    synced_page_ids: list[str] = []

    def sync_page(page_info: PageInfo) -> None:
        synced_page_ids.append(page_info.page_id)

    app = create_app(settings=settings, state=state, sync_page=sync_page)
    client = TestClient(app)
    payload = build_event(event_type="page.updated")
    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/webhook/notion",
        content=body,
        headers={"X-Notion-Signature": build_signature(body, settings.webhook_secret)},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "unsupported_event"}
    assert synced_page_ids == []


def test_idempotency_skip_synced_pages(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    state = SyncState(settings.state_file)
    state.mark_synced(
        "page-123",
        {
            "title": "Existing page",
            "file_path": "team/meetings/existing-page.md",
            "last_edited_time": "2026-03-13T12:34:56.789Z",
        },
    )
    synced_page_ids: list[str] = []

    def sync_page(page_info: PageInfo) -> None:
        synced_page_ids.append(page_info.page_id)

    app = create_app(settings=settings, state=state, sync_page=sync_page)
    client = TestClient(app)
    payload = build_event()
    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/webhook/notion",
        content=body,
        headers={"X-Notion-Signature": build_signature(body, settings.webhook_secret)},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "already_synced", "page_id": "page-123"}
    assert synced_page_ids == []
