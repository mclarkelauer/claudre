"""Textual App for claudre."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from claudre.config import ClaudreConfig
from claudre.screens.dashboard import DashboardScreen

CSS_PATH = Path(__file__).parent / "css" / "app.tcss"


class ClaudreApp(App):
    CSS_PATH = CSS_PATH

    def __init__(self, config: ClaudreConfig, popup_mode: bool = False) -> None:
        super().__init__()
        self.config = config
        self.popup_mode = popup_mode

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen(self.config, popup_mode=self.popup_mode))
