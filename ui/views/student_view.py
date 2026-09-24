"""
ui/views/student_view.py: Student portal view with complaint submission wizard,
animated registered vs resolved chart, responsive reflow, loading state prevention,
private anonymous tracking, hostel status, and feedback rating.
"""

import os
import uuid
import asyncio
import weakref
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import flet as ft

logger = logging.getLogger("complaint_box.student_view")
from services.complaint_service import ComplaintService
from services.feedback_service import FeedbackService
from services.hostel_service import HostelService
from services.storage_service import StorageService
from services.analytics_service import AnalyticsService
from database.supabase_client import get_supabase_client, get_trusted_backend_client
from ui.theme import (
    COLOR_PRIMARY, COLOR_SURFACE, COLOR_BORDER, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_MUTED, STATUS_COLORS, PRIORITY_COLORS, get_theme_colors
)
from ui.state import AppState
from ui.flet_compat import show_feedback_message, open_dialog, close_dialog
from ui.components.stat_card import create_stat_card
from ui.components.complaint_card import create_complaint_card
from ui.components.complaint_detail import show_complaint_detail_dialog
from ui.components.animated_chart import (
    create_registered_vs_resolved_chart,
    create_priority_distribution_chart,
    create_category_distribution_chart
)
from utils.validators import validate_description, validate_attachment
from models.user import UserRole
from models.complaint import (
    PRACTICAL_SUBCATEGORIES,
    PRACTICAL_SUBCATEGORIES_CONFIG,
    get_default_priority
)

BASELINE_SUBCATEGORIES = PRACTICAL_SUBCATEGORIES


class StudentView:
    def __init__(self, page: ft.Page, student: Dict[str, Any], initial_tab: int = 0):
        self.page = page
        self.student = student
        self.student_id = student["id"]
        self.roll_number = student["roll_number"]
        self.department_id = student["department_id"]
        self.selected_tab_index = initial_tab
        self.cached_complaints = None
        self.active_container = ft.Container(expand=True)
        self.categories = []
        self.subcategories_by_cat = {}
        self.locations = []
        self.selected_files: List[Dict[str, Any]] = []
        self.file_picker = ft.FilePicker()
        # Register in both the root view services list AND the ServiceRegistry.
        # The services list placement ensures the control is in the tree for
        # rendering. The ServiceRegistry registration ensures invoke_method
        # works for pick_files/upload calls.
        if hasattr(self.page, "services"):
            if self.file_picker not in self.page.services:
                self.page.services.append(self.file_picker)
        # Always ensure ServiceRegistry registration (critical for mobile)
        if hasattr(self.page, "_services") and hasattr(self.page._services, "register_service"):
            try:
                self.page._services.register_service(self.file_picker)
            except Exception:
                pass
        try:
            self.file_picker._parent = weakref.ref(self.page)
        except Exception:
            pass
        # Retain strong page reference so GC never purges it
        try:
            setattr(self.page, "_student_file_picker", self.file_picker)
        except Exception:
            pass

    def _ensure_reference_data_loaded(self):
        if not self.categories:
            from services.cache_service import CacheService
            self.categories, self.subcategories_by_cat, self.locations = CacheService.get_categories_and_subcategories()

    def render(self) -> ft.Control:
        self._switch_view(self.selected_tab_index)
        return self.active_container

    def _create_dashboard_skeleton(self) -> ft.Control:
        """Lightweight loading skeleton shown while dashboard data loads."""
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)
        placeholder_color = colors.get("surface_variant", "#f1f5f9")
        return ft.Column(
            controls=[
                ft.Text("Dashboard", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Row(
                    controls=[
                        ft.Container(width=140, height=80, bgcolor=placeholder_color, border_radius=12)
                        for _ in range(4)
                    ],
                    wrap=True, spacing=12
                ),
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.ProgressRing(width=24, height=24, stroke_width=3, color=colors["primary"]),
                            ft.Text("Loading your complaints...", size=14, color=colors["text_muted"])
                        ],
                        spacing=12
                    ),
                    padding=24
                )
            ],
            spacing=14, expand=True
        )

    def _switch_view(self, index: int):
        self.selected_tab_index = index
        try:
            if hasattr(self.page, "session") and self.page.session and hasattr(self.page.session, "store") and self.page.session.store:
                self.page.session.store.set("active_tab_index", index)
        except Exception:
            pass
        if index == 0:
            # Show skeleton immediately, then load dashboard data
            if self.cached_complaints is None:
                self.active_container.content = self._create_dashboard_skeleton()
                self.page.update()
                # Fetch data then render real dashboard
                self.cached_complaints = ComplaintService.get_complaints_for_user(
                    role="Student",
                    user_id=self.student_id,
                    department_id=self.department_id
                )
            self.active_container.content = self._render_dashboard()
        elif index == 1:
            self.active_container.content = self._render_new_complaint()
        elif index == 2:
            self.active_container.content = self._render_my_complaints()
        elif index == 3:
            self.active_container.content = self._render_feedback()
        elif index == 4:
            self.active_container.content = self._render_hostel_status()
        elif index == 5:
            from ui.views.account_view import AccountView
            self.active_container.content = AccountView(
                self.page,
                self.student,
                UserRole.STUDENT.value,
                on_refresh=lambda: self._switch_view(self.selected_tab_index)
            ).render()
        self.page.update()

    # -------------------------------------------------------------------------
    # TAB 0: DASHBOARD
    # -------------------------------------------------------------------------
    def _render_dashboard(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        # Use cached complaints if available, otherwise fetch inline (fast path
        # after first load). For the very first load the data is fetched once
        # here; subsequent tab switches reuse self.cached_complaints.
        if self.cached_complaints is None:
            self.cached_complaints = ComplaintService.get_complaints_for_user(
                role="Student",
                user_id=self.student_id,
                department_id=self.department_id
            )
        complaints = self.cached_complaints

        total = len(complaints)
        pending = sum(1 for c in complaints if c.get("status") == "Pending")
        in_prog = sum(1 for c in complaints if c.get("status") == "In Progress")
        resolved = sum(1 for c in complaints if c.get("status") == "Resolved")
        rejected = sum(1 for c in complaints if c.get("status") == "Rejected")

        # Stat cards
        stats_row = ft.Row(
            controls=[
                create_stat_card("Total Submitted", str(total), ft.Icons.FOLDER_SPECIAL, colors["primary"], is_dark=is_dark),
                create_stat_card("Pending Review", str(pending), ft.Icons.HOURGLASS_EMPTY, "#d97706", is_dark=is_dark),
                create_stat_card("In Progress", str(in_prog), ft.Icons.AUTORENEW, "#2563eb", is_dark=is_dark),
                create_stat_card("Resolved", str(resolved), ft.Icons.CHECK_CIRCLE, "#059669", is_dark=is_dark),
                create_stat_card("Rejected", str(rejected), ft.Icons.CANCEL, "#dc2626", is_dark=is_dark)
            ],
            wrap=True,
            spacing=12
        )

        # Animated Charts
        chart_card = create_registered_vs_resolved_chart(
            registered=total,
            resolved=resolved,
            in_progress=in_prog,
            pending=pending,
            rejected=rejected,
            title="My Grievance Resolution Analytics",
            subtitle="Personal grievance tracking and status breakdown",
            is_dark=is_dark
        )
        prio_card = create_priority_distribution_chart(
            complaints=complaints,
            title="My Priority Breakdown",
            subtitle="Grievances categorized by urgency level",
            is_dark=is_dark
        )
        charts_row = ft.ResponsiveRow(
            controls=[
                ft.Container(chart_card, col={"xs": 12, "md": 7}),
                ft.Container(prio_card, col={"xs": 12, "md": 5})
            ],
            spacing=12,
            run_spacing=12
        )

        # Recent complaints list
        recent_cards = []
        for c in complaints[:4]:
            recent_cards.append(create_complaint_card(c, self._open_detail_dialog))

        if not recent_cards:
            recent_cards.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.MARK_EMAIL_READ_OUTLINED, size=48, color=colors["text_muted"]),
                            ft.Text("No complaints registered yet.", size=14, color=colors["text_muted"]),
                            ft.ElevatedButton(
                                content=ft.Text("Register First Complaint"),
                                icon=ft.Icons.ADD,
                                style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE),
                                on_click=lambda _: self._switch_view(1)
                            )
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER
                    ),
                    padding=32
                )
            )

        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text(f"Welcome back, {self.student.get('full_name')}!", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                ft.Text(f"Roll Number: {self.roll_number} | Year: {self.student.get('year', 'N/A')}", size=13, color=colors["text_muted"])
                            ],
                            spacing=2
                        ),
                        ft.ElevatedButton(
                            content=ft.Text("New Complaint"),
                            icon=ft.Icons.ADD_COMMENT,
                            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE),
                            on_click=lambda _: self._switch_view(1)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True
                ),
                stats_row,
                charts_row,
                ft.Divider(color=colors["border"]),
                ft.Text("Recent Grievances", size=18, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Column(controls=recent_cards, spacing=8)
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB 1: NEW COMPLAINT WIZARD
    # -------------------------------------------------------------------------
    def _render_new_complaint(self) -> ft.Control:
        self._ensure_reference_data_loaded()
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        title_field = ft.TextField(label="Complaint Title", hint_text="Brief summary of the issue", dense=True)

        char_counter = ft.Text("0 / 1000 characters (min 10)", size=11, color=colors["text_muted"])
        desc_field = ft.TextField(
            label="Detailed Description",
            hint_text="Explain the grievance clearly with location specifics (10 to 1000 characters).",
            multiline=True,
            min_lines=3,
            max_lines=6,
            dense=True
        )

        def on_desc_change(e):
            n = len(desc_field.value or "")
            char_counter.value = f"{n} / 1000 characters (min 10)"
            char_counter.color = "#dc2626" if (n < 10 or n > 1000) else "#059669"
            self.page.update()

        desc_field.on_change = on_desc_change

        cat_options = [ft.dropdown.Option(key=str(c["id"]), text=str(c["name"])) for c in self.categories]

        custom_cat_field = ft.TextField(
            label="Specify Custom Category / Subcategory (Compulsory)",
            hint_text="Please describe your specific issue in detail...",
            dense=True,
            visible=False,
            expand=True
        )

        priority_dropdown = ft.Dropdown(
            label="Priority",
            options=[
                ft.dropdown.Option("Low"),
                ft.dropdown.Option("Medium"),
                ft.dropdown.Option("High")
            ],
            value="Low",
            dense=True,
            width=160
        )

        def on_subcat_change(e):
            selected_sub_key = getattr(e, "data", None) or getattr(e.control, "value", None) or getattr(self.subcategory_dropdown, "value", None)
            if hasattr(self, "subcategory_dropdown") and self.subcategory_dropdown:
                self.subcategory_dropdown.value = selected_sub_key

            cat_id = getattr(self.category_dropdown, "value", None)
            cat_name = ""
            for c in self.categories:
                if str(c.get("id")) == str(cat_id) or str(c.get("name")) == str(cat_id):
                    cat_name = str(c.get("name", ""))
                    break

            selected_sub_name = ""
            if hasattr(self, "subcategory_dropdown") and self.subcategory_dropdown.options:
                for opt in self.subcategory_dropdown.options:
                    if str(opt.key) == str(selected_sub_key) or str(opt.text) == str(selected_sub_key):
                        selected_sub_name = str(opt.text)
                        break

            is_other_cat = (cat_name.strip().lower() == "other")
            is_other_sub = (
                selected_sub_key == "OTHER" or
                selected_sub_name.strip().lower() in ["other", "other complaint", "other / custom subcategory"]
            )
            custom_cat_field.visible = bool(is_other_cat or is_other_sub)
            if custom_cat_field.visible:
                custom_cat_field.label = "Specify Custom Details (Compulsory for Other)"

            smart_pri = get_default_priority(cat_name, selected_sub_name)
            priority_dropdown.value = smart_pri

            try:
                priority_dropdown.update()
            except Exception:
                pass
            try:
                custom_cat_field.update()
            except Exception:
                pass
            try:
                self.page.update()
            except Exception:
                pass

        self.subcategory_dropdown = subcategory_dropdown = ft.Dropdown(
            label="Subcategory (Select Category First)",
            options=[],
            dense=True,
            expand=True,
            on_select=on_subcat_change
        )
        self.subcategory_dropdown.on_select = on_subcat_change
        self.subcategory_dropdown.on_change = on_subcat_change
        self.subcat_holder = subcat_holder = ft.Container(content=subcategory_dropdown, col={"xs": 12, "sm": 6})

        def on_cat_change(e):
            raw_cat = getattr(e, "data", None) or getattr(e.control, "value", None) or (self.category_dropdown.value if hasattr(self, "category_dropdown") else None)
            if hasattr(self, "category_dropdown") and self.category_dropdown:
                self.category_dropdown.value = raw_cat
            cat_id = raw_cat
            cat_name = ""
            for c in self.categories:
                c_id_str = str(c.get("id", "")).strip().lower()
                c_name_str = str(c.get("name", "")).strip().lower()
                raw_str = str(raw_cat or "").strip().lower()
                if c_id_str == raw_str or c_name_str == raw_str:
                    cat_name = str(c.get("name", ""))
                    cat_id = str(c.get("id"))
                    break

            subs = []
            if cat_id and str(cat_id) in self.subcategories_by_cat:
                subs = self.subcategories_by_cat[str(cat_id)]
            elif cat_name and cat_name.strip().lower() in self.subcategories_by_cat:
                subs = self.subcategories_by_cat[cat_name.strip().lower()]
            elif cat_name:
                for pk, p_list in PRACTICAL_SUBCATEGORIES.items():
                    if pk.strip().lower() == cat_name.strip().lower():
                        subs = [{"id": f"sub_{pk.lower()}_{s.lower().replace(' ', '_')}", "name": s} for s in p_list]
                        break

            opts = []
            for s in subs:
                sname = str(s.get("name", "")).strip()
                sid = str(s.get("id", sname))
                if sname:
                    opts.append(ft.dropdown.Option(key=sid, text=sname))

            lbl = f"Subcategory ({len(opts)} available)" if opts else "Subcategory"
            print(f"[CATEGORY_CHANGE] raw_cat={raw_cat}, resolved_id={cat_id}, resolved_name='{cat_name}', options_count={len(opts)}")

            new_subcat = ft.Dropdown(
                label=lbl,
                options=opts,
                value=None,
                dense=True,
                expand=True,
                on_select=on_subcat_change
            )
            new_subcat.on_select = on_subcat_change
            new_subcat.on_change = on_subcat_change

            self.subcategory_dropdown = new_subcat
            self.subcat_holder.content = new_subcat

            is_other_cat = (cat_name.strip().lower() == "other")
            if is_other_cat:
                custom_cat_field.visible = True
                custom_cat_field.label = "Specify Custom Details (Compulsory for Other)"
            else:
                custom_cat_field.visible = False
                custom_cat_field.value = ""

            priority_dropdown.value = "Low"

            try:
                self.subcat_holder.update()
            except Exception as ex:
                print(f"[CATEGORY_CHANGE] subcat_holder.update warning: {ex}")
            try:
                custom_cat_field.update()
            except Exception:
                pass
            try:
                priority_dropdown.update()
            except Exception:
                pass
            try:
                self.page.update()
            except Exception as ex:
                print(f"[CATEGORY_CHANGE] page.update warning: {ex}")

        self.category_dropdown = category_dropdown = ft.Dropdown(
            label="Category",
            options=cat_options,
            dense=True,
            expand=True,
            on_select=on_cat_change
        )
        self.category_dropdown.on_select = on_cat_change
        self.category_dropdown.on_change = on_cat_change

        loc_options = [ft.dropdown.Option(l["id"], l["name"]) for l in self.locations]
        loc_options.append(ft.dropdown.Option("OTHER", "Other / Custom Location"))
        location_dropdown = ft.Dropdown(label="Location", options=loc_options, dense=True, expand=True)
        custom_loc_field = ft.TextField(label="Specify Custom Location", dense=True, visible=False, expand=True)

        def on_loc_change(e):
            custom_loc_field.visible = (location_dropdown.value == "OTHER")
            self.page.update()

        location_dropdown.on_select = on_loc_change
        location_dropdown.on_change = on_loc_change

        anonymous_checkbox = ft.Checkbox(
            label="Submit Anonymously (Identity strictly hidden from all staff & administration)",
            value=False
        )

        is_approved_hostel = self.student.get("is_hostel_approved", False)
        hostel_checkbox = ft.Checkbox(
            label="Hostel-related Complaint",
            value=False,
            disabled=not is_approved_hostel
        )
        hostel_note = ft.Text(
            "Hostel complaints require Hostel Incharge residency approval." if not is_approved_hostel else "Enabled (Approved hostel resident).",
            size=11,
            color=colors["text_muted"] if is_approved_hostel else "#dc2626"
        )

        # File picker for attachments (Max 2)
        files_display = ft.Column(spacing=4)
        init_count = len(self.selected_files)
        attach_label = "Add Attachment (0/2)" if init_count == 0 else ("Add Another Attachment (1/2)" if init_count == 1 else "Maximum 2 Attachments Added")
        attach_btn = ft.ElevatedButton(
            content=ft.Text(attach_label),
            icon=ft.Icons.ATTACH_FILE,
            disabled=(init_count >= 2)
        )

        def update_attach_btn():
            count = len(self.selected_files)
            if count == 0:
                attach_btn.disabled = False
                attach_btn.content = ft.Text("Add Attachment (0/2)")
            elif count == 1:
                attach_btn.disabled = False
                attach_btn.content = ft.Text("Add Another Attachment (1/2)")
            else:
                attach_btn.disabled = True
                attach_btn.content = ft.Text("Maximum 2 Attachments Added")
            self.page.update()

        # In-form alert box
        alert_box = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.WHITE),
                    ft.Text("", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.WHITE, expand=True)
                ],
                spacing=10
            ),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            visible=False
        )

        def show_alert(msg: str, is_error: bool = True):
            alert_box.visible = True
            alert_box.bgcolor = "#dc2626" if is_error else "#059669"
            alert_box.content.controls[0].name = ft.Icons.ERROR_OUTLINE if is_error else ft.Icons.CHECK_CIRCLE_OUTLINE
            alert_box.content.controls[1].value = msg
            self.page.update()

        def remove_file(idx: int):
            if 0 <= idx < len(self.selected_files):
                removed = self.selected_files.pop(idx)
                if removed.get("is_temp") and removed.get("path"):
                    try:
                        p = removed["path"]
                        if os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass
                show_feedback_message(self.page, f"Removed {removed.get('name', 'attachment')}", is_error=False)
                refresh_files_display()
                update_attach_btn()

        def refresh_files_display(update_page: bool = True):
            files_display.controls.clear()
            for idx, f in enumerate(self.selected_files):
                f_name = f.get("name", "attachment")
                f_size = f.get("size", 0)
                size_str = f"{f_size / 1024:.1f} KB" if f_size else ""

                def make_remover(i):
                    return lambda _: remove_file(i)

                del_btn = ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color="#dc2626",
                    tooltip=f"Remove {f_name}",
                    icon_size=20,
                    on_click=make_remover(idx)
                )

                files_display.controls.append(
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.ATTACH_FILE, size=16, color=colors["primary"]),
                                        ft.Text(f"{f_name} ({size_str})", size=13, weight=ft.FontWeight.W_500, color=colors["text"])
                                    ],
                                    spacing=8
                                ),
                                del_btn
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER
                        ),
                        bgcolor=colors.get("surface_variant", "#f1f5f9"),
                        padding=ft.padding.symmetric(horizontal=12, vertical=4),
                        border_radius=8,
                        border=ft.Border.all(1, colors["border"])
                    )
                )
            if update_page:
                try:
                    self.page.update()
                except Exception:
                    pass

        # Populate pre-existing attachments if any
        if self.selected_files:
            refresh_files_display(update_page=False)

        async def on_pick_attachment(e):
            if len(self.selected_files) >= 2:
                show_feedback_message(self.page, "Maximum 2 attachments allowed.", is_error=True)
                return
            attach_btn.disabled = True
            attach_btn.content = ft.Text("Opening Picker...")
            self.page.update()

            try:
                files = await self.file_picker.pick_files(
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["jpg", "jpeg", "png", "webp", "mp4", "mov", "pdf"],
                    allow_multiple=False,
                    with_data=False,
                    cancel_upload_on_window_blur=False
                )
                if not files:
                    return

                for f in files:
                    if len(self.selected_files) >= 2:
                        show_feedback_message(self.page, "Maximum 2 attachments allowed.", is_error=True)
                        break
                    valid, err = validate_attachment(f.name, f.size)
                    if not valid:
                        show_feedback_message(self.page, err, is_error=True)
                        continue

                    # If local desktop file path exists directly
                    if f.path and os.path.exists(f.path):
                        self.selected_files.append({
                            "name": f.name,
                            "path": f.path,
                            "bytes": None,
                            "size": f.size,
                            "is_temp": False
                        })
                    else:
                        # Web / mobile stream: Upload file to private temp server storage via HTTP PUT
                        attach_btn.content = ft.Text(f"Attaching {f.name[:12]}...")
                        self.page.update()

                        ext = os.path.splitext(f.name)[1].lower()
                        clean_sid = str(self.student_id).replace("-", "")
                        temp_rel_path = f"temp/{clean_sid}/{uuid.uuid4().hex}{ext}"
                        upload_url = self.page.get_upload_url(temp_rel_path, 3600)

                        # Track upload state with a simple mutable flag instead of
                        # a Future. On mobile browsers the WebSocket can briefly
                        # disconnect when the file-picker overlay appears, which
                        # makes Future-based tracking unreliable.
                        upload_state = {"done": False, "error": None}

                        def on_upload_evt(evt: ft.FilePickerUploadEvent):
                            if evt.error:
                                upload_state["error"] = evt.error
                                upload_state["done"] = True
                            elif (evt.progress is not None and evt.progress >= 0.99) or getattr(evt, "status", None) == "done":
                                upload_state["done"] = True

                        self.file_picker.on_upload = on_upload_evt
                        await self.file_picker.upload([
                            ft.FilePickerUploadFile(
                                name=f.name,
                                id=f.id,
                                upload_url=upload_url,
                                method="PUT"
                            )
                        ])

                        # Poll for completion: check both callback flag AND disk
                        # file presence. This survives WebSocket reconnects.
                        abs_disk_path = os.path.realpath(os.path.join(str(Path("uploads").resolve()), temp_rel_path))
                        for _poll in range(60):  # up to 30 seconds
                            if os.path.exists(abs_disk_path) and os.path.getsize(abs_disk_path) > 0:
                                break
                            if upload_state.get("error"):
                                break
                            await asyncio.sleep(0.5)

                        # Check upload result
                        if upload_state.get("error"):
                            show_feedback_message(self.page, f"Upload error: {upload_state['error']}", is_error=True)
                            continue
                        if os.path.exists(abs_disk_path) and os.path.getsize(abs_disk_path) > 0:
                            self.selected_files.append({
                                "name": f.name,
                                "path": abs_disk_path,
                                "bytes": None,
                                "size": os.path.getsize(abs_disk_path),
                                "is_temp": True
                            })
                        else:
                            show_feedback_message(self.page, f"Unable to attach {f.name}. Please try again.", is_error=True)
                            continue

                refresh_files_display()
            except Exception as ex:
                logger.warning("Attachment picker error: %s", ex)
                show_feedback_message(self.page, "Unable to select attachment. Please try again.", is_error=True)
            finally:
                update_attach_btn()

        attach_btn.on_click = on_pick_attachment

        submit_btn = ft.ElevatedButton(
            content=ft.Text("Submit Complaint"),
            icon=ft.Icons.SEND,
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def submit_form(e):
            val_desc, err = validate_description(desc_field.value or "")
            if not val_desc:
                show_alert(err, is_error=True)
                show_feedback_message(self.page, err, is_error=True)
                return

            cat_id = category_dropdown.value
            if not cat_id:
                show_alert("Please select a Category.", is_error=True)
                show_feedback_message(self.page, "Please select a Category.", is_error=True)
                return

            cat_name = ""
            for c in self.categories:
                if str(c.get("id")) == str(cat_id) or str(c.get("name")) == str(cat_id):
                    cat_name = str(c.get("name", ""))
                    break

            subcat_ctrl = getattr(self, "subcategory_dropdown", None) or subcat_holder.content
            selected_subcat = subcat_ctrl.value if subcat_ctrl else None
            custom_cat_val = (custom_cat_field.value or "").strip()

            selected_sub_name = ""
            if subcat_ctrl and getattr(subcat_ctrl, "options", None):
                for opt in subcat_ctrl.options:
                    if str(opt.key) == str(selected_subcat) or str(opt.text) == str(selected_subcat):
                        selected_sub_name = str(opt.text)
                        break

            is_other_cat = (cat_name.strip().lower() == "other")
            is_other_sub = (
                selected_subcat == "OTHER" or
                selected_sub_name.strip().lower() in ["other", "other complaint", "other / custom subcategory"]
            )

            if not selected_subcat and subcat_ctrl and getattr(subcat_ctrl, "options", None) and not is_other_cat:
                show_alert("Please select a Subcategory.", is_error=True)
                show_feedback_message(self.page, "Please select a Subcategory.", is_error=True)
                return

            if is_other_cat or is_other_sub or custom_cat_field.visible:
                if not custom_cat_val:
                    show_alert("Please specify the custom category/subcategory details (compulsory for Other).", is_error=True)
                    show_feedback_message(self.page, "Please specify the custom category/subcategory details.", is_error=True)
                    return

            subcat_id = None
            if selected_subcat and len(str(selected_subcat)) == 36 and "-" in str(selected_subcat):
                subcat_id = selected_subcat

            final_desc = desc_field.value or ""
            if custom_cat_val:
                final_desc = f"[Custom Subcategory: {custom_cat_val}]\n" + final_desc

            loc_id = location_dropdown.value if location_dropdown.value != "OTHER" else None
            custom_loc = custom_loc_field.value if location_dropdown.value == "OTHER" else None

            submit_btn.disabled = True
            submit_btn.content = ft.Text("Submitting Grievance...")
            alert_box.visible = False
            self.page.update()

            try:
                ok, msg, created_comp = ComplaintService.submit_complaint(
                    student_id=self.student_id,
                    title=title_field.value or "",
                    description=final_desc,
                    department_id=self.department_id,
                    category_id=category_dropdown.value,
                    subcategory_id=subcat_id,
                    location_id=loc_id,
                    priority=priority_dropdown.value or "Low",
                    is_anonymous=anonymous_checkbox.value,
                    is_hostel=hostel_checkbox.value,
                    location_custom=custom_loc,
                    category_custom=custom_cat_val if is_other_cat else None,
                    subcategory_custom=custom_cat_val if is_other_sub else None
                )

                if ok and created_comp:
                    cid = created_comp["complaint_id"]
                    for f_info in self.selected_files:
                        try:
                            StorageService.upload_attachment(
                                complaint_id=cid,
                                local_file_path=f_info.get("path"),
                                original_filename=f_info.get("name"),
                                file_bytes=f_info.get("bytes")
                            )
                            # Once stored in Supabase, remove temporary disk copy
                            if f_info.get("is_temp") and f_info.get("path"):
                                try:
                                    if os.path.exists(f_info["path"]):
                                        os.remove(f_info["path"])
                                except Exception:
                                    pass
                        except Exception as up_err:
                            logger.error("Error uploading attachment to Supabase: %s", up_err)

                    self.selected_files.clear()
                    show_feedback_message(self.page, f"Complaint #{cid} registered successfully!", is_error=False)
                    self.cached_complaints = None
                    self._switch_view(2)  # Switch to My Complaints
                else:
                    submit_btn.disabled = False
                    submit_btn.content = ft.Text("Submit Complaint")
                    show_alert(msg, is_error=True)
                    show_feedback_message(self.page, msg, is_error=True)
            except Exception as ex:
                submit_btn.disabled = False
                submit_btn.content = ft.Text("Submit Complaint")
                err_msg = "Unable to submit grievance. Please verify your connection."
                show_alert(err_msg, is_error=True)
                show_feedback_message(self.page, err_msg, is_error=True)

        submit_btn.on_click = submit_form

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Register New Grievance", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    alert_box,
                    title_field,
                    desc_field,
                    char_counter,
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(category_dropdown, col={"xs": 12, "sm": 6}),
                            self.subcat_holder
                        ]
                    ),
                    custom_cat_field,
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(location_dropdown, col={"xs": 12, "sm": 6}),
                            ft.Container(custom_loc_field, col={"xs": 12, "sm": 6})
                        ]
                    ),
                    ft.Row(controls=[priority_dropdown]),
                    anonymous_checkbox,
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(hostel_checkbox, col={"xs": 12, "sm": 6}),
                            ft.Container(hostel_note, col={"xs": 12, "sm": 6})
                        ]
                    ),
                    ft.Divider(color=colors["border"]),
                    ft.Text("Attachments (Max 2 files, up to 10MB each: JPG, PNG, WEBP, MP4, MOV, PDF)", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.Row(
                        controls=[
                            attach_btn
                        ]
                    ),
                    files_display,
                    ft.Divider(color=colors["border"]),
                    submit_btn
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=14,
            padding=24,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB 2: MY COMPLAINTS & EDITING
    # -------------------------------------------------------------------------
    def _render_my_complaints(self) -> ft.Control:
        self._ensure_reference_data_loaded()
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        search_field = ft.TextField(hint_text="Search complaints by ID, title, or description...", prefix_icon=ft.Icons.SEARCH, dense=True, expand=True)
        status_filter = ft.Dropdown(
            label="Status",
            options=[
                ft.dropdown.Option("ALL", "All Statuses"),
                ft.dropdown.Option("Pending", "Pending"),
                ft.dropdown.Option("In Progress", "In Progress"),
                ft.dropdown.Option("Resolved", "Resolved"),
                ft.dropdown.Option("Rejected", "Rejected")
            ],
            value="ALL",
            dense=True,
            width=140
        )
        priority_filter = ft.Dropdown(
            label="Priority",
            options=[
                ft.dropdown.Option("ALL", "All Priorities"),
                ft.dropdown.Option("Urgent", "Urgent"),
                ft.dropdown.Option("High", "High"),
                ft.dropdown.Option("Medium", "Medium"),
                ft.dropdown.Option("Low", "Low")
            ],
            value="ALL",
            dense=True,
            width=140
        )

        cat_filter_opts = [ft.dropdown.Option("ALL", "All Categories")]
        for c in self.categories:
            cat_filter_opts.append(ft.dropdown.Option(str(c.get("name")), str(c.get("name"))))

        category_filter = ft.Dropdown(
            label="Category",
            options=cat_filter_opts,
            value="ALL",
            dense=True,
            width=160
        )

        subcat_filter_opts = [ft.dropdown.Option("ALL", "All Subcategories")]
        subcategory_filter = ft.Dropdown(
            label="Subcategory",
            options=subcat_filter_opts,
            value="ALL",
            dense=True,
            width=160
        )

        complaints_container = ft.Column(spacing=8)

        def update_subcat_options(c_val=None):
            if c_val is None:
                c_val = category_filter.value or "ALL"
            new_opts = [ft.dropdown.Option("ALL", "All Subcategories")]
            if c_val != "ALL":
                subs = []
                key = c_val.strip().lower()
                if key in self.subcategories_by_cat:
                    subs = self.subcategories_by_cat[key]
                elif c_val in PRACTICAL_SUBCATEGORIES:
                    subs = [{"name": s} for s in PRACTICAL_SUBCATEGORIES[c_val]]
                for s in subs:
                    s_name = s.get("name") if isinstance(s, dict) else str(s)
                    new_opts.append(ft.dropdown.Option(s_name, s_name))
            subcategory_filter.options = new_opts
            subcategory_filter.value = "ALL"
            try:
                subcategory_filter.update()
            except Exception:
                pass
            self.page.update()

        def load_data(force: bool = False):
            if force or self.cached_complaints is None:
                self.cached_complaints = ComplaintService.get_complaints_for_user(
                    role="Student",
                    user_id=self.student_id,
                    department_id=self.department_id
                )
            return self.cached_complaints

        def reset_filters(e=None):
            search_field.value = ""
            status_filter.value = "ALL"
            priority_filter.value = "ALL"
            category_filter.value = "ALL"
            subcategory_filter.options = [ft.dropdown.Option("ALL", "All Subcategories")]
            subcategory_filter.value = "ALL"
            refresh_list(force_reload=False)

        def refresh_list(force_reload: bool = False):
            complaints = load_data(force=force_reload)
            query = (search_field.value or "").strip().lower()
            st_val = (status_filter.value or "ALL").strip()
            pr_val = (priority_filter.value or "ALL").strip()
            cat_val = (category_filter.value or "ALL").strip()
            sub_val = (subcategory_filter.value or "ALL").strip()

            filtered = []
            for c in complaints:
                cid_str = str(c.get("complaint_id", ""))
                title = (c.get("title") or "").lower()
                desc = (c.get("description") or "").lower()
                c_st = (c.get("status") or "").strip()
                c_pr = (c.get("priority") or "").strip()

                cat_obj = c.get("categories")
                c_cat = cat_obj.get("name") if isinstance(cat_obj, dict) else (c.get("category_name") or c.get("category_custom") or "")
                sub_obj = c.get("subcategories")
                c_sub = sub_obj.get("name") if isinstance(sub_obj, dict) else (c.get("subcategory_name") or c.get("subcategory_custom") or "")

                if query and (query not in cid_str and query not in title and query not in desc):
                    continue
                if st_val != "ALL" and c_st.lower() != st_val.lower():
                    continue
                if pr_val != "ALL" and c_pr.lower() != pr_val.lower():
                    continue
                if cat_val != "ALL" and str(c_cat).strip().lower() != cat_val.lower():
                    continue
                if sub_val != "ALL" and str(c_sub).strip().lower() != sub_val.lower():
                    continue
                filtered.append(c)

            def confirm_delete_complaint(comp: Dict[str, Any]):
                cid = comp.get("complaint_id")
                confirm_btn = ft.ElevatedButton(
                    content=ft.Text("Yes, Delete"),
                    style=ft.ButtonStyle(bgcolor="#dc2626", color=ft.Colors.WHITE)
                )

                def do_delete(ev):
                    confirm_btn.disabled = True
                    confirm_btn.content = ft.Text("Deleting...")
                    self.page.update()
                    ok, msg = ComplaintService.delete_complaint_by_student(cid, self.student_id)
                    close_dialog(self.page, del_dlg)
                    if ok:
                        show_feedback_message(self.page, msg, is_error=False)
                        self.cached_complaints = None
                        refresh_list(force_reload=True)
                    else:
                        show_feedback_message(self.page, msg, is_error=True)
                        self.page.update()

                confirm_btn.on_click = do_delete

                del_dlg = ft.AlertDialog(
                    title=ft.Text("Confirm Deletion", weight=ft.FontWeight.BOLD, color=colors["text"]),
                    content=ft.Text(f"Are you sure you want to delete Complaint #{cid}? This action cannot be undone.", size=14, color=colors["text"]),
                    bgcolor=colors["surface"],
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, del_dlg)),
                        confirm_btn
                    ]
                )
                open_dialog(self.page, del_dlg)

            cards = [create_complaint_card(c, self._open_detail_dialog, is_staff=False, on_delete=confirm_delete_complaint) for c in filtered]
            if not cards:
                cards.append(
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Icon(ft.Icons.SEARCH_OFF, size=36, color=colors["text_muted"]),
                                ft.Text("No grievances found matching your search or filter criteria.", size=14, color=colors["text_muted"]),
                                ft.ElevatedButton("Reset Filters", icon=ft.Icons.CLEAR_ALL, on_click=reset_filters)
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=10
                        ),
                        alignment=ft.Alignment.CENTER,
                        padding=40
                    )
                )

            complaints_container.controls = cards
            self.page.update()

        def on_cat_filter_change(e):
            c_val = getattr(e, "data", None) or getattr(e.control, "value", None) or category_filter.value or "ALL"
            category_filter.value = c_val
            update_subcat_options(c_val)
            refresh_list(force_reload=False)

        search_field.on_change = lambda _: refresh_list(force_reload=False)
        status_filter.on_select = lambda _: refresh_list(force_reload=False)
        status_filter.on_change = lambda _: refresh_list(force_reload=False)
        priority_filter.on_select = lambda _: refresh_list(force_reload=False)
        priority_filter.on_change = lambda _: refresh_list(force_reload=False)
        category_filter.on_select = on_cat_filter_change
        category_filter.on_change = on_cat_filter_change
        subcategory_filter.on_select = lambda _: refresh_list(force_reload=False)
        subcategory_filter.on_change = lambda _: refresh_list(force_reload=False)

        refresh_list(force_reload=False)

        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("My Complaints", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Row(
                            controls=[
                                ft.IconButton(
                                    icon=ft.Icons.REFRESH,
                                    tooltip="Refresh from Server",
                                    on_click=lambda _: refresh_list(force_reload=True)
                                ),
                                ft.ElevatedButton(
                                    content=ft.Text("Submit New"),
                                    icon=ft.Icons.ADD,
                                    style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE),
                                    on_click=lambda _: self._switch_view(1)
                                )
                            ],
                            spacing=8
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True
                ),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(search_field, col={"xs": 12, "md": 4}),
                        ft.Container(status_filter, col={"xs": 6, "sm": 3, "md": 2}),
                        ft.Container(priority_filter, col={"xs": 6, "sm": 3, "md": 2}),
                        ft.Container(category_filter, col={"xs": 6, "sm": 3, "md": 2}),
                        ft.Container(subcategory_filter, col={"xs": 6, "sm": 3, "md": 2}),
                    ],
                    spacing=8,
                    run_spacing=8
                ),
                ft.Divider(color=colors["border"]),
                complaints_container
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=14,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB 3: FEEDBACK
    # -------------------------------------------------------------------------
    def _render_feedback(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        if self.cached_complaints is None:
            self.cached_complaints = ComplaintService.get_complaints_for_user(
                role="Student",
                user_id=self.student_id,
                department_id=self.department_id
            )
        complaints = [c for c in (self.cached_complaints or []) if c.get("status") == "Resolved"]

        feedback_cards = []
        for c in complaints:
            cid = c.get("complaint_id")
            title = c.get("title")

            def open_feedback_dialog(e, comp_id=cid, c_title=title):
                st_id_field = ft.TextField(label="Confirm Student Roll Number", value=self.roll_number, disabled=True, dense=True)
                st_pass_field = ft.TextField(label="Enter Account Password", password=True, can_reveal_password=True, dense=True)
                rating_slider = ft.Slider(min=1, max=5, divisions=4, value=5, label="{value} Stars")
                rating_text = ft.Text("Rating: 5 / 5 Stars", weight=ft.FontWeight.BOLD, color=colors["text"])
                comment_field = ft.TextField(label="Comments (Optional)", multiline=True, dense=True)

                submit_fb_btn = ft.ElevatedButton(
                    content=ft.Text("Submit Rating"),
                    style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
                )

                def on_slider_change(ev):
                    rating_text.value = f"Rating: {int(rating_slider.value)} / 5 Stars"
                    self.page.update()

                rating_slider.on_change = on_slider_change

                def do_submit_feedback(ev):
                    submit_fb_btn.disabled = True
                    submit_fb_btn.content = ft.Text("Submitting...")
                    self.page.update()

                    ok, msg, fb = FeedbackService.submit_feedback(
                        student_id=self.student_id,
                        roll_number=self.roll_number,
                        password=st_pass_field.value or "",
                        complaint_id=comp_id,
                        rating=int(rating_slider.value),
                        comment=comment_field.value
                    )

                    submit_fb_btn.disabled = False
                    submit_fb_btn.content = ft.Text("Submit Rating")

                    if ok:
                        show_feedback_message(self.page, msg, is_error=False)
                        close_dialog(self.page, dlg)
                        self._switch_view(3)
                    else:
                        show_feedback_message(self.page, msg, is_error=True)
                        self.page.update()

                submit_fb_btn.on_click = do_submit_feedback

                dlg = ft.AlertDialog(
                    title=ft.Text(f"Provide Feedback on #{comp_id}", weight=ft.FontWeight.BOLD, color=colors["text"]),
                    content=ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Text(f"Issue: {c_title}", size=13, color=colors["text_muted"]),
                                st_id_field,
                                st_pass_field,
                                rating_text,
                                rating_slider,
                                comment_field
                            ],
                            spacing=10
                        ),
                        width=460,
                        height=320
                    ),
                    bgcolor=colors["surface"],
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                        submit_fb_btn
                    ]
                )
                open_dialog(self.page, dlg)

            feedback_cards.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text(f"Complaint #{cid}: {title}", size=15, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                    ft.Text("Status: Resolved", size=12, color="#059669")
                                ],
                                expand=True
                            ),
                            ft.ElevatedButton(
                                content=ft.Text("Give Feedback"),
                                icon=ft.Icons.STAR_RATE,
                                style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE),
                                on_click=open_feedback_dialog
                            )
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        wrap=True
                    ),
                    bgcolor=colors["surface"],
                    border=ft.Border.all(1, colors["border"]),
                    border_radius=10,
                    padding=16,
                    margin=ft.margin.only(bottom=8)
                )
            )

        if not feedback_cards:
            feedback_cards.append(
                ft.Container(
                    content=ft.Text("No resolved complaints waiting for feedback.", size=14, color=colors["text_muted"]),
                    padding=40
                )
            )

        return ft.Column(
            controls=[
                ft.Text("Resolution Feedback & Quality Rating", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Text("Feedback can only be submitted for Resolved grievances.", size=13, color=colors["text_muted"]),
                ft.Column(controls=feedback_cards, spacing=8)
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=14,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB 4: HOSTEL STATUS & RE-REQUEST
    # -------------------------------------------------------------------------
    def _render_hostel_status(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        req = HostelService.get_student_hostel_request(self.student_id)

        if not req:
            return ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("Hostel Access Status", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Text("You have not requested hostel accommodation yet.", size=14, color=colors["text_muted"]),
                        ft.ElevatedButton(
                            content=ft.Text("Request Hostel Access"),
                            icon=ft.Icons.HOTEL,
                            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE),
                            on_click=self._open_hostel_request_modal
                        )
                    ],
                    spacing=16
                ),
                padding=24
            )

        status = req.get("status", "Pending")
        status_color = "#d97706" if status == "Pending" else ("#059669" if status == "Approved" else "#dc2626")

        rows = [
            ft.Text("Hostel Access Status", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text("Status:", size=14, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Container(
                            content=ft.Text(status, size=13, weight=ft.FontWeight.BOLD, color=status_color),
                            bgcolor=ft.Colors.with_opacity(0.12, status_color),
                            border_radius=8,
                            padding=ft.padding.symmetric(horizontal=10, vertical=4)
                        )
                    ],
                    spacing=8
                )
            ),
            ft.Text(f"Hostel: {req.get('hostel_name')} | Block: {req.get('block')} | Room: {req.get('room_number')}", size=14, color=colors["text"])
        ]

        if status == "Denied":
            rows.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Denial Reason from Hostel Incharge:", weight=ft.FontWeight.BOLD, color="#dc2626", size=13),
                            ft.Text(req.get("deny_reason", "No reason specified"), size=13, color="#991b1b")
                        ]
                    ),
                    bgcolor="#450a0a" if is_dark else "#fef2f2",
                    border=ft.Border.all(1, "#991b1b" if is_dark else "#fecaca"),
                    border_radius=8,
                    padding=12
                )
            )
            rows.append(
                ft.ElevatedButton(
                    content=ft.Text("Submit New Request"),
                    icon=ft.Icons.REFRESH,
                    style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE),
                    on_click=self._open_hostel_request_modal
                )
            )

        return ft.Container(
            content=ft.Column(controls=rows, spacing=14),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=14,
            padding=24,
            expand=True
        )

    def _open_hostel_request_modal(self, e):
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        h_name = ft.TextField(label="Hostel Name", value="Boys Hostel Block A", dense=True)
        h_block = ft.TextField(label="Block", value="A", dense=True)
        h_room = ft.TextField(label="Room Number", value="101", dense=True)

        submit_req_btn = ft.ElevatedButton(
            content=ft.Text("Submit Request"),
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def do_req(ev):
            submit_req_btn.disabled = True
            submit_req_btn.content = ft.Text("Submitting...")
            self.page.update()

            ok, msg, req = HostelService.submit_hostel_request(
                student_id=self.student_id,
                hostel_name=h_name.value or "",
                block=h_block.value or "",
                room_number=h_room.value or ""
            )

            submit_req_btn.disabled = False
            submit_req_btn.content = ft.Text("Submit Request")

            if ok:
                show_feedback_message(self.page, msg, is_error=False)
                close_dialog(self.page, dlg)
                self._switch_view(4)
            else:
                show_feedback_message(self.page, msg, is_error=True)
                self.page.update()

        submit_req_btn.on_click = do_req

        dlg = ft.AlertDialog(
            title=ft.Text("Hostel Accommodation Request", weight=ft.FontWeight.BOLD, color=colors["text"]),
            content=ft.Container(
                content=ft.Column(controls=[h_name, h_block, h_room], spacing=10),
                width=400,
                height=200
            ),
            bgcolor=colors["surface"],
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                submit_req_btn
            ]
        )
        open_dialog(self.page, dlg)

    def _open_detail_dialog(self, complaint: Dict[str, Any]):
        def on_updated():
            self.cached_complaints = None
            self._switch_view(self.selected_tab_index)

        show_complaint_detail_dialog(
            page=self.page,
            complaint=complaint,
            current_role="Student",
            current_user_id=self.student_id,
            current_dept_id=self.department_id,
            on_updated=on_updated
        )
