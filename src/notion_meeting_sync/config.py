from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NMS_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    notion_token: str
    notion_database_id: str = "2ef7d8322b04834aac8a8158796b0a9a"
    webhook_secret: str = ""
    git_repo_path: Path = Field(default_factory=lambda: Path.home() / "project/agentic-services-docs")
    meetings_dir: str = "team/meetings"
    state_file: Path = Field(default_factory=lambda: Path.home() / ".config/notion-meeting-sync/state.json")
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    dry_run: bool = False
