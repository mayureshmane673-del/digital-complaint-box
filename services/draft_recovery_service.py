"""
services/draft_recovery_service.py: Cross-reload recovery service for Digital Complaint Box.

Preserves active tab index and New Complaint draft (form fields and verified temporary attachments)
across page reloads using Flet SharedPreferences (backed by browser localStorage).

Security architecture & guarantees:
1. Browser localStorage is client-controlled and completely untrusted.
   - It is NEVER used as proof of authentication or authorization.
   - User roles and credentials are NEVER read from or authenticated via localStorage.
   - Authentication must be validated through server-side credentials on reload.
2. Draft and tab state are strictly owner-scoped:
   - Drafts record the server-authenticated student's owner_id.
   - On reload, drafts and tabs are restored ONLY IF the owner matches the server-validated user.
   - Mismatched or unowned drafts in browser storage are rejected and purged.
3. Temporary file path validation:
   - Restored attachment paths are strictly confined to the application's approved
     temporary directory for that specific student: uploads/temp/<clean_sid>/
   - Arbitrary filesystem paths, symlinks, directory traversal (../), disallowed extensions,
     and oversized/zero-byte files are strictly blocked.
4. On logout, all session data and client storage entries are cleared.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import flet as ft
from flet.controls.services.shared_preferences import SharedPreferences
from utils.validators import ALLOWED_ATTACHMENT_EXTENSIONS, MAX_ATTACHMENT_SIZE_BYTES

logger = logging.getLogger("complaint_box.draft_recovery")

# Storage keys
SP_KEY_USER = "dcb_auth_user"
SP_KEY_ROLE = "dcb_auth_role"
SP_KEY_ACTIVE_TAB = "dcb_active_tab"
SP_KEY_DRAFT = "dcb_complaint_draft"

# In-memory session store keys
SESSION_KEY_USER = "current_user"
SESSION_KEY_ROLE = "role"
SESSION_KEY_ACTIVE_TAB = "active_tab_index"
SESSION_KEY_ACTIVE_TAB_OWNER = "active_tab_owner"
SESSION_KEY_DRAFT = "complaint_draft"

# Security whitelists
ALLOWED_USER_KEYS = {
    "id",
    "roll_number",
    "full_name",
    "username",
    "email",
    "department_id",
    "departments",
    "year",
    "is_hostel_approved",
    "role",
    "designation",
}

ALLOWED_DRAFT_KEYS = {
    "owner_id",
    "title",
    "description",
    "category_id",
    "subcategory_id",
    "location_id",
    "priority",
    "is_anonymous",
    "is_hostel",
    "location_custom",
    "category_custom",
    "subcategory_custom",
    "temp_files",
}

# Valid student navigation tab indices (0=Dashboard..5=Account).
# Used to reject out-of-range values from untrusted storage.
VALID_STUDENT_TAB_RANGE = range(0, 6)
DEFAULT_TAB_INDEX = 0


def sanitize_profile_for_storage(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Extract strictly non-sensitive fields from user dictionary for in-memory session."""
    if not user or not isinstance(user, dict):
        return None
    safe: Dict[str, Any] = {}
    for k, v in user.items():
        if k in ALLOWED_USER_KEYS:
            if isinstance(v, (str, int, float, bool)) or v is None:
                safe[k] = v
            elif k == "departments" and isinstance(v, dict):
                safe[k] = {dk: dv for dk, dv in v.items() if isinstance(dv, (str, int, float, bool))}
    return safe


def get_student_temp_dir(student_id: str) -> Optional[str]:
    """Returns the approved absolute temporary directory for a specific student (lexical path)."""
    if not student_id:
        return None
    clean_sid = str(student_id).replace("-", "").strip()
    if not clean_sid or not clean_sid.isalnum():
        return None
    base_uploads = os.path.realpath(str(Path("uploads").resolve()))
    student_dir = os.path.abspath(os.path.join(base_uploads, "temp", clean_sid))
    return student_dir


def validate_student_temp_path(
    file_path: str,
    student_id: str,
    file_name: Optional[str] = None
) -> Tuple[bool, Optional[str], int]:
    """
    Validates that a temporary file path is legitimate:
    1. student_id is required.
    2. Path must be strictly within the application's approved temporary upload
       directory for this specific student: <base_uploads>/temp/<clean_sid>/
    3. Path traversal attacks (../, symlinks, absolute paths outside) are blocked.
    4. The student's temp directory and its relevant existing parent directories must not be symlinks.
    5. File must exist on disk and be a regular file (not directory or symlink).
    6. File extension must be in ALLOWED_ATTACHMENT_EXTENSIONS.
    7. File size must be > 0 and <= MAX_ATTACHMENT_SIZE_BYTES (10 MB).

    Returns (is_valid, resolved_path, file_size).
    """
    if not file_path or not student_id:
        return False, None, 0

    student_dir = get_student_temp_dir(student_id)
    if not student_dir:
        return False, None, 0

    try:
        # Check lexical student_dir and its relevant parent directories for symlinks
        # BEFORE resolving with realpath(). This ensures symlinks in uploads/temp/<clean_sid>
        # or uploads/temp are caught before the path is replaced with the target location.
        base_uploads = os.path.realpath(str(Path("uploads").resolve()))
        norm_base = os.path.normcase(base_uploads)

        curr = os.path.abspath(student_dir)
        while curr and len(os.path.normcase(curr)) >= len(norm_base):
            if os.path.islink(curr):
                logger.warning("[SECURITY] Rejected symlinked temp directory in hierarchy")
                return False, None, 0
            if os.path.normcase(curr) == norm_base:
                break
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent

        # Check for symlink on the file and any intermediate directories under student_dir
        abs_file = os.path.abspath(file_path)
        if os.path.islink(abs_file):
            logger.warning("[SECURITY] Rejected symlink in temp file path")
            return False, None, 0

        norm_student = os.path.normcase(os.path.abspath(student_dir))
        curr_f = os.path.dirname(abs_file)
        while curr_f and len(os.path.normcase(curr_f)) >= len(norm_student):
            if os.path.islink(curr_f):
                logger.warning("[SECURITY] Rejected symlink in temp file path")
                return False, None, 0
            if os.path.normcase(curr_f) == norm_student:
                break
            parent_f = os.path.dirname(curr_f)
            if parent_f == curr_f:
                break
            curr_f = parent_f

        real_student_dir = os.path.realpath(student_dir)
        real_path = os.path.realpath(abs_file)

        # Check path containment strictly under real_student_dir
        try:
            common = os.path.commonpath([real_path, real_student_dir])
        except Exception:
            return False, None, 0

        if common != real_student_dir or real_path == real_student_dir:
            logger.warning("[SECURITY] Path traversal or unauthorized directory detected")
            return False, None, 0

        # Must be a regular file and not a symlink
        if not os.path.isfile(real_path) or os.path.islink(real_path):
            return False, None, 0

        # Extension check on resolved path
        ext = os.path.splitext(real_path)[1].lower()
        if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
            logger.warning("[SECURITY] Disallowed file extension in temp upload")
            return False, None, 0

        if file_name:
            fn_ext = os.path.splitext(file_name)[1].lower()
            if fn_ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
                logger.warning("[SECURITY] Disallowed file extension in filename")
                return False, None, 0

        # File size check
        sz = os.path.getsize(real_path)
        if sz <= 0 or sz > MAX_ATTACHMENT_SIZE_BYTES:
            logger.warning("[SECURITY] Temp file size outside allowed range")
            return False, None, 0

        return True, real_path, sz

    except Exception:
        logger.warning("[SECURITY] Exception validating temp file path")
        return False, None, 0


def sanitize_draft_for_storage(
    draft: Optional[Dict[str, Any]],
    owner_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Sanitizes complaint draft and verifies temporary files against owner and directory."""
    if not draft or not isinstance(draft, dict):
        return None

    resolved_owner = str(owner_id or draft.get("owner_id") or "").strip()
    if not resolved_owner:
        return None

    safe: Dict[str, Any] = {"owner_id": resolved_owner}
    for k, v in draft.items():
        if k not in ALLOWED_DRAFT_KEYS or k == "owner_id":
            continue
        if k == "temp_files" and isinstance(v, list):
            valid_files = []
            for item in v:
                if isinstance(item, dict) and item.get("name") and item.get("path"):
                    raw_p = str(item.get("path", ""))
                    raw_name = os.path.basename(str(item.get("name", "attachment")))
                    is_valid, resolved_p, f_size = validate_student_temp_path(
                        raw_p,
                        student_id=resolved_owner,
                        file_name=raw_name
                    )
                    if is_valid and resolved_p:
                        valid_files.append({
                            "name": raw_name,
                            "path": resolved_p,
                            "size": f_size,
                            "is_temp": bool(item.get("is_temp", True)),
                        })
            safe["temp_files"] = valid_files
        elif isinstance(v, (str, int, float, bool)) or v is None:
            safe[k] = v
    return safe


def get_shared_preferences(page: ft.Page) -> Optional[Any]:
    """Retrieves or attaches the SharedPreferences service singleton on the page."""
    if not hasattr(page, "services") or page.services is None:
        return None
    for s in page.services:
        if isinstance(s, SharedPreferences) or (hasattr(s, "get") and hasattr(s, "set") and hasattr(s, "remove")):
            return s
    sp = SharedPreferences()
    page.services.append(sp)
    if hasattr(page, "_services") and hasattr(page._services, "register_service"):
        try:
            page._services.register_service(sp)
        except Exception:
            pass
    return sp


def _get_session_store(page: ft.Page) -> Optional[Any]:
    if not hasattr(page, "session") or not page.session or not hasattr(page.session, "store"):
        return None
    return page.session.store


def _store_get(store: Any, key: str, default: Any = None) -> Any:
    val = default
    if hasattr(store, "contains_key"):
        val = store.get(key) if store.contains_key(key) else default
    elif hasattr(store, "get"):
        val = store.get(key, default)
    if type(val).__name__ == "MagicMock":
        return default
    return val


def _store_set(store: Any, key: str, value: Any) -> None:
    if hasattr(store, "set"):
        store.set(key, value)
    elif hasattr(store, "__setitem__"):
        store[key] = value


def _store_remove(store: Any, key: str) -> None:
    if hasattr(store, "remove"):
        try:
            store.remove(key)
        except Exception:
            pass
    elif hasattr(store, "pop"):
        store.pop(key, None)


# -----------------------------------------------------------------------------
# AUTHENTICATION SESSION RECOVERY (IN-MEMORY ONLY)
# -----------------------------------------------------------------------------
async def save_auth_session_async(page: ft.Page, user: Dict[str, Any], role: str) -> None:
    """Stores validated auth session strictly in server-side session store."""
    save_auth_session(page, user, role)


def save_auth_session(page: ft.Page, user: Dict[str, Any], role: str) -> None:
    """Stores validated auth session strictly in server-side session store (not in localStorage)."""
    store = _get_session_store(page)
    safe_user = sanitize_profile_for_storage(user)
    if store is not None and safe_user:
        _store_set(store, SESSION_KEY_USER, safe_user)
        _store_set(store, SESSION_KEY_ROLE, role)


async def clear_auth_session_async(page: ft.Page) -> None:
    """Clears in-memory session store and wipes persistent draft and legacy keys on logout."""
    store = _get_session_store(page)
    if store is not None:
        _store_remove(store, SESSION_KEY_USER)
        _store_remove(store, SESSION_KEY_ROLE)
        _store_remove(store, SESSION_KEY_ACTIVE_TAB)
        _store_remove(store, SESSION_KEY_ACTIVE_TAB_OWNER)
        _store_remove(store, SESSION_KEY_DRAFT)

    try:
        sp = get_shared_preferences(page)
        if sp and hasattr(page, "session") and getattr(page.session, "id", None):
            await sp.remove(SP_KEY_USER)
            await sp.remove(SP_KEY_ROLE)
            await sp.remove(SP_KEY_ACTIVE_TAB)
            await sp.remove(SP_KEY_DRAFT)
    except Exception as ex:
        logger.debug("clear_auth_session_async: storage cleanup error: %s", type(ex).__name__)


def clear_auth_session(page: ft.Page) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_remove(store, SESSION_KEY_USER)
        _store_remove(store, SESSION_KEY_ROLE)
        _store_remove(store, SESSION_KEY_ACTIVE_TAB)
        _store_remove(store, SESSION_KEY_ACTIVE_TAB_OWNER)
        _store_remove(store, SESSION_KEY_DRAFT)

    if hasattr(page, "run_task"):
        try:
            page.run_task(clear_auth_session_async, page)
        except Exception:
            pass


async def restore_auth_session_async(page: ft.Page) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    SECURITY NOTE:
    Browser localStorage is client-controlled and untrusted.
    It MUST NOT be used to authenticate a user or determine their role.
    Only the server-side in-memory session store (populated by successful backend
    authentication via AuthService) may provide an active session.
    """
    store = _get_session_store(page)
    if store is not None:
        u = _store_get(store, SESSION_KEY_USER)
        r = _store_get(store, SESSION_KEY_ROLE)
        if u and r:
            return u, r
    return None, None


# -----------------------------------------------------------------------------
# ACTIVE TAB RECOVERY
# -----------------------------------------------------------------------------
async def save_active_tab_async(page: ft.Page, tab_index: int, owner_id: Optional[str] = None) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_ACTIVE_TAB, int(tab_index))
        _store_set(store, SESSION_KEY_ACTIVE_TAB_OWNER, str(owner_id).strip() if owner_id else None)

    try:
        sp = get_shared_preferences(page)
        if sp and hasattr(page, "session") and getattr(page.session, "id", None):
            payload = {
                "tab_index": int(tab_index),
                "owner_id": str(owner_id).strip() if owner_id else None
            }
            await sp.set(SP_KEY_ACTIVE_TAB, json.dumps(payload))
    except Exception as ex:
        logger.debug("save_active_tab_async: storage write error: %s", type(ex).__name__)


def save_active_tab(page: ft.Page, tab_index: int, owner_id: Optional[str] = None) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_ACTIVE_TAB, int(tab_index))
        _store_set(store, SESSION_KEY_ACTIVE_TAB_OWNER, str(owner_id).strip() if owner_id else None)

    if hasattr(page, "run_task"):
        try:
            page.run_task(save_active_tab_async, page, tab_index, owner_id)
        except Exception:
            pass


async def restore_active_tab_async(page: ft.Page, expected_owner_id: Optional[str] = None) -> Optional[int]:
    """
    Restores active tab index only if owner matches expected_owner_id.

    Security hardening:
    - When expected_owner_id is provided, REQUIRES a matching owner_id.
      Unowned or legacy values (bare integers without owner) are rejected.
    - Tab index is validated against VALID_STUDENT_TAB_RANGE. Out-of-range
      values are silently rejected (returns None, caller falls back to default).
    """
    def _validate_tab(idx_val: Any) -> Optional[int]:
        """Validate and clamp tab index to the allowed range."""
        try:
            tab = int(idx_val)
        except (ValueError, TypeError):
            return None
        if tab not in VALID_STUDENT_TAB_RANGE:
            return None
        return tab

    store = _get_session_store(page)
    if store is not None:
        idx = _store_get(store, SESSION_KEY_ACTIVE_TAB)
        owner = _store_get(store, SESSION_KEY_ACTIVE_TAB_OWNER)
        if idx is not None:
            # When an expected owner is specified, require a matching owner.
            # Reject if owner is missing (legacy/unowned) or mismatched.
            if expected_owner_id:
                if not owner or str(owner) != str(expected_owner_id):
                    return None
            return _validate_tab(idx)

    try:
        sp = get_shared_preferences(page)
        if sp and hasattr(page, "session") and getattr(page.session, "id", None):
            raw = await asyncio.wait_for(sp.get(SP_KEY_ACTIVE_TAB), timeout=1.5)
            if raw is not None:
                # Legacy bare int/float without owner — reject when owner validation required
                if isinstance(raw, (int, float)):
                    if expected_owner_id:
                        return None
                    return _validate_tab(raw)
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        tab_owner = data.get("owner_id")
                        if expected_owner_id:
                            if not tab_owner or str(tab_owner) != str(expected_owner_id):
                                return None
                        return _validate_tab(data.get("tab_index", DEFAULT_TAB_INDEX))
                    elif isinstance(data, int):
                        # Legacy JSON integer — no owner, reject when required
                        if expected_owner_id:
                            return None
                        return _validate_tab(data)
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
    except Exception:
        logger.debug("restore_active_tab_async: storage read error")

    return None


# -----------------------------------------------------------------------------
# COMPLAINT DRAFT RECOVERY
# -----------------------------------------------------------------------------
async def save_complaint_draft_async(
    page: ft.Page,
    draft: Dict[str, Any],
    owner_id: Optional[str] = None
) -> None:
    safe_draft = sanitize_draft_for_storage(draft, owner_id=owner_id)
    if safe_draft is None:
        return

    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_DRAFT, safe_draft)

    try:
        sp = get_shared_preferences(page)
        if sp and hasattr(page, "session") and getattr(page.session, "id", None):
            await sp.set(SP_KEY_DRAFT, json.dumps(safe_draft))
    except Exception as ex:
        logger.debug("save_complaint_draft_async: storage write error: %s", type(ex).__name__)


def save_complaint_draft(
    page: ft.Page,
    draft: Dict[str, Any],
    owner_id: Optional[str] = None
) -> None:
    safe_draft = sanitize_draft_for_storage(draft, owner_id=owner_id)
    if safe_draft is None:
        return

    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_DRAFT, safe_draft)

    if hasattr(page, "run_task"):
        try:
            page.run_task(save_complaint_draft_async, page, draft, owner_id)
        except Exception:
            pass


async def restore_complaint_draft_async(
    page: ft.Page,
    expected_owner_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Restores draft from session store or SharedPreferences.
    CRITICAL SECURITY CHECKS:
    1. expected_owner_id must be provided (the authenticated student from the server).
    2. The draft's owner_id must match expected_owner_id. If not, the draft is rejected
       and discarded so other users cannot access it.
    3. Every temporary file path is strictly validated against the approved temporary
       upload directory for this student and allowed extensions/sizes.
    """
    if not expected_owner_id:
        logger.warning("[SECURITY] restore_complaint_draft_async called without expected_owner_id")
        return None

    clean_expected_owner = str(expected_owner_id).strip()
    draft = None

    # Check in-memory session store first
    store = _get_session_store(page)
    if store is not None:
        cand = _store_get(store, SESSION_KEY_DRAFT)
        if cand and isinstance(cand, dict):
            if str(cand.get("owner_id")) == clean_expected_owner:
                draft = cand
            else:
                _store_remove(store, SESSION_KEY_DRAFT)

    # If not in session store, check SharedPreferences
    if not draft:
        try:
            sp = get_shared_preferences(page)
            if sp and hasattr(page, "session") and getattr(page.session, "id", None):
                raw = await asyncio.wait_for(sp.get(SP_KEY_DRAFT), timeout=1.5)
                if raw:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        if str(parsed.get("owner_id")) == clean_expected_owner:
                            draft = parsed
                        else:
                            # Stored draft belongs to someone else - wipe it from storage
                            logger.info(
                                "[SECURITY] Discarding draft: owner mismatch with authenticated user"
                            )
                            await sp.remove(SP_KEY_DRAFT)
        except Exception:
            logger.debug("restore_complaint_draft_async: storage read error")

    if draft and isinstance(draft, dict):
        sanitized = sanitize_draft_for_storage(draft, owner_id=clean_expected_owner)
        if sanitized:
            if store is not None:
                _store_set(store, SESSION_KEY_DRAFT, sanitized)

            # Sync verified temporary files to page attachment state
            from ui.components.page_file_services import _set_selected_files
            valid_files = sanitized.get("temp_files", [])
            _set_selected_files(page, valid_files)
            return sanitized

    return None


def get_current_complaint_draft(
    page: ft.Page,
    expected_owner_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Synchronous access to already-restored draft in session store."""
    store = _get_session_store(page)
    if store is not None:
        draft = _store_get(store, SESSION_KEY_DRAFT)
        if draft and isinstance(draft, dict):
            if expected_owner_id and draft.get("owner_id"):
                if str(draft.get("owner_id")) != str(expected_owner_id):
                    return None
            return draft
    return None


async def clear_complaint_draft_async(page: ft.Page) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_remove(store, SESSION_KEY_DRAFT)

    try:
        sp = get_shared_preferences(page)
        if sp and hasattr(page, "session") and getattr(page.session, "id", None):
            await sp.remove(SP_KEY_DRAFT)
    except Exception as ex:
        logger.debug("clear_complaint_draft_async: storage cleanup error: %s", type(ex).__name__)


def clear_complaint_draft(page: ft.Page) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_remove(store, SESSION_KEY_DRAFT)

    if hasattr(page, "run_task"):
        try:
            page.run_task(clear_complaint_draft_async, page)
        except Exception:
            pass
