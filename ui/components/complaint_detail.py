"""
ui/components/complaint_detail.py: Full complaint detail modal with history timeline, attachments, and role-appropriate management actions.
Supports Dark Mode, loading states, and mobile responsive layout.
"""

from typing import Dict, Any, Callable, Optional
import flet as ft
from ui.theme import (
    COLOR_PRIMARY, STATUS_COLORS, PRIORITY_COLORS, get_theme_colors
)
from ui.state import AppState
from ui.flet_compat import show_feedback_message, open_dialog, close_dialog
from utils.helpers import format_datetime, format_file_size
from models.user import UserRole
from models.complaint import ComplaintStatus, ComplaintPriority
from services.complaint_service import ComplaintService
from services.storage_service import StorageService
from database.supabase_client import get_supabase_client


def show_complaint_detail_dialog(
    page: ft.Page,
    complaint: Dict[str, Any],
    current_role: str,
    current_user_id: str,
    current_dept_id: Optional[str] = None,
    on_updated: Optional[Callable[[], None]] = None
):
    is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)

    cid = complaint.get("complaint_id")
    status = complaint.get("status", "Pending")
    priority = complaint.get("priority", "Low")
    auto_pri = complaint.get("auto_priority", "Low")
    is_anon = complaint.get("is_anonymous", False)

    # Load fresh history and attachments concurrently via trusted backend service
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_hist = executor.submit(ComplaintService.get_complaint_history, cid)
        f_att = executor.submit(ComplaintService.get_complaint_attachments, cid)
        history_items = f_hist.result()
        attachments = f_att.result()

    # History timeline widgets
    history_widgets = []
    for h in history_items:
        act = h.get("action", "")
        role = h.get("actor_role", "System")
        rem = h.get("remarks", "")
        t_str = format_datetime(h.get("created_at"))
        history_widgets.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=16, color=colors["primary"]),
                                ft.Text(f"{act.replace('_', ' ').title()} by {role}", weight=ft.FontWeight.W_600, size=13, color=colors["text"]),
                                ft.Text(t_str, size=11, color=colors["text_muted"])
                            ],
                            spacing=6,
                            wrap=True
                        ),
                        ft.Text(rem, size=12, color=colors["text"]) if rem else ft.Container()
                    ],
                    spacing=2
                ),
                padding=ft.padding.only(left=8, bottom=8)
            )
        )

    if not history_widgets:
        history_widgets.append(ft.Text("No history entries yet.", size=12, italic=True, color=colors["text_muted"]))

    # Attachments list widgets
    attachment_widgets = []
    for att in attachments:
        fname = att.get("file_name", "Attachment")
        fsize = format_file_size(att.get("file_size", 0))
        fpath = att.get("file_path", "")
        ext = fpath.split(".")[-1].lower() if "." in fpath else ""
        is_img = ext in ("jpg", "jpeg", "png", "webp")
        is_pdf = ext == "pdf"
        is_video = ext in ("mp4", "mov")

        if is_img:
            icon_type = ft.Icons.IMAGE
        elif is_pdf:
            icon_type = ft.Icons.PICTURE_AS_PDF
        elif is_video:
            icon_type = ft.Icons.VIDEO_FILE
        else:
            icon_type = ft.Icons.ATTACH_FILE

        # Precompute authorized signed URL using preloaded complaint object
        signed_file_url = StorageService.get_authorized_signed_url(
            complaint_id=cid,
            storage_path=fpath,
            user_id=current_user_id,
            role=current_role,
            department_id=current_dept_id,
            complaint=complaint
        ) or StorageService.get_signed_url(fpath)

        def open_url(e, p=fpath, pre_signed=signed_file_url):
            url_to_open = pre_signed or StorageService.get_authorized_signed_url(
                complaint_id=cid,
                storage_path=p,
                user_id=current_user_id,
                role=current_role,
                department_id=current_dept_id,
                complaint=complaint
            ) or StorageService.get_signed_url(p)
            if url_to_open:
                page.launch_url(url_to_open, web_popup_window_name="_blank")
            else:
                show_feedback_message(page, "Could not generate attachment link.", is_error=True)

        preview_content = None
        if is_img and signed_file_url:
            preview_content = ft.Image(
                src=signed_file_url,
                width=72,
                height=56,
                fit=ft.BoxFit.COVER if hasattr(ft, "BoxFit") else "cover",
                border_radius=6,
                error_content=ft.Container(
                    content=ft.Icon(icon_type, size=28, color=colors["primary"]),
                    alignment=ft.Alignment.CENTER,
                    bgcolor=colors.get("surface_variant", "#f1f5f9"),
                    border_radius=6
                )
            )

        if not preview_content:
            preview_content = ft.Container(
                content=ft.Icon(icon_type, size=28, color=colors["primary"]),
                width=72,
                height=56,
                alignment=ft.Alignment.CENTER,
                bgcolor=colors.get("surface_variant", "#f1f5f9"),
                border_radius=6
            )
        else:
            preview_content = ft.Container(
                content=preview_content,
                width=72,
                height=56,
                alignment=ft.Alignment.CENTER,
                border_radius=6,
                clip_behavior=ft.ClipBehavior.HARD_EDGE
            )

        btn_label = "Open" if (is_img or is_pdf or is_video) else "Download"
        btn_url = ft.Url(url=signed_file_url, target=ft.UrlTarget.BLANK) if signed_file_url else None
        open_button = ft.ElevatedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.OPEN_IN_NEW, size=14),
                ft.Text(btn_label, size=12)
            ], spacing=4),
            url=btn_url,
            on_click=open_url if not signed_file_url else None,
            style=ft.ButtonStyle(
                bgcolor=colors["primary"],
                color=ft.Colors.WHITE,
                padding=ft.padding.symmetric(horizontal=12, vertical=6)
            )
        )

        attachment_card = ft.Container(
            content=ft.Row(
                controls=[
                    preview_content,
                    ft.Column(
                        controls=[
                            ft.Text(
                                fname,
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=colors["text"],
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text(fsize, size=11, color=colors["text_muted"]),
                                    ft.Container(
                                        content=ft.Text(ext.upper() if ext else "FILE", size=9, weight=ft.FontWeight.BOLD, color=colors["primary"]),
                                        bgcolor=ft.Colors.with_opacity(0.12, colors["primary"]),
                                        border_radius=4,
                                        padding=ft.padding.symmetric(horizontal=5, vertical=1)
                                    )
                                ],
                                spacing=6
                            )
                        ],
                        expand=True,
                        spacing=3
                    ),
                    open_button
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12
            ),
            border=ft.Border.all(1, colors["border"]),
            border_radius=8,
            padding=8,
            margin=ft.margin.only(bottom=6),
            bgcolor=colors["surface"]
        )
        attachment_widgets.append(attachment_card)

    if not attachment_widgets:
        attachment_widgets.append(ft.Text("No attachments attached to this complaint.", size=12, italic=True, color=colors["text_muted"]))

    # Management controls
    management_controls = []

    if current_role == UserRole.STUDENT.value:
        is_pending = (status == "Pending")
        no_admin_action = not complaint.get("has_admin_action", False)

        if is_pending and no_admin_action:
            delete_btn = ft.ElevatedButton(
                content=ft.Row([
                    ft.Icon(ft.Icons.DELETE_FOREVER, size=16, color=ft.Colors.WHITE),
                    ft.Text("Delete Complaint", size=13, color=ft.Colors.WHITE)
                ], spacing=6),
                style=ft.ButtonStyle(bgcolor="#dc2626", color=ft.Colors.WHITE)
            )

            def open_delete_confirm(e):
                confirm_btn = ft.ElevatedButton(
                    content=ft.Text("Yes, Delete"),
                    style=ft.ButtonStyle(bgcolor="#dc2626", color=ft.Colors.WHITE)
                )

                def do_confirm_delete(ev):
                    confirm_btn.disabled = True
                    confirm_btn.content = ft.Text("Deleting...")
                    page.update()
                    ok, msg = ComplaintService.delete_complaint_by_student(cid, current_user_id)
                    close_dialog(page, confirm_dlg)
                    close_dialog(page, dlg)
                    if ok:
                        show_feedback_message(page, msg, is_error=False)
                        if on_updated:
                            on_updated()
                    else:
                        show_feedback_message(page, msg, is_error=True)
                    page.update()

                confirm_btn.on_click = do_confirm_delete

                confirm_dlg = ft.AlertDialog(
                    title=ft.Text("Confirm Deletion", weight=ft.FontWeight.BOLD, color=colors["text"]),
                    content=ft.Text(f"Are you sure you want to delete Complaint #{cid}? This action cannot be undone.", size=14, color=colors["text"]),
                    bgcolor=colors["surface"],
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _: close_dialog(page, confirm_dlg)),
                        confirm_btn
                    ]
                )
                open_dialog(page, confirm_dlg)

            delete_btn.on_click = open_delete_confirm
            management_controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text("Need to withdraw this grievance?", size=13, color=colors["text_muted"]),
                        delete_btn
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                    bgcolor=colors.get("surface_variant", "#f1f5f9"),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8
                )
            )
        else:
            management_controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.LOCK_OUTLINE, size=16, color=colors["text_muted"]),
                        ft.Text(
                            "Complaint cannot be deleted: Administrative review has already started or status is no longer Pending.",
                            size=12,
                            color=colors["text_muted"],
                            expand=True
                        )
                    ], spacing=6),
                    bgcolor=colors.get("surface_variant", "#f1f5f9"),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8
                )
            )

    can_change_status = current_role in (UserRole.HOD.value, UserRole.COORDINATOR.value, UserRole.HOSTEL_INCHARGE.value, UserRole.PRINCIPAL.value)
    if can_change_status:
        status_dropdown = ft.Dropdown(
            label="Update Status",
            value=status,
            options=[
                ft.dropdown.Option(key="Pending", text="Pending"),
                ft.dropdown.Option(key="In Progress", text="In Progress"),
                ft.dropdown.Option(key="Resolved", text="Resolved"),
                ft.dropdown.Option(key="Rejected", text="Rejected")
            ],
            dense=True,
            width=180
        )
        status_remark = ft.TextField(
            label="Remark / Resolution Reason",
            hint_text="Compulsory for Resolved, Rejected, or backward changes.",
            multiline=True,
            dense=True,
            min_lines=1,
            max_lines=3,
            expand=True
        )

        save_status_btn = ft.ElevatedButton(
            content=ft.Text("Save Status"),
            icon=ft.Icons.CHECK,
            style=ft.ButtonStyle(bgcolor=colors["primary"], color=ft.Colors.WHITE)
        )

        def apply_status(e):
            new_st = status_dropdown.value
            rem = status_remark.value

            save_status_btn.disabled = True
            save_status_btn.content = ft.Text("Saving...")
            page.update()

            ok, msg = ComplaintService.update_status(
                actor_role=current_role,
                actor_id=current_user_id,
                actor_dept_id=current_dept_id,
                complaint_id=cid,
                new_status=new_st,
                remark=rem
            )

            save_status_btn.disabled = False
            save_status_btn.content = ft.Text("Save Status")

            if ok:
                show_feedback_message(page, msg, is_error=False)
                dlg.open = False
                page.update()
                on_updated()
            else:
                show_feedback_message(page, msg, is_error=True)
                page.update()

        save_status_btn.on_click = apply_status

        management_controls.append(
            ft.Column(
                controls=[
                    ft.Text("Status Management", weight=ft.FontWeight.BOLD, size=14, color=colors["text"]),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(status_dropdown, col={"xs": 12, "sm": 4}),
                            ft.Container(status_remark, col={"xs": 12, "sm": 8}),
                        ]
                    ),
                    save_status_btn
                ],
                spacing=8
            )
        )

    # Metadata chips
    cat_name = complaint.get("categories", {}).get("name") if isinstance(complaint.get("categories"), dict) else (complaint.get("category_name") or "General")
    sub_name = complaint.get("subcategories", {}).get("name") if isinstance(complaint.get("subcategories"), dict) else (complaint.get("subcategory_name") or complaint.get("subcategory_custom") or "")
    loc_name = complaint.get("locations", {}).get("name") if isinstance(complaint.get("locations"), dict) else (complaint.get("location_custom") or complaint.get("location_name") or "Campus")
    created_at_fmt = format_datetime(complaint.get("created_at"))

    meta_chips = [
        ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CATEGORY_OUTLINED, size=12, color=colors["primary"]),
                    ft.Text(cat_name, size=11, weight=ft.FontWeight.W_500, color=colors["text"])
                ],
                spacing=4
            ),
            bgcolor=colors.get("surface_variant", "#f1f5f9"),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=8, vertical=4)
        ),
    ]

    if sub_name and str(sub_name).lower() not in ("none", "null", ""):
        meta_chips.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.SUBDIRECTORY_ARROW_RIGHT, size=12, color=colors["primary"]),
                        ft.Text(str(sub_name), size=11, weight=ft.FontWeight.W_500, color=colors["text"])
                    ],
                    spacing=4
                ),
                bgcolor=colors.get("surface_variant", "#f1f5f9"),
                border_radius=8,
                padding=ft.padding.symmetric(horizontal=8, vertical=4)
            )
        )

    meta_chips.extend([
        ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.LOCATION_ON_OUTLINED, size=12, color=colors["text_muted"]),
                    ft.Text(loc_name, size=11, color=colors["text_muted"])
                ],
                spacing=4
            ),
            bgcolor=colors.get("surface_variant", "#f1f5f9"),
            padding=ft.padding.symmetric(horizontal=8, vertical=4)
        ),
        ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SCHEDULE, size=12, color=colors["text_muted"]),
                    ft.Text(f"Submitted: {created_at_fmt}", size=11, color=colors["text_muted"])
                ],
                spacing=4
            ),
            bgcolor=colors.get("surface_variant", "#f1f5f9"),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=8, vertical=4)
        ),
        ft.Container(
            content=ft.Text(f"Priority: {priority}", size=11, weight=ft.FontWeight.BOLD, color=PRIORITY_COLORS.get(priority, "#6b7280")),
            bgcolor=ft.Colors.with_opacity(0.12, PRIORITY_COLORS.get(priority, "#6b7280")),
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=8, vertical=4)
        )
    ])

    if is_anon:
        meta_chips.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.VISIBILITY_OFF, size=12, color="#94a3b8" if is_dark else "#64748b"),
                        ft.Text("Identity Masked (Anonymous)", size=11, weight=ft.FontWeight.W_600, color="#94a3b8" if is_dark else "#64748b")
                    ],
                    spacing=4
                ),
                bgcolor="#1e293b" if is_dark else "#f1f5f9",
                border_radius=8,
                padding=ft.padding.symmetric(horizontal=8, vertical=4)
            )
        )

    # Main modal content
    content_col = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Text(f"Complaint #{cid}", size=20, weight=ft.FontWeight.BOLD, color=colors["text"]),
                    ft.Container(
                        content=ft.Text(status, size=12, weight=ft.FontWeight.BOLD, color=STATUS_COLORS.get(status, "#6b7280")),
                        bgcolor=ft.Colors.with_opacity(0.12, STATUS_COLORS.get(status, "#6b7280")),
                        border_radius=12,
                        padding=ft.padding.symmetric(horizontal=10, vertical=4)
                    )
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                wrap=True
            ),
            ft.Row(controls=meta_chips, wrap=True, spacing=6),
            ft.Divider(color=colors["border"], height=10),
            ft.Text(complaint.get("title", ""), size=17, weight=ft.FontWeight.BOLD, color=colors["text"]),
            ft.Text(complaint.get("description", ""), size=13, color=colors["text"]),
            ft.Divider(color=colors["border"]),
            ft.Text(f"Attachments ({len(attachments)})", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]),
            ft.Column(controls=attachment_widgets, spacing=4),
            ft.Divider(color=colors["border"]),
            ft.Text("Audit Timeline", weight=ft.FontWeight.BOLD, size=13, color=colors["text"]),
            ft.Column(controls=history_widgets, spacing=4),
            ft.Divider(color=colors["border"]) if management_controls else ft.Container(),
            ft.Column(controls=management_controls, spacing=8)
        ],
        spacing=10,
        scroll=ft.ScrollMode.AUTO
    )

    dlg_height = min(620, int(page.height * 0.85)) if getattr(page, "height", None) else 580
    dlg = ft.AlertDialog(
        content=ft.Container(
            content=content_col,
            width=640,
            height=dlg_height,
            padding=ft.padding.symmetric(horizontal=12, vertical=8)
        ),
        bgcolor=colors["surface"],
        actions=[
            ft.TextButton("Close", on_click=lambda _: close_dialog(page, dlg))
        ]
    )

    open_dialog(page, dlg)
