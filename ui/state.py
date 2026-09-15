"""
ui/state.py: Global session state, user context, and view routing manager.
"""

from typing import Optional, Dict, Any, Callable
import flet as ft
from models.user import UserRole


class AppState:
    current_user: Optional[Dict[str, Any]] = None
    role: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    department_code: Optional[str] = None
    is_hostel_approved: bool = False
    is_dark_mode: bool = False
    page: Optional[ft.Page] = None
    navigate_callback: Optional[Callable[[str], None]] = None
    theme_callback: Optional[Callable[[bool], None]] = None

    @classmethod
    def toggle_dark_mode(cls):
        cls.is_dark_mode = not cls.is_dark_mode
        if cls.theme_callback:
            try:
                cls.theme_callback(cls.is_dark_mode)
            except TypeError:
                cls.theme_callback()

    @classmethod
    def set_user(cls, user_data: Dict[str, Any], role: str):
        cls.current_user = user_data
        cls.role = role
        cls.department_id = user_data.get("department_id")
        
        dept_info = user_data.get("departments")
        if isinstance(dept_info, dict):
            cls.department_code = dept_info.get("code")
            cls.department_name = dept_info.get("name")
        else:
            cls.department_code = user_data.get("department_code")
            cls.department_name = user_data.get("department_name")

        cls.is_hostel_approved = bool(user_data.get("is_hostel_approved", False))

    @classmethod
    def clear_user(cls):
        cls.current_user = None
        cls.role = None
        cls.department_id = None
        cls.department_name = None
        cls.department_code = None
        cls.is_hostel_approved = False

    @classmethod
    def is_authenticated(cls) -> bool:
        return cls.current_user is not None and cls.role is not None

    @classmethod
    def navigate(cls, route: str):
        if cls.navigate_callback:
            cls.navigate_callback(route)
