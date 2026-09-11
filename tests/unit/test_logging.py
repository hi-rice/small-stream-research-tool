"""중복 로그와 다른 라이브러리의 로깅 설정 변경을 방지한다."""

import logging

import pytest

from small_stream_research_tool.utils.logging import LOGGER_NAME, configure_logging


def test_module_logging_level_and_repeated_setup(monkeypatch, capsys):
    app_logger = logging.getLogger(LOGGER_NAME)
    monkeypatch.setattr(app_logger, "handlers", [])
    monkeypatch.setattr(app_logger, "level", logging.NOTSET)
    monkeypatch.setattr(app_logger, "propagate", True)
    root_handlers = list(logging.getLogger().handlers)
    configure_logging("INFO")
    configure_logging("WARNING")
    module_logger = logging.getLogger(f"{LOGGER_NAME}.synthetic")
    module_logger.info("hidden-message")
    module_logger.warning("visible-message")
    captured = capsys.readouterr()
    assert captured.err.count("visible-message") == 1
    assert "hidden-message" not in captured.err
    assert len(app_logger.handlers) == 1
    assert logging.getLogger().handlers == root_handlers


def test_invalid_logging_level():
    with pytest.raises(ValueError, match="Unsupported"):
        configure_logging("INVALID")
