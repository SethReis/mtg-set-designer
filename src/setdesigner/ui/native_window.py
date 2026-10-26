"""Spelling suggestions in the desktop window.

The window is WebView2 (through pywebview), which underlines misspelled words, but
pywebview turns WebView2's right-click menu off (it only allows it in debug mode, along
with developer tools and browser shortcuts). That menu is where spelling suggestions
are picked, so we turn it back on for text fields only.

NiceGUI opens the window in a separate process. That process unpickles the window's
start arguments before it creates the window, and `window_started` is one of them
(pywebview's `func`), so importing this module there is our chance to adjust pywebview
in time. The main process imports it too and leaves pywebview alone.
"""
from __future__ import annotations

import multiprocessing


def _show_menu_only_in_text_fields(_sender, args) -> None:
    """WebView2 ContextMenuRequested: keep the menu (spelling suggestions, cut/copy/
    paste) in text fields; elsewhere it would only offer Back, Reload, Print, ..."""
    if not args.ContextMenuTarget.IsEditable:
        args.Handled = True                    # handled = no menu


def _enable_text_field_menus() -> None:
    try:
        from webview.platforms import edgechromium
    except Exception:                          # not Windows / no WebView2: nothing to do
        return
    original = edgechromium.EdgeChrome.on_webview_ready
    if getattr(original, "patched", False):
        return

    def on_webview_ready(self, sender, args):
        original(self, sender, args)
        if args.IsSuccess:
            sender.CoreWebView2.Settings.AreDefaultContextMenusEnabled = True
            sender.CoreWebView2.ContextMenuRequested += _show_menu_only_in_text_fields

    on_webview_ready.patched = True
    edgechromium.EdgeChrome.on_webview_ready = on_webview_ready


def window_started() -> None:
    """Passed as pywebview's start `func` (it runs once the window is starting)."""


if multiprocessing.current_process().name != "MainProcess":
    _enable_text_field_menus()
