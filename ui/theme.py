"""Shared visual tokens and reusable Flet controls for the college portal."""

from typing import Any, Optional, Dict
import flet as ft
import ui.flet_compat

# Academic blue palette with quiet surfaces and readable navy text.
COLOR_PRIMARY = "#0B5CAD"
COLOR_PRIMARY_HOVER = "#084B91"
COLOR_PRIMARY_LIGHT = "#3B82F6"
COLOR_ACCENT = "#F2A33A"
COLOR_SECONDARY = "#1F9D8B"
COLOR_BG = "#F4F6FA"
COLOR_SURFACE = "#FFFFFF"
COLOR_SURFACE_VARIANT = "#EEF3F9"
COLOR_TEXT_PRIMARY = "#12263F"
COLOR_TEXT_MUTED = "#60738A"
COLOR_BORDER = "#DCE3EE"
COLOR_SUCCESS = "#16865D"
COLOR_WARNING = "#B96A08"
COLOR_DANGER = "#C33D4B"
COLOR_INFO = "#1769AA"

# Dark Theme Colors
COLOR_BG_DARK = "#101A2B"
COLOR_SURFACE_DARK = "#17243A"
COLOR_SURFACE_VARIANT_DARK = "#22334D"
COLOR_TEXT_PRIMARY_DARK = "#F3F7FC"
COLOR_TEXT_MUTED_DARK = "#A8B7CA"
COLOR_BORDER_DARK = "#334761"
COLOR_PRIMARY_DARK = "#66A9F5"

# Reusable design-system tokens. Kept as plain values so view modules can
# consume them without depending on a specific page layout.
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32, "3xl": 48}
RADII = {"sm": 8, "md": 12, "lg": 16, "xl": 20, "pill": 999}
FONT_FAMILY = "Segoe UI"
FONT_FAMILY_FALLBACK = ("Arial", "sans-serif")
BREAKPOINT_MOBILE = 600
BREAKPOINT_TABLET = 1024
DIALOG_MAX_WIDTH = 960
DIALOG_MAX_HEIGHT = 760

TEXT_STYLES = {
    "display": {"size": 36, "weight": ft.FontWeight.BOLD},
    "h1": {"size": 30, "weight": ft.FontWeight.BOLD},
    "h2": {"size": 24, "weight": ft.FontWeight.BOLD},
    "h3": {"size": 20, "weight": ft.FontWeight.W_600},
    "title": {"size": 18, "weight": ft.FontWeight.W_600},
    "body": {"size": 14, "weight": ft.FontWeight.NORMAL},
    "body_small": {"size": 12, "weight": ft.FontWeight.NORMAL},
    "label": {"size": 13, "weight": ft.FontWeight.W_600},
    "caption": {"size": 11, "weight": ft.FontWeight.NORMAL},
}

SHADOW_STYLES = {
    "none": {"blur_radius": 0, "opacity": 0.0, "offset_y": 0},
    "sm": {"blur_radius": 8, "opacity": 0.05, "offset_y": 2},
    "md": {"blur_radius": 14, "opacity": 0.08, "offset_y": 4},
    "lg": {"blur_radius": 24, "opacity": 0.12, "offset_y": 8},
}
CHART_PALETTE = (
    "#1769AA", "#6C63C7", "#1F9D8B", "#D96B1D",
    "#16865D", "#C33D4B", "#A8559E", "#5C6F82",
)
DEPARTMENT_COLORS = {
    "CSE": "#1769AA",
    "AIDS": "#6C63C7",
    "E&TC": "#1F9D8B",
    "MECH": "#D96B1D",
    "CIVIL": "#16865D",
}
MOTION_FAST_MS = 140
MOTION_NORMAL_MS = 220
HOVER_SCALE = 1.015

# Status Colors
STATUS_COLORS = {
    "Pending": COLOR_WARNING,
    "In Progress": COLOR_INFO,
    "Resolved": COLOR_SUCCESS,
    "Rejected": COLOR_DANGER,
    "Deleted": "#991B1B"
}

# Priority Colors
PRIORITY_COLORS = {
    "Low": COLOR_SUCCESS,
    "Medium": COLOR_WARNING,
    "High": "#D96B1D",
    "Urgent": COLOR_DANGER
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
            "accent": "#F5B95F",
            "card_bg": COLOR_SURFACE_DARK,
            "primary_light": COLOR_PRIMARY_DARK,
            "secondary": "#4CC3AD",
            "success": "#4CCB95",
            "warning": "#F5B95F",
            "danger": "#F07C86",
            "info": "#70B6F5",
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
        "accent": COLOR_ACCENT,
        "card_bg": COLOR_SURFACE,
        "primary_light": COLOR_PRIMARY_LIGHT,
        "secondary": COLOR_SECONDARY,
        "success": COLOR_SUCCESS,
        "warning": COLOR_WARNING,
        "danger": COLOR_DANGER,
        "info": COLOR_INFO,
        "is_dark": False
    }


def get_responsive_layout(width: Optional[float]) -> str:
    """Return ``mobile``, ``tablet`` or ``desktop`` for a viewport width."""
    if width is None or width < BREAKPOINT_MOBILE:
        return "mobile"
    if width <= BREAKPOINT_TABLET:
        return "tablet"
    return "desktop"


def get_spacing(size: str = "md") -> int:
    """Look up a spacing token, defaulting to medium spacing."""
    return SPACING.get(size, SPACING["md"])


def get_radius(size: str = "md") -> int:
    """Look up a corner-radius token, defaulting to the medium radius."""
    return RADII.get(size, RADII["md"])


def get_text_style(style: str = "body", is_dark: bool = False, **overrides: Any) -> ft.TextStyle:
    """Build a reusable text style from a named type token."""
    colors = get_theme_colors(is_dark)
    style_values = dict(TEXT_STYLES.get(style, TEXT_STYLES["body"]))
    color = colors["text_muted"] if style in ("body_small", "caption") else colors["text"]
    style_values.update({"color": color, "font_family": FONT_FAMILY})
    style_values.update(overrides)
    return ft.TextStyle(**style_values)


def get_button_style(
    is_dark: bool = False,
    variant: str = "primary",
    size: str = "md",
) -> ft.ButtonStyle:
    """Return shared styles for primary, secondary, outline and text buttons."""
    colors = get_theme_colors(is_dark)
    variants = {
        "primary": (colors["primary"], "#FFFFFF", None),
        "secondary": (colors["secondary"], "#FFFFFF", None),
        "danger": (colors["danger"], "#FFFFFF", None),
        "danger_outline": (colors["surface"], colors["danger"], colors["danger"]),
        "outline": (colors["surface"], colors["primary"], colors["border"]),
        "text": (None, colors["primary"], None),
    }
    bgcolor, text_color, border_color = variants.get(variant, variants["primary"])
    padding = {"sm": (12, 7), "md": (18, 11), "lg": (22, 14)}.get(size, (18, 11))
    side = ft.BorderSide(1, border_color) if border_color else None
    return ft.ButtonStyle(
        bgcolor=bgcolor,
        color=text_color,
        side=side,
        shape=ft.RoundedRectangleBorder(radius=RADII["md"]),
        padding=ft.padding.symmetric(horizontal=padding[0], vertical=padding[1]),
        elevation=0,
    )


def get_input_style(is_dark: bool = False) -> Dict[str, Any]:
    """Return visual TextField arguments shared by form controls."""
    colors = get_theme_colors(is_dark)
    return {
        "border": ft.InputBorder.OUTLINE,
        "border_radius": RADII["md"],
        "border_color": colors["border"],
        "focused_border_color": colors["primary"],
        "cursor_color": colors["primary"],
        "filled": True,
        "fill_color": colors["surface"],
        "content_padding": ft.padding.symmetric(horizontal=14, vertical=12),
        "text_size": 14,
        "text_style": get_text_style("body", is_dark),
        "hint_style": get_text_style("body", is_dark, color=colors["text_muted"]),
        "label_style": get_text_style("body_small", is_dark, color=colors["text_muted"]),
    }


def get_shadow(level: str = "md", is_dark: bool = False) -> list:
    """Return a standard elevation shadow from the named shadow token."""
    values = SHADOW_STYLES.get(level, SHADOW_STYLES["md"])
    if level == "none":
        return []
    shadow_color = "#000000" if is_dark else COLOR_TEXT_PRIMARY
    return [ft.BoxShadow(
        spread_radius=0,
        blur_radius=values["blur_radius"],
        color=ft.Colors.with_opacity(values["opacity"], shadow_color),
        offset=ft.Offset(0, values["offset_y"]),
    )]


def get_chart_palette() -> tuple:
    """Return the shared categorical chart colors."""
    return CHART_PALETTE


def get_department_color(code: str) -> str:
    """Return a stable chart accent for a recognized department code."""
    return DEPARTMENT_COLORS.get(str(code or "").upper(), COLOR_PRIMARY)


def get_card_shadow(is_dark: bool = False) -> list:
    """Backward-compatible card elevation helper."""
    return get_shadow("md", is_dark)


def create_glass_card(
    content: ft.Control,
    padding: Any = 16,
    border_radius: int = 16,
    is_dark: bool = False,
    border_color: str = None,
    bgcolor: str = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    col: Optional[Dict[str, int]] = None,
    expand: bool = False,
    margin: Any = None,
    on_click: Any = None
) -> ft.Container:
    """Creates a modern glassmorphic card container with soft border and subtle shadow."""
    colors = get_theme_colors(is_dark)
    bg = bgcolor or colors["card_bg"]
    border_c = border_color or colors["border"]

    return ft.Container(
        content=content,
        bgcolor=bg,
        border=ft.Border.all(1, border_c),
        border_radius=border_radius,
        padding=padding,
        margin=margin,
        shadow=get_card_shadow(is_dark),
        width=width,
        height=height,
        col=col,
        expand=expand,
        on_click=on_click
    )


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


def StatusBadge(status: str, is_dark: bool = False) -> ft.Container:
    """Render a compact, readable status pill in either color mode."""
    style = STATUS_BADGE_STYLES.get(status, {
        "light_bg": "#f1f5f9", "light_text": "#475569",
        "dark_bg": "#334155", "dark_text": "#cbd5e1"
    })
    bg_color = style["dark_bg"] if is_dark else style["light_bg"]
    text_color = style["dark_text"] if is_dark else style["light_text"]

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    width=6, height=6,
                    border_radius=3,
                    bgcolor=text_color
                ),
                ft.Text(status, size=11, weight=ft.FontWeight.W_600, color=text_color),
            ],
            spacing=5,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
        bgcolor=bg_color,
        border_radius=RADII["pill"],
        padding=ft.padding.symmetric(horizontal=10, vertical=5)
    )


def PriorityBadge(priority: str, is_dark: bool = False) -> ft.Container:
    """Render a compact priority pill with contrast-safe dark-mode text."""
    light_color = PRIORITY_COLORS.get(priority, COLOR_TEXT_MUTED)
    dark_colors = {
        "Low": "#65D6A5",
        "Medium": "#F5C45E",
        "High": "#FFA064",
        "Urgent": "#FF858D",
    }
    p_color = dark_colors.get(priority, "#C0CDDC") if is_dark else light_color
    bg_color = ft.Colors.with_opacity(0.22 if is_dark else 0.12, p_color)
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    width=6, height=6,
                    border_radius=3,
                    bgcolor=p_color
                ),
                ft.Text(priority, size=11, weight=ft.FontWeight.W_600, color=p_color),
            ],
            spacing=5,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
        bgcolor=bg_color,
        border_radius=RADII["pill"],
        padding=ft.padding.symmetric(horizontal=10, vertical=5)
    )


def create_status_badge(status: str, is_dark: bool = False) -> ft.Container:
    """Backward-compatible alias for :func:`StatusBadge`."""
    return StatusBadge(status, is_dark)


def create_priority_badge(priority: str, is_dark: bool = False) -> ft.Container:
    """Backward-compatible alias for :func:`PriorityBadge`."""
    return PriorityBadge(priority, is_dark)


def SectionHeader(
    title: str,
    subtitle: Optional[str] = None,
    icon: Any = None,
    action: Optional[ft.Control] = None,
    is_dark: bool = False,
) -> ft.Row:
    """Create a consistent page or card heading, with optional action control."""
    colors = get_theme_colors(is_dark)
    heading_controls = []
    if icon is not None:
        heading_controls.append(ft.Icon(icon, size=20, color=colors["primary"]))
    heading_controls.append(ft.Text(title, style=get_text_style("h3", is_dark), expand=True))
    heading = ft.Column(
        controls=[
            ft.Row(controls=heading_controls, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            *([ft.Text(subtitle, style=get_text_style("body_small", is_dark))] if subtitle else []),
        ],
        spacing=4,
        tight=True,
        expand=True,
    )
    controls = [heading]
    if action is not None:
        controls.append(action)
    return ft.Row(
        controls=controls,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=12,
    )


def EmptyState(
    title: str,
    message: str,
    icon: Any = ft.Icons.INBOX_OUTLINED,
    action: Optional[ft.Control] = None,
    is_dark: bool = False,
) -> ft.Container:
    """Create a centered empty-state panel with optional next action."""
    colors = get_theme_colors(is_dark)
    controls = [
        ft.Icon(icon, size=36, color=colors["text_muted"]),
        ft.Text(title, style=get_text_style("title", is_dark), text_align=ft.TextAlign.CENTER),
        ft.Text(
            message,
            style=get_text_style("body_small", is_dark),
            text_align=ft.TextAlign.CENTER,
        ),
    ]
    if action is not None:
        controls.append(action)
    return ft.Container(
        content=ft.Column(
            controls=controls,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
            tight=True,
        ),
        padding=SPACING["2xl"],
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=RADII["lg"],
        alignment=ft.Alignment(0, 0),
    )


def PageContainer(
    content: ft.Control,
    padding: Any = None,
    max_width: Optional[int] = None,
    is_dark: bool = False,
    expand: bool = True,
    margin: Any = None,
) -> ft.Container:
    """Wrap page content in the shared surface spacing and optional width."""
    colors = get_theme_colors(is_dark)
    return ft.Container(
        content=content,
        padding=padding if padding is not None else SPACING["xl"],
        margin=margin,
        width=max_width,
        expand=expand,
        bgcolor=colors["bg"],
    )


def create_app_theme(is_dark: bool = False) -> ft.Theme:
    """Configures application-wide Material 3 theme with light/dark support."""
    return ft.Theme(
        color_scheme_seed=COLOR_PRIMARY_DARK if is_dark else COLOR_PRIMARY,
        visual_density=ft.VisualDensity.COMFORTABLE,
        font_family=FONT_FAMILY,
        use_material3=True
    )
