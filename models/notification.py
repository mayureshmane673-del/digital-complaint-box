"""
models/notification.py: In-app notification model with 90-day retention metadata.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class Notification(BaseModel):
    id: Optional[str] = None
    recipient_type: str  # student, staff, role
    recipient_id: Optional[str] = None
    recipient_role: Optional[str] = None
    department_id: Optional[str] = None
    title: str
    message: str
    reference_type: Optional[str] = None  # complaint, issue_group, hostel_request, feedback
    reference_id: Optional[str] = None
    is_read: bool = False
    created_at: Optional[datetime] = None
