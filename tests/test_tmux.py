"""Tests for tmux.py."""

import subprocess

from claudre.models import TmuxWindow
from claudre.tmux import (
    CLAUDRE_WINDOW_NAME,
    list_all_panes,
    rename_claude_windows,
)


def test_list_all_panes_no_tmux(monkeypatch):
    """list_all_panes should return empty list when tmux isn't available."""

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("tmux not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert list_all_panes() == []


def test_list_all_panes_parses_output(monkeypatch):
    """list_all_panes should parse tmux output into TmuxWindow objects."""
    fake_output = (
        "main\t1\tproject\t%0\t1234\tclaude\t/home/user/repos/project\n"
        "main\t1\tproject\t%1\t1235\tbash\t/home/user/repos/project\n"
        "main\t2\tother\t%2\t1236\tvim\t/home/user/repos/other\n"
    )

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=fake_output, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    panes = list_all_panes()

    assert len(panes) == 3
    assert panes[0].session == "main"
    assert panes[0].window_index == "1"
    assert panes[0].window_name == "project"
    assert panes[0].pane_pid == 1234
    assert panes[0].pane_command == "claude"
    assert panes[0].pane_path == "/home/user/repos/project"
    assert panes[0].target == "main:1"


def test_list_all_panes_handles_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="error")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert list_all_panes() == []


def test_rename_claude_windows_no_rename_needed(monkeypatch):
    """Windows already named correctly should not be renamed."""
    from claudre.config import ProjectConfig

    panes = [
        TmuxWindow(
            session="main",
            window_index="1",
            window_name="myproject",
            pane_id="%0",
            pane_pid=123,
            pane_command="claude",
            pane_path="/home/user/repos/myproject",
        ),
    ]

    monkeypatch.setattr("claudre.tmux.list_all_panes", lambda: panes)

    projects = {"myproject": ProjectConfig(path="/home/user/repos/myproject")}
    renamed = rename_claude_windows(projects)
    assert renamed == []


def test_rename_claude_windows_renames(monkeypatch):
    """Windows with wrong names should be renamed."""
    from claudre.config import ProjectConfig

    panes = [
        TmuxWindow(
            session="main",
            window_index="1",
            window_name="bash",
            pane_id="%0",
            pane_pid=123,
            pane_command="claude",
            pane_path="/home/user/repos/myproject",
        ),
    ]

    renamed_calls = []

    def fake_rename(target, name):
        renamed_calls.append((target, name))

    monkeypatch.setattr("claudre.tmux.list_all_panes", lambda: panes)
    monkeypatch.setattr("claudre.tmux.rename_window", fake_rename)

    projects = {"myproject": ProjectConfig(path="/home/user/repos/myproject")}
    renamed = rename_claude_windows(projects)

    assert len(renamed) == 1
    assert renamed[0] == ("bash", "myproject")
    assert renamed_calls == [("main:1", "myproject")]


def test_rename_claude_windows_skips_claudre(monkeypatch):
    """The claudre dashboard window should never be renamed."""
    panes = [
        TmuxWindow(
            session="main",
            window_index="1",
            window_name=CLAUDRE_WINDOW_NAME,
            pane_id="%0",
            pane_pid=123,
            pane_command="claude",
            pane_path="/home/user/repos/claudre",
        ),
    ]

    monkeypatch.setattr("claudre.tmux.list_all_panes", lambda: panes)
    renamed = rename_claude_windows(None)
    assert renamed == []


def test_rename_claude_windows_uses_dirname_fallback(monkeypatch):
    """Without config, should use directory basename."""
    panes = [
        TmuxWindow(
            session="main",
            window_index="2",
            window_name="bash",
            pane_id="%0",
            pane_pid=123,
            pane_command="claude",
            pane_path="/home/user/repos/unknown-project",
        ),
    ]

    renamed_calls = []

    def fake_rename(target, name):
        renamed_calls.append((target, name))

    monkeypatch.setattr("claudre.tmux.list_all_panes", lambda: panes)
    monkeypatch.setattr("claudre.tmux.rename_window", fake_rename)

    renamed = rename_claude_windows(None)
    assert len(renamed) == 1
    assert renamed[0] == ("bash", "unknown-project")
