"""DB 매핑 이력과 구분되는 작업 중 컬럼 매핑 metadata."""

from dataclasses import dataclass
from enum import StrEnum


class MappingStatus(StrEnum):
    AUTO_MAPPED = "AUTO_MAPPED"
    USER_MAPPED = "USER_MAPPED"
    UNMAPPED = "UNMAPPED"
    DO_NOT_MAP = "DO_NOT_MAP"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class MappingMethod(StrEnum):
    AUTO_ALIAS = "AUTO_ALIAS"
    USER = "USER"
    NONE = "NONE"


@dataclass(frozen=True)
class MappingHeaderPart:
    row_index: int
    text: str | None
    anchor_row: int | None
    anchor_column: int | None
    anchor_text: str | None
    merged_range: str | None


@dataclass(frozen=True)
class ColumnMappingDraft:
    source_column_index: int
    source_column_letter: str
    source_header: str
    source_header_parts: tuple[MappingHeaderPart, ...]
    dictionary_id: int | None = None
    mapping_method: MappingMethod = MappingMethod.NONE
    mapping_status: MappingStatus = MappingStatus.UNMAPPED
    source_scope: str | None = None


@dataclass(frozen=True)
class MappingSummary:
    total_columns: int
    auto_mapped: int
    user_mapped: int
    unmapped: int
    do_not_map: int
    needs_review: int
