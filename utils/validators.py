"""
utils/validators.py: Production validation routines for passwords, attachments, and complaint inputs.
"""

import re
import os
from typing import Tuple

ALLOWED_ATTACHMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".pdf"}
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "video/mp4", "video/quicktime", "application/pdf"
}
MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validates password against rules:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character (!@#$%^&*...)."
    return True, "Password meets all security criteria."


def validate_roll_number(roll_number: str) -> Tuple[bool, str]:
    """Validates student roll number / ID format."""
    clean = roll_number.strip()
    if not clean:
        return False, "Roll number cannot be empty."
    if len(clean) < 3 or len(clean) > 30:
        return False, "Roll number must be between 3 and 30 characters."
    if not re.match(r"^[A-Za-z0-9_-]+$", clean):
        return False, "Roll number can only contain letters, numbers, hyphens, and underscores."
    return True, ""


def validate_description(description: str) -> Tuple[bool, str]:
    """Validates complaint description (10 to 1000 characters)."""
    clean = description.strip()
    if len(clean) < 10:
        return False, "Description must be at least 10 characters."
    if len(clean) > 1000:
        return False, "Description cannot exceed 1000 characters."
    return True, ""


def validate_attachment(file_name: str, file_size: int, mime_type: str = "") -> Tuple[bool, str]:
    """
    Validates file attachment against security constraints:
    - Allowed extension: JPG, JPEG, PNG, WEBP, MP4, MOV, PDF
    - Max size: 10MB
    - Blocks dangerous executables/scripts
    """
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
        return False, f"File format '{ext}' is not allowed. Supported formats: JPG, PNG, WEBP, MP4, MOV, PDF."
    
    if file_size <= 0:
        return False, "File cannot be empty."
    if file_size > MAX_ATTACHMENT_SIZE_BYTES:
        return False, f"File size exceeds 10 MB limit ({file_size / (1024*1024):.2f} MB)."
        
    if mime_type and mime_type.lower() not in ALLOWED_MIME_TYPES:
        # If mime type is supplied, check it matches known allowed types
        return False, f"MIME type '{mime_type}' is not supported."
        
    return True, ""
