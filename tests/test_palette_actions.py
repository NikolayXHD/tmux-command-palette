import unittest

from palette_actions import inject_client_target, inject_run_shell_target


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


class InjectRunShellTargetTest(unittest.TestCase):
    def test_when_run_shell_then_target_injected(self):
        self.assertEqual(
            inject_run_shell_target("run-shell /x/update.sh", "%3"),
            "run-shell -t %3 /x/update.sh",
        )

    def test_when_run_shell_with_flags_then_target_injected(self):
        self.assertEqual(
            inject_run_shell_target("run-shell -b /x/y.sh", "%3"),
            "run-shell -t %3 -b /x/y.sh",
        )

    def test_when_target_already_present_then_unchanged(self):
        self.assertEqual(
            inject_run_shell_target("run-shell -t %1 /x/y.sh", "%3"),
            "run-shell -t %1 /x/y.sh",
        )

    def test_when_not_run_shell_then_unchanged(self):
        self.assertEqual(inject_run_shell_target("kill-window", "%3"), "kill-window")

    def test_when_no_pane_then_unchanged(self):
        self.assertEqual(inject_run_shell_target("run-shell /x/y.sh", ""), "run-shell /x/y.sh")


if __name__ == "__main__":
    unittest.main()


class QuoteAwareTargetTest(unittest.TestCase):
    def test_when_target_inside_quotes_then_still_injected(self):
        command = 'confirm-before -p "sure?" run-shell "tmux kill-pane -t {pane_id}"'
        self.assertEqual(
            inject_client_target(command, "/dev/pts/3"),
            'confirm-before -t /dev/pts/3 -p "sure?" run-shell "tmux kill-pane -t {pane_id}"',
        )

    def test_when_run_shell_target_inside_quotes_then_still_injected(self):
        command = 'run-shell "tmux list-windows -t $T"'
        self.assertEqual(
            inject_run_shell_target(command, "%3"),
            'run-shell -t %3 "tmux list-windows -t $T"',
        )

    def test_when_unquoted_target_present_then_unchanged(self):
        self.assertEqual(
            inject_client_target("command-prompt -t /dev/pts/1 -p x", "/dev/pts/3"),
            "command-prompt -t /dev/pts/1 -p x",
        )


class ExecIdentityTest(unittest.TestCase):
    def test_when_identity_is_last_field_then_parsed(self):
        # literal tab inside the display field must not break identity lookup
        line = "C-b x\tdisplay\twith\ttab\tprefix|x"
        self.assertEqual(line.rsplit("\t", 1)[-1], "prefix|x")

    def test_when_bare_identity_then_parsed(self):
        self.assertEqual("prefix|x".rsplit("\t", 1)[-1], "prefix|x")
