"""
services/notification_service.py: In-app Notification Center with badge counter and 90-day retention cleanup.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from database.supabase_client import get_supabase_client, get_trusted_backend_client
from models.user import UserRole


def _get_client():
    return get_trusted_backend_client() or get_supabase_client()


class NotificationService:
    @classmethod
    def get_user_notifications(
        cls,
        user_id: str,
        role: str,
        department_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves in-app notifications for a user or their role."""
        client = _get_client()
        query = client.table("notifications").select("*")

        import uuid
        is_valid_uuid = False
        if user_id:
            try:
                uuid.UUID(str(user_id))
                is_valid_uuid = True
            except (ValueError, AttributeError):
                is_valid_uuid = False

        if role == UserRole.STUDENT.value:
            if is_valid_uuid:
                query = query.eq("recipient_type", "student").eq("recipient_id", user_id)
            else:
                return []
        else:
            # Staff sees user-specific notifications OR role/dept notifications
            if is_valid_uuid:
                query = query.or_(
                    f"recipient_id.eq.{user_id},"
                    f"and(recipient_type.eq.role,recipient_role.eq.{role})"
                )
            else:
                query = query.eq("recipient_type", "role").eq("recipient_role", role)

        res = query.order("created_at", desc=True).limit(100).execute()
        notifications = res.data or []

        # Filter by department if applicable for staff role notifications
        if department_id and role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
            notifications = [
                n for n in notifications
                if n.get("department_id") is None or str(n.get("department_id")) == str(department_id)
            ]

        return notifications

    @classmethod
    def get_unread_count(
        cls,
        user_id: str,
        role: str,
        department_id: Optional[str] = None,
        force_refresh: bool = False
    ) -> int:
        """Returns the unread badge count with CacheService caching."""
        from services.cache_service import CacheService
        if not force_refresh:
            cached = CacheService.get_cached_unread_count(user_id, role, department_id)
            if cached is not None:
                return cached

        notes = cls.get_user_notifications(user_id, role, department_id)
        count = sum(1 for n in notes if not n.get("is_read"))
        CacheService.set_cached_unread_count(user_id, role, department_id, count, ttl_seconds=30)
        return count

    @classmethod
    def mark_as_read(cls, notification_id: str) -> bool:
        """Marks an individual notification as read."""
        from services.cache_service import CacheService
        client = _get_client()
        try:
            client.table("notifications").update({"is_read": True}).eq("id", notification_id).execute()
            return True
        except Exception:
            return False

    @classmethod
    def mark_all_as_read(
        cls,
        user_id: str,
        role: Optional[str] = None,
        department_id: Optional[str] = None
    ) -> bool:
        """Marks all notifications visible to this user or role as read."""
        client = _get_client()
        try:
            if role:
                notes = cls.get_user_notifications(user_id, role, department_id)
                unread_ids = [n["id"] for n in notes if not n.get("is_read") and n.get("id")]
                if unread_ids:
                    client.table("notifications").update({"is_read": True}).in_("id", unread_ids).execute()
                return True
            else:
                import uuid
                try:
                    uuid.UUID(str(user_id))
                    client.table("notifications").update({"is_read": True}).eq("recipient_id", user_id).execute()
                except (ValueError, AttributeError):
                    pass
                return True
        except Exception:
            return False

    @classmethod
    def clear_notification(cls, notification_id: str) -> bool:
        """Removes/clears an individual notification record from Supabase."""
        client = _get_client()
        try:
            client.table("notifications").delete().eq("id", notification_id).execute()
            return True
        except Exception:
            return False

    @classmethod
    def clear_all_read(
        cls,
        user_id: str,
        role: Optional[str] = None,
        department_id: Optional[str] = None
    ) -> bool:
        """Clears all read notifications for this user/role from Supabase."""
        client = _get_client()
        try:
            notes = cls.get_user_notifications(user_id, role or "", department_id)
            read_ids = [n["id"] for n in notes if n.get("is_read") and n.get("id")]
            if read_ids:
                client.table("notifications").delete().in_("id", read_ids).execute()
            return True
        except Exception:
            return False

    @classmethod
    def cleanup_90_day_retention(cls) -> int:
        """
        Cleans up notifications older than 90 days.
        Important: Complaint history is completely unaffected!
        """
        client = _get_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        try:
            res = client.table("notifications").delete().lt("created_at", cutoff).execute()
            return len(res.data or [])
        except Exception:
            return 0
