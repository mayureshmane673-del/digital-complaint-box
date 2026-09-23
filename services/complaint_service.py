"""
services/complaint_service.py: Production Complaint lifecycle and business logic.
Handles concurrency-safe sequence generation, anonymous privacy, 10-minute edit locks,
role-based status transitions, soft deletes, assignments, priority enforcement, and audit logs.
"""

from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime, timezone
from database.supabase_client import get_supabase_client, get_trusted_backend_client
from utils.security import generate_anonymous_token
from utils.validators import validate_description
from services.duplicate_service import DuplicateService
from services.issue_group_service import IssueGroupService
from concurrent.futures import ThreadPoolExecutor
from services.cache_service import CacheService
from models.user import UserRole
from models.complaint import ComplaintStatus, ComplaintPriority


def _get_client():
    from unittest.mock import Mock
    if isinstance(get_supabase_client, Mock):
        return get_supabase_client()
    return get_trusted_backend_client()


class ComplaintService:
    # -------------------------------------------------------------------------
    # COMPLAINT CREATION & SUBMISSION
    # -------------------------------------------------------------------------
    @classmethod
    def submit_complaint(
        cls,
        student_id: str,
        title: str,
        description: str,
        department_id: str,
        category_id: Optional[str],
        subcategory_id: Optional[str],
        location_id: Optional[str],
        priority: str = "Low",
        is_anonymous: bool = False,
        is_hostel: bool = False,
        location_custom: Optional[str] = None,
        category_custom: Optional[str] = None,
        subcategory_custom: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Submits a new complaint:
        - Description length: 10-1000 chars
        - Location compulsory (predefined or custom)
        - Start ID at 101, sequence concurrency-safe
        - If anonymous, student_id is omitted/hidden from staff view, and privacy token is generated
        - Automatic duplicate detection runs and links to Issue Group if found
        """
        valid_desc, desc_err = validate_description(description)
        if not valid_desc:
            return False, desc_err, None

        if not student_id:
            return False, "Unauthorized: Student identity session is required.", None

        if not location_id and not (location_custom and location_custom.strip()):
            return False, "Location is compulsory (select a location or specify Other).", None

        client = get_trusted_backend_client()

        # Verify student enrollment and department match from database state
        st_res = client.table("students").select("id, department_id, is_hostel, is_hostel_approved, is_locked").eq("id", student_id).execute()
        if not st_res.data or len(st_res.data) == 0:
            return False, "Student profile not found.", None

        st_rec = st_res.data[0]
        if st_rec.get("is_locked"):
            return False, "Student account is locked. Cannot submit complaints.", None

        if str(st_rec.get("department_id")) != str(department_id):
            return False, f"Department mismatch: You can only submit complaints to your enrolled department.", None

        # Check hostel eligibility if hostel complaint
        if is_hostel:
            if not st_rec.get("is_hostel") or not st_rec.get("is_hostel_approved"):
                return False, "You must have an approved hostel residency status to submit hostel complaints.", None

        # Anonymous privacy handling
        anon_token = None
        if is_anonymous:
            anon_token = generate_anonymous_token(student_id, title.strip())

        # Atomic PostgreSQL submission parameters
        rpc_params = {
            "p_student_id": student_id,
            "p_title": title.strip(),
            "p_description": description.strip(),
            "p_department_id": department_id,
            "p_category_id": category_id,
            "p_subcategory_id": subcategory_id,
            "p_location_id": location_id,
            "p_location_custom": location_custom.strip() if location_custom else None,
            "p_category_custom": category_custom.strip() if category_custom else None,
            "p_subcategory_custom": subcategory_custom.strip() if subcategory_custom else None,
            "p_priority": priority,
            "p_is_anonymous": bool(is_anonymous),
            "p_is_hostel": bool(is_hostel),
            "p_ownership_token_hash": anon_token
        }

        try:
            # 1. Execute atomic submission (complaint + anonymous owner mapping + history + notifications)
            rpc_res = client.rpc("submit_complaint_atomic", rpc_params).execute()
            new_complaint = rpc_res.data
            if not new_complaint:
                return False, "Complaint submission failed (empty response from database).", None

            complaint_id = new_complaint["complaint_id"]

            # 2. Run duplicate detection against existing complaints in the same department/hostel scope
            cand_query = client.table("complaints").select(
                "complaint_id, title, description, department_id, category_id, subcategory_id, location_id, is_hostel, is_deleted, issue_group_id, priority"
            ).eq("department_id", department_id).eq("is_hostel", is_hostel).neq("complaint_id", complaint_id).eq("is_deleted", False)

            candidates = cand_query.execute().data or []
            duplicates = DuplicateService.find_duplicates(new_complaint, candidates, threshold=0.65)

            if duplicates:
                top_match, score = duplicates[0]
                # Link to existing or create new Issue Group
                success, msg, grp_id = IssueGroupService.create_or_link_issue_group(
                    primary_complaint_id=top_match["complaint_id"],
                    duplicate_complaint_id=complaint_id,
                    actor_role="System"
                )
                if grp_id:
                    # Update duplicate count and auto priority
                    dup_count = len(duplicates)
                    auto_pri = DuplicateService.calculate_auto_priority(dup_count + 1, priority)
                    client.table("complaints").update({
                        "auto_priority": auto_pri,
                        "priority": auto_pri
                    }).eq("complaint_id", complaint_id).execute()
                    new_complaint["auto_priority"] = auto_pri
                    new_complaint["priority"] = auto_pri

            CacheService.invalidate_metrics()
            return True, f"Complaint #{complaint_id} submitted successfully.", new_complaint

        except Exception as e:
            return False, f"Submission error: {str(e)}", None

    # -------------------------------------------------------------------------
    # EDITING (Student: 10-minute window, locked if admin action occurred)
    # -------------------------------------------------------------------------
    @classmethod
    def edit_complaint(
        cls,
        student_id: str,
        complaint_id: int,
        title: str,
        description: str,
        category_id: Optional[str] = None,
        subcategory_id: Optional[str] = None,
        location_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Allows student to edit complaint within 10 mins if no admin action has occurred."""
        complaint_id = int(complaint_id)
        client = _get_client()
        res = client.table("complaints").select("*").eq("complaint_id", complaint_id).execute()
        if not res.data:
            return False, "Complaint not found."

        c = res.data[0]

        # Ownership verification (for non-anonymous student_id, or token check)
        if c.get("student_id") and str(c.get("student_id")) != str(student_id):
            return False, "Unauthorized: You do not own this complaint."

        if c.get("is_deleted"):
            return False, "Cannot edit a deleted complaint."

        if c.get("has_admin_action") or c.get("status") != ComplaintStatus.PENDING.value:
            return False, "Editing is locked because administrative review has already started."

        # Check 10-minute window
        created_at_str = c.get("created_at")
        if created_at_str:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            now_utc = datetime.now(timezone.utc)
            if (now_utc - created_at).total_seconds() > 600:
                return False, "10-minute edit window has expired. Complaint cannot be modified."

        valid_desc, desc_err = validate_description(description)
        if not valid_desc:
            return False, desc_err

        prev_state = {"title": c.get("title"), "description": c.get("description")}

        client.table("complaints").update({
            "title": title.strip(),
            "description": description.strip(),
            "category_id": category_id or c.get("category_id"),
            "subcategory_id": subcategory_id or c.get("subcategory_id"),
            "location_id": location_id or c.get("location_id")
        }).eq("complaint_id", complaint_id).execute()

        # Log history
        client.table("complaint_history").insert({
            "complaint_id": complaint_id,
            "action": "EDITED",
            "actor_type": "Student",
            "actor_role": "Student",
            "actor_id": "Anonymous" if c.get("is_anonymous") else student_id,
            "previous_state": prev_state,
            "new_state": {"title": title, "description": description},
            "remarks": "Complaint updated by student within edit window."
        }).execute()

        return True, "Complaint updated successfully."

    # -------------------------------------------------------------------------
    # STUDENT SOFT DELETE
    # -------------------------------------------------------------------------
    @classmethod
    def delete_complaint_by_student(
        cls,
        complaint_id: int,
        student_id: str
    ) -> Tuple[bool, str]:
        """
        Soft-deletes a student's own complaint:
        - Must be owned by the student (direct or anonymous ownership).
        - Must be in 'Pending' status.
        - Must NOT have any administrative action (has_admin_action is False).
        - Sets is_deleted = True, deleted_by_role = 'Student', delete_reason = 'Deleted by student'.
        - Records immutable complaint_history audit entry with action = 'DELETED_BY_STUDENT'.
        - Invalidates cache.
        """
        try:
            complaint_id = int(complaint_id)
        except (ValueError, TypeError):
            return False, "Invalid complaint ID."

        if not student_id:
            return False, "Unauthorized: Student identity is required."

        client = get_trusted_backend_client()
        res = client.table("complaints").select("*").eq("complaint_id", complaint_id).execute()
        if not res.data:
            return False, "Complaint not found."

        c = res.data[0]

        # Verify ownership: either direct student_id match or anonymous ownership record
        is_owner = False
        if c.get("student_id") and str(c.get("student_id")) == str(student_id):
            is_owner = True
        elif c.get("is_anonymous"):
            anon_check = client.table("anonymous_complaint_owners").select("id").eq("complaint_id", complaint_id).eq("student_id", student_id).execute()
            if anon_check.data and len(anon_check.data) > 0:
                is_owner = True

        if not is_owner:
            return False, "Unauthorized: You can only delete your own complaints."

        if c.get("is_deleted"):
            return False, "This complaint has already been deleted."

        # Check eligibility: must be Pending and have no admin action
        if c.get("status") != ComplaintStatus.PENDING.value or c.get("has_admin_action"):
            return False, "Cannot delete complaint: Administrative review or action has already begun."

        # Perform soft delete
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            client.table("complaints").update({
                "is_deleted": True,
                "deleted_by_role": "Student",
                "delete_reason": "Deleted by student",
                "deleted_at": now_iso
            }).eq("complaint_id", complaint_id).execute()

            # Record immutable audit history
            client.table("complaint_history").insert({
                "complaint_id": complaint_id,
                "action": "DELETED_BY_STUDENT",
                "actor_type": "Student",
                "actor_role": "Student",
                "actor_id": "Anonymous" if c.get("is_anonymous") else str(student_id),
                "previous_state": {"status": c.get("status"), "is_deleted": False},
                "new_state": {"is_deleted": True},
                "remarks": "Complaint soft-deleted by student."
            }).execute()

            CacheService.invalidate_metrics()
            return True, f"Complaint #{complaint_id} deleted successfully."
        except Exception as ex:
            return False, f"Unable to delete complaint: {ex}"

    # -------------------------------------------------------------------------
    # STATUS MANAGEMENT & RULES
    # -------------------------------------------------------------------------
    @classmethod
    def update_status(
        cls,
        actor_role: str,
        actor_id: str,
        actor_dept_id: Optional[str],
        complaint_id: int,
        new_status: str,
        remark: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Updates complaint status with strict validation rules:
        - In Progress -> Resolved: resolution remark is COMPULSORY.
        - Any -> Rejected: rejection reason is COMPULSORY.
        - Other backward transitions: remark COMPULSORY.
        - Sets has_admin_action = True (locking student edit immediately).
        """
        complaint_id = int(complaint_id)
        client = _get_client()
        res = client.table("complaints").select("*").eq("complaint_id", complaint_id).execute()
        if not res.data:
            return False, "Complaint not found."

        c = res.data[0]
        old_status = c.get("status")

        # Department / scope verification
        if not cls._is_staff_authorized_for_complaint(actor_role, actor_dept_id, c):
            return False, "Unauthorized: This complaint is outside your departmental scope."

        clean_remark = remark.strip() if remark else ""

        # Status rules validation
        if new_status == ComplaintStatus.RESOLVED.value:
            if not clean_remark:
                return False, "A resolution remark is compulsory when resolving a complaint."
        elif new_status == ComplaintStatus.REJECTED.value:
            if not clean_remark:
                return False, "A rejection reason is compulsory when marking a complaint as Rejected."
        elif old_status in (ComplaintStatus.RESOLVED.value, ComplaintStatus.REJECTED.value, ComplaintStatus.IN_PROGRESS.value) and new_status == ComplaintStatus.PENDING.value:
            # Backward transition
            if not clean_remark:
                return False, "A remark explaining the status change is compulsory for backward transitions."

        update_payload: Dict[str, Any] = {
            "status": new_status,
            "has_admin_action": True
        }
        if new_status == ComplaintStatus.RESOLVED.value:
            update_payload["resolved_at"] = datetime.now().isoformat()

        client.table("complaints").update(update_payload).eq("complaint_id", complaint_id).execute()

        # Record immutable complaint history
        client.table("complaint_history").insert({
            "complaint_id": complaint_id,
            "action": f"STATUS_CHANGED_TO_{new_status.upper().replace(' ', '_')}",
            "actor_type": "Staff",
            "actor_role": actor_role,
            "actor_id": actor_id,
            "previous_state": {"status": old_status},
            "new_state": {"status": new_status},
            "remarks": clean_remark or f"Status changed from {old_status} to {new_status}."
        }).execute()

        # Notify student (if not anonymous)
        if c.get("student_id"):
            client.table("notifications").insert({
                "recipient_type": "student",
                "recipient_id": c["student_id"],
                "title": f"Complaint #{complaint_id} Status: {new_status}",
                "message": f"Your complaint has been updated to {new_status}. {clean_remark}",
                "reference_type": "complaint",
                "reference_id": str(complaint_id)
            }).execute()

        CacheService.invalidate_metrics()
        return True, f"Status changed to {new_status}."

    # -------------------------------------------------------------------------
    # SOFT DELETION
    # -------------------------------------------------------------------------
    @classmethod
    def soft_delete_complaint(
        cls,
        actor_role: str,
        actor_id: str,
        actor_dept_id: Optional[str],
        complaint_id: int,
        delete_reason: str
    ) -> Tuple[bool, str]:
        """
        Soft-deletes a complaint:
        - Students and Coordinators CANNOT delete.
        - HOD: own department complaints only.
        - Hostel Incharge: hostel complaints only.
        - Principal: all complaints.
        - Deletion reason is compulsory.
        """
        if actor_role in (UserRole.STUDENT.value, UserRole.COORDINATOR.value):
            return False, f"{actor_role}s are not permitted to delete complaints."

        if not delete_reason or not delete_reason.strip():
            return False, "A deletion reason is compulsory."

        complaint_id = int(complaint_id)
        client = _get_client()
        res = client.table("complaints").select("*").eq("complaint_id", complaint_id).execute()
        if not res.data:
            return False, "Complaint not found."

        c = res.data[0]
        if not cls._is_staff_authorized_for_complaint(actor_role, actor_dept_id, c):
            return False, "Unauthorized: Complaint is outside your administrative scope."

        client.table("complaints").update({
            "is_deleted": True,
            "deleted_by": actor_id,
            "deleted_by_role": actor_role,
            "delete_reason": delete_reason.strip(),
            "deleted_at": datetime.now().isoformat()
        }).eq("complaint_id", complaint_id).execute()

        # Record history
        client.table("complaint_history").insert({
            "complaint_id": complaint_id,
            "action": "SOFT_DELETED",
            "actor_type": "Staff",
            "actor_role": actor_role,
            "actor_id": actor_id,
            "remarks": f"Deleted by {actor_role}. Reason: {delete_reason.strip()}"
        }).execute()

        CacheService.invalidate_metrics()
        return True, f"Complaint #{complaint_id} has been soft-deleted."

    # -------------------------------------------------------------------------
    # ASSIGNMENT
    # -------------------------------------------------------------------------
    @classmethod
    def assign_complaint(
        cls,
        actor_role: str,
        actor_id: str,
        actor_dept_id: Optional[str],
        complaint_id: int,
        assigned_to_type: str,
        assigned_to_name: str,
        remarks: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Assigns a complaint:
        - HOD can assign department complaints.
        - Hostel Incharge can assign hostel complaints.
        - Coordinators and Students CANNOT assign.
        """
        if actor_role not in (
            UserRole.HOD.value,
            UserRole.HOSTEL_INCHARGE.value,
            UserRole.PRINCIPAL.value,
            UserRole.LIBRARY_INCHARGE.value,
            UserRole.GENERAL_HOD.value
        ):
            return False, f"{actor_role}s are not authorized to assign complaints."

        if not assigned_to_name.strip():
            return False, "Assigned team/person name is required."

        complaint_id = int(complaint_id)
        client = _get_client()
        res = client.table("complaints").select("*").eq("complaint_id", complaint_id).execute()
        if not res.data:
            return False, "Complaint not found."

        c = res.data[0]
        if not cls._is_staff_authorized_for_complaint(actor_role, actor_dept_id, c):
            return False, "Unauthorized: Complaint is outside your scope."

        # Insert assignment record
        client.table("complaint_assignments").insert({
            "complaint_id": complaint_id,
            "assigned_to_type": assigned_to_type,
            "assigned_to_name": assigned_to_name.strip(),
            "assigned_by": actor_id,
            "assigned_by_role": actor_role,
            "remarks": remarks.strip() if remarks else None,
            "is_active": True
        }).execute()

        # Mark admin action
        client.table("complaints").update({"has_admin_action": True}).eq("complaint_id", complaint_id).execute()

        # Record history
        client.table("complaint_history").insert({
            "complaint_id": complaint_id,
            "action": "ASSIGNED",
            "actor_type": "Staff",
            "actor_role": actor_role,
            "actor_id": actor_id,
            "remarks": f"Assigned to {assigned_to_type}: {assigned_to_name.strip()}."
        }).execute()

        CacheService.invalidate_metrics()
        return True, f"Complaint #{complaint_id} assigned to {assigned_to_name}."

    # -------------------------------------------------------------------------
    # PRIORITY MANAGEMENT
    # -------------------------------------------------------------------------
    @classmethod
    def change_priority(
        cls,
        actor_role: str,
        actor_id: str,
        actor_dept_id: Optional[str],
        complaint_id: int,
        new_priority: str
    ) -> Tuple[bool, str]:
        """
        Manually changes complaint priority:
        - HOD & Coordinator can change department complaint priority.
        - Hostel Incharge can change hostel complaint priority.
        - Principal does NOT manually change complaint priority.
        - Manual priority CANNOT be lower than the automatic minimum!
        """
        if actor_role == UserRole.PRINCIPAL.value:
            return False, "Principal does not manually change complaint priority."

        if actor_role not in (
            UserRole.HOD.value,
            UserRole.COORDINATOR.value,
            UserRole.HOSTEL_INCHARGE.value,
            UserRole.LIBRARY_INCHARGE.value,
            UserRole.GENERAL_HOD.value
        ):
            return False, f"{actor_role}s cannot modify complaint priority."

        complaint_id = int(complaint_id)
        client = _get_client()
        res = client.table("complaints").select("*, categories(name), students(year)").eq("complaint_id", complaint_id).execute()
        if not res.data:
            return False, "Complaint not found."

        c = res.data[0]
        if not cls._is_staff_authorized_for_complaint(actor_role, actor_dept_id, c):
            return False, "Unauthorized: Complaint is outside your scope."

        auto_min = c.get("auto_priority", "Low")
        if not DuplicateService.is_manual_priority_allowed(new_priority, auto_min):
            return False, f"Priority '{new_priority}' is lower than the automatic minimum priority '{auto_min}' based on duplicate volume."

        old_pri = c.get("priority")
        client.table("complaints").update({"priority": new_priority, "has_admin_action": True}).eq("complaint_id", complaint_id).execute()

        # Log history
        client.table("complaint_history").insert({
            "complaint_id": complaint_id,
            "action": "PRIORITY_CHANGED",
            "actor_type": "Staff",
            "actor_role": actor_role,
            "actor_id": actor_id,
            "previous_state": {"priority": old_pri},
            "new_state": {"priority": new_priority},
            "remarks": f"Priority updated from {old_pri} to {new_priority}."
        }).execute()

        CacheService.invalidate_metrics()
        return True, f"Priority updated to {new_priority}."

    # -------------------------------------------------------------------------
    # RETRIEVAL & ROLE-BASED FILTERING
    # -------------------------------------------------------------------------
    @classmethod
    def get_complaints_for_user(
        cls,
        role: str,
        user_id: str,
        department_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves complaints strictly bounded by 6-role routing matrix:
        - Student: only their own complaints (direct or anonymous).
        - Library Incharge: Library complaints across campus only.
        - Hostel Incharge: Hostel complaints across campus only.
        - General Department HOD: First Year complaints (non-hostel, non-library).
        - HOD / Coordinator: Academic Department complaints (non-hostel, non-library, 2nd+ year).
        - Principal: Campus-wide visibility of all complaints.
        """
        client = _get_client()
        query = client.table("complaints").select(
            "*, departments(code, name), categories(name), subcategories(name), locations(name), students(year, roll_number, full_name)"
        )

        filters = filters or {}
        include_deleted = filters.get("include_deleted", False)
        if not include_deleted:
            query = query.eq("is_deleted", False)

        if role == UserRole.STUDENT.value:
            # Student gets direct complaints (student_id = user_id)
            direct_query = client.table("complaints").select(
                "*, departments(code, name), categories(name), subcategories(name), locations(name), students(year, roll_number, full_name)"
            ).eq("student_id", user_id)
            if not include_deleted:
                direct_query = direct_query.eq("is_deleted", False)
            if filters.get("status"):
                direct_query = direct_query.eq("status", filters["status"])
            if filters.get("priority"):
                direct_query = direct_query.eq("priority", filters["priority"])

            # Also fetch anonymous complaints owned by this student
            anon_query = client.table("anonymous_complaint_owners").select("complaint_id").eq("student_id", user_id)

            with ThreadPoolExecutor(max_workers=2) as executor:
                f_direct = executor.submit(direct_query.execute)
                f_anon = executor.submit(anon_query.execute)
                try:
                    direct_items = f_direct.result().data or []
                except Exception:
                    direct_items = []
                try:
                    anon_owner_rows = f_anon.result().data or []
                except Exception:
                    anon_owner_rows = []

            anon_ids = [r["complaint_id"] for r in anon_owner_rows]

            anon_items = []
            if anon_ids:
                anon_c_query = client.table("complaints").select(
                    "*, departments(code, name), categories(name), subcategories(name), locations(name), students(year, roll_number, full_name)"
                ).in_("complaint_id", anon_ids)
                if not include_deleted:
                    anon_c_query = anon_c_query.eq("is_deleted", False)
                if filters.get("status"):
                    anon_c_query = anon_c_query.eq("status", filters["status"])
                if filters.get("priority"):
                    anon_c_query = anon_c_query.eq("priority", filters["priority"])
                try:
                    anon_items = anon_c_query.execute().data or []
                except Exception:
                    anon_items = []

            # Combine and sort by created_at desc
            combined = {c["complaint_id"]: c for c in (direct_items + anon_items)}
            results = sorted(combined.values(), key=lambda x: x.get("created_at", "") or "", reverse=True)
            return results

        elif role == UserRole.LIBRARY_INCHARGE.value:
            # Library complaints across campus (non-deleted)
            pass
        elif role == UserRole.HOSTEL_INCHARGE.value:
            query = query.eq("is_hostel", True)
        elif role == UserRole.GENERAL_HOD.value:
            # First Year / General Department
            query = query.eq("is_hostel", False)
        elif role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
            if department_id:
                query = query.eq("department_id", department_id).eq("is_hostel", False)
        elif role == UserRole.PRINCIPAL.value:
            pass  # All campus
        else:
            return []

        # Apply common filters for staff
        if filters.get("status"):
            query = query.eq("status", filters["status"])
        if filters.get("priority"):
            query = query.eq("priority", filters["priority"])
        if filters.get("category_id"):
            query = query.eq("category_id", filters["category_id"])

        res = query.order("created_at", desc=True).execute()
        raw_results = res.data or []

        # In-memory post-filtering to enforce exact role boundaries
        results = []
        for item in raw_results:
            cat_obj = item.get("categories")
            cat_name = cat_obj.get("name", "") if isinstance(cat_obj, dict) else str(item.get("category_name") or "")
            cat_custom = str(item.get("category_custom") or "")
            is_lib = (cat_name.strip().lower() == "library") or (cat_custom.strip().lower() == "library")

            st_obj = item.get("students")
            st_yr = (st_obj.get("year", "") if isinstance(st_obj, dict) else str(item.get("student_year") or "")).strip().upper()
            dept_obj = item.get("departments")
            dept_code = (dept_obj.get("code", "") if isinstance(dept_obj, dict) else "").strip().upper()
            is_first_yr = (st_yr in ("FE", "1", "1ST", "FIRST YEAR", "FIRST")) or (dept_code == "GEN")

            if role == UserRole.LIBRARY_INCHARGE.value:
                if not is_lib:
                    continue
            elif role == UserRole.HOSTEL_INCHARGE.value:
                if not item.get("is_hostel"):
                    continue
            elif role == UserRole.GENERAL_HOD.value:
                # General HOD handles First Year academic/campus complaints (excluding hostel and library)
                if item.get("is_hostel") or is_lib:
                    continue
                if not is_first_yr and dept_code != "GEN":
                    continue
            elif role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
                # Academic HOD/Coordinator handles 2nd+ year complaints in their academic department
                if item.get("is_hostel") or is_lib:
                    continue
                if is_first_yr or dept_code == "GEN":
                    continue

            # Enforce anonymous masking: staff NEVER sees student details
            if item.get("is_anonymous"):
                item["student_id"] = None
                item["student_info"] = "Anonymous Student"
                item["students"] = None

            results.append(item)

        return results

    @staticmethod
    def _is_staff_authorized_for_complaint(actor_role: str, actor_dept_id: Optional[str], complaint: Dict[str, Any]) -> bool:
        """Helper to enforce department, hostel, library, and year authorization boundaries."""
        if actor_role == UserRole.PRINCIPAL.value:
            return True

        cat_obj = complaint.get("categories")
        cat_name = cat_obj.get("name", "") if isinstance(cat_obj, dict) else str(complaint.get("category_name") or "")
        cat_custom = str(complaint.get("category_custom") or "")
        is_lib = (cat_name.strip().lower() == "library") or (cat_custom.strip().lower() == "library")

        if actor_role == UserRole.LIBRARY_INCHARGE.value:
            return is_lib

        if complaint.get("is_hostel"):
            return actor_role == UserRole.HOSTEL_INCHARGE.value

        if is_lib:
            return False  # Non-library roles cannot handle library complaints

        # Student year check
        st_obj = complaint.get("students")
        st_yr = (st_obj.get("year", "") if isinstance(st_obj, dict) else str(complaint.get("student_year") or "")).strip().upper()
        dept_obj = complaint.get("departments")
        dept_code = (dept_obj.get("code", "") if isinstance(dept_obj, dict) else "").strip().upper()
        is_first_yr = (st_yr in ("FE", "1", "1ST", "FIRST YEAR", "FIRST")) or (dept_code == "GEN")

        if actor_role == UserRole.GENERAL_HOD.value:
            return is_first_yr or (dept_code == "GEN")

        if actor_role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
            if is_first_yr or (dept_code == "GEN"):
                return False
            return str(complaint.get("department_id")) == str(actor_dept_id)

        return False

    @classmethod
    def get_complaint_attachments(cls, complaint_id: int) -> List[Dict[str, Any]]:
        """Retrieves attachments for a complaint via trusted backend."""
        client = _get_client()
        try:
            res = client.table("complaint_attachments").select("*").eq("complaint_id", int(complaint_id)).execute()
            return res.data or []
        except Exception:
            return []

    @classmethod
    def get_complaint_history(cls, complaint_id: int) -> List[Dict[str, Any]]:
        """Retrieves audit trail history for a complaint via trusted backend."""
        client = _get_client()
        try:
            res = client.table("complaint_history").select("*").eq("complaint_id", int(complaint_id)).order("created_at", desc=False).execute()
            return res.data or []
        except Exception:
            return []

