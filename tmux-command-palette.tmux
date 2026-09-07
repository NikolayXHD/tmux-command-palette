#!/usr/bin/env bash

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Register the launch as a named command (once per server). The alias
# value is expanded when a command is parsed, so a bind of
# tmux-command-palette stores run-shell -b "tmux display-popup ...":
# run-shell expands #{...} in -b when the key is pressed, while
# display-popup does not expand -c/-E in 3.7c. -c and
# TMUX_COMMAND_PALETTE_TTY target the client that pressed the key.
# set -a appends (a plain set would wipe the whole array; a fixed index
# is a global slot another plugin may take); the guard keeps reloads from
# stacking duplicate entries.
if ! tmux show-options -s 2>/dev/null | grep -q '^command-alias\[[0-9]*\] "tmux-command-palette='; then
  tmux set -a -s command-alias 'tmux-command-palette=run-shell -b "tmux display-popup -c \"#{client_tty}\" -w 70% -h 50% -E \"TMUX_COMMAND_PALETTE_TTY=#{client_tty} TMUX_COMMAND_PALETTE_PANE=#{pane_id} python3 '"$CURRENT_DIR"'/palette.py\" || true"'
fi

# Placeholder binds: a hotkey line written above the tpm loader parses
# before the alias exists, so it must read `bind -n K run-shell
# tmux-command-palette` (run-shell is known, the line binds, the placeholder
# command itself never runs). Now that the alias is registered, rebind the
# same keys to the real command (bind-key overwrites the placeholder in
# place):
tmux list-keys 2>/dev/null | grep ' run-shell tmux-command-palette$' \
  | while read -r _ _ table key _; do
      tmux bind-key -T "$table" "$key" tmux-command-palette
    done
