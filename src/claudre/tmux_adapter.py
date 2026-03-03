"""Async tmux subprocess adapter for claudre v3."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from claudre.logger import get_logger
from claudre.models import TmuxPane

log = get_logger(__name__)

_PANE_FMT = (
    "#{session_name}\t#{window_index}\t#{window_name}"
    "\t#{pane_id}\t#{pane_pid}\t#{pane_current_command}\t#{pane_current_path}"
)


class UnmanagedWindowError(Exception):
    """Raised when a mutation is attempted on a non-claudre-managed window."""


@dataclass
class WindowSpec:
    session: str
    template_name: str
    project_name: str
    start_directory: str


class TmuxAdapter:
    MANAGED_OPTION = "@claudre_managed"

    # ------------------------------------------------------------------ #
    # Internal subprocess helper
    # ------------------------------------------------------------------ #

    async def _run(self, args: list[str], check: bool = False) -> tuple[int, str, str]:
        """Run a tmux command asynchronously. Returns (returncode, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            rc = proc.returncode or 0
            if check and rc != 0:
                raise RuntimeError(
                    f"tmux command failed (rc={rc}): {' '.join(args)}\n{stderr.decode()}"
                )
            return rc, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            log.warning("tmux command timed out: %s", " ".join(args))
            return 1, "", "timeout"
        except FileNotFoundError:
            log.error("tmux not found in PATH")
            return 1, "", "not found"

    # ------------------------------------------------------------------ #
    # Queries (no ownership check)
    # ------------------------------------------------------------------ #

    async def list_panes(self) -> list[TmuxPane]:
        """Return all panes across all sessions."""
        rc, stdout, _ = await self._run(["tmux", "list-panes", "-a", "-F", _PANE_FMT])
        if rc != 0:
            return []

        panes: list[TmuxPane] = []
        for line in stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            try:
                panes.append(
                    TmuxPane(
                        session=parts[0],
                        window_index=parts[1],
                        window_name=parts[2],
                        pane_id=parts[3],
                        pane_pid=int(parts[4]),
                        pane_command=parts[5],
                        pane_path=parts[6],
                    )
                )
            except (ValueError, IndexError):
                continue
        return panes

    async def capture_pane(self, pane_id: str, lines: int = 100) -> str:
        """Capture the visible content of a pane."""
        rc, stdout, _ = await self._run(
            ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"]
        )
        if rc != 0:
            return ""
        return stdout

    async def get_window_option(self, target: str, option: str) -> str:
        """Get a window option value. Returns empty string if not set."""
        rc, stdout, _ = await self._run(
            ["tmux", "show-options", "-wqv", "-t", target, option]
        )
        if rc != 0:
            return ""
        return stdout.strip()

    async def is_inside_tmux(self) -> bool:
        return "TMUX" in os.environ

    async def current_session(self) -> str:
        rc, stdout, _ = await self._run(
            ["tmux", "display-message", "-p", "#{session_name}"]
        )
        if rc != 0:
            return ""
        return stdout.strip()

    async def current_window_index(self) -> str:
        rc, stdout, _ = await self._run(
            ["tmux", "display-message", "-p", "#{window_index}"]
        )
        if rc != 0:
            return ""
        return stdout.strip()

    # ------------------------------------------------------------------ #
    # Mutations (ownership checked except create + select)
    # ------------------------------------------------------------------ #

    async def create_window(self, spec: WindowSpec) -> TmuxPane:
        """Create a new tmux window. Returns the first pane."""
        rc, stdout, _ = await self._run(
            [
                "tmux", "new-window",
                "-t", spec.session,
                "-c", spec.start_directory,
                "-P", "-F", _PANE_FMT,
            ],
            check=True,
        )
        parts = stdout.strip().split("\t")
        if len(parts) < 7:
            raise RuntimeError(f"Unexpected new-window output: {stdout!r}")
        return TmuxPane(
            session=parts[0],
            window_index=parts[1],
            window_name=parts[2],
            pane_id=parts[3],
            pane_pid=int(parts[4]),
            pane_command=parts[5],
            pane_path=parts[6],
        )

    async def kill_window(self, target: str) -> None:
        await self._assert_managed(target)
        await self._run(["tmux", "kill-window", "-t", target])

    async def send_keys(self, target: str, keys: str, enter: bool = True) -> None:
        cmd = ["tmux", "send-keys", "-t", target, keys]
        if enter:
            cmd.append("Enter")
        await self._run(cmd)

    async def rename_window(self, target: str, name: str) -> None:
        await self._run(["tmux", "rename-window", "-t", target, name])
        # Lock the name
        await self._run(["tmux", "set-option", "-w", "-t", target, "allow-rename", "off"])
        await self._run(["tmux", "set-option", "-w", "-t", target, "automatic-rename", "off"])

    async def select_window(self, target: str) -> None:
        await self._run(["tmux", "select-window", "-t", target])

    async def switch_client(self, target: str) -> None:
        """Switch the tmux client to a window, crossing sessions if needed."""
        await self._run(["tmux", "switch-client", "-t", target])

    async def set_window_option(self, target: str, opt: str, val: str) -> None:
        await self._run(["tmux", "set-option", "-w", "-t", target, opt, val])

    async def set_global_option(self, opt: str, val: str) -> None:
        await self._run(["tmux", "set-option", "-g", opt, val])

    async def split_window(
        self,
        target: str,
        horizontal: bool = True,
        percent: int = 50,
        start_directory: str = "",
    ) -> None:
        """Split a window pane."""
        cmd = ["tmux", "split-window", "-t", target]
        if horizontal:
            cmd.append("-h")
        cmd += ["-p", str(percent)]
        if start_directory:
            cmd += ["-c", start_directory]
        await self._run(cmd)

    async def select_layout(self, target: str, layout: str) -> None:
        """Apply a named tmux layout to a window."""
        await self._run(["tmux", "select-layout", "-t", target, layout])

    async def select_pane(self, pane_id: str) -> None:
        """Focus a specific pane."""
        await self._run(["tmux", "select-pane", "-t", pane_id])

    # ------------------------------------------------------------------ #
    # Ownership helpers
    # ------------------------------------------------------------------ #

    async def is_managed(self, target: str) -> bool:
        """Return True if this window was created by claudre."""
        val = await self.get_window_option(target, self.MANAGED_OPTION)
        return val == "1"

    # Keep private alias for any internal callers
    async def _is_managed(self, target: str) -> bool:
        return await self.is_managed(target)

    async def _assert_managed(self, target: str) -> None:
        if not await self.is_managed(target):
            raise UnmanagedWindowError(target)
