"""Phase 7 QC와 Phase 8A/B/C의 한 값 lifecycle을 합성 임시 DB에서 검증한다."""

import json
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace

import pytest

from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.correction import CorrectionRequest
from small_stream_research_tool.models.current_value_errors import (
    CurrentValueBlockedByQualityError,
    CurrentValueConfirmationRequiredError,
)
from small_stream_research_tool.models.current_value_maintenance_errors import (
    CurrentUseLossConfirmationRequiredError,
    MaintenancePersistenceError,
)
from small_stream_research_tool.models.import_preparation import ImportFieldPolicy
from small_stream_research_tool.models.quality_control import QualityControlRequest
from small_stream_research_tool.models.quality_control_errors import QualityControlPersistenceError
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    ImportColumnMappingRepository,
    ImportHistoryRepository,
    ImportSheetRepository,
    SmallStreamRepository,
    SourceFileRepository,
)
from small_stream_research_tool.repositories.quality_control_repository import (
    QualityControlRepository,
)
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.correction_service import CorrectionService
from small_stream_research_tool.services.current_value_maintenance_service import (
    CurrentValueMaintenanceService,
)
from small_stream_research_tool.services.current_value_service import CurrentValueService
from small_stream_research_tool.services.dictionary_service import DictionaryService
from small_stream_research_tool.services.quality_control_service import QualityControlService

STAMP = "2026-09-13T01:02:03Z"
STREAM = "01234567890"
REASON = "RESEARCHER_SELECTION"
POLICY = ImportFieldPolicy(frozenset())
RAW = "SYNTHETIC_RAW_ONLY"


@pytest.fixture
def ctx(tmp_path):
    path = tmp_path / "phase_8_gate.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as conn:
        dictionary = DictionaryService(DictionaryRepository(conn))
        category = dictionary.create_category("synthetic", "Synthetic")
        version = dictionary.create_version("synthetic-v1")
        item = dictionary.create_item(
            "Synthetic measurement",
            "synthetic_measurement",
            category.category_id,
            "REAL",
            version.version_id,
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
                login_id="synthetic_actor",
                password_hash="synthetic-not-for-login",
                display_name="Synthetic",
                department=None,
                role=None,
                timestamp=STAMP,
            )
            source = SourceFileRepository(conn).create(
                file_name="synthetic.xlsx",
                original_path="C:/synthetic-only/source.xlsx",
                registered_at=STAMP,
            )
            imp = ImportHistoryRepository(conn).create(
                source_file_id=source.source_file_id,
                batch_code="synthetic-gate",
                import_type="EXCEL",
                status="SUCCESS",
                started_at=STAMP,
                finished_at=STAMP,
                created_at=STAMP,
            )
            sheet = ImportSheetRepository(conn).create(
                import_id=imp.import_id,
                sheet_name="Synthetic",
                status="SUCCESS",
                created_at=STAMP,
            )
            mapping = ImportColumnMappingRepository(conn).create(
                import_sheet_id=sheet.import_sheet_id,
                source_column_index=4,
                dictionary_id=item.dictionary_id,
                mapping_status="USER_MAPPED",
                mapping_method="USER",
                created_at=STAMP,
            )
            original = CharacteristicValueRepository(conn).create(
                stream_code=STREAM,
                dictionary_id=item.dictionary_id,
                value_number=1.5,
                original_value=RAW,
                original_unit="synthetic raw unit",
                import_id=imp.import_id,
                import_sheet_id=sheet.import_sheet_id,
                mapping_id=mapping.mapping_id,
                source_row=5,
                reference_year=2020,
                created_at=STAMP,
                updated_at=STAMP,
            )
        yield SimpleNamespace(
            conn=conn,
            item=item.dictionary_id,
            actor=actor.user_id,
            original=original,
            source=source,
            imp=imp,
            sheet=sheet,
            mapping=mapping,
            values=CharacteristicValueRepository(conn),
            qc=QualityControlService(conn),
            selection=CurrentValueService(conn),
            correction=CorrectionService(conn),
            maintenance=CurrentValueMaintenanceService(conn),
        )


def correction(ctx, parent_id, number):
    return ctx.correction.create_correction(CorrectionRequest(parent_id, ctx.actor, number, REASON))


def rule(ctx, severity, *, minimum=3):
    return ctx.conn.execute(
        "INSERT INTO quality_rule (rule_code,rule_name,target_type,dictionary_id,rule_type,"
        "default_severity,parameters_json,rule_version,is_enabled,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "synthetic_" + severity,
            "Synthetic " + severity,
            "CHARACTERISTIC_VALUE",
            ctx.item,
            "RANGE",
            severity,
            json.dumps({"min": minimum}),
            "synthetic-v1",
            1,
            STAMP,
            STAMP,
        ),
    ).lastrowid


def recheck(ctx, value_id, rule_id):
    return ctx.qc.recheck(
        QualityControlRequest((value_id,), ()), field_policy=POLICY, rule_ids=(rule_id,)
    )


def current_state(ctx):
    reps = ctx.conn.execute(
        "SELECT characteristic_value_id FROM characteristic_value "
        "WHERE stream_code=? AND dictionary_id=? AND is_active=1 AND is_representative=1",
        (STREAM, ctx.item),
    ).fetchall()
    cache = ctx.conn.execute(
        "SELECT characteristic_value_id FROM stream_characteristic "
        "WHERE stream_code=? AND dictionary_id=?",
        (STREAM, ctx.item),
    ).fetchall()
    assert len(reps) <= 1 and cache == reps
    return reps[0][0] if reps else None


def history(ctx):
    return ctx.conn.execute(
        "SELECT history_id,change_type,table_name,record_key,old_value,new_value,"
        "actor_user_id,changed_at FROM record_history ORDER BY history_id"
    ).fetchall()


def test_e2e_provenance_qc_correction_lifecycle_and_cache_rebuild(ctx):
    original_id = ctx.original.characteristic_value_id
    selected = ctx.selection.select_current_value(original_id, ctx.actor)
    assert selected.changed and current_state(ctx) == original_id
    original_current = ctx.values.get_by_id(original_id)

    first = correction(ctx, original_id, 2.5)
    second = correction(ctx, first.correction_value_id, 2.5)
    assert len({original_id, first.correction_value_id, second.correction_value_id}) == 3
    assert ctx.values.get_by_id(original_id) == original_current
    assert current_state(ctx) == original_id
    assert ctx.conn.execute("SELECT count(*) FROM data_quality_issue").fetchone()[0] == 0
    for created in (first, second):
        row = ctx.values.get_by_id(created.correction_value_id)
        assert row.source_type == "USER_CORRECTION"
        assert row.is_active and not row.is_representative
        assert row.quality_status == "UNREVIEWED"
        assert (row.stream_code, row.dictionary_id) == (STREAM, ctx.item)
        assert (row.import_id, row.import_sheet_id, row.mapping_id, row.source_row) == (
            None,
            None,
            None,
            None,
        )
    assert json.loads(
        ctx.conn.execute(
            "SELECT old_value FROM record_history WHERE history_id=?", (second.history_id,)
        ).fetchone()[0]
    ) == {"source_value_id": first.correction_value_id}

    error_rule = rule(ctx, "ERROR")
    detected = recheck(ctx, second.correction_value_id, error_rule)
    assert len(detected.created_issue_ids) == 1
    before = (current_state(ctx), tuple(history(ctx)))
    with pytest.raises(CurrentValueBlockedByQualityError):
        ctx.selection.select_current_value(
            second.correction_value_id, ctx.actor, confirm_review_required=True
        )
    assert (current_state(ctx), tuple(history(ctx))) == before
    assert ctx.values.get_by_id(second.correction_value_id) is not None

    # 합성 규칙 정의를 완화한 명시적 재검사만 기존 ERROR를 inactive로 보존한다.
    ctx.conn.execute(
        "UPDATE quality_rule SET parameters_json=? WHERE rule_id=?",
        (json.dumps({"min": 2}), error_rule),
    )
    resolved = recheck(ctx, second.correction_value_id, error_rule)
    assert resolved.deactivated_issue_ids == detected.created_issue_ids
    assert (
        ctx.conn.execute(
            "SELECT is_active FROM data_quality_issue WHERE issue_id=?",
            (detected.created_issue_ids[0],),
        ).fetchone()[0]
        == 0
    )
    switched = ctx.selection.select_current_value(second.correction_value_id, ctx.actor)
    assert switched.previous_value_id == original_id
    assert current_state(ctx) == second.correction_value_id
    assert not ctx.values.get_by_id(original_id).is_representative

    issue_rows = ctx.conn.execute("SELECT * FROM data_quality_issue").fetchall()
    old = ctx.maintenance.deactivate_value(original_id, ctx.actor, reason_code=REASON)
    assert old.changed and not old.current_use_released
    assert current_state(ctx) == second.correction_value_id
    ctx.maintenance.restore_value(original_id, ctx.actor, reason_code=REASON)
    assert ctx.values.get_by_id(original_id).is_active
    assert not ctx.values.get_by_id(original_id).is_representative
    with pytest.raises(CurrentUseLossConfirmationRequiredError):
        ctx.maintenance.deactivate_value(second.correction_value_id, ctx.actor, reason_code=REASON)
    assert current_state(ctx) == second.correction_value_id
    released = ctx.maintenance.deactivate_value(
        second.correction_value_id,
        ctx.actor,
        confirm_current_use_loss=True,
        reason_code=REASON,
    )
    assert released.current_use_released and current_state(ctx) is None
    ctx.maintenance.restore_value(second.correction_value_id, ctx.actor, reason_code=REASON)
    assert current_state(ctx) is None
    assert ctx.conn.execute("SELECT * FROM data_quality_issue").fetchall() == issue_rows

    # 대표가 없는 pair의 잘못된 캐시는 삭제되고, 명시적 재선택 뒤 missing/stale 캐시만 복구된다.
    ctx.conn.execute(
        "INSERT INTO stream_characteristic VALUES (?,?,?,?)",
        (STREAM, ctx.item, original_id, STAMP),
    )
    flags = ctx.conn.execute(
        "SELECT characteristic_value_id,is_representative FROM characteristic_value ORDER BY 1"
    ).fetchall()
    removed = ctx.maintenance.rebuild_current_value_cache(ctx.actor)
    assert removed.changed_pairs == ((STREAM, ctx.item),) and current_state(ctx) is None
    assert (
        ctx.conn.execute(
            "SELECT characteristic_value_id,is_representative FROM characteristic_value ORDER BY 1"
        ).fetchall()
        == flags
    )
    chosen = ctx.selection.select_current_value(first.correction_value_id, ctx.actor)
    assert chosen.changed and current_state(ctx) == first.correction_value_id
    chosen_flags = ctx.conn.execute(
        "SELECT characteristic_value_id,is_representative FROM characteristic_value ORDER BY 1"
    ).fetchall()
    ctx.conn.execute("DELETE FROM stream_characteristic")
    inserted = ctx.maintenance.rebuild_current_value_cache(
        ctx.actor, stream_code=STREAM, dictionary_id=ctx.item
    )
    assert inserted.changed_pairs == ((STREAM, ctx.item),)
    ctx.conn.execute("UPDATE stream_characteristic SET characteristic_value_id=?", (original_id,))
    corrected = ctx.maintenance.rebuild_current_value_cache(ctx.actor)
    assert corrected.changed_pairs == ((STREAM, ctx.item),)
    assert current_state(ctx) == first.correction_value_id
    stable = ctx.maintenance.rebuild_current_value_cache(ctx.actor)
    assert not stable.changed_pairs and not stable.history_ids
    assert ctx.conn.execute("SELECT * FROM data_quality_issue").fetchall() == issue_rows
    assert (
        ctx.conn.execute(
            "SELECT characteristic_value_id,is_representative FROM characteristic_value ORDER BY 1"
        ).fetchall()
        == chosen_flags
    )
    with transaction(ctx.conn):
        SmallStreamRepository(ctx.conn).create(
            stream_code="01234567891",
            province_code="01",
            city_county_code="234",
            town_code="567",
            stream_serial_no="891",
            stream_name="Other synthetic",
            created_at=STAMP,
            updated_at=STAMP,
        )
        foreign = ctx.values.create(
            stream_code="01234567891",
            dictionary_id=ctx.item,
            value_number=4.5,
            created_at=STAMP,
            updated_at=STAMP,
        )
    ctx.conn.execute(
        "UPDATE stream_characteristic SET characteristic_value_id=?",
        (foreign.characteristic_value_id,),
    )
    foreign_fixed = ctx.maintenance.rebuild_current_value_cache(ctx.actor)
    assert foreign_fixed.changed_pairs == ((STREAM, ctx.item),)
    assert current_state(ctx) == first.correction_value_id

    source = ctx.values.get_by_id(original_id)
    assert (
        source.value_number,
        source.original_value,
        source.original_unit,
        source.import_id,
        source.import_sheet_id,
        source.mapping_id,
        source.source_row,
        source.reference_year,
    ) == (
        1.5,
        RAW,
        "synthetic raw unit",
        ctx.imp.import_id,
        ctx.sheet.import_sheet_id,
        ctx.mapping.mapping_id,
        5,
        2020,
    )
    provenance = ctx.values.get_provenance(original_id)
    assert provenance.value == source
    assert provenance.mapping == ctx.mapping and provenance.sheet == ctx.sheet
    assert provenance.history == ctx.imp and provenance.source_file == ctx.source
    assert ctx.conn.execute("PRAGMA foreign_key_check").fetchall() == []

    events = history(ctx)
    assert [event[1] for event in events] == [
        "CURRENT_VALUE_CHANGE",
        "CORRECTION",
        "CORRECTION",
        "CURRENT_VALUE_CHANGE",
        "DEACTIVATE",
        "RESTORE",
        "DEACTIVATE",
        "RESTORE",
        "CACHE_REBUILD",
        "CURRENT_VALUE_CHANGE",
        "CACHE_REBUILD",
        "CACHE_REBUILD",
        "CACHE_REBUILD",
    ]
    assert [event[0] for event in events] == sorted(event[0] for event in events)
    assert all(
        event[6] == ctx.actor and datetime.fromisoformat(event[7]).tzinfo for event in events
    )
    assert json.loads(events[1][4]) == {"source_value_id": original_id}
    assert json.loads(events[2][4]) == {"source_value_id": first.correction_value_id}
    assert json.loads(events[3][5])["characteristic_value_id"] == second.correction_value_id
    assert json.loads(events[8][5])["characteristic_value_id"] is None
    assert all(
        event[2] == "stream_characteristic" for event in events if event[1] == "CACHE_REBUILD"
    )
    assert all(RAW not in repr(event) and "source.xlsx" not in repr(event) for event in events)


@pytest.mark.parametrize("severity", ["WARNING", "INFO"])
def test_real_qc_warning_info_requires_confirmation_without_issue_mutation(ctx, severity):
    original_id = ctx.original.characteristic_value_id
    ctx.selection.select_current_value(original_id, ctx.actor)
    created = correction(ctx, original_id, 2.5)
    rid = rule(ctx, severity)
    checked = recheck(ctx, created.correction_value_id, rid)
    assert len(checked.created_issue_ids) == 1
    assert QualityControlRepository(ctx.conn).active_severity_counts(STREAM).status == (
        "NEEDS_REVIEW"
    )
    issue = ctx.conn.execute("SELECT * FROM data_quality_issue").fetchall()
    before = tuple(history(ctx))
    with pytest.raises(CurrentValueConfirmationRequiredError):
        ctx.selection.select_current_value(created.correction_value_id, ctx.actor)
    assert current_state(ctx) == original_id and tuple(history(ctx)) == before
    selected = ctx.selection.select_current_value(
        created.correction_value_id, ctx.actor, confirm_review_required=True
    )
    assert selected.confirmation_required and selected.confirmation_used
    assert selected.qc_status_before_selection == "NEEDS_REVIEW"
    assert current_state(ctx) == created.correction_value_id
    assert ctx.conn.execute("SELECT * FROM data_quality_issue").fetchall() == issue


def test_qc_failure_after_correction_and_unrelated_issues(ctx):
    original_id = ctx.original.characteristic_value_id
    ctx.selection.select_current_value(original_id, ctx.actor)
    created = correction(ctx, original_id, 2.5)
    correction_row = ctx.values.get_by_id(created.correction_value_id)
    history_before = tuple(history(ctx))
    rid = rule(ctx, "ERROR")
    ctx.conn.execute(
        "CREATE TRIGGER fail_qc BEFORE INSERT ON data_quality_issue "
        "BEGIN SELECT RAISE(ABORT,'SYNTHETIC_PRIVATE_SQL'); END"
    )
    with pytest.raises(QualityControlPersistenceError):
        recheck(ctx, created.correction_value_id, rid)
    ctx.conn.execute("DROP TRIGGER fail_qc")
    assert ctx.values.get_by_id(created.correction_value_id) == correction_row
    assert tuple(history(ctx)) == history_before
    assert current_state(ctx) == original_id
    assert ctx.conn.execute("SELECT count(*) FROM data_quality_issue").fetchone()[0] == 0

    # 다른 값의 ERROR와 값 ID가 NULL인 issue는 대상 값 QC Gate에 포함되지 않는다.
    recheck(ctx, original_id, rid)
    ctx.conn.execute(
        "INSERT INTO data_quality_issue (characteristic_value_id,stream_code,issue_type,"
        "severity,message,created_at) VALUES (NULL,?,?,?,?,?)",
        (STREAM, "SYNTHETIC_NULL", "ERROR", "Synthetic", STAMP),
    )
    ctx.conn.execute(
        "UPDATE quality_rule SET parameters_json=? WHERE rule_id=?",
        (json.dumps({"min": 2}), rid),
    )
    # correction은 검사 완료로 가정하지 않는다. 선택은 현재 활성 issue만 재조회한다.
    assert ctx.selection.select_current_value(created.correction_value_id, ctx.actor).changed
    assert current_state(ctx) == created.correction_value_id
    counts = QualityControlRepository(ctx.conn).active_severity_counts(STREAM)
    assert counts.status == "ERROR"
    assert ctx.conn.execute("SELECT count(*) FROM data_quality_issue").fetchone()[0] == 2


def test_cache_rebuild_failure_keeps_correction_and_current_selection(ctx):
    original_id = ctx.original.characteristic_value_id
    ctx.selection.select_current_value(original_id, ctx.actor)
    created = correction(ctx, original_id, 4.5)
    ctx.selection.select_current_value(created.correction_value_id, ctx.actor)
    ctx.conn.execute("DELETE FROM stream_characteristic")
    before = tuple(history(ctx))
    rows = ctx.conn.execute("SELECT * FROM characteristic_value ORDER BY 1").fetchall()
    ctx.conn.execute(
        "CREATE TRIGGER fail_cache BEFORE INSERT ON stream_characteristic "
        "BEGIN SELECT RAISE(ABORT,'SYNTHETIC_PRIVATE_SQL'); END"
    )
    with pytest.raises(MaintenancePersistenceError):
        ctx.maintenance.rebuild_current_value_cache(ctx.actor)
    assert tuple(history(ctx)) == before
    assert ctx.conn.execute("SELECT * FROM characteristic_value ORDER BY 1").fetchall() == rows
    assert ctx.values.get_by_id(created.correction_value_id) is not None
    assert ctx.conn.execute("SELECT count(*) FROM stream_characteristic").fetchone()[0] == 0


def test_current_deactivation_failure_rolls_back_and_historical_flag_is_excluded(ctx):
    original_id = ctx.original.characteristic_value_id
    ctx.selection.select_current_value(original_id, ctx.actor)
    before_value = ctx.values.get_by_id(original_id)
    before_cache = ctx.conn.execute("SELECT * FROM stream_characteristic").fetchall()
    before_history = tuple(history(ctx))
    ctx.conn.execute(
        "CREATE TRIGGER fail_deactivate BEFORE INSERT ON record_history "
        "WHEN NEW.change_type='DEACTIVATE' "
        "BEGIN SELECT RAISE(ABORT,'SYNTHETIC_PRIVATE_SQL'); END"
    )
    with pytest.raises(MaintenancePersistenceError):
        ctx.maintenance.deactivate_value(
            original_id, ctx.actor, confirm_current_use_loss=True, reason_code=REASON
        )
    assert ctx.values.get_by_id(original_id) == before_value
    assert ctx.conn.execute("SELECT * FROM stream_characteristic").fetchall() == before_cache
    assert tuple(history(ctx)) == before_history and current_state(ctx) == original_id
    ctx.conn.execute("DROP TRIGGER fail_deactivate")

    ctx.maintenance.deactivate_value(
        original_id, ctx.actor, confirm_current_use_loss=True, reason_code=REASON
    )
    # 이전 버전에서 남을 수 있는 비활성 과거 대표 flag는 캐시의 source가 아니다.
    ctx.conn.execute(
        "UPDATE characteristic_value SET is_representative=1 "
        "WHERE characteristic_value_id=? AND is_active=0",
        (original_id,),
    )
    ctx.conn.execute(
        "INSERT INTO stream_characteristic VALUES (?,?,?,?)",
        (STREAM, ctx.item, original_id, STAMP),
    )
    rebuilt = ctx.maintenance.rebuild_current_value_cache(ctx.actor)
    assert rebuilt.changed_pairs == ((STREAM, ctx.item),)
    assert current_state(ctx) is None
    assert ctx.values.get_by_id(original_id).is_representative
