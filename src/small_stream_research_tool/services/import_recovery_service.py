"""Import-owned 근거 검사와 명시적 종료 복구. 실행·자료 수정·cleanup은 하지 않는다."""

import json
from datetime import datetime

from small_stream_research_tool.database.connection import read_transaction, transaction
from small_stream_research_tool.models.import_recovery import (
    ImportRecoveryInspection,
    ImportRecoveryResult,
    RecoveryState,
)
from small_stream_research_tool.models.import_recovery_errors import (
    ImportRecoveryConsistencyError,
    ImportRecoveryError,
    ImportRecoveryStateError,
)
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    ImportColumnMappingRepository,
    ImportHistoryRepository,
    ImportSheetRepository,
)
from small_stream_research_tool.utils.timestamps import utc_now_text

_FINALIZED = frozenset(("SUCCESS", "FAILED", "CANCELLED", "ROLLED_BACK"))
_SETTINGS = frozenset(
    ("sheet_name", "header_start_row", "header_end_row", "data_start_row", "dictionary_version_id")
)
_METHODS = {
    "AUTO_MAPPED": ("AUTO",),
    "USER_MAPPED": ("USER",),
    "UNMAPPED": ("NONE",),
    "DO_NOT_MAP": ("NONE",),
    "NEEDS_REVIEW": ("AUTO_ALIAS", "USER"),
}


def _integer(value, minimum=0, maximum=2**63 - 1):
    return type(value) is int and minimum <= value <= maximum


def _utc(value):
    try:
        return (
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") == value
        )
    except (TypeError, ValueError):
        return False


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _settings(history):
    """6B-2의 알려진 snapshot만 사용한다. 누락이나 다른 계약을 임의 보완하지 않는다."""
    try:
        settings = json.loads(history.settings_json, object_pairs_hook=_unique_object)
    except (TypeError, ValueError, RecursionError):
        return None
    if type(settings) is not dict or settings.keys() != _SETTINGS:
        return None
    if not isinstance(settings["sheet_name"], str) or not settings["sheet_name"].strip():
        return None
    if not all(
        _integer(settings[name], 1, 1048576)
        for name in ("header_start_row", "header_end_row", "data_start_row")
    ):
        return None
    if not settings["header_start_row"] <= settings["header_end_row"] < settings["data_start_row"]:
        return None
    version = settings["dictionary_version_id"]
    if version is not None and not _integer(version, 1):
        return None
    return settings


class ImportRecoveryService:
    def __init__(self, connection):
        self._connection = connection
        self._histories = ImportHistoryRepository(connection)
        self._sheets = ImportSheetRepository(connection)
        self._mappings = ImportColumnMappingRepository(connection)
        self._values = CharacteristicValueRepository(connection)

    @staticmethod
    def _validate_id(import_id):
        if not _integer(import_id, 1):
            raise ImportRecoveryStateError()

    def inspect(self, import_id: int) -> ImportRecoveryInspection:
        """읽기 snapshot만 사용한다. RUNNING이라는 사실은 프로세스 중단 증명이 아니다."""
        self._validate_id(import_id)
        try:
            with read_transaction(self._connection):
                return self._inspect(import_id)
        except ImportRecoveryError:
            raise
        except Exception:
            raise ImportRecoveryError() from None

    def list_recovery_candidates(self) -> tuple[ImportRecoveryInspection, ...]:
        """시간 임계값 없이 현재 RUNNING만 검사한다. retry/finalize는 실행하지 않는다."""
        try:
            with read_transaction(self._connection):
                return tuple(
                    self._inspect(h.import_id) for h in self._histories.list_by_status("RUNNING")
                )
        except ImportRecoveryError:
            raise
        except Exception:
            raise ImportRecoveryError() from None

    def _inspect(self, import_id):
        history = self._histories.get_by_id(import_id)
        if history is None:
            raise ImportRecoveryStateError()
        sheets = self._sheets.list_by_import_id(import_id)
        mappings = self._mappings.list_recovery_evidence(import_id)
        values = self._values.list_recovery_evidence(import_id)
        accepted = sheets[0].accepted_rows if len(sheets) == 1 else None

        def result(state, reason):
            return ImportRecoveryInspection(
                import_id,
                history.batch_code,
                history.status,
                state,
                len(sheets),
                len(mappings),
                sum(v.import_id == import_id for v in values),
                1 if history.import_type == "EXCEL" else None,
                history.total_rows if _integer(history.total_rows) else None,
                accepted if _integer(accepted) else None,
                None,
                None,
                state == RecoveryState.COMMITTED_CONSISTENT,
                state == RecoveryState.NO_PERSISTED_DATA,
                reason,
                utc_now_text(),
            )

        if history.status in _FINALIZED:
            return result(RecoveryState.ALREADY_FINALIZED, "ALREADY_FINALIZED")
        if history.status != "RUNNING":
            return result(RecoveryState.NOT_RECOVERABLE, "NOT_RUNNING")

        def inconsistent(reason):
            return result(RecoveryState.INCONSISTENT, reason)

        if (
            history.finished_at is not None
            or history.error_code is not None
            or history.error_message is not None
        ):
            return inconsistent("RUNNING_FINALIZATION_CONFLICT")
        if not sheets:
            if mappings or values:
                return inconsistent("MISSING_IMPORT_SHEET")
            if any(
                count not in (None, 0)
                for count in (history.accepted_rows, history.warning_rows, history.rejected_rows)
            ):
                return inconsistent("ROW_COUNT_MISMATCH")
            return result(RecoveryState.NO_PERSISTED_DATA, "NO_B_ARTIFACTS")
        if len(sheets) != 1:
            return inconsistent("SHEET_COUNT_MISMATCH")
        settings = _settings(history)
        if (
            history.import_type != "EXCEL"
            or settings is None
            or not _integer(history.schema_version_id, 1)
        ):
            return result(RecoveryState.NOT_RECOVERABLE, "EXECUTION_METADATA_UNAVAILABLE")
        sheet = sheets[0]
        if (
            sheet.import_id != import_id
            or sheet.status != "SUCCESS"
            or any(
                getattr(sheet, key) != settings[key]
                for key in _SETTINGS
                if key != "dictionary_version_id"
            )
            or settings["dictionary_version_id"] != history.dictionary_version_id
            or (sheet.sheet_index is not None and not _integer(sheet.sheet_index, 1))
        ):
            return inconsistent("SHEET_METADATA_MISMATCH")
        if (
            not _utc(history.started_at)
            or not _utc(history.created_at)
            or not _utc(sheet.created_at)
        ):
            return result(RecoveryState.NOT_RECOVERABLE, "EXECUTION_TIME_UNAVAILABLE")
        if (
            not _integer(history.total_rows, 1)
            or not _integer(sheet.total_rows, 1)
            or history.total_rows != sheet.total_rows
            or not _integer(accepted, 1)
            or accepted > sheet.total_rows
            or sheet.rejected_rows != 0
            or sheet.warning_rows is not None
            or history.warning_rows is not None
            or history.accepted_rows not in (None, accepted)
            or history.rejected_rows not in (None, 0)
        ):
            return inconsistent("ROW_COUNT_MISMATCH")
        lookup = {}
        columns = set()
        for mapping in mappings:
            if (
                mapping.import_sheet_id != sheet.import_sheet_id
                or not _integer(mapping.source_column_index, 1, 16384)
                or mapping.source_column_index in columns
                or mapping.mapping_id in lookup
            ):
                return inconsistent("MAPPING_PROVENANCE_MISMATCH")
            columns.add(mapping.source_column_index)
            lookup[mapping.mapping_id] = mapping
            status = mapping.mapping_status
            if (
                status not in _METHODS
                or mapping.mapping_method not in _METHODS[status]
                or mapping.user_confirmed != int(status in ("USER_MAPPED", "DO_NOT_MAP"))
            ):
                return inconsistent("MAPPING_METADATA_MISMATCH")
            if status in ("UNMAPPED", "DO_NOT_MAP"):
                if mapping.dictionary_id is not None or mapping.target_unit_id is not None:
                    return inconsistent("MAPPING_METADATA_MISMATCH")
            elif not _integer(mapping.dictionary_id, 1):
                return inconsistent("MAPPING_METADATA_MISMATCH")
        rows = set()
        cells = set()
        dictionaries = set()
        missing_mapping = False
        for value in values:
            if (
                value.import_id != import_id
                or value.import_sheet_id != sheet.import_sheet_id
                or value.source_type != "IMPORT"
                or not _integer(value.source_row, sheet.data_start_row, 1048576)
            ):
                return inconsistent("VALUE_PROVENANCE_MISMATCH")
            rows.add(value.source_row)
            if value.mapping_id is None:
                missing_mapping = True
                continue
            mapping = lookup.get(value.mapping_id)
            if (
                mapping is None
                or mapping.dictionary_id != value.dictionary_id
                or mapping.mapping_status not in ("AUTO_MAPPED", "USER_MAPPED")
                or mapping.target_unit_id != value.unit_id
            ):
                return inconsistent("VALUE_PROVENANCE_MISMATCH")
            cell = (value.source_row, mapping.source_column_index)
            dictionary = (value.source_row, value.dictionary_id)
            if cell in cells or dictionary in dictionaries:
                return inconsistent("DUPLICATE_VALUE_PROVENANCE")
            cells.add(cell)
            dictionaries.add(dictionary)
        if len(rows) > accepted:
            return inconsistent("ROW_COUNT_MISMATCH")
        if missing_mapping:
            # NULL만으로 손상을 단정하지 않는다. 다만 6B-2의 완전한 출처는 확인할 수 없다.
            return result(RecoveryState.NOT_RECOVERABLE, "MAPPING_PROVENANCE_UNAVAILABLE")
        # core-only READY도 정상이다. 독립된 기대값이 없는 값/매핑 개수는 추측하지 않는다.
        return result(RecoveryState.COMMITTED_CONSISTENT, "B_ARTIFACTS_CONSISTENT")

    def recover_success(self, import_id: int) -> ImportRecoveryResult:
        """명시적 요청만 finalize한다. BEGIN IMMEDIATE 후 상태/근거를 다시 읽는다."""
        self._validate_id(import_id)
        try:
            with transaction(self._connection):
                inspection = self._inspect(import_id)
                if inspection.current_status == "SUCCESS":
                    history = self._histories.get_by_id(import_id)
                    return ImportRecoveryResult(
                        import_id,
                        history.batch_code,
                        "SUCCESS",
                        "SUCCESS",
                        RecoveryState.ALREADY_FINALIZED,
                        history.finished_at if _utc(history.finished_at) else None,
                        False,
                    )
                if inspection.current_status != "RUNNING":
                    raise ImportRecoveryStateError()
                if not inspection.can_finalize_success:
                    raise ImportRecoveryConsistencyError()
                finished = utc_now_text()
                self._histories.update_status(
                    import_id,
                    "SUCCESS",
                    finished_at=finished,
                    total_rows=inspection.expected_total_rows,
                    accepted_rows=inspection.accepted_rows,
                    warning_rows=None,
                    rejected_rows=0,
                )
                result = ImportRecoveryResult(
                    import_id,
                    inspection.batch_code,
                    "RUNNING",
                    "SUCCESS",
                    RecoveryState.COMMITTED_CONSISTENT,
                    finished,
                    True,
                )
            return result
        except ImportRecoveryError:
            raise
        except Exception:
            raise ImportRecoveryError() from None
