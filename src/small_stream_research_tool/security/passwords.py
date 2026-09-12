"""Argon2id 처리. salt/encoding은 argon2-cffi가 관리한다."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.profiles import RFC_9106_LOW_MEMORY

from small_stream_research_tool.models.errors import InvalidPasswordError

MIN_PASSWORD_LENGTH = 15
_hasher = PasswordHasher.from_parameters(RFC_9106_LOW_MEMORY)


def validate_password(password: str) -> None:
    """최소 15자, 공백만 있는 값 거부. trim/정규화/문자 종류 제한은 없다."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH or not password.strip():
        raise InvalidPasswordError("비밀번호는 공백만으로 구성할 수 없으며 15자 이상이어야 합니다.")
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidPasswordError("비밀번호 문자열 형식이 올바르지 않습니다.") from None


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    """불일치/잘못된 hash는 실패로 처리하며 입력값을 기록하지 않는다."""
    if not isinstance(password, str) or not isinstance(encoded_hash, str):
        return False
    try:
        return _hasher.verify(encoded_hash, password)
    except (VerificationError, InvalidHashError, UnicodeError):
        return False
