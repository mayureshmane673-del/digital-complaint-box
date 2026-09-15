"""
services/feedback_service.py: Feedback system for Resolved complaints with 1-to-5 star rating and single edit constraint.
"""

from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
from database.supabase_client import get_supabase_client
from utils.security import verify_password
from models.user import UserRole
from models.complaint import ComplaintStatus


class FeedbackService:
    @classmethod
    def submit_feedback(
        cls,
        student_id: str,
        roll_number: str,
        password: str,
        complaint_id: int,
        rating: int,
        comment: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Submits feedback on a resolved complaint:
        - Re-authenticates student credentials.
        - Complaint must be in 'Resolved' status.
        - Exactly one feedback per student per complaint.
        - Rating must be between 1 and 5.
        """
        if not (1 <= rating <= 5):
            return False, "Rating must be an integer between 1 and 5 stars.", None

        client = get_supabase_client()

        # 1. Re-authenticate student
        st_res = client.table("students").select("id, password_hash, is_locked").eq("id", student_id).execute()
        if not st_res.data or st_res.data[0].get("is_locked"):
            return False, "Student authentication failed or account is locked.", None

        if not verify_password(password, st_res.data[0].get("password_hash", "")):
            return False, "Password verification failed.", None

        # 2. Verify complaint is Resolved
        c_res = client.table("complaints").select("complaint_id, status, is_deleted").eq("complaint_id", complaint_id).execute()
        if not c_res.data:
            return False, "Complaint not found.", None
        c = c_res.data[0]

        if c.get("status") != ComplaintStatus.RESOLVED.value or c.get("is_deleted"):
            return False, "Feedback can only be submitted for Resolved complaints.", None

        # 3. Check existing feedback
        fb_res = client.table("feedback").select("id").eq("complaint_id", complaint_id).eq("student_id", student_id).execute()
        if fb_res.data and len(fb_res.data) > 0:
            return False, "You have already submitted feedback for this complaint. Use Edit Feedback if needed.", None

        try:
            ins_res = client.table("feedback").insert({
                "complaint_id": complaint_id,
                "student_id": student_id,
                "rating": rating,
                "comment": comment.strip() if comment else None,
                "edit_count": 0
            }).execute()

            return True, "Thank you for your feedback!", ins_res.data[0] if ins_res.data else None

        except Exception as e:
            return False, f"Failed to submit feedback: {str(e)}", None

    @classmethod
    def edit_feedback(
        cls,
        student_id: str,
        complaint_id: int,
        new_rating: int,
        new_comment: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Allows editing feedback exactly once:
        - edit_count must be 0.
        - After edit, edit_count becomes 1 and no further edits are permitted.
        """
        if not (1 <= new_rating <= 5):
            return False, "Rating must be between 1 and 5 stars."

        client = get_supabase_client()
        fb_res = client.table("feedback").select("*").eq("complaint_id", complaint_id).eq("student_id", student_id).execute()
        if not fb_res.data:
            return False, "Feedback record not found."

        fb = fb_res.data[0]
        if fb.get("edit_count", 0) >= 1:
            return False, "Feedback can only be edited once. No further modifications are permitted."

        try:
            client.table("feedback").update({
                "rating": new_rating,
                "comment": new_comment.strip() if new_comment else None,
                "edit_count": 1,
                "updated_at": datetime.now().isoformat()
            }).eq("id", fb["id"]).execute()

            return True, "Feedback updated successfully (no further edits allowed)."

        except Exception as e:
            return False, f"Update failed: {str(e)}"

    @classmethod
    def get_feedback_for_scope(
        cls,
        role: str,
        department_id: Optional[str] = None,
        is_hostel_student: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves feedback according to department-wise visibility rules:
        - CSE student/staff sees CSE feedback.
        - AIDS sees AIDS feedback, etc.
        - Hostel feedback is visible to approved hostel students, hostel staff, and Principal.
        """
        client = get_supabase_client()
        query = client.table("feedback").select(
            "id, complaint_id, rating, comment, edit_count, created_at, complaints(title, department_id, is_hostel, departments(name, code))"
        ).order("created_at", desc=True)

        res = query.execute()
        raw = res.data or []

        filtered = []
        for item in raw:
            comp = item.get("complaints") or {}
            c_dept = comp.get("department_id")
            c_is_hostel = comp.get("is_hostel", False)

            if role == UserRole.PRINCIPAL.value:
                filtered.append(item)
            elif role == UserRole.HOSTEL_INCHARGE.value:
                if c_is_hostel:
                    filtered.append(item)
            elif role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
                if str(c_dept) == str(department_id) and not c_is_hostel:
                    filtered.append(item)
            elif role == UserRole.STUDENT.value:
                if c_is_hostel:
                    if is_hostel_student:
                        filtered.append(item)
                elif str(c_dept) == str(department_id):
                    filtered.append(item)

        return filtered
