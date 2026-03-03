"""VCS (git) status detection with async TTL cache."""

from __future__ import annotations

import asyncio
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from claudre.logger import get_logger
from claudre.models import VcsStatus

log = get_logger(__name__)

# Try to import watchdog for inotify-based invalidation
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False


@dataclass
class VcsCache:
    ttl: float = 30.0
    _cache: dict[str, tuple[VcsStatus, float]] = field(default_factory=dict)
    _executor: ThreadPoolExecutor = field(default_factory=ThreadPoolExecutor)
    _observer: object | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if _WATCHDOG_AVAILABLE:
            self._observer = Observer()
            self._observer.start()  # type: ignore[union-attr]

    async def get(self, path: str) -> VcsStatus:
        """Return cached VcsStatus, refreshing if stale."""
        entry = self._cache.get(path)
        if entry is not None:
            status, expires = entry
            if time.monotonic() < expires:
                return status

        loop = asyncio.get_event_loop()
        status = await loop.run_in_executor(self._executor, self._fetch_sync, path)
        self._cache[path] = (status, time.monotonic() + self.ttl)

        if _WATCHDOG_AVAILABLE and self._observer is not None:
            self._install_watch(path)

        return status

    def _fetch_sync(self, path: str) -> VcsStatus:
        """Synchronous git status fetch — runs in executor thread."""
        p = Path(path)
        if not (p / ".git").exists():
            return VcsStatus()

        branch = ""
        dirty = False

        try:
            result = subprocess.run(
                ["git", "-C", path, "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        try:
            result = subprocess.run(
                ["git", "-C", path, "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                dirty = bool(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return VcsStatus(vcs_type="git", branch=branch, dirty=dirty)

    def invalidate(self, path: str) -> None:
        """Force re-fetch on next access for this path."""
        self._cache.pop(path, None)

    def _install_watch(self, path: str) -> None:
        """Install inotify watches on .git/HEAD and .git/index."""
        if not _WATCHDOG_AVAILABLE or self._observer is None:
            return
        git_dir = Path(path) / ".git"
        if not git_dir.exists():
            return

        cache = self

        class _GitHandler(FileSystemEventHandler):  # type: ignore[misc]
            def on_modified(self, event):
                name = Path(event.src_path).name
                if name in ("HEAD", "index"):
                    cache.invalidate(path)

        try:
            self._observer.schedule(_GitHandler(), str(git_dir), recursive=False)  # type: ignore[union-attr]
        except Exception:
            pass

    def stop(self) -> None:
        if _WATCHDOG_AVAILABLE and self._observer is not None:
            try:
                self._observer.stop()  # type: ignore[union-attr]
                self._observer.join(timeout=2)  # type: ignore[union-attr]
            except Exception:
                pass
