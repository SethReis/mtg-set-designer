"""When Magic Set Editor can't draw the cards: one notice, worded the same everywhere
(docs/design/patterns.md, "Blocked renderer"), with the one action that fixes it.

    renderer_notice.check(session)        # once a set is open (finds a block early)
    renderer_notice.notice(session)       # the banner (shell), or compact=True (editor)
    renderer_notice.health(session)       # the shared state: kind, phase, version

Windows' Smart App Control trusts the unsigned MSE for about a day after it was opened
through Windows' own launcher. When that lapses, cards are drawn by our built-in renderer
(the "stand-in"), and they look a little off. The notice says so plainly and offers
**Renew Magic Set Editor** (app/mse_trust.py), which normally needs nothing else from the
user. Every notice watches the same state, so renewing in one place updates them all,
and the workspace and the editor redraw their pictures once MSE works again.
"""
from __future__ import annotations

import asyncio
import time
import weakref
from dataclasses import dataclass
from datetime import datetime

from nicegui import run, ui

from ..app import mse_trust
from . import components as c

POLL = 0.5                       # seconds between notice updates
MANUAL_POLL = 3.0                # seconds between checks while the user opens MSE themselves
MANUAL_WAIT = 180.0              # how long to keep checking after that
FIXED_SHOWN = 6.0                # seconds the "working again" message stays

PROBLEMS = {"blocked", "missing", "failed"}


@dataclass
class RendererHealth:
    kind: str = "unknown"        # "ok", "off", "blocked", "missing", "failed" (mse_status) or "unknown"
    message: str = ""
    phase: str = ""              # "", "renewing", "manual" (the user opens MSE), "fixed"
    dismissed: bool = False      # "Not now": the banner hides (the top bar keeps a chip)
    fixed_at: float = 0.0
    version: int = 0             # goes up on every change: notices redraw then

    def update(self, **values) -> None:
        for key, value in values.items():
            setattr(self, key, value)
        self.version += 1

    @property
    def problem(self) -> bool:
        return self.kind in PROBLEMS


_HEALTH: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def health(session) -> RendererHealth:
    if session not in _HEALTH:
        _HEALTH[session] = RendererHealth()
    return _HEALTH[session]


async def check(session) -> None:
    """Ask whether MSE can draw the cards (starts it; done in the background)."""
    status = await run.io_bound(session.mse_status)
    if not status:                               # the set was closed meanwhile
        return
    kind, message = status
    h = health(session)
    if h.phase not in ("renewing", "manual") and (kind, message) != (h.kind, h.message):
        h.update(kind=kind, message=message)


def watch(session) -> None:
    """Notice a block that happened while drawing (cheap: for timers)."""
    h = health(session)
    if session.mse_blocked and h.kind != "blocked" and h.phase not in ("renewing", "manual"):
        h.update(kind="blocked", phase="", message=session.mse_problem())
    if h.phase == "fixed" and time.monotonic() - h.fixed_at > FIXED_SHOWN:
        h.update(phase="")


async def renew(session) -> None:
    """The Renew button: a hidden launch through Windows' launcher; if Windows wants the
    user to do it, open MSE's folder and close MSE again for them once it works."""
    h = health(session)
    if h.phase in ("renewing", "manual"):
        return
    h.update(phase="renewing", dismissed=False)
    route = await run.io_bound(mse_trust.renew, session)
    if route:
        h.update(kind="ok", message="", phase="fixed", fixed_at=time.monotonic())
        return
    gui = session.mse_gui()
    if gui is None:
        h.update(phase="")
        return
    since = datetime.now()
    h.update(phase="manual")
    mse_trust.show_in_folder(gui)
    deadline = time.monotonic() + MANUAL_WAIT
    while time.monotonic() < deadline:
        await asyncio.sleep(MANUAL_POLL)
        kind, _ = await run.io_bound(session.retry_mse)
        if kind == "ok":
            await run.io_bound(mse_trust.end_started_after, gui, since)
            h.update(kind="ok", message="", phase="fixed", fixed_at=time.monotonic())
            return
    h.update(phase="")                           # gave up waiting: back to the plain notice


def why_dialog(parent: ui.element) -> None:
    with c.modal("sm", "Why does Magic Set Editor need renewing?", parent=parent, persistent=False) as m:
        for text in (
                "Your cards are drawn by Magic Set Editor, a separate program. Windows' Smart App "
                "Control only lets programs run in the background once it trusts them.",
                "Magic Set Editor isn't signed by a company, so Windows trusts it for about a day "
                "after it has been opened through Windows itself. When that runs out, Set Designer "
                "draws cards with a stand-in renderer, which gets the layout right but not every "
                "detail of the text and symbols.",
                "Renew asks Windows to trust Magic Set Editor again. Nothing opens and there's "
                "nothing to close. It isn't a virus warning, and nothing is wrong with your set.",
                "You may see this again the next day. The alternative is turning Smart App Control "
                "off in Windows Security (App & browser control); that's your choice, and Windows "
                "may not let you turn it back on."):
            ui.label(text).classes("ds-why-text")
    m.open()


def notice(session, *, compact: bool = False, dismissable: bool = True) -> ui.element:
    """The notice, redrawn whenever the shared state changes. `compact`: one line, for
    the editor's preview; otherwise the full banner, with "Not now" when `dismissable`
    (the app-wide banner; the Print dialog's notice always shows)."""
    outer = ui.element("div").classes("ds-renderer-notice-host w-full")
    seen = {"version": -1}

    with outer:
        @ui.refreshable
        def body() -> None:
            h = health(session)
            if h.phase == "fixed":
                with ui.element("div").classes("ds-renderer-notice ok" + (" compact" if compact else "")):
                    ui.icon("check_circle")
                    ui.label("Magic Set Editor is working again. Redrawing your cards…").classes("title")
                return
            if not h.problem or (h.dismissed and dismissable and not compact):
                return
            classes = "ds-renderer-notice" + (" compact" if compact else "")
            if h.kind != "blocked":
                with ui.element("div").classes(classes + " info"):
                    ui.icon("info")
                    with ui.element("div").classes("text"):
                        ui.label("Cards are drawn by a stand-in renderer and won't look quite right.") \
                            .classes("title")
                        if not compact:
                            ui.label(("Magic Set Editor isn't set up for this app yet (see the README, "
                                      "“Setup”)." if h.kind == "missing" else h.message)).classes("detail")
                    if dismissable and not compact:
                        c.button("Not now", kind="ghost", on_click=lambda: h.update(dismissed=True)).props("dense")
                return
            with ui.element("div").classes(classes).mark("renderer-notice"):
                if h.phase == "renewing":
                    ui.spinner(size="20px")
                    ui.label("Asking Windows to trust Magic Set Editor…").classes("title")
                    return
                ui.icon("warning")
                with ui.element("div").classes("text"):
                    if h.phase == "manual":
                        ui.label("Windows wants you to open Magic Set Editor yourself this time.") \
                            .classes("title")
                        ui.label("Double-click magicseteditor.exe in the folder that just opened. It "
                                 "closes again on its own once Windows trusts it.").classes("detail")
                    elif compact:
                        ui.label("Stand-in renderer: Windows is blocking Magic Set Editor, so this "
                                 "preview won't look quite right.").classes("title")
                    else:
                        ui.label("Your cards are being drawn by a stand-in renderer and won't look "
                                 "quite right.").classes("title")
                        ui.label("Windows only lets Magic Set Editor draw cards for about a day after "
                                 "it was opened through Windows. One click renews that.").classes("detail")
                with ui.row().classes("actions no-wrap items-center gap-1"):
                    if h.phase == "manual":
                        c.button("Open the folder again", kind="secondary",
                                 on_click=lambda: mse_trust.show_in_folder(session.mse_gui())).props("dense")
                    else:
                        c.button("Renew Magic Set Editor", kind="primary", icon="autorenew",
                                 on_click=lambda: renew(session),
                                 tooltip="Asks Windows to trust Magic Set Editor again. Nothing opens.") \
                            .props("dense").mark("renew-mse")
                    c.button("Why?" if compact else "Why is this needed?", kind="ghost",
                             on_click=lambda: why_dialog(outer)).props("dense")
                    if dismissable and not compact and h.phase != "manual":
                        c.button("Not now", kind="ghost", on_click=lambda: h.update(dismissed=True)) \
                            .props("dense").mark("renderer-not-now")

        body()

        def tick() -> None:
            watch(session)
            if health(session).version != seen["version"]:
                seen["version"] = health(session).version
                body.refresh()

        ui.timer(POLL, tick)
    return outer
