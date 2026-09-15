"""
ui/components/navbar.py: Role-aware navigation sidebar and responsive top app bar with Dark Mode toggle.
"""

from typing import Callable, Optional
import flet as ft
from ui.theme import (
    COLOR_PRIMARY, COLOR_PRIMARY_HOVER, COLOR_SURFACE, COLOR_BORDER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_MUTED, get_theme_colors
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
    """Creates top application bar with notification bell, dark mode toggle, and profile badge."""
    unread_count = NotificationService.get_unread_count(user_id, user_role, department_id)
    is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)

    badge_text = ft.Text(str(unread_count), size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
    badge_container = ft.Container(
        content=badge_text,
        bgcolor="#ef4444",
        border_radius=10,
        padding=ft.padding.symmetric(horizontal=5, vertical=1),
        top=6,
        right=6,
        visible=unread_count > 0
    )

    def update_badge(count: int):
        badge_text.value = str(count)
        badge_container.visible = count > 0
        page.update()

    def open_notifications(e):
        show_notification_dialog(page, user_id, user_role, department_id, on_badge_update=update_badge)

    role_badge_text = user_role
    if department_code and user_role in (UserRole.HOD.value, UserRole.COORDINATOR.value):
        role_badge_text = f"{user_role} ({department_code})"

    return ft.AppBar(
        leading=ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=ft.Colors.WHITE),
        leading_width=40,
        title=ft.Row(
            controls=[
                ft.Text("Digital Complaint Box", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Container(
                    content=ft.Text(role_badge_text, size=11, weight=ft.FontWeight.W_600, color="#1e3a8a"),
                    bgcolor="#dbeafe",
                    border_radius=12,
                    padding=ft.padding.symmetric(horizontal=10, vertical=3)
                )
            ],
            spacing=10,
            wrap=True
        ),
        bgcolor=COLOR_PRIMARY,
        actions=[
            # Dark Mode Toggle Button
            ft.IconButton(
                icon=ft.Icons.LIGHT_MODE if is_dark else ft.Icons.DARK_MODE,
                icon_color=ft.Colors.WHITE,
                tooltip="Switch to Light Mode" if is_dark else "Switch to Dark Mode",
                on_click=lambda _: AppState.toggle_dark_mode()
            ),
            # Notification Bell with Badge
            ft.Stack(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.NOTIFICATIONS_OUTLINED,
                        icon_color=ft.Colors.WHITE,
                        tooltip="Notification Center",
                        on_click=open_notifications
                    ),
                    badge_container
                ]
            ),
            ft.Row(
                controls=[
                    ft.CircleAvatar(
                        content=ft.Text(user_name[:1].upper(), color=COLOR_PRIMARY, weight=ft.FontWeight.BOLD),
                        bgcolor="#e2e8f0",
                        radius=16
                    ),
                    ft.Text(user_name, size=13, weight=ft.FontWeight.W_500, color=ft.Colors.WHITE)
                ],
                spacing=8
            ),
            ft.IconButton(
                icon=ft.Icons.LOGOUT,
                icon_color=ft.Colors.WHITE,
                tooltip="Log Out",
                on_click=lambda _: on_logout()
            ),
            ft.Container(width=6)
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

    return ft.NavigationRail(
        selected_index=selected_index,
        label_type=ft.NavigationRailLabelType.NONE if compact else ft.NavigationRailLabelType.ALL,
        min_width=56 if compact else 90,
        min_extended_width=160,
        destinations=destinations,
        on_change=lambda e: on_destination_selected(e.control.selected_index),
        bgcolor=colors["surface"]
    )
