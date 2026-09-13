"""합성 사전·규칙·값만으로 QC 판정, snapshot, 중복 방지와 rollback을 검증한다."""

import json
import sqlite3
from contextlib import closing
from dataclasses import FrozenInstanceError
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
    cursor = ctx.conn.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute("SELECT * FROM data_quality_issue ORDER BY issue_id").fetchall()


def recheck(ctx, *ids, targets=(), **kwargs):
    return ctx.service.recheck(
        QualityControlRequest(tuple(ids), tuple(targets)), field_policy=POLICY, **kwargs
    )


def compare(ctx, target, reference, rid, **kwargs):
    return ctx.service.compare_reference(target, reference, rid, field_policy=POLICY, **kwargs)


@pytest.mark.parametrize(
    "dtype,target,reference,mismatch",
    [
        ("INTEGER", 3, 3, False),
        ("INTEGER", 3, 4, True),
        ("REAL", 0.3, 0.3, False),
        ("REAL", 0.3, 0.1 + 0.2, True),
        ("TEXT", "Synthetic A", "Synthetic A", False),
        ("TEXT", "Synthetic A", "Synthetic B", True),
        ("TEXT", "A", "a", True),
        ("TEXT", "A", " A ", True),
    ],
)
def test_typed_comparison(ctx, dtype, target, reference, mismatch):
    rid = rule(ctx, "REFERENCE_COMPARE", dtype)
    a, b = value(ctx, target, dtype), value(ctx, reference, dtype)
    result = compare(ctx, a, b, rid)
    assert result.checked_count == 1 and result.finding_count == int(mismatch)
    assert len(issues(ctx)) == int(mismatch)
    if mismatch:
        row = issues(ctx)[0]
        assert row["issue_type"] == "REFERENCE_VALUE_MISMATCH"
        assert row["characteristic_value_id"] == a
        assert row["import_id"] == ctx.history.import_id
        assert row["review_status"] == "UNREVIEWED" and row["is_active"] == 1
        assert row["original_value"] is None and row["compare_value"] is None


@pytest.mark.parametrize(
    "params,target,reference,mismatch",
    [
        ('{"absolute_tolerance":0.1}', 1.1, 1.0, False),
        ('{"absolute_tolerance":0.1}', 1.11, 1.0, True),
        ('{"absolute_tolerance":0}', 1.0, 1.0, False),
        ('{"absolute_tolerance":0}', 1.01, 1.0, True),
        ('{"relative_tolerance":0.1}', 11.0, 10.0, False),
        ('{"relative_tolerance":0.1}', 11.01, 10.0, True),
        ('{"relative_tolerance":0.1}', -11.0, -10.0, False),
        ('{"absolute_tolerance":0.1}', 0.1, 0.0, False),
    ],
)
def test_tolerance(ctx, params, target, reference, mismatch):
    rid = rule(ctx, "REFERENCE_COMPARE", params=params)
    result = compare(ctx, value(ctx, target), value(ctx, reference), rid)
    assert result.finding_count == int(mismatch)


@pytest.mark.parametrize(
    "params",
    [
        '{"absolute_tolerance":-1}',
        '{"relative_tolerance":-1}',
        '{"absolute_tolerance":true}',
        '{"absolute_tolerance":"0.1"}',
        '{"relative_tolerance":null}',
        '{"min":0}',
        '{"absolute_tolerance":0,"relative_tolerance":0}',
        '{"absolute_tolerance":NaN}',
        '{"relative_tolerance":Infinity}',
        '{"comparison":"fuzzy"}',
        '{"reference_value_id":1}',
        '{"absolute_tolerance":0,"absolute_tolerance":1}',
        "[]",
        "private JSON",
    ],
)
def test_invalid_policy(ctx, params):
    rid = rule(ctx, "REFERENCE_COMPARE", params=params)
    with pytest.raises(QualityRuleConfigurationError) as caught:
        compare(ctx, value(ctx), value(ctx, 1.0), rid)
    assert params not in str(caught.value) and not issues(ctx)


@pytest.mark.parametrize("target", [0.0, 1.0])
def test_relative_zero_explicit_error(ctx, target):
    rid = rule(ctx, "REFERENCE_COMPARE", params='{"relative_tolerance":0.1}')
    with pytest.raises(QualityControlError):
        compare(ctx, value(ctx, target), value(ctx, 0.0), rid)
    assert not issues(ctx)


@pytest.mark.parametrize("side", ["target", "reference"])
@pytest.mark.parametrize("bad", ["missing", "inactive"])
def test_unavailable_value(ctx, side, bad):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)
    selected = a if side == "target" else b
    if bad == "inactive":
        ctx.conn.execute(
            "UPDATE characteristic_value SET is_active=0 WHERE characteristic_value_id=?",
            (selected,),
        )
    elif side == "target":
        a = 9999
    else:
        b = 9999
    with pytest.raises(QualityControlError):
        compare(ctx, a, b, rid)
    assert not issues(ctx)


@pytest.mark.parametrize("dtype", ["DATE", "DATETIME"])
def test_unsupported_date(ctx, dtype):
    rid = rule(ctx, "REFERENCE_COMPARE", dtype)
    with pytest.raises(QualityRuleConfigurationError):
        compare(ctx, value(ctx, "2026-01-01", dtype), value(ctx, "2026-01-02", dtype), rid)


def test_dictionary_mismatch(ctx):
    rid = rule(ctx, "REFERENCE_COMPARE")
    with pytest.raises(QualityControlError):
        compare(ctx, value(ctx), value(ctx, 1, "INTEGER"), rid)


def test_stream_mismatch(ctx):
    rid = rule(ctx, "REFERENCE_COMPARE")
    with transaction(ctx.conn):
        SmallStreamRepository(ctx.conn).create(
            stream_code="12345678010",
            province_code="12",
            city_county_code="345",
            town_code="678",
            stream_serial_no="010",
            stream_name="Other",
            created_at=STAMP,
            updated_at=STAMP,
        )
    with pytest.raises(QualityControlError):
        compare(ctx, value(ctx), value(ctx, 1.0, stream_code="12345678010"), rid)


def test_same_id_is_match(ctx):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a = value(ctx)
    assert compare(ctx, a, a, rid).finding_count == 0


@pytest.mark.parametrize("severity", ["ERROR", "WARNING", "INFO"])
def test_severity_snapshot_and_identity(ctx, severity):
    rid = rule(ctx, "REFERENCE_COMPARE", params='{"comparison":"numeric"}', severity=severity)
    a, b = value(ctx), value(ctx, 1.0)
    compare(ctx, a, b, rid)
    row = issues(ctx)[0]
    snapshot = json.loads(row["rule_parameters_snapshot_json"])
    assert snapshot == {
        "format": "reference_compare_v1",
        "rule_parameters": {"comparison": "numeric"},
        "execution": {"reference_value_id": b},
    }
    assert row["severity"] == severity and row["rule_version_snapshot"] == "synthetic-v1"
    assert (
        ctx.conn.execute("SELECT parameters_json FROM quality_rule").fetchone()[0]
        == '{"comparison":"numeric"}'
    )


def test_pair_isolation_lifecycle(ctx):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b, c = value(ctx, 1.0), value(ctx, 2.0), value(ctx, 3.0)
    first = compare(ctx, a, b, rid)
    second = compare(ctx, a, c, rid)
    assert first.created_issue_ids != second.created_issue_ids
    ctx.conn.execute(
        "UPDATE data_quality_issue SET review_status='CONFIRMED',review_note='note',reviewed_at=?",
        (STAMP,),
    )
    old = dict(issues(ctx)[0])
    assert compare(ctx, a, b, rid).kept_issue_ids == first.created_issue_ids
    assert dict(issues(ctx)[0]) == old
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_number=1 WHERE characteristic_value_id=?", (b,)
    )
    assert compare(ctx, a, b, rid).deactivated_issue_ids == first.created_issue_ids
    old["is_active"] = 0
    assert dict(issues(ctx)[0]) == old
    assert issues(ctx)[1]["is_active"] == 1
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_number=2 WHERE characteristic_value_id=?", (b,)
    )
    recurrence = compare(ctx, a, b, rid)
    assert recurrence.created_issue_ids not in (first.created_issue_ids, second.created_issue_ids)
    assert len(issues(ctx)) == 3 and issues(ctx)[0]["is_active"] == 0


def test_disabled_preserves_issue(ctx):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)
    compare(ctx, a, b, rid)
    old = tuple(issues(ctx)[0])
    ctx.conn.execute("UPDATE quality_rule SET is_enabled=0")
    result = compare(ctx, a, b, rid)
    assert result.checked_count == 0 and tuple(issues(ctx)[0]) == old


@pytest.mark.parametrize("kind", ["REQUIRED", "NON_NEGATIVE", "RANGE"])
def test_other_qc_protected(ctx, kind):
    generic = rule(ctx, kind, params='{"min":0}' if kind == "RANGE" else None)
    a, b = value(ctx), value(ctx, 1.0)
    if kind == "REQUIRED":
        ctx.conn.execute("UPDATE characteristic_value SET is_active=0")
        ctx.service.recheck(
            QualityControlRequest(required_targets=(required(ctx),)),
            field_policy=POLICY,
            rule_ids=(generic,),
        )
        ctx.conn.execute("UPDATE characteristic_value SET is_active=1")
    else:
        recheck(ctx, a, rule_ids=(generic,))
    old = tuple(issues(ctx)[0])
    rid = rule(ctx, "REFERENCE_COMPARE")
    compare(ctx, a, b, rid)
    ctx.conn.execute("UPDATE characteristic_value SET value_number=1")
    compare(ctx, a, b, rid)
    assert tuple(issues(ctx)[0]) == old


@pytest.mark.parametrize("operation", ["INSERT", "UPDATE"])
def test_rollback(ctx, operation):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)
    compare(ctx, a, b, rid)
    old = [tuple(r) for r in issues(ctx)]
    ctx.conn.execute("UPDATE quality_rule SET rule_version='v2'")
    ctx.conn.execute(
        f"CREATE TRIGGER fail BEFORE {operation} ON data_quality_issue "
        "BEGIN SELECT RAISE(ABORT,'private raw error'); END"
    )
    with pytest.raises(QualityControlPersistenceError) as caught:
        compare(ctx, a, b, rid)
    assert "private" not in str(caught.value)
    assert [tuple(r) for r in issues(ctx)] == old


def test_no_other_table_mutation_and_safe_finding(ctx, monkeypatch):
    rid = rule(ctx, "REFERENCE_COMPARE", "TEXT")
    a, b = value(ctx, "private target", "TEXT"), value(ctx, "private reference", "TEXT")
    tables = [
        r[0]
        for r in ctx.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if r[0] != "data_quality_issue"
    ]
    before = {t: [tuple(r) for r in ctx.conn.execute(f'SELECT * FROM "{t}"')] for t in tables}
    captured = []
    create = ctx.service._repository.create_issue

    def capture(finding, **kwargs):
        captured.append(finding)
        return create(finding, **kwargs)

    monkeypatch.setattr(ctx.service._repository, "create_issue", capture)
    result = compare(ctx, a, b, rid)
    assert before == {
        t: [tuple(r) for r in ctx.conn.execute(f'SELECT * FROM "{t}"')] for t in tables
    }
    for secret in ("private target", "private reference", SECRET, PATH):
        assert secret not in repr(captured) and secret not in repr(result)
    with pytest.raises(FrozenInstanceError):
        captured[0].message = "changed"


@pytest.mark.parametrize("units", ["same", "different", "one_missing"])
def test_units(ctx, units):
    rid = rule(ctx, "REFERENCE_COMPARE")
    u = ctx.dictionary.create_unit("Synthetic U", "su").unit_id
    v = ctx.dictionary.create_unit("Synthetic V", "sv").unit_id
    a = value(ctx, 1.0, unit_id=u)
    b = value(ctx, 1.0, unit_id=u if units == "same" else v if units == "different" else None)
    if units == "same":
        assert compare(ctx, a, b, rid).finding_count == 0
    else:
        with pytest.raises(QualityControlError):
            compare(ctx, a, b, rid)
    assert not issues(ctx)


@pytest.mark.parametrize(
    "change",
    [
        "rule_type='NON_NEGATIVE'",
        "target_type='UNKNOWN'",
        "dictionary_id=NULL",
        "rule_version=''",
    ],
)
def test_rule_configuration(ctx, change):
    rid = rule(ctx, "REFERENCE_COMPARE")
    ctx.conn.execute("UPDATE quality_rule SET " + change)
    with pytest.raises(QualityRuleConfigurationError):
        compare(ctx, value(ctx), value(ctx, 1.0), rid)
    assert not issues(ctx)


@pytest.mark.parametrize(
    "change",
    [
        "rule_version='v2'",
        "default_severity='INFO'",
        "parameters_json='{\"absolute_tolerance\":0}'",
    ],
)
def test_policy_change_same_pair(ctx, change):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)
    first = compare(ctx, a, b, rid)
    old = dict(issues(ctx)[0])
    ctx.conn.execute("UPDATE quality_rule SET " + change)
    result = compare(ctx, a, b, rid)
    assert result.deactivated_issue_ids == first.created_issue_ids
    assert len(result.created_issue_ids) == 1
    old["is_active"] = 0
    assert dict(issues(ctx)[0]) == old


@pytest.mark.parametrize("nonfinite", [float("inf"), float("-inf")])
def test_nonfinite_storage(ctx, nonfinite):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_number=? WHERE characteristic_value_id=?",
        (nonfinite, b),
    )
    with pytest.raises(QualityControlError):
        compare(ctx, a, b, rid)
    assert not issues(ctx)


def test_nan_pure_evaluation(ctx):
    from small_stream_research_tool.services.reference_comparison_evaluator import (
        compile_reference_rule,
    )

    rid = rule(ctx, "REFERENCE_COMPARE")
    compiled = compile_reference_rule(ctx.service._repository.get_rule(rid), ctx.items["REAL"])
    with pytest.raises(QualityControlError):
        compiled.violated(float("nan"), 1.0)


def test_text_tolerance_rejected(ctx):
    rid = rule(ctx, "REFERENCE_COMPARE", "TEXT", params='{"absolute_tolerance":0}')
    with pytest.raises(QualityRuleConfigurationError):
        compare(ctx, value(ctx, "a", "TEXT"), value(ctx, "b", "TEXT"), rid)


def test_other_target_unchanged(ctx):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b, c = value(ctx), value(ctx, 1.0), value(ctx, 2.0)
    compare(ctx, c, b, rid)
    before = tuple(issues(ctx)[0])
    compare(ctx, a, b, rid)
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_number=1 WHERE characteristic_value_id=?", (a,)
    )
    compare(ctx, a, b, rid)
    assert tuple(issues(ctx)[0]) == before


def test_commit_failure_rollback(ctx):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)

    def authorizer(action, arg1, *args):
        return (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT"
            else sqlite3.SQLITE_OK
        )

    ctx.conn.set_authorizer(authorizer)
    try:
        with pytest.raises(QualityControlPersistenceError):
            compare(ctx, a, b, rid)
    finally:
        ctx.conn.set_authorizer(None)
    assert not issues(ctx) and not ctx.conn.in_transaction


@pytest.mark.parametrize(
    "snapshot",
    [
        None,
        "not json",
        "{}",
        "[]",
        '{"format":"other","execution":{"reference_value_id":2}}',
        '{"format":"reference_compare_v1","rule_parameters":{},"execution":{"reference_value_id":true}}',
    ],
)
def test_unrecognized_snapshot_is_preserved(ctx, snapshot):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)
    compare(ctx, a, b, rid)
    ctx.conn.execute("UPDATE data_quality_issue SET rule_parameters_snapshot_json=?", (snapshot,))
    old = tuple(issues(ctx)[0])
    ctx.conn.execute("UPDATE characteristic_value SET value_number=1")
    compare(ctx, a, b, rid)
    assert tuple(issues(ctx)[0]) == old


def test_concurrent_pair_dedup(ctx):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)
    barrier = Barrier(2)

    def worker(_):
        with closing(connect_database(ctx.path)) as conn:
            barrier.wait()
            return QualityControlService(conn).compare_reference(a, b, rid, field_policy=POLICY)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert sum(len(r.created_issue_ids) for r in results) == 1
    assert len(issues(ctx)) == 1


def test_general_recheck_explicit_rules_coexists(ctx):
    generic = rule(ctx)
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)
    compare(ctx, a, b, rid)
    old = tuple(issues(ctx)[0])
    recheck(ctx, a, rule_ids=(generic,))
    assert tuple(issues(ctx)[0]) == old
    assert len(issues(ctx)) == 2


def test_excluded_item_no_comparison(ctx):
    rid = rule(ctx, "REFERENCE_COMPARE")
    a, b = value(ctx), value(ctx, 1.0)
    with pytest.raises(QualityControlError):
        ctx.service.compare_reference(
            a, b, rid, field_policy=ImportFieldPolicy(frozenset({"synthetic_real"}))
        )
    assert not issues(ctx)
