"""See README.md (Command history) — format and location of the history file.

Palette command history: every command the palette executes is upserted
into a history file in the fish history format (`- cmd:` / `when:` blocks,
two escapes — backslash and newline). One record per command — the save
step of fish: a repeat moves `when` and keeps `added_when` (the first
execution). The reader still merges duplicate records, so a fish-style
append-only file stays readable.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from palette_data import personal_toml_path

HISTORY_FILENAME = "tmux-command-palette.history"
# pseudo-table that marks a history row identity (hist|<escaped command>)
HISTORY_TABLE = "hist"


def history_path() -> Path:
    """History file next to the personal alias file (same config dir)."""
    return personal_toml_path().parent / HISTORY_FILENAME


def escape_history_value(text: str) -> str:
    """Command text -> one history file line: fish escapes, nothing else.

    Order matters: double the backslashes first, then the newlines, so the
    inserted backslashes are not doubled again.
    """
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def unescape_history_value(text: str) -> str:
    """History file value -> command text (inverse of escape_history_value).

    An unknown escape pair stays verbatim: the writer never produces one,
    and a hand-edited `\\t` more likely means a literal backslash-t than a
    tab.
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            if following == "\\":
                out.append("\\")
                index += 2
                continue
            if following == "n":
                out.append("\n")
                index += 2
                continue
        out.append(char)
        index += 1
    return "".join(out)


@dataclass(frozen=True)
class HistoryItem:
    """One distinct command, merged from its records."""

    command: str
    first_added: int
    last_added: int


def history_items(path: Path | None = None) -> list[HistoryItem]:
    """Merged history items, most recently executed first.

    Repeated executions collapse into one item (fish merge semantics):
    recency is the last execution, the tie between items executed within
    the same second goes to the later record in the file.
    """
    records = _parse_records(_read_text(path or history_path()))
    first_added: dict[str, int] = {}
    last_added: dict[str, int] = {}
    last_position: dict[str, int] = {}
    for position, (command, when, added_when) in enumerate(records):
        if not command:
            continue
        known_when = when if when is not None else 0
        first = added_when if added_when is not None else known_when
        first_added[command] = min(first_added.get(command, first), first)
        last_added[command] = max(last_added.get(command, known_when), known_when)
        last_position[command] = position
    items = [
        HistoryItem(command, first_added[command], last_added[command])
        for command in last_added
    ]
    items.sort(
        key=lambda item: (last_added[item.command], last_position[item.command]),
        reverse=True,
    )
    return items


def record_execution(
    command: str, path: Path | None = None, when: int | None = None
) -> None:
    """Upsert one execution: one record per command, newest first.

    A repeat updates the record (`when` moves, `added_when` keeps the
    first execution) — the save step of fish, its merged view made
    persistent. The file is rewritten through a per-process temporary file
    and an atomic replace; two executions within the same instant can
    still overwrite each other's record (accepted, single user).
    """
    target = path or history_path()
    executed_at = int(time.time()) if when is None else when
    items = history_items(target)
    known = next((item for item in items if item.command == command), None)
    first_added = known.first_added if known is not None else executed_at
    updated = HistoryItem(command, first_added, executed_at)
    ordered = [updated] + [item for item in items if item.command != command]
    _write_history_items(target, ordered)


def _write_history_items(path: Path, items: list[HistoryItem]) -> None:
    """Rewrite the history file atomically: one record per item, newest first.

    The replacement goes through a per-process temporary file; a temp file
    left behind by a killed palette process is removed on the next write,
    a failed write removes its own.
    """
    for stale in path.parent.glob(f"{path.name}.*.tmp"):
        stale.unlink(missing_ok=True)
    lines: list[str] = []
    for item in items:
        lines.append(f"- cmd: {escape_history_value(item.command)}")
        lines.append(f"  when: {item.last_added}")
        if item.first_added != item.last_added:
            lines.append(f"  added_when: {item.first_added}")
    payload = ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(descriptor, payload)
        finally:
            os.close(descriptor)
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _parse_records(text: str) -> list[tuple[str, int | None, int | None]]:
    """(command, when, added_when) per file record, in file order.

    Fish-compatible reader: a record starts at a `- cmd:` line, interior
    lines are indented key/value pairs, `paths` takes deeper `- ` lines.
    Unknown keys are ignored, a line that does not parse ends the record,
    stray and broken lines are skipped.
    """
    records: list[tuple[str, int | None, int | None]] = []
    command = ""
    when = added_when = None
    open_record = False
    indent = 0
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        content = line.lstrip(" ")
        lead = len(line) - len(content)
        if lead == 0:
            if open_record:
                records.append((command, when, added_when))
                open_record = False
            if content.startswith("- cmd"):
                _, _, value = content.partition(":")
                command = unescape_history_value(value.lstrip())
                when = added_when = None
                open_record = True
                indent = 0
            index += 1
            continue
        if not open_record:
            index += 1
            continue
        if indent == 0:
            indent = lead
        key, separator, value = content.partition(":")
        if lead != indent or not separator:
            records.append((command, when, added_when))
            open_record = False
            index += 1
            continue
        if key == "when":
            when = _parse_timestamp(value)
        elif key == "added_when":
            added_when = _parse_timestamp(value)
        elif key == "paths":
            index = _skip_path_lines(lines, index + 1, indent)
            continue
        index += 1
    if open_record:
        records.append((command, when, added_when))
    return records


def _skip_path_lines(lines: list[str], index: int, indent: int) -> int:
    """Index of the first line after the `paths` list items."""
    while index < len(lines):
        line = lines[index]
        content = line.lstrip(" ")
        lead = len(line) - len(content)
        if lead <= indent or not content.startswith("- "):
            return index
        index += 1
    return index


def _parse_timestamp(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
