"""Tests for registry.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudre.config import ClaudreConfig
from claudre.models import (
    ClaudeState,
    TmuxPane,
    VcsStatus,
    WindowAdded,
    WindowRemoved,
    WindowState,
    WindowStateChanged,
)
from claudre.registry import SessionRegistry


def make_pane(pane_id: str, path: str = "/tmp", command: str = "claude") -> TmuxPane:
    return TmuxPane(
        session="main",
        window_index="0",
        window_name=pane_id,
        pane_id=pane_id,
        pane_pid=100,
        pane_command=command,
        pane_path=path,
    )


def make_registry() -> tuple[SessionRegistry, MagicMock, MagicMock, MagicMock, MagicMock]:
    config = ClaudreConfig(ai_summaries=False)
    tmux = MagicMock()
    tmux.list_panes = AsyncMock(return_value=[])
    tmux.current_session = AsyncMock(return_value="main")
    tmux._is_managed = AsyncMock(return_value=False)
    detector = MagicMock()
    detector.detect = AsyncMock(return_value=ClaudeState.IDLE)
    vcs = MagicMock()
    vcs.get = AsyncMock(return_value=VcsStatus())
    vcs.stop = MagicMock()
    summary = MagicMock()
    summary.should_update = AsyncMock(return_value=False)

    reg = SessionRegistry(
        config=config,
        tmux=tmux,
        detector=detector,
        vcs=vcs,
        summary=summary,
    )
    return reg, tmux, detector, vcs, summary


@pytest.mark.asyncio
async def test_window_added_on_new_pane():
    reg, tmux, *_ = make_registry()
    events = []
    reg.subscribe(events.append)

    pane = make_pane("%1", path="/tmp/proj")
    tmux.list_panes = AsyncMock(return_value=[pane])

    await reg._refresh_once()

    assert any(isinstance(e, WindowAdded) for e in events)
    assert "%1" in reg.windows


@pytest.mark.asyncio
async def test_window_removed_on_gone_pane():
    reg, tmux, *_ = make_registry()

    pane = make_pane("%1", path="/tmp/proj")
    tmux.list_panes = AsyncMock(return_value=[pane])
    await reg._refresh_once()  # Add the pane

    events = []
    reg.subscribe(events.append)

    tmux.list_panes = AsyncMock(return_value=[])
    await reg._refresh_once()  # Remove the pane

    assert any(isinstance(e, WindowRemoved) for e in events)
    assert "%1" not in reg.windows


@pytest.mark.asyncio
async def test_state_change_emits_event():
    reg, tmux, detector, *_ = make_registry()
    events = []
    reg.subscribe(events.append)

    pane = make_pane("%1")
    tmux.list_panes = AsyncMock(return_value=[pane])
    detector.detect = AsyncMock(return_value=ClaudeState.IDLE)
    await reg._refresh_once()

    # Change state
    detector.detect = AsyncMock(return_value=ClaudeState.WORKING)
    await reg._refresh_once()

    state_changes = [e for e in events if isinstance(e, WindowStateChanged)]
    assert any(e.new == ClaudeState.WORKING for e in state_changes)


def test_subscribe_and_emit():
    reg, *_ = make_registry()
    received = []
    reg.subscribe(received.append)

    event = WindowAdded(pane_id="%99")
    reg._emit(event)
    assert event in received


def test_request_summary_marks_stale():
    reg, *_ = make_registry()
    ws = WindowState(pane_id="%1", project_name="test", path="/tmp")
    reg._windows["%1"] = ws

    reg.request_summary("%1")
    assert ws.summary_stale is True
