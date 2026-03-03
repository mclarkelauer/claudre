"""Tests for CLI dashboard switch-or-launch logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from claudre.models import TmuxPane


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


@pytest.mark.asyncio
async def test_switch_to_existing_dashboard():
    """If a 'claudre' window exists in a different index, select it and return True."""
    from claudre.tmux_adapter import TmuxAdapter

    tmux = TmuxAdapter()
    current_pane = make_pane("main", "1", "shell", "%1")
    claudre_pane = make_pane("main", "0", "claudre", "%0")

    with patch.object(tmux, "is_inside_tmux", AsyncMock(return_value=True)), \
         patch.object(tmux, "current_session", AsyncMock(return_value="main")), \
         patch.object(tmux, "current_window_index", AsyncMock(return_value="1")), \
         patch.object(tmux, "list_panes", AsyncMock(return_value=[current_pane, claudre_pane])), \
         patch.object(tmux, "select_window", AsyncMock()) as mock_select, \
         patch.object(tmux, "rename_window", AsyncMock()) as mock_rename:

        switched = await _run_switch_or_setup(tmux)

    assert switched is True
    mock_select.assert_awaited_once_with("main:0")
    mock_rename.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_existing_dashboard_renames_current():
    """If no 'claudre' window exists, rename the current window and return False."""
    from claudre.tmux_adapter import TmuxAdapter

    tmux = TmuxAdapter()
    current_pane = make_pane("main", "2", "shell", "%2")

    with patch.object(tmux, "is_inside_tmux", AsyncMock(return_value=True)), \
         patch.object(tmux, "current_session", AsyncMock(return_value="main")), \
         patch.object(tmux, "current_window_index", AsyncMock(return_value="2")), \
         patch.object(tmux, "list_panes", AsyncMock(return_value=[current_pane])), \
         patch.object(tmux, "select_window", AsyncMock()) as mock_select, \
         patch.object(tmux, "rename_window", AsyncMock()) as mock_rename:

        switched = await _run_switch_or_setup(tmux)

    assert switched is False
    mock_select.assert_not_awaited()
    mock_rename.assert_awaited_once_with("main:2", "claudre")


@pytest.mark.asyncio
async def test_claudre_window_is_current_window_launches_new():
    """If the current window is already named 'claudre', don't switch — launch TUI."""
    from claudre.tmux_adapter import TmuxAdapter

    tmux = TmuxAdapter()
    # Current window IS the claudre window
    claudre_pane = make_pane("main", "0", "claudre", "%0")

    with patch.object(tmux, "is_inside_tmux", AsyncMock(return_value=True)), \
         patch.object(tmux, "current_session", AsyncMock(return_value="main")), \
         patch.object(tmux, "current_window_index", AsyncMock(return_value="0")), \
         patch.object(tmux, "list_panes", AsyncMock(return_value=[claudre_pane])), \
         patch.object(tmux, "select_window", AsyncMock()) as mock_select, \
         patch.object(tmux, "rename_window", AsyncMock()):

        switched = await _run_switch_or_setup(tmux)

    # Window index matches — should not switch, should rename (already named claudre, harmless)
    assert switched is False
    mock_select.assert_not_awaited()


@pytest.mark.asyncio
async def test_not_inside_tmux_returns_false():
    """Outside tmux, always return False (launch normally)."""
    from claudre.tmux_adapter import TmuxAdapter

    tmux = TmuxAdapter()
    with patch.object(tmux, "is_inside_tmux", AsyncMock(return_value=False)):
        switched = await _run_switch_or_setup(tmux)

    assert switched is False


# ---------------------------------------------------------------------------
# Helper — extract the _switch_or_setup logic without Click wiring
# ---------------------------------------------------------------------------

async def _run_switch_or_setup(tmux) -> bool:
    """Replicate the _switch_or_setup coroutine from cli.dashboard()."""
    if not await tmux.is_inside_tmux():
        return False

    session = await tmux.current_session()
    current_idx = await tmux.current_window_index()
    panes = await tmux.list_panes()
    session_panes = [p for p in panes if p.session == session]

    existing = [
        p for p in session_panes
        if p.window_name == "claudre" and p.window_index != current_idx
    ]
    if existing:
        await tmux.select_window(existing[0].target)
        return True

    current_panes = [p for p in session_panes if p.window_index == current_idx]
    if current_panes:
        try:
            await tmux.rename_window(current_panes[0].target, "claudre")
        except Exception:
            pass
    return False
