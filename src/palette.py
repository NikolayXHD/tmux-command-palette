#!/usr/bin/env python3
"""tmux-command-palette — searchable keybinding documentation palette.

Replaces the native prefix ? (list-keys). The palette shows the key path,
description and command; entries marked can-exec run their command on Enter
(interactive ones — command-prompt/confirm-before/display-menu — open on the
client that launched the palette).

Pipeline (single process, runs inside display-popup):
  live tmux bindings + merged aliases
    -> fzf (search UI, palette_ui)
    -> execute the selected entry if allowed (palette_actions)

Alias sources (an alias describes an action; nothing is hidden when no
alias matches):
  palette.toml                — shared dictionary (in this repo), keyed by
    (table, exact command): stock tmux default commands plus plugin default
    commands (tpm, tmux-resurrect). Every live binding performing a
    recorded command gets the alias; unrecorded commands have none (we do
    not guarantee what we are not sure about).
  tmux-command-palette.toml   — personal aliases, kept next to your tmux.conf
    (falls back to the plugin dir); auto-maintained on every palette run:
       * bindings that differ from every expectation (stock defaults and
        palette.toml commands) are appended with a starting alias: base
        form from glossary.toml plus the remaining glossary synonyms for the
        jargon in the command (e.g. kill-pane -> "close pane, remove,
        delete");
      * when the command of a known binding changes, alias is regenerated
        (form + remaining jargon synonyms) and the old value is kept in
        alias_was;
      * filled-in aliases are never touched.
    An empty personal alias suppresses the shared entry for that key.

Expectations come from the stock defaults of this tmux version (fresh
server started with -f /dev/null) and from palette.toml commands.

Modes:
  (no args)     — interactive: sync the personal file, fzf over the live
                  bindings, run the selection
  --gen         — sync the personal file (same as the automatic step)
  --check       — validate both alias files; warn about stock bindings
                  without a shared alias (the dictionary is out of date)
  --exec IDENT  — execute entry table|key non-interactively (for testing)

palette.generated.toml — generated artifact: one entry per live binding
with command, note, alias, path, can_exec.
"""

from __future__ import annotations

import argparse
import os
import sys
import tomllib

from palette_data import (
    PALETTE_TOML,
    TmuxError,
    list_bindings,
    load_glossary,
    missing_group_words,
    personal_toml_path,
    read_toml_entries,
    shared_aliases,
    stock_bindings,
    sync_personal_file,
)
from palette_ui import cmd_ui


def validate_file(path, label: str, keyed_by_command: bool) -> str | None:
    """Return an error message, or None when the file is valid.

    palette.toml entries are keyed by (table, command) — they describe
    actions, not keys. The personal file stays keyed by (table, key).
    """
    if not path.exists():
        return f"{label}: not found"
    try:
        entries = read_toml_entries(path)
    except (tomllib.TOMLDecodeError, OSError) as error:
        return f"{label}: invalid TOML: {error}"
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        table = entry.get("table")
        ident = entry.get("command") if keyed_by_command else entry.get("key")
        if not table or not ident:
            return f"{label}: entry without table/{'command' if keyed_by_command else 'key'}"
        if (
            not keyed_by_command
            and not entry.get("alias", "")
            and not entry.get("alias_was", "")
        ):
            pass  # empty alias is the suppress marker in the personal file
        key_id = (table, ident)
        if key_id in seen:
            return f"{label}: duplicate entry {key_id}"
        seen.add(key_id)
    return None


def cmd_gen() -> int:
    """Sync the personal aliases file (same step as the automatic one)."""
    print(sync_personal_file())
    return 0


def cmd_check() -> int:
    """Validate both alias files and the shared dictionary itself.

    Checks the claims of palette.toml entries: stock bindings need an alias
    whose command equals the stock command (a mismatch means the entry
    describes another binding or the file is stale); non-stock entries need
    a command that matches some live binding. Glossary coverage: an entry
    whose command carries jargon must list every word of the resolved
    synonym group in its alias.
    """
    exit_code = 0
    for path, label, keyed in (
        (PALETTE_TOML, "palette.toml", True),
        (personal_toml_path(), "tmux-command-palette.toml", False),
    ):
        error = validate_file(path, label, keyed)
        if error is not None:
            print(error, file=sys.stderr)
            exit_code = 1
    if exit_code == 0:
        print("alias files: ok")

    # the shared dictionary is a public artifact: it must cover every stock
    # command of the tables a user can reach — prefix plus both copy-mode
    # variants — not only the tables visible in this session's mode-keys
    CHECK_TABLES = ("prefix", "copy-mode", "copy-mode-vi")
    shared = shared_aliases()
    stock_cmds = {
        (b.table, b.command) for b in stock_bindings() if b.table in CHECK_TABLES
    }
    live_cmds = {
        (b.table, b.command) for b in list_bindings() if b.table in CHECK_TABLES
    }

    problems = 0
    for table, command in sorted(stock_cmds - set(shared)):
        print(
            f"palette.toml: no alias for stock {table} command {command!r} "
            f"— dictionary out of date?",
            file=sys.stderr,
        )
        problems += 1
    for table, command in sorted(set(shared) - stock_cmds - live_cmds):
        print(
            f"palette.toml: {table} command {command!r}: not a stock command "
            f"of this tmux and no live binding performs it — stale entry?",
            file=sys.stderr,
        )
        problems += 1
    if problems:
        print(f"{problems} shared dictionary problem(s)", file=sys.stderr)
        exit_code = 1

    # glossary coverage: an entry whose command carries jargon must list
    # every word of the resolved synonym group in its alias
    glossary = load_glossary()
    glossary_problems = 0
    for entry in read_toml_entries(PALETTE_TOML):
        command = entry.get("command", "")
        alias = entry.get("alias", "")
        for word in missing_group_words(command, alias, glossary):
            print(
                f"palette.toml: {command!r}: alias lacks glossary word {word!r}",
                file=sys.stderr,
            )
            glossary_problems += 1
    if glossary_problems:
        print(f"{glossary_problems} glossary coverage problem(s)", file=sys.stderr)
        exit_code = 1
    return exit_code


def adopt_client_pane() -> None:
    """Point child tmux CLIs at the pane that opened the palette.

    The palette runs inside a display-popup pane, which dies when the popup
    closes. Commands executed afterwards (run-shell jobs, nested tmux CLIs
    such as tpm prompts) derive their target from TMUX_PANE — repoint it at
    the real pane so output and prompts land on the client that opened the
    palette, exactly as they do for a key binding.
    """
    pane = os.environ.get("TMUX_COMMAND_PALETTE_PANE", "")
    if pane:
        os.environ["TMUX_PANE"] = pane


def main() -> int:
    parser = argparse.ArgumentParser(prog="palette.py")
    parser.add_argument(
        "--gen", action="store_true", help="sync the personal aliases file"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate alias files, warn about uncovered stock bindings",
    )
    parser.add_argument(
        "--exec", metavar="IDENT", help="execute entry table|key if it can run detached"
    )
    parser.add_argument(
        "--client-tty",
        metavar="TTY",
        default="",
        help="tty of the client that opened the palette",
    )
    args = parser.parse_args()
    adopt_client_pane()

    try:
        if args.gen:
            return cmd_gen()
        if args.check:
            return cmd_check()
        if args.exec:
            from palette_actions import cmd_exec

            return cmd_exec(args.exec, args.client_tty or "")
        client_tty = args.client_tty or os.environ.get("TMUX_COMMAND_PALETTE_TTY", "")
        return cmd_ui(client_tty)
    except TmuxError as error:
        print(f"palette: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"palette: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
