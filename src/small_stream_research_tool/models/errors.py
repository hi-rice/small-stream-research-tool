"""입력값·비밀번호·hash를 메시지에 포함하지 않는 애플리케이션 오류."""


class UserError(Exception):
    """사용자/인증 처리 오류의 공통 기반."""


class InvalidLoginIdError(UserError):
    pass


class DuplicateLoginIdError(UserError):
    pass


class InvalidPasswordError(UserError):
    pass


class InvalidUserProfileError(UserError):
    pass


class AuthenticationError(UserError):
    pass


class InactiveUserError(AuthenticationError):
    pass


class UserNotFoundError(UserError):
    pass
