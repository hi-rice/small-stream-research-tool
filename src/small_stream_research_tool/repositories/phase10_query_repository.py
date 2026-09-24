"""Import 이력과 QC issue의 bounded SELECT 전용 저장소."""


class Phase10QueryRepository:
    def __init__(self, connection):
        self._connection = connection

    def count_imports(self):
        return self._connection.execute("SELECT count(*) FROM import_history").fetchone()[0]

    def page_imports(self, limit, offset):
        return self._connection.execute(
            "SELECT h.import_id,f.file_name,(SELECT sh.sheet_name FROM import_sheet sh "
            "WHERE sh.import_id=h.import_id ORDER BY sh.import_sheet_id LIMIT 1),"
            "h.status,h.started_at,h.finished_at,h.accepted_rows,h.rejected_rows "
            "FROM import_history h JOIN source_file f ON f.source_file_id=h.source_file_id "
            "ORDER BY h.import_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()

    def page_import_ids(self, limit, offset):
        return tuple(
            row[0]
            for row in self._connection.execute(
                "SELECT import_id FROM import_history ORDER BY import_id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        )

    def same_hash(self, digest, limit):
        return self._connection.execute(
            "SELECT f.file_name,h.status,h.started_at,h.finished_at,h.accepted_rows "
            "FROM source_file f JOIN import_history h ON h.source_file_id=f.source_file_id "
            "WHERE f.file_hash=? ORDER BY h.import_id DESC LIMIT ?",
            (digest, limit),
        ).fetchall()

    @staticmethod
    def _qc_where(request):
        clauses = ["q.is_active=1"]
        params = []
        for column, value in (
            ("q.severity", request.severity),
            ("q.review_status", request.review_status),
            ("COALESCE(q.stream_code,v.stream_code)", request.stream_code),
        ):
            if value is not None:
                clauses.append(column + "=?")
                params.append(value)
        return " WHERE " + " AND ".join(clauses), tuple(params)

    def count_qc(self, request):
        where, params = self._qc_where(request)
        return self._connection.execute(
            "SELECT count(*) FROM data_quality_issue q "
            "LEFT JOIN characteristic_value v "
            "ON v.characteristic_value_id=q.characteristic_value_id" + where,
            params,
        ).fetchone()[0]

    def page_qc(self, request):
        where, params = self._qc_where(request)
        return self._connection.execute(
            "SELECT q.issue_id,q.issue_type,q.severity,q.review_status,"
            "COALESCE(q.stream_code,v.stream_code),s.stream_name,d.standard_name,"
            "q.created_at,q.reviewed_at,u.display_name,"
            "d.dictionary_id "
            "FROM data_quality_issue q "
            "LEFT JOIN characteristic_value v "
            "ON v.characteristic_value_id=q.characteristic_value_id "
            "LEFT JOIN small_stream s ON s.stream_code=COALESCE(q.stream_code,v.stream_code) "
            "LEFT JOIN data_dictionary d "
            "ON d.dictionary_id=COALESCE(q.dictionary_id,v.dictionary_id) "
            "LEFT JOIN app_user u ON u.user_id=q.reviewed_by_user_id "
            + where
            + " ORDER BY q.issue_id DESC LIMIT ? OFFSET ?",
            (*params, request.page_size, (request.page - 1) * request.page_size),
        ).fetchall()

    def qc_detail(self, issue_id):
        return self._connection.execute(
            "SELECT q.issue_id,q.issue_type,q.severity,q.review_status,"
            "COALESCE(q.stream_code,v.stream_code),s.stream_name,d.standard_name,"
            "q.created_at,q.reviewed_at,u.display_name,"
            "d.dictionary_id FROM data_quality_issue q "
            "LEFT JOIN characteristic_value v "
            "ON v.characteristic_value_id=q.characteristic_value_id "
            "LEFT JOIN small_stream s ON s.stream_code=COALESCE(q.stream_code,v.stream_code) "
            "LEFT JOIN data_dictionary d "
            "ON d.dictionary_id=COALESCE(q.dictionary_id,v.dictionary_id) "
            "LEFT JOIN app_user u ON u.user_id=q.reviewed_by_user_id "
            "WHERE q.issue_id=? AND q.is_active=1 LIMIT 1",
            (issue_id,),
        ).fetchone()
