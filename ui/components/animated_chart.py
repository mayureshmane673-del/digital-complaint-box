"""
ui/components/animated_chart.py: Animated, responsive chart showing
Complaints Registered vs Complaints Resolved with real database metrics.
Supports both light and dark modes and adapts cleanly to desktop and mobile screens.
"""

import math
from typing import Dict, Any, Optional
import flet as ft
from ui.theme import (
    COLOR_PRIMARY, COLOR_PRIMARY_LIGHT, COLOR_SURFACE, COLOR_BORDER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_MUTED, get_theme_colors
)


def create_circular_status_chart(
    registered: int,
    resolved: int,
    in_progress: int = 0,
    pending: int = 0,
    rejected: int = 0,
    title: str = "Complaints Status & Resolution Distribution",
    subtitle: Optional[str] = None,
    is_dark: bool = False
) -> ft.Control:
    """
    Builds a prominent circular / donut-style status distribution graph across all dashboards.
    Uses native Flet 0.86.5 ft.Stack and rotated ft.ProgressRing controls.
    Zero complaints empty circular state and real-time live DB metrics.
    """
    colors = get_theme_colors(is_dark)
    track_color = colors.get("surface_variant", "#e2e8f0" if not is_dark else "#334155")

    # Metrics calculation
    res_rate = round((resolved / registered) * 100, 1) if registered > 0 else 0.0
    in_prog_rate = round((in_progress / registered) * 100, 1) if registered > 0 else 0.0
    pend_rate = round((pending / registered) * 100, 1) if registered > 0 else 0.0
    rej_rate = round((rejected / registered) * 100, 1) if registered > 0 else 0.0

    res_frac = min(1.0, max(0.0, resolved / registered)) if registered > 0 else 0.0
    in_prog_frac = min(1.0, max(0.0, in_progress / registered)) if registered > 0 else 0.0
    pend_frac = min(1.0, max(0.0, pending / registered)) if registered > 0 else 0.0
    rej_frac = min(1.0, max(0.0, rejected / registered)) if registered > 0 else 0.0

    # Build Circular Donut Ring (180x180)
    if registered == 0:
        donut_ring = ft.Stack(
            controls=[
                ft.ProgressRing(value=1.0, stroke_width=14, color=track_color, width=180, height=180),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.QUERY_STATS, size=32, color=colors["primary"]),
                            ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=colors["text"]),
                            ft.Text("Grievances", size=11, color=colors["text_muted"], weight=ft.FontWeight.W_500)
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=2
                    ),
                    width=180,
                    height=180,
                    alignment=ft.Alignment.CENTER
                )
            ],
            width=180,
            height=180
        )
    else:
        ring_layers = [
            ft.ProgressRing(value=1.0, stroke_width=16, color=track_color, width=180, height=180)
        ]
        cum_f = 0.0
        if res_frac > 0:
            ring_layers.append(
                ft.ProgressRing(value=res_frac, stroke_width=16, color="#059669", rotate=2 * math.pi * cum_f, width=180, height=180)
            )
            cum_f += res_frac
        if in_prog_frac > 0:
            ring_layers.append(
                ft.ProgressRing(value=in_prog_frac, stroke_width=16, color="#2563eb", rotate=2 * math.pi * cum_f, width=180, height=180)
            )
            cum_f += in_prog_frac
        if pend_frac > 0:
            ring_layers.append(
                ft.ProgressRing(value=pend_frac, stroke_width=16, color="#d97706", rotate=2 * math.pi * cum_f, width=180, height=180)
            )
            cum_f += pend_frac
        if rej_frac > 0:
            ring_layers.append(
                ft.ProgressRing(value=rej_frac, stroke_width=16, color="#dc2626", rotate=2 * math.pi * cum_f, width=180, height=180)
            )
            cum_f += rej_frac

        ring_layers.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(f"{res_rate}%", size=24, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Text("Resolution", size=11, weight=ft.FontWeight.W_600, color=colors["text_muted"]),
                        ft.Text(f"{registered} Total", size=10, color=colors["primary"], weight=ft.FontWeight.BOLD)
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=1
                ),
                width=180,
                height=180,
                alignment=ft.Alignment.CENTER
            )
        )
        donut_ring = ft.Stack(controls=ring_layers, width=180, height=180)

    def make_stat_metric(label: str, count: int, pct: float, color: str):
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(width=12, height=12, border_radius=6, bgcolor=color),
                            ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=colors["text"])
                        ],
                        spacing=8
                    ),
                    ft.Row(
                        controls=[
                            ft.Text(str(count), size=14, weight=ft.FontWeight.BOLD, color=colors["text"]),
                            ft.Text(f"({pct}%)", size=12, color=colors["text_muted"])
                        ],
                        spacing=4
                    )
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            padding=ft.padding.symmetric(vertical=4)
        )

    written_metrics = ft.Column(
        controls=[
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text("Total Grievances Recorded:", size=13, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ft.Text(str(registered), size=16, weight=ft.FontWeight.BOLD, color=colors["primary"])
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                bgcolor=ft.Colors.with_opacity(0.08, colors["primary"]),
                border_radius=8,
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                margin=ft.margin.only(bottom=6)
            ),
            make_stat_metric("Resolved Grievances", resolved, res_rate, "#059669"),
            make_stat_metric("In Progress (Assigned)", in_progress, in_prog_rate, "#2563eb"),
            make_stat_metric("Pending Initial Review", pending, pend_rate, "#d97706"),
            make_stat_metric("Rejected / Invalid", rejected, rej_rate, "#dc2626"),
            ft.Divider(color=colors["border"], height=12),
            ft.Row(
                controls=[
                    ft.Text("Overall Resolution Rate:", size=12, weight=ft.FontWeight.W_600, color=colors["text_muted"]),
                    ft.Container(
                        content=ft.Text(f"{res_rate}%", size=13, weight=ft.FontWeight.BOLD, color="#059669"),
                        bgcolor="#d1fae5" if not is_dark else "#064e3b",
                        border_radius=6,
                        padding=ft.padding.symmetric(horizontal=8, vertical=2)
                    )
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            )
        ],
        spacing=4
    )

    # Combined Layout
    card_body = ft.ResponsiveRow(
        controls=[
            ft.Container(
                content=donut_ring,
                alignment=ft.Alignment.CENTER,
                col={"xs": 12, "sm": 5},
                padding=ft.padding.symmetric(vertical=10)
            ),
            ft.Container(
                content=written_metrics,
                col={"xs": 12, "sm": 7},
                padding=ft.padding.only(left=8, right=8)
            )
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.PIE_CHART_OUTLINE, color=colors["primary"], size=22),
                                        ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                    ],
                                    spacing=8
                                ),
                                ft.Text(subtitle or "Circular status breakdown & resolution tracking", size=12, color=colors["text_muted"])
                            ],
                            spacing=2
                        ),
                        ft.Container(
                            content=ft.Text(f"{res_rate}% Resolved", size=12, weight=ft.FontWeight.BOLD, color="#059669"),
                            bgcolor="#d1fae5" if not is_dark else "#064e3b",
                            border_radius=8,
                            padding=ft.padding.symmetric(horizontal=10, vertical=4)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True
                ),
                ft.Divider(color=colors["border"], height=12),
                card_body
            ],
            spacing=10
        ),
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=12,
        padding=16
    )


# Alias for backwards compatibility across all callers
create_registered_vs_resolved_chart = create_circular_status_chart


def create_hero_3d_badge(is_dark: bool = False) -> ft.Control:
    """
    Renders a lightweight, native Flet 3D-styled institutional visual card
    with layered surfaces, subtle elevation, and key architecture guarantees.
    """
    colors = get_theme_colors(is_dark)

    return ft.Stack(
        controls=[
            # Base shadow/glow layer (offset)
            ft.Container(
                width=340,
                height=240,
                margin=ft.margin.only(top=12, left=12),
                border_radius=20,
                bgcolor=ft.Colors.with_opacity(0.18, colors["primary"]),
            ),
            # Intermediate gradient backdrop layer
            ft.Container(
                width=340,
                height=240,
                margin=ft.margin.only(top=6, left=6),
                border_radius=20,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_LEFT,
                    end=ft.Alignment.BOTTOM_RIGHT,
                    colors=["#1e3a8a", "#2563eb"] if not is_dark else ["#0f172a", "#1e3a8a"]
                ),
            ),
            # Front crisp layered card
            ft.Container(
                width=340,
                height=240,
                bgcolor=colors["surface"],
                border=ft.Border.all(1.5, colors["border"]),
                border_radius=20,
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(
                                    content=ft.Icon(ft.Icons.VERIFIED_USER, size=24, color=colors["primary"]),
                                    bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                                    border_radius=10,
                                    padding=8
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text("INSTITUTIONAL INTEGRITY", size=10, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                                        ft.Text("Guaranteed Architecture", size=14, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                    ],
                                    spacing=2
                                )
                            ],
                            spacing=12
                        ),
                        ft.Divider(color=colors["border"], height=16),
                        ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.LOCK, size=14, color="#059669"),
                                        ft.Text("Zero Credential Leakage to UI", size=12, weight=ft.FontWeight.W_500, color=colors["text"])
                                    ],
                                    spacing=8
                                ),
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.SHIELD, size=14, color="#2563eb"),
                                        ft.Text("PostgreSQL RLS & Role Isolation", size=12, weight=ft.FontWeight.W_500, color=colors["text"])
                                    ],
                                    spacing=8
                                ),
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.SCHOOL, size=14, color="#d97706"),
                                        ft.Text("5 Departments: CSE, AIDS, E&TC, MECH, Civil", size=11, weight=ft.FontWeight.W_500, color=colors["text"])
                                    ],
                                    spacing=8
                                ),
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.FINGERPRINT, size=14, color="#7c3aed"),
                                        ft.Text("Student Roll Pool Authorization", size=12, weight=ft.FontWeight.W_500, color=colors["text"])
                                    ],
                                    spacing=8
                                ),
                            ],
                            spacing=10
                        )
                    ],
                    spacing=0,
                    alignment=ft.MainAxisAlignment.START
                )
            )
        ],
        width=360,
        height=260
    )


def create_campus_overview_card(dept_metrics: list, is_dark: bool = False) -> ft.Control:
    """
    Renders Principal Campus Overview comparing real grievance metrics
    across all 5 departments: CSE, AIDS, E&TC, MECH, Civil.
    """
    colors = get_theme_colors(is_dark)

    if not dept_metrics:
        return ft.Container()

    dept_cards = []
    dept_colors = {
        "CSE": "#2563eb",
        "AIDS": "#7c3aed",
        "E&TC": "#0f766e",
        "MECH": "#ea580c",
        "Civil": "#059669"
    }

    for d in dept_metrics:
        code = d.get("code", "DEPT")
        name = d.get("name", "Department")
        total = d.get("total", 0)
        resolved = d.get("resolved", 0)
        pending = d.get("pending", 0)
        in_prog = d.get("in_progress", 0)
        accent = dept_colors.get(code, colors["primary"])
        res_rate = round((resolved / total * 100), 1) if total > 0 else 0.0

        card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Text(code, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                bgcolor=accent,
                                border_radius=6,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4)
                            ),
                            ft.Text(f"{res_rate}% Resolved", size=11, weight=ft.FontWeight.BOLD, color="#059669" if res_rate > 50 else "#d97706")
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    ft.Text(name, size=12, weight=ft.FontWeight.W_600, color=colors["text"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Divider(color=colors["border"], height=10),
                    ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text(str(total), size=18, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                    ft.Text("Total", size=10, color=colors["text_muted"])
                                ],
                                spacing=0
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(str(pending), size=18, weight=ft.FontWeight.BOLD, color="#d97706"),
                                    ft.Text("Pending", size=10, color=colors["text_muted"])
                                ],
                                spacing=0
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(str(in_prog), size=18, weight=ft.FontWeight.BOLD, color="#2563eb"),
                                    ft.Text("In Progress", size=10, color=colors["text_muted"])
                                ],
                                spacing=0
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(str(resolved), size=18, weight=ft.FontWeight.BOLD, color="#059669"),
                                    ft.Text("Resolved", size=10, color=colors["text_muted"])
                                ],
                                spacing=0
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ],
                spacing=8
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=14
        )
        dept_cards.append(ft.Container(card, col={"xs": 12, "sm": 6, "md": 4, "lg": 2.4}))

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.APARTMENT, color=colors["primary"], size=22),
                                ft.Text("Campus Academic Departments Overview", size=16, weight=ft.FontWeight.BOLD, color=colors["text"]),
                            ],
                            spacing=8
                        ),
                        ft.Container(
                            content=ft.Text("5 Departments Tracked", size=11, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                            bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                            border_radius=8,
                            padding=ft.padding.symmetric(horizontal=8, vertical=4)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True
                ),
                ft.Divider(color=colors["border"], height=12),
                ft.ResponsiveRow(controls=dept_cards, spacing=10, run_spacing=10)
            ],
            spacing=10
        ),
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=12,
        padding=16
    )


def create_priority_distribution_chart(
    complaints: list,
    title: str = "Priority Distribution",
    subtitle: Optional[str] = "Grievances segmented by urgency level",
    is_dark: bool = False
) -> ft.Control:
    """
    Renders an animated graphical chart displaying complaint distribution across
    Urgent, High, Medium, and Low priorities with real counts, percentages, and progress bars.
    """
    colors = get_theme_colors(is_dark)
    total = len(complaints)

    if total == 0:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.FLAG_OUTLINED, color=colors["primary"], size=20),
                            ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ],
                        spacing=8
                    ),
                    ft.Text(subtitle or "No priority distribution data yet", size=12, color=colors["text_muted"]),
                    ft.Divider(color=colors["border"], height=12),
                    ft.Container(
                        content=ft.Text("No grievances recorded to display priority breakdown.", size=12, color=colors["text_muted"], italic=True),
                        alignment=ft.Alignment.CENTER,
                        padding=20
                    )
                ],
                spacing=4
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )

    urgent_cnt = sum(1 for c in complaints if (c.get("priority") or "").capitalize() == "Urgent")
    high_cnt = sum(1 for c in complaints if (c.get("priority") or "").capitalize() == "High")
    med_cnt = sum(1 for c in complaints if (c.get("priority") or "").capitalize() == "Medium")
    low_cnt = sum(1 for c in complaints if (c.get("priority") or "").capitalize() in ("Low", ""))

    prio_data = [
        ("Urgent", urgent_cnt, "#dc2626"),
        ("High", high_cnt, "#ea580c"),
        ("Medium", med_cnt, "#d97706"),
        ("Low", low_cnt, "#10b981")
    ]

    metric_bars = []
    for label, count, color_hex in prio_data:
        pct = round((count / total) * 100, 1) if total > 0 else 0.0
        frac = min(1.0, count / total) if total > 0 else 0.0
        bar = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(width=10, height=10, border_radius=5, bgcolor=color_hex),
                                ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=colors["text"])
                            ],
                            spacing=6
                        ),
                        ft.Row(
                            controls=[
                                ft.Text(str(count), size=13, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                ft.Text(f"({pct}%)", size=11, color=colors["text_muted"])
                            ],
                            spacing=4
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.ProgressBar(
                    value=frac,
                    color=color_hex,
                    bgcolor=colors.get("surface_variant", "#e2e8f0" if not is_dark else "#334155"),
                    height=8,
                    border_radius=4
                )
            ],
            spacing=4
        )
        metric_bars.append(bar)

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.FLAG_OUTLINED, color=colors["primary"], size=20),
                                ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=colors["text"]),
                            ],
                            spacing=8
                        ),
                        ft.Container(
                            content=ft.Text(f"{total} Total", size=11, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                            bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                            border_radius=6,
                            padding=ft.padding.symmetric(horizontal=8, vertical=3)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Text(subtitle or "Distribution across Urgency classifications", size=12, color=colors["text_muted"]),
                ft.Divider(color=colors["border"], height=12),
                ft.Column(controls=metric_bars, spacing=10)
            ],
            spacing=6
        ),
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=12,
        padding=16
    )


def create_category_distribution_chart(
    complaints: list,
    title: str = "Category Breakdown",
    subtitle: Optional[str] = "Top grievance categories by volume",
    is_dark: bool = False,
    max_items: int = 6
) -> ft.Control:
    """
    Renders an animated graphical chart breaking down grievances across
    categories with real database counts and percentages.
    """
    colors = get_theme_colors(is_dark)
    total = len(complaints)

    if total == 0:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CATEGORY_OUTLINED, color=colors["primary"], size=20),
                            ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=colors["text"]),
                        ],
                        spacing=8
                    ),
                    ft.Text(subtitle or "Grievances segmented by category", size=12, color=colors["text_muted"]),
                    ft.Divider(color=colors["border"], height=12),
                    ft.Container(
                        content=ft.Text("No grievances recorded to display category breakdown.", size=12, color=colors["text_muted"], italic=True),
                        alignment=ft.Alignment.CENTER,
                        padding=20
                    )
                ],
                spacing=4
            ),
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=12,
            padding=16
        )

    from collections import Counter
    cat_counts = Counter()
    for c in complaints:
        cat_obj = c.get("categories")
        cname = cat_obj.get("name") if isinstance(cat_obj, dict) else (c.get("category_name") or c.get("category_custom") or "General / Other")
        cat_counts[str(cname)] += 1

    palette = ["#2563eb", "#7c3aed", "#059669", "#d97706", "#ea580c", "#0f766e", "#e11d48", "#4f46e5"]
    bars = []
    for idx, (cat_name, count) in enumerate(cat_counts.most_common(max_items)):
        color_hex = palette[idx % len(palette)]
        pct = round((count / total) * 100, 1) if total > 0 else 0.0
        frac = min(1.0, count / total) if total > 0 else 0.0
        bar = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(width=10, height=10, border_radius=5, bgcolor=color_hex),
                                ft.Text(cat_name, size=12, weight=ft.FontWeight.W_600, color=colors["text"], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
                            ],
                            spacing=6
                        ),
                        ft.Row(
                            controls=[
                                ft.Text(str(count), size=12, weight=ft.FontWeight.BOLD, color=colors["text"]),
                                ft.Text(f"({pct}%)", size=11, color=colors["text_muted"])
                            ],
                            spacing=4
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.ProgressBar(
                    value=frac,
                    color=color_hex,
                    bgcolor=colors.get("surface_variant", "#e2e8f0" if not is_dark else "#334155"),
                    height=8,
                    border_radius=4
                )
            ],
            spacing=4
        )
        bars.append(bar)

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.CATEGORY_OUTLINED, color=colors["primary"], size=20),
                                ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=colors["text"]),
                            ],
                            spacing=8
                        ),
                        ft.Container(
                            content=ft.Text(f"{len(cat_counts)} Categories", size=11, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                            bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                            border_radius=6,
                            padding=ft.padding.symmetric(horizontal=8, vertical=3)
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Text(subtitle or "Grievances segmented by category", size=12, color=colors["text_muted"]),
                ft.Divider(color=colors["border"], height=12),
                ft.Column(controls=bars, spacing=8)
            ],
            spacing=6
        ),
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=12,
        padding=16
    )
