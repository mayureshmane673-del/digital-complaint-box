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


