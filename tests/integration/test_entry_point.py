"""설치된 패키지 CLI와 합성 DB GUI 시작점을 저장소 밖에서 검증한다."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def run_application(tmp_path, command, *, local_app_data=None):
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "local") if local_app_data is None else local_app_data
    env["PYTHONIOENCODING"] = "utf-8"
    env["QT_QPA_PLATFORM"] = "offscreen"
    return subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )


@pytest.mark.parametrize("entry", ["module", "console"])
def test_installed_entry_points_show_metadata_without_data_files(tmp_path, entry):
    if entry == "module":
        command = [sys.executable, "-m", "small_stream_research_tool", "--help"]
    else:
        name = "small-stream-research-tool.exe" if os.name == "nt" else "small-stream-research-tool"
        command = [str(Path(sys.executable).with_name(name)), "--help"]
    result = run_application(tmp_path, command)
    assert result.returncode == 0, result.stderr
    assert "소하천 데이터 관리" in result.stdout
    assert str(tmp_path) not in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_gui_entry_initializes_synthetic_database(tmp_path):
    script = (
        "from PySide6.QtCore import QTimer; "
        "from PySide6.QtWidgets import QApplication; "
        "from small_stream_research_tool.app.main import main; "
        "app=QApplication([]); QTimer.singleShot(500, app.quit); "
        "raise SystemExit(main([]))"
    )
    result = run_application(tmp_path, [sys.executable, "-c", script])
    assert result.returncode == 0, result.stderr
    assert (
        tmp_path / "local" / "NDMI" / "small-stream-research-tool" / "db" / "research.sqlite3"
    ).exists()


def test_version_uses_installed_package_metadata(tmp_path):
    from importlib.metadata import version

    result = run_application(
        tmp_path, [sys.executable, "-m", "small_stream_research_tool", "--version"]
    )
    assert result.returncode == 0
    assert version("small-stream-research-tool") in result.stdout


def test_invalid_path_fails_without_exposing_environment_value(tmp_path):
    result = run_application(
        tmp_path,
        [sys.executable, "-m", "small_stream_research_tool"],
        local_app_data="synthetic-private-location",
    )
    assert result.returncode == 1
    assert "경로 설정" in result.stderr
    assert "synthetic-private-location" not in result.stderr
    assert "Traceback" not in result.stderr
    assert list(tmp_path.iterdir()) == []
