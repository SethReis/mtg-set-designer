"""Renewing Windows' trust in Magic Set Editor, when the user asks for it. No UI code.

    route = renew(session)        # "hidden-cli", "hidden-gui", or "" (Windows said no)

Windows' Smart App Control lets the unsigned MSE run in the background only for about a
day after it was opened through Windows' own launcher (a double-click does that). When
that lapses, the app's MSE is blocked (render/mse_service.MSEBlocked) and cards fall back
to the built-in renderer. The user's "Renew" button runs MSE once through that same
launcher, hidden, with --version (it prints its version and exits), so nothing opens:

  1. magicseteditor.com --version, hidden
  2. magicseteditor.exe --version, hidden (ended by us once MSE works, or after 10 s)

After each, the app tries its own MSE again. If neither helps, the UI asks the user to
double-click MSE themselves (show_in_folder), and end_started_after closes that window
for them once MSE works. Which route worked is logged, to learn which ones Windows takes.

This is a stopgap: the aim is a renderer that needs no MSE program at all.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..render.mse_service import FAKE_BLOCK

log = logging.getLogger(__name__)

WAIT = 10.0                     # seconds a hidden launch may take
POLL = 0.5


class Launcher(Protocol):
    def start(self, exe: Path, args: str) -> object | None: ...      # a process handle, or None
    def running(self, handle: object) -> bool: ...
    def end(self, handle: object) -> None: ...                       # stop it if needed, release it


class WindowsLauncher:
    """Starts a program through ShellExecuteEx (Windows' own launcher), hidden."""

    def start(self, exe: Path, args: str) -> object | None:
        import ctypes
        from ctypes import wintypes

        class ShellExecuteInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
                        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                        ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                        ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
                        ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                        ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

        see_mask_nocloseprocess, see_mask_flag_no_ui, sw_hide = 0x40, 0x400, 0
        info = ShellExecuteInfo(cbSize=ctypes.sizeof(ShellExecuteInfo),
                                fMask=see_mask_nocloseprocess | see_mask_flag_no_ui,
                                lpVerb="open", lpFile=str(exe), lpParameters=args,
                                lpDirectory=str(exe.parent), nShow=sw_hide)
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            log.info("Windows refused to start %s (error %s)", exe.name, ctypes.GetLastError())
            return None
        return info.hProcess

    def running(self, handle: object) -> bool:
        import ctypes
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x102     # WAIT_TIMEOUT

    def end(self, handle: object) -> None:
        import ctypes
        if self.running(handle):
            ctypes.windll.kernel32.TerminateProcess(handle, 0)
        ctypes.windll.kernel32.CloseHandle(handle)


def renew(session, launcher: Launcher | None = None) -> str:
    """Run MSE once through Windows' launcher, hidden, then try the app's MSE again.
    Returns the route that worked ("hidden-cli", "hidden-gui"), or "" if Windows still
    blocks it. Blocks for up to ~20 s: call it off the UI thread."""
    if FAKE_BLOCK["on"]:                         # dev switch: pretend the renewal worked
        FAKE_BLOCK["on"] = False
        return "fake" if session.retry_mse()[0] == "ok" else ""
    gui = session.mse_gui()
    if gui is None:
        return ""
    launcher = launcher or WindowsLauncher()
    for route, exe in (("hidden-cli", gui.with_suffix(".com")), ("hidden-gui", gui)):
        if not exe.is_file():
            continue
        handle = launcher.start(exe, "--version")
        if handle is None:
            continue
        works = False
        try:
            deadline = time.monotonic() + WAIT
            while launcher.running(handle) and time.monotonic() < deadline:
                time.sleep(POLL)
            works = session.retry_mse()[0] == "ok"
        finally:
            launcher.end(handle)                 # whatever we started, we end
        if works:
            log.info("Windows trusts Magic Set Editor again (route: %s)", route)
            return route
    log.info("Windows still blocks Magic Set Editor after a hidden launch")
    return ""


def show_in_folder(exe: Path) -> None:
    """Open Explorer with the program selected, for the user to double-click."""
    subprocess.Popen(["explorer", f"/select,{exe}"])


def end_started_after(exe: Path, since: datetime) -> int:
    """Close MSE windows the user opened from `exe` after `since` (the manual route), so
    they never have to close it themselves. Returns how many were closed."""
    if os.name != "nt":
        return 0
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $env:SD_EXE -and "
              "$_.CreationDate -ge [datetime]$env:SD_SINCE } | ForEach-Object { "
              "Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }")
    env = {**os.environ, "SD_EXE": str(exe), "SD_SINCE": since.isoformat(sep=" ", timespec="seconds")}
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                          capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    closed = len(done.stdout.split())
    if closed:
        log.info("Closed %d Magic Set Editor window(s) the user opened to renew trust", closed)
    return closed
