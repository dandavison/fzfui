"""Tests for clipboard abstraction."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fzfui import copy_to_clipboard


class TestCopyToClipboard:
    def test_uses_pbcopy_on_macos(self):
        with (
            patch("fzfui.app.sys") as mock_sys,
            patch("fzfui.app.subprocess.run") as mock_run,
        ):
            mock_sys.platform = "darwin"
            copy_to_clipboard("hello")
            mock_run.assert_called_once_with(
                ["pbcopy"], input="hello", text=True, check=True
            )

    def test_uses_xclip_on_linux(self):
        with (
            patch("fzfui.app.sys") as mock_sys,
            patch("fzfui.app.shutil.which", return_value="/usr/bin/xclip"),
            patch("fzfui.app.subprocess.run") as mock_run,
        ):
            mock_sys.platform = "linux"
            copy_to_clipboard("hello")
            mock_run.assert_called_once_with(
                ["xclip", "-selection", "clipboard"],
                input="hello",
                text=True,
                check=True,
            )

    def test_uses_xsel_on_linux(self):
        def which(cmd: str) -> str | None:
            return "/usr/bin/xsel" if cmd == "xsel" else None

        with (
            patch("fzfui.app.sys") as mock_sys,
            patch("fzfui.app.shutil.which", side_effect=which),
            patch("fzfui.app.subprocess.run") as mock_run,
        ):
            mock_sys.platform = "linux"
            copy_to_clipboard("hello")
            mock_run.assert_called_once_with(
                ["xsel", "--clipboard", "--input"],
                input="hello",
                text=True,
                check=True,
            )

    def test_uses_wl_copy_on_linux(self):
        def which(cmd: str) -> str | None:
            return "/usr/bin/wl-copy" if cmd == "wl-copy" else None

        with (
            patch("fzfui.app.sys") as mock_sys,
            patch("fzfui.app.shutil.which", side_effect=which),
            patch("fzfui.app.subprocess.run") as mock_run,
        ):
            mock_sys.platform = "linux"
            copy_to_clipboard("hello")
            mock_run.assert_called_once_with(
                ["wl-copy"], input="hello", text=True, check=True
            )

    def test_raises_on_linux_no_clipboard_tool(self):
        with (
            patch("fzfui.app.sys") as mock_sys,
            patch("fzfui.app.shutil.which", return_value=None),
        ):
            mock_sys.platform = "linux"
            with pytest.raises(RuntimeError, match="No clipboard tool found"):
                copy_to_clipboard("hello")

    def test_raises_on_unsupported_platform(self):
        with patch("fzfui.app.sys") as mock_sys:
            mock_sys.platform = "win32"
            with pytest.raises(RuntimeError, match="Clipboard not supported"):
                copy_to_clipboard("hello")
