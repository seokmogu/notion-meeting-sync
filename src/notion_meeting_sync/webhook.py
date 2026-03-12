from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Callable, cast

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from notion_meeting_sync.config import Settings
from notion_meeting_sync.poller import PageInfo
from notion_meeting_sync.state import SyncState

type SyncPageHandler = Callable[[PageInfo], object]


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def create_app(
    settings: Settings | None = None,
    state: SyncState | None = None,
    sync_page: SyncPageHandler | None = None,
) -> FastAPI:
    app = FastAPI()

    if settings is not None:
        app.state.settings = settings
    if state is not None:
        app.state.sync_state = state
    app.state.sync_page = sync_page or _noop_sync_page

    def health() -> dict[str, str]:
        return {"status": "ok"}

    async def notion_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
        current_settings = _get_settings(app)
        signature = request.headers.get("X-Notion-Signature", "")
        body = await request.body()

        if not verify_signature(body, signature, current_settings.webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid Notion signature")

        payload = _decode_payload(body)
        if payload.get("type") != "page.created":
            return {"status": "ignored", "reason": "unsupported_event"}

        page_info = _page_info_from_event(payload)
        if page_info is None:
            return {"status": "ignored", "reason": "invalid_payload"}

        current_state = _get_state(app, current_settings)
        if current_state.is_synced(page_info.page_id):
            return {"status": "ignored", "reason": "already_synced", "page_id": page_info.page_id}

        background_tasks.add_task(_get_sync_handler(app), page_info)
        return {"status": "accepted", "page_id": page_info.page_id}

    app.add_api_route("/health", endpoint=health, methods=["GET"])
    app.add_api_route("/webhook/notion", endpoint=notion_webhook, methods=["POST"])

    return app


def _decode_payload(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    return cast(dict[str, Any], payload)


def _page_info_from_event(payload: dict[str, Any]) -> PageInfo | None:
    entity = _as_dict(payload.get("entity"))
    timestamp = payload.get("timestamp")
    if entity is None:
        return None
    if entity.get("type") != "page":
        return None

    page_id = entity.get("id")
    if not isinstance(page_id, str):
        return None
    if not isinstance(timestamp, str):
        return None

    return PageInfo(
        page_id=page_id,
        title="",
        date="",
        categories=[],
        attendees=[],
        created_time=timestamp,
        last_edited_time=timestamp,
    )


def _get_settings(app: FastAPI) -> Settings:
    current_settings = getattr(app.state, "settings", None)
    if current_settings is None:
        settings_factory = cast(Callable[[], Settings], Settings)
        current_settings = settings_factory()
        app.state.settings = current_settings
    return cast(Settings, current_settings)


def _get_state(app: FastAPI, settings: Settings) -> SyncState:
    current_state = getattr(app.state, "sync_state", None)
    if current_state is None:
        current_state = SyncState(settings.state_file)
        app.state.sync_state = current_state
    return cast(SyncState, current_state)


def _get_sync_handler(app: FastAPI) -> SyncPageHandler:
    return cast(SyncPageHandler, app.state.sync_page)


def _noop_sync_page(page_info: PageInfo) -> None:
    return None


def _as_dict(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, Any], value)


app = create_app()

__all__ = ["app", "create_app", "verify_signature"]
