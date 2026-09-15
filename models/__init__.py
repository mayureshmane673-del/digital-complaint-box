"""
models package: Domain data structures and Pydantic models for Digital Complaint Box.
"""

from .user import Student, StaffUser, StaffSecurityCode, RollNumberEntry, UserRole
from .complaint import Complaint, ComplaintAttachment, ComplaintHistory, ComplaintAssignment, ComplaintStatus, ComplaintPriority
from .issue_group import IssueGroup, IssueGroupMember, IssueGroupHistory
from .hostel import HostelRequest, HostelRequestStatus
from .feedback import Feedback
from .notification import Notification

__all__ = [
    "Student", "StaffUser", "StaffSecurityCode", "RollNumberEntry", "UserRole",
    "Complaint", "ComplaintAttachment", "ComplaintHistory", "ComplaintAssignment",
    "ComplaintStatus", "ComplaintPriority", "IssueGroup", "IssueGroupMember",
    "IssueGroupHistory", "HostelRequest", "HostelRequestStatus", "Feedback", "Notification"
]
