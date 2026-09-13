"""합성 사전·규칙·값만으로 QC 판정, snapshot, 중복 방지와 rollback을 검증한다."""

import json
import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
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
    QualityRuleConfigurationError,
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
    return ctx.conn.execute("SELECT * FROM data_quality_issue ORDER BY issue_id").fetchall()


def test_issue_defaults_snapshot_provenance_and_dedup(ctx):
    rule_id = rule(ctx)
    vid = value(ctx)
    first = run(ctx, vid)
    assert len(first.created_issue_ids) == len(first.findings) == 1
    finding = first.findings[0]
    assert finding.rule_id == rule_id and finding.characteristic_value_id == vid
    assert (
        finding.import_id == ctx.history.import_id
        and finding.import_sheet_id == ctx.sheet.import_sheet_id
    )
    assert finding.source_row == 3 and finding.source_column == 4 and finding.stream_code == STREAM
    assert finding.severity == "WARNING" and finding.issue_type == "NEGATIVE_VALUE"
    assert finding.rule_version_snapshot == "synthetic-v1"
    stored = ctx.conn.execute(
        "SELECT review_status,is_active,rule_version_snapshot,"
        "rule_parameters_snapshot_json,original_value,compare_value,reviewed_by_user_id "
        "FROM data_quality_issue"
    ).fetchone()
    assert stored == ("UNREVIEWED", 1, "synthetic-v1", None, None, None, None)
    before = issues(ctx)
    second = run(ctx, vid)
    assert not second.created_issue_ids and second.existing_issue_ids == first.created_issue_ids
    assert issues(ctx) == before
    assert SECRET not in repr(finding) and PATH not in repr(finding)
    with pytest.raises(FrozenInstanceError):
        finding.severity = "ERROR"


@pytest.mark.parametrize(
    "dtype, number, expected",
    [
        ("REAL", -1.0, 1),
        ("REAL", 0.0, 0),
        ("REAL", 1.0, 0),
        ("INTEGER", -1, 1),
        ("INTEGER", 0, 0),
        ("INTEGER", 1, 0),
    ],
)
def test_non_negative(ctx, dtype, number, expected):
    rule(ctx, dtype=dtype)
    assert len(run(ctx, value(ctx, number, dtype)).findings) == expected


@pytest.mark.parametrize(
    "params, number, expected",
    [
        ({"min": 0}, -1.0, 1),
        ({"min": 0}, 0.0, 0),
        ({"min": 0}, 1.0, 0),
        ({"max": 10}, 10.0, 0),
        ({"max": 10}, 11.0, 1),
        ({"max": 10}, 9.0, 0),
        ({"min": 0, "max": 10}, 0.0, 0),
        ({"min": 0, "max": 10}, 10.0, 0),
        ({"min": 0, "max": 10}, 11.0, 1),
        ({"min": 0, "include_min": False}, 0.0, 1),
        ({"min": 0, "include_min": True}, 0.0, 0),
        ({"max": 10, "include_max": False}, 10.0, 1),
        ({"max": 10, "include_max": True}, 10.0, 0),
        ({"min": 0, "max": 0}, 0.0, 0),
    ],
)
def test_range_boundaries(ctx, params, number, expected):
    rule(ctx, "RANGE", params=json.dumps(params))
    assert len(run(ctx, value(ctx, number)).findings) == expected


@pytest.mark.parametrize(
    "params",
    [
        "bad-json",
        "[]",
        "null",
        "{}",
        '{"min":true}',
        '{"min":"0"}',
        '{"min":null}',
        '{"min":10,"max":0}',
        '{"min":0,"include_min":1}',
        '{"max":1,"include_max":"true"}',
        '{"min":NaN}',
        '{"max":Infinity}',
        '{"min":1e999}',
        '{"min":0,"private":"SYNTHETIC_PRIVATE_QC_VALUE"}',
        '{"include_min":true}',
        '{"min":0,"include_max":false}',
        '{"min":0,"min":1}',
    ],
)
def test_invalid_range_config_not_data_issue(ctx, params):
    rule(ctx, "RANGE", params=params)
    with pytest.raises(QualityRuleConfigurationError) as error:
        run(ctx, value(ctx))
    assert params not in str(error.value) and SECRET not in str(error.value)
    assert issues(ctx) == []


@pytest.mark.parametrize("dtype", ["TEXT", "DATE", "DATETIME"])
@pytest.mark.parametrize("kind", ["NON_NEGATIVE", "RANGE"])
def test_nonnumeric_target_config_error(ctx, dtype, kind):
    rule(ctx, kind, dtype, params='{"min":0}' if kind == "RANGE" else None)
    with pytest.raises(QualityRuleConfigurationError):
        run(ctx, value(ctx))
    assert issues(ctx) == []


def test_required_missing_present_and_other_dictionary(ctx):
    rule(ctx, "REQUIRED")
    value(ctx, 1, "INTEGER")
    first = run(ctx, targets=(required(ctx),))
    assert len(first.created_issue_ids) == 1
    finding = first.findings[0]
    assert finding.characteristic_value_id is None and finding.import_id == ctx.history.import_id
    assert finding.import_sheet_id is None and finding.source_row is None
    assert finding.issue_type == "REQUIRED_VALUE_MISSING"
    second = run(ctx, targets=(required(ctx),))
    assert second.existing_issue_ids == first.created_issue_ids
    value(ctx)
    assert run(ctx, targets=(required(ctx),)).findings == ()
    assert len(issues(ctx)) == 1  # 7B-1은 해결된 과거 issue도 비활성화하지 않는다.
    assert ctx.conn.execute("SELECT is_active FROM data_quality_issue").fetchone()[0] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"import_id": None, "import_sheet_id": None, "mapping_id": None},
        {"source_type": "USER_CORRECTION"},
        {"is_active": 0},
    ],
)
def test_required_does_not_mix_other_scopes(ctx, changes):
    rule(ctx, "REQUIRED")
    value(ctx, **changes)
    assert len(run(ctx, targets=(required(ctx),)).findings) == 1


def test_required_flag_alone_creates_no_implicit_rule(ctx):
    assert ctx.items["REAL"].required
    assert run(ctx, targets=(required(ctx),)).findings == ()


def test_optional_dictionary_required_rule_conflict(ctx):
    rule(ctx, "REQUIRED")
    ctx.conn.execute("UPDATE data_dictionary SET required=0")
    with pytest.raises(QualityRuleConfigurationError):
        run(ctx, targets=(required(ctx),))


def test_disabled_invalid_rule_ignored_and_no_implicit_numeric_rules(ctx):
    rule(ctx, "UNKNOWN", enabled=0, params=SECRET)
    assert not run(ctx, value(ctx)).findings


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE quality_rule SET dictionary_id=NULL",
        "UPDATE quality_rule SET rule_type='REFERENCE_COMPARE'",
        "UPDATE quality_rule SET target_type='UNKNOWN'",
        "UPDATE quality_rule SET rule_version=''",
        "UPDATE data_dictionary SET is_active=0",
        "UPDATE data_dictionary SET storage_type='CORE'",
    ],
)
def test_invalid_rule_links_and_types(ctx, sql):
    rule(ctx)
    vid = value(ctx)
    ctx.conn.execute(sql)
    with pytest.raises(QualityRuleConfigurationError):
        run(ctx, vid)
    assert not issues(ctx)


def test_dictionary_specific_and_selected_values_only(ctx):
    rule(ctx)
    unselected = value(ctx)
    selected = value(ctx, -1, "INTEGER")
    assert not run(ctx, selected).findings
    assert len(run(ctx, unselected).findings) == 1


def test_distinct_rule_value_and_snapshot_not_merged(ctx):
    rule(ctx)
    a, b = value(ctx), value(ctx, -2.0)
    assert len(run(ctx, a, b).created_issue_ids) == 2
    rule(ctx, "RANGE", params='{"min":0}')
    assert len(run(ctx, a).created_issue_ids) == 1
    ctx.conn.execute("UPDATE quality_rule SET rule_version='synthetic-v2' WHERE rule_id=1")
    assert len(run(ctx, a).created_issue_ids) == 1
    assert (
        ctx.conn.execute(
            "SELECT rule_version_snapshot FROM data_quality_issue WHERE issue_id=1"
        ).fetchone()[0]
        == "synthetic-v1"
    )


def test_canonical_parameter_snapshot_and_severity_preserved(ctx):
    rule(ctx, "RANGE", params='{ "max": 10, "min": 0 }', severity="INFO")
    vid = value(ctx)
    first = run(ctx, vid)
    assert first.findings[0].rule_parameters_snapshot_json == '{"max":10,"min":0}'
    ctx.conn.execute("UPDATE quality_rule SET parameters_json=?", ('{"min":0,"max":10}',))
    assert not run(ctx, vid).created_issue_ids
    ctx.conn.execute("UPDATE quality_rule SET default_severity='ERROR'")
    assert len(run(ctx, vid).created_issue_ids) == 1
    assert ctx.conn.execute(
        "SELECT severity FROM data_quality_issue ORDER BY issue_id"
    ).fetchall() == [("INFO",), ("ERROR",)]


def test_inactive_issue_not_dedup_and_review_not_changed(ctx):
    rule(ctx)
    vid = value(ctx)
    run(ctx, vid)
    ctx.conn.execute("UPDATE data_quality_issue SET review_status='CONFIRMED'")
    assert not run(ctx, vid).created_issue_ids
    assert (
        ctx.conn.execute("SELECT review_status FROM data_quality_issue").fetchone()[0]
        == "CONFIRMED"
    )
    ctx.conn.execute("UPDATE data_quality_issue SET is_active=0")
    assert len(run(ctx, vid).created_issue_ids) == 1


@pytest.mark.parametrize(
    "severity, expected",
    [("INFO", "NEEDS_REVIEW"), ("WARNING", "NEEDS_REVIEW"), ("ERROR", "ERROR")],
)
def test_active_qc_status(ctx, severity, expected):
    repo = ctx.service._repository
    assert repo.active_severity_counts(STREAM).status == "NORMAL"
    rule(ctx, severity=severity)
    run(ctx, value(ctx))
    assert repo.active_severity_counts(STREAM).status == expected
    assert repo.count_active_issues(STREAM) == len(repo.list_active_issues(STREAM)) == 1
    ctx.conn.execute("UPDATE data_quality_issue SET is_active=0")
    assert repo.active_severity_counts(STREAM).status == "NORMAL"


def test_mixed_severity_ignores_review_status(ctx):
    rule(ctx, severity="WARNING")
    rule(ctx, severity="ERROR")
    run(ctx, value(ctx))
    ctx.conn.execute("UPDATE data_quality_issue SET review_status='CORRECTED'")
    assert ctx.service._repository.active_severity_counts(STREAM).status == "ERROR"
    ctx.conn.execute("UPDATE data_quality_issue SET is_active=0 WHERE severity='ERROR'")
    assert ctx.service._repository.active_severity_counts(STREAM).status == "NEEDS_REVIEW"


def test_mid_persistence_failure_rolls_back_all_and_hides_errors(ctx, monkeypatch, caplog):
    rule(ctx)
    ids = (value(ctx), value(ctx, -2.0))
    original = ctx.service._repository.create_issue
    calls = []

    def create(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise sqlite3.OperationalError(SECRET + PATH)
        return original(*args, **kwargs)

    monkeypatch.setattr(ctx.service._repository, "create_issue", create)
    with pytest.raises(QualityControlPersistenceError) as error:
        run(ctx, *ids)
    assert issues(ctx) == [] and calls == [1, 1]
    output = "".join(traceback.format_exception(error.value)) + caplog.text
    assert SECRET not in output and PATH not in output


def test_evaluate_readonly_and_repository_needs_transaction(ctx):
    rule(ctx)
    vid = value(ctx)
    ctx.conn.execute("PRAGMA query_only=ON")
    findings = ctx.service.evaluate(QualityControlRequest((vid,)), field_policy=POLICY)
    ctx.conn.execute("PRAGMA query_only=OFF")
    assert findings and not issues(ctx)
    with pytest.raises(QualityControlPersistenceError):
        ctx.service._repository.create_issue(findings[0], timestamp=STAMP)


def test_only_issue_insert_no_other_mutation_or_internal_commit(ctx):
    rule(ctx)
    vid = value(ctx)
    writes, commits = [], []

    def authorize(action, table, _column, _db, _trigger):
        if action == sqlite3.SQLITE_TRANSACTION and table == "COMMIT":
            commits.append(1)
        if action in (sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_INSERT):
            writes.append((action, table))
            if action != sqlite3.SQLITE_INSERT or table != "data_quality_issue":
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorize)
    try:
        assert run(ctx, vid).created_issue_ids
    finally:
        ctx.conn.set_authorizer(None)
    assert writes and commits == [1]


def test_sensitive_policy_required_and_excluded(ctx):
    rule(ctx)
    vid = value(ctx)
    with pytest.raises(QualityControlError):
        run(ctx, vid, policy=None)
    ctx.conn.execute(
        "UPDATE data_dictionary SET internal_name='synthetic_secret' WHERE dictionary_id=?",
        (ctx.items["REAL"].dictionary_id,),
    )
    assert run(ctx, vid).findings == () and not issues(ctx)


def test_concurrent_run_deduplicates(ctx):
    rule(ctx)
    vid = value(ctx)
    barrier = Barrier(2)

    def work():
        with closing(connect_database(ctx.path)) as conn:
            barrier.wait(timeout=5)
            return QualityControlService(conn).run(
                QualityControlRequest((vid,)), field_policy=POLICY
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(work) for _ in range(2)]
        results = [f.result(timeout=10) for f in futures]
    assert sum(len(r.created_issue_ids) for r in results) == 1
    assert len(issues(ctx)) == 1


def test_required_different_imports_are_separate(ctx):
    rule(ctx, "REQUIRED")
    with transaction(ctx.conn):
        other = ImportHistoryRepository(ctx.conn).create(
            source_file_id=ctx.history.source_file_id,
            batch_code="synthetic-other",
            import_type="EXCEL",
            status="SUCCESS",
            started_at=STAMP,
            created_at=STAMP,
        )
    result = run(ctx, targets=(required(ctx), required(ctx, import_id=other.import_id)))
    assert len(result.created_issue_ids) == 2
    assert {f.import_id for f in result.findings} == {ctx.history.import_id, other.import_id}


def test_required_rejects_running_import(ctx):
    rule(ctx, "REQUIRED")
    ctx.conn.execute("UPDATE import_history SET status='RUNNING'")
    with pytest.raises(QualityControlError):
        run(ctx, targets=(required(ctx),))
    assert not issues(ctx)


@pytest.mark.parametrize("ids", [(), (0,), (True,), (999,), (1, 1)])
def test_invalid_scope(ctx, ids):
    with pytest.raises(QualityControlError):
        run(ctx, *ids)
    assert not issues(ctx)


def test_inactive_selected_value_rejected(ctx):
    rule(ctx)
    vid = value(ctx, is_active=0)
    with pytest.raises(QualityControlError):
        run(ctx, vid)


def test_storage_mismatch_is_safe_not_parsing_issue(ctx):
    rule(ctx)
    with transaction(ctx.conn):
        record = CharacteristicValueRepository(ctx.conn).create(
            stream_code=STREAM,
            dictionary_id=ctx.items["REAL"].dictionary_id,
            value_text=SECRET,
            created_at=STAMP,
            updated_at=STAMP,
        )
    with pytest.raises(QualityControlError) as error:
        run(ctx, record.characteristic_value_id)
    assert SECRET not in str(error.value) and not issues(ctx)


def test_mapping_dictionary_mismatch_rejected(ctx):
    rule(ctx)
    vid = value(ctx)
    ctx.conn.execute(
        "UPDATE import_column_mapping SET dictionary_id=?", (ctx.items["INTEGER"].dictionary_id,)
    )
    with pytest.raises(QualityControlError):
        run(ctx, vid)
    assert not issues(ctx)


def test_range_integer_and_large_integer_boundary(ctx):
    rule(ctx, "RANGE", "INTEGER", params=json.dumps({"min": 2**63 - 2, "max": 2**63 - 1}))
    assert not run(ctx, value(ctx, 2**63 - 1, "INTEGER")).findings
    assert run(ctx, value(ctx, 2**63 - 3, "INTEGER")).findings


@pytest.mark.parametrize("kind", ["REQUIRED", "NON_NEGATIVE"])
def test_unsupported_parameter_rejected(ctx, kind):
    rule(ctx, kind, params='{"allow_zero":false}')
    with pytest.raises(QualityRuleConfigurationError):
        run(ctx, value(ctx))


def test_schema_and_research_records_unchanged(ctx):
    rule(ctx)
    vid = value(ctx, is_representative=1)
    ctx.conn.execute(
        "INSERT INTO stream_characteristic VALUES (?, ?, ?, ?)",
        (STREAM, ctx.items["REAL"].dictionary_id, vid, STAMP),
    )
    tables = [
        r[0]
        for r in ctx.conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        if r[0] != "data_quality_issue"
    ]
    before = {t: ctx.conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
    schema = ctx.conn.execute("SELECT sql FROM sqlite_schema ORDER BY name").fetchall()
    run(ctx, vid)
    assert schema == ctx.conn.execute("SELECT sql FROM sqlite_schema ORDER BY name").fetchall()
    assert before == {t: ctx.conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}


def test_commit_failure_rolls_back_issues(ctx):
    rule(ctx)
    vid = value(ctx)

    def authorize(action, arg1, _arg2, _db, _trigger):
        if action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorize)
    try:
        with pytest.raises(QualityControlPersistenceError):
            run(ctx, vid)
    finally:
        ctx.conn.set_authorizer(None)
    assert not issues(ctx) and not ctx.conn.in_transaction


def test_rule_queries_are_enabled_and_dictionary_specific(ctx):
    a = rule(ctx)
    rule(ctx, dtype="INTEGER")
    rule(ctx, enabled=0)
    repo = ctx.service._repository
    assert len(repo.list_enabled_rules()) == 2
    assert [r.rule_id for r in repo.list_rules_by_dictionary(ctx.items["REAL"].dictionary_id)] == [
        a
    ]


def test_repository_fk_violation_is_safe(ctx):
    rule(ctx)
    vid = value(ctx)
    finding = ctx.service.evaluate(QualityControlRequest((vid,)), field_policy=POLICY)[0]
    with pytest.raises(QualityControlPersistenceError):
        with transaction(ctx.conn):
            ctx.service._repository.create_issue(replace(finding, rule_id=999), timestamp=STAMP)
    assert not issues(ctx)
