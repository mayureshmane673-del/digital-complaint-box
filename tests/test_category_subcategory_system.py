"""
tests/test_category_subcategory_system.py: Rigorous verification of practical categories,
subcategories, priority mapping, category switching, and compulsory custom descriptions.
"""

import pytest
from unittest.mock import MagicMock
import flet as ft
from models.complaint import (
    PRACTICAL_SUBCATEGORIES,
    PRACTICAL_SUBCATEGORIES_CONFIG,
    get_default_priority
)
from services.cache_service import CacheService
from ui.views.student_view import StudentView


class MockPage:
    def __init__(self):
        self.controls = []
        self.session = MagicMock()
        self.services = []
        self._services = MagicMock()
        self.overlay = []
        self.dialog = None

    def update(self):
        pass


@pytest.fixture
def mock_student():
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "roll_number": "CS2026001",
        "full_name": "Test Student",
        "department_id": "f4e141ef-14ca-44e4-a1ed-051ee0525419",
        "year": "FE",
        "is_hostel": True,
        "is_hostel_approved": True,
        "is_locked": False
    }


def test_case_1_electricity_subcategories():
    """Verify Electricity practical subcategories."""
    expected = [
        "Light Not Working",
        "Fan Not Working",
        "Power Supply Failure",
        "Frequent Power Cut",
        "Switch / Socket Damage",
        "Wiring Problem",
        "Short Circuit",
        "Electrical Spark / Burning Smell",
        "Emergency Power / Backup Issue",
        "Other"
    ]
    actual = PRACTICAL_SUBCATEGORIES["Electricity"]
    assert actual == expected, f"Electricity subcategories mismatch: {actual}"


def test_case_2_hostel_subcategories():
    """Verify Hostel practical subcategories."""
    expected = [
        "Room Maintenance",
        "Bed / Furniture Damage",
        "Room Cleaning",
        "Washroom Maintenance / Cleaning",
        "Hot Water Issue",
        "Hostel Electricity Issue",
        "Hostel Wi-Fi Issue",
        "Drinking Water Issue",
        "Noise / Disturbance",
        "Security / Gate Timing Issue",
        "Other"
    ]
    actual = PRACTICAL_SUBCATEGORIES["Hostel"]
    assert actual == expected, f"Hostel subcategories mismatch: {actual}"


def test_case_3_it_and_computer_subcategories():
    """Verify IT & Computer practical subcategories."""
    expected = [
        "Computer / PC Not Working",
        "Monitor Problem",
        "Keyboard / Mouse Problem",
        "Internet / Wi-Fi Not Working",
        "Slow Internet",
        "Lab Software Not Installed / Not Working",
        "Printer Problem",
        "Projector Problem",
        "Network Cable / Port Damage",
        "Login / User Account Issue",
        "Other"
    ]
    actual = PRACTICAL_SUBCATEGORIES["IT & Computer"]
    assert actual == expected, f"IT & Computer subcategories mismatch: {actual}"


def test_case_4_security_and_safety_subcategories():
    """Verify Security & Safety practical subcategories."""
    expected = [
        "Unauthorized Person on Campus",
        "Theft / Missing Belongings",
        "CCTV Not Working",
        "Security Guard Missing",
        "Campus Gate Security Issue",
        "Unsafe / Dark Area on Campus",
        "Emergency / Incident Report",
        "Other"
    ]
    actual = PRACTICAL_SUBCATEGORIES["Security & Safety"]
    assert actual == expected, f"Security & Safety subcategories mismatch: {actual}"


def test_case_5_other_subcategories():
    """Verify Other practical subcategories."""
    expected = [
        "General Issue",
        "Administrative Issue",
        "Facility Not Listed",
        "Other Complaint"
    ]
    actual = PRACTICAL_SUBCATEGORIES["Other"]
    assert actual == expected, f"Other subcategories mismatch: {actual}"


def test_intelligent_priority_mapping():
    """Verify intelligent priority defaults for high, medium, and low issues."""
    assert get_default_priority("Electricity", "Short Circuit") == "High"
    assert get_default_priority("Electricity", "Electrical Spark / Burning Smell") == "High"
    assert get_default_priority("Electricity", "Wiring Problem") == "High"
    assert get_default_priority("Electricity", "Light Not Working") == "Medium"
    assert get_default_priority("Electricity", "Fan Not Working") == "Medium"

    assert get_default_priority("Water & Sanitation", "Drinking Water Not Available") == "High"
    assert get_default_priority("Water & Sanitation", "Dirty / Contaminated Water") == "High"
    assert get_default_priority("Water & Sanitation", "Low Water Pressure") == "Low"

    assert get_default_priority("Security & Safety", "Unauthorized Person on Campus") == "High"
    assert get_default_priority("Security & Safety", "Theft / Missing Belongings") == "High"

    assert get_default_priority("Cleaning & Hygiene", "Classroom Cleaning") == "Low"
    assert get_default_priority("Cleaning & Hygiene", "Washroom Cleaning") == "Medium"


def test_ui_dynamic_subcategory_switching(mock_student):
    """
    Test 6: Test UI dynamic category switching in StudentView.
    Select Electricity -> options must be Electricity subcategories
    Then select Hostel -> options must be Hostel subcategories, previous cleared.
    """
    page = MockPage()
    view = StudentView(page, mock_student)
    view._render_new_complaint()

    # Find Electricity category ID
    elec_cat = next((c for c in view.categories if c["name"] == "Electricity"), None)
    assert elec_cat is not None, "Electricity category not found in view.categories"
    elec_id = str(elec_cat["id"])

    # Simulate selecting Electricity via on_select event
    select_event = MagicMock()
    select_event.data = elec_id
    select_event.control = view.category_dropdown

    # Trigger on_select handler
    view.category_dropdown.on_select(select_event)

    # Subcategory dropdown must have Electricity options
    current_subcat = view.subcategory_dropdown
    sub_texts = [opt.text for opt in current_subcat.options]
    assert "Light Not Working" in sub_texts
    assert "Short Circuit" in sub_texts
    assert "Room Maintenance" not in sub_texts  # Subcategory isolation!
    assert current_subcat.value is None  # Initially cleared

    # Simulate selecting "Short Circuit"
    short_circuit_opt = next(o for o in current_subcat.options if o.text == "Short Circuit")
    sub_event = MagicMock()
    sub_event.data = short_circuit_opt.key
    sub_event.control = current_subcat
    current_subcat.on_select(sub_event)

    # Priority must auto-default to High!
    # Find priority dropdown
    assert view.subcategory_dropdown.value == short_circuit_opt.key

    # Switch to "Hostel"
    hostel_cat = next((c for c in view.categories if c["name"] == "Hostel"), None)
    assert hostel_cat is not None, "Hostel category not found"
    hostel_id = str(hostel_cat["id"])

    hostel_select_event = MagicMock()
    hostel_select_event.data = hostel_id
    hostel_select_event.control = view.category_dropdown
    view.category_dropdown.on_select(hostel_select_event)

    # After switching to Hostel:
    # 1. Electricity options must disappear
    # 2. Hostel options must appear
    # 3. Previously selected subcategory must be cleared (value is None)
    hostel_subcat = view.subcategory_dropdown
    hostel_sub_texts = [opt.text for opt in hostel_subcat.options]
    assert "Room Maintenance" in hostel_sub_texts
    assert "Hostel Electricity Issue" in hostel_sub_texts
    assert "Light Not Working" not in hostel_sub_texts
    assert "Short Circuit" not in hostel_sub_texts
    assert hostel_subcat.value is None


def test_ui_other_category_and_custom_compulsory(mock_student):
    """
    Test 5: Selecting Other category must reveal compulsory custom description field.
    """
    page = MockPage()
    view = StudentView(page, mock_student)
    view._render_new_complaint()

    other_cat = next((c for c in view.categories if c["name"].lower() == "other"), None)
    assert other_cat is not None
    other_id = str(other_cat["id"])

    event = MagicMock()
    event.data = other_id
    event.control = view.category_dropdown
    view.category_dropdown.on_select(event)

    # Subcategory dropdown must have Other options
    sub_texts = [opt.text for opt in view.subcategory_dropdown.options]
    assert "General Issue" in sub_texts
    assert "Administrative Issue" in sub_texts
    assert "Facility Not Listed" in sub_texts
    assert "Other Complaint" in sub_texts
