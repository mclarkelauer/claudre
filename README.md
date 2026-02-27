# claudre

Claude Session Manager TUI. A dashboard for managing multiple Claude Code instances running in tmux.

## What it does

- Lists all your projects with git status, tmux window info, and Claude state (WORKING / WAITING / idle)
- Opens new Claude sessions in properly named tmux windows with configurable layouts
- Auto-discovers git repos from configured directories
- Detects Claude's state by tail-reading JSONL session logs
- Renames tmux windows to match project names

## Install

```bash
# From source
uv pip install -e .

# Or with dev dependencies
uv pip install -e ".[dev]"
```

## Setup

```bash
# Discover repos and create initial config
claudre init

# Install tmux keybindings (prefix+d / prefix+D)
claudre setup
tmux source ~/.tmux.conf
```

## Usage

```bash
claudre              # launch dashboard TUI (default)
claudre dashboard    # same as above
claudre popup        # popup mode — select a project and exit
claudre list         # print status table to stdout
claudre init         # scan for new repos, update config
claudre rename       # rename all tmux windows running claude
claudre setup        # install tmux keybindings
```

### Dashboard keybindings

| Key   | Action                                         |
|-------|------------------------------------------------|
| Enter | Open project (creates tmux window if needed)   |
| x     | Close project (with confirmation)              |
| r     | Manual refresh                                 |
| q     | Quit                                           |

### Tmux keybindings (after `claudre setup`)

| Key        | Action                                    |
|------------|-------------------------------------------|
| prefix + d | Switch to claudre window (creates if new) |
| prefix + D | Open claudre popup                        |

## Configuration

Config lives at `~/.claudre/config.toml`.

```toml
refresh_interval = 2.0
auto_discover_dirs = ["/home/user/repos", "/home/user/work"]

[defaults]
claude_command = "claude"
dangerously_skip_permissions = true
layout = "claude+terminal"       # or "claude+vim+terminal"
model = ""                       # e.g. "sonnet", "opus"
extra_args = ""

# Per-project overrides (inherits from defaults)
[projects.my-project]
path = "/home/user/repos/my-project"
layout = "claude+vim+terminal"
model = "opus"
```

### Layouts

- **`claude+terminal`** — two vertical panes: claude left, bash right
- **`claude+vim+terminal`** — claude left, vim top-right, bash bottom-right

### Auto-discovery

Directories listed in `auto_discover_dirs` are scanned every refresh cycle. Any new git repos found are automatically added to the config.

## Architecture

```
src/claudre/
  cli.py              Click CLI — entry point, subcommands
  app.py              Textual App shell
  config.py           TOML config loading, Pydantic models, project discovery
  models.py           Data models: ProjectState, ClaudeState, VcsStatus, TmuxWindow
  tmux.py             Subprocess wrappers for tmux operations
  claude_state.py     JSONL tail-reading to detect WORKING/WAITING/NOT_RUNNING
  vcs.py              Git branch + dirty status detection
  widgets/
    project_table.py  DataTable showing all projects with status
    detail_panel.py   Selected project detail view
  screens/
    dashboard.py      Main screen: table + detail panel, 2s refresh timer
    open_project.py   Modal for opening a project by name or path
    confirm.py        Yes/no confirmation modal
  css/
    app.tcss          Textual CSS layout
```

### Refresh cycle (every 2s)

1. Scan `auto_discover_dirs` for new repos
2. Rename any tmux windows running claude to their project name
3. `tmux list-panes -a` — single subprocess call for all windows
4. For each configured project: match tmux pane, detect claude state, get git status
5. Auto-discover unconfigured tmux windows running claude
6. Update the table widget

### Claude state detection

Session data lives in `~/.claude/projects/{sanitized-path}/{session-id}.jsonl`.

| Condition | State |
|-----------|-------|
| No claude process in tmux pane | NOT_RUNNING |
| Claude running, JSONL mtime < 10s | WORKING |
| Claude running, JSONL mtime > 10s, last message is `assistant` | WAITING |
| Claude running, no JSONL found | WAITING (fresh session) |

Only the last 100KB of the JSONL file is read to find the final message role.

## Tech stack

- **Python 3.12+**
- **Textual** — TUI framework
- **Click** — CLI
- **Pydantic** — config/model validation
- **hatchling** — build backend
- **uv** — package management
