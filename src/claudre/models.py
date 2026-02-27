"""Data models for claudre."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ClaudeState(Enum):
    NOT_RUNNING = "not running"
    WORKING = "working"
    WAITING = "waiting"


@dataclass
class VcsStatus:
    vcs_type: str | None = None  # "git", "hg", or None
    branch: str = ""
    dirty: bool = False


@dataclass
class TmuxWindow:
    session: str = ""
    window_index: str = ""
    window_name: str = ""
    pane_id: str = ""
    pane_pid: int = 0
    pane_command: str = ""
    pane_path: str = ""

    @property
    def target(self) -> str:
        return f"{self.session}:{self.window_index}"


@dataclass
class ProjectState:
    name: str
    path: str
    configured: bool = True  # False for auto-discovered unconfigured projects
    tmux_window: TmuxWindow | None = None
    claude_state: ClaudeState = ClaudeState.NOT_RUNNING
    vcs: VcsStatus = field(default_factory=VcsStatus)

    @property
    def is_open(self) -> bool:
        return self.tmux_window is not None
