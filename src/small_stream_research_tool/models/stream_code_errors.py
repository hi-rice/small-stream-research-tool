"""원본 검증 실패와 구분하는 API 계약 오류."""


class StreamCodeArgumentError(Exception):
    """구성요소 이름·기대 길이·서식 인자 등 API 사용이 올바르지 않다."""
