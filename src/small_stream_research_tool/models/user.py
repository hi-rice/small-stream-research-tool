"""공개 사용자 정보와 인증 저장 레코드를 구분한다."""

from dataclasses import dataclass, field, fields


@dataclass(frozen=True)
class User:
    user_id: int
    login_id: str
    display_name: str
    department: str | None
    role: str | None
    is_active: bool
    created_at: str
    updated_at: str
    last_login_at: str | None


@dataclass(frozen=True)
class UserRecord(User):
    """Repository/인증 내부 전용. repr에서도 hash를 제외한다."""

    password_hash: str = field(repr=False)

    def public_user(self) -> User:
        return User(**{item.name: getattr(self, item.name) for item in fields(User)})
