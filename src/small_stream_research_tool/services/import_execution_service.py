"""단일 시트 실행. A(시도), B(전체 자료), C(종료)를 별도 transaction으로 관리한다."""

import json
import re
from dataclasses import asdict, replace
from uuid import uuid4

from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.database.migrations import get_schema_version_id
from small_stream_research_tool.models.column_mapping import MappingStatus
from small_stream_research_tool.models.import_execution import (
    ImportExecutionRequest,
    ImportExecutionResult,
    ImportSheetSnapshot,
    SourceFileSnapshot,
)
from small_stream_research_tool.models.import_execution_errors import (
    DuplicateImportError,
    ImportFinalizeError,
    ImportPreflightError,
    ImportTransactionError,
)
from small_stream_research_tool.models.import_preparation import (
    CORE_COORDINATE_LIMITS,
    CORE_TEXT_FIELDS,
    ImportFieldPolicy,
    ImportPreparationResult,
    PreparationStatus,
    PreparedCharacteristicValue,
    PreparedImportRow,
    PreparedStreamData,
    RowAction,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    ImportColumnMappingRepository,
    ImportHistoryRepository,
    ImportSheetRepository,
    SmallStreamRepository,
    SourceFileRepository,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.column_mapping_service import validate_mappings
from small_stream_research_tool.services.dictionary_service import (
    DictionaryService,
    normalize_alias,
)
from small_stream_research_tool.utils.timestamps import utc_now_text

_IDENTITY = frozenset(
    ("stream_code", "province_code", "city_county_code", "town_code", "stream_serial_no")
)
_CORE = _IDENTITY | {"stream_name"} | CORE_TEXT_FIELDS | CORE_COORDINATE_LIMITS.keys()
_SYSTEM = frozenset(("created_at", "updated_at", "is_active"))
_MAPPED = (MappingStatus.AUTO_MAPPED, MappingStatus.USER_MAPPED)
FAILURE_CODE = "IMPORT_TRANSACTION_FAILED"
FAILURE_MESSAGE = "Import data transaction failed; all data changes were rolled back."


def _require(condition):
    if not condition:
        raise ImportPreflightError()


def _integer(value, minimum=1, maximum=2**63 - 1):
    return type(value) is int and minimum <= value <= maximum


def _text(value, *, optional=False):
    if value is None:
        return optional
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return False
    value.encode("utf-8")
    return True


def mapping_method_for_storage(mapping):
    """DB NOT NULL adapter. 상태는 바꾸지 않으며 NONE은 방법 부재를 뜻한다."""
    if mapping.mapping_status == MappingStatus.AUTO_MAPPED:
        return "AUTO"
    if mapping.mapping_status == MappingStatus.USER_MAPPED:
        return "USER"
    if mapping.mapping_status in (MappingStatus.UNMAPPED, MappingStatus.DO_NOT_MAP):
        return "NONE"
    return mapping.mapping_method.value


class ImportExecutionService:
    def __init__(self, connection):
        self._connection = connection
        self._sources = SourceFileRepository(connection)
        self._histories = ImportHistoryRepository(connection)
        self._sheets = ImportSheetRepository(connection)
        self._mappings = ImportColumnMappingRepository(connection)
        self._streams = SmallStreamRepository(connection)
        self._values = CharacteristicValueRepository(connection)
        self._users = UserRepository(connection)
        self._dictionary = DictionaryService(DictionaryRepository(connection))

    def execute(self, request: ImportExecutionRequest, *, field_policy=None):
        """명시적 정책 필수. 실패 예외의 result는 커밋 여부와 A/B/C 차이를 보존한다."""
        try:
            _require(type(request) is ImportExecutionRequest)
            batch = request.batch_code if request.batch_code is not None else str(uuid4())
            schema_id, ready, excluded = self._preflight(request, field_policy, batch)
        except DuplicateImportError:
            raise
        except Exception:
            raise ImportPreflightError() from None
        result = ImportExecutionResult(
            None, None, batch, "FAILED", False, ready, excluded, 0, 0, 0, utc_now_text(), None
        )
        try:
            source, history = self._transaction_a(request, result, schema_id)
        except Exception:
            raise ImportTransactionError("A", result) from None
        result = replace(
            result,
            import_id=history.import_id,
            source_file_id=source.source_file_id,
            status="RUNNING",
        )
        failed = False
        try:
            created, reused, values = self._transaction_b(request, field_policy, result)
            result = replace(
                result,
                data_committed=True,
                created_stream_count=created,
                reused_stream_count=reused,
                characteristic_value_count=values,
            )
        except Exception:
            # transaction helper가 B 전체를 rollback했다. 이전 루프의 개수를 내보내지 않는다.
            failed = True
        finished = utc_now_text()
        try:
            self._finalize(result, finished, failed=failed)
        except Exception:
            # B commit은 이미 끝났을 수 있다. 재실행/보상 DELETE/상태 repair를 하지 않는다.
            raise ImportFinalizeError(result) from None
        result = replace(result, status="FAILED" if failed else "SUCCESS", finished_at=finished)
        if failed:
            raise ImportTransactionError("B", result) from None
        return result

    def _preflight(self, request, policy, batch):
        _require(not self._connection.in_transaction)
        _require(type(policy) is ImportFieldPolicy)
        _require(_text(batch))
        if self._histories.get_by_batch_code(batch) is not None:
            raise DuplicateImportError()
        source, sheet = request.source, request.sheet
        _require(type(source) is SourceFileSnapshot and type(sheet) is ImportSheetSnapshot)
        _require(_text(source.file_name) and _text(source.original_path))
        for name in ("file_extension", "file_hash", "file_modified_at", "source_description"):
            _require(_text(getattr(source, name), optional=True))
        _require(source.file_size is None or _integer(source.file_size, 0))
        _require(_text(sheet.sheet_name))
        _require(
            all(
                _integer(n, 1, 1048576)
                for n in (sheet.header_start_row, sheet.header_end_row, sheet.data_start_row)
            )
        )
        _require(sheet.header_start_row <= sheet.header_end_row < sheet.data_start_row)
        # ExcelReader.sheet_info()의 시트 순서도 1-based다.
        _require(sheet.sheet_index is None or _integer(sheet.sheet_index))
        _require(request.reference_year is None or _integer(request.reference_year, 1, 9999))
        _require(type(request.preparation) is ImportPreparationResult)
        rows = request.preparation.rows
        _require(type(rows) is tuple and bool(rows))
        _require(type(request.column_mappings) is tuple)
        validate_mappings(request.column_mappings)
        for mapping in request.column_mappings:
            mapping.source_header.encode("utf-8")
            _require(
                all(
                    sheet.header_start_row <= p.row_index <= sheet.header_end_row
                    for p in mapping.source_header_parts
                )
            )
        seen = set()
        for row in rows:
            _require(type(row) is PreparedImportRow)
            _require(
                type(row.status) is PreparationStatus
                and row.status in (PreparationStatus.READY, PreparationStatus.EXCLUDED)
            )
            _require(_integer(row.source_row, sheet.data_start_row, 1048576))
            _require(row.source_row not in seen)
            seen.add(row.source_row)
            if row.status == PreparationStatus.EXCLUDED:
                continue
            _require(type(row.row_action) is RowAction)
            _require(
                isinstance(row.stream_code, str)
                and re.fullmatch(r"[0-9]{11}", row.stream_code) is not None
            )
            _require(not any(issue.blocking for issue in row.issues))
            _require(type(row.prepared_values) is tuple)
            if row.row_action == RowAction.CREATE_STREAM:
                _require(type(row.core_data) is PreparedStreamData)
                row.core_data.__post_init__()
                _require(row.core_data.stream_code == row.stream_code)
            else:
                _require(row.core_data is None and bool(row.prepared_values))
            columns = set()
            dictionaries = set()
            for value in row.prepared_values:
                _require(type(value) is PreparedCharacteristicValue)
                value.__post_init__()
                _require(value.source_row == row.source_row)
                _require(value.source_column_index not in columns)
                _require(value.dictionary_id not in dictionaries)
                columns.add(value.source_column_index)
                dictionaries.add(value.dictionary_id)
        ready = sum(row.status == PreparationStatus.READY for row in rows)
        _require(ready > 0)
        self._check_references(request, policy)
        schema_id = get_schema_version_id(self._connection)
        _require(schema_id is not None)
        return schema_id, ready, len(rows) - ready

    def _item(self, dictionary_id):
        item = self._dictionary.get_item(dictionary_id)
        _require(item is not None and item.is_active and item.deprecated_version_id is None)
        category = self._dictionary.get_category(item.category_id)
        _require(category is not None and category.is_active)
        if item.unit_id is not None:
            unit = self._dictionary.get_unit(item.unit_id)
            _require(unit is not None and unit.is_active)
        return item

    def _check_references(self, request, policy):
        _require(_integer(request.current_user_id))
        user = self._users.find_by_user_id(request.current_user_id)
        _require(user is not None and user.is_active)
        if request.dictionary_version_id is not None:
            _require(_integer(request.dictionary_version_id))
            _require(self._dictionary.get_version(request.dictionary_version_id) is not None)
        mappings = {m.source_column_index: m for m in request.column_mappings}
        items = {
            m.dictionary_id: self._item(m.dictionary_id)
            for m in request.column_mappings
            if m.dictionary_id is not None
        }
        for row in request.preparation.rows:
            if row.status == PreparationStatus.EXCLUDED:
                continue
            _require(not (_IDENTITY & policy.excluded_internal_names))
            if row.core_data is not None:
                names = _IDENTITY | {"stream_name"} | dict(row.core_data.optional_fields).keys()
                _require(not (names & policy.excluded_internal_names))
            for value in row.prepared_values:
                mapping = mappings.get(value.source_column_index)
                _require(mapping is not None and mapping.mapping_status in _MAPPED)
                _require(mapping.dictionary_id == value.dictionary_id)
                item = items[value.dictionary_id]
                _require(item.internal_name not in policy.excluded_internal_names)
                _require(item.internal_name not in _CORE | _SYSTEM)
                _require(item.data_type == value.data_type and item.unit_id == value.unit_id)

    def _transaction_a(self, request, result, schema_id):
        settings = {
            "sheet_name": request.sheet.sheet_name,
            "header_start_row": request.sheet.header_start_row,
            "header_end_row": request.sheet.header_end_row,
            "data_start_row": request.sheet.data_start_row,
            "dictionary_version_id": request.dictionary_version_id,
        }
        with transaction(self._connection):
            source = self._sources.create(**asdict(request.source), registered_at=result.started_at)
            history = self._histories.create(
                source_file_id=source.source_file_id,
                batch_code=result.batch_code,
                created_by_user_id=request.current_user_id,
                import_type="EXCEL",
                status="RUNNING",
                started_at=result.started_at,
                created_at=result.started_at,
                dictionary_version_id=request.dictionary_version_id,
                schema_version_id=schema_id,
                settings_json=json.dumps(settings, sort_keys=True, ensure_ascii=True),
                total_rows=result.ready_rows + result.excluded_rows,
            )
        return source, history

    def _transaction_b(self, request, policy, result):
        created = reused = values = 0
        with transaction(self._connection):
            self._check_references(request, policy)
            sheet = self._sheets.create(
                **asdict(request.sheet),
                import_id=result.import_id,
                total_rows=result.ready_rows + result.excluded_rows,
                accepted_rows=result.ready_rows,
                rejected_rows=0,
                status="SUCCESS",
                created_at=result.started_at,
            )
            lookup = {}
            for mapping in request.column_mappings:
                item = self._item(mapping.dictionary_id) if mapping.dictionary_id else None
                record = self._mappings.create(
                    import_sheet_id=sheet.import_sheet_id,
                    source_column_index=mapping.source_column_index,
                    source_header=mapping.source_header,
                    normalized_header=(
                        normalize_alias(mapping.source_header)
                        if mapping.source_header.strip()
                        else None
                    ),
                    dictionary_id=mapping.dictionary_id,
                    mapping_status=mapping.mapping_status.value,
                    mapping_method=mapping_method_for_storage(mapping),
                    target_unit_id=item.unit_id if item else None,
                    user_confirmed=mapping.mapping_status
                    in (MappingStatus.USER_MAPPED, MappingStatus.DO_NOT_MAP),
                    created_at=result.started_at,
                )
                _require(record.source_column_index not in lookup)
                lookup[record.source_column_index] = record
            for row in request.preparation.rows:
                if row.status != PreparationStatus.READY:
                    continue
                if row.row_action == RowAction.CREATE_STREAM:
                    self._streams.create_prepared(row.core_data, timestamp=result.started_at)
                    created += 1
                else:
                    _require(self._streams.exists_by_stream_code(row.stream_code))
                    reused += 1
                for value in row.prepared_values:
                    mapping = lookup[value.source_column_index]
                    _require(sheet.import_id == result.import_id)
                    _require(mapping.import_sheet_id == sheet.import_sheet_id)
                    _require(mapping.dictionary_id == value.dictionary_id)
                    _require(mapping.source_column_index == value.source_column_index)
                    self._values.create_prepared(
                        value,
                        stream_code=row.stream_code,
                        timestamp=result.started_at,
                        import_id=result.import_id,
                        import_sheet_id=sheet.import_sheet_id,
                        mapping_id=mapping.mapping_id,
                        reference_year=request.reference_year,
                    )
                    values += 1
        return created, reused, values

    def _finalize(self, result, finished, *, failed):
        with transaction(self._connection):
            self._histories.update_status(
                result.import_id,
                "FAILED" if failed else "SUCCESS",
                finished_at=finished,
                total_rows=result.ready_rows + result.excluded_rows,
                accepted_rows=0 if failed else result.ready_rows,
                warning_rows=None,
                rejected_rows=None if failed else 0,
                error_code=FAILURE_CODE if failed else None,
                error_message=FAILURE_MESSAGE if failed else None,
            )
