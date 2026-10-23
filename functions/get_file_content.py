from functions.paths import resolve_path
from config import MAX_CHARS
import os
def get_file_content(working_directory: str, file_path: str) -> str:

    try:
        target_dir = resolve_path(working_directory, file_path)
        if not os.path.isfile(target_dir):
            return f'Error: File not found or is not a regular file: "{file_path}"'
        # Accept regular UTF-8 and hide an optional byte-order mark from the
        # agent so the first source character is not polluted by U+FEFF.
        with open(target_dir, "r", encoding="utf-8-sig") as f:
            file_content_string = f.read(MAX_CHARS)
            if "\x00" in file_content_string:
                return f'Error: Binary file cannot be read as text: "{file_path}"'
            if f.read(1):
                file_content_string += f'[...File "{file_path}" truncated at {MAX_CHARS} characters]'
        return file_content_string
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
            },
            "required": ["file_path"],
        },
    },
}
