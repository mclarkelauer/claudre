# CLAUDE.md

## Project overview

claudre is a Claude Session Manager TUI that runs inside tmux. It manages multiple Claude Code sessions across projects, showing their status and providing quick switching/opening via a Textual dashboard.

## Build and run

```bash
uv pip install -e ".[dev]"    # install with dev deps
claudre                        # run dashboard
claudre list                   # non-TUI status output
python -m pytest tests/ -v     # run tests
```

## Architecture

- `cli.py` — Click CLI entry point. `DefaultGroup` routes bare `claudre` to `dashboard`.
- `config.py` — Loads `~/.claudre/config.toml`. `ClaudreConfig` has `defaults` (global) and per-project `ProjectConfig`. Projects inherit from defaults unless overridden.
- `models.py` — Pure data: `ClaudeState` enum, `VcsStatus`, `TmuxWindow`, `ProjectState` dataclasses.
- `tmux.py` — All tmux interaction via subprocess. `list_all_panes()` is the main data source. `create_project_window()` takes a pre-built `claude_cmd` string.
- `claude_state.py` — Detects WORKING/WAITING/NOT_RUNNING by tail-reading `~/.claude/projects/` JSONL files. Maintains a path-to-sanitized-dir cache.
- `vcs.py` — Runs `git branch` and `git status --porcelain` with 5s timeout.
- `screens/dashboard.py` — Main screen. `_collect_projects()` runs in a thread every 2s. Handles Enter (open/switch), x (close), r (refresh), q (quit).
- `widgets/project_table.py` — DataTable with row selection. Uses `coordinate_to_cell_key` for stable row tracking across refreshes.
- `app.py` — Thin Textual App wrapper that pushes `DashboardScreen`.

## Key patterns

- All subprocess calls use `timeout=5` and catch `TimeoutExpired`/`FileNotFoundError`.
- Config uses Pydantic with `None` sentinels on `ProjectConfig` fields to distinguish "not set" from "set to default". `ClaudreConfig.get_claude_cmd()` builds the full command.
- The refresh thread calls `discover_projects()` and `rename_claude_windows()` before collecting state.
- JSONL tail-read: seek to `file_size - 100KB`, scan lines in reverse for last `assistant`/`user` role.

## Testing

Tests live in `tests/`. They avoid real tmux/git/filesystem calls — use monkeypatching and `tmp_path`.

```bash
python -m pytest tests/ -v
```

## Config location

`~/.claudre/config.toml` — not `~/.config/claudre/`.
