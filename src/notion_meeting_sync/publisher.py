"""Git publisher — writes markdown files to a local git repo and pushes to remote."""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    success: bool
    file_path: Path
    error: str | None = None


class GitPublisher:
    """Saves markdown files to a local git repository and pushes to remote.

    Uses subprocess-based git operations (no gitpython dependency).

    Args:
        repo_path: Path to the local git repository root.
        meetings_dir: Subdirectory within the repo for meeting files.
        dry_run: If True, write files but skip all git operations.
    """

    def __init__(self, repo_path: Path, meetings_dir: str = "team/meetings", dry_run: bool = False) -> None:
        self.repo_path = repo_path
        self.meetings_dir = meetings_dir
        self.dry_run = dry_run

    def publish(self, file_name: str, content: str, commit_message: str) -> PublishResult:
        """Write a markdown file and commit/push it to the git repository.

        Args:
            file_name: Name of the file (e.g. "2026-03-12-standup.md").
            content: Markdown content to write.
            commit_message: Git commit message.

        Returns:
            PublishResult with success status and file path.
        """
        file_path = self.repo_path / self.meetings_dir / file_name

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        logger.info("Wrote file: %s", file_path)

        if self.dry_run:
            logger.info("Dry-run mode — skipping git operations")
            return PublishResult(success=True, file_path=file_path)

        relative_path = f"{self.meetings_dir}/{file_name}"

        steps: list[tuple[str, list[str]]] = [
            ("pull", ["pull", "--rebase"]),
            ("add", ["add", relative_path]),
            ("commit", ["commit", "-m", commit_message]),
            ("push", ["push"]),
        ]

        for step_name, args in steps:
            result = self._run_git(args)
            if result.returncode != 0:
                error_msg = result.stderr.strip() or f"git {step_name} failed with exit code {result.returncode}"
                logger.error("git %s failed: %s", step_name, error_msg)
                return PublishResult(success=False, file_path=file_path, error=error_msg)
            logger.info("git %s succeeded", step_name)

        return PublishResult(success=True, file_path=file_path)

    def _run_git(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        full_cmd = ["git", "-C", str(self.repo_path), *cmd]
        logger.debug("Running: %s", " ".join(full_cmd))
        return subprocess.run(full_cmd, capture_output=True, text=True, check=False)
