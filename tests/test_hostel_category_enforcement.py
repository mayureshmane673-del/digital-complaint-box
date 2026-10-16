"""
tests/test_hostel_category_enforcement.py: Unit tests verifying ComplaintService
enforces hostel residency checks when the complaint category is 'Hostel'.
"""

import pytest
from unittest.mock import patch, MagicMock
from services.complaint_service import ComplaintService


HOSTEL_CAT_ID = "51a1bd37-ede4-4e08-ad85-0fca9e12e5f7"
ACADEMIC_CAT_ID = "cat-academic-uuid-1"
DEPT_ID = "dept-cse"


def _build_mock_client(student_record, new_complaint_data=None):
    """Helper to mock get_trusted_backend_client with table queries and RPC calls."""
    mock_client = MagicMock()

    # Mock table calls (students, complaints, etc.)
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.neq.return_value = mock_table
    mock_table.update.return_value = mock_table

    # Default execute data: return student record
    mock_table.execute.return_value.data = [student_record] if student_record else []

    # Mock RPC call for submit_complaint_atomic
    mock_rpc = MagicMock()
    mock_client.rpc.return_value = mock_rpc
    mock_rpc.execute.return_value.data = new_complaint_data or {
        "complaint_id": 999,
        "title": "Valid complaint",
        "description": "Valid complaint description here.",
        "department_id": DEPT_ID,
        "status": "Pending"
    }

    return mock_client


class TestHostelCategoryEnforcement:
    """
    Verification of hostel category restrictions:
    (a) student without approved hostel access cannot submit with Hostel category;
    (b) student with approved hostel access can;
    (c) normal non-hostel category works for both.
    """

    # (a) Student without approved hostel access cannot submit with Hostel category
    def test_unapproved_student_cannot_submit_with_hostel_category_id(self):
        """Day scholar or unapproved student rejected when selecting Hostel category ID."""
        student_rec = {
            "id": "student-unapproved-1",
            "department_id": DEPT_ID,
            "is_hostel": False,
            "is_hostel_approved": False,
            "is_locked": False
        }
        mock_client = _build_mock_client(student_rec)

        with patch("services.complaint_service.get_trusted_backend_client", return_value=mock_client):
            ok, msg, comp = ComplaintService.submit_complaint(
                student_id="student-unapproved-1",
                title="Broken hostel window",
                description="The window in room 204 is broken and cannot close.",
                department_id=DEPT_ID,
                category_id=HOSTEL_CAT_ID,
                subcategory_id=None,
                location_id="loc-1",
                is_hostel=False  # Even if checkbox/flag is false, category is Hostel
            )
            assert ok is False
            assert "approved hostel residency status" in msg
            assert comp is None

    def test_unapproved_student_cannot_submit_with_hostel_category_name(self):
        """Unapproved student rejected when selecting Hostel by category name."""
        student_rec = {
            "id": "student-unapproved-2",
            "department_id": DEPT_ID,
            "is_hostel": True,
            "is_hostel_approved": False,  # Pending approval
            "is_locked": False
        }
        mock_client = _build_mock_client(student_rec)

        with patch("services.complaint_service.get_trusted_backend_client", return_value=mock_client):
            ok, msg, comp = ComplaintService.submit_complaint(
                student_id="student-unapproved-2",
                title="Hostel water leakage",
                description="Continuous water leakage in bathroom area.",
                department_id=DEPT_ID,
                category_id="Hostel",
                subcategory_id=None,
                location_id="loc-1",
                is_hostel=False
            )
            assert ok is False
            assert "approved hostel residency status" in msg
            assert comp is None

    def test_unapproved_student_cannot_submit_with_hostel_category_custom(self):
        """Unapproved student rejected when specifying 'Hostel' in custom category."""
        student_rec = {
            "id": "student-unapproved-3",
            "department_id": DEPT_ID,
            "is_hostel": False,
            "is_hostel_approved": False,
            "is_locked": False
        }
        mock_client = _build_mock_client(student_rec)

        with patch("services.complaint_service.get_trusted_backend_client", return_value=mock_client):
            ok, msg, comp = ComplaintService.submit_complaint(
                student_id="student-unapproved-3",
                title="Hostel corridor lights",
                description="Corridor lights are flickering on the 2nd floor.",
                department_id=DEPT_ID,
                category_id=None,
                subcategory_id=None,
                category_custom="Hostel",
                location_id="loc-1",
                is_hostel=False
            )
            assert ok is False
            assert "approved hostel residency status" in msg
            assert comp is None

    # (b) Student with approved hostel access can submit with Hostel category
    def test_approved_student_can_submit_with_hostel_category(self):
        """Approved hostel resident can successfully submit hostel complaints."""
        student_rec = {
            "id": "student-approved-1",
            "department_id": DEPT_ID,
            "is_hostel": True,
            "is_hostel_approved": True,
            "is_locked": False
        }
        mock_client = _build_mock_client(student_rec, new_complaint_data={
            "complaint_id": 701,
            "title": "Hostel fan issue",
            "description": "Ceiling fan making loud noise in room 101.",
            "department_id": DEPT_ID,
            "category_id": HOSTEL_CAT_ID,
            "status": "Pending"
        })

        # Provide candidate search return data as empty list
        mock_cand_table = MagicMock()
        mock_cand_table.select.return_value = mock_cand_table
        mock_cand_table.eq.return_value = mock_cand_table
        mock_cand_table.neq.return_value = mock_cand_table
        mock_cand_table.execute.return_value.data = []

        # Make students query return student_rec, candidates query return []
        def table_dispatcher(table_name):
            if table_name == "students":
                t = MagicMock()
                t.select.return_value = t
                t.eq.return_value = t
                t.execute.return_value.data = [student_rec]
                return t
            elif table_name == "complaints":
                return mock_cand_table
            return MagicMock()

        mock_client.table.side_effect = table_dispatcher

        with patch("services.complaint_service.get_trusted_backend_client", return_value=mock_client):
            ok, msg, comp = ComplaintService.submit_complaint(
                student_id="student-approved-1",
                title="Hostel fan issue",
                description="Ceiling fan making loud noise in room 101.",
                department_id=DEPT_ID,
                category_id=HOSTEL_CAT_ID,
                subcategory_id=None,
                location_id="loc-1",
                is_hostel=True
            )
            assert ok is True
            assert "submitted successfully" in msg
            assert comp is not None
            assert comp["complaint_id"] == 701

    # (c) Normal non-hostel category works for both approved and unapproved students
    def test_non_hostel_category_works_for_unapproved_student(self):
        """Day scholar / unapproved student can submit academic or classroom complaints."""
        student_rec = {
            "id": "student-unapproved-4",
            "department_id": DEPT_ID,
            "is_hostel": False,
            "is_hostel_approved": False,
            "is_locked": False
        }
        mock_client = _build_mock_client(student_rec, new_complaint_data={
            "complaint_id": 702,
            "title": "Projector not working in classroom 302",
            "description": "The HDMI cable is torn and projector fails to connect.",
            "department_id": DEPT_ID,
            "category_id": ACADEMIC_CAT_ID,
            "status": "Pending"
        })

        mock_cand_table = MagicMock()
        mock_cand_table.select.return_value = mock_cand_table
        mock_cand_table.eq.return_value = mock_cand_table
        mock_cand_table.neq.return_value = mock_cand_table
        mock_cand_table.execute.return_value.data = []

        def table_dispatcher(table_name):
            if table_name == "students":
                t = MagicMock()
                t.select.return_value = t
                t.eq.return_value = t
                t.execute.return_value.data = [student_rec]
                return t
            elif table_name == "complaints":
                return mock_cand_table
            return MagicMock()

        mock_client.table.side_effect = table_dispatcher

        with patch("services.complaint_service.get_trusted_backend_client", return_value=mock_client):
            ok, msg, comp = ComplaintService.submit_complaint(
                student_id="student-unapproved-4",
                title="Projector not working in classroom 302",
                description="The HDMI cable is torn and projector fails to connect.",
                department_id=DEPT_ID,
                category_id=ACADEMIC_CAT_ID,
                subcategory_id=None,
                location_id="loc-1",
                is_hostel=False
            )
            assert ok is True
            assert "submitted successfully" in msg
            assert comp is not None
            assert comp["complaint_id"] == 702

    def test_non_hostel_category_works_for_approved_student(self):
        """Approved hostel student can also submit standard academic/classroom complaints."""
        student_rec = {
            "id": "student-approved-2",
            "department_id": DEPT_ID,
            "is_hostel": True,
            "is_hostel_approved": True,
            "is_locked": False
        }
        mock_client = _build_mock_client(student_rec, new_complaint_data={
            "complaint_id": 703,
            "title": "Lab PC keyboard malfunctioning",
            "description": "Several keys on PC 12 in Lab 1 are stuck and unresponsive.",
            "department_id": DEPT_ID,
            "category_id": ACADEMIC_CAT_ID,
            "status": "Pending"
        })

        mock_cand_table = MagicMock()
        mock_cand_table.select.return_value = mock_cand_table
        mock_cand_table.eq.return_value = mock_cand_table
        mock_cand_table.neq.return_value = mock_cand_table
        mock_cand_table.execute.return_value.data = []

        def table_dispatcher(table_name):
            if table_name == "students":
                t = MagicMock()
                t.select.return_value = t
                t.eq.return_value = t
                t.execute.return_value.data = [student_rec]
                return t
            elif table_name == "complaints":
                return mock_cand_table
            return MagicMock()

        mock_client.table.side_effect = table_dispatcher

        with patch("services.complaint_service.get_trusted_backend_client", return_value=mock_client):
            ok, msg, comp = ComplaintService.submit_complaint(
                student_id="student-approved-2",
                title="Lab PC keyboard malfunctioning",
                description="Several keys on PC 12 in Lab 1 are stuck and unresponsive.",
                department_id=DEPT_ID,
                category_id=ACADEMIC_CAT_ID,
                subcategory_id=None,
                location_id="loc-1",
                is_hostel=False
            )
            assert ok is True
            assert "submitted successfully" in msg
            assert comp is not None
            assert comp["complaint_id"] == 703
