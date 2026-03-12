import subprocess
from pathlib import Path
from unittest.mock import patch

from notion_meeting_sync.publisher import GitPublisher, PublishResult


def _setup_temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with initial commit for testing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, capture_output=True, check=True)
    # Initial commit so we have a branch
    readme = repo / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    (repo / "team" / "meetings").mkdir(parents=True)
    return repo


def test_publish_creates_file(tmp_path: Path) -> None:
    repo = _setup_temp_git_repo(tmp_path)
    publisher = GitPublisher(repo_path=repo, meetings_dir="team/meetings", dry_run=True)

    result = publisher.publish(
        file_name="2026-03-12-standup.md",
        content="# Standup\n\nContent here.",
        commit_message="feat: add standup notes",
    )

    expected_path = repo / "team" / "meetings" / "2026-03-12-standup.md"
    assert result.success is True
    assert result.file_path == expected_path
    assert expected_path.exists()
    assert expected_path.read_text() == "# Standup\n\nContent here."


def test_publish_commits_to_git(tmp_path: Path) -> None:
    repo = _setup_temp_git_repo(tmp_path)
    publisher = GitPublisher(repo_path=repo, meetings_dir="team/meetings", dry_run=False)

    with patch.object(publisher, "_run_git") as mock_git:
        mock_git.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        result = publisher.publish(
            file_name="2026-03-12-standup.md",
            content="# Standup",
            commit_message="feat: add standup notes",
        )

    assert result.success is True

    # Verify git commands were called in order: pull, add, commit, push
    calls = [c.args[0] for c in mock_git.call_args_list]
    assert len(calls) == 4
    assert "pull" in calls[0]
    assert "add" in calls[1]
    assert "commit" in calls[2]
    assert "push" in calls[3]


def test_publish_dry_run_skips_git(tmp_path: Path) -> None:
    repo = _setup_temp_git_repo(tmp_path)
    publisher = GitPublisher(repo_path=repo, meetings_dir="team/meetings", dry_run=True)

    with patch.object(publisher, "_run_git") as mock_git:
        result = publisher.publish(
            file_name="2026-03-12-standup.md",
            content="# Standup",
            commit_message="feat: add standup notes",
        )

    assert result.success is True
    assert result.error is None
    # File should exist
    assert (repo / "team" / "meetings" / "2026-03-12-standup.md").exists()
    # No git commands should have been called
    mock_git.assert_not_called()


def test_publish_handles_push_failure(tmp_path: Path) -> None:
    repo = _setup_temp_git_repo(tmp_path)
    publisher = GitPublisher(repo_path=repo, meetings_dir="team/meetings", dry_run=False)

    def fake_git(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if "push" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="remote: Permission denied")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    with patch.object(publisher, "_run_git", side_effect=fake_git):
        result = publisher.publish(
            file_name="2026-03-12-standup.md",
            content="# Standup",
            commit_message="feat: add standup notes",
        )

    assert result.success is False
    assert result.error is not None
    assert "Permission denied" in result.error
    # File should still exist on disk
    assert (repo / "team" / "meetings" / "2026-03-12-standup.md").exists()


def test_publish_pulls_before_push(tmp_path: Path) -> None:
    repo = _setup_temp_git_repo(tmp_path)
    publisher = GitPublisher(repo_path=repo, meetings_dir="team/meetings", dry_run=False)

    call_order: list[str] = []

    def tracking_git(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        for op in ("pull", "add", "commit", "push"):
            if op in cmd:
                call_order.append(op)
                break
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    with patch.object(publisher, "_run_git", side_effect=tracking_git):
        publisher.publish(
            file_name="2026-03-12-standup.md",
            content="# Standup",
            commit_message="feat: add standup notes",
        )

    assert call_order == ["pull", "add", "commit", "push"]


def test_publish_integration_with_real_git(tmp_path: Path) -> None:
    """Integration test: actually runs git commands (no push since no remote)."""
    repo = _setup_temp_git_repo(tmp_path)
    publisher = GitPublisher(repo_path=repo, meetings_dir="team/meetings", dry_run=False)

    # Override _run_git to skip pull and push (no remote), but run add and commit for real
    original_run_git = publisher._run_git

    def selective_git(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if "pull" in cmd or "push" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        return original_run_git(cmd)

    with patch.object(publisher, "_run_git", side_effect=selective_git):
        result = publisher.publish(
            file_name="2026-03-12-standup.md",
            content="# Standup\n\nIntegration test.",
            commit_message="feat: add standup notes",
        )

    assert result.success is True

    # Verify file exists
    file_path = repo / "team" / "meetings" / "2026-03-12-standup.md"
    assert file_path.exists()

    # Verify git log has our commit
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "feat: add standup notes" in log.stdout
