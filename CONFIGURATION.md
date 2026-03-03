# claudre Configuration Guide

Config file: `~/.claudre/config.toml`

The file is created with defaults on first run if absent. It is hot-reloaded — changes take effect within one refresh cycle without restarting.

---

## Top-level options

```toml
refresh_interval       = 2.0    # seconds between tmux polls
vcs_cache_ttl          = 30.0   # seconds to cache git branch/dirty status
summary_interval       = 30.0   # seconds between periodic AI summary refreshes (WORKING windows only)
summary_concurrency    = 3      # max parallel Anthropic API calls
summary_model          = "claude-haiku-4-5-20251001"  # model used for summaries
ai_summaries           = true   # set false to disable all API calls entirely
notification_on_waiting = true  # show a toast when any window transitions WORKING → WAITING
status_bar_integration = false  # write a status string to #{@claudre_status} in tmux
debug_log              = ""     # path to write structured logs; empty = disabled
confirm_new_window     = true   # show template selector before creating a window
auto_discover_dirs     = []     # directories scanned by `claudre init` for git repos
scope                  = "all"  # "all" = show all tmux sessions; "session" = current session only
```

### `refresh_interval`

How often the registry polls `tmux list-panes` and re-checks each window's state. Lower values feel more responsive but consume more CPU and increase tmux subprocess load. Values below `1.0` are not recommended.

### `vcs_cache_ttl`

How long a git branch + dirty-status result is cached before being re-fetched. On Linux, cache entries are also invalidated immediately when `.git/HEAD` or `.git/index` changes (requires `watchdog`). On systems without `watchdog`, TTL is the only invalidation mechanism.

### `summary_interval`

While a window is in **WORKING** state, a new AI summary is generated every `summary_interval` seconds even if the state hasn't changed. Set to `0` to disable periodic refresh — summaries will only update on state transitions or when you press `u`.

### `summary_concurrency`

Maximum number of Anthropic API calls in flight simultaneously. Increase if you have many windows and want faster summary updates; decrease if you're hitting rate limits.

### `summary_model`

The Claude model used to generate summaries. Haiku is the default for cost and latency reasons. Any model accessible via your API key works.

| Value | Tradeoff |
|-------|----------|
| `claude-haiku-4-5-20251001` | Fastest, cheapest (~$0.00001–$0.00005 per summary) |
| `claude-sonnet-4-6` | More nuanced summaries, ~10–20× more expensive |
| `claude-opus-4-6` | Highest quality, high cost — not recommended for background polling |

### `ai_summaries`

Set to `false` to disable all Anthropic API calls. claudre will still track window state (WORKING/WAITING/CRASHED/etc.) and git status, but the Summary column will remain empty. Useful when offline or when you want to avoid API costs.

Requires `ANTHROPIC_API_KEY` to be set in the environment. If the variable is absent and `ai_summaries = true`, claudre logs a warning at startup and disables summaries automatically.

### `status_bar_integration`

When `true`, claudre writes a short string to the tmux variable `@claudre_status` every refresh cycle. Add it to your `status-right` to see ambient window status without opening the dashboard:

```bash
# Run once, or add to ~/.tmux.conf manually:
claudre setup --status-bar
```

The string looks like:
```
● my-api: WAITING · 3 working · 1 crashed
```

### `scope`

- `"all"` (default) — the dashboard shows windows from all tmux sessions.
- `"session"` — the dashboard shows only windows in the tmux session where claudre is running.

---

## `[defaults]`

Global defaults that apply to every window and every `claudre new` invocation. Per-project settings override these.

```toml
[defaults]
claude_command    = "claude"           # the binary name or full path
skip_permissions  = false              # if true, appends --dangerously-skip-permissions
template          = "claude+terminal"  # default window template
model             = ""                 # claude --model flag; empty = claude's own default
extra_args        = ""                 # appended verbatim to the claude command
```

### `claude_command`

The binary to run when creating a claude pane. Change this if you have multiple Claude versions installed or use a wrapper script:

```toml
[defaults]
claude_command = "/usr/local/bin/claude"
```

### `skip_permissions`

Appends `--dangerously-skip-permissions` to the Claude command when creating new windows. Equivalent to the v2 `dangerously_skip_permissions` field (which is still accepted but emits a deprecation warning).

### `template`

The default template used by `claudre new` when no template name is given. Must be a built-in template name or a key defined under `[templates]`.

### `model`

Passed as `--model <value>` to Claude when creating new windows. Applies globally unless overridden per project. Empty string means no `--model` flag is passed (Claude uses its own default).

```toml
[defaults]
model = "claude-sonnet-4-6"
```

### `extra_args`

Arbitrary flags appended to the claude command. Useful for flags not covered by other config fields:

```toml
[defaults]
extra_args = "--no-update-check --verbose"
```

---

## `[templates]`

Named window layouts. Three built-in templates are always available:

| Name | Layout | Panes |
|------|--------|-------|
| `claude+terminal` | even-horizontal (50/50) | claude (left), bash (right) |
| `claude+vim+terminal` | main-left | claude (left 50%), vim (top-right 30%), bash (bottom-right 20%) |
| `claude` | even-horizontal | claude (full width) |

Built-in templates cannot be overridden (user-defined templates with the same name take precedence if defined under `[templates]`).

### Defining a custom template

```toml
[templates.my-setup]
layout          = "even-horizontal"   # tmux layout name
pane_commands   = ["claude --dangerously-skip-permissions", "bash"]
pane_sizes      = [60, 40]            # percent; must sum to ≤ 100
rename_to_project = true              # rename window to project directory name
```

#### `layout`

Any tmux layout name:

| Value | Description |
|-------|-------------|
| `even-horizontal` | Panes side by side, equal width |
| `even-vertical` | Panes stacked, equal height |
| `main-horizontal` | One large pane on top, others below |
| `main-vertical` | One large pane on left, others on right |
| `main-left` | Alias for main-vertical (same behaviour in tmux) |
| `tiled` | Grid of equal-size panes |

#### `pane_commands`

List of shell commands sent to each pane after the window is created. The number of commands determines the number of panes. The first command goes to the primary (leftmost/top) pane.

If a command starts with the value of `defaults.claude_command`, `skip_permissions`, `model`, and `extra_args` are applied to it automatically. Other commands are sent verbatim.

```toml
pane_commands = ["claude", "nvim .", "bash"]
```

#### `pane_sizes`

Percentage width (or height, depending on layout) for each pane. Must have the same number of entries as `pane_commands`. Values do not need to sum to exactly 100 — tmux will rescale. If omitted, all panes split equally.

#### `rename_to_project`

If `true`, the tmux window is renamed to the project name (directory basename, or the project's config key) when the window is created. Set to `false` to leave the window name as tmux assigns it.

### Multi-pane example

```toml
[templates.research]
layout        = "main-vertical"
pane_commands = ["claude", "bash", "bash"]
pane_sizes    = [55, 25, 20]

[templates.fullscreen-claude]
layout        = "even-horizontal"
pane_commands = ["claude --dangerously-skip-permissions"]
pane_sizes    = [100]
rename_to_project = false
```

---

## `[projects]`

Named project configurations. Each entry represents one project directory. The key is the display name used in the dashboard.

```toml
[projects.my-api]
path          = "/home/user/repos/my-api"  # required — absolute path
template      = "claude+vim+terminal"       # overrides defaults.template
model         = "claude-opus-4-6"           # overrides defaults.model
extra_args    = ""                          # overrides defaults.extra_args
quick_actions = ["make test", "make lint", "git pull --rebase"]
```

### `path`

**Required.** The absolute path to the project directory. This is used to:
- Set the working directory when creating a new window for this project
- Match tmux panes to their project (by comparing `pane_current_path`)
- Locate the Claude JSONL session log for state detection

Use `~` expansion: `path = "~/repos/my-project"` is not supported — use the full path.

### `template`, `model`, `extra_args`

Per-project overrides for the corresponding `[defaults]` values. Set to an empty string or omit to inherit from defaults.

```toml
[projects.legacy-app]
path  = "/home/user/repos/legacy"
model = ""       # use defaults.model even if it's set globally
```

### `quick_actions`

A list of shell commands shown in the Run modal (`r` key in the dashboard). Select one to send it to the bash pane of that window. You can also type a free-form command in the same modal.

```toml
quick_actions = [
    "make test",
    "make lint",
    "git pull --rebase",
    "docker compose up -d",
]
```

---

## `auto_discover_dirs`

A list of directories scanned by `claudre init` for git repositories. Any subdirectory containing a `.git` folder is reported as a potential project to add to config.

```toml
auto_discover_dirs = [
    "/home/user/repos",
    "/home/user/work",
]
```

`claudre init` only reports — it does not modify the config file automatically. Copy the printed project entries into your config manually.

---

## Complete example

```toml
# ~/.claudre/config.toml

refresh_interval        = 2.0
vcs_cache_ttl           = 30.0
summary_interval        = 30.0
summary_concurrency     = 3
summary_model           = "claude-haiku-4-5-20251001"
ai_summaries            = true
notification_on_waiting = true
status_bar_integration  = false
debug_log               = ""
confirm_new_window      = true
auto_discover_dirs      = ["/home/user/repos"]
scope                   = "all"

[defaults]
claude_command   = "claude"
skip_permissions = false
template         = "claude+terminal"
model            = ""
extra_args       = ""

# ── Custom templates ──────────────────────────────────────────────────────

[templates.focused]
layout            = "even-horizontal"
pane_commands     = ["claude --dangerously-skip-permissions"]
pane_sizes        = [100]
rename_to_project = true

[templates.full]
layout            = "main-left"
pane_commands     = ["claude", "vim", "bash"]
pane_sizes        = [55, 25, 20]
rename_to_project = true

# ── Projects ──────────────────────────────────────────────────────────────

[projects.my-api]
path          = "/home/user/repos/my-api"
template      = "full"
model         = "claude-opus-4-6"
quick_actions = ["make test", "make lint", "git pull --rebase"]

[projects.frontend]
path          = "/home/user/repos/frontend"
quick_actions = ["npm test", "npm run build", "npm run lint"]

[projects.infra]
path          = "/home/user/repos/infra"
template      = "focused"
quick_actions = ["terraform plan", "terraform apply -auto-approve"]
```

---

## Migration from v2

claudre automatically migrates stale v2 config keys on load and prints a deprecation warning to stderr. No manual editing required, but you may want to clean up the old keys.

| v2 key | v3 equivalent | Notes |
|--------|---------------|-------|
| `dangerously_skip_permissions` | `defaults.skip_permissions` | Top-level or under `[defaults]` |
| `defaults.dangerously_skip_permissions` | `defaults.skip_permissions` | — |
| `projects.*.layout` | `projects.*.template` | Value is preserved as-is |

The v2 project `layout` values `"claude+terminal"` and `"claude+vim+terminal"` map directly to built-in template names, so no manual change is needed there.

---

## Debug logging

Two ways to enable:

```bash
# Command-line flag (one session):
claudre --debug
claudre --debug --log-file /tmp/claudre.log

# Config file (persistent):
debug_log = "/tmp/claudre.log"
```

Log lines look like:

```
2026-03-03T10:01:00Z INFO  registry:       my-api state changed WORKING → WAITING
2026-03-03T10:01:01Z DEBUG summary_engine: my-api API call started (~320 tokens)
2026-03-03T10:01:02Z DEBUG summary_engine: my-api summary updated in 1.1s
2026-03-03T10:01:02Z DEBUG tmux_adapter:   list_panes took 21ms, 9 panes
```
