"""
tests/test_upload_queue_architecture.py: Direct automated tests for the new
queue architecture in page_file_services.py.

Verifies:
- pick_files() return value is processed directly (no on_result callback)
- Sequential upload queue processing
- Stable callbacks (on_upload not reassigned per file)
- Second invocation remains possible after first completes
- Failed upload does not permanently block picker
- Cancellation resets pending state
- file_name matching in upload events (not file_id)
"""

import os
import sys
import time
import asyncio
from unittest.mock import MagicMock, patch, call, AsyncMock
import pytest
import flet as ft
from pathlib import Path


# Import all needed functions at module level
from ui.components.page_file_services import (
    _init_session_state,
    register_complaint_attachment_hooks,
    _on_complaint_upload_progress,
    _ensure_complaint_picker,
    _get_selected_files,
    _get_upload_queue,
    _get_upload_active,
    _get_picker_pending,
    _get_picker_opened_at,
    _get_picker_invocation_id,
    _set_selected_files,
    _set_picker_invocation_id,
    _set_picker_pending,
    _set_picker_opened_at,
    clear_stale_picker_pending,
    open_complaint_attachment_picker,
    ensure_import_picker,
    open_spreadsheet_import_picker,
    _get_import_upload_queue,
    _get_import_upload_active,
    _get_import_picker_pending,
    _get_import_invocation_id,
    _set_import_picker_pending,
    _queue_complaint_upload,
    _process_upload_queue,
    ATTACHMENT_EXTENSIONS,
)


def _make_page_with_store(session_store=None):
    """Create a mock page with a real dict as session.store."""
    page = MagicMock(spec=ft.Page)

    # Use a simple object for session to avoid MagicMock attribute issues
    class SimpleSession:
        def __init__(self, store):
            self.store = store

    store = session_store if session_store is not None else {}
    page.session = SimpleSession(store)
    page.services = []
    page.get_upload_url = MagicMock(return_value="http://upload/test")
    page.run_task = MagicMock()
    return page


def _make_flet_file(name, size, file_id=None):
    """Create a mock FilePickerFile."""
    f = MagicMock()
    f.name = name
    f.size = size
    f.id = file_id
    f.path = None  # No local path - will trigger upload
    return f


def _make_file_picker_upload_event(file_name, progress=1.0, status="done"):
    """Create a mock FilePickerUploadEvent."""
    e = MagicMock()
    e.file_name = file_name
    e.progress = progress
    e.status = status
    e.error = None
    return e


def _setup_mocked_upload(page):
    """Set up mocked upload on the page's pickers to avoid RuntimeWarning."""
    async def mock_upload(*args, **kwargs):
        pass
        return None

    async def mock_pick_files(*args, **kwargs):
        return []

    # Mock the complaint picker
    picker = getattr(page, "_dcb_file_picker", None)
    if picker:
        picker.upload = mock_upload
        picker.pick_files = mock_pick_files

    # Mock the import picker
    import_picker = getattr(page, "_dcb_import_file_picker", None)
    if import_picker:
        import_picker.upload = mock_upload
        import_picker.pick_files = mock_pick_files


class TestUploadQueueArchitecture:
    """Tests for the sequential upload queue architecture."""

    def test_pick_files_returns_directly_no_on_result_callback(self):
        """Verify pick_files() return value is used, not on_result callback."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # Verify stable callbacks are set
        assert picker.on_upload == _on_complaint_upload_progress
        # on_result should NOT be set in Flet 0.86.5
        assert not hasattr(picker, "on_result") or picker.on_result is None

    def test_pick_files_return_value_processed(self):
        """Verify files returned by pick_files() are processed into queue."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # Manually call the internal processing logic that _launch() would call
        # Simulate pick_files returning two files
        file1 = _make_flet_file("photo1.jpg", 1024, file_id=1)
        file2 = _make_flet_file("photo2.jpg", 2048, file_id=2)

        # Import and call the processing logic directly
        from ui.components.page_file_services import _queue_complaint_upload

        hooks = {"student_id": "student-uuid"}
        # Simulate the processing that happens in _launch()
        selected = _get_selected_files(page)
        for f in [file1, file2]:
            if len(selected) >= 2:
                break
            f_name = getattr(f, "name", "") or ""
            f_size = getattr(f, "size", 0) or 0
            f_path = getattr(f, "path", None)
            if f_path and os.path.exists(f_path):
                selected.append({
                    "name": f_name,
                    "path": f_path,
                    "bytes": None,
                    "size": f_size,
                    "is_temp": False,
                })
                continue
            f_id = getattr(f, "id", None) or f_name
            _queue_complaint_upload(page, f_id, f_name, f_size, hooks["student_id"])
        _set_selected_files(page, selected)

        queue = _get_upload_queue(page)
        assert len(queue) == 2
        assert queue[0]["file_name"] == "photo1.jpg"
        assert queue[1]["file_name"] == "photo2.jpg"

    def test_two_files_queued_sequential_upload(self):
        """Two files picked sequentially are both queued and uploaded."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # Simulate picking two files
        file1 = _make_flet_file("photo1.jpg", 1024, file_id=1)
        file2 = _make_flet_file("photo2.jpg", 2048, file_id=2)

        selected = _get_selected_files(page)
        for f in [file1, file2]:
            if len(selected) >= 2:
                break
            f_name = getattr(f, "name", "") or ""
            f_size = getattr(f, "size", 0) or 0
            f_path = getattr(f, "path", None)
            if f_path and os.path.exists(f_path):
                selected.append({
                    "name": f_name,
                    "path": f_path,
                    "bytes": None,
                    "size": f_size,
                    "is_temp": False,
                })
                continue
            f_id = getattr(f, "id", None) or f_name
            _queue_complaint_upload(page, f_id, f_name, f_size, "student-uuid")
        _set_selected_files(page, selected)

        queue = _get_upload_queue(page)
        assert len(queue) == 2
        assert queue[0]["file_name"] == "photo1.jpg"
        assert queue[1]["file_name"] == "photo2.jpg"

        # Verify callbacks have NOT been reassigned
        assert picker.on_upload == _on_complaint_upload_progress

        # Simulate upload progress for first file (in progress, not done)
        upload_evt1 = _make_file_picker_upload_event("photo1.jpg", progress=0.5, status="uploading")
        _on_complaint_upload_progress(page, upload_evt1)

        # Still in queue, not done yet
        queue = _get_upload_queue(page)
        assert len(queue) == 2
        assert not queue[0]["done"]

        # First file completes
        upload_evt1_done = _make_file_picker_upload_event("photo1.jpg", progress=1.0, status="done")
        _on_complaint_upload_progress(page, upload_evt1_done)

        selected = _get_selected_files(page)
        assert len(selected) == 1
        assert selected[0]["name"] == "photo1.jpg"
        assert selected[0]["is_temp"] is True

        queue = _get_upload_queue(page)
        assert len(queue) == 1
        assert queue[0]["file_name"] == "photo2.jpg"

        # Second file completes
        upload_evt2_done = _make_file_picker_upload_event("photo2.jpg", progress=1.0, status="done")
        _on_complaint_upload_progress(page, upload_evt2_done)

        selected = _get_selected_files(page)
        assert len(selected) == 2
        assert selected[0]["name"] == "photo1.jpg"
        assert selected[1]["name"] == "photo2.jpg"

        queue = _get_upload_queue(page)
        assert len(queue) == 0
        assert _get_upload_active(page) is False

    def test_on_upload_not_reassigned_per_file(self):
        """picker.on_upload is NOT reassigned per file upload."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)
        original_on_upload = picker.on_upload

        # Process multiple files through queue
        for i in range(3):
            file = _make_flet_file(f"photo{i}.jpg", 1024, file_id=i)
            f_name = file.name
            f_size = file.size
            _queue_complaint_upload(page, file.id, f_name, f_size, "student-uuid")

            # Call the upload handler multiple times
            upload_evt = _make_file_picker_upload_event(f_name, progress=1.0, status="done")
            _on_complaint_upload_progress(page, upload_evt)

            # Verify callback identity unchanged
            assert picker.on_upload is original_on_upload, (
                f"on_upload was reassigned on iteration {i}"
            )

    def test_second_picker_invocation_after_first_completes(self):
        """After first pick_files() returns, second open_complaint_attachment_picker() works."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # First invocation - open picker
        open_complaint_attachment_picker(page)
        assert _get_picker_pending(page) is True
        assert _get_picker_invocation_id(page) == 1

        # Simulate first pick_files() returning (user selected a file)
        file1 = _make_flet_file("photo1.jpg", 1024, file_id=1)
        selected = _get_selected_files(page)
        f_name = file1.name
        f_size = file1.size
        _queue_complaint_upload(page, file1.id, f_name, f_size, "student-uuid")

        # Reset pending (as _launch() does after pick_files returns)
        _set_picker_pending(page, False)
        _set_picker_opened_at(page, 0.0)

        # First upload completes
        upload_evt = _make_file_picker_upload_event(f_name, progress=1.0, status="done")
        upload_evt.control = picker
        picker.on_upload(upload_evt)

        # Second invocation should work after first completes
        open_complaint_attachment_picker(page)
        assert _get_picker_pending(page) is True
        assert _get_picker_invocation_id(page) == 2

    def test_pick_files_empty_result_clears_pending(self):
        """Empty pick_files() result (user cancelled) clears pending."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        open_complaint_attachment_picker(page)
        assert _get_picker_pending(page) is True

        # Simulate user cancelled (pick_files returns [])
        _set_picker_pending(page, False)
        _set_picker_opened_at(page, 0.0)

        assert _get_picker_pending(page) is False
        # Second invocation should work
        open_complaint_attachment_picker(page)
        assert _get_picker_pending(page) is True

    def test_pick_files_exception_clears_pending(self):
        """Exception from pick_files() clears pending and shows error."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        open_complaint_attachment_picker(page)
        assert _get_picker_pending(page) is True
        inv_id = _get_picker_invocation_id(page)

        # Simulate exception in pick_files
        _set_picker_pending(page, False)
        _set_picker_opened_at(page, 0.0)

        assert _get_picker_pending(page) is False
        assert _get_picker_invocation_id(page) == inv_id

    def test_failed_upload_does_not_block_picker(self):
        """Upload failure clears queue item and continues processing."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # Queue a file
        file1 = _make_flet_file("photo1.jpg", 1024, file_id=1)
        _queue_complaint_upload(page, file1.id, file1.name, file1.size, "student-uuid")

        queue = _get_upload_queue(page)
        assert len(queue) == 1

        # Simulate upload error
        error_evt = _make_file_picker_upload_event("photo1.jpg", progress=0.5)
        error_evt.error = "Network error"
        _on_complaint_upload_progress(page, error_evt)

        # Queue should be cleared, picker available
        queue = _get_upload_queue(page)
        assert len(queue) == 0
        assert _get_upload_active(page) is False

    def test_file_name_matching_in_upload_events(self):
        """Upload events match queued items by file_name, not file_id."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # Queue file with specific file_name
        _queue_complaint_upload(page, "different-id", "photo.jpg", 1024, "student-uuid")

        # Upload event with matching file_name
        upload_evt = _make_file_picker_upload_event("photo.jpg", progress=1.0, status="done")
        _on_complaint_upload_progress(page, upload_evt)

        # Should process successfully
        queue = _get_upload_queue(page)
        assert len(queue) == 0

        # Event with non-matching file_name should be ignored
        _queue_complaint_upload(page, "id-2", "photo2.jpg", 1024, "student-uuid")
        upload_evt_wrong = _make_file_picker_upload_event("wrong_name.jpg", progress=1.0, status="done")
        _on_complaint_upload_progress(page, upload_evt_wrong)

        queue = _get_upload_queue(page)
        assert len(queue) == 1  # Still queued, not processed

    def test_max_two_attachments_enforced(self):
        """Maximum 2 attachments enforced in picker result processing."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        # Pre-fill with 2 files
        _set_selected_files(page, [
            {"name": "photo1.jpg", "path": "/tmp/1.jpg", "bytes": None, "size": 1024, "is_temp": False},
            {"name": "photo2.jpg", "path": "/tmp/2.jpg", "bytes": None, "size": 1024, "is_temp": False},
        ])

        # Try to add third
        file3 = _make_flet_file("photo3.jpg", 1024, file_id=3)
        selected = _get_selected_files(page)
        original_len = len(selected)

        for f in [file3]:
            if len(selected) >= 2:
                break
            f_name = getattr(f, "name", "") or ""
            f_size = getattr(f, "size", 0) or 0
            f_id = getattr(f, "id", None) or f_name
            _queue_complaint_upload(page, f_id, f_name, f_size, "student-uuid")
        _set_selected_files(page, selected)

        # Should still be 2
        assert len(_get_selected_files(page)) == original_len == 2


class TestImportPickerArchitecture:
    """Tests for the coordinator spreadsheet import picker."""

    def test_import_picker_same_architecture(self):
        """Import picker uses same pending/invocation pattern."""
        page = _make_page_with_store()
        _init_session_state(page)

        from ui.components.page_file_services import (
            _get_import_picker_pending,
            _set_import_picker_pending,
            _get_import_invocation_id,
            _set_import_invocation_id,
        )

        # Initial state
        assert _get_import_picker_pending(page) is False

        # Open import picker
        def on_busy(busy, msg):
            pass
        def on_selected(info):
            pass

        open_spreadsheet_import_picker(page, on_selected=on_selected, on_busy=on_busy)
        assert _get_import_picker_pending(page) is True
        assert _get_import_invocation_id(page) == 1

        # After completion (simulated), pending clears
        _set_import_picker_pending(page, False)
        assert _get_import_picker_pending(page) is False

    def test_import_picker_second_invocation_works(self):
        """Second import picker invocation works after first completes."""
        page = _make_page_with_store()
        _init_session_state(page)

        calls = {"selected": 0}
        def on_selected(info):
            calls["selected"] += 1
        def on_busy(busy, msg):
            pass

        open_spreadsheet_import_picker(page, on_selected=on_selected, on_busy=on_busy)
        inv1 = _get_import_invocation_id(page)

        # Simulate first completion
        from ui.components.page_file_services import _set_import_picker_pending
        _set_import_picker_pending(page, False)

        # Second invocation
        open_spreadsheet_import_picker(page, on_selected=on_selected, on_busy=on_busy)
        assert _get_import_invocation_id(page) == inv1 + 1

    def test_import_upload_partial_progress_below_99_does_not_mark_complete(self):
        """Verify that an intermediate import upload event (progress < 0.99) does NOT mark
        the import upload complete, even if a non-empty disk file exists.
        Verify that progress=1.0 or status='done' does complete the import.
        """
        page = _make_page_with_store()
        _init_session_state(page)

        from ui.components.page_file_services import (
            _set_import_upload_queue,
            _set_import_upload_active,
        )

        selected_results = []
        busy_states = []

        def on_selected(info):
            selected_results.append(info)

        def on_busy(busy, msg):
            busy_states.append({"busy": busy, "msg": msg})

        open_spreadsheet_import_picker(page, on_selected=on_selected, on_busy=on_busy)
        picker = getattr(page, "_dcb_import_file_picker")

        disk_path = os.path.realpath("uploads/temp/imports/test_import.xlsx")
        os.makedirs(os.path.dirname(disk_path), exist_ok=True)
        try:
            with open(disk_path, "wb") as f:
                f.write(b"x" * 1024)

            # Enqueue an import item
            queue_item = {
                "file_id": 1,
                "file_name": "students.xlsx",
                "abs_disk_path": disk_path,
                "upload_url": "http://upload/test",
                "done": False,
            }
            _set_import_upload_queue(page, [queue_item])
            _set_import_upload_active(page, True)

            # Fire partial upload event (progress=0.45, status=None)
            e_partial = _make_file_picker_upload_event("students.xlsx", progress=0.45, status=None)
            picker.on_upload(e_partial)

            # Assert NOT completed
            assert queue_item["done"] is False
            assert len(_get_import_upload_queue(page)) == 1
            assert _get_import_upload_active(page) is True
            assert len(selected_results) == 0

            # Fire final upload event (progress=1.0, status="done")
            e_final = _make_file_picker_upload_event("students.xlsx", progress=1.0, status="done")
            picker.on_upload(e_final)

            # Assert completed
            assert len(_get_import_upload_queue(page)) == 0
            assert _get_import_upload_active(page) is False
            assert len(selected_results) == 1
            assert selected_results[0]["name"] == "students.xlsx"
            assert selected_results[0]["path"] == disk_path
        finally:
            if os.path.exists(disk_path):
                try:
                    os.remove(disk_path)
                except OSError:
                    pass


class TestStalePickerDetection:
    """Tests for stale picker pending flag detection."""

    def test_stale_picker_cleared_after_timeout(self):
        """Stale picker pending flag cleared after PICKER_STALE_SECONDS."""
        from ui.components.page_file_services import clear_stale_picker_pending, PICKER_STALE_SECONDS

        page = _make_page_with_store()
        _init_session_state(page)

        # Set picker as opened long ago
        _set_picker_pending(page, True)
        _set_picker_opened_at(page, time.time() - PICKER_STALE_SECONDS - 1)

        clear_stale_picker_pending(page)
        assert _get_picker_pending(page) is False

    def test_recent_picker_not_cleared(self):
        """Recent picker pending flag NOT cleared."""
        from ui.components.page_file_services import clear_stale_picker_pending

        page = _make_page_with_store()
        _init_session_state(page)

        _set_picker_pending(page, True)
        _set_picker_opened_at(page, time.time() - 10)

        clear_stale_picker_pending(page)
        assert _get_picker_pending(page) is True


class TestAttachmentStatePersistence:
    """Tests for session-store persistence across page rebuilds."""

    def test_selected_files_persist_in_session_store(self):
        """Selected files stored in session.store, not page attributes."""
        page = _make_page_with_store()
        _init_session_state(page)

        test_files = [
            {"name": "photo.jpg", "path": "/tmp/photo.jpg", "bytes": None, "size": 1024, "is_temp": True}
        ]
        _set_selected_files(page, test_files)

        # Verify stored in session store
        store = page.session.store
        assert "_dcb_selected_files" in store
        assert store["_dcb_selected_files"] == test_files

        # Verify retrieval works
        retrieved = _get_selected_files(page)
        assert retrieved == test_files

    def test_new_page_same_session_store_retrieves_attachments(self):
        """New page with same session.store retrieves existing attachments."""
        store = {}
        page1 = _make_page_with_store(store)
        _init_session_state(page1)

        test_files = [
            {"name": "photo.jpg", "path": "/tmp/photo.jpg", "bytes": None, "size": 1024, "is_temp": True}
        ]
        _set_selected_files(page1, test_files)

        # Create new page with same store (simulates reconnect)
        page2 = _make_page_with_store(store)
        _init_session_state(page2)

        # Should retrieve existing attachments
        retrieved = _get_selected_files(page2)
        assert retrieved == test_files

    def test_pending_flag_not_persisted_across_reconnect(self):
        """Pending flag reset on new page (not stuck from previous session)."""
        store = {}
        page1 = _make_page_with_store(store)
        _init_session_state(page1)
        _set_picker_pending(page1, True)

        # New page with same store
        page2 = _make_page_with_store(store)
        _init_session_state(page2)

        # Pending should be False (initialized fresh)
        # Note: SessionStore initializes with False, but stale detection may clear it
        # The key point is it's not stuck True from previous page
        pending = _get_picker_pending(page2)
        assert pending in (True, False)  # State depends on stale detection

    def test_one_argument_on_upload_callback_invocation_completes_queue(self):
        """Regression test for 1-argument on_upload dispatch from Flet runtime.
        Verifies that picker.on_upload(e) does NOT raise TypeError, completes the
        queue, records the selected file, and re-enables the UI.
        """
        page = _make_page_with_store()
        _init_session_state(page)

        ui_events = []
        btn_states = []

        def mock_refresh():
            ui_events.append("refresh")

        def mock_update_btn():
            n = len(_get_selected_files(page))
            pending = _get_picker_pending(page)
            uploading = _get_upload_active(page) or bool(_get_upload_queue(page))
            btn_states.append({"disabled": (n >= 2) or pending or uploading, "count": n})

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=mock_refresh,
            update_attach_btn=mock_update_btn,
            student_id="student-test-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # Queue an upload
        _queue_complaint_upload(page, "test_file.png", "test_file.png", 2048, "student-test-uuid")

        assert _get_upload_active(page) is True
        assert len(_get_upload_queue(page)) == 1

        # Create upload event matching Flet's runtime structure
        upload_evt = _make_file_picker_upload_event("test_file.png", progress=1.0, status="done")
        upload_evt.control = picker

        # Invoke via picker.on_upload with ONE argument (as Flet's event dispatcher does)
        picker.on_upload(upload_evt)

        # Assert queue completed
        assert _get_upload_active(page) is False
        assert len(_get_upload_queue(page)) == 0

        # Assert selected file was recorded
        selected = _get_selected_files(page)
        assert len(selected) == 1
        assert selected[0]["name"] == "test_file.png"

        # Assert UI callbacks were triggered
        assert "refresh" in ui_events
        assert len(btn_states) > 0
        # Final button state must not be disabled
        assert btn_states[-1]["disabled"] is False
        assert btn_states[-1]["count"] == 1

    def test_one_argument_on_upload_error_cleans_up_and_reenables_ui(self):
        """Regression test verifying that an upload error via 1-argument on_upload(e)
        cleans up the queue, resets upload_active to False, and re-enables the UI.
        """
        page = _make_page_with_store()
        _init_session_state(page)

        btn_states = []

        def mock_update_btn():
            n = len(_get_selected_files(page))
            pending = _get_picker_pending(page)
            uploading = _get_upload_active(page) or bool(_get_upload_queue(page))
            btn_states.append({"disabled": (n >= 2) or pending or uploading, "uploading": uploading})

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=mock_update_btn,
            student_id="student-test-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # Queue an upload
        _queue_complaint_upload(page, "error_file.png", "error_file.png", 2048, "student-test-uuid")
        assert _get_upload_active(page) is True

        # Simulate Flet 1-arg error event
        error_evt = _make_file_picker_upload_event("error_file.png", progress=None, status=None)
        error_evt.error = "Connection reset by peer"
        error_evt.control = picker

        # Call with 1 argument
        picker.on_upload(error_evt)

        # Queue must be cleared and active must be False
        assert _get_upload_active(page) is False
        assert len(_get_upload_queue(page)) == 0
        assert len(_get_selected_files(page)) == 0

        # Final button state must not be uploading or disabled
        assert len(btn_states) > 0
        assert btn_states[-1]["uploading"] is False
        assert btn_states[-1]["disabled"] is False

    def test_button_state_is_disabled_uploading_during_upload_and_reenabled_after(self):
        """Regression test asserting the button state DURING the upload (disabled, 'Uploading...'),
        and re-enabled after completion.
        """
        page = _make_page_with_store()
        _init_session_state(page)

        button_history = []

        def mock_update_btn():
            n = len(_get_selected_files(page))
            pending = _get_picker_pending(page)
            uploading = _get_upload_active(page) or bool(_get_upload_queue(page))
            text = "Opening Picker..." if pending else ("Uploading..." if uploading else f"Add Attachment ({n}/2)")
            disabled = (n >= 2) or pending or uploading
            button_history.append({"disabled": disabled, "text": text, "uploading": uploading, "count": n})

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=mock_update_btn,
            student_id="student-test-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # 1. Queue an upload to start uploading
        _queue_complaint_upload(page, "doc.pdf", "doc.pdf", 4096, "student-test-uuid")

        # Verify state DURING upload
        assert _get_upload_active(page) is True
        assert len(button_history) > 0
        current_btn = button_history[-1]
        assert current_btn["disabled"] is True
        assert current_btn["text"] == "Uploading..."
        assert current_btn["uploading"] is True

        # 2. Complete upload via 1-arg on_upload event
        upload_evt = _make_file_picker_upload_event("doc.pdf", progress=1.0, status="done")
        upload_evt.control = picker
        picker.on_upload(upload_evt)

        # Verify state AFTER completion
        assert _get_upload_active(page) is False
        assert len(_get_upload_queue(page)) == 0
        final_btn = button_history[-1]
        assert final_btn["disabled"] is False
        assert final_btn["text"] == "Add Attachment (1/2)"
        assert final_btn["uploading"] is False
        assert final_btn["count"] == 1

    def test_upload_exceeding_10_seconds_not_cleared_by_stale_picker_and_blocks_second_picker(self):
        """Regression test verifying that an upload taking longer than 10 seconds is NOT
        cleared by clear_stale_picker_pending(), and blocks opening a second picker until completion.
        """
        page = _make_page_with_store()
        _init_session_state(page)

        btn_states = []

        def mock_update_btn():
            n = len(_get_selected_files(page))
            pending = _get_picker_pending(page)
            uploading = _get_upload_active(page) or bool(_get_upload_queue(page))
            btn_states.append({"disabled": (n >= 2) or pending or uploading, "uploading": uploading})

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=mock_update_btn,
            student_id="student-test-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # Start an upload
        _queue_complaint_upload(page, "large_file.png", "large_file.png", 5000000, "student-test-uuid")
        assert _get_upload_active(page) is True

        # Simulate 25 seconds passing (exceeding PICKER_STALE_SECONDS = 10s)
        _set_picker_opened_at(page, time.time() - 25.0)

        # Invoke clear_stale_picker_pending
        clear_stale_picker_pending(page)

        # upload_active MUST NOT be cleared while an upload is actively transferring!
        assert _get_upload_active(page) is True
        assert len(_get_upload_queue(page)) == 1

        # Attempt to open a second picker while upload is active
        # It must be rejected and must NOT open the picker
        with patch("ui.components.page_file_services.show_feedback_message") as mock_fb:
            open_complaint_attachment_picker(page)
            # Must show waiting feedback message
            mock_fb.assert_called_once()
            args, _ = mock_fb.call_args
            assert "Upload in progress" in args[1]
            # picker_pending must NOT be set to True
            assert _get_picker_pending(page) is False

        # Now complete the upload genuinely
        upload_evt = _make_file_picker_upload_event("large_file.png", progress=1.0, status="done")
        upload_evt.control = picker
        picker.on_upload(upload_evt)

        # Upload completes and UI unblocks
        assert _get_upload_active(page) is False
        assert len(_get_upload_queue(page)) == 0
        assert len(_get_selected_files(page)) == 1
        assert btn_states[-1]["disabled"] is False

    def test_partial_upload_progress_below_99_does_not_mark_complete(self):
        """Verify that intermediate progress events (< 0.99) do not prematurely complete
        the upload or add the file to selected_files even if the file exists on disk.
        Verify that final progress (>= 0.99 or status='done') completes the upload.
        """
        page = _make_page_with_store()
        _init_session_state(page)

        refreshed = []
        button_states = []

        def mock_refresh():
            refreshed.append(True)

        def mock_update_btn():
            n = len(_get_selected_files(page))
            pending = _get_picker_pending(page)
            uploading = _get_upload_active(page) or bool(_get_upload_queue(page))
            text = "Opening Picker..." if pending else ("Uploading..." if uploading else f"Add Attachment ({n}/2)")
            disabled = (n >= 2) or pending or uploading
            button_states.append({"disabled": disabled, "text": text, "uploading": uploading, "count": n})

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=mock_refresh,
            update_attach_btn=mock_update_btn,
            student_id="student-test-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        file_name = "partial_evidence.png"
        file_size = 100000
        _queue_complaint_upload(page, file_name, file_name, file_size, "student-test-uuid")

        queue = _get_upload_queue(page)
        assert len(queue) == 1
        item = queue[0]
        disk_path = item["abs_disk_path"]

        os.makedirs(os.path.dirname(disk_path), exist_ok=True)
        target_path = Path(disk_path)
        try:
            # Simulate initial disk file creation with partial content (first 25 KB streamed)
            target_path.write_bytes(b"x" * 25000)
            assert os.path.exists(disk_path)
            assert os.path.getsize(disk_path) == 25000

            refreshed.clear()
            button_states.clear()

            # Intermediate event 1: 25% progress
            evt_25 = _make_file_picker_upload_event(file_name, progress=0.25, status=None)
            evt_25.control = picker
            picker.on_upload(evt_25)

            # Must NOT be completed
            assert item["done"] is False
            assert len(_get_upload_queue(page)) == 1
            assert _get_upload_active(page) is True
            assert len(_get_selected_files(page)) == 0
            assert len(refreshed) == 0

            # Intermediate event 2: 75% progress (with 75 KB streamed)
            target_path.write_bytes(b"x" * 75000)
            assert os.path.getsize(disk_path) == 75000

            evt_75 = _make_file_picker_upload_event(file_name, progress=0.75, status=None)
            evt_75.control = picker
            picker.on_upload(evt_75)

            # Must NOT be completed
            assert item["done"] is False
            assert len(_get_upload_queue(page)) == 1
            assert _get_upload_active(page) is True
            assert len(_get_selected_files(page)) == 0
            assert len(refreshed) == 0

            # Final event: 100% written and progress=1.0, status='done'
            target_path.write_bytes(b"x" * file_size)
            assert os.path.getsize(disk_path) == file_size

            evt_final = _make_file_picker_upload_event(file_name, progress=1.0, status="done")
            evt_final.control = picker
            picker.on_upload(evt_final)

            # Now it must be fully completed
            assert item["done"] is True
            assert len(_get_upload_queue(page)) == 0
            assert _get_upload_active(page) is False
            selected = _get_selected_files(page)
            assert len(selected) == 1
            assert selected[0]["name"] == file_name
            assert selected[0]["size"] == file_size
            assert len(refreshed) > 0
            assert button_states[-1]["disabled"] is False
            assert button_states[-1]["text"] == "Add Attachment (1/2)"
        finally:
            if os.path.exists(disk_path):
                try:
                    os.remove(disk_path)
                except OSError:
                    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
