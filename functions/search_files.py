"""Search bounded UTF-8 workspace files without leaving the workspace."""
import os

from functions.paths import resolve_path

MAX_RESULTS = 100
MAX_FILES = 1000
MAX_FILE_BYTES = 1_000_000


def search_files(working_directory: str, query: str, directory: str = ".", max_results: int = 20, suffix: str = "", case_sensitive: bool = False, include_hidden: bool = False, context_lines: int = 0) -> str:
    if not query or len(query) > 200:
        return "Error: query must contain between 1 and 200 characters"
    if type(max_results) is not int or not 1 <= max_results <= MAX_RESULTS:
        return f"Error: max_results must be an integer between 1 and {MAX_RESULTS}"
    if suffix and (not suffix.startswith(".") or len(suffix) > 20 or any(char in suffix for char in "/\\")):
        return "Error: suffix must be a short file extension such as .py"
    if type(case_sensitive) is not bool:
        return "Error: case_sensitive must be a boolean"
    if type(include_hidden) is not bool:
        return "Error: include_hidden must be a boolean"
    if type(context_lines) is not int or not 0 <= context_lines <= 3:
        return "Error: context_lines must be an integer between 0 and 3"
    try:
        root = resolve_path(working_directory, directory)
        if not root.is_dir():
            return f'Error: "{directory}" is not a directory'
        matches, checked, matched_count = [], 0, 0
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(name for name in dirs if name not in {".git", ".venv", "__pycache__"} and (include_hidden or not name.startswith(".")))
            for name in sorted(files):
                if not include_hidden and name.startswith("."):
                    continue
                if suffix and not name.casefold().endswith(suffix.casefold()):
                    continue
                if checked >= MAX_FILES or matched_count >= max_results:
                    break
                checked += 1
                relative = os.path.relpath(os.path.join(current, name), working_directory)
                try:
                    path = resolve_path(working_directory, relative)
                    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                        continue
                    with path.open("r", encoding="utf-8-sig") as file:
                        lines = file.readlines()
                        for number, line in enumerate(lines, 1):
                            matched = query in line if case_sensitive else query.casefold() in line.casefold()
                            if matched:
                                matched_count += 1
                                for context_number in range(max(1, number - context_lines), number):
                                    matches.append(f"{relative}:{context_number}-: {lines[context_number - 1].rstrip()[:300]}")
                                matches.append(f"{relative}:{number}: {line.rstrip()[:300]}")
                                for context_number in range(number + 1, min(len(lines), number + context_lines) + 1):
                                    matches.append(f"{relative}:{context_number}+: {lines[context_number - 1].rstrip()[:300]}")
                                if matched_count >= max_results:
                                    break
                except (OSError, UnicodeDecodeError, ValueError):
                    continue
            if checked >= MAX_FILES or matched_count >= max_results:
                break
        if not matches:
            return "No matches found."
        suffix = "\n[Search limit reached]" if checked >= MAX_FILES or matched_count >= max_results else ""
        return "\n".join(matches) + suffix
    except (OSError, ValueError) as error:
        return f"Error: {error}"


schema_search_files = {
    "type": "function",
    "function": {
        "name": "search_files",
        "description": "Searches bounded UTF-8 files in the workspace for literal text",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}, "directory": {"type": "string"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
            "suffix": {"type": "string", "description": "Optional file extension such as .py"},
            "case_sensitive": {"type": "boolean", "description": "Match exact letter case when true"},
            "include_hidden": {"type": "boolean", "description": "Search dot-prefixed files and directories (default: false)"},
            "context_lines": {"type": "integer", "minimum": 0, "maximum": 3, "description": "Neighboring lines to include around each match"}},
            "required": ["query"]},
    },
}
