"""Return stable, read-only metadata for one workspace file."""
from datetime import datetime, timezone
import json
import stat

from functions.paths import resolve_path


def get_file_metadata(working_directory: str, file_path: str) -> str:
    try:
        path = resolve_path(working_directory, file_path)
        if not path.is_file():
            return f'Error: File not found or is not a regular file: "{file_path}"'
        details = path.stat()
        return json.dumps({
            "path": file_path,
            "size_bytes": details.st_size,
            "modified_at": datetime.fromtimestamp(details.st_mtime, timezone.utc).isoformat(),
            "mode": oct(stat.S_IMODE(details.st_mode)),
        }, sort_keys=True)
    except (OSError, ValueError) as error:
        return f"Error: {error}"


schema_get_file_metadata = {
    "type": "function",
    "function": {
        "name": "get_file_metadata",
        "description": "Returns size, modification time, and permissions for a workspace file",
        "parameters": {"type": "object", "properties": {
            "file_path": {"type": "string"}}, "required": ["file_path"]},
    },
}
