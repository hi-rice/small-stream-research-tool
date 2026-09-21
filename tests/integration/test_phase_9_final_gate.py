"""Phase 9A~9D의 실제 read-only GUI 상태 전달을 검증하는 Final Gate."""

import json
import os
import subprocess
import sys
import time
from contextlib import closing

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from small_stream_research_tool.app.controller import ApplicationController
from small_stream_research_tool.database import connect_database
from small_stream_research_tool.database.connection import transaction
from small_stream_research_tool.repositories.dictionary_repository import DictionaryRepository
from small_stream_research_tool.repositories.import_persistence_repository import (
    CharacteristicValueRepository,
    SmallStreamRepository,
)
from small_stream_research_tool.services.research_dictionary_bootstrap import (
    ResearchDictionaryBootstrapService,
)

STAMP = "2026-09-21T00:00:00Z"
PRIMARY_STREAM = "01234567000"


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
    pytest.fail("Phase 9 Final Gate 비동기 화면 작업이 끝나지 않았습니다.")


def snapshot(path):
    with closing(connect_database(path)) as connection:
        tables = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        )
        return tuple(
            (table, tuple(connection.execute(f"SELECT * FROM [{table}] ORDER BY 1").fetchall()))
            for table in tables
        )


def seed_gate(path, actor_id):
    with closing(connect_database(path)) as connection:
        ResearchDictionaryBootstrapService(connection).bootstrap()
        with transaction(connection):
            streams = SmallStreamRepository(connection)
            for index in range(55):
                city = "234" if index < 30 else "235"
                streams.create(
                    stream_code=f"01{city}567{index:03d}",
                    province_code="01",
                    city_county_code=city,
                    town_code="567",
                    stream_serial_no=f"{index:03d}",
                    stream_name=f"Gate Stream {index:03d}",
                    province_name="Gate Province",
                    city_county_name=f"Gate City {city}",
                    town_name="Gate Town",
                    river_system="Gate Synthetic System",
                    created_at=STAMP,
                    updated_at=STAMP,
                )
        dictionary = DictionaryRepository(connection)
        basin = dictionary.get_item_by_internal_name("basin_area")
        with transaction(connection):
            value = CharacteristicValueRepository(connection).create(
                stream_code=PRIMARY_STREAM,
                dictionary_id=basin.dictionary_id,
                value_number=12.5,
                original_value="PRIVATE_GATE_ORIGINAL",
                unit_id=basin.unit_id,
                source_type="USER_CORRECTION",
                source_reference="SYNTHETIC_GATE_ONLY",
                is_representative=True,
                quality_status="UNREVIEWED",
                is_active=True,
                created_at=STAMP,
                updated_at=STAMP,
            )
            connection.execute(
                "INSERT INTO stream_characteristic VALUES (?,?,?,?)",
                (PRIMARY_STREAM, basin.dictionary_id, value.characteristic_value_id, STAMP),
            )
            for stream_code, severity in (
                (PRIMARY_STREAM, "WARNING"),
                ("01234567001", "ERROR"),
            ):
                connection.execute(
                    "INSERT INTO data_quality_issue "
                    "(stream_code,issue_type,severity,message,is_active,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        stream_code,
                        "SYNTHETIC_GATE_QC",
                        severity,
                        "PRIVATE_GATE_QC_MESSAGE",
                        1,
                        STAMP,
                    ),
                )
            events = (
                "CORRECTION",
                "CURRENT_VALUE_CHANGE",
                "DEACTIVATE",
                "RESTORE",
                "CACHE_REBUILD",
            )
            for index in range(55):
                event = events[index % len(events)]
                key = (
                    {"characteristic_value_id": value.characteristic_value_id}
                    if event in {"DEACTIVATE", "RESTORE"}
                    else {"stream_code": PRIMARY_STREAM, "dictionary_id": basin.dictionary_id}
                )
                connection.execute(
                    "INSERT INTO record_history "
                    "(table_name,record_key,old_value,new_value,change_type,reason,"
                    "actor_user_id,changed_at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        "characteristic_value",
                        json.dumps(key),
                        "PRIVATE_GATE_OLD",
                        "PRIVATE_GATE_NEW",
                        event,
                        "SOURCE_REVIEW",
                        actor_id,
                        f"2026-09-21T00:{index:02d}:00Z",
                    ),
                )


def login(controller, app, login_id="gate.user", password="synthetic-gate-password"):
    controller.start()
    window = controller.login_window
    window.login_id.setText(login_id)
    window.password.setText(password)
    window.submit.click()
    wait_for(app, lambda: controller.main_window is not None)
    return controller.main_window


def test_phase_9_end_to_end_read_flow_preserves_database(tmp_path, app):
    controller = ApplicationController(tmp_path / "phase9-final-gate.sqlite3")
    user = controller.auth_service.create_user(
        "gate.user", "synthetic-gate-password", "Gate Researcher", "Gate Department", "Researcher"
    )
    seed_gate(controller.db_path, user.user_id)
    window = login(controller, app)
    try:
        home = window.home
        wait_for(app, lambda: home.stream_count.text() == "55건")
        assert home.error_count.text() == "1건"
        assert home.review_count.text() == "1건"
        assert home.dictionary_state.text() == "연구 사전 준비됨"
        assert home.history.rowCount() == 5
        before = snapshot(controller.db_path)

        home.stream_list_button.click()
        listing = window.stream_list
        wait_for(app, lambda: listing.model.rowCount() == 50)
        listing.next.click()
        wait_for(app, lambda: listing.page == 2 and listing.model.rowCount() == 5)
        listing.name_search.setText("Gate Stream 000")
        listing.name_search.returnPressed.emit()
        wait_for(app, lambda: listing.model.rowCount() == 1)
        listing.name_search.clear()
        listing.apply_search()
        wait_for(app, lambda: listing.model.rowCount() == 50)
        wait_for(app, lambda: listing.regions["province"].count() == 2)
        listing.regions["province"].setCurrentIndex(1)
        wait_for(app, lambda: listing.regions["city_county"].count() == 3)
        listing.regions["city_county"].setCurrentIndex(1)
        wait_for(app, lambda: listing.status.text() == "전체 30건")
        listing.table.selectRow(0)
        wait_for(app, lambda: listing.detail_button.isEnabled())
        listing.detail_button.click()

        detail = window.stream_detail
        wait_for(app, lambda: detail.status.text() == "읽기 전용 상세정보")
        assert detail.category.count() == 5
        for category in range(detail.category.count()):
            detail.category.setCurrentIndex(category)
            app.processEvents()
            assert detail.model.rowCount() > 0
        detail.category.setCurrentIndex(1)
        detail.table.selectRow(0)
        for tab in range(detail.detail_tabs.count()):
            detail.detail_tabs.setCurrentIndex(tab)
            app.processEvents()
        detail.back.click()
        window.navigate("홈")
        wait_for(app, lambda: home.stream_count.text() == "55건")

        window.navigate("작업이력")
        history = window.work_history
        wait_for(app, lambda: history.table.rowCount() == 50 and history.actor.count() == 2)
        history.next.click()
        wait_for(app, lambda: history.page == 2 and history.table.rowCount() == 5)
        history.change_type.setCurrentIndex(history.change_type.findData("CORRECTION"))
        history.actor.setCurrentIndex(history.actor.findData(user.user_id))
        history.stream_code.setText(PRIMARY_STREAM)
        history.search_button.click()
        wait_for(app, lambda: history.page == 1 and history.table.rowCount() == 11)

        window.navigate("홈")
        window.user_button.click()
        my_page = window.my_page
        wait_for(app, lambda: my_page.profile_values["login_id"].text() == "gate.user")
        assert my_page.recent.rowCount() == 5
        my_page.history_button.click()
        wait_for(app, lambda: window.stack.currentWidget() is history)
        assert history.actor.currentData() == user.user_id
        assert history.change_type.currentData() is None
        assert history.stream_code.text() == ""
        assert snapshot(controller.db_path) == before

        window.navigate("홈")
        window.resize(900, 600)
        app.processEvents()
        assert home._card_mode == "compact"
        window.logout_button.click()
        app.processEvents()
        assert controller.session is None and controller.login_window.isVisible()
    finally:
        controller.close()
        app.processEvents()


def test_fresh_registration_validation_login_and_home(tmp_path, app):
    controller = ApplicationController(tmp_path / "fresh-registration.sqlite3")
    controller.start()
    setup = controller.login_window
    assert setup.initial_setup
    setup.login_id.setText(" Gate.User ")
    setup.password.setText("short")
    setup.display_name.setText("Gate User")
    setup.submit.click()
    app.processEvents()
    assert controller.auth_service.needs_initial_user_setup()
    assert setup.password.text() == ""

    setup.password.setText("synthetic-gate-password")
    setup.department.setText("")
    setup.submit.click()
    app.processEvents()
    login_window = controller.login_window
    assert not login_window.initial_setup
    assert login_window.password.echoMode() == QLineEdit.EchoMode.Password
    login_window.login_id.setText("gate.user")
    login_window.password.setText("synthetic-gate-password")
    login_window.submit.click()
    wait_for(app, lambda: controller.main_window is not None)
    assert controller.main_window.stack.currentWidget() is controller.main_window.home
    assert controller.session.department is None
    controller.close()
    app.processEvents()


@pytest.mark.parametrize("argument", (None, "--help", "--version"))
def test_import_and_metadata_commands_do_not_create_database(tmp_path, argument):
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "isolated-local")
    env["QT_QPA_PLATFORM"] = "offscreen"
    if argument is None:
        command = [
            sys.executable,
            "-c",
            "import small_stream_research_tool.app.main; "
            "from PySide6.QtWidgets import QApplication; "
            "assert QApplication.instance() is None",
        ]
    else:
        command = [sys.executable, "-m", "small_stream_research_tool", argument]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "isolated-local").exists()


def test_phase_9_ui_layer_and_smoke_tool_guards_are_preserved():
    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    ui = root / "src" / "small_stream_research_tool" / "ui"
    for path in ui.glob("*.py"):
        if path.name == "workers.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "sqlite3" not in source
        assert "Repository" not in source
        assert "SELECT " not in source
        assert "INSERT " not in source
        assert "UPDATE " not in source
        assert "DELETE " not in source
    smoke = (root / "tools" / "ui_smoke.py").read_text(encoding="utf-8")
    assert "기존 DB를 덮어쓰지 않습니다" in smoke
    assert "기본 local DB 경로는 smoke DB로 사용할 수 없습니다" in smoke
    assert 'path.parent != build or "ui_smoke" not in path.stem.lower()' in smoke
