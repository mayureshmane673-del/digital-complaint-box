"""
tests/test_storage.py: Unit tests for attachment validation and constraints.
"""

from utils.validators import validate_attachment, MAX_ATTACHMENT_SIZE_BYTES


def test_attachment_allowed_extensions():
    # Valid formats
    valid_files = ["photo.jpg", "diagram.PNG", "scan.webp", "video.mp4", "clip.MOV", "doc.pdf"]
    for f in valid_files:
        ok, _ = validate_attachment(f, 500000)
        assert ok, f"Expected {f} to be allowed"

    # Disallowed dangerous formats
    invalid_files = ["script.exe", "virus.bat", "trojan.sh", "code.py", "exploit.js", "archive.zip"]
    for f in invalid_files:
        ok, err = validate_attachment(f, 500000)
        assert not ok, f"Expected {f} to be rejected"
        assert "not allowed" in err


def test_attachment_file_size_limits():
    # 5 MB -> OK
    ok, _ = validate_attachment("photo.jpg", 5 * 1024 * 1024)
    assert ok

    # 11 MB -> Exceeds 10 MB limit
    ok, err = validate_attachment("photo.jpg", 11 * 1024 * 1024)
    assert not ok
    assert "exceeds 10 MB limit" in err

    # 0 bytes -> Empty file rejected
    ok, err = validate_attachment("photo.jpg", 0)
    assert not ok
    assert "cannot be empty" in err
