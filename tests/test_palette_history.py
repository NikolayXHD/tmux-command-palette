import tempfile
import unittest
from pathlib import Path

from palette_history import (
    escape_history_value,
    history_items,
    record_execution,
    unescape_history_value,
)

ESCAPE_VARIANTS = [
    ("kill-pane", "kill-pane"),
    ("printf 'a\\\\b'", "printf 'a\\\\\\\\b'"),
    ("for x in y\necho $x\nend", "for x in y\\necho $x\\nend"),
    ("printf \\\\n", "printf \\\\\\\\n"),
    ("a\\\\\nb", "a\\\\\\\\\\nb"),
]


class EscapeHistoryValueTest(unittest.TestCase):
    def test_when_value_escaped_then_round_trips(self):
        for command, escaped in ESCAPE_VARIANTS:
            with self.subTest(command=command):
                self.assertEqual(escape_history_value(command), escaped)
                self.assertEqual(unescape_history_value(escaped), command)

    def test_when_unknown_escape_then_kept_verbatim(self):
        self.assertEqual(unescape_history_value("a\\tb"), "a\\tb")


class HistoryItemsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.history_file = Path(self._tmp.name) / "history"

    def test_when_file_missing_then_no_items(self):
        self.assertEqual(history_items(self.history_file), [])

    def test_when_execution_recorded_then_item_read_back(self):
        record_execution("for x in y\necho $x\nend", path=self.history_file, when=1000)
        record_execution("printf 'a\\b'", path=self.history_file, when=2000)

        items = history_items(self.history_file)

        self.assertEqual(
            [(item.command, item.last_added) for item in items],
            [("printf 'a\\b'", 2000), ("for x in y\necho $x\nend", 1000)],
        )

    def test_when_command_executed_twice_then_merged_into_one_item(self):
        record_execution("kill-pane", path=self.history_file, when=1000)
        record_execution("kill-pane", path=self.history_file, when=2000)

        items = history_items(self.history_file)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].command, "kill-pane")
        self.assertEqual(items[0].first_added, 1000)
        self.assertEqual(items[0].last_added, 2000)

    def test_when_records_in_same_second_then_later_record_first(self):
        self.history_file.write_text(
            "- cmd: older\n  when: 1000\n"
            "- cmd: newer\n  when: 1000\n"
            "- cmd: newest\n  when: 1000\n"
        )

        items = history_items(self.history_file)

        self.assertEqual([item.command for item in items], ["newest", "newer", "older"])

    def test_when_added_when_recorded_then_first_added_taken_from_it(self):
        self.history_file.write_text(
            "- cmd: rm -r .venv\n  when: 2000\n  added_when: 500\n"
        )

        items = history_items(self.history_file)

        self.assertEqual(items[0].first_added, 500)
        self.assertEqual(items[0].last_added, 2000)

    def test_when_fish_paths_block_then_ignored(self):
        self.history_file.write_text(
            "- cmd: cd .pi/agent\n  when: 1000\n  paths:\n    - .pi/agent\n"
            "- cmd: pi\n  when: 2000\n"
        )

        items = history_items(self.history_file)

        self.assertEqual([item.command for item in items], ["pi", "cd .pi/agent"])

    def test_when_unknown_key_then_record_kept(self):
        self.history_file.write_text("- cmd: pi\n  custom: x\n  when: 1000\n")

        items = history_items(self.history_file)

        self.assertEqual([(item.command, item.last_added) for item in items], [("pi", 1000)])

    def test_when_broken_interior_line_then_record_ends(self):
        self.history_file.write_text(
            "- cmd: pi\nbroken line\n  when: 1000\n"
            "- cmd: ls\n  when: 2000\n"
        )

        items = history_items(self.history_file)

        self.assertEqual([item.command for item in items], ["ls", "pi"])
        self.assertEqual(items[1].last_added, 0)

    def test_when_empty_command_then_skipped(self):
        self.history_file.write_text("- cmd:\n  when: 1000\n")

        self.assertEqual(history_items(self.history_file), [])


class RecordExecutionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.history_file = Path(self._tmp.name) / "history"

    def test_when_first_execution_then_cmd_and_when_written(self):
        record_execution("kill-pane", path=self.history_file, when=1000)

        self.assertEqual(
            self.history_file.read_text(), "- cmd: kill-pane\n  when: 1000\n"
        )

    def test_when_command_reexecuted_then_one_record_updated(self):
        record_execution("kill-pane", path=self.history_file, when=1000)

        record_execution("kill-pane", path=self.history_file, when=2000)

        self.assertEqual(
            self.history_file.read_text(),
            "- cmd: kill-pane\n  when: 2000\n  added_when: 1000\n",
        )

    def test_when_new_command_then_file_rewritten_newest_first(self):
        record_execution("kill-pane", path=self.history_file, when=1000)

        record_execution("next-layout", path=self.history_file, when=2000)

        self.assertEqual(
            self.history_file.read_text(),
            "- cmd: next-layout\n  when: 2000\n"
            "- cmd: kill-pane\n  when: 1000\n",
        )

    def test_when_stale_tmp_left_by_killed_process_then_removed(self):
        stale = self.history_file.with_name(self.history_file.name + ".999.tmp")
        stale.write_text("")

        record_execution("kill-pane", path=self.history_file, when=1000)

        self.assertFalse(stale.exists())
        self.assertEqual(
            self.history_file.read_text(), "- cmd: kill-pane\n  when: 1000\n"
        )

    def test_when_multiline_command_then_one_cmd_line_written(self):
        record_execution("for x in y\necho $x\nend", path=self.history_file, when=1000)

        self.assertEqual(
            self.history_file.read_text(),
            "- cmd: for x in y\\necho $x\\nend\n  when: 1000\n",
        )


if __name__ == "__main__":
    unittest.main()
