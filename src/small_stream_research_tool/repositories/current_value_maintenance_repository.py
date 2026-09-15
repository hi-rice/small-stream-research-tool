"""값 상태·파생 캐시·구조화 이력 SQL. 업무 정책은 Service 소유다."""

import sqlite3

from small_stream_research_tool.models.current_value_maintenance_errors import (
    MaintenancePersistenceError,
)


class CurrentValueMaintenanceRepository:
    def __init__(self, connection):
        self._connection = connection

    def _execute(self, sql, params=(), *, write=False):
        try:
            if write and not self._connection.in_transaction:
                raise MaintenancePersistenceError()
            cursor = self._connection.execute(sql, params)
            try:
                return (cursor.rowcount, cursor.lastrowid) if write else cursor.fetchall()
            finally:
                cursor.close()
        except (sqlite3.Error, OverflowError, UnicodeError):
            raise MaintenancePersistenceError() from None

    def representatives(self, stream_code, dictionary_id):
        return tuple(
            row[0]
            for row in self._execute(
                "SELECT characteristic_value_id FROM characteristic_value WHERE stream_code=? "
                "AND dictionary_id=? AND is_active=1 AND is_representative=1",
                (stream_code, dictionary_id),
            )
        )

    def cache_id(self, stream_code, dictionary_id):
        rows = self._execute(
            "SELECT characteristic_value_id FROM stream_characteristic "
            "WHERE stream_code=? AND dictionary_id=?",
            (stream_code, dictionary_id),
        )
        return rows[0][0] if rows else None

    def pairs(self, stream_code=None, dictionary_id=None):
        if stream_code is None:
            rows = self._execute(
                "SELECT stream_code,dictionary_id FROM characteristic_value "
                "WHERE is_active=1 AND is_representative=1 UNION "
                "SELECT stream_code,dictionary_id FROM stream_characteristic "
                "ORDER BY stream_code,dictionary_id"
            )
        else:
            rows = self._execute(
                "SELECT stream_code,dictionary_id FROM characteristic_value "
                "WHERE stream_code=? AND dictionary_id=? AND is_active=1 AND is_representative=1 "
                "UNION SELECT stream_code,dictionary_id FROM stream_characteristic "
                "WHERE stream_code=? AND dictionary_id=? ORDER BY stream_code,dictionary_id",
                (stream_code, dictionary_id, stream_code, dictionary_id),
            )
        return tuple(rows)

    def set_active(self, value_id, old, new):
        count, _ = self._execute(
            "UPDATE characteristic_value SET is_active=? "
            "WHERE characteristic_value_id=? AND is_active=?",
            (int(new), value_id, int(old)),
            write=True,
        )
        if count != 1:
            raise MaintenancePersistenceError()

    def release_representative(self, value_id):
        count, _ = self._execute(
            "UPDATE characteristic_value SET is_representative=0 "
            "WHERE characteristic_value_id=? AND is_active=1 AND is_representative=1",
            (value_id,),
            write=True,
        )
        if count != 1:
            raise MaintenancePersistenceError()

    def delete_cache(self, stream_code, dictionary_id):
        count, _ = self._execute(
            "DELETE FROM stream_characteristic WHERE stream_code=? AND dictionary_id=?",
            (stream_code, dictionary_id),
            write=True,
        )
        if count != 1:
            raise MaintenancePersistenceError()

    def upsert_cache(self, stream_code, dictionary_id, value_id, timestamp):
        self._execute(
            "INSERT INTO stream_characteristic "
            "(stream_code,dictionary_id,characteristic_value_id,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(stream_code,dictionary_id) DO UPDATE SET "
            "characteristic_value_id=excluded.characteristic_value_id,updated_at=excluded.updated_at",
            (stream_code, dictionary_id, value_id, timestamp),
            write=True,
        )

    def insert_history(self, key, old, new, change_type, actor_id, reason, timestamp, column):
        _, history_id = self._execute(
            "INSERT INTO record_history "
            "(table_name,record_key,column_name,old_value,new_value,change_type,"
            "actor_user_id,reason,changed_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                (
                    "stream_characteristic"
                    if change_type == "CACHE_REBUILD"
                    else "characteristic_value"
                ),
                key,
                column,
                old,
                new,
                change_type,
                actor_id,
                reason,
                timestamp,
            ),
            write=True,
        )
        return history_id
