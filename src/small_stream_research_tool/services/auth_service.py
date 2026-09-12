"""로컬 인증 백엔드. 세션/GUI/권한 모델과 자동 복구를 제공하지 않는다."""

import re

from small_stream_research_tool.models.errors import (
    AuthenticationError,
    DuplicateLoginIdError,
    InactiveUserError,
    InvalidLoginIdError,
    InvalidUserProfileError,
    UserNotFoundError,
)
from small_stream_research_tool.models.user import User, UserRecord
from small_stream_research_tool.repositories.user_repository import UserRepository
from small_stream_research_tool.security.passwords import hash_password, verify_password
from small_stream_research_tool.utils.timestamps import utc_now_text


def normalize_login_id(raw_login_id: str) -> str:
    if not isinstance(raw_login_id, str):
        raise InvalidLoginIdError("로그인 ID 형식이 올바르지 않습니다.")
    trimmed = raw_login_id.strip()
    normalized = trimmed.lower()
    if not trimmed.isascii() or re.fullmatch(r"[a-z0-9._-]{4,50}", normalized) is None:
        raise InvalidLoginIdError("로그인 ID는 영문·숫자·점·밑줄·하이픈으로 4~50자여야 합니다.")
    return normalized


class AuthService:
    """동일 Repository 연결로 읽기/검증/쓰기를 하나의 transaction에서 처리한다.

    생성·활성화 API는 향후 앱 workflow가 호출하는 기반이며 관리자 권한을 뜻하지 않는다.
    반환 User에는 hash가 없으며, 현재 사용자/세션을 내부에 유지하지 않는다.
    """

    def __init__(self, repository: UserRepository):
        self._repository = repository

    def needs_initial_user_setup(self) -> bool:
        # 비활성 계정도 기존 사용자다. 비활성화를 초기 설치로 취급하지 않는다.
        return self._repository.count_users() == 0

    def create_user(
        self,
        login_id: str,
        password: str,
        display_name: str,
        department: str | None = None,
        role: str | None = None,
    ) -> User:
        normalized = normalize_login_id(login_id)
        if not isinstance(display_name, str) or not display_name.strip():
            raise InvalidUserProfileError("표시명은 필수입니다.")
        if any(value is not None and not isinstance(value, str) for value in (department, role)):
            raise InvalidUserProfileError("부서와 역할은 문자열 또는 NULL이어야 합니다.")
        with self._repository.transaction():
            if self._repository.find_by_login_id(normalized) is not None:
                raise DuplicateLoginIdError("이미 등록된 로그인 ID입니다.")
            encoded = hash_password(password)
            user = self._repository.create_user(
                login_id=normalized,
                password_hash=encoded,
                display_name=display_name,
                department=department,
                role=role,
                timestamp=utc_now_text(),
            )
        return user.public_user()

    @staticmethod
    def _check_active(user: UserRecord | None) -> UserRecord:
        if user is None:
            raise UserNotFoundError("사용자를 찾을 수 없습니다.")
        if not user.is_active:
            raise InactiveUserError("비활성 계정입니다.")
        return user

    def authenticate(self, login_id: str, password: str) -> User:
        normalized = normalize_login_id(login_id)
        with self._repository.transaction():
            user = self._check_active(self._repository.find_by_login_id(normalized))
            if not verify_password(password, user.password_hash):
                raise AuthenticationError("아이디 또는 비밀번호가 올바르지 않습니다.")
            self._repository.update_last_login_at(user.user_id, utc_now_text())
            result = self._check_active(self._repository.find_by_user_id(user.user_id))
        return result.public_user()

    def change_password(self, user_id: int, current_password: str, new_password: str) -> None:
        with self._repository.transaction():
            user = self._check_active(self._repository.find_by_user_id(user_id))
            if not verify_password(current_password, user.password_hash):
                raise AuthenticationError("현재 비밀번호가 올바르지 않습니다.")
            encoded = hash_password(new_password)
            self._repository.update_password_hash(user_id, encoded, utc_now_text())

    def set_active(self, user_id: int, is_active: bool) -> None:
        """계정을 보존한 상태 변경. 로그인이나 비밀번호 복구를 수행하지 않는다."""
        with self._repository.transaction():
            self._repository.set_active(user_id, is_active, utc_now_text())
