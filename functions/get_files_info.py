from functions.paths import resolve_path
import os

MAX_DIRECTORY_ENTRIES = 200

def get_files_info(working_directory: str, directory: str = ".", max_entries: int = MAX_DIRECTORY_ENTRIES) -> str:
    try:
        if type(max_entries) is not int or max_entries < 1 or max_entries > MAX_DIRECTORY_ENTRIES:
            return f"Error: max_entries must be an integer between 1 and {MAX_DIRECTORY_ENTRIES}"
        target_dir = resolve_path(working_directory, directory)
        if not os.path.isdir(target_dir):
            return f'Error: "{directory}" is not a directory'
        metadata = []
        names = sorted(os.listdir(target_dir))
        for name in names[:max_entries]:
            try:
                relative_path = os.path.relpath(target_dir / name, working_directory)
                filepath = resolve_path(working_directory, relative_path)
                is_dir = filepath.is_dir()
                file_size = filepath.stat().st_size
                metadata.append(f"- {name}: file_size={file_size} bytes, is_dir={is_dir}")
            except (OSError, ValueError) as error:
                metadata.append(f"- {name}: Error: {error}")
        if len(names) > max_entries:
            metadata.append(f"... {len(names) - max_entries} more entries omitted; list a subdirectory or increase max_entries to narrow the result")
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
                "max_entries": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_DIRECTORY_ENTRIES,
                    "description": "Maximum entries to return (default: 200)",
                },
            },
        },
    },
}
