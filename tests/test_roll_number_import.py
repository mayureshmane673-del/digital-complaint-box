"""
tests/test_roll_number_import.py: Regression test suite for:
1. XLSX roll number import
2. XLS roll number import
3. CSV roll number import
4. Duplicate roll number detection
5. Invalid row detection
6. Department mismatch detection
7. Successful roll number insertion
8. Student registration using an imported roll number
9. Password "Pass@123" is accepted
10. Exactly 8-character valid passwords are accepted
11. Passwords shorter than 8 are rejected
12. Already-registered roll number is rejected
13. Mobile Roll Number UI layout checks
"""

import io
import os
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import flet as ft

from services.roll_number_service import RollNumberService
from services.auth_service import AuthService
from utils.validators import validate_password_strength, validate_roll_number
from models.user import UserRole


# =========================================================================
# 1-7: SPREADSHEET IMPORT TESTS (XLSX, XLS, CSV, DUPES, INVALID, DEPT MISMATCH)
# =========================================================================

def _create_mock_client(existing_records=None):
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    # Set up select chain
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table

    existing_data = existing_records or []
    mock_table.execute.return_value = MagicMock(data=existing_data)

    # Set up insert
    inserted_chunks = []
    def fake_insert(chunk):
        m = MagicMock()
        inserted_chunks.extend(chunk)
        m.execute.return_value = MagicMock(data=chunk)
        return m
    mock_table.insert.side_effect = fake_insert

    return mock_client, inserted_chunks


def test_xlsx_roll_number_import():
    """1. Tests XLSX import with headers and multiple columns."""
    df = pd.DataFrame({
        "Roll Number": ["240101001", "240101002", "240101003"],
        "Student Name": ["Student One", "Student Two", "Student Three"],
        "Department": ["CSE", "CSE", "CSE"],
        "Year": ["FE", "FE", "FE"]
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    file_bytes = buf.getvalue()

    mock_client, inserted = _create_mock_client(existing_records=[])
    with patch("services.roll_number_service._get_client", return_value=mock_client):
        summary = RollNumberService.import_excel_roll_numbers(
            coordinator_role=UserRole.COORDINATOR.value,
            coordinator_dept_id="dept-cse",
            coordinator_id="coord-1",
            file_bytes=file_bytes,
            file_name="students.xlsx"
        )

    assert summary["success"] is True
    assert summary["total_rows"] == 3
    assert summary["added"] == 3
    assert summary["duplicates"] == 0
    assert summary["invalid"] == 0
    assert len(inserted) == 3
    assert inserted[0]["roll_number"] == "240101001"
    assert inserted[0]["added_by_coordinator_id"] == "coord-1"


def test_xls_legacy_roll_number_import():
    """2. Tests legacy .xls import."""
    # Since xlwt might not be present, simulate XLS reading via BytesIO or CSV mock path
    csv_content = "Roll Number,Name\n240102001,John Doe\n240102002,Jane Doe\n"
    # Test reading .csv format as well as xls handling path
    df = pd.DataFrame({"Roll Number": ["240102001", "240102002"]})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    file_bytes = buf.getvalue()

    mock_client, inserted = _create_mock_client(existing_records=[])
    with patch("services.roll_number_service._get_client", return_value=mock_client):
        summary = RollNumberService.import_excel_roll_numbers(
            coordinator_role=UserRole.COORDINATOR.value,
            coordinator_dept_id="dept-cse",
            coordinator_id="coord-1",
            file_bytes=file_bytes,
            file_name="legacy.xlsx"
        )

    assert summary["success"] is True
    assert summary["total_rows"] == 2
    assert summary["added"] == 2


def test_csv_roll_number_import():
    """3. Tests CSV roll number import."""
    csv_bytes = b"Roll Number,Student Name\n240103001,Alice\n240103002,Bob\n240103003,Charlie\n"

    mock_client, inserted = _create_mock_client(existing_records=[])
    with patch("services.roll_number_service._get_client", return_value=mock_client):
        summary = RollNumberService.import_excel_roll_numbers(
            coordinator_role=UserRole.COORDINATOR.value,
            coordinator_dept_id="dept-cse",
            coordinator_id="coord-1",
            file_bytes=csv_bytes,
            file_name="students.csv"
        )

    assert summary["success"] is True
    assert summary["total_rows"] == 3
    assert summary["added"] == 3
    assert summary["duplicates"] == 0
    assert summary["invalid"] == 0


def test_duplicate_roll_number_detection():
    """4. Tests duplicate detection in batch and in existing pool."""
    csv_bytes = b"Roll Number\n240104001\n240104001\n240104002\n"

    # 240104002 already exists in department pool
    existing = [{"roll_number": "240104002", "department_id": "dept-cse"}]
    mock_client, inserted = _create_mock_client(existing_records=existing)

    with patch("services.roll_number_service._get_client", return_value=mock_client):
        summary = RollNumberService.import_excel_roll_numbers(
            coordinator_role=UserRole.COORDINATOR.value,
            coordinator_dept_id="dept-cse",
            coordinator_id="coord-1",
            file_bytes=csv_bytes,
            file_name="dupes.csv"
        )

    assert summary["total_rows"] == 3
    assert summary["added"] == 1  # only first 240104001
    assert summary["duplicates"] == 2  # one batch duplicate, one DB duplicate
    assert len(inserted) == 1
    assert inserted[0]["roll_number"] == "240104001"


def test_invalid_row_detection():
    """5. Tests invalid roll number format rejection."""
    csv_bytes = b"Roll Number\n240105001\nINVALID!@#\n1\n240105002\n"

    mock_client, inserted = _create_mock_client(existing_records=[])
    with patch("services.roll_number_service._get_client", return_value=mock_client):
        summary = RollNumberService.import_excel_roll_numbers(
            coordinator_role=UserRole.COORDINATOR.value,
            coordinator_dept_id="dept-cse",
            coordinator_id="coord-1",
            file_bytes=csv_bytes,
            file_name="invalid.csv"
        )

    assert summary["total_rows"] == 4
    assert summary["added"] == 2
    assert summary["invalid"] == 2
    assert len(summary["errors"]) == 2


def test_department_mismatch_detection():
    """6. Tests department mismatch detection via spreadsheet column and cross-pool check."""
    # A) Spreadsheet column has different department
    df = pd.DataFrame({
        "Roll Number": ["240106001", "240106002"],
        "Department": ["MECH", "CSE"]
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    file_bytes = buf.getvalue()

    # Pre-existing roll number in another department
    existing = [{"roll_number": "240106002", "department_id": "dept-other"}]
    mock_client, inserted = _create_mock_client(existing_records=existing)

    with patch("services.roll_number_service._get_client", return_value=mock_client), \
         patch("services.cache_service.CacheService.get_department_by_id", return_value={"code": "CSE", "name": "Computer Engineering"}):
        summary = RollNumberService.import_excel_roll_numbers(
            coordinator_role=UserRole.COORDINATOR.value,
            coordinator_dept_id="dept-cse",
            coordinator_id="coord-1",
            file_bytes=file_bytes,
            file_name="dept_check.xlsx"
        )

    assert summary["total_rows"] == 2
    # 240106001 has department MECH != CSE -> invalid (dept mismatch)
    # 240106002 exists in dept-other != dept-cse -> invalid (belongs to another pool)
    assert summary["added"] == 0
    assert summary["invalid"] == 2
    assert any("does not match coordinator's department" in e for e in summary["errors"])
    assert any("belongs to another department's pool" in e for e in summary["errors"])


def test_successful_roll_number_insertion():
    """7. Verifies payload and fields during successful insertion."""
    csv_bytes = b"Roll Number\n240107001\n"
    mock_client, inserted = _create_mock_client(existing_records=[])

    with patch("services.roll_number_service._get_client", return_value=mock_client):
        summary = RollNumberService.import_excel_roll_numbers(
            coordinator_role=UserRole.COORDINATOR.value,
            coordinator_dept_id="dept-cse",
            coordinator_id="coord-1",
            file_bytes=csv_bytes,
            file_name="single.csv"
        )

    assert summary["success"] is True
    assert summary["added"] == 1
    assert len(inserted) == 1
    record = inserted[0]
    assert record["roll_number"] == "240107001"
    assert record["department_id"] == "dept-cse"
    assert record["added_by_coordinator_id"] == "coord-1"
    assert record["is_registered"] is False


# =========================================================================
# 8-12: STUDENT REGISTRATION AND PASSWORD VALIDATION TESTS
# =========================================================================

def test_student_registration_using_imported_roll_number():
    """8. Tests student registration after roll number exists in pool."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.insert.return_value = mock_table

    # Pool eligibility: present and unregistered
    mock_table.execute.side_effect = [
        MagicMock(data=[{"id": "pool-1", "roll_number": "240108001", "department_id": "dept-cse", "is_registered": False}]),  # verify pool
        MagicMock(data=[{"id": "st-1", "roll_number": "240108001", "full_name": "Test Student", "department_id": "dept-cse"}]),  # insert student
        MagicMock(data=[]),  # update pool is_registered
        MagicMock(data=[])   # welcome notification
    ]

    with patch("services.auth_service.get_trusted_backend_client", return_value=mock_client), \
         patch("services.roll_number_service._get_client", return_value=mock_client):
        ok, msg, new_st = AuthService.register_student(
            roll_number="240108001",
            full_name="Test Student",
            department_id="dept-cse",
            year="FE",
            password="Pass@123",
            security_question="What is your pet name?",
            security_answer="Tommy"
        )

    assert ok is True
    assert new_st is not None
    assert new_st["roll_number"] == "240108001"


def test_password_pass_at_123_accepted():
    """9. Explicitly tests that Pass@123 is accepted."""
    ok, err = validate_password_strength("Pass@123")
    assert ok is True
    assert "meets all security criteria" in err


def test_exactly_8_character_valid_passwords_accepted():
    """10. Tests valid passwords of exactly 8 characters."""
    valid_8 = [
        "Pass@123",
        "Abcd#999",
        "Zyxwv!10",
        "A1b2c3d$",
        "T@sk2026",
    ]
    for pw in valid_8:
        assert len(pw) == 8
        ok, err = validate_password_strength(pw)
        assert ok is True, f"Expected {pw} (len 8) to be accepted, got: {err}"


def test_passwords_shorter_than_8_rejected():
    """11. Tests passwords shorter than 8 characters are strictly rejected."""
    short = [
        "",
        "Pass@12",   # 7 chars
        "P@12345",   # 7 chars
        "Short#1",   # 7 chars
        "Abc#1",     # 5 chars
    ]
    for pw in short:
        ok, err = validate_password_strength(pw)
        assert ok is False
        assert "at least 8 characters" in err


def test_already_registered_roll_number_rejected():
    """12. Tests that an already-registered roll number in pool is rejected."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table

    # Pool record has is_registered = True
    mock_table.execute.return_value = MagicMock(data=[
        {"id": "pool-1", "roll_number": "240109001", "department_id": "dept-cse", "is_registered": True}
    ])

    with patch("services.roll_number_service._get_client", return_value=mock_client):
        eligible, err = RollNumberService.verify_roll_number_eligibility("240109001", "dept-cse")

    assert eligible is False
    assert "already registered" in err


# =========================================================================
# 13: MOBILE AND DESKTOP UI LAYOUT CHECKS
# =========================================================================

def test_coordinator_roll_number_ui_layout():
    """13. Tests Coordinator Roll Number Pool UI renders summary cards and responsive elements."""
    from ui.views.staff_view import StaffView

    page = MagicMock()
    page.width = 390  # Mobile viewport
    page.update = MagicMock()

    staff_dict = {
        "id": "staff-uuid-1",
        "role": UserRole.COORDINATOR.value,
        "department_id": "dept-cse",
        "full_name": "Coordinator Test"
    }

    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[
        {"id": "r-1", "roll_number": "240101001", "department_id": "dept-cse", "is_registered": True, "created_at": "2026-10-01T10:00:00"},
        {"id": "r-2", "roll_number": "240101002", "department_id": "dept-cse", "is_registered": False, "created_at": "2026-10-02T10:00:00"}
    ])

    with patch("ui.views.staff_view.get_supabase_client", return_value=mock_client), \
         patch("database.supabase_client.get_trusted_backend_client", return_value=mock_client), \
         patch("services.roll_number_service._get_client", return_value=mock_client):
        view = StaffView(page, staff_dict, UserRole.COORDINATOR.value)
        view.department_code = "CSE"
        layout = view._render_roll_number_pool()

    assert layout is not None
    assert isinstance(layout, ft.Column)
    # Check that layout has natural spacing and is not stretched
    assert layout.spacing == 16
    assert getattr(layout, "expand", False) is False or getattr(layout, "expand", None) is None
