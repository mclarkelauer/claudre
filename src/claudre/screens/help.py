"""Help screen showing all keybindings."""

from __future__ import annotations

from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Label, Static

_HELP_TEXT = """\
[bold]claudre v3 — Keybindings[/]

[bold]Navigation[/]
  ↑/↓       Move selection
  Enter     Jump to selected window
  /         Filter windows

[bold]Window Actions[/]
  n         New window (from template)
  x         Close selected window
  u         Update AI summary
  R         Force full refresh

[bold]Send to Claude[/]
  s         Send message to Claude
  r         Run quick action / command

[bold]Display[/]
  ?         Show this help
  q         Quit dashboard
  Escape    Cancel / dismiss modal

[bold]tmux bindings (set via claudre setup)[/]
  prefix+D  Jump to claudre dashboard
  prefix+N  Create new window
"""


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        ("escape", "dismiss_help", "Close"),
        ("q", "dismiss_help", "Close"),
        ("?", "dismiss_help", "Close"),
    ]

    def compose(self):
        with Vertical(id="help-dialog"):
            yield Static(_HELP_TEXT)

    def action_dismiss_help(self) -> None:
        self.dismiss(None)
