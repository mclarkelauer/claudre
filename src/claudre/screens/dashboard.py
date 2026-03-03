"""Main dashboard screen for claudre v3."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual import on, work
from textual.screen import Screen
from textual.containers import Horizontal
from textual.widgets import Footer, Input, Static

from claudre.config import ClaudreConfig
from claudre.logger import get_logger
from claudre.models import (
    RegistryEvent,
    SummaryUpdated,
    WindowAdded,
    WindowRemoved,
    WindowState,
    WindowStateChanged,
)
from claudre.registry import SessionRegistry
from claudre.state_detector import JournalStateDetector
from claudre.summary_engine import SummaryEngine
from claudre.tmux_adapter import TmuxAdapter
from claudre.vcs import VcsCache
from claudre.widgets.detail_panel import DetailPanel
from claudre.widgets.toast import ToastManager
from claudre.widgets.window_table import WindowTable

log = get_logger(__name__)


class DashboardScreen(Screen):
    BINDINGS = [
        ("enter", "jump", "Jump"),
        ("n", "new_window", "New"),
        ("x", "close_window", "Close"),
        ("s", "send_message", "Send"),
        ("r", "run_command", "Run"),
        ("u", "update_summary", "Summary"),
        ("shift+r", "force_refresh", "Refresh"),
        ("/", "filter", "Filter"),
        ("?", "help", "Help"),
        ("q", "quit_app", "Quit"),
    ]

    CSS_PATH = Path(__file__).parents[1] / "css" / "app.tcss"

    def __init__(self, config: ClaudreConfig) -> None:
        super().__init__()
        self._config = config
        self._tmux = TmuxAdapter()
        self._vcs = VcsCache(ttl=config.vcs_cache_ttl)
        self._detector = JournalStateDetector()
        self._summary = SummaryEngine(config, self._tmux, detector=self._detector)
        self._registry = SessionRegistry(
            config=config,
            tmux=self._tmux,
            detector=self._detector,
            vcs=self._vcs,
            summary=self._summary,
        )
        self._toast: ToastManager | None = None
        self._filter_visible = False

    def compose(self):
        yield Static(" claudre ", id="header")
        with Horizontal(id="body"):
            yield WindowTable(id="window-table")
            yield DetailPanel(id="detail-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._toast = ToastManager(self.app)
        self._registry.subscribe(self._on_registry_event)
        self._start_registry()

    @work(exclusive=True)
    async def _start_registry(self) -> None:
        await self._registry.start()

    def on_unmount(self) -> None:
        asyncio.ensure_future(self._registry.stop())

    # ------------------------------------------------------------------ #
    # Registry event handler (called from background task via call_from_thread)
    # ------------------------------------------------------------------ #

    def _on_registry_event(self, event: RegistryEvent) -> None:
        """Dispatch registry events to UI updates (called on the event loop)."""
        self.call_later(self._apply_event, event)

    def _apply_event(self, event: RegistryEvent) -> None:
        table = self.query_one(WindowTable)

        if isinstance(event, WindowAdded):
            ws = self._registry.windows.get(event.pane_id)
            if ws:
                table.add_window(ws)
        elif isinstance(event, WindowRemoved):
            table.remove_window(event.pane_id)
            self._update_detail(None)
        elif isinstance(event, WindowStateChanged):
            ws = self._registry.windows.get(event.pane_id)
            if ws:
                table.update_window(ws)
                if event.pane_id == table.get_selected_pane_id():
                    self._update_detail(ws)
                # Toast on WORKING → WAITING transition
                from claudre.models import ClaudeState
                if (
                    self._config.notification_on_waiting
                    and event.old == ClaudeState.WORKING
                    and event.new == ClaudeState.WAITING
                    and self._toast
                ):
                    msg = ws.summary or "waiting for input"
                    self._toast.show(f"{ws.project_name}: {msg[:60]}")
        elif isinstance(event, SummaryUpdated):
            ws = self._registry.windows.get(event.pane_id)
            if ws:
                table.update_window(ws)
                if event.pane_id == table.get_selected_pane_id():
                    self._update_detail(ws)

    def _update_detail(self, ws: WindowState | None) -> None:
        detail = self.query_one(DetailPanel)
        if ws is None:
            table = self.query_one(WindowTable)
            pane_id = table.get_selected_pane_id()
            ws = self._registry.windows.get(pane_id or "") if pane_id else None
        detail.update_window(ws)

    @on(WindowTable.RowHighlighted)
    def on_row_highlighted(self, event: WindowTable.RowHighlighted) -> None:
        self._update_detail(None)

    @on(WindowTable.RowSelected)
    def on_row_selected(self, event: WindowTable.RowSelected) -> None:
        self.action_jump()

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #

    def action_jump(self) -> None:
        ws = self._selected_window()
        if not ws or not ws.session or not ws.window_index:
            return

        async def _jump() -> None:
            current_session = await self._tmux.current_session()
            if ws.session != current_session:
                log.debug("cross-session jump: %s -> %s", current_session, ws.target)
                await self._tmux.switch_client(ws.target)
            else:
                await self._tmux.select_window(ws.target)

        asyncio.ensure_future(_jump())

    def action_new_window(self) -> None:
        async def _do_new() -> None:
            session = await self._tmux.current_session()
            self.app.push_screen(
                _new_window_screen(self._config, session),
                self._on_new_window_result,
            )

        asyncio.ensure_future(_do_new())

    def _on_new_window_result(self, result: object) -> None:
        if result is None:
            return
        from claudre.templates import create_from_template
        from claudre.tmux_adapter import WindowSpec

        async def _create() -> None:
            try:
                spec = WindowSpec(
                    session=result.session if hasattr(result, "session") else "",
                    template_name=result.template_name,
                    project_name=result.project_name,
                    start_directory=result.start_directory,
                )
                # Use current session if not set
                if not spec.session:
                    spec.session = await self._tmux.current_session()
                await create_from_template(self._tmux, spec, self._config)
                if self._toast:
                    self._toast.show(f"Created window: {result.project_name}")
            except Exception as e:
                log.error("Failed to create window: %s", e)
                if self._toast:
                    self._toast.show(f"Error: {e}")

        asyncio.ensure_future(_create())

    def action_close_window(self) -> None:
        ws = self._selected_window()
        if not ws:
            return

        from claudre.screens.confirm import ConfirmScreen

        def on_confirm(confirmed: bool) -> None:
            if confirmed and ws:
                target = ws.pane_id.rsplit(".", 1)[0] if "." in ws.pane_id else ws.pane_id
                asyncio.ensure_future(self._tmux.kill_window(target))

        self.app.push_screen(
            ConfirmScreen(f"Close window '{ws.project_name}'?"), on_confirm
        )

    def action_send_message(self) -> None:
        ws = self._selected_window()
        if not ws:
            return
        from claudre.screens.send_message import SendMessageScreen

        def on_send(text: str | None) -> None:
            if text and ws:
                asyncio.ensure_future(self._tmux.send_keys(ws.pane_id, text))
                # Queue summary update with delay
                async def _delayed_summary() -> None:
                    await asyncio.sleep(5)
                    self._registry.request_summary(ws.pane_id)

                asyncio.ensure_future(_delayed_summary())

        self.app.push_screen(SendMessageScreen(ws.project_name), on_send)

    def action_run_command(self) -> None:
        ws = self._selected_window()
        if not ws:
            return
        proj_cfg = self._config.projects.get(ws.project_name)
        quick_actions = proj_cfg.quick_actions if proj_cfg else []
        from claudre.screens.run_command import RunCommandScreen

        def on_run(cmd: str | None) -> None:
            if cmd and ws:
                asyncio.ensure_future(self._tmux.send_keys(ws.pane_id, cmd))

        self.app.push_screen(RunCommandScreen(ws.project_name, quick_actions), on_run)

    def action_update_summary(self) -> None:
        ws = self._selected_window()
        if not ws:
            return
        self._registry.request_summary(ws.pane_id)
        if self._toast:
            self._toast.show("Summary refresh queued…")

    def action_force_refresh(self) -> None:
        table = self.query_one(WindowTable)
        table.rebuild(self._registry.windows)

    def action_filter(self) -> None:
        self._toggle_filter()

    def _toggle_filter(self) -> None:
        if self._filter_visible:
            # Hide filter
            try:
                self.query_one("#filter-input").remove()
            except Exception:
                pass
            self._filter_visible = False
            self.query_one(WindowTable).set_filter("")
        else:
            inp = Input(placeholder="Filter…", id="filter-input")
            self.query_one(WindowTable).mount(inp, before=self.query_one(WindowTable))
            inp.focus()
            self._filter_visible = True

    @on(Input.Changed, "#filter-input")
    def on_filter_changed(self, event: Input.Changed) -> None:
        self.query_one(WindowTable).set_filter(event.value)
        # Rebuild visible rows
        self.query_one(WindowTable).rebuild(self._registry.windows)

    @on(Input.Submitted, "#filter-input")
    def on_filter_submitted(self, event: Input.Submitted) -> None:
        self._toggle_filter()
        self.query_one(WindowTable).focus()

    def action_help(self) -> None:
        from claudre.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())

    def action_quit_app(self) -> None:
        self.app.exit()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _selected_window(self) -> WindowState | None:
        table = self.query_one(WindowTable)
        pane_id = table.get_selected_pane_id()
        if not pane_id:
            return None
        return self._registry.windows.get(pane_id)


def _new_window_screen(config: ClaudreConfig, session: str):
    from claudre.screens.new_window import NewWindowScreen
    return NewWindowScreen(config=config, session=session)
