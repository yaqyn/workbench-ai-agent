from functions.paths import resolve_path
import os

MAX_DIRECTORY_ENTRIES = 200

def get_files_info(working_directory: str, directory: str = ".") -> str:
    try:
        target_dir = resolve_path(working_directory, directory)
        if not os.path.isdir(target_dir):
            return f'Error: "{directory}" is not a directory'
        metadata = []
        names = sorted(os.listdir(target_dir))
        for name in names[:MAX_DIRECTORY_ENTRIES]:
            try:
                relative_path = os.path.relpath(target_dir / name, working_directory)
                filepath = resolve_path(working_directory, relative_path)
                is_dir = filepath.is_dir()
                file_size = filepath.stat().st_size
                metadata.append(f"- {name}: file_size={file_size} bytes, is_dir={is_dir}")
            except (OSError, ValueError) as error:
                metadata.append(f"- {name}: Error: {error}")
        if len(names) > MAX_DIRECTORY_ENTRIES:
            metadata.append(f"... {len(names) - MAX_DIRECTORY_ENTRIES} more entries omitted; list a subdirectory to narrow the result")
        return "\n".join(metadata)
    except Exception as e:
        return f"Error: {e}"

schema_get_files_info = {
    "type": "function",
    "function": {
        "name": "get_files_info",
        "description": "Lists files in a specified directory relative to the working directory, providing file size and directory status",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to list files from, relative to the working directory (default is the working directory itself)",
                },
            },
        },
    },
}
