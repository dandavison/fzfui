"""vui - Interactive file browser built with fzfui.

Usage: vui [DIR]

Fuzzy-search files under DIR (default: current directory) with a live bat
preview. Press enter to open the selected file; quit to return to the browser.

The enter action is chosen by the VUI_ACTION env var (default: nvim):
    nvim   open in nvim
    hx     open in helix
    micro  open in micro
    bat    view in a bat pager (q to return)
"""

from __future__ import annotations

import os
import subprocess
import sys

import fzfui

LIST_COMMAND = "fd --type f --hidden --exclude .git --strip-cwd-prefix"
FOOTER = LIST_COMMAND

ACTIONS = {
    "nvim": ["nvim"],
    "hx": ["hx"],
    "micro": ["micro"],
    "bat": ["bat", "--paging=always", "--style=header,grid", "--theme=GitHub"],
}


def main() -> None:
    try:
        os.environ.setdefault("COLUMNS", str(os.get_terminal_size().columns))
    except OSError:
        pass

    action = os.environ.get("VUI_ACTION", "nvim")
    if action not in ACTIONS:
        sys.exit(f"VUI_ACTION must be one of {', '.join(ACTIONS)} (got {action!r})")

    app = fzfui.App()

    if len(sys.argv) >= 2 and not sys.argv[1].startswith(("_", "-")):
        os.chdir(os.path.expanduser(sys.argv.pop(1)))

    @app.main(
        command=LIST_COMMAND,
        preview_window="up,70%,noinfo",
        fzf_options=[
            "--footer",
            FOOTER,
            "--height",
            "100%",
            "--layout",
            "reverse",
            "--info",
            "hidden",
            "--prompt",
            " ",
        ],
    )
    def vui():
        pass

    @app.preview
    def preview(path: str) -> str:
        path = path.strip()
        if not path or not os.path.isfile(path):
            return ""
        result = subprocess.run(
            [
                "bat",
                "--color=always",
                "--line-range=:500",
                "--paging=never",
                "--style=header,grid",
                "--theme=GitHub",
                path,
            ],
            capture_output=True,
            text=True,
        )
        return result.stdout or result.stderr

    @app.action("enter", description=f"Open file in {action}")
    def open_file(path: str) -> None:
        path = path.strip()
        if path and os.path.isfile(path):
            subprocess.run([*ACTIONS[action], path])

    app()
