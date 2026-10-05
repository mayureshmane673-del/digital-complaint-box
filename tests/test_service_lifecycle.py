"""
tests/test_service_lifecycle.py: Service lifecycle and registration regression tests.

Verifies:
1. SharedPreferences and FilePicker are each registered exactly once in Flet's ServiceRegistry.
2. Repeated getter calls do not create duplicate service instances in page._services or page.services.
3. picker.page and SharedPreferences.page resolve correctly to the parent Page control.
4. FilePicker invocation calls session.invoke_method with the registered control ID and does not fail
   due to missing control mounting or corrupted parent hierarchy.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
import flet as ft
from flet.controls.context import _context_page
from flet.controls.services.file_picker import FilePicker
from flet.controls.services.shared_preferences import SharedPreferences

from services.draft_recovery_service import get_shared_preferences
from ui.components.page_file_services import (
    get_complaint_file_picker,
    ensure_import_picker,
    _register_picker,
    open_complaint_attachment_picker,
    open_spreadsheet_import_picker,
)
from utils.validators import validate_attachment


def _create_test_page():
    """Create a realistic Flet Page instance bound to the active context."""
    session = MagicMock()
    session.invoke_method = AsyncMock(return_value=[])
    page = ft.Page(session, "test-session-id")
    _context_page.set(page)
    return page


def test_services_registered_exactly_once():
    """SharedPreferences and FilePicker must each be registered exactly once in page._services."""
    page = _create_test_page()

    sp = get_shared_preferences(page)
    picker = get_complaint_file_picker(page)

    assert sp is not None
    assert picker is not None

    reg_services = page._services._services
    sp_count = sum(1 for s in reg_services if isinstance(s, SharedPreferences))
    picker_count = sum(1 for s in reg_services if isinstance(s, FilePicker))

    assert sp_count == 1, f"Expected exactly 1 SharedPreferences in registry, found {sp_count}"
    assert picker_count == 1, f"Expected exactly 1 FilePicker in registry, found {picker_count}"
    assert len(reg_services) == 2, f"Expected total 2 services in registry, found {len(reg_services)}"

    # Check view-level services list has no duplicates
    if hasattr(page, "services") and isinstance(page.services, list):
        assert page.services.count(sp) <= 1
        assert page.services.count(picker) <= 1


def test_repeated_getter_calls_idempotent():
    """Repeated calls to service getters must return the same instance without growing the registry."""
    page = _create_test_page()

    sp1 = get_shared_preferences(page)
    picker1 = get_complaint_file_picker(page)

    for _ in range(5):
        sp_next = get_shared_preferences(page)
        picker_next = get_complaint_file_picker(page)
        assert sp_next is sp1, "get_shared_preferences must return the singleton instance"
        assert picker_next is picker1, "get_complaint_file_picker must return the singleton instance"

    reg_services = page._services._services
    assert len(reg_services) == 2, f"Registry grew on repeated calls: {len(reg_services)} services"


def test_service_page_and_parent_resolution():
    """picker.page and sp.page must resolve to the page, and their parent must be ServiceRegistry."""
    page = _create_test_page()

    sp = get_shared_preferences(page)
    picker = get_complaint_file_picker(page)

    assert sp.page is page, f"Expected sp.page to be page, got {sp.page}"
    assert picker.page is page, f"Expected picker.page to be page, got {picker.page}"

    assert sp.parent is page._services, f"Expected sp.parent to be page._services, got {sp.parent}"
    assert picker.parent is page._services, f"Expected picker.parent to be page._services, got {picker.parent}"


def test_import_file_picker_registration():
    """Coordinator import FilePicker must also be registered cleanly as a singleton."""
    page = _create_test_page()

    import_picker1 = ensure_import_picker(page)
    import_picker2 = ensure_import_picker(page)

    assert import_picker1 is import_picker2
    reg_services = page._services._services
    import_count = sum(1 for s in reg_services if s is import_picker1)
    assert import_count == 1, f"Expected 1 import picker in registry, found {import_count}"


def test_register_picker_orphan_cleanup():
    """Passing a newly instantiated FilePicker when one already exists must not leave an orphan in registry."""
    page = _create_test_page()

    picker1 = get_complaint_file_picker(page)
    # Simulate a caller creating a second FilePicker and passing it to _register_picker
    orphan_picker = ft.FilePicker()
    result = _register_picker(page, orphan_picker, "_dcb_file_picker")

    assert result is picker1, "Must return existing singleton picker"
    assert orphan_picker not in page._services._services, "Orphan picker must be removed from registry"
    assert len(page._services._services) == 1


@pytest.mark.anyio
async def test_file_picker_invocation_regression_check():
    """pick_files must successfully invoke the session method on the registered control ID."""
    page = _create_test_page()

    # Pre-register SharedPreferences to simulate app startup
    get_shared_preferences(page)
    picker = get_complaint_file_picker(page)

    # Configure mock return value for session.invoke_method (dict matching Flutter bridge contract)
    page.session.invoke_method.return_value = [
        {"id": "doc1", "name": "document.pdf", "size": 1024, "path": None}
    ]

    # Verify pick_files completes without RuntimeError or missing control error
    files = await picker.pick_files(
        dialog_title="Select Attachment",
        allowed_extensions=["jpg", "png", "pdf"],
        allow_multiple=False,
    )

    assert len(files) == 1
    assert files[0].name == "document.pdf"
    assert files[0].size == 1024

    # Verify session.invoke_method was called with the registered control ID
    page.session.invoke_method.assert_called_once()
    call_args = page.session.invoke_method.call_args[0]
    called_control_id = call_args[0]
    called_method_name = call_args[1]

    assert called_control_id == picker._i, f"Expected control ID {picker._i}, called {called_control_id}"
    assert called_method_name == "pick_files"


def test_get_shared_preferences_mock_page_compatibility():
    """get_shared_preferences must safely handle None or mock pages without throwing exceptions."""
    assert get_shared_preferences(None) is None

    mock_page = MagicMock()
    mock_page.services = None
    assert get_shared_preferences(mock_page) is None


@pytest.mark.anyio
async def test_complaint_picker_uses_file_type_any_and_without_data():
    """Complaint attachment picker must use FileType.ANY and with_data=False (avoiding Android Gallery crash)."""
    page = _create_test_page()
    picker = get_complaint_file_picker(page)

    # Mock pick_files on the complaint picker
    picker.pick_files = AsyncMock(return_value=[])

    open_complaint_attachment_picker(page)
    # Allow scheduled _launch task to execute
    await asyncio.sleep(0.01)

    picker.pick_files.assert_called_once()
    kwargs = picker.pick_files.call_args.kwargs
    assert kwargs.get("file_type") == ft.FilePickerFileType.ANY
    assert kwargs.get("with_data") is False
    assert kwargs.get("allow_multiple") is False
    assert kwargs.get("cancel_upload_on_window_blur") is False
    # allowed_extensions should NOT be passed for FileType.ANY (Flet web raises exception if present)
    assert "allowed_extensions" not in kwargs or kwargs["allowed_extensions"] is None


@pytest.mark.anyio
async def test_spreadsheet_import_picker_retains_custom_extensions():
    """Coordinator import picker must preserve FileType.CUSTOM and explicit spreadsheet extensions."""
    page = _create_test_page()
    picker = ensure_import_picker(page)

    picker.pick_files = AsyncMock(return_value=[])

    on_selected = MagicMock()
    on_busy = MagicMock()
    open_spreadsheet_import_picker(page, on_selected=on_selected, on_busy=on_busy)
    await asyncio.sleep(0.01)

    picker.pick_files.assert_called_once()
    kwargs = picker.pick_files.call_args.kwargs
    assert kwargs.get("file_type") == ft.FilePickerFileType.CUSTOM
    assert kwargs.get("allowed_extensions") == ["xlsx", "xls", "csv"]
    assert kwargs.get("with_data") is False
    assert kwargs.get("allow_multiple") is False


def test_attachment_validation_rejects_unsupported_extensions():
    """validate_attachment must strictly reject disallowed extensions (executables, scripts, archives)."""
    disallowed = [
        "virus.exe", "script.bat", "run.sh", "server.php",
        "code.js", "app.py", "archive.zip", "data.tar.gz",
        "doc.docx", "presentation.pptx", "unknown.bin", "no_ext"
    ]
    for filename in disallowed:
        valid, err = validate_attachment(filename, 1024)
        assert not valid, f"Expected {filename} to be rejected"
        assert "not allowed" in err.lower() or "supported formats" in err.lower()

    allowed = [
        "photo.jpg", "photo.jpeg", "screenshot.png", "image.webp",
        "video.mp4", "clip.mov", "document.pdf",
        "UPPERCASE.JPG", "MixedCase.PnG", "DOCUMENT.PDF"
    ]
    for filename in allowed:
        valid, err = validate_attachment(filename, 1024)
        assert valid, f"Expected {filename} to be accepted, got error: {err}"
        assert err == ""


def test_attachment_validation_rejects_oversized_and_empty_files():
    """validate_attachment must reject empty files and files exceeding 10 MB."""
    # 0 bytes or negative
    valid, err = validate_attachment("test.jpg", 0)
    assert not valid
    assert "empty" in err.lower()

    valid, err = validate_attachment("test.png", -5)
    assert not valid
    assert "empty" in err.lower()

    # Exceeding 10 MB
    valid, err = validate_attachment("test.pdf", 10 * 1024 * 1024 + 1)
    assert not valid
    assert "exceeds 10 mb" in err.lower()

    valid, err = validate_attachment("test.mp4", 15 * 1024 * 1024)
    assert not valid
    assert "exceeds 10 mb" in err.lower()

    # Exactly 10 MB and valid smaller sizes
    valid, err = validate_attachment("test.pdf", 10 * 1024 * 1024)
    assert valid
    assert err == ""

    valid, err = validate_attachment("test.jpg", 50 * 1024)
    assert valid
    assert err == ""
