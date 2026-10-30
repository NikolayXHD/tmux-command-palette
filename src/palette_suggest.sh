#!/usr/bin/env bash
# See README.md (Command history) — what the suggestion block shows.
#
# Suggestion rows for the palette: the history block on top (freshest
# matches first, capped at the block size), then palette entries by fzf
# relevance. An empty query shows suggestions only — no fallback to the
# entry list. fzf --filter matches exactly like the interactive finder
# over the displayed columns, so both blocks share one matching semantics.
#
# usage: palette_suggest.sh QUERY NUM_RECENT HISTORY_ROWS_FILE ENTRY_ROWS_FILE
set -u

query=$1
num_recent=$2
history_rows=$3
entry_rows=$4

fzf_args=(--ansi --delimiter=$'\t' --with-nth=1,2 --tiebreak=begin)

matches=$(fzf "${fzf_args[@]}" --no-sort --filter="$query" <"$history_rows") || true
if [ "$num_recent" -gt 0 ] && [ -n "$matches" ]; then
  printf '%s\n' "$matches" | head -n "$num_recent"
fi
# an empty query shows suggestions only: no fallback to the entry list
if [ -n "$query" ]; then
  fzf "${fzf_args[@]}" --filter="$query" <"$entry_rows" || true
fi
