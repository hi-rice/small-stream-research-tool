"""연구값을 포함하지 않는 V1 작업 재개 metadata."""

from dataclasses import dataclass
from enum import StrEnum

from small_stream_research_tool.models.column_mapping import ColumnMappingDraft
from small_stream_research_tool.models.source_unit import SourceUnitConfirmation


class WorkspaceStep(StrEnum):
    FILE_SELECTED = "FILE_SELECTED"
    HEADER_CONFIGURED = "HEADER_CONFIGURED"
    MAPPING = "MAPPING"
    CODE_VALIDATION = "CODE_VALIDATION"
    PREVIEW = "PREVIEW"


@dataclass(frozen=True)
class WorkspaceDraft:
    workspace_version: int
    user_id: int
    source_file_path: str
    source_file_sha256: str
    selected_sheet_name: str | None
    header_start_row: int | None
    header_end_row: int | None
    data_start_row: int | None
    column_mappings: tuple[ColumnMappingDraft, ...]
    current_step: WorkspaceStep
    saved_at: str
    source_scope: str | None = None
    unit_confirmations: tuple[SourceUnitConfirmation, ...] = ()


@dataclass(frozen=True)
class WorkspaceResumeResult:
    original: WorkspaceDraft
    resumed: WorkspaceDraft
