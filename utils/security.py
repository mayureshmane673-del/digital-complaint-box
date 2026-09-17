"""
utils/security.py: Secure hashing and verification routines using bcrypt and SHA-256 HMAC.
Ensures no plaintext passwords, codes, or security answers are stored or logged.
"""

import os
import hmac
import hashlib
import bcrypt
from typing import Optional

def get_pepper() -> bytes:
    """Returns the HMAC-SHA256 pepper from APP_SECRET_KEY environment variable."""
    return os.getenv("APP_SECRET_KEY", "").encode("utf-8")


def hash_password(password: str) -> str:
    """Hashes a password using bcrypt with a secure salt, applying HMAC pepper if configured."""
    if not password:
        raise ValueError("Password cannot be empty")
    pw_bytes = password.encode("utf-8")
    pepper = get_pepper()
    if pepper:
        prep = hmac.new(pepper, pw_bytes, hashlib.sha256).digest()
    else:
        prep = pw_bytes
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(prep, salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifies a plaintext password against a bcrypt hash.
    Supports:
    1. HMAC-SHA256 peppered bcrypt (using APP_SECRET_KEY from environment)
    2. Raw unpeppered bcrypt hashes (for initial database seeds)
    """
    if not password or not hashed:
        return False

    pw_bytes = password.encode("utf-8")
    hash_bytes = hashed.encode("utf-8")
    pepper = get_pepper()

    # 1. Verify with environment pepper if configured
    if pepper:
        try:
            prep = hmac.new(pepper, pw_bytes, hashlib.sha256).digest()
            if bcrypt.checkpw(prep, hash_bytes):
                return True
        except Exception:
            pass

    # 2. Verify with raw unpeppered bcrypt for initial DB seed hashes
    try:
        if bcrypt.checkpw(pw_bytes, hash_bytes):
            return True
    except Exception:
        pass

    return False


def normalize_security_answer(answer: str) -> str:
    """Normalizes security answer: trims whitespace, removes internal spaces and converts to lowercase."""
    return "".join(answer.strip().lower().split())


def hash_security_answer(answer: str) -> str:
    """Hashes a security answer after case-insensitive normalization."""
    normalized = normalize_security_answer(answer)
    return hash_password(normalized)


def verify_security_answer(answer: str, hashed: str) -> bool:
    """Verifies a security answer against its stored hash."""
    normalized = normalize_security_answer(answer)
    return verify_password(normalized, hashed)


def hash_security_code(code: str) -> str:
    """Hashes a staff security code."""
    return hash_password(code.strip())


def verify_security_code(code: str, hashed: str) -> bool:
    """Verifies a staff security code."""
    return verify_password(code.strip(), hashed)


def generate_anonymous_token(student_id: str, complaint_title: str) -> str:
    """
    Generates a deterministic privacy-preserving ownership token hash.
    Allows the student's authenticated session to discover their own anonymous complaint,
    while being cryptographically irreversible and opaque to staff.
    """
    msg = f"{student_id}:{complaint_title}".encode("utf-8")
    return hmac.new(get_pepper(), msg, hashlib.sha256).hexdigest()


def sanitize_user_dict(user: Optional[dict]) -> Optional[dict]:
    """Strips password_hash, security_answer_hash, and code_hash from user dictionary."""
    if not user:
        return None
    safe = dict(user)
    safe.pop("password_hash", None)
    safe.pop("security_answer_hash", None)
    safe.pop("code_hash", None)
    return safe
