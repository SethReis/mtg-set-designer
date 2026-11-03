"""The Print dialog (docs/print.md): choose what to print and how, see the pages, save a PDF.

    print_dialog(state, cards=all_cards, filtered=overview_cards, parent=..., on_close=...)

Options are remembered in the user's settings (not the set). The preview shows the
pages with the overview's pictures (or text tiles, for printer-friendly prints); the
PDF itself is made in the background (app/printing.py) and saved where the user picks
(a Save As dialog in the desktop window; a download in a browser).
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from nicegui import app, run, ui

from ..app.printing import Cancelled, export_pdf
from ..export.selection import (BLEEDS, DISTRIBUTIONS, SORTS, STYLES, PrintOptions,
                                print_faces)
from ..export.sheet import PAPERS, fit, pages
from ..model import Card, Rarity
from . import components as c
from .widgets import compact_tile, served_url

PREVIEW_WIDTH = 120                     # px of a card in the page preview (text size)
POLL = 0.2                              # seconds between progress updates


def print_dialog(state, *, cards: list[Card], filtered: list[Card] | None, parent, on_close=None) -> c.Modal:
    """`filtered`: the overview's cards when a filter is on (offered as "Current filter")."""
    session, settings = state.session, state.settings
    options = PrintOptions.from_dict(settings.print_options)
    if filtered is None and options.scope == "filter":
        options.scope = "set"
    view = {"page": 0}
    job = {"cancel": None, "text": "", "fraction": 0.0, "running": False}

    def chosen() -> list[Card]:
        return filtered if options.scope == "filter" and filtered is not None else cards

    def save_options() -> None:
        settings.print_options = options.to_dict()
        settings.save(state.settings_path)

    def set_option(**values) -> None:
        for key, value in values.items():
            setattr(options, key, value)
        view["page"] = 0
        save_options()
        copies_row.set_visibility(options.distribution == "rarity")
        preview.refresh()

    def set_copies(rarity: Rarity, value) -> None:
        options.copies[rarity.value] = max(0, int(value or 0))
        save_options()
        preview.refresh()

    with c.modal("lg", "Print", parent=parent, footer=True, persistent=False, on_close=on_close,
                 subtitle="Paper proxies: every face is its own card") as m:
        renderer_warning = c.status("", "warning").classes("ds-print-warning")
        renderer_warning.set_visibility(False)
        with ui.element("div").classes("ds-print"):
            # ---- options
            with ui.element("div").classes("ds-print-options"):
                if filtered is not None:
                    c.label("Cards")
                    c.segmented({"set": f"Whole set · {len(cards)}", "filter": f"Current filter · {len(filtered)}"},
                                options.scope, lambda e: set_option(scope=e.value)).mark("print-scope")
                c.label("Copies")
                c.segmented(DISTRIBUTIONS, options.distribution,
                            lambda e: set_option(distribution=e.value)).mark("print-copies")
                copies_row = ui.element("div").classes("ds-print-copies")
                with copies_row:
                    for rarity in (Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.MYTHIC):
                        ui.number(rarity.value.title(), value=options.copies.get(rarity.value, 1), min=0,
                                  format="%d", on_change=lambda e, r=rarity: set_copies(r, e.value)) \
                            .props("dense").mark(f"copies-{rarity.value}")
                copies_row.set_visibility(options.distribution == "rarity")
                c.hint("A card's own Print copies (in the editor) wins over its rarity.") \
                    .bind_visibility_from(copies_row, "visible")
                c.label("Style")
                c.segmented(STYLES, options.style, lambda e: set_option(style=e.value)).mark("print-style")
                c.hint("Printer-friendly: no art or frame, plain symbols, thin borders — saves ink.")
                c.label("Paper")
                c.segmented({k: v[0] for k, v in PAPERS.items()}, options.paper,
                            lambda e: set_option(paper=e.value))
                with ui.element("div").classes("ds-print-pair"):
                    ui.select({b: "None" if not b else f"{b:g} mm" for b in BLEEDS}, label="Bleed",
                              value=options.bleed_mm if options.bleed_mm in BLEEDS else 0.0,
                              on_change=lambda e: set_option(bleed_mm=float(e.value))) \
                        .tooltip("Extra picture around each card, so a slightly off cut shows no white")
                    ui.select({k: v[0] for k, v in SORTS.items()}, label="Order", value=options.sort,
                              on_change=lambda e: set_option(sort=e.value))
                ui.switch("Crop marks", value=options.crop_marks,
                          on_change=lambda e: set_option(crop_marks=e.value))
                ui.switch("Labels under cards", value=options.labels,
                          on_change=lambda e: set_option(labels=e.value)) \
                    .tooltip("Set code, number and face in small print, to sort the printout")

            # ---- page preview
            with ui.element("div").classes("ds-print-preview"):
                @ui.refreshable
                def preview() -> None:
                    faces = print_faces(chosen(), options)
                    grid = fit(options.paper, options.bleed_mm, options.spacing_mm, options.labels)
                    sheets = pages(faces, grid)
                    view["page"] = min(view["page"], max(0, len(sheets) - 1))
                    with ui.row().classes("w-full items-center gap-2 no-wrap"):
                        n = len(faces)
                        ui.label(f"{n} card{'s' * (n != 1)} · {len(sheets)} page{'s' * (len(sheets) != 1)} · "
                                 f"{grid.columns} × {grid.rows} per page").classes("muted").mark("print-summary")
                        ui.space()
                        if len(sheets) > 1:
                            c.button(icon="chevron_left", kind="icon", tooltip="Previous page",
                                     on_click=lambda: turn(-1)).props("dense")
                            ui.label(f"{view['page'] + 1} / {len(sheets)}").classes("num")
                            c.button(icon="chevron_right", kind="icon", tooltip="Next page",
                                     on_click=lambda: turn(1)).props("dense")
                    if not sheets:
                        c.empty_state("print", "Nothing to print",
                                      "Every card is set to 0 copies, or the filter shows no cards.")
                        return
                    page_w, page_h = grid.page
                    with ui.element("div").classes("ds-print-page").style(f"aspect-ratio:{page_w}/{page_h}"):
                        for slot in sheets[view["page"]]:
                            face = slot.item
                            style = (f"left:{slot.x / page_w * 100:.3f}%;top:{slot.y / page_h * 100:.3f}%;"
                                     f"width:{grid.card[0] / page_w * 100:.3f}%;"
                                     f"height:{grid.card[1] / page_h * 100:.3f}%")
                            with ui.element("div").classes("ds-print-card").style(style):
                                slot_picture(face)

                def turn(step: int) -> None:
                    view["page"] += step
                    preview.refresh()

                def slot_picture(face) -> None:
                    """The overview's picture of the face (fronts only), else its text."""
                    path = session.thumbnails.get(face.card) if face.face == 0 else None
                    if options.style == "rendered" and path is not None:
                        ui.element("img").props(f'src="{served_url(session.thumbnails.cache.folder, path)}" '
                                                f'draggable=false alt=""')
                    elif face.face == 0:
                        compact_tile(face.card, PREVIEW_WIDTH)
                    else:
                        with ui.element("div").classes("ds-text-tile"):
                            ui.label(face.card.faces[face.face].name or "(back)").classes("name")
                            ui.label(face.card.faces[face.face].type_line).classes("type")

                preview()

        # ---- footer: progress, then Export
        with m.footer:
            progress = ui.linear_progress(value=0, show_value=False).classes("ds-print-progress")
            progress.set_visibility(False)
            status = ui.label("").classes("muted truncate")
            ui.space()
            saved: dict[str, Path | None] = {"path": None}
            open_button = c.button("Open PDF", kind="ghost", icon="open_in_new",
                                   on_click=lambda: saved["path"] and os.startfile(saved["path"]))  # noqa: S606
            open_button.set_visibility(False)
            cancel_button = c.button("Cancel", kind="ghost", on_click=lambda: job["cancel"] and job["cancel"].set())
            cancel_button.set_visibility(False)
            export_button = c.button("Export PDF", kind="primary", icon="picture_as_pdf",
                                     on_click=lambda: export()).mark("print-export")

    def show_progress() -> None:
        if job["running"]:
            progress.value = job["fraction"]
            status.text = job["text"]

    ui.timer(POLL, show_progress)

    async def check_renderer() -> None:
        """Say up front when rendered prints won't come from MSE (e.g. Windows blocks it)."""
        problem = await run.io_bound(session.mse_problem)
        if problem and not renderer_warning.is_deleted:
            renderer_warning.text = f"{problem}. Rendered prints will look slightly different from MSE's."
            renderer_warning.set_visibility(True)

    ui.timer(0, check_renderer, once=True)

    def report(text: str, fraction: float) -> None:          # from the export thread
        job["text"], job["fraction"] = text, fraction

    async def target() -> Path | None:
        """Where to save: the system's Save As in the desktop window, else a temp file."""
        name = f"{session.project.info.code or 'set'}-print.pdf"
        if app.native.main_window is None:
            folder = Path(tempfile.mkdtemp(prefix="setdesigner-print-"))
            return folder / name
        import webview
        dialog = getattr(webview, "FileDialog", None)
        kind = dialog.SAVE if dialog else webview.SAVE_DIALOG
        start = settings.print_folder if settings.print_folder and Path(settings.print_folder).is_dir() \
            else str(Path.home() / "Documents")
        result = await app.native.main_window.create_file_dialog(
            dialog_type=kind, directory=start, save_filename=name, file_types=("PDF files (*.pdf)",))
        if not result:
            return None
        path = Path(result if isinstance(result, str) else result[0])
        return path if path.suffix.lower() == ".pdf" else path.with_suffix(".pdf")

    async def export() -> None:
        selected = chosen()
        if not print_faces(selected, options):
            ui.notify("Nothing to print", type="warning")
            return
        path = await target()
        if path is None:
            return
        session.flush()
        job.update(cancel=threading.Event(), text="Starting…", fraction=0.0, running=True)
        export_button.disable()
        open_button.set_visibility(False)
        cancel_button.set_visibility(True)
        progress.set_visibility(True)
        try:
            result = await run.io_bound(export_pdf, session, selected, options, path,
                                        progress=report, cancel=job["cancel"])
        except Cancelled:
            path.unlink(missing_ok=True)
            status.text = "Cancelled"
            return
        except Exception as e:                    # shown, not raised: the dialog stays usable
            path.unlink(missing_ok=True)
            status.text = ""
            ui.notify(f"Could not make the PDF: {e}", type="negative", multi_line=True)
            return
        finally:
            job["running"] = False
            if not export_button.is_deleted:
                export_button.enable()
                cancel_button.set_visibility(False)
                progress.set_visibility(False)
        settings.print_folder = str(path.parent)
        save_options()
        status.text = f"Saved {result.pages} page{'s' * (result.pages != 1)} to {path.name}"
        if result.builtin:
            ui.notify((result.renderer_note or "Magic Set Editor couldn't draw the cards, so the built-in "
                       "renderer did") + ". Text may sit slightly differently than in MSE's pictures.",
                      type="warning", multi_line=True, timeout=0, close_button="OK")
        if result.overflow:
            ui.notify(f"Text cut short on: {', '.join(result.overflow[:5])}"
                      + (f" and {len(result.overflow) - 5} more" if len(result.overflow) > 5 else ""),
                      type="warning", multi_line=True)
        if app.native.main_window is None:
            ui.download.file(path)
        else:
            saved["path"] = path
            open_button.set_visibility(True)
            ui.notify(f"Saved {path.name}", type="positive")

    m.open()
    return m
