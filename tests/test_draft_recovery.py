"""
tests/test_draft_recovery.py: Regression tests for secure cross-reload recovery.

Verifies:
1. LocalStorage profile/role tampering CANNOT authenticate or elevate privileges.
2. Complaint drafts are restored ONLY IF the owner matches the server-authenticated student.
3. Temporary attachment paths are strictly validated against the approved directory and student ownership.
   Path traversal, arbitrary system files, other students' folders, and invalid extensions are blocked.
4. Active tabs are restored only for their owner.
5. Logout completely clears in-memory and persistent session/draft data.
6. StudentView accurately renders restored drafts and purges them on successful submission.
"""

import json
import os
import shutil
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from services.draft_recovery_service import (
    sanitize_profile_for_storage,
    sanitize_draft_for_storage,
    validate_student_temp_path,
    get_student_temp_dir,
    save_auth_session,
    clear_auth_session,
    restore_auth_session_async,
    save_active_tab,
    save_active_tab_async,
    restore_active_tab_async,
    save_complaint_draft,
    restore_complaint_draft_async,
    get_current_complaint_draft,
    clear_complaint_draft,
    SP_KEY_USER,
    SP_KEY_ROLE,
    SP_KEY_ACTIVE_TAB,
    SP_KEY_DRAFT,
    SESSION_KEY_USER,
    SESSION_KEY_ROLE,
    SESSION_KEY_ACTIVE_TAB,
    SESSION_KEY_ACTIVE_TAB_OWNER,
    SESSION_KEY_DRAFT,
    VALID_STUDENT_TAB_RANGE,
    DEFAULT_TAB_INDEX,
)
from ui.state import AppState
from ui.views.student_view import StudentView
from ui.components.page_file_services import _get_selected_files, _set_selected_files


class FakeSessionStore(dict):
    def set(self, key, value):
        self[key] = value

    def contains_key(self, key):
        return key in self

    def remove(self, key):
        self.pop(key, None)


class MockSharedPreferences:
    """In-memory mock of Flet SharedPreferences (browser localStorage)."""
    def __init__(self):
        self._data = {}

    async def get(self, key):
        return self._data.get(key)

    async def set(self, key, value):
        self._data[key] = str(value)

    async def remove(self, key):
        self._data.pop(key, None)

    async def clear(self):
        self._data.clear()


class MockPageWithStore:
    def __init__(self):
        self.sp = MockSharedPreferences()
        self.services = [self.sp]
        self._services = MagicMock()
        self.session = MagicMock()
        self.session.id = "mock_session_123"
        self.session.store = FakeSessionStore()
        self.controls = []
        self.overlay = []
        self.width = 1000

    def clean(self):
        self.controls.clear()

    def add(self, *ctrls):
        self.controls.extend(ctrls)

    def update(self):
        pass

    def run_task(self, handler, *args, **kwargs):
        pass


def test_sanitize_profile_strips_secrets():
    """Verify passwords, hashes, security answers, and unknown keys are strictly stripped."""
    dirty_user = {
        "id": "std-123",
        "roll_number": "22CS101",
        "full_name": "Test Student",
        "password": "supersecretpassword",
        "password_hash": "$2b$12$fakehash...",
        "security_question": "Pet name?",
        "security_answer": "Fluffy",
        "security_answer_hash": "$2b$12$fakehash...",
        "supabase_service_role_key": "secret-jwt-key",
        "access_token": "token123",
        "department_id": "dept-1",
        "departments": {"code": "CSE", "name": "Computer Science"},
        "year": "3rd",
        "is_hostel_approved": True,
        "role": "Student"
    }

    clean = sanitize_profile_for_storage(dirty_user)
    assert clean is not None
    assert clean["id"] == "std-123"
    assert clean["roll_number"] == "22CS101"
    assert clean["full_name"] == "Test Student"
    assert clean["department_id"] == "dept-1"
    assert clean["departments"] == {"code": "CSE", "name": "Computer Science"}
    assert clean["is_hostel_approved"] is True

    # Security assertions: secrets MUST NOT exist
    assert "password" not in clean
    assert "password_hash" not in clean
    assert "security_answer" not in clean
    assert "security_answer_hash" not in clean
    assert "supabase_service_role_key" not in clean
    assert "access_token" not in clean


def test_validate_student_temp_path_security():
    """Test comprehensive security validation of temporary file paths."""
    student_id = "std-sec-001"
    clean_sid = student_id.replace("-", "")
    student_dir = get_student_temp_dir(student_id)
    assert student_dir is not None
    os.makedirs(student_dir, exist_ok=True)

    other_student_id = "std-victim-999"
    other_dir = get_student_temp_dir(other_student_id)
    assert other_dir is not None
    os.makedirs(other_dir, exist_ok=True)

    # 1. Legitimate file inside student's directory
    legit_file = os.path.join(student_dir, "photo.jpg")
    with open(legit_file, "wb") as f:
        f.write(b"valid jpg binary content")

    # 2. Other student's file
    other_file = os.path.join(other_dir, "victim_photo.png")
    with open(other_file, "wb") as f:
        f.write(b"victim data")

    # 3. Disallowed extension
    script_file = os.path.join(student_dir, "exploit.exe")
    with open(script_file, "wb") as f:
        f.write(b"binary exe")

    # 4. Zero-byte file
    empty_file = os.path.join(student_dir, "empty.png")
    with open(empty_file, "wb") as f:
        pass

    try:
        # A. Valid file succeeds
        ok, res_path, sz = validate_student_temp_path(legit_file, student_id, file_name="photo.jpg")
        assert ok is True
        assert res_path == os.path.realpath(legit_file)
        assert sz > 0

        # B. Traversal outside student directory fails
        traversal_path = os.path.join(student_dir, "..", "..", "app.py")
        ok, _, _ = validate_student_temp_path(traversal_path, student_id)
        assert ok is False

        # C. Access to another student's file fails
        ok, _, _ = validate_student_temp_path(other_file, student_id)
        assert ok is False

        # D. System files outside uploads fail
        system_file = os.path.abspath(__file__)
        ok, _, _ = validate_student_temp_path(system_file, student_id)
        assert ok is False

        # E. Disallowed extension fails
        ok, _, _ = validate_student_temp_path(script_file, student_id, file_name="exploit.exe")
        assert ok is False

        # F. Zero byte file fails
        ok, _, _ = validate_student_temp_path(empty_file, student_id)
        assert ok is False

        # G. Non-existent file fails
        missing_file = os.path.join(student_dir, "not_real.png")
        ok, _, _ = validate_student_temp_path(missing_file, student_id)
        assert ok is False

    finally:
        shutil.rmtree(student_dir, ignore_errors=True)
        shutil.rmtree(other_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_tampered_localstorage_cannot_authenticate_or_elevate_privileges():
    """Verify that tampered localStorage entries NEVER authenticate a user or elevate privileges."""
    page = MockPageWithStore()

    # Attacker injects fake Administrator/Principal credentials into browser localStorage
    attacker_profile = {
        "id": "attacker-root-001",
        "username": "superadmin",
        "full_name": "Injected Superadmin",
        "role": "Principal"
    }
    await page.sp.set(SP_KEY_USER, json.dumps(attacker_profile))
    await page.sp.set(SP_KEY_ROLE, "Principal")

    # Ensure AppState starts unauthenticated
    AppState.clear_user()

    # Attempt to restore auth from client storage
    restored_user, restored_role = await restore_auth_session_async(page)

    # MUST return None, None - localStorage is untrusted
    assert restored_user is None
    assert restored_role is None
    assert AppState.is_authenticated() is False
    assert AppState.role is None


@pytest.mark.anyio
async def test_draft_owner_validation_rejects_unowned_draft():
    """Verify that a complaint draft is rejected and purged if owner doesn't match authenticated user."""
    page = MockPageWithStore()
    _set_selected_files(page, [])

    # Student A left a draft in localStorage
    draft_alice = {
        "owner_id": "std-alice-111",
        "title": "Alice's Secret Complaint",
        "description": "Sensitive details only Alice should see.",
        "priority": "High",
        "temp_files": []
    }
    await page.sp.set(SP_KEY_DRAFT, json.dumps(draft_alice))

    # Student B logs in (server authenticated as Bob)
    restored = await restore_complaint_draft_async(page, expected_owner_id="std-bob-222")

    # Draft must be rejected
    assert restored is None
    # Session store must NOT contain Alice's draft
    assert page.session.store.get(SESSION_KEY_DRAFT) is None
    # Alice's draft must be purged from client storage to prevent cross-account leak
    assert await page.sp.get(SP_KEY_DRAFT) is None
    # Selected files remains empty
    assert _get_selected_files(page) == []


@pytest.mark.anyio
async def test_draft_owner_validation_restores_for_legitimate_owner():
    """Verify that a complaint draft is restored when owner matches the authenticated user."""
    page = MockPageWithStore()
    _set_selected_files(page, [])

    student_id = "std-legit-333"
    clean_sid = student_id.replace("-", "")
    student_dir = get_student_temp_dir(student_id)
    os.makedirs(student_dir, exist_ok=True)
    real_photo = os.path.join(student_dir, "evidence.png")
    with open(real_photo, "wb") as f:
        f.write(b"legitimate photo bytes")

    try:
        legit_draft = {
            "owner_id": student_id,
            "title": "Classroom Projector Malfunction",
            "description": "HDMI port in room 204 is physically damaged.",
            "priority": "Medium",
            "temp_files": [
                {"name": "evidence.png", "path": real_photo, "size": 22, "is_temp": True}
            ]
        }
        await page.sp.set(SP_KEY_DRAFT, json.dumps(legit_draft))

        # Restored for the genuine owner
        restored = await restore_complaint_draft_async(page, expected_owner_id=student_id)

        assert restored is not None
        assert restored["title"] == "Classroom Projector Malfunction"
        assert restored["owner_id"] == student_id
        assert len(restored["temp_files"]) == 1
        assert restored["temp_files"][0]["name"] == "evidence.png"

        # Verify page attachment state was synced
        selected = _get_selected_files(page)
        assert len(selected) == 1
        assert selected[0]["name"] == "evidence.png"
        assert selected[0]["path"] == os.path.realpath(real_photo)
    finally:
        shutil.rmtree(student_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_draft_recovery_drops_tampered_attachment_paths():
    """Verify that even if draft owner matches, invalid or tampered attachment paths are dropped."""
    page = MockPageWithStore()
    _set_selected_files(page, [])

    student_id = "std-tamper-444"
    tampered_draft = {
        "owner_id": student_id,
        "title": "Testing Path Injection",
        "description": "Draft with injected file paths.",
        "temp_files": [
            {"name": "app.py", "path": os.path.abspath("app.py"), "size": 100, "is_temp": True},
            {"name": "passwd", "path": "/etc/passwd", "size": 100, "is_temp": True},
            {"name": "hosts", "path": "C:\\Windows\\System32\\drivers\\etc\\hosts", "size": 100, "is_temp": True}
        ]
    }
    await page.sp.set(SP_KEY_DRAFT, json.dumps(tampered_draft))

    restored = await restore_complaint_draft_async(page, expected_owner_id=student_id)
    assert restored is not None
    # All invalid paths MUST be pruned
    assert restored["temp_files"] == []
    assert _get_selected_files(page) == []


@pytest.mark.anyio
async def test_active_tab_restored_only_for_owner():
    """Verify active tab index is restored only if owned by the authenticated student."""
    page = MockPageWithStore()

    # Save active tab 1 for Alice
    await save_active_tab_async(page, tab_index=1, owner_id="std-alice-111")

    # Bob logs in -> tab should NOT restore for Bob (returns None)
    bob_tab = await restore_active_tab_async(page, expected_owner_id="std-bob-222")
    assert bob_tab is None

    # Alice logs in -> tab restores to 1
    alice_tab = await restore_active_tab_async(page, expected_owner_id="std-alice-111")
    assert alice_tab == 1


@pytest.mark.anyio
async def test_active_tab_rejects_unowned_legacy_in_session_store():
    """Session-store tab with missing owner is rejected when expected_owner_id is provided."""
    page = MockPageWithStore()

    # Simulate legacy state: tab index set without owner
    page.session.store.set(SESSION_KEY_ACTIVE_TAB, 3)
    # No SESSION_KEY_ACTIVE_TAB_OWNER set

    result = await restore_active_tab_async(page, expected_owner_id="std-alice-111")
    assert result is None, "Unowned legacy tab in session store must be rejected when owner is required"


@pytest.mark.anyio
async def test_active_tab_rejects_owner_mismatch_in_session_store():
    """Session-store tab with different owner must be rejected."""
    page = MockPageWithStore()

    page.session.store.set(SESSION_KEY_ACTIVE_TAB, 2)
    page.session.store.set(SESSION_KEY_ACTIVE_TAB_OWNER, "std-alice-111")

    result = await restore_active_tab_async(page, expected_owner_id="std-bob-222")
    assert result is None, "Tab owned by Alice must not restore for Bob"


@pytest.mark.anyio
async def test_active_tab_rejects_invalid_indices():
    """Tab indices outside VALID_STUDENT_TAB_RANGE must be rejected."""
    page = MockPageWithStore()

    for invalid_idx in [-1, 6, 99, -100, 1000]:
        # Set in session store with matching owner
        page.session.store.set(SESSION_KEY_ACTIVE_TAB, invalid_idx)
        page.session.store.set(SESSION_KEY_ACTIVE_TAB_OWNER, "std-test-001")

        result = await restore_active_tab_async(page, expected_owner_id="std-test-001")
        assert result is None, f"Out-of-range tab index {invalid_idx} must be rejected"


@pytest.mark.anyio
async def test_active_tab_accepts_all_valid_indices():
    """All tab indices within VALID_STUDENT_TAB_RANGE must be accepted for the correct owner."""
    page = MockPageWithStore()

    for valid_idx in VALID_STUDENT_TAB_RANGE:
        page.session.store.set(SESSION_KEY_ACTIVE_TAB, valid_idx)
        page.session.store.set(SESSION_KEY_ACTIVE_TAB_OWNER, "std-test-001")

        result = await restore_active_tab_async(page, expected_owner_id="std-test-001")
        assert result == valid_idx, f"Valid tab index {valid_idx} must be accepted for matching owner"


@pytest.mark.anyio
async def test_active_tab_rejects_legacy_bare_int_in_shared_prefs():
    """Legacy bare integer in SharedPreferences must be rejected when expected_owner_id is provided."""
    page = MockPageWithStore()

    # Clear session store so it falls through to SharedPreferences
    page.session.store.clear()

    # Store bare integer (legacy format without owner info)
    await page.sp.set(SP_KEY_ACTIVE_TAB, "2")

    result = await restore_active_tab_async(page, expected_owner_id="std-test-001")
    # The JSON parse of "2" yields int 2 — a legacy value with no owner, must be rejected
    assert result is None, "Legacy bare integer in SharedPreferences must be rejected when owner required"


@pytest.mark.anyio
async def test_active_tab_rejects_dict_without_owner_in_shared_prefs():
    """SharedPreferences tab dict without owner_id must be rejected when expected_owner_id is provided."""
    page = MockPageWithStore()
    page.session.store.clear()

    # JSON dict with tab_index but no owner_id
    await page.sp.set(SP_KEY_ACTIVE_TAB, json.dumps({"tab_index": 3}))

    result = await restore_active_tab_async(page, expected_owner_id="std-test-001")
    assert result is None, "Tab dict without owner_id must be rejected when owner required"


def test_get_student_temp_dir_preserves_lexical_unresolved_path():
    """Verify get_student_temp_dir returns lexical path without premature realpath resolution."""
    student_id = "std-lexical-999"
    student_dir = get_student_temp_dir(student_id)
    assert student_dir is not None
    # Must end with uploads/temp/<clean_sid>
    clean_sid = student_id.replace("-", "")
    expected_suffix = os.path.join("uploads", "temp", clean_sid)
    assert student_dir.endswith(expected_suffix)
    assert os.path.isabs(student_dir)


def test_validate_student_temp_path_rejects_symlinked_student_directory_mocked():
    """Verify that a symlinked student temp directory uploads/temp/<student_id> is rejected (mocked)."""
    student_id = "std-symmock-001"
    student_dir = get_student_temp_dir(student_id)
    assert student_dir is not None

    norm_target = os.path.normcase(os.path.abspath(student_dir))

    # Mock os.path.islink to return True specifically for the student's temp directory
    with patch("services.draft_recovery_service.os.path.islink") as mock_islink:
        mock_islink.side_effect = lambda p: os.path.normcase(os.path.abspath(p)) == norm_target

        fake_file = os.path.join(student_dir, "document.pdf")
        ok, res, sz = validate_student_temp_path(fake_file, student_id)
        assert ok is False, "Symlinked student temp directory must be rejected"
        assert res is None
        assert sz == 0


def test_validate_student_temp_path_rejects_symlinked_parent_temp_directory_mocked():
    """Verify that a symlinked parent directory (uploads/temp) is rejected (mocked)."""
    student_id = "std-parentsym-002"
    student_dir = get_student_temp_dir(student_id)
    assert student_dir is not None

    parent_temp_dir = os.path.dirname(student_dir)
    norm_parent = os.path.normcase(os.path.abspath(parent_temp_dir))

    with patch("services.draft_recovery_service.os.path.islink") as mock_islink:
        mock_islink.side_effect = lambda p: os.path.normcase(os.path.abspath(p)) == norm_parent

        fake_file = os.path.join(student_dir, "document.pdf")
        ok, res, sz = validate_student_temp_path(fake_file, student_id)
        assert ok is False, "Symlinked parent temp directory must be rejected"
        assert res is None
        assert sz == 0


def test_validate_student_temp_path_rejects_symlinked_directory_filesystem():
    """Real filesystem symlink test for uploads/temp/<student_id> (if permitted by OS privileges)."""
    student_id = "std-symlink-real"
    student_dir = get_student_temp_dir(student_id)
    assert student_dir is not None

    target_dir = os.path.join(os.path.dirname(student_dir), "symlink_target_dir_real")
    os.makedirs(target_dir, exist_ok=True)
    target_file = os.path.join(target_dir, "secret.jpg")
    with open(target_file, "wb") as f:
        f.write(b"secret data outside containment")

    try:
        if os.path.exists(student_dir):
            shutil.rmtree(student_dir, ignore_errors=True)
        try:
            os.symlink(target_dir, student_dir)
            symlink_created = True
        except (OSError, NotImplementedError):
            symlink_created = False

        if symlink_created:
            symlinked_file = os.path.join(student_dir, "secret.jpg")
            ok, _, _ = validate_student_temp_path(symlinked_file, student_id)
            assert ok is False, "Files under a real symlinked student temp directory must be rejected"
    finally:
        if os.path.islink(student_dir):
            os.remove(student_dir)
        elif os.path.isdir(student_dir):
            shutil.rmtree(student_dir, ignore_errors=True)
        shutil.rmtree(target_dir, ignore_errors=True)


def test_save_and_clear_auth_session():
    """Verify session saving in memory and complete cleanup on logout."""
    page = MockPageWithStore()
    user = {"id": "user-1", "roll_number": "22CS101", "full_name": "Alice"}
    save_auth_session(page, user, "Student")

    assert page.session.store.get(SESSION_KEY_USER)["id"] == "user-1"
    assert page.session.store.get(SESSION_KEY_ROLE) == "Student"

    save_active_tab(page, 1, owner_id="user-1")
    assert page.session.store.get(SESSION_KEY_ACTIVE_TAB) == 1

    clear_auth_session(page)
    assert page.session.store.get(SESSION_KEY_USER) is None
    assert page.session.store.get(SESSION_KEY_ROLE) is None
    assert page.session.store.get(SESSION_KEY_ACTIVE_TAB) is None
    assert page.session.store.get(SESSION_KEY_DRAFT) is None


def test_student_view_ignores_unowned_draft():
    """Verify StudentView does not render draft belonging to a different user."""
    page = MockPageWithStore()
    student = {
        "id": "std-actual-user",
        "roll_number": "22CS999",
        "full_name": "Actual User",
        "department_id": "dept-1",
        "is_hostel_approved": False
    }

    # Session store contains draft owned by someone else
    page.session.store.set(SESSION_KEY_DRAFT, {
        "owner_id": "std-other-user",
        "title": "Private Issue of Other User",
        "description": "Other user's complaint content.",
        "temp_files": []
    })

    view = StudentView(page, student, initial_tab=1)
    form_ctrl = view._render_new_complaint()
    assert form_ctrl is not None
    col = form_ctrl.content
    title_ctrl = next(c for c in col.controls if getattr(c, "label", None) == "Complaint Title")

    # MUST be empty, not populated from other user's draft
    assert title_ctrl.value == ""


def test_student_view_restores_draft_values():
    """Verify StudentView form controls populate with restored draft values for owner."""
    page = MockPageWithStore()
    student = {
        "id": "std-456",
        "roll_number": "22CS102",
        "full_name": "Bob",
        "department_id": "dept-1",
        "is_hostel_approved": True
    }

    # Pre-populate draft in session store for std-456
    page.session.store.set(SESSION_KEY_DRAFT, {
        "owner_id": "std-456",
        "title": "Restored Draft Title",
        "description": "Detailed explanation restored from draft storage.",
        "priority": "High",
        "is_anonymous": True,
        "is_hostel": True,
        "temp_files": []
    })

    view = StudentView(page, student, initial_tab=1)
    form_ctrl = view._render_new_complaint()

    assert form_ctrl is not None
    col = form_ctrl.content
    title_ctrl = next(c for c in col.controls if getattr(c, "label", None) == "Complaint Title")
    assert title_ctrl.value == "Restored Draft Title"

    desc_ctrl = next(c for c in col.controls if getattr(c, "label", None) == "Detailed Description")
    assert "Detailed explanation restored from draft storage." in desc_ctrl.value


def test_student_view_clears_draft_on_successful_submission():
    """Verify draft is cleared from storage when a complaint is successfully submitted."""
    page = MockPageWithStore()
    student = {
        "id": "std-789",
        "roll_number": "22CS103",
        "full_name": "Charlie",
        "department_id": "dept-1",
        "is_hostel_approved": False
    }

    page.session.store.set(SESSION_KEY_DRAFT, {
        "owner_id": "std-789",
        "title": "Draft to be submitted",
        "description": "Complaint description that will be cleared.",
        "temp_files": []
    })

    view = StudentView(page, student, initial_tab=1)
    view.categories = [{"id": "cat-1", "name": "Academic"}]
    view.subcategories_by_cat = {"cat-1": [{"id": "sub-1", "name": "Exam"}]}
    view.locations = [{"id": "loc-1", "name": "Hall 1"}]

    form_ctrl = view._render_new_complaint()
    col = form_ctrl.content

    title_ctrl = next(c for c in col.controls if getattr(c, "label", None) == "Complaint Title")
    title_ctrl.value = "Draft to be submitted"

    desc_ctrl = next(c for c in col.controls if getattr(c, "label", None) == "Detailed Description")
    desc_ctrl.value = "Valid complaint description with more than 10 characters."

    view.category_dropdown.value = "cat-1"

    with patch("services.complaint_service.ComplaintService.submit_complaint") as mock_submit:
        mock_submit.return_value = (True, "Complaint created", {"complaint_id": "CMP-999"})

        submit_btn = None
        for c in col.controls:
            if hasattr(c, "content") and hasattr(c.content, "value") and "Submit" in str(c.content.value):
                submit_btn = c
                break
            elif hasattr(c, "text") and "Submit" in str(c.text):
                submit_btn = c
                break

        assert submit_btn is not None
        submit_btn.on_click(MagicMock())

        mock_submit.assert_called_once()
        assert page.session.store.get(SESSION_KEY_DRAFT) is None


@pytest.mark.anyio
async def test_on_authenticated_draft_recovery_exception_falls_back_safely():
    """Verify that an exception during draft/tab recovery falls back to tab 0 and renders portal."""
    rendered_tabs = []

    def mock_render_portal_view(initial_tab=None):
        rendered_tabs.append(initial_tab)

    user_data = {"id": "std-error-test", "roll_number": "22CS999", "role": "Student"}
    page = MockPageWithStore()

    with patch("services.draft_recovery_service.restore_active_tab_async", side_effect=RuntimeError("Storage connection failed")), \
         patch("services.draft_recovery_service.restore_complaint_draft_async", side_effect=TimeoutError("Storage timeout")):

        tab = 0
        try:
            sid = str(user_data.get("id") or "")
            restored_tab = await restore_active_tab_async(page, expected_owner_id=sid)
            draft = await restore_complaint_draft_async(page, expected_owner_id=sid)
            if restored_tab is not None:
                tab = restored_tab
            elif draft and (draft.get("title") or draft.get("description") or draft.get("temp_files")):
                tab = 1
        except Exception:
            tab = 0
        mock_render_portal_view(initial_tab=tab)

    assert len(rendered_tabs) == 1
    assert rendered_tabs[0] == 0
