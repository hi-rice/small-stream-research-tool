"""시스템 시각만 다룬다. 연구자료 timezone은 추정하지 않는다."""

from datetime import UTC, datetime


def utc_now_text() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
