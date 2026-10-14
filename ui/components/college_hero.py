"""
ui/components/college_hero.py: Institutional campus visual assets, hero banners,
and authentic college background components based on real campus imagery.
"""

from typing import Optional, Callable
import flet as ft
from ui.theme import get_theme_colors, get_card_shadow, get_button_style, RADII, SPACING

COLLEGE_BUILDING_IMG = "/images/college_building.jpg"
COLLEGE_STATUE_IMG = "/images/college_statue.jpg"


def _complaint_lifecycle_strip(compact: bool = False, is_dark: bool = False) -> ft.Control:
    """Small, static lifecycle guide that stays inexpensive on mobile GPUs."""
    colors = get_theme_colors(is_dark)
    steps = [
        (ft.Icons.DESCRIPTION_OUTLINED, "Submitted", colors["primary"]),
        (ft.Icons.ACCOUNT_BALANCE_OUTLINED, "Department review", colors["warning"]),
        (ft.Icons.TASK_ALT, "Resolved", colors["success"]),
    ]
    controls = []
    for index, (icon, label, color) in enumerate(steps):
        controls.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(icon, size=15 if compact else 17, color=color),
                        ft.Text(label, size=9 if compact else 10, color=ft.Colors.WHITE, weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ],
                    spacing=5,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.WHITE)),
                border_radius=RADII["sm"],
                padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["sm"]),
                expand=True,
            )
        )
        if index < len(steps) - 1:
            controls.append(ft.Icon(ft.Icons.ARROW_FORWARD, size=13, color=colors["primary_light"]))
    return ft.Row(controls=controls, spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def create_login_hero_panel(is_staff: bool = False, is_dark: bool = False, compact: bool = False) -> ft.Control:
    """
    Builds the authentic campus visual panel for the login screen.
    Uses real college photos (Building / Statue) with soft royal blue / violet gradient overlays
    and institutional messaging: "A Cleaner, Safer and Better Campus Together".
    """
    colors = get_theme_colors(is_dark)
    img_src = COLLEGE_STATUE_IMG if is_staff else COLLEGE_BUILDING_IMG
    role_label = "COORDINATOR & STAFF PORTAL" if is_staff else "STUDENT GRIEVANCE PORTAL"

    if compact:
        # Mobile compact hero card
        return ft.Container(
            content=ft.Stack(
                controls=[
                    ft.Image(
                        src=img_src,
                        fit=ft.ImageFit.COVER,
                        expand=True,
                        height=160,
                        border_radius=14,
                    ),
                    ft.Container(
                        expand=True,
                        bgcolor=ft.Colors.with_opacity(0.72, colors["bg"] if is_dark else colors["primary"]),
                        border_radius=RADII["md"],
                        padding=ft.padding.symmetric(horizontal=SPACING["lg"], vertical=SPACING["md"]),
                        content=ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=ft.Colors.WHITE, size=18),
                                        ft.Text("Digital Complaint Box", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                    ],
                                    spacing=6
                                ),
                                ft.Text(
                                    "A Cleaner, Safer and Better Campus Together",
                                    size=12,
                                    italic=True,
                                    color=colors["primary_light"],
                                    weight=ft.FontWeight.W_500
                                ),
                                ft.Container(
                                    content=ft.Text(role_label, size=9, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                    bgcolor=ft.Colors.with_opacity(0.35, ft.Colors.WHITE),
                                    border_radius=6,
                                    padding=ft.padding.symmetric(horizontal=6, vertical=2)
                                ),
                                _complaint_lifecycle_strip(compact=True, is_dark=is_dark),
                            ],
                            spacing=4,
                            alignment=ft.MainAxisAlignment.CENTER
                        )
                    )
                ]
            ),
            border_radius=RADII["md"],
            height=198,
            margin=ft.margin.only(bottom=8)
        )

    # Desktop / Tablet hero panel (Image 3 Left Panel)
    return ft.Container(
        content=ft.Stack(
            controls=[
                # Background real college photo
                ft.Image(
                    src=img_src,
                    fit=ft.ImageFit.COVER,
                    expand=True,
                    border_radius=20,
                ),
                # Soft gradient overlay with subtle opacity to keep campus recognizable
                ft.Container(
                    bgcolor=ft.Colors.with_opacity(0.76 if is_dark else 0.72, colors["bg"] if is_dark else colors["primary"]),
                    border_radius=RADII["xl"],
                    padding=SPACING["xl"],
                    content=ft.Column(
                        controls=[
                            # Institution Pill
                            ft.Container(
                                content=ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=colors["primary_light"], size=15),
                                        ft.Text("INSTITUTIONAL GRIEVANCE REDRESSAL", size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                    ],
                                    spacing=6,
                                ),
                                bgcolor=ft.Colors.with_opacity(0.16, colors["surface"]),
                                border=ft.Border.all(1, ft.Colors.with_opacity(0.3, colors["primary_light"])),
                                border_radius=RADII["pill"],
                                padding=ft.padding.symmetric(horizontal=12, vertical=5),
                            ),
                            ft.Container(height=10),
                            ft.Text(
                                "Digital Complaint Box",
                                size=28,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.WHITE
                            ),
                            ft.Text(
                                "A Cleaner, Safer and Better Campus Together",
                                size=18,
                                italic=True,
                                color=colors["primary_light"],
                                weight=ft.FontWeight.W_500
                            ),
                            ft.Container(height=8),
                            ft.Text(
                                "Empowering students and faculty through transparent, confidential, and role-isolated grievance resolution.",
                                size=13,
                                color=ft.Colors.WHITE,
                                height=1.4
                            ),
                            _complaint_lifecycle_strip(is_dark=is_dark),
                            ft.Container(expand=True),
                            # Highlights
                            ft.Column(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=colors["success"]),
                                            ft.Text("5 Core Academic Departments", size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.W_500)
                                        ],
                                        spacing=8
                                    ),
                                    ft.Row(
                                        controls=[
                                            ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=colors["success"]),
                                            ft.Text("Role Isolation & Anonymous Grievances", size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.W_500)
                                        ],
                                        spacing=8
                                    ),
                                    ft.Row(
                                        controls=[
                                            ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=colors["success"]),
                                            ft.Text("Zero-Leakage Institutional Security", size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.W_500)
                                        ],
                                        spacing=8
                                    ),
                                ],
                                spacing=8
                            ),
                            ft.Container(height=6),
                            # Campus watermark text
                            ft.Text(
                                "Official Campus Portal • Real-Time Tracking",
                                size=11,
                                color=colors["text_muted"]
                            )
                        ],
                        spacing=6,
                        horizontal_alignment=ft.CrossAxisAlignment.START
                    )
                )
            ]
        ),
        border_radius=RADII["xl"],
        expand=True,
        shadow=get_card_shadow(is_dark)
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
            style=get_button_style(is_dark),
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
                                bgcolor=colors["surface_variant"],
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
            border_radius=RADII["md"],
            padding=SPACING["md"],
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
                            bgcolor=colors["surface_variant"],
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
        border_radius=RADII["lg"],
        padding=ft.padding.symmetric(horizontal=20, vertical=16),
        shadow=get_card_shadow(is_dark),
        margin=ft.margin.only(bottom=14)
    )
