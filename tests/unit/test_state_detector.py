"""Tests for state_detector.py."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claudre.models import ClaudeState, TmuxPane
from claudre.state_detector import JournalStateDetector


def make_pane(command: str = "claude", pid: int = 1234, path: str = "/tmp/proj") -> TmuxPane:
    return TmuxPane(
        session="main",
        window_index="0",
        window_name="test",
        pane_id="%1",
        pane_pid=pid,
        pane_command=command,
        pane_path=path,
    )


@pytest.fixture
def detector():
    return JournalStateDetector()


@pytest.mark.asyncio
async def test_detect_process_not_alive(detector):
    pane = make_pane(pid=999999)
    with patch.object(detector, "_is_process_alive", return_value=False):
        with patch.object(detector, "_get_sanitized_dir", return_value=None):
            state = await detector.detect(pane)
    assert state == ClaudeState.UNKNOWN


@pytest.mark.asyncio
async def test_detect_idle_command(detector):
    pane = make_pane(command="bash")
    with patch.object(detector, "_is_process_alive", return_value=True):
        state = await detector.detect(pane)
    assert state == ClaudeState.IDLE


@pytest.mark.asyncio
async def test_detect_opening_no_jsonl(detector):
    pane = make_pane(command="claude")
    with patch.object(detector, "_is_process_alive", return_value=True):
        with patch.object(detector, "_get_sanitized_dir", return_value=None):
            state = await detector.detect(pane)
    assert state == ClaudeState.OPENING


@pytest.mark.asyncio
async def test_detect_waiting(detector, tmp_path):
    # Create a JSONL file with last role == assistant, old mtime
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text(json.dumps({"role": "assistant", "content": "done"}) + "\n")
    # Make mtime old
    old_time = time.time() - 60
    import os
    os.utime(jsonl, (old_time, old_time))

    pane = make_pane(command="claude")
    with patch.object(detector, "_is_process_alive", return_value=True):
        with patch.object(detector, "_get_sanitized_dir", return_value="my_proj"):
        # The _find_latest_jsonl and _tail_read_last_role use real paths
        # so we patch them directly
            with patch.object(detector, "_find_latest_jsonl", return_value=jsonl):
                with patch.object(detector, "_get_cpu_percent", return_value=0.0):
                    state = await detector.detect(pane)
    assert state == ClaudeState.WAITING


@pytest.mark.asyncio
async def test_detect_crashed(detector, tmp_path):
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text(json.dumps({"role": "user", "content": "hello"}) + "\n")

    pane = make_pane(command="claude")
    with patch.object(detector, "_is_process_alive", return_value=False):
        with patch.object(detector, "_get_sanitized_dir", return_value="my_proj"):
            with patch.object(detector, "_find_latest_jsonl", return_value=jsonl):
                state = await detector.detect(pane)
    assert state == ClaudeState.CRASHED


@pytest.mark.asyncio
async def test_detect_suspended(detector, tmp_path):
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text(json.dumps({"role": "assistant", "content": "ok"}) + "\n")

    pane = make_pane(command="claude")
    with patch.object(detector, "_is_process_alive", return_value=False):
        with patch.object(detector, "_get_sanitized_dir", return_value="my_proj"):
            with patch.object(detector, "_find_latest_jsonl", return_value=jsonl):
                state = await detector.detect(pane)
    assert state == ClaudeState.SUSPENDED


def test_tail_read_last_role_empty_file(detector, tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert detector._tail_read_last_role(empty) is None


def test_tail_read_last_role_finds_last(detector, tmp_path):
    jsonl = tmp_path / "session.jsonl"
    lines = [
        json.dumps({"role": "user", "content": "hello"}),
        json.dumps({"role": "assistant", "content": "hi"}),
        json.dumps({"role": "user", "content": "question"}),
    ]
    jsonl.write_text("\n".join(lines) + "\n")
    assert detector._tail_read_last_role(jsonl) == "user"


def test_build_path_cache_missing_dir(detector, monkeypatch, tmp_path):
    monkeypatch.setattr("claudre.state_detector.CLAUDE_DIR", tmp_path / "nonexistent")
    cache = detector._build_path_cache()
    assert cache == {}


def test_build_path_cache_reads_cwd(detector, monkeypatch, tmp_path):
    claude_dir = tmp_path / "projects"
    proj_dir = claude_dir / "-home-user-myproject"
    proj_dir.mkdir(parents=True)
    jsonl = proj_dir / "abc123.jsonl"
    jsonl.write_text(json.dumps({"cwd": "/home/user/myproject", "role": "user"}) + "\n")

    monkeypatch.setattr("claudre.state_detector.CLAUDE_DIR", claude_dir)
    cache = detector._build_path_cache()
    assert cache.get("/home/user/myproject") == "-home-user-myproject"


def test_get_jsonl_path_returns_none_for_unknown(detector, monkeypatch, tmp_path):
    monkeypatch.setattr("claudre.state_detector.CLAUDE_DIR", tmp_path / "nonexistent")
    result = detector.get_jsonl_path("/some/path")
    assert result is None


def test_get_jsonl_path_returns_latest(detector, monkeypatch, tmp_path):
    claude_dir = tmp_path / "projects"
    proj_dir = claude_dir / "-tmp-myproj"
    proj_dir.mkdir(parents=True)

    # Two JSONL files — latest should be returned
    old_jsonl = proj_dir / "old.jsonl"
    new_jsonl = proj_dir / "new.jsonl"
    old_jsonl.write_text(json.dumps({"cwd": "/tmp/myproj", "role": "user"}) + "\n")
    new_jsonl.write_text(json.dumps({"cwd": "/tmp/myproj", "role": "assistant"}) + "\n")

    import os, time as _time
    os.utime(old_jsonl, (_time.time() - 100, _time.time() - 100))
    os.utime(new_jsonl, (_time.time(), _time.time()))

    monkeypatch.setattr("claudre.state_detector.CLAUDE_DIR", claude_dir)
    result = detector.get_jsonl_path("/tmp/myproj")
    assert result == new_jsonl
