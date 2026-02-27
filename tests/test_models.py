"""Tests for models.py."""

from claudre.models import ClaudeState, ProjectState, TmuxWindow, VcsStatus


def test_claude_state_values():
    assert ClaudeState.NOT_RUNNING.value == "not running"
    assert ClaudeState.WORKING.value == "working"
    assert ClaudeState.WAITING.value == "waiting"


def test_vcs_status_defaults():
    v = VcsStatus()
    assert v.vcs_type is None
    assert v.branch == ""
    assert v.dirty is False


def test_tmux_window_target():
    tw = TmuxWindow(session="main", window_index="3", window_name="test")
    assert tw.target == "main:3"


def test_project_state_is_open():
    proj = ProjectState(name="test", path="/tmp/test")
    assert proj.is_open is False

    tw = TmuxWindow(session="0", window_index="1")
    proj_open = ProjectState(name="test", path="/tmp/test", tmux_window=tw)
    assert proj_open.is_open is True


def test_project_state_defaults():
    proj = ProjectState(name="test", path="/tmp/test")
    assert proj.configured is True
    assert proj.claude_state is ClaudeState.NOT_RUNNING
    assert proj.vcs.vcs_type is None
