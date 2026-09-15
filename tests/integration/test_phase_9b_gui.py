"""합성 DB와 offscreen Qt에서 Phase 9B의 인증·목록 흐름을 검증한다."""

import os
import time
from contextlib import closing
from dataclasses import fields

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit

from small_stream_research_tool.app.controller import ApplicationController, GuiSession
from small_stream_research_tool.database import connect_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.stream_read import StreamListPage, StreamListRow
from small_stream_research_tool.models.stream_read_errors import InvalidStreamReadRequest
from small_stream_research_tool.repositories.import_persistence_repository import (
    SmallStreamRepository,
)
from small_stream_research_tool.services.stream_read_service import StreamReadService
from small_stream_research_tool.ui.presentation import HEADERS, display_row

STAMP = "2026-09-13T01:02:03Z"


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
    pytest.fail("합성 DB GUI 작업이 끝나지 않았습니다.")


def seed(path, count=65):
    with closing(connect_database(path)) as conn:
        with transaction(conn):
            repo = SmallStreamRepository(conn)
            for i in range(count):
                province = "01" if i < 40 else "02"
                city = "234" if i < 20 or i >= 40 else "235"
                repo.create(
                    stream_code=province + city + "567" + f"{i:03d}",
                    province_code=province,
                    city_county_code=city,
                    town_code="567",
                    stream_serial_no=f"{i:03d}",
                    stream_name=f"Synthetic {i:03d}",
                    province_name="Synthetic North" if province == "01" else "Synthetic South",
                    city_county_name="Synthetic City " + city,
                    town_name="Synthetic Town",
                    created_at=STAMP,
                    updated_at=STAMP,
                )


@pytest.fixture
def controller(tmp_path, app):
    control = ApplicationController(tmp_path / "synthetic.sqlite3")
    yield control
    control.close()
    app.processEvents()


def test_initial_setup_login_failure_success_and_logout(controller, app):
    controller.start()
    setup = controller.login_window
    assert setup.initial_setup and setup.isVisible()
    assert setup.password.echoMode() == QLineEdit.EchoMode.Password
    setup.login_id.setText("synthetic_actor")
    setup.password.setText("synthetic-password")
    setup.display_name.setText("Synthetic Researcher")
    setup.department.setText("Synthetic Team")
    setup.submit.click()
    app.processEvents()
    login = controller.login_window
    assert not login.initial_setup and login.isVisible()
    login.login_id.setText("synthetic_actor")
    login.password.setText("incorrect")
    login.submit.click()
    assert controller.session is None and login.isVisible()
    assert "비밀번호" in login.error.text()
    assert "incorrect" not in login.error.text()
    login.password.setText("synthetic-password")
    login.password.returnPressed.emit()
    wait_for(app, lambda: controller.main_window is not None)
    assert controller.main_window.isVisible()
    assert controller.session.display_name == "Synthetic Researcher"
    assert controller.session.department == "Synthetic Team"
    assert {f.name for f in fields(GuiSession)} == {"user_id", "display_name", "department", "role"}
    controller.main_window.logout_requested.emit()
    app.processEvents()
    assert controller.session is None and controller.login_window.isVisible()


def test_list_navigation_search_regions_sort_pages_and_selection(controller, app):
    controller.auth_service.create_user("synthetic_actor", "synthetic-password", "Synthetic")
    seed(controller.db_path)
    controller.start()
    login = controller.login_window
    login.login_id.setText("synthetic_actor")
    login.password.setText("synthetic-password")
    login.submit.click()
    window = controller.main_window
    view = window.stream_list
    wait_for(app, lambda: view.model.rowCount() == 50)
    assert view.page_label.text().startswith("1 / 2")
    assert not view.previous.isEnabled() and view.next.isEnabled()
    assert view.model.headerData(5, Qt.Orientation.Horizontal) == "데이터 상태"
    assert view.model.data(view.model.index(0, 5)) == "활성 문제 없음"
    assert view.table.editTriggers() == view.table.EditTrigger.NoEditTriggers
    assert HEADERS[0] == "소하천 관리코드"
    view.table.selectRow(0)
    assert view.selected_code == view.model.stream_code(0)
    window.navigate("홈")
    assert window.stack.currentWidget() is window.placeholder
    assert window.placeholder_title.text() == "홈"
    window.navigate("소하천 조회")
    assert window.stack.currentWidget() is view
    view.next.click()
    wait_for(app, lambda: view.page == 2 and view.model.rowCount() == 15)
    assert view.previous.isEnabled() and not view.next.isEnabled()
    view.sort_by_column(1)
    wait_for(app, lambda: view.page == 1 and view.model.rowCount() == 50)
    assert view.sort_field == "stream_name" and view.sort_direction == "ASC"
    view.search.setText("Synthetic 064")
    view.search.returnPressed.emit()
    wait_for(app, lambda: view.model.rowCount() == 1)
    assert view.page == 1 and view.model.stream_code(0).endswith("064")
    view.search.setText("No matching synthetic")
    view.search_button.click()
    wait_for(app, lambda: "조건에 맞는" in view.status.text())
    assert view.model.rowCount() == 0
    view.search.clear()
    view.apply_search()
    wait_for(app, lambda: view.model.rowCount() == 50)
    wait_for(app, lambda: view.regions["province"].count() == 3)
    view.regions["province"].setCurrentIndex(1)
    wait_for(app, lambda: view.regions["city_county"].count() == 3)
    wait_for(app, lambda: view.status.text() == "전체 40건")
    view.regions["city_county"].setCurrentIndex(1)
    wait_for(app, lambda: view.regions["town"].count() == 2)
    wait_for(app, lambda: view.status.text() == "전체 20건")
    assert view.page == 1
    view.regions["province"].setCurrentIndex(2)
    wait_for(app, lambda: view.status.text() == "전체 25건")
    assert view.regions["city_county"].currentData() is None
    assert view.regions["town"].currentData() is None


def test_safe_presentation_and_stale_result(controller, app):
    controller.auth_service.create_user("synthetic_actor", "synthetic-password", "Synthetic")
    controller.start()
    login = controller.login_window
    login.login_id.setText("synthetic_actor")
    login.password.setText("synthetic-password")
    login.submit.click()
    view = controller.main_window.stream_list
    wait_for(app, lambda: "조건에 맞는" in view.status.text())
    row = StreamListRow("01234567001", "Synthetic", "North", "City", "Town", True, "ERROR")
    assert display_row(row)[5] == "오류"
    assert display_row(row)[0] == "01234567001"
    assert (
        display_row(StreamListRow("01234567002", "S", None, None, None, True, "NEEDS_REVIEW"))[5]
        == "확인 필요"
    )
    assert (
        "정상"
        not in display_row(
            StreamListRow("01234567003", "S", None, None, None, True, "ACTIVE_ISSUES_NONE")
        )[5]
    )
    stale = StreamListPage(1, 1, 50, 1, (row,))
    view._generation += 1
    view._list_result(view._generation - 1, stale, None)
    assert view.model.rowCount() == 0
    view._list_result(view._generation, None, "failure")
    assert view.status.text() == "조회 중 오류가 발생했습니다."
    assert "failure" not in view.status.text()


def test_region_option_service_obeys_parent_codes(controller):
    seed(controller.db_path)
    with closing(connect_database(controller.db_path)) as conn:
        service = StreamReadService(conn)
        assert [o.code for o in service.region_options("province")] == ["01", "02"]
        assert [o.code for o in service.region_options("city_county", province_code="01")] == [
            "234",
            "235",
        ]
        assert [
            o.code
            for o in service.region_options("town", province_code="01", city_county_code="235")
        ] == ["567"]
        with pytest.raises(InvalidStreamReadRequest):
            service.region_options("town", city_county_code="235")
