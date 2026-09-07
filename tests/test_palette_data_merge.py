import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from palette_data import merged_aliases


class MergedAliasesTest(unittest.TestCase):
    def write(self, directory, name, text):
        path = Path(directory) / name
        path.write_text(text)
        return path

    def test_when_personal_alias_filled_then_overrides_shared(self):
        with TemporaryDirectory() as td:
            shared = self.write(
                td,
                "palette.toml",
                '[[entry]]\n    table = "prefix"\n    key = "c"\n    alias = "new tab"\n',
            )
            personal = self.write(
                td,
                "personal.toml",
                '[[entry]]\n    table = "prefix"\n    key = "c"\n    command = "foo"\n    alias = "custom"\n',
            )
            with patch("palette_data.PALETTE_TOML", shared), patch("palette_data.PERSONAL_TOML", personal):
                merged = merged_aliases()
            self.assertEqual(merged[("prefix", "c")], "custom")

    def test_when_personal_alias_empty_then_suppresses_shared(self):
        with TemporaryDirectory() as td:
            shared = self.write(
                td,
                "palette.toml",
                '[[entry]]\n    table = "prefix"\n    key = "n"\n    alias = "next tab"\n',
            )
            personal = self.write(
                td,
                "personal.toml",
                '[[entry]]\n    table = "prefix"\n    key = "n"\n    command = "foo"\n    alias = ""\n',
            )
            with patch("palette_data.PALETTE_TOML", shared), patch("palette_data.PERSONAL_TOML", personal):
                merged = merged_aliases()
            self.assertEqual(merged[("prefix", "n")], "")

    def test_when_no_personal_file_then_shared_used(self):
        with TemporaryDirectory() as td:
            shared = self.write(
                td,
                "palette.toml",
                '[[entry]]\n    table = "prefix"\n    key = "n"\n    alias = "next tab"\n',
            )
            with patch("palette_data.PALETTE_TOML", shared), patch("palette_data.PERSONAL_TOML", Path(td) / "absent.toml"):
                merged = merged_aliases()
            self.assertEqual(merged[("prefix", "n")], "next tab")


if __name__ == "__main__":
    unittest.main()
