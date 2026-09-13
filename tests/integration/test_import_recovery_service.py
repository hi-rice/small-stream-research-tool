"""실제 6B-2 T1과 합성 SQLite 불일치로 보수적 복구/멱등성을 검증한다."""

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
from small_stream_research_tool.models.column_mapping import (
    ColumnMappingDraft,
    MappingMethod,
    MappingStatus,
)
from small_stream_research_tool.models.import_execution import (
    ImportExecutionRequest,
    ImportSheetSnapshot,
    SourceFileSnapshot,
)
from small_stream_research_tool.models.import_execution_errors import ImportFinalizeError
from small_stream_research_tool.models.import_preparation import (
    ImportFieldPolicy,
    ImportPreparationResult,
    ImportPreparationSummary,
    PreparationStatus,
    PreparedCharacteristicValue,
    PreparedImportRow,
    PreparedStreamData,
    RowAction,
)
from small_stream_research_tool.models.import_preview import PreviewStatus
from small_stream_research_tool.models.import_recovery import RecoveryState
from small_stream_research_tool.models.import_recovery_errors import (
    ImportRecoveryConsistencyError,
    ImportRecoveryError,
    ImportRecoveryStateError,
)
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.dictionary_service import DictionaryService
from small_stream_research_tool.services.import_execution_service import ImportExecutionService
from small_stream_research_tool.services.import_recovery_service import ImportRecoveryService

STAMP = "2026-09-13T01:02:03Z"
SECRET = "SYNTHETIC_PRIVATE_RECOVERY_VALUE"
PATH = "C:/synthetic-only/private-source.xlsx"
POLICY = ImportFieldPolicy(frozenset({"synthetic_secret"}))


def fail(*_args, **_kwargs):
    raise sqlite3.OperationalError(SECRET + PATH)


@pytest.fixture
def ctx(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    with closing(connect_database(path)) as conn:
        dictionary = DictionaryService(DictionaryRepository(conn))
        category = dictionary.create_category("synthetic", "Synthetic")
        version = dictionary.create_version("synthetic-v1")
        item = dictionary.create_item(
            "Synthetic Metric", "synthetic_metric", category.category_id, "TEXT", version.version_id
        )
        with transaction(conn):
            user = UserRepository(conn).create_user(
                login_id="synthetic_user",
                password_hash="SYNTHETIC_TEST_HASH",
                display_name="Synthetic User",
                department=None,
                role=None,
                timestamp=STAMP,
            )
        core = PreparedStreamData("12345678009", "12", "345", "678", "009", "Synthetic Stream")
        value = PreparedCharacteristicValue(
            item.dictionary_id, "TEXT", 4, 3, value_text=SECRET, original_value=SECRET
        )
        row = PreparedImportRow(
            3,
            core.stream_code,
            core.stream_name,
            RowAction.CREATE_STREAM,
            PreparationStatus.READY,
            (value,),
            (),
            PreviewStatus.NEW_STREAM,
            core,
        )
        preparation = ImportPreparationResult((row,), ImportPreparationSummary(1, 1, 0, 0, 1, 0, 1))
        mapping = ColumnMappingDraft(
            4,
            "D",
            "Synthetic",
            (),
            item.dictionary_id,
            MappingMethod.USER,
            MappingStatus.USER_MAPPED,
        )
        request = ImportExecutionRequest(
            SourceFileSnapshot("synthetic.xlsx", PATH),
            ImportSheetSnapshot("Synthetic", 1, 2, 3, 1),
            preparation,
            (mapping,),
            user.user_id,
            version.version_id,
            "synthetic-t1",
        )
        execution = ImportExecutionService(conn)
        yield SimpleNamespace(
            conn=conn,
            path=path,
            execution=execution,
            request=request,
            service=ImportRecoveryService(conn),
        )


def t1(ctx, *, no_data=False, request=None):
    original_finalize = ctx.execution._finalize
    original_value = ctx.execution._values.create_prepared
    ctx.execution._finalize = fail
    if no_data:
        ctx.execution._values.create_prepared = fail
    try:
        with pytest.raises(ImportFinalizeError) as error:
            ctx.execution.execute(request or ctx.request, field_policy=POLICY)
        return error.value.result.import_id
    finally:
        ctx.execution._finalize = original_finalize
        ctx.execution._values.create_prepared = original_value


def dump(ctx):
    return tuple(ctx.conn.iterdump())


def artifacts(ctx):
    names = [
        r[0]
        for r in ctx.conn.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    return {
        name: ctx.conn.execute(f"SELECT * FROM {name}").fetchall()
        for name in names
        if name != "import_history"
    }


def test_t1_inspection_explicit_recovery_and_idempotency(ctx):
    import_id = t1(ctx)
    before = dump(ctx)
    inspection = ctx.service.inspect(import_id)
    assert inspection.recovery_state == RecoveryState.COMMITTED_CONSISTENT
    assert inspection.can_finalize_success and not inspection.can_retry
    assert (
        inspection.sheet_count,
        inspection.mapping_count,
        inspection.characteristic_value_count,
    ) == (1, 1, 1)
    assert inspection.expected_total_rows == inspection.accepted_rows == 1
    assert inspection.expected_mapping_count is None
    assert inspection.expected_characteristic_value_count is None
    assert dump(ctx) == before
    data = artifacts(ctx)
    result = ctx.service.recover_success(import_id)
    assert result.changed and result.previous_status == "RUNNING" and result.new_status == "SUCCESS"
    assert result.finalized_at.endswith("Z")
    history = ctx.execution._histories.get_by_id(import_id)
    assert (
        history.total_rows,
        history.accepted_rows,
        history.warning_rows,
        history.rejected_rows,
    ) == (1, 1, None, 0)
    assert history.finished_at == result.finalized_at
    assert artifacts(ctx) == data
    final = dump(ctx)
    second = ctx.service.recover_success(import_id)
    assert not second.changed and second.finalized_at == result.finalized_at
    assert second.recovery_state == RecoveryState.ALREADY_FINALIZED
    assert dump(ctx) == final
    with pytest.raises(FrozenInstanceError):
        inspection.can_retry = True
    with pytest.raises(FrozenInstanceError):
        result.changed = False


@pytest.mark.parametrize("status", ["SUCCESS", "FAILED", "CANCELLED", "ROLLED_BACK", "PENDING"])
def test_nonrunning_status_never_changed(ctx, status):
    import_id = t1(ctx)
    ctx.conn.execute("UPDATE import_history SET status=?", (status,))
    before = dump(ctx)
    inspection = ctx.service.inspect(import_id)
    expected = (
        RecoveryState.NOT_RECOVERABLE if status == "PENDING" else RecoveryState.ALREADY_FINALIZED
    )
    assert inspection.recovery_state == expected
    assert not inspection.can_retry and not inspection.can_finalize_success
    if status == "SUCCESS":
        assert not ctx.service.recover_success(import_id).changed
    else:
        with pytest.raises(ImportRecoveryStateError):
            ctx.service.recover_success(import_id)
    assert dump(ctx) == before


def test_no_data_is_candidate_only(ctx):
    import_id = t1(ctx, no_data=True)
    before = dump(ctx)
    inspection = ctx.service.inspect(import_id)
    assert inspection.recovery_state == RecoveryState.NO_PERSISTED_DATA
    assert inspection.can_retry and not inspection.can_finalize_success
    assert (
        inspection.sheet_count,
        inspection.mapping_count,
        inspection.characteristic_value_count,
    ) == (0, 0, 0)
    with pytest.raises(ImportRecoveryConsistencyError):
        ctx.service.recover_success(import_id)
    assert dump(ctx) == before
    assert ctx.execution._histories.get_by_id(import_id).status == "RUNNING"


@pytest.mark.parametrize("has_mapping", [False, True])
def test_core_only_import_is_committed_even_without_values(ctx, has_mapping):
    row = replace(ctx.request.preparation.rows[0], prepared_values=())
    req = replace(
        ctx.request,
        preparation=replace(ctx.request.preparation, rows=(row,)),
        column_mappings=ctx.request.column_mappings if has_mapping else (),
    )
    import_id = t1(ctx, request=req)
    inspection = ctx.service.inspect(import_id)
    assert inspection.characteristic_value_count == 0
    assert inspection.recovery_state == RecoveryState.COMMITTED_CONSISTENT
    assert ctx.service.recover_success(import_id).changed


def test_existing_only_does_not_require_new_stream(ctx):
    original = ctx.request.preparation.rows[0]
    with transaction(ctx.conn):
        ctx.execution._streams.create_prepared(original.core_data, timestamp=STAMP)
    row = replace(
        original,
        row_action=RowAction.USE_EXISTING_STREAM,
        core_data=None,
        preview_status=PreviewStatus.EXISTING_STREAM,
    )
    req = replace(ctx.request, preparation=replace(ctx.request.preparation, rows=(row,)))
    import_id = t1(ctx, request=req)
    assert ctx.service.inspect(import_id).can_finalize_success


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE import_sheet SET accepted_rows=2",
        "UPDATE import_sheet SET total_rows=2",
        "UPDATE import_history SET total_rows=2",
        "UPDATE import_history SET accepted_rows=2",
        "UPDATE import_sheet SET rejected_rows=1",
        "UPDATE import_sheet SET warning_rows=1",
        "UPDATE import_history SET warning_rows=1",
        "UPDATE import_sheet SET accepted_rows=NULL",
        "UPDATE import_sheet SET accepted_rows=-1",
        "UPDATE import_sheet SET status='RUNNING'",
        "UPDATE import_sheet SET header_start_row=2",
        "UPDATE import_sheet SET sheet_name='Synthetic Changed'",
        "UPDATE import_sheet SET sheet_index=0",
        "UPDATE import_history SET finished_at='2026-01-01T00:00:00Z'",
        "UPDATE import_history SET error_code='SYNTHETIC_ERROR'",
        "UPDATE import_column_mapping SET source_column_index=0",
        "UPDATE import_column_mapping SET mapping_method='UNKNOWN'",
        "UPDATE import_column_mapping SET user_confirmed=0",
        "UPDATE import_column_mapping SET dictionary_id=NULL",
        "UPDATE characteristic_value SET source_row=0",
        "UPDATE characteristic_value SET import_sheet_id=NULL",
        "UPDATE characteristic_value SET source_type='MANUAL'",
    ],
)
def test_inconsistent_artifacts_refuse_finalization(ctx, sql):
    import_id = t1(ctx)
    ctx.conn.execute(sql)
    before = dump(ctx)
    inspection = ctx.service.inspect(import_id)
    assert inspection.recovery_state == RecoveryState.INCONSISTENT
    assert not inspection.can_retry and not inspection.can_finalize_success
    with pytest.raises(ImportRecoveryConsistencyError):
        ctx.service.recover_success(import_id)
    assert dump(ctx) == before


@pytest.mark.parametrize(
    "settings",
    [None, "{}", "[]", "not-json", '{"sheet_name":1}', '{"sheet_name":"A","sheet_name":"B"}'],
)
def test_missing_contract_not_guessed(ctx, settings):
    import_id = t1(ctx)
    ctx.conn.execute("UPDATE import_history SET settings_json=?", (settings,))
    assert ctx.service.inspect(import_id).recovery_state == RecoveryState.NOT_RECOVERABLE
    with pytest.raises(ImportRecoveryConsistencyError):
        ctx.service.recover_success(import_id)


def test_nullable_mapping_is_insufficient_not_assumed_corruption(ctx):
    import_id = t1(ctx)
    ctx.conn.execute("UPDATE characteristic_value SET mapping_id=NULL")
    inspection = ctx.service.inspect(import_id)
    assert inspection.recovery_state == RecoveryState.NOT_RECOVERABLE
    assert inspection.reason_code == "MAPPING_PROVENANCE_UNAVAILABLE"
    with pytest.raises(ImportRecoveryConsistencyError):
        ctx.service.recover_success(import_id)


def second_import(ctx):
    row = replace(
        ctx.request.preparation.rows[0],
        row_action=RowAction.USE_EXISTING_STREAM,
        core_data=None,
        preview_status=PreviewStatus.EXISTING_STREAM,
    )
    req = replace(
        ctx.request,
        batch_code="synthetic-second",
        preparation=replace(ctx.request.preparation, rows=(row,)),
    )
    return t1(ctx, request=req)


@pytest.mark.parametrize("column", ["import_id", "import_sheet_id", "mapping_id"])
def test_cross_import_links_detected_in_both_directions(ctx, column):
    first = t1(ctx)
    second = second_import(ctx)
    a = ctx.execution._values.list_by_import_id(first)[0]
    b = ctx.execution._values.list_by_import_id(second)[0]
    ctx.conn.execute(
        f"UPDATE characteristic_value SET {column}=? WHERE characteristic_value_id=?",
        (getattr(b, column), a.characteristic_value_id),
    )
    for import_id in (first, second):
        assert ctx.service.inspect(import_id).recovery_state == RecoveryState.INCONSISTENT
        with pytest.raises(ImportRecoveryConsistencyError):
            ctx.service.recover_success(import_id)


def test_value_without_sheet_detected(ctx):
    first = t1(ctx)
    no_data = t1(ctx, no_data=True, request=replace(ctx.request, batch_code="synthetic-no-data"))
    ctx.conn.execute(
        "UPDATE characteristic_value SET import_id=?,import_sheet_id=NULL,mapping_id=NULL "
        "WHERE import_id=?",
        (no_data, first),
    )
    inspection = ctx.service.inspect(no_data)
    assert inspection.reason_code == "MISSING_IMPORT_SHEET"
    assert inspection.recovery_state == RecoveryState.INCONSISTENT


def test_extra_sheet_rejected(ctx):
    import_id = t1(ctx)
    with transaction(ctx.conn):
        ctx.execution._sheets.create(
            import_id=import_id, sheet_name="Synthetic Extra", status="SUCCESS", created_at=STAMP
        )
    assert ctx.service.inspect(import_id).reason_code == "SHEET_COUNT_MISMATCH"


def test_duplicate_value_provenance_rejected(ctx):
    import_id = t1(ctx)
    value = ctx.execution._values.list_by_import_id(import_id)[0]
    with transaction(ctx.conn):
        ctx.execution._values.create(
            stream_code=value.stream_code,
            dictionary_id=value.dictionary_id,
            value_text="Synthetic Extra",
            import_id=import_id,
            import_sheet_id=value.import_sheet_id,
            mapping_id=value.mapping_id,
            source_row=value.source_row,
            created_at=STAMP,
            updated_at=STAMP,
        )
    assert ctx.service.inspect(import_id).reason_code == "DUPLICATE_VALUE_PROVENANCE"


def test_distinct_value_rows_exceed_accepted_rejected(ctx):
    import_id = t1(ctx)
    value = ctx.execution._values.list_by_import_id(import_id)[0]
    with transaction(ctx.conn):
        ctx.execution._values.create(
            stream_code=value.stream_code,
            dictionary_id=value.dictionary_id,
            value_text="Synthetic Extra",
            import_id=import_id,
            import_sheet_id=value.import_sheet_id,
            mapping_id=value.mapping_id,
            source_row=4,
            created_at=STAMP,
            updated_at=STAMP,
        )
    assert ctx.service.inspect(import_id).reason_code == "ROW_COUNT_MISMATCH"


def test_inspect_then_other_finalizer_success_is_noop(ctx):
    import_id = t1(ctx)
    assert ctx.service.inspect(import_id).can_finalize_success
    with closing(connect_database(ctx.path)) as other:
        ImportRecoveryService(other).recover_success(import_id)
    before = dump(ctx)
    assert not ctx.service.recover_success(import_id).changed
    assert dump(ctx) == before


def test_inspect_then_metadata_changes_rechecked(ctx):
    import_id = t1(ctx)
    assert ctx.service.inspect(import_id).can_finalize_success
    ctx.conn.execute("UPDATE import_sheet SET total_rows=2")
    before = dump(ctx)
    with pytest.raises(ImportRecoveryConsistencyError):
        ctx.service.recover_success(import_id)
    assert dump(ctx) == before


def test_concurrent_finalization_changes_once(ctx):
    import_id = t1(ctx)
    before = artifacts(ctx)
    barrier = Barrier(2)

    def recover():
        with closing(connect_database(ctx.path)) as connection:
            barrier.wait(timeout=5)
            return ImportRecoveryService(connection).recover_success(import_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(recover) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert sorted(r.changed for r in results) == [False, True]
    assert results[0].finalized_at == results[1].finalized_at
    assert artifacts(ctx) == before


def test_recovery_failure_rolls_back_and_sanitizes_error(ctx, monkeypatch, caplog):
    import_id = t1(ctx)
    before = dump(ctx)
    original = ctx.service._histories.update_status

    def update(*args, **kwargs):
        original(*args, **kwargs)
        fail()

    monkeypatch.setattr(ctx.service._histories, "update_status", update)
    with pytest.raises(ImportRecoveryError) as error:
        ctx.service.recover_success(import_id)
    assert dump(ctx) == before
    output = "".join(traceback.format_exception(error.value)) + caplog.text
    assert SECRET not in output and PATH not in output


def test_inspection_database_error_is_safe(ctx, monkeypatch):
    import_id = t1(ctx)
    monkeypatch.setattr(ctx.service._histories, "get_by_id", fail)
    with pytest.raises(ImportRecoveryError) as error:
        ctx.service.inspect(import_id)
    output = "".join(traceback.format_exception(error.value))
    assert SECRET not in output and PATH not in output


def test_inspection_query_only_and_no_raw_value_reads(ctx):
    import_id = t1(ctx)
    before = dump(ctx)
    ctx.conn.execute("PRAGMA query_only=ON")
    denied = {
        "original_value",
        "value_number",
        "value_integer",
        "value_text",
        "value_date",
        "original_path",
        "source_header",
        "password_hash",
    }

    def authorize(action, _table, column, _db, _trigger):
        if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and column in denied:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorize)
    try:
        result = ctx.service.inspect(import_id)
        assert result.can_finalize_success
    finally:
        ctx.conn.set_authorizer(None)
        ctx.conn.execute("PRAGMA query_only=OFF")
    assert dump(ctx) == before
    assert SECRET not in repr(result) and PATH not in repr(result)


def test_only_import_history_update_is_permitted(ctx):
    import_id = t1(ctx)
    writes = []

    def authorize(action, table, _column, _db, _trigger):
        if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
            writes.append((action, table))
            if action != sqlite3.SQLITE_UPDATE or table != "import_history":
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorize)
    try:
        result = ctx.service.recover_success(import_id)
    finally:
        ctx.conn.set_authorizer(None)
    assert result.changed and writes
    assert all(
        action == sqlite3.SQLITE_UPDATE and name == "import_history" for action, name in writes
    )


def test_running_candidates_no_time_assumption(ctx):
    first = t1(ctx)
    second = second_import(ctx)
    ctx.service.recover_success(second)
    before = dump(ctx)
    candidates = ctx.service.list_recovery_candidates()
    assert [c.import_id for c in candidates] == [first]
    assert dump(ctx) == before


@pytest.mark.parametrize("import_id", [None, 0, -1, True, "1", 99999])
def test_invalid_or_missing_id(ctx, import_id):
    with pytest.raises(ImportRecoveryStateError):
        ctx.service.inspect(import_id)
    with pytest.raises(ImportRecoveryStateError):
        ctx.service.recover_success(import_id)


def test_caller_transaction_not_consumed(ctx):
    import_id = t1(ctx)
    with transaction(ctx.conn):
        with pytest.raises(ImportRecoveryError):
            ctx.service.inspect(import_id)
        assert ctx.conn.in_transaction
        with pytest.raises(ImportRecoveryError):
            ctx.service.recover_success(import_id)
        assert ctx.conn.in_transaction


def test_recovery_commit_failure_rolls_back(ctx):
    import_id = t1(ctx)
    before = dump(ctx)

    def authorize(action, arg1, _arg2, _db, _trigger):
        if action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    ctx.conn.set_authorizer(authorize)
    try:
        with pytest.raises(ImportRecoveryError):
            ctx.service.recover_success(import_id)
    finally:
        ctx.conn.set_authorizer(None)
    assert dump(ctx) == before and not ctx.conn.in_transaction


def test_representative_and_cache_remain_untouched(ctx):
    import_id = t1(ctx)
    value = ctx.execution._values.list_by_import_id(import_id)[0]
    ctx.conn.execute("UPDATE characteristic_value SET is_representative=1")
    ctx.conn.execute(
        "INSERT INTO stream_characteristic VALUES (?, ?, ?, ?)",
        (value.stream_code, value.dictionary_id, value.characteristic_value_id, STAMP),
    )
    before = artifacts(ctx)
    assert ctx.service.recover_success(import_id).changed
    assert artifacts(ctx) == before


def test_inspection_uses_one_read_snapshot(ctx, monkeypatch):
    ctx.conn.execute("PRAGMA journal_mode=WAL")
    import_id = t1(ctx)
    original = ctx.service._sheets.list_by_import_id

    def read(import_id):
        with closing(connect_database(ctx.path)) as other:
            other.execute("UPDATE import_sheet SET total_rows=2")
        return original(import_id)

    monkeypatch.setattr(ctx.service._sheets, "list_by_import_id", read)
    assert ctx.service.inspect(import_id).can_finalize_success  # 기존 snapshot
    monkeypatch.setattr(ctx.service._sheets, "list_by_import_id", original)
    with pytest.raises(ImportRecoveryConsistencyError):
        ctx.service.recover_success(import_id)  # 새 transaction에서는 변경을 확인


def test_duplicate_mapping_evidence_is_rejected(ctx, monkeypatch):
    import_id = t1(ctx)
    original = ctx.service._mappings.list_recovery_evidence

    def duplicated(import_id):
        records = original(import_id)
        return records + records

    monkeypatch.setattr(ctx.service._mappings, "list_recovery_evidence", duplicated)
    assert ctx.service.inspect(import_id).reason_code == "MAPPING_PROVENANCE_MISMATCH"


@pytest.mark.parametrize("column", ["accepted_rows", "warning_rows", "rejected_rows"])
def test_no_data_conflicting_counts_not_retryable(ctx, column):
    import_id = t1(ctx, no_data=True)
    ctx.conn.execute(f"UPDATE import_history SET {column}=1")
    inspection = ctx.service.inspect(import_id)
    assert inspection.recovery_state == RecoveryState.INCONSISTENT and not inspection.can_retry


def test_settings_private_payload_not_exposed(ctx):
    import_id = t1(ctx)
    payload = '{"private":"' + SECRET + PATH + '"}'
    ctx.conn.execute("UPDATE import_history SET settings_json=?", (payload,))
    result = ctx.service.inspect(import_id)
    assert result.recovery_state == RecoveryState.NOT_RECOVERABLE
    assert SECRET not in repr(result) and PATH not in repr(result)
    with pytest.raises(ImportRecoveryConsistencyError) as error:
        ctx.service.recover_success(import_id)
    assert SECRET not in str(error.value) and PATH not in str(error.value)
