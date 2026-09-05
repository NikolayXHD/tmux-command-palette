"""tmux data layer: bindings, alias files, entry building.

No UI and no command execution here — pure tmux state and file merging.
"""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Data files live at the plugin root, one level above this module's dir.
PLUGIN_ROOT = Path(__file__).parent.parent
PALETTE_TOML = PLUGIN_ROOT / "palette.toml"
PALETTE_GENERATED_TOML = PLUGIN_ROOT / "palette.generated.toml"

PERSONAL_FILENAME = "tmux-command-palette.toml"

PERSONAL_HEADER = """\
# tmux-command-palette.toml — personal aliases for your non-stock bindings.
# Auto-maintained on every palette run; filled-in aliases are never touched:
#   - new bindings (absent from stock tmux, or rebound) are appended with a
#     starting alias: human full form from glossary.toml plus the glossary
#     synonyms of the jargon terms in the command
#     (e.g. kill-pane -> "close pane, remove, delete");
#   - when the command of a binding changes, alias is regenerated and the
#     previous value is kept in alias_was;
#   - replace the generated alias with your own wording any time; an empty
#     alias suppresses the shared palette.toml entry for that key.
"""


class TmuxError(RuntimeError):
    """tmux command failed."""


def run_tmux(args: list[str]) -> str:
    proc = subprocess.run(["tmux", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise TmuxError(proc.stderr.strip() or f"tmux {' '.join(args)} failed")
    return proc.stdout


@functools.lru_cache(maxsize=1)
def personal_toml_path() -> Path:
    """Personal alias file: next to the user's tmux.conf, not the plugin.

    The personal file is user config: it lives next to the user's tmux.conf,
    not in the plugin directory that tpm manages. The config location comes
    from tmux #{config_files} (last existing non-system config). Falls back
    next to this script when tmux is unreachable or only system configs
    exist. TMUX_COMMAND_PALETTE_FILE overrides everything (used by tests
    and unusual setups).
    """
    env_file = os.environ.get("TMUX_COMMAND_PALETTE_FILE")
    if env_file:
        return Path(os.path.expanduser(env_file))
    try:
        out = run_tmux(["display-message", "-p", "#{config_files}"]).strip()
    except TmuxError:
        out = ""
    for name in reversed([p for p in out.split(",") if p.strip()]):
        config = Path(os.path.expanduser(name.strip()))
        if config.exists() and not str(config).startswith(("/etc/", "/usr/")):
            return config.parent / PERSONAL_FILENAME
    return PLUGIN_ROOT / PERSONAL_FILENAME


@dataclass(frozen=True)
class Binding:
    table: str
    key: str
    command: str
    note: str


def list_bindings(socket: list[str] | None = None) -> list[Binding]:
    prefix_args = socket or []
    fmt = "#{key_table}\t#{key_string}\t#{key_command}\t#{key_note}"
    out = run_tmux([*prefix_args, "list-keys", "-a", "-F", fmt])
    return [Binding(*line.split("\t", 3)) for line in out.splitlines()]


def stock_bindings() -> list[Binding]:
    """Default bindings of this tmux version (fresh server, no config)."""
    socket = ["-L", f"palette-stock-{os.getpid()}"]
    try:
        run_tmux([*socket, "-f", "/dev/null", "new-session", "-d", "-s", "stock"])
        return list_bindings(socket)
    finally:
        subprocess.run(
            ["tmux", *socket, "kill-server"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def entry_points(bindings: list[Binding] | None = None) -> dict[str, str]:
    """Map mode table -> prefix key that enters it.

    copy-mode is entered by any command starting with 'copy-mode'
    (mode-keys decides emacs/vi); custom tables by 'switch-client -T <table>'.
    """
    if bindings is None:
        bindings = list_bindings()
    prefix_bindings = [b for b in bindings if b.table == "prefix"]
    points: dict[str, str] = {}
    switch_re = re.compile(r"switch-client\s+(?:\S+\s+)*-T\s+(\S+)")
    for binding in prefix_bindings:
        command = binding.command
        if command.startswith("copy-mode"):
            mode_keys = run_tmux(["show-options", "-gv", "mode-keys"]).strip()
            table = "copy-mode" if mode_keys == "emacs" else "copy-mode-vi"
            points.setdefault(table, binding.key)
        else:
            match = switch_re.search(command)
            if match and match.group(1) != "root":
                points.setdefault(match.group(1), binding.key)
    return points


def visible_tables(bindings: list[Binding]) -> set[str]:
    """Tables the palette shows: prefix, the active copy-mode, reachable modes."""
    tables = {"prefix"}
    mode_keys = run_tmux(["show-options", "-gv", "mode-keys"]).strip()
    tables.add("copy-mode" if mode_keys == "emacs" else "copy-mode-vi")
    tables.update(entry_points(bindings))
    return tables


def non_stock_bindings(
    live: list[Binding],
    stock: list[Binding],
    tables: set[str],
    covered: set[tuple[str, str]] = frozenset(),
) -> list[Binding]:
    """Live bindings that differ from every expectation we know.

    Expected commands come from the stock defaults (per key) and from
    palette.toml aliases keyed by (table, command): a live binding whose
    command is covered by either source is known, not personal.
    """
    stock_map = {(b.table, b.key): b.command for b in stock}
    return [
        b
        for b in live
        if b.table in tables
        and (
            (b.table, b.key) not in stock_map
            or stock_map[(b.table, b.key)] != b.command
        )
        and (b.table, b.command) not in covered
    ]


def read_toml_entries(path: Path) -> list[dict]:
    with path.open("rb") as f:
        return tomllib.load(f).get("entry", [])


def shared_aliases() -> dict[tuple[str, str], str]:
    """Shared dictionary from palette.toml: (table, command) -> alias.

    An alias describes an action, so it is keyed by the exact command that
    performs it — every live binding with that command gets the alias.
    """
    if not PALETTE_TOML.exists():
        return {}
    result: dict[tuple[str, str], str] = {}
    for entry in read_toml_entries(PALETTE_TOML):
        missing = [f for f in ("table", "command") if not entry.get(f)]
        if missing:
            raise TmuxError(
                f"{PALETTE_TOML.name}: entry without {', '.join(missing)}: {entry!r}"
            )
        result[(entry["table"], entry["command"])] = entry.get("alias", "")
    return result


@dataclass(frozen=True)
class Glossary:
    """glossary.toml data: jargon -> context groups; command -> human full form."""

    jargon: dict[str, dict[str, tuple[str, ...]]]
    forms: dict[str, str]


GLOSSARY_TOML = PLUGIN_ROOT / "glossary.toml"


def load_glossary(path: Path | None = None) -> Glossary:
    """Strict load of glossary.toml — a broken file fails the run (fail early)."""
    p = path or GLOSSARY_TOML
    if not p.exists():
        raise TmuxError(f"{p.name}: not found")
    try:
        with p.open("rb") as f:
            raw = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as error:
        raise TmuxError(f"{p.name}: invalid TOML: {error}") from error
    jargon: dict[str, dict[str, tuple[str, ...]]] = {}
    for entry in raw.get("jargon", []):
        word = entry.get("word", "")
        if not isinstance(word, str) or not word:
            raise TmuxError(f"{p.name}: jargon entry without word: {entry!r}")
        raw_groups = {k: v for k, v in entry.items() if k != "word"}
        if not raw_groups.get("default"):
            raise TmuxError(f"{p.name}: jargon {word!r} without default group")
        for name, group in raw_groups.items():
            if not isinstance(group, list) or not group or not all(
                isinstance(item, str) and item for item in group
            ):
                raise TmuxError(
                    f"{p.name}: jargon {word!r}: group {name!r} must be a non-empty list of words"
                )
        if word in jargon:
            raise TmuxError(f"{p.name}: duplicate jargon word {word!r}")
        jargon[word] = {name: tuple(group) for name, group in raw_groups.items()}
    forms: dict[str, str] = {}
    for entry in raw.get("phrase", []):
        command = entry.get("command", "")
        phrase = entry.get("phrase", "")
        if not command or not phrase:
            raise TmuxError(f"{p.name}: phrase entry without command/phrase: {entry!r}")
        if command in forms:
            raise TmuxError(f"{p.name}: duplicate phrase command {command!r}")
        forms[command] = phrase
    return Glossary(jargon=jargon, forms=forms)


def personal_entries() -> dict[tuple[str, str], dict]:
    """Personal file: (table, key) -> {command, alias, alias_was}."""
    path = personal_toml_path()
    if not path.exists():
        return {}
    try:
        entries = read_toml_entries(path)
    except tomllib.TOMLDecodeError as error:
        raise TmuxError(
            f"{path}: invalid TOML: {error} — fix or remove the file"
        ) from error
    result = {}
    for entry in entries:
        missing = [f for f in ("table", "key") if not entry.get(f)]
        if missing:
            raise TmuxError(
                f"{path}: entry without {', '.join(missing)}: {entry!r} — fix or remove the file"
            )
        result[(entry["table"], entry["key"])] = {
            "command": entry.get("command", ""),
            "alias": entry.get("alias", ""),
            "alias_was": entry.get("alias_was", ""),
        }
    return result


def resolve_alias(
    shared: dict[tuple[str, str], str],
    personal: dict[tuple[str, str], dict],
    table: str,
    key: str,
    command: str,
) -> str:
    """Alias for a live binding: personal (per key) wins over shared.

    An empty personal alias suppresses the shared one — the user rebinds the
    key and does not want the stock action description on it. Without a
    personal record the shared alias for (table, command) applies to every
    binding performing that command.
    """
    rec = personal.get((table, key))
    if rec is not None:
        return rec["alias"]
    return shared.get((table, command), "")


def toml_value(value: str) -> str:
    # JSON strings are valid TOML basic strings and escape \n, \t, control
    # characters and quotes correctly.
    return json.dumps(value)


# tmux jargon -> synonym groups live in glossary.toml (data, not code):
# each found jargon word contributes its whole flat group (context resolved
# by words in the command) to the generated alias and to --check coverage.


def _bare_command(command: str) -> str:
    """Command without quoted strings and format variables (#{...})."""
    return re.sub(r""""[^"]*"|'[^']*'|#\{[^}]*\}""", "", command)


def _word_in(text: str, word: str) -> bool:
    """Case-sensitive whole-word containment (word boundary)."""
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _resolve_group(contexts: dict[str, tuple[str, ...]], bare: str) -> tuple[str, ...]:
    """Group for a jargon hit: first declared context present in the command, else default."""
    for context, group in contexts.items():
        if context != "default" and re.search(rf"\b{context}\b", bare):
            return group
    return contexts["default"]


def glossary_matches(
    bare: str, jargon: dict[str, dict[str, tuple[str, ...]]]
) -> list[tuple[str, tuple[str, ...]]]:
    """(jargon, group) pairs found in the bare command, in key position order.

    Single matcher shared by alias generation and --check coverage.
    """
    hits: list[tuple[int, str, tuple[str, ...]]] = []
    for word, contexts in jargon.items():
        match = re.search(rf"\b{re.escape(word)}\b", bare)
        if match:
            hits.append((match.start(), word, _resolve_group(contexts, bare)))
    return [(word, group) for _, word, group in sorted(hits)]


def generate_alias(command: str, glossary: Glossary) -> str:
    """Starting alias for a personal entry: form plus synonyms.

    Form — the command's entry in glossary.toml [[phrase]] (human full form,
    e.g. "terminate current session"); synonyms — the group words of the
    jargon terms found in the bare command, minus the words the form or the
    command already carry. The parts are independent: form without terms
    yields the form alone; terms without a form yield the synonyms alone.
    Returns "" when there is neither.
    """
    bare = _bare_command(command)
    matches = glossary_matches(bare, glossary.jargon)
    form = glossary.forms.get(command, "")
    remaining: list[str] = []
    for _, group in matches:
        for word in group:
            if word not in remaining and not _word_in(form, word) and not _word_in(bare, word):
                remaining.append(word)
    parts = [part for part in (form, ", ".join(remaining)) if part]
    return ", ".join(parts)


def missing_group_words(command: str, alias: str, glossary: Glossary) -> list[str]:
    """Group words the command requires but the alias lacks (--check).

    Menu commands (display-menu) enumerate item commands in their arguments;
    the alias describes the menu, not the items, so the rule does not apply.
    """
    if command.lstrip().startswith("display-menu"):
        return []
    bare = _bare_command(command)
    missing: list[str] = []
    for _, group in glossary_matches(bare, glossary.jargon):
        for word in group:
            if word not in missing and not _word_in(alias, word):
                missing.append(word)
    return missing


def write_personal(entries: list[tuple[tuple[str, str], dict]]) -> None:
    path = personal_toml_path()
    out = [PERSONAL_HEADER, ""]
    for (table, key), rec in entries:
        lines = ["[[entry]]"]
        lines += [
            f"    table = {toml_value(table)}",
            f"    key = {toml_value(key)}",
            f"    command = {toml_value(rec['command'])}",
            f"    alias = {toml_value(rec['alias'])}",
        ]
        if rec.get("alias_was"):
            lines.append(f"    alias_was = {toml_value(rec['alias_was'])}")
        out.append("\n".join(lines))
    try:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text("\n".join(out) + "\n")
        os.replace(tmp, path)
    except OSError as error:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise TmuxError(f"cannot write {path}: {error}") from error


def sync_entries(
    entries: dict[tuple[str, str], dict],
    diff_map: dict[tuple[str, str], str],
    glossary: Glossary,
) -> tuple[bool, int]:
    """Apply the live non-stock diff to the personal entries in place.

    Returns (changed, appended): new bindings are added with a starting
    alias (form + jargon synonyms); when the command of a known binding
    changed, alias is regenerated (the old value is kept in alias_was);
    filled-in aliases of unchanged bindings are left alone.
    """
    changed = False
    appended = 0
    for key_id, command in diff_map.items():
        rec = entries.get(key_id)
        if rec is None:
            alias = generate_alias(command, glossary)
            entries[key_id] = {
                "command": command,
                "alias": alias,
                "alias_was": "",
            }
            changed = True
            appended += 1
        elif rec["command"] != command:
            rec["command"] = command
            if rec["alias"]:
                rec["alias_was"] = rec["alias"]
            rec["alias"] = generate_alias(command, glossary)
            changed = True
    return changed, appended


def sync_personal_file() -> str:
    """Bring the personal file in line with the current non-stock bindings.

    Appends new bindings (starting alias), regenerates the alias of rebound
    bindings (keeping the old value in alias_was), never touches filled-in
    aliases.
    Returns a human-readable summary.
    """
    live = list_bindings()
    tables = visible_tables(live)
    covered = set(shared_aliases())
    diff = non_stock_bindings(live, stock_bindings(), tables, covered)
    # the plugin's own binding opens the palette again — it is not a user
    # binding, keep it out of the personal file
    diff = [
        b
        for b in diff
        if "palette.py" not in b.command and "tmux-command-palette" not in b.command
    ]
    diff_map = {(b.table, b.key): b.command for b in diff}
    entries = personal_entries()
    changed, appended = sync_entries(entries, diff_map, load_glossary())
    # drop auto-created leftovers of bindings that went back to stock; keep
    # anything carrying a user alias or history
    stale = [k for k in list(entries) if k not in diff_map]
    for key_id in stale:
        rec = entries[key_id]
        if not rec["alias"] and not rec["alias_was"]:
            del entries[key_id]
            changed = True
    stale = [k for k in entries if k not in diff_map]

    if changed:
        ordered = sorted(entries.items(), key=lambda kv: (kv[0][0], kv[0][1]))
        write_personal(ordered)

    summary = (
        f"non-stock bindings: {len(diff_map)}, "
        f"personal aliases filled: {sum(1 for r in entries.values() if r['alias'])}"
    )
    if appended:
        summary += f", appended: {appended}"
    if stale:
        summary += f", stale (unused): {len(stale)}"
    return summary


def prefix_key() -> str:
    return run_tmux(["show-options", "-gv", "prefix"]).strip()


# commands that cannot run detached: send-keys needs a mode context,
# if-shell is a conditional wrapper. command-prompt/confirm-before and
# display-menu are interactive but addressable: the executor injects
# -t <client-tty> so the prompt/menu opens on the right client. run-shell
# runs a script; the executor gives it -t <pane> (inject_run_shell_target)
# so its output lands in the pane that opened the palette, and nested tmux
# calls inherit that pane via TMUX_PANE set by the server on the job.
INTERACTIVE_PREFIXES = (
    "command-prompt",
    "confirm-before",
    "display-menu",
)
# shows a message on a client: needs the palette client injected via -t
CLIENT_PREFIXES = (*INTERACTIVE_PREFIXES, "display-message")
NON_EXEC_PREFIXES = (
    "send-keys",
    "if-shell",
)


def source_file_command(command: str) -> str:
    """Command-string syntax -> tmux config line for `source-file`.

    Chain separators: a command string uses \\; (or a bare ;), the config
    parser treats \\; as an escaped semicolon argument — only a bare ;
    splits commands. Rewrite unquoted \\; to ;, leave quoted text and
    already-bare separators alone.
    """
    out: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
        elif ch in '"\'':
            quote = ch
            out.append(ch)
        elif ch == "\\" and command[i : i + 2] == "\\;":
            out.append(";")
            i += 1
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def can_exec_command(command: str, have_client_tty: bool = False) -> bool:
    """Whether the binding command runs detached, without client or mode.

    Chains (\\;) are fine: the executor runs the command through
    `tmux source-file -`, the config parser, exactly as the keyboard runs it.
    """
    head = command.lstrip()
    if head.startswith(NON_EXEC_PREFIXES):
        return False
    if head.startswith(CLIENT_PREFIXES):
        # interactive is fine when the executor can target the opening client
        return have_client_tty
    return True


@dataclass(frozen=True)
class FullEntry:
    table: str
    key: str
    command: str
    note: str
    alias: str
    path: str
    can_exec: bool


def build_full_entries(client_tty: str = "") -> list[FullEntry]:
    """Live bindings + merged aliases -> complete entries."""
    bindings = list_bindings()
    prefixes = entry_points(bindings)
    shared = shared_aliases()
    personal = personal_entries()
    prefix = prefix_key()
    entries: list[FullEntry] = []

    for binding in bindings:
        table = binding.table
        if table == "root":
            continue  # root bindings (mouse, global keys) are out of scope
        if table == "prefix":
            path = f"{prefix} {binding.key}"
        elif table in prefixes:
            path = f"{prefix} {prefixes[table]} {binding.key}"
        else:
            continue  # unreachable mode table (e.g. copy-mode-vi with emacs)
        entries.append(
            FullEntry(
                table=table,
                key=binding.key,
                command=binding.command,
                note=binding.note,
                alias=resolve_alias(
                    shared, personal, table, binding.key, binding.command
                ),
                path=path,
                can_exec=can_exec_command(
                    binding.command, have_client_tty=bool(client_tty)
                ),
            )
        )
    return entries


def write_full_toml(entries: list[FullEntry]) -> None:
    """Write the generated artifact (one entry per live binding)."""
    out = [
        "# generated by palette.py from live tmux state + merged aliases",
        'description = "tmux command palette (full)"',
        'version = "1"',
        "",
    ]
    for entry in sorted(entries, key=lambda e: (e.table, e.key)):
        out.append(
            f"[[entry]]\n"
            f"    table = {toml_value(entry.table)}\n"
            f"    key = {toml_value(entry.key)}\n"
            f"    command = {toml_value(entry.command)}\n"
            f"    note = {toml_value(entry.note)}\n"
            f"    alias = {toml_value(entry.alias)}\n"
            f"    path = {toml_value(entry.path)}\n"
            f"    can_exec = {str(entry.can_exec).lower()}"
        )
    try:
        PALETTE_GENERATED_TOML.write_text("\n".join(out) + "\n")
    except OSError as error:
        raise TmuxError(f"cannot write {PALETTE_GENERATED_TOML}: {error}") from error
