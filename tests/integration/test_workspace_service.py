"""로컬 AppData를 사용하지 않고 tmp_path의 JSON/원본만 검증한다."""

import hashlib
import io
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from openpyxl import Workbook

from small_stream_research_tool.models.column_mapping import ColumnMappingDraft, MappingHeaderPart
from small_stream_research_tool.models.workspace import WorkspaceStep
from small_stream_research_tool.models.workspace_errors import (
    InvalidWorkspaceError,
    UnsafeWorkspaceMetadataError,
    UnsupportedWorkspaceVersionError,
    WorkspaceIOError,
    WorkspaceSourceChangedError,
    WorkspaceSourceMissingError,
    WorkspaceUserMismatchError,
)
from small_stream_research_tool.services.workspace_service import WorkspaceService
from small_stream_research_tool.utils.file_hash import HASH_CHUNK_SIZE, file_sha256


@pytest.fixture
def context(tmp_path):
    path = tmp_path / "synthetic.xlsx"
    workbook = Workbook()
    workbook.active.append(["Synthetic Area"])
    workbook.active.append(["SYNTHETIC_ROW_DATA_DO_NOT_STORE"])
    workbook.save(path)
    workbook.close()
    service = WorkspaceService(tmp_path / "workspace")
    mapping = ColumnMappingDraft(
        1, "A", "Synthetic Area", (MappingHeaderPart(1, "Synthetic Area", None, None, None, None),)
    )
    draft = service.create_workspace(
        current_user_id=1,
        source_file_path=path,
        selected_sheet_name="Sheet",
        header_start_row=1,
        header_end_row=1,
        data_start_row=2,
        column_mappings=(mapping,),
        current_step=WorkspaceStep.MAPPING,
    )
    return service, draft, tmp_path / "workspace" / "user_1.json"


def test_save_load_metadata_and_no_raw_data(context):
    service, draft, path = context
    assert not path.exists() and service.load_workspace(1) is None
    saved = service.save_workspace(draft, 1)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["workspace_version"] == 1 and data["user_id"] == 1
    assert data["source_file_path"] == draft.source_file_path
    assert data["source_file_sha256"] == file_sha256(draft.source_file_path)
    assert data["selected_sheet_name"] == "Sheet"
    assert (data["header_start_row"], data["header_end_row"], data["data_start_row"]) == (1, 1, 2)
    assert data["current_step"] == "MAPPING"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", data["saved_at"])
    assert data["column_mappings"][0]["source_header_parts"][0]["text"] == "Synthetic Area"
    assert "SYNTHETIC_ROW_DATA_DO_NOT_STORE" not in path.read_text(encoding="utf-8")
    assert all(field not in data for field in ("password", "password_hash", "rows", "cells"))
    assert WorkspaceService(path.parent).load_workspace(1) == saved


def test_default_path_and_no_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from small_stream_research_tool.config.settings import get_app_paths

    service = WorkspaceService()
    assert service.load_workspace(1) is None
    assert not get_app_paths().workspace_dir.exists()


def test_repo_path_rejected(tmp_path):
    repo = tmp_path / "synthetic_repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    with pytest.raises(InvalidWorkspaceError):
        WorkspaceService(repo / "workspace")


@pytest.mark.parametrize("user", [0, -1, True, "../1", None])
def test_invalid_user(context, user):
    service, draft, _ = context
    with pytest.raises(InvalidWorkspaceError):
        service.save_workspace(draft, user)
    with pytest.raises(InvalidWorkspaceError):
        service.load_workspace(user)


def test_user_mismatch_save_and_load(context):
    service, draft, path = context
    with pytest.raises(WorkspaceUserMismatchError):
        service.save_workspace(draft, 2)
    service.save_workspace(draft, 1)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["user_id"] = 2
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(WorkspaceUserMismatchError):
        service.load_workspace(1)


@pytest.mark.parametrize("version", [0, 2, True, "1"])
def test_unsupported_version(context, version):
    service, draft, path = context
    service.save_workspace(draft, 1)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["workspace_version"] = version
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(UnsupportedWorkspaceVersionError):
        service.load_workspace(1)


@pytest.mark.parametrize("payload", [b"{", b"[]", b"null", b"\xff", b'{"user_id":1,"user_id":2}'])
def test_malformed_json_is_application_error(context, payload):
    service, draft, path = context
    service.save_workspace(draft, 1)
    path.write_bytes(payload)
    with pytest.raises(InvalidWorkspaceError):
        service.load_workspace(1)
    assert path.read_bytes() == payload


@pytest.mark.parametrize("level", ["workspace", "mapping", "part"])
@pytest.mark.parametrize("field", ["password_hash", "password", "raw_cells", "service_key"])
def test_unknown_sensitive_fields_rejected_at_every_level(context, level, field):
    service, draft, path = context
    service.save_workspace(draft, 1)
    data = json.loads(path.read_text(encoding="utf-8"))
    target = data if level == "workspace" else data["column_mappings"][0]
    if level == "part":
        target = target["source_header_parts"][0]
    target[field] = "SYNTHETIC_NOT_A_REAL_SECRET"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(InvalidWorkspaceError):
        service.load_workspace(1)


@pytest.mark.parametrize(
    "text",
    [
        "password=SYNTHETIC",
        "service_key=SYNTHETIC",
        "192.0.2.1",
        "rtsp://example.invalid/test",
        "synthetic@example.invalid",
        "2001:db8::1",
        "010-0000-0000",
    ],
)
def test_sensitive_metadata_refused_without_overwriting(context, text):
    service, draft, path = context
    service.save_workspace(draft, 1)
    before = path.read_bytes()
    mapping = replace(draft.column_mappings[0], source_header=text)
    with pytest.raises(UnsafeWorkspaceMetadataError):
        service.save_workspace(replace(draft, column_mappings=(mapping,)), 1)
    assert path.read_bytes() == before


def test_header_datetime_is_not_ipv6(context):
    service, draft, _ = context
    part = replace(draft.column_mappings[0].source_header_parts[0], text="2020-01-01 00:00:00")
    mapping = replace(draft.column_mappings[0], source_header_parts=(part,))
    service.save_workspace(replace(draft, column_mappings=(mapping,)), 1)


@pytest.mark.parametrize("change", ["missing", "changed", "directory"])
def test_source_failure_refuses_resume(context, change):
    service, draft, path = context
    service.save_workspace(draft, 1)
    original = Path(draft.source_file_path)
    stored = path.read_bytes()
    if change == "changed":
        original.write_bytes(b"SYNTHETIC_CHANGED_SOURCE")
        error = WorkspaceSourceChangedError
    else:
        original.rename(original.with_name("moved.xlsx"))
        if change == "directory":
            original.mkdir()
        error = InvalidWorkspaceError if change == "directory" else WorkspaceSourceMissingError
    with pytest.raises(error):
        service.load_workspace(1)
    assert path.read_bytes() == stored


def test_save_changed_source_preserves_old_workspace(context):
    service, draft, path = context
    service.save_workspace(draft, 1)
    before = path.read_bytes()
    Path(draft.source_file_path).write_bytes(b"SYNTHETIC_CHANGED_SOURCE")
    with pytest.raises(WorkspaceSourceChangedError):
        service.save_workspace(draft, 1)
    assert path.read_bytes() == before


def test_overwrite_delete_isolated_and_source_unchanged(context):
    service, draft, path = context
    original_hash = file_sha256(draft.source_file_path)
    service.save_workspace(draft, 1)
    service.save_workspace(replace(draft, user_id=2), 2)
    updated = replace(draft, data_start_row=3)
    assert service.save_workspace(updated, 1) == service.load_workspace(1)
    unrelated = path.parent / "unrelated.txt"
    unrelated.write_text("synthetic", encoding="utf-8")
    assert service.delete_workspace(1) is True
    assert service.delete_workspace(1) is False and service.load_workspace(1) is None
    assert (path.parent / "user_2.json").exists() and unrelated.exists()
    assert file_sha256(draft.source_file_path) == original_hash


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_atomic_failure_preserves_previous_and_cleans_temp(context, monkeypatch, failure):
    import small_stream_research_tool.services.workspace_service as module

    service, draft, path = context
    service.save_workspace(draft, 1)
    before = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("synthetic private I/O details")

    monkeypatch.setattr(module.os, failure, fail)
    with pytest.raises(WorkspaceIOError) as caught:
        service.save_workspace(replace(draft, data_start_row=3), 1)
    assert "private" not in str(caught.value)
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


def test_hash_chunking_and_change_detection(tmp_path, monkeypatch):
    content = b"synthetic" * (HASH_CHUNK_SIZE // 4)
    path = tmp_path / "hash_source"
    path.write_bytes(content)
    assert file_sha256(path) == hashlib.sha256(content).hexdigest()
    path.write_bytes(content + b"changed")
    assert file_sha256(path) != hashlib.sha256(content).hexdigest()
    requests = []

    class Observed(io.BytesIO):
        def read(self, size=-1):
            requests.append(size)
            return super().read(size)

    monkeypatch.setattr(Path, "open", lambda *a, **k: Observed(content))
    assert file_sha256(path) == hashlib.sha256(content).hexdigest()
    assert len(requests) >= 3 and set(requests) == {HASH_CHUNK_SIZE}


@pytest.mark.parametrize(
    "changes",
    [
        {"header_start_row": 0},
        {"header_end_row": 0},
        {"data_start_row": 1},
        {"header_start_row": True},
        {"selected_sheet_name": None},
        {"saved_at": "2020-99-99T00:00:00Z"},
        {"source_file_sha256": "bad"},
        {"current_step": "MAPPING"},
        {"source_scope": "other"},
    ],
)
def test_invalid_workspace_model(context, changes):
    service, draft, _ = context
    with pytest.raises(InvalidWorkspaceError):
        service.save_workspace(replace(draft, **changes), 1)


def test_file_and_header_steps(context):
    service, draft, _ = context
    first = service.create_workspace(current_user_id=1, source_file_path=draft.source_file_path)
    assert service.save_workspace(first, 1) == service.load_workspace(1)
    header = replace(draft, current_step=WorkspaceStep.HEADER_CONFIGURED, column_mappings=())
    assert service.save_workspace(header, 1) == service.load_workspace(1)


def test_no_database_or_logging(context, monkeypatch, caplog):
    import sqlite3

    service, draft, _ = context

    def forbidden(*args, **kwargs):
        pytest.fail("Workspace must not access the research database")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    service.save_workspace(draft, 1)
    service.load_workspace(1)
    service.delete_workspace(1)
    assert caplog.records == []


def test_unavailable_workspace_path_is_sanitized(context, monkeypatch):
    service, _, _ = context

    def fail(*args, **kwargs):
        raise OSError("SYNTHETIC_PRIVATE_PATH")

    monkeypatch.setattr(Path, "resolve", fail)
    with pytest.raises(WorkspaceIOError) as caught:
        service.load_workspace(1)
    assert "PRIVATE" not in str(caught.value)


def test_workspace_symlink_is_refused(context, monkeypatch):
    service, draft, path = context
    service.save_workspace(draft, 1)
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == path or original(p))
    with pytest.raises(WorkspaceIOError):
        service.load_workspace(1)
    with pytest.raises(WorkspaceIOError):
        service.delete_workspace(1)
    assert path.exists()


def test_source_changes_while_hashing(context, monkeypatch):
    import small_stream_research_tool.services.workspace_service as module

    service, draft, _ = context
    original_hash = module.file_sha256

    def changing(path):
        path.write_bytes(b"synthetic-changed-during-hashing")
        return original_hash(path)

    monkeypatch.setattr(module, "file_sha256", changing)
    with pytest.raises(WorkspaceSourceChangedError):
        service.save_workspace(draft, 1)


def test_workspace_size_limit_applies_to_read_and_write(context, monkeypatch):
    import small_stream_research_tool.services.workspace_service as module

    service, draft, path = context
    service.save_workspace(draft, 1)
    before = path.read_bytes()
    monkeypatch.setattr(module, "MAX_WORKSPACE_BYTES", 20)
    with pytest.raises(InvalidWorkspaceError):
        service.load_workspace(1)
    with pytest.raises(InvalidWorkspaceError):
        service.save_workspace(draft, 1)
    assert path.read_bytes() == before


def test_invalid_unicode_metadata_is_refused(context):
    service, draft, _ = context
    mapping = replace(draft.column_mappings[0], source_header="\ud800")
    with pytest.raises(InvalidWorkspaceError):
        service.save_workspace(replace(draft, column_mappings=(mapping,)), 1)
