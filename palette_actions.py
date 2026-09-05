"""Command execution for selected palette entries."""

from __future__ import annotations

import os
import subprocess
import sys

from palette_data import (
    INTERACTIVE_PREFIXES,
    TmuxError,
    build_full_entries,
    can_exec_command,
)

# display-message shows on a client but returns immediately: it gets the
# client injected like interactive commands, but runs synchronously.
CLIENT_TARGET_PREFIXES = (*INTERACTIVE_PREFIXES, "display-message")


def _has_option_before_quote(command: str, option: str) -> bool:
    """Whether `option` appears as a token before any quoting starts.

    tmux config syntax may quote the rest of the command ({}, " or '); an
    option mentioned inside quoted text is not a real option of this
    command, so the scan stops at the first quote character.
    """
    for token in command.split():
        if token[0] in "{\"'":
            break
        if token == option:
            return True
    return False


def inject_client_target(command: str, client_tty: str) -> str:
    """Inject -t <client-tty> into interactive commands.

    command-prompt, confirm-before, display-menu and display-message open on
    a target client (-t). Without it the prompt would land on an arbitrary
    client; we pass the tty of the client that opened the palette.
    """
    if not client_tty:
        return command
    tokens = command.split(None, 1)
    if not tokens:
        return command
    head = tokens[0]
    rest = tokens[1] if len(tokens) > 1 else ""
    # skip existing -t (outside quoted text) to avoid duplicates
    if _has_option_before_quote(command, "-t"):
        return command
    return f"{head} -t {client_tty} {rest}"


def inject_run_shell_target(command: str, pane: str) -> str:
    """Give a run-shell an explicit target pane.

    Commands run through the tmux CLI (palette) have no target pane, so the
    job output would go to the CLI stdout (nowhere for the palette). With
    -t <pane> the output lands in the pane, like it does for a key binding.
    """
    if not pane:
        return command
    tokens = command.split(None, 1)
    if len(tokens) < 2 or tokens[0] != "run-shell":
        return command
    if _has_option_before_quote(command, "-t"):
        return command
    # keep the rest verbatim (flags and quoted command body)
    return f"run-shell -t {pane} {tokens[1]}"


def cmd_exec(selection: str, client_tty: str = "") -> int:
    """Execute the command of the selected entry if it can run detached.

    `selection` is the fzf line: path\tdisplay\ttable|key, or a bare
    table|key identity. `client_tty` is the tty of the client that opened
    the palette — passed through to interactive commands (command-prompt,
    confirm-before, display-menu, display-message) via -t so the prompt
    appears on the right client. The binding command is in tmux config
    syntax ({}, quotes, \\; separators) which the tmux CLI cannot parse from
    argv — it is run through `tmux source-file -`, the config parser.
    """
    try:
        identity = selection.rsplit("\t", 1)[-1]
    except (IndexError, ValueError):
        return 0
    try:
        table, key = identity.split("|", 1)
    except ValueError:
        return 0
    entries = build_full_entries()
    entry = next((e for e in entries if e.table == table and e.key == key), None)
    if entry is None or not can_exec_command(entry.command, have_client_tty=bool(client_tty)):
        return 0
    command = entry.command
    head = command.lstrip()
    # interactive commands accept -t target-client; inject our client tty so
    # the prompt/menu shows on the client that selected the entry
    if client_tty and head.startswith(CLIENT_TARGET_PREFIXES):
        command = inject_client_target(command, client_tty)
    # run-shell needs an explicit target pane, otherwise job output goes to
    # the CLI stdout; the pane env is set by the binding (adopt_client_pane)
    if head.startswith("run-shell"):
        command = inject_run_shell_target(
            command, os.environ.get("TMUX_COMMAND_PALETTE_PANE", "")
        )
    # interactive commands and run-shell scripts may block until the user
    # answers (tpm prompts) or run long; launch them in the background so
    # the palette exits and the popup closes
    if head.startswith(INTERACTIVE_PREFIXES) or head.startswith("run-shell"):
        proc = subprocess.Popen(
            ["tmux", "source-file", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            text=True,
        )
        if proc.stdin is None:
            print("palette: cannot run tmux: no stdin", file=sys.stderr)
            return 1
        try:
            proc.stdin.write(command + "\n")
            proc.stdin.close()
        except OSError as error:
            print(f"palette: cannot run tmux: {error}", file=sys.stderr)
            return 1
        return 0
    try:
        result = subprocess.run(
            ["tmux", "source-file", "-"],
            input=command + "\n",
            capture_output=True,
            text=True,
        )
    except OSError as error:
        print(f"palette: cannot run tmux: {error}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        return 1
    return 0
