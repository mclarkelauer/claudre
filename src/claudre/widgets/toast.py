"""Toast notification widget for claudre."""

from __future__ import annotations

import asyncio
from collections import deque

from textual.app import App
from textual.widget import Widget
from textual.widgets import Label


class Toast(Widget):
    """Auto-dismissing notification overlay (upper-right)."""

    DEFAULT_CSS = """
    Toast {
        dock: top;
        align: right top;
        margin: 1 2;
        width: auto;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 0 1;
        layer: overlay;
    }
    """

    def __init__(self, message: str, duration: float = 3.0) -> None:
        super().__init__()
        self._message = message
        self._duration = duration

    def compose(self):
        yield Label(self._message)

    def on_mount(self) -> None:
        self.set_timer(self._duration, self._dismiss)

    def _dismiss(self) -> None:
        self.remove()


class ToastManager:
    """Manages a queue of toast notifications, showing one at a time."""

    def __init__(self, app: App, duration: float = 3.0) -> None:
        self._app = app
        self._duration = duration
        self._queue: deque[str] = deque()
        self._active: Toast | None = None

    def show(self, message: str) -> None:
        """Enqueue a toast message."""
        self._queue.append(message)
        if self._active is None:
            self._show_next()

    def _show_next(self) -> None:
        if not self._queue:
            self._active = None
            return
        msg = self._queue.popleft()
        toast = Toast(msg, duration=self._duration)
        self._active = toast
        self._app.mount(toast)
        self._app.set_timer(self._duration + 0.1, self._show_next)
