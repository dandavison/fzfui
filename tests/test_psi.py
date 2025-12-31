#!/usr/bin/env python3
"""Test suite for psi (process viewer) using pytest and tmux."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

TEST_INTERACTIVE = Path(__file__).parent / "test-interactive"
CMDI_DIR = Path(__file__).parent.parent


def get_test_tmux_socket(session_name: str) -> str:
    """Get a unique tmux socket name for testing."""
    return f"test-socket-{session_name}"


def tmux_cmd(socket: str, *args: str) -> list[str]:
    """Build a tmux command with the test socket."""
    return ["tmux", "-L", socket] + list(args)


def run_psi_test(args: str = "", sleep_time: float = 1.0) -> str:
    """Run psi with test-interactive and capture output.

    Args:
        args: Additional arguments to pass to psi
        sleep_time: How long to wait for UI to render

    Returns:
        str: Captured output from tmux session
    """
    if os.environ.get("CI") == "true":
        sleep_time += 0.5

    psi_path = CMDI_DIR / "psi"
    command = f"{psi_path} {args}".strip()

    result = subprocess.run(
        [TEST_INTERACTIVE, command, str(sleep_time)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout


@pytest.fixture(scope="module", autouse=True)
def ensure_executable():
    """Ensure test-interactive and psi scripts are executable."""
    TEST_INTERACTIVE.chmod(0o755)
    (CMDI_DIR / "psi").chmod(0o755)
    (CMDI_DIR / "cmdz").chmod(0o755)
    (CMDI_DIR / "cmdz-toggle").chmod(0o755)
    (CMDI_DIR / "cmdz-on-change").chmod(0o755)


class TestBasicUI:
    """Tests for basic UI rendering and functionality."""

    def test_psi_starts_and_shows_output(self):
        """Test: psi starts and displays ps output."""
        output = run_psi_test()

        # Should show ps header columns (PID is hidden via --with-nth)
        assert "%CPU" in output or "cpu" in output.lower(), (
            f"Expected %CPU column in output, got:\n{output}"
        )
        assert "COMMAND" in output or "command" in output.lower(), (
            f"Expected COMMAND column in output, got:\n{output}"
        )

    def test_psi_shows_footer_with_command(self):
        """Test: psi shows the current command in footer."""
        output = run_psi_test()

        # Footer should show the command
        assert "psi-cmd" in output or "ps " in output, (
            f"Expected command in footer, got:\n{output}"
        )

    def test_psi_shows_processes(self):
        """Test: psi displays actual process data."""
        output = run_psi_test()

        # Should show common system processes or at least the shell running the test
        # Look for typical process indicators
        lines = output.strip().split("\n")
        # Should have more than just header and footer
        assert len(lines) > 3, f"Expected process data rows, got:\n{output}"


class TestModeToggle:
    """Tests for query/command mode toggling."""

    def test_starts_in_query_mode(self):
        """Test: psi starts in query mode (search enabled, footer shows command)."""
        output = run_psi_test()

        # In query mode, the footer shows the command
        assert "psi-cmd" in output or "ps " in output, (
            f"Expected command in footer (query mode), got:\n{output}"
        )

        # The prompt should contain '/'
        lines = output.split("\n")
        assert any("/" in line for line in lines[:3]), (
            f"Expected prompt '/' in first few lines, got:\n{output}"
        )

    def test_ctrl_backslash_switches_to_command_mode(self):
        """Test: ctrl-\\ switches from query mode to command mode."""
        session_name = f"test-psi-mode-toggle-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = CMDI_DIR / "psi"

        try:
            # Start psi
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(CMDI_DIR),
                    str(psi_path),
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

            # Command mode uses '>' prompt
            lines = output.split("\n")
            has_command_prompt = any(">" in line for line in lines[:3])
            assert has_command_prompt, (
                f"Expected command mode prompt '>' after ctrl-\\, got:\n{output}"
            )

            # The command should now be in the input area
            assert "psi-cmd" in output or "ps " in output, (
                f"Expected command visible, got:\n{output}"
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
        """Regression test: toggle should not display raw fzf action strings."""
        session_name = f"test-psi-no-raw-action-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = CMDI_DIR / "psi"

        try:
            # Start psi
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(CMDI_DIR),
                    str(psi_path),
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
        session_name = f"test-psi-filter-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = CMDI_DIR / "psi"

        try:
            # Start psi
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(CMDI_DIR),
                    str(psi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            # Type a filter query - use something likely to appear in ps output
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "bash"),
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

            # The query 'bash' should appear in the input
            assert "bash" in output.lower(), (
                f"Expected 'bash' query in output, got:\n{output}"
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
        """Test: typing in command mode changes the ps command and updates results."""
        session_name = f"test-psi-cmd-type-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = CMDI_DIR / "psi"

        try:
            # Start psi
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(CMDI_DIR),
                    str(psi_path),
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

            # Clear and type a different ps command
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-u"),
                check=True,
            )
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "ps -ef"),
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

            # The command line should now show ps -ef
            assert "ps -ef" in output, (
                f"Expected 'ps -ef' in command line after typing, got:\n{output}"
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

    def test_psi_script_exists(self):
        """Test: main psi script exists."""
        psi_path = CMDI_DIR / "psi"
        assert psi_path.exists(), f"psi script not found at {psi_path}"

    def test_psi_conf_exists(self):
        """Test: psi.conf config file exists."""
        conf_path = CMDI_DIR / "psi.conf"
        assert conf_path.exists(), f"psi.conf not found at {conf_path}"

    def test_psi_has_shebang(self):
        """Test: psi script has proper shebang."""
        psi_path = CMDI_DIR / "psi"
        with open(psi_path) as f:
            first_line = f.readline()
            assert first_line.startswith("#!/"), (
                f"psi should have a shebang, got: {first_line}"
            )

    def test_psi_is_valid_bash(self):
        """Test: psi script passes bash syntax check."""
        psi_path = CMDI_DIR / "psi"
        result = subprocess.run(
            ["bash", "-n", str(psi_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"psi has bash syntax errors: {result.stderr}"
        )

    def test_psi_conf_has_kill_binding(self):
        """Test: psi.conf has ctrl-k kill binding."""
        conf_path = CMDI_DIR / "psi.conf"
        content = conf_path.read_text()
        assert "ctrl-k" in content, (
            f"psi.conf should have ctrl-k binding, got:\n{content}"
        )
        assert "kill" in content, (
            f"psi.conf should have kill command, got:\n{content}"
        )

    def test_psi_conf_has_header_lines(self):
        """Test: psi.conf skips ps header line."""
        conf_path = CMDI_DIR / "psi.conf"
        content = conf_path.read_text()
        assert "--header-lines" in content, (
            f"psi.conf should have --header-lines, got:\n{content}"
        )


