"""
models/user.py: User, Student, Staff, and Authentication models.
"""

from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    PRINCIPAL = "Principal"
    HOD = "HOD"
    COORDINATOR = "Coordinator"
    HOSTEL_INCHARGE = "Hostel Incharge"
    LIBRARY_INCHARGE = "Library Incharge"
    GENERAL_HOD = "General Department HOD"
    STUDENT = "Student"


class Student(BaseModel):
    id: Optional[str] = None
    roll_number: str
    full_name: str
    department_id: str
    department_code: Optional[str] = None
    year: str
    password_hash: Optional[str] = None
    security_question: str
    security_answer_hash: Optional[str] = None
    is_hostel: bool = False
    is_hostel_approved: bool = False
    failed_login_attempts: int = 0
    is_locked: bool = False
    locked_at: Optional[datetime] = None
    must_change_password: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def can_submit_hostel_complaint(self) -> bool:
        return self.is_hostel and self.is_hostel_approved


class StaffUser(BaseModel):
    id: Optional[str] = None
    username: str
    full_name: str
    role: UserRole
    department_id: Optional[str] = None
    department_code: Optional[str] = None
    password_hash: Optional[str] = None
    security_question: str
    security_answer_hash: Optional[str] = None
    failed_login_attempts: int = 0
    is_locked: bool = False
    locked_at: Optional[datetime] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StaffSecurityCode(BaseModel):
    id: Optional[str] = None
    role: UserRole
    department_id: Optional[str] = None
    code_hash: str
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class RollNumberEntry(BaseModel):
    id: Optional[str] = None
    department_id: str
    roll_number: str
    added_by_coordinator_id: Optional[str] = None
    is_registered: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
