"""원시 연구값·SQL·경로를 포함하지 않는 보정 오류."""


class CorrectionError(Exception):
    def __init__(self):
        super().__init__("보정 요청을 처리할 수 없습니다.")


class CorrectionValidationError(CorrectionError):
    def __init__(self):
        Exception.__init__(self, "보정 대상, 작업자 또는 입력값이 유효하지 않습니다.")


class CorrectionPersistenceError(CorrectionError):
    def __init__(self):
        Exception.__init__(self, "보정값과 이력을 저장할 수 없습니다.")
