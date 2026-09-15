"""
ui/components/stat_card.py: Metric card with icon and count.
Supports Dark Mode and responsive scaling.
"""

import flet as ft
from ui.state import AppState
from ui.theme import get_theme_colors, COLOR_PRIMARY


def create_stat_card(title: str, value: str, icon: str, color: str, is_dark: bool = None) -> ft.Container:
    """Creates a card showing a summary metric with dark mode support."""
    if is_dark is None:
        is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, color=color, size=28),
                    bgcolor=ft.Colors.with_opacity(0.12, color),
                    border_radius=12,
                    padding=12
                ),
                ft.Column(
                    controls=[
                        ft.Text(title, size=13, color=colors["text_muted"], weight=ft.FontWeight.W_500),
                        ft.Text(value, size=24, color=colors["text"], weight=ft.FontWeight.BOLD),
                    ],
                    spacing=2,
                    alignment=ft.MainAxisAlignment.CENTER
                )
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16
        ),
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=14,
        padding=ft.padding.symmetric(horizontal=18, vertical=12),
    )
