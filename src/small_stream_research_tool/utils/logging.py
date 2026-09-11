"""앱 전용 콘솔 로깅. 비밀값·원본자료·사용자 경로는 호출부에서 기록하지 않는다."""

import logging

LOGGER_NAME = "small_stream_research_tool"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def configure_logging(level: str = "INFO") -> None:
    """모듈 logger를 앱 logger에 모으며 외부/root logger 설정은 변경하지 않는다."""
    if level not in LOG_LEVELS:
        raise ValueError("Unsupported log level")
    app_logger = logging.getLogger(LOGGER_NAME)
    app_logger.setLevel(level)
    app_logger.propagate = False
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        app_logger.addHandler(handler)
