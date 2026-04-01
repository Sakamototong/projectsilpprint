"""Unit tests สำหรับ security module"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_app.db")

from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
import pytest

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    validate_password,
    SECRET_KEY,
    ALGORITHM,
    MIN_PASSWORD_LENGTH,
)


# -- password hashing --

def test_hash_password_returns_bcrypt_string():
    h = hash_password("Test1234")
    assert h.startswith("$2")
    assert len(h) > 50


def test_verify_password_correct():
    h = hash_password("Hello123")
    assert verify_password("Hello123", h)


def test_verify_password_wrong():
    h = hash_password("Hello123")
    assert not verify_password("Wrong999", h)


def test_hash_password_unique_salts():
    h1 = hash_password("Same1234")
    h2 = hash_password("Same1234")
    assert h1 != h2  # different salts


# -- JWT tokens --

def test_create_and_decode_token():
    token = create_access_token({"sub": "42", "store_name": "TestShop"})
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["store_name"] == "TestShop"
    assert "exp" in payload


def test_decode_invalid_token():
    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")


def test_decode_expired_token():
    data = {"sub": "1"}
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode({**data, "exp": expired}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(JWTError):
        decode_token(token)


# -- validate_password --

def test_validate_password_too_short():
    err = validate_password("Ab1")
    assert err is not None
    assert str(MIN_PASSWORD_LENGTH) in err


def test_validate_password_all_digits():
    err = validate_password("12345678")
    assert err is not None


def test_validate_password_all_alpha():
    err = validate_password("abcdefgh")
    assert err is not None


def test_validate_password_ok():
    assert validate_password("Test1234") is None


def test_validate_password_boundary():
    # Exactly MIN_PASSWORD_LENGTH chars, mixed
    pwd = "A" * (MIN_PASSWORD_LENGTH - 1) + "1"
    assert validate_password(pwd) is None
    # One char too short
    pwd_short = "A" * (MIN_PASSWORD_LENGTH - 2) + "1"
    assert validate_password(pwd_short) is not None
