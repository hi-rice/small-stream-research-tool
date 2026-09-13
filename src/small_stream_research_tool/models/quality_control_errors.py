"""입력/설정/저장 오류를 연구값 오류와 구분한다."""


class QualityControlError(Exception):
    def __init__(self):
        super().__init__("QC 실행 입력 또는 자료 연결을 확인해야 합니다.")


class QualityRuleConfigurationError(QualityControlError):
    def __init__(self):
        Exception.__init__(self, "QC 규칙의 대상·자료형·설정을 확인해야 합니다.")


class QualityControlPersistenceError(QualityControlError):
    def __init__(self):
        Exception.__init__(self, "QC 저장소 작업을 완료할 수 없습니다.")
