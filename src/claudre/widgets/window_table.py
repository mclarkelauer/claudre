"""DataTable widget showing tmux window status."""

from __future__ import annotations

from textual.widgets import DataTable
from textual.widgets.data_table import ColumnKey

from claudre.models import ClaudeState, WindowState


def _state_markup(state: ClaudeState) -> str:
    match state:
        case ClaudeState.WORKING:
            return "[bold green]WORKING[/]"
        case ClaudeState.WAITING:
            return "[bold yellow]WAITING[/]"
        case ClaudeState.CRASHED:
            return "[bold red]CRASHED[/]"
        case ClaudeState.SUSPENDED:
            return "[dim]SUSPENDED[/]"
        case ClaudeState.IDLE:
            return "[dim]idle[/]"
        case ClaudeState.OPENING:
            return "[cyan]OPENING[/]"
        case _:
            return "[dim]unknown[/]"


def _row_cells(ws: WindowState) -> tuple[str, ...]:
    managed = "[green]●[/]" if ws.managed else "[dim]○[/]"
    branch = ws.vcs.branch or ""
    dirty = "[red]*[/]" if ws.vcs.dirty else ""
    state = _state_markup(ws.state)
    summary = ws.summary[:80] if ws.summary else "[dim]—[/]"
    if ws.summary_stale and ws.summary:
        summary = f"[dim]{summary}[/]"
    return (managed, ws.project_name, branch, dirty, state, summary)


# Column identifiers used with update_cell()
_COL_MANAGED  = "managed"
_COL_PROJECT  = "project"
_COL_BRANCH   = "branch"
_COL_DIRTY    = "dirty"
_COL_STATE    = "state"
_COL_SUMMARY  = "summary"

_COLUMNS: list[tuple[str, str]] = [
    (_COL_MANAGED,  "#"),
    (_COL_PROJECT,  "Project"),
    (_COL_BRANCH,   "Branch"),
    (_COL_DIRTY,    "M"),
    (_COL_STATE,    "State"),
    (_COL_SUMMARY,  "Summary"),
]


class WindowTable(DataTable):
    """Table displaying all tmux windows and their status."""

    BINDINGS: list = []
    _filter_text: str = ""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        for col_key, label in _COLUMNS:
            self.add_column(label, key=col_key)

    # ------------------------------------------------------------------ #
    # Public API — incremental updates
    # ------------------------------------------------------------------ #

    def add_window(self, ws: WindowState) -> None:
        """Append a new row for the given window."""
        if self._filter_matches(ws):
            self.add_row(*_row_cells(ws), key=ws.pane_id)

    def update_window(self, ws: WindowState) -> None:
        """Update the row for an existing window in-place."""
        if not self._filter_matches(ws):
            # Row should not be visible — remove it if present
            try:
                self.remove_row(ws.pane_id)
            except Exception:
                pass
            return

        cells = _row_cells(ws)
        col_keys = [k for k, _ in _COLUMNS]
        try:
            for col_key, value in zip(col_keys, cells):
                self.update_cell(ws.pane_id, col_key, value)
        except Exception:
            # Row doesn't exist yet — add it
            try:
                self.add_row(*cells, key=ws.pane_id)
            except Exception:
                pass

    def remove_window(self, pane_id: str) -> None:
        """Remove the row for a given pane_id."""
        try:
            self.remove_row(pane_id)
        except Exception:
            pass

    def rebuild(self, windows: dict[str, WindowState]) -> None:
        """Full rebuild — preserves cursor position."""
        selected_key = self._selected_key()
        self.clear()
        restore_row = 0
        for i, ws in enumerate(windows.values()):
            if self._filter_matches(ws):
                self.add_row(*_row_cells(ws), key=ws.pane_id)
                if ws.pane_id == selected_key:
                    restore_row = i
        if self.row_count > 0:
            self.move_cursor(row=min(restore_row, self.row_count - 1))

    def get_selected_pane_id(self) -> str | None:
        return self._selected_key()

    def set_filter(self, text: str) -> None:
        self._filter_text = text.lower()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _selected_key(self) -> str | None:
        if self.row_count == 0:
            return None
        try:
            return self.coordinate_to_cell_key(self.cursor_coordinate).row_key.value  # type: ignore[return-value]
        except Exception:
            return None

    def _filter_matches(self, ws: WindowState) -> bool:
        if not self._filter_text:
            return True
        needle = self._filter_text
        return (
            needle in ws.project_name.lower()
            or needle in ws.path.lower()
            or needle in ws.state.value.lower()
            or needle in ws.summary.lower()
        )
