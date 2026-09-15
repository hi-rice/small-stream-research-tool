"""보정 이력 SQL만 담당한다. 값 INSERT/조회는 기존 저장소를 사용한다."""

import sqlite3

from small_stream_research_tool.models.correction_errors import CorrectionPersistenceError


class CorrectionRepository:
    def __init__(self, connection):
        self._connection = connection

    def insert_history(self, *, record_key, old_value, new_value, actor_user_id, reason, timestamp):
        try:
            if not self._connection.in_transaction:
                raise CorrectionPersistenceError()
            cursor = self._connection.execute(
                "INSERT INTO record_history "
                "(table_name,record_key,old_value,new_value,change_type,reason,"
                "actor_user_id,changed_at) "
                "VALUES ('characteristic_value',?,?,?,'CORRECTION',?,?,?)",
                (record_key, old_value, new_value, reason, actor_user_id, timestamp),
            )
            try:
                return cursor.lastrowid
            finally:
                cursor.close()
        except (sqlite3.Error, OverflowError, UnicodeError):
            raise CorrectionPersistenceError() from None

    def get_history(self, history_id):
        try:
            cursor = self._connection.execute(
                "SELECT table_name,record_key,old_value,new_value,change_type,reason,actor_user_id,"
                "changed_at,issue_id,import_id,column_name,changed_by "
                "FROM record_history WHERE history_id=?",
                (history_id,),
            )
            try:
                row = cursor.fetchone()
                return tuple(row) if row is not None else None
            finally:
                cursor.close()
        except (sqlite3.Error, OverflowError, UnicodeError):
            raise CorrectionPersistenceError() from None
