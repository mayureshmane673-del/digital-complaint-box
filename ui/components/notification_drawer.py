"""
ui/components/notification_drawer.py: In-app Notification Center dialog with mark-as-read and reference navigation.
"""

from typing import Callable, Optional
import flet as ft
from services.notification_service import NotificationService
from ui.theme import COLOR_PRIMARY, COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_MUTED
from utils.helpers import format_datetime
from ui.flet_compat import open_dialog, close_dialog


def show_notification_dialog(
    page: ft.Page,
    user_id: str,
    role: str,
    department_id: Optional[str],
    on_select_reference: Optional[Callable[[str, str], None]] = None,
    on_badge_update: Optional[Callable[[int], None]] = None
):
    from ui.state import AppState
    from ui.theme import get_theme_colors
    is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)

    notifications = NotificationService.get_user_notifications(user_id, role, department_id)
    current_unread = sum(1 for n in notifications if not n.get("is_read"))

    notification_items = []
    item_trackers = []

    for n in notifications:
        nid = n.get("id")
        is_read = n.get("is_read", False)
        title = n.get("title", "Notification")
        msg = n.get("message", "")
        t_str = format_datetime(n.get("created_at"))
        ref_type = n.get("reference_type")
        ref_id = n.get("reference_id")

        icon_ctrl = ft.Icon(
            ft.Icons.NOTIFICATIONS_ACTIVE if not is_read else ft.Icons.NOTIFICATIONS_NONE,
            color=colors["primary"] if not is_read else colors["text_muted"],
            size=22
        )
        title_ctrl = ft.Text(
            title,
            weight=ft.FontWeight.BOLD if not is_read else ft.FontWeight.NORMAL,
            size=13,
            color=colors["text"]
        )
        time_ctrl = ft.Text(t_str, size=11, color=colors["text_muted"])
        msg_ctrl = ft.Text(
            msg,
            size=12,
            color=colors["text"] if not is_read else colors["text_muted"]
        )

        read_btn = None
        clear_btn = None
        card_container = None

        tracker = {
            "id": nid,
            "icon": icon_ctrl,
            "title": title_ctrl,
            "msg": msg_ctrl,
            "read_btn": None,
            "clear_btn": None,
            "container": None,
            "is_read": is_read
        }

        def make_clear_handler(n_id, trk):
            def do_clear(e):
                if n_id:
                    NotificationService.clear_notification(n_id)
                if trk["container"]:
                    trk["container"].visible = False
                page.update()
            return do_clear

        clear_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            tooltip="Clear notification",
            icon_color=colors["text_muted"],
            icon_size=18,
            visible=is_read,
            on_click=make_clear_handler(nid, tracker)
        )
        tracker["clear_btn"] = clear_btn

        if not is_read and nid:
            def make_mark_read_handler(n_id, trk):
                def do_mark_read(e):
                    nonlocal current_unread
                    if NotificationService.mark_as_read(n_id):
                        current_unread = max(0, current_unread - 1)
                        if on_badge_update:
                            on_badge_update(current_unread)
                        if trk["container"]:
                            trk["container"].bgcolor = colors["surface"]
                            trk["container"].border = ft.Border.all(1, colors["border"])
                        if trk["read_btn"]:
                            trk["read_btn"].visible = False
                        if trk["clear_btn"]:
                            trk["clear_btn"].visible = True
                        trk["is_read"] = True
                        trk["icon"].name = ft.Icons.NOTIFICATIONS_NONE
                        trk["icon"].color = colors["text_muted"]
                        trk["title"].weight = ft.FontWeight.NORMAL
                        trk["msg"].color = colors["text_muted"]
                        page.update()
                return do_mark_read

            read_btn = ft.IconButton(
                icon=ft.Icons.CHECK,
                tooltip="Mark as read",
                icon_color="#059669",
                icon_size=18,
                on_click=make_mark_read_handler(nid, tracker)
            )
            tracker["read_btn"] = read_btn

        def make_click_note_handler(n_id, r_type, r_id, was_unread, trk):
            def on_click_note(e):
                nonlocal current_unread
                if was_unread and n_id:
                    NotificationService.mark_as_read(n_id)
                    current_unread = max(0, current_unread - 1)
                    if on_badge_update:
                        on_badge_update(current_unread)
                dlg.open = False
                page.update()
                if on_select_reference and r_type and r_id:
                    on_select_reference(r_type, r_id)
            return on_click_note

        action_icons = []
        if read_btn:
            action_icons.append(read_btn)
        action_icons.append(clear_btn)

        card_row_controls = [
            icon_ctrl,
            ft.Column(
                controls=[
                    ft.Row(
                        controls=[title_ctrl, time_ctrl],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    msg_ctrl
                ],
                expand=True,
                spacing=2
            ),
            ft.Row(controls=action_icons, spacing=0)
        ]

        card_container = ft.Container(
            content=ft.Row(
                controls=card_row_controls,
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
            bgcolor=colors["surface"] if is_read else ("#1e293b" if is_dark else "#f0f7ff"),
            border=ft.Border.all(1, colors["border"] if is_read else colors["primary"]),
            border_radius=8,
            padding=10,
            margin=ft.margin.only(bottom=6),
            on_click=make_click_note_handler(nid, ref_type, ref_id, not is_read, tracker)
        )
        tracker["container"] = card_container
        item_trackers.append(tracker)
        notification_items.append(card_container)

    if not notification_items:
        notification_items.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.NOTIFICATIONS_OFF_OUTLINED, size=40, color=colors["text_muted"]),
                        ft.Text("No notifications yet", size=14, color=colors["text_muted"])
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER
                ),
                padding=40
            )
        )

    def mark_all_read(e):
        nonlocal current_unread
        NotificationService.mark_all_as_read(user_id, role, department_id)
        current_unread = 0
        if on_badge_update:
            on_badge_update(0)
        for trk in item_trackers:
            trk["is_read"] = True
            if trk["container"]:
                trk["container"].bgcolor = colors["surface"]
                trk["container"].border = ft.Border.all(1, colors["border"])
            if trk["read_btn"]:
                trk["read_btn"].visible = False
            if trk["clear_btn"]:
                trk["clear_btn"].visible = True
            trk["icon"].name = ft.Icons.NOTIFICATIONS_NONE
            trk["icon"].color = colors["text_muted"]
            trk["title"].weight = ft.FontWeight.NORMAL
            trk["msg"].color = colors["text_muted"]
        page.update()

    def clear_all_read(e):
        NotificationService.clear_all_read(user_id, role, department_id)
        for trk in item_trackers:
            if trk["is_read"] and trk["container"]:
                trk["container"].visible = False
        page.update()

    dlg = ft.AlertDialog(
        title=ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.NOTIFICATIONS, color=colors["primary"]),
                        ft.Text("Notification Center", size=18, weight=ft.FontWeight.BOLD, color=colors["text"])
                    ],
                    spacing=8
                ),
                ft.Row(
                    controls=[
                        ft.TextButton(
                            content=ft.Row([ft.Icon(ft.Icons.DONE_ALL, size=15), ft.Text("Mark Read", size=12)]),
                            on_click=mark_all_read
                        ),
                        ft.TextButton(
                            content=ft.Row([ft.Icon(ft.Icons.DELETE_SWEEP, size=15), ft.Text("Clear Read", size=12)]),
                            on_click=clear_all_read
                        )
                    ],
                    spacing=4
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        ),
        content=ft.Container(
            content=ft.Column(controls=notification_items, scroll=ft.ScrollMode.AUTO),
            width=540,
            height=440
        ),
        bgcolor=colors["surface"],
        actions=[
            ft.TextButton("Close", on_click=lambda _: close_dialog(page, dlg))
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )

    open_dialog(page, dlg)
