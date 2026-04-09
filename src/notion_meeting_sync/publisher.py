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
        """Write a markdown file into a per-meeting folder and commit/push.

        Each meeting gets its own directory so that attachments can be placed
        alongside the notes.  The directory name equals *file_name* (which no
        longer carries a ``.md`` suffix) and the notes are stored as
        ``index.md`` inside that directory.

        Args:
            file_name: Directory name for the meeting (e.g. "2026-03-12-GENERAL-standup").
            content: Markdown content to write.
            commit_message: Git commit message.

        Returns:
            PublishResult with success status and file path.
        """
        meeting_dir = self.repo_path / self.meetings_dir / file_name
        file_path = meeting_dir / "index.md"

        if self.dry_run:
            meeting_dir.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            logger.info("Wrote file: %s", file_path)
            logger.info("Dry-run mode — skipping git operations")
            return PublishResult(success=True, file_path=file_path)

        relative_path = f"{self.meetings_dir}/{file_name}/index.md"

        self._run_git(["stash"])
        pull_result = self._run_git(["pull", "--rebase"])
        self._run_git(["stash", "pop"])

        if pull_result.returncode != 0:
            error_msg = pull_result.stderr.strip() or "git pull failed"
            logger.error("git pull failed: %s", error_msg)
            return PublishResult(success=False, file_path=file_path, error=error_msg)
        logger.info("git pull succeeded")

        meeting_dir.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        logger.info("Wrote file: %s", file_path)

        steps = [
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

    def publish_file(self, file_path: Path, commit_message: str) -> PublishResult:
        """Commit and push a file that already exists on disk.

        Args:
            file_path: Absolute path to the file to commit.
            commit_message: Git commit message.

        Returns:
            PublishResult with success status.
        """
        if self.dry_run:
            logger.info("Dry-run mode — skipping git for %s", file_path)
            return PublishResult(success=True, file_path=file_path)

        relative_path = str(file_path.relative_to(self.repo_path))

        steps = [
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
