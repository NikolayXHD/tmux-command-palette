import unittest

from palette_data import resolve_alias


def shared(alias, command="act"):
    return {("prefix", command): alias}


class ResolveAliasTest(unittest.TestCase):
    def test_when_personal_filled_then_overrides_shared(self):
        personal = {("prefix", "k"): {"command": "act", "alias": "custom", "alias_was": ""}}
        self.assertEqual(resolve_alias(shared("stock"), personal, "prefix", "k", "act"), "custom")

    def test_when_personal_empty_then_suppresses_shared(self):
        personal = {("prefix", "k"): {"command": "act", "alias": "", "alias_was": "stock"}}
        self.assertEqual(resolve_alias(shared("stock"), personal, "prefix", "k", "act"), "")

    def test_when_shared_command_matches_then_alias_shown(self):
        self.assertEqual(resolve_alias(shared("stock"), {}, "prefix", "k", "act"), "stock")

    def test_when_shared_has_no_entry_for_command_then_empty(self):
        self.assertEqual(resolve_alias(shared("stock"), {}, "prefix", "k", "other"), "")

    def test_when_shared_covers_other_key_same_command_then_alias_shown(self):
        # alias is keyed by command: any key performing it gets the alias
        self.assertEqual(resolve_alias(shared("stock"), {}, "prefix", "j", "act"), "stock")

    def test_when_personal_on_other_key_then_shared_still_applies(self):
        personal = {("prefix", "j"): {"command": "act", "alias": "", "alias_was": "stock"}}
        self.assertEqual(resolve_alias(shared("stock"), personal, "prefix", "k", "act"), "stock")


if __name__ == "__main__":
    unittest.main()
