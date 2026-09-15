"""
tests/test_roles.py: Unit tests verifying strict role permission boundaries.
"""

from models.user import UserRole
from services.security_code_service import SecurityCodeService
from services.complaint_service import ComplaintService


def test_coordinator_cannot_delete_or_assign():
    # Coordinator attempting to delete
    res, msg = ComplaintService.soft_delete_complaint(
        actor_role=UserRole.COORDINATOR.value,
        actor_id="coord-1",
        actor_dept_id="dept-cse",
        complaint_id=101,
        delete_reason="Testing unauthorized delete"
    )
    assert not res
    assert "not permitted to delete" in msg

    # Coordinator attempting to assign
    res, msg = ComplaintService.assign_complaint(
        actor_role=UserRole.COORDINATOR.value,
        actor_id="coord-1",
        actor_dept_id="dept-cse",
        complaint_id=101,
        assigned_to_type="team",
        assigned_to_name="Maintenance Team"
    )
    assert not res
    assert "not authorized to assign" in msg


def test_coordinator_cannot_change_security_codes():
    res, msg = SecurityCodeService.update_security_code(
        actor_role=UserRole.COORDINATOR.value,
        actor_dept_id="dept-cse",
        target_role=UserRole.HOD.value,
        target_dept_id="dept-cse",
        new_code="NewHODCode@123"
    )
    assert not res
    assert "not permitted to change security codes" in msg


def test_principal_cannot_manually_change_priority():
    res, msg = ComplaintService.change_priority(
        actor_role=UserRole.PRINCIPAL.value,
        actor_id="principal-1",
        actor_dept_id=None,
        complaint_id=101,
        new_priority="Urgent"
    )
    assert not res
    assert "Principal does not manually change complaint priority" in msg


def test_department_isolation_check():
    cse_complaint = {"department_id": "dept-cse", "is_hostel": False}
    # AIDS HOD cannot access CSE complaint
    assert not ComplaintService._is_staff_authorized_for_complaint(
        actor_role=UserRole.HOD.value,
        actor_dept_id="dept-aids",
        complaint=cse_complaint
    )
    # CSE HOD can access
    assert ComplaintService._is_staff_authorized_for_complaint(
        actor_role=UserRole.HOD.value,
        actor_dept_id="dept-cse",
        complaint=cse_complaint
    )
    # Principal can access all
    assert ComplaintService._is_staff_authorized_for_complaint(
        actor_role=UserRole.PRINCIPAL.value,
        actor_dept_id=None,
        complaint=cse_complaint
    )
    # Hostel Incharge cannot access academic department complaint
    assert not ComplaintService._is_staff_authorized_for_complaint(
        actor_role=UserRole.HOSTEL_INCHARGE.value,
        actor_dept_id=None,
        complaint=cse_complaint
    )
    # HOD cannot access hostel complaint
    hostel_complaint = {"department_id": "dept-cse", "is_hostel": True}
    assert not ComplaintService._is_staff_authorized_for_complaint(
        actor_role=UserRole.HOD.value,
        actor_dept_id="dept-cse",
        complaint=hostel_complaint
    )


def test_security_code_department_isolation():
    # CSE HOD cannot change AIDS security code
    res, msg = SecurityCodeService.update_security_code(
        actor_role=UserRole.HOD.value,
        actor_dept_id="dept-cse",
        target_role=UserRole.HOD.value,
        target_dept_id="dept-aids",
        new_code="AttemptedHOD@123",
        old_code="Pass@123"
    )
    assert not res
    assert "cannot modify security codes of other departments" in msg


def test_hostel_request_staff_isolation():
    from services.hostel_service import HostelService
    # HOD cannot review hostel request
    ok, msg = HostelService.review_hostel_request(
        reviewer_role=UserRole.HOD.value,
        reviewer_id="hod-1",
        request_id="req-123",
        action="Approve"
    )
    assert not ok
    assert "Only Hostel Incharge or Principal" in msg

    # Coordinator cannot review hostel request
    ok, msg = HostelService.review_hostel_request(
        reviewer_role=UserRole.COORDINATOR.value,
        reviewer_id="coord-1",
        request_id="req-123",
        action="Approve"
    )
    assert not ok
    assert "Only Hostel Incharge or Principal" in msg

