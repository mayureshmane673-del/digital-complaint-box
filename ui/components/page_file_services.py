"""
Page-level FilePicker services for mobile/web stability.

Android Chrome briefly disconnects the Flet WebSocket when the system file
manager opens. That triggers a full portal re-render, which destroys in-form
controls. Pickers and attachment state must live in page.session.store,
with UI hooks rebound on each form build — not inside transient view closures alone.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
import weakref
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import flet as ft

from ui.flet_compat import show_feedback_message
from utils.validators import validate_attachment

logger = logging.getLogger("complaint_box.page_file_services")

ATTACHMENT_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "mp4", "mov", "pdf"]
IMPORT_EXTENSIONS = ["xlsx", "xls", "csv"]
PICKER_STALE_SECONDS = 90

# Session store keys
SESSION_KEY_SELECTED_FILES = "_dcb_selected_files"
SESSION_KEY_PICKER_PENDING = "_dcb_picker_pending"
SESSION_KEY_PICKER_OPENED_AT = "_dcb_picker_opened_at"
SESSION_KEY_ATTACHMENT_HOOKS = "_dcb_attachment_hooks"
SESSION_KEY_UPLOAD_QUEUE = "_dcb_upload_queue"
SESSION_KEY_UPLOAD_ACTIVE = "_dcb_upload_active"
SESSION_KEY_PICKER_INVOCATION_ID = "_dcb_picker_invocation_id"


def _get_session_store(page: ft.Page) -> Optional[Dict[str, Any]]:
    """Get the session store, creating if needed. Returns None if no valid session store."""
    if not hasattr(page, "session") or not page.session or not hasattr(page.session, "store"):
        return None
    store = page.session.store
    # Handle MagicMock in tests - if store is a MagicMock, treat as no store
    if type(store).__name__ == "MagicMock":
        return None
    return store


def _register_picker(page: ft.Page, picker: ft.FilePicker, attr: str) -> ft.FilePicker:
    existing = getattr(page, attr, None)
    if existing is not None:
        return existing
    setattr(page, attr, picker)
    if hasattr(page, "services") and picker not in page.services:
        page.services.append(picker)
    if hasattr(page, "_services") and hasattr(page._services, "register_service"):
        try:
            page._services.register_service(picker)
        except Exception:
            pass
    try:
        picker._parent = weakref.ref(page)
    except Exception:
        pass
    return picker


def _store_get(store, key, default=None):
    """Safe get from SessionStore or dict."""
    if hasattr(store, 'contains_key'):  # SessionStore
        if store.contains_key(key):
            return store.get(key)
        return default
    return store.get(key, default)


def _store_set(store, key, value):
    """Safe set on SessionStore or dict."""
    if hasattr(store, 'contains_key'):  # SessionStore
        store.set(key, value)
    else:
        store[key] = value


def _store_has(store, key):
    """Safe key check on SessionStore or dict."""
    if hasattr(store, 'contains_key'):  # SessionStore
        return store.contains_key(key)
    return key in store


def _init_session_state(page: ft.Page) -> None:
    """Initialize attachment state in session store (persists across reconnects)."""
    store = _get_session_store(page)
    if not store:
        # Fallback to page attributes if no session store (tests)
        if not hasattr(page, SESSION_KEY_SELECTED_FILES):
            setattr(page, SESSION_KEY_SELECTED_FILES, [])
        if not hasattr(page, SESSION_KEY_PICKER_PENDING):
            setattr(page, SESSION_KEY_PICKER_PENDING, False)
        if not hasattr(page, SESSION_KEY_PICKER_OPENED_AT):
            setattr(page, SESSION_KEY_PICKER_OPENED_AT, 0.0)
        if not hasattr(page, SESSION_KEY_ATTACHMENT_HOOKS):
            setattr(page, SESSION_KEY_ATTACHMENT_HOOKS, {})
        if not hasattr(page, SESSION_KEY_UPLOAD_QUEUE):
            setattr(page, SESSION_KEY_UPLOAD_QUEUE, [])
        if not hasattr(page, SESSION_KEY_UPLOAD_ACTIVE):
            setattr(page, SESSION_KEY_UPLOAD_ACTIVE, False)
        if not hasattr(page, SESSION_KEY_PICKER_INVOCATION_ID):
            setattr(page, SESSION_KEY_PICKER_INVOCATION_ID, 0)
        return

    if not _store_has(store, SESSION_KEY_SELECTED_FILES):
        _store_set(store, SESSION_KEY_SELECTED_FILES, [])
    if not _store_has(store, SESSION_KEY_PICKER_PENDING):
        _store_set(store, SESSION_KEY_PICKER_PENDING, False)
    if not _store_has(store, SESSION_KEY_PICKER_OPENED_AT):
        _store_set(store, SESSION_KEY_PICKER_OPENED_AT, 0.0)
    if not _store_has(store, SESSION_KEY_ATTACHMENT_HOOKS):
        _store_set(store, SESSION_KEY_ATTACHMENT_HOOKS, {})
    if not _store_has(store, SESSION_KEY_UPLOAD_QUEUE):
        _store_set(store, SESSION_KEY_UPLOAD_QUEUE, [])
    if not _store_has(store, SESSION_KEY_UPLOAD_ACTIVE):
        _store_set(store, SESSION_KEY_UPLOAD_ACTIVE, False)
    if not _store_has(store, SESSION_KEY_PICKER_INVOCATION_ID):
        _store_set(store, SESSION_KEY_PICKER_INVOCATION_ID, 0)


def _get_selected_files(page: ft.Page) -> List[Dict[str, Any]]:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, SESSION_KEY_SELECTED_FILES, [])
    return getattr(page, SESSION_KEY_SELECTED_FILES, [])


def _set_selected_files(page: ft.Page, files: List[Dict[str, Any]]) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_SELECTED_FILES, files)
    else:
        setattr(page, SESSION_KEY_SELECTED_FILES, files)


def _get_picker_pending(page: ft.Page) -> bool:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, SESSION_KEY_PICKER_PENDING, False)
    return getattr(page, SESSION_KEY_PICKER_PENDING, False)


def _set_picker_pending(page: ft.Page, value: bool) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_PICKER_PENDING, value)
    else:
        setattr(page, SESSION_KEY_PICKER_PENDING, value)


def _get_picker_opened_at(page: ft.Page) -> float:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, SESSION_KEY_PICKER_OPENED_AT, 0.0)
    return getattr(page, SESSION_KEY_PICKER_OPENED_AT, 0.0)


def _set_picker_opened_at(page: ft.Page, value: float) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_PICKER_OPENED_AT, value)
    else:
        setattr(page, SESSION_KEY_PICKER_OPENED_AT, value)


def _get_attachment_hooks(page: ft.Page) -> Dict[str, Any]:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, SESSION_KEY_ATTACHMENT_HOOKS, {})
    return getattr(page, SESSION_KEY_ATTACHMENT_HOOKS, {})


def _set_attachment_hooks(page: ft.Page, hooks: Dict[str, Any]) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_ATTACHMENT_HOOKS, hooks)
    else:
        setattr(page, SESSION_KEY_ATTACHMENT_HOOKS, hooks)


def _get_upload_queue(page: ft.Page) -> List[Dict[str, Any]]:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, SESSION_KEY_UPLOAD_QUEUE, [])
    return getattr(page, SESSION_KEY_UPLOAD_QUEUE, [])


def _set_upload_queue(page: ft.Page, queue: List[Dict[str, Any]]) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_UPLOAD_QUEUE, queue)
    else:
        setattr(page, SESSION_KEY_UPLOAD_QUEUE, queue)


def _get_upload_active(page: ft.Page) -> bool:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, SESSION_KEY_UPLOAD_ACTIVE, False)
    return getattr(page, SESSION_KEY_UPLOAD_ACTIVE, False)


def _set_upload_active(page: ft.Page, value: bool) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_UPLOAD_ACTIVE, value)
    else:
        setattr(page, SESSION_KEY_UPLOAD_ACTIVE, value)


def _get_picker_invocation_id(page: ft.Page) -> int:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, SESSION_KEY_PICKER_INVOCATION_ID, 0)
    return getattr(page, SESSION_KEY_PICKER_INVOCATION_ID, 0)


def _set_picker_invocation_id(page: ft.Page, value: int) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, SESSION_KEY_PICKER_INVOCATION_ID, value)
    else:
        setattr(page, SESSION_KEY_PICKER_INVOCATION_ID, value)


def ensure_complaint_attachment_state(page: ft.Page) -> None:
    _init_session_state(page)


def clear_stale_picker_pending(page: ft.Page) -> None:
    """Reset a stuck pending flag after reconnect or abandoned picker."""
    _init_session_state(page)
    if not _get_picker_pending(page):
        return
    opened = _get_picker_opened_at(page)
    if opened and (time.time() - opened) > PICKER_STALE_SECONDS:
        logger.info("[ATTACHMENT] Clearing stale picker pending flag")
        _set_picker_pending(page, False)


def register_complaint_attachment_hooks(
    page: ft.Page,
    *,
    refresh_files_display: Callable[[], None],
    update_attach_btn: Callable[[], None],
    student_id: str,
) -> None:
    """Rebind UI updaters each time the complaint form is built."""
    _init_session_state(page)
    clear_stale_picker_pending(page)
    _set_attachment_hooks(page, {
        "refresh_files_display": refresh_files_display,
        "update_attach_btn": update_attach_btn,
        "student_id": student_id,
    })
    _ensure_complaint_picker(page)


def _notify_attachment_ui(page: ft.Page) -> None:
    hooks = _get_attachment_hooks(page) or {}
    refreshed = False
    for key in ("refresh_files_display", "update_attach_btn"):
        fn = hooks.get(key)
        if callable(fn):
            try:
                fn()
                refreshed = True
            except Exception as ex:
                logger.warning("[ATTACHMENT] UI hook %s failed: %s", key, ex)
    if not refreshed:
        try:
            page.update()
        except Exception:
            pass


def get_complaint_file_picker(page: ft.Page) -> ft.FilePicker:
    """Return the singleton complaint attachment FilePicker for this page session."""
    return _ensure_complaint_picker(page)


def _ensure_complaint_picker(page: ft.Page) -> ft.FilePicker:
    picker = getattr(page, "_dcb_file_picker", None)
    if picker is None:
        picker = ft.FilePicker()
        picker = _register_picker(page, picker, "_dcb_file_picker")
        picker.on_result = _on_complaint_picker_result
        picker.on_upload = _on_complaint_upload_progress
    else:
        # Ensure callbacks remain stable across page rebuilds
        picker.on_result = _on_complaint_picker_result
        picker.on_upload = _on_complaint_upload_progress
    return picker


def _on_complaint_picker_result(page: ft.Page, e: ft.FilePickerResultEvent) -> None:
    _init_session_state(page)
    _set_picker_pending(page, False)
    _set_picker_opened_at(page, 0.0)
    logger.info("[ATTACHMENT] attachment_picker_result files=%s", len(getattr(e, "files", None) or []))

    files = getattr(e, "files", None) or []
    if not files:
        _notify_attachment_ui(page)
        return

    hooks = _get_attachment_hooks(page) or {}
    student_id = hooks.get("student_id") or ""

    selected = _get_selected_files(page)
    for f in files:
        if len(selected) >= 2:
            show_feedback_message(page, "Maximum 2 attachments allowed.", is_error=True)
            break
        f_name = getattr(f, "name", "") or ""
        f_size = getattr(f, "size", 0) or 0
        valid, err = validate_attachment(f_name, f_size)
        if not valid:
            show_feedback_message(page, err, is_error=True)
            continue

        f_path = getattr(f, "path", None)
        if f_path and os.path.exists(f_path):
            selected.append({
                "name": f_name,
                "path": f_path,
                "bytes": None,
                "size": f_size,
                "is_temp": False,
            })
            logger.info("[ATTACHMENT] Desktop/local path added: %s", f_name)
            _notify_attachment_ui(page)
            continue

        f_id = getattr(f, "id", None) or f_name
        _queue_complaint_upload(page, f_id, f_name, f_size, student_id)
    _set_selected_files(page, selected)


def _queue_complaint_upload(
    page: ft.Page,
    file_id: str,
    file_name: str,
    file_size: int,
    student_id: str,
) -> None:
    """Add upload to queue and process if not already active."""
    ext = os.path.splitext(file_name)[1].lower()
    clean_sid = str(student_id or "anon").replace("-", "")
    temp_rel_path = f"temp/{clean_sid}/{uuid.uuid4().hex}{ext}"
    abs_disk_path = os.path.realpath(os.path.join(str(Path("uploads").resolve()), temp_rel_path))

    try:
        upload_url = page.get_upload_url(temp_rel_path, 3600)
    except Exception as ex:
        logger.warning("[ATTACHMENT] temp_upload_failure get_upload_url: %s", ex)
        show_feedback_message(page, f"Cannot prepare upload for {file_name}.", is_error=True)
        _notify_attachment_ui(page)
        return

    upload_item = {
        "file_id": file_id,
        "file_name": file_name,
        "file_size": file_size,
        "temp_rel_path": temp_rel_path,
        "abs_disk_path": abs_disk_path,
        "upload_url": upload_url,
        "done": False,
    }
    queue = _get_upload_queue(page)
    queue.append(upload_item)
    _set_upload_queue(page, queue)
    logger.info("[ATTACHMENT] Queued upload: %s (queue size=%s)", file_name, len(queue))

    _process_upload_queue(page)


def _process_upload_queue(page: ft.Page) -> None:
    """Process the next upload in the queue sequentially."""
    if _get_upload_active(page) or not _get_upload_queue(page):
        return

    queue = _get_upload_queue(page)
    item = queue[0]
    _set_upload_active(page, True)
    logger.info("[ATTACHMENT] Starting upload: %s", item["file_name"])

    picker = _ensure_complaint_picker(page)
    try:
        # picker.upload is a coroutine function; pass it to run_task with args
        upload_args = [
            ft.FilePickerUploadFile(
                name=item["file_name"],
                id=item["file_id"],
                upload_url=item["upload_url"],
                method="PUT",
            )
        ]
        if hasattr(page, "run_task"):
            page.run_task(picker.upload, upload_args)
        else:
            # Fallback: schedule on current event loop
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(picker.upload(upload_args))
            else:
                loop.run_until_complete(picker.upload(upload_args))
    except Exception as ex:
        logger.warning("[ATTACHMENT] upload() failed for %s: %s", item["file_name"], ex)
        show_feedback_message(page, f"Upload failed for {item['file_name']}.", is_error=True)
        queue.pop(0)
        _set_upload_queue(page, queue)
        _set_upload_active(page, False)
        _process_upload_queue(page)
        _notify_attachment_ui(page)


def _on_complaint_upload_progress(page: ft.Page, e: ft.FilePickerUploadEvent) -> None:
    """Single stable upload progress handler - dispatches to queued item by file_name."""
    queue = _get_upload_queue(page)
    if not queue:
        return

    item = queue[0]
    # FilePickerUploadEvent has file_name, not file_id. Match by file_name.
    if e.file_name != item["file_name"]:
        logger.debug("[ATTACHMENT] Upload event for unknown file_name=%s (expected=%s)", e.file_name, item["file_name"])
        return

    if e.error:
        logger.warning("[ATTACHMENT] temp_upload_failure file=%s err=%s", item["file_name"], e.error)
        show_feedback_message(page, f"Upload error for {item['file_name']}: {e.error}", is_error=True)
        queue.pop(0)
        _set_upload_queue(page, queue)
        _set_upload_active(page, False)
        _process_upload_queue(page)
        _notify_attachment_ui(page)
        return

    if item["done"]:
        return

    if (
        (e.progress is not None and e.progress >= 0.99)
        or getattr(e, "status", None) == "done"
        or (os.path.exists(item["abs_disk_path"]) and os.path.getsize(item["abs_disk_path"]) > 0)
    ):
        item["done"] = True
        actual_size = item["file_size"]
        if os.path.exists(item["abs_disk_path"]):
            actual_size = os.path.getsize(item["abs_disk_path"]) or item["file_size"]
        selected = _get_selected_files(page)
        selected.append({
            "name": item["file_name"],
            "path": item["abs_disk_path"],
            "bytes": None,
            "size": actual_size,
            "is_temp": True,
        })
        _set_selected_files(page, selected)
        logger.info("[ATTACHMENT] temp_upload_success file=%s size=%s", item["file_name"], actual_size)
        queue.pop(0)
        _set_upload_queue(page, queue)
        _set_upload_active(page, False)
        _process_upload_queue(page)
        _notify_attachment_ui(page)


def open_complaint_attachment_picker(page: ft.Page) -> None:
    """Open attachment picker (non-blocking). Safe across mobile reconnect."""
    _init_session_state(page)
    clear_stale_picker_pending(page)

    selected = _get_selected_files(page)
    if len(selected) >= 2:
        show_feedback_message(page, "Maximum 2 attachments allowed.", is_error=True)
        return
    if _get_picker_pending(page):
        show_feedback_message(page, "File picker already open.", is_error=False)
        return

    invocation_id = _get_picker_invocation_id(page) + 1
    _set_picker_invocation_id(page, invocation_id)

    picker = _ensure_complaint_picker(page)
    _set_picker_pending(page, True)
    _set_picker_opened_at(page, time.time())
    logger.info("[ATTACHMENT] attachment_picker_open invocation=%s count=%s", invocation_id, len(selected))
    _notify_attachment_ui(page)

    async def _launch():
        try:
            await picker.pick_files(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=ATTACHMENT_EXTENSIONS,
                allow_multiple=False,
                with_data=False,
                cancel_upload_on_window_blur=False,
            )
        except Exception as ex:
            logger.warning("[ATTACHMENT] pick_files failed: %s", ex)
            if _get_picker_invocation_id(page) == invocation_id:
                _set_picker_pending(page, False)
                _set_picker_opened_at(page, 0.0)
                show_feedback_message(page, "Unable to open file picker. Please try again.", is_error=True)
                _notify_attachment_ui(page)

    try:
        if hasattr(page, "run_task"):
            page.run_task(_launch)
        else:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_launch())
            else:
                loop.run_until_complete(_launch())
    except Exception as ex:
        logger.warning("[ATTACHMENT] launch error: %s", ex)
        if _get_picker_invocation_id(page) == invocation_id:
            _set_picker_pending(page, False)
            _set_picker_opened_at(page, 0.0)
            show_feedback_message(page, "Unable to open file picker. Please try again.", is_error=True)
            _notify_attachment_ui(page)


# ---------------------------------------------------------------------------
# Coordinator spreadsheet import (same lifecycle rules)
# ---------------------------------------------------------------------------

# Import session store keys
IMPORT_SESSION_KEY_PICKER_PENDING = "_dcb_import_picker_pending"
IMPORT_SESSION_KEY_UPLOAD_QUEUE = "_dcb_import_upload_queue"
IMPORT_SESSION_KEY_UPLOAD_ACTIVE = "_dcb_import_upload_active"
IMPORT_SESSION_KEY_INVOCATION_ID = "_dcb_import_invocation_id"


def _get_import_picker_pending(page: ft.Page) -> bool:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, IMPORT_SESSION_KEY_PICKER_PENDING, False)
    return getattr(page, IMPORT_SESSION_KEY_PICKER_PENDING, False)


def _set_import_picker_pending(page: ft.Page, value: bool) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, IMPORT_SESSION_KEY_PICKER_PENDING, value)
    else:
        setattr(page, IMPORT_SESSION_KEY_PICKER_PENDING, value)


def _get_import_upload_queue(page: ft.Page) -> List[Dict[str, Any]]:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, IMPORT_SESSION_KEY_UPLOAD_QUEUE, [])
    return getattr(page, IMPORT_SESSION_KEY_UPLOAD_QUEUE, [])


def _set_import_upload_queue(page: ft.Page, queue: List[Dict[str, Any]]) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, IMPORT_SESSION_KEY_UPLOAD_QUEUE, queue)
    else:
        setattr(page, IMPORT_SESSION_KEY_UPLOAD_QUEUE, queue)


def _get_import_upload_active(page: ft.Page) -> bool:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, IMPORT_SESSION_KEY_UPLOAD_ACTIVE, False)
    return getattr(page, IMPORT_SESSION_KEY_UPLOAD_ACTIVE, False)


def _set_import_upload_active(page: ft.Page, value: bool) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, IMPORT_SESSION_KEY_UPLOAD_ACTIVE, value)
    else:
        setattr(page, IMPORT_SESSION_KEY_UPLOAD_ACTIVE, value)


def _get_import_invocation_id(page: ft.Page) -> int:
    store = _get_session_store(page)
    if store is not None:
        return _store_get(store, IMPORT_SESSION_KEY_INVOCATION_ID, 0)
    return getattr(page, IMPORT_SESSION_KEY_INVOCATION_ID, 0)


def _set_import_invocation_id(page: ft.Page, value: int) -> None:
    store = _get_session_store(page)
    if store is not None:
        _store_set(store, IMPORT_SESSION_KEY_INVOCATION_ID, value)
    else:
        setattr(page, IMPORT_SESSION_KEY_INVOCATION_ID, value)


def ensure_import_picker(page: ft.Page) -> ft.FilePicker:
    picker = getattr(page, "_dcb_import_file_picker", None)
    if picker is None:
        picker = ft.FilePicker()
        picker = _register_picker(page, picker, "_dcb_import_file_picker")
    return picker


def open_spreadsheet_import_picker(
    page: ft.Page,
    *,
    on_selected: Callable[[Optional[Dict[str, Any]]], None],
    on_busy: Callable[[bool, str], None],
    max_bytes: int = 5 * 1024 * 1024,
) -> None:
    """
    Pick .xlsx/.xls/.csv without blocking the UI thread on mobile.
    on_selected receives file info dict or None on cancel/failure.
    on_busy(True, message) while uploading; on_busy(False, message) when idle.
    """
    _init_session_state(page)

    if _get_import_picker_pending(page):
        on_busy(True, "File picker already open.")
        return

    picker = ensure_import_picker(page)
    invocation_id = _get_import_invocation_id(page) + 1
    _set_import_invocation_id(page, invocation_id)
    _set_import_picker_pending(page, True)
    on_busy(True, "Opening file picker...")

    def _finish(info: Optional[Dict[str, Any]], idle_msg: str = "") -> None:
        if _get_import_invocation_id(page) == invocation_id:
            _set_import_picker_pending(page, False)
        on_busy(False, idle_msg)
        on_selected(info)

    def _process_import_queue():
        if _get_import_upload_active(page) or not _get_import_upload_queue(page):
            return
        current = _get_import_upload_queue(page)[0]
        _set_import_upload_active(page, True)
        try:
            # picker.upload is a coroutine function; pass it to run_task with args
            upload_args = [
                ft.FilePickerUploadFile(
                    name=current["file_name"],
                    id=current["file_id"],
                    upload_url=current["upload_url"],
                    method="PUT",
                )
            ]
            if hasattr(page, "run_task"):
                page.run_task(picker.upload, upload_args)
            else:
                # Fallback: schedule on current event loop
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(picker.upload(upload_args))
                else:
                    loop.run_until_complete(picker.upload(upload_args))
        except Exception as ex:
            logger.warning("[IMPORT] upload() failed for %s: %s", current["file_name"], ex)
            queue = _get_import_upload_queue(page)
            queue.pop(0)
            _set_import_upload_queue(page, queue)
            _set_import_upload_active(page, False)
            _process_import_queue()

    def _on_import_upload(e: ft.FilePickerUploadEvent) -> None:
        queue = _get_import_upload_queue(page)
        if not queue:
            return
        current = queue[0]
        # FilePickerUploadEvent has file_name, not file_id. Match by file_name.
        if e.file_name != current["file_name"]:
            return
        if e.error:
            logger.warning("[IMPORT] upload error for %s: %s", current["file_name"], e.error)
            queue.pop(0)
            _set_import_upload_queue(page, queue)
            _set_import_upload_active(page, False)
            _finish(None, f"Upload failed for {current['file_name']}.")
            _process_import_queue()
            return
        if current["done"]:
            return
        if (
            (e.progress is not None and e.progress >= 0.99)
            or getattr(e, "status", None) == "done"
            or (os.path.exists(current["abs_disk_path"]) and os.path.getsize(current["abs_disk_path"]) > 0)
        ):
            current["done"] = True
            queue.pop(0)
            _set_import_upload_queue(page, queue)
            _set_import_upload_active(page, False)
            _finish(
                {"name": current["file_name"], "path": current["abs_disk_path"], "bytes": None, "is_temp": True},
                f"Selected: {current['file_name']}",
            )
            _process_import_queue()

    def _on_result(e: ft.FilePickerResultEvent) -> None:
        files = getattr(e, "files", None) or []
        if not files:
            _finish(None, "No file selected")
            return

        f = files[0]
        f_name = getattr(f, "name", "") or ""
        f_size = getattr(f, "size", 0) or 0
        name_lower = f_name.lower()
        if not (name_lower.endswith(".xlsx") or name_lower.endswith(".xls") or name_lower.endswith(".csv")):
            _finish(None, f"Invalid file type: {f_name}")
            return
        if f_size and f_size > max_bytes:
            _finish(None, "File exceeds 5MB limit.")
            return

        if f.path and os.path.exists(f.path):
            _finish({"name": f_name, "path": f.path, "bytes": None, "is_temp": False}, f"Selected: {f_name}")
            return

        on_busy(True, f"Uploading {f_name}...")
        ext = os.path.splitext(f_name)[1].lower()
        temp_rel_path = f"temp/imports/{uuid.uuid4().hex}{ext}"
        try:
            upload_url = page.get_upload_url(temp_rel_path, 3600)
        except Exception as ex:
            logger.warning("[IMPORT] get_upload_url failed: %s", ex)
            _finish(None, "Upload preparation failed.")
            return

        abs_disk_path = os.path.realpath(os.path.join(str(Path("uploads").resolve()), temp_rel_path))

        upload_item = {
            "file_id": getattr(f, "id", None) or f_name,
            "file_name": f_name,
            "abs_disk_path": abs_disk_path,
            "upload_url": upload_url,
            "done": False,
        }
        queue = _get_import_upload_queue(page)
        queue.append(upload_item)
        _set_import_upload_queue(page, queue)
        _process_import_queue()

    # Stable callbacks for the lifetime of the picker - set BEFORE launching
    picker.on_upload = _on_import_upload
    picker.on_result = _on_result

    async def _launch():
        try:
            await picker.pick_files(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=IMPORT_EXTENSIONS,
                allow_multiple=False,
                with_data=False,
                cancel_upload_on_window_blur=False,
            )
        except Exception as ex:
            logger.warning("[IMPORT] pick_files failed: %s", ex)
            if _get_import_invocation_id(page) == invocation_id:
                _set_import_picker_pending(page, False)
                _finish(None, "Unable to open file picker.")

    try:
        if hasattr(page, "run_task"):
            page.run_task(_launch)
        else:
            asyncio.ensure_future(_launch())
    except Exception as ex:
        logger.warning("[IMPORT] launch error: %s", ex)
        if _get_import_invocation_id(page) == invocation_id:
            _set_import_picker_pending(page, False)
            _finish(None, "Unable to open file picker.")