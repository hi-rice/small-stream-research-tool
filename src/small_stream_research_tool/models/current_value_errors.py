"""현재값 선택의 안전한 domain 오류. 원본 입력/SQL은 포함하지 않는다."""


class CurrentValueSelectionError(Exception):
    def __init__(self):
        super().__init__("현재 사용값 선택 입력과 자료 연결을 확인해야 합니다.")


class CurrentValueBlockedByQualityError(CurrentValueSelectionError):
    def __init__(self):
        Exception.__init__(self, "활성 ERROR가 있는 값은 현재 사용값으로 선택할 수 없습니다.")


class CurrentValueConfirmationRequiredError(CurrentValueSelectionError):
    def __init__(self):
        Exception.__init__(self, "활성 WARNING/INFO를 확인한 뒤 명시적 선택 확인이 필요합니다.")


class CurrentValueInvariantError(CurrentValueSelectionError):
    def __init__(self):
        Exception.__init__(self, "현재 사용값 flag와 참조 캐시의 일관성을 확인해야 합니다.")


class CurrentValuePersistenceError(CurrentValueSelectionError):
    def __init__(self):
        Exception.__init__(self, "현재 사용값 선택을 저장할 수 없습니다.")
