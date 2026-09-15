"""
services/security_code_service.py: Strict role-based management of staff security codes.
Enforces all permission boundaries for Principal, HOD, Coordinator, and Hostel Incharge.
Never exposes raw code_hash to non-backend callers.
"""

from typing import Tuple, Optional, Dict, Any
from database.supabase_client import get_trusted_backend_client
from utils.security import hash_security_code, verify_security_code
from models.user import UserRole


class SecurityCodeService:
    @staticmethod
    def _get_special_dept_id(code: str) -> Optional[str]:
        from services.cache_service import CacheService
        return CacheService.get_special_dept_id(code)

    @classmethod
    def get_code_record(cls, role: str, department_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Internal trusted helper: Fetches the security code record including hash for verification.
        Uses CacheService for ultra-fast in-memory caching with trusted backend client.
        """
        from services.cache_service import CacheService
        return CacheService.get_security_code_record(role, department_id)

    @classmethod
    def get_code_metadata(cls, role: str, department_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Safe method for UI and inspection. Returns metadata only, NEVER exposes code_hash.
        """
        record = cls.get_code_record(role, department_id)
        if not record:
            return None
        safe = {
            "id": record.get("id"),
            "role": record.get("role"),
            "department_id": record.get("department_id"),
            "updated_by": record.get("updated_by"),
            "updated_at": record.get("updated_at")
        }
        return safe

    @classmethod
    def verify_role_code(cls, role: str, department_id: Optional[str], code: str) -> bool:
        """Verifies provided security code against the stored bcrypt hash."""
        record = cls.get_code_record(role, department_id)
        if not record or not record.get("code_hash"):
            return False
        return verify_security_code(code, record["code_hash"])

    @classmethod
    def update_security_code(
        cls,
        actor_role: str,
        actor_dept_id: Optional[str],
        target_role: str,
        target_dept_id: Optional[str],
        new_code: str,
        old_code: Optional[str] = None,
        actor_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Updates a security code while strictly enforcing role authority rules:
        - If actor_id is provided, verifies actor's actual role and department from staff_users.
        - Coordinator: CANNOT change any security code.
        - HOD: Can change own HOD code and own department's Coordinator code.
        - Hostel Incharge: Can change own code (requires old code).
        - Principal: Can reset any code unconditionally without old code.
        """
        client = get_trusted_backend_client()

        # Derive actor identity from trusted DB state if actor_id provided
        if actor_id:
            staff_res = client.table("staff_users").select("id, role, department_id, is_active, is_locked").eq("id", actor_id).execute()
            if not staff_res.data:
                return False, "Unauthorized: Staff record not found."
            actual_staff = staff_res.data[0]
            if actual_staff.get("is_locked") or not actual_staff.get("is_active"):
                return False, "Unauthorized: Staff account is locked or inactive."
            actor_role = actual_staff.get("role")
            actor_dept_id = actual_staff.get("department_id")

        if not new_code or len(new_code.strip()) < 6:
            return False, "Security code must be at least 6 characters."

        # Rule 1: Coordinator cannot change any code
        if actor_role == UserRole.COORDINATOR.value:
            return False, "Coordinators are not permitted to change security codes."

        # Rule 2: HOD authority boundaries
        if actor_role in (UserRole.HOD.value, UserRole.GENERAL_HOD.value):
            if target_role not in (UserRole.HOD.value, UserRole.GENERAL_HOD.value, UserRole.COORDINATOR.value):
                return False, "HOD can only manage HOD and Coordinator security codes."
            if str(actor_dept_id) != str(target_dept_id):
                return False, "HOD cannot modify security codes of other departments."
            # If changing own HOD code, old code verification is required
            if target_role in (UserRole.HOD.value, UserRole.GENERAL_HOD.value):
                if not old_code or not cls.verify_role_code(target_role, target_dept_id, old_code):
                    return False, "Current HOD security code is required and invalid."

        # Rule 3: Hostel Incharge authority boundaries
        elif actor_role == UserRole.HOSTEL_INCHARGE.value:
            if target_role != UserRole.HOSTEL_INCHARGE.value:
                return False, "Hostel Incharge can only update the Hostel security code."
            if not old_code or not cls.verify_role_code(target_role, None, old_code):
                return False, "Current Hostel security code is required and invalid."

        # Rule 3b: Library Incharge authority boundaries
        elif actor_role == UserRole.LIBRARY_INCHARGE.value:
            if target_role != UserRole.LIBRARY_INCHARGE.value:
                return False, "Library Incharge can only update the Library security code."
            if not old_code or not cls.verify_role_code(target_role, None, old_code):
                return False, "Current Library security code is required and invalid."

        # Rule 4: Principal has system-wide reset authority without needing old code
        elif actor_role == UserRole.PRINCIPAL.value:
            pass  # Authorized for all staff codes

        else:
            return False, f"Unauthorized role: {actor_role}"

        # Proceed to update database
        new_hash = hash_security_code(new_code)
        
        # Check if record exists
        existing = cls.get_code_record(target_role, target_dept_id)
        if existing:
            client.table("staff_security_codes").update({
                "code_hash": new_hash,
                "updated_by": f"{actor_role}:{actor_dept_id or 'all'}"
            }).eq("id", existing["id"]).execute()
        else:
            client.table("staff_security_codes").insert({
                "role": target_role,
                "department_id": target_dept_id,
                "code_hash": new_hash,
                "updated_by": f"{actor_role}:{actor_dept_id or 'all'}"
            }).execute()

        from services.cache_service import CacheService
        CacheService.invalidate_security_codes()

        return True, f"Security code for {target_role} successfully updated."
