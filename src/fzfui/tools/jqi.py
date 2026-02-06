"""
jqi - Interactive jq expression explorer

Usage: cat data.json | jqi
       curl api.example.com | jqi '.items[]'

Type jq expressions and see results in real-time.
Start with "." (identity) to see the full JSON.

Keys:
    enter       Output jq result and exit
    ctrl-c      Print jq command (to stderr) and exit
    ctrl-\\      LLM assist - describe what you want in natural language
    alt-up/down Navigate history
    ctrl-k      Kill to end of line
    ctrl-y      Yank (paste)
    esc         Exit without output
"""

from __future__ import annotations

import atexit
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import typer

import fzfui

PROMPT = "jq> "
LLM_PROMPT = "llm> "

HISTORY_FILE = Path.home() / ".jqi_history"


def main() -> None:
    # LLM state file - shared across all subprocesses via env var
    if "JQI_LLM_STATE" in os.environ:
        llm_state_file = Path(os.environ["JQI_LLM_STATE"])
    else:
        llm_state_file = Path(f"/tmp/jqi-llm-{os.getpid()}.state")
        os.environ["JQI_LLM_STATE"] = str(llm_state_file)

    # Read stdin and save to temp file (jq needs to re-read on each query).
    # Only for main invocation, not fzf callbacks.
    if len(sys.argv) == 1 or (len(sys.argv) >= 2 and not sys.argv[1].startswith("_")):
        if not sys.stdin.isatty():
            fd, tmpfile = tempfile.mkstemp(prefix="jqi-", suffix=".json")
            os.write(fd, sys.stdin.buffer.read())
            os.close(fd)
            os.environ["FZFUI_ARG_file"] = tmpfile
            atexit.register(lambda: os.unlink(tmpfile))
            sys.stdin = open("/dev/tty")
        atexit.register(lambda: llm_state_file.unlink(missing_ok=True))

    app = fzfui.App()
    script = app.script

    enter_binding = f"transform({script} _enter {{q}})"
    llm_binding = f"transform({script} _llm-toggle {{q}})"

    @app.main(
        disabled=True,
        initial_query=".",
        prompt=PROMPT,
        bindings={
            "ctrl-k": "kill-line",
            "alt-up": "prev-history",
            "alt-down": "next-history",
            "ctrl-\\": llm_binding,
            "enter": enter_binding,
        },
        fzf_options=["--history", str(HISTORY_FILE)],
    )
    def jqi():
        pass

    @app.cli.command("_enter", hidden=True)
    def enter_handler(query: str = typer.Argument("")):
        """Handle enter - check LLM mode or output result."""
        if llm_state_file.exists():
            original = llm_state_file.read_text()
            llm_state_file.unlink()

            llm_cmd = os.environ.get("LLM")
            if not llm_cmd:
                print(
                    f"change-prompt({PROMPT})+change-query[{original}]+refresh-preview"
                )
                return

            json_file = app.arg("file")
            llm_prompt = _build_llm_prompt(original, query, json_file)
            try:
                result = subprocess.run(
                    f"{llm_cmd} {shlex.quote(llm_prompt)}",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                new_expr = _clean_llm_response(result.stdout.strip())
            except Exception:
                new_expr = original

            print(f"change-prompt({PROMPT})+change-query[{new_expr}]+refresh-preview")
        else:
            print(f"execute({script} _action enter {{q}})+abort")

    @app.cli.command("_llm-toggle", hidden=True)
    def llm_toggle(query: str = typer.Argument("")):
        """Toggle LLM assist mode."""
        if llm_state_file.exists():
            original = llm_state_file.read_text()
            llm_state_file.unlink()
            print(f"change-prompt({PROMPT})+change-query[{original}]")
        else:
            llm_state_file.write_text(query)
            print(f"change-prompt({LLM_PROMPT})+change-query[]")

    @app.query_preview
    def preview(query: str) -> str:
        if llm_state_file.exists():
            query = llm_state_file.read_text()

        file = app.arg("file")
        if not file:
            return "Pipe JSON to stdin: cat data.json | jqi"

        if not os.path.exists(file):
            return f"File not found: {file}"

        try:
            result = subprocess.run(
                ["jq", "-C", query, file],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout
            else:
                return f"jq error:\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return "Query timed out"
        except FileNotFoundError:
            return "jq not found. Install with: brew install jq"

    @app.action("enter", exit=True)
    def output_result(query: str):
        """Output the jq result and exit."""
        _save_history(query)
        file = app.arg("file")
        if not file:
            return
        result = subprocess.run(
            ["jq", query, file],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(result.stdout, end="")

    @app.action("ctrl-c", exit=True)
    def print_command(query: str):
        """Print the jq command and copy expression to clipboard."""
        _save_history(query)
        fzfui.copy_to_clipboard(query)
        print(f"jq '{query}'", file=sys.stderr)

    if sys.stdin.isatty() and not os.environ.get("FZFUI_ARG_file"):
        print((__doc__ or "").strip(), file=sys.stderr)
        sys.exit(1)
    app()


def _save_history(query: str) -> None:
    """Append query to history if it's not the same as the last entry."""
    try:
        last = (
            HISTORY_FILE.read_text().splitlines()[-1] if HISTORY_FILE.exists() else ""
        )
    except (IndexError, OSError):
        last = ""
    if query and query != last:
        with open(HISTORY_FILE, "a") as f:
            f.write(query + "\n")


def _build_llm_prompt(current_expr: str, request: str, json_file: str | None) -> str:
    """Build the prompt for the LLM, including a sample of the JSON data."""
    json_sample = ""
    if json_file and os.path.exists(json_file):
        try:
            with open(json_file) as f:
                content = f.read(4000)
                if len(content) == 4000:
                    content = content.rsplit("\n", 1)[0] + "\n... (truncated)"
                json_sample = f"\nJSON data sample:\n```json\n{content}\n```\n"
        except Exception:
            pass

    return f"""Convert this natural language request into a valid jq expression.
{json_sample}
Current jq expression: {current_expr}
Request: {request}

Respond with ONLY the jq expression, no explanation or markdown."""


def _clean_llm_response(response: str) -> str:
    """Clean up common LLM response artifacts."""
    if response.startswith("```"):
        lines = response.split("\n")
        start = 1 if lines[0].startswith("```") else 0
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        response = "\n".join(lines[start:end])
    response = response.strip()
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]
    if response.startswith("'") and response.endswith("'"):
        response = response[1:-1]
    return response.strip()
