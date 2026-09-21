"""Phase 10A bounded 조회와 QC 검토 계약을 합성 DB에서 검증한다."""

import sqlite3
from contextlib import closing

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.app_read import WorkHistoryRequest
from small_stream_research_tool.models.current_value_errors import (
    CurrentValueBlockedByQualityError,
)
from small_stream_research_tool.models.import_preparation import ImportFieldPolicy
from small_stream_research_tool.models.phase10_read import (
    InvalidPhase10ReadRequest,
    PageRequest,
    QCIssueRequest,
)
from small_stream_research_tool.models.qc_review import (
    QCReviewError,
    QCReviewPersistenceError,
    QCReviewRequest,
)
from small_stream_research_tool.models.quality_control import QualityControlRequest
from small_stream_research_tool.services.app_read_service import AppReadService
from small_stream_research_tool.services.current_value_service import CurrentValueService
from small_stream_research_tool.services.phase10_import_policy_service import (
    Phase10ImportPolicyService,
)
from small_stream_research_tool.services.phase10_read_service import Phase10ReadService
from small_stream_research_tool.services.qc_review_service import QCReviewService
from small_stream_research_tool.services.quality_control_service import QualityControlService

STAMP = "2026-09-22T00:00:00Z"
STREAM = "01234567001"
DIGEST = "a" * 64


@pytest.fixture
def ctx(tmp_path):
    path = tmp_path / "phase10a.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        with transaction(connection):
            actor = connection.execute(
                "INSERT INTO app_user "
                "(login_id,password_hash,display_name,is_active,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                ("synthetic_actor", "synthetic-only", "합성 작업자", 1, STAMP, STAMP),
            ).lastrowid
            inactive = connection.execute(
                "INSERT INTO app_user "
                "(login_id,password_hash,display_name,is_active,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                ("inactive_actor", "synthetic-only", "비활성 작업자", 0, STAMP, STAMP),
            ).lastrowid
            connection.execute(
                "INSERT INTO small_stream (stream_code,province_code,city_county_code,town_code,"
                "stream_serial_no,stream_name,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (STREAM, "01", "234", "567", "001", "합성 하천", STAMP, STAMP),
            )
            category = connection.execute(
                "INSERT INTO data_category (category_key,category_name,created_at,updated_at) "
                "VALUES (?,?,?,?)",
                ("synthetic", "합성", STAMP, STAMP),
            ).lastrowid
            version = connection.execute(
                "INSERT INTO dictionary_version (version,created_at) VALUES (?,?)",
                ("synthetic-v1", STAMP),
            ).lastrowid
            item = connection.execute(
                "INSERT INTO data_dictionary (internal_name,standard_name,category_id,"
                "data_type,storage_type,created_version_id,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("synthetic_area", "합성 면적", category, "REAL", "FLEX", version, STAMP, STAMP),
            ).lastrowid
            for index in range(55):
                source = connection.execute(
                    "INSERT INTO source_file (file_name,original_path,file_hash,registered_at) "
                    "VALUES (?,?,?,?)",
                    (
                        "C:/PRIVATE/합성 54.xlsx" if index == 54 else f"합성 {index}.xlsx",
                        "C:/PRIVATE/source.xlsx",
                        DIGEST,
                        STAMP,
                    ),
                ).lastrowid
                imported = connection.execute(
                    "INSERT INTO import_history (source_file_id,batch_code,import_type,status,"
                    "started_at,accepted_rows,created_at) VALUES (?,?,?,?,?,?,?)",
                    (source, f"synthetic-{index}", "SYNTHETIC", "SUCCESS", STAMP, index, STAMP),
                ).lastrowid
                connection.execute(
                    "INSERT INTO import_sheet (import_id,sheet_name,status,created_at) "
                    "VALUES (?,?,?,?)",
                    (imported, "합성 시트", "SUCCESS", STAMP),
                )
                connection.execute(
                    "INSERT INTO data_quality_issue (stream_code,dictionary_id,issue_type,"
                    "severity,message,created_at) VALUES (?,?,?,?,?,?)",
                    (STREAM, item, "VALUE_OUT_OF_RANGE", "WARNING", "PRIVATE QC", STAMP),
                )
        yield connection, actor, inactive, item


def test_import_history_duplicate_and_qc_pages_are_bounded_and_read_only(ctx):
    connection, _, _, _ = ctx
    service = Phase10ReadService(connection)
    before = connection.total_changes
    snapshot = tuple(connection.iterdump())
    trace = []
    connection.set_trace_callback(trace.append)
    try:
        first = service.list_import_history(PageRequest(page_size=20))
        last = service.list_import_history(PageRequest(page=3, page_size=20))
        duplicates = service.find_duplicate_imports(DIGEST)
        issues = service.list_qc_issues(QCIssueRequest(page_size=20, severity="WARNING"))
    finally:
        connection.set_trace_callback(None)
    assert (first.total_count, first.total_pages, len(first.items)) == (55, 3, 20)
    assert first.items[0].file_name == "합성 54.xlsx"
    assert len(last.items) == 15
    assert len(duplicates) == 20 and duplicates[0].status == "SUCCESS"
    assert (issues.total_count, len(issues.items)) == (55, 20)
    assert issues.items[0].standard_name is None
    assert service.get_qc_issue(1).issue_type == "VALUE_OUT_OF_RANGE"
    assert "PRIVATE" not in repr((first, duplicates, issues))
    assert "C:/" not in repr((first, duplicates, issues))
    page_selects = (
        sql
        for sql in trace
        if "SELECT" in sql
        and "count(" not in sql.lower()
        and (
            "FROM import_history h JOIN" in sql
            or "FROM source_file f JOIN import_history h" in sql
            or "FROM data_quality_issue q " in sql
        )
    )
    assert all("LIMIT" in sql for sql in page_selects)
    assert connection.total_changes == before
    assert tuple(connection.iterdump()) == snapshot
    with pytest.raises(InvalidPhase10ReadRequest):
        service.find_duplicate_imports("invalid")
    with pytest.raises(InvalidPhase10ReadRequest):
        service.list_qc_issues(QCIssueRequest(page_size=1000))


def test_empty_pages_invalid_filters_and_duplicate_filename_independence(ctx):
    connection, actor, _, _ = ctx
    service = Phase10ReadService(connection)
    assert service.list_import_history(PageRequest(page=9)).items == ()
    assert service.list_qc_issues(QCIssueRequest(page=9)).items == ()
    assert service.get_qc_issue(9999) is None
    for request in (PageRequest(page=0), PageRequest(page_size=101), PageRequest(page=True)):
        with pytest.raises(InvalidPhase10ReadRequest):
            service.list_import_history(request)
    for request in (
        QCIssueRequest(severity=[]),
        QCIssueRequest(review_status={}),
        QCIssueRequest(severity="NORMAL"),
        QCIssueRequest(stream_code="123"),
    ):
        with pytest.raises(InvalidPhase10ReadRequest):
            service.list_qc_issues(request)
    connection.execute("UPDATE import_history SET status='FAILED' WHERE batch_code='synthetic-54'")
    duplicates = service.find_duplicate_imports(DIGEST)
    assert duplicates[0].status == "FAILED" and duplicates[1].status == "SUCCESS"
    assert duplicates[0].file_name != duplicates[1].file_name
    assert all("PRIVATE" not in repr(row) and "C:/" not in repr(row) for row in duplicates)
    QCReviewService(connection).review(QCReviewRequest(1, actor, "IN_REVIEW"))
    filtered = service.list_qc_issues(
        QCIssueRequest(severity="WARNING", review_status="IN_REVIEW", stream_code=STREAM)
    )
    assert filtered.total_count == 1 and filtered.items[0].issue_id == 1


def test_empty_database_public_pages(tmp_path):
    path = tmp_path / "empty.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as connection:
        service = Phase10ReadService(connection)
        imports = service.list_import_history()
        qc = service.list_qc_issues()
        assert (imports.total_count, imports.total_pages, imports.items) == (0, 0, ())
        assert (qc.total_count, qc.total_pages, qc.items) == (0, 0, ())
        assert service.find_duplicate_imports(DIGEST) == ()


def test_qc_page_select_count_does_not_scale_with_rows(ctx):
    connection, _, _, _ = ctx
    service = Phase10ReadService(connection)
    trace = []
    connection.set_trace_callback(trace.append)
    try:
        service.list_qc_issues(QCIssueRequest(page_size=1))
        one = sum(sql.lstrip().upper().startswith("SELECT") for sql in trace)
        trace.clear()
        service.list_qc_issues(QCIssueRequest(page_size=50))
        fifty = sum(sql.lstrip().upper().startswith("SELECT") for sql in trace)
    finally:
        connection.set_trace_callback(None)
    assert one == fifty


def test_qc_review_transitions_noop_audit_and_safe_history(ctx):
    connection, actor, _, _ = ctx
    service = QCReviewService(connection)
    first = service.review(QCReviewRequest(1, actor, "IN_REVIEW", note="PRIVATE NOTE"))
    assert first.changed
    assert not service.review(QCReviewRequest(1, actor, "IN_REVIEW")).changed
    second = service.review(QCReviewRequest(1, actor, "CONFIRMED", result="PRIVATE RESULT"))
    assert second.changed
    row = connection.execute(
        "SELECT review_status,reviewed_by_user_id,review_note,review_result,is_active,severity "
        "FROM data_quality_issue WHERE issue_id=1"
    ).fetchone()
    assert row == ("CONFIRMED", actor, "PRIVATE NOTE", "PRIVATE RESULT", 1, "WARNING")
    history = AppReadService(connection).list_work_history(
        WorkHistoryRequest(change_type="QC_REVIEW")
    )
    assert history.total_count == 2
    assert all(i.target_state == "RESOLVED" and i.stream_code == STREAM for i in history.items)
    assert "PRIVATE NOTE" not in repr(history) and "PRIVATE RESULT" not in repr(history)
    assert "issue_id" not in repr(history) and "record_key" not in repr(history)
    assert (
        AppReadService(connection).get_home_summary().recent_history[0].change_type == "QC_REVIEW"
    )
    assert AppReadService(connection).recent_user_work(actor)[0].change_type == "QC_REVIEW"


def test_qc_review_rejects_invalid_actor_issue_transition_and_text(ctx):
    connection, actor, inactive, _ = ctx
    service = QCReviewService(connection)
    for request in (
        QCReviewRequest(1, 99999, "IN_REVIEW"),
        QCReviewRequest(1, None, "IN_REVIEW"),
        QCReviewRequest(99999, actor, "IN_REVIEW"),
        QCReviewRequest(1, inactive, "IN_REVIEW"),
        QCReviewRequest(1, actor, "CONFIRMED"),
        QCReviewRequest(1, actor, "IN_REVIEW", note="x" * 501),
        QCReviewRequest(1, actor, "IN_REVIEW", result="x" * 201),
        QCReviewRequest(1, actor, "IN_REVIEW", note="   "),
        QCReviewRequest(1, actor, "IN_REVIEW", result=""),
    ):
        with pytest.raises(QCReviewError):
            service.review(request)
    connection.execute("UPDATE data_quality_issue SET is_active=0 WHERE issue_id=1")
    with pytest.raises(QCReviewError):
        service.review(QCReviewRequest(1, actor, "IN_REVIEW"))
    assert connection.execute("SELECT count(*) FROM record_history").fetchone()[0] == 0


def test_qc_review_commit_failure_rolls_back(ctx):
    connection, actor, _, _ = ctx

    class CommitFailConnection:
        @property
        def in_transaction(self):
            return connection.in_transaction

        def execute(self, sql, parameters=()):
            if sql == "COMMIT":
                raise sqlite3.OperationalError("PRIVATE COMMIT FAILURE")
            return connection.execute(sql, parameters)

    service = QCReviewService(CommitFailConnection())
    with pytest.raises(QCReviewPersistenceError) as error:
        service.review(QCReviewRequest(1, actor, "IN_REVIEW", note="PRIVATE NOTE"))
    assert "PRIVATE" not in str(error.value)
    assert connection.execute(
        "SELECT review_status,review_note,reviewed_by_user_id,reviewed_at "
        "FROM data_quality_issue WHERE issue_id=1"
    ).fetchone() == ("UNREVIEWED", None, None, None)
    assert connection.execute("SELECT count(*) FROM record_history").fetchone()[0] == 0


def test_qc_review_preserves_home_severity_and_current_use_error_gate(ctx):
    connection, actor, _, item_id = ctx
    value_id = connection.execute(
        "INSERT INTO characteristic_value "
        "(stream_code,dictionary_id,value_number,created_at,updated_at) VALUES (?,?,?,?,?)",
        (STREAM, item_id, 12.0, STAMP, STAMP),
    ).lastrowid
    issue_id = connection.execute(
        "INSERT INTO data_quality_issue "
        "(characteristic_value_id,issue_type,severity,message,created_at) "
        "VALUES (?,?,?,?,?)",
        (value_id, "VALUE_OUT_OF_RANGE", "ERROR", "PRIVATE QC", STAMP),
    ).lastrowid
    before = AppReadService(connection).get_home_summary()
    QCReviewService(connection).review(QCReviewRequest(issue_id, actor, "IN_REVIEW"))
    QCReviewService(connection).review(QCReviewRequest(issue_id, actor, "CONFIRMED"))
    after = AppReadService(connection).get_home_summary()
    assert (after.error_stream_count, after.needs_review_stream_count) == (
        before.error_stream_count,
        before.needs_review_stream_count,
    )
    with pytest.raises(CurrentValueBlockedByQualityError):
        CurrentValueService(connection).select_current_value(value_id, actor)
    assert (
        connection.execute(
            "SELECT is_representative FROM characteristic_value WHERE characteristic_value_id=?",
            (value_id,),
        ).fetchone()[0]
        == 0
    )


def test_qc_review_malformed_legacy_history_and_actor_filter(ctx):
    connection, actor, other, _ = ctx
    QCReviewService(connection).review(QCReviewRequest(1, actor, "IN_REVIEW"))
    connection.execute(
        "INSERT INTO record_history "
        "(table_name,record_key,change_type,actor_user_id,changed_at) "
        "VALUES (?,?,?,?,?)",
        ("data_quality_issue", "PRIVATE INVALID JSON", "QC_REVIEW", other, STAMP),
    )
    service = AppReadService(connection)
    page = service.list_work_history(WorkHistoryRequest(change_type="QC_REVIEW"))
    assert page.total_count == 2
    assert page.items[0].target_state == "UNRESOLVED"
    assert page.items[0].stream_code is None
    assert "PRIVATE" not in repr(page)
    own = service.recent_user_work(actor)
    assert len(own) == 1 and own[0].actor_display_name == "합성 작업자"
    assert service.recent_user_work(other)[0].target_state == "UNRESOLVED"
    assert (
        service.list_work_history(
            WorkHistoryRequest(change_type="QC_REVIEW", actor_user_id=actor)
        ).total_count
        == 1
    )


def test_qc_review_audit_failure_rolls_back(ctx, monkeypatch):
    connection, actor, _, _ = ctx
    service = QCReviewService(connection)

    def fail(*_args):
        raise RuntimeError("PRIVATE FAILURE")

    monkeypatch.setattr(service._repository, "audit", fail)
    with pytest.raises(QCReviewPersistenceError) as error:
        service.review(QCReviewRequest(1, actor, "IN_REVIEW"))
    assert "PRIVATE" not in str(error.value)
    assert (
        connection.execute(
            "SELECT review_status FROM data_quality_issue WHERE issue_id=1"
        ).fetchone()[0]
        == "UNREVIEWED"
    )
    assert connection.execute("SELECT count(*) FROM record_history").fetchone()[0] == 0


def test_qc_review_without_characteristic_has_safe_stream_target(ctx):
    connection, actor, _, _ = ctx
    issue_id = connection.execute(
        "INSERT INTO data_quality_issue (stream_code,issue_type,severity,message,created_at) "
        "VALUES (?,?,?,?,?)",
        (STREAM, "REQUIRED_VALUE_MISSING", "INFO", "PRIVATE QC", STAMP),
    ).lastrowid
    result = QCReviewService(connection).review(QCReviewRequest(issue_id, actor, "IN_REVIEW"))
    assert result.changed
    history = AppReadService(connection).list_work_history(
        WorkHistoryRequest(change_type="QC_REVIEW")
    )
    assert history.items[0].target_state == "RESOLVED"
    assert history.items[0].dictionary_standard_name == "특성항목 미지정"
    assert "PRIVATE" not in repr(history)


def test_qc_read_resolves_value_scoped_issue_without_direct_stream_fields(ctx):
    connection, _, _, item_id = ctx
    value_id = connection.execute(
        "INSERT INTO characteristic_value "
        "(stream_code,dictionary_id,value_number,created_at,updated_at) "
        "VALUES (?,?,?,?,?)",
        (STREAM, item_id, 12.0, STAMP, STAMP),
    ).lastrowid
    issue_id = connection.execute(
        "INSERT INTO data_quality_issue "
        "(characteristic_value_id,issue_type,severity,message,created_at) "
        "VALUES (?,?,?,?,?)",
        (value_id, "UNIT_MISSING", "WARNING", "PRIVATE QC", STAMP),
    ).lastrowid
    service = Phase10ReadService(connection)
    item = service.get_qc_issue(issue_id)
    assert item.stream_code == STREAM
    assert item.stream_name == "합성 하천"
    assert item.standard_name is None
    assert "PRIVATE" not in repr(item)
    assert service.list_qc_issues(QCIssueRequest(stream_code=STREAM)).total_count == 56


def test_import_policy_is_deny_by_default_and_unit_is_not_inferred(ctx):
    connection, _, _, item_id = ctx
    service = Phase10ImportPolicyService(connection)
    policies = service.policies()
    assert "synthetic_area" in policies.preview.excluded_internal_names
    assert "synthetic_area" in policies.import_fields.excluded_internal_names
    assert "stream_name" in policies.approved_internal_names
    assert service.unit_confirmation(item_id).status == "NOT_APPLICABLE"
    assert service.unit_confirmation(item_id, "decorative unit").status == "NEEDS_REVIEW"
    unit_id = connection.execute(
        "INSERT INTO unit_dictionary (unit_name,unit_symbol,created_at,updated_at) "
        "VALUES (?,?,?,?)",
        ("합성 단위", "km", STAMP, STAMP),
    ).lastrowid
    connection.execute(
        "UPDATE data_dictionary SET unit_id=? WHERE dictionary_id=?", (unit_id, item_id)
    )
    assert service.unit_confirmation(item_id).status == "NEEDS_REVIEW"
    assert service.unit_confirmation(item_id, "decorative km").status == "NEEDS_REVIEW"
    assert service.unit_confirmation(item_id, "km").status == "CONFIRMED"


def test_review_then_recheck_retains_old_audit_and_new_issue_starts_unreviewed(ctx):
    connection, actor, _, item_id = ctx
    connection.execute(
        "INSERT INTO quality_rule "
        "(rule_code,rule_name,target_type,dictionary_id,rule_type,default_severity,"
        "rule_version,is_enabled,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "synthetic_nonnegative",
            "합성 규칙",
            "CHARACTERISTIC_VALUE",
            item_id,
            "NON_NEGATIVE",
            "WARNING",
            "synthetic-v1",
            1,
            STAMP,
            STAMP,
        ),
    )
    value_id = connection.execute(
        "INSERT INTO characteristic_value "
        "(stream_code,dictionary_id,value_number,created_at,updated_at) VALUES (?,?,?,?,?)",
        (STREAM, item_id, -1.0, STAMP, STAMP),
    ).lastrowid
    qc = QualityControlService(connection)
    request = QualityControlRequest((value_id,), ())
    first = qc.recheck(request, field_policy=ImportFieldPolicy())
    (old_issue,) = first.created_issue_ids
    review = QCReviewService(connection)
    review.review(QCReviewRequest(old_issue, actor, "IN_REVIEW", note="합성 검토"))
    review.review(QCReviewRequest(old_issue, actor, "CONFIRMED"))
    connection.execute(
        "UPDATE characteristic_value SET value_number=2 WHERE characteristic_value_id=?",
        (value_id,),
    )
    resolved = qc.recheck(request, field_policy=ImportFieldPolicy())
    assert resolved.deactivated_issue_ids == (old_issue,)
    assert connection.execute(
        "SELECT is_active,review_status,review_note FROM data_quality_issue WHERE issue_id=?",
        (old_issue,),
    ).fetchone() == (0, "CONFIRMED", "합성 검토")
    connection.execute(
        "UPDATE characteristic_value SET value_number=-2 WHERE characteristic_value_id=?",
        (value_id,),
    )
    recurring = qc.recheck(request, field_policy=ImportFieldPolicy())
    assert recurring.created_issue_ids != (old_issue,)
    assert (
        connection.execute(
            "SELECT review_status FROM data_quality_issue WHERE issue_id=?",
            (recurring.created_issue_ids[0],),
        ).fetchone()[0]
        == "UNREVIEWED"
    )
    assert (
        AppReadService(connection)
        .list_work_history(WorkHistoryRequest(change_type="QC_REVIEW"))
        .total_count
        == 2
    )
