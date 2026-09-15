"""
services/account_service.py: Role-scoped Account Management, Profile viewing/editing,
Self Password Change, Soft Deactivation, and Hierarchical Subordinate Management.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

from database.supabase_client import get_trusted_backend_client
from utils.security import hash_password, verify_password, sanitize_user_dict
from utils.validators import validate_password_strength
from models.user import UserRole

logger = logging.getLogger("complaint_box.account")


class AccountService:
    @classmethod
    def get_profile(cls, user_id: str, role: str) -> Optional[Dict[str, Any]]:
        client = get_trusted_backend_client()
        try:
            if role == UserRole.STUDENT.value:
                res = client.table("students").select("*, departments(code, name)").eq("id", user_id).execute()
            else:
                res = client.table("staff_users").select("*, departments(code, name)").eq("id", user_id).execute()

            if not res.data or len(res.data) == 0:
                return None

            user = res.data[0]
            dept_obj = user.get("departments") or {}
            dept_name = dept_obj.get("name") if isinstance(dept_obj, dict) else None
            dept_code = dept_obj.get("code") if isinstance(dept_obj, dict) else None

            safe_data = sanitize_user_dict(user)
            safe_data["department_name"] = dept_name
            safe_data["department_code"] = dept_code
            return safe_data
        except Exception as ex:
            logger.error("Error retrieving profile: %s", ex)
            return None

    @classmethod
    def update_profile(cls, user_id: str, role: str, full_name: str) -> Tuple[bool, str]:
        clean_name = (full_name or "").strip()
        if not clean_name or len(clean_name) < 2 or len(clean_name) > 100:
            return False, "Full Name must be between 2 and 100 characters."

        client = get_trusted_backend_client()
        try:
            table_name = "students" if role == UserRole.STUDENT.value else "staff_users"
            client.table(table_name).update({
                "full_name": clean_name
            }).eq("id", user_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "PROFILE_UPDATE",
                    "actor_id": user_id,
                    "actor_role": role,
                    "metadata": {"updated_field": "full_name"}
                }).execute()
            except Exception:
                pass

            return True, "Profile updated successfully."
        except Exception as ex:
            logger.error("Error updating profile: %s", ex)
            return False, "Unable to update profile. Please try again."

    @classmethod
    def change_own_password(
        cls,
        user_id: str,
        role: str,
        current_password: str,
        new_password: str
    ) -> Tuple[bool, str]:
        if not current_password:
            return False, "Current password is required."

        val_ok, val_err = validate_password_strength(new_password)
        if not val_ok:
            return False, val_err

        client = get_trusted_backend_client()
        table_name = "students" if role == UserRole.STUDENT.value else "staff_users"

        try:
            res = client.table(table_name).select("id, password_hash").eq("id", user_id).execute()
            if not res.data or len(res.data) == 0:
                return False, "Account not found."

            user = res.data[0]
            if not verify_password(current_password, user.get("password_hash", "")):
                return False, "Incorrect current password."

            new_hash = hash_password(new_password)
            client.table(table_name).update({
                "password_hash": new_hash
            }).eq("id", user_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "ACCOUNT_PASSWORD_CHANGE",
                    "actor_id": user_id,
                    "actor_role": role,
                    "metadata": {"action": "self_password_change"}
                }).execute()
            except Exception:
                pass

            return True, "Password changed successfully."
        except Exception as ex:
            logger.error("Error changing password: %s", ex)
            return False, "Unable to change password. Please try again."

    @classmethod
    def deactivate_student_account(cls, student_id: str) -> Tuple[bool, str]:
        client = get_trusted_backend_client()
        try:
            res = client.table("students").select("id, roll_number").eq("id", student_id).execute()
            if not res.data or len(res.data) == 0:
                return False, "Student account not found."

            student = res.data[0]
            client.table("students").update({
                "is_locked": True,
                "locked_at": datetime.now().isoformat()
            }).eq("id", student_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "STUDENT_ACCOUNT_DEACTIVATE",
                    "actor_id": student_id,
                    "actor_role": UserRole.STUDENT.value,
                    "metadata": {"roll_number": student.get("roll_number"), "reason": "Self account deletion"}
                }).execute()
            except Exception:
                pass

            return True, "Your account has been deactivated successfully."
        except Exception as ex:
            logger.error("Error deactivating student account: %s", ex)
            return False, "Unable to deactivate account. Please try again."

    @classmethod
    def deactivate_staff_account(
        cls,
        staff_id: str,
        actor_id: str,
        actor_role: str,
        reason: Optional[str] = None
    ) -> Tuple[bool, str]:
        client = get_trusted_backend_client()
        try:
            target_res = client.table("staff_users").select("*").eq("id", staff_id).execute()
            if not target_res.data or len(target_res.data) == 0:
                return False, "Staff account not found."

            target = target_res.data[0]
            target_role = target.get("role")
            target_dept = target.get("department_id")

            if staff_id != actor_id:
                if actor_role == UserRole.HOD.value:
                    actor_res = client.table("staff_users").select("department_id, is_active").eq("id", actor_id).execute()
                    if not actor_res.data or not actor_res.data[0].get("is_active"):
                        return False, "Unauthorized or inactive HOD account."
                    hod_dept = actor_res.data[0].get("department_id")
                    if target_role != UserRole.COORDINATOR.value or str(target_dept) != str(hod_dept):
                        return False, "HOD can only manage Coordinators in their own department."
                elif actor_role == UserRole.PRINCIPAL.value:
                    if target_role not in (UserRole.HOD.value, UserRole.HOSTEL_INCHARGE.value, UserRole.COORDINATOR.value):
                        return False, "Principal cannot manage this account type."
                else:
                    return False, "Unauthorized to deactivate this staff account."

            if target_role == UserRole.HOD.value:
                active_hods = client.table("staff_users").select("id").eq("role", UserRole.HOD.value).eq("department_id", target_dept).eq("is_active", True).execute()
                if len(active_hods.data or []) <= 1:
                    return False, "Cannot deactivate account. Each academic department must have an active HOD. Please assign another HOD first."

            elif target_role == UserRole.PRINCIPAL.value:
                active_principals = client.table("staff_users").select("id").eq("role", UserRole.PRINCIPAL.value).eq("is_active", True).execute()
                if len(active_principals.data or []) <= 1:
                    return False, "Cannot deactivate account. Campus must have at least one active Principal."

            elif target_role == UserRole.HOSTEL_INCHARGE.value:
                active_hi = client.table("staff_users").select("id").eq("role", UserRole.HOSTEL_INCHARGE.value).eq("is_active", True).execute()
                if len(active_hi.data or []) <= 1:
                    return False, "Cannot deactivate account. Campus must have an active Hostel Incharge."

            client.table("staff_users").update({
                "is_active": False
            }).eq("id", staff_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "ACCOUNT_DEACTIVATE",
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "metadata": {
                        "target_id": staff_id,
                        "target_username": target.get("username"),
                        "target_role": target_role,
                        "reason": reason or "Account deactivation"
                    }
                }).execute()
            except Exception:
                pass

            return True, "Account deactivated successfully."
        except Exception as ex:
            logger.error("Error deactivating staff account: %s", ex)
            return False, "Unable to deactivate account. Please try again."

    @classmethod
    def reactivate_staff_account(
        cls,
        staff_id: str,
        actor_id: str,
        actor_role: str
    ) -> Tuple[bool, str]:
        client = get_trusted_backend_client()
        try:
            target_res = client.table("staff_users").select("*").eq("id", staff_id).execute()
            if not target_res.data or len(target_res.data) == 0:
                return False, "Staff account not found."

            target = target_res.data[0]
            target_role = target.get("role")
            target_dept = target.get("department_id")

            if actor_role == UserRole.HOD.value:
                actor_res = client.table("staff_users").select("department_id, is_active").eq("id", actor_id).execute()
                if not actor_res.data or not actor_res.data[0].get("is_active"):
                    return False, "Unauthorized or inactive HOD account."
                hod_dept = actor_res.data[0].get("department_id")
                if target_role != UserRole.COORDINATOR.value or str(target_dept) != str(hod_dept):
                    return False, "HOD can only manage Coordinators in their own department."
            elif actor_role == UserRole.PRINCIPAL.value:
                pass
            else:
                return False, "Unauthorized to reactivate this staff account."

            if target_role == UserRole.HOD.value:
                existing_active = client.table("staff_users").select("id").eq("role", UserRole.HOD.value).eq("department_id", target_dept).eq("is_active", True).execute()
                if existing_active.data and len(existing_active.data) > 0:
                    return False, "Cannot reactivate. An active HOD is already assigned to this department."

            if target_role == UserRole.HOSTEL_INCHARGE.value:
                existing_active = client.table("staff_users").select("id").eq("role", UserRole.HOSTEL_INCHARGE.value).eq("is_active", True).execute()
                if existing_active.data and len(existing_active.data) > 0:
                    return False, "Cannot reactivate. An active Hostel Incharge is already assigned."

            client.table("staff_users").update({
                "is_active": True,
                "is_locked": False,
                "failed_login_attempts": 0
            }).eq("id", staff_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "ACCOUNT_REACTIVATE",
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "metadata": {
                        "target_id": staff_id,
                        "target_username": target.get("username"),
                        "target_role": target_role
                    }
                }).execute()
            except Exception:
                pass

            return True, "Account reactivated successfully."
        except Exception as ex:
            logger.error("Error reactivating staff account: %s", ex)
            return False, "Unable to reactivate account. Please try again."

    @classmethod
    def list_department_coordinators(cls, hod_id: str) -> List[Dict[str, Any]]:
        client = get_trusted_backend_client()
        try:
            hod_res = client.table("staff_users").select("id, role, department_id, is_active").eq("id", hod_id).execute()
            if not hod_res.data or len(hod_res.data) == 0:
                return []

            hod = hod_res.data[0]
            if hod.get("role") != UserRole.HOD.value or not hod.get("is_active"):
                return []

            dept_id = hod.get("department_id")
            if not dept_id:
                return []

            res = client.table("staff_users").select(
                "id, username, full_name, role, department_id, is_active, is_locked, created_at, updated_at, departments(code, name)"
            ).eq("role", UserRole.COORDINATOR.value).eq("department_id", dept_id).order("created_at", desc=False).execute()

            return res.data or []
        except Exception as ex:
            logger.error("Error listing department coordinators: %s", ex)
            return []

    @classmethod
    def reset_coordinator_password_by_hod(
        cls,
        hod_id: str,
        coordinator_id: str,
        new_password: str
    ) -> Tuple[bool, str]:
        pw_ok, pw_err = validate_password_strength(new_password)
        if not pw_ok:
            return False, pw_err

        client = get_trusted_backend_client()
        try:
            hod_res = client.table("staff_users").select("id, role, department_id, is_active").eq("id", hod_id).execute()
            if not hod_res.data or len(hod_res.data) == 0:
                return False, "Unauthorized HOD account."
            hod = hod_res.data[0]
            if hod.get("role") != UserRole.HOD.value or not hod.get("is_active"):
                return False, "Unauthorized or inactive HOD account."

            coord_res = client.table("staff_users").select("id, role, department_id, username").eq("id", coordinator_id).execute()
            if not coord_res.data or len(coord_res.data) == 0:
                return False, "Coordinator account not found."
            coord = coord_res.data[0]
            if coord.get("role") != UserRole.COORDINATOR.value:
                return False, "HOD can only reset Coordinator passwords."

            if str(coord.get("department_id")) != str(hod.get("department_id")):
                return False, "HOD can only reset passwords for Coordinators in their own department."

            new_hash = hash_password(new_password)
            client.table("staff_users").update({
                "password_hash": new_hash,
                "is_locked": False,
                "failed_login_attempts": 0,
                "locked_at": None
            }).eq("id", coordinator_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "ADMIN_PASSWORD_RESET",
                    "actor_id": hod_id,
                    "actor_role": UserRole.HOD.value,
                    "metadata": {
                        "target_id": coordinator_id,
                        "target_username": coord.get("username"),
                        "target_role": UserRole.COORDINATOR.value
                    }
                }).execute()
            except Exception:
                pass

            return True, f"Password for Coordinator '{coord.get('username')}' has been reset successfully."
        except Exception as ex:
            logger.error("Error resetting coordinator password: %s", ex)
            return False, "Unable to reset coordinator password. Please try again."

    @classmethod
    def list_hods_for_principal(cls, principal_id: str) -> List[Dict[str, Any]]:
        client = get_trusted_backend_client()
        try:
            p_res = client.table("staff_users").select("id, role, is_active").eq("id", principal_id).execute()
            if not p_res.data or len(p_res.data) == 0:
                return []
            principal = p_res.data[0]
            if principal.get("role") != UserRole.PRINCIPAL.value or not principal.get("is_active"):
                return []

            res = client.table("staff_users").select(
                "id, username, full_name, role, department_id, is_active, is_locked, created_at, updated_at, departments(code, name)"
            ).eq("role", UserRole.HOD.value).order("created_at", desc=False).execute()

            return res.data or []
        except Exception as ex:
            logger.error("Error listing HODs for principal: %s", ex)
            return []

    @classmethod
    def reset_hod_password_by_principal(
        cls,
        principal_id: str,
        hod_id: str,
        new_password: str
    ) -> Tuple[bool, str]:
        pw_ok, pw_err = validate_password_strength(new_password)
        if not pw_ok:
            return False, pw_err

        client = get_trusted_backend_client()
        try:
            p_res = client.table("staff_users").select("id, role, is_active").eq("id", principal_id).execute()
            if not p_res.data or len(p_res.data) == 0:
                return False, "Unauthorized Principal account."
            principal = p_res.data[0]
            if principal.get("role") != UserRole.PRINCIPAL.value or not principal.get("is_active"):
                return False, "Unauthorized or inactive Principal account."

            hod_res = client.table("staff_users").select("id, role, username").eq("id", hod_id).execute()
            if not hod_res.data or len(hod_res.data) == 0:
                return False, "HOD account not found."
            hod = hod_res.data[0]
            if hod.get("role") != UserRole.HOD.value:
                return False, "Target account is not an HOD."

            new_hash = hash_password(new_password)
            client.table("staff_users").update({
                "password_hash": new_hash,
                "is_locked": False,
                "failed_login_attempts": 0,
                "locked_at": None
            }).eq("id", hod_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "ADMIN_PASSWORD_RESET",
                    "actor_id": principal_id,
                    "actor_role": UserRole.PRINCIPAL.value,
                    "metadata": {
                        "target_id": hod_id,
                        "target_username": hod.get("username"),
                        "target_role": UserRole.HOD.value
                    }
                }).execute()
            except Exception:
                pass

            return True, f"Password for HOD '{hod.get('username')}' has been reset successfully."
        except Exception as ex:
            logger.error("Error resetting HOD password: %s", ex)
            return False, "Unable to reset HOD password. Please try again."

    @classmethod
    def get_hostel_incharge_for_principal(cls, principal_id: str) -> Optional[Dict[str, Any]]:
        client = get_trusted_backend_client()
        try:
            p_res = client.table("staff_users").select("id, role, is_active").eq("id", principal_id).execute()
            if not p_res.data or len(p_res.data) == 0:
                return None
            principal = p_res.data[0]
            if principal.get("role") != UserRole.PRINCIPAL.value or not principal.get("is_active"):
                return None

            res = client.table("staff_users").select(
                "id, username, full_name, role, is_active, is_locked, created_at, updated_at"
            ).eq("role", UserRole.HOSTEL_INCHARGE.value).execute()

            if not res.data or len(res.data) == 0:
                return None

            return res.data[0]
        except Exception as ex:
            logger.error("Error fetching Hostel Incharge for principal: %s", ex)
            return None

    @classmethod
    def reset_hostel_incharge_password_by_principal(
        cls,
        principal_id: str,
        incharge_id: str,
        new_password: str
    ) -> Tuple[bool, str]:
        pw_ok, pw_err = validate_password_strength(new_password)
        if not pw_ok:
            return False, pw_err

        client = get_trusted_backend_client()
        try:
            p_res = client.table("staff_users").select("id, role, is_active").eq("id", principal_id).execute()
            if not p_res.data or len(p_res.data) == 0:
                return False, "Unauthorized Principal account."
            principal = p_res.data[0]
            if principal.get("role") != UserRole.PRINCIPAL.value or not principal.get("is_active"):
                return False, "Unauthorized or inactive Principal account."

            hi_res = client.table("staff_users").select("id, role, username").eq("id", incharge_id).execute()
            if not hi_res.data or len(hi_res.data) == 0:
                return False, "Hostel Incharge account not found."
            hi = hi_res.data[0]
            if hi.get("role") != UserRole.HOSTEL_INCHARGE.value:
                return False, "Target account is not a Hostel Incharge."

            new_hash = hash_password(new_password)
            client.table("staff_users").update({
                "password_hash": new_hash,
                "is_locked": False,
                "failed_login_attempts": 0,
                "locked_at": None
            }).eq("id", incharge_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "ADMIN_PASSWORD_RESET",
                    "actor_id": principal_id,
                    "actor_role": UserRole.PRINCIPAL.value,
                    "metadata": {
                        "target_id": incharge_id,
                        "target_username": hi.get("username"),
                        "target_role": UserRole.HOSTEL_INCHARGE.value
                    }
                }).execute()
            except Exception:
                pass

            return True, f"Password for Hostel Incharge '{hi.get('username')}' has been reset successfully."
        except Exception as ex:
            logger.error("Error resetting Hostel Incharge password: %s", ex)
            return False, "Unable to reset Hostel Incharge password. Please try again."

    # -------------------------------------------------------------------------
    # COORDINATOR: STUDENT PASSWORD RESET & MANAGEMENT
    # -------------------------------------------------------------------------
    @classmethod
    def list_department_students_for_coordinator(cls, coordinator_id: str) -> List[Dict[str, Any]]:
        """
        Lists students belonging STRICTLY to the coordinator's academic department,
        excluding other departments and excluding First Year general students.
        """
        client = get_trusted_backend_client()
        try:
            c_res = client.table("staff_users").select("id, role, department_id, is_active").eq("id", coordinator_id).execute()
            if not c_res.data or len(c_res.data) == 0:
                return []
            coord = c_res.data[0]
            if coord.get("role") != UserRole.COORDINATOR.value or not coord.get("is_active"):
                return []
            dept_id = coord.get("department_id")
            if not dept_id:
                return []

            res = client.table("students").select(
                "id, roll_number, full_name, department_id, year, is_hostel, is_locked, created_at, departments(code, name)"
            ).eq("department_id", dept_id).order("roll_number", desc=False).execute()

            students = res.data or []
            # Exclude First Year students (who belong to General Department)
            valid_students = [
                s for s in students
                if str(s.get("year", "")).strip().upper() not in ("FE", "1", "1ST", "FIRST YEAR", "FIRST")
            ]
            return valid_students
        except Exception as ex:
            logger.error("Error listing department students for coordinator: %s", ex)
            return []

    @classmethod
    def reset_student_password_by_coordinator(
        cls,
        coordinator_id: str,
        student_id: str,
        new_password: str
    ) -> Tuple[bool, str]:
        """
        Allows a Coordinator to reset password for a student belonging strictly to their
        own academic department (excluding other departments and first-year general students).
        Sets temporary password, unlocks account, forces password change on next login,
        and logs to audit trail without storing the password.
        """
        pw_ok, pw_err = validate_password_strength(new_password)
        if not pw_ok:
            return False, pw_err

        client = get_trusted_backend_client()
        try:
            # 1. Verify Coordinator
            c_res = client.table("staff_users").select("id, role, department_id, is_active").eq("id", coordinator_id).execute()
            if not c_res.data or len(c_res.data) == 0:
                return False, "Unauthorized Coordinator account."
            coord = c_res.data[0]
            if coord.get("role") != UserRole.COORDINATOR.value or not coord.get("is_active"):
                return False, "Unauthorized or inactive Coordinator account."
            dept_id = coord.get("department_id")
            if not dept_id:
                return False, "Coordinator does not have an assigned academic department."

            # 2. Verify Student
            s_res = client.table("students").select("id, roll_number, department_id, year, security_question").eq("id", student_id).execute()
            if not s_res.data or len(s_res.data) == 0:
                return False, "Student account not found."
            student = s_res.data[0]

            # Enforce department boundary
            if str(student.get("department_id")) != str(dept_id):
                return False, "Unauthorized: Coordinator can only reset passwords for students in their own academic department."

            # Enforce First Year boundary
            st_year = str(student.get("year", "")).strip().upper()
            if st_year in ("FE", "1", "1ST", "FIRST YEAR", "FIRST"):
                return False, "Unauthorized: First Year student accounts are managed by the General Department, not Academic Coordinators."

            # 3. Hash password and update student
            new_hash = hash_password(new_password)
            update_payload: Dict[str, Any] = {
                "password_hash": new_hash,
                "is_locked": False,
                "failed_login_attempts": 0,
                "locked_at": None
            }

            # Try updating must_change_password column; fallback to security_question prefix if not in schema
            sq = student.get("security_question", "")
            if not sq.startswith("RESET_REQUIRED:"):
                update_payload["security_question"] = f"RESET_REQUIRED:{sq}"

            try:
                client.table("students").update(dict(update_payload, must_change_password=True)).eq("id", student_id).execute()
            except Exception:
                client.table("students").update(update_payload).eq("id", student_id).execute()

            # 4. Audit Log without storing plaintext password
            try:
                client.table("audit_logs").insert({
                    "event_type": "COORDINATOR_STUDENT_PASSWORD_RESET",
                    "actor_id": coordinator_id,
                    "actor_role": UserRole.COORDINATOR.value,
                    "metadata": {
                        "target_student_id": student_id,
                        "roll_number": student.get("roll_number"),
                        "action": "password_reset_and_unlock"
                    }
                }).execute()
            except Exception:
                pass

            return True, f"Password for student ({student.get('roll_number')}) reset successfully. Account unlocked."
        except Exception as ex:
            logger.error("Error resetting student password by coordinator: %s", ex)
            return False, "Unable to reset student password. Please try again."

    # -------------------------------------------------------------------------
    # PRINCIPAL: LIBRARY INCHARGE & GENERAL HOD MANAGEMENT
    # -------------------------------------------------------------------------
    @classmethod
    def get_library_incharge_for_principal(cls, principal_id: str) -> Optional[Dict[str, Any]]:
        client = get_trusted_backend_client()
        try:
            p_res = client.table("staff_users").select("id, role, is_active").eq("id", principal_id).execute()
            if not p_res.data or len(p_res.data) == 0:
                return None
            principal = p_res.data[0]
            if principal.get("role") != UserRole.PRINCIPAL.value or not principal.get("is_active"):
                return None

            from services.security_code_service import SecurityCodeService
            lib_id = SecurityCodeService._get_special_dept_id("LIB")

            res = client.table("staff_users").select(
                "id, username, full_name, role, is_active, is_locked, created_at, updated_at, department_id"
            ).execute()

            matches = [
                r for r in (res.data or [])
                if r.get("role") == "Library Incharge" or (r.get("role") == "HOD" and str(r.get("department_id")) == str(lib_id))
            ]
            return matches[0] if matches else None
        except Exception as ex:
            logger.error("Error fetching Library Incharge for principal: %s", ex)
            return None

    @classmethod
    def reset_library_incharge_password_by_principal(
        cls,
        principal_id: str,
        incharge_id: str,
        new_password: str
    ) -> Tuple[bool, str]:
        pw_ok, pw_err = validate_password_strength(new_password)
        if not pw_ok:
            return False, pw_err

        client = get_trusted_backend_client()
        try:
            p_res = client.table("staff_users").select("id, role, is_active").eq("id", principal_id).execute()
            if not p_res.data or len(p_res.data) == 0:
                return False, "Unauthorized Principal account."
            principal = p_res.data[0]
            if principal.get("role") != UserRole.PRINCIPAL.value or not principal.get("is_active"):
                return False, "Unauthorized or inactive Principal account."

            new_hash = hash_password(new_password)
            client.table("staff_users").update({
                "password_hash": new_hash,
                "is_locked": False,
                "failed_login_attempts": 0,
                "locked_at": None
            }).eq("id", incharge_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "ADMIN_PASSWORD_RESET",
                    "actor_id": principal_id,
                    "actor_role": UserRole.PRINCIPAL.value,
                    "metadata": {
                        "target_id": incharge_id,
                        "target_role": "Library Incharge"
                    }
                }).execute()
            except Exception:
                pass

            return True, "Password for Library Incharge reset successfully."
        except Exception as ex:
            logger.error("Error resetting Library Incharge password: %s", ex)
            return False, "Unable to reset Library Incharge password."

    @classmethod
    def get_general_hod_for_principal(cls, principal_id: str) -> Optional[Dict[str, Any]]:
        client = get_trusted_backend_client()
        try:
            p_res = client.table("staff_users").select("id, role, is_active").eq("id", principal_id).execute()
            if not p_res.data or len(p_res.data) == 0:
                return None
            principal = p_res.data[0]
            if principal.get("role") != UserRole.PRINCIPAL.value or not principal.get("is_active"):
                return None

            from services.security_code_service import SecurityCodeService
            gen_id = SecurityCodeService._get_special_dept_id("GEN")

            res = client.table("staff_users").select(
                "id, username, full_name, role, is_active, is_locked, created_at, updated_at, department_id"
            ).execute()

            matches = [
                r for r in (res.data or [])
                if r.get("role") == "General Department HOD" or (r.get("role") == "HOD" and str(r.get("department_id")) == str(gen_id))
            ]
            return matches[0] if matches else None
        except Exception as ex:
            logger.error("Error fetching General Department HOD for principal: %s", ex)
            return None

    @classmethod
    def reset_general_hod_password_by_principal(
        cls,
        principal_id: str,
        hod_id: str,
        new_password: str
    ) -> Tuple[bool, str]:
        pw_ok, pw_err = validate_password_strength(new_password)
        if not pw_ok:
            return False, pw_err

        client = get_trusted_backend_client()
        try:
            p_res = client.table("staff_users").select("id, role, is_active").eq("id", principal_id).execute()
            if not p_res.data or len(p_res.data) == 0:
                return False, "Unauthorized Principal account."
            principal = p_res.data[0]
            if principal.get("role") != UserRole.PRINCIPAL.value or not principal.get("is_active"):
                return False, "Unauthorized or inactive Principal account."

            new_hash = hash_password(new_password)
            client.table("staff_users").update({
                "password_hash": new_hash,
                "is_locked": False,
                "failed_login_attempts": 0,
                "locked_at": None
            }).eq("id", hod_id).execute()

            try:
                client.table("audit_logs").insert({
                    "event_type": "ADMIN_PASSWORD_RESET",
                    "actor_id": principal_id,
                    "actor_role": UserRole.PRINCIPAL.value,
                    "metadata": {
                        "target_id": hod_id,
                        "target_role": "General Department HOD"
                    }
                }).execute()
            except Exception:
                pass

            return True, "Password for General Department HOD reset successfully."
        except Exception as ex:
            logger.error("Error resetting General Department HOD password: %s", ex)
            return False, "Unable to reset General Department HOD password."
