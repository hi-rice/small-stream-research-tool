"""QC 검토 상태와 감사이력의 한 transaction 내 SQL."""

import json


def _compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class QCReviewRepository:
    def __init__(self, connection):
        self._connection = connection

    def issue(self, issue_id):
        return self._connection.execute(
            "SELECT q.review_status,q.is_active,COALESCE(q.stream_code,v.stream_code),"
            "COALESCE(q.dictionary_id,v.dictionary_id),q.reviewed_at "
            "FROM data_quality_issue q LEFT JOIN characteristic_value v "
            "ON v.characteristic_value_id=q.characteristic_value_id WHERE q.issue_id=?",
            (issue_id,),
        ).fetchone()

    def actor_active(self, user_id):
        row = self._connection.execute(
            "SELECT is_active FROM app_user WHERE user_id=?", (user_id,)
        ).fetchone()
        return row is not None and row[0] == 1

    def target_exists(self, stream_code, dictionary_id):
        stream = self._connection.execute(
            "SELECT 1 FROM small_stream WHERE stream_code=?", (stream_code,)
        ).fetchone()
        if stream is None:
            return False
        if dictionary_id is None:
            return True
        item = self._connection.execute(
            "SELECT 1 FROM data_dictionary WHERE dictionary_id=?", (dictionary_id,)
        ).fetchone()
        return item is not None

    def change(self, request, old_status, timestamp):
        updated = self._connection.execute(
            "UPDATE data_quality_issue SET review_status=?,"
            "review_note=COALESCE(?,review_note),review_result=COALESCE(?,review_result),"
            "reviewed_by_user_id=?,reviewed_at=? WHERE issue_id=? AND is_active=1 "
            "AND review_status=?",
            (
                request.review_status,
                request.note,
                request.result,
                request.actor_user_id,
                timestamp,
                request.issue_id,
                old_status,
            ),
        )
        return updated.rowcount == 1

    def audit(self, issue_id, stream_code, dictionary_id, old, new, actor_id, timestamp):
        self._connection.execute(
            "INSERT INTO record_history (issue_id,table_name,record_key,column_name,"
            "old_value,new_value,change_type,actor_user_id,changed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                issue_id,
                "data_quality_issue",
                _compact({"stream_code": stream_code, "dictionary_id": dictionary_id}),
                "review_status",
                _compact({"review_status": old}),
                _compact({"review_status": new}),
                "QC_REVIEW",
                actor_id,
                timestamp,
            ),
        )
