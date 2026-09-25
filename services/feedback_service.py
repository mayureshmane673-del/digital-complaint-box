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

    # =========================================================================
    # NEW DEPARTMENT-BASED FEEDBACK METHODS (v2)
    # =========================================================================

    @classmethod
    def get_resolved_complaints_for_student(
        cls,
        student_id: str,
        department_id: Optional[str],
        is_hostel_student: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Returns ALL resolved complaints that this student is eligible to give
        feedback on, based on their department (and hostel status).

        Business rules:
        - For academic (non-hostel, non-library) complaints:
            Show resolved complaints whose department_id matches the student's
            department_id. The student does NOT need to be the original complainant.
        - For hostel complaints:
            Show resolved hostel complaints only if the student is an approved
            hostel resident (is_hostel_approved=True).
        - Library complaints:
            NOT shown to regular students via the feedback tab.
            Library Incharge handles library feedback via the staff view.
        - is_deleted=True complaints are never shown.

        The UNIQUE(student_id, complaint_id) constraint in the feedback table
        still allows multiple *different* students to submit feedback for the
        same complaint — one record per student per complaint.
        """
        from database.supabase_client import get_trusted_backend_client
        client = get_trusted_backend_client()

        try:
            # Fetch resolved, non-deleted complaints for this department
            query = (
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
            )

            # Filter by department (academic complaints)
            if department_id:
                query = query.eq("department_id", department_id)

            res = query.execute()
            raw = res.data or []

            # Post-filter: exclude hostel complaints unless student is approved,
            # and exclude library complaints from the student feedback view.
            results = []
            for item in raw:
                c_is_hostel = item.get("is_hostel", False)
                cat_obj = item.get("categories") or {}
                cat_name = (cat_obj.get("name", "") if isinstance(cat_obj, dict) else "").strip().lower()
                cat_custom = (item.get("category_custom") or "").strip().lower()
                is_lib = (cat_name == "library") or (cat_custom == "library")

                if is_lib:
                    # Library feedback is handled by Library Incharge, not students
                    continue

                if c_is_hostel and not is_hostel_student:
                    # Hostel complaints only visible to approved hostel residents
                    continue

                results.append(item)

            return results

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
        submitted feedback. Used to show 'Submitted' vs 'Pending' badges
        without querying feedback status for each complaint individually.
        """
        from database.supabase_client import get_trusted_backend_client
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
    def submit_feedback_v2(
        cls,
        student_id: str,
        department_id: Optional[str],
        complaint_id: int,
        rating: int,
        comment: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Submits feedback without password re-authentication (student is already
        authenticated via the session).

        Authorization rules enforced here (server-side):
        1. Rating must be 1-5.
        2. Complaint must exist, be Resolved, and not deleted.
        3. The complaint must belong to a department/scope the student is
           eligible for (department_id match, or hostel eligibility).
        4. The student must not have already submitted feedback (UNIQUE constraint).

        Multiple different students from the same eligible department can each
        submit one feedback record for the same complaint.
        """
        if not (1 <= rating <= 5):
            return False, "Rating must be between 1 and 5 stars.", None

        from database.supabase_client import get_trusted_backend_client
        client = get_trusted_backend_client()

        try:
            # 1. Fetch student record to verify account status and hostel status
            st_res = (
                client.table("students")
                .select("id, department_id, is_hostel_approved, is_locked")
                .eq("id", student_id)
                .execute()
            )
            if not st_res.data:
                return False, "Student profile not found.", None
            st = st_res.data[0]
            if st.get("is_locked"):
                return False, "Your account is locked. Cannot submit feedback.", None

            # 2. Fetch complaint
            c_res = (
                client.table("complaints")
                .select("complaint_id, status, is_deleted, department_id, is_hostel, categories(name), category_custom")
                .eq("complaint_id", complaint_id)
                .execute()
            )
            if not c_res.data:
                return False, "Complaint not found.", None
            c = c_res.data[0]

            if c.get("status") != ComplaintStatus.RESOLVED.value or c.get("is_deleted"):
                return False, "Feedback can only be submitted for Resolved complaints.", None

            # 3. Eligibility check
            c_dept = str(c.get("department_id", ""))
            c_is_hostel = c.get("is_hostel", False)
            cat_obj = c.get("categories") or {}
            cat_name = (cat_obj.get("name", "") if isinstance(cat_obj, dict) else "").strip().lower()
            cat_custom = (c.get("category_custom") or "").strip().lower()
            is_lib = (cat_name == "library") or (cat_custom == "library")

            if is_lib:
                return False, "Library complaint feedback is handled through the Library Incharge.", None

            if c_is_hostel:
                if not st.get("is_hostel_approved"):
                    return False, "Only approved hostel residents can give feedback on hostel complaints.", None
            else:
                # Academic department: must match the complaint's department
                if department_id and c_dept != str(department_id):
                    return False, "You are not eligible to give feedback on complaints from another department.", None
                # Also verify via student's stored department_id
                if str(st.get("department_id", "")) != c_dept:
                    return False, "You are not eligible to give feedback on complaints from another department.", None

            # 4. Duplicate check (UNIQUE constraint will also enforce this at DB level)
            fb_check = (
                client.table("feedback")
                .select("id")
                .eq("complaint_id", complaint_id)
                .eq("student_id", student_id)
                .execute()
            )
            if fb_check.data:
                return False, "You have already submitted feedback for this complaint.", None

            # 5. Insert feedback
            ins_res = client.table("feedback").insert({
                "complaint_id": complaint_id,
                "student_id": student_id,
                "rating": rating,
                "comment": comment.strip() if comment else None,
                "edit_count": 0
            }).execute()

            return True, "Thank you for your feedback!", ins_res.data[0] if ins_res.data else None

        except Exception as e:
            err_str = str(e)
            if "unique" in err_str.lower() or "duplicate" in err_str.lower():
                return False, "You have already submitted feedback for this complaint.", None
            return False, f"Failed to submit feedback: {err_str}", None
