import pytest
from models.user import UserRole
from services.duplicate_service import DuplicateService
from services.complaint_service import ComplaintService
from services.account_service import AccountService
from services.security_code_service import SecurityCodeService
from database.supabase_client import get_trusted_backend_client

def test_14_master_categories_seeded():
    client = get_trusted_backend_client()
    res = client.table('categories').select('id, name').execute()
    assert res.data, 'Categories table should not be empty'
    cat_names = {c['name'].strip() for c in res.data}
    assert len(cat_names) >= 14, f'Expected at least 14 categories, found {len(cat_names)}'
    
    expected_categories = {
        'Cleaning & Hygiene', 'Infrastructure', 'Electricity', 'Water & Sanitation',
        'IT & Computer', 'Academics', 'Faculty', 'Canteen', 'Hostel', 'Transport',
        'Student Related', 'Security & Safety', 'Other', 'Library'
    }
    for ec in expected_categories:
        assert ec in cat_names, f'Category {ec} must be present in database'

def test_duplicate_detection_3_dimensions_and_scope():
    c1 = {
        'title': 'Projector broken in Lab 301',
        'description': 'The ceiling projector is flickering and shuts off after 5 minutes in Lab 301.',
        'category_id': 'cat-infra-1',
        'subcategory_id': 'sub-proj-1',
        'priority': 'High',
        'location_id': 'loc-301',
        'department_id': 'dept-cse-1',
        'is_hostel': False
    }
    
    # Same 3 dimensions + scope -> High similarity >= 0.65
    c2 = {
        'title': 'Lab 301 Projector broken and flickering',
        'description': 'The ceiling projector is flickering and shuts off after 5 minutes in Lab 301.',
        'category_id': 'cat-infra-1',
        'subcategory_id': 'sub-proj-1',
        'priority': 'High',
        'location_id': 'loc-301',
        'department_id': 'dept-cse-1',
        'is_hostel': False
    }
    score = DuplicateService.compute_similarity(c1, c2)
    assert score >= 0.65, f'Expected high similarity >= 0.65, got {score}'
    
    # Mismatch in Priority -> 0.0
    c3 = dict(c2, priority='Low')
    assert DuplicateService.compute_similarity(c1, c3) == 0.0

    # Mismatch in Subcategory -> 0.0
    c4 = dict(c2, subcategory_id='sub-fan-2')
    assert DuplicateService.compute_similarity(c1, c4) == 0.0

    # Mismatch in Category -> 0.0
    c5 = dict(c2, category_id='cat-sports-2')
    assert DuplicateService.compute_similarity(c1, c5) == 0.0

    # Mismatch in Scope (Hostel vs Academic Dept) -> 0.0
    c6 = dict(c2, is_hostel=True)
    assert DuplicateService.compute_similarity(c1, c6) == 0.0

def test_complaint_routing_matrix_authorization():
    cse_dept_id = 'dept-cse-uuid'
    mech_dept_id = 'dept-mech-uuid'

    # 1. First Year academic complaint
    c_fe = {
        'id': 101,
        'department_id': cse_dept_id,
        'departments': {'code': 'CSE', 'name': 'Computer'},
        'categories': {'name': 'Academic'},
        'students': {'year': 'FE', 'roll_number': 'FE01'},
        'is_hostel': False
    }
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.GENERAL_HOD.value, None, c_fe) is True
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.PRINCIPAL.value, None, c_fe) is True
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.HOD.value, cse_dept_id, c_fe) is False
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.COORDINATOR.value, cse_dept_id, c_fe) is False
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.LIBRARY_INCHARGE.value, None, c_fe) is False
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.HOSTEL_INCHARGE.value, None, c_fe) is False

    # 2. Second Year CSE academic complaint
    c_se = {
        'id': 102,
        'department_id': cse_dept_id,
        'departments': {'code': 'CSE', 'name': 'Computer'},
        'categories': {'name': 'Academic'},
        'students': {'year': 'SE', 'roll_number': 'SE01'},
        'is_hostel': False
    }
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.HOD.value, cse_dept_id, c_se) is True
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.COORDINATOR.value, cse_dept_id, c_se) is True
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.PRINCIPAL.value, None, c_se) is True
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.GENERAL_HOD.value, None, c_se) is False
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.HOD.value, mech_dept_id, c_se) is False

    # 3. Library complaint (Any year)
    c_lib = {
        'id': 103,
        'department_id': cse_dept_id,
        'departments': {'code': 'CSE', 'name': 'Computer'},
        'categories': {'name': 'Library'},
        'students': {'year': 'TE', 'roll_number': 'TE01'},
        'is_hostel': False
    }
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.LIBRARY_INCHARGE.value, None, c_lib) is True
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.PRINCIPAL.value, None, c_lib) is True
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.HOD.value, cse_dept_id, c_lib) is False
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.COORDINATOR.value, cse_dept_id, c_lib) is False

    # 4. Hostel complaint (Any year)
    c_hostel = {
        'id': 104,
        'department_id': cse_dept_id,
        'departments': {'code': 'CSE', 'name': 'Computer'},
        'categories': {'name': 'Hostel'},
        'students': {'year': 'BE', 'roll_number': 'BE01'},
        'is_hostel': True
    }
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.HOSTEL_INCHARGE.value, None, c_hostel) is True
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.PRINCIPAL.value, None, c_hostel) is True
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.HOD.value, cse_dept_id, c_hostel) is False
    assert ComplaintService._is_staff_authorized_for_complaint(UserRole.COORDINATOR.value, cse_dept_id, c_hostel) is False

def test_auto_priority_escalation_rules():
    # 1 duplicate: Student's original priority
    assert DuplicateService.calculate_auto_priority(1, 'Low') == 'Low'
    assert DuplicateService.calculate_auto_priority(1, 'High') == 'High'

    # 2-3 duplicates: Minimum Medium
    assert DuplicateService.calculate_auto_priority(2, 'Low') == 'Medium'
    assert DuplicateService.calculate_auto_priority(3, 'Low') == 'Medium'
    assert DuplicateService.calculate_auto_priority(2, 'High') == 'High'

    # 4-5 duplicates: Minimum High
    assert DuplicateService.calculate_auto_priority(4, 'Low') == 'High'
    assert DuplicateService.calculate_auto_priority(5, 'Medium') == 'High'
    assert DuplicateService.calculate_auto_priority(4, 'Urgent') == 'Urgent'

    # 6+ duplicates: Minimum Urgent
    assert DuplicateService.calculate_auto_priority(6, 'Low') == 'Urgent'
    assert DuplicateService.calculate_auto_priority(10, 'Medium') == 'Urgent'

    # Staff manual priority cannot downgrade below auto minimum
    assert DuplicateService.is_manual_priority_allowed('Low', 'High') is False
    assert DuplicateService.is_manual_priority_allowed('Medium', 'High') is False
    assert DuplicateService.is_manual_priority_allowed('High', 'High') is True
    assert DuplicateService.is_manual_priority_allowed('Urgent', 'High') is True

def test_coordinator_student_password_reset_boundaries():
    coord_res = AccountService.reset_student_password_by_coordinator(
        coordinator_id='00000000-0000-0000-0000-000000000000',
        student_id='00000000-0000-0000-0000-000000000001',
        new_password='Valid@Password123'
    )
    assert coord_res[0] is False
    assert 'Unauthorized' in coord_res[1]

def test_principal_can_fetch_library_and_general_hod():
    # Verify methods don\'t crash and return dictionary or None
    lib = AccountService.get_library_incharge_for_principal('non-existent-principal')
    assert lib is None or isinstance(lib, dict)

    gen = AccountService.get_general_hod_for_principal('non-existent-principal')
    assert gen is None or isinstance(gen, dict)
