"""10B Workspace에서 10C 매핑·Preview까지 조정한다. 연구 DB는 읽기만 한다."""

import hashlib
import re
from contextlib import closing
from dataclasses import replace

from small_stream_research_tool.database import connect_database
from small_stream_research_tool.models.column_mapping import MappingStatus
from small_stream_research_tool.models.import_mapping_workflow import (
    MappingCandidate,
    MappingRow,
    MappingWorkflowError,
    MappingWorkflowState,
    PreviewRowSummary,
    PreviewSummary,
)
from small_stream_research_tool.models.import_preparation import PreparationStatus
from small_stream_research_tool.models.import_preview import PreviewStatus
from small_stream_research_tool.models.import_workflow import ImportWorkflowState
from small_stream_research_tool.models.workspace import WorkspaceStep
from small_stream_research_tool.models.workspace_errors import (
    WorkspaceSourceChangedError,
    WorkspaceSourceMissingError,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.stream_lookup_repository import StreamLookupRepository
from small_stream_research_tool.services.app_read_service import AppReadService
from small_stream_research_tool.services.column_mapping_service import ColumnMappingService
from small_stream_research_tool.services.dictionary_service import DictionaryService
from small_stream_research_tool.services.excel_reader import ExcelReader
from small_stream_research_tool.services.import_inspection_service import ImportInspectionService
from small_stream_research_tool.services.import_preparation_service import ImportPreparationService
from small_stream_research_tool.services.import_preview_service import ImportPreviewService
from small_stream_research_tool.services.phase10_import_policy_service import (
    Phase10ImportPolicyService,
)
from small_stream_research_tool.services.workspace_service import WorkspaceService
from small_stream_research_tool.utils.file_hash import file_sha256

NATIONAL_SCOPE = "NATIONAL_2024"
PREVIEW_DISPLAY_LIMIT = 50
_SENSITIVE_HEADER = re.compile(
    r"service[ _-]?key|api[ _-]?key|password|passwd|secret|token|credential|"
    r"cctv|rtsp|(?:public|private)[ _-]?ip|(?:^|[ _-])ip(?:$|[ _-])|"
    r"연락처|전화번호|휴대전화|비밀번호|인증정보|접속정보|서비스[ _-]?(?:키|key)|이메일|"
    r"공인[ _-]?ip|사설[ _-]?ip|업체|담당자",
    re.IGNORECASE,
)
_STATUS_LABELS = {
    MappingStatus.AUTO_MAPPED: "자동 매핑 제안",
    MappingStatus.USER_MAPPED: "사용자 매핑",
    MappingStatus.UNMAPPED: "미매핑",
    MappingStatus.DO_NOT_MAP: "가져오지 않음",
    MappingStatus.NEEDS_REVIEW: "확인 필요",
}
_PREVIEW_LABELS = {
    PreviewStatus.NEW_STREAM: "신규 소하천",
    PreviewStatus.EXISTING_STREAM: "기존 소하천",
    PreviewStatus.NEEDS_REVIEW: "확인 필요",
    PreviewStatus.EXCLUDED: "제외",
}
_PREPARATION_LABELS = {
    PreparationStatus.READY: "준비 가능",
    PreparationStatus.BLOCKED: "차단",
    PreparationStatus.EXCLUDED: "제외",
}
_ISSUE_LABELS = {
    "IDENTITY_MAPPING_INCOMPLETE": "관리코드 매핑이 부족합니다.",
    "IDENTITY_UNAVAILABLE": "관리코드를 안전하게 확인할 수 없습니다.",
    "MAPPING_NEEDS_REVIEW": "매핑을 다시 확인해야 합니다.",
    "DUPLICATE_SEMANTIC_MAPPING": "같은 표준항목에 여러 열이 연결되었습니다.",
    "PREVIEW_BLOCKED": "Preview 차단 사유를 확인해 주세요.",
    "COMPONENTS_REQUIRED": "신규 하천의 구성코드가 필요합니다.",
    "STREAM_NAME_REQUIRED": "신규 하천의 원본 하천명이 필요합니다.",
    "NO_CHARACTERISTIC_VALUES": "기존 하천에 저장할 특성값이 없습니다.",
}


def _safe_header(column):
    header = column.display_header
    if not _SENSITIVE_HEADER.search(header):
        return column, False
    # Workspace에는 민감 원본 헤더도 저장하지 않는다. digest는 재개 시 구조 비교용이다.
    marker = "제외 대상 열 " + hashlib.sha256(header.encode("utf-8")).hexdigest()
    return replace(column, display_header=marker, header_parts=()), True


def _identity(mapping):
    return (
        mapping.source_column_index,
        mapping.source_column_letter,
        mapping.source_header,
        mapping.source_header_parts,
        mapping.source_scope,
    )


class ImportMappingWorkflowService:
    def __init__(self, db_path, workspace_dir=None):
        self._db_path = db_path
        self._workspace_dir = workspace_dir
        self._inspection = ImportInspectionService(db_path, workspace_dir)

    def _source(self, state, draft):
        if (
            type(state) is not ImportWorkflowState
            or not state.columns
            or state.workspace_saved_at is None
            or state.source_path != draft.source_file_path
            or state.file_hash != draft.source_file_sha256
            or state.selected_sheet != draft.selected_sheet_name
            or state.header_start_row != draft.header_start_row
            or state.header_end_row != draft.header_end_row
            or state.data_start_row != draft.data_start_row
            or state.workspace_saved_at != draft.saved_at
        ):
            raise MappingWorkflowError(
                "저장된 파일 구조와 현재 작업이 다릅니다. 다시 확인해 주세요."
            )
        inspected = self._inspection.inspect(state.source_path)
        if inspected.file_hash != state.file_hash:
            raise MappingWorkflowError(
                "원본 파일이 변경되었습니다. 파일 구조부터 다시 확인해 주세요."
            )
        verified = self._inspection.structure(
            inspected,
            state.selected_sheet,
            state.header_start_row,
            state.header_end_row,
            state.data_start_row,
        )
        if verified.columns != state.columns:
            raise MappingWorkflowError(
                "원본 헤더가 달라졌습니다. 파일 구조부터 다시 확인해 주세요."
            )
        return replace(verified, workspace_saved_at=draft.saved_at)

    @staticmethod
    def _dictionary(connection):
        if AppReadService(connection).get_home_summary().dictionary_state != "READY":
            raise MappingWorkflowError("연구 사전을 확인해야 컬럼 매핑을 진행할 수 있습니다.")
        repository = DictionaryRepository(connection)
        dictionary = DictionaryService(repository)
        policies = Phase10ImportPolicyService(connection).policies()
        candidates = []
        for item in repository.list_items(active_only=True):
            if (
                item.deprecated_version_id is not None
                or item.internal_name not in policies.approved_internal_names
            ):
                continue
            category = repository.get_category(item.category_id)
            unit = repository.get_unit(item.unit_id) if item.unit_id is not None else None
            if (
                category is None
                or not category.is_active
                or (unit is not None and not unit.is_active)
            ):
                continue
            candidates.append(
                MappingCandidate(
                    item.dictionary_id,
                    item.standard_name,
                    category.category_name,
                    unit.unit_symbol if unit else "—",
                )
            )
        candidates.sort(key=lambda candidate: (candidate.category, candidate.label))
        return dictionary, policies, tuple(candidates)

    @staticmethod
    def _columns(source):
        with ExcelReader(source.source_path) as reader:
            raw = reader.read_columns(
                source.selected_sheet,
                header_start_row=source.header_start_row,
                header_end_row=source.header_end_row,
            )
        if file_sha256(source.source_path) != source.file_hash:
            raise MappingWorkflowError("원본 파일이 변경되었습니다. 다시 확인해 주세요.")
        return tuple(_safe_header(column) for column in raw)

    @staticmethod
    def _rows(mappings, candidates):
        targets = {item.dictionary_id: item for item in candidates}
        result = []
        for mapping in mappings:
            candidate = targets.get(mapping.dictionary_id)
            sensitive = mapping.source_header.startswith("제외 대상 열 ")
            result.append(
                MappingRow(
                    mapping.source_column_index,
                    mapping.source_column_letter,
                    "제외 대상 열" if sensitive else mapping.source_header,
                    _STATUS_LABELS[mapping.mapping_status],
                    candidate.label if candidate else "—",
                    (candidate.unit if candidate else "—"),
                    sensitive,
                )
            )
        return tuple(result)

    def start(self, source, user_id):
        try:
            workspace = WorkspaceService(self._workspace_dir)
            draft = workspace.load_workspace(user_id)
            if draft is None or draft.current_step == WorkspaceStep.FILE_SELECTED:
                raise MappingWorkflowError("먼저 파일 구조를 저장해 주세요.")
            source = self._source(source, draft)
            columns = self._columns(source)
            with closing(connect_database(self._db_path)) as connection:
                dictionary, policies, candidates = self._dictionary(connection)
                service = ColumnMappingService(dictionary)
                initial = service.build_initial_mappings(
                    (column for column, _sensitive in columns), draft.source_scope
                )
                allowed_ids = {item.dictionary_id for item in candidates}
                initial = tuple(
                    service.mark_do_not_map(mapping)
                    if sensitive
                    else service.clear_mapping(mapping)
                    if mapping.dictionary_id is not None
                    and mapping.dictionary_id not in allowed_ids
                    else mapping
                    for mapping, (_column, sensitive) in zip(initial, columns, strict=True)
                )
                if draft.current_step == WorkspaceStep.HEADER_CONFIGURED:
                    mappings = initial
                    draft = workspace.save_workspace(
                        replace(
                            draft,
                            column_mappings=mappings,
                            current_step=WorkspaceStep.MAPPING,
                            source_scope=draft.source_scope,
                        ),
                        user_id,
                    )
                else:
                    mappings = service.revalidate_mappings(draft.column_mappings)
                    if len(mappings) != len(initial) or any(
                        _identity(current) != _identity(expected)
                        for current, expected in zip(mappings, initial, strict=True)
                    ):
                        raise MappingWorkflowError(
                            "원본 열 또는 헤더가 달라졌습니다. 파일 구조를 다시 확인해 주세요."
                        )
                    mappings = tuple(
                        replace(mapping, mapping_status=MappingStatus.NEEDS_REVIEW)
                        if mapping.dictionary_id is not None
                        and mapping.dictionary_id not in allowed_ids
                        else mapping
                        for mapping in mappings
                    )
                source = replace(source, workspace_saved_at=draft.saved_at)
                return MappingWorkflowState(
                    source,
                    mappings,
                    candidates,
                    self._rows(mappings, candidates),
                    draft.saved_at,
                    source_scope=draft.source_scope,
                )
        except MappingWorkflowError:
            raise
        except (WorkspaceSourceChangedError, WorkspaceSourceMissingError):
            raise MappingWorkflowError(
                "원본 파일을 확인할 수 없습니다. 파일 구조부터 다시 확인해 주세요."
            ) from None
        except Exception:
            raise MappingWorkflowError("컬럼 매핑 작업을 시작할 수 없습니다.") from None

    def resume(self, user_id):
        try:
            source = self._inspection.resume(user_id)
            return self.start(source, user_id)
        except MappingWorkflowError:
            raise
        except Exception:
            raise MappingWorkflowError("저장된 매핑을 다시 확인할 수 없습니다.") from None

    def set_scope(self, state, scope, user_id):
        if type(state) is not MappingWorkflowState or scope not in (None, NATIONAL_SCOPE):
            raise MappingWorkflowError("지원하는 자료 범위를 선택해 주세요.")
        try:
            workspace = WorkspaceService(self._workspace_dir)
            draft = workspace.load_workspace(user_id)
            if draft is None or draft.column_mappings != state.mappings:
                raise MappingWorkflowError("저장된 매핑을 다시 확인해 주세요.")
            source = self._source(state.source, draft)
            columns = self._columns(source)
            with closing(connect_database(self._db_path)) as connection:
                dictionary, _policies, candidates = self._dictionary(connection)
                service = ColumnMappingService(dictionary)
                initial = service.build_initial_mappings(
                    (column for column, _sensitive in columns), scope
                )
                allowed_ids = {candidate.dictionary_id for candidate in candidates}
                mappings = []
                for old, fresh, (_column, sensitive) in zip(
                    state.mappings, initial, columns, strict=True
                ):
                    if sensitive:
                        mappings.append(service.mark_do_not_map(fresh))
                    elif old.mapping_status == MappingStatus.DO_NOT_MAP:
                        mappings.append(service.mark_do_not_map(fresh))
                    elif old.mapping_status == MappingStatus.USER_MAPPED:
                        mappings.append(
                            service.set_user_mapping(fresh, old.dictionary_id)
                            if old.dictionary_id in allowed_ids
                            else fresh
                        )
                    elif fresh.dictionary_id is not None and fresh.dictionary_id not in allowed_ids:
                        mappings.append(service.clear_mapping(fresh))
                    else:
                        mappings.append(fresh)
                saved = workspace.save_workspace(
                    replace(
                        draft,
                        column_mappings=tuple(mappings),
                        current_step=WorkspaceStep.MAPPING,
                        source_scope=scope,
                    ),
                    user_id,
                )
                source = replace(source, workspace_saved_at=saved.saved_at)
                return MappingWorkflowState(
                    source,
                    tuple(mappings),
                    candidates,
                    self._rows(mappings, candidates),
                    saved.saved_at,
                    source_scope=scope,
                )
        except MappingWorkflowError:
            raise
        except Exception:
            raise MappingWorkflowError("자료 범위를 적용하지 못했습니다.") from None

    def update(self, state, index, action, dictionary_id, user_id):
        if type(state) is not MappingWorkflowState or type(index) is not int:
            raise MappingWorkflowError()
        try:
            workspace = WorkspaceService(self._workspace_dir)
            draft = workspace.load_workspace(user_id)
            if (
                draft is None
                or draft.saved_at != state.saved_at
                or draft.column_mappings != state.mappings
            ):
                raise MappingWorkflowError("작업 상태가 변경되었습니다. 다시 열어 주세요.")
            source = self._source(state.source, draft)
            with closing(connect_database(self._db_path)) as connection:
                dictionary, _policies, candidates = self._dictionary(connection)
                mapping_service = ColumnMappingService(dictionary)
                mappings = list(mapping_service.revalidate_mappings(state.mappings))
                if action == "auto":
                    mappings = list(mapping_service.refresh_auto_mappings(mappings))
                    allowed_ids = {candidate.dictionary_id for candidate in candidates}
                    mappings = [
                        mapping_service.clear_mapping(mapping)
                        if mapping.dictionary_id is not None
                        and mapping.dictionary_id not in allowed_ids
                        else mapping
                        for mapping in mappings
                    ]
                else:
                    position = next(
                        (
                            i
                            for i, mapping in enumerate(mappings)
                            if mapping.source_column_index == index
                        ),
                        None,
                    )
                    if position is None or mappings[position].source_header.startswith(
                        "제외 대상 열 "
                    ):
                        raise MappingWorkflowError("선택한 원본 열을 매핑할 수 없습니다.")
                if action == "map":
                    if dictionary_id not in {candidate.dictionary_id for candidate in candidates}:
                        raise MappingWorkflowError("허용된 연구 사전 항목을 선택해 주세요.")
                    mappings[position] = mapping_service.set_user_mapping(
                        mappings[position], dictionary_id
                    )
                elif action == "exclude":
                    mappings[position] = mapping_service.mark_do_not_map(mappings[position])
                elif action == "clear":
                    mappings[position] = mapping_service.clear_mapping(mappings[position])
                elif action == "auto":
                    pass
                else:
                    raise MappingWorkflowError("지원하지 않는 매핑 작업입니다.")
                saved = workspace.save_workspace(
                    replace(
                        draft,
                        column_mappings=tuple(mappings),
                        current_step=WorkspaceStep.MAPPING,
                    ),
                    user_id,
                )
                source = replace(source, workspace_saved_at=saved.saved_at)
                return MappingWorkflowState(
                    source,
                    tuple(mappings),
                    candidates,
                    self._rows(mappings, candidates),
                    saved.saved_at,
                    source_scope=state.source_scope,
                )
        except MappingWorkflowError:
            raise
        except (WorkspaceSourceChangedError, WorkspaceSourceMissingError):
            raise MappingWorkflowError(
                "원본 파일을 확인할 수 없습니다. 파일 구조부터 다시 확인해 주세요."
            ) from None
        except Exception:
            raise MappingWorkflowError("매핑 변경을 저장하지 못했습니다.") from None

    def preview(self, state, user_id):
        if type(state) is not MappingWorkflowState or state.saved_at is None:
            raise MappingWorkflowError("먼저 컬럼 매핑을 저장해 주세요.")
        try:
            workspace = WorkspaceService(self._workspace_dir)
            draft = workspace.load_workspace(user_id)
            if draft is None or draft.saved_at != state.saved_at:
                raise MappingWorkflowError("저장된 매핑을 다시 확인해 주세요.")
            source = self._source(state.source, draft)
            self._columns(source)
            if draft.column_mappings != state.mappings:
                raise MappingWorkflowError("현재 매핑과 저장된 작업이 다릅니다.")
            with closing(connect_database(self._db_path)) as connection:
                dictionary, policies, candidates = self._dictionary(connection)
                mappings = ColumnMappingService(dictionary).revalidate_mappings(state.mappings)
                if mappings != state.mappings:
                    raise MappingWorkflowError("연구 사전 매핑을 다시 확인해 주세요.")
                preview_service = ImportPreviewService(
                    dictionary, StreamLookupRepository(connection)
                )
                preparation = ImportPreparationService(dictionary)
                counts = {status: 0 for status in PreparationStatus}
                displayed = []
                with ExcelReader(source.source_path) as reader:
                    rows = reader.iter_rows(
                        source.selected_sheet,
                        header_start_row=source.header_start_row,
                        header_end_row=source.header_end_row,
                        data_start_row=source.data_start_row,
                    )
                    for preview_row in preview_service.iter_preview_rows(
                        rows, mappings, field_policy=policies.preview
                    ):
                        prepared = preparation.prepare_row(
                            preview_row, field_policy=policies.import_fields
                        )
                        counts[prepared.status] += 1
                        if len(displayed) < PREVIEW_DISPLAY_LIMIT:
                            issues = tuple(
                                f"{issue.code}: "
                                f"{_ISSUE_LABELS.get(issue.code, '원본 행을 확인해 주세요.')}"
                                for issue in (*preview_row.issues, *prepared.issues)
                            )
                            displayed.append(
                                PreviewRowSummary(
                                    preview_row.source_row,
                                    preview_row.stream_code or "—",
                                    _PREVIEW_LABELS[preview_row.status],
                                    _PREPARATION_LABELS[prepared.status],
                                    issues[:4],
                                )
                            )
                if file_sha256(source.source_path) != source.file_hash:
                    raise MappingWorkflowError("Preview 중 원본 파일이 변경되었습니다.")
                total = sum(counts.values())
                unit_review = sum(
                    candidate.unit != "—" and candidate.dictionary_id == mapping.dictionary_id
                    for mapping in mappings
                    for candidate in candidates
                )
                ready = (
                    counts[PreparationStatus.READY] > 0 and counts[PreparationStatus.BLOCKED] == 0
                )
                saved = workspace.save_workspace(
                    replace(draft, current_step=WorkspaceStep.PREVIEW), user_id
                )
                source = replace(source, workspace_saved_at=saved.saved_at)
                return replace(
                    state,
                    source=source,
                    saved_at=saved.saved_at,
                    preview=PreviewSummary(
                        total,
                        counts[PreparationStatus.READY],
                        counts[PreparationStatus.BLOCKED],
                        counts[PreparationStatus.EXCLUDED],
                        tuple(displayed),
                        ready,
                        unit_review,
                    ),
                )
        except MappingWorkflowError:
            raise
        except (WorkspaceSourceChangedError, WorkspaceSourceMissingError):
            raise MappingWorkflowError(
                "원본 파일을 확인할 수 없습니다. Preview를 다시 확인해 주세요."
            ) from None
        except Exception:
            raise MappingWorkflowError("Preview를 생성하지 못했습니다.") from None
