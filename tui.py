"""Persistent Workbench terminal application, independent of the provider client."""
import asyncio
import copy
import os
import queue
import threading
from pathlib import Path

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, VSplit, Window, Layout, DynamicContainer, ConditionalContainer, FloatContainer, Float
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.scrollable_pane import ScrollablePane
from prompt_toolkit.styles import DynamicStyle, Style
from prompt_toolkit.widgets import Button, Frame, Label, TextArea, SearchToolbar

from terminal_ui import PALETTES, clean


class Choice:
    """One selection state: arrows commit immediately; Enter advances focus."""
    def __init__(self, values, value, changed=lambda value: None):
        self.values = values
        self.index = next(i for i, (v, _) in enumerate(values) if v == value)
        self.changed = changed
        self.advance = None
        keys = KeyBindings()
        for key, delta in [('up', -1), ('left', -1), ('down', 1), ('right', 1)]:
            keys.add(key)(lambda event, delta=delta: self.move(delta, event.app))
        @keys.add('enter')
        def advance(event):
            self.advance() if self.advance else event.app.layout.focus_next()
        @keys.add(' ')
        def space(event):
            self.move(1, event.app)
        self.control = FormattedTextControl(self.fragments, focusable=True, key_bindings=keys)
        self.window = Window(self.control, height=len(values), style='class:field')

    @property
    def value(self):
        return self.values[self.index][0]

    def move(self, delta, app):
        self.index = (self.index + delta) % len(self.values)
        self.changed(self.value)
        app.invalidate()

    def fragments(self):
        result = []
        for i, (_, label) in enumerate(self.values):
            selected = i == self.index
            focused = get_app().layout.has_focus(self.control)
            result.append(('class:choice.focused' if selected and focused else
                           'class:choice.selected' if selected else 'class:choice',
                           ('> ' if selected and focused else '* ' if selected else '  ') + label + '\n'))
        return result[:-1] + [(result[-1][0], result[-1][1].rstrip('\n'))]

    def __pt_container__(self):
        return self.window


class WorkbenchApp:
    def __init__(self, args, runner):
        self.args = args
        self.runner = runner
        self.theme = args.theme
        self.page = 'workbench'
        self.busy = False
        self.stop = threading.Event()
        self.status = 'Ready. Enter a task, then press Enter to run. F2 opens settings.'
        self.logs = []
        self.answer = ''
        self.prompt_history = []
        self.history_position = 0
        self.draft = ''
        self.task = None
        self.no_color = 'NO_COLOR' in os.environ
        self.search = SearchToolbar()
        self.output = TextArea(text='Your results will appear here.\n\n'
            'F2: project, access, theme, model and export settings.\n'
            'F1: all keyboard controls.\n\n'
            'Inspect only is selected for a new interactive session.',
            read_only=True, scrollbar=True, wrap_lines=True,
            search_field=self.search, style='class:output')
        self.prompt = TextArea(text=args.user_prompt or '', height=lambda: 1 if get_app().output.get_size().rows < 22 else 3, multiline=True,
                               wrap_lines=True, style='class:field')
        self.focus_style(self.prompt)
        self.workspace = self.field(str(args.workspace), path=True)
        self.model = self.field(args.model)
        self.steps = self.field(str(args.max_steps))
        self.transcript = self.field(str(args.transcript or ''), path=True, directories=False)
        self.export = self.field('workbench-output.txt', path=True, directories=False)
        self.appearance = Choice([(name, label) for name, label in [
            ('workbench', 'Workbench / charcoal, ivory, brass'),
            ('light', 'Light / paper and dark ink'),
            ('contrast', 'High contrast / black, white, yellow')]], args.theme, self.set_theme)
        self.access = Choice([(True, 'Inspect only / list and read files'),
                             (False, 'Edit and execute / can change this host')], args.read_only)
        self.spacing = Choice([('comfortable', 'Comfortable'), ('compact', 'Compact')], args.spacing)
        self.run_button = Button('Run task', handler=self.start)
        self.cancel_button = Button('Stop task', handler=self.cancel)
        self.apply_button = Button('Apply settings', handler=self.apply_settings)
        self.settings_body = ScrollablePane(HSplit([
            Label('Appearance / arrows preview; Enter advances' +
                  (' / NO_COLOR disables palette colors' if self.no_color else '')),
            self.appearance,
            Label('Workspace access / applies to the next task'), self.access,
            Label('Edit access permits file overwrites and Python execution on this host.'),
            Label('Project directory / Down opens suggestions'), self.workspace,
            Label('Model'), self.model,
            Label('Maximum steps / positive whole number'), self.steps,
            Label('Spacing'), self.spacing,
            Label('JSON transcript / optional; replaced after each task'), self.transcript,
            Label('Export text path / Ctrl+S exports results; replaces this file'), self.export,
            self.apply_button,
        ], padding=0), show_scrollbar=True,
            width=lambda: max(1, get_app().output.get_size().columns - 2))
        self.settings_view = Frame(self.settings_body, title='Settings / F2 returns to task')
        self.workbench_view = HSplit([
            Frame(self.output, title='Results / F3 browse / Ctrl+F search'),
            self.search,
            ConditionalContainer(Window(height=1), filter=Condition(lambda: self.spacing.value == 'comfortable' and get_app().output.get_size().rows >= 24)),
            Frame(self.prompt, title='Task / Enter run / Ctrl+J newline'),
            VSplit([self.run_button, self.cancel_button,
                    Button('Settings', handler=lambda: self.show('settings')),
                    ConditionalContainer(Button('Export', handler=self.export_text),
                        filter=Condition(lambda: get_app().output.get_size().columns >= 68)),
                    ConditionalContainer(Button('Help', handler=lambda: self.show('help')),
                        filter=Condition(lambda: get_app().output.get_size().columns >= 68))], padding=1, height=1),
        ], padding=0)
        self.help_view = Frame(TextArea(read_only=True, scrollbar=True, text=(
            'Workbench keyboard guide\n\n'
            'Enter in Task: run. Ctrl+J: new line. Bracketed paste keeps pasted lines.\n'
            'F5 or Ctrl+R: run from anywhere. Duplicate runs are blocked.\n'
            'Ctrl+N: new task. Alt+P / Alt+N: recall tasks from this session.\n'
            'Tab / Shift+Tab: next / previous control.\n'
            'Settings choices: arrows apply immediately; Enter advances.\n'
            'Settings fields: Enter advances; Down opens path completion.\n'
            'F2: settings / task. F3: results. F4: task. F1: help / task.\n'
            'Ctrl+F in results: search. Enter confirms; Escape cancels search.\n'
            'Results: arrows, PageUp / PageDown, Home / End to navigate.\n'
            'Ctrl+S: export activity and results to the configured text path.\n'
            'Ctrl+C: stop after the current request or tool finishes.\n'
            'Ctrl+Q: quit. During work, stop first and wait for it to finish.\n\n'
            'Stopping cannot undo file changes or interrupt an already running tool.\n'
            'The UI stays responsive while requests run. Provider response time varies.\n'
            'No prompts are persisted unless you enable transcripts or export text.\n'
            'Use --plain for linear screen-reader output. NO_COLOR keeps the TUI\n'
            'monochrome. Terminal font size and line height use terminal settings.\n'
            'Mouse capture is off: use your terminal to select/copy visible text.\n'
            'Use export for the complete output.\n'
        ), style='class:output'), title='Help / F1 returns to task')
        root = HSplit([
            Window(FormattedTextControl(self.header), height=1, style='class:header'),
            Window(FormattedTextControl(self.context), height=1, style='class:context'),
            DynamicContainer(lambda: {'workbench': self.workbench_view,
                                      'settings': self.settings_view, 'help': self.help_view}[self.page]),
            Window(FormattedTextControl(lambda: clean(self.status)), height=lambda: 1 if get_app().output.get_size().rows < 22 else 2, wrap_lines=True, style='class:status'),
            Window(FormattedTextControl(lambda: (' F1 Help  F2 Settings  F3 Results  F4 Task  F5 Run  Ctrl+C Stop  Ctrl+Q Quit'
                if get_app().output.get_size().columns >= 76 else ' F1 Help  F2 Setup  F3 Results  F5 Run  ^Q Quit')), height=1, style='class:header'),
        ])
        root = FloatContainer(root, floats=[Float(xcursor=True, ycursor=True,
            content=CompletionsMenu(max_height=8, scroll_offset=1))])
        self.app = Application(layout=Layout(root, focused_element=self.prompt),
                               key_bindings=self.bindings(), full_screen=True,
                               style=DynamicStyle(self.make_style), mouse_support=False,
                               min_redraw_interval=0.016)
        # Avoid waiting for terminal cursor-position reports in unsupported emulators.
        for choice in (self.appearance, self.access, self.spacing):
            choice.advance = self.focus_next
        self.app.ttimeoutlen = 0.05
        self.app.timeoutlen = 0.3

    def field(self, text, path=False, directories=True):
        area = TextArea(text=text, height=1, multiline=False, style='class:field',
                        completer=PathCompleter(only_directories=directories, expanduser=True) if path else None,
                        complete_while_typing=False)
        self.focus_style(area)
        area.buffer.accept_handler = lambda buffer: self.focus_next() or True
        return area

    @staticmethod
    def focus_style(area):
        area.window.style = lambda: ('class:field.focused' if get_app().layout.has_focus(area)
                                     else 'class:field')

    def header(self):
        return f' Workbench   /   Inspect · edit · execute     {"Offline preview" if self.args.preview else self.page.title()}'

    def context(self):
        return clean(f' {"Inspect only" if self.args.read_only else "Edit and execute"}  |  {Path(self.args.workspace).name or self.args.workspace}  |  {self.args.model}')

    def set_theme(self, value):
        self.theme = value

    def make_style(self):
        if self.no_color:
            return Style.from_dict({'header': 'reverse', 'choice.selected': 'bold', 'choice.focused': 'reverse bold',
                                    'field.focused': 'reverse',
                                    'focused': 'underline', 'button.focused': 'reverse bold',
                                    'text-area focused': 'underline', 'search': 'reverse'})
        bg, fg, accent = PALETTES[self.theme]
        return Style.from_dict({
            '': f'{fg} bg:{bg}', 'header': f'{bg} bg:{accent} bold',
            'context': f'{accent} bg:{bg}', 'status': f'{accent} bg:{bg}',
            'frame.label': f'{accent} bold', 'frame.border': f'{accent}',
            'field': f'{fg} bg:{bg}', 'text-area': f'{fg} bg:{bg}',
            'text-area focused': f'{fg} bg:{bg} underline',
            'choice.selected': f'{accent} bold', 'choice.focused': f'{bg} bg:{accent} bold',
            'field.focused': f'{bg} bg:{accent}',
            'button': f'{accent} bg:{bg}', 'button.focused': f'{bg} bg:{accent} bold',
            'scrollbar.background': f'bg:{bg}', 'scrollbar.button': f'bg:{accent}',
            'scrollbar.arrow': accent, 'search': f'{bg} bg:{accent}',
            'selected-text': f'{bg} bg:{accent}',
            'completion-menu.completion': f'{fg} bg:{bg}',
            'completion-menu.completion.current': f'{bg} bg:{accent}',
            'completion-menu.meta.completion': f'{fg} bg:{bg}',
            'completion-menu.meta.completion.current': f'{bg} bg:{accent}',
        })

    def bindings(self):
        kb = KeyBindings()
        @kb.add('tab')
        def next_control(event):
            if event.current_buffer.complete_state:
                event.current_buffer.complete_next()
            else:
                self.focus_next()
        @kb.add('s-tab')
        def previous_control(event):
            self.focus_next(-1)
        @kb.add('enter', filter=Condition(lambda: self.app.layout.has_focus(self.prompt)), eager=True)
        def run(event):
            self.start()
        @kb.add('c-j', filter=Condition(lambda: self.app.layout.has_focus(self.prompt)), eager=True)
        def newline(event):
            if not self.busy:
                self.prompt.buffer.insert_text('\n')
        @kb.add('down', filter=Condition(lambda: self.page == 'settings' and (
            self.app.layout.has_focus(self.workspace) or self.app.layout.has_focus(self.transcript)
            or self.app.layout.has_focus(self.export))))
        def complete(event):
            if event.current_buffer.complete_state:
                event.current_buffer.complete_next()
            else:
                event.current_buffer.start_completion(select_first=False)
        @kb.add('f1')
        def help(event):
            self.show('workbench' if self.page == 'help' else 'help')
        @kb.add('f2')
        def settings(event):
            if self.page == 'settings':
                self.apply_settings()
            else:
                self.show('settings')
        @kb.add('f3')
        def results(event):
            self.show('workbench', self.output)
        @kb.add('f4')
        def task(event):
            self.show('workbench')
        @kb.add('f5')
        @kb.add('c-r')
        def submit(event):
            self.start()
        @kb.add('c-n')
        def new_task(event):
            self.prompt.text = ''
            self.history_position = len(self.prompt_history)
            self.show('workbench')
            self.status = 'New task. Previous results remain available.'
        @kb.add('escape', 'p')
        def previous_task(event):
            self.recall(-1)
        @kb.add('escape', 'n')
        def next_task(event):
            self.recall(1)
        @kb.add('c-s')
        def export(event):
            self.export_text()
        @kb.add('c-f', filter=Condition(lambda: self.app.layout.has_focus(self.output)))
        def search(event):
            from prompt_toolkit.search import start_search
            start_search(self.output.control)
        @kb.add('c-c')
        def stop(event):
            self.cancel()
        @kb.add('c-q')
        def quit(event):
            if self.busy:
                self.cancel()
                self.status = 'Stopping. Quit after the current request/tool finishes; changes cannot be undone.'
            else:
                event.app.exit(result=0)
        return kb

    def focus_next(self, delta=1):
        if self.page == 'settings':
            # Explicit order includes controls below the viewport. Focusing one
            # causes ScrollablePane to reveal it on the next render.
            controls = [self.appearance.control, self.access.control, self.workspace,
                        self.model, self.steps, self.spacing.control, self.transcript,
                        self.export, self.apply_button]
            index = next((i for i, control in enumerate(controls)
                          if self.app.layout.has_focus(control)), -1)
            self.app.layout.focus(controls[(index + delta) % len(controls)])
        elif delta == 1:
            self.app.layout.focus_next()
        else:
            self.app.layout.focus_previous()

    def show(self, page, focus=None):
        self.page = page
        target = focus or {'settings': self.appearance.control, 'workbench': self.prompt,
                           'help': self.help_view.body}[page]
        self.app.layout.focus(target)
        self.app.invalidate()

    def recall(self, delta):
        if not self.prompt_history:
            return
        if self.history_position == len(self.prompt_history):
            self.draft = self.prompt.text
        self.history_position = max(0, min(len(self.prompt_history), self.history_position + delta))
        self.prompt.text = (self.draft if self.history_position == len(self.prompt_history)
                            else self.prompt_history[self.history_position])
        self.prompt.buffer.cursor_position = len(self.prompt.text)
        self.show('workbench')

    def validate(self):
        if not self.workspace.text.strip():
            self.status = 'Project directory is required.'
            self.show('settings', self.workspace)
            return False
        workspace = Path(self.workspace.text).expanduser().resolve()
        if not workspace.is_dir():
            self.status = 'Project directory does not exist. Enter an existing directory.'
            self.show('settings', self.workspace)
            return False
        if not self.model.text.strip():
            self.status = 'Model is required.'
            self.show('settings', self.model)
            return False
        try:
            steps = int(self.steps.text)
            if steps < 1:
                raise ValueError
        except ValueError:
            self.status = 'Maximum steps must be a positive whole number.'
            self.show('settings', self.steps)
            return False
        self.args.workspace, self.args.model = workspace, self.model.text.strip()
        self.args.max_steps, self.args.read_only = steps, self.access.value
        self.args.theme, self.args.spacing = self.theme, self.spacing.value
        self.args.transcript = Path(self.transcript.text).expanduser() if self.transcript.text.strip() else None
        return True

    def apply_settings(self):
        if self.validate():
            self.show('workbench')
            self.status = 'Settings applied to the next task. Enter a task and press Enter.'

    def append(self, text):
        self.logs.append(clean(text))
        separator = '\n\n' if self.spacing.value == 'comfortable' else '\n'
        self.output.buffer.set_document(Document(separator.join(self.logs)), bypass_readonly=True)
        self.output.buffer.cursor_position = len(self.output.text)
        self.app.invalidate()

    def event(self, kind, detail):
        self.status = clean(f'{kind}: {detail}')
        self.append(self.status)

    def start(self):
        if self.busy:
            self.status = 'A task is already running. Ctrl+C requests a stop.'
            return
        if not self.validate():
            return
        prompt = self.prompt.text.strip()
        if not prompt:
            self.status = 'Enter a task before running.'
            self.show('workbench')
            return
        self.busy = True  # Set synchronously to prevent duplicate submissions.
        self.run_button.text = 'Running'
        self.stop = threading.Event()
        options = copy.copy(self.args)  # Settings can change without altering in-flight permissions.
        self.show('workbench')
        self.append(f'Task: {prompt}\nProject: {options.workspace}\n'
                    f'Access: {"Inspect only" if options.read_only else "Edit and execute"}\nModel: {options.model}')
        if not self.prompt_history or self.prompt_history[-1] != prompt:
            self.prompt_history.append(prompt)
        self.history_position = len(self.prompt_history)
        self.status = 'Starting task. You can browse results or settings while waiting.'
        self.task = self.app.create_background_task(self.execute(options, prompt))

    async def execute(self, options, prompt):
        loop = asyncio.get_running_loop()
        events = queue.SimpleQueue()
        def drain():
            while True:
                try:
                    kind, detail = events.get_nowait()
                except queue.Empty:
                    break
                self.event(kind, detail)
        def notify(kind, detail):
            events.put((kind, detail))
            loop.call_soon_threadsafe(drain)
        try:
            result = await asyncio.to_thread(self.runner, options, prompt, notify, self.stop)
            drain()
            if self.stop.is_set():
                self.append('Stopped. Any completed tool changes remain in the workspace.')
                self.status = 'Stopped. Edit the task and press Enter to run again.'
            else:
                self.answer = result
                self.append('Final response:\n' + result)
                self.status = 'Task complete. Enter runs another task; F3 browses results; Ctrl+S exports.'
        except InterruptedError:
            drain()
            self.append('Stopped. Any completed tool changes remain in the workspace.')
            self.status = 'Stopped. Edit the task and press Enter to run again.'
        except Exception as error:
            drain()
            self.append(f'Error: {clean(error)}')
            self.status = 'Task failed. Details are in results. Fix settings or edit the task, then press Enter to retry.'
        finally:
            self.busy = False
            self.run_button.text = 'Run task'
            self.app.invalidate()

    def cancel(self):
        if self.busy:
            self.stop.set()
            self.status = 'Stop requested. Waiting for the current request/tool to finish; no further tools will start.'
        else:
            self.status = 'No task is running. Ctrl+Q quits; F4 returns to task input.'

    def export_text(self):
        if not self.logs:
            self.status = 'No results to export. Run a task first.'
            return
        if not self.export.text.strip():
            self.status = 'Choose an export text path in settings.'
            self.show('settings', self.export)
            return
        try:
            path = Path(self.export.text).expanduser()
            path.write_text('\n\n'.join(self.logs) + '\n', encoding='utf-8')
            self.status = f'Exported results to {path.resolve()}'
        except OSError as error:
            self.status = f'Export failed: {clean(error)}. Choose a writable path in settings.'
        self.app.invalidate()

    def run(self):
        return self.app.run()
