import threading
import sys
from functions.paths import resolve_path
from config import MAX_CHARS
import os
import re
import subprocess


SENSITIVE_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
SENSITIVE_ENV_NAMES = {
    "DATABASE_URL",
    "REDIS_URL",
    "CONNECTION_STRING",
    "PGPASSWORD",
    "PGPASSFILE",
    "MYSQL_PWD",
    "REDISCLI_AUTH",
}


def _read_limited(stream, limit: int) -> bytes:
    """Drain a subprocess pipe while retaining only a bounded prefix."""
    captured = bytearray()
    while chunk := stream.read(8192):
        remaining = limit + 1 - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])
    return bytes(captured)


def _capture_stream(index: int, stream, captured: list[bytes]) -> None:
    captured[index] = _read_limited(stream, MAX_CHARS)


def safe_environment() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if name.upper() not in SENSITIVE_ENV_NAMES
        and not set(re.split(r"[^A-Z0-9]+", name.upper())).intersection(SENSITIVE_ENV_MARKERS)
    }


def run_python_file(
    working_directory: str, file_path: str, args: list[str] | None = None
) -> str:
    try:
        if args is not None and (not isinstance(args, list) or len(args) > 100):
            return "Error: Python arguments must be a list of at most 100 strings"
        if args is not None and (
            any(not isinstance(arg, str) or len(arg) > 4096 for arg in args)
            or sum(map(len, args)) > 16384
        ):
            return "Error: Python arguments exceed the safe size limit"
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

        process = subprocess.Popen(
            command,
            cwd=absolute_working_directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=safe_environment(),
        )
        captured = [b"", b""]
        readers = [
            threading.Thread(target=_capture_stream, args=(index, stream, captured))
            for index, stream in enumerate((process.stdout, process.stderr))
        ]
        for reader in readers:
            reader.start()
        try:
            returncode = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            for reader in readers:
                reader.join()
            process.stdout.close()
            process.stderr.close()
            raise
        for reader in readers:
            reader.join()
        process.stdout.close()
        process.stderr.close()

        output_text = []
        remaining = MAX_CHARS
        for raw in captured:
            kept = raw[:remaining]
            text = kept.decode("utf-8", errors="replace")
            remaining -= len(kept)
            if len(raw) > len(kept):
                text += "\n[Output truncated]"
            output_text.append(text)
        stdout_text, stderr_text = output_text

        output = []

        if returncode != 0:
            output.append(f"Process exited with code {returncode}")

        if not stdout_text and not stderr_text:
            output.append("No output produced")
        else:
            if stdout_text:
                output.append(f"STDOUT:\n{stdout_text}")

            if stderr_text:
                output.append(f"STDERR:\n{stderr_text}")

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
