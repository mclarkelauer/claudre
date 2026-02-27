"""Load and save TOML configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".claudre"
CONFIG_PATH = CONFIG_DIR / "config.toml"


class DefaultsConfig(BaseModel):
    claude_command: str = "claude"
    dangerously_skip_permissions: bool = True
    layout: str = "claude+terminal"
    model: str = ""
    extra_args: str = ""


class ProjectConfig(BaseModel):
    path: str
    dangerously_skip_permissions: bool | None = None
    layout: str | None = None
    model: str | None = None
    extra_args: str | None = None


class ClaudreConfig(BaseModel):
    refresh_interval: float = 2.0
    auto_discover_dirs: list[str] = Field(default_factory=lambda: [str(Path.home() / "repos")])
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)

    def get_layout(self, project: ProjectConfig) -> str:
        return project.layout if project.layout is not None else self.defaults.layout

    def get_skip_perms(self, project: ProjectConfig) -> bool:
        return project.dangerously_skip_permissions if project.dangerously_skip_permissions is not None else self.defaults.dangerously_skip_permissions

    def get_claude_cmd(self, project: ProjectConfig) -> str:
        cmd = self.defaults.claude_command
        skip = self.get_skip_perms(project)
        model = project.model if project.model is not None else self.defaults.model
        extra = project.extra_args if project.extra_args is not None else self.defaults.extra_args

        if skip:
            cmd += " --dangerously-skip-permissions"
        if model:
            cmd += f" --model {model}"
        if extra:
            cmd += f" {extra}"
        return cmd


def load_config() -> ClaudreConfig:
    if not CONFIG_PATH.exists():
        return ClaudreConfig()
    text = CONFIG_PATH.read_text()
    raw = tomllib.loads(text)

    defaults = DefaultsConfig(**raw.get("defaults", {}))

    projects = {}
    for name, proj_data in raw.get("projects", {}).items():
        projects[name] = ProjectConfig(**proj_data)

    default_dirs = [str(Path.home() / "repos")]
    return ClaudreConfig(
        refresh_interval=raw.get("refresh_interval", 2.0),
        auto_discover_dirs=raw.get("auto_discover_dirs", default_dirs),
        defaults=defaults,
        projects=projects,
    )


def save_config(config: ClaudreConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"refresh_interval = {config.refresh_interval}"]

    default_dirs = [str(Path.home() / "repos")]
    if config.auto_discover_dirs != default_dirs:
        dir_list = ", ".join(f'"{d}"' for d in config.auto_discover_dirs)
        lines.append(f"auto_discover_dirs = [{dir_list}]")

    # Defaults section
    d = config.defaults
    lines.append("")
    lines.append("[defaults]")
    lines.append(f'claude_command = "{d.claude_command}"')
    lines.append(f"dangerously_skip_permissions = {'true' if d.dangerously_skip_permissions else 'false'}")
    lines.append(f'layout = "{d.layout}"')
    if d.model:
        lines.append(f'model = "{d.model}"')
    if d.extra_args:
        lines.append(f'extra_args = "{d.extra_args}"')

    # Projects
    for name, proj in sorted(config.projects.items()):
        lines.append(f"\n[projects.{name}]")
        lines.append(f'path = "{proj.path}"')
        if proj.dangerously_skip_permissions is not None:
            lines.append(f"dangerously_skip_permissions = {'true' if proj.dangerously_skip_permissions else 'false'}")
        if proj.layout is not None:
            lines.append(f'layout = "{proj.layout}"')
        if proj.model is not None:
            lines.append(f'model = "{proj.model}"')
        if proj.extra_args is not None:
            lines.append(f'extra_args = "{proj.extra_args}"')

    lines.append("")
    CONFIG_PATH.write_text("\n".join(lines))


def discover_projects(config: ClaudreConfig) -> int:
    """Scan auto_discover_dirs for new git repos and add to config.

    Returns the number of newly discovered projects.
    """
    discovered = 0
    for dir_path in config.auto_discover_dirs:
        scan_dir = Path(dir_path).expanduser()
        if not scan_dir.exists():
            continue
        for d in scan_dir.iterdir():
            if d.is_dir() and (d / ".git").exists():
                name = d.name
                if name not in config.projects:
                    config.projects[name] = ProjectConfig(path=str(d))
                    discovered += 1
    if discovered:
        save_config(config)
    return discovered
