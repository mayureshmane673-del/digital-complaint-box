"""
ui/views/auth_view.py: Authentication screen supporting Student and Staff tabs,
registration with roll number pool checks, role-based staff security codes, account recovery,
full responsive reflow, loading state prevention, and dark mode theming.
"""

from typing import Callable, Optional, Dict, Any, List
import flet as ft
from services.auth_service import AuthService
from database.supabase_client import get_supabase_client
from ui.theme import (
    COLOR_PRIMARY, COLOR_PRIMARY_LIGHT, COLOR_SURFACE, COLOR_BORDER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_MUTED, get_theme_colors
)
from ui.state import AppState
from ui.flet_compat import show_feedback_message, open_dialog, close_dialog
from ui.components.animated_chart import create_hero_3d_badge
from models.user import UserRole

# Standard fallback departments if database not yet migrated
DEFAULT_DEPTS = [
    {"code": "CSE", "name": "Computer Science and Engineering"},
    {"code": "AIDS", "name": "Artificial Intelligence and Data Science"},
    {"code": "E&TC", "name": "Electronics and Telecommunication Engineering"},
    {"code": "MECH", "name": "Mechanical Engineering"},
    {"code": "Civil", "name": "Civil Engineering"}
]


class AuthView:
    def __init__(self, page: ft.Page, on_authenticated: Callable[[Dict[str, Any], str], None]):
        self.page = page
        self.on_authenticated = on_authenticated
        self.departments = self._load_departments()

    def _load_departments(self) -> List[Dict[str, Any]]:
        from services.cache_service import CacheService
        return CacheService.get_departments()

    def _make_alert_box(self) -> ft.Container:
        """Creates an in-form visual banner container for instant feedback."""
        icon_ctrl = ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.WHITE)
        text_ctrl = ft.Text("", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.WHITE, expand=True)
        container = ft.Container(
            content=ft.Row(controls=[icon_ctrl, text_ctrl], spacing=10),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            visible=False
        )

        def show(msg: str, is_error: bool = True):
            container.visible = True
            container.bgcolor = "#dc2626" if is_error else "#059669"
            icon_ctrl.name = ft.Icons.ERROR_OUTLINE if is_error else ft.Icons.CHECK_CIRCLE_OUTLINE
            text_ctrl.value = msg
            self.page.update()

        def hide():
            container.visible = False
            self.page.update()

        container.show_alert = show
        container.hide_alert = hide
        return container

    def render(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

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
        st_login_roll = ft.TextField(label="Roll Number / Student ID", prefix_icon=ft.Icons.BADGE_OUTLINED, dense=True)
        st_login_pass = ft.TextField(label="Password", prefix_icon=ft.Icons.LOCK_OUTLINED, password=True, can_reveal_password=True, dense=True)
        btn_st_login = ft.ElevatedButton("Login", icon=ft.Icons.LOGIN, style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE))

        def do_student_login(e):
            alert_st_login.hide_alert()
            roll_val = (st_login_roll.value or "").strip()
            pass_val = st_login_pass.value or ""

            if not roll_val or not pass_val:
                alert_st_login.show_alert("Please enter both Roll Number and Password.", is_error=True)
                show_feedback_message(self.page, "Please enter both Roll Number and Password.", is_error=True)
                return

            btn_st_login.disabled = True
            btn_st_login.content = "Verifying..."
            self.page.update()

            try:
                ok, msg, student = AuthService.login_student(roll_val, pass_val)
                if ok and student:
                    show_feedback_message(self.page, "Login successful!", is_error=False)
                    self.on_authenticated(student, UserRole.STUDENT.value)
                else:
                    alert_st_login.show_alert(msg, is_error=True)
                    show_feedback_message(self.page, msg, is_error=True)
            except Exception as ex:
                alert_st_login.show_alert("Unable to complete login. Please try again.", is_error=True)
                show_feedback_message(self.page, "Unable to complete login. Please try again.", is_error=True)
            finally:
                btn_st_login.disabled = False
                btn_st_login.content = "Login"
                self.page.update()

        btn_st_login.on_click = do_student_login

        # ---------------------------------------------------------------------
        # TAB 2: STUDENT REGISTRATION CONTROLS
        # ---------------------------------------------------------------------
        st_reg_roll = ft.TextField(label="Roll Number / Student ID", hint_text="Must be present in department pool", prefix_icon=ft.Icons.BADGE_OUTLINED, dense=True)
        st_reg_name = ft.TextField(label="Full Name", prefix_icon=ft.Icons.PERSON_OUTLINED, dense=True)
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
        st_reg_pass = ft.TextField(label="Password (min 8 chars, 1 upper, 1 lower, 1 digit, 1 special)", prefix_icon=ft.Icons.LOCK_OUTLINED, password=True, can_reveal_password=True, dense=True)
        st_reg_q = ft.TextField(label="Security Question", hint_text="e.g. What was your first school?", dense=True)
        st_reg_ans = ft.TextField(label="Security Answer", dense=True)

        st_reg_hostel = ft.Checkbox(label="I reside in the College Hostel", value=False)
        st_hostel_name = ft.TextField(label="Hostel Name", hint_text="e.g. Boys Hostel", dense=True, visible=False)
        st_hostel_block = ft.TextField(label="Block", hint_text="e.g. A", dense=True, visible=False)
        st_hostel_room = ft.TextField(label="Room Number", hint_text="e.g. 101", dense=True, visible=False)

        def on_hostel_toggle(e):
            is_hostel = bool(st_reg_hostel.value)
            st_hostel_name.visible = is_hostel
            st_hostel_block.visible = is_hostel
            st_hostel_room.visible = is_hostel
            self.page.update()

        st_reg_hostel.on_change = on_hostel_toggle
        btn_st_reg = ft.ElevatedButton("Register Account", icon=ft.Icons.HOW_TO_REG, style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE))

        def do_student_register(e):
            alert_st_reg.hide_alert()
            roll_val = (st_reg_roll.value or "").strip()
            name_val = (st_reg_name.value or "").strip()
            dept_val = st_reg_dept.value
            year_val = st_reg_year.value or "FE"
            pass_val = st_reg_pass.value or ""
            q_val = (st_reg_q.value or "").strip()
            ans_val = (st_reg_ans.value or "").strip()

            if not roll_val or not name_val or not pass_val or not q_val or not ans_val:
                alert_st_reg.show_alert("Please fill in all required registration fields.", is_error=True)
                show_feedback_message(self.page, "Please fill in all required registration fields.", is_error=True)
                return

            btn_st_reg.disabled = True
            btn_st_reg.content = "Creating Account..."
            self.page.update()

            hostel_details = None
            if st_reg_hostel.value:
                hostel_details = {
                    "hostel_name": st_hostel_name.value or "Campus Hostel",
                    "block": st_hostel_block.value or "A",
                    "room_number": st_hostel_room.value or "101"
                }

            try:
                ok, msg, new_st = AuthService.register_student(
                    roll_number=roll_val,
                    full_name=name_val,
                    department_id=dept_val,
                    year=year_val,
                    password=pass_val,
                    security_question=q_val,
                    security_answer=ans_val,
                    is_hostel=bool(st_reg_hostel.value),
                    hostel_details=hostel_details
                )

                if ok and new_st:
                    alert_st_reg.show_alert(f"Account for {roll_val} registered successfully! You can now log in.", is_error=False)
                    show_feedback_message(self.page, "Registration successful! You can now log in.", is_error=False)
                    # Clear registration form
                    st_reg_roll.value = ""
                    st_reg_name.value = ""
                    st_reg_pass.value = ""
                    st_reg_q.value = ""
                    st_reg_ans.value = ""
                    st_reg_hostel.value = False
                    st_hostel_name.visible = False
                    st_hostel_block.visible = False
                    st_hostel_room.visible = False
                    # Keep login inputs clean (no prefilled credentials)
                    st_login_roll.value = ""
                    st_login_pass.value = ""
                    self.page.update()
                else:
                    alert_st_reg.show_alert(msg, is_error=True)
                    show_feedback_message(self.page, msg, is_error=True)
            except Exception as ex:
                alert_st_reg.show_alert("Unable to complete registration. Please try again.", is_error=True)
                show_feedback_message(self.page, "Unable to complete registration. Please try again.", is_error=True)
            finally:
                btn_st_reg.disabled = False
                btn_st_reg.content = "Register Account"
                self.page.update()

        btn_st_reg.on_click = do_student_register

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
        sf_login_user = ft.TextField(label="Staff Username / ID", prefix_icon=ft.Icons.PERSON_OUTLINED, dense=True)
        sf_login_pass = ft.TextField(label="Password", prefix_icon=ft.Icons.LOCK_OUTLINED, password=True, can_reveal_password=True, dense=True)
        sf_login_code = ft.TextField(label="Staff Security Code", hint_text="Role Authority Code", prefix_icon=ft.Icons.KEY_OUTLINED, password=True, can_reveal_password=True, dense=True)

        def on_staff_role_change(e):
            needs_dept = sf_login_role.value in (UserRole.HOD.value, UserRole.COORDINATOR.value)
            sf_login_dept.visible = needs_dept
            sf_login_dept_col.visible = needs_dept
            self.page.update()

        sf_login_role.on_change = on_staff_role_change
        btn_sf_login = ft.ElevatedButton("Staff Sign In", icon=ft.Icons.LOCK_OPEN, style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE))

        def do_staff_login(e):
            alert_sf_login.hide_alert()
            role_val = sf_login_role.value
            dept_val = sf_login_dept.value if (sf_login_dept.visible and role_val in (UserRole.HOD.value, UserRole.COORDINATOR.value)) else None
            if role_val in (UserRole.PRINCIPAL.value, UserRole.HOSTEL_INCHARGE.value, UserRole.LIBRARY_INCHARGE.value):
                dept_val = None
            elif role_val == UserRole.GENERAL_HOD.value:
                dept_val = SecurityCodeService._get_special_dept_id("GEN")
            user_val = (sf_login_user.value or "").strip()
            pass_val = sf_login_pass.value or ""
            code_val = (sf_login_code.value or "").strip()

            if not user_val or not pass_val or not code_val:
                alert_sf_login.show_alert("Invalid username, password, or security code.", is_error=True)
                show_feedback_message(self.page, "Invalid username, password, or security code.", is_error=True)
                return

            btn_sf_login.disabled = True
            btn_sf_login.content = "Verifying..."
            self.page.update()

            try:
                ok, msg, staff = AuthService.login_staff(
                    role=role_val,
                    username=user_val,
                    password=pass_val,
                    security_code=code_val,
                    department_id=dept_val
                )
                if ok and staff:
                    show_feedback_message(self.page, "Staff login successful!", is_error=False)
                    self.on_authenticated(staff, role_val)
                else:
                    alert_sf_login.show_alert(msg, is_error=True)
                    show_feedback_message(self.page, msg, is_error=True)
            except Exception as ex:
                alert_sf_login.show_alert("Invalid username, password, or security code.", is_error=True)
                show_feedback_message(self.page, "Invalid username, password, or security code.", is_error=True)
            finally:
                btn_sf_login.disabled = False
                btn_sf_login.content = "Staff Sign In"
                self.page.update()

        btn_sf_login.on_click = do_staff_login

        # ---------------------------------------------------------------------
        # TAB 4: STAFF REGISTRATION CONTROLS
        # ---------------------------------------------------------------------
        sf_reg_role = ft.Dropdown(label="Select Staff Role", options=staff_roles, value=UserRole.COORDINATOR.value, dense=True)
        sf_reg_dept = ft.Dropdown(label="Department", options=dept_options, dense=True, value=dept_options[0].key if dept_options else None)
        sf_reg_dept_col = ft.Container(sf_reg_dept, col={"xs": 12, "sm": 6})
        sf_reg_name = ft.TextField(label="Full Name", prefix_icon=ft.Icons.PERSON_OUTLINED, dense=True)
        sf_reg_user = ft.TextField(label="Desired Username", prefix_icon=ft.Icons.BADGE_OUTLINED, dense=True)
        sf_reg_pass = ft.TextField(label="Password (min 8 chars)", prefix_icon=ft.Icons.LOCK_OUTLINED, password=True, can_reveal_password=True, dense=True)
        sf_reg_code = ft.TextField(label="Role Security Code", hint_text="Required to verify authority", prefix_icon=ft.Icons.KEY_OUTLINED, password=True, can_reveal_password=True, dense=True)
        sf_reg_q = ft.TextField(label="Security Question", hint_text="e.g. First school or favourite teacher", dense=True)
        sf_reg_ans = ft.TextField(label="Security Answer", dense=True)

        def on_reg_staff_role_change(e):
            needs_dept = sf_reg_role.value in (UserRole.HOD.value, UserRole.COORDINATOR.value)
            sf_reg_dept.visible = needs_dept
            sf_reg_dept_col.visible = needs_dept
            self.page.update()

        sf_reg_role.on_change = on_reg_staff_role_change
        btn_sf_reg = ft.ElevatedButton("Create Staff Account", icon=ft.Icons.BADGE, style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE))

        def do_staff_register(e):
            alert_sf_reg.hide_alert()
            role_val = sf_reg_role.value
            dept_val = sf_reg_dept.value if (sf_reg_dept.visible and role_val in (UserRole.HOD.value, UserRole.COORDINATOR.value)) else None
            if role_val in (UserRole.PRINCIPAL.value, UserRole.HOSTEL_INCHARGE.value, UserRole.LIBRARY_INCHARGE.value):
                dept_val = None
            elif role_val == UserRole.GENERAL_HOD.value:
                dept_val = SecurityCodeService._get_special_dept_id("GEN")
            user_val = (sf_reg_user.value or "").strip()
            name_val = (sf_reg_name.value or "").strip()
            pass_val = sf_reg_pass.value or ""
            code_val = (sf_reg_code.value or "").strip()
            q_val = (sf_reg_q.value or "").strip()
            ans_val = (sf_reg_ans.value or "").strip()

            if not user_val or not name_val:
                alert_sf_reg.show_alert("Username and Full Name are required.", is_error=True)
                show_feedback_message(self.page, "Username and Full Name are required.", is_error=True)
                return

            if role_val in (UserRole.HOD.value, UserRole.COORDINATOR.value) and not dept_val:
                alert_sf_reg.show_alert(f"Department selection is required for {role_val}.", is_error=True)
                show_feedback_message(self.page, f"Department selection is required for {role_val}.", is_error=True)
                return

            if not code_val:
                alert_sf_reg.show_alert("Role Security Code is required.", is_error=True)
                show_feedback_message(self.page, "Role Security Code is required.", is_error=True)
                return

            btn_sf_reg.disabled = True
            btn_sf_reg.content = "Creating Account..."
            self.page.update()

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
                    # Clear registration form
                    sf_reg_user.value = ""
                    sf_reg_name.value = ""
                    sf_reg_pass.value = ""
                    sf_reg_code.value = ""
                    sf_reg_q.value = ""
                    sf_reg_ans.value = ""
                    # Keep login inputs clean (no prefilled credentials)
                    sf_login_user.value = ""
                    sf_login_pass.value = ""
                    sf_login_code.value = ""
                    self.page.update()
                else:
                    alert_sf_reg.show_alert(msg, is_error=True)
                    show_feedback_message(self.page, msg, is_error=True)
            except Exception as ex:
                alert_sf_reg.show_alert("Unable to create staff account. Please try again.", is_error=True)
                show_feedback_message(self.page, "Unable to create staff account. Please try again.", is_error=True)
            finally:
                btn_sf_reg.disabled = False
                btn_sf_reg.content = "Create Staff Account"
                self.page.update()

        btn_sf_reg.on_click = do_staff_register

        # ---------------------------------------------------------------------
        # FORGOT PASSWORD MODAL
        # ---------------------------------------------------------------------
        def show_forgot_password(e):
            recov_roll = ft.TextField(label="Enter Student ID / Roll Number", dense=True)
            question_text = ft.Text("", weight=ft.FontWeight.BOLD, color=colors["primary"], visible=False)
            recov_ans = ft.TextField(label="Your Security Answer", dense=True, visible=False)
            recov_new_pass = ft.TextField(label="New Password", password=True, can_reveal_password=True, dense=True, visible=False)
            recov_btn = ft.ElevatedButton("Find Account", icon=ft.Icons.SEARCH)

            def on_recov_action(ev):
                if not question_text.visible:
                    # Step 1: Find question
                    ok, msg, q = AuthService.get_student_security_question(recov_roll.value or "")
                    if ok and q:
                        question_text.value = f"Security Question: {q}"
                        question_text.visible = True
                        recov_ans.visible = True
                        recov_new_pass.visible = True
                        recov_btn.content = "Reset & Unlock"
                        recov_btn.icon = ft.Icons.LOCK_RESET
                        self.page.update()
                    else:
                        show_feedback_message(self.page, msg or "Account not found.", is_error=True)
                else:
                    # Step 2: Reset
                    ok, msg = AuthService.reset_student_password(
                        roll_number=recov_roll.value or "",
                        security_answer=recov_ans.value or "",
                        new_password=recov_new_pass.value or ""
                    )
                    if ok:
                        show_feedback_message(self.page, msg, is_error=False)
                        close_dialog(self.page, dlg)
                    else:
                        show_feedback_message(self.page, msg, is_error=True)

            recov_btn.on_click = on_recov_action

            dlg = ft.AlertDialog(
                title=ft.Text("Password Recovery & Account Unlock", weight=ft.FontWeight.BOLD, color=colors["text"]),
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Answer your security question to set a new password and unlock your account.", size=13, color=colors["text_muted"]),
                            recov_roll,
                            question_text,
                            recov_ans,
                            recov_new_pass,
                            recov_btn
                        ],
                        spacing=12
                    ),
                    width=420,
                    height=280
                ),
                actions=[ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg))]
            )
            open_dialog(self.page, dlg)

        # ---------------------------------------------------------------------
        # RESPONSIVE TABS CONTAINER
        # ---------------------------------------------------------------------
        tab1_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Student Portal Access", size=18, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                    ft.Text("Enter your registered Roll Number and Password to access your grievance portal.", size=13, color=colors["text_muted"]),
                    alert_st_login,
                    st_login_roll,
                    st_login_pass,
                    ft.Row(
                        controls=[
                            ft.TextButton("Forgot Password / Locked?", on_click=show_forgot_password),
                            btn_st_login
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        wrap=True
                    )
                ],
                spacing=14,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=20)
        )

        tab2_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("New Student Registration", size=18, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                    ft.Text("Note: Roll Number must be authorized by your Coordinator in the department pool.", size=12, color=colors["text_muted"]),
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
                spacing=12,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=20)
        )

        tab3_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Staff / Administration Login", size=18, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                    ft.Text("Requires valid staff credentials and role security code.", size=13, color=colors["text_muted"]),
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
                spacing=14,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=20)
        )

        tab4_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Staff Self-Registration", size=18, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                    ft.Text("Authorized faculty registration with department verification.", size=12, color=colors["text_muted"]),
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
                    sf_reg_code,
                    ft.ResponsiveRow(controls=[
                        ft.Container(sf_reg_q, col={"xs": 12, "sm": 6}),
                        ft.Container(sf_reg_ans, col={"xs": 12, "sm": 6}),
                    ]),
                    btn_sf_reg
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=20)
        )

        tabs = ft.Tabs(
            length=4,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="Student Login", icon=ft.Icons.SCHOOL),
                            ft.Tab(label="Student Register", icon=ft.Icons.PERSON_ADD),
                            ft.Tab(label="Staff Login", icon=ft.Icons.ADMIN_PANEL_SETTINGS),
                            ft.Tab(label="Staff Register", icon=ft.Icons.SECURITY),
                        ]
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[tab1_content, tab2_content, tab3_content, tab4_content]
                    )
                ]
            ),
            expand=True
        )

        # Hero area (Left column on desktop, top on mobile/tablet)
        hero_col = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Text("INSTITUTIONAL GRIEVANCE REDRESSAL", size=10, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                        bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                        border_radius=8,
                        padding=ft.padding.symmetric(horizontal=10, vertical=4)
                    ),
                    ft.Text("Digital Complaint Box", size=26, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.Text(
                        "Empowering Students, Enabling Faculty.\nConfidential, role-isolated grievance resolution built on institutional integrity and trust.",
                        size=13,
                        color=colors["text_muted"],
                        height=1.4
                    ),
                    ft.Container(height=6),
                    create_hero_3d_badge(is_dark=is_dark),
                    ft.Container(height=6),
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color="#059669"),
                                    ft.Text("5 Departments: CSE, AIDS, E&TC, MECH, Civil", size=12, color=colors["text"])
                                ],
                                spacing=8
                            ),
                            ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color="#059669"),
                                    ft.Text("Strict Role Isolation & Identity Masking", size=12, color=colors["text"])
                                ],
                                spacing=8
                            ),
                            ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color="#059669"),
                                    ft.Text("Zero Credential Leakage Architecture", size=12, color=colors["text"])
                                ],
                                spacing=8
                            ),
                        ],
                        spacing=8
                    )
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.START
            ),
            padding=ft.padding.all(12),
            col={"xs": 12, "md": 5, "lg": 5}
        )

        auth_card = ft.Container(
            content=tabs,
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=16,
            height=580,
            col={"xs": 12, "md": 7, "lg": 7}
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.ResponsiveRow(
                        controls=[
                            hero_col,
                            auth_card
                        ],
                        spacing=16,
                        run_spacing=16,
                        vertical_alignment=ft.CrossAxisAlignment.START
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True
            ),
            bgcolor=colors["bg"],
            expand=True,
            padding=ft.padding.symmetric(horizontal=16, vertical=12)
        )
