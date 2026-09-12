"""실제 계정과 무관한 입력·암호 처리 검증."""

import pytest
from argon2 import extract_parameters
from argon2.low_level import Type

from small_stream_research_tool.models.errors import InvalidLoginIdError, InvalidPasswordError
from small_stream_research_tool.security.passwords import hash_password, verify_password
from small_stream_research_tool.services.auth_service import normalize_login_id


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Researcher_01  ", "researcher_01"),
        ("\tAB.c-d_01\n", "ab.c-d_01"),
        ("a._-", "a._-"),
        ("A" * 50, "a" * 50),
    ],
)
def test_login_normalization(raw, expected):
    assert normalize_login_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "abc",
        "a" * 51,
        "test user",
        "test@id",
        "한글계정",
        "test\0",
        "test\nuser",
        "Ktest",
        "",
        None,
        123,
    ],
)
def test_invalid_login_id(raw):
    with pytest.raises(InvalidLoginIdError):
        normalize_login_id(raw)


def test_argon2id_hash_salt_and_verification():
    password = "synthetic long test passphrase"
    first, second = hash_password(password), hash_password(password)
    assert first != second and first != password
    assert password not in first
    params = extract_parameters(first)
    assert params.type == Type.ID
    assert (params.memory_cost, params.time_cost, params.parallelism) == (65536, 3, 4)
    assert verify_password(password, first)
    assert not verify_password("wrong synthetic password", first)


@pytest.mark.parametrize(
    "password", ["", " " * 20, "\t\n" * 10, "a" * 14, None, b"synthetic", "a" * 15 + "\ud800"]
)
def test_invalid_password(password):
    with pytest.raises(InvalidPasswordError):
        hash_password(password)


@pytest.mark.parametrize(
    "password",
    ["a" * 15, "a" * 100, "가상 비밀번호를 검증하는 문장입니다", "  synthetic test passphrase  "],
)
def test_password_boundaries_unicode_and_spaces(password):
    encoded = hash_password(password)
    assert verify_password(password, encoded)
    if password != password.strip():
        assert not verify_password(password.strip(), encoded)


@pytest.mark.parametrize("encoded", ["", "not-a-hash", "$argon2id$invalid", None])
def test_invalid_hash_is_authentication_failure(encoded):
    assert not verify_password("synthetic test passphrase", encoded)
