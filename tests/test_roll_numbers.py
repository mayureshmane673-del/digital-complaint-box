"""
tests/test_roll_numbers.py: Unit tests for roll number format validation and Coordinator authority.
"""

from utils.validators import validate_roll_number
from services.roll_number_service import RollNumberService
from models.user import UserRole


def test_roll_number_format_cases():
    valid = ["240101030", "240101024", "CSE-2026-10", "AIDS_042"]
    for r in valid:
        ok, _ = validate_roll_number(r)
        assert ok, f"Expected {r} to be valid"

    invalid = ["", "   ", "a", "too_long_" + "x" * 40, "2401#010"]
    for r in invalid:
        ok, err = validate_roll_number(r)
        assert not ok, f"Expected {r} to be invalid"


def test_non_coordinator_cannot_add_roll_number():
    # HOD attempting to add roll number
    res, msg = RollNumberService.add_single_roll_number(
        coordinator_role=UserRole.HOD.value,
        coordinator_dept_id="dept-1",
        coordinator_id="hod-1",
        roll_number="240101099"
    )
    assert not res
    assert "Only Coordinators are authorized" in msg

    # Principal attempting to add roll number
    res, msg = RollNumberService.add_single_roll_number(
        coordinator_role=UserRole.PRINCIPAL.value,
        coordinator_dept_id="dept-1",
        coordinator_id="principal-1",
        roll_number="240101099"
    )
    assert not res
    assert "Only Coordinators are authorized" in msg
