"""실제 사용자 설정이나 연구자료를 읽지 않는 설정 검증."""

import importlib
from pathlib import Path

import pytest

from small_stream_research_tool.config.settings import (
    APP_ID,
    APP_NAME,
    ORGANIZATION,
    get_app_paths,
)


def test_package_and_metadata():
    assert importlib.import_module("small_stream_research_tool") is not None
    assert APP_NAME == "소하천 데이터 관리"
    assert ORGANIZATION == "NDMI"
    assert APP_ID == "small-stream-research-tool"


def test_paths_use_local_app_data_without_creating_files(tmp_path, monkeypatch):
    base = tmp_path / "가상 사용자"
    monkeypatch.setenv("LOCALAPPDATA", str(base))
    paths = get_app_paths()
    assert paths.root == base / ORGANIZATION / APP_ID
    assert paths.database_dir == paths.root / "db"
    assert paths.workspace_dir == paths.root / "workspace"
    assert paths.backups_dir == paths.root / "backups"
    assert not base.exists()


def test_missing_local_app_data_uses_home(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert get_app_paths().root == tmp_path / "AppData" / "Local" / ORGANIZATION / APP_ID
    assert list(tmp_path.iterdir()) == []


def test_relative_local_app_data_is_rejected(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", "relative-location")
    with pytest.raises(ValueError, match="absolute"):
        get_app_paths()
