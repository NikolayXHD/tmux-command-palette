import unittest

from palette_actions import inject_client_target


class InjectClientTargetTest(unittest.TestCase):
    def test_when_interactive_command_then_target_injected_after_name(self):
        command = inject_client_target("command-prompt -p x { kill-window }", "/dev/pts/3")
        self.assertEqual(command, "command-prompt -t /dev/pts/3 -p x { kill-window }")

    def test_when_confirm_before_then_target_injected(self):
        command = inject_client_target("confirm-before -p y kill-pane", "/dev/pts/3")
        self.assertEqual(command, "confirm-before -t /dev/pts/3 -p y kill-pane")

    def test_when_target_already_present_then_not_duplicated(self):
        command = inject_client_target("display-menu -t /dev/pts/1 -T t", "/dev/pts/3")
        self.assertEqual(command, "display-menu -t /dev/pts/1 -T t")

    def test_when_empty_command_then_unchanged(self):
        self.assertEqual(inject_client_target("", "/dev/pts/3"), "")


if __name__ == "__main__":
    unittest.main()
