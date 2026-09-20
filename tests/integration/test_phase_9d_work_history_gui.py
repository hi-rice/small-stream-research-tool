"""Phase 9D-3 작업이력 GUI를 synthetic DB와 offscreen Qt에서 검증한다."""

import json
import os
import sqlite3
import time
from contextlib import closing

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from small_stream_research_tool.app.controller import ApplicationController
from small_stream_research_tool.database import connect_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.app_read import WorkHistoryPage, WorkHistoryRequest
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    SmallStreamRepository,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
)
from small_stream_research_tool.ui import workers
from small_stream_research_tool.ui.workers import AppQueryTask

STREAM = "01234567001"
OTHER_STREAM = "01234567002"
STAMP = "2026-09-20T00:00:00Z"


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, condition, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return
        time.sleep(0.02)
    pytest.fail("작업이력 GUI 비동기 작업이 끝나지 않았습니다.")


def snapshot(path):
    with closing(connect_database(path)) as conn:
        tables = tuple(
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        )
        return tuple(
            (table, tuple(conn.execute(f"SELECT * FROM [{table}] ORDER BY 1").fetchall()))
            for table in tables
        )


def seed_history(path, actor_one, actor_two):
    with closing(connect_database(path)) as conn:
        with transaction(conn):
            repository = SmallStreamRepository(conn)
            for code, name, serial in (
                (STREAM, "합성 소하천 A", "001"),
                (OTHER_STREAM, "합성 소하천 B", "002"),
            ):
                repository.create(
                    stream_code=code,
                    province_code="01",
                    city_county_code="234",
                    town_code="567",
                    stream_serial_no=serial,
                    stream_name=name,
                    province_name="합성도",
                    city_county_name="합성군",
                    town_name="합성면",
                    created_at=STAMP,
                    updated_at=STAMP,
                )
        ResearchDictionaryBootstrapService(conn).bootstrap()
        item = DictionaryRepository(conn).get_item_by_internal_name("basin_area")
        with transaction(conn):
            value = CharacteristicValueRepository(conn).create(
                stream_code=STREAM,
                dictionary_id=item.dictionary_id,
                value_number=1.0,
                original_value="SYNTHETIC_VALUE_NOT_FOR_UI",
                is_active=True,
                is_representative=False,
                created_at=STAMP,
                updated_at=STAMP,
            )
            events = (
                "CORRECTION",
                "CURRENT_VALUE_CHANGE",
                "DEACTIVATE",
                "RESTORE",
                "CACHE_REBUILD",
            )
            reasons = ("RESEARCHER_SELECTION", "SOURCE_REVIEW", "QC_REVIEW_CONFIRMED")
            for index in range(55):
                event = events[index % len(events)]
                code = STREAM if index % 2 == 0 else OTHER_STREAM
                if event in {"DEACTIVATE", "RESTORE"}:
                    value_id = (
                        value.characteristic_value_id
                        if index != 52
                        else value.characteristic_value_id + 9999
                    )
                    key = {"characteristic_value_id": value_id}
                else:
                    key = {"stream_code": code, "dictionary_id": item.dictionary_id}
                actor = None if index == 53 else actor_one if index % 2 == 0 else actor_two
                reason = "PRIVATE_RAW_REASON" if index == 52 else reasons[index % len(reasons)]
                conn.execute(
                    "INSERT INTO record_history "
                    "(table_name,record_key,old_value,new_value,change_type,reason,"
                    "actor_user_id,changed_at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        "characteristic_value",
                        json.dumps(key),
                        "PRIVATE_OLD_VALUE",
                        "PRIVATE_NEW_VALUE",
                        event,
                        reason,
                        actor,
                        f"2026-09-20T00:{index:02d}:00Z",
                    ),
                )


@pytest.fixture
def controller(tmp_path, app):
    control = ApplicationController(tmp_path / "history.sqlite3")
    first = control.auth_service.create_user("synthetic_actor", "synthetic-password", "합성 작업자")
    second = control.auth_service.create_user(
        "other_actor", "other-synthetic-password", "합성 작업자"
    )
    seed_history(control.db_path, first.user_id, second.user_id)
    yield control
    control.close()
    app.processEvents()


def login(controller, app):
    controller.start()
    login_window = controller.login_window
    login_window.login_id.setText("synthetic_actor")
    login_window.password.setText("synthetic-password")
    login_window.submit.click()
    wait_for(app, lambda: controller.main_window is not None)
    return controller.main_window


def test_navigation_default_page_safe_projection_and_pagination(controller, app):
    window = login(controller, app)
    assert window.stack.currentWidget() is window.home
    window.home.work_history_button.click()
    view = window.work_history
    wait_for(app, lambda: view.table.rowCount() == 50 and view.actor.count() == 3)
    assert view.actor.itemText(1) == view.actor.itemText(2) == "합성 작업자"
    assert view.actor.itemData(1) != view.actor.itemData(2)
    assert window.stack.currentWidget() is view
    assert window.nav_buttons["작업이력"].objectName() == "navSelected"
    assert view.page_label.text() == "1 / 2 페이지 · 총 55건"
    assert not view.previous.isEnabled() and view.next.isEnabled()
    assert not view.table.isSortingEnabled()
    first_row = [view.table.item(0, column).text() for column in range(6)]
    assert first_row[0] == "2026-09-20 00:54 UTC"
    assert first_row[1] == "현재값 캐시 재구축"
    displayed = " ".join(
        view.table.item(row, column).text()
        for row in range(view.table.rowCount())
        for column in range(view.table.columnCount())
    )
    for forbidden in (
        "record_key",
        "dictionary_id",
        "characteristic_value_id",
        "PRIVATE_RAW_REASON",
        "PRIVATE_OLD_VALUE",
        "PRIVATE_NEW_VALUE",
        "SYNTHETIC_VALUE_NOT_FOR_UI",
    ):
        assert forbidden not in displayed
    assert "작업자 미상" in displayed
    assert "대상 정보 확인 필요" in displayed
    view.next.click()
    wait_for(app, lambda: view.page == 2 and view.table.rowCount() == 5)
    assert view.previous.isEnabled() and not view.next.isEnabled()
    assert view.page_label.text() == "2 / 2 페이지 · 총 55건"


def test_filters_combination_validation_and_state_preservation(controller, app):
    window = login(controller, app)
    window.navigate("작업이력")
    view = window.work_history
    wait_for(app, lambda: view.table.rowCount() == 50 and view.actor.count() == 3)
    view.next.click()
    wait_for(app, lambda: view.page == 2)
    view.change_type.setCurrentIndex(view.change_type.findData("CORRECTION"))
    view.search_button.click()
    wait_for(app, lambda: view.page == 1 and view.table.rowCount() == 11)
    assert all(view.table.item(row, 1).text() == "특성정보 보정" for row in range(11))

    view.actor.setCurrentIndex(view.actor.findText("합성 작업자"))
    view.stream_code.setText(STREAM)
    view.stream_code.returnPressed.emit()
    wait_for(app, lambda: view.status.text().startswith("전체"))
    assert view.page == 1
    assert all(STREAM in view.table.item(row, 2).text() for row in range(view.table.rowCount()))

    generation = view._generation
    view.stream_code.setText("123")
    view.search_button.click()
    assert view._generation == generation
    assert view.status.text() == "관리코드는 숫자로 된 11자리여야 합니다."

    view.stream_code.setText("99999999999")
    view.search_button.click()
    wait_for(app, lambda: view.page_label.text() == "0 / 0 페이지 · 0건")
    assert view.empty_state.isVisible() and not view.table.isVisible()

    window.navigate("홈")
    window.navigate("작업이력")
    assert view.stream_code.text() == "99999999999"
    wait_for(app, lambda: view.page_label.text() == "0 / 0 페이지 · 0건")


def test_stale_loading_safe_error_worker_close_and_read_only(controller, app, monkeypatch):
    window = login(controller, app)
    window.navigate("작업이력")
    view = window.work_history
    wait_for(app, lambda: view.table.rowCount() == 50)
    before = snapshot(controller.db_path)
    original_rows = view.table.rowCount()
    stale = WorkHistoryPage(0, 1, 50, 0, ())
    view._generation += 1
    view._history_result(view._generation - 1, stale, None)
    assert view.table.rowCount() == original_rows
    window.navigate("홈")
    view._history_result(view._generation, stale, None)
    assert window.stack.currentWidget() is window.home
    window.navigate("작업이력")
    wait_for(app, lambda: view.table.rowCount() == 50)

    held = []

    class HoldingPool:
        def start(self, task):
            held.append(task)

    real_pool = view.pool
    view.pool = HoldingPool()
    view.refresh()
    assert view.status.text() == "조회 중" and len(held) == 1
    view.pool = real_pool
    view._generation += 1
    view._history_result(view._generation, None, "private database path")
    assert view.status.text() == "작업이력을 불러오지 못했습니다."
    assert "private" not in view.status.text()

    connections = []
    real_connect = connect_database

    def tracked(path):
        connection = real_connect(path)
        connections.append(connection)
        return connection

    monkeypatch.setattr(workers, "connect_database", tracked)
    results = []
    task = AppQueryTask(
        controller.db_path,
        9,
        "list_work_history",
        ((WorkHistoryRequest(page_size=50),), {}),
    )
    task.signals.finished.connect(lambda *values: results.append(values))
    task.run()
    app.processEvents()
    assert results and results[0][2] is None
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")
    assert snapshot(controller.db_path) == before


def test_responsive_navigation_identity_and_logout(controller, app):
    window = login(controller, app)
    view = window.work_history
    identity = id(view)
    stack_count = window.stack.count()
    window.navigate("작업이력")
    wait_for(app, lambda: view.table.rowCount() == 50)
    window.resize(900, 600)
    app.processEvents()
    assert view._filter_mode == "compact"
    assert view.table.horizontalScrollBar().maximum() > 0
    window.navigate("홈")
    assert window.stack.currentWidget() is window.home
    window.navigate("소하천 조회")
    window.navigate("작업이력")
    assert id(window.work_history) == identity and window.stack.count() == stack_count
    window.logout_button.click()
    app.processEvents()
    assert controller.session is None and controller.login_window.isVisible()
