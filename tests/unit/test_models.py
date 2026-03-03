"""Tests for models.py."""

from claudre.models import (
    ClaudeState,
    TmuxPane,
    VcsStatus,
    WindowState,
    WindowAdded,
    WindowRemoved,
    WindowStateChanged,
    SummaryUpdated,
)


def test_claude_state_values():
    assert ClaudeState.UNKNOWN.value == "unknown"
    assert ClaudeState.IDLE.value == "idle"
    assert ClaudeState.WORKING.value == "working"
    assert ClaudeState.WAITING.value == "waiting"
    assert ClaudeState.CRASHED.value == "crashed"
    assert ClaudeState.SUSPENDED.value == "suspended"
    assert ClaudeState.OPENING.value == "opening"


def test_tmux_pane_target():
    pane = TmuxPane(
        session="main",
        window_index="3",
        window_name="my-project",
        pane_id="%10",
        pane_pid=12345,
        pane_command="claude",
        pane_path="/home/user/project",
    )
    assert pane.target == "main:3"


def test_window_state_defaults():
    ws = WindowState(pane_id="%1", project_name="test", path="/tmp/test")
    assert ws.state == ClaudeState.UNKNOWN
    assert ws.summary == ""
    assert ws.summary_stale is False
    assert ws.managed is False
    assert ws.session == ""
    assert ws.window_index == ""
    assert isinstance(ws.vcs, VcsStatus)


def test_window_state_target():
    ws = WindowState(
        pane_id="%5",
        project_name="proj",
        path="/tmp/proj",
        session="main",
        window_index="3",
    )
    assert ws.target == "main:3"


def test_window_state_target_empty():
    ws = WindowState(pane_id="%1", project_name="test", path="/tmp")
    assert ws.target == ":"


def test_event_types():
    e1 = WindowAdded(pane_id="%1")
    assert e1.pane_id == "%1"

    e2 = WindowRemoved(pane_id="%2")
    assert e2.pane_id == "%2"

    e3 = WindowStateChanged(pane_id="%3", old=ClaudeState.IDLE, new=ClaudeState.WORKING)
    assert e3.old == ClaudeState.IDLE
    assert e3.new == ClaudeState.WORKING

    e4 = SummaryUpdated(pane_id="%4", summary="doing stuff")
    assert e4.summary == "doing stuff"
