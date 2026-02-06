# fzfui

Build interactive fzf UIs with Python.

## Installation

```bash
uv add fzfui
```

## Usage

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["fzfui"]
# ///

import fzfui

app = fzfui.App(__file__)

@app.main(command="ls -la", header_lines=1)
def my_app():
    pass

@app.action("enter")
def select(selection: str):
    print(f"Selected: {selection}")

if __name__ == "__main__":
    app()
```

## Features

- Two modes: query mode (filter output) and command mode (edit command live)
- Toggle between modes with ctrl-\
- Declarative action bindings via decorators
- Preview panel support
- Single-file scripts with uv dependencies

## jqi - Interactive jq Explorer

`jqi` is an interactive jq expression explorer built with fzfui. Pipe JSON in, type jq expressions, and see results in real-time.

### Prerequisites

- [fzf](https://github.com/junegunn/fzf)
- [jq](https://jqlang.github.io/jq/)

On macOS:

```bash
brew install fzf jq
```

### Install

```bash
curl -fsSL https://raw.githubusercontent.com/dandavison/fzfui/main/examples/jqi -o ~/.local/bin/jqi
chmod +x ~/.local/bin/jqi
```

Ensure `~/.local/bin` is on your `PATH`.

### Usage

```bash
cat data.json | jqi
curl -s https://api.github.com/repos/junegunn/fzf/commits | jqi '.[] | .commit.message'
```

uv resolves dependencies automatically on first run.

## Examples

See `examples/psi` for a full example (interactive process viewer).

