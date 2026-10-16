"""
ui/views/auth_view.py: Authentication screen supporting Student and Staff tabs,
registration with roll number pool checks, role-based staff security codes, account recovery,
full responsive reflow, loading state prevention, and dark mode theming.
"""

import time
import logging
from typing import Callable, Optional, Dict, Any, List
import flet as ft
from services.auth_service import AuthService
from database.supabase_client import get_supabase_client
from ui.theme import (
    MOTION_FAST_MS, MOTION_NORMAL_MS, RADII, SPACING,
    get_button_style, get_input_style, get_responsive_layout,
    get_text_style, get_theme_colors, get_card_shadow, PageContainer,
    DIALOG_MAX_HEIGHT, DIALOG_MAX_WIDTH
)
from ui.state import AppState
from ui.flet_compat import show_feedback_message, open_dialog, close_dialog
from ui.components.animated_chart import create_hero_3d_badge
from ui.components.college_hero import create_login_hero_panel
from models.user import UserRole

logger = logging.getLogger("complaint_box.auth_view")

from services.cache_service import CacheService

DEFAULT_DEPTS = CacheService.DEFAULT_DEPARTMENTS


class AuthView:
    def __init__(self, page: ft.Page, on_authenticated: Callable[[Dict[str, Any], str], None]):
        self.page = page
        self.on_authenticated = on_authenticated
        self.departments = self._load_departments()

    def _load_departments(self) -> List[Dict[str, Any]]:
        with CacheService._lock:
            if CacheService._departments is not None:
                return CacheService._departments
        # Background pre-warm so initial login render has 0ms network latency
        import threading
        threading.Thread(target=CacheService.get_departments, daemon=True).start()
        return CacheService.DEFAULT_DEPARTMENTS

    def _make_alert_box(self) -> ft.Container:
        """Creates an in-form visual banner container for instant feedback."""
        colors = get_theme_colors(AppState.is_dark_mode)
        icon_ctrl = ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.WHITE)
        text_ctrl = ft.Text("", style=get_text_style("body_small", colors["is_dark"], color=ft.Colors.WHITE), weight=ft.FontWeight.W_500, expand=True)
        container = ft.Container(
            content=ft.Row(controls=[icon_ctrl, text_ctrl], spacing=SPACING["md"]),
            border_radius=RADII["md"],
            padding=ft.padding.symmetric(horizontal=SPACING["md"], vertical=SPACING["sm"]),
            visible=False,
            animate_opacity=MOTION_FAST_MS,
        )

        def show(msg: str, is_error: bool = True):
            container.visible = True
            container.bgcolor = colors["danger"] if is_error else colors["success"]
            icon_ctrl.name = ft.Icons.ERROR_OUTLINE if is_error else ft.Icons.CHECK_CIRCLE_OUTLINE
            text_ctrl.value = msg
            self.page.update()

        def hide():
            if container.visible:
                container.visible = False
                self.page.update()

        container.show_alert = show
        container.hide_alert = hide
        return container

    def render(self, initial_tab: int = 0) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)
        raw_width = getattr(self.page, "width", None)
        screen_width = raw_width if isinstance(raw_width, (int, float)) else 1280
        responsive_mode = get_responsive_layout(screen_width)
        viewport_height = getattr(self.page, "height", None)
        tablet_portrait = responsive_mode == "tablet" and (
            not isinstance(viewport_height, (int, float)) or viewport_height > screen_width
        )
        is_compact = responsive_mode == "mobile" or tablet_portrait
        input_style = get_input_style(is_dark)

        def style_form_field(field):
            """Apply shared input tokens without changing a field's handlers."""
            for name, value in input_style.items():
                if hasattr(field, name):
                    setattr(field, name, value)
            field.error_style = get_text_style("caption", is_dark, color=colors["danger"])
            original_on_change = getattr(field, "on_change", None)
            if original_on_change is not None:
                def clear_inline_error(e, current=field, handler=original_on_change):
                    current.error_text = None
                    handler(e)
                field.on_change = clear_inline_error
            original_on_select = getattr(field, "on_select", None)
            if original_on_select is not None:
                def clear_select_error(e, current=field, handler=original_on_select):
                    current.error_text = None
                    handler(e)
                field.on_select = clear_select_error
            return field

        def set_inline_error(field, message="Required"):
            field.error_text = message

        def clear_inline_errors(*fields):
            for field in fields:
                field.error_text = None

        # In-form visual alert banners
        alert_st_login = self._make_alert_box()
        alert_st_reg = self._make_alert_box()
        alert_sf_login = self._make_alert_box()
        alert_sf_reg = self._make_alert_box()

        # Shared department dropdown options (academic departments only)
        academic_depts = [d for d in self.departments if d.get("code") not in ("GEN", "LIB")]
        dept_options = [
            ft.dropdown.Option(d.get("id") or d["code"], f"{d['code']} - {d['name']}")
            for d in (academic_depts or self.departments)
        ]

        # ---------------------------------------------------------------------
        # TAB 1: STUDENT LOGIN CONTROLS
        # ---------------------------------------------------------------------
        st_login_roll = ft.TextField(label="Roll Number / Student ID", prefix_icon=ft.Icons.BADGE_OUTLINED, dense=True, on_change=lambda e: setattr(st_login_roll, "value", e.control.value))
        st_login_pass = ft.TextField(label="Password", prefix_icon=ft.Icons.LOCK_OUTLINED, password=True, can_reveal_password=True, dense=True, on_change=lambda e: setattr(st_login_pass, "value", e.control.value))
        btn_st_login = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.LOGIN, color=ft.Colors.WHITE, size=18),
                    ft.Text("Login", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8
            ),
            style=get_button_style(is_dark, size="lg")
        )

        def do_student_login(e):
            if btn_st_login.disabled:
                return
            alert_st_login.hide_alert()
            clear_inline_errors(st_login_roll, st_login_pass)
            roll_val = (st_login_roll.value or "").strip()
            pass_val = (st_login_pass.value or "").strip()

            if not roll_val or not pass_val:
                if not roll_val:
                    set_inline_error(st_login_roll)
                if not pass_val:
                    set_inline_error(st_login_pass)
                alert_st_login.show_alert("Please enter both Roll Number and Password.", is_error=True)
                show_feedback_message(self.page, "Please enter both Roll Number and Password.", is_error=True)
                return

            def _reset_student_btn():
                btn_st_login.disabled = False
                btn_st_login.content = ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.LOGIN, color=ft.Colors.WHITE, size=18),
                        ft.Text("Login", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8
                )

            btn_st_login.disabled = True
            btn_st_login.content = ft.Row(
                controls=[
                    ft.ProgressRing(width=16, height=16, stroke_width=2, color=ft.Colors.WHITE),
                    ft.Text("Signing in...", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8
            )
            self.page.update()

            def authenticate_student():
                t0 = time.perf_counter()
                try:
                    ok, msg, student = AuthService.login_student(roll_val, pass_val)
                    logger.info("Student auth query completed in %.3fs", time.perf_counter() - t0)
                    if ok and student:
                        show_feedback_message(self.page, "Login successful!", is_error=False)
                        try:
                            self.on_authenticated(student, UserRole.STUDENT.value)
                        except Exception as auth_cb_ex:
                            logger.exception("Student auth callback failed (%s)", type(auth_cb_ex).__name__)
                            _reset_student_btn()
                            self.page.update()
                    else:
                        _reset_student_btn()
                        alert_st_login.show_alert(msg, is_error=True)
                        show_feedback_message(self.page, msg, is_error=True)
                        self.page.update()
                except Exception as ex:
                    logger.warning("Student login failed (%s)", type(ex).__name__)
                    _reset_student_btn()
                    alert_st_login.show_alert("Unable to complete login. Please try again.", is_error=True)
                    show_feedback_message(self.page, "Unable to complete login. Please try again.", is_error=True)
                    self.page.update()

            self.page.run_thread(authenticate_student)

        btn_st_login.on_click = do_student_login
        st_login_roll.on_submit = do_student_login
        st_login_pass.on_submit = do_student_login

        # ---------------------------------------------------------------------
        # TAB 2: STUDENT REGISTRATION CONTROLS
        # ---------------------------------------------------------------------
        st_reg_roll = ft.TextField(label="Roll Number / Student ID", hint_text="Must be present in department pool", prefix_icon=ft.Icons.BADGE_OUTLINED, dense=True, on_change=lambda e: setattr(st_reg_roll, "value", e.control.value))
        st_reg_name = ft.TextField(label="Full Name", prefix_icon=ft.Icons.PERSON_OUTLINED, dense=True, on_change=lambda e: setattr(st_reg_name, "value", e.control.value))
        st_reg_dept = ft.Dropdown(label="Academic Department", options=dept_options, dense=True, value=dept_options[0].key if dept_options else None)
        st_reg_year = ft.Dropdown(
            label="Year of Study",
            options=[
                ft.dropdown.Option("FE", "First Year (FE)"),
                ft.dropdown.Option("SE", "Second Year (SE)"),
                ft.dropdown.Option("TE", "Third Year (TE)"),
                ft.dropdown.Option("BE", "Final Year (BE)")
            ],
            dense=True,
            value="FE"
        )
        st_reg_pass = ft.TextField(
            label="Password",
            prefix_icon=ft.Icons.LOCK_OUTLINED,
            password=True,
            can_reveal_password=True,
            dense=True,
            on_change=lambda e: setattr(st_reg_pass, "value", e.control.value),
        )
        st_reg_q = ft.TextField(label="Security Question", hint_text="e.g. What was your first school?", dense=True, on_change=lambda e: setattr(st_reg_q, "value", e.control.value))
        st_reg_ans = ft.TextField(label="Security Answer", dense=True, on_change=lambda e: setattr(st_reg_ans, "value", e.control.value))

        st_reg_hostel = ft.Checkbox(label="I reside in the College Hostel", value=False)
        st_hostel_name = ft.TextField(label="Hostel Name", hint_text="e.g. Boys Hostel", dense=True, visible=False)
        st_hostel_block = ft.TextField(label="Block", hint_text="e.g. A", dense=True, visible=False)
        st_hostel_room = ft.TextField(label="Room Number", hint_text="e.g. 101", dense=True, visible=False)

        for field in (
            st_login_roll, st_login_pass, st_reg_roll, st_reg_name, st_reg_dept,
            st_reg_year, st_reg_pass, st_reg_q, st_reg_ans, st_hostel_name,
            st_hostel_block, st_hostel_room,
        ):
            style_form_field(field)

        def on_hostel_toggle(e):
            is_hostel = bool(st_reg_hostel.value)
            st_hostel_name.visible = is_hostel
            st_hostel_block.visible = is_hostel
            st_hostel_room.visible = is_hostel
            self.page.update()

        st_reg_hostel.on_change = on_hostel_toggle
        btn_st_reg = ft.ElevatedButton("Register Account", icon=ft.Icons.HOW_TO_REG, style=get_button_style(is_dark, size="lg"))

        def do_student_register(e):
            if btn_st_reg.disabled:
                return
            alert_st_reg.hide_alert()
            clear_inline_errors(st_reg_roll, st_reg_name, st_reg_pass, st_reg_q, st_reg_ans)
            roll_val = (st_reg_roll.value or "").strip()
            name_val = (st_reg_name.value or "").strip()
            dept_val = st_reg_dept.value
            year_val = st_reg_year.value or "FE"
            pass_val = (st_reg_pass.value or "").strip()
            q_val = (st_reg_q.value or "").strip()
            ans_val = (st_reg_ans.value or "").strip()

            if not roll_val or not name_val or not pass_val or not q_val or not ans_val:
                for field, value in (
                    (st_reg_roll, roll_val), (st_reg_name, name_val),
                    (st_reg_pass, pass_val), (st_reg_q, q_val), (st_reg_ans, ans_val),
                ):
                    if not value:
                        set_inline_error(field)
                alert_st_reg.show_alert("Please fill in all required registration fields.", is_error=True)
                show_feedback_message(self.page, "Please fill in all required registration fields.", is_error=True)
                return

            btn_st_reg.disabled = True
            btn_st_reg.content = "Creating Account..."
            self.page.update()

            hostel_val = bool(st_reg_hostel.value)
            hostel_details = None
            if hostel_val:
                hostel_details = {
                    "hostel_name": st_hostel_name.value or "Campus Hostel",
                    "block": st_hostel_block.value or "A",
                    "room_number": st_hostel_room.value or "101"
                }

            def register_student():
                try:
                    ok, msg, new_st = AuthService.register_student(
                        roll_number=roll_val,
                        full_name=name_val,
                        department_id=dept_val,
                        year=year_val,
                        password=pass_val,
                        security_question=q_val,
                        security_answer=ans_val,
                        is_hostel=hostel_val,
                        hostel_details=hostel_details
                    )

                    if ok and new_st:
                        alert_st_reg.show_alert(f"Account for {roll_val} registered successfully! You can now log in.", is_error=False)
                        show_feedback_message(self.page, "Registration successful! You can now log in.", is_error=False)
                        st_reg_roll.value = ""
                        st_reg_name.value = ""
                        st_reg_pass.value = ""
                        st_reg_q.value = ""
                        st_reg_ans.value = ""
                        st_reg_hostel.value = False
                        st_hostel_name.visible = False
                        st_hostel_block.visible = False
                        st_hostel_room.visible = False
                        st_login_roll.value = ""
                        st_login_pass.value = ""
                        self.page.update()
                    else:
                        alert_st_reg.show_alert(msg, is_error=True)
                        show_feedback_message(self.page, msg, is_error=True)
                except Exception as ex:
                    logger.warning("Student registration failed (%s)", type(ex).__name__)
                    alert_st_reg.show_alert("Unable to complete registration. Please try again.", is_error=True)
                    show_feedback_message(self.page, "Unable to complete registration. Please try again.", is_error=True)
                finally:
                    btn_st_reg.disabled = False
                    btn_st_reg.content = "Register Account"
                    self.page.update()

            self.page.run_thread(register_student)

        btn_st_reg.on_click = do_student_register
        st_reg_ans.on_submit = do_student_register

        # ---------------------------------------------------------------------
        # TAB 3: STAFF LOGIN CONTROLS (6 Administrative Roles)
        # ---------------------------------------------------------------------
        staff_roles = [
            ft.dropdown.Option(UserRole.COORDINATOR.value, "Department Coordinator"),
            ft.dropdown.Option(UserRole.HOD.value, "Head of Department (HOD)"),
            ft.dropdown.Option(UserRole.GENERAL_HOD.value, "General Department HOD (First Year)"),
            ft.dropdown.Option(UserRole.HOSTEL_INCHARGE.value, "Hostel Incharge"),
            ft.dropdown.Option(UserRole.LIBRARY_INCHARGE.value, "Library Incharge"),
            ft.dropdown.Option(UserRole.PRINCIPAL.value, "Principal (Highest Authority)")
        ]
        sf_login_role = ft.Dropdown(label="Staff Role", options=staff_roles, value=UserRole.COORDINATOR.value, dense=True)
        sf_login_dept = ft.Dropdown(label="Department", options=dept_options, dense=True, value=dept_options[0].key if dept_options else None)
        sf_login_dept_col = ft.Container(sf_login_dept, col={"xs": 12, "sm": 6})
        sf_login_user = ft.TextField(label="Staff Username / ID", prefix_icon=ft.Icons.PERSON_OUTLINED, dense=True, on_change=lambda e: setattr(sf_login_user, "value", e.control.value))
        sf_login_pass = ft.TextField(label="Password", prefix_icon=ft.Icons.LOCK_OUTLINED, password=True, can_reveal_password=True, dense=True, on_change=lambda e: setattr(sf_login_pass, "value", e.control.value))
        sf_login_code = ft.TextField(label="Staff Security Code", hint_text="Role Authority Code", prefix_icon=ft.Icons.KEY_OUTLINED, password=True, can_reveal_password=True, dense=True, on_change=lambda e: setattr(sf_login_code, "value", e.control.value))

        for field in (sf_login_role, sf_login_dept, sf_login_user, sf_login_pass, sf_login_code):
            style_form_field(field)

        def on_staff_role_change(e):
            needs_dept = sf_login_role.value in (UserRole.HOD.value, UserRole.COORDINATOR.value)
            sf_login_dept.visible = needs_dept
            sf_login_dept_col.visible = needs_dept
            self.page.update()

        sf_login_role.on_change = on_staff_role_change
        btn_sf_login = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.LOCK_OPEN, color=ft.Colors.WHITE, size=18),
                    ft.Text("Staff Sign In", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8
            ),
            style=get_button_style(is_dark, size="lg")
        )

        def do_staff_login(e):
            if btn_sf_login.disabled:
                return
            alert_sf_login.hide_alert()
            clear_inline_errors(sf_login_user, sf_login_pass, sf_login_code)
            role_val = sf_login_role.value
            dept_val = sf_login_dept.value if (sf_login_dept.visible and role_val in (UserRole.HOD.value, UserRole.COORDINATOR.value)) else None
            if role_val in (UserRole.PRINCIPAL.value, UserRole.HOSTEL_INCHARGE.value, UserRole.LIBRARY_INCHARGE.value):
                dept_val = None
            elif role_val == UserRole.GENERAL_HOD.value:
                dept_val = SecurityCodeService._get_special_dept_id("GEN")
            user_val = (sf_login_user.value or "").strip()
            pass_val = (sf_login_pass.value or "").strip()
            code_val = (sf_login_code.value or "").strip()

            if not user_val or not pass_val or not code_val:
                for field, value in (
                    (sf_login_user, user_val), (sf_login_pass, pass_val),
                    (sf_login_code, code_val),
                ):
                    if not value:
                        set_inline_error(field)
                alert_sf_login.show_alert("Invalid username, password, or security code.", is_error=True)
                show_feedback_message(self.page, "Invalid username, password, or security code.", is_error=True)
                return

            def _reset_staff_btn():
                btn_sf_login.disabled = False
                btn_sf_login.content = ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.LOCK_OPEN, color=ft.Colors.WHITE, size=18),
                        ft.Text("Staff Sign In", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8
                )

            btn_sf_login.disabled = True
            btn_sf_login.content = ft.Row(
                controls=[
                    ft.ProgressRing(width=16, height=16, stroke_width=2, color=ft.Colors.WHITE),
                    ft.Text("Signing in...", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8
            )
            self.page.update()

            def authenticate_staff():
                t0 = time.perf_counter()
                try:
                    ok, msg, staff = AuthService.login_staff(
                        role=role_val,
                        username=user_val,
                        password=pass_val,
                        security_code=code_val,
                        department_id=dept_val
                    )
                    logger.info("Staff auth query completed in %.3fs", time.perf_counter() - t0)
                    if ok and staff:
                        show_feedback_message(self.page, "Staff login successful!", is_error=False)
                        try:
                            self.on_authenticated(staff, role_val)
                        except Exception as auth_cb_ex:
                            logger.exception("Staff auth callback failed (%s)", type(auth_cb_ex).__name__)
                            _reset_staff_btn()
                            self.page.update()
                    else:
                        _reset_staff_btn()
                        alert_sf_login.show_alert(msg, is_error=True)
                        show_feedback_message(self.page, msg, is_error=True)
                        self.page.update()
                except Exception as ex:
                    logger.warning("Staff login failed (%s)", type(ex).__name__)
                    _reset_staff_btn()
                    alert_sf_login.show_alert("Invalid username, password, or security code.", is_error=True)
                    show_feedback_message(self.page, "Invalid username, password, or security code.", is_error=True)
                    self.page.update()

            self.page.run_thread(authenticate_staff)

        btn_sf_login.on_click = do_staff_login
        sf_login_code.on_submit = do_staff_login

        # ---------------------------------------------------------------------
        # TAB 4: STAFF REGISTRATION CONTROLS
        # ---------------------------------------------------------------------
        sf_reg_role = ft.Dropdown(label="Select Staff Role", options=staff_roles, value=UserRole.COORDINATOR.value, dense=True)
        sf_reg_dept = ft.Dropdown(label="Department", options=dept_options, dense=True, value=dept_options[0].key if dept_options else None)
        sf_reg_dept_col = ft.Container(sf_reg_dept, col={"xs": 12, "sm": 6})
        sf_reg_name = ft.TextField(label="Full Name", prefix_icon=ft.Icons.PERSON_OUTLINED, dense=True, on_change=lambda e: setattr(sf_reg_name, "value", e.control.value))
        sf_reg_user = ft.TextField(label="Desired Username", prefix_icon=ft.Icons.BADGE_OUTLINED, dense=True, on_change=lambda e: setattr(sf_reg_user, "value", e.control.value))
        sf_reg_pass = ft.TextField(label="Password", prefix_icon=ft.Icons.LOCK_OUTLINED, password=True, can_reveal_password=True, dense=True, on_change=lambda e: setattr(sf_reg_pass, "value", e.control.value))
        sf_reg_code = ft.TextField(label="Role Security Code", hint_text="Required to verify authority", prefix_icon=ft.Icons.KEY_OUTLINED, password=True, can_reveal_password=True, dense=True, on_change=lambda e: setattr(sf_reg_code, "value", e.control.value))
        sf_reg_q = ft.TextField(label="Security Question", hint_text="e.g. First school or favourite teacher", dense=True, on_change=lambda e: setattr(sf_reg_q, "value", e.control.value))
        sf_reg_ans = ft.TextField(label="Security Answer", dense=True, on_change=lambda e: setattr(sf_reg_ans, "value", e.control.value))

        for field in (sf_reg_role, sf_reg_dept, sf_reg_name, sf_reg_user, sf_reg_pass, sf_reg_code, sf_reg_q, sf_reg_ans):
            style_form_field(field)

        def on_reg_staff_role_change(e):
            needs_dept = sf_reg_role.value in (UserRole.HOD.value, UserRole.COORDINATOR.value)
            sf_reg_dept.visible = needs_dept
            sf_reg_dept_col.visible = needs_dept
            self.page.update()

        sf_reg_role.on_change = on_reg_staff_role_change
        btn_sf_reg = ft.ElevatedButton("Create Staff Account", icon=ft.Icons.BADGE, style=get_button_style(is_dark, size="lg"))

        def do_staff_register(e):
            if btn_sf_reg.disabled:
                return
            alert_sf_reg.hide_alert()
            clear_inline_errors(sf_reg_name, sf_reg_user, sf_reg_dept, sf_reg_code)
            role_val = sf_reg_role.value
            dept_val = sf_reg_dept.value if (sf_reg_dept.visible and role_val in (UserRole.HOD.value, UserRole.COORDINATOR.value)) else None
            if role_val in (UserRole.PRINCIPAL.value, UserRole.HOSTEL_INCHARGE.value, UserRole.LIBRARY_INCHARGE.value):
                dept_val = None
            elif role_val == UserRole.GENERAL_HOD.value:
                dept_val = SecurityCodeService._get_special_dept_id("GEN")
            user_val = (sf_reg_user.value or "").strip()
            name_val = (sf_reg_name.value or "").strip()
            pass_val = (sf_reg_pass.value or "").strip()
            code_val = (sf_reg_code.value or "").strip()
            q_val = (sf_reg_q.value or "").strip()
            ans_val = (sf_reg_ans.value or "").strip()

            if not user_val or not name_val:
                if not user_val:
                    set_inline_error(sf_reg_user)
                if not name_val:
                    set_inline_error(sf_reg_name)
                alert_sf_reg.show_alert("Username and Full Name are required.", is_error=True)
                show_feedback_message(self.page, "Username and Full Name are required.", is_error=True)
                return

            if role_val in (UserRole.HOD.value, UserRole.COORDINATOR.value) and not dept_val:
                set_inline_error(sf_reg_dept)
                alert_sf_reg.show_alert(f"Department selection is required for {role_val}.", is_error=True)
                show_feedback_message(self.page, f"Department selection is required for {role_val}.", is_error=True)
                return

            if not code_val:
                set_inline_error(sf_reg_code)
                alert_sf_reg.show_alert("Role Security Code is required.", is_error=True)
                show_feedback_message(self.page, "Role Security Code is required.", is_error=True)
                return

            btn_sf_reg.disabled = True
            btn_sf_reg.content = "Creating Account..."
            self.page.update()

            def register_staff():
                try:
                    ok, msg, new_staff = AuthService.register_staff(
                        username=user_val,
                        full_name=name_val,
                        role=role_val,
                        department_id=dept_val,
                        password=pass_val,
                        security_question=q_val,
                        security_answer=ans_val,
                        security_code=code_val
                    )
                    if ok and new_staff:
                        alert_sf_reg.show_alert(f"Staff account '{user_val}' created successfully! You can now log in.", is_error=False)
                        show_feedback_message(self.page, "Staff account created successfully! You can now log in.", is_error=False)
                        sf_reg_user.value = ""
                        sf_reg_name.value = ""
                        sf_reg_pass.value = ""
                        sf_reg_code.value = ""
                        sf_reg_q.value = ""
                        sf_reg_ans.value = ""
                        sf_login_user.value = ""
                        sf_login_pass.value = ""
                        sf_login_code.value = ""
                        self.page.update()
                    else:
                        alert_sf_reg.show_alert(msg, is_error=True)
                        show_feedback_message(self.page, msg, is_error=True)
                except Exception as ex:
                    logger.warning("Staff registration failed (%s)", type(ex).__name__)
                    alert_sf_reg.show_alert("Unable to create staff account. Please try again.", is_error=True)
                    show_feedback_message(self.page, "Unable to create staff account. Please try again.", is_error=True)
                finally:
                    btn_sf_reg.disabled = False
                    btn_sf_reg.content = "Create Staff Account"
                    self.page.update()

            self.page.run_thread(register_staff)

        btn_sf_reg.on_click = do_staff_register
        sf_reg_ans.on_submit = do_staff_register

        # ---------------------------------------------------------------------
        # FORGOT PASSWORD MODAL
        # ---------------------------------------------------------------------
        def show_forgot_password(e):
            recov_roll = style_form_field(ft.TextField(label="Enter Student ID / Roll Number", dense=True))
            question_text = ft.Text("", weight=ft.FontWeight.BOLD, color=colors["primary"], visible=False)
            recov_ans = style_form_field(ft.TextField(label="Your Security Answer", dense=True, visible=False))
            recov_new_pass = style_form_field(ft.TextField(label="New Password", password=True, can_reveal_password=True, dense=True, visible=False))
            recov_btn = ft.ElevatedButton("Find Account", icon=ft.Icons.SEARCH, style=get_button_style(is_dark))

            def on_recov_action(ev):
                if recov_btn.disabled:
                    return
                finding_question = not question_text.visible
                roll_val = recov_roll.value or ""
                answer_val = recov_ans.value or ""
                new_password_val = recov_new_pass.value or ""
                recov_btn.disabled = True
                recov_btn.content = "Looking up account…" if finding_question else "Resetting password…"
                self.page.update()

                def recover_student_password():
                    succeeded = False
                    try:
                        if finding_question:
                            ok, msg, question = AuthService.get_student_security_question(roll_val)
                            if ok and question:
                                question_text.value = f"Security Question: {question}"
                                question_text.visible = True
                                recov_ans.visible = True
                                recov_new_pass.visible = True
                                recov_btn.content = "Reset & Unlock"
                                recov_btn.icon = ft.Icons.LOCK_RESET
                                succeeded = True
                            else:
                                recov_roll.error_text = msg or "Account not found."
                                show_feedback_message(self.page, msg or "Account not found.", is_error=True)
                        else:
                            ok, msg = AuthService.reset_student_password(
                                roll_number=roll_val,
                                security_answer=answer_val,
                                new_password=new_password_val
                            )
                            if ok:
                                show_feedback_message(self.page, msg, is_error=False)
                                close_dialog(self.page, dlg)
                                succeeded = True
                            else:
                                recov_ans.error_text = msg
                                recov_new_pass.error_text = msg
                                show_feedback_message(self.page, msg, is_error=True)
                    except Exception as exc:
                        logger.warning("Student password recovery failed (%s)", type(exc).__name__)
                        show_feedback_message(self.page, "Unable to complete password recovery. Please try again.", is_error=True)
                    finally:
                        recov_btn.disabled = False
                        if not succeeded:
                            recov_btn.content = "Find Account" if finding_question else "Reset & Unlock"
                        try:
                            self.page.update()
                        except Exception:
                            pass

                self.page.run_thread(recover_student_password)

            recov_btn.on_click = on_recov_action
            recov_roll.on_submit = on_recov_action
            recov_new_pass.on_submit = on_recov_action

            dlg = ft.AlertDialog(
                title=ft.Text("Password Recovery & Account Unlock", style=get_text_style("title", is_dark)),
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Answer your security question to set a new password and unlock your account.", style=get_text_style("body_small", is_dark)),
                            recov_roll,
                            question_text,
                            recov_ans,
                            recov_new_pass,
                            recov_btn
                        ],
                        spacing=SPACING["md"],
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    width=min(DIALOG_MAX_WIDTH / 2, max(SPACING["3xl"], screen_width - 2 * SPACING["lg"])),
                    height=DIALOG_MAX_HEIGHT / 2,
                    padding=SPACING["md"],
                    bgcolor=colors["surface"],
                    border_radius=RADII["lg"],
                ),
                actions=[ft.TextButton("Cancel", style=get_button_style(is_dark, "text"), on_click=lambda _: close_dialog(self.page, dlg))]
            )
            open_dialog(self.page, dlg)

        # ---------------------------------------------------------------------
        # RESPONSIVE TABS CONTAINER
        # ---------------------------------------------------------------------
        tab1_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Student Portal Access", style=get_text_style("title", is_dark, color=colors["primary"]), weight=ft.FontWeight.BOLD),
                    ft.Text("Enter your registered Roll Number and Password to access your grievance portal.", style=get_text_style("body_small", is_dark)),
                    alert_st_login,
                    st_login_roll,
                    st_login_pass,
                    ft.Row(
                        controls=[
                            ft.TextButton("Forgot Password / Locked?", style=get_button_style(is_dark, "text"), on_click=show_forgot_password),
                            btn_st_login
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        wrap=True
                    )
                ],
                spacing=SPACING["sm"] if is_compact else SPACING["md"],
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.symmetric(horizontal=SPACING["lg"], vertical=SPACING["sm"] if is_compact else SPACING["xl"])
        )

        tab2_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("New Student Registration", style=get_text_style("title", is_dark, color=colors["primary"]), weight=ft.FontWeight.BOLD),
                    ft.Text("Note: Roll Number must be authorized by your Coordinator in the department pool.", style=get_text_style("body_small", is_dark)),
                    alert_st_reg,
                    ft.ResponsiveRow(controls=[
                        ft.Container(st_reg_roll, col={"xs": 12, "sm": 6}),
                        ft.Container(st_reg_name, col={"xs": 12, "sm": 6}),
                    ]),
                    ft.ResponsiveRow(controls=[
                        ft.Container(st_reg_dept, col={"xs": 12, "sm": 6}),
                        ft.Container(st_reg_year, col={"xs": 12, "sm": 6}),
                    ]),
                    st_reg_pass,
                    ft.Text("Minimum 8 characters with uppercase, lowercase, number and symbol.", style=get_text_style("caption", is_dark)),
                    ft.ResponsiveRow(controls=[
                        ft.Container(st_reg_q, col={"xs": 12, "sm": 6}),
                        ft.Container(st_reg_ans, col={"xs": 12, "sm": 6}),
                    ]),
                    st_reg_hostel,
                    ft.ResponsiveRow(controls=[
                        ft.Container(st_hostel_name, col={"xs": 12, "sm": 4}),
                        ft.Container(st_hostel_block, col={"xs": 12, "sm": 4}),
                        ft.Container(st_hostel_room, col={"xs": 12, "sm": 4}),
                    ]),
                    btn_st_reg
                ],
                spacing=SPACING["md"],
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.symmetric(horizontal=SPACING["lg"], vertical=SPACING["xl"])
        )

        tab3_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Staff / Administration Login", style=get_text_style("title", is_dark, color=colors["primary"]), weight=ft.FontWeight.BOLD),
                    ft.Text("Requires valid staff credentials and role security code.", style=get_text_style("body_small", is_dark)),
                    alert_sf_login,
                    ft.ResponsiveRow(controls=[
                        ft.Container(sf_login_role, col={"xs": 12, "sm": 6}),
                        sf_login_dept_col,
                    ]),
                    sf_login_user,
                    sf_login_pass,
                    sf_login_code,
                    btn_sf_login
                ],
                spacing=SPACING["md"],
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.symmetric(horizontal=SPACING["lg"], vertical=SPACING["xl"])
        )

        tab4_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Staff Self-Registration", style=get_text_style("title", is_dark, color=colors["primary"]), weight=ft.FontWeight.BOLD),
                    ft.Text("Authorized faculty registration with department verification.", style=get_text_style("body_small", is_dark)),
                    alert_sf_reg,
                    ft.ResponsiveRow(controls=[
                        ft.Container(sf_reg_role, col={"xs": 12, "sm": 6}),
                        sf_reg_dept_col,
                    ]),
                    ft.ResponsiveRow(controls=[
                        ft.Container(sf_reg_name, col={"xs": 12, "sm": 6}),
                        ft.Container(sf_reg_user, col={"xs": 12, "sm": 6}),
                    ]),
                    sf_reg_pass,
                    ft.Text("Minimum 8 characters.", style=get_text_style("caption", is_dark)),
                    sf_reg_code,
                    ft.ResponsiveRow(controls=[
                        ft.Container(sf_reg_q, col={"xs": 12, "sm": 6}),
                        ft.Container(sf_reg_ans, col={"xs": 12, "sm": 6}),
                    ]),
                    btn_sf_reg
                ],
                spacing=SPACING["md"],
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.symmetric(horizontal=SPACING["lg"], vertical=SPACING["xl"])
        )

        selected_portal = 1 if initial_tab >= 2 else 0
        selected_mode = initial_tab % 2
        tab_animation = ft.Duration(milliseconds=MOTION_NORMAL_MS)

        student_tabs = ft.Tabs(
            selected_index=selected_mode,
            length=2,
            animation_duration=tab_animation,
            content=ft.Column(expand=True, controls=[
                ft.TabBar(tabs=[
                    ft.Tab(label="Login", icon=ft.Icons.LOGIN),
                    ft.Tab(label="Create Account", icon=ft.Icons.PERSON_ADD),
                ], visible=False),
                ft.TabBarView(expand=True, controls=[tab1_content, tab2_content]),
            ]),
            expand=True,
        )
        staff_tabs = ft.Tabs(
            selected_index=selected_mode,
            length=2,
            animation_duration=tab_animation,
            content=ft.Column(expand=True, controls=[
                ft.TabBar(tabs=[
                    ft.Tab(label="Login", icon=ft.Icons.LOGIN),
                    ft.Tab(label="Create Account", icon=ft.Icons.PERSON_ADD),
                ], visible=False),
                ft.TabBarView(expand=True, controls=[tab3_content, tab4_content]),
            ]),
            expand=True,
        )
        tabs = ft.Tabs(
            selected_index=selected_portal,
            length=2,
            animation_duration=tab_animation,
            content=ft.Column(expand=True, controls=[
                ft.TabBar(tabs=[
                    ft.Tab(label="Student Portal", icon=ft.Icons.SCHOOL),
                    ft.Tab(label="Staff Portal", icon=ft.Icons.ADMIN_PANEL_SETTINGS),
                ], visible=False),
                ft.TabBarView(expand=True, controls=[student_tabs, staff_tabs]),
            ]),
            expand=True,
        )

        segmented_style = ft.ButtonStyle(
            bgcolor={
                ft.ControlState.DEFAULT: colors["surface_variant"],
                ft.ControlState.SELECTED: colors["primary"],
            },
            color={
                ft.ControlState.DEFAULT: colors["text_muted"],
                ft.ControlState.SELECTED: ft.Colors.WHITE,
            },
            side=ft.BorderSide(1, colors["border"]),
            shape=ft.RoundedRectangleBorder(radius=RADII["pill"]),
            padding=ft.padding.symmetric(horizontal=SPACING["md"], vertical=SPACING["sm"]),
        )
        portal_selector = ft.SegmentedButton(
            segments=[
                ft.Segment(value="student", icon=ft.Icons.SCHOOL, label="Student Portal"),
                ft.Segment(value="staff", icon=ft.Icons.ADMIN_PANEL_SETTINGS, label="Staff Portal"),
            ],
            selected=["staff" if selected_portal else "student"],
            show_selected_icon=False,
            style=segmented_style,
            expand=True,
        )
        mode_selector = ft.SegmentedButton(
            segments=[
                ft.Segment(value="login", icon=ft.Icons.LOGIN, label="Login"),
                ft.Segment(value="register", icon=ft.Icons.PERSON_ADD, label="Create Account"),
            ],
            selected=["register" if selected_mode else "login"],
            show_selected_icon=False,
            style=segmented_style,
            expand=True,
        )

        def on_portal_change(e):
            selected = e.control.selected[0]
            tabs.selected_index = 1 if selected == "staff" else 0
            active_tabs = staff_tabs if selected == "staff" else student_tabs
            mode_selector.selected = ["register" if active_tabs.selected_index else "login"]
            self.page.update()

        def on_mode_change(e):
            selected = e.control.selected[0]
            active_tabs = staff_tabs if tabs.selected_index else student_tabs
            active_tabs.selected_index = 1 if selected == "register" else 0
            self.page.update()

        portal_selector.on_change = on_portal_change
        mode_selector.on_change = on_mode_change

        card_header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=24, color=colors["primary"]),
                        bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                        border_radius=RADII["md"],
                        padding=SPACING["sm"]
                    ),
                    ft.Column(
                        controls=[
                            ft.Text("Welcome back", style=get_text_style("title", is_dark)),
                            ft.Text("Sign in or create your campus account", style=get_text_style("caption", is_dark))
                        ],
                        spacing=1
                    )
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
            padding=ft.padding.only(
                left=SPACING["lg"],
                right=SPACING["lg"],
                top=SPACING["sm"] if is_compact else SPACING["lg"],
                bottom=SPACING["xs"] if is_compact else SPACING["sm"]
            )
        )

        auth_height = DIALOG_MAX_HEIGHT - SPACING["3xl"]
        auth_card = ft.Container(
            content=ft.Column(
                controls=[
                    card_header,
                    ft.Container(content=portal_selector, padding=ft.padding.symmetric(horizontal=SPACING["lg"], vertical=SPACING["xs"])),
                    ft.Container(content=mode_selector, padding=ft.padding.symmetric(horizontal=SPACING["lg"], vertical=SPACING["xs"])),
                    ft.Divider(height=1, color=colors["border"]),
                    tabs
                ],
                spacing=SPACING["xs"],
                expand=True
            ),
            bgcolor=colors["card_bg"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=RADII["xl"],
            shadow=get_card_shadow(is_dark),
            height=auth_height,
            col={"xs": 12, "lg": 7},
            animate_opacity=MOTION_FAST_MS,
        )

        if is_compact:
            compact_brand = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Icon(ft.Icons.ACCOUNT_BALANCE, size=22, color=colors["primary"]),
                            bgcolor=colors["surface"],
                            border=ft.Border.all(1, colors["border"]),
                            border_radius=RADII["md"],
                            padding=SPACING["sm"],
                        ),
                        ft.Column(
                            controls=[
                                ft.Text("Digital Complaint Box", style=get_text_style("title", is_dark)),
                                ft.Text("A transparent campus grievance portal", style=get_text_style("caption", is_dark)),
                            ],
                            spacing=SPACING["xs"],
                            expand=True,
                        ),
                    ],
                    spacing=SPACING["md"],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=SPACING["sm"],
                animate_opacity=MOTION_FAST_MS,
            )
            return PageContainer(
                content=ft.Column(
                    controls=[
                        compact_brand,
                        auth_card
                    ],
                    spacing=SPACING["md"],
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=SPACING["md"],
                is_dark=is_dark,
            )

        # Desktop and laptop split: campus lifecycle panel beside the form.
        desktop_hero = ft.Container(
            content=create_login_hero_panel(is_staff=False, is_dark=is_dark, compact=False),
            height=auth_height,
            col={"xs": 12, "lg": 5},
        )

        return PageContainer(
            content=ft.Column(
                controls=[
                    ft.ResponsiveRow(
                        controls=[
                            desktop_hero,
                            auth_card
                        ],
                        spacing=SPACING["lg"],
                        run_spacing=SPACING["lg"],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True
            ),
            padding=ft.padding.symmetric(horizontal=SPACING["xl"], vertical=SPACING["lg"]),
            is_dark=is_dark,
        )
