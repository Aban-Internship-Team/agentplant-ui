"""Unit tests for the in-memory file-handle store (no HTTP, no LLM)."""

from __future__ import annotations

import pytest

from backend_api.AgentPlant.files import (
    MAX_UPLOAD_SIZE_BYTES,
    FileUploadRejected,
    InMemoryFileStore,
)
from backend_api.AgentPlant.schemas import FileRef


def test_register_upload_returns_file_ref():
    store = InMemoryFileStore()
    ref = store.register_upload("paper.pdf", 128)
    assert isinstance(ref, FileRef)


def test_file_id_is_non_empty():
    store = InMemoryFileStore()
    ref = store.register_upload("paper.pdf", 128)
    assert ref.file_id
    assert isinstance(ref.file_id, str)


def test_name_preserved_for_normal_filename():
    store = InMemoryFileStore()
    ref = store.register_upload("paper.pdf", 128)
    assert ref.name == "paper.pdf"


def test_two_uploads_produce_different_ids():
    store = InMemoryFileStore()
    first = store.register_upload("a.pdf", 10)
    second = store.register_upload("b.pdf", 10)
    assert first.file_id != second.file_id


def test_unix_path_becomes_basename():
    store = InMemoryFileStore()
    ref = store.register_upload("../etc/passwd", 32)
    assert ref.name == "passwd"


def test_windows_path_becomes_basename():
    store = InMemoryFileStore()
    ref = store.register_upload(r"C:\Windows\System32\foo.pdf", 32)
    assert ref.name == "foo.pdf"


def test_empty_filename_falls_back_to_upload():
    store = InMemoryFileStore()
    assert store.register_upload("", 16).name == "upload"
    assert store.register_upload("   ", 16).name == "upload"
    assert store.register_upload(".", 16).name == "upload"
    assert store.register_upload("..", 16).name == "upload"


def test_oversized_input_is_rejected():
    store = InMemoryFileStore()
    with pytest.raises(FileUploadRejected, match="file too large"):
        store.register_upload("big.pdf", MAX_UPLOAD_SIZE_BYTES + 1)


def test_empty_input_is_rejected():
    store = InMemoryFileStore()
    with pytest.raises(FileUploadRejected, match="empty file"):
        store.register_upload("empty.pdf", 0)
    with pytest.raises(FileUploadRejected, match="empty file"):
        store.register_upload("empty.pdf", -1)


def test_store_does_not_retain_uploaded_bytes():
    store = InMemoryFileStore()
    payload = b"secret-pdf-bytes"
    store.register_upload("notes.pdf", len(payload))
    assert store._refs
    for ref in store._refs.values():
        assert set(ref.model_dump()) == {"file_id", "name"}
    dumped = repr(store.__dict__)
    assert payload not in dumped.encode()
    assert b"secret-pdf-bytes" not in dumped.encode()
    assert not hasattr(store, "_bytes")
    assert not hasattr(store, "contents")
