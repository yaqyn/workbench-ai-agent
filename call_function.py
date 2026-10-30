"""Validate and dispatch model tool calls into a configured workspace."""
import inspect
import json
from collections.abc import Callable
from pathlib import Path

from functions.get_files_info import get_files_info, schema_get_files_info
from functions.get_file_content import get_file_content, schema_get_file_content
from functions.run_python_file import run_python_file, schema_run_python_file
from functions.write_file import write_file, schema_write_file
from functions.search_files import search_files, schema_search_files
from functions.get_file_metadata import get_file_metadata, schema_get_file_metadata

DEFAULT_WORKSPACE = Path(__file__).resolve().parent / "calculator"
available_functions = [schema_get_files_info, schema_get_file_content,
                       schema_run_python_file, schema_write_file, schema_search_files,
                       schema_get_file_metadata]
function_map: dict[str, Callable[..., str]] = {
    "get_files_info": get_files_info, "get_file_content": get_file_content,
    "run_python_file": run_python_file, "write_file": write_file,
    "search_files": search_files,
    "get_file_metadata": get_file_metadata,
}


def call_function(tool_call, verbose=False, working_directory=None, read_only=False):
    name = tool_call.function.name
    try:
        if name not in function_map:
            raise ValueError(f"Unknown function: {name}")
        if read_only and name in {"write_file", "run_python_file"}:
            raise ValueError(f"{name} is disabled in read-only mode")
        arguments = json.loads(tool_call.function.arguments or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object")
        if "working_directory" in arguments:
            raise ValueError("The model cannot override the working directory")
        for key, value in arguments.items():
            if key == "args":
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    raise ValueError("args must be an array of strings")
            elif key in {"start_line", "line_count", "max_entries", "max_results"}:
                if type(value) is not int or value < 1:
                    raise ValueError(f"{key} must be a positive integer")
            elif not isinstance(value, str):
                raise ValueError(f"{key} must be a string")
        arguments["working_directory"] = str(working_directory or DEFAULT_WORKSPACE)
        inspect.signature(function_map[name]).bind(**arguments)
        if verbose:
            print(f" - Calling function: {name}")
        result = function_map[name](**arguments)
    except (ValueError, TypeError, OSError) as error:
        result = f"Error: {error}"
    return {"role": "tool", "tool_call_id": tool_call.id, "content": result}
