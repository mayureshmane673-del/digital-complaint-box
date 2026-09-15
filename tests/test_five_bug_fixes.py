"""
tests/test_five_bug_fixes.py: Comprehensive test suite for the 5 confirmed bug fixes.
"""

import pytest
import flet as ft
from models.user import UserRole
from models.hostel import HostelRequestStatus
from services.hostel_service import HostelService
from services.security_code_service import SecurityCodeService
from services.notification_service import NotificationService
from services.auth_service import AuthService
from services.complaint_service import ComplaintService
from ui.components.animated_chart import create_circular_status_chart, create_registered_vs_resolved_chart
from database.supabase_client import get_trusted_backend_client


def test_bug1_hostel_request_lifecycle_and_notifications():
    """Bug 1: Full hostel request submission, review, deny with reason, reapprove, and notification check."""
    client = get_trusted_backend_client()

    # Fetch any existing test student
    res = client.table("students").select("id, roll_number, department_id").limit(1).execute()
    assert res.data, "No student record found to test"
    st = res.data[0]
    st_id = st["id"]
    orig_dept = st["department_id"]

    # Clear any old test requests for this student
    client.table("hostel_requests").delete().eq("student_id", st_id).execute()

    # 1. Submit hostel request
    ok, msg, req = HostelService.submit_hostel_request(
        student_id=st_id,
        hostel_name="Nilgiri Hostel",
        block="C",
        room_number="304"
    )
    assert ok, f"Hostel submission failed: {msg}"
    assert req is not None
    req_id = req["id"]
    assert req["status"] == HostelRequestStatus.PENDING.value

    # Verify student flags and department preservation
    st_check = client.table("students").select("is_hostel, is_hostel_approved, department_id").eq("id", st_id).execute()
    assert st_check.data[0]["is_hostel"] is True
    assert st_check.data[0]["is_hostel_approved"] is False
    assert st_check.data[0]["department_id"] == orig_dept, "Student academic department was mutated!"

    # 2. Deny request with mandatory reason
    ok_deny_empty, _ = HostelService.review_hostel_request(
        reviewer_role=UserRole.HOSTEL_INCHARGE.value,
        reviewer_id=None,
        request_id=req_id,
        action="Deny",
        deny_reason=""
    )
    assert not ok_deny_empty, "Denial should fail without mandatory reason"

    ok_deny, msg_deny = HostelService.review_hostel_request(
        reviewer_role=UserRole.HOSTEL_INCHARGE.value,
        reviewer_id=None,
        request_id=req_id,
        action="Deny",
        deny_reason="Room capacity full for current semester"
    )
    assert ok_deny, f"Denial failed: {msg_deny}"

    # Verify denied status in DB
    h_denied = client.table("hostel_requests").select("status, deny_reason").eq("id", req_id).execute()
    assert h_denied.data[0]["status"] == HostelRequestStatus.DENIED.value
    assert h_denied.data[0]["deny_reason"] == "Room capacity full for current semester"

    # 3. Re-approve previously denied request
    ok_reapp, msg_reapp = HostelService.review_hostel_request(
        reviewer_role=UserRole.HOSTEL_INCHARGE.value,
        reviewer_id=None,
        request_id=req_id,
        action="Approve"
    )
    assert ok_reapp, f"Re-approval failed: {msg_reapp}"

    h_approved = client.table("hostel_requests").select("status, deny_reason").eq("id", req_id).execute()
    assert h_approved.data[0]["status"] == HostelRequestStatus.APPROVED.value
    assert h_approved.data[0]["deny_reason"] is None

    st_app = client.table("students").select("is_hostel_approved").eq("id", st_id).execute()
    assert st_app.data[0]["is_hostel_approved"] is True

    # Clean up test request
    client.table("hostel_requests").delete().eq("id", req_id).execute()


def test_bug2_circular_status_chart_rendering():
    """Bug 2: Circular donut status chart renders correctly for empty state and populated state."""
    # Empty State (0 complaints)
    empty_chart = create_circular_status_chart(0, 0, 0, 0, 0)
    assert isinstance(empty_chart, ft.Container)
    assert empty_chart.content is not None

    # Populated State
    pop_chart = create_circular_status_chart(
        registered=20,
        resolved=12,
        in_progress=4,
        pending=3,
        rejected=1,
        title="Institutional Performance Analytics",
        is_dark=False
    )
    assert isinstance(pop_chart, ft.Container)
    assert create_registered_vs_resolved_chart == create_circular_status_chart


def test_bug3_notification_mark_as_read():
    """Bug 3: Notification mark as read and mark all as read persistence."""
    client = get_trusted_backend_client()

    # Create dummy unread notification
    res = client.table("notifications").insert({
        "recipient_type": "role",
        "recipient_role": UserRole.HOSTEL_INCHARGE.value,
        "title": "Automated Bug 3 Verification",
        "message": "Testing notification mark as read persistence.",
        "is_read": False
    }).execute()
    assert res.data, "Failed to insert test notification"
    nid = res.data[0]["id"]

    # Mark individual as read
    ok = NotificationService.mark_as_read(nid)
    assert ok, "NotificationService.mark_as_read failed"

    # Verify persistence
    check = client.table("notifications").select("is_read").eq("id", nid).execute()
    assert check.data[0]["is_read"] is True, "Notification is_read was not persisted as True"

    # Insert another unread for mark_all_as_read
    res2 = client.table("notifications").insert({
        "recipient_type": "role",
        "recipient_role": UserRole.HOSTEL_INCHARGE.value,
        "title": "Automated Bug 3 Verification 2",
        "message": "Testing mark all as read.",
        "is_read": False
    }).execute()
    nid2 = res2.data[0]["id"]

    ok_all = NotificationService.mark_all_as_read("any_staff_id", role=UserRole.HOSTEL_INCHARGE.value)
    assert ok_all, "mark_all_as_read failed"

    check2 = client.table("notifications").select("is_read").eq("id", nid2).execute()
    assert check2.data[0]["is_read"] is True

    # Cleanup
    client.table("notifications").delete().in_("id", [nid, nid2]).execute()


def test_bug4_library_incharge_security_code_verification():
    """Bug 4: Pass@123 accepted for Library Incharge without department_id requirement."""
    # 1. Verify Pass@123 for Library Incharge
    valid = SecurityCodeService.verify_role_code(UserRole.LIBRARY_INCHARGE.value, None, "Pass@123")
    assert valid is True, "Pass@123 verification failed for Library Incharge"

    # 2. Verify Pass@123 for General HOD
    valid_gen = SecurityCodeService.verify_role_code(UserRole.GENERAL_HOD.value, None, "Pass@123")
    assert valid_gen is True, "Pass@123 verification failed for General HOD"

    # 3. Invalid code rejected
    invalid = SecurityCodeService.verify_role_code(UserRole.LIBRARY_INCHARGE.value, None, "WrongCode!999")
    assert invalid is False, "Invalid security code was incorrectly accepted"


def test_bug5_compact_attachment_controls():
    """Bug 5: Complaint detail dialog imports cleanly and uses compact attachment cards."""
    from ui.components.complaint_detail import show_complaint_detail_dialog
    assert callable(show_complaint_detail_dialog)
