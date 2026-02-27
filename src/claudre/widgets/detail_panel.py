"""Detail panel showing selected project info."""

from __future__ import annotations

from textual.widgets import Static

from claudre.models import ClaudeState, ProjectState


class DetailPanel(Static):
    """Panel showing details of the selected project."""

    def update_project(self, project: ProjectState | None) -> None:
        if project is None:
            self.update("[dim]No project selected[/]")
            return

        lines = [
            f"[bold]{project.name}[/]",
            f"  Path: {project.path}",
        ]
        if project.vcs.vcs_type:
            branch_str = project.vcs.branch or "(detached)"
            dirty_str = " [bold red]*dirty*[/]" if project.vcs.dirty else ""
            lines.append(f"  Branch: {branch_str}{dirty_str}")

        if project.tmux_window:
            tw = project.tmux_window
            lines.append(f"  Window: {tw.session}:{tw.window_index} ({tw.window_name})")
        else:
            lines.append("  Window: [dim]not open[/]")

        state_str = {
            ClaudeState.WORKING: "[bold green]WORKING[/]",
            ClaudeState.WAITING: "[bold yellow]WAITING[/]",
            ClaudeState.NOT_RUNNING: "[dim]not running[/]",
        }[project.claude_state]
        lines.append(f"  Claude: {state_str}")

        if not project.configured:
            lines.append("  [dim italic](auto-discovered)[/]")

        self.update("\n".join(lines))
