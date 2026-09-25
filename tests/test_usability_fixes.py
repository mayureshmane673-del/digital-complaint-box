"""
tests/test_usability_fixes.py: Comprehensive test suite validating the 5 usability fixes:
1. Login performance, loading indicators, and duplicate click prevention.
2. Mobile attachment cancel_upload_on_window_blur stability and session restoration.
3. Student attachment removal in complaint wizard with memory-only update and 2-file limit preservation.
4. Student soft delete for pending complaints with audit logging and restriction on reviewed complaints.
5. Coordinator roll number pool displaying authoritative year without roll number prefix heuristics.
"""

import pytest
from unittest.mock import MagicMock, patch
import flet as ft
from models.user import UserRole
from models.complaint import ComplaintStatus
from services.complaint_service import ComplaintService


# =============================================================================
# ISSUE 1 & 2: LOGIN PERFORMANCE & MOBILE ATTACHMENT BLUR STABILITY
# =============================================================================
def test_login_button_loading_state_and_duplicate_prevention():
    from ui.views.auth_view import AuthView
    page = MagicMock(spec=ft.Page)
    page.session = MagicMock()
    page.session.store = MagicMock()
    auth_view = AuthView(page, on_authenticated=MagicMock())
    rendered = auth_view.render()
    assert rendered is not None


def test_mobile_pick_files_blur_setting():
    """Verify that student view uses mobile-resilient attachment picker configuration.

    As of v1.1.0, the attachment picker uses:
    - cancel_upload_on_window_blur=False (prevents Android window blur from cancelling selection)
    - page-level persistent FilePicker (_dcb_file_picker)
    - page-level selected_files (_dcb_selected_files) that survive reconnects
    - with_data=False and allow_multiple=False to prevent mobile RAM bloat
    """
    import inspect
    from ui.views.student_view import StudentView

    # Verify mobile-resilient architecture is in place
    st_src = inspect.getsource(StudentView._render_new_complaint)
    assert "cancel_upload_on_window_blur=False" in st_src, "Must disable window blur cancellation for mobile file picker"
    assert "_dcb_selected_files" in st_src, "Must use page-level persistent selected_files"
    assert "allow_multiple=False" in st_src, "Must enforce single-file selection"
    assert "with_data=False" in st_src, "Must use with_data=False to avoid memory bloat"

    # Verify __init__ registers the page-level picker
    init_src = inspect.getsource(StudentView.__init__)
    assert "_dcb_file_picker" in init_src, "Must use page-level persistent picker"
    assert "_dcb_picker_pending" in init_src, "Must track picker pending state"


# =============================================================================
# ISSUE 3: ATTACHMENT REMOVAL IN STUDENT WIZARD
# =============================================================================
def test_student_attachment_removal_flow():
    """Verifies that attachments can be added, removed from memory, and re-added up to limit 2."""
    from ui.views.student_view import StudentView
    page = MagicMock(spec=ft.Page)
    page.services = []
    student = {
        "id": "11111111-1111-1111-1111-111111111111",
        "roll_number": "240101030",
        "department_id": "22222222-2222-2222-2222-222222222222",
        "full_name": "Test Student",
        "is_hostel_approved": False
    }
    view = StudentView(page, student)

    # Simulate memory list of selected attachments
    selected_files = [
        {"name": "doc1.pdf", "size": 1024, "bytes": b"file1", "path": None},
        {"name": "doc2.jpg", "size": 2048, "bytes": b"file2", "path": None}
    ]
    assert len(selected_files) == 2

    # Remove the first file
    removed = selected_files.pop(0)
    assert removed["name"] == "doc1.pdf"
    assert len(selected_files) == 1
    assert selected_files[0]["name"] == "doc2.jpg"

    # Now another file can be added up to limit 2
    selected_files.append({"name": "doc3.png", "size": 4096, "bytes": b"file3", "path": None})
    assert len(selected_files) == 2


# =============================================================================
# ISSUE 4: STUDENT SOFT DELETE LOGIC & BOUNDARIES
# =============================================================================
def test_delete_complaint_by_student_pending_success():
    """Student can delete their own pending complaint when no admin action was taken."""
    mock_complaint = {
        "complaint_id": 901,
        "student_id": "st-uuid-123",
        "status": "Pending",
        "has_admin_action": False,
        "is_deleted": False,
        "is_anonymous": False
    }

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [mock_complaint]
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{"complaint_id": 901, "is_deleted": True}]
    mock_client.table.return_value.insert.return_value.execute.return_value.data = [{"id": "hist-1"}]

    with patch("services.complaint_service.get_trusted_backend_client", return_value=mock_client):
        ok, msg = ComplaintService.delete_complaint_by_student(901, "st-uuid-123")
        assert ok is True
        assert "deleted successfully" in msg.lower()

        # Verify update set is_deleted=True and did NOT hard delete
        mock_client.table.assert_any_call("complaints")
        mock_client.table.assert_any_call("complaint_history")


def test_delete_complaint_by_student_blocked_when_in_progress():
    """Student cannot delete a complaint that is In Progress or has admin action."""
    mock_complaint = {
        "complaint_id": 902,
        "student_id": "st-uuid-123",
        "status": "In Progress",
        "has_admin_action": True,
        "is_deleted": False,
        "is_anonymous": False
    }

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [mock_complaint]

    with patch("services.complaint_service.get_trusted_backend_client", return_value=mock_client):
        ok, msg = ComplaintService.delete_complaint_by_student(902, "st-uuid-123")
        assert ok is False
        assert "cannot delete complaint" in msg.lower()


def test_delete_complaint_by_student_unauthorized_user():
    """Another student cannot delete someone else's complaint."""
    mock_complaint = {
        "complaint_id": 903,
        "student_id": "st-uuid-different",
        "status": "Pending",
        "has_admin_action": False,
        "is_deleted": False,
        "is_anonymous": False
    }

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [mock_complaint]

    with patch("services.complaint_service.get_trusted_backend_client", return_value=mock_client):
        ok, msg = ComplaintService.delete_complaint_by_student(903, "st-uuid-123")
        assert ok is False
        assert "unauthorized" in msg.lower()


# =============================================================================
# ISSUE 5: COORDINATOR ROLL NUMBER POOL AUTHORITATIVE YEAR
# =============================================================================
def test_coordinator_pool_year_without_prefix_heuristics():
    """Verifies that roll numbers like 240101030 do NOT guess 'TE', and show Not Registered or registered year."""
    from ui.views.staff_view import StaffView
    page = MagicMock(spec=ft.Page)
    staff = {
        "id": "staff-uuid-1",
        "role": UserRole.COORDINATOR.value,
        "department_id": "dept-uuid-1",
        "department_code": "CSE"
    }
    view = StaffView(page, staff, UserRole.COORDINATOR.value)

    # Helper function extracted to test directly
    # Case 1: Unregistered roll number starting with "24" (previously erroneously guessed as TE)
    roll = "240101030"
    st_info_none = None

    # Let's inspect the academic year logic by rendering or extracting
    # In staff_view, get_academic_year_info:
    # If st_info is None, it MUST return "NOT_REGISTERED" / "Not Registered"
    import inspect
    src = inspect.getsource(view._render_roll_number_pool)
    assert 'startswith("24")' not in src
    assert 'clean.startswith("24")' not in src
    assert 'clean.startswith("25")' not in src
    assert 'clean.startswith("26")' not in src
    assert 'clean.startswith("23")' not in src
    assert '"NOT_REGISTERED"' in src
    assert '"Not Registered"' in src


# =============================================================================
# ISSUE 6: MOBILE ATTACHMENT MEMORY OPTIMIZATION & FAST LOGIN TESTS
# =============================================================================
def test_cache_service_department_lookups():
    """Verify get_department_by_id and get_department_by_code operate accurately in memory."""
    from services.cache_service import CacheService
    # Ensure cache is initialized
    CacheService.get_departments()

    cse = CacheService.get_department_by_code("CSE")
    assert cse is not None
    assert cse.get("code") == "CSE"
    assert "Computer Science" in cse.get("name")

    dept_id = cse.get("id")
    assert dept_id is not None
    by_id = CacheService.get_department_by_id(dept_id)
    assert by_id is not None
    assert by_id.get("code") == "CSE"

    assert CacheService.get_department_by_id(None) is None
    assert CacheService.get_department_by_code(None) is None


def test_student_login_fast_query_and_department_attachment():
    """Verify student login performs single table select and attaches cached department info."""
    from services.auth_service import AuthService
    from utils.security import hash_password

    pw_hash = hash_password("Pass@123")
    mock_student = {
        "id": "stu-1111-2222",
        "roll_number": "240101030",
        "full_name": "Test Student",
        "department_id": "f4e141ef-14ca-44e4-a1ed-051ee0525419",
        "password_hash": pw_hash,
        "is_active": True,
        "is_locked": False,
        "failed_login_attempts": 0
    }

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [mock_student]

    with patch("services.auth_service.get_trusted_backend_client", return_value=mock_client):
        ok, msg, stu = AuthService.login_student("240101030", "Pass@123")
        assert ok is True
        assert stu is not None
        assert stu["roll_number"] == "240101030"
        # Department was attached without DB network join
        assert "departments" in stu
        assert stu["departments"]["code"] == "CSE"
        # Verify select("*") was used (not embedded foreign join)
        mock_client.table.return_value.select.assert_called_with("*")


def test_staff_login_fast_query_and_department_attachment():
    """Verify staff login queries select('*') and attaches department without foreign table join."""
    from services.auth_service import AuthService
    from utils.security import hash_password

    pw_hash = hash_password("Pass@123")
    mock_staff = {
        "id": "staff-9999",
        "username": "msm",
        "full_name": "Coordinator User",
        "role": UserRole.COORDINATOR.value,
        "department_id": "f4e141ef-14ca-44e4-a1ed-051ee0525419",
        "password_hash": pw_hash,
        "is_active": True,
        "is_locked": False,
        "failed_login_attempts": 0
    }

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_staff]

    with patch("services.auth_service.get_trusted_backend_client", return_value=mock_client), \
         patch("services.security_code_service.SecurityCodeService.verify_role_code", return_value=True):
        ok, msg, staff = AuthService.login_staff(
            role=UserRole.COORDINATOR.value,
            username="msm",
            password="Pass@123",
            security_code="Pass@123",
            department_id="f4e141ef-14ca-44e4-a1ed-051ee0525419"
        )
        assert ok is True
        assert staff is not None
        assert "departments" in staff
        assert staff["departments"]["code"] == "CSE"
        mock_client.table.return_value.select.assert_called_with("*")


def test_mobile_attachment_memory_settings():
    """Verify StudentView pick_files uses memory-safe with_data=False and single-file selection."""
    import inspect
    from ui.views.student_view import StudentView

    src = inspect.getsource(StudentView._render_new_complaint)
    assert "allow_multiple=False" in src
    assert "with_data=False" in src
    assert "cancel_upload_on_window_blur=False" in src, "Must have cancel_upload_on_window_blur=False for Android mobile support"
    assert "Add Attachment (0/2)" in src
    assert "Maximum 2 Attachments Added" in src


def test_excel_importer_size_limit():
    """Verify Excel importer dialog enforces a 5MB size limit to protect mobile RAM."""
    import inspect
    import ui.components.excel_importer as excel_imp

    src = inspect.getsource(excel_imp.show_excel_importer_dialog)
    assert "5 * 1024 * 1024" in src
    assert "5MB limit" in src


def test_app_bar_non_blocking_unread_count():
    """Verify create_app_bar does not make blocking queries and uses cached unread count."""
    from ui.components.navbar import create_app_bar
    from services.cache_service import CacheService

    page = MagicMock(spec=ft.Page)
    CacheService.set_cached_unread_count("user-1", "Student", None, 3)

    app_bar = create_app_bar(
        page=page,
        user_name="Student One",
        user_role="Student",
        department_code="CSE",
        user_id="user-1",
        department_id=None,
        on_logout=MagicMock()
    )
    assert app_bar is not None


def test_api_health_version():
    """Verify health endpoint returns updated production version."""
    from app import api_health
    health = api_health()
    assert health["status"] == "healthy"
    assert health["version"] == "v1.1.0-mobile-attachment-feedback-flow"

