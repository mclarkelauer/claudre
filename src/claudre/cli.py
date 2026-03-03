"""Click CLI entry point for claudre v3."""

from __future__ import annotations

import re
from pathlib import Path

import click

from claudre.config import ConfigError, load_config


class DefaultGroup(click.Group):
    """Click group that defaults to 'dashboard' when no subcommand is given."""

    def parse_args(self, ctx, args):
        if not args or (args[0] not in self.commands and args[0] not in ("--help", "-h")):
            args = ["dashboard"] + list(args)
        return super().parse_args(ctx, args)


@click.group(cls=DefaultGroup)
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging.")
@click.option("--log-file", default="", metavar="PATH", help="Write logs to this file.")
@click.pass_context
def main(ctx: click.Context, debug: bool, log_file: str) -> None:
    """claudre — Claude-native tmux session manager."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    ctx.obj["log_file"] = log_file

    from claudre.logger import setup_logging
    setup_logging(log_path=log_file, debug=debug)


@main.command()
@click.pass_context
def dashboard(ctx: click.Context) -> None:
    """Launch the persistent dashboard TUI."""
    try:
        config = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))

    import asyncio
    import sys
    from claudre.tmux_adapter import TmuxAdapter
    tmux = TmuxAdapter()

    async def _switch_or_setup() -> bool:
        """Switch to an existing claudre dashboard if one is open.

        Returns True if we switched (caller should exit), False if a new
        dashboard should be launched (current window renamed to 'claudre').
        """
        if not await tmux.is_inside_tmux():
            return False

        session = await tmux.current_session()
        current_idx = await tmux.current_window_index()
        panes = await tmux.list_panes()
        session_panes = [p for p in panes if p.session == session]

        # Look for any window named "claudre" that isn't the current window
        existing = [
            p for p in session_panes
            if p.window_name == "claudre" and p.window_index != current_idx
        ]
        if existing:
            await tmux.select_window(existing[0].target)
            return True

        # No existing dashboard — rename current window and launch TUI
        current_panes = [p for p in session_panes if p.window_index == current_idx]
        if current_panes:
            try:
                await tmux.rename_window(current_panes[0].target, "claudre")
            except Exception:
                pass
        return False

    if asyncio.run(_switch_or_setup()):
        sys.exit(0)

    from textual.app import App
    from claudre.screens.dashboard import DashboardScreen

    class ClaudreApp(App):
        CSS_PATH = Path(__file__).parent / "css" / "app.tcss"

        def __init__(self, config) -> None:
            super().__init__()
            self._config = config

        def on_mount(self) -> None:
            self.push_screen(DashboardScreen(self._config))

    app = ClaudreApp(config)
    app.run()


@main.command()
@click.argument("template", default="")
@click.pass_context
def new(ctx: click.Context, template: str) -> None:
    """Create a new tmux window from a template (no TUI needed)."""
    import asyncio

    try:
        config = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))

    template_name = template or config.defaults.template
    cwd = str(Path.cwd())
    project_name = Path(cwd).name

    async def _run():
        from claudre.tmux_adapter import TmuxAdapter, WindowSpec
        from claudre.templates import create_from_template

        tmux = TmuxAdapter()
        if not await tmux.is_inside_tmux():
            raise click.ClickException("Not inside a tmux session")

        session = await tmux.current_session()
        spec = WindowSpec(
            session=session,
            template_name=template_name,
            project_name=project_name,
            start_directory=cwd,
        )
        pane = await create_from_template(tmux, spec, config)
        click.echo(f"Created window '{project_name}' in session '{session}' (pane {pane.pane_id})")

    asyncio.run(_run())


@main.command()
@click.pass_context
def popup(ctx: click.Context) -> None:
    """Quick window-switcher popup (run via: tmux display-popup -E 'claudre popup')."""
    try:
        config = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))

    from claudre.screens.popup import PopupApp
    app = PopupApp(config)
    app.run()


@main.command()
@click.option("--status-bar", is_flag=True, help="Also add status bar integration")
def setup(status_bar: bool) -> None:
    """Install tmux keybindings (prefix+D, prefix+N, prefix+P) to ~/.tmux.conf."""
    tmux_conf = Path.home() / ".tmux.conf"
    marker = "# claudre-v3"

    lines_to_add = [
        f"\n{marker}",
        'bind-key D run-shell "tmux select-window -t claudre 2>/dev/null || true"',
        'bind-key N run-shell "claudre new"',
        'bind-key P display-popup -E -w 80% -h 40% "claudre popup"',
    ]

    if status_bar:
        lines_to_add.append('set -g status-right "#{@claudre_status} | %H:%M"')

    block = "\n".join(lines_to_add) + "\n"

    if tmux_conf.exists():
        content = tmux_conf.read_text()
        if marker in content:
            content = re.sub(
                r"\n?" + re.escape(marker) + r".*?(?=\n#[^#]|\n\n|\Z)",
                block.rstrip(),
                content,
                flags=re.DOTALL,
            )
            tmux_conf.write_text(content)
            click.echo("Updated claudre bindings in ~/.tmux.conf")
        else:
            tmux_conf.write_text(content.rstrip() + "\n" + block)
            click.echo("Appended claudre bindings to ~/.tmux.conf")
    else:
        tmux_conf.write_text(block)
        click.echo("Created ~/.tmux.conf with claudre bindings")

    click.echo("  prefix+D  → jump to claudre dashboard")
    click.echo("  prefix+N  → create new window")
    click.echo("  prefix+P  → quick window-switcher popup")
    click.echo("\nRun 'tmux source ~/.tmux.conf' to activate.")


@main.command()
def init() -> None:
    """Discover projects in auto_discover_dirs and print results."""
    try:
        config = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))

    discovered = 0
    for dir_path in config.auto_discover_dirs:
        scan_dir = Path(dir_path).expanduser()
        if not scan_dir.exists():
            click.echo(f"  [skip] {scan_dir} — not found")
            continue
        for d in sorted(scan_dir.iterdir()):
            if d.is_dir() and (d / ".git").exists():
                name = d.name
                if name not in config.projects:
                    click.echo(f"  + {name} ({d})")
                    discovered += 1

    if discovered:
        click.echo(f"\nDiscovered {discovered} project(s).")
        click.echo("Add them to ~/.claudre/config.toml manually or use claudre init --save.")
    else:
        click.echo("No new projects discovered.")


@main.command("list")
def list_cmd() -> None:
    """Print window status table to stdout (no TUI)."""
    import asyncio

    async def _run():
        from claudre.tmux_adapter import TmuxAdapter
        from claudre.state_detector import JournalStateDetector

        tmux = TmuxAdapter()
        detector = JournalStateDetector()
        panes = await tmux.list_panes()

        click.echo(f"{'Pane':<12} {'Window':<12} {'Project':<20} {'State':<12}")
        click.echo("-" * 60)

        for pane in panes:
            state = await detector.detect(pane)
            project = Path(pane.pane_path).name or pane.window_name
            click.echo(
                f"{pane.pane_id:<12} {pane.target:<12} {project:<20} {state.value:<12}"
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
