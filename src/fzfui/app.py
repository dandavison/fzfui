from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

import typer


@dataclass
class Action:
    fn: Callable
    key: str
    reload: bool = False
    silent: bool = False
    field: int = 0
    exit: bool = False


class App:
    def __init__(self, script: str):
        self.script = os.path.abspath(script)
        self.cli = typer.Typer(add_completion=False, no_args_is_help=False)

        self._command: str = ""
        self._config: dict = {}
        self._actions: dict[str, Action] = {}
        self._preview_fn: Optional[Callable] = None
        self._query_preview_fn: Optional[Callable] = None
        self._reload_command: Optional[str] = None
        self._main_fn: Optional[Callable] = None

        self._register_internal_commands()

    def _register_internal_commands(self):
        @self.cli.command("_toggle", hidden=True)
        def toggle_cmd():
            self._handle_toggle()

        @self.cli.command("_on-change", hidden=True)
        def on_change_cmd():
            self._handle_on_change()

        @self.cli.command("_action", hidden=True)
        def action_cmd(name: str, selection: str = typer.Argument("")):
            self._handle_action(name, selection)

        @self.cli.command("_preview", hidden=True)
        def preview_cmd(selection: str = typer.Argument("")):
            if self._preview_fn:
                print(self._preview_fn(selection))

        @self.cli.command("_query-preview", hidden=True)
        def query_preview_cmd(query: str = typer.Argument("")):
            if self._query_preview_fn:
                print(self._query_preview_fn(query))

        @self.cli.command("_reload", hidden=True)
        def reload_cmd():
            os.system(self._reload_command or self._command)

    def _handle_toggle(self):
        state_file = os.environ["FZFUI_STATE"]
        with open(state_file) as f:
            mode, query, cmd = f.read().strip().split("|", 2)

        fzf_query = os.environ.get("FZF_QUERY", "")

        if mode == "query":
            with open(state_file, "w") as f:
                f.write(f"command|{fzf_query}|{cmd}")
            print(
                f"disable-search+change-query({cmd})+change-footer({fzf_query})+change-prompt(> )"
            )
        else:
            new_cmd = fzf_query
            with open(state_file, "w") as f:
                f.write(f"query|{query}|{new_cmd}")
            escaped = shlex.quote(new_cmd)
            print(
                f"enable-search+reload(eval {escaped} 2>/dev/null)+change-query({query})+change-footer({new_cmd})+change-prompt(/ )"
            )

    def _handle_on_change(self):
        state_file = os.environ["FZFUI_STATE"]
        with open(state_file) as f:
            mode = f.read().split("|")[0]

        if mode == "command":
            fzf_query = os.environ.get("FZF_QUERY", "")
            escaped = shlex.quote(fzf_query)
            print(f"reload:eval {escaped} 2>/dev/null")

    def _handle_action(self, name: str, selection: str):
        if name in self._actions:
            action = self._actions[name]
            action.fn(selection)

    def main(
        self,
        command: str = "",
        *,
        header_lines: int = 0,
        with_nth: Optional[str] = None,
        reload_command: Optional[str] = None,
        disabled: bool = False,
        initial_query: str = "",
        preview_window: Optional[str] = None,
        bindings: Optional[dict[str, str]] = None,
        fzf_options: Optional[list[str]] = None,
    ):
        """
        Decorator to configure the main fzf interface.

        Args:
            command: Shell command to generate items (not needed for disabled mode)
            header_lines: Number of header lines in command output
            with_nth: Field selector for display (e.g., "2..")
            reload_command: Command for reload action (defaults to command)
            disabled: If True, use preview mode (query is input, not filter)
            initial_query: Starting query string
            preview_window: Preview window config (e.g., "up,80%,wrap")
            bindings: Extra fzf key bindings (e.g., {"ctrl-k": "kill-line"})
            fzf_options: Raw fzf CLI options (e.g., ["--height", "100%"])
        """
        def decorator(fn):
            self._command = command
            self._reload_command = reload_command or command
            self._config = {
                "header_lines": header_lines,
                "with_nth": with_nth,
                "disabled": disabled,
                "initial_query": initial_query,
                "preview_window": preview_window,
                "bindings": bindings or {},
                "fzf_options": fzf_options or [],
            }
            self._main_fn = fn

            @self.cli.callback(invoke_without_command=True)
            def wrapper(ctx: typer.Context):
                if ctx.invoked_subcommand is None:
                    self._run_fzf()

            return fn

        return decorator

    def arg(self, name: str, default: Optional[str] = None) -> str:
        """Get a CLI argument value (set via FZFUI_ARG_<name> env var)."""
        return os.environ.get(f"FZFUI_ARG_{name}", default or "")

    def action(self, key: str, *, reload: bool = False, silent: bool = False, field: int = 0, exit: bool = False):
        def decorator(fn):
            self._actions[fn.__name__] = Action(
                fn=fn, key=key, reload=reload, silent=silent, field=field, exit=exit
            )
            return fn

        return decorator

    def preview(self, fn: Callable):
        """Preview based on selected item."""
        self._preview_fn = fn
        return fn

    def query_preview(self, fn: Callable):
        """Preview based on query string (for disabled/preview mode)."""
        self._query_preview_fn = fn
        return fn

    def _run_fzf(self):
        disabled = self._config.get("disabled", False)

        if disabled:
            self._run_fzf_preview_mode()
        else:
            self._run_fzf_filter_mode()

    def _run_fzf_preview_mode(self):
        """Run fzf in preview/disabled mode (query is input, not filter)."""
        script = self.script
        initial_query = self._config.get("initial_query", "")
        preview_window = self._config.get("preview_window", "up,80%,wrap")

        args = [
            "fzf",
            "--ansi",
            "--disabled",
            "--layout", "reverse",
            "--prompt", "> ",
            "--with-shell", "bash -c",
        ]

        if initial_query:
            args.extend(["--query", initial_query])

        # Query-based preview
        if self._query_preview_fn:
            args.extend([
                "--preview", f"{script} _query-preview {{q}}",
                "--preview-window", preview_window,
            ])

        # Actions
        for name, action in self._actions.items():
            execute = "execute-silent" if action.silent else "execute"
            binding = f"{execute}({script} _action {name} {{q}})"
            if action.exit:
                binding += "+abort"
            args.extend(["--bind", f"{action.key}:{binding}"])

        # Custom bindings (e.g., emacs keys)
        for key, fzf_action in self._config.get("bindings", {}).items():
            args.extend(["--bind", f"{key}:{fzf_action}"])

        # Raw fzf options
        args.extend(self._config.get("fzf_options", []))

        # Feed empty input - we don't need items in preview mode
        fzf_proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            env=os.environ,
        )
        fzf_proc.communicate(input=b"\n")

    def _run_fzf_filter_mode(self):
        """Run fzf in filter mode (classic item selection)."""
        state_fd, state_file = tempfile.mkstemp(prefix="fzfui-")
        os.write(state_fd, f"query||{self._command}".encode())
        os.close(state_fd)

        try:
            env = os.environ.copy()
            env["FZFUI_STATE"] = state_file

            script = self.script
            field_spec = "{}" if not self._config.get("with_nth") else "{1}"

            args = [
                "fzf",
                "--ansi",
                "--border",
                "none",
                "--no-separator",
                "--footer",
                self._command,
                "--prompt",
                "/ ",
                "--with-shell",
                "bash -c",
                "--bind",
                f"ctrl-\\:transform:{script} _toggle",
                "--bind",
                f"change:transform:{script} _on-change",
            ]

            if self._config.get("header_lines"):
                args.extend(["--header-lines", str(self._config["header_lines"])])
            if self._config.get("with_nth"):
                args.extend(["--with-nth", self._config["with_nth"]])

            for name, action in self._actions.items():
                execute = "execute-silent" if action.silent else "execute"
                field = f"{{{action.field}}}" if action.field else field_spec
                binding = f"{execute}({script} _action {name} {field})"
                if action.reload:
                    binding += f"+reload({script} _reload)"
                if action.exit:
                    binding += "+abort"
                args.extend(["--bind", f"{action.key}:{binding}"])

            if self._preview_fn:
                args.extend(
                    [
                        "--preview",
                        f"{script} _preview {field_spec}",
                        "--preview-window",
                        "up,30%,hidden,wrap",
                        "--bind",
                        "ctrl-h:toggle-preview",
                    ]
                )

            # Custom bindings
            for key, fzf_action in self._config.get("bindings", {}).items():
                args.extend(["--bind", f"{key}:{fzf_action}"])

            # Raw fzf options
            args.extend(self._config.get("fzf_options", []))

            cmd_proc = subprocess.Popen(
                self._command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

            fzf_proc = subprocess.Popen(
                args,
                stdin=cmd_proc.stdout,
                env=env,
            )
            fzf_proc.wait()

        finally:
            os.unlink(state_file)

    def __call__(self):
        self.cli()

