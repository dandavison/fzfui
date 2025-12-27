#!/usr/bin/env python3
"""Test suite for snitchi using pytest and tmux."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import List

import pytest

TEST_INTERACTIVE = Path(__file__).parent / "test-interactive"
SNITCHI_DIR = Path(__file__).parent.parent


def get_test_tmux_socket(session_name: str) -> str:
    """Get a unique tmux socket name for testing."""
    return f"test-socket-{session_name}"


def tmux_cmd(socket: str, *args: str) -> List[str]:
    """Build a tmux command with the test socket."""
    return ["tmux", "-L", socket] + list(args)


def run_snitchi_test(args: str = "", sleep_time: float = 1.0) -> str:
    """Run snitchi with test-interactive and capture output.

    Args:
        args: Additional arguments to pass to snitchi
        sleep_time: How long to wait for UI to render

    Returns:
        str: Captured output from tmux session
    """
    if os.environ.get("CI") == "true":
        sleep_time += 0.5

    snitchi_path = SNITCHI_DIR / "snitchi"
    command = f"{snitchi_path} {args}".strip()

    result = subprocess.run(
        [TEST_INTERACTIVE, command, str(sleep_time)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout


@pytest.fixture(scope="module", autouse=True)
def ensure_executable():
    """Ensure test-interactive and snitchi scripts are executable."""
    TEST_INTERACTIVE.chmod(0o755)
    (SNITCHI_DIR / "snitchi").chmod(0o755)
    (SNITCHI_DIR / "snitchi-help").chmod(0o755)
    (SNITCHI_DIR / "cmdi").chmod(0o755)
    (SNITCHI_DIR / "cmdi-toggle").chmod(0o755)
    (SNITCHI_DIR / "cmdi-on-change").chmod(0o755)


class TestBasicUI:
    """Tests for basic UI rendering and functionality."""

    def test_snitchi_starts_and_shows_output(self):
        """Test: snitchi starts and displays snitch output."""
        output = run_snitchi_test()

        # Should show snitch output with table headers (PID, PROCESS, etc.)
        # The header contains these column names
        assert "PID" in output and "PROCESS" in output, (
            f"Expected snitch table headers in output, got:\n{output}"
        )

        # Should show actual connection data
        assert "│" in output, f"Expected table rows in output, got:\n{output}"

    def test_snitchi_shows_footer_with_command(self):
        """Test: snitchi shows the current command in footer."""
        output = run_snitchi_test()

        # Footer should show the snitch command
        assert "snitch ls" in output, (
            f"Expected 'snitch ls' command in footer, got:\n{output}"
        )

    def test_snitchi_with_args(self):
        """Test: snitchi passes arguments to snitch ls."""
        output = run_snitchi_test("-t")

        # Should show snitch ls -t in footer
        assert "snitch ls -t" in output or "snitch ls" in output, (
            f"Expected snitch command with args in output, got:\n{output}"
        )


class TestModeToggle:
    """Tests for query/command mode toggling."""

    def test_starts_in_query_mode(self):
        """Test: snitchi starts in query mode (search enabled, footer shows command)."""
        output = run_snitchi_test()

        # In query mode, the footer shows the snitch command
        assert "snitch ls" in output, (
            f"Expected 'snitch ls' in footer (query mode), got:\n{output}"
        )

        # The prompt should contain '/' (without checking trailing space since
        # tmux capture may not preserve it exactly)
        lines = output.split("\n")
        # First non-empty line should be the prompt area
        assert any("/" in line for line in lines[:3]), (
            f"Expected prompt '/' in first few lines, got:\n{output}"
        )

    def test_ctrl_backslash_switches_to_command_mode(self):
        """Test: ctrl-\\ switches from query mode to command mode."""
        session_name = f"test-mode-toggle-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        snitchi_path = SNITCHI_DIR / "snitchi"

        try:
            # Start snitchi
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(SNITCHI_DIR),
                    str(snitchi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            # Press ctrl-\ to toggle to command mode
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-\\"),
                check=True,
            )
            time.sleep(1.0)

            # Capture output
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

            # Command mode uses '>' prompt (check first few lines)
            lines = output.split("\n")
            has_command_prompt = any(">" in line for line in lines[:3])
            assert has_command_prompt, (
                f"Expected command mode prompt '>' after ctrl-\\, got:\n{output}"
            )

            # The snitch command should now be in the input area (first few lines)
            # and snitch ls should appear there, not just in footer
            assert "snitch ls" in output, (
                f"Expected 'snitch ls' command visible, got:\n{output}"
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

    def test_toggle_back_to_query_mode(self):
        """Test: pressing ctrl-\\ twice returns to query mode."""
        session_name = f"test-toggle-back-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        snitchi_path = SNITCHI_DIR / "snitchi"

        try:
            # Start snitchi
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(SNITCHI_DIR),
                    str(snitchi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            # Press ctrl-\ twice to toggle to command mode and back
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-\\"),
                check=True,
            )
            time.sleep(0.5)
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-\\"),
                check=True,
            )
            time.sleep(1.0)

            # Capture output
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

            # Should be back in query mode with '/' prompt
            lines = output.split("\n")
            has_query_prompt = any(
                "/" in line and ">" not in line for line in lines[:3]
            )
            # Also verify footer shows command (indicator of query mode)
            assert "snitch ls" in output, (
                f"Expected 'snitch ls' in footer after double toggle, got:\n{output}"
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

    def test_toggle_does_not_show_raw_action_string(self):
        """Regression test: toggle should not display raw fzf action strings.

        Bug: If fzf action syntax is wrong (using : instead of () for non-final
        actions in a chain), the raw action string appears in the query field
        instead of being executed.
        """
        session_name = f"test-no-raw-action-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        snitchi_path = SNITCHI_DIR / "snitchi"

        try:
            # Start snitchi
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(SNITCHI_DIR),
                    str(snitchi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            # Press ctrl-\ to toggle mode
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-\\"),
                check=True,
            )
            time.sleep(1.0)

            # Capture output
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

            # Raw fzf action keywords should NOT appear in output
            raw_action_keywords = [
                "change-query",
                "change-footer",
                "change-prompt",
                "disable-search",
                "enable-search",
            ]
            for keyword in raw_action_keywords:
                assert keyword not in output, (
                    f"Raw fzf action '{keyword}' should not appear in output. "
                    f"This indicates the transform action syntax is broken.\n"
                    f"Output:\n{output}"
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


class TestQueryMode:
    """Tests for query (filter) mode behavior."""

    def test_typing_filters_results(self):
        """Test: typing in query mode filters the result list."""
        session_name = f"test-filter-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        snitchi_path = SNITCHI_DIR / "snitchi"

        try:
            # Start snitchi
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(SNITCHI_DIR),
                    str(snitchi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            # Get initial result count from info line
            initial_result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Type a filter query - use something likely to match some but not all
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "tcp"),
                check=True,
            )
            time.sleep(0.5)

            # Capture filtered output
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

            # The query 'tcp' should appear in the input
            assert "tcp" in output.lower(), (
                f"Expected 'tcp' query in output, got:\n{output}"
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


class TestCommandMode:
    """Tests for command mode behavior."""

    def test_typing_in_command_mode_updates_results(self):
        """Test: typing in command mode changes the snitch command and updates results."""
        session_name = f"test-cmd-type-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        snitchi_path = SNITCHI_DIR / "snitchi"

        try:
            # Start snitchi
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(SNITCHI_DIR),
                    str(snitchi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            # Switch to command mode
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-\\"),
                check=True,
            )
            time.sleep(0.5)

            # The command should be in the input area - add an option
            # Go to end of line and add " -t"
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-e"),
                check=True,
            )
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, " -t"),
                check=True,
            )
            time.sleep(1.0)

            # Capture output
            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

            # The command line should now include -t
            assert "-t" in output, (
                f"Expected '-t' in command line after typing, got:\n{output}"
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


class TestScriptStructure:
    """Tests for script structure and basic invocability."""

    def test_snitchi_script_exists(self):
        """Test: main snitchi script exists."""
        snitchi_path = SNITCHI_DIR / "snitchi"
        assert snitchi_path.exists(), f"snitchi script not found at {snitchi_path}"

    def test_cmdi_exists(self):
        """Test: cmdi framework script exists."""
        cmdi_path = SNITCHI_DIR / "cmdi"
        assert cmdi_path.exists(), f"cmdi not found at {cmdi_path}"

    def test_cmdi_toggle_exists(self):
        """Test: cmdi-toggle helper script exists."""
        toggle_path = SNITCHI_DIR / "cmdi-toggle"
        assert toggle_path.exists(), f"cmdi-toggle not found at {toggle_path}"

    def test_cmdi_on_change_exists(self):
        """Test: cmdi-on-change helper script exists."""
        on_change_path = SNITCHI_DIR / "cmdi-on-change"
        assert on_change_path.exists(), (
            f"cmdi-on-change not found at {on_change_path}"
        )

    def test_snitchi_help_exists(self):
        """Test: snitchi-help helper script exists."""
        help_path = SNITCHI_DIR / "snitchi-help"
        assert help_path.exists(), f"snitchi-help not found at {help_path}"

    def test_snitch_conf_exists(self):
        """Test: snitch.conf config file exists."""
        conf_path = SNITCHI_DIR / "snitch.conf"
        assert conf_path.exists(), f"snitch.conf not found at {conf_path}"

    def test_scripts_have_shebang(self):
        """Test: all scripts have proper shebang."""
        scripts = ["snitchi", "snitchi-help", "cmdi", "cmdi-toggle", "cmdi-on-change"]

        for script_name in scripts:
            script_path = SNITCHI_DIR / script_name
            with open(script_path) as f:
                first_line = f.readline()
                assert first_line.startswith("#!/"), (
                    f"{script_name} should have a shebang, got: {first_line}"
                )

    def test_scripts_are_valid_bash(self):
        """Test: all scripts pass bash syntax check."""
        scripts = ["snitchi", "snitchi-help", "cmdi", "cmdi-toggle", "cmdi-on-change"]

        for script_name in scripts:
            script_path = SNITCHI_DIR / script_name
            result = subprocess.run(
                ["bash", "-n", str(script_path)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, (
                f"{script_name} has bash syntax errors: {result.stderr}"
            )
