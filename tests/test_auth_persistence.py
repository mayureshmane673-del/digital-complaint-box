"""
tests/test_auth_persistence.py: Regression and integration tests for secure auth session persistence.

Verifies:
1. save_auth_session persists sanitized profile to SharedPreferences without secrets.
2. Sensitive fields (passwords, tokens, secret keys) are strictly excluded from storage.
3. restore_auth_session_async reads SharedPreferences in a fresh Flet session.
4. restore_auth_session_async requires backend database validation before restoring.
5. Tampered user ID / role or nonexistent accounts are rejected and purged from client storage.
6. Locked or deactivated accounts are rejected and purged.
7. clear_auth_session_async removes persistent auth and draft keys on logout.
8. app.py startup restoration flow deterministically restores an authenticated student.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import flet as ft

from services.draft_recovery_service import (
    save_auth_session,
    save_auth_session_async,
    restore_auth_session_async,
    clear_auth_session_async,
    clear_auth_session,
    get_shared_preferences,
    SP_KEY_USER,
    SP_KEY_ROLE,
    SP_KEY_ACTIVE_TAB,
    SP_KEY_DRAFT,
    SESSION_KEY_USER,
    SESSION_KEY_ROLE,
    SESSION_KEY_ACTIVE_TAB,
    SESSION_KEY_DRAFT,
)
from ui.state import AppState


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
    def __init__(self, sp=None):
        self.sp = sp if sp is not None else MockSharedPreferences()
        self.services = [self.sp]
        self._services = MagicMock()
        self.session = MagicMock()
        self.session.id = "mock_session_123"
        self.session.store = FakeSessionStore()
        self.controls = []
        self.overlay = []
        self.width = 1000
        self.bgcolor = None
        self._tasks = []

    def clean(self):
        self.controls.clear()

    def add(self, *ctrls):
        self.controls.extend(ctrls)

    def update(self):
        pass

    def run_task(self, handler, *args, **kwargs):
        coro = handler(*args, **kwargs)
        self._tasks.append(coro)
        return coro


@pytest.mark.anyio
async def test_save_auth_session_persists_sanitized_profile_without_secrets():
    """Verify save_auth_session persists whitelisted fields and strictly strips secrets."""
    page = MockPageWithStore()
    dirty_user = {
        "id": "std-uuid-001",
        "roll_number": "240101030",
        "full_name": "Mayuresh Mane",
        "year": "TE",
        "department_id": "dept-cse-01",
        "password": "SuperSecretPassword123!",
        "password_hash": "$2b$12$eW...fakehash",
        "security_question": "First pet?",
        "security_answer": "Max",
        "security_answer_hash": "$2b$12$fakeans...",
        "access_token": "bearer.jwt.token",
        "refresh_token": "refresh.jwt.token",
        "supabase_service_role_key": "service-role-secret-key",
    }

    await save_auth_session_async(page, dirty_user, "Student")

    # In-memory session store verification
    stored_in_mem = page.session.store.get(SESSION_KEY_USER)
    assert stored_in_mem is not None
    assert stored_in_mem["id"] == "std-uuid-001"
    assert stored_in_mem["roll_number"] == "240101030"
    assert "password" not in stored_in_mem
    assert "password_hash" not in stored_in_mem
    assert "access_token" not in stored_in_mem
    assert "supabase_service_role_key" not in stored_in_mem
    assert page.session.store.get(SESSION_KEY_ROLE) == "Student"

    # Persistent SharedPreferences verification
    raw_sp_user = await page.sp.get(SP_KEY_USER)
    raw_sp_role = await page.sp.get(SP_KEY_ROLE)
    assert raw_sp_user is not None
    assert raw_sp_role == "Student"

    sp_user = json.loads(raw_sp_user)
    assert sp_user["id"] == "std-uuid-001"
    assert sp_user["roll_number"] == "240101030"
    assert sp_user["full_name"] == "Mayuresh Mane"
    assert "password" not in sp_user
    assert "password_hash" not in sp_user
    assert "security_answer" not in sp_user
    assert "security_answer_hash" not in sp_user
    assert "access_token" not in sp_user
    assert "refresh_token" not in sp_user
    assert "supabase_service_role_key" not in sp_user


@pytest.mark.anyio
async def test_restore_auth_session_validates_against_backend():
    """Verify fresh session reads SharedPreferences and validates against the backend."""
    page = MockPageWithStore()
    # Emulate fresh session: session.store is empty!
    assert page.session.store.get(SESSION_KEY_USER) is None

    # Populate client storage with a legitimate student profile
    stored_profile = {
        "id": "std-uuid-001",
        "roll_number": "240101030",
        "full_name": "Mayuresh Mane",
        "department_id": "dept-cse-01",
    }
    await page.sp.set(SP_KEY_USER, json.dumps(stored_profile))
    await page.sp.set(SP_KEY_ROLE, "Student")

    mock_db_student = {
        "id": "std-uuid-001",
        "roll_number": "240101030",
        "full_name": "Mayuresh Mane",
        "department_id": "dept-cse-01",
        "year": "TE",
        "is_active": True,
        "is_locked": False,
    }

    mock_backend_client = MagicMock()
    mock_execute = MagicMock()
    mock_execute.data = [mock_db_student]
    mock_backend_client.table().select().eq().eq().limit().execute.return_value = mock_execute

    with patch("database.supabase_client.get_trusted_backend_client", return_value=mock_backend_client), \
         patch("services.cache_service.CacheService.get_department_by_id", return_value={"code": "CSE", "name": "Computer Science"}):
        restored_user, restored_role = await restore_auth_session_async(page)

    assert restored_user is not None
    assert restored_user["id"] == "std-uuid-001"
    assert restored_user["roll_number"] == "240101030"
    assert restored_role == "Student"

    # Confirms session store is populated with validated data
    assert page.session.store.get(SESSION_KEY_USER) == restored_user
    assert page.session.store.get(SESSION_KEY_ROLE) == "Student"


@pytest.mark.anyio
async def test_restore_auth_session_rejects_tampered_role_or_id():
    """Verify forged profile in SharedPreferences is rejected and purged when not in backend."""
    page = MockPageWithStore()

    # Attacker injects forged admin credentials into client storage
    forged_profile = {
        "id": "attacker-fake-id",
        "username": "fakeadmin",
        "full_name": "Attacker",
        "role": "Principal",
    }
    await page.sp.set(SP_KEY_USER, json.dumps(forged_profile))
    await page.sp.set(SP_KEY_ROLE, "Principal")

    mock_backend_client = MagicMock()
    mock_execute = MagicMock()
    mock_execute.data = []  # User not found in database!
    mock_backend_client.table().select().eq().eq().limit().execute.return_value = mock_execute

    with patch("database.supabase_client.get_trusted_backend_client", return_value=mock_backend_client):
        restored_user, restored_role = await restore_auth_session_async(page)

    assert restored_user is None
    assert restored_role is None

    # Persistent storage must be purged
    assert await page.sp.get(SP_KEY_USER) is None
    assert await page.sp.get(SP_KEY_ROLE) is None


@pytest.mark.anyio
async def test_restore_auth_session_rejects_locked_or_deactivated_account():
    """Verify locked or deactivated accounts in database are rejected and purged."""
    page = MockPageWithStore()

    stored_profile = {
        "id": "std-locked-001",
        "roll_number": "240101099",
        "full_name": "Locked Student",
    }
    await page.sp.set(SP_KEY_USER, json.dumps(stored_profile))
    await page.sp.set(SP_KEY_ROLE, "Student")

    mock_locked_student = {
        "id": "std-locked-001",
        "roll_number": "240101099",
        "is_active": True,
        "is_locked": True,  # LOCKED!
    }

    mock_backend_client = MagicMock()
    mock_execute = MagicMock()
    mock_execute.data = [mock_locked_student]
    mock_backend_client.table().select().eq().eq().limit().execute.return_value = mock_execute

    with patch("database.supabase_client.get_trusted_backend_client", return_value=mock_backend_client):
        restored_user, restored_role = await restore_auth_session_async(page)

    assert restored_user is None
    assert restored_role is None
    assert await page.sp.get(SP_KEY_USER) is None


@pytest.mark.anyio
async def test_clear_auth_session_purges_all_keys():
    """Verify clear_auth_session_async wipes both in-memory store and SharedPreferences."""
    page = MockPageWithStore()

    # Pre-populate session store and client storage
    page.session.store.set(SESSION_KEY_USER, {"id": "std-1"})
    page.session.store.set(SESSION_KEY_ROLE, "Student")
    page.session.store.set(SESSION_KEY_ACTIVE_TAB, 1)
    page.session.store.set(SESSION_KEY_DRAFT, {"title": "Draft"})

    await page.sp.set(SP_KEY_USER, json.dumps({"id": "std-1"}))
    await page.sp.set(SP_KEY_ROLE, "Student")
    await page.sp.set(SP_KEY_ACTIVE_TAB, "1")
    await page.sp.set(SP_KEY_DRAFT, json.dumps({"title": "Draft"}))

    await clear_auth_session_async(page)

    # In-memory store must be cleared
    assert page.session.store.get(SESSION_KEY_USER) is None
    assert page.session.store.get(SESSION_KEY_ROLE) is None
    assert page.session.store.get(SESSION_KEY_ACTIVE_TAB) is None
    assert page.session.store.get(SESSION_KEY_DRAFT) is None

    # SharedPreferences must be cleared
    assert await page.sp.get(SP_KEY_USER) is None
    assert await page.sp.get(SP_KEY_ROLE) is None
    assert await page.sp.get(SP_KEY_ACTIVE_TAB) is None
    assert await page.sp.get(SP_KEY_DRAFT) is None


@pytest.mark.anyio
async def test_app_startup_restores_valid_student_on_new_session():
    """Verify app.py startup flow restores student portal on fresh session."""
    from app import main

    page = MockPageWithStore()
    stored_profile = {
        "id": "std-uuid-001",
        "roll_number": "240101030",
        "full_name": "Mayuresh Mane",
        "department_id": "dept-cse-01",
    }
    await page.sp.set(SP_KEY_USER, json.dumps(stored_profile))
    await page.sp.set(SP_KEY_ROLE, "Student")

    mock_db_student = {
        "id": "std-uuid-001",
        "roll_number": "240101030",
        "full_name": "Mayuresh Mane",
        "department_id": "dept-cse-01",
        "year": "TE",
        "is_active": True,
        "is_locked": False,
    }

    from services.cache_service import CacheService
    orig_categories = CacheService._categories
    orig_subcategories = CacheService._subcategories_by_cat
    orig_locations = CacheService._locations
    orig_departments = CacheService._departments
    orig_by_id = CacheService._departments_by_id
    orig_by_code = CacheService._departments_by_code

    def mock_table(name):
        mock_t = MagicMock()
        if name == "students":
            mock_execute = MagicMock()
            mock_execute.data = [mock_db_student]
            mock_t.select().eq().eq().limit().execute.return_value = mock_execute
        else:
            mock_execute = MagicMock()
            mock_execute.data = []
            mock_t.select().execute.return_value = mock_execute
            mock_t.select().eq().execute.return_value = mock_execute
        return mock_t

    mock_backend_client = MagicMock()
    mock_backend_client.table.side_effect = mock_table

    try:
        with patch("database.supabase_client.get_trusted_backend_client", return_value=mock_backend_client), \
             patch("services.cache_service.CacheService.get_department_by_id", return_value={"code": "CSE", "name": "Computer Science"}):
            main(page)
            # Execute the background task scheduled via page.run_task
            assert len(page._tasks) > 0
            await page._tasks[0]

        assert AppState.is_authenticated() is True
        assert AppState.current_user["id"] == "std-uuid-001"
        assert AppState.role == "Student"
    finally:
        CacheService._categories = orig_categories
        CacheService._subcategories_by_cat = orig_subcategories
        CacheService._locations = orig_locations
        CacheService._departments = orig_departments
        CacheService._departments_by_id = orig_by_id
        CacheService._departments_by_code = orig_by_code


@pytest.mark.anyio
async def test_login_flow_awaits_persistence_before_render_and_restores_on_reload():
    """Regression test: Proves that login flow awaits persistent auth write before portal render,
    and a subsequent simulated fresh session / page reload successfully restores authenticated user.
    """
    from app import main

    # 1. First session: user visits login page
    page_login = MockPageWithStore()

    captured_on_authenticated = []
    with patch("app.AuthView") as MockAuthView:
        def fake_auth_init(page, on_authenticated):
            captured_on_authenticated.append(on_authenticated)
            instance = MagicMock()
            instance.render.return_value = ft.Container()
            return instance
        MockAuthView.side_effect = fake_auth_init

        main(page_login)
        assert len(page_login._tasks) > 0
        await page_login._tasks[0]

    assert len(captured_on_authenticated) == 1
    on_authenticated = captured_on_authenticated[0]

    student_user = {
        "id": "std-uuid-login-1",
        "roll_number": "240101030",
        "full_name": "Mayuresh Mane",
        "department_id": "dept-cse-01",
        "year": "TE",
        "is_active": True,
        "is_locked": False,
    }

    # 2. Trigger login via on_authenticated callback
    on_authenticated(student_user, "Student")

    # In-memory session store is immediately updated
    assert page_login.session.store.get(SESSION_KEY_USER) is not None
    assert page_login.session.store.get(SESSION_KEY_USER)["id"] == "std-uuid-login-1"

    # Execute the scheduled persistence & render task
    assert len(page_login._tasks) > 0
    await page_login._tasks[-1]

    # Persistent storage write MUST be guaranteed to have completed!
    raw_sp_user = await page_login.sp.get(SP_KEY_USER)
    assert raw_sp_user is not None
    assert json.loads(raw_sp_user)["id"] == "std-uuid-login-1"
    assert await page_login.sp.get(SP_KEY_ROLE) == "Student"

    # 3. Simulate a reload / fresh WebSocket connection:
    # A new page instance sharing the exact same browser storage (sp),
    # but with an EMPTY in-memory session.store.
    page_reload = MockPageWithStore(sp=page_login.sp)
    assert page_reload.session.store.get(SESSION_KEY_USER) is None

    mock_backend_client = MagicMock()
    def mock_table(name):
        mock_t = MagicMock()
        if name == "students":
            mock_execute = MagicMock()
            mock_execute.data = [student_user]
            mock_t.select().eq().eq().limit().execute.return_value = mock_execute
        else:
            mock_execute = MagicMock()
            mock_execute.data = []
            mock_t.select().execute.return_value = mock_execute
            mock_t.select().eq().execute.return_value = mock_execute
        return mock_t

    mock_backend_client.table.side_effect = mock_table

    from services.cache_service import CacheService
    orig_categories = CacheService._categories
    orig_subcategories = CacheService._subcategories_by_cat
    orig_locations = CacheService._locations
    orig_departments = CacheService._departments
    orig_by_id = CacheService._departments_by_id
    orig_by_code = CacheService._departments_by_code

    try:
        with patch("database.supabase_client.get_trusted_backend_client", return_value=mock_backend_client), \
             patch("services.cache_service.CacheService.get_department_by_id", return_value={"code": "CSE", "name": "Computer Science"}):
            main(page_reload)
            assert len(page_reload._tasks) > 0
            await page_reload._tasks[0]

        # Restored successfully on fresh session
        assert AppState.is_authenticated() is True
        assert AppState.current_user["id"] == "std-uuid-login-1"
        assert AppState.role == "Student"
        assert page_reload.session.store.get(SESSION_KEY_USER)["id"] == "std-uuid-login-1"
    finally:
        CacheService._categories = orig_categories
        CacheService._subcategories_by_cat = orig_subcategories
        CacheService._locations = orig_locations
        CacheService._departments = orig_departments
        CacheService._departments_by_id = orig_by_id
        CacheService._departments_by_code = orig_by_code


@pytest.mark.anyio
async def test_persistence_success_and_failure_distinction():
    """Verify that _persist_and_render_portal correctly distinguishes:
    1. persistence succeeds -> portal renders and _dcb_auth_persisted is True
    2. persistence fails -> failure is detected (_dcb_auth_persisted is False, not falsely reported),
       while in-memory portal still renders safely.
    """
    from app import main

    # Case 1: Persistence succeeds
    page_ok = MockPageWithStore()
    captured_ok = []
    with patch("app.AuthView") as MockAuthView:
        def fake_auth_init(page, on_authenticated):
            captured_ok.append(on_authenticated)
            instance = MagicMock()
            instance.render.return_value = ft.Container()
            return instance
        MockAuthView.side_effect = fake_auth_init

        main(page_ok)
        assert len(page_ok._tasks) > 0
        await page_ok._tasks[0]

    student_user = {
        "id": "std-uuid-distinguish-1",
        "roll_number": "240101030",
        "full_name": "Mayuresh Mane",
        "department_id": "dept-cse-01",
        "year": "TE",
        "is_active": True,
        "is_locked": False,
    }

    captured_ok[0](student_user, "Student")
    assert len(page_ok._tasks) > 1
    await page_ok._tasks[-1]

    # Persistence confirmed
    assert getattr(page_ok, "_dcb_auth_persisted", None) is True
    assert await page_ok.sp.get(SP_KEY_USER) is not None
    assert AppState.is_authenticated() is True

    # Case 2: Persistence fails (e.g. storage quota exceeded or disabled in browser)
    page_fail = MockPageWithStore()
    # Mock SharedPreferences set to raise an error
    page_fail.sp.set = AsyncMock(side_effect=OSError("QuotaExceededError: localStorage full or disabled"))

    captured_fail = []
    with patch("app.AuthView") as MockAuthView:
        def fake_auth_init(page, on_authenticated):
            captured_fail.append(on_authenticated)
            instance = MagicMock()
            instance.render.return_value = ft.Container()
            return instance
        MockAuthView.side_effect = fake_auth_init

        main(page_fail)
        assert len(page_fail._tasks) > 0
        await page_fail._tasks[0]

    captured_fail[0](student_user, "Student")
    assert len(page_fail._tasks) > 1
    await page_fail._tasks[-1]

    # Persistence failure was correctly detected and NOT falsely reported as persisted
    assert getattr(page_fail, "_dcb_auth_persisted", None) is False
    # Persistent storage does not have the profile
    assert await page_fail.sp.get(SP_KEY_USER) is None
    # However, active session remains valid in-memory so user is not locked out
    assert AppState.is_authenticated() is True
    assert page_fail.session.store.get(SESSION_KEY_USER)["id"] == "std-uuid-distinguish-1"
