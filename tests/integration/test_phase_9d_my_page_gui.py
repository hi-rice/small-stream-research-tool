"""Phase 9D-4 My Page를 synthetic DB와 offscreen Qt에서 검증한다."""

import json
import os
import sqlite3
import time
from contextlib import closing

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from small_stream_research_tool.app.controller import ApplicationController
from small_stream_research_tool.database import connect_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    SmallStreamRepository,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
)
from small_stream_research_tool.ui import workers
from small_stream_research_tool.ui.my_page import MyPageView
from small_stream_research_tool.ui.workers import MyPageQueryTask

STAMP = "2026-09-20T00:00:00Z"
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
    pytest.fail("My Page 비동기 작업이 끝나지 않았습니다.")


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


def seed_recent(path, actor_id):
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
            for index, event in enumerate(
                (
                    "CORRECTION",
                    "CURRENT_VALUE_CHANGE",
                    "CACHE_REBUILD",
                    "CORRECTION",
                    "CURRENT_VALUE_CHANGE",
                    "CACHE_REBUILD",
                )
            ):
                conn.execute(
                    "INSERT INTO record_history "
                    "(table_name,record_key,old_value,new_value,change_type,reason,"
                    "actor_user_id,changed_at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        "characteristic_value",
                        json.dumps({"stream_code": STREAM, "dictionary_id": item.dictionary_id}),
                        "PRIVATE_OLD",
                        "PRIVATE_NEW",
                        event,
                        "PRIVATE_REASON",
                        actor_id,
                        f"2026-09-20T00:0{index}:00Z",
                    ),
                )


@pytest.fixture
def controller(tmp_path, app):
    control = ApplicationController(tmp_path / "my-page.sqlite3")
    user = control.auth_service.create_user(
        "synthetic_actor",
        "synthetic-password",
        "합성 작업자",
        "합성 연구팀",
        "연구자",
    )
    seed_recent(control.db_path, user.user_id)
    other = control.auth_service.create_user(
        "other_actor", "other-synthetic-password", "다른 작업자"
    )
    with closing(connect_database(control.db_path)) as conn:
        item = DictionaryRepository(conn).get_item_by_internal_name("basin_area")
        with transaction(conn):
            conn.execute(
                "INSERT INTO record_history "
                "(table_name,record_key,change_type,actor_user_id,changed_at) "
                "VALUES (?,?,?,?,?)",
                (
                    "characteristic_value",
                    json.dumps({"stream_code": STREAM, "dictionary_id": item.dictionary_id}),
                    "CORRECTION",
                    other.user_id,
                    "2026-09-20T00:59:00Z",
                ),
            )
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


def visible_text(widget):
    labels = [label.text() for label in widget.findChildren(QLabel)]
    table = widget.recent
    cells = [
        table.item(row, column).text()
        for row in range(table.rowCount())
        for column in range(table.columnCount())
    ]
    return " ".join(labels + cells)


def test_topbar_identity_keeps_readable_geometry_at_supported_sizes(tmp_path, app):
    control = ApplicationController(tmp_path / "topbar-identity.sqlite3")
    control.auth_service.create_user(
        "topbar_actor",
        "synthetic-password",
        "권혜연",
        "기후영향분석팀",
        "연구자",
    )
    control.start()
    login_window = control.login_window
    login_window.login_id.setText("topbar_actor")
    login_window.password.setText("synthetic-password")
    login_window.submit.click()
    wait_for(app, lambda: control.main_window is not None)
    window = control.main_window
    try:
        window.show()
        for width, height in ((1440, 900), (1200, 800), (900, 600)):
            window.resize(width, height)
            app.processEvents()
            assert window.user_name.text() == "권혜연"
            assert window.user_department.text() == "기후영향분석팀"
            assert (
                window.user_name.contentsRect().width()
                >= window.user_name.fontMetrics().horizontalAdvance(window.user_name.text())
            )
            assert (
                window.user_department.contentsRect().width()
                >= window.user_department.fontMetrics().horizontalAdvance(
                    window.user_department.text()
                )
            )
            assert window.logout_button.isVisible()
            assert (
                window.logout_button.geometry().right()
                <= window.logout_button.parentWidget().contentsRect().right()
            )

        window.user_button.click()
        assert window.stack.currentWidget() is window.my_page
        window.logout_button.click()
        app.processEvents()
        assert control.session is None and control.login_window.isVisible()
    finally:
        control.close()
        app.processEvents()


def test_topbar_profile_recent_work_and_navigation_are_safe(controller, app):
    window = login(controller, app)
    with closing(connect_database(controller.db_path)) as conn:
        with transaction(conn):
            conn.execute(
                "UPDATE app_user SET display_name=?,department=?,role=? WHERE user_id=?",
                ("DB 최신 작업자", "DB 최신 부서", "DB 최신 역할", controller.session.user_id),
            )
    before = snapshot(controller.db_path)
    window.user_button.click()
    page = window.my_page
    wait_for(app, lambda: page.profile_values["login_id"].text() == "synthetic_actor")
    assert window.stack.currentWidget() is page
    assert all(button.objectName() == "navButton" for button in window.nav_buttons.values())
    assert window.nav_buttons["설정"].objectName() != "navSelected"
    assert window.user_name.text() == "합성 작업자"
    assert page.profile_values["display_name"].text() == "DB 최신 작업자"
    assert page.profile_values["department"].text() == "DB 최신 부서"
    assert page.profile_values["role"].text() == "DB 최신 역할"
    assert page.profile_values["status"].text() == "사용 중"
    assert page.profile_values["created_at"].text().endswith("UTC")
    assert page.profile_values["last_login_at"].text().endswith("UTC")
    assert page.recent.rowCount() == 5
    assert page.recent.item(0, 0).text() == "2026-09-20 00:05 UTC"
    text = visible_text(page)
    for forbidden in (
        "password",
        "hash",
        "record_key",
        "PRIVATE_OLD",
        "PRIVATE_NEW",
        "PRIVATE_REASON",
        "dictionary_id",
    ):
        assert forbidden not in text
    assert "합성 소하천 · 유역면적" in text
    assert snapshot(controller.db_path) == before

    window.work_history.change_type.setCurrentIndex(1)
    window.work_history.stream_code.setText("99999999999")
    page.history_button.click()
    wait_for(app, lambda: window.work_history.actor.count() == 3)
    assert window.stack.currentWidget() is window.work_history
    assert window.work_history.actor.currentData() == controller.session.user_id
    assert window.work_history.change_type.currentData() is None
    assert window.work_history.stream_code.text() == ""
    assert window.nav_buttons["작업이력"].objectName() == "navSelected"
    window.navigate("홈")
    assert window.stack.currentWidget() is window.home
    window.navigate("설정")
    assert window.stack.currentWidget() is window.placeholder
    assert window.placeholder_title.text() == "설정"
    window.user_button.click()
    assert window.stack.currentWidget() is page


def test_null_profile_and_empty_recent_work(tmp_path, app):
    controller = ApplicationController(tmp_path / "empty-profile.sqlite3")
    user = controller.auth_service.create_user(
        "empty_actor", "synthetic-password", "작업 없는 사용자"
    )
    page = MyPageView(controller.db_path, user.user_id)
    page.show()
    page.refresh()
    wait_for(app, lambda: page.profile_values["login_id"].text() == "empty_actor")
    assert page.profile_values["department"].text() == "미등록"
    assert page.profile_values["role"].text() == "미지정"
    assert page.profile_values["last_login_at"].text() == "로그인 기록 없음"
    assert page.empty_recent.isVisible() and not page.recent.isVisible()
    assert page.empty_recent.text() == "최근 작업이 없습니다."
    page.close()
    controller.close()


@pytest.mark.parametrize("state", ("missing", "inactive"))
def test_missing_and_inactive_user_show_safe_error(tmp_path, app, state):
    controller = ApplicationController(tmp_path / f"{state}.sqlite3")
    user = controller.auth_service.create_user("state_actor", "synthetic-password", "상태 사용자")
    user_id = user.user_id if state == "inactive" else user.user_id + 9999
    if state == "inactive":
        controller.auth_service.set_active(user.user_id, False)
    page = MyPageView(controller.db_path, user_id)
    page.show()
    page.refresh()
    wait_for(app, lambda: "다시 로그인" in page.status.text())
    assert page.status.text() == "현재 사용자 정보를 확인할 수 없습니다. 다시 로그인해주세요."
    assert str(user_id) not in page.status.text()
    page.close()
    controller.close()


def test_loading_stale_worker_close_responsive_and_logout(controller, app, monkeypatch):
    window = login(controller, app)
    page = window.my_page
    held = []

    class HoldingPool:
        def start(self, task):
            held.append(task)

    real_pool = page.pool
    page.pool = HoldingPool()
    window.navigate("마이페이지")
    assert page.status.text() == "사용자 정보를 불러오는 중입니다."
    token = page._generation
    window.navigate("홈")
    page._result(held[0], token, None, "private path")
    assert window.stack.currentWidget() is window.home
    assert page.status.text() == "현재 사용자 정보를 확인할 수 없습니다. 다시 로그인해주세요."

    connections = []
    real_connect = connect_database

    def tracked(path):
        connection = real_connect(path)
        connections.append(connection)
        return connection

    monkeypatch.setattr(workers, "connect_database", tracked)
    results = []
    task = MyPageQueryTask(controller.db_path, 7, controller.session.user_id)
    task.signals.finished.connect(lambda *values: results.append(values))
    task.run()
    app.processEvents()
    assert results and results[0][2] is None
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")

    page.pool = real_pool
    window.resize(900, 600)
    app.processEvents()
    assert page.scroll_area.horizontalScrollBar().maximum() == 0
    identity = id(page)
    count = window.stack.count()
    window.navigate("마이페이지")
    assert id(window.my_page) == identity and window.stack.count() == count
    logout_token = page._generation
    window.logout_button.click()
    app.processEvents()
    assert controller.session is None and controller.login_window.isVisible()
    page._result(held[0], logout_token, None, "late private error")
    assert controller.session is None and controller.login_window.isVisible()
