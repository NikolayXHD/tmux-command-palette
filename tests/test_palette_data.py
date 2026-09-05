import unittest

from palette_data import (
    Binding,
    Glossary,
    can_exec_command,
    non_stock_bindings,
    sync_entries,
    source_file_command,
    toml_value,
)

KILL_JARGON = {
    "kill": {
        "default": ("close", "remove", "delete"),
        "session": ("close", "terminate", "exit", "quit"),
    }
}
NO_BASE = Glossary(jargon=KILL_JARGON, forms={})
WITH_BASE = Glossary(
    jargon=KILL_JARGON, forms={"kill-session": "terminate current session"}
)


class CanExecTest(unittest.TestCase):
    def test_when_plain_command_then_executable(self):
        for command in (
            "kill-window",
            "next-window",
            "new-window -c x",
            "run-shell ls",
            "run-shell -b ls",
        ):
            with self.subTest(command=command):
                self.assertTrue(can_exec_command(command))

    def test_when_command_chain_then_executable(self):
        self.assertTrue(can_exec_command("kill-window \\; display-message x"))

    def test_when_mode_or_conditional_command_then_not_executable(self):
        for command in ("send-keys -X page-down", "if-shell true a b"):
            with self.subTest(command=command):
                self.assertFalse(can_exec_command(command))

    def test_when_interactive_without_client_tty_then_not_executable(self):
        for command in (
            "command-prompt -p x",
            "confirm-before -p y kill-pane",
            "display-menu -T t",
        ):
            with self.subTest(command=command):
                self.assertFalse(can_exec_command(command))

    def test_when_interactive_with_client_tty_then_executable(self):
        for command in (
            "command-prompt -p x",
            "confirm-before -p y kill-pane",
            "display-menu -T t",
        ):
            with self.subTest(command=command):
                self.assertTrue(can_exec_command(command, have_client_tty=True))


class SourceFileCommandTest(unittest.TestCase):
    def test_when_chain_separator_then_bare_semicolon(self):
        self.assertEqual(
            source_file_command("swap-window -t :-1 \\; previous-window"),
            "swap-window -t :-1 ; previous-window",
        )

    def test_when_bare_separator_then_unchanged(self):
        self.assertEqual(source_file_command("kill-window ; next-window"),
                         "kill-window ; next-window")

    def test_when_semicolon_in_quotes_then_unchanged(self):
        self.assertEqual(
            source_file_command('display-menu "a ; b" ; kill-window'),
            'display-menu "a ; b" ; kill-window',
        )

    def test_when_quoted_command_then_quotes_preserved(self):
        self.assertEqual(
            source_file_command(
                'command-prompt -F -I "#W" ; run-shell "echo a ; b"'
            ),
            'command-prompt -F -I "#W" ; run-shell "echo a ; b"',
        )

    def test_when_single_quotes_then_chain_outside_only(self):
        self.assertEqual(
            source_file_command("run-shell 'a ; b' \\; next-window"),
            "run-shell 'a ; b' ; next-window",
        )

    def test_when_quoted_chain_marker_then_preserved(self):
        # a literal backslash-semicolon inside a quoted argument is data, not
        # a separator: quoted text is never touched
        self.assertEqual(
            source_file_command('run-shell "a \\; b"'),
            'run-shell "a \\; b"',
        )

    def test_when_chain_after_quoted_arg_then_separator_converted(self):
        self.assertEqual(
            source_file_command('display-message "x" \\; next-window'),
            'display-message "x" ; next-window',
        )


class NonStockBindingsTest(unittest.TestCase):
    def make_binding(self, table, key, command):
        return Binding(table=table, key=key, command=command, note="")

    def test_when_matches_stock_then_excluded(self):
        live = [self.make_binding("prefix", "n", "next-window")]
        stock = [self.make_binding("prefix", "n", "next-window")]
        self.assertEqual(non_stock_bindings(live, stock, {"prefix"}), [])

    def test_when_absent_from_stock_then_included(self):
        live = [self.make_binding("prefix", "Q", "kill-session")]
        stock = []
        self.assertEqual(non_stock_bindings(live, stock, {"prefix"}), live)

    def test_when_command_differs_from_stock_then_included(self):
        live = [self.make_binding("prefix", "n", "next-window -c x")]
        stock = [self.make_binding("prefix", "n", "next-window")]
        self.assertEqual(non_stock_bindings(live, stock, {"prefix"}), live)

    def test_when_table_not_visible_then_excluded(self):
        live = [self.make_binding("root", "C-S-P", "run-shell x")]
        self.assertEqual(non_stock_bindings(live, [], {"prefix"}), [])

    def test_when_command_covered_by_shared_then_excluded(self):
        live = [self.make_binding("prefix", "Q", "kill-session")]
        self.assertEqual(
            non_stock_bindings(live, [], {"prefix"}, {("prefix", "kill-session")}),
            [],
        )


class SyncEntriesTest(unittest.TestCase):
    def test_when_new_binding_with_form_then_appended_with_alias(self):
        entries = {}
        diff = {("prefix", "Q"): "kill-session"}
        changed, appended = sync_entries(entries, diff, WITH_BASE)
        self.assertTrue(changed)
        self.assertEqual(appended, 1)
        self.assertEqual(
            entries[("prefix", "Q")],
            {"command": "kill-session", "alias": "terminate current session, close, exit, quit", "alias_was": ""},
        )

    def test_when_new_binding_without_form_then_synonyms_only(self):
        entries = {}
        diff = {("prefix", "Q"): "kill-session"}
        changed, appended = sync_entries(entries, diff, NO_BASE)
        self.assertTrue(changed)
        self.assertEqual(entries[("prefix", "Q")]["alias"], "close, terminate, exit, quit")

    def test_when_no_changes_then_idempotent(self):
        entries = {
            ("prefix", "Q"): {
                "command": "kill-session",
                "alias": "close",
                "alias_was": "",
            }
        }
        diff = {("prefix", "Q"): "kill-session"}
        changed, appended = sync_entries(entries, diff, NO_BASE)
        self.assertFalse(changed)
        self.assertEqual(appended, 0)
        self.assertEqual(entries[("prefix", "Q")]["alias"], "close")

    def test_when_command_changed_then_alias_regenerated_and_kept(self):
        entries = {
            ("prefix", "Q"): {
                "command": "kill-session",
                "alias": "close session",
                "alias_was": "",
            }
        }
        sync_entries(entries, {("prefix", "Q"): "kill-server"}, WITH_BASE)
        self.assertEqual(entries[("prefix", "Q")]["command"], "kill-server")
        self.assertEqual(entries[("prefix", "Q")]["alias"], "close, remove, delete")
        self.assertEqual(entries[("prefix", "Q")]["alias_was"], "close session")

    def test_when_command_changed_with_empty_alias_then_alias_was_stays_empty(self):
        entries = {
            ("prefix", "Q"): {"command": "kill-session", "alias": "", "alias_was": ""}
        }
        sync_entries(entries, {("prefix", "Q"): "kill-server"}, NO_BASE)
        self.assertEqual(entries[("prefix", "Q")]["command"], "kill-server")
        self.assertEqual(entries[("prefix", "Q")]["alias"], "close, remove, delete")
        self.assertEqual(entries[("prefix", "Q")]["alias_was"], "")

    def test_when_filled_alias_and_command_unchanged_then_left_alone(self):
        entries = {
            ("prefix", "Q"): {
                "command": "kill-session",
                "alias": "close",
                "alias_was": "",
            }
        }
        sync_entries(entries, {("prefix", "Q"): "kill-session"}, NO_BASE)
        self.assertEqual(entries[("prefix", "Q")]["alias"], "close")


class TomlValueTest(unittest.TestCase):
    def test_when_plain_then_quoted(self):
        self.assertEqual(toml_value("abc"), '"abc"')

    def test_when_quotes_and_backslashes_then_escaped(self):
        self.assertEqual(toml_value('say "hi" \\ done'), '"say \\"hi\\" \\\\ done"')


if __name__ == "__main__":
    unittest.main()
