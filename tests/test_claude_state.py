"""Tests for claude_state.py."""

import json
import time

from claudre.claude_state import (
    ClaudeState,
    _tail_read_last_role,
    detect_state,
    invalidate_cache,
)


def test_detect_state_not_running():
    assert detect_state("/tmp/nonexistent", process_running=False) == ClaudeState.NOT_RUNNING


def test_detect_state_no_jsonl():
    """No JSONL found for path should return WAITING (fresh session)."""
    invalidate_cache()
    assert detect_state("/tmp/definitely-not-a-project", process_running=True) == ClaudeState.WAITING


def test_tail_read_last_role_assistant(tmp_path):
    jsonl = tmp_path / "test.jsonl"
    lines = [
        json.dumps({"role": "user", "content": "hello"}),
        json.dumps({"role": "assistant", "content": "hi there"}),
    ]
    jsonl.write_text("\n".join(lines) + "\n")

    assert _tail_read_last_role(jsonl) == "assistant"


def test_tail_read_last_role_user(tmp_path):
    jsonl = tmp_path / "test.jsonl"
    lines = [
        json.dumps({"role": "user", "content": "hello"}),
        json.dumps({"role": "assistant", "content": "hi"}),
        json.dumps({"role": "user", "content": "do something"}),
    ]
    jsonl.write_text("\n".join(lines) + "\n")

    assert _tail_read_last_role(jsonl) == "user"


def test_tail_read_last_role_empty(tmp_path):
    jsonl = tmp_path / "test.jsonl"
    jsonl.write_text("")

    assert _tail_read_last_role(jsonl) is None


def test_tail_read_last_role_no_role(tmp_path):
    jsonl = tmp_path / "test.jsonl"
    jsonl.write_text(json.dumps({"type": "system", "cwd": "/tmp"}) + "\n")

    assert _tail_read_last_role(jsonl) is None


def test_tail_read_large_file(tmp_path):
    """Tail read should work even with large files."""
    jsonl = tmp_path / "test.jsonl"
    # Write a bunch of lines, then an assistant line at the end
    lines = []
    for i in range(5000):
        lines.append(json.dumps({"role": "user", "content": f"message {i}"}))
    lines.append(json.dumps({"role": "assistant", "content": "final response"}))
    jsonl.write_text("\n".join(lines) + "\n")

    assert _tail_read_last_role(jsonl) == "assistant"
