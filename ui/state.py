"""
ui/state.py: Multi-session state, user context, and view routing manager.
Isolates session state across concurrent connections via contextvars while maintaining
seamless backward-compatible class-level property access.
"""

import contextvars
from typing import Optional, Dict, Any, Callable
import flet as ft
from models.user import UserRole

_session_state: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar("DCB_SESSION_STATE", default=None)


class MetaAppState(type):
    def _store(cls) -> Dict[str, Any]:
        s = _session_state.get()
        if s is None:
            s = {
                "current_user": cls._default_user,
                "role": cls._default_role,
                "department_id": cls._default_dept_id,
                "department_name": cls._default_dept_name,
                "department_code": cls._default_dept_code,
                "is_hostel_approved": cls._default_is_hostel_approved,
                "is_dark_mode": cls._default_dark,
                "page": cls._default_page,
                "navigate_callback": cls._default_navigate,
                "theme_callback": cls._default_theme
            }
            _session_state.set(s)
        return s

    @property
    def current_user(cls) -> Optional[Dict[str, Any]]:
        return cls._store().get("current_user")

    @current_user.setter
    def current_user(cls, val):
        cls._store()["current_user"] = val
        cls._default_user = val

    @property
    def role(cls) -> Optional[str]:
        return cls._store().get("role")

    @role.setter
    def role(cls, val):
        cls._store()["role"] = val
        cls._default_role = val

    @property
    def department_id(cls) -> Optional[str]:
        return cls._store().get("department_id")

    @department_id.setter
    def department_id(cls, val):
        cls._store()["department_id"] = val
        cls._default_dept_id = val

    @property
    def department_name(cls) -> Optional[str]:
        return cls._store().get("department_name")

    @department_name.setter
    def department_name(cls, val):
        cls._store()["department_name"] = val
        cls._default_dept_name = val

    @property
    def department_code(cls) -> Optional[str]:
        return cls._store().get("department_code")

    @department_code.setter
    def department_code(cls, val):
        cls._store()["department_code"] = val
        cls._default_dept_code = val

    @property
    def is_hostel_approved(cls) -> bool:
        return bool(cls._store().get("is_hostel_approved", False))

    @is_hostel_approved.setter
    def is_hostel_approved(cls, val: bool):
        cls._store()["is_hostel_approved"] = bool(val)
        cls._default_is_hostel_approved = bool(val)

    @property
    def is_dark_mode(cls) -> bool:
        return bool(cls._store().get("is_dark_mode", False))

    @is_dark_mode.setter
    def is_dark_mode(cls, val: bool):
        cls._store()["is_dark_mode"] = bool(val)
        cls._default_dark = bool(val)

    @property
    def page(cls) -> Optional[ft.Page]:
        return cls._store().get("page")

    @page.setter
    def page(cls, val):
        cls._store()["page"] = val
        cls._default_page = val

    @property
    def navigate_callback(cls) -> Optional[Callable[[str], None]]:
        return cls._store().get("navigate_callback")

    @navigate_callback.setter
    def navigate_callback(cls, val):
        cls._store()["navigate_callback"] = val
        cls._default_navigate = val

    @property
    def theme_callback(cls) -> Optional[Callable[..., None]]:
        return cls._store().get("theme_callback")

    @theme_callback.setter
    def theme_callback(cls, val):
        cls._store()["theme_callback"] = val
        cls._default_theme = val


class AppState(metaclass=MetaAppState):
    _default_user: Optional[Dict[str, Any]] = None
    _default_role: Optional[str] = None
    _default_dept_id: Optional[str] = None
    _default_dept_name: Optional[str] = None
    _default_dept_code: Optional[str] = None
    _default_is_hostel_approved: bool = False
    _default_dark: bool = False
    _default_page: Optional[ft.Page] = None
    _default_navigate: Optional[Callable[[str], None]] = None
    _default_theme: Optional[Callable[..., None]] = None

    @classmethod
    def init_session(cls, page: Optional[ft.Page] = None) -> Dict[str, Any]:
        """Initializes an isolated session state store for this connection."""
        s = {
            "current_user": None,
            "role": None,
            "department_id": None,
            "department_name": None,
            "department_code": None,
            "is_hostel_approved": False,
            "is_dark_mode": False,
            "page": page,
            "navigate_callback": None,
            "theme_callback": None
        }
        _session_state.set(s)
        return s

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
