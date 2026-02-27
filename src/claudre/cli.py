"""Click CLI for claudre."""

from __future__ import annotations

import click

from claudre.config import load_config, save_config, discover_projects, ClaudreConfig, ProjectConfig


class DefaultGroup(click.Group):
    """Click group that defaults to 'dashboard' when no subcommand is given."""

    def parse_args(self, ctx, args):
        # Don't redirect --help to the dashboard subcommand
        if not args or (args[0] not in self.commands and args[0] not in ("--help", "-h")):
            args = ["dashboard"] + list(args)
        return super().parse_args(ctx, args)


@click.group(cls=DefaultGroup)
def main():
    """claudre — Claude Session Manager TUI."""
    pass


@main.command()
def dashboard():
    """Launch the persistent dashboard TUI."""
    from claudre import tmux

    config = load_config()
    # Name the current tmux window so we can jump back to it
    if tmux.is_inside_tmux():
        tmux.rename_current_window(tmux.CLAUDRE_WINDOW_NAME)

    from claudre.app import ClaudreApp

    app = ClaudreApp(config, popup_mode=False)
    app.run()


@main.command()
def popup():
    """Launch popup mode — exits after switching to a project."""
    config = load_config()
    from claudre.app import ClaudreApp

    app = ClaudreApp(config, popup_mode=True)
    app.run()


@main.command()
def init():
    """Auto-discover repos from configured directories and update config."""
    config = load_config()
    before = set(config.projects.keys())
    discovered = discover_projects(config)
    for name in sorted(set(config.projects.keys()) - before):
        click.echo(f"  + {name} ({config.projects[name].path})")
    if discovered:
        click.echo(f"\nDiscovered {discovered} project(s). Config saved.")
    else:
        click.echo("No new projects discovered.")


@main.command()
def setup():
    """Install tmux keybinding (prefix + d) to jump back to claudre."""
    import shutil
    from pathlib import Path

    # Find the claudre binary
    claudre_bin = shutil.which("claudre")
    if not claudre_bin:
        # Fall back to the venv we're running from
        claudre_bin = str(Path(__file__).resolve().parents[2] / ".." / ".." / ".venv" / "bin" / "claudre")
        # Or just use sys.executable approach
        import sys
        claudre_bin = str(Path(sys.executable).parent / "claudre")

    tmux_conf = Path.home() / ".tmux.conf"
    marker = "# claudre"
    binding = f"bind d run-shell 'tmux select-window -t claudre 2>/dev/null || tmux new-window -n claudre {claudre_bin}'"
    popup_binding = f"bind D display-popup -E -h 80% -w 80% '{claudre_bin} popup'"

    block = f"\n{marker}\n{binding}\n{popup_binding}\n"

    if tmux_conf.exists():
        content = tmux_conf.read_text()
        if marker in content:
            # Replace existing block
            import re
            content = re.sub(
                r"\n?# claudre\n.*?(?=\n[^b]|\n$|\Z)",
                block.rstrip(),
                content,
                flags=re.DOTALL,
            )
            tmux_conf.write_text(content)
            click.echo("Updated claudre bindings in ~/.tmux.conf")
        else:
            tmux_conf.write_text(content.rstrip() + "\n" + block)
            click.echo("Added to ~/.tmux.conf:")
    else:
        tmux_conf.write_text(block)
        click.echo("Created ~/.tmux.conf:")

    click.echo(f"  prefix + d  → switch to claudre (or create)")
    click.echo(f"  prefix + D  → claudre popup")
    click.echo(f"  binary: {claudre_bin}")
    click.echo("\nRun 'tmux source ~/.tmux.conf' to activate.")


@main.command()
def rename():
    """Rename all tmux windows running claude to their project name."""
    from claudre import tmux

    config = load_config()
    renamed = tmux.rename_claude_windows(config.projects)
    if renamed:
        for old, new in renamed:
            click.echo(f"  {old} → {new}")
        click.echo(f"\nRenamed {len(renamed)} window(s).")
    else:
        click.echo("All claude windows already named correctly.")


@main.command("list")
def list_cmd():
    """Print project status table to stdout."""
    from claudre import claude_state, tmux, vcs
    from claudre.models import TmuxWindow

    config = load_config()
    panes = tmux.list_all_panes()

    # Header
    click.echo(f"{'Project':<20} {'Window':<15} {'Branch':<20} {'Dirty':<6} {'Claude':<10}")
    click.echo("-" * 71)

    for name, proj_cfg in config.projects.items():
        path = proj_cfg.path
        tw = _match_pane(panes, path)
        window = ""
        if tw:
            window = f"{tw.session}:{tw.window_index}"

        process_running = _is_claude_running(tw, panes)
        state = claude_state.detect_state(path, process_running)
        vcs_status = vcs.get_vcs_status(path)

        branch = vcs_status.branch or ""
        dirty = "*" if vcs_status.dirty else ""

        click.echo(f"{name:<20} {window:<15} {branch:<20} {dirty:<6} {state.value:<10}")


def _match_pane(panes, path) -> object | None:
    for pane in panes:
        if pane.pane_path == path:
            return pane
    return None


def _is_claude_running(matched_pane, all_panes) -> bool:
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


if __name__ == "__main__":
    main()
