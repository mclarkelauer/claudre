"""Tests for popup screen logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from claudre.config import ClaudreConfig
from claudre.models import ClaudeState, TmuxPane
from claudre.screens.popup import _Entry, _state_icon, _state_markup, _WindowItem


def make_pane(session: str, window_index: str, window_name: str, pane_id: str) -> TmuxPane:
    return TmuxPane(
        session=session,
        window_index=window_index,
        window_name=window_name,
        pane_id=pane_id,
        pane_pid=100,
        pane_command="bash",
        pane_path="/tmp",
    )


# ── Icon / markup helpers ─────────────────────────────────────────────────────

def test_state_icons_cover_all_states():
    for state in ClaudeState:
        icon = _state_icon(state)
        assert isinstance(icon, str) and len(icon) == 1


def test_state_markup_contains_label():
    assert "WORKING" in _state_markup(ClaudeState.WORKING)
    assert "WAITING" in _state_markup(ClaudeState.WAITING)
    assert "CRASHED" in _state_markup(ClaudeState.CRASHED)
    assert "idle"    in _state_markup(ClaudeState.IDLE)


# ── _load_windows deduplication logic (extracted for unit testing) ────────────

def _deduplicate(panes: list[TmuxPane]) -> list[TmuxPane]:
    """Mirror the deduplication logic from PopupScreen._load_windows."""
    seen: set[tuple[str, str]] = set()
    unique: list[TmuxPane] = []
    for p in panes:
        key = (p.session, p.window_index)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def test_deduplication_one_per_window():
    panes = [
        make_pane("main", "0", "shell",  "%0"),
        make_pane("main", "0", "shell",  "%1"),   # second pane in same window
        make_pane("main", "1", "my-api", "%2"),
    ]
    unique = _deduplicate(panes)
    assert len(unique) == 2
    assert unique[0].pane_id == "%0"
    assert unique[1].pane_id == "%2"


def test_deduplication_across_sessions():
    panes = [
        make_pane("main", "0", "shell",  "%0"),
        make_pane("work", "0", "editor", "%1"),
    ]
    unique = _deduplicate(panes)
    assert len(unique) == 2


# ── Filter logic (mirrors PopupScreen._render_list filter) ───────────────────

def _matches(entry: _Entry, needle: str) -> bool:
    if not needle:
        return True
    return (
        needle in entry.name.lower()
        or needle in entry.state.value.lower()
        or needle in entry.pane.target.lower()
    )


def test_filter_by_name():
    entry = _Entry(
        pane=make_pane("main", "1", "my-api", "%1"),
        name="my-api",
        state=ClaudeState.WAITING,
    )
    assert _matches(entry, "api")
    assert _matches(entry, "my-api")
    assert not _matches(entry, "frontend")


def test_filter_by_state():
    entry = _Entry(
        pane=make_pane("main", "2", "frontend", "%2"),
        name="frontend",
        state=ClaudeState.CRASHED,
    )
    assert _matches(entry, "crashed")
    assert not _matches(entry, "waiting")


def test_filter_by_target():
    entry = _Entry(
        pane=make_pane("work", "3", "infra", "%3"),
        name="infra",
        state=ClaudeState.IDLE,
    )
    assert _matches(entry, "work:3")
    assert _matches(entry, "work")
    assert not _matches(entry, "main")


def test_empty_needle_matches_all():
    entry = _Entry(
        pane=make_pane("main", "0", "proj", "%0"),
        name="proj",
        state=ClaudeState.IDLE,
    )
    assert _matches(entry, "")


# ── Dashboard window exclusion logic ─────────────────────────────────────────

def test_claudre_window_excluded_from_popup():
    """The claudre dashboard window should not appear in the popup list."""
    panes = [
        make_pane("main", "0", "claudre", "%0"),  # dashboard — should be excluded
        make_pane("main", "1", "my-api",  "%1"),
    ]
    current_session = "main"
    current_idx = "0"

    filtered = [
        p for p in panes
        if not (
            p.session == current_session
            and p.window_index == current_idx
            and p.window_name == "claudre"
        )
    ]
    assert len(filtered) == 1
    assert filtered[0].window_name == "my-api"
