"""
ui/theme.py: Modern college portal design system and Material 3 theme configuration.
"""

import flet as ft
import ui.flet_compat

# Color Palette (Light Theme Defaults)
COLOR_PRIMARY = "#1e3a8a"       # Deep Navy
COLOR_PRIMARY_HOVER = "#172554"
COLOR_PRIMARY_LIGHT = "#3b82f6" # Accent Blue
COLOR_SECONDARY = "#0f766e"     # Teal
COLOR_BG = "#f8fafc"            # Slate light background
COLOR_SURFACE = "#ffffff"       # Card / Container background
COLOR_SURFACE_VARIANT = "#f1f5f9"
COLOR_TEXT_PRIMARY = "#0f172a"  # Slate 900
COLOR_TEXT_MUTED = "#64748b"    # Slate 500
COLOR_BORDER = "#e2e8f0"        # Slate 200

# Dark Theme Colors
COLOR_BG_DARK = "#0f172a"            # Slate 900
COLOR_SURFACE_DARK = "#1e293b"       # Slate 800
COLOR_SURFACE_VARIANT_DARK = "#334155" # Slate 700
COLOR_TEXT_PRIMARY_DARK = "#f8fafc"  # Slate 50
COLOR_TEXT_MUTED_DARK = "#94a3b8"    # Slate 400
COLOR_BORDER_DARK = "#334155"        # Slate 700
COLOR_PRIMARY_DARK = "#3b82f6"       # Lighter Blue for Dark Mode Contrast

# Status Colors
STATUS_COLORS = {
    "Pending": "#d97706",       # Amber 600
    "In Progress": "#2563eb",   # Blue 600
    "Resolved": "#059669",      # Emerald 600
    "Rejected": "#dc2626",      # Red 600
    "Deleted": "#991b1b"
}

# Priority Colors
PRIORITY_COLORS = {
    "Low": "#059669",           # Emerald
    "Medium": "#d97706",        # Amber
    "High": "#ea580c",          # Orange
    "Urgent": "#dc2626"         # Crimson Red
}


def get_theme_colors(is_dark: bool = False):
    """Returns dynamic color dictionary based on active theme mode."""
    if is_dark:
        return {
            "bg": COLOR_BG_DARK,
            "surface": COLOR_SURFACE_DARK,
            "surface_variant": COLOR_SURFACE_VARIANT_DARK,
            "text": COLOR_TEXT_PRIMARY_DARK,
            "text_muted": COLOR_TEXT_MUTED_DARK,
            "border": COLOR_BORDER_DARK,
            "primary": COLOR_PRIMARY_DARK,
            "primary_hover": "#60a5fa",
            "is_dark": True
        }
    return {
        "bg": COLOR_BG,
        "surface": COLOR_SURFACE,
        "surface_variant": COLOR_SURFACE_VARIANT,
        "text": COLOR_TEXT_PRIMARY,
        "text_muted": COLOR_TEXT_MUTED,
        "border": COLOR_BORDER,
        "primary": COLOR_PRIMARY,
        "primary_hover": COLOR_PRIMARY_HOVER,
        "is_dark": False
    }


STATUS_BADGE_STYLES = {
    "Pending": {
        "light_bg": "#fef3c7", "light_text": "#b45309",
        "dark_bg": "#451a03", "dark_text": "#fde68a"
    },
    "In Progress": {
        "light_bg": "#dbeafe", "light_text": "#1d4ed8",
        "dark_bg": "#172554", "dark_text": "#93c5fd"
    },
    "Resolved": {
        "light_bg": "#d1fae5", "light_text": "#047857",
        "dark_bg": "#064e3b", "dark_text": "#a7f3d0"
    },
    "Rejected": {
        "light_bg": "#ffe4e6", "light_text": "#be123c",
        "dark_bg": "#4c0519", "dark_text": "#fecdd3"
    },
    "Deleted": {
        "light_bg": "#fee2e2", "light_text": "#991b1b",
        "dark_bg": "#450a0a", "dark_text": "#fca5a5"
    }
}


def create_status_badge(status: str, is_dark: bool = False) -> ft.Container:
    """Renders a soft, modern pill status badge with crisp typography."""
    style = STATUS_BADGE_STYLES.get(status, {
        "light_bg": "#f1f5f9", "light_text": "#475569",
        "dark_bg": "#334155", "dark_text": "#cbd5e1"
    })
    bg_color = style["dark_bg"] if is_dark else style["light_bg"]
    text_color = style["dark_text"] if is_dark else style["light_text"]

    return ft.Container(
        content=ft.Text(status, size=11, weight=ft.FontWeight.W_600, color=text_color),
        bgcolor=bg_color,
        border_radius=12,
        padding=ft.padding.symmetric(horizontal=10, vertical=4)
    )


def create_priority_badge(priority: str, is_dark: bool = False) -> ft.Container:
    """Renders a modern pill priority badge."""
    p_color = PRIORITY_COLORS.get(priority, "#64748b")
    return ft.Container(
        content=ft.Text(priority, size=11, weight=ft.FontWeight.W_600, color=p_color),
        bgcolor=ft.Colors.with_opacity(0.12 if not is_dark else 0.22, p_color),
        border_radius=12,
        padding=ft.padding.symmetric(horizontal=10, vertical=4)
    )


def create_app_theme(is_dark: bool = False) -> ft.Theme:
    """Configures application-wide Material 3 theme with light/dark support."""
    return ft.Theme(
        color_scheme_seed=COLOR_PRIMARY_DARK if is_dark else COLOR_PRIMARY,
        visual_density=ft.VisualDensity.COMFORTABLE,
        font_family="Segoe UI, Roboto, sans-serif",
        use_material3=True
    )
