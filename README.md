# claudre

AI-native tmux control plane. Keeps a live plain-English summary of every open tmux window so you always know what each Claude session is doing — without switching to it.

## Requirements

- Python 3.12+
- tmux
- `ANTHROPIC_API_KEY` set in your environment (for AI summaries; optional — app works without it)

## Install

```bash
# Clone and install globally (claudre available on PATH in all shells)
git clone <repo-url> claudre
cd claudre/claudre
make install        # uses pipx — isolated env, globally available

# Alternative if you use uv:
make install-uv
```

**pipx** puts the `claudre` binary in `~/.local/bin` (added to PATH automatically by pipx). No venv activation needed — `claudre` just works.

If you don't have pipx:

```bash
pip install --user pipx
pipx ensurepath     # adds ~/.local/bin to PATH; restart your shell once
```

## First-time setup

```bash
claudre setup           # writes prefix+D and prefix+N bindings to ~/.tmux.conf
tmux source ~/.tmux.conf
```

Then from inside any tmux session:

```bash
claudre dashboard       # open the dashboard (or: claudre)
```

## Usage

```bash
claudre                 # open dashboard (default)
claudre dashboard       # same — switches to existing dashboard if already open
claudre popup           # quick window-switcher (designed for tmux display-popup)
claudre new [template]  # stamp out a new window from a template
claudre list            # print window status table to stdout (no TUI)
claudre setup           # (re)install tmux keybindings
claudre init            # scan auto_discover_dirs for new git repos
claudre --debug         # enable debug logging
claudre --log-file /tmp/claudre.log   # write logs to file
```

## Dashboard keybindings

| Key     | Action                                      |
|---------|---------------------------------------------|
| `Enter` | Jump to selected window                     |
| `n`     | New window (template selector)              |
| `x`     | Close selected window (confirmation)        |
| `s`     | Send message to Claude pane                 |
| `r`     | Run quick action / command in bash pane     |
| `u`     | Force AI summary refresh                    |
| `R`     | Force full registry refresh                 |
| `/`     | Filter by name, path, state, or summary     |
| `?`     | Help                                        |
| `q`     | Quit dashboard (tmux session stays open)    |

## tmux keybindings (after `claudre setup`)

| Key        | Action                                             |
|------------|----------------------------------------------------|
| `prefix+D` | Jump to claudre dashboard (switch to existing one) |
| `prefix+N` | Create new window using default template           |
| `prefix+P` | Quick window-switcher popup                        |

## Configuration

Config lives at `~/.claudre/config.toml`. Created with defaults if absent.

```toml
refresh_interval = 2.0          # seconds between tmux polls
summary_interval = 30.0         # seconds between periodic AI summary refreshes
ai_summaries = true             # set false to disable all API calls
notification_on_waiting = true  # toast when a window transitions WORKING → WAITING
status_bar_integration = false  # write summary to tmux status-right
debug_log = ""                  # path to log file; empty = disabled

[defaults]
claude_command = "claude"
skip_permissions = false        # pass --dangerously-skip-permissions
template = "claude+terminal"
model = ""
extra_args = ""

[templates.claude+terminal]     # built-in — two panes side by side
layout = "even-horizontal"
pane_commands = ["claude", "bash"]
pane_sizes = [50, 50]

[templates.claude+vim+terminal] # built-in — claude left, vim+bash right
layout = "main-left"
pane_commands = ["claude", "vim", "bash"]
pane_sizes = [50, 30, 20]

# Custom template example
[templates.my-setup]
layout = "even-horizontal"
pane_commands = ["claude --dangerously-skip-permissions", "bash"]
pane_sizes = [60, 40]

# Per-project config
[projects.my-api]
path = "/home/user/repos/my-api"
template = "claude+vim+terminal"
model = "claude-opus-4-6"
quick_actions = ["make test", "make lint", "git pull --rebase"]
```

## Releasing

Versions are derived automatically from git tags via `hatch-vcs`. There is no version field to edit manually.

```bash
# 1. Make sure tests pass and the working tree is clean
make test

# 2. Tag and push
make release VERSION=3.1.0

# 3. Go to GitHub → Releases → Draft a new release
#    Select tag v3.1.0 → write release notes → Publish release
#    The CI workflow runs tests on Python 3.12 + 3.13, builds the package,
#    then publishes to PyPI automatically.
```

**One-time PyPI setup (first release only):**
1. Create a `pypi` environment in your GitHub repo (Settings → Environments)
2. On PyPI, go to your project → Publishing → add a trusted publisher:
   - Owner: your GitHub username/org
   - Repository: your repo name
   - Workflow: `publish.yml`
   - Environment: `pypi`

After that, no API tokens are needed — GitHub Actions authenticates via OIDC.

## Uninstall

```bash
make uninstall      # pipx uninstall claudre
```

## Development

```bash
make dev            # install with dev dependencies into active venv
make test           # run test suite
make clean          # remove build artifacts
```
