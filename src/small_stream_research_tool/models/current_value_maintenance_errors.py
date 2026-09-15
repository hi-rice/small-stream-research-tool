"""현재값 유지관리 오류에는 연구값·SQL·경로를 포함하지 않는다."""


class CurrentValueMaintenanceError(Exception):
    def __init__(self):
        super().__init__("현재 사용값 유지관리 요청을 처리할 수 없습니다.")


class MaintenanceValidationError(CurrentValueMaintenanceError):
    def __init__(self):
        Exception.__init__(self, "유지관리 대상 또는 작업자를 확인해야 합니다.")


class CurrentUseLossConfirmationRequiredError(CurrentValueMaintenanceError):
    def __init__(self):
        Exception.__init__(self, "현재 사용값 해제를 명시적으로 확인해야 합니다.")


class MaintenanceInvariantError(CurrentValueMaintenanceError):
    def __init__(self):
        Exception.__init__(self, "대표값과 참조 캐시의 일관성을 확인해야 합니다.")


class MaintenancePersistenceError(CurrentValueMaintenanceError):
    def __init__(self):
        Exception.__init__(self, "현재 사용값 유지관리 변경을 저장할 수 없습니다.")
