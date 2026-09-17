"""개발 전용 UI smoke DB의 격리·합성 상태·Phase 8 연계를 검증한다."""

import time
import uuid
from contextlib import closing

import pytest
from PySide6.QtWidgets import QApplication
from tools.ui_smoke import ROOT, create_database, finalize_after_registration, smoke_path

from small_stream_research_tool.app.controller import GuiSession
from small_stream_research_tool.config.settings import get_app_paths
from small_stream_research_tool.database import connect_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.models.errors import AuthenticationError
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.services.auth_service import AuthService
from small_stream_research_tool.ui.main_window import MainWindow


@pytest.fixture
def smoke_database():
    path = ROOT / "build" / f"test_ui_smoke_{uuid.uuid4().hex}.db"
    try:
        yield create_database(path)
    finally:
        path.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, condition, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return
        time.sleep(0.02)
    pytest.fail("UI smoke 화면 전환이 완료되지 않았습니다.")


def test_path_guard_refuses_default_outside_and_overwrite(smoke_database):
    default = get_app_paths().database_dir / "research.sqlite3"
    with pytest.raises(ValueError):
        smoke_path(default)
    with pytest.raises(ValueError):
        smoke_path(ROOT / "ui_smoke.db")
    with pytest.raises(FileExistsError):
        create_database(smoke_database)


def test_created_database_is_synthetic_unregistered_and_bootstrapped(smoke_database):
    with closing(connect_database(smoke_database)) as connection:
        assert connection.execute("SELECT count(*) FROM app_user").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM small_stream").fetchone() == (5,)
        assert connection.execute("SELECT count(*) FROM data_dictionary").fetchone() == (70,)
        assert connection.execute(
            "SELECT count(*) FROM dictionary_version "
            "WHERE version='research-dictionary-v1' AND is_current=1"
        ).fetchone() == (1,)
        names = {row[0] for row in connection.execute("SELECT stream_name FROM small_stream")}
        assert names == {"테스트천A", "테스트천B", "테스트천C", "테스트천D", "테스트천E"}
        assert connection.execute("SELECT count(*) FROM characteristic_value").fetchone()[0] >= 100
        assert connection.execute("SELECT original_path FROM source_file").fetchone() == (
            "synthetic://ui-smoke/synthetic_ui_smoke.xlsx",
        )


def test_registration_finalizer_uses_services_and_builds_ui_states(smoke_database):
    with closing(connect_database(smoke_database)) as connection:
        with transaction(connection):
            UserRepository(connection).create_user(
                login_id="synthetic_actor",
                password_hash="NOT_A_LOGIN_CREDENTIAL",
                display_name="합성 UI 검수자",
                department="합성 부서",
                role=None,
                timestamp="2026-09-17T00:01:00Z",
            )
    assert finalize_after_registration(smoke_database)
    assert finalize_after_registration(smoke_database)
    with closing(connect_database(smoke_database)) as connection:
        representatives = dict(
            connection.execute(
                "SELECT stream_code,count(*) FROM characteristic_value "
                "WHERE is_active=1 AND is_representative=1 GROUP BY stream_code"
            )
        )
        caches = dict(
            connection.execute(
                "SELECT stream_code,count(*) FROM stream_characteristic GROUP BY stream_code"
            )
        )
        assert representatives["99000000001"] == 70
        assert 0 < representatives["99000000004"] < 70
        assert representatives["99000000005"] > 0
        assert caches.get("99000000005", 0) == 0
        assert connection.execute(
            "SELECT count(*) FROM characteristic_value WHERE source_type='USER_CORRECTION'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM characteristic_value "
            "WHERE source_type='USER_CORRECTION' AND is_representative=1"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM record_history WHERE change_type='CORRECTION'"
        ).fetchone() == (1,)
        states = set(
            connection.execute(
                "SELECT severity,review_status FROM data_quality_issue WHERE is_active=1"
            )
        )
        assert ("WARNING", "CONFIRMED") in states
        assert ("ERROR", "IN_REVIEW") in states


def test_smoke_registration_and_login_use_same_database_and_password(smoke_database):
    password = "synthetic smoke passphrase"
    with closing(connect_database(smoke_database)) as connection:
        service = AuthService(UserRepository(connection))
        assert service.needs_initial_user_setup()
        created = service.create_user("smoke.researcher", password, "합성 검수자", department=None)
        assert created.department is None
    assert finalize_after_registration(smoke_database)
    with closing(connect_database(smoke_database)) as connection:
        service = AuthService(UserRepository(connection))
        authenticated = service.authenticate(" SMOKE.RESEARCHER ", password)
        assert authenticated.user_id == created.user_id
        with pytest.raises(AuthenticationError):
            service.authenticate("smoke.researcher", "wrong synthetic passphrase")


def test_offscreen_smoke_browse_detail_tabs_back_and_logout(smoke_database, app):
    with closing(connect_database(smoke_database)) as connection:
        service = AuthService(UserRepository(connection))
        user = service.create_user("smoke.researcher", "synthetic smoke passphrase", "합성 검수자")
    assert finalize_after_registration(smoke_database)
    window = MainWindow(smoke_database, GuiSession(user.user_id, user.display_name, None, None))
    logout = []
    window.logout_requested.connect(lambda: logout.append(True))
    try:
        wait_for(app, lambda: window.stream_list.model.rowCount() == 5)
        view = window.stream_list
        row = next(
            index
            for index in range(view.model.rowCount())
            if view.model.stream_code(index) == "99000000001"
        )
        view.table.selectRow(row)
        wait_for(app, lambda: view.summary_name.text() == "테스트천A")
        view.detail_button.click()
        detail = window.stream_detail
        wait_for(app, lambda: detail.status.text() == "읽기 전용 상세정보")
        assert detail.category.count() == 5
        for index in range(detail.category.count()):
            detail.category.setCurrentIndex(index)
            app.processEvents()
            assert detail.model.rowCount() > 0
        detail.table.selectRow(0)
        for index in range(detail.detail_tabs.count()):
            detail.detail_tabs.setCurrentIndex(index)
            app.processEvents()
        detail.back.click()
        assert window.stack.currentWidget() is view
        window.logout_button.click()
        assert logout == [True]
    finally:
        window.close()
        app.processEvents()
