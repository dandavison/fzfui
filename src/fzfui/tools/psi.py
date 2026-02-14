"""psi - Interactive process viewer built with fzfui."""

from __future__ import annotations

import os
import subprocess
import sys
from textwrap import dedent

import fzfui

OPTIONAL_COLUMNS = ("cpu", "mem", "stat", "time")
ALL_COLUMNS = OPTIONAL_COLUMNS


def main() -> None:
    try:
        os.environ.setdefault("COLUMNS", str(os.get_terminal_size().columns))
    except OSError:
        pass

    app = fzfui.App()
    script = app.script

    columns = _get_columns_from_argv()

    ps_default = _build_ps_command(())
    footer_default = _ps_footer(())

    # Register all filter combinations
    ps_min = _build_ps_command(())
    listening_min = ps_min.rstrip() + " | awk 'NR==1 || $2!=\"-\"'"
    footer_min = _ps_footer(())

    ps_full = _build_ps_command(ALL_COLUMNS)
    listening_full = ps_full.rstrip() + " | awk 'NR==1 || $2!=\"-\"'"
    footer_full = _ps_footer(ALL_COLUMNS)

    app.register_filter("all", ps_min, footer=footer_min, default=True)
    app.register_filter("all-full", ps_full, footer=f"{footer_full} [+cols]")
    app.register_filter("listening", listening_min, footer=f"{footer_min} [listening]")
    app.register_filter(
        "listening-full", listening_full, footer=f"{footer_full} [listening,+cols]"
    )

    # CLI flags for non-interactive mode
    ps_cli = _build_ps_command(columns)
    listening_cli = ps_cli.rstrip() + " | awk 'NR==1 || $2!=\"-\"'"
    footer_cli = _ps_footer(columns)
    col_suffix = f" [{','.join(columns)}]" if columns else ""
    app.register_filter(
        "listening-cli",
        listening_cli,
        footer=f"{footer_cli} [listening]{col_suffix}",
        cli=("-l", "--listening"),
    )

    toggle_listening = f"transform({script} _toggle-listening)"
    toggle_columns = f"transform({script} _toggle-columns)"

    @app.main(
        command=ps_default,
        header_lines=1,
        with_nth="2..",
        fzf_options=["--footer", footer_default],
        bindings={"ctrl-l": toggle_listening, "ctrl-o": toggle_columns},
    )
    def psi():
        pass

    @app.cli.command("_toggle-listening", hidden=True)
    def toggle_listening_cmd():
        """Toggle between all processes and listening-only."""
        current = app.current_filter
        if current and "full" in current.name:
            print(app.toggle_filter("all-full", "listening-full"))
        else:
            print(app.toggle_filter("all", "listening"))

    @app.cli.command("_toggle-columns", hidden=True)
    def toggle_columns_cmd():
        """Toggle between minimal and full columns."""
        current = app.current_filter
        name = current.name if current else "all"
        if "full" in name:
            new_name = name.replace("-full", "")
        else:
            new_name = f"{name}-full"
        print(app.set_filter(new_name))

    @app.action("enter", description="Show process details", field=1)
    def detail(pid: str):
        pid = pid.strip()
        if not pid.isdigit():
            return

        result = subprocess.run(
            [
                "ps",
                "-p",
                pid,
                "-o",
                "pid=,user=,%cpu=,%mem=,stat=,start=,time=,command=",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"Process {pid} not found")
            input("Press any key...")
            return

        parts = result.stdout.strip().split(None, 7)
        info = dict(
            zip(
                ["pid", "user", "cpu", "mem", "stat", "start", "time", "cmd"],
                parts + [""] * (8 - len(parts)),
            )
        )
        info["cmd"] = info["cmd"][:70]

        lsof_result = subprocess.run(
            ["lsof", "-p", pid], capture_output=True, text=True
        )
        if lsof_result.returncode == 0:
            lines = lsof_result.stdout.strip().split("\n")[1:21]
            files = (
                "\n".join(
                    f"        {p[4]:10} {p[8]}"
                    for line in lines
                    if len(p := line.split()) >= 9
                )
                or "        (none)"
            )
        else:
            files = "        (permission denied)"

        os.system("clear")
        print(
            dedent(f"""
            ═══════════════════════════════════════════════════════════════════
              PROCESS DETAILS (PID: {pid})
            ═══════════════════════════════════════════════════════════════════

              PID      {info["pid"]}
              User     {info["user"]}
              CPU      {info["cpu"]}
              Memory   {info["mem"]}
              State    {info["stat"]}
              Started  {info["start"]}
              Time     {info["time"]}

              Command:
                {info["cmd"]}

            ───────────────────────────────────────────────────────────────────
              Open files/ports (first 20):
            {files}

            ═══════════════════════════════════════════════════════════════════
        """)
        )
        input("Press any key...")

    @app.action(
        "ctrl-k",
        description="Kill process (SIGKILL)",
        reload=True,
        silent=True,
        field=1,
    )
    def kill_proc(pid: str):
        pid = pid.strip()
        if pid.isdigit():
            try:
                os.kill(int(pid), 9)
            except ProcessLookupError:
                pass

    @app.action("ctrl-r", description="Reload process list", reload=True, silent=True)
    def reload(_: str):
        pass

    @app.preview
    def help_panel(_: str) -> str:
        extra_bindings = {
            "ctrl-l": "Toggle listening-only filter",
            "ctrl-o": "Toggle extra columns (cpu,mem,stat,time)",
        }
        return app.help_text(extra_bindings=extra_bindings)

    _strip_columns_arg()
    app()


def _get_columns_from_argv() -> tuple[str, ...]:
    """Parse --columns argument from sys.argv."""
    for i, arg in enumerate(sys.argv):
        if arg == "--columns" and i + 1 < len(sys.argv):
            cols = tuple(c.strip() for c in sys.argv[i + 1].split(","))
            return tuple(c for c in cols if c in OPTIONAL_COLUMNS)
        if arg.startswith("--columns="):
            cols = tuple(c.strip() for c in arg.split("=", 1)[1].split(","))
            return tuple(c for c in cols if c in OPTIONAL_COLUMNS)
    return ()


def _strip_columns_arg() -> None:
    """Remove --columns arg from sys.argv so typer doesn't see it."""
    i = 0
    while i < len(sys.argv):
        if sys.argv[i] == "--columns" and i + 1 < len(sys.argv):
            sys.argv.pop(i)
            sys.argv.pop(i)
        elif sys.argv[i].startswith("--columns="):
            sys.argv.pop(i)
        else:
            i += 1


def _build_ps_command(columns: tuple[str, ...] = ()) -> str:
    """Build the ps command with optional columns."""
    cols = set(columns)
    fixed_headers: list[str] = ["$1", '"PORTS"']
    fixed_data: list[str] = ["$1", "p"]

    if "cpu" in cols:
        fixed_headers.append("$2")
        fixed_data.append("$2")
    if "mem" in cols:
        fixed_headers.append("$3")
        fixed_data.append("$3")
    if "stat" in cols:
        fixed_headers.append("$4")
        fixed_data.append("$4")
    if "time" in cols:
        fixed_headers.append("$5")
        fixed_data.append("$5")

    fixed_headers.append('"CWD"')
    fixed_data.append("c")

    nc = len(fixed_headers)
    fc = nc + 1

    header_stores = "; ".join(f"f[0,{i}] = {h}" for i, h in enumerate(fixed_headers, 1))
    header_stores += f'; f[0,{fc}] = "COMMAND"'

    data_stores = "; ".join(f"f[nr,{i}] = {d}" for i, d in enumerate(fixed_data, 1))
    data_stores += f"; f[nr,{fc}] = cmd"

    return rf"""
tw=${{FZF_COLUMNS:-${{COLUMNS:-$(tput cols 2>/dev/null || echo 120)}}}}
ps -U $USER -o pid,%cpu,%mem,stat,time,command | awk -v tw="$tw" '
BEGIN {{
    if (tw+0 < 40) tw = 120
    cmd = "lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null"
    while ((cmd | getline line) > 0) {{
        n = split(line, arr)
        if (n >= 9 && arr[1] != "COMMAND") {{
            pid = arr[2]; port = arr[9]
            gsub(/.*:/, "", port); gsub(/\(LISTEN\)/, "", port)
            if (pid in ports) ports[pid] = ports[pid] "," port
            else ports[pid] = port
        }}
    }}
    close(cmd)
    cmd = "lsof -d cwd -a -u $USER 2>/dev/null"
    while ((cmd | getline line) > 0) {{
        n = split(line, arr)
        if (n >= 9 && arr[1] != "COMMAND") {{
            pid = arr[2]; cwd[pid] = arr[n]
        }}
    }}
    close(cmd)
}}
NR == 1 {{
    {header_stores}
    for (i = 1; i <= {fc}; i++) if (length(f[0,i]) > w[i]) w[i] = length(f[0,i])
    nr = 1; next
}}
{{
    p = ($1 in ports) ? ports[$1] : "-"
    c = ($1 in cwd) ? cwd[$1] : "-"
    home = ENVIRON["HOME"]
    if (home != "" && index(c, home) == 1) c = "~" substr(c, length(home) + 1)
    cmd = ""
    for (i = 6; i <= NF; i++) cmd = cmd (i > 6 ? " " : "") $i
    {data_stores}
    for (i = 1; i <= {fc}; i++) if (length(f[nr,i]) > w[i]) w[i] = length(f[nr,i])
    nr++
}}
END {{
    total = 0
    for (i = 1; i <= {fc}; i++) total += w[i] + (i < {fc} ? 2 : 0)
    if (total > tw) {{
        pcap = int(tw / 4); if (pcap < 10) pcap = 10
        if (w[2] > pcap) w[2] = pcap
        ccap = int(tw / 3); if (ccap < 15) ccap = 15
        if (w[{nc}] > ccap) w[{nc}] = ccap
    }}
    cw = tw
    for (i = 1; i <= {nc}; i++) cw -= w[i] + 2
    if (cw < 20) cw = 20
    w[{fc}] = cw
    for (r = 0; r < nr; r++) {{
        s = ""
        for (i = 1; i <= {fc}; i++) {{
            v = f[r,i]
            if (length(v) > w[i]) v = substr(v, 1, w[i] - 3) "..."
            if (i < {fc}) s = s sprintf("%-" w[i] "s  ", v)
            else s = s v
        }}
        print s
    }}
}}
'
"""


def _ps_footer(columns: tuple[str, ...] = ()) -> str:
    """Build footer text showing the conceptual ps command."""
    cols = set(columns)
    parts = ["pid"]
    if "cpu" in cols:
        parts.append("%cpu")
    if "mem" in cols:
        parts.append("%mem")
    if "stat" in cols:
        parts.append("stat")
    if "time" in cols:
        parts.append("time")
    parts.append("command")
    return f"ps -U $USER -o {','.join(parts)}"
