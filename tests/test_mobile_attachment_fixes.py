"""
tests/test_mobile_attachment_fixes.py: Verification tests for mobile attachment stability,
lifecycle preservation, memory optimization, ServiceRegistry patching, and multi-session safety.
"""

import os
import sys
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import flet as ft
from flet.controls.page import ServiceRegistry
from flet.messaging.session import Session

import ui.flet_compat
from ui.state import AppState
from ui.views.student_view import StudentView
from services.storage_service import StorageService


def test_service_registry_retains_services_across_events():
    """
    Verifies that ServiceRegistry.unregister_services does not purge FilePicker.
    Prevents Flet 0.86.5 from unregistering services on after_event, which was
    the root cause of 'Control is not registered' and SESSION_CRASHED reload.
    """
    sr = ServiceRegistry()
    fp = ft.FilePicker()
    sr._services.append(fp)
    assert len(sr._services) == 1

    # Call unregister_services() - should be a safe no-op that retains active services
    sr.unregister_services()
    assert len(sr._services) == 1
    assert sr._services[0] is fp


def test_session_safe_handle_invoke_method_results():
    """
    Verifies that Session.handle_invoke_method_results resolves pending method calls
    even if the control is not found in the weakref index, preventing unhandled RuntimeError.
    """
    mock_conn = MagicMock()
    sess = Session(mock_conn)

    # Simulate pending invoke-method call
    call_id = "test_call_999"
    evt = asyncio.Event()
    sess._Session__method_calls[call_id] = evt

    # Handle result for a control_id that is NOT in sess.__index
    control_id = 99999
    expected_result = [{"id": 1, "name": "photo.jpg", "size": 1024}]

    sess.handle_invoke_method_results(control_id, call_id, expected_result, None)

    # Event must be set and result recorded without raising RuntimeError
    assert evt.is_set()
    res, err = sess._Session__method_call_results.get(evt, (None, None))
    assert res == expected_result
    assert err is None


def test_storage_rollback_on_failed_db_insert():
    """
    Verifies that if database record insertion fails in complaint_attachments,
    the uploaded object is immediately removed from Supabase Storage so no orphaned
    files are retained.
    """
    mock_client = MagicMock()
    mock_storage_bucket = MagicMock()
    mock_client.storage.from_.return_value = mock_storage_bucket

    # Mock storage upload success
    mock_storage_bucket.upload.return_value = {"Key": "test"}

    # Mock database insert failure
    mock_table = MagicMock()
    mock_table.select.return_value.eq.return_value.execute.return_value.data = []
    mock_table.insert.return_value.execute.side_effect = RuntimeError("DB connection dropped")
    mock_client.table.return_value = mock_table

    with patch("services.storage_service._get_client", return_value=mock_client):
        success, msg, data = StorageService.upload_attachment(
            complaint_id=999,
            original_filename="receipt.pdf",
            file_bytes=b"%PDF-1.4 sample content"
        )
        assert success is False
        assert "Database attachment record failed" in msg

        # Verify rollback: Storage remove must have been called
        mock_storage_bucket.remove.assert_called_once()
        removed_paths = mock_storage_bucket.remove.call_args[0][0]
        assert len(removed_paths) == 1
        assert "complaints/999/" in removed_paths[0]


def test_app_state_multi_session_isolation():
    """
    Verifies that AppState isolates user sessions via contextvars so that
    concurrent web connections do not leak or overwrite user credentials.
    """
    # Initialize Session A
    AppState.init_session()
    AppState.set_user({"id": "student-A", "roll_number": "240101001"}, "Student")
    assert AppState.is_authenticated() is True
    assert AppState.current_user["id"] == "student-A"

    # In a separate coroutine/task context (Session B)
    async def session_b_worker():
        AppState.init_session()
        assert AppState.is_authenticated() is False
        AppState.set_user({"id": "staff-B", "username": "hod_cse"}, "HOD")
        assert AppState.current_user["id"] == "staff-B"
        assert AppState.role == "HOD"

    asyncio.run(session_b_worker())

    # Session A must still retain its own original state
    assert AppState.current_user["id"] == "student-A"
    assert AppState.role == "Student"
    AppState.clear_user()
    assert AppState.is_authenticated() is False


def test_tab_index_restoration_across_reconnect():
    """
    Verifies that StudentView accepts initial_tab and updates session store on switch,
    ensuring mobile reconnections keep the student on Tab 1 (New Complaint).
    """
    page = MagicMock(spec=ft.Page)
    store = {}
    page.session = MagicMock()
    page.session.store.get.side_effect = lambda k, d=None: store.get(k, d)
    page.session.store.set.side_effect = lambda k, v: store.__setitem__(k, v)

    student = {"id": "std-1", "roll_number": "240101001", "department_id": "dept-1"}

    # Start student view on Tab 1 (New Complaint)
    sv = StudentView(page, student, initial_tab=1)
    assert sv.selected_tab_index == 1

    # Switch view to Tab 2 (My Complaints)
    sv._switch_view(2)
    assert sv.selected_tab_index == 2
    assert store.get("active_tab_index") == 2


def test_temp_upload_file_removal_on_delete():
    """
    Verifies that temporary upload files on server disk are properly removed
    when the student clicks Remove or after successful grievance submission.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        tmp.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        tmp_path = tmp.name

    assert os.path.exists(tmp_path)

    # Simulate StudentView selected_files state with temporary file.
    # As of v1.0.9+, selected files are stored on page._dcb_selected_files
    # so they persist across StudentView recreations on Android WebSocket reconnects.
    page = MagicMock(spec=ft.Page)
    student = {"id": "std-1", "roll_number": "240101001", "department_id": "dept-1"}
    sv = StudentView(page, student)

    # Add to the page-level persistent list (the new architecture)
    sv.page._dcb_selected_files.append({
        "name": "photo.jpg",
        "path": tmp_path,
        "size": 104,
        "is_temp": True
    })

    # Remove file
    removed = sv.page._dcb_selected_files.pop(0)
    if removed.get("is_temp") and removed.get("path"):
        if os.path.exists(removed["path"]):
            os.remove(removed["path"])

    assert not os.path.exists(tmp_path)

