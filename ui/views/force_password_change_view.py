"""
ui/views/force_password_change_view.py: Mandatory password change screen for students
whose temporary passwords were reset by their Academic Coordinator.
Blocks access to dashboard navigation until a secure new password is set.
"""

import logging
from typing import Callable, Dict, Any
import flet as ft

from services.account_service import AccountService
from ui.theme import (
    DIALOG_MAX_WIDTH, MOTION_FAST_MS, RADII, SPACING,
    get_button_style, get_card_shadow, get_input_style, get_text_style,
    get_theme_colors, PageContainer,
)
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
        input_style = get_input_style(is_dark)

        curr_pass_field = ft.TextField(
            label="Temporary / Current Password",
            password=True,
            can_reveal_password=True,
            dense=True,
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            **input_style,
        )

        new_pass_field = ft.TextField(
            label="New Password",
            password=True,
            can_reveal_password=True,
            dense=True,
            prefix_icon=ft.Icons.LOCK,
            **input_style,
        )

        pwd_hint = ft.Text(
            "Minimum 8 characters with letters, numbers, and special characters",
            style=get_text_style("body_small", is_dark),
            expand=True,
        )

        confirm_pass_field = ft.TextField(
            label="Confirm New Password",
            password=True,
            can_reveal_password=True,
            dense=True,
            prefix_icon=ft.Icons.LOCK_CLOCK,
            **input_style,
        )

        def clear_field_error(e):
            e.control.error_text = None

        for field in (curr_pass_field, new_pass_field, confirm_pass_field):
            field.error_style = get_text_style("caption", is_dark, color=colors["danger"])
            field.on_change = clear_field_error

        # In-form alert message box
        alert_icon = ft.Icon(ft.Icons.ERROR_OUTLINE, size=18, color=ft.Colors.WHITE)
        alert_text = ft.Text("", style=get_text_style("body_small", is_dark, color=ft.Colors.WHITE), weight=ft.FontWeight.W_500, expand=True)
        alert_container = ft.Container(
            content=ft.Row(controls=[alert_icon, alert_text], spacing=SPACING["md"]),
            border_radius=RADII["md"],
            padding=ft.padding.symmetric(horizontal=SPACING["md"], vertical=SPACING["sm"]),
            visible=False,
            animate_opacity=MOTION_FAST_MS,
        )

        def show_alert(msg: str, is_error: bool = True):
            alert_container.visible = True
            alert_container.bgcolor = colors["danger"] if is_error else colors["success"]
            alert_icon.name = ft.Icons.ERROR_OUTLINE if is_error else ft.Icons.CHECK_CIRCLE_OUTLINE
            alert_text.value = msg
            self.page.update()

        submit_btn = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=18, color=ft.Colors.WHITE),
                    ft.Text("Update Password & Continue", style=get_text_style("label", is_dark, color=ft.Colors.WHITE), weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=SPACING["sm"],
            ),
            style=get_button_style(is_dark, size="lg"),
        )

        logout_btn = ft.TextButton(
            text="Cancel & Sign Out",
            icon=ft.Icons.LOGOUT,
            icon_color=colors["text_muted"],
            style=get_button_style(is_dark, variant="text"),
        )

        def handle_submit(e):
            if submit_btn.disabled:
                return
            curr_val = (curr_pass_field.value or "").strip()
            new_val = (new_pass_field.value or "").strip()
            conf_val = (confirm_pass_field.value or "").strip()

            if not curr_val:
                curr_pass_field.error_text = "Current temporary password is required."
                show_alert("Current temporary password is required.", is_error=True)
                return
            if not new_val:
                new_pass_field.error_text = "New password is required."
                show_alert("New password is required.", is_error=True)
                return
            if new_val == curr_val:
                new_pass_field.error_text = "New password cannot be the same as your temporary password."
                show_alert("New password cannot be the same as your temporary password.", is_error=True)
                return
            if new_val != conf_val:
                confirm_pass_field.error_text = "New password and Confirm password do not match."
                show_alert("New password and Confirm password do not match.", is_error=True)
                return

            submit_btn.disabled = True
            submit_btn.content = ft.Row(
                controls=[ft.ProgressRing(width=SPACING["lg"], height=SPACING["lg"], stroke_width=2, color=ft.Colors.WHITE), ft.Text("Updating password…", style=get_text_style("label", is_dark, color=ft.Colors.WHITE))],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=SPACING["sm"],
            )
            self.page.update()
            user_id = self.user.get("id")

            def update_password():
                try:
                    ok, msg = AccountService.change_own_password(
                        user_id=user_id,
                        role=UserRole.STUDENT.value,
                        current_password=curr_val,
                        new_password=new_val,
                    )
                except Exception as exc:
                    logger.warning("Mandatory password change failed (%s)", type(exc).__name__)
                    ok, msg = False, "Unable to update your password. Please try again."

                submit_btn.disabled = False
                submit_btn.content = ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE, size=18, color=ft.Colors.WHITE),
                        ft.Text("Update Password & Continue", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8,
                )
                if not ok:
                    new_pass_field.error_text = msg
                    show_alert(msg, is_error=True)
                    return

                show_alert("Password updated successfully! Loading dashboard...", is_error=False)
                try:
                    self.on_password_changed()
                except Exception as exc:
                    logger.warning("Post-password-change navigation failed (%s)", type(exc).__name__)
                    self.page.update()

            self.page.run_thread(update_password)
        submit_btn.on_click = handle_submit
        curr_pass_field.on_submit = handle_submit
        new_pass_field.on_submit = handle_submit
        confirm_pass_field.on_submit = handle_submit
        logout_btn.on_click = lambda _: self.on_logout()

        raw_width = getattr(self.page, "width", None)
        screen_width = raw_width if isinstance(raw_width, (int, float)) else DIALOG_MAX_WIDTH
        card_width = min(DIALOG_MAX_WIDTH / 2, max(SPACING["3xl"], screen_width - 2 * SPACING["lg"]))
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
                                bgcolor=colors["surface_variant"],
                                border_radius=RADII["pill"],
                                padding=SPACING["md"],
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text("Password Change Required", style=get_text_style("title", is_dark)),
                                    ft.Text(f"{name} ({roll_no})", style=get_text_style("body_small", is_dark), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                ],
                                spacing=SPACING["xs"],
                                expand=True,
                            ),
                        ],
                        spacing=SPACING["md"],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=1, color=colors["border"]),
                    # Instruction Notice
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.INFO_OUTLINE, size=20, color=colors["warning"]),
                                ft.Text(
                                    "Set a new personal password to unlock your dashboard.",
                                    style=get_text_style("body_small", is_dark),
                                    expand=True,
                                ),
                            ],
                            spacing=SPACING["sm"],
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        bgcolor=colors["surface_variant"],
                        border=ft.Border.all(1, colors["border"]),
                        border_radius=RADII["md"],
                        padding=SPACING["md"],
                    ),
                    alert_container,
                    ft.Text("Set New Password", style=get_text_style("label", is_dark)),
                    curr_pass_field,
                    new_pass_field,
                    ft.Row(controls=[ft.Icon(ft.Icons.CHECKLIST, size=16, color=colors["text_muted"]), pwd_hint], spacing=SPACING["sm"]),
                    confirm_pass_field,
                    submit_btn,
                    ft.Row(controls=[logout_btn], alignment=ft.MainAxisAlignment.CENTER),
                ],
                spacing=SPACING["md"],
                tight=True,
            ),
            width=card_width,
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=RADII["xl"],
            padding=SPACING["2xl"],
            shadow=get_card_shadow(is_dark),
        )

        root = PageContainer(
            content=card,
            expand=True,
            padding=SPACING["md"],
            is_dark=is_dark,
        )
        root.alignment = ft.alignment.center
        return root
