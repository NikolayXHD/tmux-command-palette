import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SUGGEST_SCRIPT = Path(__file__).resolve().parent.parent / "src" / "palette_suggest.sh"

HISTORY_ROW_KILL = "↺\tkill-pane\thist|kill-pane"
HISTORY_ROW_NEW = "↺\tnew-window\thist|new-window"
HISTORY_ROW_SPLIT = "↺\tsplit-window\thist|split-window"
ENTRY_ROW_KILL = "▶ C-b K\tclose pane, remove, delete  kill-pane\tprefix|K"
ENTRY_ROW_NEW = "▶ C-b c\tnew tab, create  new-window\tprefix|c"


def run_suggest(query, num_recent, history_lines, entry_lines):
    """Run the suggestion pipeline over fixture rows, return output lines."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        history_rows = Path(tmp_dir) / "history_rows"
        entry_rows = Path(tmp_dir) / "entry_rows"
        history_rows.write_text("\n".join(history_lines) + "\n")
        entry_rows.write_text("\n".join(entry_lines) + "\n")
        result = subprocess.run(
            [
                "bash",
                str(SUGGEST_SCRIPT),
                query,
                str(num_recent),
                str(history_rows),
                str(entry_rows),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    return result.stdout.splitlines()


@unittest.skipUnless(shutil.which("fzf"), "fzf is required to run the suggestion pipeline")
class SuggestPipelineTest(unittest.TestCase):
    HISTORY_FRESHEST_FIRST = [HISTORY_ROW_SPLIT, HISTORY_ROW_NEW, HISTORY_ROW_KILL]

    def test_when_query_empty_then_only_recent_block_shown(self):
        lines = run_suggest(
            "",
            2,
            self.HISTORY_FRESHEST_FIRST,
            [ENTRY_ROW_KILL, ENTRY_ROW_NEW],
        )

        self.assertEqual(lines, [HISTORY_ROW_SPLIT, HISTORY_ROW_NEW])

    def test_when_query_empty_and_history_empty_then_empty_list(self):
        lines = run_suggest("", 3, [], [ENTRY_ROW_KILL, ENTRY_ROW_NEW])

        self.assertEqual(lines, [])

    def test_when_more_history_matches_then_block_capped_at_num_recent(self):
        lines = run_suggest(
            "wi",
            1,
            self.HISTORY_FRESHEST_FIRST,
            [ENTRY_ROW_KILL, ENTRY_ROW_NEW],
        )

        self.assertEqual(lines, [HISTORY_ROW_SPLIT, ENTRY_ROW_NEW])

    def test_when_query_matches_then_freshest_history_matches_first(self):
        lines = run_suggest(
            "wi",
            3,
            self.HISTORY_FRESHEST_FIRST,
            [ENTRY_ROW_KILL, ENTRY_ROW_NEW],
        )

        self.assertEqual(lines, [HISTORY_ROW_SPLIT, HISTORY_ROW_NEW, ENTRY_ROW_NEW])

    def test_when_no_history_match_then_entries_only(self):
        lines = run_suggest(
            "tab",
            3,
            self.HISTORY_FRESHEST_FIRST,
            [ENTRY_ROW_KILL, ENTRY_ROW_NEW],
        )

        self.assertEqual(lines, [ENTRY_ROW_NEW])

    def test_when_nothing_matches_then_empty(self):
        lines = run_suggest("zzz", 3, [HISTORY_ROW_KILL], [ENTRY_ROW_KILL])

        self.assertEqual(lines, [])


if __name__ == "__main__":
    unittest.main()
