"""Tests for cli.py."""

from click.testing import CliRunner

from claudre.cli import main


def test_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "claudre" in result.output
    assert "dashboard" in result.output
    assert "init" in result.output
    assert "list" in result.output
    assert "popup" in result.output
    assert "setup" in result.output
    assert "rename" in result.output


def test_list_command(monkeypatch):
    """list command should print a table."""
    from claudre.config import ClaudreConfig, ProjectConfig

    monkeypatch.setattr(
        "claudre.cli.load_config",
        lambda: ClaudreConfig(
            projects={"test": ProjectConfig(path="/tmp/test")}
        ),
    )
    # Mock tmux to return no panes
    monkeypatch.setattr("claudre.tmux.list_all_panes", lambda: [])
    # Mock vcs
    from claudre.models import VcsStatus
    monkeypatch.setattr("claudre.vcs.get_vcs_status", lambda p: VcsStatus())
    # Mock claude_state
    from claudre.models import ClaudeState
    monkeypatch.setattr(
        "claudre.claude_state.detect_state",
        lambda p, r: ClaudeState.NOT_RUNNING,
    )

    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "test" in result.output
    assert "not running" in result.output


def test_init_discovers_repos(tmp_path, monkeypatch):
    """init should discover git repos."""
    (tmp_path / "repo_a" / ".git").mkdir(parents=True)
    (tmp_path / "repo_b" / ".git").mkdir(parents=True)

    config_dir = tmp_path / "config"
    monkeypatch.setattr("claudre.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("claudre.config.CONFIG_PATH", config_dir / "config.toml")

    from claudre.config import ClaudreConfig
    monkeypatch.setattr(
        "claudre.cli.load_config",
        lambda: ClaudreConfig(auto_discover_dirs=[str(tmp_path)]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0
    assert "repo_a" in result.output
    assert "repo_b" in result.output
    assert "Discovered 2" in result.output


def test_init_no_new_repos(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    monkeypatch.setattr("claudre.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("claudre.config.CONFIG_PATH", config_dir / "config.toml")

    from claudre.config import ClaudreConfig
    monkeypatch.setattr(
        "claudre.cli.load_config",
        lambda: ClaudreConfig(auto_discover_dirs=[str(tmp_path)]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0
    assert "No new projects" in result.output
