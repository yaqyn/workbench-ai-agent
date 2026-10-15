import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.data_structures import Size

from main import run_agent, run_terminal_task
from tui import WorkbenchApp
from test_agent import response


def options(**kwargs):
    values = dict(theme='workbench', workspace=Path.cwd(), model='test', max_steps=3,
                  read_only=True, transcript=None, spacing='comfortable', user_prompt=None,
                  preview=False, verbose=False)
    return SimpleNamespace(**(values | kwargs))


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(.005)
    await asyncio.wait_for(wait(), 3)


class Screen(DummyOutput):
    def __init__(self, columns=80, rows=24):
        self.columns, self.rows = columns, rows
    def get_size(self):
        return Size(rows=self.rows, columns=self.columns)


@asynccontextmanager
async def running(runner=lambda *args: 'Done', **kwargs):
    with create_pipe_input() as keys, create_app_session(input=keys, output=Screen(**kwargs)):
        ui = WorkbenchApp(options(), runner)
        task = asyncio.create_task(ui.app.run_async())
        await until(lambda: ui.app.is_running)
        try:
            yield ui, keys
        finally:
            if not task.done():
                ui.app.exit(result=0)
            await asyncio.wait_for(task, 3)


class TUITests(unittest.IsolatedAsyncioTestCase):
    async def test_arrows_preview_and_enter_advances_without_space(self):
        async with running() as (ui, keys):
            keys.send_text('\x1bOQ')  # F2
            await until(lambda: ui.page == 'settings')
            keys.send_text('\x1b[B')
            await until(lambda: ui.theme == 'light')
            self.assertEqual(ui.appearance.value, 'light')
            keys.send_text('\r')
            await until(lambda: ui.app.layout.has_focus(ui.access.control))
            keys.send_text('\x1bOQ')
            await until(lambda: ui.page == 'workbench')
            self.assertEqual(ui.args.theme, 'light')
            self.assertTrue(ui.app.is_running)

    async def test_enter_runs_and_stays_in_tui_for_multiple_tasks(self):
        runner = Mock(return_value='Completed response')
        async with running(runner) as (ui, keys):
            keys.send_text('Inspect\r')
            await until(lambda: ui.answer == 'Completed response' and not ui.busy)
            self.assertIn('Final response:', ui.output.text)
            self.assertTrue(ui.app.is_running)
            self.assertEqual(runner.call_args.args[1], 'Inspect')
            keys.send_text('\x0eSecond task\r')  # Ctrl+N
            await until(lambda: runner.call_count == 2 and not ui.busy)
            self.assertIn('Inspect', ui.output.text)
            self.assertIn('Second task', ui.output.text)
            keys.send_text('\x1bp')
            await until(lambda: ui.prompt.text == 'Second task')
            keys.send_text('\x1bp')
            await until(lambda: ui.prompt.text == 'Inspect')

    async def test_enter_in_field_keeps_value_and_moves_focus(self):
        async with running() as (ui, keys):
            ui.show('settings', ui.model)
            ui.model.text = 'changed-model'
            keys.send_text('\r')
            await until(lambda: ui.app.layout.has_focus(ui.steps))
            self.assertEqual(ui.model.text, 'changed-model')

    async def test_busy_ui_responds_and_prevents_duplicate_run(self):
        release = threading.Event()
        started = threading.Event()
        calls = []
        def runner(args, prompt, event, stop):
            calls.append(args)
            started.set()
            release.wait(2)
            return 'Done'
        async with running(runner) as (ui, keys):
            try:
                keys.send_text('Task\r\r\r')
                await until(started.is_set)
                self.assertEqual(len(calls), 1)
                keys.send_text('\x1bOQ')
                await until(lambda: ui.page == 'settings')
                ui.access.index = 1
                ui.apply_settings()
                self.assertTrue(calls[0].read_only)  # in-flight permissions are immutable
                keys.send_text('\x03')
                await until(ui.stop.is_set)
                self.assertTrue(ui.app.is_running)
            finally:
                release.set()
            await until(lambda: not ui.busy)
            self.assertIn('Stopped', ui.status)

    async def test_failure_stays_in_app_and_can_retry(self):
        runner = Mock(side_effect=[RuntimeError('Provider unavailable'), 'Recovered'])
        async with running(runner) as (ui, keys):
            keys.send_text('Inspect\r')
            await until(lambda: 'Task failed' in ui.status)
            self.assertIn('Provider unavailable', ui.output.text)
            self.assertEqual(ui.prompt.text, 'Inspect')
            self.assertTrue(ui.app.is_running)
            keys.send_text('\r')
            await until(lambda: ui.answer == 'Recovered')

    async def test_invalid_settings_focus_field_and_do_not_start(self):
        runner = Mock()
        async with running(runner) as (ui, keys):
            ui.steps.text = 'zero'
            keys.send_text('Inspect\r')
            await until(lambda: ui.page == 'settings')
            self.assertTrue(ui.app.layout.has_focus(ui.steps))
            self.assertIn('positive whole number', ui.status)
            runner.assert_not_called()

    async def test_help_search_export_and_small_terminal(self):
        async with running(columns=48, rows=18) as (ui, keys):
            keys.send_text('Inspect\r')
            await until(lambda: ui.answer == 'Done')
            keys.send_text('\x1bOP')
            await until(lambda: ui.page == 'help')
            keys.send_text('\x1bOR\x06')  # F3, Ctrl+F
            await until(lambda: ui.app.layout.has_focus(ui.search))
            keys.send_text('Done\r')
            await until(lambda: ui.app.layout.has_focus(ui.output))
            with tempfile.TemporaryDirectory() as directory:
                ui.export.text = str(Path(directory) / 'result.txt')
                keys.send_text('\x13')
                await until(lambda: 'Exported' in ui.status)
                self.assertIn('Done', Path(ui.export.text).read_text())
            self.assertTrue(ui.app.is_running)

    async def test_progress_precedes_final_response_and_does_not_replace_done_status(self):
        def runner(args, prompt, event, stop):
            for i in range(10):
                event('Step', str(i))
            return 'Finished'
        async with running(runner) as (ui, keys):
            keys.send_text('Inspect\r')
            await until(lambda: ui.answer == 'Finished' and not ui.busy)
            await asyncio.sleep(.05)
            self.assertLess(ui.output.text.index('Step: 9'), ui.output.text.index('Final response:'))
            self.assertIn('Task complete', ui.status)

    async def test_directory_completion_is_available_and_selection_is_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'project'
            path.mkdir()
            async with running() as (ui, keys):
                ui.workspace.text = str(Path(directory) / 'pro')
                ui.workspace.buffer.cursor_position = len(ui.workspace.text)
                ui.show('settings', ui.workspace)
                keys.send_text('\x1b[B')
                await until(lambda: ui.workspace.buffer.complete_state is not None)
                keys.send_text('\x1b[B')
                await until(lambda: ui.workspace.text.rstrip('/') == str(path))
                keys.send_text('\r')
                await until(lambda: ui.app.layout.has_focus(ui.model))
                self.assertEqual(Path(ui.workspace.text), path)

    async def test_preview_uses_no_provider(self):
        async with running(run_terminal_task) as (ui, keys):
            ui.args.preview = True
            with patch('main.OpenAI') as provider:
                keys.send_text('Inspect\r')
                await until(lambda: bool(ui.answer))
            provider.assert_not_called()
            self.assertIn('stay in this screen', ui.answer)


class StopTests(unittest.TestCase):
    def test_stop_during_request_prevents_tool_dispatch(self):
        stopped = threading.Event()
        client = Mock()
        def reply(**kwargs):
            stopped.set()
            return response(calls=[{'id': 'call_1', 'type': 'function', 'function': {
                'name': 'write_file', 'arguments': '{"file_path":"new.txt","content":"x"}'}}])
        client.chat.completions.create.side_effect = reply
        with patch('main.call_function') as dispatch:
            with self.assertRaises(InterruptedError):
                run_agent(client, 'Task', should_stop=stopped.is_set)
        dispatch.assert_not_called()

    def test_stop_between_tools_prevents_next_tool(self):
        stopped = threading.Event()
        client = Mock()
        client.chat.completions.create.return_value = response(calls=[
            {'id': f'call_{i}', 'type': 'function', 'function': {
                'name': 'write_file', 'arguments': '{"file_path":"new.txt","content":"x"}'}}
            for i in range(2)])
        def dispatch(*args, **kwargs):
            stopped.set()
            return {'role': 'tool', 'tool_call_id': 'call_0', 'content': 'Done'}
        with patch('main.call_function', side_effect=dispatch) as tool:
            with self.assertRaises(InterruptedError):
                run_agent(client, 'Task', should_stop=stopped.is_set)
        self.assertEqual(tool.call_count, 1)
