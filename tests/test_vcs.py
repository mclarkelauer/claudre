"""Tests for vcs.py."""

import subprocess

from claudre.models import VcsStatus
from claudre.vcs import get_vcs_status


def test_no_vcs(tmp_path):
    status = get_vcs_status(str(tmp_path))
    assert status.vcs_type is None
    assert status.branch == ""
    assert status.dirty is False


def test_git_repo(tmp_path):
    # Init a real git repo
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        capture_output=True,
    )
    # Create initial commit so branch exists
    (tmp_path / "file.txt").write_text("hello")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        capture_output=True,
    )

    status = get_vcs_status(str(tmp_path))
    assert status.vcs_type == "git"
    assert status.branch != ""  # master or main depending on config
    assert status.dirty is False


def test_git_dirty(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        capture_output=True,
    )
    (tmp_path / "file.txt").write_text("hello")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        capture_output=True,
    )

    # Make it dirty
    (tmp_path / "file.txt").write_text("changed")

    status = get_vcs_status(str(tmp_path))
    assert status.vcs_type == "git"
    assert status.dirty is True
