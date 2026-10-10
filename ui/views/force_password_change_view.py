"""
ui/views/force_password_change_view.py: Mandatory password change screen for students
whose temporary passwords were reset by their Academic Coordinator.
Blocks access to dashboard navigation until a secure new password is set.
"""

import logging
from typing import Callable, Dict, Any
import flet as ft

from services.account_service import AccountService
from ui.theme import get_theme_colors, get_card_shadow
from ui.state import AppState
from models.user import UserRole

logger = logging.getLogger("complaint_box.force_password_change")


class ForcePasswordChangeView:
    def __init__(
        self,
        page: ft.Page,
        user: Dict[str, Any],
        on_password_changed: Callable[[], None],
        on_logout: Callable[[], None]
    ):
        self.page = page
        self.user = user
        self.on_password_changed = on_password_changed
        self.on_logout = on_logout

    def render(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        curr_pass_field = ft.TextField(
            label="Temporary / Current Password",
            password=True,
            can_reveal_password=True,
            dense=True,
            border_radius=8,
            prefix_icon=ft.Icons.LOCK_OUTLINE,
        )

        new_pass_field = ft.TextField(
            label="New Password",
            password=True,
            can_reveal_password=True,
            dense=True,
            border_radius=8,
            prefix_icon=ft.Icons.LOCK,
        )

        pwd_hint = ft.Text(
            "Minimum 8 characters with letters, numbers, and special characters",
            size=11,
            color=colors["text_muted"]
        )

        confirm_pass_field = ft.TextField(
            label="Confirm New Password",
            password=True,
            can_reveal_password=True,
            dense=True,
            border_radius=8,
            prefix_icon=ft.Icons.LOCK_CLOCK,
        )

        # In-form alert message box
        alert_icon = ft.Icon(ft.Icons.ERROR_OUTLINE, size=18, color=ft.Colors.WHITE)
        alert_text = ft.Text("", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.WHITE, expand=True)
        alert_container = ft.Container(
            content=ft.Row(controls=[alert_icon, alert_text], spacing=10),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            visible=False,
        )

        def show_alert(msg: str, is_error: bool = True):
            alert_container.visible = True
            alert_container.bgcolor = "#dc2626" if is_error else "#059669"
            alert_icon.name = ft.Icons.ERROR_OUTLINE if is_error else ft.Icons.CHECK_CIRCLE_OUTLINE
            alert_text.value = msg
            self.page.update()

        submit_btn = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=18, color=ft.Colors.WHITE),
                    ft.Text("Update Password & Continue", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
            ),
            style=ft.ButtonStyle(
                bgcolor=colors["primary"],
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.padding.symmetric(vertical=12, horizontal=20),
            ),
        )

        logout_btn = ft.TextButton(
            text="Cancel & Sign Out",
            icon=ft.Icons.LOGOUT,
            icon_color=colors["text_muted"],
            style=ft.ButtonStyle(color=colors["text_muted"]),
        )

        def handle_submit(e):
            curr_val = (curr_pass_field.value or "").strip()
            new_val = (new_pass_field.value or "").strip()
            conf_val = (confirm_pass_field.value or "").strip()

            if not curr_val:
                show_alert("Current temporary password is required.", is_error=True)
                return

            if not new_val:
                show_alert("New password is required.", is_error=True)
                return

            if new_val == curr_val:
                show_alert("New password cannot be the same as your temporary password.", is_error=True)
                return

            if new_val != conf_val:
                show_alert("New password and Confirm password do not match.", is_error=True)
                return

            submit_btn.disabled = True
            self.page.update()

            user_id = self.user.get("id")
            ok, msg = AccountService.change_own_password(
                user_id=user_id,
                role=UserRole.STUDENT.value,
                current_password=curr_val,
                new_password=new_val
            )

            submit_btn.disabled = False

            if not ok:
                show_alert(msg, is_error=True)
                return

            # Password change succeeded!
            show_alert("Password updated successfully! Loading dashboard...", is_error=False)
            self.on_password_changed()

        submit_btn.on_click = handle_submit
        logout_btn.on_click = lambda _: self.on_logout()

        roll_no = self.user.get("roll_number", "")
        name = self.user.get("full_name", "Student")

        card = ft.Container(
            content=ft.Column(
                controls=[
                    # Header
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Icon(ft.Icons.LOCK_RESET, size=32, color=colors["primary"]),
                                bgcolor=ft.Colors.with_opacity(0.1, colors["primary"]),
                                border_radius=50,
                                padding=12,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text("Password Change Required", size=18, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                    ft.Text(f"{name} ({roll_no})", size=13, color=colors["text_muted"]),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=1, color=colors["border"]),
                    # Instruction Notice
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.INFO_OUTLINE, size=20, color="#d97706"),
                                ft.Text(
                                    "Your temporary password was set by your Academic Coordinator. For security, you must set a new personal password before accessing the dashboard.",
                                    size=12,
                                    color="#92400e" if not is_dark else "#fde68a",
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        bgcolor="#fef3c7" if not is_dark else "#78350f",
                        border_radius=8,
                        padding=12,
                    ),
                    alert_container,
                    ft.Text("Set New Password", size=14, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    curr_pass_field,
                    new_pass_field,
                    pwd_hint,
                    confirm_pass_field,
                    ft.Container(height=6),
                    submit_btn,
                    ft.Row(controls=[logout_btn], alignment=ft.MainAxisAlignment.CENTER),
                ],
                spacing=14,
                tight=True,
            ),
            width=480,
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=24,
            shadow=get_card_shadow(is_dark),
        )

        return ft.Container(
            content=card,
            alignment=ft.alignment.center,
            expand=True,
            padding=16,
        )
