"""
ui/views/student_view.py: Student portal view with complaint submission wizard,
animated registered vs resolved chart, responsive reflow, loading state prevention,
private anonymous tracking, hostel status, and feedback rating.
"""

import os
import uuid
import logging
import time
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime
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
    COLOR_TEXT_MUTED, STATUS_COLORS, PRIORITY_COLORS, get_theme_colors, get_card_shadow,
    get_responsive_layout, get_text_style, get_button_style, get_input_style,
    SectionHeader, EmptyState, PageContainer, StatusBadge,
    SPACING, RADII, MOTION_NORMAL_MS
)
from ui.state import AppState
from ui.components.college_hero import create_dashboard_welcome_banner
from ui.flet_compat import show_feedback_message, open_dialog, close_dialog
from ui.components.stat_card import create_stat_card
from ui.components.complaint_card import create_complaint_card
from ui.components.complaint_detail import show_complaint_detail_dialog
from ui.components.animated_chart import (
    create_registered_vs_resolved_chart,
    create_priority_distribution_chart,
    create_category_distribution_chart
)
from utils.validators import validate_description
from ui.components.page_file_services import (
    ensure_complaint_attachment_state,
    clear_stale_picker_pending,
    get_complaint_file_picker,
    register_complaint_attachment_hooks,
    open_complaint_attachment_picker,
    _get_selected_files,
    _set_selected_files,
    _get_picker_pending,
    _set_picker_pending,
    _get_upload_active,
    _get_upload_queue,
    _notify_attachment_ui,
)
from models.user import UserRole
from models.complaint import (
    PRACTICAL_SUBCATEGORIES,
    PRACTICAL_SUBCATEGORIES_CONFIG,
    get_default_priority
)
from services.draft_recovery_service import (
    get_current_complaint_draft,
    save_complaint_draft,
    clear_complaint_draft,
    save_active_tab,
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
        try:
            if hasattr(self.page, "session") and self.page.session and hasattr(self.page.session, "store") and self.page.session.store:
                self.page.session.store.set("active_tab_index", initial_tab)
        except Exception:
            pass
        self.cached_complaints = None
        self._dashboard_loading = False
        self._dashboard_error: Optional[str] = None
        self._complaint_query_lock = threading.Lock()
        self._complaint_query_event: Optional[threading.Event] = None
        self._complaint_query_error: Optional[str] = None
        self.active_container = ft.Container(expand=True)
        self._tab_cache: Dict[int, ft.Control] = {}
        self._reference_loading = False
        self._reference_error = None
        from services.cache_service import CacheService
        reference_data = CacheService.get_cached_categories_and_subcategories()
        self.categories, self.subcategories_by_cat, self.locations = reference_data or ([], {}, [])

        # Page-level attachment state + singleton FilePicker (see page_file_services.py).
        # Uses session.store for persistence across WebSocket reconnects.
        ensure_complaint_attachment_state(self.page)
        clear_stale_picker_pending(self.page)
        self.file_picker = get_complaint_file_picker(self.page)
    def invalidate_tab_cache(self, index: Optional[int] = None):
        if index is None:
            self._tab_cache.clear()
        else:
            self._tab_cache.pop(index, None)

    def _viewport_width(self) -> Optional[float]:
        width = getattr(self.page, "width", None)
        return width if isinstance(width, (int, float)) else None

    def _viewport_layout(self) -> str:
        return get_responsive_layout(self._viewport_width())

    def _load_complaints(self, force: bool = False) -> List[Dict[str, Any]]:
        """Single-flight complaint fetch shared by dashboard and complaint list."""
        with self._complaint_query_lock:
            if self.cached_complaints is not None and not force:
                return self.cached_complaints
            event = self._complaint_query_event
            if event is None or event.is_set():
                event = threading.Event()
                self._complaint_query_event = event
                self._complaint_query_error = None
                is_owner = True
            else:
                is_owner = False

        if is_owner:
            try:
                self.cached_complaints = ComplaintService.get_complaints_for_user(
                    role="Student",
                    user_id=self.student_id,
                    department_id=self.department_id,
                    raise_errors=True,
                ) or []
            except Exception as exc:
                self._complaint_query_error = type(exc).__name__
            finally:
                event.set()
        else:
            event.wait()

        if self._complaint_query_error:
            raise RuntimeError("Student complaints are unavailable")
        return self.cached_complaints or []

    def render(self) -> ft.Control:
        self._switch_view(self.selected_tab_index)
        return self.active_container

    def _trigger_progressive_dashboard_load(self):
        """Asynchronously loads complaints in background thread and updates dashboard in-place."""
        if self._dashboard_loading:
            return
        self._dashboard_loading = True
        self._dashboard_error = None

        import threading
        def _fetch_worker():
            started_at = time.perf_counter()
            try:
                self._load_complaints()
                self._dashboard_error = None
                logger.info("Student dashboard complaints loaded in %.3fs", time.perf_counter() - started_at)
            except Exception as exc:
                self._dashboard_error = "Your complaints could not be loaded. Check your connection and retry."
                logger.warning("Student dashboard data unavailable (%s)", type(exc).__name__)
            finally:
                self._dashboard_loading = False
                self.invalidate_tab_cache(0)
                if self.selected_tab_index == 0:
                    self.active_container.content = self._render_dashboard()
                    try:
                        self.page.update()
                    except Exception:
                        pass

        threading.Thread(target=_fetch_worker, daemon=True).start()

    def _ensure_reference_data_loaded(self):
        if self.categories:
            return True

        from services.cache_service import CacheService
        cached = CacheService.get_cached_categories_and_subcategories()
        if cached:
            self.categories, self.subcategories_by_cat, self.locations = cached
            return True

        if not self._reference_loading:
            import threading
            self._reference_loading = True
            self._reference_error = None

            def load_reference_data():
                try:
                    data = CacheService.get_categories_and_subcategories()
                    self.categories, self.subcategories_by_cat, self.locations = data
                except Exception as exc:
                    self._reference_error = type(exc).__name__
                finally:
                    self._reference_loading = False
                    self.invalidate_tab_cache(1)
                    self.invalidate_tab_cache(2)
                    if self.selected_tab_index in (1, 2):
                        if self._reference_error:
                            self.active_container.content = self._reference_loading_view()
                        elif self.selected_tab_index == 1:
                            self.active_container.content = self._render_new_complaint()
                        else:
                            self.active_container.content = self._render_my_complaints()
                        try:
                            self.page.update()
                        except Exception:
                            pass

            threading.Thread(target=load_reference_data, daemon=True).start()
        return False

    def _reference_loading_view(self) -> ft.Control:
        colors = get_theme_colors(AppState.is_dark_mode)
        message = "Reference data is temporarily unavailable. Retry to load the form." if self._reference_error else "Loading complaint form options…"
        controls: List[ft.Control] = [
            ft.ProgressRing(width=22, height=22, stroke_width=2.5, color=colors["primary"]) if not self._reference_error else ft.Icon(ft.Icons.ERROR_OUTLINE, color="#dc2626"),
            ft.Text(message, size=14, color=colors["text_muted"]),
        ]
        if self._reference_error:
            def retry(_):
                self._reference_error = None
                self._ensure_reference_data_loaded()
                self.active_container.content = self._reference_loading_view()
                self.page.update()
            controls.append(ft.ElevatedButton("Retry", on_click=retry))
        return ft.Container(
            content=ft.Column(controls=controls, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14),
            alignment=ft.Alignment.CENTER,
            padding=32,
            expand=True,
        )

    def _switch_view(self, index: int):
        self.selected_tab_index = index
        try:
            if hasattr(self.page, "session") and self.page.session and hasattr(self.page.session, "store") and self.page.session.store:
                self.page.session.store.set("active_tab_index", index)
        except Exception:
            pass

        # Fast path: instant tab switching from cached controls
        if index in self._tab_cache:
            self.active_container.content = self._tab_cache[index]
            try:
                self.page.update()
            except Exception:
                pass
            return

        try:
            if index == 0:
                if self.cached_complaints is None:
                    self._trigger_progressive_dashboard_load()
                content = self._render_dashboard()
            elif index == 1:
                content = self._render_new_complaint()
            elif index == 2:
                content = self._render_my_complaints()
            elif index == 3:
                content = self._render_feedback()
            elif index == 4:
                content = self._render_hostel_status()
            elif index == 5:
                from ui.views.account_view import AccountView
                content = AccountView(
                    self.page,
                    self.student,
                    UserRole.STUDENT.value,
                    on_refresh=lambda: self._switch_view(self.selected_tab_index)
                ).render()
            else:
                content = self._render_dashboard()

            # Cache tab content for instant navigation (dashboard is cached once complaints loaded)
            if index != 0 or self.cached_complaints is not None:
                self._tab_cache[index] = content

            self.active_container.content = content
            self.page.update()
        except Exception as ex:
            logger.exception("Error switching student view to tab %s: %s", index, ex)

    # -------------------------------------------------------------------------
    # TAB 0: DASHBOARD
    # -------------------------------------------------------------------------
    def _student_hostel_summary_card(self, colors: Dict[str, Any], is_dark: bool) -> ft.Control:
        """Show the hostel approval state already present on the student profile."""
        approved = bool(self.student.get("is_hostel_approved", False))
        status_text = "Approved resident" if approved else "Request or review access"
        status_color = colors["success"] if approved else colors["primary"]
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(ft.Icons.HOTEL, color=status_color, size=22),
                        bgcolor=ft.Colors.with_opacity(0.10, status_color),
                        border_radius=RADII["md"],
                        padding=SPACING["md"],
                    ),
                    ft.Column(
                        controls=[
                            ft.Text("Hostel request", style=get_text_style("label", is_dark)),
                            ft.Row(
                                controls=[
                                    ft.Container(
                                        content=ft.Text(status_text, style=get_text_style("body_small", is_dark, color=status_color)),
                                        bgcolor=ft.Colors.with_opacity(0.10, status_color),
                                        border_radius=RADII["pill"],
                                        padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"]),
                                    )
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.TextButton(
                        "View status",
                        icon=ft.Icons.ARROW_FORWARD,
                        on_click=lambda _: self._switch_view(4),
                        style=get_button_style(is_dark, "text", "sm"),
                    ),
                ],
                spacing=SPACING["md"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=RADII["lg"],
            padding=SPACING["lg"],
            shadow=get_card_shadow(is_dark),
            animate=MOTION_NORMAL_MS,
        )

    def _render_dashboard(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        viewport = self._viewport_layout()
        is_compact = viewport != "desktop"
        dept_display = AppState.department_name or AppState.department_code or ""
        welcome_banner = create_dashboard_welcome_banner(
            user_name=self.student.get('full_name', 'Student'),
            roll_number=self.roll_number,
            year=self.student.get('year', ''),
            dept_name=dept_display,
            role_text="Student",
            on_new_complaint=lambda: self._switch_view(1),
            is_dark=is_dark,
            compact=is_compact
        )

        recent_header = ft.Row(
            controls=[
                ft.Text("Recent Complaints", size=18, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.TextButton(
                    content=ft.Row([
                        ft.Text("View All", size=13, weight=ft.FontWeight.W_600, color=colors["primary"]),
                        ft.Icon(ft.Icons.ARROW_FORWARD, size=14, color=colors["primary"])
                    ], spacing=4),
                    on_click=lambda _: self._switch_view(2)
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        )

        # Progressive Shell: If complaints are still loading in background, render skeleton cards immediately
        if self.cached_complaints is None:
            stats_row = ft.ResponsiveRow(
                controls=[
                    create_stat_card("Total Submitted", "—", ft.Icons.FOLDER_SPECIAL, colors["primary"], is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3}),
                    create_stat_card("Pending Review", "—", ft.Icons.HOURGLASS_EMPTY, "#d97706", is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3}),
                    create_stat_card("In Progress", "—", ft.Icons.AUTORENEW, "#2563eb", is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3}),
                    create_stat_card("Resolved", "—", ft.Icons.CHECK_CIRCLE, "#059669", is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3}),
                    create_stat_card("Rejected", "—", ft.Icons.CANCEL, "#dc2626", is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3})
                ],
                spacing=12,
                run_spacing=12
            )

            placeholder_chart = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row([
                            ft.ProgressRing(width=20, height=20, stroke_width=2.5, color=colors["primary"]),
                            ft.Text("Loading resolution analytics...", size=13, color=colors["text_muted"])
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                height=220,
                border_radius=16,
                bgcolor=colors.get("card_bg", colors.get("surface", "#ffffff")),
                border=ft.border.all(1, colors.get("border", "#e2e8f0")),
                alignment=ft.alignment.center,
                col={"xs": 12, "md": 7}
            )

            placeholder_prio = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row([
                            ft.ProgressRing(width=20, height=20, stroke_width=2.5, color=colors["primary"]),
                            ft.Text("Loading priority distribution...", size=13, color=colors["text_muted"])
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                height=220,
                border_radius=16,
                bgcolor=colors.get("card_bg", colors.get("surface", "#ffffff")),
                border=ft.border.all(1, colors.get("border", "#e2e8f0")),
                alignment=ft.alignment.center,
                col={"xs": 12, "md": 5}
            )

            charts_row = ft.ResponsiveRow(
                controls=[placeholder_chart, placeholder_prio],
                spacing=12,
                run_spacing=12
            )

            if self._dashboard_error:
                def retry_dashboard(_):
                    self._dashboard_error = None
                    self.invalidate_tab_cache(0)
                    self._trigger_progressive_dashboard_load()
                    self.active_container.content = self._render_dashboard()
                    self.page.update()

                loading_recent = ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.ERROR_OUTLINE, color="#dc2626"),
                        ft.Text(self._dashboard_error, size=13, color=colors["text_muted"], expand=True),
                        ft.ElevatedButton("Retry", icon=ft.Icons.REFRESH, on_click=retry_dashboard),
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                    padding=24,
                    border_radius=12,
                    bgcolor=colors.get("card_bg", colors.get("surface", "#ffffff")),
                    border=ft.border.all(1, colors.get("border", "#e2e8f0"))
                )
            else:
                loading_recent = ft.Container(
                    content=ft.Row([
                        ft.ProgressRing(width=20, height=20, stroke_width=2.5, color=colors["primary"]),
                        ft.Text("Loading your recent grievances...", size=13, color=colors["text_muted"])
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                    padding=28,
                    border_radius=12,
                    bgcolor=colors.get("card_bg", colors.get("surface", "#ffffff")),
                    border=ft.border.all(1, colors.get("border", "#e2e8f0"))
                )

            return PageContainer(ft.Column(
                controls=[
                    welcome_banner,
                    stats_row,
                    self._student_hostel_summary_card(colors, is_dark),
                    charts_row,
                    ft.Divider(color=colors["border"]),
                    recent_header,
                    loading_recent
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=16,
                expand=True
            ), padding=SPACING["md"] if viewport == "mobile" else SPACING["lg"], is_dark=is_dark)

        # Full Dashboard when data is ready
        complaints = self.cached_complaints
        total = len(complaints)
        pending = sum(1 for c in complaints if c.get("status") == "Pending")
        in_prog = sum(1 for c in complaints if c.get("status") == "In Progress")
        resolved = sum(1 for c in complaints if c.get("status") == "Resolved")
        rejected = sum(1 for c in complaints if c.get("status") == "Rejected")

        # Stat cards
        stats_row = ft.ResponsiveRow(
            controls=[
                create_stat_card("Total Submitted", str(total), ft.Icons.FOLDER_SPECIAL, colors["primary"], is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3}),
                create_stat_card("Pending Review", str(pending), ft.Icons.HOURGLASS_EMPTY, "#d97706", is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3}),
                create_stat_card("In Progress", str(in_prog), ft.Icons.AUTORENEW, "#2563eb", is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3}),
                create_stat_card("Resolved", str(resolved), ft.Icons.CHECK_CIRCLE, "#059669", is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3}),
                create_stat_card("Rejected", str(rejected), ft.Icons.CANCEL, "#dc2626", is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 6, "xl": 3})
            ],
            spacing=12,
            run_spacing=12
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
            recent_cards.append(EmptyState(
                "No complaints yet",
                "Report an issue and follow its progress here.",
                icon=ft.Icons.MARK_EMAIL_READ_OUTLINED,
                action=ft.ElevatedButton(
                    "Register First Complaint",
                    icon=ft.Icons.ADD,
                    style=get_button_style(is_dark),
                    on_click=lambda _: self._switch_view(1),
                ),
                is_dark=is_dark,
            ))

        return PageContainer(ft.Column(
            controls=[
                welcome_banner,
                stats_row,
                self._student_hostel_summary_card(colors, is_dark),
                charts_row,
                ft.Divider(color=colors["border"]),
                recent_header,
                ft.Column(controls=recent_cards, spacing=8)
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            expand=True
        ), padding=SPACING["md"] if viewport == "mobile" else SPACING["lg"], is_dark=is_dark)

    # -------------------------------------------------------------------------
    # TAB 1: NEW COMPLAINT WIZARD
    # -------------------------------------------------------------------------
    def _render_new_complaint(self) -> ft.Control:
        if not self._ensure_reference_data_loaded():
            return self._reference_loading_view()
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        draft = get_current_complaint_draft(self.page, expected_owner_id=self.student_id) or {}
        init_title = draft.get("title", "")
        init_desc = draft.get("description", "")
        init_cat = draft.get("category_id")
        init_sub = draft.get("subcategory_id")
        init_loc = draft.get("location_id")
        init_loc_custom = draft.get("location_custom", "")
        init_cat_custom = draft.get("category_custom", "")
        init_pri = draft.get("priority", "Low")
        init_anon = bool(draft.get("is_anonymous", False))
        init_hostel = bool(draft.get("is_hostel", False))
        student_obj = AppState.current_user if (AppState.current_user and str(AppState.current_user.get("id")) == str(self.student_id)) else self.student
        is_approved_hostel = bool(student_obj.get("is_hostel_approved", False))

        def _is_hostel_cat(raw_cat):
            if not raw_cat:
                return False
            raw_str = str(raw_cat).strip().lower()
            if raw_str == "hostel":
                return True
            for c in self.categories:
                if str(c.get("id", "")).strip().lower() == raw_str or str(c.get("name", "")).strip().lower() == raw_str:
                    return str(c.get("name", "")).strip().lower() == "hostel"
            return False

        if not is_approved_hostel and _is_hostel_cat(init_cat):
            init_cat = None
            init_sub = None
            init_hostel = False

        title_field = ft.TextField(
            label="Complaint Title",
            hint_text="Brief summary of the issue",
            value=init_title,
            dense=True
        )

        desc_len = len(init_desc)
        char_counter = ft.Text(
            f"{desc_len} / 1000 characters (min 10)",
            size=11,
            color="#059669" if (10 <= desc_len <= 1000) else ("#dc2626" if desc_len > 1000 else colors["text_muted"])
        )
        desc_field = ft.TextField(
            label="Detailed Description",
            hint_text="Explain the grievance clearly with location specifics (10 to 1000 characters).",
            value=init_desc,
            multiline=True,
            min_lines=3,
            max_lines=6,
            dense=True
        )

        def save_draft_state():
            try:
                subcat_val = None
                if hasattr(self, "subcategory_dropdown") and self.subcategory_dropdown:
                    subcat_val = self.subcategory_dropdown.value
                cat_val = getattr(self, "category_dropdown", None).value if hasattr(self, "category_dropdown") and self.category_dropdown else None
                d = {
                    "owner_id": str(self.student_id),
                    "title": title_field.value or "",
                    "description": desc_field.value or "",
                    "category_id": cat_val,
                    "subcategory_id": subcat_val,
                    "location_id": location_dropdown.value,
                    "priority": priority_dropdown.value or "Low",
                    "is_anonymous": bool(anonymous_checkbox.value),
                    "is_hostel": bool(hostel_checkbox.value),
                    "location_custom": custom_loc_field.value if location_dropdown.value == "OTHER" else None,
                    "category_custom": custom_cat_field.value or "",
                    "temp_files": _get_selected_files(self.page),
                }
                save_complaint_draft(self.page, d, owner_id=self.student_id)
            except Exception:
                pass

        def on_desc_change(e):
            n = len(desc_field.value or "")
            char_counter.value = f"{n} / 1000 characters (min 10)"
            char_counter.color = "#dc2626" if (n < 10 or n > 1000) else "#059669"
            save_draft_state()
            self.page.update()

        desc_field.on_change = on_desc_change
        title_field.on_change = lambda e: save_draft_state()

        cat_options = [
            ft.dropdown.Option(key=str(c["id"]), text=str(c["name"]))
            for c in self.categories
            if is_approved_hostel or str(c.get("name", "")).strip().lower() != "hostel"
        ]

        custom_cat_field = ft.TextField(
            label="Specify Custom Category / Subcategory (Compulsory)",
            hint_text="Please describe your specific issue in detail...",
            value=init_cat_custom,
            dense=True,
            visible=bool(init_cat_custom),
            expand=True
        )
        custom_cat_field.on_change = lambda e: save_draft_state()

        priority_dropdown = ft.Dropdown(
            label="Priority",
            options=[
                ft.dropdown.Option("Low"),
                ft.dropdown.Option("Medium"),
                ft.dropdown.Option("High")
            ],
            value=init_pri,
            dense=True,
            width=160
        )
        priority_dropdown.on_change = lambda e: save_draft_state()

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
            save_draft_state()

        def _build_subcategory_dropdown(raw_cat, preselected_sub=None):
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

            sub_val = None
            if preselected_sub:
                for opt in opts:
                    if str(opt.key) == str(preselected_sub) or str(opt.text) == str(preselected_sub):
                        sub_val = str(opt.key)
                        break

            new_subcat = ft.Dropdown(
                label=lbl,
                options=opts,
                value=sub_val,
                dense=True,
                expand=True,
                on_select=on_subcat_change
            )
            new_subcat.on_select = on_subcat_change
            new_subcat.on_change = on_subcat_change
            return new_subcat, cat_name

        if init_cat:
            init_subcat_ctrl, init_cat_name = _build_subcategory_dropdown(init_cat, init_sub)
            self.subcategory_dropdown = init_subcat_ctrl
            if (init_cat_name.strip().lower() == "other") or (init_sub == "OTHER"):
                custom_cat_field.visible = True
        else:
            self.subcategory_dropdown = ft.Dropdown(
                label="Subcategory (Select Category First)",
                options=[],
                dense=True,
                expand=True,
                on_select=on_subcat_change
            )
            self.subcategory_dropdown.on_select = on_subcat_change
            self.subcategory_dropdown.on_change = on_subcat_change

        self.subcat_holder = subcat_holder = ft.Container(content=self.subcategory_dropdown, col={"xs": 12, "sm": 6})

        def on_cat_change(e):
            raw_cat = getattr(e, "data", None) or getattr(e.control, "value", None) or (self.category_dropdown.value if hasattr(self, "category_dropdown") else None)
            if hasattr(self, "category_dropdown") and self.category_dropdown:
                self.category_dropdown.value = raw_cat

            new_subcat, cat_name = _build_subcategory_dropdown(raw_cat)
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
            save_draft_state()

        self.category_dropdown = category_dropdown = ft.Dropdown(
            label="Category",
            options=cat_options,
            value=init_cat,
            dense=True,
            expand=True,
            on_select=on_cat_change
        )
        self.category_dropdown.on_select = on_cat_change
        self.category_dropdown.on_change = on_cat_change

        loc_options = [ft.dropdown.Option(l["id"], l["name"]) for l in self.locations]
        loc_options.append(ft.dropdown.Option("OTHER", "Other / Custom Location"))
        location_dropdown = ft.Dropdown(label="Location", options=loc_options, value=init_loc, dense=True, expand=True)
        custom_loc_field = ft.TextField(label="Specify Custom Location", dense=True, value=init_loc_custom, visible=(init_loc == "OTHER"), expand=True)

        def on_loc_change(e):
            custom_loc_field.visible = (location_dropdown.value == "OTHER")
            save_draft_state()
            self.page.update()

        location_dropdown.on_select = on_loc_change
        location_dropdown.on_change = on_loc_change
        custom_loc_field.on_change = lambda e: save_draft_state()

        anonymous_checkbox = ft.Checkbox(
            label="Submit Anonymously (Identity strictly hidden from all staff & administration)",
            value=init_anon
        )
        anonymous_checkbox.on_change = lambda e: save_draft_state()

        is_approved_hostel = bool(student_obj.get("is_hostel_approved", False))
        hostel_checkbox = ft.Checkbox(
            label="Hostel-related Complaint",
            value=init_hostel if is_approved_hostel else False,
            disabled=not is_approved_hostel
        )
        hostel_checkbox.on_change = lambda e: save_draft_state()
        hostel_note = ft.Text(
            "Hostel complaints require Hostel Incharge residency approval." if not is_approved_hostel else "Enabled (Approved hostel resident).",
            size=11,
            color=colors["text_muted"] if is_approved_hostel else "#dc2626"
        )

        # File picker for attachments (Max 2)
        # Attachment state is stored in page.session.store (persists across Android WebSocket reconnects).
        # When Android opens the file manager, the WebSocket may briefly disconnect.
        # app.py will call render_portal_view() which creates a new StudentView,
        # but session store persists the already-selected files.

        files_display = ft.Column(spacing=SPACING["sm"])
        upload_progress_indicator = ft.Column(
            controls=[
                ft.ProgressBar(color=colors["primary"], bgcolor=colors["surface_variant"]),
                ft.Text("Preparing attachment upload…", style=get_text_style("caption", is_dark)),
            ],
            spacing=SPACING["xs"],
            visible=False,
        )

        def _get_count() -> int:
            return len(_get_selected_files(self.page))

        def _count_label() -> str:
            n = _get_count()
            if n == 0:
                return "Add Attachment (0/2)"
            elif n == 1:
                return "Add Another Attachment (1/2)"
            return "Maximum 2 Attachments Added"

        attach_btn = ft.ElevatedButton(
            content=ft.Text(_count_label()),
            icon=ft.Icons.ATTACH_FILE,
            disabled=(_get_count() >= 2)
        )

        def update_attach_btn():
            n = _get_count()
            pending = _get_picker_pending(self.page)
            uploading = _get_upload_active(self.page) or bool(_get_upload_queue(self.page))
            attach_btn.disabled = (n >= 2) or pending or uploading
            upload_progress_indicator.visible = uploading
            if pending:
                attach_btn.content = ft.Text("Opening Picker...")
            elif uploading:
                attach_btn.content = ft.Text("Uploading...")
            else:
                attach_btn.content = ft.Text(_count_label())
            try:
                attach_btn.update()
            except Exception:
                pass
            try:
                self.page.update()
            except Exception:
                pass

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
            files = _get_selected_files(self.page)
            if 0 <= idx < len(files):
                removed = files.pop(idx)
                _set_selected_files(self.page, files)
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
            for idx, f in enumerate(_get_selected_files(self.page)):
                f_name = f.get("name", "attachment")
                f_size = f.get("size", 0)
                if f_size and f_size >= 1024 * 1024:
                    size_str = f"{f_size / (1024 * 1024):.1f} MB"
                elif f_size:
                    size_str = f"{f_size / 1024:.1f} KB"
                else:
                    size_str = ""

                def make_remover(i):
                    return lambda _: remove_file(i)

                ext = f_name.rsplit(".", 1)[-1].lower() if "." in f_name else ""
                icon_name = ft.Icons.IMAGE if ext in ("jpg", "jpeg", "png", "webp") else (ft.Icons.PICTURE_AS_PDF if ext == "pdf" else (ft.Icons.VIDEO_FILE if ext in ("mp4", "mov") else ft.Icons.ATTACH_FILE))
                icon_color = "#2563eb" if ext in ("jpg", "jpeg", "png", "webp") else ("#dc2626" if ext == "pdf" else "#7c3aed")

                del_btn = ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color="#dc2626",
                    tooltip=f"Remove {f_name}",
                    icon_size=20,
                    width=44,
                    height=44,
                    on_click=make_remover(idx)
                )

                files_display.controls.append(
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Container(
                                            content=ft.Icon(icon_name, size=20, color=icon_color),
                                            bgcolor=ft.Colors.with_opacity(0.12, icon_color),
                                            border_radius=8,
                                            padding=8
                                        ),
                                        ft.Column(
                                            controls=[
                                                ft.Text(f_name, size=13, weight=ft.FontWeight.W_600, color=colors["text"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                                ft.Text(size_str, size=11, color=colors["text_muted"])
                                            ],
                                            spacing=2,
                                            expand=True
                                        )
                                    ],
                                    spacing=10,
                                    expand=True
                                ),
                                del_btn
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER
                        ),
                        bgcolor=colors.get("surface_variant", "#f1f5f9"),
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                        border_radius=10,
                        border=ft.Border.all(1, colors["border"])
                    )
                )
            if update_page:
                try:
                    self.page.update()
                except Exception:
                    pass
            save_draft_state()

# Populate pre-existing attachments if any
        if _get_selected_files(self.page):
            refresh_files_display(update_page=False)

        register_complaint_attachment_hooks(
            self.page,
            refresh_files_display=lambda: refresh_files_display(update_page=True),
            update_attach_btn=update_attach_btn,
            student_id=self.student_id,
        )

        def on_pick_attachment(e):
            if _get_picker_pending(self.page) or _get_upload_active(self.page):
                return
            open_complaint_attachment_picker(self.page)

        attach_btn.on_click = on_pick_attachment

        submit_btn = ft.ElevatedButton(
            content=ft.Text("Submit Complaint"),
            icon=ft.Icons.SEND,
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def submit_form(e):
            if submit_btn.disabled:
                return
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

            student_obj = AppState.current_user if (AppState.current_user and str(AppState.current_user.get("id")) == str(self.student_id)) else self.student
            if cat_name.strip().lower() == "hostel" and not bool(student_obj.get("is_hostel_approved", False)):
                msg = "You must have an approved hostel residency status to submit hostel complaints."
                show_alert(msg, is_error=True)
                show_feedback_message(self.page, msg, is_error=True)
                return

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
            title_val = title_field.value or ""
            category_id_val = category_dropdown.value
            priority_val = priority_dropdown.value or "Low"
            anonymous_val = bool(anonymous_checkbox.value)
            hostel_val = bool(hostel_checkbox.value)
            selected_files = list(_get_selected_files(self.page))

            submit_btn.disabled = True
            submit_btn.content = ft.Text("Submitting Grievance...")
            alert_box.visible = False
            self.page.update()

            def submit_complaint():
                try:
                    ok, msg, created_comp = ComplaintService.submit_complaint(
                        student_id=self.student_id,
                        title=title_val,
                        description=final_desc,
                        department_id=self.department_id,
                        category_id=category_id_val,
                        subcategory_id=subcat_id,
                        location_id=loc_id,
                        priority=priority_val,
                        is_anonymous=anonymous_val,
                        is_hostel=hostel_val,
                        location_custom=custom_loc,
                        category_custom=custom_cat_val if is_other_cat else None,
                        subcategory_custom=custom_cat_val if is_other_sub else None
                    )

                    if ok and created_comp:
                        cid = created_comp["complaint_id"]
                        for f_info in selected_files:
                            try:
                                StorageService.upload_attachment(
                                    complaint_id=cid,
                                    local_file_path=f_info.get("path"),
                                    original_filename=f_info.get("name"),
                                    file_bytes=f_info.get("bytes")
                                )
                                if f_info.get("is_temp") and f_info.get("path"):
                                    try:
                                        if os.path.exists(f_info["path"]):
                                            os.remove(f_info["path"])
                                    except Exception:
                                        pass
                            except Exception as up_err:
                                logger.warning("Attachment upload failed (%s)", type(up_err).__name__)

                        _set_selected_files(self.page, [])
                        clear_complaint_draft(self.page)
                        show_feedback_message(self.page, f"Complaint #{cid} registered successfully!", is_error=False)
                        self.cached_complaints = None
                        self.invalidate_tab_cache()
                        self._switch_view(2)
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
                    logger.warning("Student complaint submission failed (%s)", type(ex).__name__)

            self.page.run_thread(submit_complaint)

        submit_btn.on_click = submit_form

        # Four focused form stages. The original controls and their callbacks
        # remain attached; only their presentation is grouped by step.
        wizard_step_names = ["Details", "Category", "Attachments", "Review"]
        step_state = [0]
        stepper_header = ft.Container(margin=ft.margin.only(bottom=SPACING["xs"]))
        wizard_progress = ft.ProgressBar(
            value=0.25,
            color=colors["primary"],
            bgcolor=colors["surface_variant"],
            border_radius=RADII["pill"],
            height=5,
        )
        step_title = ft.Text("Step 1 of 4 · Details", style=get_text_style("label", is_dark))

        upload_dropzone = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED, size=32, color=colors["primary"]),
                    ft.Text("Click to add files or browse device", size=13, weight=ft.FontWeight.W_600, color=colors["text"]),
                    ft.Text("JPG, PNG, WEBP, MP4, MOV, PDF (Max 10MB each)", size=11, color=colors["text_muted"])
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4
            ),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.4, colors["primary"])),
            border_radius=12,
            padding=ft.padding.symmetric(vertical=16, horizontal=16),
            bgcolor=ft.Colors.with_opacity(0.04, colors["primary"]),
            alignment=ft.Alignment.CENTER,
            on_click=on_pick_attachment
        )

        def make_stepper_header(active_step: int) -> ft.Control:
            is_mobile = (self._viewport_layout() == "mobile")
            items: List[ft.Control] = []
            for idx, name in enumerate(wizard_step_names):
                active_or_done = idx <= active_step
                is_current = (idx == active_step)
                accent = colors["primary"] if active_or_done else colors["text_muted"]
                show_label = not is_mobile or is_current

                step_row_controls = [
                    ft.Container(
                        content=ft.Text(str(idx + 1), size=11, weight=ft.FontWeight.BOLD,
                                        color=ft.Colors.WHITE if active_or_done else colors["text_muted"]),
                        bgcolor=colors["primary"] if active_or_done else colors["surface_variant"],
                        border_radius=RADII["pill"], width=24, height=24,
                        alignment=ft.Alignment.CENTER,
                    ),
                ]
                if show_label:
                    step_row_controls.append(
                        ft.Text(name, style=get_text_style("body_small", is_dark,
                                                           color=accent,
                                                           weight=ft.FontWeight.W_600 if is_current else ft.FontWeight.NORMAL))
                    )

                items.append(ft.Container(
                    content=ft.Row(
                        controls=step_row_controls,
                        spacing=SPACING["xs"],
                        tight=True,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.08, colors["primary"]) if is_current else None,
                    border_radius=RADII["pill"],
                    padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"]),
                    animate=MOTION_NORMAL_MS,
                ))
                if idx < len(wizard_step_names) - 1:
                    items.append(ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14 if is_mobile else 16, color=colors["border"]))
            return ft.Container(
                content=ft.Row(controls=items, wrap=False, scroll=ft.ScrollMode.AUTO if is_mobile else None, spacing=SPACING["xs"]),
                padding=ft.padding.symmetric(vertical=SPACING["xs"]),
            )

        # Apply the shared input styling to the existing fields without
        # altering values, validators, or event handlers.
        shared_input_style = get_input_style(is_dark)
        for field in (title_field, desc_field, custom_cat_field, custom_loc_field):
            for property_name, property_value in shared_input_style.items():
                setattr(field, property_name, property_value)

        privacy_panel = ft.Container(
            content=ft.Column(
                controls=[
                    anonymous_checkbox,
                    ft.Text(
                        "When enabled, staff see the complaint details without your name, student ID, or roll number.",
                        style=get_text_style("body_small", is_dark),
                    ),
                ],
                spacing=SPACING["xs"],
            ),
            bgcolor=colors["surface_variant"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=RADII["md"],
            padding=SPACING["md"],
        )

        detail_header = SectionHeader(
            "Describe the issue",
            "Add a clear title and 10–1000 characters of detail.",
            is_dark=is_dark,
        )
        hostel_panel = ft.Container(
            content=ft.Column(controls=[hostel_checkbox, hostel_note], spacing=SPACING["xs"]),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=RADII["md"],
            padding=SPACING["md"],
        )
        category_step = ft.Column(
            controls=[
                SectionHeader("Categorize the complaint", "Choose a department category, location, and urgency.", is_dark=is_dark),
                ft.ResponsiveRow(controls=[
                    ft.Container(category_dropdown, col={"xs": 12, "sm": 6}),
                    self.subcat_holder,
                ], spacing=SPACING["sm"], run_spacing=SPACING["sm"]),
                custom_cat_field,
                ft.ResponsiveRow(controls=[
                    ft.Container(location_dropdown, col={"xs": 12, "sm": 6}),
                    ft.Container(custom_loc_field, col={"xs": 12, "sm": 6}),
                ], spacing=SPACING["sm"], run_spacing=SPACING["sm"]),
                priority_dropdown,
            ],
            spacing=SPACING["md"],
        )
        attachment_step = ft.Column(
            controls=[
                SectionHeader("Add attachments", "Optional · up to two files, maximum 10 MB each.", is_dark=is_dark),
                ft.Text("Accepted types: JPG, PNG, WEBP, MP4, MOV, PDF", style=get_text_style("body_small", is_dark)),
                upload_dropzone,
                ft.Row(controls=[attach_btn], wrap=True),
                upload_progress_indicator,
                files_display,
            ],
            spacing=SPACING["md"],
        )

        review_title = ft.Text("—", style=get_text_style("title", is_dark))
        review_category = ft.Text("—", style=get_text_style("body", is_dark))
        review_location = ft.Text("—", style=get_text_style("body", is_dark))
        review_priority = ft.Text("—", style=get_text_style("body", is_dark))
        review_privacy = ft.Text("—", style=get_text_style("body_small", is_dark))
        review_description = ft.Text("—", style=get_text_style("body_small", is_dark), selectable=True)
        review_attachments = ft.Text("No attachments", style=get_text_style("body_small", is_dark))
        review_step = ft.Column(
            controls=[
                SectionHeader("Review before submitting", "Check the complaint details and privacy choice.", is_dark=is_dark),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            review_title,
                            ft.Divider(color=colors["border"]),
                            review_description,
                            ft.Row([ft.Text("Category", style=get_text_style("label", is_dark)), review_category], wrap=True),
                            ft.Row([ft.Text("Location", style=get_text_style("label", is_dark)), review_location], wrap=True),
                            ft.Row([ft.Text("Priority", style=get_text_style("label", is_dark)), review_priority], wrap=True),
                            review_privacy,
                            review_attachments,
                        ],
                        spacing=SPACING["sm"],
                    ),
                    bgcolor=colors["surface_variant"],
                    border=ft.Border.all(1, colors["border"]),
                    border_radius=RADII["md"],
                    padding=SPACING["lg"],
                ),
            ],
            spacing=SPACING["md"],
        )
        wizard_steps = [
            [detail_header, title_field, desc_field, char_counter, privacy_panel, hostel_panel],
            [category_step],
            [attachment_step],
            [review_step, submit_btn],
        ]
        for controls_in_step in wizard_steps:
            for control in controls_in_step:
                control.visible = False
                control.animate_opacity = MOTION_NORMAL_MS

        back_btn = ft.OutlinedButton("Back", icon=ft.Icons.ARROW_BACK, visible=False)
        back_btn.height = 48
        next_btn = ft.ElevatedButton("Continue", icon=ft.Icons.ARROW_FORWARD, style=get_button_style(is_dark), height=48)
        wizard_actions = ft.Row(
            controls=[back_btn, next_btn],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        def set_wizard_step(index: int, update_page: bool = True):
            index = max(0, min(index, len(wizard_steps) - 1))
            step_state[0] = index
            if index == 3:
                selected_files = _get_selected_files(self.page)
                category_text = next((str(item.get("name", "")) for item in self.categories
                                      if str(item.get("id")) == str(category_dropdown.value)
                                      or str(item.get("name")) == str(category_dropdown.value)), "—")
                subcategory_control = getattr(self, "subcategory_dropdown", None)
                subcategory_text = ""
                if subcategory_control and getattr(subcategory_control, "options", None):
                    subcategory_text = next((str(option.text) for option in subcategory_control.options
                                             if str(option.key) == str(subcategory_control.value)), "")
                review_title.value = title_field.value or "Untitled complaint"
                review_description.value = desc_field.value or "—"
                review_category.value = " · ".join(value for value in (category_text, subcategory_text) if value) or "—"
                review_location.value = (custom_loc_field.value or "Other / Custom Location") if location_dropdown.value == "OTHER" else next(
                    (str(item.get("name", "")) for item in self.locations
                     if str(item.get("id")) == str(location_dropdown.value)), "—"
                )
                review_priority.value = priority_dropdown.value or "Low"
                review_privacy.value = "Anonymous complaint · your name and student identifiers are hidden from staff." if anonymous_checkbox.value else "Submitted with your student account details for staff follow-up."
                review_attachments.value = f"{len(selected_files)} attachment(s) selected" if selected_files else "No attachments"
            for step_idx, controls_in_step in enumerate(wizard_steps):
                for control in controls_in_step:
                    control.visible = step_idx == index
            stepper_header.content = make_stepper_header(index)
            wizard_progress.value = (index + 1) / len(wizard_steps)
            step_title.value = f"Step {index + 1} of {len(wizard_steps)} · {wizard_step_names[index]}"
            back_btn.visible = index > 0
            next_btn.visible = index < len(wizard_steps) - 1
            if update_page:
                self.page.update()

        back_btn.on_click = lambda _: set_wizard_step(step_state[0] - 1)
        next_btn.on_click = lambda _: set_wizard_step(step_state[0] + 1)
        set_wizard_step(0, update_page=False)

        return ft.Container(
            content=ft.Column(
                controls=[
                    SectionHeader("New Complaint", "A guided form with a review before submission.", icon=ft.Icons.ADD_CIRCLE_OUTLINE, is_dark=is_dark),
                    stepper_header,
                    wizard_progress,
                    step_title,
                    alert_box,
                    detail_header,
                    title_field,
                    desc_field,
                    char_counter,
                    privacy_panel,
                    hostel_panel,
                    category_step,
                    attachment_step,
                    review_step,
                    submit_btn,
                    wizard_actions,
                ],
                spacing=SPACING["md"],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            bgcolor=colors["card_bg"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=RADII["xl"],
            shadow=get_card_shadow(is_dark),
            padding=SPACING["lg"] if self._viewport_layout() == "mobile" else SPACING["2xl"],
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB 2: MY COMPLAINTS & EDITING
    # -------------------------------------------------------------------------
    def _render_my_complaints(self) -> ft.Control:
        if not self._ensure_reference_data_loaded():
            return self._reference_loading_view()
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
            expand=True
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
            expand=True
        )

        cat_filter_opts = [ft.dropdown.Option("ALL", "All Categories")]
        for c in self.categories:
            cat_filter_opts.append(ft.dropdown.Option(str(c.get("name")), str(c.get("name"))))

        category_filter = ft.Dropdown(
            label="Category",
            options=cat_filter_opts,
            value="ALL",
            dense=True,
            expand=True
        )

        subcat_filter_opts = [ft.dropdown.Option("ALL", "All Subcategories")]
        subcategory_filter = ft.Dropdown(
            label="Subcategory",
            options=subcat_filter_opts,
            value="ALL",
            dense=True,
            expand=True
        )

        complaints_container = ft.Column(spacing=8)
        complaint_list_loading = [False]

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
            return self._load_complaints(force=force)

        def reset_filters(e=None):
            search_field.value = ""
            status_filter.value = "ALL"
            priority_filter.value = "ALL"
            category_filter.value = "ALL"
            subcategory_filter.options = [ft.dropdown.Option("ALL", "All Subcategories")]
            subcategory_filter.value = "ALL"
            refresh_list(force_reload=False)

        def refresh_list(force_reload: bool = False):
            if complaint_list_loading[0]:
                return
            if force_reload or self.cached_complaints is None:
                complaint_list_loading[0] = True
                complaints_container.controls = [
                    ft.Container(
                        content=ft.Row(
                            controls=[ft.ProgressRing(width=20, height=20, stroke_width=2, color=colors["primary"]), ft.Text("Loading your complaints…", color=colors["text_muted"])],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        padding=24,
                        alignment=ft.Alignment.CENTER,
                    )
                ]
                self.page.update()

                def fetch_complaints():
                    try:
                        load_data(force=force_reload)
                        render_list()
                    except Exception as exc:
                        logger.warning("Student complaint list unavailable (%s)", type(exc).__name__)
                        complaints_container.controls = [
                            ft.Container(
                                content=ft.Column(
                                    controls=[
                                        ft.Icon(ft.Icons.ERROR_OUTLINE, color="#dc2626"),
                                        ft.Text("Your complaints could not be loaded. Check your connection and retry.", color=colors["text_muted"], text_align=ft.TextAlign.CENTER),
                                        ft.ElevatedButton("Retry", icon=ft.Icons.REFRESH, on_click=lambda _: refresh_list(force_reload=True)),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=10,
                                ),
                                padding=24,
                                alignment=ft.Alignment.CENTER,
                            )
                        ]
                        try:
                            self.page.update()
                        except Exception:
                            pass

                    finally:
                        complaint_list_loading[0] = False

                self.page.run_thread(fetch_complaints)
                return
            render_list()

        def render_list():
            complaints = load_data(force=False) or []
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
                    if confirm_btn.disabled:
                        return
                    confirm_btn.disabled = True
                    confirm_btn.content = ft.Text("Deleting...")
                    self.page.update()

                    def delete_complaint():
                        try:
                            ok, msg = ComplaintService.delete_complaint_by_student(cid, self.student_id)
                            close_dialog(self.page, del_dlg)
                            if ok:
                                show_feedback_message(self.page, msg, is_error=False)
                                self.cached_complaints = None
                                self.invalidate_tab_cache()
                                refresh_list(force_reload=True)
                            else:
                                show_feedback_message(self.page, msg, is_error=True)
                        except Exception as exc:
                            logger.warning("Student complaint delete failed (%s)", type(exc).__name__)
                            show_feedback_message(self.page, "Unable to delete complaint. Please try again.", is_error=True)
                        finally:
                            confirm_btn.disabled = False
                            confirm_btn.content = ft.Text("Yes, Delete")
                            try:
                                self.page.update()
                            except Exception:
                                pass

                    self.page.run_thread(delete_complaint)

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
                cards.append(EmptyState(
                    "No matching complaints",
                    "Try changing your search or filters.",
                    icon=ft.Icons.SEARCH_OFF,
                    action=ft.OutlinedButton("Reset Filters", icon=ft.Icons.CLEAR_ALL, on_click=reset_filters),
                    is_dark=is_dark,
                ))

            complaints_container.controls = cards
            self.page.update()

        def on_cat_filter_change(e):
            c_val = getattr(e, "data", None) or getattr(e.control, "value", None) or category_filter.value or "ALL"
            category_filter.value = c_val
            update_subcat_options(c_val)
            refresh_list(force_reload=False)

        student_search_timer = [None]
        def on_student_search(e):
            if student_search_timer[0]:
                student_search_timer[0].cancel()
            import threading
            student_search_timer[0] = threading.Timer(0.15, lambda: refresh_list(force_reload=False))
            student_search_timer[0].daemon = True
            student_search_timer[0].start()

        search_field.on_change = on_student_search
        status_filter.on_select = lambda _: refresh_list(force_reload=False)
        status_filter.on_change = lambda _: refresh_list(force_reload=False)
        priority_filter.on_select = lambda _: refresh_list(force_reload=False)
        priority_filter.on_change = lambda _: refresh_list(force_reload=False)
        category_filter.on_select = on_cat_filter_change
        category_filter.on_change = on_cat_filter_change
        subcategory_filter.on_select = lambda _: refresh_list(force_reload=False)
        subcategory_filter.on_change = lambda _: refresh_list(force_reload=False)

        refresh_list(force_reload=False)

        viewport = self._viewport_layout()
        filter_controls = ft.ResponsiveRow(
            controls=[
                ft.Container(search_field, col={"xs": 12, "md": 4}),
                ft.Container(status_filter, col={"xs": 6, "sm": 6, "md": 2}),
                ft.Container(priority_filter, col={"xs": 6, "sm": 6, "md": 2}),
                ft.Container(category_filter, col={"xs": 6, "sm": 6, "md": 2}),
                ft.Container(subcategory_filter, col={"xs": 6, "sm": 6, "md": 2}),
            ],
            spacing=SPACING["sm"],
            run_spacing=SPACING["sm"],
        )
        filters_panel: ft.Control
        if viewport == "mobile":
            filters_panel = ft.ExpansionTile(
                title="Filters",
                subtitle="Status, priority, category and search",
                leading=ft.Icons.FILTER_LIST,
                controls=[filter_controls],
                expanded=False,
                bgcolor=colors["surface"],
                collapsed_bgcolor=colors["surface"],
                text_color=colors["text"],
                icon_color=colors["primary"],
                shape=ft.RoundedRectangleBorder(radius=RADII["md"]),
                collapsed_shape=ft.RoundedRectangleBorder(radius=RADII["md"]),
            )
        else:
            filters_panel = ft.Container(
                content=filter_controls,
                bgcolor=colors["surface"],
                border=ft.Border.all(1, colors["border"]),
                border_radius=RADII["md"],
                padding=SPACING["md"],
            )

        return PageContainer(ft.Column(
            controls=[
                SectionHeader(
                    "My Complaints",
                    "Track status, review updates, and manage your submissions.",
                    icon=ft.Icons.INVENTORY_2_OUTLINED,
                    action=ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.REFRESH,
                                tooltip="Refresh from Server",
                                on_click=lambda _: refresh_list(force_reload=True),
                            ),
                            ft.ElevatedButton(
                                content=ft.Text("Submit New"),
                                icon=ft.Icons.ADD,
                                style=get_button_style(is_dark),
                                on_click=lambda _: self._switch_view(1),
                            ),
                        ],
                        spacing=SPACING["sm"],
                        wrap=True,
                    ),
                    is_dark=is_dark,
                ),
                filters_panel,
                ft.Divider(color=colors["border"]),
                complaints_container
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=SPACING["lg"],
            expand=True
        ), padding=SPACING["md"] if viewport == "mobile" else SPACING["lg"], is_dark=is_dark)

    # -------------------------------------------------------------------------
    # TAB 3: FEEDBACK  (Institution-Wide Resolved Complaints → Detail → Rate)
    # -------------------------------------------------------------------------
    def _render_feedback(self) -> ft.Control:
        """
        Feedback workflow:
          1. Show ALL resolved complaints in the institution (institution-wide list).
          2. It does NOT matter which student originally submitted the complaint.
          3. Only complaints with status = 'Resolved' (non-deleted) are shown.
          4. Student can submit feedback ONLY ONCE per complaint (student_id, complaint_id).
          5. If feedback already submitted, card shows 'Feedback Submitted' + submitted rating/comment.
          6. If feedback not submitted, card shows 'Give Feedback'.
          7. Single edit rule is preserved.
          8. Complainant's identity is strictly anonymous/private across all cards and modals.
        """
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)
        viewport = self._viewport_layout()

        # 2-Query pattern: 1 query for all resolved complaints + 1 batch query for student's feedback
        all_resolved = FeedbackService.get_resolved_complaints_for_student(
            student_id=self.student_id
        )

        search_field = ft.TextField(
            hint_text="Search resolved complaints by ID, title, or department...",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=8,
            expand=True
        )

        filter_status = ft.Dropdown(
            label="Feedback Status",
            options=[
                ft.dropdown.Option("ALL", "All Resolved Complaints"),
                ft.dropdown.Option("PENDING", "Pending Your Feedback"),
                ft.dropdown.Option("SUBMITTED", "Feedback Submitted")
            ],
            value="ALL",
            dense=True,
            width=200
        )

        show_all_state = [False]
        complaints_list_container = ft.Column(spacing=10)

        def _open_complaint_detail_with_feedback(comp: Dict[str, Any]):
            """Opens a dialog showing complaint details + feedback form / review."""
            cid = comp.get("complaint_id")
            existing_fb = comp.get("student_feedback")
            already_gave = bool(comp.get("has_feedback"))

            def _row(label: str, value: str) -> ft.Control:
                return ft.Row(
                    controls=[
                        ft.Text(label + ":", size=12, color=colors["text_muted"], width=88 if viewport == "mobile" else 110),
                        ft.Text(str(value or "—"), size=13, color=colors["text"], expand=True)
                    ],
                    spacing=SPACING["xs"],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )

            cat_obj = comp.get("categories")
            cat_name = cat_obj.get("name") if isinstance(cat_obj, dict) else (comp.get("category_custom") or "—")
            sub_obj = comp.get("subcategories")
            sub_name = sub_obj.get("name") if isinstance(sub_obj, dict) else (comp.get("subcategory_custom") or "—")
            loc_obj = comp.get("locations")
            loc_name = loc_obj.get("name") if isinstance(loc_obj, dict) else (comp.get("location_custom") or "—")
            dept_obj = comp.get("departments")
            dept_name = dept_obj.get("name") if isinstance(dept_obj, dict) else "—"
            resolved_at = (comp.get("resolved_at") or "")[:10] or "—"
            remarks = comp.get("resolution_remarks") or "Resolved as per administrative review."

            detail_col = ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(f"Complaint #{cid}", size=18, weight=ft.FontWeight.BOLD, color=colors["primary"], expand=True),
                            ft.Container(
                                content=ft.Text("✓ Resolved", size=12, weight=ft.FontWeight.BOLD, color="#059669"),
                                bgcolor=ft.Colors.with_opacity(0.12, "#059669"),
                                border_radius=6,
                                padding=ft.padding.symmetric(horizontal=8, vertical=3)
                            )
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    _row("Title", comp.get("title") or "—"),
                    _row("Description", comp.get("description") or "—"),
                    _row("Department", dept_name),
                    _row("Category", cat_name or "—"),
                    _row("Subcategory", sub_name or "—"),
                    _row("Location", loc_name),
                    _row("Priority", comp.get("priority") or "—"),
                    _row("Created", (comp.get("created_at") or "")[:10] or "—"),
                    _row("Resolved", resolved_at),
                    _row("Resolution", remarks),
                ],
                spacing=6
            )

            fb_container = ft.Container()

            if already_gave and existing_fb:
                cur_rating = existing_fb.get("rating", 5)
                cur_comment = existing_fb.get("comment") or "No comments provided."
                cur_edits = existing_fb.get("edit_count", 0)

                def render_existing_view():
                    stars_str = "★" * cur_rating + "☆" * (5 - cur_rating)
                    controls = [
                        ft.Divider(color=colors["border"]),
                        ft.Text("Your Feedback", size=15, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Row(
                            controls=[
                                ft.Text("Rating:", size=13, color=colors["text_muted"]),
                                ft.Text(f"{stars_str} ({cur_rating}/5)", size=14, weight=ft.FontWeight.BOLD, color="#f59e0b")
                            ],
                            spacing=6
                        ),
                        ft.Row(
                            controls=[
                                ft.Text("Comments:", size=13, color=colors["text_muted"], width=80),
                                ft.Text(cur_comment, size=13, color=colors["text"], expand=True)
                            ],
                            spacing=6
                        ),
                    ]

                    if cur_edits == 0:
                        edit_btn = ft.TextButton("Edit Feedback (1 edit allowed)", icon=ft.Icons.EDIT, on_click=lambda _: render_edit_form())
                        controls.append(edit_btn)
                    else:
                        controls.append(
                            ft.Text("✓ Feedback locked (maximum 1 edit used).", size=12, color=colors["text_muted"], italic=True)
                        )

                    fb_container.content = ft.Column(controls=controls, spacing=8)
                    try:
                        fb_container.update()
                    except Exception:
                        pass

                def render_edit_form():
                    edit_rating_val = [cur_rating]

                    def _build_edit_stars(sel: int):
                        icons = []
                        for i in range(1, 6):
                            icons.append(
                                ft.IconButton(
                                    icon=ft.Icons.STAR if i <= sel else ft.Icons.STAR_BORDER,
                                    icon_color="#f59e0b" if i <= sel else colors["text_muted"],
                                    icon_size=28,
                                    width=44,
                                    height=44,
                                    data=i,
                                    on_click=lambda ev, idx=i: _on_edit_star(ev, idx)
                                )
                            )
                        return icons

                    edit_stars_row = ft.Row(controls=_build_edit_stars(cur_rating), spacing=0)
                    edit_rating_lbl = ft.Text(f"{cur_rating} / 5 Stars", size=13, weight=ft.FontWeight.W_600, color="#f59e0b")

                    def _on_edit_star(ev, idx: int):
                        edit_rating_val[0] = idx
                        edit_rating_lbl.value = f"{idx} / 5 Stars"
                        edit_stars_row.controls = _build_edit_stars(idx)
                        try:
                            edit_stars_row.update()
                            edit_rating_lbl.update()
                        except Exception:
                            self.page.update()

                    edit_comment_field = ft.TextField(
                        label="Updated Comment (Optional)",
                        value=existing_fb.get("comment") or "",
                        multiline=True,
                        min_lines=2,
                        max_lines=4,
                        dense=True
                    )

                    save_edit_btn = ft.ElevatedButton(
                        content=ft.Text("Save Changes"),
                        icon=ft.Icons.CHECK,
                        style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
                    )

                    def do_save_edit(ev):
                        if save_edit_btn.disabled:
                            return
                        save_edit_btn.disabled = True
                        save_edit_btn.content = ft.Text("Saving...")
                        self.page.update()
                        rating_to_save = edit_rating_val[0]
                        comment_to_save = edit_comment_field.value

                        def save_feedback_edit():
                            try:
                                ok, msg = FeedbackService.edit_feedback(
                                    student_id=self.student_id,
                                    complaint_id=cid,
                                    new_rating=rating_to_save,
                                    new_comment=comment_to_save
                                )
                                if ok:
                                    show_feedback_message(self.page, msg, is_error=False)
                                    close_dialog(self.page, detail_dlg)
                                    self.invalidate_tab_cache(3)
                                    self._switch_view(3)
                                else:
                                    show_feedback_message(self.page, msg, is_error=True)
                            except Exception as exc:
                                logger.warning("Feedback update failed (%s)", type(exc).__name__)
                                show_feedback_message(self.page, "Unable to update feedback. Please try again.", is_error=True)
                            finally:
                                save_edit_btn.disabled = False
                                save_edit_btn.content = ft.Text("Save Changes")
                                try:
                                    self.page.update()
                                except Exception:
                                    pass

                        self.page.run_thread(save_feedback_edit)

                    save_edit_btn.on_click = do_save_edit

                    fb_container.content = ft.Column(
                        controls=[
                            ft.Divider(color=colors["border"]),
                            ft.Text("Edit Feedback (Final Edit)", size=15, weight=ft.FontWeight.BOLD, color=colors["text"]),
                            ft.Row(controls=[ft.Text("Rating:", size=13, color=colors["text_muted"]), edit_stars_row, edit_rating_lbl], spacing=4, wrap=True),
                            edit_comment_field,
                            ft.Row(
                                controls=[
                                    save_edit_btn,
                                    ft.TextButton("Cancel", on_click=lambda _: render_existing_view())
                                ],
                                spacing=8
                            )
                        ],
                        spacing=8
                    )
                    try:
                        fb_container.update()
                    except Exception:
                        pass

                render_existing_view()
                dlg_actions = [
                    ft.TextButton("Close", on_click=lambda _: close_dialog(self.page, detail_dlg))
                ]
            else:
                # Fresh feedback form
                rating_val = [5]

                def _build_stars(selected: int) -> List[ft.Control]:
                    icons = []
                    for i in range(1, 6):
                        icons.append(
                            ft.IconButton(
                                icon=ft.Icons.STAR if i <= selected else ft.Icons.STAR_BORDER,
                                icon_color="#f59e0b" if i <= selected else colors["text_muted"],
                                    icon_size=30,
                                    width=44,
                                    height=44,
                                data=i,
                                on_click=lambda ev, idx=i: _on_star_click(ev, idx)
                            )
                        )
                    return icons

                stars_row = ft.Row(controls=_build_stars(5), spacing=0)
                rating_label = ft.Text("5 / 5 Stars", size=13, weight=ft.FontWeight.W_600, color="#f59e0b")

                def _on_star_click(ev, idx: int):
                    rating_val[0] = idx
                    rating_label.value = f"{idx} / 5 Stars"
                    stars_row.controls = _build_stars(idx)
                    try:
                        stars_row.update()
                        rating_label.update()
                    except Exception:
                        self.page.update()

                comment_field = ft.TextField(
                    label="Comment (Optional)",
                    hint_text="Provide feedback on the resolution quality or timeliness...",
                    multiline=True,
                    min_lines=2,
                    max_lines=4,
                    dense=True
                )

                submit_fb_btn = ft.ElevatedButton(
                    content=ft.Text("Submit Feedback"),
                    icon=ft.Icons.SEND,
                    style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
                )

                def do_submit_feedback(ev):
                    if submit_fb_btn.disabled:
                        return
                    if rating_val[0] < 1:
                        show_feedback_message(self.page, "Please select a star rating (1–5).", is_error=True)
                        return
                    submit_fb_btn.disabled = True
                    submit_fb_btn.content = ft.Text("Submitting...")
                    self.page.update()
                    rating_to_submit = rating_val[0]
                    comment_to_submit = comment_field.value

                    def submit_feedback():
                        try:
                            ok, msg, fb = FeedbackService.submit_feedback_v2(
                                student_id=self.student_id,
                                department_id=self.department_id,
                                complaint_id=cid,
                                rating=rating_to_submit,
                                comment=comment_to_submit
                            )
                            if ok:
                                show_feedback_message(self.page, msg, is_error=False)
                                close_dialog(self.page, detail_dlg)
                                self.invalidate_tab_cache(3)
                                self._switch_view(3)
                            else:
                                show_feedback_message(self.page, msg, is_error=True)
                        except Exception as exc:
                            logger.warning("Feedback submission failed (%s)", type(exc).__name__)
                            show_feedback_message(self.page, "Unable to submit feedback. Please try again.", is_error=True)
                        finally:
                            submit_fb_btn.disabled = False
                            submit_fb_btn.content = ft.Text("Submit Feedback")
                            try:
                                self.page.update()
                            except Exception:
                                pass

                    self.page.run_thread(submit_feedback)

                submit_fb_btn.on_click = do_submit_feedback

                fb_container.content = ft.Column(
                    controls=[
                        ft.Divider(color=colors["border"]),
                        ft.Text("Give Resolution Feedback", size=15, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Row(
                            controls=[
                                ft.Text("Rating (Required):", size=13, color=colors["text_muted"]),
                                stars_row,
                                rating_label
                            ],
                            spacing=4,
                            wrap=True
                        ),
                        comment_field,
                        submit_fb_btn
                    ],
                    spacing=10
                )
                dlg_actions = [
                    ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, detail_dlg))
                ]

            detail_dlg = ft.AlertDialog(
                title=ft.Text(f"Complaint #{cid} — Details & Feedback",
                              weight=ft.FontWeight.BOLD, color=colors["text"]),
                content=ft.Container(
                    content=ft.Column(
                        controls=[detail_col, fb_container],
                        spacing=10,
                        scroll=ft.ScrollMode.AUTO
                    ),
                    width=max(280, min(540, int((self._viewport_width() or 600) - 40))),
                    height=500
                ),
                bgcolor=colors["surface"],
                actions=dlg_actions
            )
            open_dialog(self.page, detail_dlg)

        def _refresh_list_view():
            query = (search_field.value or "").strip().lower()
            st_filter = filter_status.value or "ALL"

            filtered = []
            for comp in all_resolved:
                cid_str = str(comp.get("complaint_id", ""))
                title = (comp.get("title") or "").lower()
                dept_obj = comp.get("departments")
                dept_name = (dept_obj.get("name") if isinstance(dept_obj, dict) else "").lower()
                already_gave = bool(comp.get("has_feedback"))

                if query and (query not in cid_str and query not in title and query not in dept_name):
                    continue
                if st_filter == "PENDING" and already_gave:
                    continue
                if st_filter == "SUBMITTED" and not already_gave:
                    continue
                filtered.append(comp)

            # Cap initially rendered cards to 25 for mobile smoothness
            display_count = len(filtered) if show_all_state[0] else min(25, len(filtered))
            displayed_items = filtered[:display_count]

            cards: List[ft.Control] = []
            for comp in displayed_items:
                cid = comp.get("complaint_id")
                title = comp.get("title") or "—"
                cat_obj = comp.get("categories")
                cat_name = cat_obj.get("name") if isinstance(cat_obj, dict) else (comp.get("category_custom") or "—")
                sub_obj = comp.get("subcategories")
                sub_name = sub_obj.get("name") if isinstance(sub_obj, dict) else (comp.get("subcategory_custom") or "")
                dept_obj = comp.get("departments")
                dept_name = dept_obj.get("name") if isinstance(dept_obj, dict) else "—"
                resolved_at = (comp.get("resolved_at") or comp.get("updated_at") or "")[:10] or "—"
                remarks = comp.get("resolution_remarks") or "Resolution details recorded."

                existing_fb = comp.get("student_feedback")
                already_gave = bool(comp.get("has_feedback"))

                fb_badge_color = "#059669" if already_gave else "#d97706"
                fb_badge_text = "Feedback Submitted" if already_gave else "Give Feedback"

                feedback_preview = None
                if already_gave and existing_fb:
                    r = existing_fb.get("rating", 5)
                    c = existing_fb.get("comment") or ""
                    edits = existing_fb.get("edit_count", 0)
                    stars = "★" * r + "☆" * (5 - r)
                    feedback_preview = ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Row([
                                    ft.Text("Your Feedback:", size=12, weight=ft.FontWeight.W_600, color=colors["text_muted"]),
                                    ft.Text(f"{stars} ({r}/5)", size=12, weight=ft.FontWeight.BOLD, color="#f59e0b")
                                ], spacing=6),
                                ft.Text(f'"{c}"' if c else "No comment submitted.", size=12, italic=not bool(c), color=colors["text"], max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
                            ],
                            spacing=2
                        ),
                        bgcolor=colors.get("surface_variant", "#f8fafc"),
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        border_radius=8
                    )

                cards.append(
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                # Header row: ID, Title, Badges
                                ft.Row(
                                    controls=[
                                        ft.Row(
                                            controls=[
                                                ft.TextButton(
                                                    content=ft.Text(
                                                        f"#{cid}",
                                                        size=15, weight=ft.FontWeight.BOLD,
                                                        color=colors["primary"],
                                                        style=ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)
                                                    ),
                                                    on_click=lambda _, c=comp: _open_complaint_detail_with_feedback(c),
                                                    style=ft.ButtonStyle(
                                                        padding=ft.padding.all(0),
                                                        overlay_color=ft.Colors.TRANSPARENT
                                                    )
                                                ),
                                        ft.Text(f"  {title[:32 if viewport == 'mobile' else 50]}", size=14, weight=ft.FontWeight.W_600, color=colors["text"], expand=True, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
                                            ],
                                            spacing=0,
                                            expand=True
                                        ),
                                        ft.Row(
                                            controls=[
                                                StatusBadge("Resolved", is_dark),
                                                ft.Container(
                                                    content=ft.Text(fb_badge_text, size=11, weight=ft.FontWeight.BOLD, color=fb_badge_color),
                                                    bgcolor=ft.Colors.with_opacity(0.12, fb_badge_color),
                                                    border_radius=12,
                                                    padding=ft.padding.symmetric(horizontal=8, vertical=3)
                                                )
                                            ],
                                            spacing=6,
                                            tight=True,
                                        )
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                # Metadata: Category, Department, Resolved Date
                                ft.Row(
                                    controls=[
                                        ft.Text(cat_name, size=12, color=colors["text_muted"]),
                                        ft.Text(" · ", size=12, color=colors["text_muted"]),
                                        ft.Text(sub_name[:25] if sub_name else "", size=12, color=colors["text_muted"]) if sub_name else ft.Container(),
                                        ft.Text(" · " if sub_name else "", size=12, color=colors["text_muted"]) if sub_name else ft.Container(),
                                        ft.Text(dept_name, size=12, color=colors["text_muted"]),
                                        ft.Text(f" · Resolved {resolved_at}", size=12, color=colors["text_muted"])
                                    ],
                                    spacing=0,
                                    wrap=True
                                ),
                                # Resolution Remarks preview
                                ft.Row(
                                    controls=[
                                        ft.Text("Resolution:", size=12, weight=ft.FontWeight.W_600, color=colors["text_muted"]),
                                        ft.Text(remarks[:120] + ("..." if len(remarks) > 120 else ""), size=12, color=colors["text"], expand=True)
                                    ],
                                    spacing=4
                                ),
                                # Student Feedback preview if submitted
                                feedback_preview if feedback_preview else ft.Container(),
                                # Action button row
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            "✓ Feedback submitted (locked)" if already_gave and existing_fb and existing_fb.get("edit_count", 0) >= 1
                                            else ("Feedback submitted · 1 edit available" if already_gave else "Your feedback helps improve campus services"),
                                            size=11, color=colors["text_muted"], italic=True, expand=True
                                        ),
                                        ft.ElevatedButton(
                                            content=ft.Text(
                                                "Give Feedback" if not already_gave
                                                else ("Edit Feedback" if existing_fb and existing_fb.get("edit_count", 0) == 0 else "View Details")
                                            ),
                                            icon=ft.Icons.RATE_REVIEW if not already_gave else (ft.Icons.EDIT if existing_fb and existing_fb.get("edit_count", 0) == 0 else ft.Icons.VISIBILITY),
                                            style=ft.ButtonStyle(
                                                bgcolor=colors["primary"] if not already_gave else colors.get("surface_variant", "#e2e8f0"),
                                                color=ft.Colors.WHITE if not already_gave else colors["text"]
                                            ),
                                            on_click=lambda _, c=comp: _open_complaint_detail_with_feedback(c)
                                        )
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                )
                            ],
                            spacing=8
                        ),
                        bgcolor=colors["surface"],
                        border=ft.Border.all(1, colors["border"]),
                        border_radius=RADII["lg"],
                        shadow=get_card_shadow(is_dark),
                        padding=SPACING["lg"],
                        margin=ft.margin.only(bottom=SPACING["sm"]),
                        animate=MOTION_NORMAL_MS,
                    )
                )

            if not filtered:
                cards.append(EmptyState(
                    "No resolved complaints found",
                    "Resolved complaints matching these filters will appear here.",
                    icon=ft.Icons.INBOX_OUTLINED,
                    is_dark=is_dark,
                ))
            elif len(filtered) > display_count and not show_all_state[0]:
                def _expand_cards(e):
                    show_all_state[0] = True
                    _refresh_list_view()

                cards.append(
                    ft.Container(
                        content=ft.ElevatedButton(
                            content=ft.Text(f"Show All Resolved Complaints ({len(filtered)} Total)"),
                            icon=ft.Icons.EXPAND_MORE,
                            on_click=_expand_cards,
                            style=ft.ButtonStyle(
                                bgcolor=colors.get("surface_variant", "#e2e8f0"),
                                color=colors["text"]
                            )
                        ),
                        alignment=ft.Alignment(0, 0),
                        padding=ft.padding.symmetric(vertical=8)
                    )
                )

            complaints_list_container.controls = cards
            try:
                complaints_list_container.update()
            except Exception:
                pass

        # Debounced search & filter listener
        import threading
        search_timer = [None]

        def _on_search_change(e):
            if search_timer[0]:
                search_timer[0].cancel()
            def _debounced():
                _refresh_list_view()
            search_timer[0] = threading.Timer(0.15, _debounced)
            search_timer[0].start()

        search_field.on_change = _on_search_change
        filter_status.on_change = lambda _: _refresh_list_view()

        _refresh_list_view()

        return PageContainer(ft.Column(
            controls=[
                SectionHeader(
                    "Resolved Complaints & Feedback",
                    "Review outcomes and rate how the resolution was handled.",
                    icon=ft.Icons.RATE_REVIEW_OUTLINED,
                    action=ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        tooltip="Refresh list",
                        on_click=lambda _: (self.invalidate_tab_cache(3), self._switch_view(3)),
                    ),
                    is_dark=is_dark,
                ),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(search_field, col={"xs": 12, "md": 8}),
                        ft.Container(filter_status, col={"xs": 12, "md": 4}),
                    ],
                    spacing=SPACING["sm"],
                    run_spacing=SPACING["sm"],
                ),
                ft.Divider(color=colors["border"]),
                complaints_list_container
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=SPACING["md"],
            expand=True
        ), padding=SPACING["md"] if viewport == "mobile" else SPACING["lg"], is_dark=is_dark)

    # -------------------------------------------------------------------------
    # TAB 4: HOSTEL STATUS & RE-REQUEST
    # -------------------------------------------------------------------------
    def _render_hostel_status(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        req = HostelService.get_student_hostel_request(self.student_id)

        if not req:
            return PageContainer(EmptyState(
                "Hostel access",
                "You have not requested hostel accommodation yet.",
                icon=ft.Icons.HOTEL,
                action=ft.ElevatedButton(
                    "Request Hostel Access",
                    icon=ft.Icons.ADD,
                    style=get_button_style(is_dark),
                    on_click=self._open_hostel_request_modal,
                ),
                is_dark=is_dark,
            ), padding=SPACING["lg"], is_dark=is_dark)

        status = req.get("status", "Pending")
        status_color = "#d97706" if status == "Pending" else ("#059669" if status == "Approved" else "#dc2626")

        rows = [
            SectionHeader("Hostel Access Status", "Review your current accommodation request.", icon=ft.Icons.HOTEL, is_dark=is_dark),
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text("Status:", size=14, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Container(
                            content=ft.Text(status, size=13, weight=ft.FontWeight.BOLD, color=status_color),
                            bgcolor=ft.Colors.with_opacity(0.12, status_color),
                            border_radius=20,
                            padding=ft.padding.symmetric(horizontal=12, vertical=5)
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
                    border_radius=10,
                    padding=14
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
            border_radius=RADII["lg"],
            shadow=get_card_shadow(is_dark),
            padding=SPACING["xl"],
            expand=True
        )

    def _open_hostel_request_modal(self, e):
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        h_name = ft.TextField(label="Hostel Name", value="Boys Hostel Block A", dense=True)
        h_block = ft.TextField(label="Block", value="A", dense=True)
        h_room = ft.TextField(label="Room Number", value="101", dense=True)
        for field in (h_name, h_block, h_room):
            for property_name, property_value in get_input_style(is_dark).items():
                setattr(field, property_name, property_value)

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
                width=max(280, min(400, int((self._viewport_width() or 440) - 40))),
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
