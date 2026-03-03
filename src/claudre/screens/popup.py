"""Quick window-switcher popup for claudre.

Designed to run inside `tmux display-popup -E`. Shows all tmux windows with
their current state. Type to filter, arrow keys to navigate, Enter to jump,
Escape to cancel. On selection the window is focused and the process exits,
which causes tmux to close the popup.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

from claudre.config import ClaudreConfig
from claudre.logger import get_logger
from claudre.models import ClaudeState, TmuxPane
from claudre.state_detector import JournalStateDetector
from claudre.tmux_adapter import TmuxAdapter

log = get_logger(__name__)


# ── Data ─────────────────────────────────────────────────────────────────────

@dataclass
class _Entry:
    pane: TmuxPane
    name: str
    state: ClaudeState


def _state_icon(state: ClaudeState) -> str:
    match state:
        case ClaudeState.WORKING:   return "◌"
        case ClaudeState.WAITING:   return "●"
        case ClaudeState.CRASHED:   return "⚠"
        case ClaudeState.SUSPENDED: return "—"
        case ClaudeState.OPENING:   return "…"
        case _:                     return " "


def _state_markup(state: ClaudeState) -> str:
    match state:
        case ClaudeState.WORKING:   return "[bold green]WORKING[/]"
        case ClaudeState.WAITING:   return "[bold yellow]WAITING[/]"
        case ClaudeState.CRASHED:   return "[bold red]CRASHED[/]"
        case ClaudeState.SUSPENDED: return "[dim]SUSPENDED[/]"
        case ClaudeState.IDLE:      return "[dim]idle[/]"
        case ClaudeState.OPENING:   return "[cyan]OPENING[/]"
        case _:                     return "[dim]—[/]"


# ── List item widget ──────────────────────────────────────────────────────────

class _WindowItem(ListItem):
    """A single row in the popup list."""

    DEFAULT_CSS = """
    _WindowItem {
        height: 1;
        padding: 0 1;
    }
    _WindowItem:focus-within,
    _WindowItem.--highlight {
        background: $accent 30%;
    }
    """

    def __init__(self, entry: _Entry) -> None:
        super().__init__()
        self._entry = entry

    def compose(self) -> ComposeResult:
        icon = _state_icon(self._entry.state)
        state_mu = _state_markup(self._entry.state)
        target = f"{self._entry.pane.target:<10}"
        name = self._entry.name[:28]
        yield Static(
            f"[dim]{target}[/]  {icon} {name:<28}  {state_mu}",
            markup=True,
        )


# ── Screen ────────────────────────────────────────────────────────────────────

class PopupScreen(Screen):
    """Filterable window list for the popup switcher."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    CSS = """
    PopupScreen {
        layout: vertical;
        background: $surface;
    }
    #filter-bar {
        height: 3;
        padding: 0 1;
        border-bottom: solid $accent;
    }
    #filter-input {
        border: none;
        background: transparent;
        width: 1fr;
        height: 1;
        margin: 1 0;
    }
    #window-list {
        height: 1fr;
        border: none;
        padding: 0;
    }
    #empty-label {
        color: $text-muted;
        padding: 1 2;
    }
    """

    def __init__(self, config: ClaudreConfig) -> None:
        super().__init__()
        self._config = config
        self._all_entries: list[_Entry] = []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="type to filter…", id="filter-input")
        yield ListView(id="window-list")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#filter-input", Input).focus()
        self.run_worker(self._load_windows(), exclusive=True)

    async def _load_windows(self) -> None:
        tmux = TmuxAdapter()
        detector = JournalStateDetector()
        panes = await tmux.list_panes()

        if self._config.scope == "session":
            session = await tmux.current_session()
            panes = [p for p in panes if p.session == session]

        # One entry per window — take the first pane per (session, window_index)
        seen: set[tuple[str, str]] = set()
        unique: list[TmuxPane] = []
        for p in panes:
            key = (p.session, p.window_index)
            if key not in seen:
                seen.add(key)
                unique.append(p)

        # Skip the claudre dashboard window itself
        current_idx = await tmux.current_window_index()
        current_session = await tmux.current_session()
        unique = [
            p for p in unique
            if not (p.session == current_session and p.window_index == current_idx
                    and p.window_name == "claudre")
        ]

        # Detect states concurrently
        raw = await asyncio.gather(
            *[detector.detect(p) for p in unique],
            return_exceptions=True,
        )

        self._all_entries = [
            _Entry(
                pane=p,
                name=p.window_name or Path(p.pane_path).name or p.pane_id,
                state=s if isinstance(s, ClaudeState) else ClaudeState.UNKNOWN,
            )
            for p, s in zip(unique, raw)
        ]
        self._render_list("")

    def _render_list(self, needle: str) -> None:
        lst = self.query_one("#window-list", ListView)
        lst.clear()
        for entry in self._all_entries:
            if needle and (
                needle not in entry.name.lower()
                and needle not in entry.state.value.lower()
                and needle not in entry.pane.target.lower()
            ):
                continue
            lst.append(_WindowItem(entry))
        # Keep cursor on first visible item
        if lst._nodes:
            lst.index = 0

    # ── Key handling ──────────────────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        """Route arrow keys and Enter to the list while keeping filter focused."""
        if event.key == "down":
            self._move_selection(1)
            event.prevent_default()
            event.stop()
        elif event.key == "up":
            self._move_selection(-1)
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            self._select_highlighted()
            event.prevent_default()
            event.stop()

    def _move_selection(self, delta: int) -> None:
        lst = self.query_one("#window-list", ListView)
        count = lst.item_count
        if count == 0:
            return
        current = lst.index if lst.index is not None else -1
        lst.index = max(0, min(count - 1, current + delta))

    def _select_highlighted(self) -> None:
        lst = self.query_one("#window-list", ListView)
        if lst.index is None or lst.item_count == 0:
            return
        item = lst._nodes[lst.index] if lst.index < len(lst._nodes) else None
        if isinstance(item, _WindowItem):
            asyncio.ensure_future(self._switch_and_exit(item._entry))

    # ── Events ────────────────────────────────────────────────────────────────

    @on(Input.Changed, "#filter-input")
    def on_filter_changed(self, event: Input.Changed) -> None:
        self._render_list(event.value.lower())

    @on(ListView.Selected)
    def on_item_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, _WindowItem):
            asyncio.ensure_future(self._switch_and_exit(event.item._entry))

    def action_cancel(self) -> None:
        self.app.exit()

    # ── Switch ────────────────────────────────────────────────────────────────

    async def _switch_and_exit(self, entry: _Entry) -> None:
        try:
            tmux = TmuxAdapter()
            await tmux.select_window(entry.pane.target)
        except Exception as e:
            log.warning("Failed to select window %s: %s", entry.pane.target, e)
        finally:
            self.app.exit()


# ── App ───────────────────────────────────────────────────────────────────────

class PopupApp(App):
    """Minimal Textual app hosting the popup switcher screen."""

    CSS = """
    App {
        background: $surface;
    }
    """

    def __init__(self, config: ClaudreConfig) -> None:
        super().__init__()
        self._config = config

    def on_mount(self) -> None:
        self.push_screen(PopupScreen(self._config))
