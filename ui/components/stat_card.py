"""
ui/components/stat_card.py: Metric card with icon and count.
Supports Dark Mode and responsive scaling.
"""

import flet as ft
from ui.state import AppState
from ui.theme import (
    get_theme_colors, get_card_shadow, get_shadow, get_text_style,
    RADII, SPACING, HOVER_SCALE, MOTION_FAST_MS,
)


def create_stat_card(
    title: str,
    value: str,
    icon: str,
    color: str,
    is_dark: bool = None,
    col: dict = None
) -> ft.Container:
    """Creates a modern glassmorphic card showing a summary metric with dark mode and elevation."""
    if is_dark is None:
        is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)

    def on_hover(e):
        hovered = str(getattr(e, "data", "")).lower() == "true"
        e.control.scale = HOVER_SCALE if hovered else 1
        e.control.shadow = get_shadow("lg" if hovered else "md", is_dark)
        try:
            e.control.update()
        except Exception:
            pass

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, color=color, size=24),
                    bgcolor=ft.Colors.with_opacity(0.12, color),
                    border_radius=RADII["md"],
                    padding=SPACING["md"]
                ),
                ft.Column(
                    controls=[
                        ft.Text(title, style=get_text_style("body_small", is_dark, weight=ft.FontWeight.W_600)),
                        ft.Text(value, style=get_text_style("h2", is_dark)),
                    ],
                    spacing=1,
                    alignment=ft.MainAxisAlignment.CENTER,
                    expand=True
                )
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12
        ),
        bgcolor=colors["card_bg"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=RADII["lg"],
        padding=ft.padding.symmetric(horizontal=SPACING["lg"], vertical=SPACING["md"]),
        shadow=get_card_shadow(is_dark),
        col=col,
        scale=1,
        animate=MOTION_FAST_MS,
        on_hover=on_hover,
    )
