"""Path-input modal for creating a new claude+terminal window."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.events import Key
from textual.message import Message
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Input, Label, ListItem, ListView, Static

from claudre.config import ClaudreConfig
from claudre.logger import get_logger

log = get_logger(__name__)


@dataclass
class NewWindowResult:
    template_name: str
    project_name: str
    start_directory: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_matches(current: str) -> list[Path]:
    """Return directories that complete the current input value."""
    expanded = os.path.expanduser(current)
    if not current or current.endswith("/"):
        search_dir = Path(expanded)
        prefix = ""
    else:
        search_dir = Path(expanded).parent
        prefix = Path(expanded).name
    try:
        return sorted(
            p for p in search_dir.iterdir()
            if p.name.startswith(prefix) and p.is_dir()
        )
    except (OSError, PermissionError):
        return []


def _display_path(input_val: str, path: Path) -> str:
    """Use ~ notation when the original input started with ~."""
    s = str(path)
    home = str(Path.home())
    if input_val.startswith("~") and s.startswith(home):
        return "~" + s[len(home):]
    return s


# ── Widgets ───────────────────────────────────────────────────────────────────

class _PathInput(Input):
    """Input that posts TabPressed instead of cycling focus."""

    class TabPressed(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def on_key(self, event: Key) -> None:
        if event.key == "tab":
            self.post_message(self.TabPressed(self.value))
            event.prevent_default()
            event.stop()


class _CompletionItem(ListItem):
    """A completion entry that carries its resolved Path."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def compose(self) -> ComposeResult:
        yield Static(self.path.name)


class _CompletionList(ListView):
    """Dropdown that returns focus to the path input on Escape."""

    BINDINGS = [("escape", "close_list", "Close")]

    def action_close_list(self) -> None:
        self.display = False
        self.screen.query_one("#dir-input", _PathInput).focus()


# ── Screen ────────────────────────────────────────────────────────────────────

class NewWindowScreen(ModalScreen[NewWindowResult | None]):
    """Modal that opens a claude (left) + terminal (right) window at a chosen path."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, config: ClaudreConfig, session: str) -> None:
        super().__init__()
        self._config = config
        self._session = session
        self._tab_input_val: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="new-window-dialog"):
            yield Label("Open claude + terminal at:")
            yield _PathInput(
                placeholder="~/repos/my-project   (Tab to complete)",
                id="dir-input",
            )
            yield _CompletionList(id="completions")
            yield Static(
                "[dim]Tab: complete   ↑↓ / Enter: pick   Esc: cancel[/]",
                markup=True,
                id="new-window-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#dir-input", _PathInput).focus()
        self.query_one("#completions", _CompletionList).display = False

    # ── Tab completion ────────────────────────────────────────────────────

    @on(_PathInput.TabPressed)
    def on_tab_pressed(self, event: _PathInput.TabPressed) -> None:
        lst = self.query_one("#completions", _CompletionList)
        lst.display = False

        matches = _get_matches(event.value)
        if not matches:
            return

        self._tab_input_val = event.value

        if len(matches) == 1:
            self._fill_path(matches[0])
        else:
            lst.clear()
            for m in matches:
                lst.append(_CompletionItem(m))
            lst.display = True
            lst.index = 0
            lst.focus()

    @on(ListView.Selected, "#completions")
    def on_completion_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, _CompletionItem):
            self._fill_path(event.item.path)
        self.query_one("#completions", _CompletionList).display = False
        self.query_one("#dir-input", _PathInput).focus()

    @on(Input.Changed, "#dir-input")
    def on_dir_changed(self, event: Input.Changed) -> None:
        self.query_one("#completions", _CompletionList).display = False

    def _fill_path(self, path: Path) -> None:
        new_val = _display_path(self._tab_input_val, path) + "/"
        inp = self.query_one("#dir-input", _PathInput)
        inp.value = new_val
        inp.cursor_position = len(new_val)

    # ── Submit / cancel ───────────────────────────────────────────────────

    @on(Input.Submitted, "#dir-input")
    def on_dir_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        dir_val = self.query_one("#dir-input", _PathInput).value.strip()
        if not dir_val:
            return
        start_dir = str(Path(dir_val).expanduser().resolve())
        project_name = Path(start_dir).name
        log.debug("NewWindowScreen: opening %s as %r", start_dir, project_name)
        self.dismiss(
            NewWindowResult(
                template_name="claude+terminal",
                project_name=project_name,
                start_directory=start_dir,
            )
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
