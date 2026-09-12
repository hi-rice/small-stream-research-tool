"""런타임 Preview와 일반 표시 payload를 구분한다. Workspace 저장 대상이 아니다."""

from dataclasses import dataclass, field
from enum import StrEnum

from small_stream_research_tool.models.excel import ExcelCell, ExcelValue
from small_stream_research_tool.models.stream_code import (
    ComparisonStatus,
    StreamCodeValidationResult,
)


class PreviewStatus(StrEnum):
    NEW_STREAM = "NEW_STREAM"
    EXISTING_STREAM = "EXISTING_STREAM"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    EXCLUDED = "EXCLUDED"


@dataclass(frozen=True)
class PreviewFieldPolicy:
    excluded_internal_names: frozenset[str] = frozenset()
    masked_internal_names: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ImportPreviewIssue:
    code: str
    message: str
    blocking: bool
    source_column_index: int | None = None


@dataclass(frozen=True)
class PreviewMappedValue:
    source_column_index: int
    dictionary_id: int
    internal_name: str
    cell: ExcelCell = field(repr=False)


@dataclass(frozen=True)
class PreviewDisplayValue:
    source_column_index: int
    internal_name: str
    value: ExcelValue


@dataclass(frozen=True)
class ImportPreviewDisplayRow:
    source_row: int
    status: PreviewStatus
    source_code: str | None
    generated_code: str | None
    effective_code: str | None
    comparison_status: ComparisonStatus
    stream_name: str | None
    display_values: tuple[PreviewDisplayValue, ...]
    issues: tuple[ImportPreviewIssue, ...]
    existing_stream_found: bool | None


@dataclass(frozen=True)
class ImportPreviewRow:
    source_row: int
    status: PreviewStatus
    stream_code: str | None
    stream_name: str | None
    stream_code_validation: StreamCodeValidationResult = field(repr=False)
    mapped_values: tuple[PreviewMappedValue, ...] = field(repr=False)
    display_values: tuple[PreviewDisplayValue, ...]
    issues: tuple[ImportPreviewIssue, ...]
    excluded: bool
    existing_stream_found: bool | None

    def to_display(self) -> ImportPreviewDisplayRow:
        """UI에는 이 payload만 전달한다. 내부 raw mapped_values를 직렬화하지 않는다."""
        validation = self.stream_code_validation
        return ImportPreviewDisplayRow(
            self.source_row,
            self.status,
            validation.normalized_source_code,
            validation.generated_code,
            self.stream_code,
            validation.comparison_status,
            self.stream_name,
            self.display_values,
            self.issues,
            self.existing_stream_found,
        )


@dataclass(frozen=True)
class ImportPreviewSummary:
    total_rows: int
    new_stream: int
    existing_stream: int
    needs_review: int
    excluded: int


@dataclass(frozen=True)
class ImportPreviewResult:
    rows: tuple[ImportPreviewRow, ...]
    summary: ImportPreviewSummary
