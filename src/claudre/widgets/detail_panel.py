"""Detail panel showing full info for the selected window."""

from __future__ import annotations

import time
from datetime import datetime

from textual.widgets import Static

from claudre.models import ClaudeState, WindowState


class DetailPanel(Static):
    """Panel showing details of the selected tmux window."""

    def update_window(self, ws: WindowState | None) -> None:
        if ws is None:
            self.update("[dim]No window selected[/]")
            return

        lines: list[str] = [f"[bold]{ws.project_name}[/]", f"  Path: {ws.path}"]

        # State
        state_map = {
            ClaudeState.WORKING: "[bold green]WORKING[/]",
            ClaudeState.WAITING: "[bold yellow]WAITING[/]",
            ClaudeState.CRASHED: "[bold red]CRASHED[/]",
            ClaudeState.SUSPENDED: "[dim]SUSPENDED[/]",
            ClaudeState.IDLE: "[dim]idle[/]",
            ClaudeState.OPENING: "[cyan]OPENING[/]",
            ClaudeState.UNKNOWN: "[dim]unknown[/]",
        }
        lines.append(f"  State: {state_map.get(ws.state, str(ws.state))}")

        # VCS
        if ws.vcs.vcs_type:
            branch = ws.vcs.branch or "(detached)"
            dirty = " [bold red]*dirty*[/]" if ws.vcs.dirty else ""
            lines.append(f"  Branch: {branch}{dirty}")

        # Pane info
        lines.append(f"  Pane: {ws.pane_id}")
        managed = "[green]yes[/]" if ws.managed else "[dim]no[/]"
        lines.append(f"  Managed: {managed}")

        # Summary
        lines.append("")
        if ws.summary:
            stale = " [dim](stale)[/]" if ws.summary_stale else ""
            lines.append(f"[bold]Summary[/]{stale}")
            lines.append(f"  {ws.summary}")

            if ws.summary_updated_at:
                age = int(time.time() - ws.summary_updated_at.timestamp())
                lines.append(f"  [dim]Updated {age}s ago[/]")
        else:
            lines.append("[dim]No summary yet (press u to generate)[/]")

        self.update("\n".join(lines))
