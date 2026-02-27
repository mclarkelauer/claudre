"""VCS (git) status detection."""

from __future__ import annotations

import subprocess
from pathlib import Path

from claudre.models import VcsStatus


def get_vcs_status(path: str) -> VcsStatus:
    p = Path(path)
    if (p / ".git").exists():
        return _git_status(path)
    return VcsStatus()


def _git_status(path: str) -> VcsStatus:
    branch = ""
    dirty = False
    try:
        result = subprocess.run(
            ["git", "-C", path, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            dirty = bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return VcsStatus(vcs_type="git", branch=branch, dirty=dirty)
