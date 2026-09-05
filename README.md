# Tmux command palette

Command palette for tmux, in the spirit of VS Code and other GUI software.

- Searchable menu to run commands
- Shows hotkeys to teach the faster way.

Trigger the palette via hotkey, type what you want — "new tab", "move pane",
hit `Enter` to execute.

By default, palette is bound to `Prefix + ?`.

![Screenshot](screenshot.png)

## Installation

Requirements

- tmux 3.7+
- Systemwide python 3.11+
- [fzf](https://github.com/junegunn/fzf)
- [tpm](https://github.com/tmux-plugins/tpm)

Add to `~/.tmux.conf`:

```tmux
set -g @plugin 'NikolayXHD/tmux-command-palette'
```

In tmux press `Prefix + I` to install the plugin.

## Bind a to different hotkey

To open the palette with **Ctrl + Shift + P**, similar to vscode, add this to
`~/.tmux.conf` before the plugin line:

```tmux
set -g @command-palette-key C-S-P
```

Make sure your terminal + tmux combo support passing `Ctrl + Shift` to
applications.

## Development

Entry point: `palette.py`. The personal alias file is kept up to date
automatically on every palette run; the flags run that step or the checks
standalone:

- `--gen` — update `tmux-command-palette.toml`: search aliases for your custom
  bindings
- `--check` — check `palette.toml` is complete and current for this tmux
  version (every built-in command described, no stale entries)
- `--exec table|key` — run one entry's command (for testing)

Customizing aliases: edit `tmux-command-palette.toml` next to your
`tmux.conf` (e.g. `~/.config/tmux/tmux-command-palette.toml`).

Run tests: `make test`

`palette_data.py` — tmux bindings layer.

`palette_actions.py` — execution of a selected entry.

`palette_ui.py` — `fzf` UI and line rendering.

`palette.toml` — common search aliases, manually maintained in this repo.

`palette.generated.toml` — comprehensive source to build `fzf` input.

`tmux-command-palette.tmux` — plugin entry point: binds the palette trigger
key.

## AI disclosure

This plugin was vibecoded with [Pi](https://github.com/earendil-works/pi) and
deepseek-v4-flash model.
