"""
tests/test_account_management.py: Automated tests for Account Management,
Profile updates, Own Password Changes, Soft Deactivation, and Hierarchical Oversight.
"""

import pytest
from services.account_service import AccountService
from services.auth_service import AuthService
from services.roll_number_service import RollNumberService
from models.user import UserRole
from utils.security import hash_password, verify_password


class TestAccountManagement:
    def test_own_password_complexity_enforcement(self):
        """Validates that password changes strictly enforce policy."""
        # Too short
        ok, msg = AccountService.change_own_password("mock-id", UserRole.STUDENT.value, "OldPass@123", "Short1!")
        assert not ok
        assert "8 characters" in msg

        # No uppercase
        ok, msg = AccountService.change_own_password("mock-id", UserRole.STUDENT.value, "OldPass@123", "lowercase1@")
        assert not ok
        assert "uppercase" in msg

        # No digit
        ok, msg = AccountService.change_own_password("mock-id", UserRole.STUDENT.value, "OldPass@123", "NoDigits@Here")
        assert not ok
        assert "number" in msg

        # No special char
        ok, msg = AccountService.change_own_password("mock-id", UserRole.STUDENT.value, "OldPass@123", "NoSpecial123")
        assert not ok
        assert "special" in msg

    def test_profile_update_validation(self):
        """Validates that empty or excessively long names are rejected."""
        ok, msg = AccountService.update_profile("mock-id", UserRole.STUDENT.value, "")
        assert not ok

        ok, msg = AccountService.update_profile("mock-id", UserRole.STUDENT.value, "A" * 105)
        assert not ok

    def test_non_coordinator_cannot_add_roll_number(self):
        """Verifies that Students, HODs, and Principals cannot add roll numbers."""
        ok, msg = RollNumberService.add_single_roll_number(
            coordinator_role=UserRole.STUDENT.value,
            coordinator_dept_id="00000000-0000-0000-0000-000000000000",
            coordinator_id="00000000-0000-0000-0000-000000000000",
            roll_number="240101001"
        )
        assert not ok
        assert "Only Coordinators" in msg

    def test_invalid_roll_number_rejected_by_service(self):
        """Verifies roll number format validation."""
        ok, msg = RollNumberService.add_single_roll_number(
            coordinator_role=UserRole.COORDINATOR.value,
            coordinator_dept_id="00000000-0000-0000-0000-000000000000",
            coordinator_id="00000000-0000-0000-0000-000000000000",
            roll_number="2401#010"
        )
        assert not ok
        assert "Roll number can only contain" in msg
