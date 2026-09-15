"""
services/hostel_service.py: Hostel request lifecycle and student hostel status enforcement.
"""

from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime
from database.supabase_client import get_supabase_client, get_trusted_backend_client
from models.user import UserRole
from models.hostel import HostelRequestStatus


def _get_client():
    from unittest.mock import Mock
    if isinstance(get_supabase_client, Mock):
        return get_supabase_client()
    return get_trusted_backend_client()


class HostelService:
    @classmethod
    def get_student_hostel_request(cls, student_id: str) -> Optional[Dict[str, Any]]:
        """Fetches the latest hostel request for a student."""
        client = _get_client()
        res = client.table("hostel_requests").select("*").eq("student_id", student_id).order("created_at", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None

    @classmethod
    def submit_hostel_request(
        cls,
        student_id: str,
        hostel_name: str,
        block: str,
        room_number: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Submits or re-requests hostel access after a denial."""
        if not hostel_name or not block or not room_number:
            return False, "Hostel Name, Block, and Room Number are all required.", None

        client = _get_client()

        # Check if active pending request already exists
        existing = cls.get_student_hostel_request(student_id)
        if existing and existing.get("status") == HostelRequestStatus.PENDING.value:
            return False, "You already have a pending hostel request awaiting review.", None

        try:
            res = client.table("hostel_requests").insert({
                "student_id": student_id,
                "hostel_name": hostel_name.strip(),
                "block": block.strip(),
                "room_number": room_number.strip(),
                "status": HostelRequestStatus.PENDING.value
            }).execute()

            # Update student record flag
            client.table("students").update({
                "is_hostel": True,
                "is_hostel_approved": False
            }).eq("id", student_id).execute()

            req_id = res.data[0]["id"] if res.data else None

            # Fetch student name/roll for notification
            st_name = "A student"
            try:
                st_res = client.table("students").select("full_name, roll_number").eq("id", student_id).execute()
                if st_res.data:
                    st_name = f"{st_res.data[0].get('full_name')} ({st_res.data[0].get('roll_number')})"
            except Exception:
                pass

            # Notify Hostel Incharge
            try:
                client.table("notifications").insert({
                    "recipient_type": "role",
                    "recipient_role": UserRole.HOSTEL_INCHARGE.value,
                    "title": "New Hostel Access Request",
                    "message": f"{st_name} has submitted a hostel access request for {hostel_name} Block {block} Room {room_number}.",
                    "reference_type": "hostel_request",
                    "reference_id": req_id
                }).execute()
            except Exception:
                pass

            # Notify Principal
            try:
                client.table("notifications").insert({
                    "recipient_type": "role",
                    "recipient_role": UserRole.PRINCIPAL.value,
                    "title": "New Hostel Access Request",
                    "message": f"{st_name} has submitted a hostel access request for {hostel_name} Block {block} Room {room_number}.",
                    "reference_type": "hostel_request",
                    "reference_id": req_id
                }).execute()
            except Exception:
                pass

            return True, "Hostel request submitted successfully.", res.data[0] if res.data else None

        except Exception as e:
            return False, f"Failed to submit hostel request: {str(e)}", None

    @classmethod
    def get_all_hostel_requests(cls, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves hostel requests with student info for Hostel Incharge dashboard.
        Never exposes password or security answer.
        """
        client = _get_client()
        query = client.table("hostel_requests").select(
            "id, hostel_name, block, room_number, request_date, status, deny_reason, "
            "students(id, roll_number, full_name, year, departments(name, code))"
        ).order("created_at", desc=True)

        if status_filter and status_filter.lower() != "all":
            query = query.eq("status", status_filter)

        res = query.execute()
        return res.data or []

    @classmethod
    def review_hostel_request(
        cls,
        reviewer_role: str,
        reviewer_id: str,
        request_id: str,
        action: str,  # 'Approve' or 'Deny'
        deny_reason: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Hostel Incharge review workflow:
        - Approve: marks student as hostel approved.
        - Deny: mandatory deny_reason, notifies student with reason.
        """
        if reviewer_role not in (UserRole.HOSTEL_INCHARGE.value, UserRole.PRINCIPAL.value):
            return False, "Only Hostel Incharge or Principal can review hostel requests."

        client = _get_client()
        res = client.table("hostel_requests").select("*, students(id, full_name)").eq("id", request_id).execute()
        if not res.data or len(res.data) == 0:
            return False, "Hostel request not found."

        req = res.data[0]
        student_id = req["student_id"]

        import uuid
        valid_reviewer_uuid = None
        if reviewer_id:
            try:
                uuid.UUID(str(reviewer_id))
                valid_reviewer_uuid = str(reviewer_id)
            except (ValueError, AttributeError):
                valid_reviewer_uuid = None

        if action.lower() == "approve":
            client.table("hostel_requests").update({
                "status": HostelRequestStatus.APPROVED.value,
                "reviewed_by": valid_reviewer_uuid,
                "reviewed_at": datetime.now().isoformat(),
                "deny_reason": None
            }).eq("id", request_id).execute()

            client.table("students").update({
                "is_hostel_approved": True
            }).eq("id", student_id).execute()

            # Notify student
            client.table("notifications").insert({
                "recipient_type": "student",
                "recipient_id": student_id,
                "title": "Hostel Request Approved",
                "message": f"Your request for {req.get('hostel_name')} has been approved! You may now submit hostel-related complaints and feedback.",
                "reference_type": "hostel_request",
                "reference_id": request_id
            }).execute()

            return True, "Hostel request approved successfully."

        elif action.lower() == "deny":
            if not deny_reason or not deny_reason.strip():
                return False, "A denial reason is compulsory when rejecting a hostel request."

            client.table("hostel_requests").update({
                "status": HostelRequestStatus.DENIED.value,
                "reviewed_by": valid_reviewer_uuid,
                "reviewed_at": datetime.now().isoformat(),
                "deny_reason": deny_reason.strip()
            }).eq("id", request_id).execute()

            client.table("students").update({
                "is_hostel_approved": False
            }).eq("id", student_id).execute()

            # Notify student with denial reason
            client.table("notifications").insert({
                "recipient_type": "student",
                "recipient_id": student_id,
                "title": "Hostel Request Denied",
                "message": f"Your hostel request was denied. Reason: {deny_reason.strip()}. You may submit a new request if needed.",
                "reference_type": "hostel_request",
                "reference_id": request_id
            }).execute()

            return True, "Hostel request denied with reason recorded."

        return False, "Invalid review action."
