"""Phase 10D execution orchestration and GUI-safe history integration."""

import os
import time
from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from tests.integration.test_phase_10c_import_mapping import _source, _workbook

from small_stream_research_tool.app.controller import ApplicationController
from small_stream_research_tool.database import connect_database, initialize_database
from small_stream_research_tool.models.import_execution import ImportExecutionResult
from small_stream_research_tool.models.import_execution_errors import ImportFinalizeError
from small_stream_research_tool.models.import_execution_workflow import (
    DuplicateImportConfirmationRequired,
    ImportExecutionWorkflowError,
)
from small_stream_research_tool.models.phase10_read import PageRequest
from small_stream_research_tool.models.workspace import WorkspaceStep
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.auth_service import AuthService
from small_stream_research_tool.services.import_execution_service import ImportExecutionService
from small_stream_research_tool.services.import_execution_workflow_service import (
    ImportExecutionWorkflowService,
)
from small_stream_research_tool.services.import_mapping_workflow_service import (
    ImportMappingWorkflowService,
)
from small_stream_research_tool.services.phase10_read_service import Phase10ReadService
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
)
from small_stream_research_tool.services.research_unit_evidence_service import (
    ResearchUnitEvidenceService,
)
from small_stream_research_tool.services.workspace_service import WorkspaceService
from small_stream_research_tool.ui.import_execution import ImportExecutionView
from small_stream_research_tool.ui.main_window import MainWindow


def _wait(app, condition, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return
        time.sleep(0.02)
    pytest.fail("합성 Phase 10D GUI 작업이 끝나지 않았습니다.")


def _ready(tmp_path, *, v2=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "research.sqlite3"
    workbook = tmp_path / "synthetic.xlsx"
    workspace = tmp_path / "workspace"
    initialize_database(db)
    with closing(connect_database(db)) as connection:
        bootstrap = ResearchDictionaryBootstrapService(connection)
        bootstrap.bootstrap_v2() if v2 else bootstrap.bootstrap()
        user = AuthService(UserRepository(connection)).create_user(
            "phase10d_actor", "synthetic-password", "합성 작업자", "합성 부서", "연구원"
        )
    _workbook(workbook)
    source = _source(workbook, db, workspace)
    mapping = ImportMappingWorkflowService(db, workspace)
    state = mapping.set_scope(mapping.start(source, user.user_id), "NATIONAL_2024", user.user_id)
    unknown = next(row for row in state.rows if row.target == "—" and not row.sensitive)
    state = mapping.update(state, unknown.index, "exclude", None, user.user_id)
    if v2:
        basin = next(row for row in state.rows if row.target == "유역면적")
        unit = next(option.unit_id for option in state.unit_options if option.symbol == "km²")
        state = mapping.confirm_unit(state, basin.index, unit, user.user_id)
    state = mapping.preview(state, user.user_id)
    assert state.preview.ready_for_import_preparation
    return db, workbook, workspace, user, state


def test_v2_ready_executes_once_and_preserves_import_invariants(tmp_path):
    db, _workbook_path, workspace, user, state = _ready(tmp_path)
    workflow = ImportExecutionWorkflowService(db, workspace)
    plan = workflow.prepare(state, user.user_id)
    assert plan.summary.ready_rows == 1
    assert not plan.summary.duplicate_success
    outcome = workflow.execute(plan.workflow_state, user.user_id, False, True)
    assert outcome.status == "SUCCESS"
    assert outcome.created_stream_count == 1
    assert outcome.characteristic_value_count == 1
    with closing(connect_database(db)) as connection:
        assert connection.execute("SELECT status FROM import_history").fetchall() == [("SUCCESS",)]
        assert connection.execute("SELECT stream_code FROM small_stream").fetchall() == [
            ("01234567001",)
        ]
        value = connection.execute(
            "SELECT v.original_unit,u.unit_symbol,v.is_representative "
            "FROM characteristic_value v JOIN unit_dictionary u ON u.unit_id=v.unit_id"
        ).fetchone()
        assert value == ("km²", "km²", 0)
        assert connection.execute("SELECT count(*) FROM data_quality_issue").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM stream_characteristic").fetchone() == (0,)
    assert (
        WorkspaceService(workspace).load_workspace(user.user_id).current_step
        == WorkspaceStep.COMPLETED
    )


def test_v1_source_change_and_duplicate_confirmation_are_blocking(tmp_path):
    v1_db, _path, v1_workspace, user, state = _ready(tmp_path / "v1", v2=False)
    with pytest.raises(ImportExecutionWorkflowError, match="연구 사전"):
        ImportExecutionWorkflowService(v1_db, v1_workspace).prepare(state, user.user_id)

    db, workbook, workspace, user, state = _ready(tmp_path / "v2")
    workflow = ImportExecutionWorkflowService(db, workspace)
    outcome = workflow.execute(state, user.user_id, False, True)
    assert outcome.status == "SUCCESS"
    state = ImportMappingWorkflowService(db, workspace).resume(user.user_id)
    state = ImportMappingWorkflowService(db, workspace).preview(state, user.user_id)
    with pytest.raises(DuplicateImportConfirmationRequired):
        workflow.execute(state, user.user_id, False, True)
    workbook.write_bytes(workbook.read_bytes() + b"changed")
    with pytest.raises(ImportExecutionWorkflowError, match="원본 파일"):
        workflow.prepare(state, user.user_id)


def test_execution_rechecks_evidence_fingerprint_immediately(tmp_path, monkeypatch):
    db, workbook, workspace, user, state = _ready(tmp_path)
    workflow = ImportExecutionWorkflowService(db, workspace)
    plan = workflow.prepare(state, user.user_id)
    original = ResearchUnitEvidenceService.load

    def changed(service):
        evidence = original(service)
        return replace(evidence, fingerprint="0" * 64)

    monkeypatch.setattr(ResearchUnitEvidenceService, "load", changed)
    with closing(connect_database(db)) as connection:
        with pytest.raises(ImportExecutionWorkflowError, match="단위 근거"):
            workflow._verify_execution_prerequisites(connection, plan, workbook)


@pytest.mark.parametrize("data_committed", (False, True))
def test_finalize_failure_message_matches_data_commit_state(tmp_path, monkeypatch, data_committed):
    db, _workbook_path, workspace, user, state = _ready(tmp_path)
    result = ImportExecutionResult(
        1,
        1,
        "synthetic-batch",
        "RUNNING",
        data_committed,
        1,
        0,
        1 if data_committed else 0,
        0,
        1 if data_committed else 0,
        "2026-01-01T00:00:00Z",
        None,
    )

    def fail_finalize(*args, **kwargs):
        raise ImportFinalizeError(result)

    monkeypatch.setattr(ImportExecutionService, "execute", fail_finalize)
    outcome = ImportExecutionWorkflowService(db, workspace).execute(
        state, user.user_id, False, True
    )
    assert outcome.status == "RECOVERY_REQUIRED"
    assert outcome.recovery_required
    assert ("저장은 완료" in outcome.message) is data_committed
    assert ("저장되지 않았" in outcome.message) is (not data_committed)


def test_recovery_completes_only_matching_workspace(tmp_path, monkeypatch):
    db, _workbook_path, workspace, user, state = _ready(tmp_path)

    def fail_finalize(*args, **kwargs):
        raise RuntimeError("synthetic finalize failure")

    monkeypatch.setattr(ImportExecutionService, "_finalize", fail_finalize)
    workflow = ImportExecutionWorkflowService(db, workspace)
    outcome = workflow.execute(state, user.user_id, False, True)
    assert outcome.status == "RECOVERY_REQUIRED"
    assert (
        WorkspaceService(workspace).load_workspace(user.user_id).current_step
        == WorkspaceStep.PREVIEW
    )

    assert "SUCCESS" in workflow.recover(1, 25, 0, user.user_id)
    assert (
        WorkspaceService(workspace).load_workspace(user.user_id).current_step
        == WorkspaceStep.COMPLETED
    )


def test_import_history_is_database_paginated_and_safe(tmp_path):
    db, _path, workspace, user, state = _ready(tmp_path)
    ImportExecutionWorkflowService(db, workspace).execute(state, user.user_id, False, True)
    with closing(connect_database(db)) as connection:
        page = Phase10ReadService(connection).list_import_history(PageRequest(1, 1))
    assert page.total_count == page.total_pages == 1
    assert page.items[0].status == "SUCCESS"
    assert page.items[0].file_name == "synthetic.xlsx"
    text = repr(page)
    assert str(tmp_path) not in text
    assert "01234567001" not in text


def test_execution_view_prevents_double_submission_and_emits_mutation_guard(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    _db, _path, workspace, user, state = _ready(tmp_path)
    plan = ImportExecutionWorkflowService(_db, workspace).prepare(state, user.user_id)

    class PendingPool:
        def __init__(self):
            self.tasks = []

        def start(self, task):
            self.tasks.append(task)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    view = ImportExecutionView(_db, user.user_id, workspace)
    pool = PendingPool()
    view.pool = pool
    states = []
    view.mutation_state_changed.connect(states.append)
    view.state = plan.workflow_state
    view.plan = plan
    view.execute_import()
    view.execute_import()
    app.processEvents()
    assert len(pool.tasks) == 1
    assert view.mutation_active
    assert states == [True]
    assert not view.execute_button.isEnabled()
    view._mutating = False
    view.close()


def test_main_window_disables_logout_and_rejects_close_during_mutation(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    db = tmp_path / "guard.sqlite3"
    initialize_database(db)
    session = SimpleNamespace(user_id=1, display_name="합성 사용자", department=None)
    window = MainWindow(db, session, tmp_path / "workspace")
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    window._mutation_state(True)
    assert not window.logout_button.isEnabled()
    event = QCloseEvent()
    window.closeEvent(event)
    app.processEvents()
    assert not event.isAccepted()
    window._mutation_state(False)
    window.close()


def test_synthetic_gui_flow_reaches_success_and_import_history(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    db = tmp_path / "gui.sqlite3"
    workspace = tmp_path / "workspace"
    workbook = tmp_path / "synthetic.xlsx"
    initialize_database(db)
    _workbook(workbook)
    controller = ApplicationController(db, workspace)
    try:
        with closing(connect_database(db)) as connection:
            ResearchDictionaryBootstrapService(connection).bootstrap_v2()
        controller.auth_service.create_user(
            "phase10d_gui", "synthetic-password", "합성 사용자", "합성 부서", "연구원"
        )
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        controller.start()
        controller.login_window.login_id.setText("phase10d_gui")
        controller.login_window.password.setText("synthetic-password")
        controller.login_window.submit.click()
        _wait(app, lambda: controller.main_window is not None)
        window = controller.main_window
        window.navigate("Excel 가져오기")
        structure = window.import_workspace
        structure.select_file(str(workbook))
        _wait(app, lambda: structure.state is not None)
        structure.sheets.selectRow(0)
        structure.structure_button.click()
        _wait(app, lambda: bool(structure.state and structure.state.columns))
        structure.save_button.click()
        _wait(app, lambda: structure.next_button.isEnabled())
        structure.next_button.click()
        mapping = window.import_mapping
        _wait(app, lambda: mapping.state is not None)
        mapping.scope.setCurrentIndex(1)
        mapping.scope_button.click()
        _wait(app, lambda: mapping.state.source_scope == "NATIONAL_2024")
        unknown_index = next(
            index
            for index, row in enumerate(mapping.state.rows)
            if row.target == "—" and not row.sensitive
        )
        mapping.mapping_table.selectRow(unknown_index)
        mapping.exclude_button.click()
        _wait(app, lambda: mapping.state.rows[unknown_index].status == "가져오지 않음")
        basin_index = next(
            index for index, row in enumerate(mapping.state.rows) if row.target == "유역면적"
        )
        mapping.mapping_table.selectRow(basin_index)
        mapping.source_unit.setCurrentIndex(mapping.source_unit.findText("km²"))
        mapping.unit_button.click()
        _wait(app, lambda: mapping.state.rows[basin_index].unit_status == "확인됨")
        mapping.preview_button.click()
        _wait(app, lambda: mapping.next_button.isEnabled())
        mapping.next_button.click()
        execution = window.import_execution
        _wait(app, lambda: execution.plan is not None)
        execution.execute_button.click()
        _wait(app, lambda: not execution.mutation_active and "완료" in execution.status.text())
        assert "SUCCESS" in execution.result.text()
        window.navigate("Import 이력")
        history = window.import_history
        _wait(app, lambda: history.result is not None and history.result.total_count == 1)
        assert history.result.items[0].status == "SUCCESS"
        window.navigate("소하천 조회")
        _wait(app, lambda: window.stream_list.model.rowCount() == 1)
        window.stream_list.table.selectRow(0)
        _wait(app, lambda: window.stream_list.detail_button.isEnabled())
        window.stream_list.detail_button.click()
        _wait(app, lambda: window.stack.currentWidget() is window.stream_detail)
        _wait(app, lambda: window.stream_detail._detail is not None)
        assert window.stream_detail._detail.basic.stream_code == "01234567001"
    finally:
        controller.close()
        app.processEvents()
