"""
models/complaint.py: Core Complaint, Attachment, History, and Assignment models.
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from pydantic import BaseModel, Field


class ComplaintStatus(str, Enum):
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    REJECTED = "Rejected"


class ComplaintPriority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"


class ComplaintAttachment(BaseModel):
    id: Optional[str] = None
    complaint_id: int
    file_name: str
    file_path: str
    file_size: int
    mime_type: str
    created_at: Optional[datetime] = None


class ComplaintAssignment(BaseModel):
    id: Optional[str] = None
    complaint_id: int
    assigned_to_type: str  # team, person, custom
    assigned_to_name: str
    assigned_by: str
    assigned_by_role: str
    remarks: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


class ComplaintHistory(BaseModel):
    id: Optional[str] = None
    complaint_id: int
    action: str
    actor_type: str  # Student, Staff, System
    actor_role: Optional[str] = None
    actor_id: Optional[str] = None  # Anonymized if anonymous student
    previous_state: Optional[Dict[str, Any]] = None
    new_state: Optional[Dict[str, Any]] = None
    remarks: Optional[str] = None
    created_at: Optional[datetime] = None


class Complaint(BaseModel):
    complaint_id: int
    id: Optional[str] = None
    student_id: Optional[str] = None
    student_year: Optional[str] = None
    anonymous_token_hash: Optional[str] = None
    is_anonymous: bool = False
    department_id: str
    department_code: Optional[str] = None
    department_name: Optional[str] = None
    is_hostel: bool = False
    title: str
    description: str
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    subcategory_id: Optional[str] = None
    subcategory_name: Optional[str] = None
    location_id: Optional[str] = None
    location_name: Optional[str] = None
    location_custom: Optional[str] = None
    category_custom: Optional[str] = None
    subcategory_custom: Optional[str] = None
    priority: ComplaintPriority = ComplaintPriority.LOW
    initial_priority: ComplaintPriority = ComplaintPriority.LOW
    auto_priority: ComplaintPriority = ComplaintPriority.LOW
    status: ComplaintStatus = ComplaintStatus.PENDING
    is_deleted: bool = False
    deleted_by: Optional[str] = None
    deleted_by_role: Optional[str] = None
    delete_reason: Optional[str] = None
    deleted_at: Optional[datetime] = None
    issue_group_id: Optional[str] = None
    has_admin_action: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    # Transient/Display attributes
    attachments: List[ComplaintAttachment] = Field(default_factory=list)
    history: List[ComplaintHistory] = Field(default_factory=list)
    assignment: Optional[ComplaintAssignment] = None
    duplicate_count: int = 0
    feedback_rating: Optional[int] = None
    feedback_comment: Optional[str] = None

    def is_editable_by_student(self) -> bool:
        """
        Student may edit complaint within 10 minutes of submission,
        unless an authorized admin action has already taken place.
        """
        if self.has_admin_action or self.is_deleted or self.status != ComplaintStatus.PENDING:
            return False
        if not self.created_at:
            return True
        diff_seconds = (datetime.now(self.created_at.tzinfo) - self.created_at).total_seconds()
        return diff_seconds <= 600


# =============================================================================
# PRACTICAL CATEGORY & SUBCATEGORY CONFIGURATION WITH INTELLIGENT DEFAULTS
# =============================================================================

PRACTICAL_SUBCATEGORIES_CONFIG: Dict[str, List[Tuple[str, str]]] = {
    "Cleaning & Hygiene": [
        ("Classroom Cleaning", "Low"),
        ("Lab Cleaning", "Low"),
        ("Washroom Cleaning", "Medium"),
        ("Canteen Hygiene", "Medium"),
        ("Campus Cleaning", "Low"),
        ("Garbage / Waste Disposal", "Medium"),
        ("Bad Odour", "Medium"),
        ("Pest / Insect Problem", "Medium"),
        ("Hostel Cleaning", "Medium"),
        ("Other", "Low"),
    ],
    "Infrastructure": [
        ("Building Damage", "High"),
        ("Classroom Damage", "Medium"),
        ("Lab Damage", "Medium"),
        ("Bench / Desk / Chair", "Low"),
        ("Door / Window", "Medium"),
        ("Blackboard / Whiteboard", "Low"),
        ("Roof / Ceiling Leakage", "High"),
        ("Floor / Tile Damage", "Medium"),
        ("Lift / Elevator Problem", "High"),
        ("Other Infrastructure Issue", "Medium"),
        ("Other", "Low"),
    ],
    "Electricity": [
        ("Light Not Working", "Medium"),
        ("Fan Not Working", "Medium"),
        ("Power Supply Failure", "Medium"),
        ("Frequent Power Cut", "Medium"),
        ("Switch / Socket Damage", "Medium"),
        ("Wiring Problem", "High"),
        ("Short Circuit", "High"),
        ("Electrical Spark / Burning Smell", "High"),
        ("Emergency Power / Backup Issue", "High"),
        ("Other", "Medium"),
    ],
    "Water & Sanitation": [
        ("Drinking Water Not Available", "High"),
        ("Dirty / Contaminated Water", "High"),
        ("Water Cooler Problem", "Medium"),
        ("Water Filter Problem", "Medium"),
        ("Washroom Tap Not Working", "Medium"),
        ("Flush Not Working", "Medium"),
        ("Water Leakage", "Medium"),
        ("Low Water Pressure", "Low"),
        ("Drainage Blockage / Overflow", "High"),
        ("Other", "Medium"),
    ],
    "IT & Computer": [
        ("Computer / PC Not Working", "Medium"),
        ("Monitor Problem", "Low"),
        ("Keyboard / Mouse Problem", "Low"),
        ("Internet / Wi-Fi Not Working", "Medium"),
        ("Slow Internet", "Low"),
        ("Lab Software Not Installed / Not Working", "Medium"),
        ("Printer Problem", "Low"),
        ("Projector Problem", "Medium"),
        ("Network Cable / Port Damage", "Medium"),
        ("Login / User Account Issue", "Medium"),
        ("Other", "Low"),
    ],
    "Academics": [
        ("Timetable Issue", "Medium"),
        ("Lecture / Practical Rescheduling", "Medium"),
        ("Syllabus Incompletion", "High"),
        ("Assignment / Submission Query", "Low"),
        ("Internal Assessment / Marks Issue", "Medium"),
        ("Attendance Mismatch", "Medium"),
        ("Academic Material / Notes Not Provided", "Low"),
        ("Other Academic Issue", "Low"),
        ("Other", "Low"),
    ],
    "Faculty": [
        ("Faculty Unavailability", "Medium"),
        ("Lecture Not Conducted", "Medium"),
        ("Irregular Classes", "Medium"),
        ("Teaching Pace / Clarity", "Low"),
        ("Doubts Not Resolved", "Low"),
        ("Evaluation / Feedback Delay", "Medium"),
        ("Communication Gap", "Low"),
        ("Other Faculty Issue", "Low"),
        ("Other", "Low"),
    ],
    "Canteen": [
        ("Food Quality Issue", "Medium"),
        ("Unhygienic Food Preparation", "High"),
        ("Stale / Expired Food", "High"),
        ("Overcharging / Price Dispute", "Low"),
        ("Slow Service", "Low"),
        ("Limited Food Availability", "Low"),
        ("Drinking Water Issue", "High"),
        ("Canteen Seating / Table Cleanliness", "Low"),
        ("Other", "Low"),
    ],
    "Hostel": [
        ("Room Maintenance", "Low"),
        ("Bed / Furniture Damage", "Low"),
        ("Room Cleaning", "Low"),
        ("Washroom Maintenance / Cleaning", "Medium"),
        ("Hot Water Issue", "Medium"),
        ("Hostel Electricity Issue", "Medium"),
        ("Hostel Wi-Fi Issue", "Low"),
        ("Drinking Water Issue", "High"),
        ("Noise / Disturbance", "Medium"),
        ("Security / Gate Timing Issue", "High"),
        ("Other", "Low"),
    ],
    "Transport": [
        ("Bus Delay", "Medium"),
        ("Bus Not Arrived", "High"),
        ("Overcrowded Bus", "Medium"),
        ("Route Issue", "Medium"),
        ("Rash / Unsafe Driving", "High"),
        ("Driver / Conductor Behaviour", "Medium"),
        ("Bus Cleanliness", "Low"),
        ("Breakdown / Maintenance", "High"),
        ("Other", "Low"),
    ],
    "Student Related": [
        ("Student Misconduct", "Medium"),
        ("Noise / Discipline Issue", "Low"),
        ("Lost & Found", "Low"),
        ("Bullying / Harassment", "High"),
        ("Group Conflict", "High"),
        ("ID Card / Library Card Issue", "Low"),
        ("Common Area Misuse", "Low"),
        ("Other", "Low"),
    ],
    "Security & Safety": [
        ("Unauthorized Person on Campus", "High"),
        ("Theft / Missing Belongings", "High"),
        ("CCTV Not Working", "High"),
        ("Security Guard Missing", "High"),
        ("Campus Gate Security Issue", "High"),
        ("Unsafe / Dark Area on Campus", "High"),
        ("Emergency / Incident Report", "High"),
        ("Other", "Medium"),
    ],
    "Other": [
        ("General Issue", "Low"),
        ("Administrative Issue", "Medium"),
        ("Facility Not Listed", "Low"),
        ("Other Complaint", "Low"),
    ],
    "Library": [
        ("Book Availability", "Low"),
        ("Book Issue / Return", "Low"),
        ("Library Membership", "Low"),
        ("Library Timing", "Low"),
        ("Seating / Study Area", "Low"),
        ("Library Cleanliness", "Low"),
        ("Computer / Digital Library", "Medium"),
        ("Internet / Wi-Fi", "Medium"),
        ("Reference Material", "Low"),
        ("Lost / Damaged Book", "Low"),
        ("Library Staff Behaviour", "Low"),
        ("Other", "Low"),
    ],
}

PRACTICAL_SUBCATEGORIES: Dict[str, List[str]] = {
    cat: [item[0] for item in items]
    for cat, items in PRACTICAL_SUBCATEGORIES_CONFIG.items()
}

_SUBCAT_PRIORITY_LOOKUP: Dict[Tuple[str, str], str] = {}
for _cat, _items in PRACTICAL_SUBCATEGORIES_CONFIG.items():
    for _sub, _pri in _items:
        _SUBCAT_PRIORITY_LOOKUP[(_cat.strip().lower(), _sub.strip().lower())] = _pri
        _SUBCAT_PRIORITY_LOOKUP[("", _sub.strip().lower())] = _pri


def get_default_priority(category_name: Optional[str], subcategory_name: Optional[str]) -> str:
    """
    Returns the intelligent default priority ('Low', 'Medium', or 'High')
    for a given category and subcategory combination.
    """
    cat_k = (category_name or "").strip().lower()
    sub_k = (subcategory_name or "").strip().lower()

    if (cat_k, sub_k) in _SUBCAT_PRIORITY_LOOKUP:
        return _SUBCAT_PRIORITY_LOOKUP[(cat_k, sub_k)]
    if ("", sub_k) in _SUBCAT_PRIORITY_LOOKUP:
        return _SUBCAT_PRIORITY_LOOKUP[("", sub_k)]

    # Keywords heuristic fallback
    high_keywords = {"fire", "spark", "burning", "short circuit", "theft", "ragging", "harassment", "unauthorized", "emergency", "breakdown", "unsafe"}
    for kw in high_keywords:
        if kw in sub_k:
            return "High"

    med_keywords = {"not working", "leakage", "cut", "failure", "delay", "damaged", "damage", "pressure", "water"}
    for kw in med_keywords:
        if kw in sub_k:
            return "Medium"

    return "Low"

