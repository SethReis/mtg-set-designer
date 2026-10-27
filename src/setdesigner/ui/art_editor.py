"""The card editor's Art section: add art (pick, drop, paste) and choose its crop.

Without art it shows a drop zone. With art: the whole image with the frame's art box
drawn on it (the part outside is dimmed). Drag the box to move it, zoom with the slider.
The crop is saved with the card; the original file is never changed.
"""
from __future__ import annotations

from typing import Callable

from nicegui import run, ui
from PIL import Image

from ..app.art import crop_box, nudge, zoomed
from ..app.assets import AssetError, import_art, remove_art
from ..model import Card
from .widgets import served_url

DROP_HINT = "Drop an image here, paste one with Ctrl+V, or click to choose"


def art_editor(session, card: Card, on_changed: Callable[[], None], face: int = 0):
    """Build the section; returns its refreshable (refresh it when art changes elsewhere)."""

    async def picked(e) -> None:
        try:
            import_art(session, card, await e.file.read(), e.file.name, face)
        except AssetError as error:
            ui.notify(str(error), type="negative")
            return
        panel.refresh()
        on_changed()

    @ui.refreshable
    def panel() -> None:
        art_face = card.faces[face]
        path = session.project.resolve(art_face.art_path)
        has_art = path is not None and path.is_file()
        with ui.column().classes("w-full gap-1").props(f'data-art-card="{card.id}"'):
            ui.label("Art").classes("text-xs text-gray-500")
            picker = ui.upload(label=DROP_HINT, on_upload=picked, auto_upload=True, max_files=1) \
                .props('accept="image/*" flat bordered').classes("w-full")
            if not has_art:
                if art_face.art_path:
                    ui.label(f"The art file {art_face.art_path} is missing.").classes("text-sm text-amber-700")
                return
            picker.classes("hidden")                     # still used by "Replace"
            box = session.art_box(card, face)
            if box is None:                              # first card in this frame: look it up
                ui.label("Measuring the frame's art box…").classes("text-sm text-gray-500")

                async def measure() -> None:
                    await run.io_bound(session.find_art_box, card, face)
                    panel.refresh()
                ui.timer(0.01, measure, once=True)
                return
            crop_editor(path, box[0] / box[1], picker)

    def crop_editor(path, aspect: float, picker) -> None:
        with Image.open(path) as img:
            size = img.size
        state = {"crop": card.faces[face].art_crop, "drag": None}

        def overlay() -> str:
            w, h = size
            left, top, right, bottom = crop_box(size, aspect, state["crop"])
            stroke = max(size) / 160
            return (f'<path d="M0 0H{w}V{h}H0Z M{left} {top}V{bottom}H{right}V{top}Z" '
                    f'fill="black" fill-opacity="0.5" fill-rule="evenodd"/>'
                    f'<rect x="{left}" y="{top}" width="{right - left}" height="{bottom - top}" '
                    f'fill="none" stroke="#facc15" stroke-width="{stroke}"/>')

        def apply(crop) -> None:
            state["crop"] = crop
            image.content = overlay()
            session.update(card, "art_crop", crop, face)
            on_changed()

        def on_mouse(e) -> None:
            if e.type == "mousedown":
                state["drag"] = (e.image_x, e.image_y)
            elif e.type == "mousemove" and state["drag"] is not None and e.buttons & 1:
                x0, y0 = state["drag"]
                state["drag"] = (e.image_x, e.image_y)
                apply(nudge(state["crop"], e.image_x - x0, e.image_y - y0, size, aspect))
            else:                                        # mouseup / mouseleave
                state["drag"] = None

        def zoom(value) -> None:
            apply(zoomed(state["crop"], float(value), size, aspect))

        def reset() -> None:
            zoom_slider.value = 1.0
            apply(None)

        def remove() -> None:
            remove_art(session, card, face)
            panel.refresh()
            on_changed()

        image = ui.interactive_image(served_url(session.folder, path), content=overlay(),
                                     events=["mousedown", "mousemove", "mouseup", "mouseleave"],
                                     on_mouse=on_mouse) \
            .classes("w-full").style("max-width:520px;cursor:move")
        ui.label("Drag the yellow box to choose what shows on the card.").classes("text-xs text-gray-500")
        with ui.row().classes("w-full items-center gap-2"):
            ui.label("Zoom").classes("text-sm")
            zoom_slider = ui.slider(min=1, max=4, step=0.05,
                                    value=state["crop"].zoom if state["crop"] else 1.0) \
                .on("update:model-value", lambda e: zoom(e.args), throttle=0.1) \
                .classes("grow").style("max-width:300px")
            ui.button("Reset", on_click=reset).props("flat dense no-caps")
            ui.button("Replace", on_click=lambda: picker.run_method("pickFiles")).props("flat dense no-caps")
            ui.button("Remove", on_click=remove).props("flat dense no-caps color=negative")

    panel()
    return panel
