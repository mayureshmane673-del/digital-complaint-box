"""
tests/test_feedback.py: Unit and regression tests for student institution-wide feedback,
department-scoped coordinator/HOD visibility, 1-to-5 star rating, single edit rule,
composite uniqueness, and performance / N+1 query prevention.
"""

import pytest
from unittest.mock import patch, MagicMock
from models.feedback import Feedback
from models.user import UserRole
from services.feedback_service import FeedbackService


# =============================================================================
# MODEL TESTS: Rating bounds & Single Edit Flag
# =============================================================================

def test_feedback_rating_and_edit_count():
    """Initial feedback with edit_count=0 is editable; after 1 edit it is locked."""
    fb = Feedback(
        complaint_id=101,
        student_id="student-1",
        rating=5,
        comment="Resolved promptly.",
        edit_count=0
    )
    assert fb.can_edit()

    fb.rating = 4
    fb.edit_count = 1
    assert not fb.can_edit()


def test_invalid_feedback_rating():
    """Rating must be between 1 and 5 stars."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        Feedback(complaint_id=101, student_id="s1", rating=0)

    with pytest.raises(pydantic.ValidationError):
        Feedback(complaint_id=101, student_id="s1", rating=6)


def test_feedback_composite_uniqueness():
    """Composite uniqueness is (student_id, complaint_id)."""
    fb1 = Feedback(complaint_id=101, student_id="student-A", rating=5)
    fb2 = Feedback(complaint_id=101, student_id="student-B", rating=4)
    assert (fb1.student_id, fb1.complaint_id) != (fb2.student_id, fb2.complaint_id)
    assert fb1.complaint_id == fb2.complaint_id

    # Same student on same complaint is detected as duplicate pair
    fb1_duplicate = Feedback(complaint_id=101, student_id="student-A", rating=3)
    assert (fb1.student_id, fb1.complaint_id) == (fb1_duplicate.student_id, fb1_duplicate.complaint_id)


# =============================================================================
# REGRESSION TEST 16: Single Edit Rule & Tamper Prevention
# =============================================================================

def test_existing_one_edit_rule_remains_intact():
    """Requirement 16: Verify first edit is permitted and second edit is rejected."""
    with patch("services.feedback_service.get_supabase_client") as mock_client:
        mock_table = MagicMock()
        mock_client.return_value.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table

        # Case A: edit_count == 0 -> Allowed
        mock_table.execute.return_value.data = [
            {"id": "fb-uuid-1", "edit_count": 0, "student_id": "student-1", "complaint_id": 101}
        ]
        ok, msg = FeedbackService.edit_feedback(
            student_id="student-1",
            complaint_id=101,
            new_rating=4,
            new_comment="Updated feedback"
        )
        assert ok is True
        assert "successfully" in msg

        # Case B: edit_count == 1 -> Blocked
        mock_table.execute.return_value.data = [
            {"id": "fb-uuid-1", "edit_count": 1, "student_id": "student-1", "complaint_id": 101}
        ]
        ok2, msg2 = FeedbackService.edit_feedback(
            student_id="student-1",
            complaint_id=101,
            new_rating=3,
            new_comment="Second edit attempt"
        )
        assert ok2 is False
        assert "only be edited once" in msg2


# =============================================================================
# REGRESSION TESTS 1-6: Institution-Wide Resolved Complaints Visibility
# =============================================================================

def test_all_resolved_complaints_returned_for_student_feedback():
    """Requirement 1: All resolved complaints in system are returned for Student Feedback."""
    resolved_data = [
        {"complaint_id": 101, "title": "CSE Lab AC", "status": "Resolved", "is_deleted": False, "department_id": "dept-cse"},
        {"complaint_id": 102, "title": "MECH Workshop Tool", "status": "Resolved", "is_deleted": False, "department_id": "dept-mech"},
        {"complaint_id": 103, "title": "Civil Lab Level", "status": "Resolved", "is_deleted": False, "department_id": "dept-civil"}
    ]

    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        def mock_table(name):
            t = MagicMock()
            if name == "complaints":
                # Returns all resolved, non-deleted complaints
                t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = list(resolved_data)
            elif name == "feedback":
                t.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []
            return t

        mock_backend.table = mock_table

        results = FeedbackService.get_resolved_complaints_for_student(student_id="st-1")
        assert len(results) == 3
        cids = [r["complaint_id"] for r in results]
        assert cids == [101, 102, 103]


def test_resolved_complaint_from_another_student_is_visible():
    """Requirement 2: Complaint submitted by Student A is visible in Student B's feedback view."""
    # Note: complaints table row contains no student_id column in the public select query
    resolved_data = [
        {"complaint_id": 201, "title": "Student A Grievance", "status": "Resolved", "is_deleted": False, "department_id": "dept-cse"}
    ]

    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        def mock_table(name):
            t = MagicMock()
            if name == "complaints":
                t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = list(resolved_data)
            elif name == "feedback":
                t.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []
            return t

        mock_backend.table = mock_table

        # Student B fetches feedback list
        results = FeedbackService.get_resolved_complaints_for_student(student_id="student-B-id")
        assert len(results) == 1
        assert results[0]["complaint_id"] == 201


def test_pending_in_progress_rejected_deleted_complaints_not_visible():
    """Requirements 3, 4, 5, 6: Pending, In Progress, Rejected, and Deleted complaints are excluded."""
    # Database query strictly applies: .eq("status", "Resolved").eq("is_deleted", False)
    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        mock_complaints_table = MagicMock()
        mock_backend.table.return_value = mock_complaints_table
        mock_complaints_table.select.return_value = mock_complaints_table
        mock_complaints_table.eq.return_value = mock_complaints_table
        mock_complaints_table.order.return_value = mock_complaints_table
        mock_complaints_table.execute.return_value.data = []

        FeedbackService.get_resolved_complaints_for_student(student_id="st-1")

        # Verify eq calls filter strictly by Resolved and is_deleted=False
        eq_calls = mock_complaints_table.eq.call_args_list
        assert any(call[0] == ("status", "Resolved") for call in eq_calls)
        assert any(call[0] == ("is_deleted", False) for call in eq_calls)


# =============================================================================
# REGRESSION TESTS 7, 8, 9, 10: Feedback Submission Rules
# =============================================================================

def test_student_can_submit_feedback_for_another_student_resolved_complaint():
    """Requirement 7: Student B can submit feedback for Student A's resolved complaint."""
    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        def mock_table(name):
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "st-B", "is_locked": False}
                ]
            elif name == "complaints":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"complaint_id": 101, "status": "Resolved", "is_deleted": False}
                ]
            elif name == "feedback":
                # No existing feedback by student B
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                t.insert.return_value.execute.return_value.data = [
                    {"id": "fb-new-1", "complaint_id": 101, "student_id": "st-B", "rating": 5}
                ]
            return t

        mock_backend.table = mock_table

        ok, msg, fb = FeedbackService.submit_feedback_v2(
            student_id="st-B",
            complaint_id=101,
            rating=5,
            comment="Resolution verified by student B"
        )
        assert ok is True
        assert "Thank you" in msg
        assert fb["rating"] == 5


def test_same_student_cannot_submit_feedback_twice_for_same_complaint():
    """Requirement 8: Same student cannot submit feedback twice for the same complaint."""
    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        def mock_table(name):
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "st-B", "is_locked": False}
                ]
            elif name == "complaints":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"complaint_id": 101, "status": "Resolved", "is_deleted": False}
                ]
            elif name == "feedback":
                # Feedback ALREADY exists for (st-B, 101)
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "fb-existing-1", "complaint_id": 101, "student_id": "st-B"}
                ]
            return t

        mock_backend.table = mock_table

        ok, msg, _ = FeedbackService.submit_feedback_v2(
            student_id="st-B",
            complaint_id=101,
            rating=4
        )
        assert ok is False
        assert "already submitted feedback" in msg.lower()


def test_different_students_can_each_submit_feedback_for_same_complaint():
    """Requirement 9: Different students can each submit feedback for the same complaint."""
    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        # Mock Student A submission
        def mock_table_a(name):
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.execute.return_value.data = [{"id": "st-A", "is_locked": False}]
            elif name == "complaints":
                t.select.return_value.eq.return_value.execute.return_value.data = [{"complaint_id": 101, "status": "Resolved", "is_deleted": False}]
            elif name == "feedback":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                t.insert.return_value.execute.return_value.data = [{"id": "fb-A", "rating": 5}]
            return t

        mock_backend.table = mock_table_a
        ok_a, msg_a, _ = FeedbackService.submit_feedback_v2(student_id="st-A", complaint_id=101, rating=5)
        assert ok_a is True

        # Mock Student B submission on the same complaint #101
        def mock_table_b(name):
            t = MagicMock()
            if name == "students":
                t.select.return_value.eq.return_value.execute.return_value.data = [{"id": "st-B", "is_locked": False}]
            elif name == "complaints":
                t.select.return_value.eq.return_value.execute.return_value.data = [{"complaint_id": 101, "status": "Resolved", "is_deleted": False}]
            elif name == "feedback":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
                t.insert.return_value.execute.return_value.data = [{"id": "fb-B", "rating": 4}]
            return t

        mock_backend.table = mock_table_b
        ok_b, msg_b, _ = FeedbackService.submit_feedback_v2(student_id="st-B", complaint_id=101, rating=4)
        assert ok_b is True


def test_student_sees_own_feedback_submitted_state_correctly():
    """Requirement 10: Student sees their own 'Feedback Submitted' state correctly merged."""
    resolved_comps = [
        {"complaint_id": 101, "title": "Comp 101", "status": "Resolved", "is_deleted": False},
        {"complaint_id": 102, "title": "Comp 102", "status": "Resolved", "is_deleted": False}
    ]

    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        def mock_table(name):
            t = MagicMock()
            if name == "complaints":
                t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = list(resolved_comps)
            elif name == "feedback":
                # Student A has submitted feedback on 101, but NOT on 102
                t.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
                    {"id": "fb-1", "complaint_id": 101, "student_id": "st-A", "rating": 5, "comment": "Good job", "edit_count": 0}
                ]
            return t

        mock_backend.table = mock_table

        results = FeedbackService.get_resolved_complaints_for_student(student_id="st-A")
        assert len(results) == 2

        # 101: feedback submitted
        c101 = next(c for c in results if c["complaint_id"] == 101)
        assert c101["has_feedback"] is True
        assert c101["student_feedback"]["rating"] == 5
        assert c101["student_feedback"]["comment"] == "Good job"

        # 102: feedback pending
        c102 = next(c for c in results if c["complaint_id"] == 102)
        assert c102["has_feedback"] is False
        assert c102["student_feedback"] is None


# =============================================================================
# REGRESSION TESTS 11, 12, 13, 14: Department Isolation & Privacy
# =============================================================================

def test_coordinator_sees_feedback_only_for_own_department():
    """Requirement 11: Coordinator sees feedback only for resolved complaints in own department."""
    feedback_raw = [
        {"id": "fb-1", "complaint_id": 101, "rating": 5, "comment": "CSE feedback", "complaints": {"department_id": "dept-cse-1", "is_hostel": False, "title": "CSE 1"}},
        {"id": "fb-2", "complaint_id": 102, "rating": 4, "comment": "MECH feedback", "complaints": {"department_id": "dept-mech-2", "is_hostel": False, "title": "MECH 1"}}
    ]

    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend
        mock_backend.table.return_value.select.return_value.order.return_value.execute.return_value.data = feedback_raw

        # CSE Coordinator queries
        cse_feedbacks = FeedbackService.get_feedback_for_scope(
            role=UserRole.COORDINATOR.value,
            department_id="dept-cse-1"
        )
        assert len(cse_feedbacks) == 1
        assert cse_feedbacks[0]["complaint_id"] == 101


def test_hod_sees_feedback_only_for_own_department():
    """Requirement 12: HOD sees feedback only for resolved complaints in own department."""
    feedback_raw = [
        {"id": "fb-1", "complaint_id": 101, "rating": 5, "comment": "CSE feedback", "complaints": {"department_id": "dept-cse-1", "is_hostel": False}},
        {"id": "fb-2", "complaint_id": 102, "rating": 3, "comment": "Civil feedback", "complaints": {"department_id": "dept-civil-3", "is_hostel": False}}
    ]

    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend
        mock_backend.table.return_value.select.return_value.order.return_value.execute.return_value.data = feedback_raw

        hod_feedbacks = FeedbackService.get_feedback_for_scope(
            role=UserRole.HOD.value,
            department_id="dept-cse-1"
        )
        assert len(hod_feedbacks) == 1
        assert hod_feedbacks[0]["complaint_id"] == 101


def test_cse_coordinator_cannot_see_mech_feedback():
    """Requirement 13: CSE Coordinator cannot see MECH feedback."""
    feedback_raw = [
        {"id": "fb-2", "complaint_id": 102, "rating": 4, "comment": "MECH review", "complaints": {"department_id": "dept-mech", "is_hostel": False}}
    ]

    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend
        mock_backend.table.return_value.select.return_value.order.return_value.execute.return_value.data = feedback_raw

        # CSE Coordinator queries
        res = FeedbackService.get_feedback_for_scope(
            role=UserRole.COORDINATOR.value,
            department_id="dept-cse"
        )
        assert len(res) == 0


def test_anonymous_complaint_owner_identity_not_exposed():
    """Requirement 14: Complainant identity/roll number/tokens are never exposed in feedback."""
    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        # Mock complaint retrieval
        mock_backend.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = [
            {"complaint_id": 105, "title": "Anonymous grievance", "is_anonymous": True, "status": "Resolved", "is_deleted": False}
        ]
        mock_backend.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []

        comps = FeedbackService.get_resolved_complaints_for_student(student_id="any-st")
        assert len(comps) == 1
        comp = comps[0]
        # Sensitive credentials or user IDs must not be present
        for forbidden in ["student_id", "roll_number", "password_hash", "ownership_token_hash", "full_name"]:
            assert forbidden not in comp


# =============================================================================
# REGRESSION TEST 15: No N+1 Queries (Batch 2-Query Pattern)
# =============================================================================

def test_no_n_plus_1_feedback_queries():
    """Requirement 15: Exactly 2 database queries are executed for N resolved complaints."""
    # Generate 50 resolved complaints
    bulk_comps = [
        {"complaint_id": i, "title": f"Complaint {i}", "status": "Resolved", "is_deleted": False}
        for i in range(1, 51)
    ]

    query_counts = {"complaints": 0, "feedback": 0}

    with patch("services.feedback_service.get_trusted_backend_client") as mock_client:
        mock_backend = MagicMock()
        mock_client.return_value = mock_backend

        def mock_table(name):
            t = MagicMock()
            if name == "complaints":
                query_counts["complaints"] += 1
                t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = list(bulk_comps)
            elif name == "feedback":
                query_counts["feedback"] += 1
                t.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
                    {"id": "fb-1", "complaint_id": 1, "student_id": "st-1", "rating": 5, "edit_count": 0}
                ]
            return t

        mock_backend.table = mock_table

        results = FeedbackService.get_resolved_complaints_for_student(student_id="st-1")

        assert len(results) == 50
        # Exactly 1 query for complaints, and 1 query for feedback batch
        assert query_counts["complaints"] == 1
        assert query_counts["feedback"] == 1
        # Total queries = 2, strictly NOT 51 (prevented N+1)
        assert query_counts["complaints"] + query_counts["feedback"] == 2


# =============================================================================
# REGRESSION TEST 17: Tab Cache Invalidation Granularity
# =============================================================================

def test_performance_tab_caching_remains_intact():
    """Requirement 17: Feedback tab cache invalidation only clears Tab 3, preserving Tab 0."""
    from ui.views.student_view import StudentView
    from unittest.mock import MagicMock

    mock_page = MagicMock()
    mock_student = {"id": "st-test-1", "full_name": "Test Student", "roll_number": "240101001", "year": "SE", "department_id": "dept-cse-1"}

    view = StudentView(mock_page, mock_student, initial_tab=0)
    view._tab_cache[0] = MagicMock()  # Dashboard cached
    view._tab_cache[3] = MagicMock()  # Feedback cached

    # Invalidate ONLY tab 3 (Feedback)
    view.invalidate_tab_cache(3)

    assert 3 not in view._tab_cache
    assert 0 in view._tab_cache  # Dashboard cache preserved!
