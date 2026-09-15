"""
ui/components/complaint_card.py: Presentation card for complaints with status pills, priority badges, and +N group indicators.
Supports responsive reflow and Dark Mode styling.
"""

from typing import Dict, Any, Callable
import flet as ft
from ui.theme import (
    COLOR_PRIMARY, STATUS_COLORS, PRIORITY_COLORS, get_theme_colors
)
from ui.state import AppState
from utils.helpers import format_datetime


def create_complaint_card(
    complaint: Dict[str, Any],
    on_view_details: Callable[[Dict[str, Any]], None],
    is_staff: bool = False
) -> ft.Container:
    """Renders a complaint card with full Dark Mode and responsive support."""
    is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)

    cid = complaint.get("complaint_id")
    title = complaint.get("title", "Untitled")
    desc = complaint.get("description", "")
    short_desc = desc if len(desc) <= 120 else desc[:117] + "..."
    status = complaint.get("status", "Pending")
    priority = complaint.get("priority", "Low")
    is_anon = complaint.get("is_anonymous", False)
    is_hostel = complaint.get("is_hostel", False)

    # Categories & Locations
    cat_name = complaint.get("categories", {}).get("name") if isinstance(complaint.get("categories"), dict) else (complaint.get("category_name") or "General")
    loc_name = complaint.get("locations", {}).get("name") if isinstance(complaint.get("locations"), dict) else (complaint.get("location_custom") or complaint.get("location_name") or "Campus")

    status_color = STATUS_COLORS.get(status, "#6b7280")
    priority_color = PRIORITY_COLORS.get(priority, "#6b7280")

    # Header tags
    header_chips = [
        ft.Container(
            content=ft.Text(f"#{cid}", size=12, weight=ft.FontWeight.BOLD, color=colors["primary"]),
            bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=8, vertical=4)
        ),
        ft.Container(
            content=ft.Text(cat_name, size=11, weight=ft.FontWeight.W_500, color="#94a3b8" if is_dark else "#334155"),
            bgcolor="#334155" if is_dark else "#e2e8f0",
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=8, vertical=4)
        ),
        ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.LOCATION_ON_OUTLINED, size=12, color=colors["text_muted"]),
                    ft.Text(loc_name, size=11, color=colors["text_muted"])
                ],
                spacing=2
            )
        )
    ]

    if is_hostel:
        header_chips.append(
            ft.Container(
                content=ft.Text("Hostel", size=11, weight=ft.FontWeight.W_600, color="#2dd4bf" if is_dark else "#0f766e"),
                bgcolor="#134e4a" if is_dark else "#ccfbf1",
                border_radius=8,
                padding=ft.padding.symmetric(horizontal=8, vertical=4)
            )
        )

    if is_anon:
        header_chips.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.VISIBILITY_OFF, size=12, color="#94a3b8" if is_dark else "#64748b"),
                        ft.Text("Anonymous", size=11, weight=ft.FontWeight.W_600, color="#94a3b8" if is_dark else "#64748b")
                    ],
                    spacing=3
                ),
                bgcolor="#1e293b" if is_dark else "#f1f5f9",
                border_radius=8,
                padding=ft.padding.symmetric(horizontal=8, vertical=4)
            )
        )

    # Duplicate count / Issue Group Indicator (+N)
    dup_count = complaint.get("duplicate_count", 0)
    if dup_count > 0:
        header_chips.append(
            ft.Container(
                content=ft.Text(f"+{dup_count} Similar", size=11, weight=ft.FontWeight.BOLD, color="#f59e0b" if is_dark else "#b45309"),
                bgcolor="#78350f" if is_dark else "#fef3c7",
                border_radius=8,
                padding=ft.padding.symmetric(horizontal=8, vertical=4)
            )
        )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(controls=header_chips, wrap=True, spacing=8),
                ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Text(short_desc, size=13, color=colors["text_muted"], max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Divider(height=1, color=colors["border"]),
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                # Status Pill
                                ft.Container(
                                    content=ft.Text(status, size=12, weight=ft.FontWeight.W_600, color=status_color),
                                    bgcolor=ft.Colors.with_opacity(0.12, status_color),
                                    border_radius=20,
                                    padding=ft.padding.symmetric(horizontal=10, vertical=4)
                                ),
                                # Priority Pill
                                ft.Container(
                                    content=ft.Text(priority, size=12, weight=ft.FontWeight.W_600, color=priority_color),
                                    bgcolor=ft.Colors.with_opacity(0.12, priority_color),
                                    border_radius=20,
                                    padding=ft.padding.symmetric(horizontal=10, vertical=4)
                                )
                            ],
                            spacing=8,
                            wrap=True
                        ),
                        ft.ElevatedButton(
                            content=ft.Text("View Details"),
                            icon=ft.Icons.ARROW_FORWARD,
                            style=ft.ButtonStyle(
                                bgcolor=colors["primary"],
                                color=ft.Colors.WHITE,
                                padding=ft.padding.symmetric(horizontal=14, vertical=8),
                                shape=ft.RoundedRectangleBorder(radius=8)
                            ),
                            on_click=lambda _: on_view_details(complaint)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True
                )
            ],
            spacing=10
        ),
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=12,
        padding=16,
        margin=ft.margin.only(bottom=12)
    )
