"""
ui/components/college_hero.py: Institutional campus visual assets, hero banners,
and authentic college background components based on real campus imagery.
"""

from typing import Optional, Callable
import flet as ft
from ui.theme import get_theme_colors, COLOR_PRIMARY, COLOR_PRIMARY_LIGHT, get_card_shadow

COLLEGE_BUILDING_IMG = "/images/college_building.jpg"
COLLEGE_STATUE_IMG = "/images/college_statue.jpg"


def create_login_hero_panel(is_staff: bool = False, is_dark: bool = False, compact: bool = False) -> ft.Control:
    """Build a lightweight, illustrative complaint lifecycle panel for authentication."""
    colors = get_theme_colors(is_dark)
    role_label = "STAFF PORTAL" if is_staff else "STUDENT PORTAL"
    steps = [
        (ft.Icons.DESCRIPTION_OUTLINED, "Submitted"),
        (ft.Icons.ACCOUNT_TREE_OUTLINED, "Routed"),
        (ft.Icons.ACCESS_TIME, "Under review"),
        (ft.Icons.TASK_ALT, "Resolved"),
    ]
    step_items = []
    for index, (icon, label) in enumerate(steps):
        step_items.append(
            ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Icon(icon, size=19, color=colors["primary"]),
                        width=38 if compact else 44,
                        height=38 if compact else 44,
                        alignment=ft.Alignment.CENTER,
                        bgcolor="#eff6ff",
                        border=ft.Border.all(1, "#bfdbfe"),
                        border_radius=14,
                    ),
                    ft.Text(label, size=9 if compact else 10, color=colors["text_muted"], text_align=ft.TextAlign.CENTER, max_lines=2),
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
        )
        if index < len(steps) - 1:
            step_items.append(
                ft.Container(
                    height=2,
                    bgcolor="#bfdbfe",
                    expand=True,
                    margin=ft.margin.only(bottom=22),
                )
            )

    lifecycle = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(controls=step_items, spacing=4, vertical_alignment=ft.CrossAxisAlignment.START),
                ft.ProgressBar(
                    value=None,
                    bar_height=2,
                    color=colors["primary"],
                    bgcolor="#eff6ff",
                    semantics_label="Illustrative complaint lifecycle",
                ),
                ft.Text("Illustrative flow · Live progress appears on each complaint", size=11, color=colors["text_muted"]),
            ],
            spacing=10,
        ),
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=14,
        padding=12 if compact else 16,
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.ACCOUNT_BALANCE_OUTLINED, size=17, color=colors["primary"]),
                            ft.Text(role_label, size=10, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                        ],
                        spacing=7,
                    ),
                    bgcolor="#eff6ff",
                    border_radius=20,
                    padding=ft.padding.symmetric(horizontal=11, vertical=6),
                ),
                ft.Text("A better campus starts with being heard.", size=23 if compact else 30, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Text(
                    "Share concerns securely and follow a clear path to resolution.",
                    size=13,
                    color=colors["text_muted"],
                ),
                lifecycle,
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.SHIELD_OUTLINED, size=15, color=colors["primary"]),
                        ft.Text("Private, role-based access", size=11, color=colors["text_muted"]),
                    ],
                    spacing=6,
                ),
            ],
            spacing=14 if compact else 20,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        ),
        bgcolor=colors["bg"],
        border_radius=20,
        padding=14 if compact else 28,
        expand=not compact,
        shadow=get_card_shadow(is_dark),
    )


def create_complaint_lifecycle_panel(is_dark: bool = False) -> ft.Control:
    """Show the standard complaint workflow as an illustrative dashboard panel."""
    colors = get_theme_colors(is_dark)
    steps = [
        (ft.Icons.DESCRIPTION_OUTLINED, "Complaint Received"),
        (ft.Icons.ACCOUNT_BALANCE_OUTLINED, "Assigned to Department"),
        (ft.Icons.PENDING_ACTIONS, "Under Review"),
        (ft.Icons.TASK_ALT, "Resolved"),
    ]
    flow = []
    for index, (icon, label) in enumerate(steps):
        flow.append(ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, size=20, color=colors["primary"]),
                    width=42, height=42, alignment=ft.Alignment.CENTER,
                    bgcolor=colors["surface_variant"], border_radius=12,
                ),
                ft.Text(label, size=10, color=colors["text_muted"],
                        text_align=ft.TextAlign.CENTER, max_lines=2),
            ], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True,
        ))
        if index < len(steps) - 1:
            flow.append(ft.Container(
                height=2, bgcolor=colors["border"], expand=True,
                margin=ft.margin.only(bottom=22),
            ))
    return ft.Container(
        content=ft.Column(controls=[
            ft.Row(controls=[
                ft.Icon(ft.Icons.ACCOUNT_TREE_OUTLINED, size=19, color=colors["primary"]),
                ft.Text("Complaint Resolution Process", size=15,
                        weight=ft.FontWeight.BOLD, color=colors["text"]),
            ], spacing=8),
            ft.Text("A clear path from submission to resolution", size=12, color=colors["text_muted"]),
            ft.Row(controls=flow, spacing=4, vertical_alignment=ft.CrossAxisAlignment.START),
        ], spacing=10),
        bgcolor=colors["surface"], border=ft.Border.all(1, colors["border"]),
        border_radius=12, padding=16,
    )


def create_dashboard_welcome_banner(
    user_name: str,
    roll_number: str = "",
    year: str = "",
    dept_name: str = "",
    role_text: str = "Student",
    on_new_complaint: Optional[Callable[[], None]] = None,
    is_dark: bool = False,
    compact: bool = False
) -> ft.Container:
    """
    Builds the top welcome banner card (Image 3 Panel 2).
    Includes real college panorama visual accent, student details, and primary action button.
    """
    colors = get_theme_colors(is_dark)

    info_parts = []
    if roll_number:
        info_parts.append(f"Roll: {roll_number}")
    if year:
        info_parts.append(f"Year: {year}")
    if dept_name:
        info_parts.append(dept_name)

    subtitle_str = " | ".join(info_parts) if info_parts else role_text

    button_ctrl = None
    if on_new_complaint:
        button_ctrl = ft.ElevatedButton(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.ADD, size=18, color=ft.Colors.WHITE),
                    ft.Text("New Complaint", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6
            ),
            style=ft.ButtonStyle(
                bgcolor=colors["primary"],
                padding=ft.padding.symmetric(horizontal=18, vertical=12),
                shape=ft.RoundedRectangleBorder(radius=10)
            ),
            on_click=lambda _: on_new_complaint()
        )

    if compact:
        # Compact mobile welcome card
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.CircleAvatar(
                                content=ft.Text(user_name[:1].upper() if user_name else "U", color=colors["primary"], weight=ft.FontWeight.BOLD),
                                bgcolor=colors.get("surface_variant", "#e2e8f0"),
                                radius=18
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(f"Welcome back, {user_name}!", size=16, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                    ft.Text(subtitle_str, size=11, color=colors["text_muted"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                ],
                                spacing=2,
                                expand=True
                            )
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER
                    ),
                    *( [button_ctrl] if button_ctrl else [] )
                ],
                spacing=10
            ),
            bgcolor=colors["card_bg"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=14,
            padding=14,
            shadow=get_card_shadow(is_dark),
            margin=ft.margin.only(bottom=10)
        )

    # Desktop / Tablet banner with subtle college panorama accent
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.CircleAvatar(
                            content=ft.Text(user_name[:1].upper() if user_name else "U", size=18, color=colors["primary"], weight=ft.FontWeight.BOLD),
                            bgcolor=colors.get("surface_variant", "#e2e8f0"),
                            radius=24
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(f"Welcome back, {user_name}!", size=20, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                ft.Text(subtitle_str, size=13, color=colors["text_muted"])
                            ],
                            spacing=3
                        )
                    ],
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER
                ),
                *( [button_ctrl] if button_ctrl else [] )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True
        ),
        bgcolor=colors["card_bg"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=16,
        padding=ft.padding.symmetric(horizontal=20, vertical=16),
        shadow=get_card_shadow(is_dark),
        margin=ft.margin.only(bottom=14)
    )
