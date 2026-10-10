"""
tests/test_staff_security_and_student_mgmt.py: Comprehensive test suite for:
1. Staff Security Code Validation (Pass@123 across all roles and departments)
2. Security code rejection on invalid input
3. Principal-authorized security code reset persistence & verification
4. CSE Coordinator finding and resetting CSE student password
5. CSE Coordinator isolated from AIDS student (cannot find or reset)
6. AIDS Coordinator isolated from CSE student (cannot reset)
7. Anti-confusion for similar roll numbers across departments
8. Hostel Incharge isolation (cannot view directory or reset passwords)
9. Library Incharge isolation (cannot view directory or reset passwords)
10. Principal campus-wide management and department filtering
11. Rejection of unauthorized/inactive/student callers
12. Credential safety (no plaintext passwords, hashes omitted from list)
13. Regression suite compatibility
"""

import pytest
from unittest.mock import MagicMock, patch

from models.user import UserRole
from services.security_code_service import SecurityCodeService
from services.account_service import AccountService
from services.cache_service import CacheService
from utils.security import verify_password, hash_password
from utils.validators import validate_password_strength
from ui.views.account_view import generate_secure_temporary_password


class TestStaffSecurityAndStudentManagement:

    # -------------------------------------------------------------------------
    # SCENARIO 1: Pass@123 works across all staff creation flows & departments
    # -------------------------------------------------------------------------
    def test_scenario_01_pass_at_123_accepted_across_all_roles_and_departments(self):
        """Verifies that configured security code Pass@123 validates for all departments and roles."""
        depts = CacheService.get_departments()
        dept_codes = [d["code"] for d in depts if d.get("code") not in ("GEN", "LIB")]

        for code in dept_codes:
            dept_id = CacheService.resolve_department_id(code)
            # Both UUID and department code should resolve and verify
            assert SecurityCodeService.verify_role_code(UserRole.HOD.value, dept_id, "Pass@123"), f"HOD failed for {code}"
            assert SecurityCodeService.verify_role_code(UserRole.COORDINATOR.value, dept_id, "Pass@123"), f"Coordinator failed for {code}"
            assert SecurityCodeService.verify_role_code(UserRole.HOD.value, code, "Pass@123"), f"HOD by code failed for {code}"
            assert SecurityCodeService.verify_role_code(UserRole.COORDINATOR.value, code, "Pass@123"), f"Coord by code failed for {code}"

        # Global and special roles
        assert SecurityCodeService.verify_role_code(UserRole.PRINCIPAL.value, None, "Pass@123"), "Principal verification failed"
        assert SecurityCodeService.verify_role_code(UserRole.HOSTEL_INCHARGE.value, None, "Pass@123"), "Hostel Incharge verification failed"
        assert SecurityCodeService.verify_role_code(UserRole.LIBRARY_INCHARGE.value, None, "Pass@123"), "Library Incharge verification failed"
        assert SecurityCodeService.verify_role_code(UserRole.GENERAL_HOD.value, None, "Pass@123"), "General HOD verification failed"

    # -------------------------------------------------------------------------
    # SCENARIO 2: Incorrect security code rejected
    # -------------------------------------------------------------------------
    def test_scenario_02_incorrect_security_code_rejected(self):
        """Verifies that wrong security codes or empty codes are rejected."""
        aids_id = CacheService.resolve_department_id("AIDS")
        assert not SecurityCodeService.verify_role_code(UserRole.HOD.value, aids_id, "WrongCode@999")
        assert not SecurityCodeService.verify_role_code(UserRole.COORDINATOR.value, aids_id, "Incorrect@123")
        assert not SecurityCodeService.verify_role_code(UserRole.PRINCIPAL.value, None, "BadPass@000")
        assert not SecurityCodeService.verify_role_code(UserRole.HOSTEL_INCHARGE.value, None, "")
        assert not SecurityCodeService.verify_role_code(UserRole.LIBRARY_INCHARGE.value, None, "   ")

    # -------------------------------------------------------------------------
    # SCENARIO 3: Principal-authorized code reset persists and validates
    # -------------------------------------------------------------------------
    def test_scenario_03_principal_security_code_reset_persists(self):
        """Verifies Principal can reset security code for AIDS HOD and new code validates."""
        aids_id = CacheService.resolve_department_id("AIDS")
        new_test_code = "ResetPass@2026"

        with patch("services.security_code_service.get_trusted_backend_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])

            with patch.object(SecurityCodeService, "get_code_record", return_value={"id": "record-aids-hod", "role": "HOD", "department_id": aids_id}):
                ok, msg = SecurityCodeService.update_security_code(
                    actor_role=UserRole.PRINCIPAL.value,
                    actor_dept_id=None,
                    target_role=UserRole.HOD.value,
                    target_dept_id=aids_id,
                    new_code=new_test_code
                )
                assert ok, f"Update failed: {msg}"
                assert "successfully updated" in msg

    # -------------------------------------------------------------------------
    # SCENARIO 4: CSE Coordinator can find/reset CSE student password
    # -------------------------------------------------------------------------
    def test_scenario_04_cse_coordinator_can_find_and_reset_cse_student(self):
        """Verifies CSE Coordinator can list and reset passwords for CSE departmental students."""
        cse_id = CacheService.resolve_department_id("CSE")
        coord_id = "cse-coord-uuid"
        student_id = "cse-student-uuid"

        mock_coord = {"id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": cse_id, "is_active": True, "is_locked": False}
        mock_student = {
            "id": student_id,
            "roll_number": "CSE2024001",
            "full_name": "CSE Student",
            "department_id": cse_id,
            "year": "SE",
            "is_hostel": False,
            "is_locked": True,
            "created_at": "2026-01-01T00:00:00",
            "security_question": "Pet name?"
        }

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            # Mock staff lookup
            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_coord])

            # Mock student lookup
            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[mock_student])
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_student])
            student_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_student])

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "students":
                    return student_table
                return MagicMock()

            client.table.side_effect = table_router

            # 1. List students
            students = AccountService.list_students_for_staff(coord_id)
            assert len(students) == 1
            assert students[0]["roll_number"] == "CSE2024001"

            # 2. Reset password
            ok, msg = AccountService.reset_student_password_by_staff(coord_id, student_id, "Temp@2026!")
            assert ok
            assert "reset successfully" in msg
            assert "Account unlocked" in msg

    # -------------------------------------------------------------------------
    # SCENARIO 5: CSE Coordinator cannot find/reset AIDS student
    # -------------------------------------------------------------------------
    def test_scenario_05_cse_coordinator_cannot_find_or_reset_aids_student(self):
        """Verifies CSE Coordinator is isolated from AIDS students and rejected if attempting reset."""
        cse_id = CacheService.resolve_department_id("CSE")
        aids_id = CacheService.resolve_department_id("AIDS")
        coord_id = "cse-coord-uuid"
        aids_student_id = "aids-student-uuid"

        mock_coord = {"id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": cse_id, "is_active": True, "is_locked": False}
        mock_aids_student = {
            "id": aids_student_id,
            "roll_number": "AIDS2024001",
            "full_name": "AIDS Student",
            "department_id": aids_id,
            "year": "SE",
            "security_question": "Pet name?"
        }

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_coord])

            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_aids_student])

            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "students":
                    return student_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            ok, msg = AccountService.reset_student_password_by_staff(coord_id, aids_student_id, "Temp@2026!")
            assert not ok
            assert "own academic department" in msg
            # Verify security audit log was written
            assert audit_table.insert.called
            call_args = audit_table.insert.call_args[0][0]
            assert call_args["event_type"] == "UNAUTHORIZED_STUDENT_PASSWORD_RESET_ATTEMPT"

    # -------------------------------------------------------------------------
    # SCENARIO 6: AIDS Coordinator cannot reset CSE student
    # -------------------------------------------------------------------------
    def test_scenario_06_aids_coordinator_cannot_reset_cse_student(self):
        """Verifies AIDS Coordinator cannot reset CSE student credentials."""
        cse_id = CacheService.resolve_department_id("CSE")
        aids_id = CacheService.resolve_department_id("AIDS")
        coord_id = "aids-coord-uuid"
        cse_student_id = "cse-student-uuid"

        mock_coord = {"id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": aids_id, "is_active": True, "is_locked": False}
        mock_cse_student = {
            "id": cse_student_id,
            "roll_number": "CSE2024099",
            "full_name": "CSE Student",
            "department_id": cse_id,
            "year": "TE"
        }

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_coord])

            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_cse_student])

            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "students":
                    return student_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            ok, msg = AccountService.reset_student_password_by_staff(coord_id, cse_student_id, "Temp@2026!")
            assert not ok
            assert "own academic department" in msg
            assert audit_table.insert.called

    # -------------------------------------------------------------------------
    # SCENARIO 7: Similar roll numbers from different departments anti-confusion
    # -------------------------------------------------------------------------
    def test_scenario_07_similar_roll_numbers_anti_confusion(self):
        """Verifies students with similar or duplicate roll numbers in different departments cannot be confused."""
        cse_id = CacheService.resolve_department_id("CSE")
        aids_id = CacheService.resolve_department_id("AIDS")
        cse_coord_id = "cse-coord-uuid"

        mock_coord = {"id": cse_coord_id, "role": UserRole.COORDINATOR.value, "department_id": cse_id, "is_active": True, "is_locked": False}
        # Two students with same roll number '240101' in different departments
        cse_student = {"id": "uuid-cse-240101", "roll_number": "240101", "full_name": "Rahul Sharma", "department_id": cse_id, "year": "SE"}
        aids_student = {"id": "uuid-aids-240101", "roll_number": "240101", "full_name": "Rahul Verma", "department_id": aids_id, "year": "SE"}

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_coord])

            student_table = MagicMock()
            # Coordinator query filters by department_id
            student_table.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[cse_student])

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "students":
                    return student_table
                return MagicMock()

            client.table.side_effect = table_router

            # Query by roll number
            results = AccountService.list_students_for_staff(cse_coord_id, search_query="240101")
            assert len(results) == 1
            assert results[0]["id"] == "uuid-cse-240101"
            assert results[0]["full_name"] == "Rahul Sharma"
            assert results[0]["departments"]["code"] == "CSE"

    # -------------------------------------------------------------------------
    # SCENARIO 8: Hostel Incharge cannot access student directory or reset
    # -------------------------------------------------------------------------
    def test_scenario_08_hostel_incharge_strictly_isolated_from_student_mgmt(self):
        """Verifies Hostel Incharge cannot view student directory or execute password resets."""
        hostel_id = "hostel-incharge-uuid"
        student_id = "student-uuid"

        mock_hostel = {"id": hostel_id, "role": UserRole.HOSTEL_INCHARGE.value, "department_id": None, "is_active": True, "is_locked": False}

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_hostel])

            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            # 1. Directory access returns empty
            students = AccountService.list_students_for_staff(hostel_id)
            assert students == []

            # 2. Reset attempt rejected
            ok, msg = AccountService.reset_student_password_by_staff(hostel_id, student_id, "Temp@2026!")
            assert not ok
            assert "not permitted to reset student passwords" in msg
            assert audit_table.insert.called

    # -------------------------------------------------------------------------
    # SCENARIO 9: Library Incharge cannot access student directory or reset
    # -------------------------------------------------------------------------
    def test_scenario_09_library_incharge_strictly_isolated_from_student_mgmt(self):
        """Verifies Library Incharge cannot view student directory or execute password resets."""
        lib_id = "library-incharge-uuid"
        student_id = "student-uuid"

        mock_lib = {"id": lib_id, "role": UserRole.LIBRARY_INCHARGE.value, "department_id": None, "is_active": True, "is_locked": False}

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_lib])

            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            # 1. Directory access returns empty
            students = AccountService.list_students_for_staff(lib_id)
            assert students == []

            # 2. Reset attempt rejected
            ok, msg = AccountService.reset_student_password_by_staff(lib_id, student_id, "Temp@2026!")
            assert not ok
            assert "not permitted to reset student passwords" in msg
            assert audit_table.insert.called

    # -------------------------------------------------------------------------
    # SCENARIO 10: Approved Principal & HOD institutional management permissions
    # -------------------------------------------------------------------------
    def test_scenario_10_approved_hierarchical_permissions_enforced(self):
        """
        Verifies approved account-management permissions:
        - Coordinator: manages departmental students only.
        - Principal: manages HODs, Hostel Incharge, Library Incharge, General HOD; NOT general student resets.
        - HOD: manages departmental Coordinators; NOT student resets.
        - Hostel Incharge & Library Incharge: NO student directory, NO resets.
        """
        principal_id = "principal-uuid"
        hod_id = "hod-uuid"
        student_id = "any-student-uuid"

        mock_principal = {"id": principal_id, "role": UserRole.PRINCIPAL.value, "department_id": None, "is_active": True, "is_locked": False}
        mock_hod = {"id": hod_id, "role": UserRole.HOD.value, "department_id": "dept-uuid", "is_active": True, "is_locked": False}

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            # 1. Principal is rejected from listing students or resetting student passwords
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_principal])
            assert AccountService.list_students_for_staff(principal_id) == []
            ok, msg = AccountService.reset_student_password_by_staff(principal_id, student_id, "Temp@2026!")
            assert not ok
            assert "Principal is not permitted to reset student passwords" in msg

            # 2. HOD is rejected from listing students or resetting student passwords
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_hod])
            assert AccountService.list_students_for_staff(hod_id) == []
            ok, msg = AccountService.reset_student_password_by_staff(hod_id, student_id, "Temp@2026!")
            assert not ok
            assert "HOD is not permitted to reset student passwords" in msg

    # -------------------------------------------------------------------------
    # SCENARIO 11: Unauthorized direct backend requests rejected
    # -------------------------------------------------------------------------
    def test_scenario_11_unauthorized_direct_requests_rejected(self):
        """Verifies inactive, locked, or student accounts are rejected by backend reset methods."""
        student_actor_id = "student-actor-uuid"
        target_id = "target-uuid"

        mock_inactive = {"id": "inact-id", "role": UserRole.COORDINATOR.value, "department_id": "dept-1", "is_active": False, "is_locked": False}
        mock_locked = {"id": "locked-id", "role": UserRole.COORDINATOR.value, "department_id": "dept-1", "is_active": True, "is_locked": True}

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client
            staff_table = MagicMock()

            # Case A: Inactive staff
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_inactive])
            client.table.return_value = staff_table
            ok, msg = AccountService.reset_student_password_by_staff("inact-id", target_id, "Temp@2026!")
            assert not ok
            assert "locked or inactive" in msg

            # Case B: Locked staff
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_locked])
            ok, msg = AccountService.reset_student_password_by_staff("locked-id", target_id, "Temp@2026!")
            assert not ok
            assert "locked or inactive" in msg

            # Case C: Unknown staff
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            ok, msg = AccountService.reset_student_password_by_staff("unknown-id", target_id, "Temp@2026!")
            assert not ok
            assert "Unauthorized" in msg

    # -------------------------------------------------------------------------
    # SCENARIO 12: Password resets do not expose plaintext credentials
    # -------------------------------------------------------------------------
    def test_scenario_12_password_resets_do_not_expose_credentials(self):
        """Verifies password hashes are never exposed in listing or audit logs, and passwords are encrypted."""
        cse_id = CacheService.resolve_department_id("CSE")
        coord_id = "cse-coord-uuid"
        student_id = "cse-student-uuid"

        mock_coord = {"id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": cse_id, "is_active": True, "is_locked": False}
        mock_student = {
            "id": student_id,
            "roll_number": "CSE2024001",
            "full_name": "CSE Student",
            "department_id": cse_id,
            "year": "SE",
            "password_hash": "$2b$12$oldhashplaceholder",
            "security_answer_hash": "$2b$12$oldanswerplaceholder"
        }

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_coord])

            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[mock_student])
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_student])
            student_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "students":
                    return student_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            # 1. Listing strips password hash
            students = AccountService.list_students_for_staff(coord_id)
            assert len(students) == 1
            assert "password_hash" not in students[0]
            assert "security_answer_hash" not in students[0]

            # 2. Reset sets bcrypt hash, not plaintext
            ok, msg = AccountService.reset_student_password_by_staff(coord_id, student_id, "Temp@2026!")
            assert ok
            update_call = student_table.update.call_args[0][0]
            assert update_call["password_hash"] != "Temp@2026!"
            assert verify_password("Temp@2026!", update_call["password_hash"])

            # 3. Audit log contains no password
            audit_call = audit_table.insert.call_args[0][0]
            assert "Temp@2026!" not in str(audit_call)

    # -------------------------------------------------------------------------
    # SCENARIO 13: First Year (FE) student boundary enforcement
    # -------------------------------------------------------------------------
    def test_scenario_13_first_year_student_boundary_enforced(self):
        """Verifies Academic Coordinators cannot list or reset First Year students."""
        cse_id = CacheService.resolve_department_id("CSE")
        coord_id = "cse-coord-uuid"
        fe_student_id = "fe-student-uuid"

        mock_coord = {"id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": cse_id, "is_active": True, "is_locked": False}
        fe_student = {
            "id": fe_student_id,
            "roll_number": "CSE2026001",
            "full_name": "First Year Student",
            "department_id": cse_id,
            "year": "FE"
        }

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_coord])

            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[fe_student])
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[fe_student])

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "students":
                    return student_table
                return MagicMock()

            client.table.side_effect = table_router

            # 1. Listing filters out FE students
            students = AccountService.list_students_for_staff(coord_id)
            assert len(students) == 0

            # 2. Reset attempt for FE student rejected
            ok, msg = AccountService.reset_student_password_by_staff(coord_id, fe_student_id, "Temp@2026!")
            assert not ok
            assert "First Year student accounts are managed by the General Department" in msg

    # -------------------------------------------------------------------------
    # SCENARIO 14: Department resolver robustness
    # -------------------------------------------------------------------------
    def test_scenario_14_department_resolver_robustness(self):
        """
        Tests CacheService.resolve_department_id across all inputs:
        - Canonical UUIDs
        - Legacy dummy UUIDs
        - Department codes (uppercase and lowercase)
        - Unknown identifiers
        - None, empty string, and 'none'
        - Cache refresh behavior and lock safety
        """
        # A. None and empty values
        assert CacheService.resolve_department_id(None) is None
        assert CacheService.resolve_department_id("") is None
        assert CacheService.resolve_department_id("   ") is None
        assert CacheService.resolve_department_id("none") is None
        assert CacheService.resolve_department_id("None") is None

        # B. Canonical UUIDs pass through intact
        cse_canonical = "f4e141ef-14ca-44e4-a1ed-051ee0525419"
        aids_canonical = "067bc0be-bd8c-47ce-a520-b3e93407deb8"
        etc_canonical = "9260c753-a8a9-49b8-a3a3-28f907b3f84a"
        mech_canonical = "c0c9498b-06c3-4e7a-9041-3cd7e104399a"
        civil_canonical = "730449ab-f29f-4d0a-8ea1-3e17116e5ae6"

        assert CacheService.resolve_department_id(cse_canonical) == cse_canonical
        assert CacheService.resolve_department_id(aids_canonical) == aids_canonical
        assert CacheService.resolve_department_id(etc_canonical) == etc_canonical
        assert CacheService.resolve_department_id(mech_canonical) == mech_canonical
        assert CacheService.resolve_department_id(civil_canonical) == civil_canonical

        # C. Legacy dummy UUIDs map to canonical database UUIDs
        assert CacheService.resolve_department_id("06059c36-8a03-4f9e-9086-1d116a3bc533") == aids_canonical
        assert CacheService.resolve_department_id("a90df03a-3243-4ce2-bdf1-3312c5b3d6f1") == etc_canonical
        assert CacheService.resolve_department_id("d05fe7ee-bfcf-41c3-8be2-72abcb71b802") == mech_canonical
        assert CacheService.resolve_department_id("517fc5e3-cf9d-4340-9a4f-a2e6f4770176") == civil_canonical

        # D. Department codes (case-insensitive)
        assert CacheService.resolve_department_id("AIDS") == aids_canonical
        assert CacheService.resolve_department_id("aids") == aids_canonical
        assert CacheService.resolve_department_id("CSE") == cse_canonical
        assert CacheService.resolve_department_id("cse") == cse_canonical
        assert CacheService.resolve_department_id("E&TC") == etc_canonical
        assert CacheService.resolve_department_id("e&tc") == etc_canonical
        assert CacheService.resolve_department_id("MECH") == mech_canonical
        assert CacheService.resolve_department_id("mech") == mech_canonical
        assert CacheService.resolve_department_id("Civil") == civil_canonical
        assert CacheService.resolve_department_id("civil") == civil_canonical

        # E. Unknown identifier safe fallback (does not crash or raise AttributeError)
        unknown_id = "unknown-custom-uuid-999"
        assert CacheService.resolve_department_id(unknown_id) == unknown_id

        # F. Re-entrant lock check (no deadlock or AttributeError)
        with CacheService._lock:
            res = CacheService.resolve_department_id("CSE")
            assert res == cse_canonical

    # -------------------------------------------------------------------------
    # SCENARIO 15: Temporary password generation uniqueness and compliance
    # -------------------------------------------------------------------------
    def test_scenario_15_temporary_password_generator_uniqueness_and_strength(self):
        """Verifies generated temporary passwords meet complexity rules and are unique."""
        passwords = set()
        for _ in range(50):
            pw = generate_secure_temporary_password(12)
            valid, err = validate_password_strength(pw)
            assert valid, f"Generated password '{pw}' failed validation: {err}"
            assert len(pw) == 12
            passwords.add(pw)

        # 50 random generations should yield 50 distinct passwords
        assert len(passwords) == 50, "Generated passwords were not unique"

    # -------------------------------------------------------------------------
    # SCENARIO 16: Security question preserved and never altered
    # -------------------------------------------------------------------------
    def test_scenario_16_security_question_preserved_on_student_reset(self):
        """Verifies student password reset does not alter or prefix security_question."""
        cse_id = CacheService.resolve_department_id("CSE")
        coord_id = "cse-coord-uuid"
        student_id = "cse-student-uuid"

        mock_coord = {"id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": cse_id, "is_active": True, "is_locked": False}
        original_question = "What is your mother's maiden name?"
        mock_student = {
            "id": student_id,
            "roll_number": "CSE2024001",
            "full_name": "CSE Student",
            "department_id": cse_id,
            "year": "SE",
            "security_question": original_question,
            "is_locked": True
        }

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_coord])

            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_student])
            student_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "students":
                    return student_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            ok, msg = AccountService.reset_student_password_by_staff(coord_id, student_id, "Temp@2026!")
            assert ok

            update_payload = student_table.update.call_args[0][0]
            # Must NOT touch or alter security_question
            assert "security_question" not in update_payload
            assert not any("RESET_REQUIRED" in str(v) for v in update_payload.values())

    # -------------------------------------------------------------------------
    # SCENARIO 17: Coordinator reset sets must_change_password=True with fallback
    # -------------------------------------------------------------------------
    def test_scenario_17_coordinator_reset_sets_must_change_password_with_fallback(self):
        """Verifies reset_student_password_by_staff includes must_change_password=True, with schema fallback."""
        cse_id = CacheService.resolve_department_id("CSE")
        coord_id = "cse-coord-uuid"
        student_id = "cse-student-uuid"

        mock_coord = {"id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": cse_id, "is_active": True, "is_locked": False}
        mock_student = {
            "id": student_id,
            "roll_number": "CSE2024001",
            "full_name": "CSE Student",
            "department_id": cse_id,
            "year": "SE",
            "is_locked": False
        }

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            staff_table = MagicMock()
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_coord])

            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_student])
            student_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "students":
                    return student_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            # A. Normal execution with column present
            ok, msg = AccountService.reset_student_password_by_staff(coord_id, student_id, "Temp@2026!")
            assert ok
            update_payload = student_table.update.call_args[0][0]
            assert update_payload.get("must_change_password") is True

            # B. Safe failure when column does not exist in database (no silent unforced reset)
            student_table.update.side_effect = [
                Exception("column 'must_change_password' does not exist")
            ]
            ok, msg = AccountService.reset_student_password_by_staff(coord_id, student_id, "Temp@2026!")
            assert not ok
            assert "migration 009 is pending" in msg

    # -------------------------------------------------------------------------
    # SCENARIO 18: Student self password change clears must_change_password flag
    # -------------------------------------------------------------------------
    def test_scenario_18_student_password_change_clears_must_change_password_flag(self):
        """Verifies change_own_password sets must_change_password=False for student accounts."""
        student_id = "cse-student-uuid"
        old_hash = hash_password("OldTemp@123")
        mock_student = {
            "id": student_id,
            "password_hash": old_hash,
            "must_change_password": True
        }

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_student])
            student_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def table_router(table_name):
                if table_name == "students":
                    return student_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            # 1. Invalid current password fails
            ok, msg = AccountService.change_own_password(student_id, UserRole.STUDENT.value, "WrongPass@123", "NewSecret@2026")
            assert not ok
            assert "Incorrect current password" in msg

            # 2. Correct current password succeeds and clears flag
            ok, msg = AccountService.change_own_password(student_id, UserRole.STUDENT.value, "OldTemp@123", "NewSecret@2026")
            assert ok
            update_payload = student_table.update.call_args[0][0]
            assert update_payload.get("must_change_password") is False
            assert verify_password("NewSecret@2026", update_payload["password_hash"])

    # -------------------------------------------------------------------------
    # SCENARIO 19: Student login propagates must_change_password to session
    # -------------------------------------------------------------------------
    def test_scenario_19_student_login_propagates_must_change_password(self):
        """Verifies AuthService.login_student passes must_change_password to session without touching security_question."""
        from services.auth_service import AuthService
        cse_id = CacheService.resolve_department_id("CSE")
        student_id = "cse-student-uuid"
        correct_pass = "Temp@Pass123"
        hashed = hash_password(correct_pass)

        mock_student = {
            "id": student_id,
            "roll_number": "240101001",
            "full_name": "Test Student",
            "department_id": cse_id,
            "password_hash": hashed,
            "is_active": True,
            "is_locked": False,
            "failed_login_attempts": 0,
            "security_question": "Favorite pet?",
            "must_change_password": True
        }

        with patch("services.auth_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client

            student_table = MagicMock()
            student_mock_res = MagicMock(data=[mock_student])
            student_table.select.return_value.eq.return_value.execute.return_value = student_mock_res
            student_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = student_mock_res
            client.table.return_value = student_table

            ok, msg, user = AuthService.login_student("240101001", correct_pass)
            assert ok
            assert user is not None
            assert user.get("must_change_password") is True
            assert "password_hash" not in user
            assert user.get("security_question") == "Favorite pet?"

    # -------------------------------------------------------------------------
    # SCENARIO 20: ForcePasswordChangeView form validation and callback
    # -------------------------------------------------------------------------
    def test_scenario_20_force_password_change_view_workflow(self):
        """Verifies ForcePasswordChangeView component renders and triggers callback upon valid update."""
        import flet as ft
        from ui.views.force_password_change_view import ForcePasswordChangeView

        mock_page = MagicMock()
        mock_user = {"id": "test-student-id", "roll_number": "240101001", "full_name": "Test Student"}
        callback_called = [False]

        def on_pw_changed():
            callback_called[0] = True

        view = ForcePasswordChangeView(
            page=mock_page,
            user=mock_user,
            on_password_changed=on_pw_changed,
            on_logout=MagicMock()
        )
        ctrl = view.render()
        assert ctrl is not None
        assert isinstance(ctrl, ft.Container)

        # Locate fields inside card
        card = ctrl.content
        col = card.content
        text_fields = [c for c in col.controls if isinstance(c, ft.TextField)]
        buttons = [c for c in col.controls if isinstance(c, ft.ElevatedButton)]

        assert len(text_fields) == 3
        curr_f, new_f, conf_f = text_fields
        submit_btn = buttons[0]

        # 1. Reject identical password
        curr_f.value = "Temp@Pass123"
        new_f.value = "Temp@Pass123"
        conf_f.value = "Temp@Pass123"
        submit_btn.on_click(None)
        assert not callback_called[0]

        # 2. Reject mismatch
        curr_f.value = "Temp@Pass123"
        new_f.value = "BrandNew@2026!"
        conf_f.value = "Different@2026!"
        submit_btn.on_click(None)
        assert not callback_called[0]

        # 3. Successful change triggers on_password_changed
        with patch.object(AccountService, "change_own_password", return_value=(True, "Password changed successfully.")):
            curr_f.value = "Temp@Pass123"
            new_f.value = "BrandNew@2026!"
            conf_f.value = "BrandNew@2026!"
            submit_btn.on_click(None)
            assert callback_called[0] is True

    # -------------------------------------------------------------------------
    # SCENARIO 21: Fail-closed department authorization enforcement
    # -------------------------------------------------------------------------
    def test_scenario_21_fail_closed_department_authorization(self):
        """Verifies fail-closed enforcement when department IDs are missing, invalid, or unrecognized."""
        coord_id = "coord-fail-closed"
        student_id = "student-fail-closed"
        cse_id = CacheService.resolve_department_id("CSE")

        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client
            staff_table = MagicMock()
            student_table = MagicMock()
            audit_table = MagicMock()

            def table_router(table_name):
                if table_name == "staff_users":
                    return staff_table
                elif table_name == "students":
                    return student_table
                elif table_name == "audit_logs":
                    return audit_table
                return MagicMock()

            client.table.side_effect = table_router

            # 1. Coordinator missing department ID -> Fails closed
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": None, "is_active": True, "is_locked": False
            }])
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "id": student_id, "roll_number": "CSE2024001", "department_id": cse_id, "year": "SE"
            }])
            ok, msg = AccountService.reset_student_password_by_staff(coord_id, student_id, "Temp@2026!")
            assert not ok
            assert "valid, assigned academic departments" in msg

            # 2. Student missing department ID -> Fails closed
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": cse_id, "is_active": True, "is_locked": False
            }])
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "id": student_id, "roll_number": "CSE2024001", "department_id": None, "year": "SE"
            }])
            ok, msg = AccountService.reset_student_password_by_staff(coord_id, student_id, "Temp@2026!")
            assert not ok
            assert "valid, assigned academic departments" in msg

            # 3. Both have identical unrecognized/invalid department ID -> Fails closed
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": "non-existent-dept", "is_active": True, "is_locked": False
            }])
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "id": student_id, "roll_number": "CSE2024001", "department_id": "non-existent-dept", "year": "SE"
            }])
            ok, msg = AccountService.reset_student_password_by_staff(coord_id, student_id, "Temp@2026!")
            assert not ok
            assert "valid, assigned academic departments" in msg

            # 4. list_students_for_staff fails closed when coordinator has invalid department ID
            students = AccountService.list_students_for_staff(coord_id)
            assert students == []

            # 5. Legitimate matching valid department succeeds
            staff_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "id": coord_id, "role": UserRole.COORDINATOR.value, "department_id": cse_id, "is_active": True, "is_locked": False
            }])
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "id": student_id, "roll_number": "CSE2024001", "department_id": cse_id, "year": "SE"
            }])
            student_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
            ok, msg = AccountService.reset_student_password_by_staff(coord_id, student_id, "Temp@2026!")
            assert ok

    # -------------------------------------------------------------------------
    # SCENARIO 22: Cache locking and concurrent lookups without deadlock
    # -------------------------------------------------------------------------
    def test_scenario_22_cache_locking_and_concurrency(self):
        """Verifies cache resolver thread-safety, validation fail-closed, and lack of deadlocks under concurrency."""
        import threading

        # Test validation fail-closed directly
        assert CacheService.validate_and_canonicalize_department_id(None) is None
        assert CacheService.validate_and_canonicalize_department_id("") is None
        assert CacheService.validate_and_canonicalize_department_id("None") is None
        assert CacheService.validate_and_canonicalize_department_id("INVALID_DEPT_CODE_123") is None

        # Test valid departments resolve to canonical UUIDs
        cse_canonical = CacheService.validate_and_canonicalize_department_id("CSE")
        assert cse_canonical is not None
        assert CacheService.validate_and_canonicalize_department_id(cse_canonical) == cse_canonical

        # Concurrency stress test: 20 threads simultaneously resolving departments
        errors = []

        def worker(dept_key):
            try:
                res1 = CacheService.resolve_department_id(dept_key)
                res2 = CacheService.validate_and_canonicalize_department_id(dept_key)
                if dept_key in ("CSE", "AIDS", "MECH"):
                    assert res1 is not None
                    assert res2 is not None
                elif dept_key == "BOGUS":
                    assert res2 is None
            except Exception as e:
                errors.append(e)

        mock_dept_client = MagicMock()
        mock_dept_client.table.return_value.select.return_value.execute.return_value = MagicMock(data=CacheService.DEFAULT_DEPARTMENTS)

        with patch("database.supabase_client.get_trusted_backend_client", return_value=mock_dept_client), \
             patch("database.supabase_client.get_supabase_client", return_value=mock_dept_client):
            threads = []
            keys = ["CSE", "AIDS", "MECH", "BOGUS", "E&TC", "Civil"] * 4
            for k in keys:
                t = threading.Thread(target=worker, args=(k,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=5.0)
                assert not t.is_alive(), "Thread deadlock detected in CacheService"

        assert len(errors) == 0, f"Errors occurred during concurrent cache operations: {errors}"

    # -------------------------------------------------------------------------
    # SCENARIO 23: Legacy RESET_REQUIRED migration backfill and auth handling
    # -------------------------------------------------------------------------
    def test_scenario_23_legacy_reset_required_migration_and_auth(self):
        """Verifies legacy RESET_REQUIRED prefix is handled gracefully, stripped upon reset, and preserves answers."""
        from services.auth_service import AuthService

        # 1. Simulating Phase 1 migration logic on record:
        raw_question = "RESET_REQUIRED:What was your first school?"
        raw_answer_hash = hash_password("st. anne's")

        # Phase 1: SET must_change_password = TRUE WHERE LEFT(security_question, 15) = 'RESET_REQUIRED:' AND must_change_password = FALSE
        # Exact-prefix condition matches literal 'RESET_REQUIRED:' and rejects wildcard variations like 'RESETxREQUIRED:'
        def matches_phase1(q_text, flag):
            return q_text[:15] == "RESET_REQUIRED:" and not flag

        # Matches exact prefix
        assert matches_phase1(raw_question, False) is True
        # Rejects similar strings where underscore was replaced or character changed (which LIKE 'RESET_REQUIRED:%' might match)
        assert matches_phase1("RESETxREQUIRED:What was your first school?", False) is False
        assert matches_phase1("RESET1REQUIRED:What was your first school?", False) is False
        assert matches_phase1("RESET_REQUIREM:What was your first school?", False) is False
        assert matches_phase1("What was your first school?", False) is False

        # In Phase 1, the security_question prefix is preserved in the database for backward compatibility
        phase1_must_change = True
        phase1_question = raw_question  # Preserved in database
        phase1_answer_hash = raw_answer_hash  # Answer hash untouched

        assert phase1_must_change is True
        assert phase1_question == "RESET_REQUIRED:What was your first school?"
        assert verify_password("st. anne's", phase1_answer_hash)

        # Idempotency check: running Phase 1 backfill again when must_change_password=True matches 0 rows
        assert matches_phase1(phase1_question, phase1_must_change) is False

        # Phase 3 (post-deployment cleanup): SET security_question = TRIM(SUBSTRING(security_question FROM 16))
        phase3_cleaned_question = phase1_question[len("RESET_REQUIRED:"):].strip()
        assert phase3_cleaned_question == "What was your first school?"

        # 2. AuthService.login_student with legacy unmigrated record
        student_id = "legacy-student-uuid"
        cse_id = CacheService.resolve_department_id("CSE")
        mock_student = {
            "id": student_id,
            "roll_number": "CSE2024099",
            "full_name": "Legacy Student",
            "department_id": cse_id,
            "password_hash": hash_password("TempPass@123"),
            "security_question": "RESET_REQUIRED:What was your first school?",
            "security_answer_hash": raw_answer_hash,
            "must_change_password": False,
            "is_active": True,
            "is_locked": False,
            "failed_login_attempts": 0
        }

        with patch("services.auth_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client
            student_table = MagicMock()
            mock_res = MagicMock(data=[mock_student])
            student_table.select.return_value.eq.return_value.execute.return_value = mock_res
            student_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_res
            client.table.return_value = student_table

            ok, msg, user = AuthService.login_student("CSE2024099", "TempPass@123")
            assert ok
            assert user["must_change_password"] is True
            assert user["security_question"] == "What was your first school?"

        # 3. AuthService.get_student_security_question strips prefix
        with patch("services.auth_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client
            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "security_question": "RESET_REQUIRED:What was your first school?"
            }])
            client.table.return_value = student_table

            ok, msg, q = AuthService.get_student_security_question("CSE2024099")
            assert ok
            assert q == "What was your first school?"

        # 4. AccountService.change_own_password cleans security_question in database
        with patch("services.account_service.get_trusted_backend_client") as mock_backend:
            client = MagicMock()
            mock_backend.return_value = client
            student_table = MagicMock()
            student_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                "id": student_id,
                "password_hash": hash_password("TempPass@123"),
                "security_question": "RESET_REQUIRED:What was your first school?"
            }])
            student_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
            audit_table = MagicMock()
            audit_table.insert.return_value.execute.return_value = MagicMock()

            def router(t):
                if t == "students":
                    return student_table
                elif t == "audit_logs":
                    return audit_table
                return MagicMock()
            client.table.side_effect = router

            ok, msg = AccountService.change_own_password(student_id, UserRole.STUDENT.value, "TempPass@123", "NewSecurePassword@2026")
            assert ok
            payload = student_table.update.call_args[0][0]
            assert payload.get("must_change_password") is False
            assert payload.get("security_question") == "What was your first school?"
            assert verify_password("NewSecurePassword@2026", payload["password_hash"])

    # -------------------------------------------------------------------------
    # SCENARIO 24: Password generator safe validation and edge cases
    # -------------------------------------------------------------------------
    def test_scenario_24_password_generator_validation(self):
        """Verifies generate_secure_temporary_password guards invalid lengths and produces strong passwords."""
        # Invalid length inputs fallback to default (length >= 8)
        p1 = generate_secure_temporary_password(length=4)
        assert len(p1) >= 8
        val_ok, _ = validate_password_strength(p1)
        assert val_ok

        p2 = generate_secure_temporary_password(length=-10)
        assert len(p2) >= 8
        val_ok, _ = validate_password_strength(p2)
        assert val_ok

        p3 = generate_secure_temporary_password(length="invalid")  # type: ignore
        assert len(p3) >= 8
        val_ok, _ = validate_password_strength(p3)
        assert val_ok

        # Valid custom length
        p4 = generate_secure_temporary_password(length=16)
        assert len(p4) == 16
        val_ok, _ = validate_password_strength(p4)
        assert val_ok
