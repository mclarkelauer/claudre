"""Tests for config.py."""

import warnings

import pytest

from claudre.config import (
    ClaudreConfig,
    ConfigError,
    DefaultsConfig,
    ProjectConfig,
    TemplateConfig,
    load_config,
    _migrate_raw,
)


def test_defaults():
    cfg = ClaudreConfig()
    assert cfg.refresh_interval == 2.0
    assert cfg.summary_model == "claude-haiku-4-5-20251001"
    assert cfg.ai_summaries is True
    assert cfg.scope == "all"
    assert isinstance(cfg.defaults, DefaultsConfig)


def test_load_config_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("claudre.config.CONFIG_PATH", tmp_path / "nonexistent.toml")
    cfg = load_config()
    assert isinstance(cfg, ClaudreConfig)


def test_load_config_valid(tmp_path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text(
        """
refresh_interval = 5.0
ai_summaries = false

[defaults]
claude_command = "claude"
skip_permissions = true

[projects.myproj]
path = "/home/user/myproj"
quick_actions = ["make test", "make lint"]
"""
    )
    monkeypatch.setattr("claudre.config.CONFIG_PATH", toml)
    cfg = load_config()
    assert cfg.refresh_interval == 5.0
    assert cfg.ai_summaries is False
    assert cfg.defaults.skip_permissions is True
    assert "myproj" in cfg.projects
    assert cfg.projects["myproj"].quick_actions == ["make test", "make lint"]


def test_load_config_invalid_toml(tmp_path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text("this is not valid toml ][}")
    monkeypatch.setattr("claudre.config.CONFIG_PATH", toml)
    with pytest.raises(ConfigError, match="parse error"):
        load_config()


def test_load_config_validation_error(tmp_path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text("refresh_interval = 'not a number'")
    monkeypatch.setattr("claudre.config.CONFIG_PATH", toml)
    with pytest.raises(ConfigError, match="validation error"):
        load_config()


def test_migrate_dangerously_skip_permissions():
    raw = {"defaults": {"dangerously_skip_permissions": True}}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = _migrate_raw(raw)
    assert result["defaults"].get("skip_permissions") is True
    assert "dangerously_skip_permissions" not in result["defaults"]
    assert any("deprecated" in str(warning.message).lower() for warning in w)


def test_migrate_project_layout():
    raw = {"projects": {"foo": {"path": "/tmp/foo", "layout": "even-horizontal"}}}
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        result = _migrate_raw(raw)
    assert result["projects"]["foo"].get("template") == "even-horizontal"
    assert "layout" not in result["projects"]["foo"]


def test_template_config_defaults():
    t = TemplateConfig()
    assert t.layout == "even-horizontal"
    assert "claude" in t.pane_commands
    assert t.rename_to_project is True
