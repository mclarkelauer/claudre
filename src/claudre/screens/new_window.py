"""Two-step modal for creating a new tmux window."""

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Input, Label, ListView, ListItem, Static

from claudre.config import ClaudreConfig


@dataclass
class NewWindowResult:
    template_name: str
    project_name: str
    start_directory: str


class NewWindowScreen(ModalScreen[NewWindowResult | None]):
    """Template selector + path/name input."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, config: ClaudreConfig, session: str) -> None:
        super().__init__()
        self._config = config
        self._session = session
        self._selected_template: str = config.defaults.template

    def compose(self):
        # Build template list: builtins + user-defined
        from claudre.templates import _BUILTIN_TEMPLATES
        template_names = list(_BUILTIN_TEMPLATES.keys())
        for name in self._config.templates:
            if name not in template_names:
                template_names.append(name)

        with Vertical(id="new-window-dialog"):
            yield Label("Select template:")
            yield ListView(
                *[
                    ListItem(Static(name), id=f"tmpl-{name}")
                    for name in template_names
                ],
                id="template-list",
            )
            yield Label("Project directory:")
            yield Input(placeholder="/path/to/project", id="dir-input")
            yield Label("Project name (optional):")
            yield Input(placeholder="leave blank to use dir name", id="name-input")

    def on_mount(self) -> None:
        self.query_one("#template-list", ListView).focus()

    @on(ListView.Selected)
    def on_template_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("tmpl-"):
            self._selected_template = item_id[5:]
            self.query_one("#dir-input", Input).focus()

    @on(Input.Submitted, "#name-input")
    def on_name_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    @on(Input.Submitted, "#dir-input")
    def on_dir_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#name-input", Input).focus()

    def _submit(self) -> None:
        from pathlib import Path
        dir_val = self.query_one("#dir-input", Input).value.strip()
        name_val = self.query_one("#name-input", Input).value.strip()

        if not dir_val:
            return

        start_dir = str(Path(dir_val).expanduser())
        project_name = name_val or Path(start_dir).name

        self.dismiss(
            NewWindowResult(
                template_name=self._selected_template,
                project_name=project_name,
                start_directory=start_dir,
            )
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
