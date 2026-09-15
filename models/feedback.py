"""
models/feedback.py: Feedback model with 1-to-5 star rating and single edit constraint.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class Feedback(BaseModel):
    id: Optional[str] = None
    complaint_id: int
    student_id: str
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
    edit_count: int = Field(default=0, le=1)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def can_edit(self) -> bool:
        return self.edit_count < 1
