import re
import unittest

from palette_data import FullEntry
from palette_history import HistoryItem
from palette_ui import (
    EXEC_MARK,
    NOEXEC_MARK,
    RECENT_MARK,
    build_lines,
    history_entry,
    mark_path,
    render_display,
)


def make_entry(**overrides):
    fields = {
        "table": "prefix",
        "key": "x",
        "command": "kill-pane",
        "note": "",
        "alias": "",
        "path": "C-b x",
        "can_exec": True,
    }
    fields.update(overrides)
    return FullEntry(**fields)


class MarkPathTest(unittest.TestCase):
    def test_when_executable_then_exec_mark(self):
        self.assertTrue(mark_path("C-b x", True).startswith(EXEC_MARK))

    def test_when_not_executable_then_noexec_mark(self):
        self.assertTrue(mark_path("C-b x", False).startswith(NOEXEC_MARK))


class RenderDisplayTest(unittest.TestCase):
    def strip_ansi(self, text):
        import re

        return re.sub(r"\x1b\[[0-9;]*m", "", text)

    def test_when_note_and_alias_then_both_shown(self):
        rendered = render_display(
            make_entry(note="Kill the active pane", alias="close pane, kill")
        )
        text = self.strip_ansi(rendered)
        self.assertIn("Kill the active pane", text)
        self.assertIn("close pane, kill", text)
        self.assertIn("kill-pane", text)

    def test_when_note_only_then_note_and_command(self):
        text = self.strip_ansi(render_display(make_entry(note="Close pane")))
        self.assertIn("Close pane", text)
        self.assertIn("kill-pane", text)

    def test_when_alias_only_then_alias_and_command(self):
        text = self.strip_ansi(render_display(make_entry(alias="close pane")))
        self.assertIn("close pane", text)
        self.assertIn("kill-pane", text)

    def test_when_bare_then_command_only(self):
        text = self.strip_ansi(render_display(make_entry()))
        self.assertIn("kill-pane", text)
        self.assertNotIn("C-b", text)


class BuildLinesTest(unittest.TestCase):
    def test_when_entry_then_three_tab_fields_with_identity(self):
        entry = make_entry(table="prefix", key="x")
        line = build_lines([entry])[0]
        path_field, _, identity = line.split("\t")
        self.assertTrue(path_field.startswith(EXEC_MARK))
        self.assertEqual(identity, "prefix|x")


class HistoryEntryTest(unittest.TestCase):
    def fields(self, command, entry=None):
        line = build_lines([history_entry(HistoryItem(command, 1000, 2000), entry)])[0]
        self.assertEqual(len(line.split("\t")), 3)
        return line.split("\t")

    def test_when_history_item_then_identity_carries_escaped_command(self):
        _, _, identity = self.fields("for x in y\necho $x\nend")

        self.assertEqual(identity, "hist|for x in y\\necho $x\\nend")

    def test_when_no_live_entry_then_marker_and_command_only(self):
        path_field, display, _ = self.fields("kill-pane")

        self.assertEqual(path_field, RECENT_MARK)
        self.assertEqual(re.sub(r"\x1b\[[0-9;]*m", "", display), "kill-pane")

    def test_when_live_entry_then_row_differs_only_by_marker(self):
        entry = make_entry(
            table="prefix",
            key="K",
            command="kill-pane",
            alias="close pane",
            path="C-b K",
        )
        entry_line = build_lines([entry])[0].split("\t")

        path_field, display, _ = self.fields("kill-pane", entry)

        self.assertEqual(path_field, entry_line[0].replace(EXEC_MARK, RECENT_MARK))
        self.assertEqual(display, entry_line[1])

    def test_when_multiline_command_then_display_is_one_flat_line(self):
        _, display, _ = self.fields("for x in y\necho $x\nend")

        flat = re.sub(r"\x1b\[[0-9;]*m", "", display)
        self.assertEqual(flat, "for x in y echo $x end")


if __name__ == "__main__":
    unittest.main()
