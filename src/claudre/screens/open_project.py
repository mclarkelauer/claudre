"""Modal screen for opening a project."""

from __future__ import annotations

from textual import on
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Input, Label, ListView, ListItem, Static

from claudre import tmux
from claudre.config import ClaudreConfig


class OpenProjectScreen(ModalScreen[None]):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, config: ClaudreConfig) -> None:
        super().__init__()
        self.config = config

    def compose(self):
        with Vertical(id="open-dialog"):
            yield Label("Open Project")
            yield ListView(
                *[
                    ListItem(Static(f"{name} — {proj.path}"), id=f"proj-{name}")
                    for name, proj in self.config.projects.items()
                ],
                id="project-list",
            )
            yield Label("[dim]Or enter a path:[/]")
            yield Input(placeholder="/path/to/project", id="path-input")

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("proj-"):
            name = item_id[5:]
            proj = self.config.projects.get(name)
            if proj:
                layout = self.config.get_layout(proj)
                claude_cmd = self.config.get_claude_cmd(proj)
                self._open_project(name, proj.path, layout, claude_cmd)

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = event.value.strip()
        if path:
            from pathlib import Path

            name = Path(path).name
            self._open_project(name, path)

    def _open_project(
        self,
        name: str,
        path: str,
        layout: str = "claude+terminal",
        claude_cmd: str = "claude --dangerously-skip-permissions",
    ) -> None:
        tmux.create_project_window(name, path, layout, claude_cmd)
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
