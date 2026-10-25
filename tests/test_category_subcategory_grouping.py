"""
tests/test_category_subcategory_grouping.py: Unit tests verifying deterministic
Category + Subcategory issue grouping and scope isolation.
"""

import pytest
from unittest.mock import MagicMock, patch
from services.duplicate_service import DuplicateService
from services.complaint_service import ComplaintService
from services.issue_group_service import IssueGroupService


# =============================================================================
# 1. DETERMINISTIC MATCHING TESTS VIA DuplicateService
# =============================================================================

def test_same_department_category_subcategory_matches():
    target = {
        "complaint_id": 201,
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": "sub-fan",
        "is_hostel": False,
        "category_custom": None,
        "subcategory_custom": None,
    }
    candidate = {
        "complaint_id": 101,
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": "sub-fan",
        "is_hostel": False,
        "category_custom": None,
        "subcategory_custom": None,
        "is_deleted": False,
    }
    matches = DuplicateService.find_category_subcategory_matches(target, [candidate])
    assert len(matches) == 1
    assert matches[0]["complaint_id"] == 101


def test_hostel_scope_groups_across_different_academic_departments():
    """Hostel complaints group within hostel scope regardless of academic departments."""
    target = {
        "complaint_id": 202,
        "department_id": "dept-cse",  # Student enrolled in CSE
        "category_id": "cat-hostel",
        "subcategory_id": "sub-water",
        "is_hostel": True,
        "category_custom": None,
        "subcategory_custom": None,
    }
    candidate = {
        "complaint_id": 102,
        "department_id": "dept-mech",  # Student enrolled in MECH
        "category_id": "cat-hostel",
        "subcategory_id": "sub-water",
        "is_hostel": True,
        "category_custom": None,
        "subcategory_custom": None,
        "is_deleted": False,
    }
    matches = DuplicateService.find_category_subcategory_matches(target, [candidate])
    assert len(matches) == 1
    assert matches[0]["complaint_id"] == 102


def test_different_departments_do_not_group_for_academic_complaints():
    """Non-hostel complaints from different departments must NOT group."""
    target = {
        "complaint_id": 203,
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": "sub-fan",
        "is_hostel": False,
        "category_custom": None,
        "subcategory_custom": None,
    }
    candidate = {
        "complaint_id": 103,
        "department_id": "dept-aids",
        "category_id": "cat-elec",
        "subcategory_id": "sub-fan",
        "is_hostel": False,
        "category_custom": None,
        "subcategory_custom": None,
        "is_deleted": False,
    }
    matches = DuplicateService.find_category_subcategory_matches(target, [candidate])
    assert len(matches) == 0


def test_different_subcategory_does_not_group():
    """Same department and category but different subcategory must NOT group."""
    target = {
        "complaint_id": 204,
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": "sub-light",
        "is_hostel": False,
        "category_custom": None,
        "subcategory_custom": None,
    }
    candidate = {
        "complaint_id": 104,
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": "sub-fan",
        "is_hostel": False,
        "category_custom": None,
        "subcategory_custom": None,
        "is_deleted": False,
    }
    matches = DuplicateService.find_category_subcategory_matches(target, [candidate])
    assert len(matches) == 0


def test_custom_category_or_subcategory_never_grouped():
    """Custom categories or subcategories must stay ungrouped."""
    # Target has custom category
    target_custom_cat = {
        "complaint_id": 205,
        "department_id": "dept-cse",
        "category_id": "cat-other",
        "subcategory_id": "sub-other",
        "category_custom": "Custom Lab Issue",
        "subcategory_custom": None,
        "is_hostel": False,
    }
    candidate = {
        "complaint_id": 105,
        "department_id": "dept-cse",
        "category_id": "cat-other",
        "subcategory_id": "sub-other",
        "category_custom": None,
        "subcategory_custom": None,
        "is_deleted": False,
    }
    assert len(DuplicateService.find_category_subcategory_matches(target_custom_cat, [candidate])) == 0

    # Target has custom subcategory
    target_custom_sub = {
        "complaint_id": 206,
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": "sub-other",
        "category_custom": None,
        "subcategory_custom": "Custom Switch Problem",
        "is_hostel": False,
    }
    assert len(DuplicateService.find_category_subcategory_matches(target_custom_sub, [candidate])) == 0


def test_missing_category_or_subcategory_never_grouped():
    """Complaints with None or missing category/subcategory stay ungrouped."""
    target_no_sub = {
        "complaint_id": 207,
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": None,
        "is_hostel": False,
    }
    candidate = {
        "complaint_id": 107,
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": None,
        "is_deleted": False,
    }
    assert len(DuplicateService.find_category_subcategory_matches(target_no_sub, [candidate])) == 0


# =============================================================================
# 2. SUBMIT_COMPLAINT INTEGRATION WITH DETERMINISTIC GROUPING
# =============================================================================

def test_submit_complaint_creates_issue_group_for_matching_candidate():
    """Submitting a complaint that matches an existing complaint creates/links Issue Group."""
    client_mock = MagicMock()

    # Student query returns valid enrolled student
    student_table = MagicMock()
    student_table.select.return_value = student_table
    student_table.eq.return_value = student_table
    student_table.execute.return_value.data = [{
        "id": "student-1",
        "department_id": "dept-cse",
        "is_hostel": False,
        "is_hostel_approved": False,
        "is_locked": False
    }]

    # Atomic RPC returns new complaint #302
    rpc_mock = MagicMock()
    rpc_mock.execute.return_value.data = {
        "complaint_id": 302,
        "title": "Fan not working in 202",
        "description": "Classroom ceiling fan speed regulator is broken and fan does not rotate.",
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": "sub-fan",
        "location_id": "loc-1",
        "is_hostel": False,
        "priority": "Low",
        "category_custom": None,
        "subcategory_custom": None
    }
    client_mock.rpc.return_value = rpc_mock

    # Candidate query returns existing complaint #301 with same dept, cat, subcat
    existing_c301 = {
        "complaint_id": 301,
        "title": "Broken fan in room 202",
        "description": "Fan in room 202 is completely stopped.",
        "department_id": "dept-cse",
        "category_id": "cat-elec",
        "subcategory_id": "sub-fan",
        "location_id": "loc-1",
        "is_hostel": False,
        "is_deleted": False,
        "issue_group_id": None,
        "priority": "Low",
        "category_custom": None,
        "subcategory_custom": None
    }

    complaints_table = MagicMock()
    complaints_table.select.return_value = complaints_table
    complaints_table.eq.return_value = complaints_table
    complaints_table.neq.return_value = complaints_table
    complaints_table.update.return_value = complaints_table
    complaints_table.execute.return_value.data = [existing_c301]

    def table_dispatcher(name):
        if name == "students":
            return student_table
        elif name == "complaints":
            return complaints_table
        return MagicMock()

    client_mock.table.side_effect = table_dispatcher

    with patch("services.complaint_service.get_trusted_backend_client", return_value=client_mock), \
         patch("services.complaint_service.IssueGroupService.create_or_link_issue_group", return_value=(True, "Linked", "grp-uuid-1")) as mock_link:

        ok, msg, comp = ComplaintService.submit_complaint(
            student_id="student-1",
            title="Fan not working in 202",
            description="Classroom ceiling fan speed regulator is broken and fan does not rotate.",
            department_id="dept-cse",
            category_id="cat-elec",
            subcategory_id="sub-fan",
            location_id="loc-1"
        )
        assert ok is True
        mock_link.assert_called_once_with(
            primary_complaint_id=301,
            duplicate_complaint_id=302,
            actor_role="System"
        )


# =============================================================================
# 3. GROUP MEMBER DATA INCLUDES DESCRIPTION AND CREATED_AT
# =============================================================================

def test_issue_group_service_includes_description_and_created_at():
    """Verify IssueGroupService.get_department_groups returns description, created_at, and masks anonymous."""
    client_mock = MagicMock()

    # Return one group
    group_table = MagicMock()
    group_table.select.return_value = group_table
    group_table.eq.return_value = group_table
    group_table.order.return_value = group_table
    group_table.execute.return_value.data = [{
        "id": "grp-1",
        "title": "Grouped Issue: Classroom Projector Issue",
        "department_id": "dept-cse",
        "is_hostel": False,
        "group_status": "Pending",
        "primary_complaint_id": 501,
        "duplicate_count": 1
    }]

    # Return member data with description and created_at
    members_table = MagicMock()
    members_table.select.return_value = members_table
    members_table.in_.return_value = members_table
    members_table.execute.return_value.data = [
        {
            "id": "m-1",
            "issue_group_id": "grp-1",
            "complaint_id": 501,
            "complaints": {
                "complaint_id": 501,
                "title": "Projector HDMI cable broken",
                "description": "HDMI cable torn at connector pin.",
                "status": "Pending",
                "priority": "Medium",
                "is_anonymous": False,
                "created_at": "2026-10-25T10:00:00Z",
                "categories": {"name": "Academic"}
            }
        },
        {
            "id": "m-2",
            "issue_group_id": "grp-1",
            "complaint_id": 502,
            "complaints": {
                "complaint_id": 502,
                "title": "Cannot connect to projector",
                "description": "Display is blinking blue repeatedly.",
                "status": "Pending",
                "priority": "Low",
                "is_anonymous": True,
                "created_at": "2026-10-25T11:00:00Z",
                "categories": {"name": "Academic"}
            }
        }
    ]

    def table_router(name):
        if name == "issue_groups":
            return group_table
        if name == "issue_group_members":
            return members_table
        return MagicMock()

    client_mock.table.side_effect = table_router

    with patch("services.issue_group_service.get_trusted_backend_client", return_value=client_mock), \
         patch("services.cache_service.CacheService.get_cached_issue_groups", return_value=None), \
         patch("services.cache_service.CacheService.set_cached_issue_groups"):

        groups = IssueGroupService.get_department_groups(department_id="dept-cse", role="HOD")
        assert len(groups) == 1
        g = groups[0]
        members = g.get("members", [])
        assert len(members) == 2

        # Verify member 1
        m1 = members[0]
        assert m1["complaint_id"] == 501
        assert m1["description"] == "HDMI cable torn at connector pin."
        assert m1["created_at"] == "2026-10-25T10:00:00Z"

        # Verify member 2 (anonymous)
        m2 = members[1]
        assert m2["complaint_id"] == 502
        assert m2["description"] == "Display is blinking blue repeatedly."
        assert m2["created_at"] == "2026-10-25T11:00:00Z"
        assert m2["student_info"] == "Anonymous Student"
        assert m2.get("student_id") is None


def test_staff_complaints_list_excludes_grouped_complaints():
    client_mock = MagicMock()
    complaints_table = MagicMock()
    client_mock.table.return_value = complaints_table

    for method in ("select", "eq", "or_", "in_", "order"):
        getattr(complaints_table, method).return_value = complaints_table

    sample_complaints = [
        {
            "complaint_id": 601,
            "title": "Ungrouped issue",
            "department_id": "dept-cse",
            "issue_group_id": None,
            "is_hostel": False,
            "is_deleted": False,
            "categories": {"name": "Lab"},
            "students": {"year": "SE"},
            "departments": {"code": "CSE"}
        },
        {
            "complaint_id": 602,
            "title": "Grouped issue 1",
            "department_id": "dept-cse",
            "issue_group_id": "grp-abc-123",
            "is_hostel": False,
            "is_deleted": False,
            "categories": {"name": "Lab"},
            "students": {"year": "SE"},
            "departments": {"code": "CSE"}
        }
    ]

    complaints_table.execute.return_value = MagicMock(data=sample_complaints)

    with patch("services.complaint_service._get_client", return_value=client_mock):
        results = ComplaintService.get_complaints_for_user(
            role="HOD",
            user_id="staff-1",
            department_id="dept-cse",
            exclude_grouped=True
        )
        assert len(results) == 1
        assert results[0]["complaint_id"] == 601
        assert results[0]["issue_group_id"] is None


def test_student_complaints_list_includes_grouped_complaints():
    client_mock = MagicMock()
    complaints_table = MagicMock()
    anon_table = MagicMock()

    def router(name):
        if name == "anonymous_complaint_owners":
            return anon_table
        return complaints_table

    client_mock.table.side_effect = router

    for method in ("select", "eq", "or_", "in_", "order"):
        getattr(complaints_table, method).return_value = complaints_table
        getattr(anon_table, method).return_value = anon_table

    anon_table.execute.return_value = MagicMock(data=[])

    sample_complaints = [
        {
            "complaint_id": 701,
            "title": "Student issue in group",
            "issue_group_id": "grp-xyz-789",
            "student_id": "student-1",
            "is_deleted": False
        }
    ]
    complaints_table.execute.return_value = MagicMock(data=sample_complaints)

    with patch("services.complaint_service._get_client", return_value=client_mock):
        results = ComplaintService.get_complaints_for_user(
            role="Student",
            user_id="student-1",
            exclude_grouped=True
        )
        assert len(results) == 1
        assert results[0]["complaint_id"] == 701
        assert results[0]["issue_group_id"] == "grp-xyz-789"


def test_default_get_complaints_for_user_unchanged():
    client_mock = MagicMock()
    complaints_table = MagicMock()
    client_mock.table.return_value = complaints_table

    for method in ("select", "eq", "or_", "in_", "order"):
        getattr(complaints_table, method).return_value = complaints_table

    sample_complaints = [
        {
            "complaint_id": 801,
            "title": "Ungrouped",
            "department_id": "dept-cse",
            "issue_group_id": None,
            "is_hostel": False,
            "is_deleted": False,
            "categories": {"name": "Academic"},
            "students": {"year": "TE"},
            "departments": {"code": "CSE"}
        },
        {
            "complaint_id": 802,
            "title": "Grouped",
            "department_id": "dept-cse",
            "issue_group_id": "grp-default-999",
            "is_hostel": False,
            "is_deleted": False,
            "categories": {"name": "Academic"},
            "students": {"year": "TE"},
            "departments": {"code": "CSE"}
        }
    ]
    complaints_table.execute.return_value = MagicMock(data=sample_complaints)

    with patch("services.complaint_service._get_client", return_value=client_mock):
        results = ComplaintService.get_complaints_for_user(
            role="HOD",
            user_id="staff-1",
            department_id="dept-cse"
        )
        assert len(results) == 2
        cids = [r["complaint_id"] for r in results]
        assert 801 in cids
        assert 802 in cids


def test_get_complaint_by_id_masks_anonymous_student():
    client_mock = MagicMock()
    complaints_table = MagicMock()
    client_mock.table.return_value = complaints_table

    for method in ("select", "eq"):
        getattr(complaints_table, method).return_value = complaints_table

    sample = {
        "complaint_id": 901,
        "title": "Anonymous complaint",
        "is_anonymous": True,
        "student_id": "real-student-uuid",
        "students": {"year": "BE", "roll_number": "2024001", "full_name": "Secret Student"}
    }
    complaints_table.execute.return_value = MagicMock(data=[sample])

    with patch("services.complaint_service._get_client", return_value=client_mock):
        item = ComplaintService.get_complaint_by_id(901)
        assert item is not None
        assert item["complaint_id"] == 901
        assert item["student_id"] is None
        assert item["student_info"] == "Anonymous Student"
        assert item["students"] is None
