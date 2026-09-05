import unittest

from palette_data import Binding, can_exec_command, dynamic_alias, non_stock_bindings, sync_entries, toml_value


class CanExecTest(unittest.TestCase):
    def test_when_plain_command_then_executable(self):
        for command in ("kill-window", "next-window", "new-window -c x"):
            with self.subTest(command=command):
                self.assertTrue(can_exec_command(command))

    def test_when_command_chain_then_not_executable(self):
        self.assertFalse(can_exec_command("kill-window \\; display-message x"))

    def test_when_mode_or_conditional_command_then_not_executable(self):
        for command in ("send-keys -X page-down", "if-shell true a b"):
            with self.subTest(command=command):
                self.assertFalse(can_exec_command(command))

    def test_when_run_shell_then_executable(self):
        self.assertTrue(can_exec_command("run-shell -b ls"))

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
            "display-message hi",
        ):
            with self.subTest(command=command):
                self.assertTrue(can_exec_command(command, have_client_tty=True))

    def test_when_display_message_without_tty_then_not_executable(self):
        self.assertFalse(can_exec_command("display-message hi"))


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

    def test_when_covered_by_dictionary_command_then_excluded(self):
        live = [self.make_binding("prefix", "Q", "run-shell /x/tpm/bindings/install_plugins")]
        covered = {("prefix", "run-shell /x/tpm/bindings/install_plugins")}
        self.assertEqual(non_stock_bindings(live, [], {"prefix"}, covered), [])

    def test_when_covered_command_differs_then_included(self):
        live = [self.make_binding("prefix", "Q", "run-shell /custom/path")]
        covered = {("prefix", "run-shell /x/tpm/bindings/install_plugins")}
        self.assertEqual(non_stock_bindings(live, [], {"prefix"}, covered), live)

    def test_when_same_command_on_other_key_covered_then_excluded(self):
        # dictionary is keyed by command, not by key
        live = [self.make_binding("prefix", "Q", "run-shell /x/tpm/bindings/install_plugins")]
        covered = {("prefix", "run-shell /x/tpm/bindings/install_plugins")}
        self.assertEqual(non_stock_bindings(live, [], {"prefix"}, covered), [])


class SyncEntriesTest(unittest.TestCase):
    def test_when_new_binding_then_appended_with_glossary_alias(self):
        entries = {}
        diff = {("prefix", "Q"): "kill-session"}
        changed, appended = sync_entries(entries, diff)
        self.assertTrue(changed)
        self.assertEqual(appended, 1)
        self.assertEqual(entries[("prefix", "Q")], {"command": "kill-session", "alias": "close", "alias_was": ""})

    def test_when_new_binding_without_glossary_terms_then_alias_empty(self):
        entries = {}
        sync_entries(entries, {("prefix", "Q"): "resize-pane -L 2"})
        self.assertEqual(entries[("prefix", "Q")]["alias"], "")

    def test_when_no_changes_then_idempotent(self):
        entries = {("prefix", "Q"): {"command": "kill-session", "alias": "close", "alias_was": ""}}
        diff = {("prefix", "Q"): "kill-session"}
        changed, appended = sync_entries(entries, diff)
        self.assertFalse(changed)
        self.assertEqual(appended, 0)
        self.assertEqual(entries[("prefix", "Q")]["alias"], "close")

    def test_when_command_changed_with_filled_alias_then_alias_regenerated_and_kept(self):
        entries = {("prefix", "Q"): {"command": "kill-session", "alias": "close session", "alias_was": ""}}
        sync_entries(entries, {("prefix", "Q"): "kill-server"})
        self.assertEqual(entries[("prefix", "Q")]["command"], "kill-server")
        self.assertEqual(entries[("prefix", "Q")]["alias"], "close")
        self.assertEqual(entries[("prefix", "Q")]["alias_was"], "close session")

    def test_when_command_changed_without_glossary_terms_then_alias_empty(self):
        entries = {("prefix", "Q"): {"command": "kill-session", "alias": "close", "alias_was": ""}}
        sync_entries(entries, {("prefix", "Q"): "resize-pane -L 2"})
        self.assertEqual(entries[("prefix", "Q")]["alias"], "")
        self.assertEqual(entries[("prefix", "Q")]["alias_was"], "close")

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


class TomlValueControlTest(unittest.TestCase):
    def test_when_newline_and_tab_then_valid_toml_escaping(self):
        import tomllib

        encoded = toml_value("line1\nline2\tend")
        decoded = tomllib.loads("alias = " + encoded)
        self.assertEqual(decoded["alias"], "line1\nline2\tend")

    def test_when_quotes_and_backslashes_then_escaped(self):
        import tomllib

        encoded = toml_value('say "hi" \\ done')
        self.assertEqual(tomllib.loads("alias = " + encoded)["alias"], 'say "hi" \\ done')

class DynamicAliasTest(unittest.TestCase):
    def test_when_window_jargon_then_tab(self):
        self.assertEqual(dynamic_alias('new-window -c "#{pane_current_path}"'), "tab")

    def test_when_kill_and_window_then_close_tab_in_command_order(self):
        self.assertEqual(dynamic_alias("kill-window"), "close tab")

    def test_when_kill_pane_then_close(self):
        self.assertEqual(dynamic_alias("kill-pane"), "close")

    def test_when_buffer_jargon_then_clipboard(self):
        self.assertEqual(dynamic_alias("delete-buffer -b x"), "clipboard")

    def test_when_jargon_in_quotes_or_format_variable_then_ignored(self):
        self.assertEqual(dynamic_alias('display-message -p "#{window_name}"'), "")
        self.assertEqual(dynamic_alias('confirm-before -p "kill pane?" kill-pane'), "close")

    def test_when_no_jargon_then_empty(self):
        self.assertEqual(dynamic_alias("resize-pane -L 2"), "")
