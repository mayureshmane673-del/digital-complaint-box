"""
tests/test_complaints.py: Unit tests for complaint editing limits, admin lockouts, and soft-deletion constraints.
"""

from datetime import datetime, timezone, timedelta
from utils.validators import validate_description
from models.complaint import Complaint, ComplaintStatus, ComplaintPriority


def test_description_length_validation():
    # Less than 10 chars (9 characters)
    ok, err = validate_description("Too short")
    assert not ok
    assert "at least 10 characters" in err

    # Between 10 and 1000 chars
    ok, _ = validate_description("The classroom fan on row 3 is not working properly.")
    assert ok

    # Over 1000 chars
    ok, err = validate_description("a" * 1001)
    assert not ok
    assert "cannot exceed 1000 characters" in err


def test_student_10_minute_edit_window():
    now = datetime.now(timezone.utc)

    # 5 minutes ago -> editable
    c1 = Complaint(
        complaint_id=101,
        department_id="dept-1",
        title="Projector issue",
        description="Classroom projector bulb is flickering.",
        created_at=now - timedelta(minutes=5),
        has_admin_action=False,
        status=ComplaintStatus.PENDING
    )
    assert c1.is_editable_by_student()

    # 15 minutes ago -> locked
    c2 = Complaint(
        complaint_id=102,
        department_id="dept-1",
        title="Projector issue",
        description="Classroom projector bulb is flickering.",
        created_at=now - timedelta(minutes=15),
        has_admin_action=False,
        status=ComplaintStatus.PENDING
    )
    assert not c2.is_editable_by_student()


def test_immediate_lock_on_admin_action():
    now = datetime.now(timezone.utc)
    # Submitted 2 minutes ago, but HOD already viewed or assigned it
    c = Complaint(
        complaint_id=103,
        department_id="dept-1",
        title="Lab PC issue",
        description="PC #14 in Lab 3 blue screens on startup.",
        created_at=now - timedelta(minutes=2),
        has_admin_action=True,  # Admin has acted
        status=ComplaintStatus.IN_PROGRESS
    )
    assert not c.is_editable_by_student()


def test_soft_delete_constraints():
    c = Complaint(
        complaint_id=104,
        department_id="dept-1",
        title="Test issue",
        description="Valid description for complaint testing.",
        is_deleted=True,
        delete_reason="Duplicate submission by student.",
        deleted_by_role="HOD"
    )
    assert c.is_deleted
    assert c.delete_reason is not None
    assert not c.is_editable_by_student()


def test_anonymous_complaint_privacy():
    # Anonymous complaint has student_id = None in the complaint row
    anon = Complaint(
        complaint_id=105,
        department_id="dept-1",
        title="Faculty Behavior Issue",
        description="Anonymous complaint about attendance unfairness.",
        is_anonymous=True,
        student_id=None,
        status=ComplaintStatus.PENDING
    )
    assert anon.is_anonymous
    assert anon.student_id is None

    # Simulating staff payload sanitization
    staff_view_dict = anon.model_dump()
    assert staff_view_dict["student_id"] is None

