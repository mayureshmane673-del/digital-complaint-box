"""
services/feedback_service.py: Feedback system for Resolved complaints with 1-to-5 star rating and single edit constraint.
"""

from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
from database.supabase_client import get_supabase_client, get_trusted_backend_client
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

            from services.cache_service import CacheService
            CacheService.invalidate_metrics()
            return True, "Feedback updated successfully (no further edits allowed)."

        except Exception as e:
            return False, f"Update failed: {str(e)}"

    @classmethod
    def get_feedback_for_complaint(cls, complaint_id: int) -> List[Dict[str, Any]]:
        """
        Retrieves feedback submitted for a specific complaint.
        Does NOT expose student personal identity, roll number, or credentials.
        """
        client = get_trusted_backend_client()
        try:
            res = (
                client.table("feedback")
                .select("id, complaint_id, rating, comment, edit_count, created_at, updated_at")
                .eq("complaint_id", complaint_id)
                .order("created_at", desc=True)
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    @classmethod
    def get_feedback_for_scope(
        cls,
        role: str,
        department_id: Optional[str] = None,
        is_hostel_student: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves feedback according to department-wise visibility rules:
        - Coordinator & HOD: feedback for resolved complaints in their department.
        - Hostel Incharge: feedback for hostel complaints.
        - General HOD: feedback for first-year / general complaints.
        - Library Incharge: feedback for library complaints.
        - Principal: all campus-wide feedback.
        - Does NOT expose student personal identity, credentials, or anonymous ownership.
        """
        client = get_trusted_backend_client()
        try:
            query = client.table("feedback").select(
                "id, complaint_id, rating, comment, edit_count, created_at, updated_at, "
                "complaints(complaint_id, title, department_id, is_hostel, resolved_at, "
                "departments(name, code), categories(name))"
            ).order("created_at", desc=True)

            res = query.execute()
            raw = res.data or []

            filtered = []
            for item in raw:
                comp = item.get("complaints") or {}
                c_dept = str(comp.get("department_id") or "")
                c_is_hostel = comp.get("is_hostel", False)

                if role == UserRole.PRINCIPAL.value:
                    filtered.append(item)
                elif role == UserRole.HOSTEL_INCHARGE.value:
                    if c_is_hostel:
                        filtered.append(item)
                elif role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
                    if department_id and c_dept == str(department_id) and not c_is_hostel:
                        filtered.append(item)
                elif role == UserRole.GENERAL_HOD.value:
                    if department_id and c_dept == str(department_id) and not c_is_hostel:
                        filtered.append(item)
                elif role == UserRole.LIBRARY_INCHARGE.value:
                    cat_obj = comp.get("categories") or {}
                    cat_name = (cat_obj.get("name") if isinstance(cat_obj, dict) else "").strip().lower()
                    if cat_name == "library":
                        filtered.append(item)
                elif role == UserRole.STUDENT.value:
                    filtered.append(item)

            return filtered
        except Exception as ex:
            import logging
            logging.getLogger("complaint_box.feedback").warning(
                "get_feedback_for_scope error: %s", ex
            )
            return []

    # =========================================================================
    # INSTITUTION-WIDE RESOLVED COMPLAINTS & FEEDBACK (v2)
    # =========================================================================

    @classmethod
    def get_resolved_complaints_for_student(
        cls,
        student_id: Optional[str] = None,
        department_id: Optional[str] = None,
        is_hostel_student: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Returns ALL resolved complaints across the institution that are eligible
        for student feedback.

        Requirements:
        - Shows ALL resolved complaints in the system (institution-wide).
        - It does NOT matter which student originally submitted the complaint.
        - Excludes Pending, In Progress, Rejected, and Deleted / soft-deleted complaints.
        - Privacy: Does NOT expose original complainant's name, roll number,
          student ID, or anonymous ownership credentials.
        - 2-Query Pattern (No N+1 queries):
          1. Query for all resolved, non-deleted complaints.
          2. If student_id provided, 1 batch query for this student's feedback
             matching the returned complaint IDs, then merges in memory.
        """
        client = get_trusted_backend_client()

        try:
            # Query 1: Fetch all resolved, non-deleted complaints institution-wide
            res = (
                client.table("complaints")
                .select(
                    "complaint_id, title, description, status, priority, is_hostel, "
                    "is_anonymous, created_at, updated_at, resolved_at, "
                    "department_id, category_id, subcategory_id, location_id, "
                    "location_custom, category_custom, subcategory_custom, "
                    "departments(code, name), categories(name), "
                    "subcategories(name), locations(name)"
                )
                .eq("status", ComplaintStatus.RESOLVED.value)
                .eq("is_deleted", False)
                .order("resolved_at", desc=True)
                .execute()
            )
            resolved_complaints = res.data or []

            # Query 2: Batch fetch feedback records for the current student
            if student_id and resolved_complaints:
                resolved_ids = [c["complaint_id"] for c in resolved_complaints if c.get("complaint_id")]
                if resolved_ids:
                    fb_res = (
                        client.table("feedback")
                        .select("id, complaint_id, student_id, rating, comment, edit_count, created_at, updated_at")
                        .eq("student_id", student_id)
                        .in_("complaint_id", resolved_ids)
                        .execute()
                    )
                    feedback_map = {row["complaint_id"]: row for row in (fb_res.data or [])}
                    for comp in resolved_complaints:
                        cid = comp.get("complaint_id")
                        comp["student_feedback"] = feedback_map.get(cid)
                        comp["has_feedback"] = cid in feedback_map
                else:
                    for comp in resolved_complaints:
                        comp["student_feedback"] = None
                        comp["has_feedback"] = False
            else:
                for comp in resolved_complaints:
                    comp["student_feedback"] = None
                    comp["has_feedback"] = False

            return resolved_complaints

        except Exception as ex:
            import logging
            logging.getLogger("complaint_box.feedback").warning(
                "get_resolved_complaints_for_student error: %s", ex
            )
            return []

    @classmethod
    def get_student_feedback_complaint_ids(cls, student_id: str) -> set:
        """
        Returns a set of complaint_ids for which this student has already
        submitted feedback.
        """
        client = get_trusted_backend_client()
        try:
            res = (
                client.table("feedback")
                .select("complaint_id")
                .eq("student_id", student_id)
                .execute()
            )
            return {row["complaint_id"] for row in (res.data or [])}
        except Exception:
            return set()

    @classmethod
    def get_student_feedback(cls, student_id: str, complaint_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves the feedback record submitted by a specific student for a specific complaint.
        """
        client = get_trusted_backend_client()
        try:
            res = (
                client.table("feedback")
                .select("id, complaint_id, student_id, rating, comment, edit_count, created_at, updated_at")
                .eq("student_id", student_id)
                .eq("complaint_id", complaint_id)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except Exception:
            return None

    @classmethod
    def submit_feedback_v2(
        cls,
        student_id: str,
        department_id: Optional[str] = None,
        complaint_id: int = 0,
        rating: int = 5,
        comment: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Submits feedback on a resolved complaint:
        - Student must exist and account must not be locked.
        - Complaint must exist, have status 'Resolved', and not be deleted.
        - Rating must be between 1 and 5 stars.
        - Exactly ONE feedback per student per complaint: UNIQUE(student_id, complaint_id).
        - Multiple students can review the same resolved complaint.
        - Cache is invalidated on successful submission.
        """
        if not (1 <= rating <= 5):
            return False, "Rating must be between 1 and 5 stars.", None

        client = get_trusted_backend_client()

        try:
            # 1. Fetch student record to verify account status
            st_res = (
                client.table("students")
                .select("id, is_locked")
                .eq("id", student_id)
                .execute()
            )
            if not st_res.data:
                return False, "Student profile not found.", None
            st = st_res.data[0]
            if st.get("is_locked"):
                return False, "Your account is locked. Cannot submit feedback.", None

            # 2. Fetch complaint and verify Resolved status
            c_res = (
                client.table("complaints")
                .select("complaint_id, status, is_deleted")
                .eq("complaint_id", complaint_id)
                .execute()
            )
            if not c_res.data:
                return False, "Complaint not found.", None
            c = c_res.data[0]

            if c.get("status") != ComplaintStatus.RESOLVED.value or c.get("is_deleted"):
                return False, "Feedback can only be submitted for Resolved complaints.", None

            # 3. Duplicate check for this student (UNIQUE constraint also enforces at DB level)
            fb_check = (
                client.table("feedback")
                .select("id")
                .eq("complaint_id", complaint_id)
                .eq("student_id", student_id)
                .execute()
            )
            if fb_check.data:
                return False, "You have already submitted feedback for this complaint.", None

            # 4. Insert feedback
            ins_res = client.table("feedback").insert({
                "complaint_id": complaint_id,
                "student_id": student_id,
                "rating": rating,
                "comment": comment.strip() if comment else None,
                "edit_count": 0
            }).execute()

            from services.cache_service import CacheService
            CacheService.invalidate_metrics()

            return True, "Thank you for your feedback!", ins_res.data[0] if ins_res.data else None

        except Exception as e:
            err_str = str(e)
            if "unique" in err_str.lower() or "duplicate" in err_str.lower():
                return False, "You have already submitted feedback for this complaint.", None
            return False, f"Failed to submit feedback: {err_str}", None

