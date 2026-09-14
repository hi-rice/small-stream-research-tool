"""합성 사전·규칙·값만으로 QC 판정, snapshot, 중복 방지와 rollback을 검증한다."""

import json
import sqlite3
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
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
from small_stream_research_tool.services.statistical_outlier_evaluator import (
    StatisticalPolicy,
    iqr_bounds,
    numeric_value,
)

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


def population(ctx, numbers=(0, 0, 0, 0, 100), dtype="INTEGER"):
    unit = ctx.dictionary.create_unit("Synthetic stat unit", "synstat").unit_id
    ids = tuple(
        value(ctx, float(n) if dtype == "REAL" else n, dtype, unit_id=unit) for n in numbers
    )
    return ids, unit


def stat_rule(ctx, dtype="INTEGER", params='{"method":"IQR","multiplier":1.5}', severity="INFO"):
    return rule(ctx, "STATISTICAL_OUTLIER", dtype, params=params, severity=severity)


def check(ctx, ids, rid, target=None):
    return ctx.service.check_statistical_outlier(
        ids[-1] if target is None else target, rid, population_value_ids=ids, field_policy=POLICY
    )


@pytest.mark.parametrize("dtype", ["INTEGER", "REAL"])
@pytest.mark.parametrize(
    "numbers,candidate",
    [
        ((0, 0, 0, 0, 100), True),
        ((0, 0, 0, 0, -100), True),
        ((1, 2, 3, 4, 5), False),
        ((1, 1, 1, 1, 1), False),
        ((7,), False),
        ((0, 10), False),
    ],
)
def test_iqr_candidates(ctx, dtype, numbers, candidate):
    ids, unit = population(ctx, numbers, dtype)
    result = check(ctx, ids, stat_rule(ctx, dtype))
    assert result.checked_count == 1 and result.finding_count == int(candidate)
    if candidate:
        row = issues(ctx)[0]
        assert row["issue_type"] == "STATISTICAL_OUTLIER_CANDIDATE"
        assert row["severity"] == "INFO" and row["is_active"] == 1
        assert row["original_value"] is None and row["compare_value"] is None
        assert row["characteristic_value_id"] == ids[-1]
        assert row["import_id"] == ctx.history.import_id
        assert result.qc_status == "NEEDS_REVIEW"


@pytest.mark.parametrize("severity", ["WARNING", "ERROR"])
def test_info_only(ctx, severity):
    ids, _ = population(ctx)
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, ids, stat_rule(ctx, severity=severity))
    assert not issues(ctx)


@pytest.mark.parametrize(
    "params",
    [
        None,
        "{}",
        '{"method":"IQR"}',
        '{"multiplier":1.5}',
        '{"method":"Z_SCORE","multiplier":1.5}',
        '{"method":"IQR","multiplier":-1}',
        '{"method":"IQR","multiplier":true}',
        '{"method":"IQR","multiplier":"1.5"}',
        '{"method":"IQR","multiplier":NaN}',
        '{"method":"IQR","multiplier":Infinity}',
        '{"method":"IQR","multiplier":1,"extra":0}',
        '{"method":"IQR","multiplier":1,"minimum_sample_size":0}',
        '{"method":"IQR","multiplier":1,"minimum_sample_size":true}',
        '{"method":"IQR","multiplier":1,"minimum_sample_size":2.5}',
        '{"method":"IQR","multiplier":1,"minimum_sample_size":"5"}',
        '{"method":"IQR","multiplier":1,"multiplier":2}',
        "[]",
        "private JSON",
    ],
)
def test_invalid_parameters(ctx, params):
    ids, _ = population(ctx)
    with pytest.raises(QualityRuleConfigurationError) as caught:
        check(ctx, ids, stat_rule(ctx, params=params))
    assert "private" not in str(caught.value) and not issues(ctx)


@pytest.mark.parametrize("minimum,success", [(5, True), (6, False)])
def test_minimum_sample(ctx, minimum, success):
    ids, _ = population(ctx)
    rid = stat_rule(
        ctx, params=json.dumps({"method": "IQR", "multiplier": 0, "minimum_sample_size": minimum})
    )
    if success:
        assert check(ctx, ids, rid).finding_count == 1
    else:
        with pytest.raises(QualityControlError):
            check(ctx, ids, rid)


def test_linear_quartiles_and_boundaries():
    policy = StatisticalPolicy("{}", Fraction(1), 1)
    bounds = iqr_bounds(tuple(map(Fraction, [0, 1, 2, 3])), policy)
    assert (bounds.q1, bounds.q3) == (Fraction(3, 4), Fraction(9, 4))
    assert bounds.q3 - bounds.q1 == Fraction(3, 2)
    assert (bounds.lower, bounds.upper) == (Fraction(-3, 4), Fraction(15, 4))
    assert not bounds.is_candidate(bounds.lower)
    assert not bounds.is_candidate(bounds.upper)
    assert not bounds.is_candidate(Fraction(0))
    assert bounds.is_candidate(Fraction(-1)) and bounds.is_candidate(Fraction(4))
    assert bounds == iqr_bounds(tuple(map(Fraction, [3, 0, 2, 1])), policy)
    assert repr(bounds) == "IQRBounds()"


def test_zero_iqr_and_empty_algorithm():
    policy = StatisticalPolicy("{}", Fraction(0), 1)
    bounds = iqr_bounds(tuple(map(Fraction, [0, 0, 0, 0, 100])), policy)
    assert bounds.q1 == bounds.q3 == bounds.lower == bounds.upper == 0
    assert bounds.is_candidate(Fraction(100))
    with pytest.raises(QualityControlError):
        iqr_bounds((), policy)


@pytest.mark.parametrize(
    "bad",
    [
        "empty",
        "duplicate",
        "target_missing",
        "list",
        "missing",
        "inactive",
        "wrong_dictionary",
        "wrong_unit",
        "null_unit",
        "inactive_target",
        "null_target_unit",
    ],
)
def test_bad_population(ctx, bad):
    ids, unit = population(ctx)
    rid = stat_rule(ctx)
    target = ids[-1]
    if bad == "empty":
        ids = ()
    elif bad == "duplicate":
        ids = ids + (ids[0],)
    elif bad == "target_missing":
        ids = ids[:-1]
    elif bad == "list":
        ids = list(ids)
    elif bad == "missing":
        ids = (99999,) + ids[1:]
    elif bad in ("inactive", "inactive_target"):
        ctx.conn.execute(
            "UPDATE characteristic_value SET is_active=0 WHERE characteristic_value_id=?",
            (target if bad == "inactive_target" else ids[0],),
        )
    elif bad == "wrong_dictionary":
        ctx.conn.execute(
            "UPDATE characteristic_value SET dictionary_id=? WHERE characteristic_value_id=?",
            (ctx.items["REAL"].dictionary_id, ids[0]),
        )
    elif bad == "wrong_unit":
        other = ctx.dictionary.create_unit("Other", "other").unit_id
        ctx.conn.execute(
            "UPDATE characteristic_value SET unit_id=? WHERE characteristic_value_id=?",
            (other, ids[0]),
        )
    else:
        ctx.conn.execute(
            "UPDATE characteristic_value SET unit_id=NULL WHERE characteristic_value_id=?",
            (target if bad == "null_target_unit" else ids[0],),
        )
    with pytest.raises(QualityControlError):
        check(ctx, ids, rid, target)
    assert not issues(ctx)


@pytest.mark.parametrize("dtype", ["TEXT", "DATE", "DATETIME"])
def test_nonnumeric_configuration(ctx, dtype):
    unit = ctx.dictionary.create_unit("Unit", "unit").unit_id
    vid = value(ctx, "2026-01-01", dtype, unit_id=unit)
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, (vid,), stat_rule(ctx, dtype))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), None, "raw"])
def test_invalid_numeric_typed_value(ctx, bad):
    ids, _ = population(ctx, dtype="REAL")
    record = ctx.service._values.get_by_id(ids[0])
    with pytest.raises(QualityControlError):
        numeric_value(replace(record, value_number=bad), "REAL")


def test_two_typed_fields_rejected(ctx):
    ids, _ = population(ctx)
    record = ctx.service._values.get_by_id(ids[0])
    with pytest.raises(QualityControlError):
        numeric_value(replace(record, value_text="raw"), "INTEGER")


def test_population_identity_order_dedup(ctx):
    ids, unit = population(ctx)
    rid = stat_rule(ctx)
    first = check(ctx, ids, rid)
    result = check(ctx, tuple(reversed(ids)), rid, target=ids[-1])
    assert result.kept_issue_ids == first.created_issue_ids
    snapshot = json.loads(issues(ctx)[0]["rule_parameters_snapshot_json"])
    assert snapshot["execution"]["population_value_ids"] == sorted(ids)
    assert snapshot["execution"]["sample_size"] == 5
    assert snapshot["execution"]["percentile_algorithm"] == "linear_n_minus_one_v1"
    assert snapshot["rule_parameters"] == {"method": "IQR", "multiplier": 1.5}


def test_population_change_protected(ctx):
    ids, unit = population(ctx)
    rid = stat_rule(ctx)
    first = check(ctx, ids, rid)
    extra = value(ctx, 0, "INTEGER", unit_id=unit)
    second = check(ctx, ids + (extra,), rid, target=ids[-1])
    assert first.created_issue_ids != second.created_issue_ids
    old = tuple(issues(ctx)[0])
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_integer=0 WHERE characteristic_value_id=?",
        (ids[-1],),
    )
    resolved = check(ctx, ids + (extra,), rid, target=ids[-1])
    assert resolved.deactivated_issue_ids == second.created_issue_ids
    assert tuple(issues(ctx)[0]) == old


def test_lifecycle_review(ctx):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    first = check(ctx, ids, rid)
    ctx.conn.execute(
        "UPDATE data_quality_issue SET review_status='CONFIRMED',review_note='note',reviewed_at=?",
        (STAMP,),
    )
    old = dict(issues(ctx)[0])
    assert check(ctx, ids, rid).kept_issue_ids == first.created_issue_ids
    assert dict(issues(ctx)[0]) == old
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_integer=0 WHERE characteristic_value_id=?",
        (ids[-1],),
    )
    assert check(ctx, ids, rid).deactivated_issue_ids == first.created_issue_ids
    old["is_active"] = 0
    assert dict(issues(ctx)[0]) == old
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_integer=100 WHERE characteristic_value_id=?",
        (ids[-1],),
    )
    assert check(ctx, ids, rid).created_issue_ids != first.created_issue_ids
    assert len(issues(ctx)) == 2 and issues(ctx)[0]["is_active"] == 0


def test_policy_change_preserves_snapshot(ctx):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    first = check(ctx, ids, rid)
    old = dict(issues(ctx)[0])
    ctx.conn.execute(
        "UPDATE quality_rule SET parameters_json=?", ('{"method":"IQR","multiplier":3}',)
    )
    result = check(ctx, ids, rid)
    assert (
        result.deactivated_issue_ids == first.created_issue_ids
        and len(result.created_issue_ids) == 1
    )
    old["is_active"] = 0
    assert dict(issues(ctx)[0]) == old


def test_disabled_preserves(ctx):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    check(ctx, ids, rid)
    old = tuple(issues(ctx)[0])
    ctx.conn.execute("UPDATE quality_rule SET is_enabled=0")
    assert check(ctx, ids, rid).checked_count == 0
    assert tuple(issues(ctx)[0]) == old


@pytest.mark.parametrize("operation", ["INSERT", "UPDATE"])
def test_write_rollback(ctx, operation):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    check(ctx, ids, rid)
    old = [tuple(r) for r in issues(ctx)]
    ctx.conn.execute("UPDATE quality_rule SET rule_version='v2'")
    ctx.conn.execute(
        f"CREATE TRIGGER fail BEFORE {operation} ON data_quality_issue "
        "BEGIN SELECT RAISE(ABORT,'private SQL'); END"
    )
    with pytest.raises(QualityControlPersistenceError) as caught:
        check(ctx, ids, rid)
    assert "private" not in str(caught.value) and [tuple(r) for r in issues(ctx)] == old


def test_no_mutation_or_raw_finding(ctx, monkeypatch):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
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
    result = check(ctx, ids, rid)
    assert before == {
        t: [tuple(r) for r in ctx.conn.execute(f'SELECT * FROM "{t}"')] for t in tables
    }
    for secret in (SECRET, PATH, "Synthetic stat unit", "100", "q1", "lower_bound"):
        assert secret not in repr(captured) and secret not in repr(result)
    snapshot = json.loads(issues(ctx)[0]["rule_parameters_snapshot_json"])
    assert set(snapshot) == {"format", "rule_parameters", "execution"}
    with pytest.raises(FrozenInstanceError):
        captured[0].severity = "ERROR"


@pytest.mark.parametrize(
    "kind",
    [
        "REQUIRED",
        "NON_NEGATIVE",
        "RANGE",
        "REFERENCE_COMPARE",
        "UNIT_MATCH",
        "UNIT_CONVERSION_MISSING",
    ],
)
def test_other_qc_protection(ctx, kind):
    ids, unit = population(ctx, (0, 0, 0, 0, -100))
    target = ids[-1]
    generic = rule(ctx, kind, "INTEGER", params='{"min":0}' if kind == "RANGE" else None)
    if kind == "REQUIRED":
        ctx.conn.execute("UPDATE characteristic_value SET is_active=0")
        recheck(ctx, targets=(required(ctx, "INTEGER"),), rule_ids=(generic,))
        ctx.conn.execute("UPDATE characteristic_value SET is_active=1")
    elif kind == "REFERENCE_COMPARE":
        ctx.service.compare_reference(target, ids[0], generic, field_policy=POLICY)
    elif kind in ("UNIT_MATCH", "UNIT_CONVERSION_MISSING"):
        expected = ctx.dictionary.create_unit("Expected", "expected").unit_id
        ctx.conn.execute(
            "UPDATE data_dictionary SET unit_id=? WHERE dictionary_id=?",
            (expected, ctx.items["INTEGER"].dictionary_id),
        )
        ctx.service.check_unit(target, generic, field_policy=POLICY)
    else:
        recheck(ctx, target, rule_ids=(generic,))
    old = tuple(issues(ctx)[0])
    rid = stat_rule(ctx)
    check(ctx, ids, rid)
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_integer=0 WHERE characteristic_value_id=?", (target,)
    )
    check(ctx, ids, rid)
    assert tuple(issues(ctx)[0]) == old


@pytest.mark.parametrize(
    "change",
    [
        "rule_type='RANGE'",
        "target_type='UNKNOWN'",
        "dictionary_id=NULL",
        "rule_version=''",
        "dictionary_id=999",
    ],
)
def test_bad_rule(ctx, change):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    if change == "dictionary_id=999":
        change = "dictionary_id=" + str(ctx.items["REAL"].dictionary_id)
    ctx.conn.execute("UPDATE quality_rule SET " + change)
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, ids, rid)
    assert not issues(ctx)


def test_core_rejected(ctx):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    ctx.conn.execute("UPDATE data_dictionary SET storage_type='CORE'")
    with pytest.raises(QualityRuleConfigurationError):
        check(ctx, ids, rid)


def test_other_target_unchanged(ctx):
    ids, unit = population(ctx, (0, 0, 0, 0, 0, 0, -100, 100))
    rid = stat_rule(ctx)
    check(ctx, ids, rid, target=ids[-2])
    old = tuple(issues(ctx)[0])
    check(ctx, ids, rid)
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_integer=0 WHERE characteristic_value_id=?",
        (ids[-1],),
    )
    check(ctx, ids, rid)
    assert tuple(issues(ctx)[0]) == old


@pytest.mark.parametrize("snapshot", [None, "{}", "private", "[]"])
def test_invalid_snapshot_preserved(ctx, snapshot):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    check(ctx, ids, rid)
    ctx.conn.execute("UPDATE data_quality_issue SET rule_parameters_snapshot_json=?", (snapshot,))
    old = tuple(issues(ctx)[0])
    ctx.conn.execute("UPDATE characteristic_value SET value_integer=0")
    check(ctx, ids, rid)
    assert tuple(issues(ctx)[0]) == old


def test_concurrent_dedup(ctx):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    barrier = Barrier(2)

    def worker(_):
        with closing(connect_database(ctx.path)) as conn:
            barrier.wait()
            return QualityControlService(conn).check_statistical_outlier(
                ids[-1], rid, population_value_ids=ids, field_policy=POLICY
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert sum(len(r.created_issue_ids) for r in results) == 1
    assert len(issues(ctx)) == 1


def test_commit_failure_rollback(ctx):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)

    def authorizer(action, arg1, *args):
        if action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorizer)
    try:
        with pytest.raises(QualityControlPersistenceError):
            check(ctx, ids, rid)
    finally:
        ctx.conn.set_authorizer(None)
    assert not issues(ctx) and not ctx.conn.in_transaction


def test_population_not_filtered_by_representative(ctx):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    assert (
        ctx.conn.execute("SELECT sum(is_representative) FROM characteristic_value").fetchone()[0]
        == 0
    )
    assert check(ctx, ids, rid).finding_count == 1


def test_policy_exclusion(ctx):
    ids, _ = population(ctx)
    rid = stat_rule(ctx)
    with pytest.raises(QualityControlError):
        ctx.service.check_statistical_outlier(
            ids[-1],
            rid,
            population_value_ids=ids,
            field_policy=ImportFieldPolicy(frozenset({"synthetic_integer"})),
        )
    assert not issues(ctx)


def test_phase7_final_multi_issue_and_current_use_information_gate(ctx):
    """실제 QC API 공존과 값별 정보 가용성. current-use 변경 서비스는 구현하지 않는다."""
    from small_stream_research_tool.repositories.quality_control_repository import (
        QualityControlRepository,
    )

    ids, actual = population(ctx)
    target = ids[-1]
    reference = ids[0]
    expected = ctx.dictionary.create_unit("Gate expected", "gateE").unit_id
    ctx.conn.execute(
        "UPDATE data_dictionary SET unit_id=? WHERE dictionary_id=?",
        (expected, ctx.items["INTEGER"].dictionary_id),
    )
    ref_rule = rule(ctx, "REFERENCE_COMPARE", "INTEGER", severity="WARNING")
    unit_rule = rule(ctx, "UNIT_MATCH", "INTEGER", severity="WARNING")
    statistical_rule = stat_rule(ctx)
    error_rule = rule(ctx, "RANGE", "INTEGER", params='{"max":50}', severity="ERROR")
    repository = QualityControlRepository(ctx.conn)

    def target_severities(value_id):
        return {
            issue.severity
            for issue in repository.list_active_issues(STREAM)
            if issue.characteristic_value_id == value_id
        }

    ctx.service.compare_reference(target, reference, ref_rule, field_policy=POLICY)
    ctx.service.check_unit(target, unit_rule, field_policy=POLICY)
    check(ctx, ids, statistical_rule)
    assert target_severities(target) == {"WARNING", "INFO"}
    assert repository.active_severity_counts(STREAM).status == "NEEDS_REVIEW"
    assert target_severities(reference) == set()
    ctx.conn.execute("UPDATE data_quality_issue SET review_status='CONFIRMED'")
    assert repository.active_severity_counts(STREAM).status == "NEEDS_REVIEW"

    recheck(ctx, target, rule_ids=(error_rule,))
    assert target_severities(target) == {"ERROR", "WARNING", "INFO"}
    assert repository.active_severity_counts(STREAM).status == "ERROR"
    ctx.conn.execute("UPDATE data_quality_issue SET review_status='CORRECTED'")
    assert repository.active_severity_counts(STREAM).status == "ERROR"

    # 합성 fixture의 외부 설정/자료 변경을 모의하여 각 검사로 해소한다.
    ctx.conn.execute(
        "UPDATE quality_rule SET parameters_json=? WHERE rule_id=?", ('{"max":200}', error_rule)
    )
    recheck(ctx, target, rule_ids=(error_rule,))
    assert target_severities(target) == {"WARNING", "INFO"}
    assert repository.active_severity_counts(STREAM).status == "NEEDS_REVIEW"
    ctx.conn.execute(
        "UPDATE characteristic_value SET value_integer=100 WHERE characteristic_value_id=?",
        (reference,),
    )
    ctx.service.compare_reference(target, reference, ref_rule, field_policy=POLICY)
    ctx.conn.execute(
        "UPDATE data_dictionary SET unit_id=? WHERE dictionary_id=?",
        (actual, ctx.items["INTEGER"].dictionary_id),
    )
    ctx.service.check_unit(target, unit_rule, field_policy=POLICY)
    assert target_severities(target) == {"INFO"}
    assert repository.active_severity_counts(STREAM).status == "NEEDS_REVIEW"
    check(ctx, ids, statistical_rule)
    assert target_severities(target) == set()
    assert repository.active_severity_counts(STREAM).status == "NORMAL"
    assert len(issues(ctx)) == 4
    assert all(row["is_active"] == 0 and row["review_status"] == "CORRECTED" for row in issues(ctx))
    assert (
        ctx.conn.execute("SELECT sum(is_representative) FROM characteristic_value").fetchone()[0]
        == 0
    )
    assert ctx.conn.execute("SELECT count(*) FROM stream_characteristic").fetchone()[0] == 0
