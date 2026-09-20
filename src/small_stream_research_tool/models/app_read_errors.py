"""민감한 DB·인증 세부정보를 노출하지 않는 Phase 9D 조회 오류."""


class AppReadError(Exception):
    def __init__(self, message="화면 정보를 조회할 수 없습니다."):
        super().__init__(message)


class InvalidAppReadRequest(AppReadError):
    def __init__(self):
        super().__init__("조회 조건을 확인해야 합니다.")


class AppReadFailure(AppReadError):
    pass


class UserProfileNotFound(AppReadError):
    def __init__(self):
        super().__init__("현재 사용자 정보를 찾을 수 없습니다.")


class InactiveUserProfile(AppReadError):
    def __init__(self):
        super().__init__("현재 계정은 비활성 상태입니다.")
