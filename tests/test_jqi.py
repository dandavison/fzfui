"""Tests for jqi example."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

PROMPT = "jq> "
LLM_PROMPT = "llm> "


@pytest.fixture(scope="module", autouse=True)
def ensure_executable():
    (EXAMPLES_DIR / "jqi").chmod(0o755)


def get_test_tmux_socket(session_name: str) -> str:
    return f"test-socket-{session_name}"


def tmux_cmd(socket: str, *args: str) -> list[str]:
    return ["tmux", "-L", socket] + list(args)


class TestJqiLlmBinding:
    """Test that the LLM assist binding works correctly."""

    def test_llm_mode_toggle(self):
        """Test that ctrl-k changes prompt to LLM mode."""
        # Create a temp JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test": 123}, f)
            json_file = f.name

        session_name = f"test-jqi-llm-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        jqi_path = EXAMPLES_DIR / "jqi"

        try:
            # Start jqi in tmux
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-x",
                    "120",
                    "-y",
                    "40",
                ),
                check=True,
                timeout=5,
            )

            subprocess.run(
                tmux_cmd(
                    socket,
                    "send-keys",
                    "-t",
                    session_name,
                    f"cat {json_file} | {jqi_path}",
                    "Enter",
                ),
                check=True,
            )
            time.sleep(2.0)

            # Capture initial state - should show "jq> ." prompt
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            initial_output = result.stdout
            print(f"Initial output:\n{initial_output}")

            assert f"{PROMPT}." in initial_output, (
                f"Expected '{PROMPT}.' prompt, got:\n{initial_output}"
            )

            # Send LLM toggle key
            llm_key = "C-\\"  # ctrl-backslash
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, llm_key),
                check=True,
            )
            time.sleep(1.0)

            # Capture output after LLM toggle
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            after_toggle = result.stdout
            print(f"After LLM toggle:\n{after_toggle}")

            # Should see LLM prompt (emoji prompt)
            assert f"{LLM_PROMPT}" in after_toggle, (
                f"Expected LLM prompt after toggle, got:\n{after_toggle}"
            )

        finally:
            subprocess.run(
                tmux_cmd(socket, "kill-session", "-t", session_name),
                capture_output=True,
                timeout=5,
            )
            subprocess.run(
                tmux_cmd(socket, "kill-server"),
                capture_output=True,
                timeout=5,
            )
            os.unlink(json_file)

    def test_llm_toggle_command_works(self):
        """Test that the _llm-toggle command produces correct output."""
        jqi_path = EXAMPLES_DIR / "jqi"

        result = subprocess.run(
            [str(jqi_path), "_llm-toggle", ".foo"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        output = result.stdout + result.stderr
        print(f"_llm-toggle output: {output}")

        # Should output fzf transform actions
        assert "change-prompt" in output or "llm-toggle" in output, (
            f"Expected transform actions from _llm-toggle, got:\n{output}"
        )

    def test_llm_full_flow_with_fake_llm(self):
        """Test full LLM flow: toggle -> type request -> enter -> get result."""
        fake_llm = Path(__file__).parent / "fake_llm"
        jqi_path = EXAMPLES_DIR / "jqi"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"items": [1, 2, 3]}, f)
            json_file = f.name

        session_name = f"test-jqi-llm-full-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        llm_key = "C-\\"  # ctrl-backslash

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-x",
                    "120",
                    "-y",
                    "40",
                ),
                check=True,
                timeout=5,
            )

            # Start jqi with fake LLM (export so fzf subprocesses inherit it)
            subprocess.run(
                tmux_cmd(
                    socket,
                    "send-keys",
                    "-t",
                    session_name,
                    f"export LLM={fake_llm}; cat {json_file} | {jqi_path}",
                    "Enter",
                ),
                check=True,
            )
            time.sleep(2.0)

            # Verify initial state
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            print(f"Initial:\n{result.stdout}")
            assert PROMPT in result.stdout

            # Enter LLM mode
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, llm_key),
                check=True,
            )
            time.sleep(1.0)

            # Verify LLM mode - prompt changes but preview stays the same
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            print(f"After toggle:\n{result.stdout}")
            assert LLM_PROMPT in result.stdout  # LLM mode prompt
            # Preview should still show JSON data (not help text)
            assert "items" in result.stdout

            # Type a request and press enter
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "get length"),
                check=True,
            )
            time.sleep(0.5)
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "Enter"),
                check=True,
            )
            time.sleep(2.0)  # Give LLM time to run

            # After LLM call, should be back to normal mode with new expression
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            print(f"After LLM:\n{result.stdout}")

            # Should be back to normal prompt (jq>) after LLM call
            # and have the expression from fake_llm (". | length" for "length")
            assert PROMPT in result.stdout, (
                f"Should exit LLM mode, got:\n{result.stdout}"
            )

        finally:
            subprocess.run(
                tmux_cmd(socket, "kill-session", "-t", session_name),
                capture_output=True,
                timeout=5,
            )
            subprocess.run(
                tmux_cmd(socket, "kill-server"), capture_output=True, timeout=5
            )
            os.unlink(json_file)
