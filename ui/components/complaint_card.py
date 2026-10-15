"""
ui/components/complaint_card.py: Presentation card for complaints with status pills, priority badges, and +N group indicators.
Supports responsive reflow and Dark Mode styling.
"""

from typing import Dict, Any, Callable, Optional
import flet as ft
from ui.theme import (
    STATUS_COLORS, get_theme_colors, get_card_shadow, StatusBadge, PriorityBadge,
    RADII, SPACING, get_button_style, get_text_style
)
from ui.state import AppState
from utils.helpers import format_datetime


def create_complaint_card(
    complaint: Dict[str, Any],
    on_view_details: Callable[[Dict[str, Any]], None],
    is_staff: bool = False,
    on_delete: Optional[Callable[[Dict[str, Any]], None]] = None
) -> ft.Container:
    """Renders a complaint card with full Dark Mode, elevation, and responsive support."""
    is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)

    cid = complaint.get("complaint_id")
    title = complaint.get("title", "Untitled")
    desc = complaint.get("description", "")
    short_desc = desc if len(desc) <= 120 else desc[:117] + "..."
    status = complaint.get("status", "Pending")
    priority = complaint.get("priority", "Low")
    status_color = STATUS_COLORS.get(status, colors["text_muted"])
    is_anon = complaint.get("is_anonymous", False)
    is_hostel = complaint.get("is_hostel", False)
    created_at = complaint.get("created_at") or ""
    date_str = str(created_at)[:10] if created_at else ""

    # Categories & Locations
    cat_name = complaint.get("categories", {}).get("name") if isinstance(complaint.get("categories"), dict) else (complaint.get("category_name") or "General")
    loc_name = complaint.get("locations", {}).get("name") if isinstance(complaint.get("locations"), dict) else (complaint.get("location_custom") or complaint.get("location_name") or "Campus")

    sub_name = complaint.get("subcategories", {}).get("name") if isinstance(complaint.get("subcategories"), dict) else (complaint.get("subcategory_name") or complaint.get("subcategory_custom") or "")
    department = complaint.get("departments") or complaint.get("department")
    department_name = (
        department.get("name") if isinstance(department, dict)
        else department or complaint.get("department_name") or complaint.get("department_code")
    )
    attachment_count = complaint.get("attachment_count", complaint.get("attachments_count"))
    if attachment_count is None:
        complaint_attachments = complaint.get("attachments")
        attachment_count = len(complaint_attachments) if isinstance(complaint_attachments, list) else 0

    # Header tags
    header_chips = [
        ft.Container(
            content=ft.Text(f"#{cid}", size=12, weight=ft.FontWeight.BOLD, color=colors["primary"]),
            bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
            border_radius=RADII["sm"],
            padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"])
        ),
        ft.Container(
            content=ft.Text(cat_name, size=11, weight=ft.FontWeight.W_500, color=colors["text"]),
            bgcolor=colors["surface_variant"],
            border_radius=RADII["sm"],
            padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"])
        ),
    ]

    if sub_name and str(sub_name).lower() not in ("none", "null", ""):
        header_chips.append(
            ft.Container(
                content=ft.Text(str(sub_name), size=11, weight=ft.FontWeight.W_500, color=colors["primary"]),
                bgcolor=ft.Colors.with_opacity(0.08, colors["primary"]),
                border_radius=RADII["sm"],
                padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"])
            )
        )

    if department_name:
        header_chips.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.APARTMENT, size=12, color=colors["primary"]),
                        ft.Text(str(department_name), size=11, color=colors["text_muted"]),
                    ],
                    spacing=4,
                    tight=True,
                ),
                bgcolor=colors["surface_variant"],
                border_radius=RADII["sm"],
                padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"]),
            )
        )

    header_chips.append(
        ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.ATTACH_FILE, size=12, color=colors["text_muted"]),
                    ft.Text(str(attachment_count), size=11, color=colors["text_muted"]),
                ],
                spacing=3,
                tight=True,
            ),
            bgcolor=colors["surface_variant"],
            border_radius=RADII["sm"],
            padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"]),
        )
    )

    header_chips.append(
        ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.LOCATION_ON_OUTLINED, size=12, color=colors["text_muted"]),
                    ft.Text(loc_name, size=11, color=colors["text_muted"])
                ],
                spacing=2,
                tight=True,
            )
        )
    )

    if date_str:
        header_chips.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=11, color=colors["text_muted"]),
                        ft.Text(date_str, size=11, color=colors["text_muted"])
                    ],
                    spacing=2,
                    tight=True,
                )
            )
        )

    if is_hostel:
        header_chips.append(
            ft.Container(
                content=ft.Text("Hostel", size=11, weight=ft.FontWeight.W_600, color=colors["secondary"]),
                bgcolor=ft.Colors.with_opacity(0.12, colors["secondary"]),
                border_radius=RADII["sm"],
                padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"])
            )
        )

    if is_anon:
        header_chips.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.VISIBILITY_OFF, size=12, color=colors["text_muted"]),
                        ft.Text("Anonymous", size=11, weight=ft.FontWeight.W_600, color=colors["text_muted"])
                    ],
                    spacing=3,
                    tight=True,
                ),
                bgcolor=colors["surface_variant"],
                border_radius=RADII["sm"],
                padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"])
            )
        )

    # Duplicate count / Issue Group Indicator (+N)
    dup_count = complaint.get("duplicate_count", 0)
    if dup_count > 0:
        header_chips.append(
            ft.Container(
                content=ft.Text(f"+{dup_count} Similar", size=11, weight=ft.FontWeight.BOLD, color=colors["warning"]),
                bgcolor=ft.Colors.with_opacity(0.12, colors["warning"]),
                border_radius=RADII["sm"],
                padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"])
            )
        )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(controls=header_chips, wrap=True, spacing=8),
                ft.Text(title, style=get_text_style("title", is_dark)),
                ft.Text(short_desc, size=13, color=colors["text_muted"], max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Divider(height=1, color=colors["border"]),
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                # Status Pill
                                StatusBadge(status, is_dark),
                                # Priority Pill
                                PriorityBadge(priority, is_dark)
                            ],
                            spacing=8,
                            tight=True,
                        ),
                        ft.Row(
                            controls=[
                                *(
                                    [
                                        ft.OutlinedButton(
                                            content=ft.Row([
                                                ft.Icon(ft.Icons.DELETE_OUTLINE, size=16, color=colors["danger"]),
                                                ft.Text("Delete", size=12, color=colors["danger"])
                                            ], spacing=4),
                                            style=get_button_style(is_dark, variant="danger_outline", size="sm"),
                                            tooltip="Delete this pending grievance",
                                            on_click=lambda _: on_delete(complaint)
                                        )
                                    ] if (on_delete and not is_staff and status == "Pending" and not complaint.get("has_admin_action")) else []
                                ),
                                ft.ElevatedButton(
                                    content=ft.Row(
                                        controls=[
                                            ft.Text("View Details", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                                            ft.Icon(ft.Icons.ARROW_FORWARD, size=14, color=ft.Colors.WHITE)
                                        ],
                                        spacing=4
                                    ),
                                    style=get_button_style(is_dark, size="sm"),
                                    on_click=lambda _: on_view_details(complaint)
                                )
                            ],
                            spacing=8
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True
                )
            ],
            spacing=10
        ),
        bgcolor=colors["card_bg"],
        border=ft.Border(
            left=ft.BorderSide(4, status_color),
            top=ft.BorderSide(1, colors["border"]),
            right=ft.BorderSide(1, colors["border"]),
            bottom=ft.BorderSide(1, colors["border"])
        ),
        border_radius=RADII["lg"],
        padding=SPACING["lg"],
        shadow=get_card_shadow(is_dark),
        margin=ft.margin.only(bottom=12)
    )
