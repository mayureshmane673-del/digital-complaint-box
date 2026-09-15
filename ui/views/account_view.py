"""
ui/views/account_view.py: Comprehensive Account Management view supporting:
- Profile inspection and safe editing (full_name only)
- Own Password Change with password complexity enforcement
- Self-deactivation/deletion with confirmation dialog and invariant enforcement
- HOD Departmental Coordinator oversight (safe list, administrative password reset, deactivate/reactivate)
- Principal Campus-wide HOD & Hostel Incharge oversight (safe list, reset, toggle status)
- Responsive reflow and Dark Mode theme integration
"""

from typing import Callable, Optional, Dict, Any, List
import flet as ft

from services.account_service import AccountService
from ui.theme import (
    COLOR_PRIMARY, COLOR_SURFACE, COLOR_BORDER, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_MUTED, STATUS_COLORS, get_theme_colors
)
from ui.state import AppState
from ui.flet_compat import show_feedback_message, open_dialog, close_dialog
from models.user import UserRole


class AccountView:
    def __init__(self, page: ft.Page, user: Dict[str, Any], role: str, on_logout: Optional[Callable[[], None]] = None, on_refresh: Optional[Callable[[], None]] = None):
        self.page = page
        self.user = user
        self.role = role
        self.user_id = user["id"]
        self.on_logout = on_logout
        self.on_refresh = on_refresh

    def render(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        # Refresh profile details from backend
        fresh_profile = AccountService.get_profile(self.user_id, self.role)
        if fresh_profile:
            self.user.update(fresh_profile)

        sections = [
            self._render_profile_card(colors, is_dark),
            self._render_password_change_card(colors, is_dark),
            self._render_deactivation_card(colors, is_dark)
        ]

        # Role-specific subordinate management sections
        if self.role == UserRole.COORDINATOR.value:
            sections.append(self._render_coordinator_student_management(colors, is_dark))
        elif self.role == UserRole.HOD.value:
            sections.append(self._render_hod_coordinator_management(colors, is_dark))
        elif self.role == UserRole.PRINCIPAL.value:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=4) as executor:
                f_hod = executor.submit(self._render_principal_hod_management, colors, is_dark)
                f_hostel = executor.submit(self._render_principal_hostel_management, colors, is_dark)
                f_lib = executor.submit(self._render_principal_library_management, colors, is_dark)
                f_gen = executor.submit(self._render_principal_general_hod_management, colors, is_dark)
                sections.append(f_hod.result())
                sections.append(f_hostel.result())
                sections.append(f_lib.result())
                sections.append(f_gen.result())

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Account & Profile Management", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.Text("Manage your personal profile, credentials, and institutional oversight.", size=13, color=colors["text_muted"]),
                    ft.Divider(color=colors["border"]),
                    *sections
                ],
                spacing=16,
                scroll=ft.ScrollMode.AUTO,
                expand=True
            ),
            expand=True
        )

    # -------------------------------------------------------------------------
    # SECTION 1: PROFILE CARD & EDIT PROFILE
    # -------------------------------------------------------------------------
    def _render_profile_card(self, colors: Dict[str, str], is_dark: bool) -> ft.Control:
        full_name = self.user.get("full_name", "")
        identifier = self.user.get("roll_number") if self.role == UserRole.STUDENT.value else self.user.get("username", "")
        dept_name = self.user.get("department_name") or self.user.get("department_code") or "Campus Wide"
        year = self.user.get("year", "")
        is_active = self.user.get("is_active", True)
        is_locked = self.user.get("is_locked", False)
        status_text = "Active" if (is_active and not is_locked) else ("Locked" if is_locked else "Inactive")
        status_color = "#10b981" if status_text == "Active" else "#ef4444"

        name_field = ft.TextField(label="Full Name", value=full_name, dense=True, width=320)
        save_btn = ft.ElevatedButton(
            content=ft.Text("Save Changes"),
            icon=ft.Icons.SAVE,
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def save_profile(e):
            new_name = name_field.value or ""
            save_btn.disabled = True
            save_btn.content = ft.Text("Saving...")
            self.page.update()

            ok, msg = AccountService.update_profile(self.user_id, self.role, new_name)
            save_btn.disabled = False
            save_btn.content = ft.Text("Save Changes")

            if ok:
                self.user["full_name"] = new_name.strip()
                if AppState.current_user:
                    AppState.current_user["full_name"] = new_name.strip()
                show_feedback_message(self.page, msg, is_error=False)
            else:
                show_feedback_message(self.page, msg, is_error=True)
            self.page.update()

        save_btn.on_click = save_profile

        info_rows = [
            ft.Row(controls=[ft.Text("Identity Identifier:", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]), ft.Text(str(identifier), size=13, color=colors["primary"])]),
            ft.Row(controls=[ft.Text("Role:", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]), ft.Text(self.role, size=13, color=colors["text"])]),
            ft.Row(controls=[ft.Text("Department:", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]), ft.Text(str(dept_name), size=13, color=colors["text"])]),
        ]
        if self.role == UserRole.STUDENT.value:
            if year:
                info_rows.append(ft.Row(controls=[ft.Text("Academic Year:", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]), ft.Text(str(year), size=13, color=colors["text"])]))
            phone_val = self.user.get("phone") or "Not Provided"
            email_val = self.user.get("email") or "Not Provided"
            info_rows.append(ft.Row(controls=[ft.Text("Phone Number:", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]), ft.Text(str(phone_val), size=13, color=colors["text"])]))
            info_rows.append(ft.Row(controls=[ft.Text("Email Address:", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]), ft.Text(str(email_val), size=13, color=colors["text"])]))
            h_app = self.user.get("is_hostel_approved", False)
            info_rows.append(ft.Row(controls=[
                ft.Text("Hostel Residency:", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Text("Approved Resident" if h_app else "Day Scholar / Pending", size=13, color="#059669" if h_app else colors["text_muted"])
            ]))

        info_rows.append(
            ft.Row(controls=[
                ft.Text("Account Status:", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Container(
                    content=ft.Text(status_text, size=11, weight=ft.FontWeight.BOLD, color=status_color),
                    bgcolor=ft.Colors.with_opacity(0.12, status_color),
                    border_radius=8,
                    padding=ft.padding.symmetric(horizontal=8, vertical=2)
                )
            ])
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.PERSON, color=colors["primary"], size=22),
                            ft.Text("My Profile Details", size=16, weight=ft.FontWeight.BOLD, color=colors["text"])
                        ],
                        spacing=8
                    ),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(ft.Column(controls=info_rows, spacing=6), col={"xs": 12, "md": 6}),
                            ft.Container(
                                ft.Column(
                                    controls=[
                                        ft.Text("Update Profile Details", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                        ft.Text("Protected fields (Roll Number, Department, Role) cannot be changed.", size=11, color=colors["text_muted"]),
                                        name_field,
                                        save_btn
                                    ],
                                    spacing=8
                                ),
                                col={"xs": 12, "md": 6}
                            )
                        ]
                    )
                ],
                spacing=12
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )

    # -------------------------------------------------------------------------
    # SECTION 2: OWN PASSWORD CHANGE
    # -------------------------------------------------------------------------
    def _render_password_change_card(self, colors: Dict[str, str], is_dark: bool) -> ft.Control:
        curr_pass_field = ft.TextField(label="Current Password", password=True, can_reveal_password=True, dense=True, width=320)
        new_pass_field = ft.TextField(label="New Password", password=True, can_reveal_password=True, dense=True, width=320)
        confirm_pass_field = ft.TextField(label="Confirm New Password", password=True, can_reveal_password=True, dense=True, width=320)

        change_btn = ft.ElevatedButton(
            content=ft.Text("Update Password"),
            icon=ft.Icons.LOCK_RESET,
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def do_change_password(e):
            curr_val = curr_pass_field.value or ""
            new_val = new_pass_field.value or ""
            conf_val = confirm_pass_field.value or ""

            if not curr_val:
                show_feedback_message(self.page, "Current password is required.", is_error=True)
                return

            if new_val != conf_val:
                show_feedback_message(self.page, "New password and Confirm password do not match.", is_error=True)
                return

            change_btn.disabled = True
            change_btn.content = ft.Text("Updating...")
            self.page.update()

            ok, msg = AccountService.change_own_password(self.user_id, self.role, curr_val, new_val)
            change_btn.disabled = False
            change_btn.content = ft.Text("Update Password")

            if ok:
                show_feedback_message(self.page, msg, is_error=False)
                curr_pass_field.value = ""
                new_pass_field.value = ""
                confirm_pass_field.value = ""
            else:
                show_feedback_message(self.page, msg, is_error=True)
            self.page.update()

        change_btn.on_click = do_change_password

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.LOCK, color=colors["primary"], size=22),
                            ft.Text("Change Password", size=16, weight=ft.FontWeight.BOLD, color=colors["text"])
                        ],
                        spacing=8
                    ),
                    ft.Text("Must contain at least 8 characters, with uppercase, lowercase, number, and special character.", size=12, color=colors["text_muted"]),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(curr_pass_field, col={"xs": 12, "sm": 4}),
                            ft.Container(new_pass_field, col={"xs": 12, "sm": 4}),
                            ft.Container(confirm_pass_field, col={"xs": 12, "sm": 4}),
                        ]
                    ),
                    ft.Row(controls=[change_btn])
                ],
                spacing=12
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )

    # -------------------------------------------------------------------------
    # SECTION 3: ACCOUNT DELETION / DEACTIVATION
    # -------------------------------------------------------------------------
    def _render_deactivation_card(self, colors: Dict[str, str], is_dark: bool) -> ft.Control:
        action_label = "Delete My Account" if self.role == UserRole.STUDENT.value else "Deactivate My Account"
        deact_btn = ft.OutlinedButton(
            content=ft.Text(action_label, color="#dc2626"),
            icon=ft.Icons.DELETE_FOREVER,
            style=ft.ButtonStyle(side=ft.BorderSide(1, "#dc2626"))
        )

        def confirm_deactivation(e):
            def execute_deactivation(e_dlg):
                close_dialog(self.page, dlg)

                if self.role == UserRole.STUDENT.value:
                    ok, msg = AccountService.deactivate_student_account(self.user_id)
                else:
                    ok, msg = AccountService.deactivate_staff_account(self.user_id, self.user_id, self.role, reason="Self deactivation")

                if ok:
                    show_feedback_message(self.page, msg, is_error=False)
                    if self.on_logout:
                        self.on_logout()
                    else:
                        AppState.current_user = None
                        AppState.role = None
                        if AppState.theme_callback:
                            AppState.theme_callback()
                else:
                    show_feedback_message(self.page, msg, is_error=True)

            dlg = ft.AlertDialog(
                title=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.WARNING_AMBER, color="#dc2626"),
                        ft.Text("Confirm Account Deactivation", size=18, weight=ft.FontWeight.BOLD)
                    ],
                    spacing=8
                ),
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Are you sure you want to proceed? Your account will be marked inactive and you will not be able to log in.",
                            size=13
                        ),
                        ft.Text(
                            "Note: Historical complaints, remarks, and institutional records are preserved.",
                            size=12,
                            italic=True,
                            color=colors["text_muted"]
                        )
                    ],
                    spacing=10,
                    tight=True
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                    ft.ElevatedButton(
                        content=ft.Text("Yes, Deactivate", color=ft.Colors.WHITE),
                        style=ft.ButtonStyle(bgcolor="#dc2626"),
                        on_click=execute_deactivation
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END
            )
            open_dialog(self.page, dlg)

        deact_btn.on_click = confirm_deactivation

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.SHIELD_MOON, color="#dc2626", size=22),
                            ft.Text("Account Lifecycle & Deactivation", size=16, weight=ft.FontWeight.BOLD, color="#dc2626")
                        ],
                        spacing=8
                    ),
                    ft.Text(
                        "Deactivating your account safely revokes login access while permanently preserving your historical complaints, feedback, and audit history.",
                        size=12,
                        color=colors["text_muted"]
                    ),
                    ft.Row(controls=[deact_btn])
                ],
                spacing=10
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, "#dc2626")),
            border_radius=12,
            padding=16
        )

    # -------------------------------------------------------------------------
    # SECTION 4: HOD COORDINATOR OVERSIGHT
    # -------------------------------------------------------------------------
    def _render_hod_coordinator_management(self, colors: Dict[str, str], is_dark: bool) -> ft.Control:
        coords = AccountService.list_department_coordinators(self.user_id)

        rows = []
        for c in coords:
            cid = c["id"]
            username = c.get("username", "")
            name = c.get("full_name", "")
            is_active = c.get("is_active", True)
            is_locked = c.get("is_locked", False)
            created_at = (c.get("created_at") or "")[:10]

            status_text = "Active" if (is_active and not is_locked) else ("Locked" if is_locked else "Inactive")
            st_color = "#10b981" if status_text == "Active" else "#ef4444"

            def make_reset_dialog_handler(target_id=cid, target_user=username):
                def open_reset_dialog(e):
                    new_pw_field = ft.TextField(label="New Password", password=True, can_reveal_password=True, dense=True)
                    conf_pw_field = ft.TextField(label="Confirm Password", password=True, can_reveal_password=True, dense=True)

                    def do_reset(e_rst):
                        p1 = new_pw_field.value or ""
                        p2 = conf_pw_field.value or ""
                        if p1 != p2:
                            show_feedback_message(self.page, "Passwords do not match.", is_error=True)
                            return
                        close_dialog(self.page, dlg)
                        ok, msg = AccountService.reset_coordinator_password_by_hod(self.user_id, target_id, p1)
                        show_feedback_message(self.page, msg, is_error=not ok)
                        if self.on_refresh:
                            self.on_refresh()
                        else:
                            self.page.update()

                    dlg = ft.AlertDialog(
                        title=ft.Text(f"Reset Password for '{target_user}'", size=16, weight=ft.FontWeight.BOLD),
                        content=ft.Column(
                            controls=[
                                ft.Text("Enter a new compliant password for this Coordinator.", size=12, color=colors["text_muted"]),
                                new_pw_field,
                                conf_pw_field
                            ],
                            spacing=10,
                            tight=True
                        ),
                        actions=[
                            ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                            ft.ElevatedButton("Reset Password", on_click=do_reset)
                        ]
                    )
                    open_dialog(self.page, dlg)
                return open_reset_dialog

            def make_toggle_active_handler(target_id=cid, target_user=username, active=is_active):
                def toggle(e):
                    if active:
                        def do_deactivate(e_conf):
                            close_dialog(self.page, dlg_conf)
                            ok, msg = AccountService.deactivate_staff_account(target_id, self.user_id, self.role, reason="HOD deactivation")
                            show_feedback_message(self.page, msg, is_error=not ok)
                            if self.on_refresh:
                                self.on_refresh()
                            else:
                                self.page.update()

                        dlg_conf = ft.AlertDialog(
                            title=ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.WARNING_AMBER, color="#dc2626"),
                                    ft.Text(f"Deactivate Coordinator '{target_user}'?", size=16, weight=ft.FontWeight.BOLD)
                                ],
                                spacing=8
                            ),
                            content=ft.Text(f"Are you sure you want to deactivate coordinator '{target_user}'? Login access will be revoked while historical records are preserved.", size=13),
                            actions=[
                                ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg_conf)),
                                ft.ElevatedButton(
                                    content=ft.Text("Yes, Deactivate", color=ft.Colors.WHITE),
                                    style=ft.ButtonStyle(bgcolor="#dc2626"),
                                    on_click=do_deactivate
                                )
                            ],
                            actions_alignment=ft.MainAxisAlignment.END
                        )
                        open_dialog(self.page, dlg_conf)
                    else:
                        ok, msg = AccountService.reactivate_staff_account(target_id, self.user_id, self.role)
                        show_feedback_message(self.page, msg, is_error=not ok)
                        if self.on_refresh:
                            self.on_refresh()
                        else:
                            self.page.update()
                return toggle

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(name, weight=ft.FontWeight.BOLD, color=colors["text"])),
                        ft.DataCell(ft.Text(username, color=colors["primary"])),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(status_text, size=11, color=st_color, weight=ft.FontWeight.BOLD),
                                bgcolor=ft.Colors.with_opacity(0.12, st_color),
                                border_radius=6,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2)
                            )
                        ),
                        ft.DataCell(ft.Text(created_at, color=colors["text_muted"], size=12)),
                        ft.DataCell(
                            ft.Row(
                                controls=[
                                    ft.TextButton("Reset PW", icon=ft.Icons.PASSWORD, on_click=make_reset_dialog_handler()),
                                    ft.TextButton("Deactivate" if is_active else "Reactivate", icon=ft.Icons.BLOCK if is_active else ft.Icons.CHECK_CIRCLE, on_click=make_toggle_active_handler())
                                ],
                                spacing=4
                            )
                        )
                    ]
                )
            )

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Coordinator Name", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Username", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Registered Date", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD, color=colors["text"])),
            ],
            rows=rows,
            border=ft.Border.all(1, colors["border"]),
            border_radius=8
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.SUPERVISED_USER_CIRCLE, color=colors["primary"], size=22),
                            ft.Text("Department Coordinators Oversight", size=16, weight=ft.FontWeight.BOLD, color=colors["text"])
                        ],
                        spacing=8
                    ),
                    ft.Text("As HOD, you can view, reset credentials, and manage Coordinators assigned to your department.", size=12, color=colors["text_muted"]),
                    ft.Row(controls=[table], scroll=ft.ScrollMode.AUTO) if rows else ft.Text("No Coordinators found in your department.", italic=True, size=13, color=colors["text_muted"])
                ],
                spacing=12
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )

    # -------------------------------------------------------------------------
    # SECTION 5: PRINCIPAL HOD OVERSIGHT
    # -------------------------------------------------------------------------
    def _render_principal_hod_management(self, colors: Dict[str, str], is_dark: bool) -> ft.Control:
        hods = AccountService.list_hods_for_principal(self.user_id)

        rows = []
        for h in hods:
            hid = h["id"]
            username = h.get("username", "")
            name = h.get("full_name", "")
            dept_obj = h.get("departments") or {}
            dept_code = dept_obj.get("code") if isinstance(dept_obj, dict) else "Dept"
            is_active = h.get("is_active", True)
            is_locked = h.get("is_locked", False)
            created_at = (h.get("created_at") or "")[:10]

            status_text = "Active" if (is_active and not is_locked) else ("Locked" if is_locked else "Inactive")
            st_color = "#10b981" if status_text == "Active" else "#ef4444"

            def make_reset_hod_dialog(target_id=hid, target_user=username):
                def open_dialog_handler(e):
                    new_pw_field = ft.TextField(label="New Password", password=True, can_reveal_password=True, dense=True)
                    conf_pw_field = ft.TextField(label="Confirm Password", password=True, can_reveal_password=True, dense=True)

                    def do_reset(e_rst):
                        p1 = new_pw_field.value or ""
                        p2 = conf_pw_field.value or ""
                        if p1 != p2:
                            show_feedback_message(self.page, "Passwords do not match.", is_error=True)
                            return
                        close_dialog(self.page, dlg)
                        ok, msg = AccountService.reset_hod_password_by_principal(self.user_id, target_id, p1)
                        show_feedback_message(self.page, msg, is_error=not ok)
                        if self.on_refresh:
                            self.on_refresh()
                        else:
                            self.page.update()

                    dlg = ft.AlertDialog(
                        title=ft.Text(f"Reset Password for HOD '{target_user}'", size=16, weight=ft.FontWeight.BOLD),
                        content=ft.Column(
                            controls=[
                                ft.Text("Enter a new compliant password for this Head of Department.", size=12, color=colors["text_muted"]),
                                new_pw_field,
                                conf_pw_field
                            ],
                            spacing=10,
                            tight=True
                        ),
                        actions=[
                            ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                            ft.ElevatedButton("Reset Password", on_click=do_reset)
                        ]
                    )
                    open_dialog(self.page, dlg)
                return open_dialog_handler

            def make_toggle_hod(target_id=hid, target_user=username, active=is_active):
                def toggle(e):
                    if active:
                        def do_deactivate(e_conf):
                            close_dialog(self.page, dlg_conf)
                            ok, msg = AccountService.deactivate_staff_account(target_id, self.user_id, self.role, reason="Principal deactivation")
                            show_feedback_message(self.page, msg, is_error=not ok)
                            if self.on_refresh:
                                self.on_refresh()
                            else:
                                self.page.update()

                        dlg_conf = ft.AlertDialog(
                            title=ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.WARNING_AMBER, color="#dc2626"),
                                    ft.Text(f"Deactivate HOD '{target_user}'?", size=16, weight=ft.FontWeight.BOLD)
                                ],
                                spacing=8
                            ),
                            content=ft.Text(f"Are you sure you want to deactivate HOD '{target_user}'? Login access will be revoked while historical department records are preserved.", size=13),
                            actions=[
                                ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg_conf)),
                                ft.ElevatedButton(
                                    content=ft.Text("Yes, Deactivate", color=ft.Colors.WHITE),
                                    style=ft.ButtonStyle(bgcolor="#dc2626"),
                                    on_click=do_deactivate
                                )
                            ],
                            actions_alignment=ft.MainAxisAlignment.END
                        )
                        open_dialog(self.page, dlg_conf)
                    else:
                        ok, msg = AccountService.reactivate_staff_account(target_id, self.user_id, self.role)
                        show_feedback_message(self.page, msg, is_error=not ok)
                        if self.on_refresh:
                            self.on_refresh()
                        else:
                            self.page.update()
                return toggle

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(f"{dept_code}", weight=ft.FontWeight.BOLD, color=colors["primary"])),
                        ft.DataCell(ft.Text(name, weight=ft.FontWeight.BOLD, color=colors["text"])),
                        ft.DataCell(ft.Text(username, color=colors["text"])),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(status_text, size=11, color=st_color, weight=ft.FontWeight.BOLD),
                                bgcolor=ft.Colors.with_opacity(0.12, st_color),
                                border_radius=6,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2)
                            )
                        ),
                        ft.DataCell(ft.Text(created_at, color=colors["text_muted"], size=12)),
                        ft.DataCell(
                            ft.Row(
                                controls=[
                                    ft.TextButton("Reset PW", icon=ft.Icons.PASSWORD, on_click=make_reset_hod_dialog()),
                                    ft.TextButton("Deactivate" if is_active else "Reactivate", icon=ft.Icons.BLOCK if is_active else ft.Icons.CHECK_CIRCLE, on_click=make_toggle_hod())
                                ],
                                spacing=4
                            )
                        )
                    ]
                )
            )

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Department", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("HOD Name", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Username", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Registered Date", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD, color=colors["text"])),
            ],
            rows=rows,
            border=ft.Border.all(1, colors["border"]),
            border_radius=8
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.ACCOUNT_TREE, color=colors["primary"], size=22),
                            ft.Text("Department Heads (HOD) Oversight", size=16, weight=ft.FontWeight.BOLD, color=colors["text"])
                        ],
                        spacing=8
                    ),
                    ft.Text("As Principal, you have campus-wide authority to oversee and manage all Head of Department accounts.", size=12, color=colors["text_muted"]),
                    ft.Row(controls=[table], scroll=ft.ScrollMode.AUTO) if rows else ft.Text("No HOD accounts registered.", italic=True, size=13, color=colors["text_muted"])
                ],
                spacing=12
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )

    # -------------------------------------------------------------------------
    # SECTION 6: PRINCIPAL HOSTEL INCHARGE OVERSIGHT
    # -------------------------------------------------------------------------
    def _render_principal_hostel_management(self, colors: Dict[str, str], is_dark: bool) -> ft.Control:
        hi = AccountService.get_hostel_incharge_for_principal(self.user_id)

        if not hi:
            content_control = ft.Text("No active Hostel Incharge account registered.", italic=True, size=13, color=colors["text_muted"])
        else:
            hi_id = hi["id"]
            hi_name = hi.get("full_name", "")
            hi_username = hi.get("username", "")
            is_active = hi.get("is_active", True)
            is_locked = hi.get("is_locked", False)
            status_text = "Active" if (is_active and not is_locked) else ("Locked" if is_locked else "Inactive")
            st_color = "#10b981" if status_text == "Active" else "#ef4444"

            def open_reset_hi_dialog(e):
                new_pw_field = ft.TextField(label="New Password", password=True, can_reveal_password=True, dense=True)
                conf_pw_field = ft.TextField(label="Confirm Password", password=True, can_reveal_password=True, dense=True)

                def do_reset(e_rst):
                    p1 = new_pw_field.value or ""
                    p2 = conf_pw_field.value or ""
                    if p1 != p2:
                        show_feedback_message(self.page, "Passwords do not match.", is_error=True)
                        return
                    close_dialog(self.page, dlg)
                    ok, msg = AccountService.reset_hostel_incharge_password_by_principal(self.user_id, hi_id, p1)
                    show_feedback_message(self.page, msg, is_error=not ok)
                    if self.on_refresh:
                        self.on_refresh()
                    else:
                        self.page.update()

                dlg = ft.AlertDialog(
                    title=ft.Text(f"Reset Password for Hostel Incharge '{hi_username}'", size=16, weight=ft.FontWeight.BOLD),
                    content=ft.Column(
                        controls=[
                            ft.Text("Enter a new compliant password for the Hostel Incharge.", size=12, color=colors["text_muted"]),
                            new_pw_field,
                            conf_pw_field
                        ],
                        spacing=10,
                        tight=True
                    ),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                        ft.ElevatedButton("Reset Password", on_click=do_reset)
                    ]
                )
                open_dialog(self.page, dlg)

            def toggle_hi_active(e):
                if is_active:
                    def do_deactivate(e_conf):
                        close_dialog(self.page, dlg_conf)
                        ok, msg = AccountService.deactivate_staff_account(hi_id, self.user_id, self.role, reason="Principal deactivation")
                        show_feedback_message(self.page, msg, is_error=not ok)
                        if self.on_refresh:
                            self.on_refresh()
                        else:
                            self.page.update()

                    dlg_conf = ft.AlertDialog(
                        title=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.WARNING_AMBER, color="#dc2626"),
                                ft.Text(f"Deactivate Hostel Incharge '{hi_username}'?", size=16, weight=ft.FontWeight.BOLD)
                            ],
                            spacing=8
                        ),
                        content=ft.Text(f"Are you sure you want to deactivate Hostel Incharge '{hi_username}'? Login access will be revoked while hostel records are preserved.", size=13),
                        actions=[
                            ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg_conf)),
                            ft.ElevatedButton(
                                content=ft.Text("Yes, Deactivate", color=ft.Colors.WHITE),
                                style=ft.ButtonStyle(bgcolor="#dc2626"),
                                on_click=do_deactivate
                            )
                        ],
                        actions_alignment=ft.MainAxisAlignment.END
                    )
                    open_dialog(self.page, dlg_conf)
                else:
                    ok, msg = AccountService.reactivate_staff_account(hi_id, self.user_id, self.role)
                    show_feedback_message(self.page, msg, is_error=not ok)
                    if self.on_refresh:
                        self.on_refresh()
                    else:
                        self.page.update()

            content_control = ft.ResponsiveRow(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Row(controls=[ft.Text("Incharge Name:", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]), ft.Text(hi_name, size=13, color=colors["text"])]),
                                ft.Row(controls=[ft.Text("Username:", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]), ft.Text(hi_username, size=13, color=colors["primary"])]),
                                ft.Row(controls=[
                                    ft.Text("Status:", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]),
                                    ft.Container(
                                        content=ft.Text(status_text, size=11, color=st_color, weight=ft.FontWeight.BOLD),
                                        bgcolor=ft.Colors.with_opacity(0.12, st_color),
                                        border_radius=6,
                                        padding=ft.padding.symmetric(horizontal=8, vertical=2)
                                    )
                                ])
                            ],
                            spacing=6
                        ),
                        col={"xs": 12, "sm": 6}
                    ),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.ElevatedButton("Reset Password", icon=ft.Icons.PASSWORD, on_click=open_reset_hi_dialog),
                                ft.OutlinedButton("Deactivate" if is_active else "Reactivate", icon=ft.Icons.BLOCK if is_active else ft.Icons.CHECK_CIRCLE, on_click=toggle_hi_active)
                            ],
                            spacing=8
                        ),
                        col={"xs": 12, "sm": 6}
                    )
                ]
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.HOTEL, color=colors["primary"], size=22),
                            ft.Text("Hostel Incharge Oversight", size=16, weight=ft.FontWeight.BOLD, color=colors["text"])
                        ],
                        spacing=8
                    ),
                    content_control
                ],
                spacing=12
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )

    # -------------------------------------------------------------------------
    # SECTION 7: COORDINATOR STUDENT PASSWORD RESET & MANAGEMENT
    # -------------------------------------------------------------------------
    def _render_coordinator_student_management(self, colors: Dict[str, str], is_dark: bool) -> ft.Control:
        students = AccountService.list_department_students_for_coordinator(self.user_id)

        search_field = ft.TextField(
            hint_text="Search students by roll number or name...",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            expand=True
        )

        table_rows_container = ft.Column(spacing=6)

        def make_student_reset_dialog(s_id: str, s_roll: str, s_name: str):
            def open_dialog_handler(e):
                new_pw_field = ft.TextField(
                    label="Temporary Password",
                    value="Temp@2026!",
                    password=True,
                    can_reveal_password=True,
                    dense=True
                )

                def do_reset(e_rst):
                    p1 = (new_pw_field.value or "").strip()
                    close_dialog(self.page, dlg)
                    ok, msg = AccountService.reset_student_password_by_coordinator(self.user_id, s_id, p1)
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
                                    ft.Text(f"Password for student {s_name} ({s_roll}) has been reset.", size=13),
                                    ft.Container(
                                        content=ft.Text(f"Temporary Password: {p1}", weight=ft.FontWeight.BOLD, size=14, color=colors["primary"]),
                                        bgcolor=ft.Colors.with_opacity(0.1, colors["primary"]),
                                        border_radius=8,
                                        padding=12
                                    ),
                                    ft.Text("The student will be required to change this password on next login.", size=12, color=colors["text_muted"])
                                ],
                                spacing=10,
                                tight=True
                            ),
                            actions=[
                                ft.ElevatedButton("Done", on_click=lambda _: close_dialog(self.page, info_dlg))
                            ]
                        )
                        open_dialog(self.page, info_dlg)
                        if self.on_refresh:
                            self.on_refresh()
                        else:
                            self.page.update()
                    else:
                        show_feedback_message(self.page, msg, is_error=True)

                dlg = ft.AlertDialog(
                    title=ft.Text(f"Reset Password for {s_roll}", size=16, weight=ft.FontWeight.BOLD),
                    content=ft.Column(
                        controls=[
                            ft.Text(f"Reset credentials for {s_name} ({s_roll}). Account will be unlocked and must change password on login.", size=12, color=colors["text_muted"]),
                            new_pw_field
                        ],
                        spacing=10,
                        tight=True
                    ),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                        ft.ElevatedButton("Reset Password", on_click=do_reset)
                    ]
                )
                open_dialog(self.page, dlg)
            return open_dialog_handler

        def render_table():
            q = (search_field.value or "").strip().lower()
            filtered = [s for s in students if not q or q in s.get("roll_number", "").lower() or q in s.get("full_name", "").lower()]

            if not filtered:
                table_rows_container.controls = [
                    ft.Text("No departmental students found matching search.", italic=True, size=13, color=colors["text_muted"])
                ]
            else:
                rows = []
                for s in filtered:
                    s_id = s["id"]
                    s_roll = s.get("roll_number", "")
                    s_name = s.get("full_name", "")
                    s_year = s.get("year", "")
                    is_locked = s.get("is_locked", False)
                    status_str = "Locked" if is_locked else "Active"
                    status_col = "#ef4444" if is_locked else "#10b981"

                    rows.append(
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Text(s_roll, weight=ft.FontWeight.BOLD, size=13, color=colors["text"]),
                                            ft.Text(f"— {s_name}", size=13, color=colors["text"]),
                                            ft.Container(
                                                content=ft.Text(s_year or "—", size=11, color=colors["primary"]),
                                                bgcolor=ft.Colors.with_opacity(0.1, colors["primary"]),
                                                border_radius=6,
                                                padding=ft.padding.symmetric(horizontal=6, vertical=2)
                                            ),
                                            ft.Container(
                                                content=ft.Text(status_str, size=11, color=status_col, weight=ft.FontWeight.BOLD),
                                                bgcolor=ft.Colors.with_opacity(0.1, status_col),
                                                border_radius=6,
                                                padding=ft.padding.symmetric(horizontal=6, vertical=2)
                                            )
                                        ],
                                        spacing=8,
                                        wrap=True
                                    ),
                                    ft.ElevatedButton(
                                        "Reset Password",
                                        icon=ft.Icons.LOCK_RESET,
                                        style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=10, vertical=4)),
                                        on_click=make_student_reset_dialog(s_id, s_roll, s_name)
                                    )
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                wrap=True
                            ),
                            padding=ft.padding.symmetric(vertical=6, horizontal=8),
                            border=ft.Border.all(1, colors["border"]),
                            border_radius=8
                        )
                    )
                table_rows_container.controls = rows
            self.page.update()

        search_field.on_change = lambda _: render_table()
        render_table()

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.SCHOOL, color=colors["primary"], size=22),
                            ft.Text("Department Student Password Management", size=16, weight=ft.FontWeight.BOLD, color=colors["text"])
                        ],
                        spacing=8
                    ),
                    ft.Text("Coordinators can reset student passwords strictly within their department (excluding First Year).", size=12, color=colors["text_muted"]),
                    search_field,
                    table_rows_container
                ],
                spacing=12
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )

    # -------------------------------------------------------------------------
    # SECTION 8: PRINCIPAL LIBRARY INCHARGE OVERSIGHT
    # -------------------------------------------------------------------------
    def _render_principal_library_management(self, colors: Dict[str, str], is_dark: bool) -> ft.Control:
        lib = AccountService.get_library_incharge_for_principal(self.user_id)

        if not lib:
            content_control = ft.Text("No active Library Incharge account registered.", italic=True, size=13, color=colors["text_muted"])
        else:
            lib_id = lib["id"]
            lib_name = lib.get("full_name", "")
            lib_username = lib.get("username", "")
            is_active = lib.get("is_active", True)
            is_locked = lib.get("is_locked", False)
            status_text = "Active" if (is_active and not is_locked) else ("Locked" if is_locked else "Inactive")
            st_color = "#10b981" if status_text == "Active" else "#ef4444"

            def open_reset_lib_dialog(e):
                new_pw_field = ft.TextField(label="New Password", password=True, can_reveal_password=True, dense=True)
                conf_pw_field = ft.TextField(label="Confirm Password", password=True, can_reveal_password=True, dense=True)

                def do_reset(e_rst):
                    p1 = new_pw_field.value or ""
                    p2 = conf_pw_field.value or ""
                    if p1 != p2:
                        show_feedback_message(self.page, "Passwords do not match.", is_error=True)
                        return
                    close_dialog(self.page, dlg)
                    ok, msg = AccountService.reset_library_incharge_password_by_principal(self.user_id, lib_id, p1)
                    show_feedback_message(self.page, msg, is_error=not ok)
                    if self.on_refresh:
                        self.on_refresh()
                    else:
                        self.page.update()

                dlg = ft.AlertDialog(
                    title=ft.Text(f"Reset Password for Library Incharge '{lib_username}'", size=16, weight=ft.FontWeight.BOLD),
                    content=ft.Column(
                        controls=[
                            ft.Text("Enter a new compliant password for the Library Incharge.", size=12, color=colors["text_muted"]),
                            new_pw_field,
                            conf_pw_field
                        ],
                        spacing=10,
                        tight=True
                    ),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                        ft.ElevatedButton("Reset Password", on_click=do_reset)
                    ]
                )
                open_dialog(self.page, dlg)

            content_control = ft.ResponsiveRow(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Row(controls=[ft.Text("Incharge Name:", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]), ft.Text(lib_name, size=13, color=colors["text"])]),
                                ft.Row(controls=[ft.Text("Username:", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]), ft.Text(lib_username, size=13, color=colors["primary"])]),
                                ft.Row(controls=[
                                    ft.Text("Status:", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]),
                                    ft.Container(
                                        content=ft.Text(status_text, size=11, color=st_color, weight=ft.FontWeight.BOLD),
                                        bgcolor=ft.Colors.with_opacity(0.12, st_color),
                                        border_radius=6,
                                        padding=ft.padding.symmetric(horizontal=8, vertical=2)
                                    )
                                ])
                            ],
                            spacing=6
                        ),
                        col={"xs": 12, "sm": 6}
                    ),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.ElevatedButton("Reset Password", icon=ft.Icons.PASSWORD, on_click=open_reset_lib_dialog),
                            ],
                            spacing=8
                        ),
                        col={"xs": 12, "sm": 6}
                    )
                ]
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.LOCAL_LIBRARY, color=colors["primary"], size=22),
                            ft.Text("Library Incharge Oversight", size=16, weight=ft.FontWeight.BOLD, color=colors["text"])
                        ],
                        spacing=8
                    ),
                    content_control
                ],
                spacing=12
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )

    # -------------------------------------------------------------------------
    # SECTION 9: PRINCIPAL GENERAL DEPARTMENT HOD OVERSIGHT
    # -------------------------------------------------------------------------
    def _render_principal_general_hod_management(self, colors: Dict[str, str], is_dark: bool) -> ft.Control:
        gen = AccountService.get_general_hod_for_principal(self.user_id)

        if not gen:
            content_control = ft.Text("No active General Department HOD account registered.", italic=True, size=13, color=colors["text_muted"])
        else:
            gen_id = gen["id"]
            gen_name = gen.get("full_name", "")
            gen_username = gen.get("username", "")
            is_active = gen.get("is_active", True)
            is_locked = gen.get("is_locked", False)
            status_text = "Active" if (is_active and not is_locked) else ("Locked" if is_locked else "Inactive")
            st_color = "#10b981" if status_text == "Active" else "#ef4444"

            def open_reset_gen_dialog(e):
                new_pw_field = ft.TextField(label="New Password", password=True, can_reveal_password=True, dense=True)
                conf_pw_field = ft.TextField(label="Confirm Password", password=True, can_reveal_password=True, dense=True)

                def do_reset(e_rst):
                    p1 = new_pw_field.value or ""
                    p2 = conf_pw_field.value or ""
                    if p1 != p2:
                        show_feedback_message(self.page, "Passwords do not match.", is_error=True)
                        return
                    close_dialog(self.page, dlg)
                    ok, msg = AccountService.reset_general_hod_password_by_principal(self.user_id, gen_id, p1)
                    show_feedback_message(self.page, msg, is_error=not ok)
                    if self.on_refresh:
                        self.on_refresh()
                    else:
                        self.page.update()

                dlg = ft.AlertDialog(
                    title=ft.Text(f"Reset Password for General Dept HOD '{gen_username}'", size=16, weight=ft.FontWeight.BOLD),
                    content=ft.Column(
                        controls=[
                            ft.Text("Enter a new compliant password for the General Department HOD.", size=12, color=colors["text_muted"]),
                            new_pw_field,
                            conf_pw_field
                        ],
                        spacing=10,
                        tight=True
                    ),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: close_dialog(self.page, dlg)),
                        ft.ElevatedButton("Reset Password", on_click=do_reset)
                    ]
                )
                open_dialog(self.page, dlg)

            content_control = ft.ResponsiveRow(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Row(controls=[ft.Text("HOD Name:", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]), ft.Text(gen_name, size=13, color=colors["text"])]),
                                ft.Row(controls=[ft.Text("Username:", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]), ft.Text(gen_username, size=13, color=colors["primary"])]),
                                ft.Row(controls=[
                                    ft.Text("Status:", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]),
                                    ft.Container(
                                        content=ft.Text(status_text, size=11, color=st_color, weight=ft.FontWeight.BOLD),
                                        bgcolor=ft.Colors.with_opacity(0.12, st_color),
                                        border_radius=6,
                                        padding=ft.padding.symmetric(horizontal=8, vertical=2)
                                    )
                                ])
                            ],
                            spacing=6
                        ),
                        col={"xs": 12, "sm": 6}
                    ),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.ElevatedButton("Reset Password", icon=ft.Icons.PASSWORD, on_click=open_reset_gen_dialog),
                            ],
                            spacing=8
                        ),
                        col={"xs": 12, "sm": 6}
                    )
                ]
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.DOMAIN, color=colors["primary"], size=22),
                            ft.Text("General Department HOD Oversight", size=16, weight=ft.FontWeight.BOLD, color=colors["text"])
                        ],
                        spacing=8
                    ),
                    content_control
                ],
                spacing=12
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )
