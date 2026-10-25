"""
ui/components/navbar.py: Role-aware navigation sidebar and responsive top app bar with Dark Mode toggle.
"""

from typing import Callable, Optional
import flet as ft
from ui.theme import (
    COLOR_DANGER, get_theme_colors, get_text_style,
    RADII, SPACING
)
from ui.state import AppState
from models.user import UserRole
from services.notification_service import NotificationService
from ui.components.notification_drawer import show_notification_dialog


def create_app_bar(
    page: ft.Page,
    user_name: str,
    user_role: str,
    department_code: Optional[str],
    user_id: str,
    department_id: Optional[str],
    on_logout: Callable[[], None]
) -> ft.AppBar:
    from services.cache_service import CacheService
    cached_unread = CacheService.get_cached_unread_count(user_id, user_role, department_id)
    unread_count = cached_unread if cached_unread is not None else 0
    is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)

    badge_text = ft.Text(str(unread_count), size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
    badge_container = ft.Container(
        content=badge_text,
        bgcolor=COLOR_DANGER,
        border_radius=RADII["pill"],
        padding=ft.padding.symmetric(horizontal=5, vertical=1),
        top=6,
        right=6,
        visible=unread_count > 0
    )

    def update_badge(count: int):
        badge_text.value = str(count)
        badge_container.visible = count > 0
        try:
            page.update()
        except Exception:
            pass

    # If unread count was not in cache, fetch asynchronously without blocking UI render
    if cached_unread is None:
        import threading
        def _fetch_unread_bg():
            try:
                count = NotificationService.get_unread_count(user_id, user_role, department_id)
                if count != unread_count:
                    update_badge(count)
            except Exception:
                pass
        threading.Thread(target=_fetch_unread_bg, daemon=True).start()

    def open_notifications(e):
        show_notification_dialog(page, user_id, user_role, department_id, on_badge_update=update_badge)

    role_badge_text = user_role
    if department_code and user_role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
        role_badge_text = f"{user_role} ({department_code})"

    is_compact = bool(isinstance(getattr(page, "width", None), (int, float)) and page.width < 768)

    user_menu_content = ft.Row(
        controls=[
            ft.CircleAvatar(
                content=ft.Text(
                    user_name[:1].upper() if user_name else "U",
                    color=colors["primary"],
                    weight=ft.FontWeight.BOLD,
                    size=11 if is_compact else 13,
                ),
                bgcolor=colors["surface_variant"],
                radius=12 if is_compact else 15,
            ),
            *([] if is_compact else [
                ft.Column(
                    controls=[
                        ft.Text(user_name or "User", style=get_text_style("label", is_dark)),
                        ft.Text(role_badge_text, style=get_text_style("caption", is_dark)),
                    ],
                    spacing=0,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18, color=colors["text_muted"]),
            ]),
        ],
        spacing=SPACING["sm"],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    user_menu = ft.PopupMenuButton(
        content=user_menu_content,
        bgcolor=colors["surface"],
        shape=ft.RoundedRectangleBorder(radius=RADII["md"]),
        items=[
            ft.PopupMenuItem(
                content=ft.Column(
                    controls=[
                        ft.Text(user_name or "User", weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Text(role_badge_text, size=12, color=colors["text_muted"]),
                    ],
                    spacing=2,
                    tight=True,
                ),
            ),
            ft.PopupMenuItem(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.LOGOUT, size=18, color=colors["text_muted"]),
                        ft.Text("Log out", color=colors["text"]),
                    ],
                    spacing=SPACING["sm"],
                ),
                on_click=lambda _: on_logout(),
            ),
        ],
    )

    return ft.AppBar(
        leading=ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=colors["primary"], size=22),
        leading_width=36 if is_compact else 40,
        title=ft.Row(
            controls=[
                ft.Text(
                    "Complaint Box" if is_compact else "Digital Complaint Box",
                    size=15 if is_compact else 17,
                    weight=ft.FontWeight.BOLD,
                    color=colors["text"]
                ),
                *(
                    [
                        ft.Container(
                            content=ft.Text(role_badge_text, size=11, weight=ft.FontWeight.W_600, color=colors["primary"]),
                            bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                            border_radius=RADII["pill"],
                            padding=ft.padding.symmetric(horizontal=8, vertical=2)
                        )
                    ] if not is_compact else []
                )
            ],
            spacing=6 if is_compact else 8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
        bgcolor=colors["surface"],
        color=colors["text"],
        elevation=0,
        shadow_color=ft.Colors.with_opacity(0.06, colors["text"]),
        actions=[
            # Dark Mode Toggle Button
            ft.IconButton(
                icon=ft.Icons.LIGHT_MODE if is_dark else ft.Icons.DARK_MODE,
                icon_color=colors["text_muted"],
                icon_size=18 if is_compact else 20,
                tooltip="Switch to Light Mode" if is_dark else "Switch to Dark Mode",
                on_click=lambda _: AppState.toggle_dark_mode()
            ),
            # Notification Bell with Badge
            ft.Stack(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.NOTIFICATIONS_OUTLINED,
                        icon_color=colors["text_muted"],
                        icon_size=18 if is_compact else 20,
                        tooltip="Notification Center",
                        on_click=open_notifications
                    ),
                    badge_container
                ]
            ),
            user_menu,
            ft.Container(width=SPACING["xs"])
        ]
    )


def create_navigation_rail(
    role: str,
    selected_index: int,
    on_destination_selected: Callable[[int], None],
    compact: bool = False
) -> ft.NavigationRail:
    """Builds role-specific navigation sidebar with dark mode and responsive compact mode."""
    is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)

    destinations = []
    if role == UserRole.STUDENT.value:
        destinations = [
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationRailDestination(icon=ft.Icons.ADD_COMMENT_OUTLINED, selected_icon=ft.Icons.ADD_COMMENT, label="New Complaint"),
            ft.NavigationRailDestination(icon=ft.Icons.FOLDER_OUTLINED, selected_icon=ft.Icons.FOLDER, label="My Complaints"),
            ft.NavigationRailDestination(icon=ft.Icons.RATE_REVIEW_OUTLINED, selected_icon=ft.Icons.RATE_REVIEW, label="Feedback"),
            ft.NavigationRailDestination(icon=ft.Icons.HOTEL_OUTLINED, selected_icon=ft.Icons.HOTEL, label="Hostel Status"),
            ft.NavigationRailDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="My Account"),
        ]
    elif role == UserRole.COORDINATOR.value:
        destinations = [
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationRailDestination(icon=ft.Icons.LIST_ALT_OUTLINED, selected_icon=ft.Icons.LIST_ALT, label="Complaints"),
            ft.NavigationRailDestination(icon=ft.Icons.DYNAMIC_FEED_OUTLINED, selected_icon=ft.Icons.DYNAMIC_FEED, label="Issue Groups"),
            ft.NavigationRailDestination(icon=ft.Icons.BADGE_OUTLINED, selected_icon=ft.Icons.BADGE, label="Roll Numbers"),
            ft.NavigationRailDestination(icon=ft.Icons.BAR_CHART_OUTLINED, selected_icon=ft.Icons.BAR_CHART, label="Reports"),
            ft.NavigationRailDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="My Account"),
        ]
    elif role == UserRole.HOD.value:
        destinations = [
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationRailDestination(icon=ft.Icons.LIST_ALT_OUTLINED, selected_icon=ft.Icons.LIST_ALT, label="Complaints"),
            ft.NavigationRailDestination(icon=ft.Icons.DYNAMIC_FEED_OUTLINED, selected_icon=ft.Icons.DYNAMIC_FEED, label="Issue Groups"),
            ft.NavigationRailDestination(icon=ft.Icons.PASSWORD_OUTLINED, selected_icon=ft.Icons.PASSWORD, label="Security Codes"),
            ft.NavigationRailDestination(icon=ft.Icons.ANALYTICS_OUTLINED, selected_icon=ft.Icons.ANALYTICS, label="Reports & Analytics"),
            ft.NavigationRailDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="Account & Coords"),
        ]
    elif role == UserRole.GENERAL_HOD.value:
        destinations = [
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationRailDestination(icon=ft.Icons.LIST_ALT_OUTLINED, selected_icon=ft.Icons.LIST_ALT, label="Complaints"),
            ft.NavigationRailDestination(icon=ft.Icons.DYNAMIC_FEED_OUTLINED, selected_icon=ft.Icons.DYNAMIC_FEED, label="Issue Groups"),
            ft.NavigationRailDestination(icon=ft.Icons.PASSWORD_OUTLINED, selected_icon=ft.Icons.PASSWORD, label="Security Code"),
            ft.NavigationRailDestination(icon=ft.Icons.ANALYTICS_OUTLINED, selected_icon=ft.Icons.ANALYTICS, label="Reports"),
            ft.NavigationRailDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="My Account"),
        ]
    elif role == UserRole.LIBRARY_INCHARGE.value:
        destinations = [
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationRailDestination(icon=ft.Icons.LOCAL_LIBRARY_OUTLINED, selected_icon=ft.Icons.LOCAL_LIBRARY, label="Library Complaints"),
            ft.NavigationRailDestination(icon=ft.Icons.DYNAMIC_FEED_OUTLINED, selected_icon=ft.Icons.DYNAMIC_FEED, label="Issue Groups"),
            ft.NavigationRailDestination(icon=ft.Icons.PASSWORD_OUTLINED, selected_icon=ft.Icons.PASSWORD, label="Security Code"),
            ft.NavigationRailDestination(icon=ft.Icons.BAR_CHART_OUTLINED, selected_icon=ft.Icons.BAR_CHART, label="Reports"),
            ft.NavigationRailDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="My Account"),
        ]
    elif role == UserRole.HOSTEL_INCHARGE.value:
        destinations = [
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationRailDestination(icon=ft.Icons.HOW_TO_REG_OUTLINED, selected_icon=ft.Icons.HOW_TO_REG, label="Hostel Requests"),
            ft.NavigationRailDestination(icon=ft.Icons.HOTEL_OUTLINED, selected_icon=ft.Icons.HOTEL, label="Hostel Complaints"),
            ft.NavigationRailDestination(icon=ft.Icons.DYNAMIC_FEED_OUTLINED, selected_icon=ft.Icons.DYNAMIC_FEED, label="Issue Groups"),
            ft.NavigationRailDestination(icon=ft.Icons.PASSWORD_OUTLINED, selected_icon=ft.Icons.PASSWORD, label="Security Code"),
            ft.NavigationRailDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="My Account"),
        ]
    elif role == UserRole.PRINCIPAL.value:
        destinations = [
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Campus Overview"),
            ft.NavigationRailDestination(icon=ft.Icons.LIST_ALT_OUTLINED, selected_icon=ft.Icons.LIST_ALT, label="All Complaints"),
            ft.NavigationRailDestination(icon=ft.Icons.ANALYTICS_OUTLINED, selected_icon=ft.Icons.ANALYTICS, label="Dept Analytics"),
            ft.NavigationRailDestination(icon=ft.Icons.LOCATION_CITY_OUTLINED, selected_icon=ft.Icons.LOCATION_CITY, label="Locations"),
            ft.NavigationRailDestination(icon=ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, selected_icon=ft.Icons.ADMIN_PANEL_SETTINGS, label="Staff Security Codes"),
            ft.NavigationRailDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="Account Mgmt"),
        ]

    safe_index = min(selected_index, len(destinations) - 1) if destinations else 0

    return ft.NavigationRail(
        selected_index=safe_index,
        label_type=ft.NavigationRailLabelType.NONE if compact else ft.NavigationRailLabelType.ALL,
        min_width=56 if compact else 100,
        min_extended_width=180,
        destinations=destinations,
        on_change=lambda e: on_destination_selected(e.control.selected_index),
        bgcolor=colors["surface"],
        indicator_color=ft.Colors.with_opacity(0.14, colors["primary"]),
        selected_label_text_style=get_text_style("caption", is_dark, color=colors["primary"], weight=ft.FontWeight.W_600),
        unselected_label_text_style=get_text_style("caption", is_dark, color=colors["text_muted"]),
        use_indicator=True,
    )


def create_bottom_nav_bar(
    role: str,
    selected_index: int,
    on_destination_selected: Callable[[int], None]
) -> ft.NavigationBar:
    """Builds role-specific bottom navigation bar for mobile screens (Image 3)."""
    is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)
    destinations = []
    if role == UserRole.STUDENT.value:
        destinations = [
            ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Home"),
            ft.NavigationBarDestination(icon=ft.Icons.ADD_COMMENT_OUTLINED, selected_icon=ft.Icons.ADD_COMMENT, label="New"),
            ft.NavigationBarDestination(icon=ft.Icons.FOLDER_OUTLINED, selected_icon=ft.Icons.FOLDER, label="My"),
            ft.NavigationBarDestination(icon=ft.Icons.RATE_REVIEW_OUTLINED, selected_icon=ft.Icons.RATE_REVIEW, label="Feedback"),
            ft.NavigationBarDestination(icon=ft.Icons.HOTEL_OUTLINED, selected_icon=ft.Icons.HOTEL, label="Hostel"),
            ft.NavigationBarDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="Account"),
        ]
    elif role == UserRole.COORDINATOR.value:
        destinations = [
            ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Home"),
            ft.NavigationBarDestination(icon=ft.Icons.LIST_ALT_OUTLINED, selected_icon=ft.Icons.LIST_ALT, label="Complaints"),
            ft.NavigationBarDestination(icon=ft.Icons.DYNAMIC_FEED_OUTLINED, selected_icon=ft.Icons.DYNAMIC_FEED, label="Groups"),
            ft.NavigationBarDestination(icon=ft.Icons.BADGE_OUTLINED, selected_icon=ft.Icons.BADGE, label="Rolls"),
            ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART_OUTLINED, selected_icon=ft.Icons.BAR_CHART, label="Reports"),
            ft.NavigationBarDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="Account"),
        ]
    elif role in (UserRole.HOD.value, UserRole.GENERAL_HOD.value):
        destinations = [
            ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Home"),
            ft.NavigationBarDestination(icon=ft.Icons.LIST_ALT_OUTLINED, selected_icon=ft.Icons.LIST_ALT, label="Complaints"),
            ft.NavigationBarDestination(icon=ft.Icons.DYNAMIC_FEED_OUTLINED, selected_icon=ft.Icons.DYNAMIC_FEED, label="Groups"),
            ft.NavigationBarDestination(icon=ft.Icons.PASSWORD_OUTLINED, selected_icon=ft.Icons.PASSWORD, label="Security"),
            ft.NavigationBarDestination(icon=ft.Icons.ANALYTICS_OUTLINED, selected_icon=ft.Icons.ANALYTICS, label="Reports"),
            ft.NavigationBarDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="Account"),
        ]
    elif role == UserRole.LIBRARY_INCHARGE.value:
        destinations = [
            ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Home"),
            ft.NavigationBarDestination(icon=ft.Icons.LOCAL_LIBRARY_OUTLINED, selected_icon=ft.Icons.LOCAL_LIBRARY, label="Complaints"),
            ft.NavigationBarDestination(icon=ft.Icons.DYNAMIC_FEED_OUTLINED, selected_icon=ft.Icons.DYNAMIC_FEED, label="Groups"),
            ft.NavigationBarDestination(icon=ft.Icons.PASSWORD_OUTLINED, selected_icon=ft.Icons.PASSWORD, label="Security"),
            ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART_OUTLINED, selected_icon=ft.Icons.BAR_CHART, label="Reports"),
            ft.NavigationBarDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="Account"),
        ]
    elif role == UserRole.HOSTEL_INCHARGE.value:
        destinations = [
            ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Home"),
            ft.NavigationBarDestination(icon=ft.Icons.HOW_TO_REG_OUTLINED, selected_icon=ft.Icons.HOW_TO_REG, label="Requests"),
            ft.NavigationBarDestination(icon=ft.Icons.HOTEL_OUTLINED, selected_icon=ft.Icons.HOTEL, label="Complaints"),
            ft.NavigationBarDestination(icon=ft.Icons.DYNAMIC_FEED_OUTLINED, selected_icon=ft.Icons.DYNAMIC_FEED, label="Groups"),
            ft.NavigationBarDestination(icon=ft.Icons.PASSWORD_OUTLINED, selected_icon=ft.Icons.PASSWORD, label="Security"),
            ft.NavigationBarDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="Account"),
        ]
    elif role == UserRole.PRINCIPAL.value:
        destinations = [
            ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Overview"),
            ft.NavigationBarDestination(icon=ft.Icons.LIST_ALT_OUTLINED, selected_icon=ft.Icons.LIST_ALT, label="Complaints"),
            ft.NavigationBarDestination(icon=ft.Icons.ANALYTICS_OUTLINED, selected_icon=ft.Icons.ANALYTICS, label="Analytics"),
            ft.NavigationBarDestination(icon=ft.Icons.LOCATION_CITY_OUTLINED, selected_icon=ft.Icons.LOCATION_CITY, label="Locations"),
            ft.NavigationBarDestination(icon=ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, selected_icon=ft.Icons.ADMIN_PANEL_SETTINGS, label="Security"),
            ft.NavigationBarDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="Account"),
        ]
    else:
        # Default staff bottom bar without groups
        destinations = [
            ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Home"),
            ft.NavigationBarDestination(icon=ft.Icons.LIST_ALT_OUTLINED, selected_icon=ft.Icons.LIST_ALT, label="Complaints"),
            ft.NavigationBarDestination(icon=ft.Icons.ANALYTICS_OUTLINED, selected_icon=ft.Icons.ANALYTICS, label="Reports"),
            ft.NavigationBarDestination(icon=ft.Icons.MANAGE_ACCOUNTS_OUTLINED, selected_icon=ft.Icons.MANAGE_ACCOUNTS, label="Account"),
        ]

    safe_index = min(selected_index, len(destinations) - 1) if destinations else 0

    return ft.NavigationBar(
        destinations=destinations,
        selected_index=safe_index,
        on_change=lambda e: on_destination_selected(e.control.selected_index),
        bgcolor=colors["surface"],
        indicator_color=ft.Colors.with_opacity(0.14, colors["primary"]),
        elevation=0,
        border=ft.Border.only(top=ft.BorderSide(1, colors["border"])),
        label_behavior=ft.NavigationBarLabelBehavior.ONLY_SHOW_SELECTED,
        animation_duration=220,
    )
