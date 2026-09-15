"""
ui/views/analytics_view.py: Department comparisons, resolution duration metrics, and satisfaction analytics.
"""

from typing import Optional
import flet as ft
from services.analytics_service import AnalyticsService
from ui.theme import get_theme_colors
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

        scrollable_table = ft.Row(
            controls=[table],
            scroll=ft.ScrollMode.AUTO
        )

        return ft.Column(
            controls=[
                ft.Text("Academic Department Performance Comparison", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                ft.Text("Real-time comparative resolution metrics across CSE, AIDS, E&TC, MECH, and Civil departments.", size=13, color=colors["text_muted"]),
                ft.Divider(color=colors["border"]),
                ft.Container(
                    content=scrollable_table,
                    bgcolor=colors["surface"],
                    border=ft.border.all(1, colors["border"]),
                    border_radius=12,
                    padding=16
                )
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            expand=True
        )

