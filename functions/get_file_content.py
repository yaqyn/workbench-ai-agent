from functions.paths import resolve_path
from config import MAX_CHARS
import os
def get_file_content(working_directory: str, file_path: str, start_line: int = 1) -> str:

    try:
        target_dir = resolve_path(working_directory, file_path)
        if not os.path.isfile(target_dir):
            return f'Error: File not found or is not a regular file: "{file_path}"'
        # Accept regular UTF-8 and hide an optional byte-order mark from the
        # agent so the first source character is not polluted by U+FEFF.
        if type(start_line) is not int or start_line < 1:
            return "Error: start_line must be a positive integer"
        with open(target_dir, "r", encoding="utf-8-sig") as f:
            for _ in range(start_line - 1):
                if not f.readline():
                    return ""
            file_content_string = f.read(MAX_CHARS)
            if "\x00" in file_content_string:
                return f'Error: Binary file cannot be read as text: "{file_path}"'
            if f.read(1):
                file_content_string += f'[...File "{file_path}" truncated at {MAX_CHARS} characters]'
        return file_content_string
    except UnicodeDecodeError:
        return f'Error: File is not valid UTF-8 text: "{file_path}"'
    except Exception as e:
        return f"Error: {e}"

schema_get_file_content = {
    "type": "function",
    "function": {
        "name": "get_file_content",
        "description": "Reads and returns the contents of a file relative to the working directory",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read, relative to the working directory",
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "One-based line number to start reading from",
                },
            },
            "required": ["file_path"],
        },
    },
}
