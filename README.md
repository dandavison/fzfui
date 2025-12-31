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

## Examples

See `examples/psi` for a full example (interactive process viewer).

