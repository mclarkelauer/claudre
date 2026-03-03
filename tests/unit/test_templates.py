"""Tests for templates.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudre.config import ClaudreConfig, TemplateConfig
from claudre.models import TmuxPane
from claudre.templates import resolve_template, _BUILTIN_TEMPLATES
from claudre.tmux_adapter import WindowSpec


def make_config(**kwargs) -> ClaudreConfig:
    return ClaudreConfig(**kwargs)


def test_resolve_builtin():
    config = make_config()
    tmpl = resolve_template("claude+terminal", config)
    assert tmpl.layout == "even-horizontal"
    assert "claude" in tmpl.pane_commands


def test_resolve_user_template():
    custom = TemplateConfig(layout="main-left", pane_commands=["nvim", "bash"])
    config = make_config(templates={"my-template": custom})
    tmpl = resolve_template("my-template", config)
    assert tmpl.layout == "main-left"
    assert tmpl.pane_commands == ["nvim", "bash"]


def test_resolve_unknown_falls_back():
    config = make_config()
    tmpl = resolve_template("nonexistent", config)
    assert tmpl == _BUILTIN_TEMPLATES["claude+terminal"]


def test_window_spec_fields():
    spec = WindowSpec(
        session="main",
        template_name="claude+terminal",
        project_name="myproj",
        start_directory="/home/user/myproj",
    )
    assert spec.session == "main"
    assert spec.template_name == "claude+terminal"
    assert spec.project_name == "myproj"


@pytest.mark.asyncio
async def test_create_from_template_single_pane():
    """create_from_template with a single-pane template marks managed and sends command."""
    config = make_config()
    spec = WindowSpec(
        session="main",
        template_name="claude",
        project_name="testproj",
        start_directory="/tmp/testproj",
    )

    primary = TmuxPane(
        session="main",
        window_index="2",
        window_name="testproj",
        pane_id="%5",
        pane_pid=999,
        pane_command="bash",
        pane_path="/tmp/testproj",
    )

    tmux = MagicMock()
    tmux.create_window = AsyncMock(return_value=primary)
    tmux.set_window_option = AsyncMock()
    tmux.rename_window = AsyncMock()
    tmux.select_layout = AsyncMock()
    tmux.split_window = AsyncMock()
    tmux.send_keys = AsyncMock()
    tmux.select_pane = AsyncMock()
    tmux.list_panes = AsyncMock(return_value=[primary])
    tmux.MANAGED_OPTION = "@claudre_managed"

    from claudre.templates import create_from_template
    result = await create_from_template(tmux, spec, config)

    assert result is primary
    # Should mark the window as managed
    tmux.set_window_option.assert_awaited_once_with(
        primary.target, "@claudre_managed", "1"
    )
    # Should rename the window
    tmux.rename_window.assert_awaited_once_with(primary.target, "testproj")
    # Should send the claude command to the single pane
    tmux.send_keys.assert_awaited_once()
    call_args = tmux.send_keys.call_args
    assert call_args[0][0] == "%5"
    assert "claude" in call_args[0][1]
    # Single-pane template — no splits
    tmux.split_window.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_from_template_two_panes():
    """create_from_template with claude+terminal splits and sends to both panes."""
    config = make_config()
    spec = WindowSpec(
        session="main",
        template_name="claude+terminal",
        project_name="myproj",
        start_directory="/tmp/myproj",
    )

    pane1 = TmuxPane(
        session="main", window_index="3", window_name="myproj",
        pane_id="%10", pane_pid=100, pane_command="bash", pane_path="/tmp/myproj",
    )
    pane2 = TmuxPane(
        session="main", window_index="3", window_name="myproj",
        pane_id="%11", pane_pid=101, pane_command="bash", pane_path="/tmp/myproj",
    )

    tmux = MagicMock()
    tmux.create_window = AsyncMock(return_value=pane1)
    tmux.set_window_option = AsyncMock()
    tmux.rename_window = AsyncMock()
    tmux.select_layout = AsyncMock()
    tmux.split_window = AsyncMock()
    tmux.send_keys = AsyncMock()
    tmux.select_pane = AsyncMock()
    tmux.list_panes = AsyncMock(return_value=[pane1, pane2])
    tmux.MANAGED_OPTION = "@claudre_managed"

    from claudre.templates import create_from_template
    result = await create_from_template(tmux, spec, config)

    assert result is pane1
    # Layout should be applied twice (before and after splits)
    assert tmux.select_layout.await_count == 2
    # One split for the second pane
    tmux.split_window.assert_awaited_once()
    # Commands sent to both panes
    assert tmux.send_keys.await_count == 2
    # First pane focuses
    tmux.select_pane.assert_awaited_once_with("%10")
