"""Modal for running a quick action or custom command."""

from __future__ import annotations

from textual import on
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Input, Label, ListView, ListItem, Static


class RunCommandScreen(ModalScreen[str | None]):
    """ListView of quick_actions + free-form input."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, project_name: str, quick_actions: list[str]) -> None:
        super().__init__()
        self._project_name = project_name
        self._quick_actions = quick_actions

    def compose(self):
        with Vertical(id="run-dialog"):
            yield Label(f"Run in [bold]{self._project_name}[/]:")
            if self._quick_actions:
                yield ListView(
                    *[
                        ListItem(Static(action), id=f"action-{i}")
                        for i, action in enumerate(self._quick_actions)
                    ],
                    id="action-list",
                )
            yield Label("[dim]Or enter command:[/]")
            yield Input(placeholder="bash command…", id="cmd-input")

    def on_mount(self) -> None:
        if self._quick_actions:
            self.query_one(ListView).focus()
        else:
            self.query_one("#cmd-input", Input).focus()

    @on(ListView.Selected)
    def on_action_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("action-"):
            idx = int(item_id[7:])
            self.dismiss(self._quick_actions[idx])

    @on(Input.Submitted)
    def on_cmd_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.dismiss(text if text else None)

    def action_cancel(self) -> None:
        self.dismiss(None)
