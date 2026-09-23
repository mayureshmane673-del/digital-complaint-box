"""
services/auth_service.py: Production authentication and account protection service.
Implements Student and Staff registration, login, 5-attempt lockout, password recovery, and security code verification.
"""

import logging
from typing import Tuple, Optional, Dict, Any
from datetime import datetime
from database.supabase_client import get_supabase_client, get_trusted_backend_client
from utils.security import (
    hash_password, verify_password,
    hash_security_answer, verify_security_answer
)
from utils.validators import validate_password_strength, validate_roll_number
from services.security_code_service import SecurityCodeService
from services.roll_number_service import RollNumberService
from models.user import UserRole

logger = logging.getLogger("complaint_box.auth")

MAX_FAILED_ATTEMPTS = 5

def sanitize_user_dict(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Strips password_hash and security_answer_hash from user dictionary."""
    if not user:
        return None
    safe = dict(user)
    safe.pop("password_hash", None)
    safe.pop("security_answer_hash", None)
    return safe


class AuthService:
    # -------------------------------------------------------------------------
    # STUDENT AUTHENTICATION
    # -------------------------------------------------------------------------
    @classmethod
    def register_student(
        cls,
        roll_number: str,
        full_name: str,
        department_id: str,
        year: str,
        password: str,
        security_question: str,
        security_answer: str,
        is_hostel: bool = False,
        hostel_details: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Registers a new student account:
        1. Validates roll number against the coordinator's roll number pool.
        2. Validates password strength policy.
        3. Hashes password and security answer.
        4. Inserts into students table and marks roll number as registered.
        5. If is_hostel is True, submits initial hostel request for Hostel Incharge review.
        """
        clean_roll = (roll_number or "").strip().upper()
        clean_name = (full_name or "").strip()
        if not clean_roll:
            return False, "Roll Number is required.", None
        if not clean_name:
            return False, "Full Name is required.", None
        if not department_id:
            return False, "Academic Department is required.", None

        # Format check
        is_valid_roll, roll_err = validate_roll_number(clean_roll)
        if not is_valid_roll:
            return False, roll_err, None

        # Pool eligibility check
        eligible, pool_err = RollNumberService.verify_roll_number_eligibility(clean_roll, department_id)
        if not eligible:
            return False, pool_err, None

        # Password strength check
        pw_ok, pw_err = validate_password_strength(password)
        if not pw_ok:
            return False, pw_err, None

        if not security_question or not (security_answer or "").strip():
            return False, "Security question and answer are required.", None

        client = get_trusted_backend_client()
        pw_hash = hash_password(password)
        ans_hash = hash_security_answer(security_answer)

        student_data = {
            "roll_number": clean_roll,
            "full_name": clean_name,
            "department_id": department_id,
            "year": year or "FE",
            "password_hash": pw_hash,
            "security_question": security_question.strip(),
            "security_answer_hash": ans_hash,
            "is_hostel": bool(is_hostel),
            "is_hostel_approved": False,
            "failed_login_attempts": 0,
            "is_locked": False
        }

        try:
            res = client.table("students").insert(student_data).execute()
            if not res.data:
                return False, "Unable to create student record. Please try again.", None
            new_student = res.data[0]

            # Mark roll number as registered in pool
            client.table("roll_number_pool").update({"is_registered": True}).eq("roll_number", clean_roll).execute()

            # If hostel student, create pending hostel request
            if is_hostel and hostel_details:
                try:
                    h_res = client.table("hostel_requests").insert({
                        "student_id": new_student["id"],
                        "hostel_name": hostel_details.get("hostel_name", "Campus Hostel"),
                        "block": hostel_details.get("block", "A"),
                        "room_number": hostel_details.get("room_number", "101"),
                        "status": "Pending"
                    }).execute()
                    h_id = h_res.data[0]["id"] if h_res.data else None

                    # Notify Hostel Incharge
                    try:
                        client.table("notifications").insert({
                            "recipient_type": "role",
                            "recipient_role": UserRole.HOSTEL_INCHARGE.value,
                            "title": "New Hostel Access Request",
                            "message": f"Student {clean_name} ({clean_roll}) registered and requested hostel access for {hostel_details.get('hostel_name', 'Hostel')} Block {hostel_details.get('block', '')}.",
                            "reference_type": "hostel_request",
                            "reference_id": h_id
                        }).execute()
                    except Exception:
                        pass

                    # Notify Principal
                    try:
                        client.table("notifications").insert({
                            "recipient_type": "role",
                            "recipient_role": UserRole.PRINCIPAL.value,
                            "title": "New Hostel Access Request",
                            "message": f"Student {clean_name} ({clean_roll}) registered and requested hostel access for {hostel_details.get('hostel_name', 'Hostel')} Block {hostel_details.get('block', '')}.",
                            "reference_type": "hostel_request",
                            "reference_id": h_id
                        }).execute()
                    except Exception:
                        pass

                except Exception as h_err:
                    logger.warning("Could not submit hostel request: %s", h_err)

            # Create welcome notification
            try:
                client.table("notifications").insert({
                    "recipient_type": "student",
                    "recipient_id": new_student["id"],
                    "title": "Welcome to Digital Complaint Box",
                    "message": f"Hello {clean_name}, your student account has been registered successfully."
                }).execute()
            except Exception as n_err:
                logger.warning("Could not create welcome notification: %s", n_err)

            return True, "Registration successful!", sanitize_user_dict(new_student)

        except Exception as e:
            logger.error("Student registration database error: %s", e)
            err_str = str(e).lower()
            if "duplicate" in err_str or "unique" in err_str or "23505" in err_str:
                return False, "This Roll Number is already registered.", None
            return False, "Unable to complete registration. Please verify your details and try again.", None

    @classmethod
    def login_student(cls, roll_number: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Authenticates student:
        - 5 failed attempts locks the account.
        - Successful login resets attempt counter.
        """
        clean_roll = (roll_number or "").strip().upper()
        if not clean_roll or not password:
            return False, "Invalid Roll Number or Password.", None

        client = get_trusted_backend_client()

        try:
            res = client.table("students").select("*").eq("roll_number", clean_roll).limit(1).execute()
        except Exception as ex:
            logger.error("Database error during student login: %s", ex)
            return False, "Invalid Roll Number or Password.", None

        if not res.data or len(res.data) == 0:
            return False, "Invalid Roll Number or Password.", None

        student = res.data[0]
        # Attach department from cache without network join
        from services.cache_service import CacheService
        dept = CacheService.get_department_by_id(student.get("department_id"))
        if dept:
            student["departments"] = {"code": dept.get("code"), "name": dept.get("name")}

        # Check account status
        if student.get("is_active") is False:
            return False, "This account has been deactivated. Please contact Administrator.", None

        # Check account lockout
        if student.get("is_locked"):
            return False, "Account is locked due to 5 failed login attempts. Please use Forgot Password to recover your account.", None

        # Verify password
        if not verify_password(password, student.get("password_hash", "")):
            failed = student.get("failed_login_attempts", 0) + 1
            update_fields: Dict[str, Any] = {"failed_login_attempts": failed}
            if failed >= MAX_FAILED_ATTEMPTS:
                update_fields["is_locked"] = True
                update_fields["locked_at"] = datetime.now().isoformat()
                try:
                    client.table("students").update(update_fields).eq("id", student["id"]).execute()
                except Exception as lk_err:
                    logger.error("Error locking student account: %s", lk_err)
                return False, "Account locked! You have exceeded 5 failed login attempts. Please reset via Forgot Password.", None
            else:
                try:
                    client.table("students").update(update_fields).eq("id", student["id"]).execute()
                except Exception as up_err:
                    logger.error("Error updating failed login attempts: %s", up_err)
                remaining = MAX_FAILED_ATTEMPTS - failed
                return False, f"Invalid password. {remaining} attempt(s) remaining before account lockout.", None

        # Reset failed attempts upon successful login only if previously > 0
        if student.get("failed_login_attempts", 0) > 0:
            try:
                client.table("students").update({"failed_login_attempts": 0}).eq("id", student["id"]).execute()
            except Exception as r_err:
                logger.warning("Could not reset failed attempts: %s", r_err)

        student["failed_login_attempts"] = 0
        student["is_locked"] = False

        # Check must_change_password flag or reset marker
        sq = str(student.get("security_question") or "")
        if student.get("must_change_password") or sq.startswith("RESET_REQUIRED:"):
            student["must_change_password"] = True

        return True, "Login successful.", sanitize_user_dict(student)

    @classmethod
    def get_student_security_question(cls, roll_number: str) -> Tuple[bool, str, Optional[str]]:
        """Retrieves the security question for a student without exposing password or answer."""
        clean_roll = (roll_number or "").strip().upper()
        if not clean_roll:
            return False, "Roll Number is required.", None
        client = get_trusted_backend_client()
        try:
            res = client.table("students").select("security_question").eq("roll_number", clean_roll).execute()
        except Exception as ex:
            logger.error("Error fetching student security question: %s", ex)
            return False, "Account not found.", None
        if not res.data or len(res.data) == 0:
            return False, "Account not found.", None
        return True, "", res.data[0].get("security_question")

    @classmethod
    def reset_student_password(
        cls,
        roll_number: str,
        security_answer: str,
        new_password: str
    ) -> Tuple[bool, str]:
        """
        Verifies the security answer, updates password, and unlocks locked account.
        """
        clean_roll = (roll_number or "").strip().upper()
        if not clean_roll:
            return False, "Roll Number is required."
        if not (security_answer or "").strip():
            return False, "Security answer is required."

        client = get_trusted_backend_client()
        try:
            res = client.table("students").select("id, security_answer_hash").eq("roll_number", clean_roll).execute()
        except Exception as ex:
            logger.error("Error during password reset lookup: %s", ex)
            return False, "Account not found."

        if not res.data or len(res.data) == 0:
            return False, "Account not found."

        student = res.data[0]
        if not verify_security_answer(security_answer, student.get("security_answer_hash", "")):
            return False, "Incorrect security answer."

        pw_ok, pw_err = validate_password_strength(new_password)
        if not pw_ok:
            return False, pw_err

        # Update password and unlock
        try:
            client.table("students").update({
                "password_hash": hash_password(new_password),
                "is_locked": False,
                "failed_login_attempts": 0,
                "locked_at": None
            }).eq("id", student["id"]).execute()
        except Exception as ex:
            logger.error("Error updating student password: %s", ex)
            return False, "Unable to reset password. Please try again."

        return True, "Password reset successfully. Your account is now unlocked."

    # -------------------------------------------------------------------------
    # STAFF AUTHENTICATION
    # -------------------------------------------------------------------------
    @classmethod
    def register_staff(
        cls,
        username: str,
        full_name: str,
        role: str,
        department_id: Optional[str],
        password: str,
        security_question: str,
        security_answer: str,
        security_code: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Registers staff user after validating role-appropriate security code and single active HOD rule.
        """
        clean_username = (username or "").strip()
        clean_name = (full_name or "").strip()

        if not clean_username:
            return False, "Username is required.", None
        if not clean_name:
            return False, "Full Name is required.", None
        if not role:
            return False, "Staff Role selection is required.", None

        # Enforce department requirement
        if role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
            if not department_id:
                return False, f"Academic department is required for {role} role.", None
        elif role == UserRole.GENERAL_HOD.value:
            gen_id = SecurityCodeService._get_special_dept_id("GEN")
            department_id = gen_id
        elif role in (UserRole.PRINCIPAL.value, UserRole.HOSTEL_INCHARGE.value, UserRole.LIBRARY_INCHARGE.value):
            department_id = None

        pw_ok, pw_err = validate_password_strength(password)
        if not pw_ok:
            return False, pw_err, None

        if not security_code or not security_code.strip():
            return False, "Role Security Code is required.", None

        if not security_question or not (security_answer or "").strip():
            return False, "Security question and answer are required.", None

        # Verify security code for the role and department
        code_valid = SecurityCodeService.verify_role_code(role, department_id, security_code)
        if not code_valid:
            return False, "Invalid security code for the selected role/department.", None

        client = get_trusted_backend_client()

        # Enforce single active Principal constraint
        if role == UserRole.PRINCIPAL.value:
            try:
                existing_p = client.table("staff_users").select("id").eq("role", UserRole.PRINCIPAL.value).eq("is_active", True).execute()
                if existing_p.data and len(existing_p.data) > 0:
                    return False, "An active Principal is already registered for the institution.", None
            except Exception as ex:
                logger.error("Error checking existing Principal: %s", ex)

        # Enforce single active HOD constraint
        if role == UserRole.HOD.value:
            try:
                existing_hod = client.table("staff_users").select("id").eq("role", UserRole.HOD.value).eq("department_id", department_id).eq("is_active", True).execute()
                if existing_hod.data and len(existing_hod.data) > 0:
                    return False, "An active HOD is already registered for this department.", None
            except Exception as ex:
                logger.error("Error checking existing HOD: %s", ex)

        # Enforce single active General Department HOD constraint
        if role == UserRole.GENERAL_HOD.value:
            gen_id = SecurityCodeService._get_special_dept_id("GEN")
            try:
                existing_gh = client.table("staff_users").select("id").eq("department_id", gen_id).eq("is_active", True).execute()
                if existing_gh.data and len(existing_gh.data) > 0:
                    return False, "An active General Department HOD is already registered.", None
            except Exception as ex:
                logger.error("Error checking existing General HOD: %s", ex)

        # Enforce single active Hostel Incharge constraint
        if role == UserRole.HOSTEL_INCHARGE.value:
            try:
                existing_hi = client.table("staff_users").select("id").eq("role", UserRole.HOSTEL_INCHARGE.value).eq("is_active", True).execute()
                if existing_hi.data and len(existing_hi.data) > 0:
                    return False, "An active Hostel Incharge is already registered.", None
            except Exception as ex:
                logger.error("Error checking existing Hostel Incharge: %s", ex)

        # Enforce single active Library Incharge constraint
        if role == UserRole.LIBRARY_INCHARGE.value:
            lib_id = SecurityCodeService._get_special_dept_id("LIB")
            try:
                existing_lib = client.table("staff_users").select("id").eq("department_id", lib_id).eq("is_active", True).execute()
                if not existing_lib.data:
                    existing_lib = client.table("staff_users").select("id").eq("role", "Library Incharge").eq("is_active", True).execute()
                if existing_lib.data and len(existing_lib.data) > 0:
                    return False, "An active Library Incharge is already registered.", None
            except Exception as ex:
                logger.error("Error checking existing Library Incharge: %s", ex)

        # Check existing username
        try:
            u_check = client.table("staff_users").select("id, is_active").eq("username", clean_username).execute()
            if u_check.data and len(u_check.data) > 0:
                active_users = [u for u in u_check.data if u.get("is_active", True)]
                if active_users:
                    return False, f"Username '{clean_username}' is already taken.", None
                else:
                    for old_u in u_check.data:
                        old_id = old_u["id"]
                        client.table("staff_users").update({
                            "username": f"{clean_username}#inactive_{old_id[:8]}"
                        }).eq("id", old_id).execute()
        except Exception as ex:
            logger.error("Error checking staff username: %s", ex)

        # Determine DB role and DB department for maximum schema compatibility
        db_role = role
        db_dept = department_id
        if role == UserRole.GENERAL_HOD.value:
            db_dept = SecurityCodeService._get_special_dept_id("GEN")
            db_role = "HOD"
        elif role == UserRole.LIBRARY_INCHARGE.value:
            db_dept = SecurityCodeService._get_special_dept_id("LIB")
            db_role = "HOD"

        staff_data = {
            "username": clean_username,
            "full_name": clean_name,
            "role": db_role,
            "department_id": db_dept,
            "password_hash": hash_password(password),
            "security_question": security_question.strip(),
            "security_answer_hash": hash_security_answer(security_answer),
            "failed_login_attempts": 0,
            "is_locked": False,
            "is_active": True
        }

        try:
            res = client.table("staff_users").insert(staff_data).execute()
            if not res.data:
                return False, "Unable to create staff account. Please try again.", None
            created = res.data[0]
            created["role"] = role
            return True, "Staff registered successfully!", sanitize_user_dict(created)
        except Exception as e:
            logger.error("Staff registration database error: %s", e)
            err_str = str(e).lower()
            if "duplicate" in err_str or "unique" in err_str or "23505" in err_str:
                return False, f"Username '{clean_username}' is already taken.", None
            return False, "Unable to create staff account. Please check the provided details and try again.", None

    @classmethod
    def login_staff(
        cls,
        role: str,
        username: str,
        password: str,
        security_code: str,
        department_id: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Staff login requires:
        1. Role selection (any of the 6 roles)
        2. Username + Password
        3. Valid role/department security code
        4. 5-attempt lockout enforcement
        """
        clean_user = (username or "").strip()
        if not clean_user or not password or not security_code:
            return False, "Invalid username, password, or security code.", None

        client = get_trusted_backend_client()

        # Fetch staff user
        try:
            gen_id = SecurityCodeService._get_special_dept_id("GEN")
            lib_id = SecurityCodeService._get_special_dept_id("LIB")

            if role == UserRole.GENERAL_HOD.value:
                # Query by username and General Department
                res = client.table("staff_users").select("*").eq("username", clean_user).execute()
                valid_rows = [
                    r for r in (res.data or [])
                    if r.get("role") == "General Department HOD" or (r.get("role") == "HOD" and str(r.get("department_id")) == str(gen_id))
                ]
                staff_matches = valid_rows
            elif role == UserRole.LIBRARY_INCHARGE.value:
                # Query by username and Library Department or Library Incharge role
                res = client.table("staff_users").select("*").eq("username", clean_user).execute()
                valid_rows = [
                    r for r in (res.data or [])
                    if r.get("role") == "Library Incharge" or (r.get("role") == "HOD" and str(r.get("department_id")) == str(lib_id))
                ]
                staff_matches = valid_rows
            else:
                res = client.table("staff_users").select("*").eq("username", clean_user).eq("role", role).execute()
                staff_matches = res.data or []

        except Exception as ex:
            logger.error("Database error during staff login: %s", ex)
            return False, "Invalid username, password, or security code.", None

        if not staff_matches:
            return False, "Invalid username, password, or security code.", None

        staff = staff_matches[0]
        # Attach department from cache without network join
        from services.cache_service import CacheService
        dept = CacheService.get_department_by_id(staff.get("department_id"))
        if dept:
            staff["departments"] = {"code": dept.get("code"), "name": dept.get("name")}

        # Check account status
        if not staff.get("is_active"):
            return False, "This account has been deactivated. Please contact Administrator.", None

        # Check account lockout
        if staff.get("is_locked"):
            return False, "Account is locked due to multiple failed login attempts. Please contact Administrator.", None

        # Verify department for HOD and Coordinator
        if role in (UserRole.HOD.value, UserRole.COORDINATOR.value) and department_id:
            if str(staff.get("department_id")) != str(department_id):
                return False, "Invalid username, password, or security code.", None

        # Verify role security code
        target_dept = department_id or staff.get("department_id")
        if not SecurityCodeService.verify_role_code(role, target_dept, security_code):
            return False, "Invalid username, password, or security code.", None

        # Verify password
        if not verify_password(password, staff.get("password_hash", "")):
            failed = staff.get("failed_login_attempts", 0) + 1
            fields: Dict[str, Any] = {"failed_login_attempts": failed}
            if failed >= MAX_FAILED_ATTEMPTS:
                fields["is_locked"] = True
                fields["locked_at"] = datetime.now().isoformat()
                try:
                    client.table("staff_users").update(fields).eq("id", staff["id"]).execute()
                except Exception as lk_err:
                    logger.error("Error locking staff account: %s", lk_err)
                return False, "Account is locked due to multiple failed login attempts. Please contact Administrator.", None
            else:
                try:
                    client.table("staff_users").update(fields).eq("id", staff["id"]).execute()
                except Exception as up_err:
                    logger.error("Error updating failed login attempts: %s", up_err)
                return False, "Invalid username, password, or security code.", None

        # Reset failed attempts upon successful login only if previously > 0
        if staff.get("failed_login_attempts", 0) > 0:
            try:
                client.table("staff_users").update({"failed_login_attempts": 0}).eq("id", staff["id"]).execute()
            except Exception as r_err:
                logger.warning("Could not reset failed attempts for staff: %s", r_err)

        staff["failed_login_attempts"] = 0
        staff["is_locked"] = False
        staff["role"] = role  # Present requested role
        return True, "Staff login successful.", sanitize_user_dict(staff)

    # -------------------------------------------------------------------------
    # PROFILE MANAGEMENT & PROTECTED FIELD ENFORCEMENT
    # -------------------------------------------------------------------------
    @classmethod
    def update_student_profile(
        cls,
        student_id: str,
        updates: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Updates student profile allowing ONLY non-protected fields:
        Allowed: full_name, phone, email, avatar_url.
        Strictly forbidden: department_id, roll_number, is_hostel_approved, is_locked,
        failed_login_attempts, locked_at, password_hash, security_answer_hash.
        """
        PROTECTED_FIELDS = {
            "department_id", "roll_number", "is_hostel_approved",
            "is_locked", "failed_login_attempts", "locked_at",
            "password_hash", "security_answer_hash"
        }
        for field in updates.keys():
            if field in PROTECTED_FIELDS:
                return False, f"Unauthorized: Students cannot directly modify protected field '{field}'."

        ALLOWED_FIELDS = {"full_name", "phone", "email", "avatar_url"}
        filtered = {k: v for k, v in updates.items() if k in ALLOWED_FIELDS}
        if not filtered:
            return False, "No valid profile fields provided for update."

        client = get_supabase_client()
        try:
            client.table("students").update(filtered).eq("id", student_id).execute()
            return True, "Profile updated successfully."
        except Exception as e:
            return False, f"Profile update failed: {str(e)}"

    @classmethod
    def get_staff_profile(cls, staff_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves staff profile safely without exposing password or security answer hashes."""
        client = get_supabase_client()
        res = client.table("staff_users").select(
            "id, username, full_name, role, department_id, is_locked, is_active, created_at, updated_at, departments(code, name)"
        ).eq("id", staff_id).execute()
        if res.data and len(res.data) > 0:
            return sanitize_user_dict(res.data[0])
        return None

    @classmethod
    def admin_reset_staff_password(
        cls,
        principal_id: str,
        target_staff_id: str,
        new_password: str
    ) -> Tuple[bool, str]:
        """
        Principal resets a staff member's password without receiving or reading credential hashes.
        """
        client = get_trusted_backend_client()
        # Verify principal identity from database state
        p_res = client.table("staff_users").select("role, is_active, is_locked").eq("id", principal_id).execute()
        if not p_res.data or p_res.data[0].get("role") != UserRole.PRINCIPAL.value:
            return False, "Unauthorized: Only the Principal can administratively reset staff passwords."

        pw_ok, pw_err = validate_password_strength(new_password)
        if not pw_ok:
            return False, pw_err

        client.table("staff_users").update({
            "password_hash": hash_password(new_password),
            "is_locked": False,
            "failed_login_attempts": 0,
            "locked_at": None
        }).eq("id", target_staff_id).execute()

        return True, "Staff password reset successfully. Account unlocked."
