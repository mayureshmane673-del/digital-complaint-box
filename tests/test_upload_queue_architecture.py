"""
tests/test_upload_queue_architecture.py: Direct automated tests for the new
queue architecture in page_file_services.py.

Verifies:
- Sequential upload queue processing
- Stable callbacks (on_result, on_upload not reassigned per file)
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
    _on_complaint_picker_result,
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
    open_complaint_attachment_picker,
    ensure_import_picker,
    open_spreadsheet_import_picker,
    _get_import_upload_queue,
    _get_import_upload_active,
    _get_import_picker_pending,
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


def _setup_mocked_upload(page):
    """Set up mocked upload on the page's pickers to avoid RuntimeWarning."""
    import asyncio

    async def mock_upload(*args, **kwargs):
        """Mock upload that does nothing but returns a proper coroutine."""
        # Simulate the async upload start
        pass
        return None

    async def mock_pick_files(*args, **kwargs):
        """Mock pick_files that returns empty list (simulating user cancel)."""
        # Return empty list to simulate user canceling
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

    # Make page.run_task actually run the coroutine function with args
    # Production calls: page.run_task(picker.upload, [upload_args])
    # Flet's run_task calls: handler(*args) -> picker.upload([upload_args])
    def run_task_impl(handler, *args, **kwargs):
        if hasattr(handler, '__call__'):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            # Call the handler with the args (which is a list of FilePickerUploadFile)
            coro = handler(*args, **kwargs)
            if hasattr(coro, '__await__'):
                if not loop.is_running():
                    loop.run_until_complete(coro)
                else:
                    asyncio.ensure_future(coro)
        return None

    page.run_task = run_task_impl
    return page


def _make_file_picker_result(files_list):
    """Create a mock FilePickerResultEvent with given files."""
    evt = MagicMock()
    evt.files = files_list
    return evt


def _make_file_picker_upload_event(file_name, progress=None, error=None, status=None):
    """Create a mock FilePickerUploadEvent."""
    evt = MagicMock()
    evt.file_name = file_name
    evt.progress = progress
    evt.error = error
    evt.status = status
    return evt


def _make_flet_file(name, size=1024, file_id=1, path=None):
    """Create a mock flet.FilePickerFile."""
    f = MagicMock()
    f.name = name
    f.size = size
    f.id = file_id
    f.path = path
    return f


class TestUploadQueueArchitecture:
    """Test the sequential upload queue architecture."""

    def test_two_files_queued_sequential_upload(self):
        """Image 1 queued, Image 2 queued -> both upload sequentially -> both in selected."""
        page = _make_page_with_store()
        _init_session_state(page)

        calls = {"refresh": 0, "btn": 0}
        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: calls.__setitem__("refresh", calls["refresh"] + 1),
            update_attach_btn=lambda: calls.__setitem__("btn", calls["btn"] + 1),
            student_id="student-uuid",
        )

        picker = _ensure_complaint_picker(page)
        _setup_mocked_upload(page)

        # Verify stable callbacks are set
        assert picker.on_result == _on_complaint_picker_result
        assert picker.on_upload == _on_complaint_upload_progress

        # Simulate picking two files (one at a time, as allow_multiple=False)
        # First file
        file1 = _make_flet_file("photo1.jpg", 1024, file_id=1)
        evt1 = _make_file_picker_result([file1])
        _on_complaint_picker_result(page, evt1)

        queue = _get_upload_queue(page)
        assert len(queue) == 1
        assert queue[0]["file_name"] == "photo1.jpg"
        assert queue[0]["file_id"] == 1

        # Second file
        file2 = _make_flet_file("photo2.jpg", 2048, file_id=2)
        evt2 = _make_file_picker_result([file2])
        _on_complaint_picker_result(page, evt2)

        queue = _get_upload_queue(page)
        assert len(queue) == 2
        assert queue[0]["file_name"] == "photo1.jpg"
        assert queue[1]["file_name"] == "photo2.jpg"

        # Verify callbacks have NOT been reassigned
        assert picker.on_result == _on_complaint_picker_result
        assert picker.on_upload == _on_complaint_upload_progress

        # Simulate upload progress for first file
        upload_evt1 = _make_file_picker_upload_event("photo1.jpg", progress=0.5)
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
        original_on_result = picker.on_result

        # Process multiple files through picker result
        for i in range(3):
            file = _make_flet_file(f"photo{i}.jpg", 1024, file_id=i)
            evt = _make_file_picker_result([file])
            _on_complaint_picker_result(page, evt)

            # Call the upload handler multiple times
            upload_evt = _make_file_picker_upload_event(f"photo{i}.jpg", progress=1.0, status="done")
            _on_complaint_upload_progress(page, upload_evt)

        # Callbacks must remain the exact same function objects
        assert picker.on_upload is original_on_upload
        assert picker.on_result is original_on_result

    def test_on_result_not_cleared_after_first_result(self):
        """picker.on_result is NOT cleared after the first result."""
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
        original_on_result = picker.on_result

        # First picker result
        file1 = _make_flet_file("photo1.jpg", 1024, file_id=1)
        _on_complaint_picker_result(page, _make_file_picker_result([file1]))
        assert picker.on_result is original_on_result

        # Second picker result (simulating second invocation)
        file2 = _make_flet_file("photo2.jpg", 1024, file_id=2)
        _on_complaint_picker_result(page, _make_file_picker_result([file2]))
        assert picker.on_result is original_on_result

    def test_second_invocation_possible(self):
        """Second picker invocation remains possible after first completes."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        # First file picked and uploaded
        file1 = _make_flet_file("photo1.jpg", 1024, file_id=1)
        _on_complaint_picker_result(page, _make_file_picker_result([file1]))

        upload_evt1 = _make_file_picker_upload_event("photo1.jpg", progress=1.0, status="done")
        _on_complaint_upload_progress(page, upload_evt1)

        # Pending flag should be reset
        assert _get_picker_pending(page) is False

        # Second invocation should be possible
        file2 = _make_flet_file("photo2.jpg", 1024, file_id=2)
        _on_complaint_picker_result(page, _make_file_picker_result([file2]))

        upload_evt2 = _make_file_picker_upload_event("photo2.jpg", progress=1.0, status="done")
        _on_complaint_upload_progress(page, upload_evt2)

        selected = _get_selected_files(page)
        assert len(selected) == 2

    def test_failed_upload_does_not_block_picker(self):
        """Failed upload does not permanently block the picker."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        # Queue a file
        file1 = _make_flet_file("photo1.jpg", 1024, file_id=1)
        _on_complaint_picker_result(page, _make_file_picker_result([file1]))

        # Simulate upload error
        upload_evt_error = _make_file_picker_upload_event("photo1.jpg", error="Network error")
        _on_complaint_upload_progress(page, upload_evt_error)

        # Queue should be cleared, upload_active should be False
        assert len(_get_upload_queue(page)) == 0
        assert _get_upload_active(page) is False
        assert _get_picker_pending(page) is False

        # Should be able to pick another file
        file2 = _make_flet_file("photo2.jpg", 1024, file_id=2)
        _on_complaint_picker_result(page, _make_file_picker_result([file2]))

        upload_evt2 = _make_file_picker_upload_event("photo2.jpg", progress=1.0, status="done")
        _on_complaint_upload_progress(page, upload_evt2)

        selected = _get_selected_files(page)
        assert len(selected) == 1
        assert selected[0]["name"] == "photo2.jpg"

    def test_cancellation_resets_pending_state(self):
        """Cancellation (empty files) resets pending state."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        # Simulate picker opened - use the session store invocation id
        _set_picker_invocation_id(page, 1)

        # User cancels (empty files)
        _on_complaint_picker_result(page, _make_file_picker_result([]))

        assert _get_picker_pending(page) is False
        assert _get_picker_opened_at(page) == 0.0

    def test_file_name_matching_not_file_id(self):
        """Upload events are matched by file_name, not file_id."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        # File picked with id=999
        file1 = _make_flet_file("test.jpg", 1024, file_id=999)
        _on_complaint_picker_result(page, _make_file_picker_result([file1]))

        queue = _get_upload_queue(page)
        assert queue[0]["file_id"] == 999
        assert queue[0]["file_name"] == "test.jpg"

        # Upload event comes with file_name only (no file_id in Flet 0.86.5)
        upload_evt = _make_file_picker_upload_event("test.jpg", progress=1.0, status="done")
        _on_complaint_upload_progress(page, upload_evt)

        selected = _get_selected_files(page)
        assert len(selected) == 1
        assert selected[0]["name"] == "test.jpg"

    def test_concurrent_picker_open_blocked(self):
        """Rapid taps on Add Attachment are blocked while picker pending."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        # First open
        open_complaint_attachment_picker(page)
        assert _get_picker_pending(page) is True

        # Second rapid tap should be blocked
        open_complaint_attachment_picker(page)
        # Should still be pending, no error thrown
        assert _get_picker_pending(page) is True

    def test_state_persists_across_page_rebuild(self):
        """Attachment state survives page rebuild (session store persistence)."""
        # Create a shared session store
        shared_store = {}
        page = _make_page_with_store(shared_store)
        _init_session_state(page)

        # Add some selected files
        test_files = [
            {"name": "doc1.pdf", "path": "/tmp/doc1.pdf", "size": 1024, "is_temp": True},
            {"name": "doc2.jpg", "path": "/tmp/doc2.jpg", "size": 2048, "is_temp": True},
        ]
        _set_selected_files(page, test_files)
        _set_picker_invocation_id(page, 5)

        # Simulate page rebuild - create new page with SAME session store
        new_page = _make_page_with_store(shared_store)
        _init_session_state(new_page)

        # State should be preserved
        selected = _get_selected_files(new_page)
        assert len(selected) == 2
        assert selected[0]["name"] == "doc1.pdf"
        assert selected[1]["name"] == "doc2.jpg"

        assert _get_picker_invocation_id(new_page) == 5

    def test_max_two_attachments_enforced(self):
        """Maximum 2 attachments limit is enforced."""
        page = _make_page_with_store()
        _init_session_state(page)

        register_complaint_attachment_hooks(
            page,
            refresh_files_display=lambda: None,
            update_attach_btn=lambda: None,
            student_id="student-uuid",
        )

        # Add 3 files - simulate local files with paths so they're added directly
        # Mock os.path.exists to return True for our test paths
        import os
        original_exists = os.path.exists
        try:
            os.path.exists = lambda p: True

            for i in range(3):
                file = _make_flet_file(f"photo{i}.jpg", 1024, file_id=i, path=f"/tmp/photo{i}.jpg")
                _on_complaint_picker_result(page, _make_file_picker_result([file]))
        finally:
            os.path.exists = original_exists

        selected = _get_selected_files(page)
        assert len(selected) == 2
        assert selected[0]["name"] == "photo0.jpg"
        assert selected[1]["name"] == "photo1.jpg"


class TestImportPickerQueue:
    """Test the import picker queue (coordinator spreadsheet import)."""

    def test_import_picker_queue_sequential(self):
        """Import picker processes uploads sequentially."""
        page = _make_page_with_store()
        _init_session_state(page)

        results = []
        busy_calls = []

        def on_selected(info):
            results.append(info)

        def on_busy(busy, msg):
            busy_calls.append((busy, msg))

        # Get the picker and the result handler that was registered
        from ui.components.page_file_services import ensure_import_picker
        picker = ensure_import_picker(page)
        _setup_mocked_upload(page)

        # Pick a file - this sets up the picker callbacks
        open_spreadsheet_import_picker(page, on_selected=on_selected, on_busy=on_busy)

        # The on_result handler was set in open_spreadsheet_import_picker
        # We need to call that handler directly
        import_handler = picker.on_result
        assert import_handler is not None, "on_result handler should be set"

        # Simulate file selection - call the result handler
        file = _make_flet_file("data.xlsx", 1024, file_id=1)
        file.path = None  # Force upload path
        import_handler(_make_file_picker_result([file]))

        # Check queue
        queue = _get_import_upload_queue(page)
        assert len(queue) == 1
        assert queue[0]["file_name"] == "data.xlsx"

        # Simulate upload complete - call the on_upload handler
        upload_handler = picker.on_upload
        assert upload_handler is not None, "on_upload handler should be set"
        upload_handler(_make_file_picker_upload_event("data.xlsx", progress=1.0, status="done"))

        assert len(results) == 1
        assert results[0]["name"] == "data.xlsx"
        assert results[0]["is_temp"] is True
        assert _get_import_upload_active(page) is False
        assert _get_import_picker_pending(page) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])