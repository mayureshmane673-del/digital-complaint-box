"""
ui/components/stat_card.py: Metric card with icon and count.
Supports Dark Mode and responsive scaling.
"""

import flet as ft
from ui.state import AppState
from ui.theme import get_theme_colors, COLOR_PRIMARY, get_card_shadow


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

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, color=color, size=24),
                    bgcolor=ft.Colors.with_opacity(0.14, color),
                    border_radius=12,
                    padding=10
                ),
                ft.Column(
                    controls=[
                        ft.Text(title, size=12, color=colors["text_muted"], weight=ft.FontWeight.W_600),
                        ft.Text(value, size=24, color=colors["text"], weight=ft.FontWeight.BOLD),
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
        border_radius=14,
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
        shadow=get_card_shadow(is_dark),
        col=col
    )
