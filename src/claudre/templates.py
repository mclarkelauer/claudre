"""Window template creation for claudre v3."""

from __future__ import annotations

from claudre.config import ClaudreConfig, TemplateConfig
from claudre.logger import get_logger
from claudre.models import TmuxPane
from claudre.tmux_adapter import TmuxAdapter, WindowSpec

log = get_logger(__name__)

# Built-in templates
_BUILTIN_TEMPLATES: dict[str, TemplateConfig] = {
    "claude+terminal": TemplateConfig(
        layout="even-horizontal",
        pane_commands=["claude", "bash"],
        pane_sizes=[50, 50],
        rename_to_project=True,
    ),
    "claude+vim+terminal": TemplateConfig(
        layout="main-left",
        pane_commands=["claude", "vim", "bash"],
        pane_sizes=[50, 30, 20],
        rename_to_project=True,
    ),
    "claude": TemplateConfig(
        layout="even-horizontal",
        pane_commands=["claude"],
        pane_sizes=[100],
        rename_to_project=True,
    ),
}


def resolve_template(name: str, config: ClaudreConfig) -> TemplateConfig:
    """Return the TemplateConfig for a given name, checking user config first."""
    if name in config.templates:
        return config.templates[name]
    if name in _BUILTIN_TEMPLATES:
        return _BUILTIN_TEMPLATES[name]
    log.warning("Unknown template %r; falling back to claude+terminal", name)
    return _BUILTIN_TEMPLATES["claude+terminal"]


async def create_from_template(
    tmux: TmuxAdapter,
    spec: WindowSpec,
    config: ClaudreConfig,
) -> TmuxPane:
    """Create a tmux window from a template. Returns the primary (claude) pane."""
    template = resolve_template(spec.template_name, config)

    # Create the base window
    primary = await tmux.create_window(spec)
    target = primary.target

    # Mark as managed immediately
    await tmux.set_window_option(target, tmux.MANAGED_OPTION, "1")

    # Rename window
    if template.rename_to_project:
        await tmux.rename_window(target, spec.project_name)

    commands = template.pane_commands
    sizes = template.pane_sizes

    if len(commands) > 1:
        # Apply the named layout first
        await tmux.select_layout(target, template.layout)

        # Split panes for each additional command
        for i in range(1, len(commands)):
            percent = sizes[i] if i < len(sizes) else 50
            await tmux.split_window(
                target,
                horizontal=True,
                percent=percent,
                start_directory=spec.start_directory,
            )

        # Re-apply layout to even things out
        await tmux.select_layout(target, template.layout)

    # Send commands to each pane in the new window
    all_panes = await tmux.list_panes()
    window_panes = [
        p for p in all_panes
        if p.session == primary.session and p.window_index == primary.window_index
    ]

    for i, pane in enumerate(window_panes):
        if i < len(commands):
            cmd = commands[i]
            if config.defaults.skip_permissions and cmd == config.defaults.claude_command:
                cmd += " --dangerously-skip-permissions"
            if config.defaults.model and cmd.startswith(config.defaults.claude_command):
                cmd += f" --model {config.defaults.model}"
            if config.defaults.extra_args and cmd.startswith(config.defaults.claude_command):
                cmd += f" {config.defaults.extra_args}"
            await tmux.send_keys(pane.pane_id, cmd, enter=True)

    # Focus the first (claude) pane
    if window_panes:
        await tmux.select_pane(window_panes[0].pane_id)

    return primary
