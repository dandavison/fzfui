# fzfui

Build interactive fzf UIs with Python. Includes two tools: `jqi` (interactive jq explorer) and `psi` (interactive process viewer).

## Prerequisites

- [fzf](https://github.com/junegunn/fzf)
- `jqi` also requires [jq](https://jqlang.github.io/jq/)

On macOS:

```bash
brew install fzf jq
```

## Install the tools

```bash
uv tool install git+https://github.com/dandavison/fzfui.git
```

This installs `jqi` and `psi` as commands. If this is your first `uv tool install`, run `uv tool update-shell` to add the tool bin directory to your `PATH`.

### Try without installing

```bash
uvx --from git+https://github.com/dandavison/fzfui.git jqi
uvx --from git+https://github.com/dandavison/fzfui.git psi
```

### Upgrade

```bash
uv tool upgrade fzfui
```

## jqi - Interactive jq Explorer

Pipe JSON in, type jq expressions, see results in real-time.

```bash
cat data.json | jqi
curl -s https://api.github.com/repos/junegunn/fzf/commits | jqi '.[] | .commit.message'
```

Keys:
- **enter** - output jq result and exit
- **ctrl-c** - copy jq expression to clipboard and exit
- **ctrl-\\** - LLM assist (describe what you want in natural language)
- **esc** - exit without output

## psi - Interactive Process Viewer

```bash
psi
psi -l          # show only processes with listening ports
```

Keys:
- **enter** - show process details
- **ctrl-k** - kill process
- **ctrl-l** - toggle listening-only filter
- **ctrl-o** - toggle extra columns (cpu, mem, stat, time)
- **ctrl-r** - reload
- **ctrl-\\** - toggle query/command mode

## Using fzfui as a library

```bash
uv add fzfui
```

```python
import fzfui

app = fzfui.App()

@app.main(command="ls -la", header_lines=1)
def my_app():
    pass

@app.action("enter")
def select(selection: str):
    print(f"Selected: {selection}")

if __name__ == "__main__":
    app()
```

### Features

- Two modes: query mode (filter output) and command mode (edit command live)
- Toggle between modes with ctrl-\
- Declarative action bindings via decorators
- Preview panel support

