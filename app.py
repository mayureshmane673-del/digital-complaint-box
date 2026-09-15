"""
app.py: Application entry point for Digital Complaint Box System.
Initializes Flet application, theme, responsive layouts, dark mode switching, and view routers.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure root directory is on Python path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import flet as ft
import ui.flet_compat  # Initialize Flet 0.86+ backward compatibility shim
from ui.theme import create_app_theme, COLOR_BG, COLOR_BG_DARK, get_theme_colors, COLOR_PRIMARY
from ui.state import AppState
from ui.views.auth_view import AuthView
from ui.views.student_view import StudentView
from ui.views.staff_view import StaffView
from ui.components.navbar import create_app_bar, create_navigation_rail
from database.supabase_client import check_schema_health
from models.user import UserRole


def main(page: ft.Page):
    page.title = "Digital Complaint Box System"
    is_dark = AppState.is_dark_mode
    page.theme = create_app_theme(is_dark=is_dark)
    page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
    colors = get_theme_colors(is_dark)
    page.bgcolor = colors["bg"]
    page.window_min_width = 360
    page.window_min_height = 540
    page.padding = 0

    AppState.page = page

    # Verify Supabase schema status
    schema_status = check_schema_health()

    current_active_view = [None]
    current_nav_rail = [None]
    current_portal_content = [None]

    def on_logout():
        AppState.clear_user()
        page.appbar = None
        render_auth_view()

    def on_authenticated(user_data: Dict[str, Any], role: str):
        AppState.set_user(user_data, role)
        render_portal_view()

    def render_auth_view():
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)
        page.bgcolor = colors["bg"]
        auth_view = AuthView(page, on_authenticated)
        schema_banner = ft.Container()

        if not schema_status.get("tables_ready", False):
            schema_banner = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, color="#1e3a8a", size=20),
                        ft.Text(
                            "Supabase Setup Note: To ensure full PostgreSQL functionality, execute 'database/migrations/all_migrations.sql' in your Supabase SQL Editor.",
                            size=12,
                            color="#1e3a8a",
                            weight=ft.FontWeight.W_500
                        )
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    wrap=True
                ),
                bgcolor="#dbeafe",
                padding=8
            )

        page.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.ACCOUNT_BALANCE, color=ft.Colors.WHITE),
            leading_width=40,
            title=ft.Text("Digital Complaint Box", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            bgcolor=COLOR_PRIMARY,
            actions=[
                ft.IconButton(
                    icon=ft.Icons.LIGHT_MODE if is_dark else ft.Icons.DARK_MODE,
                    icon_color=ft.Colors.WHITE,
                    tooltip="Switch to Light Mode" if is_dark else "Switch to Dark Mode",
                    on_click=lambda _: AppState.toggle_dark_mode()
                )
            ]
        )
        page.clean()
        page.add(
            ft.Column(
                controls=[
                    schema_banner,
                    auth_view.render()
                ],
                spacing=0,
                expand=True
            )
        )
        page.update()

    def is_compact_screen() -> bool:
        w = page.width or 1000
        return w < 768

    def render_portal_view():
        user = AppState.current_user
        role = AppState.role

        if not user or not role:
            render_auth_view()
            return

        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)
        page.bgcolor = colors["bg"]
        page.theme = create_app_theme(is_dark=is_dark)
        page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT

        user_name = user.get("full_name", user.get("username", "User"))
        dept_code = AppState.department_code

        # Top App Bar with notification and dark mode toggle
        page.appbar = create_app_bar(
            page=page,
            user_name=user_name,
            user_role=role,
            department_code=dept_code,
            user_id=user["id"],
            department_id=AppState.department_id,
            on_logout=on_logout
        )

        # Active View Component
        if role == UserRole.STUDENT.value:
            student_view = StudentView(page, user)
            current_active_view[0] = student_view
        else:
            staff_view = StaffView(page, user, role)
            current_active_view[0] = staff_view

        def on_nav_change(index: int):
            if current_active_view[0]:
                current_active_view[0]._switch_view(index)

        compact = is_compact_screen()
        rail = create_navigation_rail(role, current_active_view[0].selected_tab_index, on_nav_change, compact=compact)
        current_nav_rail[0] = rail

        content_container = ft.Container(
            content=current_active_view[0].render(),
            expand=True,
            padding=16 if compact else 24
        )
        current_portal_content[0] = content_container

        page.clean()
        page.add(
            ft.Row(
                controls=[
                    rail,
                    ft.VerticalDivider(width=1, color=colors["border"]),
                    content_container
                ],
                spacing=0,
                expand=True
            )
        )
        page.update()

    def on_theme_change(*args, **kwargs):
        """Handles seamless dynamic theme switching across the entire app."""
        is_dark = AppState.is_dark_mode
        page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        page.theme = create_app_theme(is_dark=is_dark)
        colors = get_theme_colors(is_dark)
        page.bgcolor = colors["bg"]

        if AppState.current_user:
            render_portal_view()
        else:
            render_auth_view()

    AppState.theme_callback = on_theme_change

    def on_page_resize(e):
        """Adapts navigation rail and spacing dynamically upon window resizing."""
        if AppState.current_user and current_active_view[0]:
            compact = is_compact_screen()
            if current_nav_rail[0]:
                current_nav_rail[0].min_width = 56 if compact else 90
                current_nav_rail[0].label_type = ft.NavigationRailLabelType.NONE if compact else ft.NavigationRailLabelType.ALL
                if current_portal_content[0]:
                    current_portal_content[0].padding = 12 if compact else 24
                page.update()

    page.on_resized = on_page_resize

    # Initial start
    render_auth_view()


# Export ASGI application for production Uvicorn / Render Web deployment
app = ft.run(main=main, export_asgi_app=True)

# Restore ft.app function in case ft.run internal imports shadowed it with the flet.app module
import flet.app as _flet_app_module
ft.app = _flet_app_module.app

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8550))
    host = os.environ.get("HOST", "0.0.0.0")
    if os.environ.get("RENDER") or os.environ.get("USE_UVICORN"):
        import uvicorn
        uvicorn.run(app, host=host, port=port)
    else:
        ft.run(main=main)

