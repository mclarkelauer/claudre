"""Tmux subprocess wrappers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from claudre.models import TmuxWindow

CLAUDRE_WINDOW_NAME = "claudre"

# Format string for tmux list-panes
_PANE_FMT = "#{session_name}\t#{window_index}\t#{window_name}\t#{pane_id}\t#{pane_pid}\t#{pane_current_command}\t#{pane_current_path}"


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a tmux command with default timeout."""
    kwargs.setdefault("timeout", 5)
    return subprocess.run(args, **kwargs)


def is_inside_tmux() -> bool:
    return "TMUX" in os.environ


def get_current_window_target() -> str | None:
    """Get the session:window_index of the current tmux window."""
    if not is_inside_tmux():
        return None
    try:
        result = _run(
            ["tmux", "display-message", "-p", "#{session_name}:#{window_index}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def rename_current_window(name: str) -> None:
    """Rename the current tmux window and disable auto-rename."""
    try:
        _run(["tmux", "rename-window", name])
        _run(["tmux", "set-option", "-w", "allow-rename", "off"])
        _run(["tmux", "set-option", "-w", "automatic-rename", "off"])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def list_all_panes() -> list[TmuxWindow]:
    """List all panes across all tmux sessions."""
    try:
        result = _run(
            ["tmux", "list-panes", "-a", "-F", _PANE_FMT],
            capture_output=True,
            text=True,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if result.returncode != 0:
        return []

    panes = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        panes.append(
            TmuxWindow(
                session=parts[0],
                window_index=parts[1],
                window_name=parts[2],
                pane_id=parts[3],
                pane_pid=int(parts[4]),
                pane_command=parts[5],
                pane_path=parts[6],
            )
        )
    return panes


def find_claudre_window() -> str | None:
    """Find the claudre dashboard window target, if it exists."""
    panes = list_all_panes()
    for pane in panes:
        if pane.window_name == CLAUDRE_WINDOW_NAME:
            return pane.target
    return None


def create_project_window(
    name: str,
    path: str,
    layout: str = "claude+terminal",
    claude_cmd: str = "claude --dangerously-skip-permissions",
) -> None:
    """Create a new tmux window with the specified layout."""
    # Create new window with project name, disable auto-rename
    _run(["tmux", "new-window", "-n", name, "-c", path], check=True)
    _run(["tmux", "set-option", "-w", "allow-rename", "off"])
    _run(["tmux", "set-option", "-w", "automatic-rename", "off"])

    if layout == "claude+vim+terminal":
        # Split right for vim
        _run(["tmux", "split-window", "-h", "-c", path], check=True)
        # Split bottom-right for terminal
        _run(["tmux", "split-window", "-v", "-c", path], check=True)
        # Send vim to top-right pane
        _run(["tmux", "send-keys", "-t", ":.1", "vim", "Enter"])
        # Send claude to left pane
        _run(["tmux", "send-keys", "-t", ":.0", claude_cmd, "Enter"])
        # Select left pane
        _run(["tmux", "select-pane", "-t", ":.0"])
    else:
        # claude+terminal: two vertical panes
        _run(["tmux", "split-window", "-h", "-c", path], check=True)
        # Send claude to left pane
        _run(["tmux", "send-keys", "-t", ":.0", claude_cmd, "Enter"])
        # Select left pane
        _run(["tmux", "select-pane", "-t", ":.0"])


def rename_window(target: str, name: str) -> None:
    """Rename a tmux window and lock the name."""
    try:
        _run(["tmux", "rename-window", "-t", target, name])
        _run(["tmux", "set-option", "-w", "-t", target, "allow-rename", "off"])
        _run(["tmux", "set-option", "-w", "-t", target, "automatic-rename", "off"])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def rename_claude_windows(config_projects: dict | None = None) -> list[tuple[str, str]]:
    """Find windows running claude and rename them to their repo directory name.

    If config_projects is provided (name -> ProjectConfig), uses the config name
    for matching paths. Otherwise falls back to the directory basename.

    Returns list of (old_name, new_name) for windows that were renamed.
    """
    panes = list_all_panes()

    # Build path -> config name lookup
    path_to_name: dict[str, str] = {}
    if config_projects:
        for name, proj in config_projects.items():
            path_to_name[proj.path] = name

    # Group panes by window (session:index)
    windows: dict[str, list[TmuxWindow]] = {}
    for pane in panes:
        key = pane.target
        windows.setdefault(key, []).append(pane)

    renamed = []
    for target, win_panes in windows.items():
        has_claude = any(p.pane_command == "claude" for p in win_panes)
        if not has_claude:
            continue

        current_name = win_panes[0].window_name
        # Skip the claudre dashboard window
        if current_name == CLAUDRE_WINDOW_NAME:
            continue

        # Use path from any pane in the window
        path = win_panes[0].pane_path
        desired_name = path_to_name.get(path, Path(path).name)

        if current_name != desired_name:
            rename_window(target, desired_name)
            renamed.append((current_name, desired_name))

    return renamed


def switch_to_window(target: str) -> None:
    """Switch to the specified tmux window."""
    _run(["tmux", "select-window", "-t", target])


def kill_window(target: str) -> None:
    """Kill the specified tmux window."""
    _run(["tmux", "kill-window", "-t", target])
