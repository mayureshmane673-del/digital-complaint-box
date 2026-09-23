"""
ui/components/excel_importer.py: Coordinator Excel/CSV batch roll number importer with metrics summary.
"""

import weakref
from typing import Callable, Optional
import flet as ft
from services.roll_number_service import RollNumberService
from ui.theme import COLOR_PRIMARY, COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_MUTED
from ui.flet_compat import open_dialog, close_dialog


def show_excel_importer_dialog(
    page: ft.Page,
    coordinator_role: str,
    coordinator_dept_id: str,
    coordinator_id: str,
    on_imported: Callable[[], None]
):
    selected_path = ft.Text("No file selected", italic=True, size=12, color=COLOR_TEXT_MUTED)
    summary_container = ft.Column(spacing=8)

    file_picker = ft.FilePicker()
    if hasattr(page, "services"):
        if file_picker not in page.services:
            page.services.append(file_picker)
    elif hasattr(page, "_services"):
        try:
            page._services.register_service(file_picker)
        except Exception:
            pass
    try:
        file_picker._parent = weakref.ref(page)
    except Exception:
        pass
    page.update()

    selected_file_info = [None]

    async def on_choose_file(e):
        try:
            files = await file_picker.pick_files(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["xlsx", "xls", "csv"],
                allow_multiple=False,
                with_data=True,
                cancel_upload_on_window_blur=False
            )
            if not files or len(files) == 0:
                selected_file_info[0] = None
                selected_path.value = "No file selected"
                selected_path.italic = True
                selected_path.color = COLOR_TEXT_MUTED
                import_btn.disabled = True
                page.update()
                return

            f = files[0]
            name_lower = f.name.lower()
            if not (name_lower.endswith(".xlsx") or name_lower.endswith(".xls") or name_lower.endswith(".csv")):
                selected_file_info[0] = None
                selected_path.value = f"Invalid file type: {f.name}. Please select .xlsx, .xls, or .csv"
                selected_path.italic = False
                selected_path.color = "#dc2626"
                import_btn.disabled = True
                page.update()
                return

            selected_file_info[0] = {
                "name": f.name,
                "bytes": f.bytes,
                "path": f.path
            }
            display_name = f.name
            selected_path.value = f"Selected: {display_name}"
            selected_path.italic = False
            selected_path.color = COLOR_PRIMARY
            import_btn.disabled = False
            page.update()
        except Exception:
            selected_path.value = "Unable to open file picker. Please try again."
            selected_path.color = "#dc2626"
            page.update()

    def run_import(e):
        if not selected_file_info[0]:
            return
        import_btn.disabled = True
        import_btn.text = "Importing..."
        page.update()

        info = selected_file_info[0]
        summary = RollNumberService.import_excel_roll_numbers(
            coordinator_role=coordinator_role,
            coordinator_dept_id=coordinator_dept_id,
            coordinator_id=coordinator_id,
            file_path=info.get("path"),
            file_bytes=info.get("bytes"),
            file_name=info.get("name")
        )

        import_btn.disabled = False
        import_btn.text = "Import File"

        # Render summary metrics
        metrics_rows = [
            ft.Text(summary.get("message", ""), weight=ft.FontWeight.BOLD, size=13, color="#10b981" if summary.get("success") else "#dc2626"),
            ft.Row(
                controls=[
                    _chip("Total", summary.get("total_rows", 0), "#3b82f6"),
                    _chip("Valid", summary.get("valid", 0), "#10b981"),
                    _chip("Added", summary.get("added", 0), "#059669"),
                    _chip("Duplicates", summary.get("duplicates", 0), "#d97706"),
                    _chip("Invalid", summary.get("invalid", 0), "#ef4444"),
                    _chip("Failed", summary.get("failed", 0), "#991b1b")
                ],
                wrap=True,
                spacing=8
            )
        ]

        if summary.get("errors"):
            metrics_rows.append(
                ft.Text("Errors:", size=12, weight=ft.FontWeight.BOLD, color="#dc2626")
            )
            for err in summary["errors"][:5]:
                metrics_rows.append(ft.Text(f"• {err}", size=11, color="#ef4444"))

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
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=8, vertical=4)
        )

    import_btn = ft.ElevatedButton(
        text="Import File",
        icon=ft.Icons.UPLOAD_FILE,
        disabled=True,
        on_click=run_import
    )

    dlg = ft.AlertDialog(
        title=ft.Row(
            controls=[
                ft.Icon(ft.Icons.TABLE_VIEW, color=COLOR_PRIMARY),
                ft.Text("Import Roll Numbers from Excel", size=18, weight=ft.FontWeight.BOLD)
            ],
            spacing=8
        ),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Upload an Excel (.xlsx, .xls) or CSV file containing student roll numbers.", size=13, color=COLOR_TEXT_PRIMARY),
                    ft.Row(
                        controls=[
                            ft.ElevatedButton(
                                "Choose File",
                                icon=ft.Icons.FILE_UPLOAD,
                                on_click=on_choose_file
                            ),
                            selected_path
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=12
                    ),
                    import_btn,
                    ft.Divider(color=COLOR_BORDER),
                    summary_container
                ],
                spacing=14,
                scroll=ft.ScrollMode.AUTO
            ),
            width=540,
            height=360
        ),
        actions=[
            ft.TextButton("Close", on_click=lambda _: close_dialog(page, dlg))
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )

    open_dialog(page, dlg)
