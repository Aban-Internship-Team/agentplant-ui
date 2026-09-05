"""In-memory file-handle registry for AgentPlant uploads.

Stores only ``FileRef`` metadata. Bytes are never retained or written to disk.
"""

from __future__ import annotations

from uuid import uuid4

from backend_api.AgentPlant.schemas import FileRef

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
_FALLBACK_NAME = "upload"


class FileUploadRejected(ValueError):
    """Raised when an upload is empty or larger than ``MAX_UPLOAD_SIZE_BYTES``."""


def safe_display_name(filename: str | None) -> str:
    """Return a display name: basename only, or ``upload`` if unusable."""
    raw = (filename or "").strip()
    if not raw:
        return _FALLBACK_NAME
    normalized = raw.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."}:
        return _FALLBACK_NAME
    return name


class InMemoryFileStore:
    """Process-local map of ``file_id`` → ``FileRef``. No file bytes."""

    def __init__(self) -> None:
        self._refs: dict[str, FileRef] = {}

    def register_upload(self, filename: str, file_size: int) -> FileRef:
        if file_size <= 0:
            raise FileUploadRejected("empty file")
        if file_size > MAX_UPLOAD_SIZE_BYTES:
            raise FileUploadRejected("file too large")
        file_id = uuid4().hex
        ref = FileRef(file_id=file_id, name=safe_display_name(filename))
        self._refs[file_id] = ref
        return ref


default_file_store = InMemoryFileStore()
