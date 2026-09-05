import unittest

from palette_actions import inject_client_target, inject_run_shell_target


class InjectClientTargetTest(unittest.TestCase):
    def test_when_interactive_command_then_target_injected_after_name(self):
        command = inject_client_target(
            "command-prompt -p x { kill-window }", "/dev/pts/3"
        )
        self.assertEqual(command, "command-prompt -t /dev/pts/3 -p x { kill-window }")

    def test_when_confirm_before_then_target_injected(self):
        command = inject_client_target("confirm-before -p y kill-pane", "/dev/pts/3")
        self.assertEqual(command, "confirm-before -t /dev/pts/3 -p y kill-pane")

    def test_when_target_already_present_then_not_duplicated(self):
        command = inject_client_target("display-menu -t /dev/pts/1 -T t", "/dev/pts/3")
        self.assertEqual(command, "display-menu -t /dev/pts/1 -T t")

    def test_when_empty_command_then_unchanged(self):
        self.assertEqual(inject_client_target("", "/dev/pts/3"), "")

    def test_when_target_after_quoted_arg_then_not_duplicated(self):
        command = inject_client_target(
            'command-prompt -p "x" -t /dev/pts/1', "/dev/pts/3"
        )
        self.assertEqual(command, 'command-prompt -p "x" -t /dev/pts/1')

    def test_when_target_inside_menu_items_then_injected(self):
        command = inject_client_target(
            'display-menu -T t x { copy-mode -t = ; send-keys -X -t = search }',
            "/dev/pts/3",
        )
        self.assertEqual(
            command,
            'display-menu -t /dev/pts/3 -T t x { copy-mode -t = ; send-keys -X -t = search }',
        )


class InjectRunShellTargetTest(unittest.TestCase):
    def test_when_run_shell_then_target_injected(self):
        command = inject_run_shell_target(
            'run-shell -b "echo a"', "%5"
        )
        self.assertEqual(command, 'run-shell -t %5 -b "echo a"')

    def test_when_target_present_then_not_duplicated(self):
        command = inject_run_shell_target("run-shell -t %3 ls", "%5")
        self.assertEqual(command, "run-shell -t %3 ls")

    def test_when_not_run_shell_then_unchanged(self):
        self.assertEqual(inject_run_shell_target("ls", "%5"), "ls")

    def test_when_no_pane_then_unchanged(self):
        self.assertEqual(inject_run_shell_target("run-shell ls", ""), "run-shell ls")


if __name__ == "__main__":
    unittest.main()
