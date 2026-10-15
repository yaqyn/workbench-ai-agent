"""A configurable OpenRouter coding agent with an offline-testable loop."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from call_function import DEFAULT_WORKSPACE, available_functions, call_function
from prompts import system_prompt
from terminal_ui import TerminalUI, interactive_terminal


def OpenAI(**kwargs):
    # Keep provider SDK initialization out of the interactive startup path.
    from openai import OpenAI as Client
    return Client(**kwargs)


def save_transcript(path, history):
    """Atomically save a conversation, creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as transcript:
            temporary = transcript.name
            json.dump(history, transcript, indent=2, ensure_ascii=False)
            transcript.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def run_agent(client, prompt, *, workspace=DEFAULT_WORKSPACE,
              model="openrouter/free", max_steps=20, read_only=False,
              verbose=False, messages=None, on_event=None, should_stop=lambda: False):
    history = messages if messages is not None else []
    history.extend([{"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}])
    tools = [tool for tool in available_functions if not read_only or
             tool["function"]["name"] not in {"write_file", "run_python_file"}]
    for step in range(max_steps):
        if should_stop():
            raise InterruptedError("Task stopped")
        if on_event:
            on_event("Step", f"{step + 1}/{max_steps} - waiting for model")
        response = client.chat.completions.create(
            model=model, messages=history, temperature=0, tools=tools)
        if not response.choices:
            raise RuntimeError("Provider returned no response choices")
        if verbose:
            if on_event and response.usage:
                on_event("Tokens", f"{response.usage.prompt_tokens} prompt, "
                         f"{response.usage.completion_tokens} response")
            elif not on_event:
                print(f"Step {step + 1}/{max_steps}", file=sys.stderr)
                if response.usage:
                    print(f"Tokens: {response.usage.prompt_tokens} prompt, "
                          f"{response.usage.completion_tokens} response", file=sys.stderr)
        if should_stop():
            raise InterruptedError("Task stopped")
        message = response.choices[0].message
        history.append(message.model_dump(exclude_none=True))
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if should_stop():
                    raise InterruptedError("Task stopped")
                if on_event:
                    on_event("Tool", tool_call.function.name)
                result = call_function(tool_call, verbose=verbose and not on_event,
                                       working_directory=workspace, read_only=read_only)
                history.append(result)
        else:
            if not message.content:
                raise RuntimeError("Provider returned an empty final response")
            return message.content
    if should_stop():
        raise InterruptedError("Task stopped")
    raise RuntimeError(f"Maximum steps ({max_steps}) reached without a final response")


def run_terminal_task(args, prompt, on_event, stop):
    """Run off the UI thread; all UI writes go through the event callback."""
    if args.preview:
        on_event("Preview", "Offline demonstration; no request or workspace changes")
        on_event("Step", "1/1 - simulated response")
        return "Workbench is ready. Settings, task input, progress and results stay in this screen."
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Set OPENROUTER_API_KEY in the environment or project .env, then restart Workbench.")
    from openai import APIError
    history = []
    try:
        with OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                    timeout=30, max_retries=0) as client:
            return run_agent(client, prompt, workspace=args.workspace, model=args.model,
                             max_steps=args.max_steps, read_only=args.read_only,
                             verbose=args.verbose, messages=history, on_event=on_event,
                             should_stop=stop.is_set)
    except APIError as error:
        raise RuntimeError(f"Provider request failed ({type(error).__name__}). Check connectivity, "
                           "model availability, credentials and quota; retry with Enter.") from None
    finally:
        if args.transcript:
            save_transcript(args.transcript, history)


def main(argv=None):
    load_dotenv(Path(__file__).resolve().parent / ".env")
    parser = argparse.ArgumentParser(description="Inspect, edit, and run a local project using AI")
    parser.add_argument("user_prompt", nargs="?", help="Task in plain language")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE,
                        help="Project directory (default: bundled calculator)")
    parser.add_argument("--model", default=os.getenv("OPENROUTER_MODEL", "openrouter/free"))
    parser.add_argument("--max-steps", type=positive_int, default=20)
    parser.add_argument("--read-only", action="store_true", help="Disable writes and code execution")
    parser.add_argument("--transcript", type=Path, help="Save conversation as JSON; may contain file contents")
    parser.add_argument("--theme", choices=("workbench", "light", "contrast"),
                        default=os.getenv("WORKBENCH_THEME", "workbench"), help="Terminal palette")
    parser.add_argument("--plain", action="store_true", help="Linear text for screen readers; no color or full-screen menus")
    parser.add_argument("--spacing", choices=("comfortable", "compact"), default="comfortable")
    parser.add_argument("--tui", action="store_true", help="Require a full-screen interactive terminal")
    parser.add_argument("--preview", action="store_true", help="Preview the interface without credentials or a model request")
    args = parser.parse_args(argv)
    if args.theme not in ("workbench", "light", "contrast"):
        parser.error("WORKBENCH_THEME must be workbench, light, or contrast")
    if args.tui and args.plain:
        parser.error("Choose either --tui or --plain")
    if args.tui and not interactive_terminal():
        parser.error("--tui requires an interactive terminal with TERM set (for example xterm-256color)")
    if not args.plain and interactive_terminal():
        from tui import WorkbenchApp
        if args.user_prompt is None:
            args.read_only = True
        return WorkbenchApp(args, run_terminal_task).run()
    ui = TerminalUI(args.theme, args.plain, args.spacing)
    if args.user_prompt is None and not args.preview:
        try:
            ui.setup(args)
        except (KeyboardInterrupt, EOFError):
            ui.line("Cancelled. No task sent.")
            return 130
    else:
        ui.banner()
    if args.preview:
        ui.context(args, args.workspace.resolve())
        ui.event("Step", "1/20 - waiting for model (preview)")
        ui.event("Tool", "get_files_info (preview)")
        ui.answer("This is an offline preview. No files were changed and no request was sent.")
        return 0
    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        parser.error(f"Workspace is not a directory: {workspace}")
    if not args.user_prompt.strip():
        parser.error("Prompt cannot be empty")
    ui.context(args, workspace)
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        print("Error: Set OPENROUTER_API_KEY in the environment or project .env", file=sys.stderr)
        return 1
    from openai import APIError
    history = []
    exit_code = 0
    try:
        with OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                    timeout=60, max_retries=2) as client:
            answer = run_agent(client, args.user_prompt, workspace=workspace,
                               model=args.model, max_steps=args.max_steps,
                               read_only=args.read_only, verbose=args.verbose, messages=history,
                               on_event=ui.event)
        ui.answer(answer)
    except APIError as error:
        print(f"Provider request failed ({type(error).__name__}). Check connectivity, "
              "model availability, credentials, and quota.", file=sys.stderr)
        exit_code = 1
    except (RuntimeError, OSError) as error:
        ui.line(f"Error: {error}", error=True)
        exit_code = 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        exit_code = 130
    if args.transcript:
        try:
            save_transcript(args.transcript, history)
        except (OSError, TypeError, ValueError) as error:
            print(f"Could not save transcript: {error}", file=sys.stderr)
            if exit_code == 0:
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
