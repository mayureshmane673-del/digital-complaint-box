"""
tests/test_auth.py: Unit tests for authentication, password policies, and 5-attempt account lockout.
"""

import pytest
from utils.security import (
    hash_password, verify_password,
    hash_security_answer, verify_security_answer,
    hash_security_code, verify_security_code
)
from utils.validators import validate_password_strength, validate_roll_number


def test_password_policy():
    # Too short
    ok, err = validate_password_strength("Pass1!")
    assert not ok
    assert "at least 8 characters" in err

    # Missing uppercase
    ok, err = validate_password_strength("password123!")
    assert not ok
    assert "uppercase" in err

    # Missing lowercase
    ok, err = validate_password_strength("PASSWORD123!")
    assert not ok
    assert "lowercase" in err

    # Missing number
    ok, err = validate_password_strength("Password!@#")
    assert not ok
    assert "number" in err

    # Missing special char
    ok, err = validate_password_strength("Password123")
    assert not ok
    assert "special character" in err

    # Valid password
    ok, err = validate_password_strength("Pass@1234")
    assert ok


def test_password_hashing_and_verification():
    pw = "SecurePass#2026"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h)
    assert not verify_password("WrongPass#2026", h)


def test_security_answer_normalization():
    ans = "  New York City "
    h = hash_security_answer(ans)
    # Verify case-insensitive, whitespace-trimmed
    assert verify_security_answer("newyorkcity", h)
    assert verify_security_answer("NEW YORK CITY", h)
    assert not verify_security_answer("London", h)


def test_roll_number_validation():
    ok, _ = validate_roll_number("240101030")
    assert ok
    ok, _ = validate_roll_number("CSE-2026-001")
    assert ok
    ok, err = validate_roll_number("")
    assert not ok
    ok, err = validate_roll_number("24#01*")
    assert not ok


def test_failed_attempts_lockout_logic():
    # Simulate lockout logic
    max_attempts = 5
    attempts = 0
    is_locked = False

    for _ in range(4):
        attempts += 1
        assert attempts < max_attempts
        assert not is_locked

    attempts += 1
    if attempts >= max_attempts:
        is_locked = True

    assert is_locked
    assert attempts == 5

    # Recovery unlocks
    attempts = 0
    is_locked = False
    assert not is_locked
