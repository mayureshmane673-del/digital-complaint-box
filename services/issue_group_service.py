"""
services/issue_group_service.py: Non-destructive duplicate grouping and Issue Group lifecycle.
Individual complaints and statuses remain strictly independent.
"""

from typing import Tuple, Optional, Dict, Any, List
from database.supabase_client import get_supabase_client, get_trusted_backend_client
from models.user import UserRole


class IssueGroupService:
    @classmethod
    def create_or_link_issue_group(
        cls,
        primary_complaint_id: int,
        duplicate_complaint_id: int,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Links a duplicate complaint to an existing Issue Group or creates a new one.
        Ensures neither complaint is deleted or overwritten.
        """
        client = get_supabase_client()

        # Check primary complaint
        p_res = client.table("complaints").select("*").eq("complaint_id", primary_complaint_id).execute()
        if not p_res.data:
            return False, f"Primary complaint #{primary_complaint_id} not found.", None
        primary_c = p_res.data[0]

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

        return True, f"Complaint #{duplicate_complaint_id} successfully linked to Issue Group.", group_id

    @classmethod
    def unlink_complaint(
        cls,
        complaint_id: int,
        actor_id: str,
        actor_role: str
    ) -> Tuple[bool, str]:
        """
        Unlinks a complaint from its Issue Group.
        """
        client = get_supabase_client()
        c_res = client.table("complaints").select("issue_group_id").eq("complaint_id", complaint_id).execute()
        if not c_res.data or not c_res.data[0].get("issue_group_id"):
            return False, f"Complaint #{complaint_id} is not part of any Issue Group."

        group_id = c_res.data[0]["issue_group_id"]

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

        return True, f"Complaint #{complaint_id} unlinked from group."

    @classmethod
    def get_issue_group_details(cls, group_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves Issue Group with all member complaints and independent statuses.
        Anonymous student identities are strictly masked!
        """
        client = get_supabase_client()
        grp_res = client.table("issue_groups").select("*").eq("id", group_id).execute()
        if not grp_res.data:
            return None

        group = grp_res.data[0]
        # Fetch members
        members_res = client.table("issue_group_members").select(
            "complaint_id, complaints(complaint_id, title, description, status, priority, is_anonymous, created_at)"
        ).eq("issue_group_id", group_id).execute()

        member_list = []
        for m in (members_res.data or []):
            comp = m.get("complaints")
            if comp:
                # Mask anonymous student
                if comp.get("is_anonymous"):
                    comp["student_info"] = "Anonymous Student"
                member_list.append(comp)

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
        Retrieves Issue Groups scoped to the user's role and department:
        - Principal -> All issue groups across campus
        - HOD -> Own academic department issue groups
        - Coordinator -> Own academic department issue groups
        - General Department HOD -> General / First Year issue groups
        - Hostel Incharge -> Hostel-related issue groups only
        - Library Incharge -> Library-related issue groups only
        - Student -> Strictly blocked from issue group internal management (returns [])

        Anonymous complaints within groups have student identities strictly masked.
        """
        if role == UserRole.STUDENT.value:
            return []

        client = get_trusted_backend_client()

        try:
            query = client.table("issue_groups").select("*")

            # Apply role-based scoping
            if role == UserRole.PRINCIPAL.value:
                pass
            elif role == UserRole.HOSTEL_INCHARGE.value or is_hostel is True:
                query = query.eq("is_hostel", True)
            elif role == UserRole.LIBRARY_INCHARGE.value:
                # Scoped to library complaints
                pass
            elif role == UserRole.GENERAL_HOD.value:
                if department_id:
                    query = query.eq("department_id", department_id).eq("is_hostel", False)
            elif role in (UserRole.HOD.value, UserRole.COORDINATOR.value) or department_id:
                if department_id:
                    query = query.eq("department_id", department_id).eq("is_hostel", False)
            elif is_hostel is False:
                query = query.eq("is_hostel", False)

            res = query.order("created_at", desc=True).execute()
        except Exception:
            return []

        groups = res.data or []
        if not groups:
            return []

        filtered_groups = []
        # For each group, load its members and mask anonymous student info
        for g in groups:
            gid = g["id"]
            g["parent_complaint_id"] = g.get("primary_complaint_id")
            g["status"] = g.get("group_status", "Active")

            try:
                m_res = client.table("issue_group_members").select(
                    "id, complaint_id, complaints(complaint_id, title, description, status, priority, is_anonymous, created_at, category_id, categories(name))"
                ).eq("issue_group_id", gid).execute()

                members = []
                is_library_group = False
                for m in (m_res.data or []):
                    comp = m.get("complaints")
                    if comp:
                        c_dict = {
                            "id": m.get("id"),
                            "complaint_id": comp.get("complaint_id"),
                            "title": comp.get("title"),
                            "status": comp.get("status", "Pending"),
                            "priority": comp.get("priority", "Low"),
                            "is_anonymous": comp.get("is_anonymous", False),
                            "created_at": comp.get("created_at")
                        }
                        cat_info = comp.get("categories")
                        cat_name = cat_info.get("name", "") if isinstance(cat_info, dict) else ""
                        if cat_name.lower() == "library":
                            is_library_group = True
                        if comp.get("is_anonymous"):
                            c_dict["student_info"] = "Anonymous Student"
                        members.append(c_dict)
                    else:
                        members.append({
                            "id": m.get("id"),
                            "complaint_id": m.get("complaint_id"),
                            "status": "Pending",
                            "priority": "Low"
                        })
                g["members"] = members
            except Exception:
                g["members"] = []

            # Role filtering for library
            if role == UserRole.LIBRARY_INCHARGE.value and not is_library_group:
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

        return filtered_groups
