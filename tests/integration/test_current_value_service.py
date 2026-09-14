"""합성 사전·규칙·값만으로 QC 판정, snapshot, 중복 방지와 rollback을 검증한다."""

import json
import sqlite3
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.current_value_errors import (
    CurrentValueBlockedByQualityError,
    CurrentValueConfirmationRequiredError,
    CurrentValueInvariantError,
    CurrentValuePersistenceError,
    CurrentValueSelectionError,
)
from small_stream_research_tool.models.import_preparation import ImportFieldPolicy
from small_stream_research_tool.models.quality_control import (
    QualityControlRequest,
    RequiredImportTarget,
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
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.current_value_service import CurrentValueService
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


@pytest.fixture
def actor(ctx):
    with transaction(ctx.conn):
        return (
            UserRepository(ctx.conn)
            .create_user(
                login_id="synthetic_actor",
                password_hash="synthetic-not-for-login",
                display_name="Synthetic",
                department=None,
                role=None,
                timestamp=STAMP,
            )
            .user_id
        )


def select(ctx, vid, actor, **kwargs):
    return CurrentValueService(ctx.conn).select_current_value(vid, actor, **kwargs)


def history(ctx):
    cursor = ctx.conn.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute("SELECT * FROM record_history ORDER BY history_id").fetchall()


def state(ctx):
    return {
        t: ctx.conn.execute(f"SELECT * FROM {t}").fetchall()
        for t in (
            "characteristic_value",
            "stream_characteristic",
            "record_history",
            "data_quality_issue",
        )
    }


def add_issue(ctx, vid, severity="ERROR", active=1, review="UNREVIEWED", kind="SYNTHETIC"):
    ctx.conn.execute(
        "INSERT INTO data_quality_issue (characteristic_value_id,stream_code,issue_type,"
        "severity,message,is_active,review_status,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (vid, STREAM, kind, severity, "Synthetic", active, review, STAMP),
    )


def test_first_switch_noop(ctx, actor):
    a, b = value(ctx), value(ctx, 2.0)
    before = ctx.conn.execute("SELECT * FROM characteristic_value").fetchall()
    first = select(ctx, a, actor, reason="RESEARCHER_SELECTION")
    assert first.changed and first.previous_value_id is None and first.current_value_id == a
    assert first.qc_status_before_selection == "NORMAL"
    assert first.completed_at.endswith("Z") and first.history_id == history(ctx)[0]["history_id"]
    assert history(ctx)[0]["actor_user_id"] == actor
    assert history(ctx)[0]["change_type"] == "CURRENT_VALUE_CHANGE"
    assert json.loads(history(ctx)[0]["old_value"]) == {"characteristic_value_id": None}
    result = select(ctx, b, actor)
    assert result.previous_value_id == a and result.current_value_id == b
    assert ctx.conn.execute(
        "SELECT characteristic_value_id FROM characteristic_value WHERE is_representative=1"
    ).fetchall() == [(b,)]
    assert ctx.conn.execute(
        "SELECT characteristic_value_id FROM stream_characteristic"
    ).fetchall() == [(b,)]
    assert json.loads(history(ctx)[1]["old_value"]) == {"characteristic_value_id": a}
    assert json.loads(history(ctx)[1]["new_value"])["characteristic_value_id"] == b
    stable = state(ctx)
    noop = select(ctx, b, actor)
    assert not noop.changed and noop.history_id is None and state(ctx) == stable
    columns = [r[1] for r in ctx.conn.execute("PRAGMA table_info(characteristic_value)")]
    index = columns.index("is_representative")
    after = ctx.conn.execute("SELECT * FROM characteristic_value").fetchall()
    assert [r[:index] + r[index + 1 :] for r in before] == [
        r[:index] + r[index + 1 :] for r in after
    ]
    with pytest.raises(FrozenInstanceError):
        first.changed = False


@pytest.mark.parametrize("confirmation", [False, True])
@pytest.mark.parametrize("review", ["UNREVIEWED", "CONFIRMED", "CORRECTED", "DEFERRED"])
def test_error_never_overridden(ctx, actor, confirmation, review):
    vid = value(ctx)
    add_issue(ctx, vid, review=review)
    before = state(ctx)
    with pytest.raises(CurrentValueBlockedByQualityError):
        select(ctx, vid, actor, confirm_review_required=confirmation)
    assert state(ctx) == before


@pytest.mark.parametrize(
    "severity,kind",
    [
        ("WARNING", "REFERENCE_VALUE_MISMATCH"),
        ("WARNING", "UNIT_MISMATCH"),
        ("INFO", "UNIT_CONVERSION_MISSING"),
        ("INFO", "STATISTICAL_OUTLIER_CANDIDATE"),
    ],
)
def test_confirmation_does_not_resolve(ctx, actor, severity, kind):
    vid = value(ctx)
    add_issue(ctx, vid, severity, kind=kind, review="CONFIRMED")
    before = state(ctx)
    with pytest.raises(CurrentValueConfirmationRequiredError):
        select(ctx, vid, actor)
    assert state(ctx) == before
    result = select(ctx, vid, actor, confirm_review_required=True, reason="QC_REVIEW_CONFIRMED")
    assert result.confirmation_required and result.confirmation_used
    assert result.qc_status_before_selection == "NEEDS_REVIEW"
    assert state(ctx)["data_quality_issue"] == before["data_quality_issue"]
    payload = json.loads(history(ctx)[0]["new_value"])
    assert payload["confirmation_used"] and history(ctx)[0]["reason"] == "QC_REVIEW_CONFIRMED"


@pytest.mark.parametrize("severities", [("WARNING", "INFO"), ("ERROR", "WARNING")])
def test_mixed_gate(ctx, actor, severities):
    vid = value(ctx)
    for severity in severities:
        add_issue(ctx, vid, severity)
    if "ERROR" in severities:
        with pytest.raises(CurrentValueBlockedByQualityError):
            select(ctx, vid, actor, confirm_review_required=True)
    else:
        with pytest.raises(CurrentValueConfirmationRequiredError):
            select(ctx, vid, actor)
        assert select(ctx, vid, actor, confirm_review_required=True).changed


@pytest.mark.parametrize("scope", ["other_value", "null_value", "inactive"])
def test_unrelated_issue_not_blocking(ctx, actor, scope):
    vid = value(ctx)
    other = value(ctx, 2.0)
    add_issue(
        ctx,
        other if scope == "other_value" else None if scope == "null_value" else vid,
        active=0 if scope == "inactive" else 1,
    )
    assert select(ctx, vid, actor).qc_status_before_selection == "NORMAL"


@pytest.mark.parametrize(
    "bad",
    [
        "missing_value",
        "inactive_value",
        "missing_actor",
        "inactive_actor",
        "inactive_stream",
        "inactive_dictionary",
        "deprecated_dictionary",
        "core",
        "inactive_category",
    ],
)
def test_target_actor_validation(ctx, actor, bad):
    vid = value(ctx)
    if bad == "missing_value":
        vid = 9999
    elif bad == "missing_actor":
        actor = 9999
    elif bad == "inactive_actor":
        ctx.conn.execute("UPDATE app_user SET is_active=0")
    elif bad == "inactive_value":
        ctx.conn.execute("UPDATE characteristic_value SET is_active=0")
    elif bad == "inactive_stream":
        ctx.conn.execute("UPDATE small_stream SET is_active=0")
    elif bad == "inactive_dictionary":
        ctx.conn.execute("UPDATE data_dictionary SET is_active=0")
    elif bad == "deprecated_dictionary":
        ctx.conn.execute("UPDATE data_dictionary SET deprecated_version_id=created_version_id")
    elif bad == "core":
        ctx.conn.execute("UPDATE data_dictionary SET storage_type='CORE'")
    else:
        ctx.conn.execute("UPDATE data_category SET is_active=0")
    before = state(ctx)
    with pytest.raises(CurrentValueSelectionError):
        select(ctx, vid, actor)
    assert state(ctx) == before


@pytest.mark.parametrize(
    "bad",
    [
        "flag_only",
        "cache_only",
        "different_flag",
        "inactive_cache",
        "wrong_dictionary",
        "wrong_stream",
    ],
)
def test_inconsistent_state_rejected(ctx, actor, bad):
    a, b = value(ctx), value(ctx, 2.0)
    dictionary_id = ctx.items["REAL"].dictionary_id
    if bad in ("flag_only", "different_flag"):
        ctx.conn.execute(
            "UPDATE characteristic_value SET is_representative=1 WHERE characteristic_value_id=?",
            (a,),
        )
    if bad != "flag_only":
        cached = b if bad == "different_flag" else a
        if bad == "inactive_cache":
            ctx.conn.execute(
                "UPDATE characteristic_value SET is_active=0 WHERE characteristic_value_id=?", (a,)
            )
        elif bad == "wrong_dictionary":
            cached = value(ctx, 1, "INTEGER")
        elif bad == "wrong_stream":
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
            cached = value(ctx, 2.0, stream_code="12345678010")
        ctx.conn.execute(
            "INSERT INTO stream_characteristic VALUES (?,?,?,?)",
            (STREAM, dictionary_id, cached, STAMP),
        )
    before = state(ctx)
    with pytest.raises(CurrentValueInvariantError):
        select(ctx, b, actor)
    assert state(ctx) == before


@pytest.mark.parametrize(
    "table,operation",
    [
        ("characteristic_value", "UPDATE"),
        ("stream_characteristic", "UPDATE"),
        ("record_history", "INSERT"),
    ],
)
def test_failure_rolls_back_switch(ctx, actor, table, operation):
    a, b = value(ctx), value(ctx, 2.0)
    select(ctx, a, actor)
    before = state(ctx)
    ctx.conn.execute(
        f"CREATE TRIGGER fail BEFORE {operation} ON {table} "
        "BEGIN SELECT RAISE(ABORT,'private SQL'); END"
    )
    with pytest.raises(CurrentValuePersistenceError) as caught:
        select(ctx, b, actor)
    assert "private" not in str(caught.value) and state(ctx) == before
    assert not ctx.conn.in_transaction


def test_commit_failure(ctx, actor):
    vid = value(ctx)
    before = state(ctx)

    def authorizer(action, arg1, *args):
        if action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorizer)
    try:
        with pytest.raises(CurrentValuePersistenceError):
            select(ctx, vid, actor)
    finally:
        ctx.conn.set_authorizer(None)
    assert state(ctx) == before and not ctx.conn.in_transaction


def test_concurrent_selection(ctx, actor):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    a, b = value(ctx), value(ctx, 2.0)
    barrier = Barrier(2)

    def worker(vid):
        with closing(connect_database(ctx.path)) as conn:
            barrier.wait()
            return CurrentValueService(conn).select_current_value(vid, actor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, (a, b)))
    reps = ctx.conn.execute(
        "SELECT characteristic_value_id FROM characteristic_value "
        "WHERE is_representative=1 AND is_active=1"
    ).fetchall()
    cache = ctx.conn.execute("SELECT characteristic_value_id FROM stream_characteristic").fetchall()
    assert len(reps) == 1 and cache == reps
    assert len(history(ctx)) == 2 and all(r.changed for r in results)
    assert (
        json.loads(history(ctx)[1]["old_value"])["characteristic_value_id"]
        == json.loads(history(ctx)[0]["new_value"])["characteristic_value_id"]
    )


@pytest.mark.parametrize("bad", [1, "true", None])
def test_confirmation_exact_bool(ctx, actor, bad):
    with pytest.raises(CurrentValueSelectionError):
        select(ctx, value(ctx), actor, confirm_review_required=bad)


@pytest.mark.parametrize(
    "reason", ["C:/private.xlsx", "rtsp://private", "010-0000-0000", SECRET, [], 1]
)
def test_reason_is_safe_code(ctx, actor, reason):
    with pytest.raises(CurrentValueSelectionError) as caught:
        select(ctx, value(ctx), actor, reason=reason)
    assert "private" not in str(caught.value) and not history(ctx)


def test_current_reselect_rechecks_error(ctx, actor):
    vid = value(ctx)
    select(ctx, vid, actor)
    add_issue(ctx, vid)
    before = state(ctx)
    with pytest.raises(CurrentValueBlockedByQualityError):
        select(ctx, vid, actor, confirm_review_required=True)
    assert state(ctx) == before


@pytest.mark.parametrize(
    "dtype,data",
    [
        ("REAL", 1.25),
        ("INTEGER", 4),
        ("TEXT", "private text"),
        ("DATE", "2026-09-14"),
        ("DATETIME", "2026-09-14T00:00:00"),
    ],
)
def test_all_flex_types_preserved(ctx, actor, dtype, data):
    vid = value(ctx, data, dtype)
    before = ctx.service._values.get_by_id(vid)
    result = select(ctx, vid, actor)
    after = ctx.service._values.get_by_id(vid)
    assert replace(before, is_representative=True) == after
    assert SECRET not in repr(result) and PATH not in repr(result)
    assert SECRET not in str([dict(r) for r in history(ctx)])


@pytest.mark.parametrize("bad", [None, True, 0, -1, "1"])
def test_bad_id(ctx, actor, bad):
    with pytest.raises(CurrentValueSelectionError):
        select(ctx, bad, actor)
    with pytest.raises(CurrentValueSelectionError):
        select(ctx, value(ctx), bad)
    assert not history(ctx)


def test_noop_does_not_execute_write(ctx, actor):
    vid = value(ctx)
    select(ctx, vid, actor)

    def authorizer(action, *args):
        if action in (sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_INSERT, sqlite3.SQLITE_DELETE):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorizer)
    try:
        assert not select(ctx, vid, actor).changed
    finally:
        ctx.conn.set_authorizer(None)


def test_final_invariant_failure_rollback(ctx, actor, monkeypatch):
    from small_stream_research_tool.repositories.current_value_repository import (
        CurrentValueRepository,
    )

    vid = value(ctx)
    before = state(ctx)
    monkeypatch.setattr(CurrentValueRepository, "set_cache", lambda *args: None)
    with pytest.raises(CurrentValueInvariantError):
        select(ctx, vid, actor)
    assert state(ctx) == before


def test_qc_query_and_write_share_immediate_transaction(ctx, actor):
    vid = value(ctx)
    trace = []
    ctx.conn.set_trace_callback(trace.append)
    try:
        select(ctx, vid, actor)
    finally:
        ctx.conn.set_trace_callback(None)
    begin = trace.index("BEGIN IMMEDIATE")
    qc = next(
        i for i, s in enumerate(trace) if "SELECT severity,count(*) FROM data_quality_issue" in s
    )
    write = next(i for i, s in enumerate(trace) if s.startswith("UPDATE characteristic_value"))
    commit = trace.index("COMMIT")
    assert begin < qc < write < commit
    assert sum(s == "COMMIT" for s in trace) == 1


def test_other_stream_error_does_not_block(ctx, actor):
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
    other = value(ctx, 2.0, stream_code="12345678010")
    add_issue(ctx, other)
    ctx.conn.execute("UPDATE data_quality_issue SET stream_code='12345678010'")
    assert select(ctx, value(ctx), actor).changed
