"""Import 6개 저장소. 호출자가 연결과 transaction을 소유하며 SQL 값은 전부 binding한다."""

import sqlite3
from dataclasses import fields

from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.import_persistence import (
    CharacteristicProvenance,
    CharacteristicValueRecord,
    ImportColumnMappingRecord,
    ImportHistoryRecord,
    ImportSheetRecord,
    SmallStreamRecord,
    SourceFileRecord,
)
from small_stream_research_tool.models.import_persistence_errors import (
    ConstraintViolationError,
    DuplicateRecordError,
    ForeignKeyReferenceError,
    InvalidPersistenceArgumentError,
    PersistenceError,
    RecordNotFoundError,
    TransactionRequiredError,
)
from small_stream_research_tool.models.import_preparation import (
    PreparedCharacteristicValue,
    PreparedStreamData,
)

# 기존 DictionaryRepository처럼 모델과 SQL 식별자를 코드 내부에서만 고정한다.
_TABLES = {
    SourceFileRecord: ("source_file", "source_file_id"),
    ImportHistoryRecord: ("import_history", "import_id"),
    ImportSheetRecord: ("import_sheet", "import_sheet_id"),
    ImportColumnMappingRecord: ("import_column_mapping", "mapping_id"),
    SmallStreamRecord: ("small_stream", "stream_code"),
    CharacteristicValueRecord: ("characteristic_value", "characteristic_value_id"),
}


def _database_error(error):
    code = getattr(error, "sqlite_errorcode", None)
    if code in (sqlite3.SQLITE_CONSTRAINT_UNIQUE, sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY):
        return DuplicateRecordError("이미 존재하는 식별자 또는 출처 조합입니다.")
    if code == sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY:
        return ForeignKeyReferenceError("참조하는 레코드가 존재하지 않습니다.")
    if isinstance(error, sqlite3.IntegrityError):
        return ConstraintViolationError("저장 값이 DB 제약을 만족하지 않습니다.")
    return PersistenceError("Import 저장소에 접근할 수 없습니다.")


class _ImportRepository:
    """이 모듈 전용 SQL 공통부. 범용 쿼리나 임의 테이블 API는 제공하지 않는다."""

    _model = None

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._table, self._pk = _TABLES[self._model]
        self._columns = tuple(f.name for f in fields(self._model))

    def transaction(self):
        """호출자가 명시적으로 사용할 기존 helper. create/update에서 호출하지 않는다."""
        return transaction(self._connection)

    def _execute(self, sql, parameters=(), *, write=False, result="all"):
        try:
            if write and not self._connection.in_transaction:
                raise TransactionRequiredError(
                    "저장에는 호출자가 연 명시적 transaction이 필요합니다."
                )
            cursor = self._connection.execute(sql, parameters)
            try:
                if result == "insert":
                    return cursor.lastrowid
                if result == "update":
                    return cursor.rowcount
                return cursor.fetchall()
            finally:
                cursor.close()
        except sqlite3.Error as error:
            raise _database_error(error) from None
        except (OverflowError, UnicodeError):
            raise InvalidPersistenceArgumentError("SQLite에 전달할 수 없는 값입니다.") from None

    def _select(self, where, parameters):
        rows = self._execute(
            f"SELECT {','.join(self._columns)} FROM {self._table} "
            f"WHERE {where} ORDER BY {self._pk}",
            parameters,
        )
        result = []
        for row in rows:
            values = dict(zip(self._columns, row, strict=True))
            for name in ("is_active", "is_representative", "user_confirmed"):
                if name in values:
                    values[name] = bool(values[name])
            result.append(self._model(**values))
        return result

    def _one(self, where, parameters):
        rows = self._select(where, parameters)
        return rows[0] if rows else None

    def _count(self, where, parameters):
        return self._execute(
            f"SELECT count(*) FROM {self._table} WHERE {where}",
            parameters,
        )[0][0]

    def _insert(self, values):
        allowed = set(self._columns)
        if self._model is not SmallStreamRecord:
            allowed.remove(self._pk)
        if not values or not values.keys() <= allowed:
            raise InvalidPersistenceArgumentError("허용되지 않은 저장 컬럼입니다.")
        # NULL/DEFAULT를 바꾸거나 누락값을 생성하지 않는다. 생략한 컬럼은 DB 정의를 따른다.
        pk = self._execute(
            f"INSERT INTO {self._table} ({','.join(values)}) "
            f"VALUES ({','.join('?' for _ in values)})",
            tuple(values.values()),
            write=True,
            result="insert",
        )
        if self._model is SmallStreamRecord:
            pk = values["stream_code"]
        record = self._one(f"{self._pk}=?", (pk,))
        if record is None:
            raise RecordNotFoundError("생성된 레코드를 조회할 수 없습니다.")
        return record


class SourceFileRepository(_ImportRepository):
    _model = SourceFileRecord

    def create(self, **values) -> SourceFileRecord:
        return self._insert(values)

    def get_by_id(self, source_file_id: int) -> SourceFileRecord | None:
        return self._one("source_file_id=?", (source_file_id,))

    def find_by_hash(self, file_hash: str | None) -> list[SourceFileRecord]:
        """같은 hash의 모든 등록을 ID 순서로 반환한다. NULL은 hash 조회 근거가 아니다."""
        if file_hash is None:
            return []
        return self._select("file_hash=?", (file_hash,))


class ImportHistoryRepository(_ImportRepository):
    _model = ImportHistoryRecord

    def create(self, **values) -> ImportHistoryRecord:
        return self._insert(values)

    def get_by_id(self, import_id: int) -> ImportHistoryRecord | None:
        return self._one("import_id=?", (import_id,))

    def get_by_batch_code(self, batch_code: str) -> ImportHistoryRecord | None:
        return self._one("batch_code=?", (batch_code,))

    def list_by_status(self, status: str) -> list[ImportHistoryRecord]:
        return self._select("status=?", (status,))

    def count_by_status(self, status: str) -> int:
        return self._count("status=?", (status,))

    def update_status(self, import_id: int, status: str, **changes) -> ImportHistoryRecord:
        """전이 판단/시각 생성 없음. 생략 필드는 유지, 명시적 None은 NULL로 기록한다."""
        allowed = {
            "finished_at",
            "total_rows",
            "accepted_rows",
            "warning_rows",
            "rejected_rows",
            "error_code",
            "error_message",
        }
        if not changes.keys() <= allowed:
            raise InvalidPersistenceArgumentError("허용되지 않은 이력 갱신 컬럼입니다.")
        values = {"status": status, **changes}
        count = self._execute(
            f"UPDATE import_history SET {','.join(name + '=?' for name in values)} "
            "WHERE import_id=?",
            (*values.values(), import_id),
            write=True,
            result="update",
        )
        if count != 1:
            raise RecordNotFoundError("갱신할 Import 이력이 없습니다.")
        return self.get_by_id(import_id)


class ImportSheetRepository(_ImportRepository):
    _model = ImportSheetRecord

    def create(self, **values) -> ImportSheetRecord:
        return self._insert(values)

    def get_by_id(self, import_sheet_id: int) -> ImportSheetRecord | None:
        return self._one("import_sheet_id=?", (import_sheet_id,))

    def list_by_import_id(self, import_id: int) -> list[ImportSheetRecord]:
        return self._select("import_id=?", (import_id,))

    def count_by_import_id(self, import_id: int) -> int:
        return self._count("import_id=?", (import_id,))


class ImportColumnMappingRepository(_ImportRepository):
    _model = ImportColumnMappingRecord

    def create(self, **values) -> ImportColumnMappingRecord:
        """상태/방법 TEXT는 그대로 저장한다. Draft→DB 의미 변환을 하지 않는다."""
        return self._insert(values)

    def get_by_id(self, mapping_id: int) -> ImportColumnMappingRecord | None:
        return self._one("mapping_id=?", (mapping_id,))

    def list_by_import_sheet_id(self, import_sheet_id: int) -> list[ImportColumnMappingRecord]:
        return self._select("import_sheet_id=?", (import_sheet_id,))

    def count_by_import_sheet_id(self, import_sheet_id: int) -> int:
        return self._count("import_sheet_id=?", (import_sheet_id,))


class SmallStreamRepository(_ImportRepository):
    _model = SmallStreamRecord

    def create(self, **values) -> SmallStreamRecord:
        return self._insert(values)

    def create_prepared(self, prepared: PreparedStreamData, *, timestamp: str) -> SmallStreamRecord:
        """Phase 6A 결과를 손실 없이 전달한다. 시각은 caller의 UTC helper 결과를 받는다."""
        if type(prepared) is not PreparedStreamData:
            raise InvalidPersistenceArgumentError("PreparedStreamData가 필요합니다.")
        values = {
            name: getattr(prepared, name)
            for name in (
                "stream_code",
                "province_code",
                "city_county_code",
                "town_code",
                "stream_serial_no",
                "stream_name",
            )
        }
        values.update(prepared.optional_fields)
        return self.create(**values, created_at=timestamp, updated_at=timestamp)

    def get_by_stream_code(self, stream_code: str) -> SmallStreamRecord | None:
        return self._one("stream_code=?", (stream_code,))

    def exists_by_stream_code(self, stream_code: str) -> bool:
        return self._count("stream_code=?", (stream_code,)) != 0

    def count(self) -> int:
        return self._count("1", ())


class CharacteristicValueRepository(_ImportRepository):
    _model = CharacteristicValueRecord

    def create(self, **values) -> CharacteristicValueRecord:
        """변환이나 기존 값 갱신 없이 INSERT한다. exactly-one은 DB CHECK로 보호한다."""
        return self._insert(values)

    def create_prepared(
        self,
        prepared: PreparedCharacteristicValue,
        *,
        stream_code: str,
        timestamp: str,
        import_id: int | None = None,
        import_sheet_id: int | None = None,
        mapping_id: int | None = None,
        reference_year: int | None = None,
    ) -> CharacteristicValueRecord:
        if type(prepared) is not PreparedCharacteristicValue:
            raise InvalidPersistenceArgumentError("PreparedCharacteristicValue가 필요합니다.")
        # source_column_index는 mapping_id를 통해 추적한다. 존재하지 않는 DB 컬럼을 만들지 않는다.
        values = {
            name: getattr(prepared, name)
            for name in (
                "dictionary_id",
                "value_number",
                "value_integer",
                "value_text",
                "value_date",
                "unit_id",
                "original_value",
                "original_unit",
                "source_row",
            )
        }
        return self.create(
            **values,
            stream_code=stream_code,
            import_id=import_id,
            import_sheet_id=import_sheet_id,
            mapping_id=mapping_id,
            reference_year=reference_year,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def get_by_id(self, characteristic_value_id: int) -> CharacteristicValueRecord | None:
        return self._one("characteristic_value_id=?", (characteristic_value_id,))

    def list_by_import_id(self, import_id: int) -> list[CharacteristicValueRecord]:
        return self._select("import_id=?", (import_id,))

    def count_by_import_id(self, import_id: int) -> int:
        return self._count("import_id=?", (import_id,))

    def list_by_stream_code(self, stream_code: str) -> list[CharacteristicValueRecord]:
        return self._select("stream_code=?", (stream_code,))

    def count_by_stream_code(self, stream_code: str) -> int:
        return self._count("stream_code=?", (stream_code,))

    def count_by_import_sheet_id(self, import_sheet_id: int) -> int:
        return self._count("import_sheet_id=?", (import_sheet_id,))

    def get_provenance(self, characteristic_value_id: int) -> CharacteristicProvenance | None:
        value = self.get_by_id(characteristic_value_id)
        if value is None:
            return None
        mapping = ImportColumnMappingRepository(self._connection).get_by_id(value.mapping_id)
        sheet = ImportSheetRepository(self._connection).get_by_id(value.import_sheet_id)
        history = ImportHistoryRepository(self._connection).get_by_id(value.import_id)
        source = (
            SourceFileRepository(self._connection).get_by_id(history.source_file_id)
            if history is not None
            else None
        )
        return CharacteristicProvenance(value, mapping, sheet, history, source)
