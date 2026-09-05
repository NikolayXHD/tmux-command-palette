import tempfile
import unittest
from pathlib import Path

import palette_data
from palette_data import (
    Glossary,
    TmuxError,
    _bare_command,
    _word_in,
    generate_alias,
    glossary_matches,
    load_glossary,
    missing_group_words,
)

# mirrors glossary.toml
JARGON = {
    "window": {"default": ("tab",)},
    "kill": {
        "default": ("close", "remove", "delete"),
        "session": ("close", "terminate", "exit", "quit"),
    },
    "buffer": {"default": ("clipboard",)},
    "swap": {"default": ("exchange", "move")},
}
DATA = Glossary(
    jargon=JARGON,
    forms={
        "kill-session": "terminate current session",
        "kill-window": "close tab",
        "kill-pane": "close pane",
        "swap-window -t :-1": "move tab left",
    },
)


class GlossaryMatchesTest(unittest.TestCase):
    def test_when_kill_session_then_session_group(self):
        self.assertEqual(
            glossary_matches(_bare_command("kill-session"), JARGON),
            [("kill", ("close", "terminate", "exit", "quit"))],
        )

    def test_when_kill_window_then_default_kill_group_and_window_group(self):
        self.assertEqual(
            glossary_matches(_bare_command("kill-window"), JARGON),
            [
                ("kill", ("close", "remove", "delete")),
                ("window", ("tab",)),
            ],
        )

    def test_when_no_jargon_then_no_matches(self):
        self.assertEqual(
            glossary_matches(_bare_command("resize-pane -L 8"), JARGON), []
        )

    def test_when_quoted_and_format_words_then_ignored(self):
        self.assertEqual(
            glossary_matches(
                _bare_command('confirm-before -p "kill-pane #P?" kill-pane'), JARGON
            ),
            [("kill", ("close", "remove", "delete"))],
        )


class GenerateAliasTest(unittest.TestCase):
    def test_when_form_then_form_plus_remaining_group_words(self):
        self.assertEqual(
            generate_alias("kill-session", DATA),
            "terminate current session, close, exit, quit",
        )

    def test_when_form_uses_group_word_then_word_not_repeated(self):
        self.assertEqual(
            generate_alias("kill-window", DATA), "close tab, remove, delete"
        )

    def test_when_command_word_in_group_then_not_listed(self):
        # "swap" is a jargon key present in the command — never a synonym
        self.assertEqual(
            generate_alias("swap-window -t :-1", DATA), "move tab left, exchange"
        )

    def test_when_no_form_then_synonyms_only(self):
        self.assertEqual(
            generate_alias("kill-window", Glossary(JARGON, {})),
            "close, remove, delete, tab",
        )

    def test_when_form_without_terms_then_form_only(self):
        self.assertEqual(
            generate_alias("resize-pane -L 8", Glossary(JARGON, {"resize-pane -L 8": "resize pane left"})),
            "resize pane left",
        )

    def test_when_no_form_and_no_jargon_then_empty(self):
        self.assertEqual(generate_alias("resize-pane -L 8", DATA), "")

    def test_when_multiple_jargon_words_then_groups_in_command_order(self):
        # swap (position 0) before window (position 5)
        self.assertEqual(
            generate_alias("swap-window", Glossary(JARGON, {})),
            "exchange, move, tab",
        )

    def test_when_substring_only_then_word_not_suppressed(self):
        # word boundary: "tabbed" does not contain the word "tab"
        no_forms = Glossary(JARGON, {"kill-window": "close tabbed window view"})
        self.assertEqual(
            generate_alias("kill-window", no_forms),
            "close tabbed window view, remove, delete, tab",
        )


class MissingGroupWordsTest(unittest.TestCase):
    def test_when_alias_complete_then_no_missing(self):
        self.assertEqual(
            missing_group_words("kill-pane", "close pane, remove, delete", DATA),
            [],
        )

    def test_when_words_missing_then_each_reported_in_group_order(self):
        self.assertEqual(
            missing_group_words("kill-session", "terminate current session", DATA),
            ["close", "exit", "quit"],
        )

    def test_when_command_is_menu_then_no_check(self):
        self.assertEqual(
            missing_group_words(
                "display-menu -T t { kill-pane } { swap-window }", "pane menu", DATA
            ),
            [],
        )

    def test_when_substring_only_then_not_counted(self):
        self.assertEqual(
            missing_group_words("kill-window", "tabulated", DATA),
            ["close", "remove", "delete", "tab"],
        )

    def test_when_context_word_in_command_then_session_group_required(self):
        self.assertEqual(
            missing_group_words(
                "kill-session", "close session, exit, quit, terminate", DATA
            ),
            [],
        )


class WordInTest(unittest.TestCase):
    def test_when_word_boundary_match_then_true(self):
        self.assertTrue(_word_in("close pane", "pane"))

    def test_when_only_substring_then_false(self):
        self.assertFalse(_word_in("tabulated", "tab"))


class LoadGlossaryTest(unittest.TestCase):
    def write_toml(self, content: str) -> Path:
        tmp = Path(tempfile.mkdtemp())
        path = tmp / "glossary.toml"
        path.write_text(content)
        return path

    def test_when_valid_then_jargon_and_phrase(self):
        path = self.write_toml(
            '[[jargon]]\n    word = "kill"\n    default = ["close"]\n'
            '[[phrase]]\n    command = "kill-pane"\n    phrase = "close pane"\n'
        )
        data = load_glossary(path)
        self.assertEqual(data.jargon, {"kill": {"default": ("close",)}})
        self.assertEqual(data.forms, {"kill-pane": "close pane"})

    def test_when_missing_file_then_fail_early(self):
        with self.assertRaises(TmuxError):
            load_glossary(Path("/nonexistent/glossary.toml"))

    def test_when_broken_toml_then_fail_early(self):
        path = self.write_toml("[[jargon]]\n    word = " )
        with self.assertRaises(TmuxError):
            load_glossary(path)

    def test_when_jargon_without_default_then_fail_early(self):
        path = self.write_toml('[[jargon]]\n    word = "kill"\n    session = ["close"]\n')
        with self.assertRaises(TmuxError):
            load_glossary(path)

    def test_when_duplicate_phrase_command_then_fail_early(self):
        path = self.write_toml(
            '[[phrase]]\n    command = "kill-pane"\n    phrase = "a"\n'
            '[[phrase]]\n    command = "kill-pane"\n    phrase = "b"\n'
        )
        with self.assertRaises(TmuxError):
            load_glossary(path)

    def test_when_real_file_then_loads(self):
        # the shipped glossary.toml is valid data
        data = load_glossary()
        self.assertIn("kill", data.jargon)
        self.assertIn("kill-session", data.forms)

    def test_when_duplicate_jargon_word_then_fail_early(self):
        path = self.write_toml(
            '[[jargon]]\n    word = "kill"\n    default = ["close"]\n'
            '[[jargon]]\n    word = "kill"\n    default = ["close"]\n'
        )
        with self.assertRaises(TmuxError):
            load_glossary(path)

    def test_when_group_not_a_list_then_fail_early(self):
        path = self.write_toml('[[jargon]]\n    word = "kill"\n    default = "close"\n')
        with self.assertRaises(TmuxError):
            load_glossary(path)

    def test_when_empty_group_then_fail_early(self):
        path = self.write_toml(
            '[[jargon]]\n    word = "kill"\n    default = ["close"]\n    session = []\n'
        )
        with self.assertRaises(TmuxError):
            load_glossary(path)

    def test_when_jargon_entry_without_word_then_fail_early(self):
        path = self.write_toml('[[jargon]]\n    default = ["close"]\n')
        with self.assertRaises(TmuxError):
            load_glossary(path)


if __name__ == "__main__":
    unittest.main()
