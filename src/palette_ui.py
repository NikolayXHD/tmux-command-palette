"""fzf search UI and line rendering.

The list is assembled per query by palette_suggest.sh (See README.md,
Command history): the recent-command block is pinned to the top N
positions, the entries below keep fzf relevance ranking.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from palette_actions import cmd_exec
from palette_data import (
    FullEntry,
    build_full_entries,
    num_recent,
    sync_personal_file,
    write_full_toml,
)
from palette_history import HISTORY_TABLE, HistoryItem, escape_history_value, history_items

SUGGEST_SCRIPT = Path(__file__).with_name("palette_suggest.sh")

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
RECENT_MARK = "\x1b[32m\u21ba\x1b[0m"


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


def history_entry(item: HistoryItem, entry: FullEntry | None = None) -> FullEntry:
    """History row: the entry row with the recent marker, nothing else.

    Path and display are copied from the live binding performing the
    command; without one only the command is shown. The hidden identity
    column carries the stored command (hist|...), so the row re-runs even
    after a rebind. The displayed command is flattened to one line — an
    fzf row is one line — while the identity keeps the full command.
    """
    return FullEntry(
        table=HISTORY_TABLE,
        key=escape_history_value(item.command),
        command=re.sub(r"\s+", " ", item.command),
        note=entry.note if entry else "",
        alias=entry.alias if entry else "",
        path=entry.path if entry else "",
        can_exec=True,
    )


def build_lines(entries: list[FullEntry]) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        display = render_display(entry)
        if entry.table == HISTORY_TABLE:
            marked = f"{RECENT_MARK} {entry.path}".rstrip()
        else:
            marked = mark_path(entry.path, entry.can_exec)
        # third field carries the record identity; --with-nth hides it
        lines.append(f"{marked}\t{display}\t{entry.table}|{entry.key}")
    return lines


def cmd_ui(client_tty: str) -> int:
    """Interactive mode: sync the personal file, fzf over the live bindings.

    fzf runs with --disabled and reloads the list from palette_suggest.sh
    on every query change; the initial list (stdin) is the empty-query
    result: the last N commands of the history block and nothing else —
    entries appear only under a query, an empty history shows an empty
    list.
    """
    sync_personal_file()
    entries = build_full_entries(client_tty)
    write_full_toml(entries)
    entry_lines = build_lines(entries)
    entry_by_command: dict[str, FullEntry] = {}
    for entry in entries:
        entry_by_command.setdefault(entry.command, entry)
    recent_lines = build_lines(
        [
            history_entry(item, entry_by_command.get(item.command))
            for item in history_items()
        ]
    )
    block_size = num_recent()
    with tempfile.TemporaryDirectory() as tmp_dir:
        history_rows = Path(tmp_dir) / "history_rows"
        entry_rows = Path(tmp_dir) / "entry_rows"
        history_rows.write_text("\n".join(recent_lines) + "\n", encoding="utf-8")
        entry_rows.write_text("\n".join(entry_lines) + "\n", encoding="utf-8")
        reload_command = (
            f"{SUGGEST_SCRIPT} {{q}} {block_size} {history_rows} {entry_rows}"
        )
        fzf = subprocess.run(
            [
                "fzf",
                *FZF_ARGS,
                "--disabled",
                "--bind",
                f"change:reload:{reload_command}",
            ],
            input="\n".join(recent_lines[:block_size]),
            capture_output=True,
            text=True,
        )
    # fzf exits 130 on Esc (SIGINT): not an error, nothing selected
    if fzf.returncode not in (0, 130):
        return fzf.returncode
    if fzf.stdout.strip():
        return cmd_exec(fzf.stdout.strip(), client_tty)
    return 0
