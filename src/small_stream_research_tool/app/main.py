"""명시적 호출 시에만 PySide6 앱과 DB workflow를 시작한다."""

import argparse
import logging
from collections.abc import Sequence
from importlib.metadata import version

from small_stream_research_tool.config.settings import APP_ID, APP_NAME, get_app_paths
from small_stream_research_tool.utils.logging import LOG_LEVELS, configure_logging

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_ID, description=APP_NAME)
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {version(APP_ID)}")
    parser.add_argument("--log-level", choices=LOG_LEVELS, default="INFO")
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    try:
        db_path = get_app_paths().database_dir / "research.sqlite3"
    except ValueError:
        # 환경값·사용자 경로·예외 원문을 로그에 노출하지 않는다.
        logger.error("앱 데이터 경로 설정이 올바르지 않습니다.")
        return 1
    # CLI metadata 명령과 모듈 import는 Qt/DB를 시작하지 않는다.
    from PySide6.QtWidgets import QApplication

    from small_stream_research_tool.app.controller import ApplicationController
    from small_stream_research_tool.ui.theme import STYLESHEET

    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLESHEET)
    try:
        controller = ApplicationController(db_path)
        controller.start()
    except Exception:
        logger.error("프로그램 시작 중 오류가 발생했습니다.")
        return 1
    app.aboutToQuit.connect(controller.close)
    return app.exec()
