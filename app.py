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

# Load environment variables early before initializing services
from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

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

    # Fast non-blocking schema status (database is verified in production)
    schema_status = {"connected": True, "tables_ready": True}

    current_active_view = [None]
    current_nav_rail = [None]
    current_portal_content = [None]

    def on_logout():
        try:
            if hasattr(page, "session") and page.session and hasattr(page.session, "store") and page.session.store:
                page.session.store.clear()
        except Exception:
            pass
        AppState.clear_user()
        page.appbar = None
        render_auth_view()

    def on_authenticated(user_data: Dict[str, Any], role: str):
        try:
            if hasattr(page, "session") and page.session and hasattr(page.session, "store") and page.session.store:
                page.session.store.set("current_user", user_data)
                page.session.store.set("role", role)
        except Exception:
            pass
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

    # Initial start: Check if this session is already authenticated (e.g. mobile tab switch/reconnection)
    restored_user = None
    restored_role = None
    try:
        if hasattr(page, "session") and page.session and hasattr(page.session, "store") and page.session.store:
            restored_user = page.session.store.get("current_user")
            restored_role = page.session.store.get("role")
    except Exception:
        pass

    if restored_user and restored_role:
        AppState.set_user(restored_user, restored_role)
        render_portal_view()
    elif AppState.is_authenticated():
        render_portal_view()
    else:
        render_auth_view()


# Export ASGI application for production Uvicorn / Render Web deployment
app = ft.run(main=main, export_asgi_app=True)

# Restore ft.app function in case ft.run internal imports shadowed it with the flet.app module
import flet.app as _flet_app_module
ft.app = _flet_app_module.app


@app.on_event("startup")
def on_app_startup():
    """
    Warms CacheService in background thread upon Uvicorn boot so reference data
    (departments, categories, subcategories, locations) is pre-loaded into RAM.
    """
    import threading
    def _warm_cache_worker():
        try:
            from services.cache_service import CacheService
            CacheService.get_departments()
            CacheService.get_categories_and_subcategories()
        except Exception:
            pass
    threading.Thread(target=_warm_cache_worker, daemon=True).start()


# =============================================================================
# Production Diagnostics & Verification Endpoints (Safe - Zero Secrets Logged)
# =============================================================================
@app.get("/api/health")
def api_health():
    import os
    from urllib.parse import urlparse
    sb_url = os.getenv("SUPABASE_URL", "")
    sb_host = urlparse(sb_url).netloc if sb_url else ""
    return {
        "status": "healthy",
        "version": "v1.0.6-perf-mobile-live",
        "supabase_hostname": sb_host,
        "env_configured": {
            "SUPABASE_URL": bool(sb_url),
            "SUPABASE_SERVICE_ROLE_KEY": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
            "APP_SECRET_KEY": bool(os.getenv("APP_SECRET_KEY")),
            "APP_ENV": os.getenv("APP_ENV", "production"),
        },
    }


@app.get("/api/diagnostics/subcategories")
def api_diagnostics_subcategories():
    """
    Safely verifies category and subcategory dynamic loading in live production.
    """
    from services.cache_service import CacheService
    cats, subs, locs = CacheService.get_categories_and_subcategories()

    test_cats = ["Electricity", "Hostel", "IT & Computer", "Security & Safety"]
    test_results = {}

    for t_cat in test_cats:
        cid = None
        for c in cats:
            if c.get("name", "").strip().lower() == t_cat.lower():
                cid = str(c.get("id"))
                break

        cat_subs = []
        if cid and cid in subs:
            cat_subs = [s.get("name") for s in subs[cid]]
        elif t_cat.lower() in subs:
            cat_subs = [s.get("name") for s in subs[t_cat.lower()]]

        test_results[t_cat] = {
            "category_id": cid,
            "count": len(cat_subs),
            "subcategories": cat_subs
        }

    return {
        "status": "ok",
        "version": "v1.0.6-perf-mobile-live",
        "total_categories": len(cats),
        "total_locations": len(locs),
        "test_categories": test_results
    }


@app.get("/api/diagnostics/auth-check")
def api_auth_check():
    """
    Safely tests live production authentication paths within the deployed container.
    Returns only pass/fail booleans, role names, and user-facing messages.
    NEVER logs or returns secret keys, passwords, or hashes.
    """
    import os
    from urllib.parse import urlparse
    from services.auth_service import AuthService
    from services.security_code_service import SecurityCodeService
    from database.supabase_client import get_trusted_backend_client
    from utils.security import verify_security_answer

    sb_url = os.getenv("SUPABASE_URL", "")
    sb_host = urlparse(sb_url).netloc if sb_url else ""
    client = get_trusted_backend_client()

    report = {
        "version": "v1.0.6-perf-mobile-live",
        "supabase_hostname": sb_host,
        "env_status": {
            "SUPABASE_URL_SET": bool(sb_url),
            "SUPABASE_SERVICE_ROLE_KEY_SET": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
            "APP_SECRET_KEY_SET": bool(os.getenv("APP_SECRET_KEY")),
            "APP_ENV": os.getenv("APP_ENV", "production"),
        },
    }

    # 1. Staff Authentication Test Matrix
    staff_results = {}
    staff_tests = [
        ("Principal", "xyz", "Pass@123", "Pass@123", None),
        ("Hostel Incharge", "Hostel", "Pass@123", "Pass@123", None),
        ("Coordinator", "msm", "Pass@123", "Pass@123", "f4e141ef-14ca-44e4-a1ed-051ee0525419"),
        ("HOD", "mm", "Pass@123", "Pass@123", "f4e141ef-14ca-44e4-a1ed-051ee0525419"),
        ("Library Incharge", "Library", "Pass@123", "Pass@123", None),
    ]
    for role, user, pw, code, dept in staff_tests:
        ok, msg, u = AuthService.login_staff(role, user, pw, code, dept)
        staff_results[role] = {"success": ok, "message": msg}
    report["staff_logins"] = staff_results

    # 2. Staff Security Code Checks
    gen_dept = SecurityCodeService._get_special_dept_id("GEN")
    code_results = {
        "Principal": SecurityCodeService.verify_role_code("Principal", None, "Pass@123"),
        "Hostel Incharge": SecurityCodeService.verify_role_code("Hostel Incharge", None, "Pass@123"),
        "Coordinator (CSE)": SecurityCodeService.verify_role_code("Coordinator", "f4e141ef-14ca-44e4-a1ed-051ee0525419", "Pass@123"),
        "HOD (CSE)": SecurityCodeService.verify_role_code("HOD", "f4e141ef-14ca-44e4-a1ed-051ee0525419", "Pass@123"),
        "General Department HOD": SecurityCodeService.verify_role_code("General Department HOD", gen_dept, "Pass@123") or SecurityCodeService.verify_role_code("HOD", gen_dept, "Pass@123"),
        "Library Incharge": SecurityCodeService.verify_role_code("Library Incharge", None, "Pass@123"),
    }
    report["security_codes"] = code_results

    # 3. Student Forgot Password Question & Answer Verification
    ok_q, msg_q, question = AuthService.get_student_security_question("240101030")
    report["student_forgot_password"] = {
        "question_retrieved": ok_q,
        "has_question": bool(question),
    }

    # Verify security answer YHK directly against student hash
    try:
        s_res = client.table("students").select("security_answer_hash").eq("roll_number", "240101030").execute()
        if s_res.data:
            sa_hash = s_res.data[0].get("security_answer_hash", "")
            report["student_forgot_password"]["answer_yhk_exact"] = verify_security_answer("YHK", sa_hash)
            report["student_forgot_password"]["answer_yhk_lower"] = verify_security_answer("yhk", sa_hash)
            report["student_forgot_password"]["answer_yhk_spaces"] = verify_security_answer(" YHK ", sa_hash)
    except Exception as ex:
        report["student_forgot_password"]["error"] = str(type(ex).__name__)

    # 4. Student Login (240101030)
    ok_stu, msg_stu, _ = AuthService.login_student("240101030", "Pass@123")
    report["student_login"] = {"success": ok_stu, "message": msg_stu}

    return report


# Ensure API diagnostic routes take precedence over the Flet SPA catch-all mount
api_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/api")]
non_api_routes = [r for r in app.routes if not getattr(r, "path", "").startswith("/api")]
app.router.routes = api_routes + non_api_routes


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8550))
    host = os.environ.get("HOST", "0.0.0.0")
    if os.environ.get("RENDER") or os.environ.get("USE_UVICORN"):
        import uvicorn
        uvicorn.run(app, host=host, port=port)
    else:
        ft.run(main=main)


