"""Phase 9D 화면용 bounded SELECT와 batch metadata 조회."""

import sqlite3

from small_stream_research_tool.models.app_read_errors import AppReadFailure

PAIR_EVENTS = frozenset(("CORRECTION", "CURRENT_VALUE_CHANGE", "CACHE_REBUILD"))
VALUE_EVENTS = frozenset(("DEACTIVATE", "RESTORE"))


def _marks(values):
    return ",".join("?" for _ in values)


class AppQueryRepository:
    def __init__(self, connection):
        self._connection = connection

    def _rows(self, sql, params=()):
        try:
            cursor = self._connection.execute(sql, params)
            try:
                return tuple(cursor.fetchall())
            finally:
                cursor.close()
        except (sqlite3.Error, OverflowError, UnicodeError):
            raise AppReadFailure() from None

    def active_stream_count(self):
        return self._rows("SELECT count(*) FROM small_stream WHERE is_active=1")[0][0]

    def qc_stream_counts(self):
        row = self._rows(
            "SELECT COALESCE(sum(has_error),0),"
            "COALESCE(sum(CASE WHEN has_error=0 AND has_review=1 THEN 1 ELSE 0 END),0) "
            "FROM (SELECT s.stream_code,"
            "MAX(CASE WHEN q.severity='ERROR' THEN 1 ELSE 0 END) has_error,"
            "MAX(CASE WHEN q.severity IN ('WARNING','INFO') THEN 1 ELSE 0 END) has_review "
            "FROM small_stream s LEFT JOIN data_quality_issue q "
            "ON q.stream_code=s.stream_code AND q.is_active=1 "
            "WHERE s.is_active=1 GROUP BY s.stream_code)"
        )[0]
        return int(row[0]), int(row[1])

    def research_version(self, version):
        rows = self._rows(
            "SELECT description,is_current FROM dictionary_version WHERE version=?", (version,)
        )
        return rows[0] if rows else None

    def dictionary_definitions(self, internal_names):
        if not internal_names:
            return ()
        return self._rows(
            "SELECT d.dictionary_id,d.internal_name,d.standard_name,d.data_type,d.analyzable,"
            "d.is_active,d.deprecated_version_id,c.category_key,c.is_active,u.unit_symbol,"
            "u.is_active FROM data_dictionary d "
            "JOIN data_category c ON c.category_id=d.category_id "
            "LEFT JOIN unit_dictionary u ON u.unit_id=d.unit_id "
            "WHERE d.internal_name IN (" + _marks(internal_names) + ")",
            internal_names,
        )

    @staticmethod
    def _history_where(request):
        clauses = [
            "h.change_type IN ('CORRECTION','CURRENT_VALUE_CHANGE','DEACTIVATE','RESTORE',"
            "'CACHE_REBUILD')"
        ]
        params = []
        if request.change_type is not None:
            clauses.append("h.change_type=?")
            params.append(request.change_type)
        if request.actor_user_id is not None:
            clauses.append("h.actor_user_id=?")
            params.append(request.actor_user_id)
        if request.stream_code is not None:
            safe_key = "CASE WHEN json_valid(h.record_key) THEN h.record_key ELSE '{}' END"
            clauses.append(
                "((h.change_type IN ('CORRECTION','CURRENT_VALUE_CHANGE','CACHE_REBUILD') "
                f"AND json_extract({safe_key},'$.stream_code')=?) OR "
                "(h.change_type IN ('DEACTIVATE','RESTORE') AND EXISTS ("
                "SELECT 1 FROM characteristic_value cv WHERE cv.characteristic_value_id="
                f"json_extract({safe_key},'$.characteristic_value_id') AND cv.stream_code=?)))"
            )
            params.extend((request.stream_code, request.stream_code))
        return " WHERE " + " AND ".join(clauses), tuple(params)

    def count_history(self, request):
        where, params = self._history_where(request)
        return self._rows("SELECT count(*) FROM record_history h" + where, params)[0][0]

    def page_history(self, request):
        where, params = self._history_where(request)
        return self._rows(
            "SELECT h.change_type,h.record_key,h.reason,h.changed_at,u.display_name "
            "FROM record_history h LEFT JOIN app_user u ON u.user_id=h.actor_user_id "
            + where
            + " ORDER BY h.history_id DESC LIMIT ? OFFSET ?",
            (*params, request.page_size, (request.page - 1) * request.page_size),
        )

    def history_actor_options(self):
        return self._rows(
            "SELECT DISTINCT u.user_id,u.display_name FROM record_history h "
            "JOIN app_user u ON u.user_id=h.actor_user_id "
            "WHERE h.change_type IN "
            "('CORRECTION','CURRENT_VALUE_CHANGE','DEACTIVATE','RESTORE','CACHE_REBUILD') "
            "ORDER BY u.display_name,u.user_id"
        )

    def value_targets(self, value_ids):
        if not value_ids:
            return ()
        return self._rows(
            "SELECT characteristic_value_id,stream_code,dictionary_id "
            "FROM characteristic_value WHERE characteristic_value_id IN ("
            + _marks(value_ids)
            + ")",
            value_ids,
        )

    def stream_names(self, stream_codes):
        if not stream_codes:
            return ()
        return self._rows(
            "SELECT stream_code,stream_name FROM small_stream WHERE stream_code IN ("
            + _marks(stream_codes)
            + ")",
            stream_codes,
        )

    def dictionary_names(self, dictionary_ids):
        if not dictionary_ids:
            return ()
        return self._rows(
            "SELECT dictionary_id,standard_name FROM data_dictionary WHERE dictionary_id IN ("
            + _marks(dictionary_ids)
            + ")",
            dictionary_ids,
        )

    def public_user_profile(self, user_id):
        rows = self._rows(
            "SELECT login_id,display_name,department,role,is_active,created_at,last_login_at "
            "FROM app_user WHERE user_id=?",
            (user_id,),
        )
        return rows[0] if rows else None
