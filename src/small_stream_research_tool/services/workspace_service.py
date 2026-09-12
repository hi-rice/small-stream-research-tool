"""연구 DB 없는 단일 사용자별 JSON Workspace. 자동 원본 검색/재지정은 하지 않는다."""

import ipaddress
import json
import os
import re
import tempfile
from dataclasses import asdict, fields, replace
from datetime import datetime
from pathlib import Path

from small_stream_research_tool.config.settings import get_app_paths
from small_stream_research_tool.models.column_mapping import (
    ColumnMappingDraft,
    MappingHeaderPart,
    MappingMethod,
    MappingStatus,
)
from small_stream_research_tool.models.mapping_errors import InvalidMappingError
from small_stream_research_tool.models.workspace import WorkspaceDraft, WorkspaceStep
from small_stream_research_tool.models.workspace_errors import (
    InvalidWorkspaceError,
    UnsafeWorkspaceMetadataError,
    UnsupportedWorkspaceVersionError,
    WorkspaceIOError,
    WorkspaceSourceChangedError,
    WorkspaceSourceMissingError,
    WorkspaceUserMismatchError,
)
from small_stream_research_tool.services.column_mapping_service import validate_mappings
from small_stream_research_tool.utils.file_hash import file_sha256
from small_stream_research_tool.utils.timestamps import utc_now_text

WORKSPACE_VERSION = 1
MAX_WORKSPACE_BYTES = 8 * 1024 * 1024

# 저장 경계의 보수적 거부 규칙이다. 자료 의미/QC를 판정하거나 값을 마스킹해 저장하지 않는다.
_UNSAFE_TEXT = re.compile(
    r"password|passwd|비밀번호|service[ _-]?key|api[ _-]?key|access[ _-]?token|"
    r"secret|credential|rtsp[s]?://|인증정보|접속정보|연락처|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"\b(?:010|011|016|017|018|019)[ -]?\d{3,4}[ -]?\d{4}\b",
    re.IGNORECASE,
)


def _positive(value):
    return type(value) is int and 0 < value <= 9223372036854775807


def _metadata_text(value, *, optional=False, blank=False):
    if value is None and optional:
        return
    if (
        not isinstance(value, str)
        or len(value) > 8192
        or "\0" in value
        or any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    ):
        raise InvalidWorkspaceError("Workspace 문자열 metadata 형식이 올바르지 않습니다.")
    if not blank and not value.strip():
        raise InvalidWorkspaceError("필수 Workspace metadata가 비어 있습니다.")
    if _UNSAFE_TEXT.search(value):
        raise UnsafeWorkspaceMetadataError(
            "민감정보 가능성이 있는 metadata는 저장/재개할 수 없습니다."
        )
    for candidate in re.findall(r"(?<!\w)[0-9a-fA-F:]*:[0-9a-fA-F:]+(?!\w)", value):
        try:
            ipaddress.IPv6Address(candidate)
        except ipaddress.AddressValueError:
            continue
        raise UnsafeWorkspaceMetadataError("IP 주소 metadata는 저장/재개할 수 없습니다.")


def _validate(workspace, current_user_id):
    if type(workspace) is not WorkspaceDraft or not _positive(current_user_id):
        raise InvalidWorkspaceError("WorkspaceDraft와 양의 현재 사용자 ID가 필요합니다.")
    if (
        type(workspace.workspace_version) is not int
        or workspace.workspace_version != WORKSPACE_VERSION
    ):
        raise UnsupportedWorkspaceVersionError("지원하지 않는 Workspace 버전입니다.")
    if not _positive(workspace.user_id):
        raise InvalidWorkspaceError("Workspace 사용자 ID 형식이 올바르지 않습니다.")
    if workspace.user_id != current_user_id:
        raise WorkspaceUserMismatchError("현재 사용자와 Workspace 소유자가 다릅니다.")
    _metadata_text(workspace.source_file_path)
    path = Path(workspace.source_file_path)
    if not path.is_absolute() or path.suffix.lower() != ".xlsx":
        raise InvalidWorkspaceError("원본은 절대경로의 .xlsx 파일이어야 합니다.")
    if not isinstance(workspace.source_file_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", workspace.source_file_sha256
    ):
        raise InvalidWorkspaceError("원본 SHA-256 형식이 올바르지 않습니다.")
    if not isinstance(workspace.current_step, WorkspaceStep):
        raise InvalidWorkspaceError("지원하는 작업 단계가 필요합니다.")
    if not isinstance(workspace.saved_at, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", workspace.saved_at
    ):
        raise InvalidWorkspaceError("UTC 저장 시각 형식이 올바르지 않습니다.")
    try:
        datetime.strptime(workspace.saved_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise InvalidWorkspaceError("UTC 저장 시각 값이 올바르지 않습니다.") from None
    _metadata_text(workspace.source_scope, optional=True)
    _metadata_text(workspace.selected_sheet_name, optional=True)
    if type(workspace.column_mappings) is not tuple:
        raise InvalidWorkspaceError("컬럼 매핑 목록은 tuple이어야 합니다.")
    positions = (workspace.header_start_row, workspace.header_end_row, workspace.data_start_row)
    if workspace.current_step == WorkspaceStep.FILE_SELECTED:
        if (
            workspace.selected_sheet_name is not None
            or any(p is not None for p in positions)
            or (workspace.column_mappings)
        ):
            raise InvalidWorkspaceError("파일 선택 단계에는 시트/헤더/매핑이 없어야 합니다.")
    else:
        if workspace.selected_sheet_name is None or not all(_positive(p) for p in positions):
            raise InvalidWorkspaceError("선택한 시트와 헤더/데이터 행이 필요합니다.")
        start, end, data_start = positions
        if not 1 <= start <= end < data_start <= 1048577 or end > 1048576:
            raise InvalidWorkspaceError("헤더/데이터 시작 행 범위가 올바르지 않습니다.")
        if workspace.current_step == WorkspaceStep.HEADER_CONFIGURED and workspace.column_mappings:
            raise InvalidWorkspaceError("헤더 설정 단계에는 매핑을 저장하지 않습니다.")
    try:
        validate_mappings(workspace.column_mappings)
    except InvalidMappingError:
        raise InvalidWorkspaceError("Workspace 컬럼 매핑 구조가 올바르지 않습니다.") from None
    for mapping in workspace.column_mappings:
        _metadata_text(mapping.source_header, blank=True)
        _metadata_text(mapping.source_scope, optional=True)
        if mapping.source_scope != workspace.source_scope:
            raise InvalidWorkspaceError("Workspace와 컬럼의 source_scope가 다릅니다.")
        for part in mapping.source_header_parts:
            if not workspace.header_start_row <= part.row_index <= workspace.header_end_row:
                raise InvalidWorkspaceError("헤더 part가 지정한 헤더 범위를 벗어났습니다.")
            _metadata_text(part.text, optional=True, blank=True)
            _metadata_text(part.anchor_text, optional=True, blank=True)
            _metadata_text(part.merged_range, optional=True)


def _exact_keys(data, model):
    if type(data) is not dict or set(data) != {field.name for field in fields(model)}:
        raise InvalidWorkspaceError("Workspace에 알 수 없거나 누락된 필드가 있습니다.")


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidWorkspaceError("Workspace JSON에 중복 필드가 있습니다.")
        result[key] = value
    return result


def _decode(payload, current_user_id):
    try:
        data = json.loads(payload, object_pairs_hook=_no_duplicate_keys)
        if type(data) is not dict or "workspace_version" not in data:
            raise InvalidWorkspaceError("Workspace 버전 필드가 필요합니다.")
        if (
            type(data["workspace_version"]) is not int
            or data["workspace_version"] != WORKSPACE_VERSION
        ):
            raise UnsupportedWorkspaceVersionError("지원하지 않는 Workspace 버전입니다.")
        _exact_keys(data, WorkspaceDraft)
        if type(data["column_mappings"]) is not list:
            raise InvalidWorkspaceError("Workspace 매핑 배열이 필요합니다.")
        mappings = []
        for raw in data["column_mappings"]:
            _exact_keys(raw, ColumnMappingDraft)
            if type(raw["source_header_parts"]) is not list:
                raise InvalidWorkspaceError("Workspace 헤더 part 배열이 필요합니다.")
            parts = []
            for part in raw["source_header_parts"]:
                _exact_keys(part, MappingHeaderPart)
                parts.append(MappingHeaderPart(**part))
            mappings.append(
                ColumnMappingDraft(
                    **{
                        **raw,
                        "source_header_parts": tuple(parts),
                        "mapping_status": MappingStatus(raw["mapping_status"]),
                        "mapping_method": MappingMethod(raw["mapping_method"]),
                    }
                )
            )
        workspace = WorkspaceDraft(
            **{
                **data,
                "column_mappings": tuple(mappings),
                "current_step": WorkspaceStep(data["current_step"]),
            }
        )
    except (ValueError, TypeError, RecursionError):
        raise InvalidWorkspaceError("Workspace JSON을 해석할 수 없습니다.") from None
    _validate(workspace, current_user_id)
    return workspace


def _source_hash(path):
    try:
        if not path.exists():
            raise WorkspaceSourceMissingError("원본 파일이 없어 재개할 수 없습니다.")
        if not path.is_file():
            raise InvalidWorkspaceError("원본 경로가 일반 파일이 아닙니다.")
        before = path.stat()
        digest = file_sha256(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise WorkspaceSourceChangedError("검증 중 원본 파일이 변경되었습니다.")
        return digest
    except OSError:
        raise WorkspaceIOError("원본 파일을 읽을 수 없습니다.") from None


class WorkspaceService:
    """사용자당 하나의 draft. 테스트는 tmp_path 기반 workspace_dir를 명시한다."""

    def __init__(self, workspace_dir: Path | None = None):
        try:
            root = get_app_paths().workspace_dir if workspace_dir is None else Path(workspace_dir)
            if not root.is_absolute():
                raise InvalidWorkspaceError("Workspace 저장 위치는 절대경로여야 합니다.")
            self._root = root.resolve()
            if any((parent / ".git").exists() for parent in (self._root, *self._root.parents)):
                raise InvalidWorkspaceError("Workspace는 Git repository 내부에 저장하지 않습니다.")
        except (OSError, ValueError, TypeError, RuntimeError):
            raise WorkspaceIOError("Workspace 저장 위치를 확인할 수 없습니다.") from None

    def _path(self, user_id):
        if not _positive(user_id):
            raise InvalidWorkspaceError("양의 사용자 ID가 필요합니다.")
        path = self._root / f"user_{user_id}.json"
        try:
            if (
                self._root.resolve() != self._root
                or path.is_symlink()
                or not path.resolve().is_relative_to(self._root)
            ):
                raise WorkspaceIOError("Workspace 경로 연결이 변경되었습니다.")
        except (OSError, RuntimeError):
            raise WorkspaceIOError("Workspace 경로를 확인할 수 없습니다.") from None
        return path

    def create_workspace(
        self,
        *,
        current_user_id,
        source_file_path,
        selected_sheet_name=None,
        header_start_row=None,
        header_end_row=None,
        data_start_row=None,
        column_mappings=(),
        current_step=WorkspaceStep.FILE_SELECTED,
        source_scope=None,
    ):
        try:
            path = Path(source_file_path).absolute()
        except (TypeError, ValueError, OSError):
            raise InvalidWorkspaceError("원본 파일 경로가 올바르지 않습니다.") from None
        # metadata 먼저 검증하여 불필요한 원본 접근을 피한다.
        draft = WorkspaceDraft(
            WORKSPACE_VERSION,
            current_user_id,
            str(path),
            "0" * 64,
            selected_sheet_name,
            header_start_row,
            header_end_row,
            data_start_row,
            tuple(column_mappings),
            current_step,
            utc_now_text(),
            source_scope,
        )
        _validate(draft, current_user_id)
        return replace(draft, source_file_sha256=_source_hash(path))

    def save_workspace(self, workspace: WorkspaceDraft, current_user_id: int):
        _validate(workspace, current_user_id)
        path = self._path(current_user_id)
        if _source_hash(Path(workspace.source_file_path)) != workspace.source_file_sha256:
            raise WorkspaceSourceChangedError("원본 hash가 달라 작업을 저장할 수 없습니다.")
        saved = replace(workspace, saved_at=utc_now_text())
        payload = json.dumps(asdict(saved), ensure_ascii=False, allow_nan=False, indent=2).encode(
            "utf-8"
        )
        if len(payload) > MAX_WORKSPACE_BYTES:
            raise InvalidWorkspaceError("Workspace metadata 크기 제한을 초과했습니다.")
        temporary = None
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self._path(current_user_id)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self._root,
                prefix=f".user_{current_user_id}_",
                suffix=".tmp",
                delete=False,
            ) as target:
                temporary = Path(target.name)
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        except OSError:
            raise WorkspaceIOError("Workspace를 저장할 수 없습니다.") from None
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    raise WorkspaceIOError("Workspace 임시 파일을 정리할 수 없습니다.") from None
        return saved

    def load_workspace(self, current_user_id: int):
        """소유권·JSON·원본을 검증한다. 사전 재검증은 ColumnMappingService가 조정한다."""
        path = self._path(current_user_id)
        try:
            if not path.exists():
                return None
            with path.open("rb") as source:
                payload = source.read(MAX_WORKSPACE_BYTES + 1)
        except OSError:
            raise WorkspaceIOError("Workspace를 읽을 수 없습니다.") from None
        if len(payload) > MAX_WORKSPACE_BYTES:
            raise InvalidWorkspaceError("Workspace metadata 크기 제한을 초과했습니다.")
        workspace = _decode(payload, current_user_id)
        if _source_hash(Path(workspace.source_file_path)) != workspace.source_file_sha256:
            raise WorkspaceSourceChangedError("원본 hash가 달라 자동 재개할 수 없습니다.")
        return workspace

    def delete_workspace(self, user_id: int):
        # 사용자당 고정된 단일 JSON만 제거한다. 원본/DB/다른 작업 파일은 건드리지 않는다.
        path = self._path(user_id)
        try:
            if not path.exists():
                return False
            path.unlink()
        except OSError:
            raise WorkspaceIOError("Workspace를 삭제할 수 없습니다.") from None
        return True
