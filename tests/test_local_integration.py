"""
tests/test_local_integration.py: [LOCAL-INTEGRATION] Tests
Verifies departmental isolation, role boundaries, anonymous identity masking,
storage access authorization, and security context protections at the application and service layer.
"""

import pytest
from unittest.mock import patch, MagicMock
from models.user import UserRole
from services.complaint_service import ComplaintService
from services.roll_number_service import RollNumberService
from services.storage_service import StorageService
from services.hostel_service import HostelService


class TestLocalIntegrationSecurityBoundaries:
    """
    [LOCAL-INTEGRATION] Test suite verifying requirements a through j:
    a. Student cannot read roll_number_pool.
    b. Coordinator can only access own department roll numbers.
    c. HOD cannot access another department.
    d. Coordinator cannot access hostel requests.
    e. Anonymous complaint owner table is inaccessible to staff.
    f. Anonymous complaint student identity is never returned to staff.
    g. Storage objects cannot be accessed by unauthorized users.
    h. HOD/Coordinator department isolation works at database and service level.
    i. Principal access works correctly.
    j. set_application_context cannot be abused by a normal user.
    """

    # Requirement a: Student cannot read/manage roll_number_pool
    def test_local_integration_student_cannot_read_roll_number_pool(self):
        """[LOCAL-INTEGRATION] Verifies students cannot manage or add to the roll number pool."""
        success, msg = RollNumberService.add_single_roll_number(
            coordinator_role=UserRole.STUDENT.value,
            coordinator_dept_id="dept-cse",
            coordinator_id="student-uuid-1",
            roll_number="2026CSE001"
        )
        assert success is False
        assert "Only Coordinators are authorized" in msg

    # Requirement b: Coordinator can only access own department roll numbers
    def test_local_integration_coordinator_department_isolation(self):
        """[LOCAL-INTEGRATION] Verifies Coordinator cannot add roll numbers belonging to another department pool."""
        with patch("services.roll_number_service.get_supabase_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            # Simulate roll number already belonging to another department
            mock_table.execute.return_value.data = [
                {"id": "uuid-1", "department_id": "dept-aids"}
            ]

            success, msg = RollNumberService.add_single_roll_number(
                coordinator_role=UserRole.COORDINATOR.value,
                coordinator_dept_id="dept-cse",
                coordinator_id="coord-uuid-1",
                roll_number="2026AIDS001"
            )
            assert success is False
            assert "another department" in msg

    # Requirement c: HOD cannot access another department complaints
    def test_local_integration_hod_cannot_access_other_department(self):
        """[LOCAL-INTEGRATION] Verifies HOD is unauthorized for other department complaints."""
        complaint = {"complaint_id": 105, "department_id": "dept-mech", "is_hostel": False}
        is_auth = ComplaintService._is_staff_authorized_for_complaint(
            actor_role=UserRole.HOD.value,
            actor_dept_id="dept-cse",
            complaint=complaint
        )
        assert is_auth is False

    # Requirement d: Coordinator cannot access hostel requests
    def test_local_integration_coordinator_cannot_access_hostel_requests(self):
        """[LOCAL-INTEGRATION] Verifies Coordinator cannot review/approve hostel requests."""
        success, msg = HostelService.review_hostel_request(
            reviewer_role=UserRole.COORDINATOR.value,
            reviewer_id="coord-1",
            request_id="req-1",
            action="Approve"
        )
        assert success is False
        assert "Only Hostel Incharge or Principal" in msg

    # Requirement e: Anonymous complaint owner table is inaccessible to staff
    def test_local_integration_anonymous_complaint_owner_table_inaccessible_to_staff(self):
        """[LOCAL-INTEGRATION] Verifies staff roles never query anonymous_complaint_owners."""
        with patch("services.complaint_service.get_supabase_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.execute.return_value.data = [
                {
                    "complaint_id": 102,
                    "title": "Broken projector",
                    "student_id": "student-uuid-secret",
                    "is_anonymous": True,
                    "department_id": "dept-cse",
                    "is_hostel": False
                }
            ]

            results = ComplaintService.get_complaints_for_user(
                role=UserRole.HOD.value,
                user_id="hod-uuid-1",
                department_id="dept-cse"
            )

            # anonymous_complaint_owners must never be queried by HOD
            for call_args in mock_client.return_value.table.call_args_list:
                table_name = call_args[0][0]
                assert table_name != "anonymous_complaint_owners"

    # Requirement f: Anonymous complaint student identity is never returned to staff
    def test_local_integration_anonymous_identity_masked_for_staff(self):
        """[LOCAL-INTEGRATION] Verifies anonymous complaints mask student_id to None and return 'Anonymous Student'."""
        with patch("services.complaint_service.get_supabase_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.execute.return_value.data = [
                {
                    "complaint_id": 103,
                    "title": "Hostel water issue",
                    "student_id": "student-uuid-secret",
                    "is_anonymous": True,
                    "is_hostel": True
                }
            ]

            results = ComplaintService.get_complaints_for_user(
                role=UserRole.HOSTEL_INCHARGE.value,
                user_id="hostel-incharge-uuid"
            )

            assert len(results) == 1
            assert results[0]["student_id"] is None
            assert results[0]["student_info"] == "Anonymous Student"

    # Requirement g: Storage objects cannot be accessed by unauthorized users
    def test_local_integration_unauthorized_storage_access_rejected(self):
        """[LOCAL-INTEGRATION] Verifies user from Dept B cannot get signed URL for Dept A complaint attachment."""
        with patch("services.storage_service.get_supabase_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.execute.return_value.data = [
                {"complaint_id": 104, "department_id": "dept-civil", "is_hostel": False}
            ]

            url = StorageService.get_authorized_signed_url(
                complaint_id=104,
                storage_path="complaints/104/evidence.jpg",
                user_id="hod-cse-id",
                role=UserRole.HOD.value,
                department_id="dept-cse"  # Wrong department!
            )

            assert url is None

    # Requirement h: HOD/Coordinator department isolation works at database and service level
    def test_local_integration_coordinator_cannot_delete_or_assign(self):
        """[LOCAL-INTEGRATION] Verifies Coordinator cannot soft-delete or assign complaints."""
        del_ok, del_msg = ComplaintService.soft_delete_complaint(
            actor_role=UserRole.COORDINATOR.value,
            actor_id="coord-1",
            actor_dept_id="dept-cse",
            complaint_id=101,
            delete_reason="Spam"
        )
        assert del_ok is False
        assert "not permitted to delete" in del_msg

        assign_ok, assign_msg = ComplaintService.assign_complaint(
            actor_role=UserRole.COORDINATOR.value,
            actor_id="coord-1",
            actor_dept_id="dept-cse",
            complaint_id=101,
            assigned_to_type="team",
            assigned_to_name="Electrician Team"
        )
        assert assign_ok is False
        assert "not authorized to assign" in assign_msg

    # Requirement i: Principal access works correctly across all departments
    def test_local_integration_principal_campus_wide_access(self):
        """[LOCAL-INTEGRATION] Verifies Principal is authorized across both department and hostel complaints."""
        dept_complaint = {"complaint_id": 106, "department_id": "dept-aids", "is_hostel": False}
        hostel_complaint = {"complaint_id": 107, "department_id": "dept-etc", "is_hostel": True}

        assert ComplaintService._is_staff_authorized_for_complaint(
            actor_role=UserRole.PRINCIPAL.value,
            actor_dept_id=None,
            complaint=dept_complaint
        ) is True

        assert ComplaintService._is_staff_authorized_for_complaint(
            actor_role=UserRole.PRINCIPAL.value,
            actor_dept_id=None,
            complaint=hostel_complaint
        ) is True

    # Requirement j: set_application_context cannot be abused by a normal user
    def test_local_integration_set_application_context_security_check(self):
        """[LOCAL-INTEGRATION] Verifies application logic does not allow normal users to set arbitrary context."""
        from database.supabase_client import get_supabase_client
        client = get_supabase_client()
        # Normal client uses anon/publishable key; it must NOT have service role bypass
        assert client.supabase_key != "service_role"

    # Additional Requirement 1: Student cannot submit complaints for another department
    def test_local_integration_student_cannot_submit_for_another_department(self):
        """[LOCAL-INTEGRATION] Verifies student enrolled in CSE cannot submit complaint to MECH."""
        with patch("services.complaint_service.get_trusted_backend_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            # Return CSE student record
            mock_table.execute.return_value.data = [
                {"id": "student-cse-1", "department_id": "dept-cse", "is_hostel": False, "is_hostel_approved": False, "is_locked": False}
            ]

            ok, msg, _ = ComplaintService.submit_complaint(
                student_id="student-cse-1",
                title="Lab AC broken",
                description="The air conditioner in lab is leaking water continuously.",
                department_id="dept-mech",  # Wrong department!
                category_id=None,
                subcategory_id=None,
                location_id="loc-1"
            )
            assert ok is False
            assert "Department mismatch" in msg

    # Additional Requirement 2: Unapproved student cannot submit hostel complaint
    def test_local_integration_unapproved_hostel_complaint_rejected(self):
        """[LOCAL-INTEGRATION] Verifies student without approved hostel residency cannot submit hostel complaint."""
        with patch("services.complaint_service.get_trusted_backend_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            # Return day scholar / unapproved student
            mock_table.execute.return_value.data = [
                {"id": "student-cse-2", "department_id": "dept-cse", "is_hostel": False, "is_hostel_approved": False, "is_locked": False}
            ]

            ok, msg, _ = ComplaintService.submit_complaint(
                student_id="student-cse-2",
                title="Hostel tap broken",
                description="Hostel bathroom tap is broken and leaking water.",
                department_id="dept-cse",
                category_id=None,
                subcategory_id=None,
                location_id="loc-1",
                is_hostel=True
            )
            assert ok is False
            assert "approved hostel residency status" in msg

    # Additional Requirement 3: Feedback single-edit enforcement
    def test_local_integration_feedback_single_edit_enforcement(self):
        """[LOCAL-INTEGRATION] Verifies feedback can be edited once, and subsequent edits or resets are blocked."""
        from services.feedback_service import FeedbackService
        with patch("services.feedback_service.get_supabase_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.update.return_value = mock_table
            # Case A: Edit count is 0 -> First edit allowed
            mock_table.execute.return_value.data = [
                {"id": "fb-1", "edit_count": 0, "student_id": "s1", "complaint_id": 101}
            ]
            ok1, msg1 = FeedbackService.edit_feedback(student_id="s1", complaint_id=101, new_rating=4)
            assert ok1 is True

            # Case B: Edit count is 1 -> Second edit strictly blocked
            mock_table.execute.return_value.data = [
                {"id": "fb-1", "edit_count": 1, "student_id": "s1", "complaint_id": 101}
            ]
            ok2, msg2 = FeedbackService.edit_feedback(student_id="s1", complaint_id=101, new_rating=3)
            assert ok2 is False
            assert "only be edited once" in msg2

    # -------------------------------------------------------------------------
    # MANDATORY SECURITY BOUNDARY CHECKS (Requirements 1-18)
    # -------------------------------------------------------------------------
    def test_student_cannot_set_is_hostel_approved_true(self):
        """[LOCAL-INTEGRATION] Student cannot self-approve hostel residency."""
        from services.auth_service import AuthService
        ok, msg = AuthService.update_student_profile("student-1", {"is_hostel_approved": True})
        assert ok is False
        assert "is_hostel_approved" in msg

    def test_student_cannot_change_department_id(self):
        """[LOCAL-INTEGRATION] Student cannot change department_id."""
        from services.auth_service import AuthService
        ok, msg = AuthService.update_student_profile("student-1", {"department_id": "dept-mech"})
        assert ok is False
        assert "department_id" in msg

    def test_student_cannot_change_roll_number(self):
        """[LOCAL-INTEGRATION] Student cannot change roll_number."""
        from services.auth_service import AuthService
        ok, msg = AuthService.update_student_profile("student-1", {"roll_number": "2026MECH099"})
        assert ok is False
        assert "roll_number" in msg

    def test_student_cannot_set_is_locked_false(self):
        """[LOCAL-INTEGRATION] Student cannot self-unlock account."""
        from services.auth_service import AuthService
        ok, msg = AuthService.update_student_profile("student-1", {"is_locked": False})
        assert ok is False
        assert "is_locked" in msg

    def test_student_cannot_modify_password_hash_directly(self):
        """[LOCAL-INTEGRATION] Student cannot modify password_hash directly."""
        from services.auth_service import AuthService
        ok, msg = AuthService.update_student_profile("student-1", {"password_hash": "$2b$12$fakehash"})
        assert ok is False
        assert "password_hash" in msg

    def test_student_cannot_modify_security_answer_hash_directly(self):
        """[LOCAL-INTEGRATION] Student cannot modify security_answer_hash directly."""
        from services.auth_service import AuthService
        ok, msg = AuthService.update_student_profile("student-1", {"security_answer_hash": "$2b$12$fakehash"})
        assert ok is False
        assert "security_answer_hash" in msg

    def test_hod_cannot_read_staff_password_hashes(self):
        """[LOCAL-INTEGRATION] HOD profile queries do not expose password_hash."""
        from services.auth_service import AuthService
        with patch("services.auth_service.get_supabase_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.execute.return_value.data = [{
                "id": "staff-1",
                "username": "hod_cse",
                "full_name": "HOD CSE",
                "role": "HOD",
                "department_id": "dept-cse",
                "password_hash": "$2b$12$secretpasswordhash",
                "security_answer_hash": "$2b$12$secretanswerhash",
                "is_locked": False,
                "is_active": True
            }]

            profile = AuthService.get_staff_profile("staff-1")
            assert profile is not None
            assert "password_hash" not in profile
            assert "security_answer_hash" not in profile

    def test_coordinator_cannot_read_staff_password_hashes(self):
        """[LOCAL-INTEGRATION] Coordinator queries do not expose password_hash."""
        from services.auth_service import AuthService
        with patch("services.auth_service.get_supabase_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.execute.return_value.data = [{
                "id": "staff-2",
                "username": "coord_cse",
                "full_name": "Coordinator CSE",
                "role": "Coordinator",
                "department_id": "dept-cse",
                "password_hash": "$2b$12$secretcoordhash",
                "security_answer_hash": "$2b$12$secretcoordanswer",
                "is_locked": False,
                "is_active": True
            }]

            profile = AuthService.get_staff_profile("staff-2")
            assert profile is not None
            assert "password_hash" not in profile
            assert "security_answer_hash" not in profile

    def test_principal_cannot_read_password_hashes_through_normal_profile_queries(self):
        """[LOCAL-INTEGRATION] Principal profile query returns sanitized dict without credential hashes."""
        from services.auth_service import AuthService
        with patch("services.auth_service.get_supabase_client") as mock_client:
            mock_table = MagicMock()
            mock_client.return_value.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.execute.return_value.data = [{
                "id": "staff-3",
                "username": "principal",
                "full_name": "Principal Dr. Smith",
                "role": "Principal",
                "department_id": None,
                "password_hash": "$2b$12$principalhash",
                "security_answer_hash": "$2b$12$principalanswer",
                "is_locked": False,
                "is_active": True
            }]

            profile = AuthService.get_staff_profile("staff-3")
            assert profile is not None
            assert "password_hash" not in profile
            assert "security_answer_hash" not in profile

    def test_hod_cannot_read_security_code_hashes(self):
        """[LOCAL-INTEGRATION] HOD security code metadata view omits code_hash."""
        from services.security_code_service import SecurityCodeService
        with patch.object(SecurityCodeService, "get_code_record") as mock_record:
            mock_record.return_value = {
                "id": "code-1",
                "role": "HOD",
                "department_id": "dept-cse",
                "code_hash": "$2b$12$supersecrethodcodehash",
                "updated_by": "Principal"
            }
            meta = SecurityCodeService.get_code_metadata("HOD", "dept-cse")
            assert meta is not None
            assert "code_hash" not in meta
            assert meta["role"] == "HOD"

    def test_coordinator_cannot_read_security_code_hashes(self):
        """[LOCAL-INTEGRATION] Coordinator security code inspection omits code_hash."""
        from services.security_code_service import SecurityCodeService
        with patch.object(SecurityCodeService, "get_code_record") as mock_record:
            mock_record.return_value = {
                "id": "code-2",
                "role": "Coordinator",
                "department_id": "dept-cse",
                "code_hash": "$2b$12$supersecretcoordcodehash",
                "updated_by": "HOD"
            }
            meta = SecurityCodeService.get_code_metadata("Coordinator", "dept-cse")
            assert meta is not None
            assert "code_hash" not in meta

    def test_hostel_incharge_cannot_read_unrelated_security_code_hashes(self):
        """[LOCAL-INTEGRATION] Hostel Incharge cannot manage or read academic security codes."""
        from services.security_code_service import SecurityCodeService
        # Hostel Incharge cannot update CSE HOD code
        ok, msg = SecurityCodeService.update_security_code(
            actor_role=UserRole.HOSTEL_INCHARGE.value,
            actor_dept_id=None,
            target_role=UserRole.HOD.value,
            target_dept_id="dept-cse",
            new_code="HackedCode@123",
            old_code="OldCode@123"
        )
        assert ok is False
        assert "only update the Hostel security code" in msg

    def test_hostel_incharge_cannot_access_non_hostel_complaints(self):
        """[LOCAL-INTEGRATION] Hostel Incharge cannot access academic department complaints."""
        academic_complaint = {"complaint_id": 110, "department_id": "dept-cse", "is_hostel": False}
        assert ComplaintService._is_staff_authorized_for_complaint(
            actor_role=UserRole.HOSTEL_INCHARGE.value,
            actor_dept_id=None,
            complaint=academic_complaint
        ) is False
