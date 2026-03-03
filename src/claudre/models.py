"""Shared data types for claudre v3."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Union


class ClaudeState(Enum):
    UNKNOWN = "unknown"
    IDLE = "idle"
    OPENING = "opening"
    WORKING = "working"
    WAITING = "waiting"
    SUSPENDED = "suspended"
    CRASHED = "crashed"


@dataclass
class TmuxPane:
    session: str
    window_index: str
    window_name: str
    pane_id: str
    pane_pid: int
    pane_command: str
    pane_path: str

    @property
    def target(self) -> str:
        return f"{self.session}:{self.window_index}"


@dataclass
class VcsStatus:
    branch: str = ""
    dirty: bool = False
    vcs_type: str | None = None


@dataclass
class WindowState:
    pane_id: str
    project_name: str
    path: str
    session: str = ""
    window_index: str = ""
    state: ClaudeState = ClaudeState.UNKNOWN
    vcs: VcsStatus = field(default_factory=VcsStatus)
    summary: str = ""
    summary_updated_at: datetime | None = None
    summary_stale: bool = False
    managed: bool = False  # @claudre_managed=1

    @property
    def target(self) -> str:
        """tmux window target, e.g. 'main:3'."""
        return f"{self.session}:{self.window_index}"


# Typed events for the event bus

@dataclass
class WindowStateChanged:
    pane_id: str
    old: ClaudeState
    new: ClaudeState


@dataclass
class SummaryUpdated:
    pane_id: str
    summary: str


@dataclass
class WindowAdded:
    pane_id: str


@dataclass
class WindowRemoved:
    pane_id: str


RegistryEvent = Union[WindowStateChanged, SummaryUpdated, WindowAdded, WindowRemoved]
