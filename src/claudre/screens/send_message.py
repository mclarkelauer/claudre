"""Modal for sending a message to a Claude pane."""

from __future__ import annotations

from textual import on
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Input, Label


class SendMessageScreen(ModalScreen[str | None]):
    """Single-input modal to send text to a Claude session."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, project_name: str) -> None:
        super().__init__()
        self._project_name = project_name

    def compose(self):
        with Vertical(id="send-dialog"):
            yield Label(f"Send to [bold]{self._project_name}[/]:")
            yield Input(placeholder="Type message…", id="message-input")

    def on_mount(self) -> None:
        self.query_one("#message-input", Input).focus()

    @on(Input.Submitted)
    def on_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.dismiss(text if text else None)

    def action_cancel(self) -> None:
        self.dismiss(None)
