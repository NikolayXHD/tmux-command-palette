#!/usr/bin/env bash

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# The palette key is an option, @command-palette-key:
#   unset           -> prefix + ? (default, replaces the native help)
#   set, e.g. C-S-P -> global key without any prefix (Ctrl+Shift+P style)
key="$(tmux show-option -gv @command-palette-key 2>/dev/null)"
if [ -z "$key" ]; then
	table="prefix"
	key="?"
else
	table="root"
fi

# run-shell -b runs in the background so prefix mode exits; display-popup
# needs a tty and -E closes the popup when the palette exits. #{client_tty}
# is expanded by tmux when the binding runs: the popup and the
# TMUX_COMMAND_PALETTE_TTY env var both target the client that pressed the key.
palette_cmd='tmux display-popup -c #{client_tty} -w 70% -h 50% -E "TMUX_COMMAND_PALETTE_TTY=#{client_tty} TMUX_COMMAND_PALETTE_PANE=#{pane_id} python3 '"$CURRENT_DIR"'/palette.py" || true'

tmux bind-key -T "$table" "$key" run-shell -b "$palette_cmd"
