"""fzf search UI and line rendering."""

from __future__ import annotations

import subprocess

from palette_actions import cmd_exec
from palette_data import (
    FullEntry,
    build_full_entries,
    sync_personal_file,
    write_full_toml,
)

FZF_ARGS = [
    "--ansi",
    "--with-nth=1,2",
    "--delimiter=\t",
    "--tiebreak=begin",
    "--layout=reverse",
    "--height=100%",
    "--scrollbar",
    "--info=inline-right",
    "--wrap=word",
]

EXEC_MARK = "\x1b[32m\u25b6\x1b[0m"
NOEXEC_MARK = "\x1b[2m\u00b7\x1b[0m"


def mark_path(path: str, can_exec: bool) -> str:
    """Prefix the path with an exec indicator, keeping columns aligned."""
    mark = EXEC_MARK if can_exec else NOEXEC_MARK
    return f"{mark} {path}"


def render_display(entry: FullEntry) -> str:
    """Brand: note (-N) bright; alias and command body dimmed.

    fzf gets --ansi; \x1b[0m resets around each span so the highlight
    color does not leak into the next segment.
    """
    note = entry.note
    dim_command = f"\x1b[2m{entry.command}\x1b[0m"
    if note and entry.alias:
        return f"\x1b[1m{note}\x1b[0m  \x1b[2m({entry.alias})\x1b[0m  {dim_command}"
    if note:
        return f"\x1b[1m{note}\x1b[0m  {dim_command}"
    if entry.alias:
        return f"\x1b[1m{entry.alias}\x1b[0m  {dim_command}"
    return dim_command


def build_lines(entries: list[FullEntry]) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        display = render_display(entry)
        # third field carries the record identity; --with-nth hides it
        lines.append(f"{mark_path(entry.path, entry.can_exec)}\t{display}\t{entry.table}|{entry.key}")
    return lines


def cmd_ui(client_tty: str) -> int:
    """Interactive mode: sync the personal file, fzf over the live bindings."""
    sync_personal_file()
    entries = build_full_entries(client_tty)
    write_full_toml(entries)
    fzf = subprocess.run(
        ["fzf", *FZF_ARGS],
        input="\n".join(build_lines(entries)),
        capture_output=True,
        text=True,
    )
    # fzf exits 130 on Esc (SIGINT): not an error, nothing selected
    if fzf.returncode not in (0, 130):
        return fzf.returncode
    if fzf.stdout.strip():
        return cmd_exec(fzf.stdout.strip(), client_tty)
    return 0
