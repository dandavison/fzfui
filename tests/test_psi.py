from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
TEST_INTERACTIVE = Path(__file__).parent / "test-interactive"


def get_test_tmux_socket(session_name: str) -> str:
    return f"test-socket-{session_name}"


def tmux_cmd(socket: str, *args: str) -> list[str]:
    return ["tmux", "-L", socket] + list(args)


def run_psi_test(args: str = "", sleep_time: float = 1.0) -> str:
    if os.environ.get("CI") == "true":
        sleep_time += 0.5

    psi_path = EXAMPLES_DIR / "psi"
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
    TEST_INTERACTIVE.chmod(0o755)
    (EXAMPLES_DIR / "psi").chmod(0o755)


class TestBasicUI:
    def test_psi_starts_and_shows_output(self):
        output = run_psi_test()

        assert "%CPU" in output or "cpu" in output.lower(), (
            f"Expected %CPU column in output, got:\n{output}"
        )
        assert "COMMAND" in output or "command" in output.lower(), (
            f"Expected COMMAND column in output, got:\n{output}"
        )

    def test_psi_shows_footer_with_command(self):
        output = run_psi_test()

        # Footer shows the command (awk script for ps+ports join)
        assert "awk" in output or "ps" in output, (
            f"Expected command in footer, got:\n{output}"
        )

    def test_psi_shows_processes(self):
        output = run_psi_test()

        lines = output.strip().split("\n")
        assert len(lines) > 3, f"Expected process data rows, got:\n{output}"


class TestModeToggle:
    def test_starts_in_query_mode(self):
        output = run_psi_test()

        # Footer shows command (awk script for ps+ports join)
        assert "awk" in output or "ps" in output, (
            f"Expected command in footer (query mode), got:\n{output}"
        )

        lines = output.split("\n")
        assert any("/" in line for line in lines[:3]), (
            f"Expected prompt '/' in first few lines, got:\n{output}"
        )

    def test_ctrl_backslash_switches_to_command_mode(self):
        session_name = f"test-psi-mode-toggle-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = EXAMPLES_DIR / "psi"

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(EXAMPLES_DIR),
                    str(psi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-\\"),
                check=True,
            )
            time.sleep(1.0)

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

            lines = output.split("\n")
            has_command_prompt = any(">" in line for line in lines[:3])
            assert has_command_prompt, (
                f"Expected command mode prompt '>' after ctrl-\\, got:\n{output}"
            )

            # Command is visible in footer (truncated awk script)
            output_lower = output.lower()
            assert "cwd" in output_lower or "ports" in output_lower or "cut" in output_lower, (
                f"Expected command visible in footer, got:\n{output}"
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
        session_name = f"test-psi-no-raw-action-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = EXAMPLES_DIR / "psi"

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(EXAMPLES_DIR),
                    str(psi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-\\"),
                check=True,
            )
            time.sleep(1.0)

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

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
    def test_typing_filters_results(self):
        session_name = f"test-psi-filter-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = EXAMPLES_DIR / "psi"

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(EXAMPLES_DIR),
                    str(psi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "bash"),
                check=True,
            )
            time.sleep(1.0)

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

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
    def test_typing_in_command_mode_updates_results(self):
        session_name = f"test-psi-cmd-type-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = EXAMPLES_DIR / "psi"

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(EXAMPLES_DIR),
                    str(psi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-\\"),
                check=True,
            )
            time.sleep(0.5)

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-u"),
                check=True,
            )
            time.sleep(0.3)
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "ps -ef"),
                check=True,
            )
            time.sleep(1.5)

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

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


class TestListeningProcesses:
    def test_ctrl_l_filters_to_listening_processes(self):
        session_name = f"test-psi-listening-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = EXAMPLES_DIR / "psi"

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(EXAMPLES_DIR),
                    str(psi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-l"),
                check=True,
            )
            time.sleep(1.0)

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

            # Footer should show "listening processes"
            assert "listening" in output.lower(), (
                f"Expected 'listening' in footer after ctrl-l, got:\n{output}"
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

    def test_ctrl_l_toggles_back_to_all_processes(self):
        session_name = f"test-psi-all-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)
        psi_path = EXAMPLES_DIR / "psi"

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    str(EXAMPLES_DIR),
                    str(psi_path),
                ),
                check=True,
                timeout=5,
            )
            time.sleep(1.5)

            # First toggle to listening
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-l"),
                check=True,
            )
            time.sleep(1.0)

            # Then toggle back to all (ctrl-l is a toggle)
            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-l"),
                check=True,
            )
            time.sleep(1.0)

            result = subprocess.run(
                tmux_cmd(socket, "capture-pane", "-t", session_name, "-p"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout

            # Footer should show ps command after toggling back
            assert "ps -U" in output, (
                f"Expected ps command in footer after toggle, got:\n{output}"
            )
            # Should NOT show [listening] indicator
            assert "[listening]" not in output, (
                f"Should not show [listening] after toggling back:\n{output}"
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
    def test_psi_script_exists(self):
        psi_path = EXAMPLES_DIR / "psi"
        assert psi_path.exists(), f"psi script not found at {psi_path}"

    def test_psi_has_uv_shebang(self):
        psi_path = EXAMPLES_DIR / "psi"
        with open(psi_path) as f:
            first_line = f.readline()
            assert "uv run" in first_line, (
                f"psi should have uv run shebang, got: {first_line}"
            )

    def test_psi_has_script_dependencies(self):
        psi_path = EXAMPLES_DIR / "psi"
        content = psi_path.read_text()
        assert "fzfui" in content, (
            f"psi should depend on fzfui, got:\n{content[:500]}"
        )

    def test_psi_has_kill_action(self):
        psi_path = EXAMPLES_DIR / "psi"
        content = psi_path.read_text()
        assert "ctrl-k" in content, f"psi should have ctrl-k binding"
        assert "kill" in content.lower(), f"psi should have kill functionality"

    def test_psi_has_header_lines_config(self):
        psi_path = EXAMPLES_DIR / "psi"
        content = psi_path.read_text()
        assert "header_lines" in content, f"psi should configure header_lines"

    def test_psi_has_listening_filter_bindings(self):
        psi_path = EXAMPLES_DIR / "psi"
        content = psi_path.read_text()
        assert "ctrl-l" in content, f"psi should have ctrl-l binding for listening"
        assert "toggle" in content.lower(), f"psi should have toggle functionality"
        assert "LISTEN" in content, f"psi should filter by LISTEN state"

    def test_psi_uses_help_text(self):
        psi_path = EXAMPLES_DIR / "psi"
        content = psi_path.read_text()
        assert "app.help_text" in content, (
            f"psi should use app.help_text() for keybindings"
        )
