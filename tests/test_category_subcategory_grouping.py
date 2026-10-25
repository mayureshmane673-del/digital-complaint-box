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


def test_end_to_end_rls_simulation_group_creation_without_mocking_issue_group_service():
    """
    Verifies that submit_complaint successfully creates an issue group end-to-end
    WITHOUT mocking IssueGroupService, where anon client returns no rows (simulating RLS)
    and trusted backend client returns realistic database rows.
    """
    tables = {
        "complaints": [
            {
                "complaint_id": 111,
                "id": "7bda3b07-b959-4a5f-8187-f5114d4b8c23",
                "student_id": "6bf8ea7f-a490-4259-a5c1-e613956fe441",
                "is_anonymous": False,
                "department_id": "f4e141ef-14ca-44e4-a1ed-051ee0525419",
                "is_hostel": False,
                "title": "cleaning",
                "description": "class room is not clean",
                "category_id": "7f4e88c7-b75c-4919-995e-f345abbe8f89",
                "subcategory_id": "9ce3180c-54d8-42c8-aa7a-6af2823f9619",
                "location_id": "599be477-8601-481d-bd2a-510fbdfadec9",
                "location_custom": None,
                "category_custom": None,
                "subcategory_custom": None,
                "priority": "Medium",
                "initial_priority": "Medium",
                "auto_priority": "Medium",
                "status": "Pending",
                "is_deleted": False,
                "issue_group_id": None
            }
        ],
        "students": [
            {
                "id": "student-real-uuid-2",
                "department_id": "f4e141ef-14ca-44e4-a1ed-051ee0525419",
                "is_hostel": False,
                "is_hostel_approved": False,
                "is_locked": False
            }
        ],
        "issue_groups": [],
        "issue_group_members": [],
        "issue_group_history": []
    }

    # Anon client (simulates live Supabase anon key blocked by RLS)
    anon_client = MagicMock()
    anon_table = MagicMock()
    anon_table.select.return_value = anon_table
    anon_table.eq.return_value = anon_table
    anon_table.execute.return_value = MagicMock(data=[])  # RLS blocks anon -> 0 rows
    anon_client.table.return_value = anon_table

    # Trusted client (simulates service role client)
    trusted_client = MagicMock()

    class MockQueryBuilder:
        def __init__(self, table_name):
            self.table_name = table_name
            self._filters = {}
            self._neqs = {}

        def select(self, *args, **kwargs):
            return self

        def eq(self, k, v):
            self._filters[k] = v
            return self

        def neq(self, k, v):
            self._neqs[k] = v
            return self

        def in_(self, k, v):
            self._filters[k] = v
            return self

        def order(self, *args, **kwargs):
            return self

        def insert(self, payload):
            if isinstance(payload, list):
                for p in payload:
                    if "id" not in p:
                        p["id"] = f"mock-uuid-{len(tables[self.table_name]) + 1}"
                    tables[self.table_name].append(p)
                self._insert_data = payload
            else:
                p = dict(payload)
                if "id" not in p:
                    p["id"] = f"mock-uuid-{len(tables[self.table_name]) + 1}"
                tables[self.table_name].append(p)
                self._insert_data = [p]
            return self

        def update(self, updates):
            # Apply update to matching items
            for item in tables[self.table_name]:
                matches = True
                for k, v in self._filters.items():
                    if item.get(k) != v:
                        matches = False
                        break
                if matches:
                    item.update(updates)
            self._update_data = [updates]
            return self

        def execute(self):
            if hasattr(self, "_insert_data"):
                return MagicMock(data=self._insert_data)
            if hasattr(self, "_update_data"):
                return MagicMock(data=self._update_data)
            rows = tables.get(self.table_name, [])
            res = []
            for r in rows:
                match = True
                for k, v in self._filters.items():
                    if r.get(k) != v:
                        match = False
                        break
                for k, v in self._neqs.items():
                    if r.get(k) == v:
                        match = False
                        break
                if match:
                    res.append(r)
            return MagicMock(data=res)

    def trusted_table_dispatcher(name):
        return MockQueryBuilder(name)

    trusted_client.table.side_effect = trusted_table_dispatcher
    rpc_mock = MagicMock()
    # Atomic RPC returns new complaint 112
    rpc_mock.execute.return_value = MagicMock(data={
        "complaint_id": 112,
        "title": "cleaning",
        "description": "class room is not clean",
        "department_id": "f4e141ef-14ca-44e4-a1ed-051ee0525419",
        "category_id": "7f4e88c7-b75c-4919-995e-f345abbe8f89",
        "subcategory_id": "9ce3180c-54d8-42c8-aa7a-6af2823f9619",
        "location_id": "599be477-8601-481d-bd2a-510fbdfadec9",
        "is_hostel": False,
        "priority": "Medium",
        "is_deleted": False,
        "category_custom": None,
        "subcategory_custom": None
    })
    trusted_client.rpc.return_value = rpc_mock

    with patch("services.complaint_service.get_trusted_backend_client", return_value=trusted_client), \
         patch("services.complaint_service._get_client", return_value=trusted_client), \
         patch("services.issue_group_service._get_client", return_value=trusted_client), \
         patch("services.issue_group_service.get_supabase_client", return_value=anon_client), \
         patch("services.cache_service.CacheService.invalidate_metrics"), \
         patch("services.cache_service.CacheService.invalidate_issue_groups"):

        ok, msg, comp = ComplaintService.submit_complaint(
            student_id="student-real-uuid-2",
            title="cleaning",
            description="class room is not clean",
            department_id="f4e141ef-14ca-44e4-a1ed-051ee0525419",
            category_id="7f4e88c7-b75c-4919-995e-f345abbe8f89",
            subcategory_id="9ce3180c-54d8-42c8-aa7a-6af2823f9619",
            location_id="599be477-8601-481d-bd2a-510fbdfadec9",
            priority="Medium"
        )

        assert ok is True
        # Verify that issue group was created in tables["issue_groups"]
        assert len(tables["issue_groups"]) == 1
        created_group = tables["issue_groups"][0]
        assert created_group["primary_complaint_id"] == 111
        # Both complaints #111 and #112 must now have issue_group_id pointing to created group
        assert tables["complaints"][0]["issue_group_id"] == created_group["id"]
        assert len(tables["issue_group_members"]) == 2


def test_issue_group_service_role_access_boundaries():
    """
    Verifies that get_department_groups enforces strict role-based access:
    - Principal: returns []
    - Student: returns []
    - Coordinator/HOD without department_id: returns []
    - Coordinator/HOD with department_id: returns only their department
    - Hostel Incharge: returns only hostel groups
    """
    mock_groups = [
        {"id": "grp-cse", "title": "CSE Lab Fan", "department_id": "dept-cse", "is_hostel": False, "group_status": "Pending", "duplicate_count": 1},
        {"id": "grp-mech", "title": "Mech Lathe", "department_id": "dept-mech", "is_hostel": False, "group_status": "Pending", "duplicate_count": 2},
        {"id": "grp-hostel", "title": "Hostel Water", "department_id": "dept-cse", "is_hostel": True, "group_status": "Pending", "duplicate_count": 1},
    ]

    client_mock = MagicMock()

    class FilterMock:
        def __init__(self, data):
            self.data = list(data)

        def select(self, *a, **k):
            return self

        def eq(self, k, v):
            self.data = [d for d in self.data if d.get(k) == v]
            return self

        def in_(self, k, v):
            self.data = [d for d in self.data if d.get(k) in v]
            return self

        def order(self, *a, **k):
            return self

        def execute(self):
            return MagicMock(data=self.data)

    def table_mock(name):
        if name == "issue_groups":
            return FilterMock(mock_groups)
        elif name == "issue_group_members":
            return FilterMock([])
        return MagicMock()

    client_mock.table.side_effect = table_mock

    with patch("services.issue_group_service._get_client", return_value=client_mock), \
         patch("services.cache_service.CacheService.get_cached_issue_groups", return_value=None), \
         patch("services.cache_service.CacheService.set_cached_issue_groups"):

        # 1. Principal gets empty list
        assert IssueGroupService.get_department_groups(role="Principal") == []
        assert IssueGroupService.get_department_groups(department_id="dept-cse", role="Principal") == []

        # 2. Student gets empty list
        assert IssueGroupService.get_department_groups(role="Student") == []

        # 3. Coordinator / HOD without department_id gets empty list
        assert IssueGroupService.get_department_groups(role="Coordinator", department_id=None) == []
        assert IssueGroupService.get_department_groups(role="HOD", department_id=None) == []

        # 4. Coordinator with CSE gets only CSE non-hostel
        cse_res = IssueGroupService.get_department_groups(role="Coordinator", department_id="dept-cse")
        assert len(cse_res) == 1
        assert cse_res[0]["id"] == "grp-cse"

        # 5. Hostel Incharge gets only hostel groups
        hostel_res = IssueGroupService.get_department_groups(role="Hostel Incharge")
        assert len(hostel_res) == 1
        assert hostel_res[0]["id"] == "grp-hostel"


def test_student_identity_and_roll_number_visibility_rules():
    """
    Verifies that:
    - Anonymous complaints strictly return 'Anonymous Student' with None for student_id and roll_number.
    - Non-anonymous complaints return full_name.
    - Roll number is visible to Coordinator, HOD, and Hostel Incharge, but hidden (None) for Library Incharge.
    """
    mock_groups = [
        {"id": "grp-1", "title": "Group 1", "department_id": "dept-cse", "is_hostel": False, "group_status": "Pending", "duplicate_count": 2}
    ]
    mock_members = [
        {
            "id": "m-1",
            "issue_group_id": "grp-1",
            "complaint_id": 101,
            "complaints": {
                "complaint_id": 101,
                "title": "Anon complaint",
                "description": "Desc anon",
                "status": "Pending",
                "priority": "Low",
                "is_anonymous": True,
                "created_at": "2026-10-25T10:00:00Z",
                "student_id": "secret-id",
                "students": {"full_name": "Real Name", "roll_number": "240101001"},
                "categories": {"name": "Cleaning"}
            }
        },
        {
            "id": "m-2",
            "issue_group_id": "grp-1",
            "complaint_id": 102,
            "complaints": {
                "complaint_id": 102,
                "title": "Named complaint",
                "description": "Desc named",
                "status": "Pending",
                "priority": "Low",
                "is_anonymous": False,
                "created_at": "2026-10-25T11:00:00Z",
                "student_id": "student-uuid-2",
                "students": {"full_name": "Alice Smith", "roll_number": "240101002"},
                "categories": {"name": "Cleaning"}
            }
        }
    ]

    client_mock = MagicMock()

    class MemberFilterMock:
        def __init__(self, data):
            self.data = list(data)

        def select(self, *a, **k):
            return self

        def in_(self, k, v):
            return self

        def eq(self, k, v):
            return self

        def order(self, *a, **k):
            return self

        def execute(self):
            return MagicMock(data=self.data)

    def table_mock(name):
        if name == "issue_groups":
            return MemberFilterMock(mock_groups)
        elif name == "issue_group_members":
            return MemberFilterMock(mock_members)
        return MagicMock()

    client_mock.table.side_effect = table_mock

    with patch("services.issue_group_service._get_client", return_value=client_mock), \
         patch("services.cache_service.CacheService.get_cached_issue_groups", return_value=None), \
         patch("services.cache_service.CacheService.set_cached_issue_groups"):

        # Coordinator sees roll number for non-anonymous, but masked for anonymous
        coord_res = IssueGroupService.get_department_groups(department_id="dept-cse", role="Coordinator")
        assert len(coord_res) == 1
        members = coord_res[0]["members"]
        m_anon = next(m for m in members if m["complaint_id"] == 101)
        m_named = next(m for m in members if m["complaint_id"] == 102)

        # Anonymous checks
        assert m_anon["student_info"] == "Anonymous Student"
        assert m_anon["student_name"] == "Anonymous Student"
        assert m_anon["roll_number"] is None
        assert m_anon["student_id"] is None

        # Named checks for Coordinator (shows full_name and roll_number)
        assert m_named["student_name"] == "Alice Smith"
        assert m_named["roll_number"] == "240101002"
        assert m_named["student_info"] == "Alice Smith (240101002)"

        # Library Incharge checks (shows full_name, but roll_number is None)
        lib_groups = [
            {"id": "grp-lib", "title": "Group Lib", "department_id": "dept-cse", "is_hostel": False, "group_status": "Pending", "duplicate_count": 1}
        ]
        lib_members = [
            {
                "id": "m-lib",
                "issue_group_id": "grp-lib",
                "complaint_id": 103,
                "complaints": {
                    "complaint_id": 103,
                    "title": "Book missing",
                    "description": "Desc book",
                    "status": "Pending",
                    "priority": "Low",
                    "is_anonymous": False,
                    "created_at": "2026-10-25T12:00:00Z",
                    "student_id": "student-uuid-3",
                    "students": {"full_name": "Bob Jones", "roll_number": "240101003"},
                    "categories": {"name": "Library"}
                }
            }
        ]

        def lib_table_mock(name):
            if name == "issue_groups":
                return MemberFilterMock(lib_groups)
            elif name == "issue_group_members":
                return MemberFilterMock(lib_members)
            return MagicMock()

        client_mock.table.side_effect = lib_table_mock
        lib_res = IssueGroupService.get_department_groups(role="Library Incharge")
        assert len(lib_res) == 1
        lib_m = lib_res[0]["members"][0]
        assert lib_m["student_name"] == "Bob Jones"
        assert lib_m["roll_number"] is None
        assert lib_m["student_info"] == "Bob Jones"

