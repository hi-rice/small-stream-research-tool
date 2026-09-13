"""Import 복구 판정과 결과. 연구값/파일 경로/설정 원문은 포함하지 않는다."""

from dataclasses import dataclass, field
from enum import StrEnum


class RecoveryState(StrEnum):
    NO_PERSISTED_DATA = "NO_PERSISTED_DATA"
    COMMITTED_CONSISTENT = "COMMITTED_CONSISTENT"
    INCONSISTENT = "INCONSISTENT"
    NOT_RECOVERABLE = "NOT_RECOVERABLE"
    ALREADY_FINALIZED = "ALREADY_FINALIZED"


@dataclass(frozen=True)
class ImportRecoveryInspection:
    import_id: int
    batch_code: str = field(repr=False)
    current_status: str
    recovery_state: RecoveryState
    sheet_count: int
    mapping_count: int
    characteristic_value_count: int
    expected_sheet_count: int | None
    expected_total_rows: int | None
    accepted_rows: int | None
    expected_mapping_count: int | None
    expected_characteristic_value_count: int | None
    can_finalize_success: bool
    can_retry: bool
    reason_code: str
    inspected_at: str


@dataclass(frozen=True)
class ImportRecoveryResult:
    import_id: int
    batch_code: str = field(repr=False)
    previous_status: str
    new_status: str
    recovery_state: RecoveryState
    finalized_at: str | None
    changed: bool


@dataclass(frozen=True)
class RecoveryMappingEvidence:
    """원본 헤더를 읽지 않는 Repository 조회 projection."""

    mapping_id: int
    import_sheet_id: int
    source_column_index: int
    dictionary_id: int | None
    mapping_status: str = field(repr=False)
    mapping_method: str = field(repr=False)
    target_unit_id: int | None
    user_confirmed: int


@dataclass(frozen=True)
class RecoveryValueEvidence:
    """원본/typed 값 대신 출처와 행·사전 연결만 조회한다."""

    characteristic_value_id: int
    import_id: int | None
    import_sheet_id: int | None
    mapping_id: int | None
    dictionary_id: int
    source_row: int | None
    source_type: str = field(repr=False)
    unit_id: int | None
