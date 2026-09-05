import unittest

from palette_data import resolve_alias


class ResolveAliasTest(unittest.TestCase):
    def test_when_personal_alias_filled_then_overrides_shared(self):
        shared = {("prefix", "new-window"): "new tab"}
        personal = {
            ("prefix", "c"): {
                "command": "new-window",
                "alias": "custom",
                "alias_was": "",
            }
        }
        self.assertEqual(
            resolve_alias(shared, personal, "prefix", "c", "new-window"), "custom"
        )

    def test_when_personal_alias_empty_then_suppresses_shared(self):
        shared = {("prefix", "new-window"): "new tab"}
        personal = {
            ("prefix", "c"): {"command": "new-window", "alias": "", "alias_was": ""}
        }
        self.assertEqual(
            resolve_alias(shared, personal, "prefix", "c", "new-window"), ""
        )

    def test_when_no_personal_record_then_shared_applies(self):
        shared = {("prefix", "new-window"): "new tab"}
        self.assertEqual(
            resolve_alias(shared, {}, "prefix", "n", "new-window"), "new tab"
        )

    def test_when_shared_missing_then_empty(self):
        self.assertEqual(resolve_alias({}, {}, "prefix", "n", "new-window"), "")


if __name__ == "__main__":
    unittest.main()
