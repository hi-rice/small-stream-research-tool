"""합성 DB에서 값 lifecycle·파생 캐시·QC/출처 보존을 검증한다."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier
from types import SimpleNamespace

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.current_value_maintenance_errors import (
    CurrentUseLossConfirmationRequiredError,
    MaintenanceInvariantError,
    MaintenancePersistenceError,
    MaintenanceValidationError,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    SmallStreamRepository,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.current_value_maintenance_service import (
    CurrentValueMaintenanceService,
)
from small_stream_research_tool.services.current_value_service import CurrentValueService
from small_stream_research_tool.services.dictionary_service import DictionaryService

STAMP = "2026-09-13T01:02:03Z"
STREAM = "01234567890"
REASON = "RESEARCHER_SELECTION"


@pytest.fixture
def ctx(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as conn:
        dictionary = DictionaryService(DictionaryRepository(conn))
        category = dictionary.create_category("synthetic", "Synthetic")
        version = dictionary.create_version("synthetic-v1")
        item = dictionary.create_item(
            "Synthetic", "synthetic_real", category.category_id, "REAL", version.version_id
        )
        with transaction(conn):
            SmallStreamRepository(conn).create(
                stream_code=STREAM,
                province_code="01",
                city_county_code="234",
                town_code="567",
                stream_serial_no="890",
                stream_name="Synthetic",
                created_at=STAMP,
                updated_at=STAMP,
            )
            actor = UserRepository(conn).create_user(
                login_id="synthetic",
                password_hash="synthetic-not-for-login",
                display_name="Synthetic",
                department=None,
                role=None,
                timestamp=STAMP,
            )
        yield SimpleNamespace(
            conn=conn,
            path=path,
            item=item.dictionary_id,
            actor=actor.user_id,
            service=CurrentValueMaintenanceService(conn),
        )


def value(ctx, number=1.5, **changes):
    data = dict(
        stream_code=STREAM,
        dictionary_id=ctx.item,
        value_number=number,
        original_value="SYNTHETIC_RAW",
        source_reference="C:/synthetic-only/source.xlsx",
        created_at=STAMP,
        updated_at=STAMP,
    )
    data.update(changes)
    with transaction(ctx.conn):
        return CharacteristicValueRepository(ctx.conn).create(**data).characteristic_value_id


def current(ctx, value_id):
    return CurrentValueService(ctx.conn).select_current_value(value_id, ctx.actor)


def deactivate(ctx, value_id, **kwargs):
    return ctx.service.deactivate_value(value_id, ctx.actor, reason_code=REASON, **kwargs)


def restore(ctx, value_id):
    return ctx.service.restore_value(value_id, ctx.actor, reason_code=REASON)


def snapshot(ctx):
    return {
        table: ctx.conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        for table in (
            "characteristic_value",
            "stream_characteristic",
            "data_quality_issue",
            "record_history",
        )
    }


def test_noncurrent_lifecycle_preserves_source_qc_and_noop(ctx):
    vid = value(ctx)
    source = CharacteristicValueRepository(ctx.conn).get_by_id(vid)
    ctx.conn.execute(
        "INSERT INTO data_quality_issue (characteristic_value_id,stream_code,issue_type,"
        "severity,message,review_status,created_at) VALUES (?,?,?,?,?,?,?)",
        (vid, STREAM, "SYNTHETIC", "ERROR", "Synthetic", "CONFIRMED", STAMP),
    )
    issues = snapshot(ctx)["data_quality_issue"]
    deactivated = deactivate(ctx, vid)
    assert deactivated.changed and not deactivated.current_use_released
    assert not CharacteristicValueRepository(ctx.conn).get_by_id(vid).is_active
    assert snapshot(ctx)["data_quality_issue"] == issues
    assert not deactivate(ctx, vid).changed
    restored = restore(ctx, vid)
    assert restored.changed and not restore(ctx, vid).changed
    assert CharacteristicValueRepository(ctx.conn).get_by_id(vid) == source
    assert snapshot(ctx)["data_quality_issue"] == issues
    assert ctx.conn.execute("SELECT count(*) FROM stream_characteristic").fetchone()[0] == 0
    rows = ctx.conn.execute(
        "SELECT change_type,old_value,new_value,actor_user_id "
        "FROM record_history ORDER BY history_id"
    ).fetchall()
    assert [r[0] for r in rows] == ["DEACTIVATE", "RESTORE"]
    assert all(r[3] == ctx.actor for r in rows)
    assert json.loads(rows[0][1])["is_active"] is True


def test_current_deactivation_needs_confirmation_and_leaves_no_current(ctx):
    a, b = value(ctx), value(ctx, 2.5)
    current(ctx, a)
    before = snapshot(ctx)
    with pytest.raises(CurrentUseLossConfirmationRequiredError):
        deactivate(ctx, a)
    assert snapshot(ctx) == before
    result = deactivate(ctx, a, confirm_current_use_loss=True)
    assert result.current_use_released
    assert ctx.conn.execute("SELECT count(*) FROM stream_characteristic").fetchone()[0] == 0
    assert (
        ctx.conn.execute(
            "SELECT count(*) FROM characteristic_value WHERE is_active=1 AND is_representative=1"
        ).fetchone()[0]
        == 0
    )
    assert not CharacteristicValueRepository(ctx.conn).get_by_id(b).is_representative
    event = ctx.conn.execute(
        "SELECT new_value FROM record_history WHERE history_id=?", (result.history_id,)
    ).fetchone()[0]
    assert json.loads(event) == {"is_active": False, "is_representative": False}
    restore(ctx, a)
    assert not CharacteristicValueRepository(ctx.conn).get_by_id(a).is_representative
    assert ctx.conn.execute("SELECT count(*) FROM stream_characteristic").fetchone()[0] == 0
    assert current(ctx, a).changed


@pytest.mark.parametrize("state", ["missing", "wrong", "stale", "none", "foreign"])
def test_rebuild_repairs_only_cache(ctx, state):
    a = value(ctx)
    b = value(ctx, 2.5)
    if state == "none":
        ctx.conn.execute(
            "INSERT INTO stream_characteristic VALUES (?,?,?,?)", (STREAM, ctx.item, a, STAMP)
        )
        expected = None
    else:
        current(ctx, a)
        expected = a
        if state == "missing":
            ctx.conn.execute("DELETE FROM stream_characteristic")
        elif state in ("wrong", "stale"):
            ctx.conn.execute("UPDATE stream_characteristic SET characteristic_value_id=?", (b,))
        else:
            with transaction(ctx.conn):
                SmallStreamRepository(ctx.conn).create(
                    stream_code="01234567891",
                    province_code="01",
                    city_county_code="234",
                    town_code="567",
                    stream_serial_no="891",
                    stream_name="Other",
                    created_at=STAMP,
                    updated_at=STAMP,
                )
            other = value(ctx, 3.5, stream_code="01234567891")
            ctx.conn.execute("UPDATE stream_characteristic SET characteristic_value_id=?", (other,))
    values = ctx.conn.execute("SELECT * FROM characteristic_value ORDER BY 1").fetchall()
    result = ctx.service.rebuild_current_value_cache(ctx.actor)
    assert result.changed_pairs == ((STREAM, ctx.item),)
    assert len(result.history_ids) == 1
    cache = ctx.conn.execute("SELECT characteristic_value_id FROM stream_characteristic").fetchall()
    assert cache == ([] if expected is None else [(expected,)])
    assert ctx.conn.execute("SELECT * FROM characteristic_value ORDER BY 1").fetchall() == values
    assert (
        ctx.conn.execute(
            "SELECT change_type FROM record_history WHERE history_id=?", (result.history_ids[0],)
        ).fetchone()[0]
        == "CACHE_REBUILD"
    )
    assert not ctx.service.rebuild_current_value_cache(ctx.actor).history_ids


def test_inactive_historical_representative_ignored_and_restore_rejected(ctx):
    vid = value(ctx, is_active=False, is_representative=True)
    assert not ctx.service.rebuild_current_value_cache(ctx.actor).changed_pairs
    before = snapshot(ctx)
    with pytest.raises(MaintenanceInvariantError):
        restore(ctx, vid)
    assert snapshot(ctx) == before


def test_rebuild_target_scope_and_no_auto_selection(ctx):
    a = value(ctx)
    assert not ctx.service.rebuild_current_value_cache(
        ctx.actor, stream_code=STREAM, dictionary_id=ctx.item
    ).changed_pairs
    current(ctx, a)
    ctx.conn.execute("DELETE FROM stream_characteristic")
    result = ctx.service.rebuild_current_value_cache(
        ctx.actor, stream_code=STREAM, dictionary_id=ctx.item
    )
    assert result.changed_pairs == ((STREAM, ctx.item),)


@pytest.mark.parametrize("action", ["deactivate", "restore", "rebuild"])
def test_history_failure_rolls_back(ctx, action):
    vid = value(ctx)
    if action == "restore":
        deactivate(ctx, vid)
    elif action == "rebuild":
        current(ctx, vid)
        ctx.conn.execute("DELETE FROM stream_characteristic")
    before = snapshot(ctx)
    ctx.conn.execute(
        "CREATE TRIGGER fail BEFORE INSERT ON record_history "
        "BEGIN SELECT RAISE(ABORT,'SYNTHETIC_PRIVATE_SQL'); END"
    )
    with pytest.raises(MaintenancePersistenceError):
        if action == "deactivate":
            deactivate(ctx, vid)
        elif action == "restore":
            restore(ctx, vid)
        else:
            ctx.service.rebuild_current_value_cache(ctx.actor)
    assert snapshot(ctx) == before and not ctx.conn.in_transaction


@pytest.mark.parametrize("bad", [None, True, 0, 2**63])
def test_actor_and_value_validation(ctx, bad):
    vid = value(ctx)
    before = snapshot(ctx)
    with pytest.raises(MaintenanceValidationError):
        ctx.service.deactivate_value(vid, bad, reason_code=REASON)
    assert snapshot(ctx) == before
    with pytest.raises(MaintenanceValidationError):
        ctx.service.restore_value(bad, ctx.actor, reason_code=REASON)
    assert snapshot(ctx) == before


def test_commit_failure_and_fk_integrity(ctx):
    vid = value(ctx)
    before = snapshot(ctx)
    ctx.conn.set_authorizer(
        lambda action, arg, *_: (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_TRANSACTION and arg == "COMMIT"
            else sqlite3.SQLITE_OK
        )
    )
    try:
        with pytest.raises(MaintenancePersistenceError):
            deactivate(ctx, vid)
    finally:
        ctx.conn.set_authorizer(None)
    assert snapshot(ctx) == before
    assert ctx.conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_concurrent_current_deactivation_and_selection(ctx):
    a, b = value(ctx), value(ctx, 2.5)
    current(ctx, a)
    barrier = Barrier(2)

    def worker(kind):
        with closing(connect_database(ctx.path)) as conn:
            barrier.wait()
            if kind == "deactivate":
                return CurrentValueMaintenanceService(conn).deactivate_value(
                    a, ctx.actor, confirm_current_use_loss=True, reason_code=REASON
                )
            return CurrentValueService(conn).select_current_value(b, ctx.actor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, kind) for kind in ("deactivate", "select")]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except MaintenanceInvariantError:
                outcomes.append("stale-current-request")
    assert any(outcome != "stale-current-request" for outcome in outcomes)
    reps = ctx.conn.execute(
        "SELECT characteristic_value_id FROM characteristic_value WHERE is_active=1 "
        "AND is_representative=1"
    ).fetchall()
    cache = ctx.conn.execute("SELECT characteristic_value_id FROM stream_characteristic").fetchall()
    assert cache == reps and len(reps) <= 1


def test_rebuild_multiple_pairs_rolls_back_together(ctx):
    a = value(ctx)
    current(ctx, a)
    ctx.conn.execute("DELETE FROM stream_characteristic")
    with transaction(ctx.conn):
        SmallStreamRepository(ctx.conn).create(
            stream_code="01234567891",
            province_code="01",
            city_county_code="234",
            town_code="567",
            stream_serial_no="891",
            stream_name="Other",
            created_at=STAMP,
            updated_at=STAMP,
        )
    b = value(ctx, 2.5, stream_code="01234567891", is_representative=True)
    assert b != a
    before = snapshot(ctx)
    ctx.conn.execute(
        "CREATE TRIGGER fail_second BEFORE INSERT ON stream_characteristic "
        "WHEN NEW.stream_code='01234567891' "
        "BEGIN SELECT RAISE(ABORT,'SYNTHETIC_PRIVATE_SQL'); END"
    )
    with pytest.raises(MaintenancePersistenceError):
        ctx.service.rebuild_current_value_cache(ctx.actor)
    assert snapshot(ctx) == before
