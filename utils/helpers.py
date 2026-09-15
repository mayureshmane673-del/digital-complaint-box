"""
utils/helpers.py: Formatting, styling, and helper methods.
"""

from datetime import datetime, date, timezone
from typing import Optional, Any


def format_datetime(dt: Any) -> str:
    """
    Safely formats timestamp/datetime to user-friendly string:
    '05 Sep 2026, 02:30 PM'
    Handles datetime objects, date objects, ISO strings with Z/offsets,
    timestamps, None, and invalid strings without raising AttributeError or ValueError.
    """
    if dt is None:
        return "N/A"
    if isinstance(dt, datetime):
        return dt.strftime("%d %b %Y, %I:%M %p")
    if isinstance(dt, date):
        return dt.strftime("%d %b %Y")
    if isinstance(dt, (int, float)):
        try:
            return datetime.fromtimestamp(dt, timezone.utc).strftime("%d %b %Y, %I:%M %p")
        except Exception:
            return str(dt)
    if isinstance(dt, str):
        s = dt.strip()
        if not s or s.lower() in ("none", "n/a", "null"):
            return "N/A"
        try:
            clean = s.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(clean)
            return parsed.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            for fmt in (
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    parsed = datetime.strptime(s, fmt)
                    return parsed.strftime("%d %b %Y, %I:%M %p" if " " in fmt or "T" in fmt else "%d %b %Y")
                except Exception:
                    pass
            return s
    return str(dt)


def format_file_size(bytes_size: int) -> str:
    """Formats byte count to human readable KB/MB."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.2f} MB"


def get_status_color(status: str) -> str:
    """Returns color hex or Flet color token for complaint status."""
    st = status.lower()
    if st == "pending":
        return "#f59e0b"  # Amber
    elif st == "in progress":
        return "#3b82f6"  # Blue
    elif st == "resolved":
        return "#10b981"  # Emerald Green
    elif st in ("rejected", "invalid", "deleted"):
        return "#ef4444"  # Red
    return "#6b7280"  # Gray


def get_priority_color(priority: str) -> str:
    """Returns color hex or token for complaint priority."""
    p = priority.lower()
    if p == "urgent":
        return "#dc2626"  # Bright Red
    elif p == "high":
        return "#ea580c"  # Orange
    elif p == "medium":
        return "#d97706"  # Amber
    elif p == "low":
        return "#10b981"  # Green
    return "#6b7280"
