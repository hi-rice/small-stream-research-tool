"""Phase 0 개발환경 확인용 진입점. 업무 화면이나 DB를 만들지 않는다."""

import argparse
import logging
from collections.abc import Sequence
from importlib.metadata import version

from small_stream_research_tool.config.settings import APP_ID, APP_NAME, get_app_paths
from small_stream_research_tool.utils.logging import LOG_LEVELS, configure_logging

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """설정 접근과 로깅을 확인한 뒤 종료한다. 파일·디렉터리는 생성하지 않는다."""
    parser = argparse.ArgumentParser(prog=APP_ID, description=APP_NAME)
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {version(APP_ID)}")
    parser.add_argument("--log-level", choices=LOG_LEVELS, default="INFO")
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    try:
        get_app_paths()
    except ValueError:
        # 환경값·사용자 경로·예외 원문을 로그에 노출하지 않는다.
        logger.error("앱 데이터 경로 설정이 올바르지 않습니다.")
        return 1
    logger.info("%s: Phase 0 시작 확인 완료. 업무 기능은 아직 구현되지 않았습니다.", APP_NAME)
    return 0
