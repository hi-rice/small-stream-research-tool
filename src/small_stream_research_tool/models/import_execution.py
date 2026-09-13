"""단일 시트 Import 실행 입력과 불변 결과. 원본 payload는 repr에서 제외한다."""

from dataclasses import dataclass, field

from small_stream_research_tool.models.column_mapping import ColumnMappingDraft
from small_stream_research_tool.models.import_preparation import ImportPreparationResult


@dataclass(frozen=True)
class SourceFileSnapshot:
    file_name: str = field(repr=False)
    original_path: str = field(repr=False)
    file_extension: str | None = field(default=None, repr=False)
    file_size: int | None = None
    file_hash: str | None = field(default=None, repr=False)
    file_modified_at: str | None = field(default=None, repr=False)
    source_description: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ImportSheetSnapshot:
    sheet_name: str = field(repr=False)
    header_start_row: int
    header_end_row: int
    data_start_row: int
    sheet_index: int | None = None


@dataclass(frozen=True)
class ImportExecutionRequest:
    source: SourceFileSnapshot = field(repr=False)
    sheet: ImportSheetSnapshot = field(repr=False)
    preparation: ImportPreparationResult = field(repr=False)
    column_mappings: tuple[ColumnMappingDraft, ...] = field(repr=False)
    current_user_id: int
    dictionary_version_id: int | None = None
    batch_code: str | None = field(default=None, repr=False)
    reference_year: int | None = None


@dataclass(frozen=True)
class ImportExecutionResult:
    import_id: int | None
    source_file_id: int | None
    batch_code: str = field(repr=False)
    status: str
    data_committed: bool
    ready_rows: int
    excluded_rows: int
    created_stream_count: int
    reused_stream_count: int
    characteristic_value_count: int
    started_at: str
    finished_at: str | None
