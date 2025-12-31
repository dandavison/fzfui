# fzfui Architecture

## Overview

fzfui is a Python library for building interactive fzf-based terminal UIs. It wraps fzf with a decorator-based Python API, allowing single-file scripts that define commands, actions, and previews declaratively.

## Core Problem

fzf is powerful but requires shell scripting for complex interactions. fzfui solves this by:

1. Providing a Python API with decorators (`@app.main`, `@app.action`, `@app.preview`)
2. Handling the callback mechanism so fzf can invoke Python functions
3. Managing state for the dual-mode interface (query mode vs command mode)

## Key Design: Self-Invoking Script Pattern

The central insight is that a single Python script serves dual purposes:

1. **Primary invocation**: Launches fzf with configured bindings
2. **Callback invocation**: fzf calls the same script with hidden subcommands

```
User runs: ./psi
  → App._run_fzf() launches fzf with bindings like:
      --bind 'ctrl-k:execute-silent(./psi _action kill_proc {1})'
      --bind 'ctrl-\:transform:./psi _toggle'

When user presses ctrl-k:
  → fzf executes: ./psi _action kill_proc <pid>
  → typer routes to hidden _action command
  → App._handle_action() calls the registered kill_proc function
```

## Components

### App Class (`src/fzfui/app.py`)

The main class users interact with:

```python
app = fzfui.App(__file__)  # __file__ is critical for callbacks
```

**Constructor takes script path** because fzf needs to know how to call back into the script. This path is embedded in all `--bind` arguments.

### Decorators

**`@app.main(command, header_lines, with_nth, reload_command)`**
- Configures the initial command that generates fzf input
- Sets up the typer callback with `invoke_without_command=True`
- When invoked without subcommand, calls `_run_fzf()`

**`@app.action(key, reload, silent, field)`**
- Registers a keybinding action
- `reload`: Re-run the command after action
- `silent`: Use `execute-silent` instead of `execute`
- `field`: Which fzf field to pass (e.g., `{1}` for first column)

**`@app.preview`**
- Registers the preview panel content function
- Called via `--preview './script _preview {}'`

### Hidden Typer Subcommands

Registered in `_register_internal_commands()`:

| Command | Purpose |
|---------|---------|
| `_toggle` | Switch between query/command mode |
| `_on-change` | Handle typing in command mode (live reload) |
| `_action <name> <selection>` | Dispatch to registered action handler |
| `_preview <selection>` | Render preview content |
| `_reload` | Re-run the data command |

These are registered with `hidden=True` so they don't appear in `--help` but are still callable.

**Important**: Command names must be explicitly set (e.g., `@self.cli.command("_toggle", hidden=True)`) because typer doesn't auto-generate names for functions starting with `_`.

### State Management

Dual-mode (query/command) requires tracking:
- Current mode
- Saved query (when in command mode)
- Current command

State is stored in a temp file, path passed via `FZFUI_STATE` environment variable:

```
Format: mode|query|command
Example: query||ps aux
Example: command|python|ls -la
```

The `_toggle` command:
1. Reads state from `FZFUI_STATE`
2. Reads current query from `FZF_QUERY` (set by fzf)
3. Outputs fzf action string to switch modes
4. Writes new state

### fzf Integration

`_run_fzf()` constructs the fzf command:

```python
args = [
    "fzf",
    "--ansi",
    "--with-shell", "bash -c",  # Required for transform actions
    "--bind", f"ctrl-\\:transform:{script} _toggle",
    "--bind", f"change:transform:{script} _on-change",
    # ... action bindings ...
]
```

**Key fzf features used:**
- `transform:` - Script outputs fzf actions (change-query, reload, etc.)
- `execute:` / `execute-silent:` - Run external command
- `reload:` - Re-run and refresh the list
- `{1}`, `{2}`, etc. - Field placeholders

## File Structure

```
src/fzfui/
├── __init__.py      # Exports App, version
└── app.py           # App class, all logic

examples/
└── psi              # Single-file uv script example

tests/
├── conftest.py      # Fixtures, dependency checks
├── test_psi.py      # Functional tests using tmux
└── test-interactive # Bash helper for tmux-based testing
```

## Example Script Anatomy

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["fzfui"]
# ///

import fzfui

app = fzfui.App(__file__)  # Script path for callbacks

@app.main(command="...", header_lines=1)
def myapp():
    pass  # Body unused, just triggers setup

@app.action("enter")
def handle_enter(selection: str):
    # Called when user presses enter
    pass

@app.preview
def show_preview(selection: str) -> str:
    return "Preview content"

if __name__ == "__main__":
    app()  # Runs typer CLI
```

## Testing Strategy

Tests use tmux to drive the interactive UI:

1. Start psi in a detached tmux session
2. Send keystrokes via `tmux send-keys`
3. Capture pane content via `tmux capture-pane`
4. Assert on visible output

The `test-interactive` script handles session setup/teardown.

## Development Notes

**Local example development**: The `examples/psi` script uses `[tool.uv.sources]` with an absolute path to the local fzfui. When published, users omit this section.

**Cache issues**: When modifying fzfui, run `uv cache clean fzfui` before testing examples, or use `uv sync --reinstall-package fzfui`.

**Debugging callbacks**: Add print statements to `_handle_*` methods. Output goes to fzf's display or is captured (for `execute-silent`).

