"""Tests for vcs.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from claudre.models import VcsStatus
from claudre.vcs import VcsCache


@pytest.fixture
def cache():
    return VcsCache(ttl=30.0)


@pytest.mark.asyncio
async def test_get_non_git_dir(cache, tmp_path):
    status = await cache.get(str(tmp_path))
    assert status.vcs_type is None
    assert status.branch == ""
    assert status.dirty is False


@pytest.mark.asyncio
async def test_get_git_dir(cache, tmp_path):
    (tmp_path / ".git").mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="main\n"),
            MagicMock(returncode=0, stdout="M  file.py\n"),
        ]
        status = await cache.get(str(tmp_path))
    assert status.vcs_type == "git"
    assert status.branch == "main"
    assert status.dirty is True


@pytest.mark.asyncio
async def test_cache_returns_cached(cache, tmp_path):
    (tmp_path / ".git").mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="main\n"),
            MagicMock(returncode=0, stdout=""),
        ]
        status1 = await cache.get(str(tmp_path))
        status2 = await cache.get(str(tmp_path))
    # subprocess.run should only be called twice (for the first fetch)
    assert mock_run.call_count == 2
    assert status1.branch == status2.branch == "main"


@pytest.mark.asyncio
async def test_invalidate_forces_refresh(cache, tmp_path):
    (tmp_path / ".git").mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="main\n"),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout="feature\n"),
            MagicMock(returncode=0, stdout=""),
        ]
        await cache.get(str(tmp_path))
        cache.invalidate(str(tmp_path))
        status = await cache.get(str(tmp_path))
    assert status.branch == "feature"


@pytest.mark.asyncio
async def test_git_timeout_handled(cache, tmp_path):
    (tmp_path / ".git").mkdir()
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5)):
        status = await cache.get(str(tmp_path))
    assert status.branch == ""
    assert status.dirty is False
