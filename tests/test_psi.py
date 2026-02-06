from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

TEST_INTERACTIVE = Path(__file__).parent / "test-interactive"
PSI_MODULE = Path(__file__).parent.parent / "src" / "fzfui" / "tools" / "psi.py"


@pytest.fixture(scope="module")
def psi_path() -> str:
    path = shutil.which("psi")
    assert path, "psi not found on PATH; run tests via 'uv run pytest'"
    return path


@pytest.fixture(scope="module", autouse=True)
def ensure_executable():
    TEST_INTERACTIVE.chmod(0o755)


def get_test_tmux_socket(session_name: str) -> str:
    return f"test-socket-{session_name}"


def tmux_cmd(socket: str, *args: str) -> list[str]:
    return ["tmux", "-L", socket] + list(args)


def run_psi_test(psi_path: str, args: str = "", sleep_time: float = 1.0) -> str:
    if os.environ.get("CI") == "true":
        sleep_time += 0.5

    command = f"{psi_path} {args}".strip()

    result = subprocess.run(
        [str(TEST_INTERACTIVE), command, str(sleep_time)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout


class TestBasicUI:
    def test_psi_starts_and_shows_output(self, psi_path: str):
        output = run_psi_test(psi_path)

        assert "PORTS" in output or "ports" in output.lower(), (
            f"Expected PORTS column in output, got:\n{output}"
        )
        assert "COMMAND" in output or "command" in output.lower(), (
            f"Expected COMMAND column in output, got:\n{output}"
        )

    def test_psi_shows_footer_with_command(self, psi_path: str):
        output = run_psi_test(psi_path)

        assert "awk" in output or "ps" in output, (
            f"Expected command in footer, got:\n{output}"
        )

    def test_psi_shows_processes(self, psi_path: str):
        output = run_psi_test(psi_path)

        lines = output.strip().split("\n")
        assert len(lines) > 3, f"Expected process data rows, got:\n{output}"


class TestModeToggle:
    def test_starts_in_query_mode(self, psi_path: str):
        output = run_psi_test(psi_path)

        assert "awk" in output or "ps" in output, (
            f"Expected command in footer (query mode), got:\n{output}"
        )

        lines = output.split("\n")
        assert any("/" in line for line in lines[:3]), (
            f"Expected prompt '/' in first few lines, got:\n{output}"
        )

    def test_ctrl_backslash_switches_to_command_mode(self, psi_path: str):
        session_name = f"test-psi-mode-toggle-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    "/tmp",
                    psi_path,
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

            output_lower = output.lower()
            assert (
                "cwd" in output_lower
                or "ports" in output_lower
                or "cut" in output_lower
            ), f"Expected command visible in footer, got:\n{output}"

        finally:
            subprocess.run(
                tmux_cmd(socket, "kill-session", "-t", session_name),
                capture_output=True,
                timeout=5,
            )
            subprocess.run(
                tmux_cmd(socket, "kill-server"), capture_output=True, timeout=5
            )

    def test_toggle_does_not_show_raw_action_string(self, psi_path: str):
        session_name = f"test-psi-no-raw-action-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    "/tmp",
                    psi_path,
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
    def test_typing_filters_results(self, psi_path: str):
        session_name = f"test-psi-filter-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    "/tmp",
                    psi_path,
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
    def test_typing_in_command_mode_updates_results(self, psi_path: str):
        session_name = f"test-psi-cmd-type-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    "/tmp",
                    psi_path,
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
    def test_ctrl_l_filters_to_listening_processes(self, psi_path: str):
        session_name = f"test-psi-listening-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    "/tmp",
                    psi_path,
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

    def test_filter_persists_after_reload(self, psi_path: str):
        session_name = f"test-psi-persist-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    "/tmp",
                    psi_path,
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

            subprocess.run(
                tmux_cmd(socket, "send-keys", "-t", session_name, "C-r"),
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

            assert "[listening]" in output, (
                f"Expected [listening] in footer after reload, got:\n{output}"
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

    def test_ctrl_l_toggles_back_to_all_processes(self, psi_path: str):
        session_name = f"test-psi-all-{os.getpid()}"
        socket = get_test_tmux_socket(session_name)

        try:
            subprocess.run(
                tmux_cmd(
                    socket,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "-c",
                    "/tmp",
                    psi_path,
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

            assert "ps -U" in output, (
                f"Expected ps command in footer after toggle, got:\n{output}"
            )
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


class TestNonInteractiveMode:
    def test_psi_l_flag_shows_listening_processes(self, psi_path: str):
        result = subprocess.run(
            [psi_path, "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"psi -l failed: {result.stderr}"
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 1, "Expected at least header line"
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2:
                assert parts[1] != "-", f"Found non-listening process: {line}"

    def test_psi_listening_flag_works(self, psi_path: str):
        result = subprocess.run(
            [psi_path, "--listening"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"psi --listening failed: {result.stderr}"
        assert "PID" in result.stdout, "Expected header with PID column"

    def test_psi_columns_flag_adds_columns(self, psi_path: str):
        result = subprocess.run(
            [psi_path, "-l", "--columns", "cpu,mem"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"psi -l --columns failed: {result.stderr}"
        header = result.stdout.split("\n")[0]
        assert "%CPU" in header, "Expected %CPU column in header"
        assert "%MEM" in header, "Expected %MEM column in header"
        assert "STAT" not in header, "Unexpected STAT column"
        assert "TIME" not in header, "Unexpected TIME column"

    def test_psi_minimal_columns_by_default(self, psi_path: str):
        result = subprocess.run(
            [psi_path, "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"psi -l failed: {result.stderr}"
        header = result.stdout.split("\n")[0]
        assert "PID" in header, "Expected PID column"
        assert "PORTS" in header, "Expected PORTS column"
        assert "CWD" in header, "Expected CWD column"
        assert "COMMAND" in header, "Expected COMMAND column"
        assert "%CPU" not in header, "Unexpected %CPU column in minimal view"
        assert "%MEM" not in header, "Unexpected %MEM column in minimal view"


class TestModuleStructure:
    def test_psi_has_kill_action(self):
        content = PSI_MODULE.read_text()
        assert "ctrl-k" in content, "psi should have ctrl-k binding"
        assert "kill" in content.lower(), "psi should have kill functionality"

    def test_psi_has_header_lines_config(self):
        content = PSI_MODULE.read_text()
        assert "header_lines" in content, "psi should configure header_lines"

    def test_psi_has_listening_filter_bindings(self):
        content = PSI_MODULE.read_text()
        assert "ctrl-l" in content, "psi should have ctrl-l binding for listening"
        assert "toggle" in content.lower(), "psi should have toggle functionality"
        assert "LISTEN" in content, "psi should filter by LISTEN state"

    def test_psi_uses_help_text(self):
        content = PSI_MODULE.read_text()
        assert "app.help_text" in content, (
            "psi should use app.help_text() for keybindings"
        )
