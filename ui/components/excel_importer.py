"""
ui/components/excel_importer.py: Coordinator Excel/CSV batch roll number importer with metrics summary.
"""

import os
from typing import Callable
import flet as ft
from services.roll_number_service import RollNumberService
from ui.theme import get_theme_colors, get_button_style, get_text_style, RADII, SPACING
from ui.state import AppState
from ui.flet_compat import open_dialog, close_dialog
from ui.components.page_file_services import open_spreadsheet_import_picker


def show_excel_importer_dialog(
    page: ft.Page,
    coordinator_role: str,
    coordinator_dept_id: str,
    coordinator_id: str,
    on_imported: Callable[[], None]
):
    is_dark = AppState.is_dark_mode
    colors = get_theme_colors(is_dark)
    selected_path = ft.Text("No file selected", italic=True, size=12, color=colors["text_muted"])
    summary_container = ft.Column(spacing=8)
    selected_file_info = [None]

    def _set_path_message(msg: str, *, error: bool = False, primary: bool = False):
        selected_path.value = msg
        selected_path.italic = not primary and not error
        if error:
            selected_path.color = colors["danger"]
        elif primary:
            selected_path.color = colors["primary"]
        else:
            selected_path.color = colors["text_muted"]

    def on_import_busy(busy: bool, message: str):
        if busy and message:
            _set_path_message(message, primary=True)
        elif message and not busy:
            if message.startswith("Selected:"):
                _set_path_message(message, primary=True)
            elif message == "No file selected":
                _set_path_message(message)
            else:
                _set_path_message(message, error=True)
        try:
            page.update()
        except Exception:
            pass

    def on_file_selected(info):
        selected_file_info[0] = info
        import_btn.disabled = info is None
        if info is None and selected_path.value == "No file selected":
            pass
        page.update()

    def on_choose_file(e):
        open_spreadsheet_import_picker(
            page,
            on_selected=on_file_selected,
            on_busy=on_import_busy,
        )

    def run_import(e):
        if not selected_file_info[0]:
            return
        import_btn.disabled = True
        import_btn.text = "Importing..."
        page.update()

        info = selected_file_info[0]

        file_bytes_val = info.get("bytes")
        file_path_val = info.get("path")
        if not file_bytes_val and file_path_val and os.path.exists(file_path_val):
            with open(file_path_val, "rb") as fp:
                file_bytes_val = fp.read()

        summary = RollNumberService.import_excel_roll_numbers(
            coordinator_role=coordinator_role,
            coordinator_dept_id=coordinator_dept_id,
            coordinator_id=coordinator_id,
            file_path=file_path_val,
            file_bytes=file_bytes_val,
            file_name=info.get("name")
        )

        if info.get("is_temp") and file_path_val and os.path.exists(file_path_val):
            try:
                os.remove(file_path_val)
            except Exception:
                pass

        import_btn.disabled = False
        import_btn.text = "Import File"
        selected_file_info[0] = None
        _set_path_message("No file selected")

        metrics_rows = [
            ft.Text(summary.get("message", ""), weight=ft.FontWeight.BOLD, size=13, color=colors["success"] if summary.get("success") else colors["danger"]),
            ft.Row(
                controls=[
                    _chip("Total", summary.get("total_rows", 0), colors["primary"]),
                    _chip("Valid", summary.get("valid", 0), colors["info"]),
                    _chip("Added", summary.get("added", 0), colors["success"]),
                    _chip("Duplicates", summary.get("duplicates", 0), colors["warning"]),
                    _chip("Invalid", summary.get("invalid", 0), colors["danger"]),
                    _chip("Failed", summary.get("failed", 0), colors["danger"])
                ],
                wrap=True,
                spacing=8
            )
        ]

        if summary.get("errors"):
            metrics_rows.append(
                ft.Text("Errors:", size=12, weight=ft.FontWeight.BOLD, color=colors["danger"])
            )
            for err in summary["errors"][:5]:
                metrics_rows.append(ft.Text(f"• {err}", size=11, color=colors["danger"]))

        summary_container.controls = metrics_rows
        page.update()
        on_imported()

    def _chip(label: str, count: int, color: str) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(label, size=11, weight=ft.FontWeight.W_500),
                    ft.Text(str(count), size=12, weight=ft.FontWeight.BOLD)
                ],
                spacing=4
            ),
            bgcolor=ft.Colors.with_opacity(0.12, color),
            border_radius=RADII["sm"],
            padding=ft.padding.symmetric(horizontal=SPACING["sm"], vertical=SPACING["xs"])
        )

    import_btn = ft.ElevatedButton(
        text="Import File",
        icon=ft.Icons.UPLOAD_FILE,
        disabled=True,
        style=get_button_style(is_dark),
        on_click=run_import
    )

    dlg = ft.AlertDialog(
        title=ft.Row(
            controls=[
                ft.Icon(ft.Icons.TABLE_VIEW, color=colors["primary"]),
                ft.Text("Import Roll Numbers from Excel", style=get_text_style("title", is_dark))
            ],
            spacing=8
        ),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Upload an Excel (.xlsx, .xls) or CSV file containing student roll numbers.", style=get_text_style("body", is_dark)),
                    ft.Row(
                        controls=[
                            ft.ElevatedButton(
                                "Choose File",
                                icon=ft.Icons.FILE_UPLOAD,
                                style=get_button_style(is_dark, variant="outline", size="sm"),
                                on_click=on_choose_file
                            ),
                            ft.Container(content=selected_path, expand=True)
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=12,
                    ),
                    import_btn,
                    ft.Divider(color=colors["border"]),
                    summary_container
                ],
                spacing=14,
                scroll=ft.ScrollMode.AUTO,
                tight=True,
            ),
            width=min(540, (page.width or 540) - 32),
            padding=SPACING["lg"],
            border_radius=RADII["lg"],
            bgcolor=colors["surface"],
        ),
        actions=[
            ft.TextButton("Close", style=get_button_style(is_dark, variant="text"), on_click=lambda _: close_dialog(page, dlg))
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        bgcolor=colors["surface"],
        shape=ft.RoundedRectangleBorder(radius=RADII["lg"]),
    )

    open_dialog(page, dlg)
