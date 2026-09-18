import pytest

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import ApiError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("abcd1234")
    assert hashed != "abcd1234"
    assert verify_password("abcd1234", hashed)
    assert not verify_password("wrongpass", hashed)


def test_two_hashes_of_same_password_differ():
    assert hash_password("abcd1234") != hash_password("abcd1234")


def test_access_token_roundtrip():
    payload = decode_token(create_access_token(42))
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert payload["exp"] > payload["iat"]


def test_refresh_token_type():
    assert decode_token(create_refresh_token(42))["type"] == "refresh"


def test_expired_token_raises_token_expired():
    from datetime import timedelta

    token = create_access_token(1, ttl=timedelta(seconds=-1))
    with pytest.raises(ApiError) as exc:
        decode_token(token)
    assert exc.value.code == ErrorCode.TOKEN_EXPIRED
    assert exc.value.http_status == 401


def test_garbage_token_raises_token_invalid():
    with pytest.raises(ApiError) as exc:
        decode_token("not.a.jwt")
    assert exc.value.code == ErrorCode.TOKEN_INVALID


def test_token_signed_with_other_secret_rejected():
    from jose import jwt

    forged = jwt.encode(
        {"sub": "1", "type": "access", "exp": 9999999999},
        "another-secret",
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(ApiError) as exc:
        decode_token(forged)
    assert exc.value.code == ErrorCode.TOKEN_INVALID
