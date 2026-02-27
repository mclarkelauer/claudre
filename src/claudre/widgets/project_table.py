"""DataTable widget showing project status."""

from __future__ import annotations

from textual.widgets import DataTable

from claudre.models import ClaudeState, ProjectState


class ProjectTable(DataTable):
    """Table displaying all projects and their status."""

    BINDINGS = []

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns("", "Project", "Branch", "Dirty", "Claude")

    def update_projects(self, projects: list[ProjectState]) -> None:
        """Replace all rows with current project data."""
        # Remember selected row key
        selected_key = None
        if self.row_count > 0:
            try:
                selected_key = self.coordinate_to_cell_key(
                    self.cursor_coordinate
                ).row_key.value
            except Exception:
                pass

        self.clear()
        restore_row = 0
        for i, proj in enumerate(projects):
            if proj.is_open:
                status = "[bold green]\u25cf[/]"
            else:
                status = "[dim]\u25cb[/]"

            branch = proj.vcs.branch or ""
            dirty = "[bold red]*[/]" if proj.vcs.dirty else ""
            claude = _format_state(proj.claude_state, proj.is_open)

            self.add_row(status, proj.name, branch, dirty, claude, key=proj.name)
            if proj.name == selected_key:
                restore_row = i

        if self.row_count > 0:
            self.move_cursor(row=min(restore_row, self.row_count - 1))

    def get_selected_project_name(self) -> str | None:
        if self.row_count == 0:
            return None
        try:
            key = self.coordinate_to_cell_key(self.cursor_coordinate).row_key.value
            return key
        except Exception:
            return None


def _format_state(state: ClaudeState, is_open: bool) -> str:
    if not is_open:
        return "[dim]--[/]"
    match state:
        case ClaudeState.WORKING:
            return "[bold green]WORKING[/]"
        case ClaudeState.WAITING:
            return "[bold yellow]WAITING[/]"
        case ClaudeState.NOT_RUNNING:
            return "[dim]idle[/]"
