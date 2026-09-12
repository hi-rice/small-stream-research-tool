"""6개 사전 테이블의 SQL 저장소. 쓰기 경계는 Service가 소유한다."""

import sqlite3
from dataclasses import fields

from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.dictionary import (
    ColumnAlias,
    DataCategory,
    DataDictionaryItem,
    DictionaryVersion,
    UnitConversion,
    UnitDefinition,
)
from small_stream_research_tool.models.dictionary_errors import (
    DictionaryEntryNotFoundError,
    DuplicateAliasError,
    DuplicateDefinitionError,
)

# SQL 식별자는 외부 입력을 사용하지 않고 아래 고정된 모델/테이블에서만 얻는다.
_TABLES = {
    DataCategory: ("data_category", "category_id"),
    DictionaryVersion: ("dictionary_version", "version_id"),
    UnitDefinition: ("unit_dictionary", "unit_id"),
    UnitConversion: ("unit_conversion", "conversion_id"),
    DataDictionaryItem: ("data_dictionary", "dictionary_id"),
    ColumnAlias: ("column_alias", "alias_id"),
}


class DictionaryRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def transaction(self):
        return transaction(self._connection)

    def _write(self, sql, parameters, *, alias=False):
        if not self._connection.in_transaction:
            raise RuntimeError("Dictionary writes require an explicit transaction")
        try:
            return self._connection.execute(sql, parameters)
        except sqlite3.IntegrityError as error:
            if error.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                error_type = DuplicateAliasError if alias else DuplicateDefinitionError
                raise error_type("동일한 식별자로 이미 등록된 항목입니다.") from None
            raise

    def _select(self, model, where="", parameters=()):
        table, pk = _TABLES[model]
        names = [f.name for f in fields(model)]
        sql = f"SELECT {','.join(names)} FROM {table}"
        if where:
            sql += " WHERE " + where
        sql += f" ORDER BY {pk}"
        result = []
        for row in self._connection.execute(sql, parameters):
            values = dict(zip(names, row, strict=True))
            for name in ("is_active", "is_current", "analyzable", "required", "nullable"):
                if name in values:
                    values[name] = bool(values[name])
            result.append(model(**values))
        return result

    def _one(self, model, where, parameters):
        rows = self._select(model, where, parameters)
        return rows[0] if rows else None

    def _insert(self, model, values):
        table, pk = _TABLES[model]
        allowed = {f.name for f in fields(model)} - {pk}
        if not values or not values.keys() <= allowed:
            raise ValueError("Invalid repository columns")
        cursor = self._write(
            f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
            tuple(values.values()),
            alias=model is ColumnAlias,
        )
        return self._one(model, f"{pk}=?", (cursor.lastrowid,))

    def create_category(self, **values) -> DataCategory:
        return self._insert(DataCategory, values)

    def get_category(self, category_id) -> DataCategory | None:
        return self._one(DataCategory, "category_id=?", (category_id,))

    def list_categories(self, active_only=True) -> list[DataCategory]:
        rows = self._select(DataCategory, "is_active=1" if active_only else "")
        return sorted(rows, key=lambda row: (row.sort_order, row.category_id))

    def create_version(self, **values) -> DictionaryVersion:
        return self._insert(DictionaryVersion, values)

    def get_version(self, version_id) -> DictionaryVersion | None:
        return self._one(DictionaryVersion, "version_id=?", (version_id,))

    def list_versions(self) -> list[DictionaryVersion]:
        return self._select(DictionaryVersion)

    def get_current_version(self) -> DictionaryVersion | None:
        return self._one(DictionaryVersion, "is_current=1", ())

    def set_current_version(self, version_id):
        if self.get_version(version_id) is None:
            raise DictionaryEntryNotFoundError("사전 버전이 없습니다.")
        self._write("UPDATE dictionary_version SET is_current=0 WHERE is_current=1", ())
        self._write("UPDATE dictionary_version SET is_current=1 WHERE version_id=?", (version_id,))

    def create_unit(self, **values) -> UnitDefinition:
        return self._insert(UnitDefinition, values)

    def get_unit(self, unit_id) -> UnitDefinition | None:
        return self._one(UnitDefinition, "unit_id=?", (unit_id,))

    def list_units(self, active_only=True) -> list[UnitDefinition]:
        return self._select(UnitDefinition, "is_active=1" if active_only else "")

    def create_conversion(self, **values) -> UnitConversion:
        return self._insert(UnitConversion, values)

    def get_conversion(
        self, from_unit_id, to_unit_id, formula_type="LINEAR"
    ) -> UnitConversion | None:
        return self._one(
            UnitConversion,
            "from_unit_id=? AND to_unit_id=? AND formula_type=?",
            (from_unit_id, to_unit_id, formula_type),
        )

    def create_item(self, **values) -> DataDictionaryItem:
        return self._insert(DataDictionaryItem, values)

    def get_item(self, dictionary_id) -> DataDictionaryItem | None:
        return self._one(DataDictionaryItem, "dictionary_id=?", (dictionary_id,))

    def get_item_by_internal_name(self, internal_name) -> DataDictionaryItem | None:
        return self._one(DataDictionaryItem, "internal_name=?", (internal_name,))

    def list_items(
        self, *, category_id=None, standard_name=None, active_only=True, analyzable_only=False
    ) -> list[DataDictionaryItem]:
        clauses, parameters = [], []
        for column, value in (("category_id", category_id), ("standard_name", standard_name)):
            if value is not None:
                clauses.append(f"{column}=?")
                parameters.append(value)
        if active_only:
            clauses.append("is_active=1 AND deprecated_version_id IS NULL")
        if analyzable_only:
            clauses.append("analyzable=1")
        return self._select(DataDictionaryItem, " AND ".join(clauses), parameters)

    def item_in_use(self, dictionary_id) -> bool:
        # 값이 비활성 상태여도 과거 출처/검사에서 사용한 정의를 보호한다.
        for table in (
            "characteristic_value",
            "stream_characteristic",
            "import_column_mapping",
            "quality_rule",
            "data_quality_issue",
        ):
            if self._connection.execute(
                f"SELECT 1 FROM {table} WHERE dictionary_id=? LIMIT 1", (dictionary_id,)
            ).fetchone():
                return True
        return False

    def update_item_definition(self, dictionary_id, changes, timestamp):
        allowed = {
            "standard_name",
            "internal_name",
            "category_id",
            "data_type",
            "unit_id",
            "description",
            "storage_type",
        }
        if not changes or not changes.keys() <= allowed:
            raise ValueError("Invalid definition columns")
        assignments = ",".join(f"{column}=?" for column in changes)
        cursor = self._write(
            f"UPDATE data_dictionary SET {assignments},updated_at=? WHERE dictionary_id=?",
            (*changes.values(), timestamp, dictionary_id),
        )
        if cursor.rowcount != 1:
            raise DictionaryEntryNotFoundError("표준 항목이 없습니다.")

    def deprecate_item(self, dictionary_id, version_id, timestamp):
        cursor = self._write(
            "UPDATE data_dictionary SET deprecated_version_id=?,is_active=0,"
            "updated_at=? WHERE dictionary_id=?",
            (version_id, timestamp, dictionary_id),
        )
        if cursor.rowcount != 1:
            raise DictionaryEntryNotFoundError("표준 항목이 없습니다.")

    def create_alias(self, **values) -> ColumnAlias:
        return self._insert(ColumnAlias, values)

    def get_alias(self, alias_id) -> ColumnAlias | None:
        return self._one(ColumnAlias, "alias_id=?", (alias_id,))

    def find_alias(self, normalized_alias, source_scope) -> ColumnAlias | None:
        return self._one(
            ColumnAlias, "normalized_alias=? AND source_scope=?", (normalized_alias, source_scope)
        )

    def deactivate(self, model, entry_id, timestamp):
        if model not in (
            DataCategory,
            UnitDefinition,
            UnitConversion,
            DataDictionaryItem,
            ColumnAlias,
        ):
            raise ValueError("Unsupported deactivation target")
        table, pk = _TABLES[model]
        cursor = self._write(
            f"UPDATE {table} SET is_active=0,updated_at=? WHERE {pk}=?", (timestamp, entry_id)
        )
        if cursor.rowcount != 1:
            raise DictionaryEntryNotFoundError("사전 항목이 없습니다.")
