"""
ui/views/staff_view.py: Role-tailored administration dashboards for Coordinator, HOD, Hostel Incharge, and Principal.
Supports animated registered vs resolved chart, responsive layout reflow, table horizontal scroll,
loading state prevention, and dark mode theming.
"""

from typing import Dict, Any, Optional, List
import flet as ft
from services.complaint_service import ComplaintService
from services.issue_group_service import IssueGroupService
from services.hostel_service import HostelService
from services.roll_number_service import RollNumberService
from services.security_code_service import SecurityCodeService
from services.analytics_service import AnalyticsService
from database.supabase_client import get_supabase_client
from ui.theme import (
    COLOR_PRIMARY, COLOR_SURFACE, COLOR_BORDER, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_MUTED, STATUS_COLORS, PRIORITY_COLORS, get_theme_colors
)
from ui.state import AppState
from ui.flet_compat import show_feedback_message, open_dialog, close_dialog
from ui.components.stat_card import create_stat_card
from ui.components.complaint_card import create_complaint_card
from ui.components.complaint_detail import show_complaint_detail_dialog
from ui.components.excel_importer import show_excel_importer_dialog
from ui.components.animated_chart import (
    create_registered_vs_resolved_chart,
    create_campus_overview_card,
    create_priority_distribution_chart,
    create_category_distribution_chart
)
from services.account_service import AccountService
from ui.views.student_view import BASELINE_SUBCATEGORIES
from models.user import UserRole
from utils.helpers import format_datetime


class StaffView:
    def __init__(self, page: ft.Page, staff: Dict[str, Any], role: str):
        self.page = page
        self.staff = staff
        self.role = role
        self.staff_id = staff["id"]
        self.department_id = staff.get("department_id")
        self.department_code = staff.get("departments", {}).get("code") if isinstance(staff.get("departments"), dict) else staff.get("department_code")
        self.selected_tab_index = 0
        self.cached_complaints = None
        self.cached_metrics = None
        self.cached_dept_breakdown = None
        self.categories = []
        self.subcategories_by_cat = {}
        self.active_container = ft.Container(expand=True)
        self._load_categories_and_subcategories()

    def _load_categories_and_subcategories(self):
        from services.cache_service import CacheService
        self.categories, self.subcategories_by_cat, _ = CacheService.get_categories_and_subcategories()

    def render(self) -> ft.Control:
        self._switch_view(self.selected_tab_index)
        return self.active_container

    def _switch_view(self, index: int):
        self.selected_tab_index = index

        if self.role == UserRole.COORDINATOR.value:
            views = [self._render_dashboard, self._render_complaints_list, self._render_issue_groups, self._render_roll_number_pool, self._render_analytics, self._render_account_management]
        elif self.role == UserRole.HOD.value:
            views = [self._render_dashboard, self._render_complaints_list, self._render_issue_groups, self._render_hod_security_codes, self._render_analytics, self._render_account_management]
        elif self.role == UserRole.GENERAL_HOD.value:
            views = [self._render_dashboard, self._render_complaints_list, self._render_issue_groups, self._render_general_security_code, self._render_analytics, self._render_account_management]
        elif self.role == UserRole.LIBRARY_INCHARGE.value:
            views = [self._render_dashboard, self._render_complaints_list, self._render_issue_groups, self._render_library_security_code, self._render_analytics, self._render_account_management]
        elif self.role == UserRole.HOSTEL_INCHARGE.value:
            views = [self._render_dashboard, self._render_hostel_requests, self._render_complaints_list, self._render_issue_groups, self._render_hostel_security_code, self._render_account_management]
        elif self.role == UserRole.PRINCIPAL.value:
            views = [self._render_dashboard, self._render_complaints_list, self._render_analytics, self._render_location_manager, self._render_principal_security_codes, self._render_account_management]
        else:
            views = [self._render_dashboard, self._render_account_management]

        target_func = views[index] if index < len(views) else self._render_dashboard
        self.active_container.content = target_func()
        self.page.update()

    def _render_account_management(self) -> ft.Control:
        from ui.views.account_view import AccountView
        return AccountView(
            self.page,
            self.staff,
            self.role,
            on_refresh=lambda: self._switch_view(self.selected_tab_index)
        ).render()

    # -------------------------------------------------------------------------
    # TAB: DASHBOARD
    # -------------------------------------------------------------------------
    def _render_dashboard(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        if self.cached_metrics is None or self.cached_complaints is None:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as executor:
                f_m = executor.submit(AnalyticsService.get_dashboard_metrics, self.role, self.department_id) if self.cached_metrics is None else None
                f_c = executor.submit(ComplaintService.get_complaints_for_user, self.role, self.staff_id, self.department_id) if self.cached_complaints is None else None
                if f_m:
                    self.cached_metrics = f_m.result()
                if f_c:
                    self.cached_complaints = f_c.result()

        metrics = self.cached_metrics

        stat_cards = [
            create_stat_card("Total Active", str(metrics["total"]), ft.Icons.FOLDER, colors["primary"], is_dark=is_dark),
            create_stat_card("Pending Action", str(metrics["pending"]), ft.Icons.HOURGLASS_TOP, "#d97706", is_dark=is_dark),
            create_stat_card("In Progress", str(metrics["in_progress"]), ft.Icons.PENDING_ACTIONS, "#2563eb", is_dark=is_dark),
            create_stat_card("Resolved", str(metrics["resolved"]), ft.Icons.TASK_ALT, "#059669", is_dark=is_dark),
            create_stat_card("Urgent / High", str(metrics["urgent_high"]), ft.Icons.WARNING_AMBER, "#dc2626", is_dark=is_dark),
            create_stat_card("Satisfaction", f"{metrics['satisfaction_rate']}%", ft.Icons.THUMB_UP_ALT, "#0f766e", is_dark=is_dark),
        ]

        # Complaints in scope
        complaints = self.cached_complaints
        recent_cards = [create_complaint_card(c, self._open_detail_dialog, is_staff=True) for c in complaints[:5]]

        if not recent_cards:
            recent_cards.append(
                ft.Container(
                    content=ft.Text("No grievances found in your assigned scope.", size=14, color=colors["text_muted"]),
                    padding=32
                )
            )

        # Animated Resolution Chart
        chart_card = create_registered_vs_resolved_chart(
            registered=metrics["total"],
            resolved=metrics["resolved"],
            in_progress=metrics["in_progress"],
            pending=metrics["pending"],
            rejected=metrics.get("rejected", 0),
            title=f"{self.role} Scope Resolution Analytics",
            subtitle=f"Live analytics for {self.department_code or 'Campus-wide'} grievances",
            is_dark=is_dark
        )

        # Priority & Category Distribution Charts
        priority_chart = create_priority_distribution_chart(
            complaints=complaints,
            title="Priority Distribution",
            subtitle=f"Urgency breakdown for {self.department_code or 'Campus-wide'} grievances",
            is_dark=is_dark
        )
        category_chart = create_category_distribution_chart(
            complaints=complaints,
            title="Category Breakdown",
            subtitle="Distribution across complaint categories",
            is_dark=is_dark
        )
        distribution_row = ft.ResponsiveRow(
            controls=[
                ft.Container(priority_chart, col={"xs": 12, "md": 6}),
                ft.Container(category_chart, col={"xs": 12, "md": 6})
            ],
            spacing=12
        )

        # For Principal: Add Campus Overview comparing all 5 academic departments
        campus_overview_card = None
        if self.role == UserRole.PRINCIPAL.value:
            try:
                if self.cached_dept_breakdown is None:
                    self.cached_dept_breakdown = AnalyticsService.get_department_breakdown()
                campus_overview_card = create_campus_overview_card(self.cached_dept_breakdown, is_dark=is_dark)
            except Exception:
                campus_overview_card = None

        dash_controls = [
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(f"{self.role} Dashboard", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                            ft.Text(f"Scope: {self.department_code or 'Campus-wide'} | Faculty: {self.staff.get('full_name')}", size=13, color=colors["text_muted"])
                        ],
                        spacing=2
                    ),
                    ft.ElevatedButton(
                        content=ft.Text("View All Complaints"),
                        icon=ft.Icons.LIST,
                        style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE),
                        on_click=lambda _: self._switch_view(1)
                    )
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                wrap=True
            ),
            ft.Row(controls=stat_cards, wrap=True, spacing=12),
        ]
        if campus_overview_card:
            dash_controls.append(campus_overview_card)
        dash_controls.extend([
            chart_card,
            distribution_row,
            ft.Divider(color=colors["border"]),
            ft.Text("Recent Grievances in Scope", size=18, weight=ft.FontWeight.BOLD, color=colors["text"]),
            ft.Column(controls=recent_cards, spacing=8)
        ])

        return ft.Column(
            controls=dash_controls,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: COMPLAINTS LIST WITH SEARCH & FILTER
    # -------------------------------------------------------------------------
    def _render_complaints_list(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        is_principal = (self.role == UserRole.PRINCIPAL.value)

        search_field = ft.TextField(hint_text="Search by Complaint ID or Keyword...", prefix_icon=ft.Icons.SEARCH, dense=True, expand=True)
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
            width=140
        )

        subcategory_filter = ft.Dropdown(
            label="Subcategory",
            options=[ft.dropdown.Option("ALL", "All Subcategories")],
            value="ALL",
            dense=True,
            width=150
        )

        dept_filter = None
        if is_principal:
            dept_filter = ft.Dropdown(
                label="Scope / Department",
                options=[
                    ft.dropdown.Option("ALL", "All Departments"),
                    ft.dropdown.Option("CSE", "CSE"),
                    ft.dropdown.Option("AIDS", "AIDS"),
                    ft.dropdown.Option("E&TC", "E&TC"),
                    ft.dropdown.Option("MECH", "MECH"),
                    ft.dropdown.Option("Civil", "Civil"),
                    ft.dropdown.Option("GEN", "General / First Year"),
                    ft.dropdown.Option("LIB", "Library"),
                    ft.dropdown.Option("HOSTEL", "Hostel Complaints")
                ],
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
                elif c_val in BASELINE_SUBCATEGORIES:
                    subs = [{"name": s} for s in BASELINE_SUBCATEGORIES[c_val]]
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
                self.cached_complaints = ComplaintService.get_complaints_for_user(self.role, self.staff_id, self.department_id)
            return self.cached_complaints

        def reset_filters(e=None):
            search_field.value = ""
            status_filter.value = "ALL"
            priority_filter.value = "ALL"
            category_filter.value = "ALL"
            subcategory_filter.options = [ft.dropdown.Option("ALL", "All Subcategories")]
            subcategory_filter.value = "ALL"
            if dept_filter:
                dept_filter.value = "ALL"
            refresh_list(force_reload=False)

        def refresh_list(force_reload: bool = False):
            complaints = load_data(force=force_reload)
            query = (search_field.value or "").strip().lower()
            st_val = (status_filter.value or "ALL").strip()
            pr_val = (priority_filter.value or "ALL").strip()
            cat_val = (category_filter.value or "ALL").strip()
            sub_val = (subcategory_filter.value or "ALL").strip()
            d_val = (dept_filter.value or "ALL").strip() if dept_filter else "ALL"

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

                if d_val != "ALL":
                    dept_obj = c.get("departments")
                    d_code = (dept_obj.get("code") if isinstance(dept_obj, dict) else (c.get("department_code") or "")).strip().upper()
                    st_obj = c.get("students")
                    st_yr = (st_obj.get("year", "") if isinstance(st_obj, dict) else str(c.get("student_year") or "")).strip().upper()
                    is_fe = (st_yr in ("FE", "1", "1ST", "FIRST YEAR", "FIRST")) or (d_code == "GEN")
                    is_lib = (str(c_cat).strip().lower() == "library")

                    if d_val == "HOSTEL":
                        if not c.get("is_hostel"):
                            continue
                    elif d_val == "LIB":
                        if not is_lib:
                            continue
                    elif d_val == "GEN":
                        if not is_fe and d_code != "GEN":
                            continue
                    else:
                        # Academic departments: CSE, AIDS, E&TC, MECH, Civil
                        if d_code != d_val.upper() or c.get("is_hostel") or is_lib or is_fe:
                            continue

                filtered.append(c)

            cards = [create_complaint_card(c, self._open_detail_dialog, is_staff=True) for c in filtered]
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

        search_field.on_change = lambda _: refresh_list(force_reload=False)
        status_filter.on_select = lambda _: refresh_list(force_reload=False)
        status_filter.on_change = lambda _: refresh_list(force_reload=False)
        priority_filter.on_select = lambda _: refresh_list(force_reload=False)
        priority_filter.on_change = lambda _: refresh_list(force_reload=False)
        def on_cat_filter_change(e):
            c_val = getattr(e, "data", None) or getattr(e.control, "value", None) or category_filter.value or "ALL"
            category_filter.value = c_val
            update_subcat_options(c_val)
            refresh_list(force_reload=False)

        category_filter.on_select = on_cat_filter_change
        category_filter.on_change = on_cat_filter_change
        subcategory_filter.on_select = lambda _: refresh_list(force_reload=False)
        subcategory_filter.on_change = lambda _: refresh_list(force_reload=False)
        if dept_filter:
            dept_filter.on_select = lambda _: refresh_list(force_reload=False)
            dept_filter.on_change = lambda _: refresh_list(force_reload=False)

        refresh_list(force_reload=False)

        filter_row_controls = [
            ft.Container(search_field, col={"xs": 12, "md": 3.5 if is_principal else 4})
        ]
        if is_principal:
            filter_row_controls.append(ft.Container(dept_filter, col={"xs": 12, "sm": 6, "md": 2}))
        filter_row_controls.append(ft.Container(status_filter, col={"xs": 6, "sm": 3, "md": 1.6 if is_principal else 2}))
        filter_row_controls.append(ft.Container(priority_filter, col={"xs": 6, "sm": 3, "md": 1.6 if is_principal else 2}))
        filter_row_controls.append(ft.Container(category_filter, col={"xs": 6, "sm": 3, "md": 1.7 if is_principal else 2}))
        filter_row_controls.append(ft.Container(subcategory_filter, col={"xs": 6, "sm": 3, "md": 1.6 if is_principal else 2}))

        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Grievance Management", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            tooltip="Refresh from Server",
                            on_click=lambda _: refresh_list(force_reload=True)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.ResponsiveRow(
                    controls=filter_row_controls
                ),
                ft.Divider(color=colors["border"]),
                complaints_container
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=14,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: ISSUE GROUPS (+N DUPLICATES)
    # -------------------------------------------------------------------------
    def _render_issue_groups(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        groups = IssueGroupService.get_department_groups(self.department_id, role=self.role)

        group_cards = []
        for g in groups:
            gid = g.get("id")
            parent_cid = g.get("parent_complaint_id")
            dup_count = g.get("duplicate_count", 0)
            status = g.get("status", "Active")
            members = g.get("members", [])

            member_rows = []
            for m in members:
                mid = m.get("id")
                m_cid = m.get("complaint_id")
                m_st = m.get("status", "Pending")
                m_pri = m.get("priority", "Low")
                member_rows.append(
                    ft.Row(
                        controls=[
                            ft.Text(f"#{m_cid}", weight=ft.FontWeight.BOLD, size=13, color=colors["primary"]),
                            ft.Container(
                                content=ft.Text(m_st, size=11, color=STATUS_COLORS.get(m_st, "#6b7280")),
                                bgcolor=ft.Colors.with_opacity(0.12, STATUS_COLORS.get(m_st, "#6b7280")),
                                border_radius=6,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2)
                            ),
                            ft.Text(f"Priority: {m_pri}", size=11, color=colors["text_muted"])
                        ],
                        spacing=8,
                        wrap=True
                    )
                )

            group_cards.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Text(f"Parent Issue #{parent_cid}", size=16, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                            ft.Container(
                                                content=ft.Text(f"+{dup_count} Similar Complaints", size=12, weight=ft.FontWeight.BOLD, color="#b45309"),
                                                bgcolor="#78350f" if is_dark else "#fef3c7",
                                                border_radius=8,
                                                padding=ft.padding.symmetric(horizontal=10, vertical=4)
                                            )
                                        ],
                                        spacing=8,
                                        wrap=True
                                    ),
                                    ft.Text(f"Group Status: {status}", size=12, weight=ft.FontWeight.W_600, color=STATUS_COLORS.get(status, "#6b7280"))
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                wrap=True
                            ),
                            ft.Text("Individual Complaints (Statuses remain independent):", size=12, color=colors["text_muted"]),
                            ft.Column(controls=member_rows)
                        ],
                        spacing=8
                    ),
                    bgcolor=colors["surface"],
                    border=ft.Border.all(1, colors["border"]),
                    border_radius=12,
                    padding=16,
                    margin=ft.margin.only(bottom=12)
                )
            )

        if not group_cards:
            group_cards.append(
                ft.Container(
                    content=ft.Text("No active Issue Groups in your departmental scope.", size=14, color=colors["text_muted"]),
                    padding=40
                )
            )

        return ft.Column(
            controls=[
                ft.Text("Duplicate Issue Groups", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Text("Similar complaints are automatically grouped together (+N) without deleting or merging them.", size=13, color=colors["text_muted"]),
                ft.Column(controls=group_cards, spacing=8)
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=14,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: COORDINATOR ROLL NUMBER POOL
    # -------------------------------------------------------------------------
    def _render_roll_number_pool(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        from concurrent.futures import ThreadPoolExecutor
        from database.supabase_client import get_trusted_backend_client

        def fetch_pool():
            return RollNumberService.get_department_pool(self.department_id)

        def fetch_students():
            return get_trusted_backend_client().table("students").select("id, roll_number, full_name, year").eq("department_id", self.department_id).execute()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f_p = executor.submit(fetch_pool)
            f_s = executor.submit(fetch_students)
            pool = f_p.result()
            try:
                st_res = f_s.result()
                student_records = {s["roll_number"].strip().upper(): s for s in (st_res.data or []) if s.get("roll_number")}
            except Exception:
                student_records = {}

        def get_academic_year_info(roll_no: str, st_info: Optional[Dict[str, Any]] = None):
            st_year = (st_info.get("year") or "").strip().upper() if st_info else ""
            if st_year in ("FE", "FIRST YEAR", "1", "1ST", "1ST YEAR"):
                return ("FE", "First Year (FE)", "#2563eb", "#dbeafe" if not is_dark else "#1e3a8a")
            elif st_year in ("SE", "SECOND YEAR", "2", "2ND", "2ND YEAR"):
                return ("SE", "Second Year (SE)", "#7c3aed", "#ede9fe" if not is_dark else "#4c1d95")
            elif st_year in ("TE", "THIRD YEAR", "3", "3RD", "3RD YEAR"):
                return ("TE", "Third Year (TE)", "#d97706", "#fef3c7" if not is_dark else "#78350f")
            elif st_year in ("BE", "FINAL YEAR", "FOURTH YEAR", "4", "4TH", "4TH YEAR"):
                return ("BE", "Fourth Year (BE)", "#059669", "#d1fae5" if not is_dark else "#064e3b")

            clean = roll_no.upper()
            if "FE" in clean or clean.startswith("26"):
                return ("FE", "First Year (FE)", "#2563eb", "#dbeafe" if not is_dark else "#1e3a8a")
            elif "SE" in clean or clean.startswith("25"):
                return ("SE", "Second Year (SE)", "#7c3aed", "#ede9fe" if not is_dark else "#4c1d95")
            elif "TE" in clean or clean.startswith("24"):
                return ("TE", "Third Year (TE)", "#d97706", "#fef3c7" if not is_dark else "#78350f")
            elif "BE" in clean or clean.startswith("23"):
                return ("BE", "Fourth Year (BE)", "#059669", "#d1fae5" if not is_dark else "#064e3b")
            return ("FE", "First Year (FE)", "#2563eb", "#dbeafe" if not is_dark else "#1e3a8a")

        single_roll_field = ft.TextField(label="Add Single Roll Number", hint_text="e.g. 240101030", dense=True, width=220)

        add_btn = ft.ElevatedButton(
            content=ft.Text("Add Roll Number"),
            icon=ft.Icons.ADD,
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def add_single(e):
            add_btn.disabled = True
            add_btn.content = ft.Text("Adding...")
            self.page.update()

            ok, msg = RollNumberService.add_single_roll_number(
                coordinator_role=self.role,
                coordinator_dept_id=self.department_id,
                coordinator_id=self.staff_id,
                roll_number=single_roll_field.value or ""
            )

            add_btn.disabled = False
            add_btn.content = ft.Text("Add Roll Number")

            if ok:
                show_feedback_message(self.page, msg, is_error=False)
                single_roll_field.value = ""
                self._switch_view(3)
            else:
                show_feedback_message(self.page, msg, is_error=True)
                self.page.update()

        add_btn.on_click = add_single

        def make_reset_handler(student_id: str, roll_num: str, student_name: str):
            def handle_click(e):
                new_pw_field = ft.TextField(
                    label="Temporary Password",
                    value="Temp@2026!",
                    password=True,
                    can_reveal_password=True,
                    dense=True
                )

                def do_student_reset(e_rst):
                    pw = (new_pw_field.value or "").strip()
                    close_dialog(self.page, dlg)
                    ok, msg = AccountService.reset_student_password_by_coordinator(
                        coordinator_id=self.staff_id,
                        student_id=student_id,
                        new_password=pw
                    )
                    if ok:
                        info_dlg = ft.AlertDialog(
                            title=ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.CHECK_CIRCLE, color="#10b981"),
                                    ft.Text("Password Reset Successful", size=16, weight=ft.FontWeight.BOLD)
                                ],
                                spacing=8
                            ),
                            content=ft.Column(
                                controls=[
                                    ft.Text(f"Password for student {student_name} ({roll_num}) has been reset.", size=13),
                                    ft.Container(
                                        content=ft.Text(f"Temporary Password: {pw}", weight=ft.FontWeight.BOLD, size=14, color=colors["primary"]),
                                        bgcolor=ft.Colors.with_opacity(0.1, colors["primary"]),
                                        border_radius=8,
                                        padding=12
                                    ),
                                    ft.Text("The student will be required to change this password upon next login.", size=12, color=colors["text_muted"])
                                ],
                                spacing=10,
                                tight=True
                            ),
                            actions=[
                                ft.ElevatedButton("Done", on_click=lambda _: close_dialog(self.page, info_dlg))
                            ]
                        )
                        open_dialog(self.page, info_dlg)
                        refresh_table()
                    else:
                        show_feedback_message(self.page, msg, is_error=True)

                dlg = ft.AlertDialog(
                    title=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.LOCK_RESET, color=colors["primary"]),
                            ft.Text(f"Reset Password for {roll_num}", size=16, weight=ft.FontWeight.BOLD)
                        ],
                        spacing=8
                    ),
                    content=ft.Column(
                        controls=[
                            ft.Text(f"Reset password for student {student_name} ({roll_num}).", size=13),
                            ft.Text("This will unlock the student's account and require them to set a new password upon login.", size=12, color=colors["text_muted"]),
                            new_pw_field
                        ],
                        spacing=10,
                        tight=True
                    ),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                        ft.ElevatedButton("Reset Password", on_click=do_student_reset)
                    ]
                )
                open_dialog(self.page, dlg)
            return handle_click

        # Filters & Sorting controls
        year_filter = ft.Dropdown(
            label="Filter Academic Year",
            options=[
                ft.dropdown.Option("ALL", "All Academic Years"),
                ft.dropdown.Option("FE", "First Year (FE)"),
                ft.dropdown.Option("SE", "Second Year (SE)"),
                ft.dropdown.Option("TE", "Third Year (TE)"),
                ft.dropdown.Option("BE", "Fourth Year (BE)")
            ],
            value="ALL",
            dense=True,
            width=180
        )

        sort_filter = ft.Dropdown(
            label="Sort By",
            options=[
                ft.dropdown.Option("ROLL_ASC", "Roll Number (Ascending)"),
                ft.dropdown.Option("ROLL_DESC", "Roll Number (Descending)"),
                ft.dropdown.Option("YEAR", "Academic Year (FE -> BE)"),
                ft.dropdown.Option("STATUS", "Status (Registered First)"),
                ft.dropdown.Option("DATE_DESC", "Date Added (Newest)")
            ],
            value="ROLL_ASC",
            dense=True,
            width=210
        )

        search_filter = ft.TextField(
            hint_text="Search roll number or student...",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            expand=True
        )

        count_text = ft.Text(f"Authorized Roll Numbers (Total: {len(pool)})", size=16, weight=ft.FontWeight.BOLD, color=colors["text"])
        data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Roll Number", color=colors["text"], weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Academic Year", color=colors["text"], weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Enrolled Student", color=colors["text"], weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Account Status", color=colors["text"], weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Date Added", color=colors["text"], weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Actions", color=colors["text"], weight=ft.FontWeight.BOLD))
            ],
            rows=[]
        )

        def refresh_table(e=None):
            y_val = (year_filter.value or "ALL").strip()
            s_val = (sort_filter.value or "ROLL_ASC").strip()
            q_val = (search_filter.value or "").strip().lower()

            # Decorate items with year info and student details
            decorated = []
            for r in pool:
                roll = r.get("roll_number", "").strip().upper()
                st_info = student_records.get(roll)
                y_key, y_lbl, y_color, y_bg = get_academic_year_info(roll, st_info)
                st_name = st_info.get("full_name", "") if st_info else ""
                decorated.append({
                    "raw": r,
                    "roll": roll,
                    "st_info": st_info,
                    "st_name": st_name,
                    "y_key": y_key,
                    "y_lbl": y_lbl,
                    "y_color": y_color,
                    "y_bg": y_bg,
                    "is_reg": r.get("is_registered", False),
                    "created_at": r.get("created_at", "")
                })

            # Filter
            filtered = []
            for item in decorated:
                if y_val != "ALL" and item["y_key"] != y_val:
                    continue
                if q_val and (q_val not in item["roll"].lower() and q_val not in item["st_name"].lower()):
                    continue
                filtered.append(item)

            # Sort
            year_order = {"FE": 1, "SE": 2, "TE": 3, "BE": 4}
            if s_val == "ROLL_ASC":
                filtered.sort(key=lambda x: x["roll"])
            elif s_val == "ROLL_DESC":
                filtered.sort(key=lambda x: x["roll"], reverse=True)
            elif s_val == "YEAR":
                filtered.sort(key=lambda x: (year_order.get(x["y_key"], 99), x["roll"]))
            elif s_val == "STATUS":
                filtered.sort(key=lambda x: (0 if x["is_reg"] else 1, x["roll"]))
            elif s_val == "DATE_DESC":
                filtered.sort(key=lambda x: x["created_at"], reverse=True)

            # Build rows
            new_rows = []
            for item in filtered:
                reg = item["is_reg"]
                st_display = item["st_name"] if item["st_name"] else ("—" if not reg else "Registered")

                # Action cell
                if reg and item.get("st_info") and item["st_info"].get("id"):
                    if item["y_key"] == "FE":
                        action_cell = ft.Text("FE (General Dept)", size=11, color=colors["text_muted"], italic=True)
                    else:
                        action_cell = ft.ElevatedButton(
                            content=ft.Text("Reset PW", size=11),
                            icon=ft.Icons.LOCK_RESET,
                            style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=8, vertical=2)),
                            on_click=make_reset_handler(item["st_info"]["id"], item["roll"], item["st_name"])
                        )
                else:
                    action_cell = ft.Text("—", color=colors["text_muted"])

                new_rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(item["roll"], weight=ft.FontWeight.BOLD, color=colors["text"])),
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text(item["y_lbl"], size=11, weight=ft.FontWeight.W_600, color=item["y_color"]),
                                    bgcolor=item["y_bg"],
                                    border_radius=8,
                                    padding=ft.padding.symmetric(horizontal=8, vertical=3)
                                )
                            ),
                            ft.DataCell(ft.Text(st_display, size=12, color=colors["text"] if item["st_name"] else colors["text_muted"])),
                            ft.DataCell(
                                ft.Container(
                                    content=ft.Text("Registered" if reg else "Available", size=11, weight=ft.FontWeight.W_600, color="#059669" if reg else "#d97706"),
                                    bgcolor="#14532d" if (is_dark and reg) else ("#78350f" if is_dark else ("#dcfce7" if reg else "#fef3c7")),
                                    border_radius=8,
                                    padding=ft.padding.symmetric(horizontal=8, vertical=2)
                                )
                            ),
                            ft.DataCell(ft.Text(format_datetime(item["created_at"]), color=colors["text_muted"])),
                            ft.DataCell(action_cell)
                        ]
                    )
                )

            data_table.rows = new_rows
            count_text.value = f"Authorized Roll Numbers (Showing {len(filtered)} of {len(pool)})"
            self.page.update()

        year_filter.on_select = refresh_table
        year_filter.on_change = refresh_table
        sort_filter.on_select = refresh_table
        sort_filter.on_change = refresh_table
        search_filter.on_change = refresh_table

        refresh_table()

        scrollable_table = ft.Row(
            controls=[data_table],
            scroll=ft.ScrollMode.AUTO
        )

        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text("Department Roll Number Pool", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                ft.Text(f"Exclusive management for {self.department_code}. Group and sort by academic year (FE, SE, TE, BE).", size=13, color=colors["text_muted"])
                            ]
                        ),
                        ft.ElevatedButton(
                            content=ft.Text("Import Excel / CSV"),
                            icon=ft.Icons.UPLOAD_FILE,
                            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE),
                            on_click=lambda _: show_excel_importer_dialog(
                                self.page,
                                self.role,
                                self.department_id,
                                self.staff_id,
                                on_imported=lambda: self._switch_view(3)
                            )
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True
                ),
                ft.Row(
                    controls=[
                        single_roll_field,
                        add_btn
                    ],
                    spacing=12,
                    wrap=True
                ),
                ft.Divider(color=colors["border"]),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(search_filter, col={"xs": 12, "md": 5}),
                        ft.Container(year_filter, col={"xs": 12, "sm": 6, "md": 3.5}),
                        ft.Container(sort_filter, col={"xs": 12, "sm": 6, "md": 3.5})
                    ]
                ),
                count_text,
                scrollable_table
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: HOSTEL REQUESTS (HOSTEL INCHARGE)
    # -------------------------------------------------------------------------
    def _render_hostel_requests(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        requests = HostelService.get_all_hostel_requests()
        cards = []

        for req in requests:
            rid = req["id"]
            st_info = req.get("students") or {}
            dept_info = st_info.get("departments") or {}
            st_name = st_info.get("full_name") or "Student"
            st_roll = st_info.get("roll_number") or "N/A"
            st_year = st_info.get("year") or "N/A"
            dept_code = dept_info.get("code") or dept_info.get("name") or "General"
            h_name = req.get("hostel_name") or "N/A"
            h_block = req.get("block") or "N/A"
            h_room = req.get("room_number") or "N/A"
            raw_date = req.get("request_date") or req.get("created_at")
            req_date_str = format_datetime(raw_date) if raw_date else "N/A"
            status = req.get("status", "Pending")
            deny_reason = req.get("deny_reason")

            def approve_req(ev, r_id=rid):
                ok, msg = HostelService.review_hostel_request(self.role, self.staff_id, r_id, action="Approve")
                show_feedback_message(self.page, msg, is_error=not ok)
                self._switch_view(1)

            def deny_dialog(ev, r_id=rid):
                reason_field = ft.TextField(
                    label="Denial Reason (Mandatory)",
                    hint_text="Specify reason for denying accommodation...",
                    dense=True,
                    multiline=True,
                    min_lines=2,
                    max_lines=4,
                    expand=True
                )
                err_text = ft.Text("", size=12, color="#dc2626", visible=False)
                confirm_btn = ft.ElevatedButton(
                    content=ft.Text("Confirm Deny"),
                    style=ft.ButtonStyle(bgcolor="#dc2626", color=ft.Colors.WHITE)
                )

                def do_deny(e):
                    val = (reason_field.value or "").strip()
                    if not val:
                        err_text.value = "Denial reason is strictly mandatory."
                        err_text.visible = True
                        self.page.update()
                        return

                    confirm_btn.disabled = True
                    confirm_btn.content = ft.Text("Denying...")
                    self.page.update()

                    ok, msg = HostelService.review_hostel_request(self.role, self.staff_id, r_id, action="Deny", deny_reason=val)
                    confirm_btn.disabled = False
                    confirm_btn.content = ft.Text("Confirm Deny")

                    if ok:
                        show_feedback_message(self.page, msg, is_error=False)
                        close_dialog(self.page, dlg)
                        self._switch_view(1)
                    else:
                        err_text.value = msg
                        err_text.visible = True
                        self.page.update()

                confirm_btn.on_click = do_deny

                dlg = ft.AlertDialog(
                    title=ft.Row([
                        ft.Icon(ft.Icons.BLOCK, color="#dc2626", size=22),
                        ft.Text("Deny Hostel Request", weight=ft.FontWeight.BOLD, color=colors["text"], size=16)
                    ], spacing=8),
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text(f"Student: {st_name} ({st_roll})", size=13, weight=ft.FontWeight.W_600, color=colors["text"]),
                            reason_field,
                            err_text
                        ], spacing=8, tight=True),
                        width=420
                    ),
                    bgcolor=colors["surface"],
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                        confirm_btn
                    ]
                )
                open_dialog(self.page, dlg)

            # Action buttons
            action_buttons = []
            if status == "Pending":
                action_buttons.extend([
                    ft.ElevatedButton(
                        content=ft.Row([ft.Icon(ft.Icons.CHECK, size=15), ft.Text("Approve", size=13)], spacing=4),
                        style=ft.ButtonStyle(bgcolor="#059669", color=ft.Colors.WHITE, padding=ft.padding.symmetric(horizontal=12, vertical=8)),
                        on_click=approve_req
                    ),
                    ft.ElevatedButton(
                        content=ft.Row([ft.Icon(ft.Icons.CLOSE, size=15), ft.Text("Deny", size=13)], spacing=4),
                        style=ft.ButtonStyle(bgcolor="#dc2626", color=ft.Colors.WHITE, padding=ft.padding.symmetric(horizontal=12, vertical=8)),
                        on_click=deny_dialog
                    )
                ])
            elif status == "Denied":
                action_buttons.append(
                    ft.ElevatedButton(
                        content=ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=15), ft.Text("Re-approve", size=13)], spacing=4),
                        style=ft.ButtonStyle(bgcolor="#059669", color=ft.Colors.WHITE, padding=ft.padding.symmetric(horizontal=12, vertical=8)),
                        on_click=approve_req
                    )
                )
            elif status == "Approved":
                action_buttons.append(
                    ft.ElevatedButton(
                        content=ft.Row([ft.Icon(ft.Icons.BLOCK, size=15), ft.Text("Revoke / Deny", size=13)], spacing=4),
                        style=ft.ButtonStyle(bgcolor="#dc2626", color=ft.Colors.WHITE, padding=ft.padding.symmetric(horizontal=12, vertical=8)),
                        on_click=deny_dialog
                    )
                )

            # Status Badge
            st_color = "#d97706" if status == "Pending" else ("#059669" if status == "Approved" else "#dc2626")
            st_bg = "#fef3c7" if status == "Pending" else ("#d1fae5" if status == "Approved" else "#fee2e2")
            if is_dark:
                st_bg = "#451a03" if status == "Pending" else ("#064e3b" if status == "Approved" else "#450a0a")

            status_badge = ft.Container(
                content=ft.Text(status.upper(), size=11, weight=ft.FontWeight.BOLD, color=st_color),
                bgcolor=st_bg,
                border_radius=6,
                padding=ft.padding.symmetric(horizontal=10, vertical=4)
            )

            # Details card contents
            card_content_items = [
                # Top Header: Student info & Status
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(
                                    content=ft.Icon(ft.Icons.PERSON, size=20, color=colors["primary"]),
                                    bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                                    border_radius=8,
                                    padding=8
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Row([
                                            ft.Text(st_name, size=15, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                            ft.Container(
                                                content=ft.Text(f"Roll: {st_roll}", size=11, weight=ft.FontWeight.W_600, color=colors["primary"]),
                                                bgcolor=ft.Colors.with_opacity(0.1, colors["primary"]),
                                                border_radius=4,
                                                padding=ft.padding.symmetric(horizontal=6, vertical=2)
                                            ),
                                            ft.Container(
                                                content=ft.Text(f"{dept_code} | Year: {st_year}", size=11, color=colors["text_muted"]),
                                                bgcolor=colors.get("surface_variant", "#f1f5f9"),
                                                border_radius=4,
                                                padding=ft.padding.symmetric(horizontal=6, vertical=2)
                                            )
                                        ], spacing=6, wrap=True),
                                        ft.Row([
                                            ft.Icon(ft.Icons.CALENDAR_MONTH, size=13, color=colors["text_muted"]),
                                            ft.Text(f"Submitted: {req_date_str}", size=12, color=colors["text_muted"])
                                        ], spacing=4)
                                    ],
                                    spacing=2
                                )
                            ],
                            spacing=10
                        ),
                        status_badge
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True
                ),
                ft.Divider(color=colors["border"], height=10),
                # Middle: Hostel accommodation details & Actions
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.HOTEL, size=16, color=colors["primary"]),
                                        ft.Text(f"Hostel: {h_name}", size=13, weight=ft.FontWeight.W_600, color=colors["text"])
                                    ], spacing=6),
                                    bgcolor=ft.Colors.with_opacity(0.06, colors["primary"]),
                                    border_radius=6,
                                    padding=ft.padding.symmetric(horizontal=10, vertical=6)
                                ),
                                ft.Container(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.APARTMENT, size=16, color="#2563eb"),
                                        ft.Text(f"Block: {h_block}", size=13, weight=ft.FontWeight.W_600, color=colors["text"])
                                    ], spacing=6),
                                    bgcolor=ft.Colors.with_opacity(0.08, "#2563eb"),
                                    border_radius=6,
                                    padding=ft.padding.symmetric(horizontal=10, vertical=6)
                                ),
                                ft.Container(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.MEETING_ROOM, size=16, color="#059669"),
                                        ft.Text(f"Room: {h_room}", size=13, weight=ft.FontWeight.W_600, color=colors["text"])
                                    ], spacing=6),
                                    bgcolor=ft.Colors.with_opacity(0.08, "#059669"),
                                    border_radius=6,
                                    padding=ft.padding.symmetric(horizontal=10, vertical=6)
                                )
                            ],
                            spacing=10,
                            wrap=True
                        ),
                        ft.Row(controls=action_buttons, spacing=8, wrap=True)
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True
                )
            ]

            if status == "Denied" and deny_reason:
                card_content_items.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.INFO_OUTLINE, size=14, color="#dc2626"),
                            ft.Text(f"Denial Reason: {deny_reason}", size=12, color="#dc2626", weight=ft.FontWeight.W_500)
                        ], spacing=6),
                        bgcolor="#fee2e2" if not is_dark else "#450a0a",
                        border_radius=6,
                        padding=ft.padding.symmetric(horizontal=10, vertical=5),
                        margin=ft.margin.only(top=6)
                    )
                )

            cards.append(
                ft.Container(
                    content=ft.Column(controls=card_content_items, spacing=8),
                    bgcolor=colors["surface"],
                    border=ft.Border.all(1, colors["border"]),
                    border_radius=10,
                    padding=14,
                    margin=ft.margin.only(bottom=8)
                )
            )

        if not cards:
            cards.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.INBOX, size=40, color=colors["text_muted"]),
                        ft.Text("No hostel accommodation requests pending review.", size=14, color=colors["text_muted"])
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    padding=40,
                    alignment=ft.Alignment.CENTER
                )
            )

        return ft.Column(
            controls=[
                ft.Row([
                    ft.Column([
                        ft.Text("Hostel Accommodation Requests", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Text("Review and authorize student hostel residency access", size=13, color=colors["text_muted"])
                    ], spacing=2),
                    ft.Container(
                        content=ft.Text(f"{len(requests)} Requests Total", size=12, weight=ft.FontWeight.W_600, color=colors["primary"]),
                        bgcolor=ft.Colors.with_opacity(0.1, colors["primary"]),
                        border_radius=8,
                        padding=ft.padding.symmetric(horizontal=10, vertical=6)
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                ft.Divider(color=colors["border"], height=8),
                ft.Column(controls=cards, spacing=8)
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: HOD SECURITY CODES
    # -------------------------------------------------------------------------
    def _render_hod_security_codes(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        old_hod_code = ft.TextField(label="Current HOD Security Code", password=True, can_reveal_password=True, dense=True)
        new_hod_code = ft.TextField(label="New HOD Security Code", password=True, can_reveal_password=True, dense=True)
        new_coord_code = ft.TextField(label="New Coordinator Security Code for Your Department", password=True, can_reveal_password=True, dense=True)

        update_hod_btn = ft.ElevatedButton(
            content=ft.Text("Update HOD Code"),
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )
        update_coord_btn = ft.ElevatedButton(
            content=ft.Text("Update Coordinator Code"),
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def save_hod_code(e):
            update_hod_btn.disabled = True
            update_hod_btn.content = ft.Text("Updating...")
            self.page.update()

            ok, msg = SecurityCodeService.update_security_code(
                actor_role=UserRole.HOD.value,
                actor_dept_id=self.department_id,
                target_role=UserRole.HOD.value,
                target_dept_id=self.department_id,
                new_code=new_hod_code.value or "",
                old_code=old_hod_code.value or ""
            )

            update_hod_btn.disabled = False
            update_hod_btn.content = ft.Text("Update HOD Code")
            show_feedback_message(self.page, msg, is_error=not ok)
            self.page.update()

        def save_coord_code(e):
            update_coord_btn.disabled = True
            update_coord_btn.content = ft.Text("Updating...")
            self.page.update()

            ok, msg = SecurityCodeService.update_security_code(
                actor_role=UserRole.HOD.value,
                actor_dept_id=self.department_id,
                target_role=UserRole.COORDINATOR.value,
                target_dept_id=self.department_id,
                new_code=new_coord_code.value or ""
            )

            update_coord_btn.disabled = False
            update_coord_btn.content = ft.Text("Update Coordinator Code")
            show_feedback_message(self.page, msg, is_error=not ok)
            self.page.update()

        update_hod_btn.on_click = save_hod_code
        update_coord_btn.on_click = save_coord_code

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Department Security Codes Management", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.Text(f"Manage staff authorization codes for {self.department_code}.", size=13, color=colors["text_muted"]),
                    ft.Divider(color=colors["border"]),
                    ft.Text("Update HOD Security Code", size=16, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(old_hod_code, col={"xs": 12, "sm": 6}),
                            ft.Container(new_hod_code, col={"xs": 12, "sm": 6})
                        ]
                    ),
                    update_hod_btn,
                    ft.Divider(color=colors["border"]),
                    ft.Text("Update Coordinator Shared Security Code", size=16, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    new_coord_code,
                    update_coord_btn
                ],
                spacing=14,
                scroll=ft.ScrollMode.AUTO
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=14,
            padding=24,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: HOSTEL INCHARGE SECURITY CODE
    # -------------------------------------------------------------------------
    def _render_hostel_security_code(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        old_code = ft.TextField(label="Current Hostel Incharge Security Code", password=True, can_reveal_password=True, dense=True)
        new_code = ft.TextField(label="New Hostel Incharge Security Code", password=True, can_reveal_password=True, dense=True)

        update_btn = ft.ElevatedButton(
            content=ft.Text("Update Code"),
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def save_hostel_code(e):
            update_btn.disabled = True
            update_btn.content = ft.Text("Updating...")
            self.page.update()

            ok, msg = SecurityCodeService.update_security_code(
                actor_role=UserRole.HOSTEL_INCHARGE.value,
                actor_dept_id=None,
                target_role=UserRole.HOSTEL_INCHARGE.value,
                target_dept_id=None,
                new_code=new_code.value or "",
                old_code=old_code.value or ""
            )

            update_btn.disabled = False
            update_btn.content = ft.Text("Update Code")
            show_feedback_message(self.page, msg, is_error=not ok)
            self.page.update()

        update_btn.on_click = save_hostel_code

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Hostel Security Code Management", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(old_code, col={"xs": 12, "sm": 6}),
                            ft.Container(new_code, col={"xs": 12, "sm": 6})
                        ]
                    ),
                    update_btn
                ],
                spacing=14
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=14,
            padding=24,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: GENERAL DEPARTMENT HOD SECURITY CODE
    # -------------------------------------------------------------------------
    def _render_general_security_code(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        old_code = ft.TextField(label="Current General Dept HOD Security Code", password=True, can_reveal_password=True, dense=True)
        new_code = ft.TextField(label="New General Dept HOD Security Code", password=True, can_reveal_password=True, dense=True)

        update_btn = ft.ElevatedButton(
            content=ft.Text("Update Security Code"),
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def save_gen_code(e):
            update_btn.disabled = True
            update_btn.content = ft.Text("Updating...")
            self.page.update()

            ok, msg = SecurityCodeService.update_security_code(
                actor_role=UserRole.GENERAL_HOD.value,
                actor_dept_id=self.department_id,
                target_role=UserRole.GENERAL_HOD.value,
                target_dept_id=self.department_id,
                new_code=new_code.value or "",
                old_code=old_code.value or ""
            )

            update_btn.disabled = False
            update_btn.content = ft.Text("Update Security Code")
            show_feedback_message(self.page, msg, is_error=not ok)
            self.page.update()

        update_btn.on_click = save_gen_code

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("General Department Security Code Management", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.Text("Manage authorization security code for First Year / General Department administration.", size=13, color=colors["text_muted"]),
                    ft.Divider(color=colors["border"]),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(old_code, col={"xs": 12, "sm": 6}),
                            ft.Container(new_code, col={"xs": 12, "sm": 6})
                        ]
                    ),
                    update_btn
                ],
                spacing=14
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=14,
            padding=24,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: LIBRARY INCHARGE SECURITY CODE
    # -------------------------------------------------------------------------
    def _render_library_security_code(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        old_code = ft.TextField(label="Current Library Incharge Security Code", password=True, can_reveal_password=True, dense=True)
        new_code = ft.TextField(label="New Library Incharge Security Code", password=True, can_reveal_password=True, dense=True)

        update_btn = ft.ElevatedButton(
            content=ft.Text("Update Security Code"),
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def save_lib_code(e):
            update_btn.disabled = True
            update_btn.content = ft.Text("Updating...")
            self.page.update()

            ok, msg = SecurityCodeService.update_security_code(
                actor_role=UserRole.LIBRARY_INCHARGE.value,
                actor_dept_id=self.department_id,
                target_role=UserRole.LIBRARY_INCHARGE.value,
                target_dept_id=self.department_id,
                new_code=new_code.value or "",
                old_code=old_code.value or ""
            )

            update_btn.disabled = False
            update_btn.content = ft.Text("Update Security Code")
            show_feedback_message(self.page, msg, is_error=not ok)
            self.page.update()

        update_btn.on_click = save_lib_code

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Library Incharge Security Code Management", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.Text("Manage authorization security code for Campus Library administration.", size=13, color=colors["text_muted"]),
                    ft.Divider(color=colors["border"]),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(old_code, col={"xs": 12, "sm": 6}),
                            ft.Container(new_code, col={"xs": 12, "sm": 6})
                        ]
                    ),
                    update_btn
                ],
                spacing=14
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=14,
            padding=24,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: PRINCIPAL MASTER SECURITY CODES RESET
    # -------------------------------------------------------------------------
    def _render_principal_security_codes(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        client = get_supabase_client()
        depts = client.table("departments").select("id, code, name").execute().data or []

        dept_options = [ft.dropdown.Option(d["id"], f"{d['code']} - {d['name']}") for d in depts]
        target_role = ft.Dropdown(
            label="Target Staff Role",
            options=[
                ft.dropdown.Option(UserRole.HOD.value),
                ft.dropdown.Option(UserRole.COORDINATOR.value),
                ft.dropdown.Option(UserRole.GENERAL_HOD.value),
                ft.dropdown.Option(UserRole.LIBRARY_INCHARGE.value),
                ft.dropdown.Option(UserRole.HOSTEL_INCHARGE.value)
            ],
            value=UserRole.HOD.value,
            dense=True
        )
        target_dept = ft.Dropdown(label="Department (for HOD/Coordinator)", options=dept_options, dense=True, value=dept_options[0].key if dept_options else None)
        new_code_field = ft.TextField(label="New Security Code", password=True, can_reveal_password=True, dense=True)

        reset_btn = ft.ElevatedButton(
            content=ft.Text("Execute Administrative Reset"),
            icon=ft.Icons.LOCK_RESET,
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def do_admin_reset(e):
            reset_btn.disabled = True
            reset_btn.content = ft.Text("Resetting...")
            self.page.update()

            if target_role.value in (UserRole.HOSTEL_INCHARGE.value, UserRole.LIBRARY_INCHARGE.value, UserRole.GENERAL_HOD.value):
                d_id = None
            else:
                d_id = target_dept.value
            ok, msg = SecurityCodeService.update_security_code(
                actor_role=UserRole.PRINCIPAL.value,
                actor_dept_id=None,
                target_role=target_role.value,
                target_dept_id=d_id,
                new_code=new_code_field.value or ""
            )

            reset_btn.disabled = False
            reset_btn.content = ft.Text("Execute Administrative Reset")
            show_feedback_message(self.page, msg, is_error=not ok)
            self.page.update()

        reset_btn.on_click = do_admin_reset

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Principal Master Security Code Administration", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.Text("Administrative privilege: Principal can reset any HOD, Coordinator, or Hostel Incharge security code without previous credentials.", size=13, color=colors["text_muted"]),
                    ft.Divider(color=colors["border"]),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(target_role, col={"xs": 12, "sm": 6}),
                            ft.Container(target_dept, col={"xs": 12, "sm": 6})
                        ]
                    ),
                    new_code_field,
                    reset_btn
                ],
                spacing=14,
                scroll=ft.ScrollMode.AUTO
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=14,
            padding=24,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: LOCATION MANAGER (PRINCIPAL)
    # -------------------------------------------------------------------------
    def _render_location_manager(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        client = get_supabase_client()
        locations = client.table("locations").select("*").order("name").execute().data or []

        new_loc_field = ft.TextField(label="Add New Campus Location", dense=True, width=280)
        add_loc_btn = ft.ElevatedButton(
            content=ft.Text("Add Location"),
            icon=ft.Icons.ADD,
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def add_loc(e):
            name = (new_loc_field.value or "").strip()
            if not name:
                return
            add_loc_btn.disabled = True
            add_loc_btn.content = ft.Text("Adding...")
            self.page.update()

            try:
                client.table("locations").insert({"name": name, "is_active": True}).execute()
                show_feedback_message(self.page, f"Location '{name}' added.", is_error=False)
                new_loc_field.value = ""
                self._switch_view(3)
            except Exception as ex:
                add_loc_btn.disabled = False
                add_loc_btn.content = ft.Text("Add Location")
                show_feedback_message(self.page, f"Failed: {str(ex)}", is_error=True)
                self.page.update()

        add_loc_btn.on_click = add_loc

        loc_rows = []
        for loc in locations:
            lid = loc["id"]
            lname = loc["name"]
            is_act = loc.get("is_active", True)

            def toggle_loc(ev, l_id=lid, cur_act=is_act):
                client.table("locations").update({"is_active": not cur_act}).eq("id", l_id).execute()
                self._switch_view(3)

            loc_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(lname, weight=ft.FontWeight.BOLD, color=colors["text"])),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text("Active" if is_act else "Deactivated", size=11, weight=ft.FontWeight.W_600, color="#059669" if is_act else "#991b1b"),
                                bgcolor="#14532d" if (is_dark and is_act) else ("#450a0a" if is_dark else ("#dcfce7" if is_act else "#fee2e2")),
                                border_radius=8,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2)
                            )
                        ),
                        ft.DataCell(ft.TextButton("Deactivate" if is_act else "Reactivate", on_click=toggle_loc))
                    ]
                )
            )

        loc_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Location Name", color=colors["text"], weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Status", color=colors["text"], weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Action", color=colors["text"], weight=ft.FontWeight.BOLD))
            ],
            rows=loc_rows
        )

        scrollable_loc_table = ft.Row(
            controls=[loc_table],
            scroll=ft.ScrollMode.AUTO
        )

        return ft.Column(
            controls=[
                ft.Text("Campus Location Management", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Row(controls=[new_loc_field, add_loc_btn], wrap=True),
                ft.Divider(color=colors["border"]),
                scrollable_loc_table
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            expand=True
        )

    # -------------------------------------------------------------------------
    # TAB: ANALYTICS & REPORTS
    # -------------------------------------------------------------------------
    def _render_analytics(self) -> ft.Control:
        from ui.views.analytics_view import AnalyticsView
        return AnalyticsView(self.page, self.role, self.department_id).render()

    def _open_detail_dialog(self, complaint: Dict[str, Any]):
        def on_updated():
            self.cached_complaints = None
            self._switch_view(self.selected_tab_index)

        show_complaint_detail_dialog(
            page=self.page,
            complaint=complaint,
            current_role=self.role,
            current_user_id=self.staff_id,
            current_dept_id=self.department_id,
            on_updated=on_updated
        )
