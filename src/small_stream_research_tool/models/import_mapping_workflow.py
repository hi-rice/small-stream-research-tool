"""Phase 10C의 비공개 매핑 상태와 안전한 GUI 투영."""

from dataclasses import dataclass, field

from small_stream_research_tool.models.column_mapping import ColumnMappingDraft
from small_stream_research_tool.models.import_workflow import ImportWorkflowState
from small_stream_research_tool.models.source_unit import SourceUnitConfirmation


@dataclass(frozen=True)
class MappingCandidate:
    dictionary_id: int = field(repr=False)
    label: str = ""
    category: str = ""
    unit: str = ""
    internal_name: str = ""
    unit_id: int | None = field(default=None, repr=False)


@dataclass(frozen=True)
class UnitOption:
    unit_id: int = field(repr=False)
    symbol: str = ""


@dataclass(frozen=True)
class MappingRow:
    index: int
    letter: str
    header: str
    status: str
    target: str
    unit: str
    sensitive: bool
    source_unit: str = "—"
    unit_status: str = "—"


@dataclass(frozen=True)
class PreviewRowSummary:
    source_row: int
    stream_code: str
    identity_status: str
    preparation_status: str
    issues: tuple[str, ...]


@dataclass(frozen=True)
class PreviewSummary:
    total: int
    ready: int
    blocked: int
    excluded: int
    displayed: tuple[PreviewRowSummary, ...]
    ready_for_import_preparation: bool
    unit_review_count: int
    unit_mismatch_count: int = 0
    unit_unresolved_count: int = 0


@dataclass(frozen=True)
class MappingWorkflowState:
    source: ImportWorkflowState = field(repr=False)
    mappings: tuple[ColumnMappingDraft, ...] = field(repr=False)
    candidates: tuple[MappingCandidate, ...] = ()
    rows: tuple[MappingRow, ...] = ()
    saved_at: str | None = None
    preview: PreviewSummary | None = None
    source_scope: str | None = None
    unit_confirmations: tuple[SourceUnitConfirmation, ...] = field(default=(), repr=False)
    unit_options: tuple[UnitOption, ...] = ()


class MappingWorkflowError(Exception):
    def __init__(self, message="컬럼 매핑 작업을 확인할 수 없습니다."):
        super().__init__(message)
