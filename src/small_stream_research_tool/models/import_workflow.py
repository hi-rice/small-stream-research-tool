"""10B 화면에 전달할 파일 구조와 비공개 workflow identity."""

from dataclasses import dataclass, field

from small_stream_research_tool.models.phase10_read import DuplicateImportSummary


@dataclass(frozen=True)
class SheetSummary:
    name: str
    index: int
    row_count: int | None
    column_count: int | None
    state: str
    kind: str
    has_cells: bool

    @property
    def selectable(self):
        return self.kind == "worksheet" and self.has_cells


@dataclass(frozen=True)
class HeaderColumnSummary:
    index: int
    letter: str
    text: str


@dataclass(frozen=True)
class ImportWorkflowState:
    source_path: str = field(repr=False)
    file_hash: str = field(repr=False)
    file_name: str
    file_size: int
    sheets: tuple[SheetSummary, ...]
    duplicates: tuple[DuplicateImportSummary, ...]
    selected_sheet: str | None = None
    header_start_row: int | None = None
    header_end_row: int | None = None
    data_start_row: int | None = None
    columns: tuple[HeaderColumnSummary, ...] = ()
    workspace_saved_at: str | None = None


class ImportInspectionError(Exception):
    def __init__(self, message="Excel 파일을 확인하지 못했습니다."):
        super().__init__(message)
