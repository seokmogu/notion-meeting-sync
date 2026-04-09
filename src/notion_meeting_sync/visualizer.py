"""Meeting note visualizer — generates Mermaid diagrams using Claude CLI."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

VISUALIZE_PROMPT = """\
You are a meeting notes analyst. Read the meeting notes below and generate Mermaid diagrams \
that visualize the key information discussed.

Generate diagrams for any of the following that are present:
- Organization structure or team assignments (graph TD)
- Timeline / action items with deadlines (gantt)
- Architecture or system design (graph TB/LR)
- Decision flow or process (flowchart)
- Relationships between concepts (graph)

Rules:
- Output ONLY valid Mermaid code blocks, each wrapped in ```mermaid ... ```
- Add a short Korean heading (## ) before each diagram explaining what it shows
- Do NOT include any other text or explanation outside the headings and code blocks
- Use Korean for all labels in the diagrams
- If no content is suitable for visualization, output exactly: "시각화 가능한 내용이 없습니다."
- Maximum 5 diagrams per meeting
"""


@dataclass(slots=True)
class VisualizeResult:
    success: bool
    output_path: Path | None = None
    error: str | None = None


def visualize_meeting(meeting_dir: Path, *, claude_bin: str = "claude") -> VisualizeResult:
    """Generate Mermaid diagrams for a meeting note using Claude CLI.

    Args:
        meeting_dir: Path to the meeting directory containing index.md.
        claude_bin: Path to the Claude CLI binary.

    Returns:
        VisualizeResult with success status and output path.
    """
    index_file = meeting_dir / "index.md"
    if not index_file.exists():
        return VisualizeResult(success=False, error=f"index.md not found in {meeting_dir}")

    content = index_file.read_text(encoding="utf-8")
    if not content.strip():
        return VisualizeResult(success=False, error="Empty meeting note")

    try:
        result = subprocess.run(
            [claude_bin, "-p", VISUALIZE_PROMPT],
            input=content,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError:
        return VisualizeResult(success=False, error=f"Claude CLI not found: {claude_bin}")
    except subprocess.TimeoutExpired:
        return VisualizeResult(success=False, error="Claude CLI timed out after 120s")

    if result.returncode != 0:
        error_msg = result.stderr.strip() or f"claude exited with code {result.returncode}"
        logger.error("Claude CLI failed: %s", error_msg)
        return VisualizeResult(success=False, error=error_msg)

    output = result.stdout.strip()
    if not output or "시각화 가능한 내용이 없습니다" in output:
        logger.info("No visualizable content in %s", meeting_dir.name)
        return VisualizeResult(success=True)

    diagrams_path = meeting_dir / "diagrams.md"
    diagrams_path.write_text(output + "\n", encoding="utf-8")
    logger.info("Generated diagrams: %s", diagrams_path)

    return VisualizeResult(success=True, output_path=diagrams_path)


__all__ = ["VisualizeResult", "visualize_meeting"]
