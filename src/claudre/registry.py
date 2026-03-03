"""Session registry — tracks all tmux windows and emits typed events."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from claudre.config import ClaudreConfig
from claudre.logger import get_logger
from claudre.models import (
    ClaudeState,
    RegistryEvent,
    TmuxPane,
    VcsStatus,
    WindowAdded,
    WindowRemoved,
    WindowState,
    WindowStateChanged,
)
from claudre.state_detector import StateDetector
from claudre.summary_engine import SummaryEngine
from claudre.tmux_adapter import TmuxAdapter
from claudre.vcs import VcsCache

log = get_logger(__name__)


class SessionRegistry:
    def __init__(
        self,
        config: ClaudreConfig,
        tmux: TmuxAdapter,
        detector: StateDetector,
        vcs: VcsCache,
        summary: SummaryEngine,
    ) -> None:
        self._config = config
        self._tmux = tmux
        self._detector = detector
        self._vcs = vcs
        self._summary = summary

        self._windows: dict[str, WindowState] = {}
        self._handlers: list[Callable[[RegistryEvent], None]] = []
        self._refresh_task: asyncio.Task | None = None
        self._config_watch_task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def windows(self) -> dict[str, WindowState]:
        """Read-only view of current window states (keyed by pane_id)."""
        return dict(self._windows)

    def subscribe(self, handler: Callable[[RegistryEvent], None]) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        """Begin the refresh loop and optional config watcher."""
        self._running = True
        self._refresh_task = asyncio.ensure_future(self._refresh_loop())
        self._config_watch_task = asyncio.ensure_future(self._config_watch_loop())

    async def stop(self) -> None:
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
        if self._config_watch_task:
            self._config_watch_task.cancel()
        self._vcs.stop()

    def request_summary(self, pane_id: str) -> None:
        """Manually trigger a summary refresh for a pane."""
        ws = self._windows.get(pane_id)
        if ws:
            ws.summary_stale = True

    # ------------------------------------------------------------------ #
    # Refresh loop
    # ------------------------------------------------------------------ #

    async def _refresh_loop(self) -> None:
        while self._running:
            try:
                await self._refresh_once()
            except Exception as e:
                log.warning("Registry refresh error: %s", e)
            await asyncio.sleep(self._config.refresh_interval)

    async def _refresh_once(self) -> None:
        panes = await self._tmux.list_panes()

        # Filter by scope
        current_session = ""
        if self._config.scope == "session":
            current_session = await self._tmux.current_session()

        if self._config.scope == "session" and current_session:
            panes = [p for p in panes if p.session == current_session]

        # Skip the claudre dashboard window itself
        dashboard_idx = await self._tmux.current_window_index()
        dashboard_session = await self._tmux.current_session()
        panes = [
            p for p in panes
            if not (p.session == dashboard_session and p.window_index == dashboard_idx
                    and p.window_name == "claudre")
        ]

        # One representative pane per window — first pane wins
        seen: set[tuple[str, str]] = set()
        unique: list[TmuxPane] = []
        for p in panes:
            key = (p.session, p.window_index)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        panes = unique

        pane_ids = {p.pane_id for p in panes}
        existing_ids = set(self._windows.keys())

        # Remove gone panes
        for pid in existing_ids - pane_ids:
            del self._windows[pid]
            self._emit(WindowRemoved(pane_id=pid))

        # Add new panes
        for pane in panes:
            if pane.pane_id not in existing_ids:
                ws = WindowState(
                    pane_id=pane.pane_id,
                    project_name=Path(pane.pane_path).name or pane.window_name,
                    path=pane.pane_path,
                    session=pane.session,
                    window_index=pane.window_index,
                    managed=False,
                )
                # Check managed flag once at creation time
                try:
                    ws.managed = await self._tmux.is_managed(pane.target)
                except Exception:
                    ws.managed = False
                self._windows[pane.pane_id] = ws
                self._emit(WindowAdded(pane_id=pane.pane_id))

        # Update all panes concurrently
        await asyncio.gather(
            *[self._update_window(p) for p in panes],
            return_exceptions=True,
        )

        # Check if summaries need updating
        for ws in list(self._windows.values()):
            if await self._summary.should_update(ws):
                await self._summary.request_update(ws, self)

        # Status bar integration
        if self._config.status_bar_integration:
            await self._update_status_bar()

    async def _update_window(self, pane: TmuxPane) -> None:
        ws = self._windows.get(pane.pane_id)
        if ws is None:
            return

        # Keep metadata in sync
        ws.project_name = pane.window_name or Path(pane.pane_path).name or ws.project_name
        ws.path = pane.pane_path
        ws.session = pane.session
        ws.window_index = pane.window_index

        # Detect state
        try:
            new_state = await self._detector.detect(pane)
        except Exception as e:
            log.debug("State detection error for %s: %s", pane.pane_id, e)
            new_state = ClaudeState.UNKNOWN

        if new_state != ws.state:
            old_state = ws.state
            ws.state = new_state
            ws.summary_stale = True
            self._emit(WindowStateChanged(
                pane_id=pane.pane_id,
                old=old_state,
                new=new_state,
            ))

        # VCS
        try:
            ws.vcs = await self._vcs.get(pane.pane_path)
        except Exception:
            pass

    async def _update_status_bar(self) -> None:
        """Update the tmux status bar with a summary of window states."""
        windows = list(self._windows.values())
        crashed = [w for w in windows if w.state == ClaudeState.CRASHED]
        waiting = [w for w in windows if w.state == ClaudeState.WAITING]
        working = [w for w in windows if w.state == ClaudeState.WORKING]

        if crashed:
            urgent = crashed[0]
            status = f"● {urgent.project_name}: CRASHED"
        elif waiting:
            urgent = waiting[0]
            status = f"● {urgent.project_name}: WAITING"
        elif working:
            status = f"● {len(working)} working"
        else:
            status = ""

        if status:
            try:
                await self._tmux.set_global_option("@claudre_status", status)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Config watcher
    # ------------------------------------------------------------------ #

    async def _config_watch_loop(self) -> None:
        """Watch ~/.claudre/config.toml and reload on change."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            return

        config_path = Path.home() / ".claudre" / "config.toml"
        if not config_path.parent.exists():
            return

        registry = self
        changed = asyncio.Event()

        class _Handler(FileSystemEventHandler):  # type: ignore[misc]
            def on_modified(self, event):
                if Path(event.src_path) == config_path:
                    changed.set()

        observer = Observer()
        observer.schedule(_Handler(), str(config_path.parent), recursive=False)
        observer.start()

        try:
            while self._running:
                await asyncio.sleep(1)
                if changed.is_set():
                    changed.clear()
                    try:
                        from claudre.config import load_config
                        new_cfg = load_config()
                        registry._config = new_cfg
                        registry._summary.update_config(new_cfg)
                        log.info("Config reloaded from %s", config_path)
                    except Exception as e:
                        log.warning("Config reload failed: %s", e)
        finally:
            observer.stop()
            observer.join(timeout=2)

    # ------------------------------------------------------------------ #
    # Event emission
    # ------------------------------------------------------------------ #

    def _emit(self, event: RegistryEvent) -> None:
        for handler in self._handlers:
            try:
                handler(event)
            except Exception as e:
                log.warning("Event handler error: %s", e)
