"""DB/library 객체와 분리된 Excel 원본 구조. 모든 위치는 1-based다."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path


@dataclass(frozen=True)
class ExcelFormula:
    """문자열이 아닌 배열/데이터 테이블 수식의 원본 표현."""

    kind: str
    expression: str | None
    attributes: tuple[tuple[str, str], ...]


type ExcelValue = (
    str | int | float | bool | date | datetime | time | timedelta | ExcelFormula | None
)


@dataclass(frozen=True)
class ExcelWorkbookInfo:
    file_path: Path
    sheet_names: tuple[str, ...]

    @property
    def sheet_count(self) -> int:
        return len(self.sheet_names)


@dataclass(frozen=True)
class ExcelSheetInfo:
    name: str
    index: int
    max_row: int | None
    max_column: int | None
    merged_ranges: tuple[str, ...]
    state: str
    kind: str


@dataclass(frozen=True)
class ExcelCell:
    row_index: int
    column_index: int
    column_letter: str
    value: ExcelValue
    value_type: str
    is_formula: bool
    number_format: str

    @property
    def coordinate(self) -> str:
        return f"{self.column_letter}{self.row_index}"


@dataclass(frozen=True)
class ExcelHeaderPart:
    """cell은 실제 위치의 원본, merged_anchor는 실제 병합 영역의 좌상단."""

    cell: ExcelCell
    merged_anchor: ExcelCell | None
    merged_range: str | None

    @property
    def effective_value(self) -> ExcelValue:
        return self.merged_anchor.value if self.merged_anchor is not None else self.cell.value


@dataclass(frozen=True)
class ExcelColumn:
    column_index: int
    column_letter: str
    header_parts: tuple[ExcelHeaderPart, ...]
    display_header: str


@dataclass(frozen=True)
class ExcelRow:
    row_index: int
    cells: tuple[ExcelCell, ...]

    @property
    def is_blank(self) -> bool:
        return all(cell.value is None for cell in self.cells)


@dataclass(frozen=True)
class ExcelPreview:
    sheet: ExcelSheetInfo
    columns: tuple[ExcelColumn, ...]
    rows: tuple[ExcelRow, ...]
