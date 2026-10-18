from functions.paths import resolve_path
import os
import tempfile

def write_file(working_directory: str, file_path: str, content: str) -> str:
    try:
        target_path = resolve_path(working_directory, file_path)
        if os.path.isdir(target_path):
            return f'Error: Cannot write to "{file_path}" as it is a directory'

        # Validate encoding before opening an existing file in truncating mode.
        content.encode("utf-8")
        parent_dir = os.path.dirname(target_path)
        os.makedirs(parent_dir, exist_ok=True)

        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=parent_dir,
                prefix=f".{target_path.name}.", delete=False,
            ) as f:
                temporary = f.name
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, target_path)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

        return f'Successfully wrote to "{file_path}" ({len(content)} characters written)'

    except (OSError, ValueError) as e:
        return f"Error: {e}"

schema_write_file = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Writes or overwrites a file with the provided content",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write, relative to the working directory",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        },
    },
}
