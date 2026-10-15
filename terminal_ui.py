"""Workbench presentation; plain streams remain the universal fallback."""
import os
import re
import sys

PALETTES = {
    "workbench": ("#171612", "#f4e8ca", "#e9b968"),
    "light": ("#faf6ed", "#27231b", "#755014"),
    "contrast": ("#000000", "#ffffff", "#ffff00"),
}


def clean(text):
    """Keep untrusted model/path text from issuing terminal control sequences."""
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", str(text))


def interactive_terminal():
    return (sys.stdin.isatty() and sys.stdout.isatty()
            and os.getenv("TERM") != "dumb")


class TerminalUI:
    def __init__(self, theme="workbench", plain=False, spacing="comfortable"):
        self.plain = (plain or "NO_COLOR" in os.environ
                      or not interactive_terminal())
        self.theme = theme
        self.spacing = spacing

    def line(self, text="", *, heading=False, error=False):
        stream = sys.stderr if error else sys.stdout
        text = clean(text)
        if not self.plain and stream.isatty() and heading:
            accent = PALETTES[self.theme][2].lstrip("#")
            rgb = tuple(int(accent[i:i + 2], 16) for i in (0, 2, 4))
            text = f"\033[1;38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{text}\033[0m"
        print(text, file=stream, flush=True)

    def banner(self):
        self.line("Workbench", heading=True)
        self.line("Inspect / edit / execute")
        if self.spacing == "comfortable":
            self.line()

    def choose(self, title, values, default):
        self.line(title)
        for index, (_, label) in enumerate(values, 1):
            self.line(f"  {index}. {label}")
        default_number = next(i for i, (v, _) in enumerate(values, 1) if v == default)
        while True:
            answer = input(f"Choice [{default_number}]: ").strip() or str(default_number)
            if answer.isdigit() and 1 <= int(answer) <= len(values):
                return values[int(answer) - 1][0]
            self.line("Enter one of the numbers above.")

    def ask(self, label, default="", *, path=False):
        return input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip() or default

    def setup(self, args):
        self.banner()
        self.line("Ctrl+C cancels. Your terminal controls font size and text selection.")
        args.theme = self.choose("Appearance", [
            ("workbench", "Workbench - charcoal, ivory and brass"),
            ("light", "Light - paper and dark ink"),
            ("contrast", "High contrast - black, white and yellow"),
        ], args.theme)
        self.__init__(args.theme, self.plain, args.spacing)
        args.read_only = self.choose("Workspace access", [
            (True, "Inspect only - list and read files"),
            (False, "Edit and execute - can overwrite files and run Python on this host"),
        ], True)
        from pathlib import Path
        while True:
            workspace = Path(self.ask("Project directory", str(args.workspace), path=True)).expanduser()
            if workspace.is_dir():
                args.workspace = workspace
                break
            self.line("Directory does not exist. Enter an existing project directory.")
        args.model = self.ask("Model", args.model)
        while not args.user_prompt or not args.user_prompt.strip():
            args.user_prompt = self.ask("What should Workbench do?")
        return args

    def context(self, args, workspace):
        self.line(f"Project: {workspace}")
        self.line(f"Access: {'Inspect only' if args.read_only else 'Edit and execute'}")
        self.line(f"Model: {args.model} | Step limit: {args.max_steps}")
        if self.spacing == "comfortable":
            self.line()

    def event(self, kind, detail):
        self.line(f"{kind}: {detail}")

    def answer(self, text):
        if self.spacing == "comfortable":
            self.line()
        self.line("Final response:", heading=True)
        self.line(text)
