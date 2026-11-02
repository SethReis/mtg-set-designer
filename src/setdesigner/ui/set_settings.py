"""The Set settings dialog: set-wide fields and the set symbol (with rarity previews and
the small-size advice). Text fields save when you leave them: set-wide changes restart
the renderer, which shouldn't happen on every keystroke."""
from __future__ import annotations

from nicegui import ui

from ..app.assets import AssetError, import_symbol
from ..app.symbol_check import check_symbol
from ..model import Rarity
from ..mse.script.values import ScriptError
from ..render.symbol import symbol_image
from . import components as c

PREVIEW_RARITIES = [("common", "Common"), ("uncommon", "Uncommon"), ("rare", "Rare"),
                    ("mythic rare", "Mythic")]
CARD_SIZE = 20                  # the symbol's height on an M15 card at 150 dpi
LARGE_SIZE = 72


def set_settings(session, frame_labels: dict[str, str], *, parent, on_close=None) -> c.Modal:
    """Open the dialog (an md modal in `parent`); `on_close` runs after it closes."""
    info = session.project.info

    def save(**values) -> None:
        if any(getattr(info, key) != value for key, value in values.items()):
            session.update_info(**values)

    def save_slot(rarity: Rarity, value) -> None:
        slots = {r.value: n for r, n in info.rarity_slots.items()}
        slots[rarity.value] = int(value or 0)
        save(rarity_slots={Rarity(r): n for r, n in slots.items() if n})

    async def symbol_picked(e) -> None:
        try:
            import_symbol(session, await e.file.read(), e.file.name)
        except AssetError as error:
            ui.notify(str(error), type="negative")
            return
        e.sender.reset()
        symbol_section.refresh()

    with c.modal("md", "Set settings", parent=parent, footer=True, persistent=False,
                 on_close=on_close) as m:
        with ui.element("div").classes("w-full") \
                .style("display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px"):
            name = ui.input("Set name", value=info.name)
            name.on("blur", lambda: save(name=name.value.strip() or info.name))
            code = ui.input("Code", value=info.code)
            code.on("blur", lambda: save(code=(code.value.strip() or info.code).upper()))
            ui.select(frame_labels, value=info.default_frame, label="Default frame",
                      on_change=lambda e: save(default_frame=e.value))
            artist = ui.input("Default artist", value=info.artist)
            artist.on("blur", lambda: save(artist=artist.value))
            copyright_ = ui.input("Copyright line", value=info.copyright)
            copyright_.on("blur", lambda: save(copyright=copyright_.value))

        ui.label("Cards wanted per rarity").classes("ds-form-h")
        c.hint("Shown as “18 / 20” in the overview.")
        with ui.row().classes("gap-2"):
            for rarity in Rarity:
                field = ui.number(rarity.value.title(), value=info.rarity_slots.get(rarity), min=0,
                                  format="%d").props("dense").classes("w-24")
                field.on("blur", lambda f=field, r=rarity: save_slot(r, f.value))

        ui.label("Set symbol").classes("ds-form-h")

        @ui.refreshable
        def symbol_section() -> None:
            path = session.project.resolve(info.symbol_path)
            ui.upload(label="Drop a PNG (or SVG) here, or click to choose", on_upload=symbol_picked,
                      auto_upload=True, max_files=1) \
                .props('accept=".png,.svg,image/*" flat bordered').classes("w-full")
            if path is None or not path.is_file():
                c.hint("No symbol yet: cards show a plain placeholder.")
            try:
                previews = [(label, symbol_image(str(path) if path else None, v, CARD_SIZE),
                             symbol_image(str(path) if path else None, v, LARGE_SIZE))
                            for v, label in PREVIEW_RARITIES]
                advice = check_symbol(path)
            except ScriptError as error:              # e.g. SVG without cairosvg
                ui.label(f"{error}. Use a PNG with a transparent background instead.") \
                    .classes("text-negative")
                return
            with ui.row().classes("gap-6 items-end"):
                for label, small, large in previews:
                    with ui.column().classes("items-center gap-1"):
                        ui.image(large).style(f"width:{large.width}px;height:{large.height}px")
                        with ui.row().classes("ds-symbol-chip items-center gap-2 px-2 py-1"):
                            ui.image(small).style(f"width:{small.width}px;height:{small.height}px")
                            ui.label("card size").classes("text-xs")
                        ui.label(label).classes("text-sm")
            for message in advice:
                c.status(message, "warning").classes("whitespace-normal")
        symbol_section()

    with m.footer:
        c.button("Done", kind="primary", on_click=m.close)
    m.open()
    return m
