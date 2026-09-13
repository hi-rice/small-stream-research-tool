"""합성 사전·규칙·값만으로 QC 판정, snapshot, 중복 방지와 rollback을 검증한다."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import FrozenInstanceError
from threading import Barrier
from types import SimpleNamespace

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.import_preparation import ImportFieldPolicy
from small_stream_research_tool.models.quality_control import (
    QualityControlRequest,
    RequiredImportTarget,
)
from small_stream_research_tool.models.quality_control_errors import (
    QualityControlError,
    QualityControlPersistenceError,
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
from small_stream_research_tool.services.dictionary_service import DictionaryService
from small_stream_research_tool.services.quality_control_service import QualityControlService

STAMP = "2026-09-13T01:02:03Z"
STREAM = "12345678009"
SECRET = "SYNTHETIC_PRIVATE_QC_VALUE"
PATH = "C:/synthetic-only/private.xlsx"
POLICY = ImportFieldPolicy(frozenset({"synthetic_secret"}))


@pytest.fixture
def ctx(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as conn:
        dictionary = DictionaryService(DictionaryRepository(conn))
        category = dictionary.create_category("synthetic", "Synthetic")
        version = dictionary.create_version("synthetic-v1")
        items = {}
        for dtype in ("REAL", "INTEGER", "TEXT", "DATE", "DATETIME"):
            items[dtype] = dictionary.create_item(
                "Synthetic " + dtype,
                "synthetic_" + dtype.lower(),
                category.category_id,
                dtype,
                version.version_id,
                required=True,
            )
        with transaction(conn):
            stream = SmallStreamRepository(conn).create(
                stream_code=STREAM,
                province_code="12",
                city_county_code="345",
                town_code="678",
                stream_serial_no="009",
                stream_name="Synthetic Stream",
                created_at=STAMP,
                updated_at=STAMP,
            )
            source = SourceFileRepository(conn).create(
                file_name="synthetic.xlsx", original_path=PATH, registered_at=STAMP
            )
            history = ImportHistoryRepository(conn).create(
                source_file_id=source.source_file_id,
                batch_code="synthetic",
                import_type="EXCEL",
                status="SUCCESS",
                started_at=STAMP,
                finished_at=STAMP,
                created_at=STAMP,
            )
            sheet = ImportSheetRepository(conn).create(
                import_id=history.import_id,
                sheet_name="Synthetic",
                status="SUCCESS",
                created_at=STAMP,
            )
            mapping = ImportColumnMappingRepository(conn).create(
                import_sheet_id=sheet.import_sheet_id,
                source_column_index=4,
                dictionary_id=items["REAL"].dictionary_id,
                mapping_status="USER_MAPPED",
                mapping_method="USER",
                created_at=STAMP,
            )
        yield SimpleNamespace(
            conn=conn,
            path=path,
            items=items,
            history=history,
            sheet=sheet,
            mapping=mapping,
            stream=stream,
            service=QualityControlService(conn),
            dictionary=dictionary,
        )


def rule(ctx, kind="NON_NEGATIVE", dtype="REAL", *, params=None, severity="WARNING", enabled=1):
    return ctx.conn.execute(
        "INSERT INTO quality_rule "
        "(rule_code,rule_name,target_type,dictionary_id,rule_type,default_severity,parameters_json,"
        "rule_version,is_enabled,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "synthetic_" + str(ctx.conn.execute("SELECT count(*) FROM quality_rule").fetchone()[0]),
            "Synthetic Rule",
            "STREAM_DICTIONARY" if kind == "REQUIRED" else "CHARACTERISTIC_VALUE",
            ctx.items[dtype].dictionary_id,
            kind,
            severity,
            params,
            "synthetic-v1",
            enabled,
            STAMP,
            STAMP,
        ),
    ).lastrowid


def value(ctx, number=-1.25, dtype="REAL", *, imported=True, **changes):
    field = {
        "REAL": "value_number",
        "INTEGER": "value_integer",
        "TEXT": "value_text",
        "DATE": "value_date",
        "DATETIME": "value_date",
    }[dtype]
    data = dict(
        stream_code=STREAM,
        dictionary_id=ctx.items[dtype].dictionary_id,
        **{field: number},
        original_value=SECRET,
        created_at=STAMP,
        updated_at=STAMP,
    )
    if imported:
        data.update(
            import_id=ctx.history.import_id,
            import_sheet_id=ctx.sheet.import_sheet_id,
            source_row=3,
            mapping_id=ctx.mapping.mapping_id if dtype == "REAL" else None,
        )
    data.update(changes)
    with transaction(ctx.conn):
        return CharacteristicValueRepository(ctx.conn).create(**data).characteristic_value_id


def run(ctx, *ids, targets=(), policy=POLICY):
    return ctx.service.run(QualityControlRequest(tuple(ids), tuple(targets)), field_policy=policy)


def required(ctx, dtype="REAL", import_id=None):
    return RequiredImportTarget(
        STREAM,
        ctx.items[dtype].dictionary_id,
        ctx.history.import_id if import_id is None else import_id,
    )


def issues(ctx):
    cursor = ctx.conn.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute("SELECT * FROM data_quality_issue ORDER BY issue_id").fetchall()


def recheck(ctx, *ids, targets=(), **kwargs):
    return ctx.service.recheck(
        QualityControlRequest(tuple(ids), tuple(targets)), field_policy=POLICY, **kwargs
    )


def test_keep_resolve_recur(ctx):
    rule(ctx)
    vid = value(ctx)
    first = recheck(ctx, vid)
    (issue_id,) = first.created_issue_ids
    ctx.conn.execute(
        "UPDATE data_quality_issue SET review_status='CONFIRMED', review_note='note', "
        "review_result='result', reviewed_at=?",
        (STAMP,),
    )
    before = tuple(issues(ctx)[0])
    kept = recheck(ctx, vid)
    assert kept.kept_issue_ids == (issue_id,)
    assert tuple(issues(ctx)[0]) == before
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_number=2 WHERE characteristic_value_id=?", (vid,)
    )
    resolved = recheck(ctx, vid)
    assert resolved.deactivated_issue_ids == (issue_id,)
    assert resolved.qc_status == "NORMAL"
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_number=-2 WHERE characteristic_value_id=?", (vid,)
    )
    recurring = recheck(ctx, vid)
    assert recurring.created_issue_ids != (issue_id,)
    assert len(issues(ctx)) == 2
    assert issues(ctx)[0]["is_active"] == 0
    assert issues(ctx)[1]["review_status"] == "UNREVIEWED"
    assert issues(ctx)[0]["review_note"] == "note"


@pytest.mark.parametrize(
    "status", ["UNREVIEWED", "IN_REVIEW", "CONFIRMED", "CORRECTED", "DEFERRED"]
)
@pytest.mark.parametrize(
    "severity,expected", [("ERROR", "ERROR"), ("WARNING", "NEEDS_REVIEW"), ("INFO", "NEEDS_REVIEW")]
)
def test_review_independent_status(ctx, status, severity, expected):
    rule(ctx, severity=severity)
    vid = value(ctx)
    recheck(ctx, vid)
    ctx.conn.execute("UPDATE data_quality_issue SET review_status=?", (status,))
    result = recheck(ctx, vid)
    assert result.qc_status == expected
    assert issues(ctx)[0]["review_status"] == status
    assert result.checked_count == result.finding_count == 1


@pytest.mark.parametrize("change", ["version", "severity", "parameters"])
def test_changed_definition_preserves_old_snapshot(ctx, change):
    rid = rule(ctx, "RANGE", params='{"min":0}')
    vid = value(ctx)
    first = recheck(ctx, vid)
    old = dict(issues(ctx)[0])
    if change == "version":
        ctx.conn.execute("UPDATE quality_rule SET rule_version='v2' WHERE rule_id=?", (rid,))
    elif change == "severity":
        ctx.conn.execute("UPDATE quality_rule SET default_severity='ERROR' WHERE rule_id=?", (rid,))
    else:
        ctx.conn.execute(
            "UPDATE quality_rule SET parameters_json=? WHERE rule_id=?", ('{"min":1}', rid)
        )
    result = recheck(ctx, vid)
    assert result.deactivated_issue_ids == first.created_issue_ids
    assert len(result.created_issue_ids) == 1
    old["is_active"] = 0
    assert dict(issues(ctx)[0]) == old


def test_disabled_not_resolved(ctx):
    rid = rule(ctx, severity="ERROR")
    vid = value(ctx)
    recheck(ctx, vid)
    before = [tuple(r) for r in issues(ctx)]
    ctx.conn.execute("UPDATE quality_rule SET is_enabled=0")
    result = recheck(ctx, vid, rule_ids=(rid,))
    assert result.checked_count == 0 and result.qc_status == "ERROR"
    assert [tuple(r) for r in issues(ctx)] == before


def test_rule_and_value_scope_protection(ctx):
    rid = rule(ctx)
    rule(ctx)
    a, b = value(ctx), value(ctx)
    recheck(ctx, a, b)
    ctx.conn.execute("UPDATE characteristic_value SET value_number=2")
    result = recheck(ctx, a, rule_ids=(rid,))
    assert len(result.deactivated_issue_ids) == 1
    assert sum(r["is_active"] for r in issues(ctx)) == 3
    assert result.qc_status == "NEEDS_REVIEW"


def test_required_lifecycle(ctx):
    rule(ctx, "REQUIRED")
    target = required(ctx)
    first = recheck(ctx, targets=(target,))
    assert len(first.created_issue_ids) == 1
    assert recheck(ctx, targets=(target,)).kept_issue_ids == first.created_issue_ids
    vid = value(ctx, 2)
    assert recheck(ctx, targets=(target,)).deactivated_issue_ids == first.created_issue_ids
    ctx.conn.execute(
        "UPDATE characteristic_value SET is_active=0 WHERE characteristic_value_id=?", (vid,)
    )
    assert len(recheck(ctx, targets=(target,)).created_issue_ids) == 1
    assert len(issues(ctx)) == 2


@pytest.mark.parametrize("number", [-5.0, 0.0, 5.0])
def test_range_resolution(ctx, number):
    rule(ctx, "RANGE", params='{"min":10}')
    vid = value(ctx, number)
    first = recheck(ctx, vid)
    ctx.conn.execute("UPDATE quality_rule SET parameters_json=?", ('{"min":-10}',))
    result = recheck(ctx, vid)
    assert result.deactivated_issue_ids == first.created_issue_ids
    assert result.finding_count == 0


@pytest.mark.parametrize("rule_ids", [(), (0,), (-1,), (True,), (999,), [1], (1, 1)])
def test_invalid_filter_rolls_back(ctx, rule_ids):
    rule(ctx)
    vid = value(ctx)
    with pytest.raises(QualityControlError):
        recheck(ctx, vid, rule_ids=rule_ids)
    assert not issues(ctx) and not ctx.conn.in_transaction


@pytest.mark.parametrize("operation", ["INSERT", "UPDATE"])
def test_write_failure_rolls_back(ctx, operation):
    rule(ctx, "RANGE", params='{"min":0}')
    vid = value(ctx)
    recheck(ctx, vid)
    before = [tuple(r) for r in issues(ctx)]
    ctx.conn.execute("UPDATE quality_rule SET rule_version='v2'")
    ctx.conn.execute(
        f"CREATE TRIGGER fail_recheck BEFORE {operation} ON data_quality_issue "
        "BEGIN SELECT RAISE(ABORT, 'private failure'); END"
    )
    with pytest.raises(QualityControlPersistenceError) as caught:
        recheck(ctx, vid)
    assert "private failure" not in str(caught.value)
    assert [tuple(r) for r in issues(ctx)] == before
    assert not ctx.conn.in_transaction


def test_parsing_issue_untouched(ctx):
    rule(ctx)
    vid = value(ctx)
    recheck(ctx, vid)
    ctx.conn.execute("UPDATE data_quality_issue SET issue_type='IMPORT_PARSE_ERROR'")
    before = tuple(issues(ctx)[0])
    ctx.conn.execute("UPDATE characteristic_value SET value_number=2")
    result = recheck(ctx, vid)
    assert not result.deactivated_issue_ids
    assert tuple(issues(ctx)[0]) == before


def test_only_issue_table_changes(ctx):
    rule(ctx)
    vid = value(ctx)
    tables = [
        r[0]
        for r in ctx.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if r[0] != "data_quality_issue"
    ]
    before = {t: [tuple(r) for r in ctx.conn.execute(f'SELECT * FROM "{t}"')] for t in tables}
    result = recheck(ctx, vid)
    assert before == {
        t: [tuple(r) for r in ctx.conn.execute(f'SELECT * FROM "{t}"')] for t in tables
    }
    assert SECRET not in repr(result) and PATH not in repr(result)
    assert result.completed_at.endswith("Z")
    with pytest.raises(FrozenInstanceError):
        result.checked_count = 0


def test_concurrent_rechecks_do_not_duplicate(ctx):
    rule(ctx)
    vid = value(ctx)
    barrier = Barrier(2)

    def worker():
        with closing(connect_database(ctx.path)) as conn:
            barrier.wait()
            return QualityControlService(conn).recheck(
                QualityControlRequest((vid,)), field_policy=POLICY
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sum(len(r.created_issue_ids) for r in results) == 1
    assert len(issues(ctx)) == 1


@pytest.mark.parametrize(
    "column", ["source_row", "source_column", "import_sheet_id", "import_id", "rule_id"]
)
def test_foreign_provenance_not_deactivated(ctx, column):
    rule(ctx)
    vid = value(ctx)
    recheck(ctx, vid)
    # NULL provenance represents another scope and must not be treated as a wildcard.
    ctx.conn.execute(f"UPDATE data_quality_issue SET {column}=NULL")
    before = tuple(issues(ctx)[0])
    ctx.conn.execute("UPDATE characteristic_value SET value_number=2")
    assert not recheck(ctx, vid).deactivated_issue_ids
    assert tuple(issues(ctx)[0]) == before


def test_policy_skipped_scope_not_resolved(ctx):
    rule(ctx)
    vid = value(ctx)
    recheck(ctx, vid)
    before = tuple(issues(ctx)[0])
    result = ctx.service.recheck(
        QualityControlRequest((vid,)), field_policy=ImportFieldPolicy(frozenset({"synthetic_real"}))
    )
    assert result.checked_count == 0
    assert tuple(issues(ctx)[0]) == before


def test_status_failure_rolls_back(ctx, monkeypatch):
    rule(ctx)
    vid = value(ctx)

    def fail(*args):
        raise RuntimeError("private status failure")

    monkeypatch.setattr(ctx.service._repository, "active_severity_counts", fail)
    with pytest.raises(QualityControlPersistenceError):
        recheck(ctx, vid)
    assert not issues(ctx)


def test_commit_failure_rolls_back(ctx):
    rule(ctx)
    vid = value(ctx)

    def authorizer(action, arg1, *args):
        if action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorizer)
    try:
        with pytest.raises(QualityControlPersistenceError):
            recheck(ctx, vid)
    finally:
        ctx.conn.set_authorizer(None)
    assert not issues(ctx) and not ctx.conn.in_transaction


def test_required_other_import_does_not_resolve(ctx):
    rule(ctx, "REQUIRED")
    target = required(ctx)
    first = recheck(ctx, targets=(target,))
    value(ctx, 2, imported=False, source_type="CORRECTION")
    result = recheck(ctx, targets=(target,))
    assert result.kept_issue_ids == first.created_issue_ids


def test_integer_recheck(ctx):
    rule(ctx, dtype="INTEGER")
    vid = value(ctx, -1, dtype="INTEGER")
    first = recheck(ctx, vid)
    ctx.conn.execute("UPDATE characteristic_value SET value_integer=0")
    assert recheck(ctx, vid).deactivated_issue_ids == first.created_issue_ids
