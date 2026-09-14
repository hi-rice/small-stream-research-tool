"""현재값 flag·참조 캐시·선택 이력 SQL. 정책과 transaction은 Service 소유다."""

import sqlite3

from small_stream_research_tool.models.current_value_errors import CurrentValuePersistenceError


class CurrentValueRepository:
    def __init__(self, connection):
        self._connection = connection

    def _execute(self, sql, params=(), *, write=False):
        try:
            if write and not self._connection.in_transaction:
                raise CurrentValuePersistenceError()
            cursor = self._connection.execute(sql, params)
            try:
                return (cursor.rowcount, cursor.lastrowid) if write else cursor.fetchall()
            finally:
                cursor.close()
        except (sqlite3.Error, OverflowError, UnicodeError):
            raise CurrentValuePersistenceError() from None

    def active_representative_ids(self, stream_code, dictionary_id):
        return tuple(
            row[0]
            for row in self._execute(
                "SELECT characteristic_value_id FROM characteristic_value "
                "WHERE stream_code=? AND dictionary_id=? AND is_active=1 AND is_representative=1 "
                "ORDER BY characteristic_value_id",
                (stream_code, dictionary_id),
            )
        )

    def cache_value_id(self, stream_code, dictionary_id):
        rows = self._execute(
            "SELECT characteristic_value_id FROM stream_characteristic "
            "WHERE stream_code=? AND dictionary_id=?",
            (stream_code, dictionary_id),
        )
        return rows[0][0] if rows else None

    def set_representative(self, value_id, stream_code, dictionary_id, *, selected):
        count, _ = self._execute(
            "UPDATE characteristic_value SET is_representative=? "
            "WHERE characteristic_value_id=? AND stream_code=? AND dictionary_id=? "
            "AND is_active=1 AND is_representative=?",
            (int(selected), value_id, stream_code, dictionary_id, int(not selected)),
            write=True,
        )
        if count != 1:
            raise CurrentValuePersistenceError()

    def set_cache(self, stream_code, dictionary_id, value_id, timestamp):
        self._execute(
            "INSERT INTO stream_characteristic "
            "(stream_code,dictionary_id,characteristic_value_id,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(stream_code,dictionary_id) DO UPDATE SET "
            "characteristic_value_id=excluded.characteristic_value_id,updated_at=excluded.updated_at",
            (stream_code, dictionary_id, value_id, timestamp),
            write=True,
        )

    def insert_history(self, *, record_key, old_value, new_value, actor_user_id, reason, timestamp):
        _, history_id = self._execute(
            "INSERT INTO record_history (table_name,record_key,column_name,old_value,new_value,"
            "change_type,reason,actor_user_id,changed_at) "
            "VALUES ('characteristic_value',?,'is_representative',?,?,"
            "'CURRENT_VALUE_CHANGE',?,?,?)",
            (record_key, old_value, new_value, reason, actor_user_id, timestamp),
            write=True,
        )
        return history_id
