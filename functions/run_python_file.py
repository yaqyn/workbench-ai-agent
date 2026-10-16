import tempfile
import sys
from functions.paths import resolve_path
from config import MAX_CHARS
import os
import subprocess


def run_python_file(
    working_directory: str, file_path: str, args: list[str] | None = None
) -> str:
    try:
        absolute_working_directory = str(resolve_path(working_directory, "."))
        absolute_file_path = str(resolve_path(working_directory, file_path))
        if not os.path.isfile(absolute_file_path):
            return (
                f'Error: "{file_path}" '
                "does not exist or is not a regular file"
            )

        if not file_path.endswith(".py"):
            return f'Error: "{file_path}" is not a Python file'

        command = [sys.executable, absolute_file_path]

        if args:
            command.extend(args)

        # Store output on disk and read only a bounded prefix into the conversation.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            result = subprocess.run(
                command,
                cwd=absolute_working_directory,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                timeout=30,
            )
            captured = []
            for stream in (stdout, stderr):
                stream.seek(0)
                raw = stream.read(MAX_CHARS + 1)
                text = raw[:MAX_CHARS].decode("utf-8", errors="replace")
                if len(raw) > MAX_CHARS:
                    text += "\n[Output truncated]"
                captured.append(text)
            result.stdout, result.stderr = captured

        output = []

        if result.returncode != 0:
            output.append(f"Process exited with code {result.returncode}")

        if not result.stdout and not result.stderr:
            output.append("No output produced")
        else:
            if result.stdout:
                output.append(f"STDOUT:\n{result.stdout}")

            if result.stderr:
                output.append(f"STDERR:\n{result.stderr}")

        return "\n".join(output)

    except subprocess.TimeoutExpired:
        return "Error: Python execution timed out after 30 seconds"
    except Exception as e:
        return f"Error: executing Python file: {e}"


schema_run_python_file = {
    "type": "function",
    "function": {
        "name": "run_python_file",
        "description": "Executes a Python file with optional arguments",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the Python file to execute, relative to the working directory",
                },
                "args": {
                    "type": "array",
                    "description": "Optional arguments to pass to the Python file",
                    "items": {
                        "type": "string",
                    },
                },
            },
            "required": ["file_path"],
        },
    },
}
