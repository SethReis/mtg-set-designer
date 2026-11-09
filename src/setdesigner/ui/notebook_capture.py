"""Quick capture: a small dialog that drops an idea into the notebook's Inbox, from
anywhere in a set (Ctrl+Shift+N, the top bar's lightbulb, a card's or a slot's menu)."""
from __future__ import annotations

from typing import Callable

from nicegui import ui

from ..model import Idea
from ..model.notebook import KINDS
from . import components as c


def capture_idea(state, *, parent: ui.element, prefill: dict | None = None,
                 on_saved: Callable[[Idea], None] | None = None) -> c.Modal:
    """Open the capture dialog. `prefill`: Idea fields to start from (kind, title, body,
    colors, links…)."""
    session, settings = state.session, state.settings
    prefill = dict(prefill or {})

    with c.modal("md", "Catch an idea", parent=parent, footer=True, persistent=False) as m:
        kind = c.segmented({k: v for k, v in KINDS.items()}, prefill.pop("kind", "card")).mark("capture-kind")
        title = ui.input("Title", value=prefill.pop("title", ""),
                         placeholder="A flier that surveils when it attacks").classes("w-full") \
            .mark("capture-title")
        body = ui.textarea("Notes", value=prefill.pop("body", "")).props("autogrow").classes("w-full") \
            .mark("capture-body")
        tags = ui.input_chips("Tags", value=list(prefill.pop("tags", [])), new_value_mode="add-unique") \
            .classes("w-full").mark("capture-tags")
        c.hint("Lands in the notebook's Inbox · Ctrl+Enter saves")

        def save(again: bool = False) -> None:
            if not (title.value or "").strip() and not (body.value or "").strip():
                ui.notify("Write a title or a note first", type="warning")
                return
            idea = session.new_idea(kind.value or "card", title.value or "", author=settings.author,
                                    body=body.value or "", tags=list(tags.value or []), **prefill)
            if on_saved:
                on_saved(idea)
            if again:
                title.value, body.value = "", ""
                title.run_method("focus")
                ui.notify("Idea saved", type="positive")
            else:
                m.dialog.close()

        with m.footer:
            c.button("Cancel", kind="ghost", on_click=m.dialog.close)
            c.button("Save & another", kind="secondary", on_click=lambda: save(True)).mark("capture-again")
            c.button("Save", kind="primary", on_click=lambda: save()).mark("capture-save")
        m.card.on("keydown.ctrl.enter", lambda: save())
    m.open()
    title.run_method("focus")
    return m
