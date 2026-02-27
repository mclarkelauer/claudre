"""Main dashboard screen."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual import on, work
from textual.screen import Screen
from textual.containers import Horizontal
from textual.widgets import Footer, Static

from claudre import claude_state, tmux, vcs
from claudre.config import ClaudreConfig, discover_projects
from claudre.models import ClaudeState, ProjectState, TmuxWindow
from claudre.widgets.detail_panel import DetailPanel
from claudre.widgets.project_table import ProjectTable


class DashboardScreen(Screen):
    BINDINGS = [
        ("x", "close_project", "Close"),
        ("r", "refresh", "Refresh"),
        ("q", "quit_app", "Quit"),
    ]

    def __init__(self, config: ClaudreConfig, popup_mode: bool = False) -> None:
        super().__init__()
        self.config = config
        self.popup_mode = popup_mode
        self._projects: list[ProjectState] = []
        self._refresh_timer = None

    def compose(self):
        title = "claudre" if not self.popup_mode else "claudre [popup]"
        yield Static(f" {title} ", id="header")
        with Horizontal(id="body"):
            yield ProjectTable(id="project-table")
            yield DetailPanel(id="detail-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.do_refresh()
        self._refresh_timer = self.set_interval(
            self.config.refresh_interval, self.do_refresh
        )

    @work(thread=True)
    def do_refresh(self) -> None:
        projects = self._collect_projects()
        self.app.call_from_thread(self._apply_refresh, projects)

    def _apply_refresh(self, projects: list[ProjectState]) -> None:
        self._projects = projects
        table = self.query_one(ProjectTable)
        table.update_projects(projects)
        self._update_detail()

    def _collect_projects(self) -> list[ProjectState]:
        """Collect state for all projects (runs in thread)."""
        # Auto-discover new repos from configured directories
        discover_projects(self.config)

        # Rename any claude windows to their project name
        tmux.rename_claude_windows(self.config.projects)

        panes = tmux.list_all_panes()
        projects: list[ProjectState] = []

        # Configured projects
        for name, proj_cfg in self.config.projects.items():
            proj_path = proj_cfg.path
            tw = _match_pane(panes, proj_path)
            process_running = _is_claude_running(tw, panes)
            state = claude_state.detect_state(proj_path, process_running)
            vcs_status = vcs.get_vcs_status(proj_path)
            projects.append(
                ProjectState(
                    name=name,
                    path=proj_path,
                    configured=True,
                    tmux_window=tw,
                    claude_state=state,
                    vcs=vcs_status,
                )
            )

        # Auto-discover unconfigured tmux windows running claude
        configured_paths = {p.path for p in self.config.projects.values()}
        seen_paths: set[str] = set()
        for pane in panes:
            if pane.pane_command == "claude" and pane.pane_path not in configured_paths:
                if pane.pane_path in seen_paths:
                    continue
                seen_paths.add(pane.pane_path)
                vcs_status = vcs.get_vcs_status(pane.pane_path)
                state = claude_state.detect_state(pane.pane_path, True)
                name = Path(pane.pane_path).name
                projects.append(
                    ProjectState(
                        name=name,
                        path=pane.pane_path,
                        configured=False,
                        tmux_window=pane,
                        claude_state=state,
                        vcs=vcs_status,
                    )
                )

        return projects

    @on(ProjectTable.RowSelected)
    def on_row_selected(self, event: ProjectTable.RowSelected) -> None:
        self.action_select_project()

    @on(ProjectTable.RowHighlighted)
    def on_row_highlighted(self, event: ProjectTable.RowHighlighted) -> None:
        self._update_detail()

    def _update_detail(self) -> None:
        table = self.query_one(ProjectTable)
        detail = self.query_one(DetailPanel)
        name = table.get_selected_project_name()
        proj = next((p for p in self._projects if p.name == name), None)
        detail.update_project(proj)

    def _get_selected_project(self) -> ProjectState | None:
        table = self.query_one(ProjectTable)
        name = table.get_selected_project_name()
        return next((p for p in self._projects if p.name == name), None)

    def action_refresh(self) -> None:
        self.do_refresh()

    def action_select_project(self) -> None:
        proj = self._get_selected_project()
        if not proj:
            return
        if proj.tmux_window:
            # Already open — switch to it
            tmux.switch_to_window(proj.tmux_window.target)
            if self.popup_mode:
                self.app.exit()
        else:
            # Not open — create window, then switch to it
            proj_cfg = self.config.projects.get(proj.name)
            if proj_cfg:
                layout = self.config.get_layout(proj_cfg)
                claude_cmd = self.config.get_claude_cmd(proj_cfg)
            else:
                layout = self.config.defaults.layout
                claude_cmd = self.config.defaults.claude_command
            tmux.create_project_window(proj.name, proj.path, layout, claude_cmd)
            if self.popup_mode:
                self.app.exit()
            else:
                # Switch back to claudre so dashboard stays visible
                claudre_target = tmux.find_claudre_window()
                if claudre_target:
                    tmux.switch_to_window(claudre_target)
                self.do_refresh()

    def action_close_project(self) -> None:
        proj = self._get_selected_project()
        if proj and proj.tmux_window:
            from claudre.screens.confirm import ConfirmScreen

            def on_confirm(confirmed: bool) -> None:
                if confirmed and proj.tmux_window:
                    tmux.kill_window(proj.tmux_window.target)
                    self.do_refresh()

            self.app.push_screen(
                ConfirmScreen(f"Close project '{proj.name}'?"), on_confirm
            )

    def action_quit_app(self) -> None:
        self.app.exit()


def _match_pane(panes: list[TmuxWindow], path: str) -> TmuxWindow | None:
    """Find a tmux pane whose path matches the project path."""
    for pane in panes:
        if pane.pane_path == path:
            return pane
    return None


def _is_claude_running(
    matched_pane: TmuxWindow | None, all_panes: list[TmuxWindow]
) -> bool:
    """Check if any pane in the same window is running claude."""
    if matched_pane is None:
        return False
    for pane in all_panes:
        if (
            pane.session == matched_pane.session
            and pane.window_index == matched_pane.window_index
            and pane.pane_command == "claude"
        ):
            return True
    return False
