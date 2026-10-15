"""
ui/views/analytics_view.py: Department comparisons, resolution duration metrics, and satisfaction analytics.
"""

from typing import Optional
import logging
import time
import flet as ft
from services.analytics_service import AnalyticsService
from ui.theme import (
    get_theme_colors, get_card_shadow, get_responsive_layout, SectionHeader,
    PageContainer, EmptyState, SPACING, RADII,
)
from ui.components.stat_card import create_stat_card
from ui.state import AppState
from models.user import UserRole

logger = logging.getLogger(__name__)


class AnalyticsView:
    def __init__(self, page: ft.Page, role: str, department_id: Optional[str] = None):
        self.page = page
        self.role = role
        self.department_id = department_id
        self._loading = False

    def render(self) -> ft.Control:
        colors = get_theme_colors(AppState.is_dark_mode)
        holder = PageContainer(
            content=ft.Row(
                controls=[ft.ProgressRing(width=22, height=22, stroke_width=2, color=colors["primary"]), ft.Text("Loading analytics and feedback…", color=colors["text_muted"])],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=10,
            ),
            padding=SPACING["lg"],
            is_dark=AppState.is_dark_mode,
            expand=True,
        )
        self._load_into(holder)
        return holder

    def _load_into(self, holder: ft.Container):
        if self._loading:
            return
        self._loading = True

        def load_analytics():
            started_at = time.perf_counter()
            try:
                from concurrent.futures import ThreadPoolExecutor
                from services.feedback_service import FeedbackService

                with ThreadPoolExecutor(max_workers=2) as executor:
                    department_future = executor.submit(AnalyticsService.get_department_breakdown)
                    feedback_future = executor.submit(FeedbackService.get_feedback_for_scope, self.role, self.department_id)
                    dept_breakdown = department_future.result()
                    feedbacks = feedback_future.result()

                holder.content = self._render_loaded_view(dept_breakdown, feedbacks)
                logger.info("Analytics view data loaded in %.3fs", time.perf_counter() - started_at)
            except Exception as exc:
                logger.warning("Analytics view data unavailable (%s)", type(exc).__name__)
                colors = get_theme_colors(AppState.is_dark_mode)
                holder.content = ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.ERROR_OUTLINE, color="#dc2626"),
                        ft.Text("Analytics could not be loaded. Check your connection and retry.", color=colors["text_muted"], text_align=ft.TextAlign.CENTER),
                        ft.ElevatedButton("Retry", icon=ft.Icons.REFRESH, on_click=lambda _: self._load_into(holder)),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                    expand=True,
                )
            finally:
                self._loading = False
                try:
                    self.page.update()
                except Exception:
                    pass

        self.page.run_thread(load_analytics)

    def _render_loaded_view(self, dept_breakdown, feedbacks) -> ft.Control:
        is_dark = AppState.is_dark_mode
        colors = get_theme_colors(is_dark)

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

        viewport_width = getattr(self.page, "width", None)
        layout = get_responsive_layout(viewport_width if isinstance(viewport_width, (int, float)) else None)
        is_mobile = layout != "desktop"

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

        # Department-Scoped Student Feedback Reviews Section
        feedback_cards = []
        for fb in feedbacks:
            cid = fb.get("complaint_id")
            comp = fb.get("complaints") or {}
            c_title = comp.get("title") or "—"
            cat_obj = comp.get("categories")
            cat_name = cat_obj.get("name") if isinstance(cat_obj, dict) else ""
            dept_obj = comp.get("departments")
            dept_name = dept_obj.get("name") if isinstance(dept_obj, dict) else ""
            r = fb.get("rating", 5)
            c_comm = fb.get("comment") or "No written feedback provided."
            fb_date = (fb.get("created_at") or "")[:10] or "—"
            res_date = (comp.get("resolved_at") or "")[:10] or "—"
            remarks = comp.get("resolution_remarks") or ""
            stars = "★" * r + "☆" * (5 - r)

            feedback_cards.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(f"#{cid} — {c_title[:50]}", size=14, weight=ft.FontWeight.BOLD, color=colors["text"], expand=True),
                                    ft.Container(
                                        content=ft.Text(f"{stars} ({r}/5)", size=12, weight=ft.FontWeight.BOLD, color="#f59e0b"),
                                        bgcolor=ft.Colors.with_opacity(0.12, "#f59e0b"),
                                        border_radius=12,
                                        padding=ft.padding.symmetric(horizontal=8, vertical=3)
                                    )
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                wrap=True
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text(cat_name, size=11, color=colors["text_muted"]) if cat_name else ft.Container(),
                                    ft.Text(" · " if cat_name else "", size=11, color=colors["text_muted"]) if cat_name else ft.Container(),
                                    ft.Text(dept_name, size=11, color=colors["text_muted"]) if dept_name else ft.Container(),
                                    ft.Text(" · " if dept_name else "", size=11, color=colors["text_muted"]) if dept_name else ft.Container(),
                                    ft.Text(f"Feedback: {fb_date}", size=11, color=colors["text_muted"]),
                                    ft.Text(f" · Resolved: {res_date}", size=11, color=colors["text_muted"]) if res_date != "—" else ft.Container()
                                ],
                                spacing=0,
                                wrap=True
                            ),
                            ft.Container(
                                content=ft.Column(
                                    controls=[
                                        ft.Text("Student Feedback:", size=11, weight=ft.FontWeight.W_600, color=colors["text_muted"]),
                                        ft.Text(f'"{c_comm}"', size=12, color=colors["text"], italic=True)
                                    ],
                                    spacing=2
                                ),
                                bgcolor=colors.get("surface_variant", "#f8fafc"),
                                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                border_radius=8
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text("Resolution Note:", size=11, weight=ft.FontWeight.W_600, color=colors["text_muted"]),
                                    ft.Text(remarks, size=11, color=colors["text_muted"], expand=True)
                                ],
                                spacing=4
                            ) if remarks else ft.Container()
                        ],
                        spacing=6
                    ),
                    bgcolor=colors["surface"],
                    border=ft.Border.all(1, colors["border"]),
                    border_radius=10,
                    shadow=get_card_shadow(is_dark),
                    padding=12,
                    margin=ft.margin.only(bottom=8)
                )
            )

        if not feedback_cards:
            feedback_cards.append(
                EmptyState(
                    "No feedback yet",
                    "Student feedback will appear here after resolved complaints are rated.",
                    icon=ft.Icons.RATE_REVIEW_OUTLINED,
                    is_dark=is_dark,
                )
            )

        feedback_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text("Department Resolution Feedback", size=18, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                    ft.Text("Student ratings and comments on resolved complaints belonging to your department.", size=12, color=colors["text_muted"])
                                ],
                                spacing=2
                            ),
                            ft.Container(
                                content=ft.Text(f"{len(feedbacks)} Reviews", size=11, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                                bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                                border_radius=12,
                                padding=ft.padding.symmetric(horizontal=10, vertical=4)
                            )
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        wrap=True
                    ),
                    ft.Divider(color=colors["border"]),
                    ft.Column(controls=feedback_cards, spacing=6)
                ],
                spacing=8
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            shadow=get_card_shadow(is_dark),
            padding=16,
            margin=ft.margin.only(top=8)
        )

        total_complaints = sum(int(d.get("total") or 0) for d in dept_breakdown)
        total_resolved = sum(int(d.get("resolved") or 0) for d in dept_breakdown)
        total_pending = sum(int(d.get("pending") or 0) for d in dept_breakdown)
        average_resolution = (
            sum(float(d.get("avg_resolution_hours") or 0) for d in dept_breakdown) / len(dept_breakdown)
            if dept_breakdown else 0
        )
        average_satisfaction = (
            sum(float(d.get("satisfaction_rate") or 0) for d in dept_breakdown) / len(dept_breakdown)
            if dept_breakdown else 0
        )
        summary_cards = ft.ResponsiveRow(
            controls=[
                create_stat_card("Total complaints", str(total_complaints), ft.Icons.FOLDER_OUTLINED, colors["primary"], is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 3}),
                create_stat_card("Resolved", str(total_resolved), ft.Icons.TASK_ALT, colors["success"], is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 3}),
                create_stat_card("Pending", str(total_pending), ft.Icons.HOURGLASS_TOP, colors["warning"], is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 3}),
                create_stat_card("Avg. satisfaction", f"{average_satisfaction:.1f}%", ft.Icons.THUMB_UP_ALT, colors["secondary"], is_dark=is_dark, col={"xs": 12, "sm": 6, "md": 3}),
            ],
            spacing=SPACING["md"],
            run_spacing=SPACING["md"],
        )
        metrics_strip = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SCHEDULE, color=colors["primary"]),
                    ft.Text("Average resolution time", color=colors["text_muted"], expand=True),
                    ft.Text(f"{average_resolution:.1f} hours", color=colors["text"], weight=ft.FontWeight.BOLD),
                ],
                wrap=True,
                spacing=SPACING["sm"],
            ),
            padding=SPACING["md"],
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=RADII["md"],
        )
        return PageContainer(
            content=ft.Column(
                controls=[
                    SectionHeader(
                        "Department performance",
                        "Complaint resolution and satisfaction across departments.",
                        icon=ft.Icons.INSIGHTS,
                        is_dark=is_dark,
                    ),
                    summary_cards,
                    metrics_strip,
                    SectionHeader(
                        "Department comparison",
                        "Resolution counts, urgency, response time and satisfaction.",
                        icon=ft.Icons.BUSINESS,
                        is_dark=is_dark,
                    ),
                    scrollable_table,
                    mobile_cards_col,
                    feedback_section
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=SPACING["lg"],
                expand=True,
            ),
            padding=SPACING["lg"],
            is_dark=is_dark,
            expand=True,
        )

