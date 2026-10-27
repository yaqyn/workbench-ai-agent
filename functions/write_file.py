from functions.paths import resolve_path
import os
import stat
import tempfile

def write_file(working_directory: str, file_path: str, content: str, overwrite: bool = True) -> str:
    try:
        target_path = resolve_path(working_directory, file_path)
        if type(overwrite) is not bool:
            return "Error: overwrite must be a boolean"
        if os.path.isdir(target_path):
            return f'Error: Cannot write to "{file_path}" as it is a directory'
        if not overwrite and os.path.exists(target_path):
            return f'Error: File already exists: "{file_path}"'

        # Validate encoding before opening an existing file in truncating mode.
        content.encode("utf-8")
        parent_dir = os.path.dirname(target_path)
        os.makedirs(parent_dir, exist_ok=True)
        existing_mode = (
            stat.S_IMODE(os.stat(target_path).st_mode)
            if os.path.exists(target_path)
            else None
        )

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
            if existing_mode is not None:
                os.chmod(temporary, existing_mode)
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
                "overwrite": {
                    "type": "boolean",
                    "description": "Whether an existing file may be replaced (default: true)",
                },
            },
            "required": ["file_path", "content"],
        },
    },
}
