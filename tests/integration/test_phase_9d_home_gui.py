"""Phase 9D-2 Home GUI를 합성 DB와 offscreen Qt에서 검증한다."""

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
from small_stream_research_tool.models.app_read import HomeSummary, WorkHistoryItem
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    SmallStreamRepository,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
)
from small_stream_research_tool.ui import workers
from small_stream_research_tool.ui.presentation import DICTIONARY_STATE_TEXT
from small_stream_research_tool.ui.workers import AppQueryTask

STAMP = "2026-09-20T01:02:03Z"
STREAM = "01234567001"


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
    pytest.fail("Home GUI 비동기 작업이 끝나지 않았습니다.")


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


def seed_home(path, actor_user_id):
    with closing(connect_database(path)) as conn:
        with transaction(conn):
            SmallStreamRepository(conn).create(
                stream_code=STREAM,
                province_code="01",
                city_county_code="234",
                town_code="567",
                stream_serial_no="001",
                stream_name="합성 소하천",
                province_name="합성도",
                city_county_name="합성군",
                town_name="합성면",
                created_at=STAMP,
                updated_at=STAMP,
            )
        ResearchDictionaryBootstrapService(conn).bootstrap()
        item = DictionaryRepository(conn).get_item_by_internal_name("basin_area")
        with transaction(conn):
            conn.execute(
                "INSERT INTO data_quality_issue "
                "(stream_code,issue_type,severity,message,is_active,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (STREAM, "SYNTHETIC_WARNING", "WARNING", "표시하면 안 되는 원문", 1, STAMP),
            )
            events = (
                "CORRECTION",
                "CURRENT_VALUE_CHANGE",
                "DEACTIVATE",
                "RESTORE",
                "CACHE_REBUILD",
                "CORRECTION",
            )
            for index, event in enumerate(events):
                key = (
                    {"stream_code": STREAM, "dictionary_id": item.dictionary_id}
                    if event in {"CORRECTION", "CURRENT_VALUE_CHANGE", "CACHE_REBUILD"}
                    else {"characteristic_value_id": 9000 + index}
                )
                conn.execute(
                    "INSERT INTO record_history "
                    "(table_name,record_key,change_type,reason,actor_user_id,changed_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        "characteristic_value",
                        json.dumps(key),
                        event,
                        "PRIVATE_REASON_NOT_FOR_UI",
                        actor_user_id,
                        f"2026-09-20T01:02:{index:02d}Z",
                    ),
                )


def login(controller, app):
    controller.start()
    window = controller.login_window
    window.login_id.setText("synthetic_actor")
    window.password.setText("synthetic-password")
    window.submit.click()
    wait_for(app, lambda: controller.main_window is not None)
    return controller.main_window


@pytest.fixture
def home_controller(tmp_path, app):
    controller = ApplicationController(tmp_path / "home.sqlite3")
    user = controller.auth_service.create_user(
        "synthetic_actor", "synthetic-password", "합성 작업자", "합성 연구팀"
    )
    seed_home(controller.db_path, user.user_id)
    yield controller
    controller.close()
    app.processEvents()


def test_login_lands_on_home_summary_and_safe_recent_history(home_controller, app):
    window = login(home_controller, app)
    home = window.home
    wait_for(app, lambda: home.stream_count.text() == "1건")
    assert window.stack.currentWidget() is home
    assert window.nav_buttons["홈"].objectName() == "navSelected"
    assert home.error_count.text() == "0건"
    assert home.review_count.text() == "1건"
    assert home.dictionary_state.text() == "연구 사전 준비됨"
    assert home.history.rowCount() == 5
    displayed = " ".join(
        home.history.item(row, column).text()
        for row in range(home.history.rowCount())
        for column in range(home.history.columnCount())
    )
    assert "정상" not in displayed and "QC 완료" not in displayed
    assert "PRIVATE_REASON" not in displayed and "표시하면 안 되는 원문" not in displayed
    assert "characteristic_value_id" not in displayed and "record_key" not in displayed
    assert "합성 작업자" in displayed
    assert "UTC" in displayed


def test_home_navigation_refresh_quick_action_and_logout_are_read_only(home_controller, app):
    window = login(home_controller, app)
    home = window.home
    wait_for(app, lambda: home.stream_count.text() == "1건")
    before = snapshot(home_controller.db_path)
    home_identity = id(home)
    stack_count = window.stack.count()
    home.stream_list_button.click()
    assert window.stack.currentWidget() is window.stream_list
    for _index in range(2):
        window.navigate("홈")
        wait_for(app, lambda: home.status.text().startswith("최근 작업"))
        window.navigate("소하천 조회")
    window.navigate("홈")
    wait_for(app, lambda: home.status.text().startswith("최근 작업"))
    assert window.stack.currentWidget() is home
    assert id(window.home) == home_identity and window.stack.count() == stack_count
    assert snapshot(home_controller.db_path) == before
    window.logout_button.click()
    app.processEvents()
    assert home_controller.session is None and home_controller.login_window.isVisible()


@pytest.mark.parametrize(("state", "label"), tuple(DICTIONARY_STATE_TEXT.items()))
def test_dictionary_state_presentation_and_history_empty_state(tmp_path, app, state, label):
    controller = ApplicationController(tmp_path / f"{state}.sqlite3")
    controller.auth_service.create_user("synthetic_actor", "synthetic-password", "합성 작업자")
    if state != "NOT_INITIALIZED":
        with closing(connect_database(controller.db_path)) as conn:
            ResearchDictionaryBootstrapService(conn).bootstrap()
            if state == "INCONSISTENT":
                conn.execute(
                    "UPDATE data_dictionary SET is_active=0 WHERE internal_name='basin_area'"
                )
    window = login(controller, app)
    wait_for(app, lambda: window.home.dictionary_state.text() == label)
    assert window.home.empty_history.isVisible()
    assert not window.home.history.isVisible()
    controller.close()


def test_home_stale_response_safe_error_and_card_reflow(home_controller, app):
    window = login(home_controller, app)
    home = window.home
    wait_for(app, lambda: home.stream_count.text() == "1건")
    stale = HomeSummary(999, 999, 999, "INCONSISTENT", ())
    started = []

    class HoldingPool:
        def start(self, task):
            started.append(task)

    real_pool = home.pool
    home.pool = HoldingPool()
    home.refresh()
    assert home.status.text() == "홈 정보를 불러오는 중입니다."
    assert len(started) == 1
    home.pool = real_pool

    home._generation += 1
    home._summary_result(started[0], home._generation - 1, stale, None)
    assert home.stream_count.text() == "1건"
    window.navigate("소하천 조회")
    home._summary_result(object(), home._generation, stale, None)
    assert window.stack.currentWidget() is window.stream_list
    window.navigate("홈")
    wait_for(app, lambda: home.stream_count.text() == "1건")
    home._summary_result(object(), home._generation, None, "private exception detail")
    assert home.status.text() == "홈 정보를 불러오지 못했습니다."
    assert "private" not in home.status.text()

    window.resize(1440, 900)
    app.processEvents()
    assert home._card_mode == "wide"
    assert home.card_layout.getItemPosition(home.card_layout.indexOf(home.cards[3]))[:2] == (0, 3)
    window.resize(900, 600)
    app.processEvents()
    assert home._card_mode == "compact"
    assert home.card_layout.getItemPosition(home.card_layout.indexOf(home.cards[3]))[:2] == (1, 1)
    assert home.scroll_area.horizontalScrollBar().maximum() == 0
    window.resize(1440, 900)
    app.processEvents()
    assert home._card_mode == "wide"


def test_app_query_worker_owns_and_closes_connection(tmp_path, app, monkeypatch):
    controller = ApplicationController(tmp_path / "worker.sqlite3")
    connections = []
    real_connect = connect_database

    def tracked(path):
        connection = real_connect(path)
        connections.append(connection)
        return connection

    monkeypatch.setattr(workers, "connect_database", tracked)
    results = []
    task = AppQueryTask(controller.db_path, 7, "get_home_summary")
    task.signals.finished.connect(lambda *values: results.append(values))
    task.run()
    app.processEvents()
    assert results and results[0][0] == 7 and results[0][2] is None
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")
    controller.close()


def test_unknown_projection_uses_neutral_labels(app, tmp_path):
    controller = ApplicationController(tmp_path / "unknown.sqlite3")
    controller.auth_service.create_user("synthetic_actor", "synthetic-password", "합성 작업자")
    window = login(controller, app)
    home = window.home
    wait_for(app, lambda: home.dictionary_state.text() == "연구 사전 미초기화")
    item = WorkHistoryItem(
        "FUTURE_EVENT",
        None,
        "UNKNOWN",
        None,
        None,
        None,
        "UNRESOLVED",
        None,
        "UNRECOGNIZED",
        "not-a-timestamp",
    )
    summary = HomeSummary(0, 0, 0, "FUTURE_STATE", (item,))
    home._summary_result(object(), home._generation, summary, None)
    values = [home.history.item(0, column).text() for column in range(4)]
    assert values == [
        "시각 확인 필요",
        "작업 유형 확인 필요",
        "대상 정보 확인 필요",
        "작업자 정보 없음",
    ]
    assert home.dictionary_state.text() == "연구 사전 상태 확인 필요"
    controller.close()
