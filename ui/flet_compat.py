"""
ui/flet_compat.py: Backward-compatibility shim for Flet 0.86+
Ensures smooth runtime compatibility for border, padding, margin, border_radius,
buttons (text -> content kwarg), Tab (text -> label kwarg), Tabs (TabBar + TabBarView),
and Page.dialog property.
"""

import flet as ft

def init_flet_compatibility():
    """Initializes backward compatibility mappings for Flet 0.86+ runtime."""
    # 1. Border shims
    if hasattr(ft, "Border"):
        if not hasattr(ft.border, "all") and hasattr(ft.Border, "all"):
            ft.border.all = ft.Border.all
        if not hasattr(ft.border, "only") and hasattr(ft.Border, "only"):
            ft.border.only = ft.Border.only
        if not hasattr(ft.border, "symmetric") and hasattr(ft.Border, "symmetric"):
            ft.border.symmetric = ft.Border.symmetric

    # 2. Padding shims
    if hasattr(ft, "Padding"):
        if not hasattr(ft.padding, "all") and hasattr(ft.Padding, "all"):
            ft.padding.all = ft.Padding.all
        if not hasattr(ft.padding, "only") and hasattr(ft.Padding, "only"):
            ft.padding.only = ft.Padding.only
        if not hasattr(ft.padding, "symmetric") and hasattr(ft.Padding, "symmetric"):
            ft.padding.symmetric = ft.Padding.symmetric

    # 3. Margin shims
    if hasattr(ft, "Margin"):
        if not hasattr(ft.margin, "all") and hasattr(ft.Margin, "all"):
            ft.margin.all = ft.Margin.all
        if not hasattr(ft.margin, "only") and hasattr(ft.Margin, "only"):
            ft.margin.only = ft.Margin.only
        if not hasattr(ft.margin, "symmetric") and hasattr(ft.Margin, "symmetric"):
            ft.margin.symmetric = ft.Margin.symmetric

    # 4. BorderRadius shims
    if hasattr(ft, "BorderRadius"):
        if not hasattr(ft.border_radius, "all") and hasattr(ft.BorderRadius, "all"):
            ft.border_radius.all = ft.BorderRadius.all
        if not hasattr(ft.border_radius, "only") and hasattr(ft.BorderRadius, "only"):
            ft.border_radius.only = ft.BorderRadius.only

    # 5. Alignment shims
    if hasattr(ft, "Alignment"):
        if not hasattr(ft.alignment, "center") and hasattr(ft.Alignment, "CENTER"):
            ft.alignment.center = ft.Alignment.CENTER
            ft.alignment.center_left = ft.Alignment.CENTER_LEFT
            ft.alignment.center_right = ft.Alignment.CENTER_RIGHT
            ft.alignment.top_center = ft.Alignment.TOP_CENTER
            ft.alignment.top_left = ft.Alignment.TOP_LEFT
            ft.alignment.top_right = ft.Alignment.TOP_RIGHT
            ft.alignment.bottom_center = ft.Alignment.BOTTOM_CENTER
            ft.alignment.bottom_left = ft.Alignment.BOTTOM_LEFT
            ft.alignment.bottom_right = ft.Alignment.BOTTOM_RIGHT

    # 6. Button 'text' kwarg backward compatibility shim
    for btn_cls in [ft.ElevatedButton, ft.TextButton, ft.OutlinedButton]:
        if not getattr(btn_cls, "_compat_patched", False):
            orig_init = btn_cls.__init__
            def make_compat_init(orig):
                def _compat_init(self, *args, **kwargs):
                    if "text" in kwargs:
                        text_val = kwargs.pop("text")
                        if "content" not in kwargs:
                            kwargs["content"] = text_val
                    orig(self, *args, **kwargs)
                return _compat_init
            btn_cls.__init__ = make_compat_init(orig_init)
            btn_cls._compat_patched = True

    # 7. Tab 'text' & 'content' kwarg backward compatibility shim
    if hasattr(ft, "Tab") and not getattr(ft.Tab, "_compat_patched", False):
        orig_tab_init = ft.Tab.__init__
        def compat_tab_init(self, *args, **kwargs):
            self._tab_content = kwargs.pop("content", None)
            if "text" in kwargs:
                t = kwargs.pop("text")
                if "label" not in kwargs:
                    kwargs["label"] = t
            orig_tab_init(self, *args, **kwargs)
        ft.Tab.__init__ = compat_tab_init
        ft.Tab._compat_patched = True

    # 8. Tabs old-syntax (tabs list) backward compatibility shim
    if hasattr(ft, "Tabs") and not getattr(ft.Tabs, "_compat_patched", False):
        orig_tabs_init = ft.Tabs.__init__
        def compat_tabs_init(self, *args, **kwargs):
            if "tabs" in kwargs and "content" not in kwargs:
                old_tabs = kwargs.pop("tabs")
                view_controls = []
                bar_tabs = []
                for t in old_tabs:
                    view_controls.append(getattr(t, "_tab_content", None) or ft.Container())
                    bar_tabs.append(t)
                kwargs["length"] = len(bar_tabs)
                kwargs["content"] = ft.Column(
                    expand=True,
                    controls=[
                        ft.TabBar(tabs=bar_tabs),
                        ft.TabBarView(expand=True, controls=view_controls)
                    ]
                )
            orig_tabs_init(self, *args, **kwargs)
        ft.Tabs.__init__ = compat_tabs_init
        ft.Tabs._compat_patched = True

    # 9. Page.dialog property backward compatibility shim
    if not hasattr(ft.Page, "dialog"):
        def get_dialog(self):
            if hasattr(self, "_dialogs") and self._dialogs.controls:
                return self._dialogs.controls[-1]
            return getattr(self, "_compat_active_dialog", None)
        def set_dialog(self, dlg):
            self._compat_active_dialog = dlg
            if dlg is not None:
                if hasattr(self, "show_dialog"):
                    try:
                        self.show_dialog(dlg)
                    except Exception:
                        pass
            else:
                if hasattr(self, "pop_dialog"):
                    try:
                        self.pop_dialog()
                    except Exception:
                        pass
        ft.Page.dialog = property(get_dialog, set_dialog)

    # 10. Page.snack_bar property backward compatibility shim
    if not hasattr(ft.Page, "snack_bar"):
        def get_snack_bar(self):
            return getattr(self, "_active_snack_bar", None)
        def set_snack_bar(self, sb):
            self._active_snack_bar = sb
            if sb is not None and hasattr(self, "show_dialog"):
                self.show_dialog(sb)
        ft.Page.snack_bar = property(get_snack_bar, set_snack_bar)

    # 11. Theme and ColorScheme 'brightness' argument backward compatibility shim
    if hasattr(ft, "Theme") and not getattr(ft.Theme, "_compat_patched", False):
        orig_theme_init = ft.Theme.__init__
        def compat_theme_init(self, *args, **kwargs):
            if "brightness" in kwargs:
                kwargs.pop("brightness")
            orig_theme_init(self, *args, **kwargs)
        ft.Theme.__init__ = compat_theme_init
        ft.Theme._compat_patched = True

    if hasattr(ft, "ColorScheme") and not getattr(ft.ColorScheme, "_compat_patched", False):
        orig_cs_init = ft.ColorScheme.__init__
        def compat_cs_init(self, *args, **kwargs):
            if "brightness" in kwargs:
                kwargs.pop("brightness")
            orig_cs_init(self, *args, **kwargs)
        ft.ColorScheme.__init__ = compat_cs_init
        ft.ColorScheme._compat_patched = True

    # 12. dropdown.Option text fallback shim
    if hasattr(ft, "dropdown") and hasattr(ft.dropdown, "Option") and not getattr(ft.dropdown.Option, "_compat_patched", False):
        orig_opt_init = ft.dropdown.Option.__init__
        def compat_opt_init(self, key=None, text=None, *args, **kwargs):
            if text is None and key is not None:
                text = str(key)
            orig_opt_init(self, key=key, text=text, *args, **kwargs)
        ft.dropdown.Option.__init__ = compat_opt_init
        ft.dropdown.Option._compat_patched = True

    # 13. Dropdown on_change kwarg and property backward compatibility shim
    if hasattr(ft, "Dropdown") and not getattr(ft.Dropdown, "_compat_patched", False):
        orig_dropdown_init = ft.Dropdown.__init__
        def compat_dropdown_init(self, *args, **kwargs):
            if "on_change" in kwargs:
                oc = kwargs.pop("on_change")
                if "on_select" not in kwargs:
                    kwargs["on_select"] = oc
            orig_dropdown_init(self, *args, **kwargs)
        ft.Dropdown.__init__ = compat_dropdown_init

        # Provide property mapping so dd.on_change = cb sets dd.on_select
        ft.Dropdown.on_change = property(
            lambda self: getattr(self, "on_select", None),
            lambda self, v: setattr(self, "on_select", v)
        )
        ft.Dropdown._compat_patched = True


    # 12. FilePicker event compatibility shim
    if not hasattr(ft, "FilePickerResultEvent"):
        ft.FilePickerResultEvent = getattr(ft, "ControlEvent", object)

    # 13. ImageFit alias to BoxFit
    if not hasattr(ft, "ImageFit") and hasattr(ft, "BoxFit"):
        ft.ImageFit = ft.BoxFit

    # 14. ButtonStyle 'dense' kwarg backward compatibility shim
    if hasattr(ft, "ButtonStyle") and not getattr(ft.ButtonStyle, "_compat_patched", False):
        orig_bs_init = ft.ButtonStyle.__init__
        def compat_bs_init(self, *args, **kwargs):
            kwargs.pop("dense", None)
            orig_bs_init(self, *args, **kwargs)
        ft.ButtonStyle.__init__ = compat_bs_init
        ft.ButtonStyle._compat_patched = True

    # 13. Container dimension arguments backward compatibility shim
    if hasattr(ft, "Container") and not getattr(ft.Container, "_compat_patched", False):
        orig_container_init = ft.Container.__init__
        def compat_container_init(self, *args, **kwargs):
            min_h = kwargs.pop("min_height", None)
            min_w = kwargs.pop("min_width", None)
            max_h = kwargs.pop("max_height", None)
            max_w = kwargs.pop("max_width", None)
            if "height" not in kwargs and min_h is not None:
                kwargs["height"] = min_h
            elif "height" not in kwargs and max_h is not None:
                kwargs["height"] = max_h
            if "width" not in kwargs and min_w is not None:
                kwargs["width"] = min_w
            elif "width" not in kwargs and max_w is not None:
                kwargs["width"] = max_w
            orig_container_init(self, *args, **kwargs)
        ft.Container.__init__ = compat_container_init
        ft.Container._compat_patched = True

def open_dialog(page: ft.Page, dialog: ft.Control):
    """Reliable helper to open a modal dialog in Flet 0.86+ and earlier versions."""
    if hasattr(page, "show_dialog"):
        try:
            page.show_dialog(dialog)
            return
        except Exception:
            pass
    page.dialog = dialog
    dialog.open = True
    page.update()

def close_dialog(page: ft.Page, dialog: ft.Control = None):
    """Reliable helper to close a dialog in Flet 0.86+ and earlier versions."""
    if dialog is not None:
        dialog.open = False
        try:
            dialog.update()
        except Exception:
            pass
    if hasattr(page, "pop_dialog"):
        try:
            page.pop_dialog()
            return
        except Exception:
            pass
    if dialog is not None and hasattr(page, "_remove_dialog"):
        try:
            page._remove_dialog(dialog)
            return
        except Exception:
            pass
    page.dialog = None
    page.update()

def show_feedback_message(page: ft.Page, message: str, is_error: bool = False, duration_ms: int = 4500):
    """Reliable helper to display an animated feedback message on any Flet page."""
    sb = ft.SnackBar(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.ERROR_OUTLINE if is_error else ft.Icons.CHECK_CIRCLE_OUTLINE, color=ft.Colors.WHITE, size=18),
                ft.Text(message, color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.W_500, expand=True)
            ],
            spacing=10
        ),
        bgcolor="#dc2626" if is_error else "#059669",
        duration=duration_ms
    )
    if hasattr(page, "show_dialog"):
        page.show_dialog(sb)
    else:
        page.snack_bar = sb
        page.update()

init_flet_compatibility()
