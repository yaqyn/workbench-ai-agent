import io
import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path

from main import main
from terminal_ui import TerminalUI, clean


class TerminalTests(unittest.TestCase):
    def test_model_output_cannot_clear_screen_or_set_terminal_title(self):
        self.assertEqual(clean('\x1b[2Jhello\x1b]0;title\x07\nworld'),
                         '[2Jhello]0;title\nworld')

    def test_no_color_disables_interactive_rendering(self):
        with patch.dict(os.environ, {'NO_COLOR': ''}), patch('terminal_ui.interactive_terminal', return_value=True):
            self.assertTrue(TerminalUI().plain)

    def test_plain_choice_retries_invalid_selection(self):
        ui = TerminalUI(plain=True)
        with patch('builtins.input', side_effect=['bad', '3', '2']), patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertFalse(ui.choose('Access', [(True, 'Inspect'), (False, 'Edit')], True))
        self.assertIn('Enter one of the numbers', output.getvalue())
        self.assertNotIn('\x1b', output.getvalue())

    def test_setup_retries_missing_directory_and_defaults_to_read_only(self):
        args = SimpleNamespace(theme='light', spacing='compact', workspace=Path.cwd(), model='test', user_prompt=None)
        with patch('builtins.input', side_effect=['', '', '/does-not-exist', str(Path.cwd()), '', 'Inspect']), patch('sys.stdout', new_callable=io.StringIO):
            TerminalUI(plain=True).setup(args)
        self.assertTrue(args.read_only)
        self.assertEqual(args.user_prompt, 'Inspect')
        self.assertEqual(args.theme, 'light')

    def test_preview_never_opens_provider(self):
        with patch('main.OpenAI') as client, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(main(['--preview', '--plain']), 0)
        client.assert_not_called()
        self.assertIn('offline preview', output.getvalue())
        self.assertNotIn('\x1b', output.getvalue())

    def test_cancel_does_not_open_provider(self):
        with patch('terminal_ui.TerminalUI.setup', side_effect=KeyboardInterrupt), patch('main.OpenAI') as client, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(main(['--plain']), 130)
        client.assert_not_called()
