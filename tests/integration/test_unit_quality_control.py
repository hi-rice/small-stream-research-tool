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


def setup_units(ctx, dtype="REAL"):
    expected = ctx.dictionary.create_unit("Synthetic expected", "synE").unit_id
    actual = ctx.dictionary.create_unit("Synthetic actual", "synA").unit_id
    ctx.conn.execute(
        "UPDATE data_dictionary SET unit_id=? WHERE dictionary_id=?",
        (expected, ctx.items[dtype].dictionary_id),
    )
    return expected, actual


def check(ctx, vid, rid):
    return ctx.service.check_unit(vid, rid, field_policy=POLICY)


def conversion(ctx, actual, expected, **kwargs):
    return ctx.dictionary.register_conversion(
        actual, expected, 2.0, offset=5.0, approved=True, **kwargs
    )


@pytest.mark.parametrize("dtype,number", [("INTEGER", 10), ("REAL", 10.0)])
@pytest.mark.parametrize(
    "state,issue", [("same", None), ("different", "UNIT_MISMATCH"), ("missing", "UNIT_MISSING")]
)
def test_match(ctx, dtype, number, state, issue):
    expected, actual = setup_units(ctx, dtype)
    rid = rule(ctx, "UNIT_MATCH", dtype)
    vid = value(
        ctx,
        number,
        dtype,
        unit_id=expected if state == "same" else actual if state == "different" else None,
        original_unit="private original unit",
    )
    result = check(ctx, vid, rid)
    assert result.checked_count == 1 and result.finding_count == int(issue is not None)
    if issue:
        row = issues(ctx)[0]
        assert row["issue_type"] == issue
        assert row["characteristic_value_id"] == vid
        assert row["original_value"] is None and row["compare_value"] is None
        assert row["review_status"] == "UNREVIEWED" and row["is_active"] == 1


@pytest.mark.parametrize("actual_present", [False, True])
@pytest.mark.parametrize("kind", ["UNIT_MATCH", "UNIT_CONVERSION_MISSING"])
def test_missing_expected_configuration(ctx, actual_present, kind):
    unit = ctx.dictionary.create_unit("Synthetic", "s").unit_id
    rid = rule(ctx, kind)
    vid = value(ctx, unit_id=unit if actual_present else None)
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, vid, rid)
    assert not issues(ctx)


@pytest.mark.parametrize("side", ["actual", "expected"])
def test_inactive_unit(ctx, side):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    vid = value(ctx, unit_id=actual)
    ctx.conn.execute(
        "UPDATE unit_dictionary SET is_active=0 WHERE unit_id=?",
        (actual if side == "actual" else expected,),
    )
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, vid, rid)
    assert not issues(ctx)


@pytest.mark.parametrize("severity", ["ERROR", "WARNING", "INFO"])
def test_severity_and_snapshot(ctx, severity):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH", severity=severity, params="{}")
    vid = value(ctx, unit_id=actual)
    check(ctx, vid, rid)
    row = issues(ctx)[0]
    assert row["severity"] == severity and row["rule_version_snapshot"] == "synthetic-v1"
    assert json.loads(row["rule_parameters_snapshot_json"]) == {
        "format": "unit_qc_v1",
        "rule_parameters": {},
        "execution": {"expected_unit_id": expected, "actual_unit_id": actual},
    }


@pytest.mark.parametrize(
    "dtype,text", [("TEXT", "text"), ("DATE", "2026-01-01"), ("DATETIME", "2026-01-01T00:00:00")]
)
def test_non_numeric_rejected(ctx, dtype, text):
    expected, actual = setup_units(ctx, dtype)
    rid = rule(ctx, "UNIT_MATCH", dtype)
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, value(ctx, text, dtype, unit_id=actual), rid)


@pytest.mark.parametrize("case", ["none", "direct", "reverse", "chain", "inactive", "same"])
def test_conversion_direction(ctx, case):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_CONVERSION_MISSING")
    vid = value(ctx, unit_id=expected if case == "same" else actual)
    if case in ("direct", "inactive"):
        conversion(ctx, actual, expected)
        if case == "inactive":
            ctx.conn.execute("UPDATE unit_conversion SET is_active=0")
    elif case == "reverse":
        conversion(ctx, expected, actual)
    elif case == "chain":
        mid = ctx.dictionary.create_unit("Middle", "synM").unit_id
        conversion(ctx, actual, mid)
        conversion(ctx, mid, expected)
    result = check(ctx, vid, rid)
    assert result.finding_count == int(case not in ("direct", "same"))
    if result.finding_count:
        assert issues(ctx)[0]["issue_type"] == "UNIT_CONVERSION_MISSING"


def test_conversion_actual_missing(ctx):
    setup_units(ctx)
    rid = rule(ctx, "UNIT_CONVERSION_MISSING")
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, value(ctx), rid)
    assert not issues(ctx)


@pytest.mark.parametrize(
    "invalid", ["formula_type='UNKNOWN'", "factor='invalid'", "offset='invalid'"]
)
def test_invalid_conversion(ctx, invalid):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_CONVERSION_MISSING")
    conversion(ctx, actual, expected)
    ctx.conn.execute("UPDATE unit_conversion SET " + invalid)
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, value(ctx, unit_id=actual), rid)
    assert not issues(ctx)


@pytest.mark.parametrize("column", ["factor", "offset"])
def test_nonfinite_conversion(ctx, column):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_CONVERSION_MISSING")
    conversion(ctx, actual, expected)
    ctx.conn.execute(f"UPDATE unit_conversion SET {column}=?", (float("inf"),))
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, value(ctx, unit_id=actual), rid)


def test_ambiguous_conversion(ctx):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_CONVERSION_MISSING")
    conversion(ctx, actual, expected)
    ctx.conn.execute(
        "INSERT INTO unit_conversion "
        "(from_unit_id,to_unit_id,factor,offset,formula_type,created_at,updated_at) "
        "VALUES (?,?,2,0,'OTHER',?,?)",
        (actual, expected, STAMP, STAMP),
    )
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, value(ctx, unit_id=actual), rid)
    assert not issues(ctx)


def test_unique_same_formula(ctx):
    expected, actual = setup_units(ctx)
    conversion(ctx, actual, expected)
    with pytest.raises(sqlite3.IntegrityError):
        ctx.conn.execute(
            "INSERT INTO unit_conversion "
            "(from_unit_id,to_unit_id,factor,formula_type,created_at,updated_at) "
            "VALUES (?,?,2,'LINEAR',?,?)",
            (actual, expected, STAMP, STAMP),
        )


def test_only_match_does_not_query_conversion(ctx, monkeypatch):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")

    def forbidden(*args):
        raise AssertionError("conversion lookup forbidden")

    monkeypatch.setattr(DictionaryRepository, "list_active_direct_conversions", forbidden)
    result = check(ctx, value(ctx, unit_id=actual), rid)
    assert result.finding_count == 1
    assert issues(ctx)[0]["issue_type"] == "UNIT_MISMATCH"


def test_match_lifecycle_review_preserved(ctx):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    vid = value(ctx, unit_id=actual)
    first = check(ctx, vid, rid)
    ctx.conn.execute(
        "UPDATE data_quality_issue SET review_status='CONFIRMED',review_note='note',"
        "review_result='result',reviewed_at=?",
        (STAMP,),
    )
    old = dict(issues(ctx)[0])
    assert check(ctx, vid, rid).kept_issue_ids == first.created_issue_ids
    assert dict(issues(ctx)[0]) == old
    ctx.conn.execute("UPDATE characteristic_value SET unit_id=?", (expected,))
    assert check(ctx, vid, rid).deactivated_issue_ids == first.created_issue_ids
    old["is_active"] = 0
    assert dict(issues(ctx)[0]) == old
    ctx.conn.execute("UPDATE characteristic_value SET unit_id=?", (actual,))
    result = check(ctx, vid, rid)
    assert result.created_issue_ids != first.created_issue_ids
    assert len(issues(ctx)) == 2 and issues(ctx)[0]["is_active"] == 0


def test_conversion_added_resolves_only_conversion_issue(ctx):
    expected, actual = setup_units(ctx)
    match = rule(ctx, "UNIT_MATCH")
    rid = rule(ctx, "UNIT_CONVERSION_MISSING")
    vid = value(ctx, unit_id=actual)
    check(ctx, vid, match)
    old = tuple(issues(ctx)[0])
    first = check(ctx, vid, rid)
    conversion(ctx, actual, expected)
    assert check(ctx, vid, rid).deactivated_issue_ids == first.created_issue_ids
    assert tuple(issues(ctx)[0]) == old
    ctx.conn.execute("UPDATE unit_conversion SET is_active=0")
    assert len(check(ctx, vid, rid).created_issue_ids) == 1
    assert len(issues(ctx)) == 3


@pytest.mark.parametrize("side", ["actual", "expected"])
def test_pair_change_distinguished(ctx, side):
    expected, actual = setup_units(ctx)
    other = ctx.dictionary.create_unit("Other", "synO").unit_id
    rid = rule(ctx, "UNIT_CONVERSION_MISSING")
    vid = value(ctx, unit_id=actual)
    first = check(ctx, vid, rid)
    old = dict(issues(ctx)[0])
    if side == "actual":
        ctx.conn.execute("UPDATE characteristic_value SET unit_id=?", (other,))
    else:
        ctx.conn.execute(
            "UPDATE data_dictionary SET unit_id=? WHERE dictionary_id=?",
            (other, ctx.items["REAL"].dictionary_id),
        )
    result = check(ctx, vid, rid)
    assert result.deactivated_issue_ids == first.created_issue_ids
    assert len(result.created_issue_ids) == 1
    assert issues(ctx)[1]["rule_parameters_snapshot_json"] != old["rule_parameters_snapshot_json"]
    old["is_active"] = 0
    assert dict(issues(ctx)[0]) == old


def test_disabled_preserves_active_issue(ctx):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    vid = value(ctx, unit_id=actual)
    check(ctx, vid, rid)
    old = tuple(issues(ctx)[0])
    ctx.conn.execute("UPDATE quality_rule SET is_enabled=0")
    result = check(ctx, vid, rid)
    assert result.checked_count == 0 and tuple(issues(ctx)[0]) == old


@pytest.mark.parametrize(
    "change",
    [
        "rule_type='RANGE'",
        "target_type='UNKNOWN'",
        "dictionary_id=NULL",
        "rule_version=''",
        "parameters_json='{\"expected_unit_id\":1}'",
    ],
)
def test_bad_rule(ctx, change):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    ctx.conn.execute("UPDATE quality_rule SET " + change)
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, value(ctx, unit_id=actual), rid)
    assert not issues(ctx)


@pytest.mark.parametrize("operation", ["INSERT", "UPDATE"])
def test_write_rollback(ctx, operation):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    vid = value(ctx, unit_id=actual)
    check(ctx, vid, rid)
    old = [tuple(r) for r in issues(ctx)]
    ctx.conn.execute("UPDATE quality_rule SET rule_version='v2'")
    ctx.conn.execute(
        f"CREATE TRIGGER fail BEFORE {operation} ON data_quality_issue "
        "BEGIN SELECT RAISE(ABORT,'private raw SQL'); END"
    )
    with pytest.raises(QualityControlPersistenceError) as caught:
        check(ctx, vid, rid)
    assert "private" not in str(caught.value)
    assert [tuple(r) for r in issues(ctx)] == old and not ctx.conn.in_transaction


def test_no_mutation_safe_finding(ctx, monkeypatch):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    vid = value(ctx, unit_id=actual, original_unit="private original")
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
    result = check(ctx, vid, rid)
    assert before == {
        t: [tuple(r) for r in ctx.conn.execute(f'SELECT * FROM "{t}"')] for t in tables
    }
    for secret in (SECRET, PATH, "private original", "Synthetic expected", "synA"):
        assert secret not in repr(captured) and secret not in repr(result)
    with pytest.raises(FrozenInstanceError):
        captured[0].severity = "ERROR"


@pytest.mark.parametrize("kind", ["REQUIRED", "NON_NEGATIVE", "RANGE", "REFERENCE_COMPARE"])
def test_other_qc_protected(ctx, kind):
    expected, actual = setup_units(ctx)
    generic = rule(ctx, kind, params='{"min":0}' if kind == "RANGE" else None)
    a, b = value(ctx, unit_id=actual), value(ctx, 1.0, unit_id=actual)
    if kind == "REFERENCE_COMPARE":
        ctx.service.compare_reference(a, b, generic, field_policy=POLICY)
    elif kind == "REQUIRED":
        ctx.conn.execute("UPDATE characteristic_value SET is_active=0")
        recheck(ctx, targets=(required(ctx),), rule_ids=(generic,))
        ctx.conn.execute("UPDATE characteristic_value SET is_active=1")
    else:
        recheck(ctx, a, rule_ids=(generic,))
    old = tuple(issues(ctx)[0])
    rid = rule(ctx, "UNIT_MATCH")
    check(ctx, a, rid)
    ctx.conn.execute("UPDATE characteristic_value SET unit_id=?", (expected,))
    check(ctx, a, rid)
    assert tuple(issues(ctx)[0]) == old


@pytest.mark.parametrize("kind", ["UNIT_MATCH", "UNIT_CONVERSION_MISSING"])
def test_other_value_and_rule_protection(ctx, kind):
    expected, actual = setup_units(ctx)
    r1, r2 = rule(ctx, kind), rule(ctx, kind)
    a, b = value(ctx, unit_id=actual), value(ctx, unit_id=actual)
    check(ctx, a, r1)
    check(ctx, a, r2)
    check(ctx, b, r1)
    old = [tuple(r) for r in issues(ctx)][1:]
    ctx.conn.execute("UPDATE characteristic_value SET unit_id=?", (expected,))
    result = check(ctx, a, r1)
    assert len(result.deactivated_issue_ids) == 1
    assert [tuple(r) for r in issues(ctx)][1:] == old


@pytest.mark.parametrize("bad", ["missing", "inactive", "wrong_dictionary"])
def test_invalid_target(ctx, bad):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    vid = value(ctx, unit_id=actual)
    if bad == "missing":
        vid = 9999
    elif bad == "inactive":
        ctx.conn.execute("UPDATE characteristic_value SET is_active=0")
    else:
        ctx.conn.execute(
            "UPDATE quality_rule SET dictionary_id=?", (ctx.items["INTEGER"].dictionary_id,)
        )
    with pytest.raises(QualityControlError):
        check(ctx, vid, rid)
    assert not issues(ctx)


@pytest.mark.parametrize(
    "params", ["[]", "null", '{"expected_unit_id":1}', '{"factor":2}', "private json"]
)
def test_parameters_rejected(ctx, params):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH", params=params)
    with pytest.raises(QualityRuleConfigurationError) as caught:
        check(ctx, value(ctx, unit_id=actual), rid)
    assert params not in str(caught.value)


def test_reference_still_rejects_unit_mismatch(ctx):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "REFERENCE_COMPARE")
    conversion(ctx, actual, expected)
    with pytest.raises(QualityControlError):
        ctx.service.compare_reference(
            value(ctx, unit_id=actual), value(ctx, unit_id=expected), rid, field_policy=POLICY
        )
    assert not issues(ctx)


def test_factor_offset_never_applied(ctx, monkeypatch):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_CONVERSION_MISSING")
    vid = value(ctx, 10.0, unit_id=actual, original_unit="original")
    conversion(ctx, actual, expected)
    old = ctx.conn.execute("SELECT * FROM characteristic_value").fetchall()

    def forbidden(*args):
        raise AssertionError("conversion forbidden")

    monkeypatch.setattr(DictionaryService, "convert_value", forbidden)
    result = check(ctx, vid, rid)
    assert result.finding_count == 0
    assert ctx.conn.execute("SELECT * FROM characteristic_value").fetchall() == old


def test_excluded_item(ctx):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    with pytest.raises(QualityControlError):
        ctx.service.check_unit(
            value(ctx, unit_id=actual),
            rid,
            field_policy=ImportFieldPolicy(frozenset({"synthetic_real"})),
        )
    assert not issues(ctx)


def test_commit_failure_rollback(ctx):
    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    vid = value(ctx, unit_id=actual)

    def authorizer(action, arg1, *args):
        if action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorizer)
    try:
        with pytest.raises(QualityControlPersistenceError):
            check(ctx, vid, rid)
    finally:
        ctx.conn.set_authorizer(None)
    assert not issues(ctx) and not ctx.conn.in_transaction


def test_concurrent_dedup(ctx):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    expected, actual = setup_units(ctx)
    rid = rule(ctx, "UNIT_MATCH")
    vid = value(ctx, unit_id=actual)
    barrier = Barrier(2)

    def worker(_):
        with closing(connect_database(ctx.path)) as conn:
            barrier.wait()
            return QualityControlService(conn).check_unit(vid, rid, field_policy=POLICY)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert sum(len(r.created_issue_ids) for r in results) == 1
    assert len(issues(ctx)) == 1
