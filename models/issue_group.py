"""
models/issue_group.py: Issue Group and Group Member models for non-destructive duplicate grouping.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class IssueGroupMember(BaseModel):
    id: Optional[str] = None
    issue_group_id: str
    complaint_id: int
    added_by: Optional[str] = None
    added_at: Optional[datetime] = None


class IssueGroupHistory(BaseModel):
    id: Optional[str] = None
    issue_group_id: str
    action: str
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    details: Optional[str] = None
    created_at: Optional[datetime] = None


class IssueGroup(BaseModel):
    id: Optional[str] = None
    title: str
    department_id: Optional[str] = None
    is_hostel: bool = False
    group_status: str = "Pending"  # Pending, In Progress, Resolved
    primary_complaint_id: Optional[int] = None
    duplicate_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    members: List[int] = Field(default_factory=list)  # List of complaint_ids
