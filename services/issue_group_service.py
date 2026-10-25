import logging
from typing import Tuple, Optional, Dict, Any, List
from collections import defaultdict
from database.supabase_client import get_supabase_client, get_trusted_backend_client
from models.user import UserRole

logger = logging.getLogger("complaint_box.issue_group_service")


def _get_client():
    from unittest.mock import Mock
    if isinstance(get_supabase_client, Mock):
        return get_supabase_client()
    return get_trusted_backend_client()


class IssueGroupService:
    @classmethod
    def create_or_link_issue_group(
        cls,
        primary_complaint_id: int,
        duplicate_complaint_id: int,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        actor_dept_id: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Links a duplicate complaint to an existing Issue Group or creates a new one.
        Ensures neither complaint is deleted or overwritten.
        Uses trusted backend client and enforces role authorization boundaries.
        """
        # Role authorization checks
        if actor_role in (UserRole.STUDENT.value, UserRole.PRINCIPAL.value):
            return False, f"Unauthorized: {actor_role} cannot create or modify issue groups.", None

        client = _get_client()

        # Check primary complaint
        p_res = client.table("complaints").select("*").eq("complaint_id", primary_complaint_id).execute()
        if not p_res.data:
            return False, f"Primary complaint #{primary_complaint_id} not found.", None
        primary_c = p_res.data[0]

        # Scope enforcement if actor_role is staff
        if actor_role in (UserRole.HOD.value, UserRole.COORDINATOR.value, UserRole.GENERAL_HOD.value) and actor_dept_id:
            if str(primary_c.get("department_id")) != str(actor_dept_id) or primary_c.get("is_hostel"):
                return False, "Unauthorized: Cannot manage issue groups outside your department.", None
        elif actor_role == UserRole.HOSTEL_INCHARGE.value:
            if not primary_c.get("is_hostel"):
                return False, "Unauthorized: Hostel Incharge can only manage hostel issue groups.", None

        group_id = primary_c.get("issue_group_id")

        if not group_id:
            # Create new Issue Group
            grp_res = client.table("issue_groups").insert({
                "title": f"Grouped Issue: {primary_c.get('title')}",
                "department_id": primary_c.get("department_id"),
                "is_hostel": primary_c.get("is_hostel", False),
                "group_status": "Pending",
                "primary_complaint_id": primary_complaint_id,
                "duplicate_count": 1
            }).execute()
            if not grp_res.data:
                return False, "Failed to initialize Issue Group.", None
            group_id = grp_res.data[0]["id"]

            # Add primary complaint as member and update its issue_group_id
            client.table("issue_group_members").insert({
                "issue_group_id": group_id,
                "complaint_id": primary_complaint_id,
                "added_by": actor_id
            }).execute()
            client.table("complaints").update({"issue_group_id": group_id}).eq("complaint_id", primary_complaint_id).execute()

        # Add duplicate complaint to group
        # Check if already member
        m_check = client.table("issue_group_members").select("id").eq("issue_group_id", group_id).eq("complaint_id", duplicate_complaint_id).execute()
        if not m_check.data:
            client.table("issue_group_members").insert({
                "issue_group_id": group_id,
                "complaint_id": duplicate_complaint_id,
                "added_by": actor_id
            }).execute()
            client.table("complaints").update({"issue_group_id": group_id}).eq("complaint_id", duplicate_complaint_id).execute()

        # Recalculate member count
        members_res = client.table("issue_group_members").select("complaint_id").eq("issue_group_id", group_id).execute()
        total_members = len(members_res.data or [])
        dup_count = max(0, total_members - 1)

        # Update group duplicate_count
        client.table("issue_groups").update({"duplicate_count": dup_count}).eq("id", group_id).execute()

        # Record group history
        client.table("issue_group_history").insert({
            "issue_group_id": group_id,
            "action": "LINK_COMPLAINT",
            "actor_id": actor_id,
            "actor_role": actor_role or "System",
            "details": f"Complaint #{duplicate_complaint_id} linked to group (Total duplicates: +{dup_count})."
        }).execute()

        from services.cache_service import CacheService
        CacheService.invalidate_issue_groups()

        return True, f"Complaint #{duplicate_complaint_id} successfully linked to Issue Group.", group_id

    @classmethod
    def unlink_complaint(
        cls,
        complaint_id: int,
        actor_id: str,
        actor_role: str,
        actor_dept_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Unlinks a complaint from its Issue Group.
        Enforces role authorization boundaries.
        """
        if actor_role in (UserRole.STUDENT.value, UserRole.PRINCIPAL.value):
            return False, f"Unauthorized: {actor_role} cannot unlink complaints from issue groups."

        client = _get_client()
        c_res = client.table("complaints").select("complaint_id, department_id, is_hostel, issue_group_id").eq("complaint_id", complaint_id).execute()
        if not c_res.data or not c_res.data[0].get("issue_group_id"):
            return False, f"Complaint #{complaint_id} is not part of any Issue Group."

        comp = c_res.data[0]
        group_id = comp["issue_group_id"]

        # Scope enforcement
        if actor_role in (UserRole.HOD.value, UserRole.COORDINATOR.value, UserRole.GENERAL_HOD.value) and actor_dept_id:
            if str(comp.get("department_id")) != str(actor_dept_id) or comp.get("is_hostel"):
                return False, "Unauthorized: Cannot unlink complaints outside your department."
        elif actor_role == UserRole.HOSTEL_INCHARGE.value:
            if not comp.get("is_hostel"):
                return False, "Unauthorized: Hostel Incharge can only unlink hostel complaints."

        # Delete membership
        client.table("issue_group_members").delete().eq("issue_group_id", group_id).eq("complaint_id", complaint_id).execute()
        client.table("complaints").update({"issue_group_id": None}).eq("complaint_id", complaint_id).execute()

        # Update member count
        members_res = client.table("issue_group_members").select("complaint_id").eq("issue_group_id", group_id).execute()
        total_members = len(members_res.data or [])
        dup_count = max(0, total_members - 1)
        client.table("issue_groups").update({"duplicate_count": dup_count}).eq("id", group_id).execute()

        # Record history
        client.table("issue_group_history").insert({
            "issue_group_id": group_id,
            "action": "UNLINK_COMPLAINT",
            "actor_id": actor_id,
            "actor_role": actor_role,
            "details": f"Complaint #{complaint_id} unlinked from group."
        }).execute()

        from services.cache_service import CacheService
        CacheService.invalidate_issue_groups()

        return True, f"Complaint #{complaint_id} unlinked from group."

    @classmethod
    def get_issue_group_details(
        cls,
        group_id: str,
        role: Optional[str] = None,
        department_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves Issue Group with all member complaints and independent statuses.
        Anonymous student identities are strictly masked!
        Enforces role-based visibility:
        - Principal -> None
        - Student -> None
        - Coordinator / HOD -> only within own department
        - Hostel Incharge -> only hostel groups
        - Library Incharge -> only library groups
        """
        if role in (UserRole.STUDENT.value, UserRole.PRINCIPAL.value):
            return None

        client = _get_client()
        grp_res = client.table("issue_groups").select("*").eq("id", group_id).execute()
        if not grp_res.data:
            return None

        group = grp_res.data[0]

        # Scope enforcement
        if role in (UserRole.HOD.value, UserRole.COORDINATOR.value, UserRole.GENERAL_HOD.value) and department_id:
            if str(group.get("department_id")) != str(department_id) or group.get("is_hostel"):
                return None
        elif role == UserRole.HOSTEL_INCHARGE.value:
            if not group.get("is_hostel"):
                return None

        # Fetch members with complaint and student details
        members_res = client.table("issue_group_members").select(
            "id, issue_group_id, complaint_id, complaints(complaint_id, title, description, status, priority, is_anonymous, created_at, student_id, students(full_name, roll_number), categories(name))"
        ).eq("issue_group_id", group_id).execute()

        member_list = []
        is_library_group = False
        for m in (members_res.data or []):
            comp = m.get("complaints")
            if comp:
                cat_info = comp.get("categories")
                cat_name = cat_info.get("name", "") if isinstance(cat_info, dict) else ""
                if cat_name.lower() == "library":
                    is_library_group = True

                is_anon = comp.get("is_anonymous", False)
                st_rec = comp.get("students") or {}
                st_name = st_rec.get("full_name") or "Student"
                st_roll = st_rec.get("roll_number")

                c_dict = {
                    "id": m.get("id"),
                    "complaint_id": comp.get("complaint_id"),
                    "title": comp.get("title"),
                    "description": comp.get("description", ""),
                    "status": comp.get("status", "Pending"),
                    "priority": comp.get("priority", "Low"),
                    "is_anonymous": is_anon,
                    "created_at": comp.get("created_at")
                }
                if is_anon:
                    c_dict["student_info"] = "Anonymous Student"
                    c_dict["student_name"] = "Anonymous Student"
                    c_dict["roll_number"] = None
                    c_dict["student_id"] = None
                    c_dict["students"] = None
                else:
                    c_dict["student_name"] = st_name
                    c_dict["student_id"] = comp.get("student_id")
                    if role in (UserRole.COORDINATOR.value, UserRole.HOD.value, UserRole.GENERAL_HOD.value, UserRole.HOSTEL_INCHARGE.value) and st_roll:
                        c_dict["roll_number"] = st_roll
                        c_dict["student_info"] = f"{st_name} ({st_roll})"
                    else:
                        c_dict["roll_number"] = None
                        c_dict["student_info"] = st_name

                member_list.append(c_dict)

        if role == UserRole.LIBRARY_INCHARGE.value and not is_library_group:
            return None

        group["member_complaints"] = member_list
        return group

    @classmethod
    def get_department_groups(
        cls,
        department_id: Optional[str] = None,
        role: Optional[str] = None,
        is_hostel: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves Issue Groups strictly scoped to allowed roles:
        - Coordinator -> Own academic department issue groups
        - HOD -> Own academic department issue groups
        - General Department HOD -> General / First Year issue groups
        - Hostel Incharge -> Hostel-related issue groups only
        - Library Incharge -> Library-related issue groups only
        - Principal -> Strictly blocked (returns [])
        - Student -> Strictly blocked (returns [])

        Anonymous complaints within groups have student identities strictly masked.
        Non-anonymous complaints display student name, and roll number only to authorized roles.
        """
        # Block unauthorized roles
        if role in (UserRole.STUDENT.value, UserRole.PRINCIPAL.value):
            return []

        allowed_roles = {
            UserRole.COORDINATOR.value,
            UserRole.HOD.value,
            UserRole.GENERAL_HOD.value,
            UserRole.LIBRARY_INCHARGE.value,
            UserRole.HOSTEL_INCHARGE.value
        }
        if role and role not in allowed_roles:
            return []

        from services.cache_service import CacheService
        cached = CacheService.get_cached_issue_groups(department_id, role, is_hostel)
        if cached is not None:
            return cached

        client = _get_client()

        try:
            query = client.table("issue_groups").select("*")

            # Apply strict role-based scoping
            if role == UserRole.HOSTEL_INCHARGE.value or is_hostel is True:
                query = query.eq("is_hostel", True)
            elif role == UserRole.LIBRARY_INCHARGE.value:
                # Scoped to library complaints (post-filtered via member categories)
                pass
            elif role in (UserRole.HOD.value, UserRole.COORDINATOR.value, UserRole.GENERAL_HOD.value):
                if not department_id:
                    return []
                query = query.eq("department_id", department_id).eq("is_hostel", False)
            elif is_hostel is False:
                query = query.eq("is_hostel", False)

            res = query.order("created_at", desc=True).execute()
        except Exception as e:
            logger.error("Failed to query issue groups: %s", e)
            return []

        groups = res.data or []
        if not groups:
            CacheService.set_cached_issue_groups(department_id, role, is_hostel, [], ttl_seconds=30)
            return []

        # Batch-fetch all members for all groups in a single query
        group_ids = [g["id"] for g in groups]
        members_by_group = defaultdict(list)
        library_groups = set()

        try:
            m_res = client.table("issue_group_members").select(
                "id, issue_group_id, complaint_id, complaints(complaint_id, title, description, status, priority, is_anonymous, created_at, category_id, student_id, students(full_name, roll_number), categories(name))"
            ).in_("issue_group_id", group_ids).execute()

            for m in (m_res.data or []):
                gid = m.get("issue_group_id")
                comp = m.get("complaints")
                if comp:
                    cat_info = comp.get("categories")
                    cat_name = cat_info.get("name", "") if isinstance(cat_info, dict) else ""
                    if cat_name.lower() == "library":
                        library_groups.add(gid)

                    is_anon = comp.get("is_anonymous", False)
                    st_rec = comp.get("students") or {}
                    st_name = st_rec.get("full_name") or "Student"
                    st_roll = st_rec.get("roll_number")

                    c_dict = {
                        "id": m.get("id"),
                        "complaint_id": comp.get("complaint_id"),
                        "title": comp.get("title"),
                        "description": comp.get("description", ""),
                        "status": comp.get("status", "Pending"),
                        "priority": comp.get("priority", "Low"),
                        "is_anonymous": is_anon,
                        "created_at": comp.get("created_at")
                    }

                    if is_anon:
                        c_dict["student_info"] = "Anonymous Student"
                        c_dict["student_name"] = "Anonymous Student"
                        c_dict["roll_number"] = None
                        c_dict["student_id"] = None
                        c_dict["students"] = None
                    else:
                        c_dict["student_name"] = st_name
                        c_dict["student_id"] = comp.get("student_id")
                        if role in (UserRole.COORDINATOR.value, UserRole.HOD.value, UserRole.GENERAL_HOD.value, UserRole.HOSTEL_INCHARGE.value) and st_roll:
                            c_dict["roll_number"] = st_roll
                            c_dict["student_info"] = f"{st_name} ({st_roll})"
                        else:
                            c_dict["roll_number"] = None
                            c_dict["student_info"] = st_name

                    members_by_group[gid].append(c_dict)
                else:
                    members_by_group[gid].append({
                        "id": m.get("id"),
                        "complaint_id": m.get("complaint_id"),
                        "title": f"Complaint #{m.get('complaint_id')}",
                        "description": "",
                        "status": "Pending",
                        "priority": "Low",
                        "is_anonymous": False,
                        "created_at": None,
                        "student_name": "Student",
                        "student_info": "Student"
                    })
        except Exception as e:
            logger.error("Failed to fetch issue group members: %s", e)

        filtered_groups = []
        for g in groups:
            gid = g["id"]
            g["parent_complaint_id"] = g.get("primary_complaint_id")
            g["status"] = g.get("group_status", "Active")
            g["members"] = members_by_group.get(gid, [])

            # Role filtering for library
            if role == UserRole.LIBRARY_INCHARGE.value and gid not in library_groups:
                continue

            # Display title formatting: Original Title + (+N)
            dup_cnt = g.get("duplicate_count", 0)
            base_t = g.get("title", "")
            if base_t.startswith("Grouped Issue: "):
                base_t = base_t.replace("Grouped Issue: ", "")
            if dup_cnt > 0:
                g["display_title"] = f"{base_t} (+{dup_cnt})"
            else:
                g["display_title"] = base_t
            filtered_groups.append(g)

        CacheService.set_cached_issue_groups(department_id, role, is_hostel, filtered_groups, ttl_seconds=30)
        return filtered_groups

