"""
ui/views/analytics_view.py: Department comparisons, resolution duration metrics, and satisfaction analytics.
"""

from typing import Optional
import flet as ft
from services.analytics_service import AnalyticsService
from ui.theme import get_theme_colors, get_card_shadow
from ui.state import AppState
from models.user import UserRole


class AnalyticsView:
    def __init__(self, page: ft.Page, role: str, department_id: Optional[str] = None):
        self.page = page
        self.role = role
        self.department_id = department_id

    def render(self) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

        dept_breakdown = AnalyticsService.get_department_breakdown()

        rows = []
        mobile_cards = []
        for d in dept_breakdown:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(f"{d['code']} - {d['name']}", weight=ft.FontWeight.BOLD, color=colors["text"])),
                        ft.DataCell(ft.Text(str(d["total"]), color=colors["text"])),
                        ft.DataCell(ft.Text(str(d["pending"]), color="#d97706")),
                        ft.DataCell(ft.Text(str(d["in_progress"]), color="#2563eb")),
                        ft.DataCell(ft.Text(str(d["resolved"]), color="#059669", weight=ft.FontWeight.BOLD)),
                        ft.DataCell(ft.Text(str(d["rejected"]), color="#dc2626")),
                        ft.DataCell(ft.Text(str(d["urgent_high"]), color="#dc2626", weight=ft.FontWeight.BOLD)),
                        ft.DataCell(ft.Text(f"{d['avg_resolution_hours']} hrs", color=colors["text"])),
                        ft.DataCell(ft.Text(f"{d['satisfaction_rate']}%", weight=ft.FontWeight.BOLD, color="#0f766e"))
                    ]
                )
            )

            mobile_cards.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(f"{d['code']} — {d['name']}", size=15, weight=ft.FontWeight.BOLD, color=colors["text"], expand=True),
                                    ft.Container(
                                        content=ft.Text(f"{d['satisfaction_rate']}% Satisfied", size=11, weight=ft.FontWeight.BOLD, color="#0f766e"),
                                        bgcolor=ft.Colors.with_opacity(0.12, "#0f766e"),
                                        border_radius=20,
                                        padding=ft.padding.symmetric(horizontal=8, vertical=3)
                                    )
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                            ),
                            ft.Divider(color=colors["border"], height=8),
                            ft.Row(
                                controls=[
                                    ft.Column([ft.Text("Total", size=11, color=colors["text_muted"]), ft.Text(str(d["total"]), size=14, weight=ft.FontWeight.BOLD, color=colors["text"])], expand=True),
                                    ft.Column([ft.Text("Resolved", size=11, color=colors["text_muted"]), ft.Text(str(d["resolved"]), size=14, weight=ft.FontWeight.BOLD, color="#059669")], expand=True),
                                    ft.Column([ft.Text("Pending", size=11, color=colors["text_muted"]), ft.Text(str(d["pending"]), size=14, weight=ft.FontWeight.BOLD, color="#d97706")], expand=True),
                                    ft.Column([ft.Text("Urgent", size=11, color=colors["text_muted"]), ft.Text(str(d["urgent_high"]), size=14, weight=ft.FontWeight.BOLD, color="#dc2626")], expand=True),
                                ]
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text("Avg Res. Time:", size=12, color=colors["text_muted"]),
                                    ft.Text(f"{d['avg_resolution_hours']} hrs", size=12, weight=ft.FontWeight.W_600, color=colors["text"]),
                                ],
                                spacing=6
                            )
                        ],
                        spacing=8
                    ),
                    bgcolor=colors["surface"],
                    border=ft.Border.all(1, colors["border"]),
                    border_radius=12,
                    shadow=get_card_shadow(is_dark),
                    padding=14,
                    margin=ft.margin.only(bottom=10)
                )
            )

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Department", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Total", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Pending", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("In Progress", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Resolved", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Rejected", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Urgent/High", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Avg Res. Time", weight=ft.FontWeight.BOLD, color=colors["text"])),
                ft.DataColumn(ft.Text("Satisfaction", weight=ft.FontWeight.BOLD, color=colors["text"]))
            ],
            rows=rows
        )

        is_mobile = (getattr(self.page, "width", None) or 1200) < 768

        scrollable_table = ft.Container(
            content=ft.Row(
                controls=[table],
                scroll=ft.ScrollMode.AUTO
            ),
            bgcolor=colors["surface"],
            border=ft.border.all(1, colors["border"]),
            border_radius=12,
            padding=16,
            visible=not is_mobile
        )

        mobile_cards_col = ft.Column(
            controls=mobile_cards,
            spacing=8,
            visible=is_mobile
        )

        return ft.Column(
            controls=[
                ft.Text("Academic Department Performance Comparison", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Text("Real-time comparative resolution metrics across CSE, AIDS, E&TC, MECH, and Civil departments.", size=13, color=colors["text_muted"]),
                ft.Divider(color=colors["border"]),
                scrollable_table,
                mobile_cards_col
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            expand=True
        )

