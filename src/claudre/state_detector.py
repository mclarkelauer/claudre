"""Detect Claude's running state by reading JSONL session files."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol

from claudre.logger import get_logger
from claudre.models import ClaudeState, TmuxPane

log = get_logger(__name__)

CLAUDE_DIR = Path.home() / ".claude" / "projects"
TAIL_BYTES = 100 * 1024  # 100KB tail read
_PATH_CACHE_TTL = 60.0   # seconds before rebuilding path→dir lookup


class StateDetector(Protocol):
    async def detect(self, pane: TmuxPane) -> ClaudeState: ...


class JournalStateDetector:
    """Detect Claude state using JSONL session files and psutil CPU usage."""

    def __init__(self) -> None:
        # path → (sanitized_dir, expiry_monotonic)
        self._path_cache: dict[str, tuple[str, float]] = {}

    async def detect(self, pane: TmuxPane) -> ClaudeState:
        """Detect state for the given pane."""
        # Check if the primary process is alive
        alive = self._is_process_alive(pane.pane_pid)

        if not alive:
            # Process is gone — check last JSONL role to distinguish crash vs suspend
            san_dir = self._get_sanitized_dir(pane.pane_path)
            if san_dir is None:
                return ClaudeState.UNKNOWN
            jsonl = self._find_latest_jsonl(san_dir)
            if jsonl is None:
                return ClaudeState.UNKNOWN
            last_role = self._tail_read_last_role(jsonl)
            if last_role == "user":
                return ClaudeState.CRASHED
            if last_role == "assistant":
                return ClaudeState.SUSPENDED
            return ClaudeState.UNKNOWN

        # Process is alive — check if claude is the pane command
        if pane.pane_command not in ("claude", "node"):
            # Shell or other command running in pane, not claude
            return ClaudeState.IDLE

        san_dir = self._get_sanitized_dir(pane.pane_path)
        if san_dir is None:
            # No JSONL yet — fresh session starting up
            return ClaudeState.OPENING

        jsonl = self._find_latest_jsonl(san_dir)
        if jsonl is None:
            return ClaudeState.OPENING

        try:
            mtime = jsonl.stat().st_mtime
        except OSError:
            return ClaudeState.WAITING

        age = time.time() - mtime

        # Use CPU percent as a more reliable WORKING indicator
        cpu = self._get_cpu_percent(pane.pane_pid)
        if cpu > 5.0 or age < 10.0:
            return ClaudeState.WORKING

        # File is older and CPU is low — check last role
        last_role = self._tail_read_last_role(jsonl)
        if last_role == "assistant":
            return ClaudeState.WAITING
        # last role is "user" or unknown → still processing
        return ClaudeState.WORKING

    def _is_process_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            import psutil
            return psutil.pid_exists(pid)
        except ImportError:
            # Fall back to /proc check
            return Path(f"/proc/{pid}").exists()

    def _get_cpu_percent(self, pid: int) -> float:
        try:
            import psutil
            proc = psutil.Process(pid)
            return proc.cpu_percent(interval=0.0)
        except Exception:
            return 0.0

    def _get_sanitized_dir(self, path: str) -> str | None:
        """Return cached sanitized dir for path, rebuilding if stale."""
        entry = self._path_cache.get(path)
        if entry is not None:
            san_dir, expiry = entry
            if time.monotonic() < expiry:
                return san_dir

        # Need to (re)build
        new_cache = self._build_path_cache()
        now = time.monotonic()
        for p, d in new_cache.items():
            self._path_cache[p] = (d, now + _PATH_CACHE_TTL)

        result = new_cache.get(path)
        if result is None:
            # Mark negative so we don't rebuild every call
            self._path_cache[path] = ("", now + _PATH_CACHE_TTL)
            return None
        return result

    def _build_path_cache(self) -> dict[str, str]:
        """Scan ~/.claude/projects/ and build {real_path: sanitized_dir} lookup."""
        cache: dict[str, str] = {}
        if not CLAUDE_DIR.exists():
            return cache
        for d in CLAUDE_DIR.iterdir():
            if not d.is_dir():
                continue
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

    def get_jsonl_path(self, path: str) -> Path | None:
        """Public: return the latest JSONL file path for a project working dir, or None."""
        san_dir = self._get_sanitized_dir(path)
        if not san_dir:
            return None
        return self._find_latest_jsonl(san_dir)

    def _find_latest_jsonl(self, sanitized_dir: str) -> Path | None:
        """Find the most recently modified JSONL file for a project."""
        if not sanitized_dir:
            return None
        proj_dir = CLAUDE_DIR / sanitized_dir
        if not proj_dir.exists():
            return None
        jsonl_files = list(proj_dir.glob("*.jsonl"))
        if not jsonl_files:
            return None
        return max(jsonl_files, key=lambda f: f.stat().st_mtime)

    def _tail_read_last_role(self, path: Path) -> str | None:
        """Read the last role from a JSONL file using efficient tail-read."""
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
                continue
        return None
