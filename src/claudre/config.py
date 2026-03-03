"""Load and validate TOML configuration for claudre v3."""

from __future__ import annotations

import tomllib
import warnings
from pathlib import Path

from pydantic import BaseModel, ValidationError

CONFIG_DIR = Path.home() / ".claudre"
CONFIG_PATH = CONFIG_DIR / "config.toml"


class ConfigError(Exception):
    pass


class TemplateConfig(BaseModel):
    layout: str = "even-horizontal"
    pane_commands: list[str] = ["claude", "bash"]
    pane_sizes: list[int] = [50, 50]
    rename_to_project: bool = True


class DefaultsConfig(BaseModel):
    claude_command: str = "claude"
    skip_permissions: bool = False
    template: str = "claude+terminal"
    model: str = ""
    extra_args: str = ""


class ProjectConfig(BaseModel):
    path: str
    template: str | None = None
    model: str | None = None
    extra_args: str | None = None
    quick_actions: list[str] = []


class ClaudreConfig(BaseModel):
    refresh_interval: float = 2.0
    vcs_cache_ttl: float = 30.0
    summary_interval: float = 30.0
    summary_concurrency: int = 3
    summary_model: str = "claude-haiku-4-5-20251001"
    ai_summaries: bool = True
    notification_on_waiting: bool = True
    status_bar_integration: bool = False
    debug_log: str = ""
    confirm_new_window: bool = True
    auto_discover_dirs: list[str] = []
    scope: str = "all"  # "all" | "session"
    defaults: DefaultsConfig = DefaultsConfig()
    templates: dict[str, TemplateConfig] = {}
    projects: dict[str, ProjectConfig] = {}


def _migrate_raw(raw: dict) -> dict:
    """Apply v2 → v3 migration transforms, emitting warnings."""
    # Top-level dangerously_skip_permissions → defaults.skip_permissions
    if "dangerously_skip_permissions" in raw:
        warnings.warn(
            "Config: 'dangerously_skip_permissions' is deprecated; "
            "use 'defaults.skip_permissions'",
            DeprecationWarning,
            stacklevel=3,
        )
        raw.setdefault("defaults", {})
        raw["defaults"].setdefault("skip_permissions", raw.pop("dangerously_skip_permissions"))

    # defaults.dangerously_skip_permissions → defaults.skip_permissions
    defaults = raw.get("defaults", {})
    if "dangerously_skip_permissions" in defaults:
        warnings.warn(
            "Config: 'defaults.dangerously_skip_permissions' is deprecated; "
            "use 'defaults.skip_permissions'",
            DeprecationWarning,
            stacklevel=3,
        )
        defaults.setdefault("skip_permissions", defaults.pop("dangerously_skip_permissions"))

    # Per-project layout → template
    for name, proj in raw.get("projects", {}).items():
        if "layout" in proj:
            warnings.warn(
                f"Config: projects.{name}.layout is deprecated; use template",
                DeprecationWarning,
                stacklevel=3,
            )
            proj.setdefault("template", proj.pop("layout"))

    return raw


def load_config() -> ClaudreConfig:
    """Load config from ~/.claudre/config.toml, returning defaults if absent."""
    if not CONFIG_PATH.exists():
        return ClaudreConfig()

    try:
        raw = tomllib.loads(CONFIG_PATH.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Config parse error: {e}") from e

    raw = _migrate_raw(raw)

    try:
        return ClaudreConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"Config validation error:\n{e}") from e
