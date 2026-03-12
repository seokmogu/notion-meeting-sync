from __future__ import annotations

import json
import logging
from datetime import datetime

from notion_meeting_sync.config import Settings
from notion_meeting_sync.fetcher import fetch_and_convert
from notion_meeting_sync.poller import NotionPoller, PageInfo
from notion_meeting_sync.publisher import GitPublisher
from notion_meeting_sync.state import SyncState

logger = logging.getLogger(__name__)


class SyncOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = SyncState(settings.state_file)
        self.poller = NotionPoller(settings)
        self.publisher = GitPublisher(
            settings.git_repo_path,
            meetings_dir=settings.meetings_dir,
            dry_run=settings.dry_run,
        )

    def sync_page(self, page_info: PageInfo) -> bool:
        if self.state.is_synced(page_info.page_id):
            logger.info("Page %s already synced, skipping", page_info.page_id)
            return True

        logger.info("Syncing page %s: %s", page_info.page_id, page_info.title)

        try:
            document = fetch_and_convert(page_info)
            logger.info("Converted page %s: %s", page_info.page_id, document.file_name)

            result = self.publisher.publish(
                document.file_name,
                document.markdown_content,
                f"docs: add meeting notes {document.file_name}",
            )

            if not result.success:
                error_message = result.error or "Unknown publish error"
                logger.error("Failed to publish %s: %s", document.file_name, error_message)
                self.state.add_failed_push(
                    page_info.page_id,
                    _serialize_failed_push(
                        error=error_message,
                        file_name=document.file_name,
                        title=page_info.title,
                    ),
                )
                return False

            self.state.mark_synced(
                page_info.page_id,
                {
                    "title": page_info.title,
                    "file_path": str(result.file_path),
                    "last_edited_time": page_info.last_edited_time,
                },
            )
            self.state.clear_failed_push(page_info.page_id)
            logger.info("Successfully synced page %s", page_info.page_id)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to sync page %s", page_info.page_id)
            self.state.add_failed_push(
                page_info.page_id,
                _serialize_failed_push(error=str(exc), title=page_info.title),
            )
            return False

    def run_catchup_sync(self, full: bool = False) -> dict[str, int]:
        retry_candidates = _failed_page_ids(self.state.get_failed_pushes())
        since = None if full else _parse_poll_time(self.state.get_last_poll_time())
        logger.info("Running catch-up sync (full=%s, since=%s)", full, since)

        pages = self.poller.poll_new_pages(since)
        logger.info("Found %d pages to sync", len(pages))

        stats = {"synced": 0, "failed": 0, "skipped": 0}

        for page_info in pages:
            if self.state.is_synced(page_info.page_id):
                logger.info("Page %s already synced, skipping", page_info.page_id)
                stats["skipped"] += 1
                continue

            success = self.sync_page(page_info)
            if success:
                stats["synced"] += 1
            else:
                stats["failed"] += 1

        self._retry_failed_pushes(retry_candidates, stats)
        self.state.update_poll_time()
        logger.info(
            "Synced %d pages, failed %d, skipped %d",
            stats["synced"],
            stats["failed"],
            stats["skipped"],
        )
        return stats

    def _retry_failed_pushes(self, retry_candidates: list[str], stats: dict[str, int]) -> None:
        if not retry_candidates:
            return

        logger.info("Retrying %d failed pushes", len(retry_candidates))
        retry_pages = self.poller.poll_new_pages(None)
        retry_lookup = {page.page_id: page for page in retry_pages}

        for page_id in retry_candidates:
            page_info = retry_lookup.get(page_id)
            if page_info is None:
                logger.warning("Failed push page %s not found during retry", page_id)
                continue
            if self.state.is_synced(page_id):
                self.state.clear_failed_push(page_id)
                continue

            success = self.sync_page(page_info)
            if success:
                stats["synced"] += 1
            else:
                stats["failed"] += 1


def _parse_poll_time(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def _failed_page_ids(failed_pushes: list[dict[str, str]]) -> list[str]:
    page_ids: list[str] = []
    seen: set[str] = set()

    for failed_push in failed_pushes:
        page_id = failed_push.get("page_id", "")
        if not page_id or page_id in seen:
            continue
        seen.add(page_id)
        page_ids.append(page_id)

    return page_ids


def _serialize_failed_push(*, error: str, title: str, file_name: str | None = None) -> str:
    payload = {
        "error": error,
        "title": title,
    }
    if file_name is not None:
        payload["file_name"] = file_name
    return json.dumps(payload, ensure_ascii=False)


__all__ = ["SyncOrchestrator"]
