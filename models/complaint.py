"""
models/complaint.py: Core Complaint, Attachment, History, and Assignment models.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
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
