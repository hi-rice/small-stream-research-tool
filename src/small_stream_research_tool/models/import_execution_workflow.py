"""Phase 10D GUI-safe import execution projections."""

from dataclasses import dataclass, field

from small_stream_research_tool.models.import_mapping_workflow import MappingWorkflowState
from small_stream_research_tool.models.import_preparation import (
    ImportFieldPolicy,
    ImportPreparationResult,
)


@dataclass(frozen=True)
class ImportExecutionSummary:
    file_name: str
    sheet_name: str
    total_rows: int
    ready_rows: int
    excluded_rows: int
    new_stream_rows: int
    existing_stream_rows: int
    prepared_value_count: int
    mapped_characteristic_count: int
    excluded_column_count: int
    unit_confirmation_complete: bool
    duplicate_success: bool
    recovery_required: bool


@dataclass(frozen=True)
class ImportExecutionPlan:
    summary: ImportExecutionSummary
    workflow_state: MappingWorkflowState = field(repr=False)
    preparation: ImportPreparationResult = field(repr=False)
    dictionary_version_id: int = field(repr=False)
    research_fingerprint: str = field(repr=False)
    evidence_fingerprint: str = field(repr=False)
    field_policy: ImportFieldPolicy = field(repr=False)


@dataclass(frozen=True)
class ImportExecutionOutcome:
    status: str
    file_name: str
    sheet_name: str
    ready_rows: int
    excluded_rows: int
    created_stream_count: int
    reused_stream_count: int
    characteristic_value_count: int
    started_at: str | None
    finished_at: str | None
    recovery_required: bool = False
    message: str = ""


class ImportExecutionWorkflowError(Exception):
    def __init__(self, message="가져오기 실행 조건을 다시 확인해야 합니다."):
        super().__init__(message)


class DuplicateImportConfirmationRequired(ImportExecutionWorkflowError):
    def __init__(self):
        super().__init__("동일한 내용의 파일을 이전에 가져온 기록이 있습니다.")


class RecoveryRequiredBeforeImport(ImportExecutionWorkflowError):
    def __init__(self):
        super().__init__("먼저 이전 가져오기 상태를 점검하거나 복구해야 합니다.")
