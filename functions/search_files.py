"""Search bounded UTF-8 workspace files without leaving the workspace."""
import os

from functions.paths import resolve_path

MAX_RESULTS = 100
MAX_FILES = 1000
MAX_FILE_BYTES = 1_000_000


def search_files(working_directory: str, query: str, directory: str = ".", max_results: int = 20, suffix: str = "") -> str:
    if not query or len(query) > 200:
        return "Error: query must contain between 1 and 200 characters"
    if type(max_results) is not int or not 1 <= max_results <= MAX_RESULTS:
        return f"Error: max_results must be an integer between 1 and {MAX_RESULTS}"
    if suffix and (not suffix.startswith(".") or len(suffix) > 20 or any(char in suffix for char in "/\\")):
        return "Error: suffix must be a short file extension such as .py"
    try:
        root = resolve_path(working_directory, directory)
        if not root.is_dir():
            return f'Error: "{directory}" is not a directory'
        matches, checked = [], 0
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(name for name in dirs if name not in {".git", ".venv", "__pycache__"})
            for name in sorted(files):
                if suffix and not name.casefold().endswith(suffix.casefold()):
                    continue
                if checked >= MAX_FILES or len(matches) >= max_results:
                    break
                checked += 1
                relative = os.path.relpath(os.path.join(current, name), working_directory)
                try:
                    path = resolve_path(working_directory, relative)
                    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                        continue
                    with path.open("r", encoding="utf-8-sig") as file:
                        for number, line in enumerate(file, 1):
                            if query.casefold() in line.casefold():
                                matches.append(f"{relative}:{number}: {line.rstrip()[:300]}")
                                if len(matches) >= max_results:
                                    break
                except (OSError, UnicodeDecodeError, ValueError):
                    continue
            if checked >= MAX_FILES or len(matches) >= max_results:
                break
        if not matches:
            return "No matches found."
        suffix = "\n[Search limit reached]" if checked >= MAX_FILES or len(matches) >= max_results else ""
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
            "suffix": {"type": "string", "description": "Optional file extension such as .py"}},
            "required": ["query"]},
    },
}
