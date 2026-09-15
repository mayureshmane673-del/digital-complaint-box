"""
ui/views package: Application views for Authentication, Student portal, Staff dashboards, and Analytics.
"""

from .auth_view import AuthView
from .student_view import StudentView
from .staff_view import StaffView
from .analytics_view import AnalyticsView

__all__ = ["AuthView", "StudentView", "StaffView", "AnalyticsView"]
