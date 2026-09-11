"""경로 계산만 제공한다. 디렉터리 생성과 DB 접근은 수행하지 않는다."""

import os
from dataclasses import dataclass
from pathlib import Path

APP_ID = "small-stream-research-tool"
APP_NAME = "소하천 데이터 관리"
ORGANIZATION = "NDMI"


@dataclass(frozen=True)
class AppPaths:
    """후속 Phase에서 사용할 로컬 저장 위치의 공통 기준."""

    root: Path

    @property
    def database_dir(self) -> Path:
        return self.root / "db"

    @property
    def workspace_dir(self) -> Path:
        return self.root / "workspace"

    @property
    def backups_dir(self) -> Path:
        return self.root / "backups"


def get_app_paths() -> AppPaths:
    """Windows LOCALAPPDATA를 사용하며 미설정 시 사용자 홈 기준으로 계산한다."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    if not base.is_absolute():
        raise ValueError("App data base must be absolute")
    return AppPaths(root=base / ORGANIZATION / APP_ID)
