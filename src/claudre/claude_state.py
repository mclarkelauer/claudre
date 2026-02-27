"""Detect Claude's state by reading JSONL session files."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from claudre.models import ClaudeState

CLAUDE_DIR = Path.home() / ".claude" / "projects"
TAIL_BYTES = 100 * 1024  # 100KB tail read
WORKING_THRESHOLD = 10  # seconds


# Cache mapping real project paths to their sanitized dir names
_path_to_dir_cache: dict[str, str] | None = None


def _build_path_cache() -> dict[str, str]:
    """Scan ~/.claude/projects/*/  and build {real_path: sanitized_dir} lookup."""
    cache: dict[str, str] = {}
    if not CLAUDE_DIR.exists():
        return cache
    for d in CLAUDE_DIR.iterdir():
        if not d.is_dir():
            continue
        # Find any JSONL file and read cwd from first message
        jsonl_files = sorted(d.glob("*.jsonl"))
        for jf in jsonl_files:
            try:
                with open(jf) as f:
                    first_line = f.readline().strip()
                    if not first_line:
                        continue
                    data = json.loads(first_line)
                    cwd = data.get("cwd", "")
                    if cwd:
                        cache[cwd] = d.name
                        break
            except (json.JSONDecodeError, OSError):
                continue
    return cache


def _get_sanitized_dir(project_path: str) -> str | None:
    """Get the sanitized dir name for a project path."""
    global _path_to_dir_cache
    if _path_to_dir_cache is None:
        _path_to_dir_cache = _build_path_cache()
    result = _path_to_dir_cache.get(project_path)
    if result is None:
        # Rebuild cache in case new sessions have been created
        _path_to_dir_cache = _build_path_cache()
        result = _path_to_dir_cache.get(project_path)
    return result


def _find_latest_jsonl(sanitized_dir: str) -> Path | None:
    """Find the most recently modified JSONL file for a project."""
    proj_dir = CLAUDE_DIR / sanitized_dir
    if not proj_dir.exists():
        return None
    jsonl_files = list(proj_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None
    return max(jsonl_files, key=lambda f: f.stat().st_mtime)


def _tail_read_last_role(path: Path) -> str | None:
    """Read the last role from a JSONL file using tail-read."""
    try:
        file_size = path.stat().st_size
    except OSError:
        return None
    if file_size == 0:
        return None

    try:
        with open(path, "rb") as f:
            offset = max(0, file_size - TAIL_BYTES)
            f.seek(offset)
            data = f.read()
    except OSError:
        return None

    # Parse lines from end to find last message with a role
    lines = data.decode("utf-8", errors="replace").strip().splitlines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            role = msg.get("role")
            if role in ("assistant", "user"):
                return role
        except json.JSONDecodeError:
            # Might be a partial line from seeking mid-line
            continue
    return None


def detect_state(project_path: str, process_running: bool) -> ClaudeState:
    """Detect Claude's current state for a project.

    Args:
        project_path: Absolute path to the project directory.
        process_running: Whether a claude process is running in the tmux pane.
    """
    if not process_running:
        return ClaudeState.NOT_RUNNING

    sanitized_dir = _get_sanitized_dir(project_path)
    if sanitized_dir is None:
        return ClaudeState.WAITING  # Fresh session, no JSONL yet

    jsonl_path = _find_latest_jsonl(sanitized_dir)
    if jsonl_path is None:
        return ClaudeState.WAITING  # Fresh session

    try:
        mtime = jsonl_path.stat().st_mtime
    except OSError:
        return ClaudeState.WAITING

    age = time.time() - mtime
    if age < WORKING_THRESHOLD:
        return ClaudeState.WORKING

    # mtime > threshold — check last message role
    last_role = _tail_read_last_role(jsonl_path)
    if last_role == "assistant":
        return ClaudeState.WAITING
    # If last role is "user" or unknown, Claude might be working on it
    return ClaudeState.WORKING


def invalidate_cache() -> None:
    """Force rebuild of the path cache on next access."""
    global _path_to_dir_cache
    _path_to_dir_cache = None
