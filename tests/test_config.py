import os
from typing import Callable, cast

import pytest
from pydantic import ValidationError

from notion_meeting_sync.config import Settings


def load_settings() -> Settings:
    return cast(Callable[[], Settings], Settings)()


def test_settings_load_from_env_vars() -> None:
    os.environ["NMS_NOTION_TOKEN"] = "test_token_123"
    try:
        settings = load_settings()
        assert settings.notion_token == "test_token_123"
    finally:
        del os.environ["NMS_NOTION_TOKEN"]


def test_settings_missing_required_notion_token() -> None:
    if "NMS_NOTION_TOKEN" in os.environ:
        del os.environ["NMS_NOTION_TOKEN"]
    with pytest.raises(ValidationError):
        load_settings()


def test_settings_default_values() -> None:
    os.environ["NMS_NOTION_TOKEN"] = "test_token"
    try:
        settings = load_settings()
        assert settings.notion_database_id == "2ef7d8322b04834aac8a8158796b0a9a"
        assert settings.webhook_secret == ""
        assert settings.meetings_dir == "team/meetings"
        assert settings.server_host == "0.0.0.0"
        assert settings.server_port == 8080
        assert settings.dry_run is False
    finally:
        del os.environ["NMS_NOTION_TOKEN"]


def test_settings_env_prefix() -> None:
    os.environ["NMS_NOTION_TOKEN"] = "test_token"
    os.environ["NMS_SERVER_PORT"] = "9000"
    try:
        settings = load_settings()
        assert settings.server_port == 9000
    finally:
        del os.environ["NMS_NOTION_TOKEN"]
        del os.environ["NMS_SERVER_PORT"]
