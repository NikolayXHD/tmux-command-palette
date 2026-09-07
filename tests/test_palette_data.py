import unittest

from palette_data import Binding, can_exec_command, non_stock_bindings, sync_entries, toml_value


class CanExecTest(unittest.TestCase):
    def test_when_plain_command_then_executable(self):
        for command in ("kill-window", "next-window", "new-window -c x"):
            with self.subTest(command=command):
                self.assertTrue(can_exec_command(command))

    def test_when_command_chain_then_not_executable(self):
        self.assertFalse(can_exec_command("kill-window \\; display-message x"))

    def test_when_background_or_mode_command_then_not_executable(self):
        for command in ("send-keys -X page-down", "run-shell -b ls", "if-shell true a b"):
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


class SyncEntriesTest(unittest.TestCase):
    def test_when_new_binding_then_appended_with_empty_alias(self):
        entries = {}
        diff = {("prefix", "Q"): "kill-session"}
        changed, appended = sync_entries(entries, diff)
        self.assertTrue(changed)
        self.assertEqual(appended, 1)
        self.assertEqual(entries[("prefix", "Q")], {"command": "kill-session", "alias": "", "alias_was": ""})

    def test_when_no_changes_then_idempotent(self):
        entries = {("prefix", "Q"): {"command": "kill-session", "alias": "close", "alias_was": ""}}
        diff = {("prefix", "Q"): "kill-session"}
        changed, appended = sync_entries(entries, diff)
        self.assertFalse(changed)
        self.assertEqual(appended, 0)
        self.assertEqual(entries[("prefix", "Q")]["alias"], "close")

    def test_when_command_changed_with_filled_alias_then_alias_reset_and_kept(self):
        entries = {("prefix", "Q"): {"command": "kill-session", "alias": "close session", "alias_was": ""}}
        sync_entries(entries, {("prefix", "Q"): "kill-server"})
        self.assertEqual(entries[("prefix", "Q")]["command"], "kill-server")
        self.assertEqual(entries[("prefix", "Q")]["alias"], "")
        self.assertEqual(entries[("prefix", "Q")]["alias_was"], "close session")

    def test_when_command_changed_with_empty_alias_then_only_command_updates(self):
        entries = {("prefix", "Q"): {"command": "kill-session", "alias": "", "alias_was": ""}}
        sync_entries(entries, {("prefix", "Q"): "kill-server"})
        self.assertEqual(entries[("prefix", "Q")]["command"], "kill-server")
        self.assertEqual(entries[("prefix", "Q")]["alias_was"], "")

    def test_when_filled_alias_and_command_unchanged_then_left_alone(self):
        entries = {("prefix", "Q"): {"command": "kill-session", "alias": "close", "alias_was": ""}}
        sync_entries(entries, {("prefix", "Q"): "kill-session"})
        self.assertEqual(entries[("prefix", "Q")]["alias"], "close")


class TomlValueTest(unittest.TestCase):
    def test_when_plain_then_quoted(self):
        self.assertEqual(toml_value("abc"), '"abc"')

    def test_when_quotes_and_backslashes_then_escaped(self):
        self.assertEqual(toml_value('say "hi" \\ done'), '"say \\"hi\\" \\\\ done"')


if __name__ == "__main__":
    unittest.main()
