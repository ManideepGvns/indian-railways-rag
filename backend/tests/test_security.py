"""Unit tests for the security module."""
from __future__ import annotations
import pytest
import time
from datetime import timedelta

from app.core.security import (
    hash_password, verify_password, create_access_token, decode_token
)


def test_hash_and_verify():
    hashed = hash_password("Admin@123")
    assert verify_password("Admin@123", hashed)
    assert not verify_password("wrong", hashed)


def test_hash_is_bcrypt():
    h = hash_password("test")
    assert h.startswith("$2b$") or h.startswith("$2a$")


def test_create_and_decode_token():
    token = create_access_token({"sub": "42"})
    payload = decode_token(token)
    assert payload["sub"] == "42"


def test_expired_token_raises():
    from jose import JWTError
    token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(JWTError):
        decode_token(token)


def test_tampered_token_raises():
    from jose import JWTError
    token = create_access_token({"sub": "1"})
    tampered = token[:-4] + "XXXX"
    with pytest.raises(JWTError):
        decode_token(tampered)
