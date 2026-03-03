"""Tests for summary_engine.py."""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudre.config import ClaudreConfig
from claudre.models import ClaudeState, WindowState
from claudre.summary_engine import SummaryEngine, SummaryRequest


def make_config(**kwargs) -> ClaudreConfig:
    return ClaudreConfig(**kwargs)


def make_ws(state: ClaudeState = ClaudeState.WORKING, stale: bool = False) -> WindowState:
    ws = WindowState(pane_id="%1", project_name="test", path="/tmp/test")
    ws.state = state
    ws.summary_stale = stale
    return ws


@pytest.fixture
def engine():
    config = make_config(ai_summaries=False)
    tmux = MagicMock()
    return SummaryEngine(config, tmux)


def test_engine_disabled_without_api_key():
    config = make_config(ai_summaries=True)
    tmux = MagicMock()
    with patch.dict("os.environ", {}, clear=True):
        # Remove ANTHROPIC_API_KEY if present
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        eng = SummaryEngine(config, tmux)
    assert eng.enabled is False


def test_engine_disabled_when_config_off():
    config = make_config(ai_summaries=False)
    tmux = MagicMock()
    eng = SummaryEngine(config, tmux)
    assert eng.enabled is False


@pytest.mark.asyncio
async def test_should_update_disabled(engine):
    ws = make_ws()
    assert await engine.should_update(ws) is False


@pytest.mark.asyncio
async def test_should_update_stale():
    config = make_config(ai_summaries=True, summary_interval=30.0)
    tmux = MagicMock()
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.AsyncAnthropic"):
            eng = SummaryEngine(config, tmux)
    eng._enabled = True

    ws = make_ws(stale=True)
    assert await eng.should_update(ws) is True


@pytest.mark.asyncio
async def test_should_update_no_summary():
    config = make_config(ai_summaries=True)
    tmux = MagicMock()
    eng = SummaryEngine(config, tmux)
    eng._enabled = True

    ws = make_ws()
    ws.summary_updated_at = None
    assert await eng.should_update(ws) is True


@pytest.mark.asyncio
async def test_should_update_working_old():
    config = make_config(ai_summaries=True, summary_interval=30.0)
    tmux = MagicMock()
    eng = SummaryEngine(config, tmux)
    eng._enabled = True

    ws = make_ws(state=ClaudeState.WORKING)
    ws.summary_updated_at = datetime.fromtimestamp(time.time() - 60)
    assert await eng.should_update(ws) is True


@pytest.mark.asyncio
async def test_summarize_returns_empty_on_error(engine):
    engine._enabled = True
    engine._client = MagicMock()
    engine._client.messages = MagicMock()
    engine._client.messages.create = AsyncMock(side_effect=Exception("API error"))

    req = SummaryRequest(pane_id="%1", terminal_capture="hello")
    result = await engine._summarize(req)
    assert result == ""


@pytest.mark.asyncio
async def test_request_update_noop_when_disabled(engine):
    ws = make_ws()
    registry = MagicMock()
    # Should not raise, should be a no-op
    await engine.request_update(ws, registry)
    assert ws.summary_stale is False  # disabled, so stale not set


def test_update_config_changes_interval():
    config1 = make_config(ai_summaries=False, summary_interval=30.0, summary_concurrency=2)
    tmux = MagicMock()
    eng = SummaryEngine(config1, tmux)
    assert eng._config.summary_interval == 30.0

    config2 = make_config(ai_summaries=False, summary_interval=60.0, summary_concurrency=2)
    eng.update_config(config2)
    assert eng._config.summary_interval == 60.0


def test_engine_uses_detector_for_jsonl(tmp_path):
    """SummaryEngine delegates JSONL path resolution to the shared detector."""
    config = make_config(ai_summaries=False)
    tmux = MagicMock()

    detector = MagicMock()
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text('{"role": "user", "content": "hello"}\n')
    detector.get_jsonl_path = MagicMock(return_value=jsonl)

    eng = SummaryEngine(config, tmux, detector=detector)
    result = eng._read_jsonl_context("/some/path")

    detector.get_jsonl_path.assert_called_once_with("/some/path")
    assert result is not None
    assert result[0]["role"] == "user"
