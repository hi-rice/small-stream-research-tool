"""저장 전 불변 후보. DB 레코드나 Workspace 직렬화 모델이 아니다."""

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from small_stream_research_tool.models.import_preparation_errors import (
    InvalidPreparationArgumentError,
)
from small_stream_research_tool.models.import_preview import PreviewStatus

TYPED_FIELDS = {
    "REAL": "value_number",
    "INTEGER": "value_integer",
    "TEXT": "value_text",
    "DATE": "value_date",
    "DATETIME": "value_date",
}
CORE_TEXT_FIELDS = frozenset(
    (
        "province_name",
        "city_county_name",
        "town_name",
        "river_system",
        "source_address",
        "end_address",
    )
)
CORE_COORDINATE_LIMITS = {
    "source_latitude": 90,
    "source_longitude": 180,
    "end_latitude": 90,
    "end_longitude": 180,
}


class PreparationStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    EXCLUDED = "EXCLUDED"


class RowAction(StrEnum):
    CREATE_STREAM = "CREATE_STREAM"
    USE_EXISTING_STREAM = "USE_EXISTING_STREAM"


def _positive(value, maximum):
    return type(value) is int and 1 <= value <= maximum


def _text(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


@dataclass(frozen=True)
class ImportFieldPolicy:
    excluded_internal_names: frozenset[str] = frozenset()

    def __post_init__(self):
        if type(self.excluded_internal_names) is not frozenset or any(
            not _text(name) or name != name.strip() for name in self.excluded_internal_names
        ):
            raise InvalidPreparationArgumentError("정확한 internal_name의 frozenset이 필요합니다.")


@dataclass(frozen=True)
class ImportPreparationIssue:
    code: str
    message: str
    blocking: bool
    source_row: int
    source_column_index: int | None = None
    dictionary_id: int | None = None


@dataclass(frozen=True)
class PreparedCharacteristicValue:
    dictionary_id: int
    data_type: str
    source_column_index: int
    source_row: int
    value_number: float | None = field(default=None, repr=False)
    value_integer: int | None = field(default=None, repr=False)
    value_text: str | None = field(default=None, repr=False)
    value_date: str | None = field(default=None, repr=False)
    original_value: str | None = field(default=None, repr=False)
    original_unit: str | None = field(default=None, repr=False)
    unit_id: int | None = None

    def __post_init__(self):
        values = (self.value_number, self.value_integer, self.value_text, self.value_date)
        if sum(value is not None for value in values) != 1:
            raise InvalidPreparationArgumentError("정확히 하나의 typed value가 필요합니다.")
        target = TYPED_FIELDS.get(self.data_type)
        if target is None or getattr(self, target) is None:
            raise InvalidPreparationArgumentError("사전 자료형과 typed value가 일치해야 합니다.")
        if not (
            _positive(self.dictionary_id, 2**63 - 1)
            and _positive(self.source_column_index, 16384)
            and _positive(self.source_row, 1048576)
            and (self.unit_id is None or _positive(self.unit_id, 2**63 - 1))
        ):
            raise InvalidPreparationArgumentError("사전 ID 또는 1-based 출처가 올바르지 않습니다.")
        value = getattr(self, target)
        valid = True
        if self.data_type == "REAL":
            valid = type(value) is float and math.isfinite(value)
        elif self.data_type == "INTEGER":
            valid = type(value) is int and -(2**63) <= value < 2**63
        elif self.data_type == "TEXT":
            valid = _text(value)
        else:
            try:
                if self.data_type == "DATE":
                    valid = (
                        isinstance(value, str) and date.fromisoformat(value).isoformat() == value
                    )
                else:
                    valid = (
                        isinstance(value, str)
                        and "T" in value
                        and datetime.fromisoformat(value).isoformat() == value
                    )
            except (ValueError, TypeError):
                valid = False
        if not valid:
            raise InvalidPreparationArgumentError("유효한 typed value가 필요합니다.")
        for original in (self.original_value, self.original_unit):
            if original is not None and not _text(original):
                raise InvalidPreparationArgumentError("원본 표현은 유효한 TEXT여야 합니다.")


@dataclass(frozen=True)
class PreparedStreamData:
    stream_code: str = field(repr=False)
    province_code: str = field(repr=False)
    city_county_code: str = field(repr=False)
    town_code: str = field(repr=False)
    stream_serial_no: str = field(repr=False)
    stream_name: str = field(repr=False)
    optional_fields: tuple[tuple[str, str | float], ...] = field(default=(), repr=False)

    def __post_init__(self):
        components = (
            self.province_code,
            self.city_county_code,
            self.town_code,
            self.stream_serial_no,
        )
        if any(
            not isinstance(value, str) or re.fullmatch(rf"[0-9]{{{width}}}", value) is None
            for value, width in zip(components, (2, 3, 3, 3), strict=True)
        ) or self.stream_code != "".join(components):
            raise InvalidPreparationArgumentError("관리코드와 네 구성요소가 일치해야 합니다.")
        if not _text(self.stream_name):
            raise InvalidPreparationArgumentError("신규 하천명이 필요합니다.")
        if type(self.optional_fields) is not tuple:
            raise InvalidPreparationArgumentError("불변 core 항목 목록이 필요합니다.")
        seen = set()
        for entry in self.optional_fields:
            if type(entry) is not tuple or len(entry) != 2:
                raise InvalidPreparationArgumentError("core 항목 형식이 올바르지 않습니다.")
            name, value = entry
            if name in seen:
                raise InvalidPreparationArgumentError("core 항목이 중복됩니다.")
            seen.add(name)
            if name in CORE_TEXT_FIELDS:
                valid = _text(value)
            elif name in CORE_COORDINATE_LIMITS:
                valid = (
                    type(value) is float
                    and math.isfinite(value)
                    and abs(value) <= CORE_COORDINATE_LIMITS[name]
                )
            else:
                valid = False
            if not valid:
                raise InvalidPreparationArgumentError("core 항목 또는 값이 올바르지 않습니다.")


@dataclass(frozen=True)
class PreparedImportRow:
    source_row: int
    stream_code: str | None = field(repr=False)
    stream_name: str | None = field(repr=False)
    row_action: RowAction | None
    status: PreparationStatus
    prepared_values: tuple[PreparedCharacteristicValue, ...] = field(repr=False)
    issues: tuple[ImportPreparationIssue, ...]
    preview_status: PreviewStatus
    core_data: PreparedStreamData | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ImportPreparationSummary:
    total_rows: int
    ready_rows: int
    blocked_rows: int
    excluded_rows: int
    create_stream_rows: int
    use_existing_stream_rows: int
    prepared_value_count: int


@dataclass(frozen=True)
class ImportPreparationResult:
    rows: tuple[PreparedImportRow, ...]
    summary: ImportPreparationSummary
