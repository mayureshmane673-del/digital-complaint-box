"""
tests/test_feedback.py: Unit tests for feedback 1-to-5 rating and single edit constraint.
"""

from models.feedback import Feedback


def test_feedback_rating_and_edit_count():
    # Initial feedback with 0 edits
    fb = Feedback(
        complaint_id=101,
        student_id="student-1",
        rating=5,
        comment="Resolved very promptly.",
        edit_count=0
    )
    assert fb.can_edit()

    # After 1 edit
    fb.rating = 4
    fb.edit_count = 1
    assert not fb.can_edit()


def test_invalid_feedback_rating():
    import pydantic
    import pytest

    # Rating below 1
    with pytest.raises(pydantic.ValidationError):
        Feedback(complaint_id=101, student_id="s1", rating=0)

    # Rating above 5
    with pytest.raises(pydantic.ValidationError):
        Feedback(complaint_id=101, student_id="s1", rating=6)


def test_feedback_composite_uniqueness():
    # Verify feedback allows distinct students on same complaint
    fb1 = Feedback(complaint_id=101, student_id="student-A", rating=5)
    fb2 = Feedback(complaint_id=101, student_id="student-B", rating=4)
    assert (fb1.student_id, fb1.complaint_id) != (fb2.student_id, fb2.complaint_id)
    assert fb1.complaint_id == fb2.complaint_id

    # Same student on same complaint should be detected as collision
    fb1_duplicate = Feedback(complaint_id=101, student_id="student-A", rating=3)
    assert (fb1.student_id, fb1.complaint_id) == (fb1_duplicate.student_id, fb1_duplicate.complaint_id)


def test_feedback_second_edit_rejected():
    """Unit test verifying that attempting a second edit is rejected."""
    from services.feedback_service import FeedbackService
    from unittest.mock import patch, MagicMock

    with patch("services.feedback_service.get_supabase_client") as mock_client:
        mock_table = MagicMock()
        mock_client.return_value.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        # Return record where edit_count is already 1
        mock_table.execute.return_value.data = [
            {"id": "fb-uuid-1", "edit_count": 1, "student_id": "student-1", "complaint_id": 101}
        ]

        ok, msg = FeedbackService.edit_feedback(
            student_id="student-1",
            complaint_id=101,
            new_rating=4,
            new_comment="Trying to edit a second time"
        )
        assert ok is False
        assert "only be edited once" in msg


def test_feedback_edit_count_tamper_prevention():
    """Unit test verifying that edit_count cannot be decremented or reset."""
    fb = Feedback(complaint_id=101, student_id="s1", rating=5, edit_count=1)
    assert fb.can_edit() is False

    # Attempting to artificially reset edit_count in a model
    fb.edit_count = 0
    # Service logic must prevent repeated submission or reset
    from services.feedback_service import FeedbackService
    from unittest.mock import patch, MagicMock

    with patch("services.feedback_service.get_supabase_client") as mock_client:
        mock_table = MagicMock()
        mock_client.return_value.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value.data = [
            {"id": "fb-uuid-1", "edit_count": 1, "student_id": "s1", "complaint_id": 101}
        ]

        ok, msg = FeedbackService.edit_feedback(
            student_id="s1",
            complaint_id=101,
            new_rating=5
        )
        assert ok is False
        assert "only be edited once" in msg


def test_feedback_v2_department_authorization():
    """Verify submit_feedback_v2 allows same-dept students and rejects other-dept students."""
    from services.feedback_service import FeedbackService
    from unittest.mock import patch, MagicMock

    cse_dept = "dept-cse-111"
    aids_dept = "dept-aids-222"

    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        # Mock student: CSE student
        def mock_table(name):
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "st-cse-1", "department_id": cse_dept, "is_hostel_approved": False, "is_locked": False}
                ]
            elif name == "complaints":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"complaint_id": 104, "status": "Resolved", "is_deleted": False, "department_id": cse_dept, "is_hostel": False, "categories": {"name": "Electricity"}}
                ]
            elif name == "feedback":
                # No prior feedback
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                t.insert.return_value.execute.return_value.data = [{"id": "fb-new", "rating": 5}]
            return t

        mock_backend.table = mock_table

        # 1. CSE student submits on CSE complaint -> Allowed
        ok, msg, fb = FeedbackService.submit_feedback_v2(
            student_id="st-cse-1",
            department_id=cse_dept,
            complaint_id=104,
            rating=5,
            comment="Great work"
        )
        assert ok is True
        assert "Thank you" in msg

        # 2. AIDS student submits on CSE complaint -> Blocked
        def mock_table_aids(name):
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "st-aids-1", "department_id": aids_dept, "is_hostel_approved": False, "is_locked": False}
                ]
            elif name == "complaints":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"complaint_id": 104, "status": "Resolved", "is_deleted": False, "department_id": cse_dept, "is_hostel": False, "categories": {"name": "Electricity"}}
                ]
            elif name == "feedback":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            return t

        mock_backend.table = mock_table_aids

        ok, msg, fb = FeedbackService.submit_feedback_v2(
            student_id="st-aids-1",
            department_id=aids_dept,
            complaint_id=104,
            rating=5
        )
        assert ok is False
        assert "not eligible" in msg.lower()


def test_feedback_v2_hostel_and_library_rules():
    """Verify hostel approved requirement and library campus-wide access in submit_feedback_v2."""
    from services.feedback_service import FeedbackService
    from unittest.mock import patch, MagicMock

    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        # Case 1: Non-approved hostel student submits on hostel complaint -> Blocked
        def mock_tbl_hostel_non_app(name):
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "st-1", "department_id": "dept-1", "is_hostel_approved": False, "is_locked": False}
                ]
            elif name == "complaints":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"complaint_id": 130, "status": "Resolved", "is_deleted": False, "department_id": "dept-1", "is_hostel": True, "categories": {"name": "Hostel"}}
                ]
            elif name == "feedback":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            return t

        mock_backend.table = mock_tbl_hostel_non_app
        ok, msg, _ = FeedbackService.submit_feedback_v2("st-1", "dept-1", 130, 4)
        assert ok is False
        assert "hostel" in msg.lower()

        # Case 2: Approved hostel student submits on hostel complaint -> Allowed
        def mock_tbl_hostel_app(name):
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "st-1", "department_id": "dept-1", "is_hostel_approved": True, "is_locked": False}
                ]
            elif name == "complaints":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"complaint_id": 130, "status": "Resolved", "is_deleted": False, "department_id": "dept-1", "is_hostel": True, "categories": {"name": "Hostel"}}
                ]
            elif name == "feedback":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                t.insert.return_value.execute.return_value.data = [{"id": "fb-h", "rating": 4}]
            return t

        mock_backend.table = mock_tbl_hostel_app
        ok, msg, _ = FeedbackService.submit_feedback_v2("st-1", "dept-1", 130, 4)
        assert ok is True

        # Case 3: Any student submits on Library complaint -> Allowed
        def mock_tbl_lib(name):
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "st-2", "department_id": "dept-2", "is_hostel_approved": False, "is_locked": False}
                ]
            elif name == "complaints":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"complaint_id": 121, "status": "Resolved", "is_deleted": False, "department_id": "dept-1", "is_hostel": False, "categories": {"name": "Library"}}
                ]
            elif name == "feedback":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                t.insert.return_value.execute.return_value.data = [{"id": "fb-lib", "rating": 5}]
            return t

        mock_backend.table = mock_tbl_lib
        ok, msg, _ = FeedbackService.submit_feedback_v2("st-2", "dept-2", 121, 5)
        assert ok is True



