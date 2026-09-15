"""
models/hostel.py: Hostel request and status models.
"""

from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class HostelRequestStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    DENIED = "Denied"


class HostelRequest(BaseModel):
    id: Optional[str] = None
    student_id: str
    student_roll: Optional[str] = None
    student_name: Optional[str] = None
    department_name: Optional[str] = None
    student_year: Optional[str] = None
    hostel_name: str
    block: str
    room_number: str
    request_date: Optional[datetime] = None
    status: HostelRequestStatus = HostelRequestStatus.PENDING
    deny_reason: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
