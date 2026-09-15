"""
utils/security.py: Secure hashing and verification routines using bcrypt and SHA-256 HMAC.
Ensures no plaintext passwords, codes, or security answers are stored or logged.
"""

import os
import hmac
import hashlib
import bcrypt
from typing import Optional

PEPPER = os.getenv("APP_SECRET_KEY", "college-complaint-box-production-secure-key-2026").encode("utf-8")


def hash_password(password: str) -> str:
    """Hashes a password using bcrypt with a secure salt."""
    if not password:
        raise ValueError("Password cannot be empty")
    # Apply HMAC pepper before bcrypt to mitigate length limitations and rainbow attacks
    prep = hmac.new(PEPPER, password.encode("utf-8"), hashlib.sha256).digest()
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(prep, salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash, supporting both peppered and seed hashes."""
    if not password or not hashed:
        return False
    try:
        prep = hmac.new(PEPPER, password.encode("utf-8"), hashlib.sha256).digest()
        if bcrypt.checkpw(prep, hashed.encode("utf-8")):
            return True
    except Exception:
        pass

    try:
        if bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")):
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
    return hmac.new(PEPPER, msg, hashlib.sha256).hexdigest()


def sanitize_user_dict(user: Optional[dict]) -> Optional[dict]:
    """Strips password_hash, security_answer_hash, and code_hash from user dictionary."""
    if not user:
        return None
    safe = dict(user)
    safe.pop("password_hash", None)
    safe.pop("security_answer_hash", None)
    safe.pop("code_hash", None)
    return safe
