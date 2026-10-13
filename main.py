"""A configurable OpenRouter coding agent with an offline-testable loop."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, APIError

from call_function import DEFAULT_WORKSPACE, available_functions, call_function
from prompts import system_prompt


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
              verbose=False, messages=None):
    history = messages if messages is not None else []
    history.extend([{"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}])
    tools = [tool for tool in available_functions if not read_only or
             tool["function"]["name"] not in {"write_file", "run_python_file"}]
    for step in range(max_steps):
        response = client.chat.completions.create(
            model=model, messages=history, temperature=0, tools=tools)
        if not response.choices:
            raise RuntimeError("Provider returned no response choices")
        if verbose:
            print(f"Step {step + 1}/{max_steps}", file=sys.stderr)
            if response.usage:
                print(f"Tokens: {response.usage.prompt_tokens} prompt, "
                      f"{response.usage.completion_tokens} response", file=sys.stderr)
        message = response.choices[0].message
        history.append(message.model_dump(exclude_none=True))
        if message.tool_calls:
            for tool_call in message.tool_calls:
                result = call_function(tool_call, verbose=verbose,
                                       working_directory=workspace, read_only=read_only)
                history.append(result)
        else:
            if not message.content:
                raise RuntimeError("Provider returned an empty final response")
            return message.content
    raise RuntimeError(f"Maximum steps ({max_steps}) reached without a final response")


def main(argv=None):
    load_dotenv(Path(__file__).resolve().parent / ".env")
    parser = argparse.ArgumentParser(description="Inspect, edit, and run a local project using AI")
    parser.add_argument("user_prompt", help="Task in plain language")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE,
                        help="Project directory (default: bundled calculator)")
    parser.add_argument("--model", default=os.getenv("OPENROUTER_MODEL", "openrouter/free"))
    parser.add_argument("--max-steps", type=positive_int, default=20)
    parser.add_argument("--read-only", action="store_true", help="Disable writes and code execution")
    parser.add_argument("--transcript", type=Path, help="Save conversation as JSON; may contain file contents")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        parser.error(f"Workspace is not a directory: {workspace}")
    if not args.user_prompt.strip():
        parser.error("Prompt cannot be empty")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        print("Error: Set OPENROUTER_API_KEY in the environment or project .env", file=sys.stderr)
        return 1
    history = []
    exit_code = 0
    try:
        with OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                    timeout=60, max_retries=2) as client:
            answer = run_agent(client, args.user_prompt, workspace=workspace,
                               model=args.model, max_steps=args.max_steps,
                               read_only=args.read_only, verbose=args.verbose, messages=history)
        print(f"Final response:\n{answer}")
    except APIError as error:
        print(f"Provider request failed ({type(error).__name__}). Check connectivity, "
              "model availability, credentials, and quota.", file=sys.stderr)
        exit_code = 1
    except (RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
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
