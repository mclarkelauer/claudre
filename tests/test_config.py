"""Tests for config.py."""

import textwrap

from claudre.config import (
    ClaudreConfig,
    DefaultsConfig,
    ProjectConfig,
    load_config,
    save_config,
    discover_projects,
    CONFIG_PATH,
)


def test_defaults_config():
    d = DefaultsConfig()
    assert d.claude_command == "claude"
    assert d.dangerously_skip_permissions is True
    assert d.layout == "claude+terminal"
    assert d.model == ""
    assert d.extra_args == ""


def test_project_config_none_sentinels():
    p = ProjectConfig(path="/tmp/test")
    assert p.dangerously_skip_permissions is None
    assert p.layout is None
    assert p.model is None
    assert p.extra_args is None


def test_get_layout_inherits_default():
    config = ClaudreConfig()
    proj = ProjectConfig(path="/tmp/test")
    assert config.get_layout(proj) == "claude+terminal"


def test_get_layout_project_override():
    config = ClaudreConfig()
    proj = ProjectConfig(path="/tmp/test", layout="claude+vim+terminal")
    assert config.get_layout(proj) == "claude+vim+terminal"


def test_get_skip_perms_inherits_default():
    config = ClaudreConfig()
    proj = ProjectConfig(path="/tmp/test")
    assert config.get_skip_perms(proj) is True


def test_get_skip_perms_project_override():
    config = ClaudreConfig(defaults=DefaultsConfig(dangerously_skip_permissions=True))
    proj = ProjectConfig(path="/tmp/test", dangerously_skip_permissions=False)
    assert config.get_skip_perms(proj) is False


def test_get_claude_cmd_default():
    config = ClaudreConfig()
    proj = ProjectConfig(path="/tmp/test")
    cmd = config.get_claude_cmd(proj)
    assert cmd == "claude --dangerously-skip-permissions"


def test_get_claude_cmd_with_model():
    config = ClaudreConfig(defaults=DefaultsConfig(model="sonnet"))
    proj = ProjectConfig(path="/tmp/test")
    cmd = config.get_claude_cmd(proj)
    assert "--model sonnet" in cmd


def test_get_claude_cmd_project_model_override():
    config = ClaudreConfig(defaults=DefaultsConfig(model="sonnet"))
    proj = ProjectConfig(path="/tmp/test", model="opus")
    cmd = config.get_claude_cmd(proj)
    assert "--model opus" in cmd
    assert "sonnet" not in cmd


def test_get_claude_cmd_extra_args():
    config = ClaudreConfig(defaults=DefaultsConfig(extra_args="--verbose"))
    proj = ProjectConfig(path="/tmp/test")
    cmd = config.get_claude_cmd(proj)
    assert cmd.endswith("--verbose")


def test_get_claude_cmd_no_skip_perms():
    config = ClaudreConfig(defaults=DefaultsConfig(dangerously_skip_permissions=False))
    proj = ProjectConfig(path="/tmp/test")
    cmd = config.get_claude_cmd(proj)
    assert "--dangerously-skip-permissions" not in cmd


def test_load_config_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("claudre.config.CONFIG_PATH", tmp_path / "nonexistent.toml")
    config = load_config()
    assert isinstance(config, ClaudreConfig)
    assert len(config.projects) == 0


def test_load_config_minimal(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(textwrap.dedent("""\
        refresh_interval = 5.0

        [projects.myproj]
        path = "/tmp/myproj"
    """))
    monkeypatch.setattr("claudre.config.CONFIG_PATH", config_file)
    config = load_config()
    assert config.refresh_interval == 5.0
    assert "myproj" in config.projects
    assert config.projects["myproj"].path == "/tmp/myproj"


def test_load_config_with_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(textwrap.dedent("""\
        [defaults]
        claude_command = "claude-dev"
        model = "opus"
        layout = "claude+vim+terminal"

        [projects.test]
        path = "/tmp/test"
    """))
    monkeypatch.setattr("claudre.config.CONFIG_PATH", config_file)
    config = load_config()
    assert config.defaults.claude_command == "claude-dev"
    assert config.defaults.model == "opus"
    assert config.defaults.layout == "claude+vim+terminal"


def test_save_and_reload(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("claudre.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("claudre.config.CONFIG_PATH", config_file)

    config = ClaudreConfig(
        refresh_interval=3.0,
        defaults=DefaultsConfig(model="sonnet"),
        projects={"proj1": ProjectConfig(path="/tmp/proj1")},
    )
    save_config(config)

    loaded = load_config()
    assert loaded.refresh_interval == 3.0
    assert loaded.defaults.model == "sonnet"
    assert "proj1" in loaded.projects
    assert loaded.projects["proj1"].path == "/tmp/proj1"


def test_discover_projects(tmp_path, monkeypatch):
    # Create fake repos
    (tmp_path / "repo_a" / ".git").mkdir(parents=True)
    (tmp_path / "repo_b" / ".git").mkdir(parents=True)
    (tmp_path / "not_a_repo").mkdir()

    config_dir = tmp_path / "config"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr("claudre.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("claudre.config.CONFIG_PATH", config_file)

    config = ClaudreConfig(auto_discover_dirs=[str(tmp_path)])
    count = discover_projects(config)

    assert count == 2
    assert "repo_a" in config.projects
    assert "repo_b" in config.projects
    assert "not_a_repo" not in config.projects
    assert config_file.exists()


def test_discover_projects_skips_existing(tmp_path, monkeypatch):
    (tmp_path / "repo_a" / ".git").mkdir(parents=True)

    config_dir = tmp_path / "config"
    monkeypatch.setattr("claudre.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("claudre.config.CONFIG_PATH", config_dir / "config.toml")

    config = ClaudreConfig(
        auto_discover_dirs=[str(tmp_path)],
        projects={"repo_a": ProjectConfig(path=str(tmp_path / "repo_a"))},
    )
    count = discover_projects(config)
    assert count == 0
