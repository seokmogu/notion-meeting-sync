from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
from collections.abc import Callable
from typing import Any, Sequence, cast

import uvicorn

from notion_meeting_sync.config import Settings
from notion_meeting_sync.orchestrator import SyncOrchestrator
from notion_meeting_sync.state import SyncState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="notion-meeting-sync")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve", help="Start webhook server")

    sync_parser = subparsers.add_parser("sync", help="Run catch-up sync")
    sync_parser.add_argument("--dry-run", action="store_true", help="Write files but skip git push")
    sync_parser.add_argument("--full", action="store_true", help="Ignore last poll time and resync all pages")

    subparsers.add_parser("status", help="Show sync status")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "serve":
        return _run_serve()
    if args.command == "sync":
        return _run_sync(dry_run=args.dry_run, full=args.full)
    if args.command == "status":
        return _run_status()
    raise ValueError(f"Unsupported command: {args.command}")


def _run_serve() -> int:
    settings = _load_settings()
    orchestrator = SyncOrchestrator(settings)

    try:
        orchestrator.run_catchup_sync()
    except Exception:  # noqa: BLE001
        logger.exception("Catch-up sync failed during startup")

    webhook_module = importlib.import_module("notion_meeting_sync.webhook")
    app_factory = cast(Callable[..., Any], getattr(webhook_module, "create_app"))
    app = app_factory(
        settings=settings,
        state=orchestrator.state,
        sync_page=orchestrator.sync_page,
    )
    logger.info("Starting webhook server on %s:%s", settings.server_host, settings.server_port)
    uvicorn.run(app, host=settings.server_host, port=settings.server_port)
    return 0


def _run_sync(*, dry_run: bool, full: bool) -> int:
    orchestrator = SyncOrchestrator(_load_settings(dry_run=dry_run))
    stats = orchestrator.run_catchup_sync(full=full)
    print(f"Synced: {stats['synced']}, Failed: {stats['failed']}, Skipped: {stats['skipped']}")
    return 0 if stats["failed"] == 0 else 1


def _run_status() -> int:
    settings = _load_settings(allow_missing_token=True)
    state = SyncState(settings.state_file)
    payload = json.loads(state.state_file.read_text(encoding="utf-8"))

    print(f"State file: {settings.state_file}")
    print(f"Synced pages: {len(payload.get('synced_pages', {}))}")
    print(f"Failed pushes: {len(payload.get('failed_pushes', []))}")
    print(f"Last poll time: {payload.get('last_poll_time') or 'never'}")
    return 0


def _load_settings(*, dry_run: bool = False, allow_missing_token: bool = False) -> Settings:
    notion_token = os.getenv("NMS_NOTION_TOKEN") or os.getenv("NOTION_TOKEN")

    if allow_missing_token and notion_token is None:
        return Settings(notion_token="", dry_run=dry_run)
    if notion_token is None:
        raise RuntimeError("NMS_NOTION_TOKEN is required")
    return Settings(notion_token=notion_token, dry_run=dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
