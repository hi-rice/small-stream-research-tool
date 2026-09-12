"""Import 준비의 API 오류와 원본을 포함하지 않는 변환 실패."""


class InvalidPreparationArgumentError(ValueError):
    """준비 API/model의 구조적 계약 위반."""


class ValueNormalizationError(ValueError):
    """변환 실패 분류만 전달한다. 원본 값은 보관하지 않는다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
