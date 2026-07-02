from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

VUI_MODULE = Path(__file__).parent.parent / "src" / "fzfui" / "tools" / "vui.py"


@pytest.fixture(scope="module")
def vui_path() -> str:
    path = shutil.which("vui")
    assert path, "vui not found on PATH; run tests via 'uv run pytest'"
    return path


@pytest.fixture(scope="module", autouse=True)
def require_tools():
    for tool in ("tmux", "fzf", "fd", "bat", "nvim", "hx", "micro"):
        if not shutil.which(tool):
            pytest.skip(f"Missing required dependency: {tool}")


@pytest.fixture
def browse_dir(tmp_path: Path) -> Path:
    (tmp_path / "alpha.txt").write_text("hello world\nsecond line\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "beta.py").write_text("def foo():\n    return 42\n")
    return tmp_path


def socket_for(name: str) -> str:
    return f"test-socket-{name}"


def tmux_cmd(socket: str, *args: str) -> list[str]:
    return ["tmux", "-L", socket] + list(args)


def capture(socket: str, session: str) -> str:
    return subprocess.run(
        tmux_cmd(socket, "capture-pane", "-t", session, "-p"),
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout


def start(
    socket: str,
    session: str,
    vui_path: str,
    cwd: Path,
    action: str | None = None,
    env: dict[str, str] | None = None,
) -> None:
    prefix = "".join(f"{k}={v} " for k, v in (env or {}).items())
    if action:
        prefix += f"VUI_ACTION={action} "
    command = f"{prefix}{vui_path}"
    subprocess.run(
        tmux_cmd(
            socket,
            "new-session",
            "-d",
            "-s",
            session,
            "-x",
            "200",
            "-y",
            "50",
            "-c",
            str(cwd),
            command,
        ),
        check=True,
        timeout=5,
    )


def send(socket: str, session: str, keys: str) -> None:
    subprocess.run(tmux_cmd(socket, "send-keys", "-t", session, keys), check=True)


class TestBasicUI:
    def test_lists_files_with_preview(self, vui_path: str, browse_dir: Path):
        session = f"test-vui-list-{os.getpid()}"
        socket = socket_for(session)
        try:
            start(socket, session, vui_path, browse_dir)
            time.sleep(2)
            output = capture(socket, session)
            assert "alpha.txt" in output, output
            assert "sub/beta.py" in output, output
            # bat preview of the selected file (line numbers + content)
            assert "hello world" in output, output
        finally:
            subprocess.run(
                tmux_cmd(socket, "kill-server"), capture_output=True, timeout=5
            )

    def test_fuzzy_filter(self, vui_path: str, browse_dir: Path):
        session = f"test-vui-filter-{os.getpid()}"
        socket = socket_for(session)
        try:
            start(socket, session, vui_path, browse_dir)
            time.sleep(2)
            send(socket, session, "beta")
            time.sleep(1)
            output = capture(socket, session)
            assert "sub/beta.py" in output, output
            assert "def foo" in output, output
        finally:
            subprocess.run(
                tmux_cmd(socket, "kill-server"), capture_output=True, timeout=5
            )

    @pytest.mark.parametrize(
        "action, quit_keys",
        [
            ("nvim", ["Escape", ":q!", "Enter"]),
            ("hx", ["Escape", ":q!", "Enter"]),
            ("micro", ["C-q"]),
        ],
    )
    def test_enter_opens_editor_then_quit_returns(
        self, vui_path: str, browse_dir: Path, action: str, quit_keys: list[str]
    ):
        (browse_dir / "big.txt").write_text(
            "".join(f"line {i}\n" for i in range(1, 301))
        )
        session = f"test-vui-{action}-{os.getpid()}"
        socket = socket_for(session)
        # Isolate micro from the developer's config (e.g. a missing colorscheme)
        env = (
            {"MICRO_CONFIG_HOME": str(browse_dir / ".microcfg")}
            if action == "micro"
            else None
        )
        try:
            start(socket, session, vui_path, browse_dir, action=action, env=env)
            time.sleep(2)
            send(socket, session, "big")
            time.sleep(1)
            send(socket, session, "Enter")
            time.sleep(2)
            in_editor = capture(socket, session)
            # editor took over: file content shown, fzf's fd footer gone
            assert "line 1" in in_editor, in_editor
            assert "fd --type f" not in in_editor, in_editor

            for key in quit_keys:
                send(socket, session, key)
                time.sleep(0.3)
            time.sleep(2)
            back = capture(socket, session)
            # Back in fzf: the fd footer is visible again
            assert "fd --type f" in back, back
            assert "big.txt" in back, back
        finally:
            subprocess.run(
                tmux_cmd(socket, "kill-server"), capture_output=True, timeout=5
            )

    def test_enter_opens_bat_then_q_returns(self, vui_path: str, browse_dir: Path):
        (browse_dir / "big.txt").write_text(
            "".join(f"line {i}\n" for i in range(1, 301))
        )
        session = f"test-vui-bat-{os.getpid()}"
        socket = socket_for(session)
        try:
            start(socket, session, vui_path, browse_dir, action="bat")
            time.sleep(2)
            send(socket, session, "big")
            time.sleep(1)
            send(socket, session, "Enter")
            time.sleep(1.5)
            in_pager = capture(socket, session)
            # Full bat pager: fzf's preview border is gone, bat's file header shows
            assert "File: big.txt" in in_pager, in_pager
            assert "line 1" in in_pager, in_pager

            send(socket, session, "q")
            time.sleep(1.5)
            back = capture(socket, session)
            # Back in fzf: the preview pane border is visible again
            assert "big.txt" in back, back
            assert "│" in back, back
        finally:
            subprocess.run(
                tmux_cmd(socket, "kill-server"), capture_output=True, timeout=5
            )


class TestModuleStructure:
    def test_vui_uses_bat_preview(self):
        content = VUI_MODULE.read_text()
        assert "bat" in content and "app.preview" in content, (
            "should register a bat preview"
        )

    def test_vui_action_env_var(self):
        content = VUI_MODULE.read_text()
        assert "VUI_ACTION" in content, "enter action should be chosen by VUI_ACTION"
        for action in ("nvim", "hx", "micro", "bat"):
            assert action in content, f"VUI_ACTION should support {action}"

    def test_vui_lists_files(self):
        content = VUI_MODULE.read_text()
        assert "fd" in content and "--type f" in content
