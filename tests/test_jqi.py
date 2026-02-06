"""Tests for jqi tool."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

PROMPT = "jq> "
LLM_PROMPT = "llm> "


@pytest.fixture(scope="module")
def jqi_path() -> str:
    path = shutil.which("jqi")
    assert path, "jqi not found on PATH; run tests via 'uv run pytest'"
    return path


def get_test_tmux_socket(session_name: str) -> str:
    return f"test-socket-{session_name}"


def tmux_cmd(socket: str, *args: str) -> list[str]:
    return ["tmux", "-L", socket] + list(args)


class TestJqiOutput:
    """Test that jqi outputs results to stdout for pipelines."""

    def test_jqi_outputs_on_enter(self, jqi_path: str):
        """Test that pressing enter outputs jq result to stdout."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test", "value": 42}, f)
            json_file = f.name

        session_name = f"test-jqi-output-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".out", delete=False) as f:
            output_file = f.name

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

            subprocess.run(
                tmux_cmd(
                    socket,
                    "send-keys",
                    "-t",
                    session_name,
                    f"cat {json_file} | {jqi_path} > {output_file}",
                    "Enter",
                ),
                check=True,
            )
            time.sleep(2.0)

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "Enter"),
                check=True,
            )
            time.sleep(1.5)

            with open(output_file) as f:
                output = f.read()

            print(f"jqi stdout output: {output!r}")

            assert "name" in output or "test" in output or "value" in output, (
                f"Expected JSON output, got: {output!r}"
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
            os.unlink(output_file)


class TestJqiLlmBinding:
    """Test that the LLM assist binding works correctly."""

    def test_llm_mode_toggle(self, jqi_path: str):
        """Test that ctrl-k changes prompt to LLM mode."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test": 123}, f)
            json_file = f.name

        session_name = f"test-jqi-llm-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)

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

            llm_key = "C-\\"
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, llm_key),
                check=True,
            )
            time.sleep(1.0)

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            after_toggle = result.stdout
            print(f"After LLM toggle:\n{after_toggle}")

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

    def test_llm_toggle_command_works(self, jqi_path: str):
        """Test that the _llm-toggle command produces correct output."""
        result = subprocess.run(
            [jqi_path, "_llm-toggle", ".foo"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        output = result.stdout + result.stderr
        print(f"_llm-toggle output: {output}")

        assert "change-prompt" in output or "llm-toggle" in output, (
            f"Expected transform actions from _llm-toggle, got:\n{output}"
        )

    def test_llm_full_flow_with_fake_llm(self, jqi_path: str):
        """Test full LLM flow: toggle -> type request -> enter -> get result."""
        fake_llm = Path(__file__).parent / "fake_llm"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"items": [1, 2, 3]}, f)
            json_file = f.name

        session_name = f"test-jqi-llm-full-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        llm_key = "C-\\"

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

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            print(f"Initial:\n{result.stdout}")
            assert PROMPT in result.stdout

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, llm_key),
                check=True,
            )
            time.sleep(1.0)

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            print(f"After toggle:\n{result.stdout}")
            assert LLM_PROMPT in result.stdout
            assert "items" in result.stdout

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "get length"),
                check=True,
            )
            time.sleep(0.5)
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "Enter"),
                check=True,
            )
            time.sleep(2.0)

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            print(f"After LLM:\n{result.stdout}")

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
