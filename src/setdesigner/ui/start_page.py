"""The start page: recent sets as a grid of cards, opening a folder, and a new set (a
modal, or right on the page when there are no sets yet)."""
from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

from ..app.session import SessionError, SetSession
from ..model.project import load_summary, slug
from . import components as c
from . import theme
from .widgets import responsive_grid, served_url


def register(state) -> None:
    from .app import FRAME_LABELS

    def open_folder(folder: Path) -> None:
        try:
            session = SetSession.open(folder, renderer_factory=state.renderer_factory)
        except SessionError as e:
            ui.notify(str(e), type="negative")
            return
        state.open_session(session)
        ui.navigate.to("/set")

    async def choose_folder() -> None:
        """The system folder picker (desktop window only)."""
        import webview
        dialog = getattr(webview, "FileDialog", None)
        kind = dialog.FOLDER if dialog else webview.FOLDER_DIALOG
        result = await app.native.main_window.create_file_dialog(dialog_type=kind,
                                                                 directory=str(state.sets_root))
        if result:
            open_folder(Path(result[0]))

    def new_set_form(on_cancel=None) -> None:
        """Name, code, frame and folder, then "Create set"."""
        with responsive_grid(200):
            name = ui.input("Set name").props("autofocus outlined").classes("w-full")
            code = ui.input("Code (3-4 letters)").props("outlined").classes("w-full")
            frame = ui.select(FRAME_LABELS, value="m15", label="Default frame").props("outlined") \
                .classes("w-full")
        folder = ui.input("Folder").props("outlined").classes("w-full mt-3")
        c.hint("Where the set's files go. It can be any folder, e.g. a git repository.")

        def suggest_folder() -> None:
            base = code.value.strip() or name.value.strip()
            if base:
                folder.value = str(state.sets_root / slug(base))
        name.on_value_change(lambda _: not code.value and suggest_folder())
        code.on_value_change(lambda _: suggest_folder())

        def create() -> None:
            try:
                session = SetSession.create(Path(folder.value or state.sets_root / slug(code.value)),
                                            name.value, code.value, frame.value,
                                            renderer_factory=state.renderer_factory)
            except (SessionError, OSError) as e:
                ui.notify(str(e), type="negative")
                return
            state.open_session(session)
            ui.navigate.to("/set")

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            if on_cancel:
                c.button("Cancel", kind="ghost", on_click=on_cancel)
            c.button("Create set", kind="primary", on_click=create)

    def set_card(folder: Path) -> None:
        """A recent set: symbol, name, code, card count. Click to open it."""
        try:
            info, count = load_summary(folder)
        except (OSError, ValueError):
            return
        with ui.element("div").classes("ds-set-card").on("click", lambda: open_folder(folder)) \
                .mark(f"recent-{folder.name}").tooltip(str(folder)):
            symbol = folder / info.symbol_path if info.symbol_path else None
            with ui.element("div").classes("ds-set-symbol"):
                if symbol is not None and symbol.is_file() and symbol.suffix.lower() != ".svg":
                    ui.element("img").props(f'src="{served_url(folder, symbol)}" alt=""')
                else:
                    ui.icon("style")
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(info.name or folder.name).classes("display text-[17px] truncate")
                with ui.row().classes("gap-2 items-center no-wrap"):
                    ui.label(info.code).classes("faint")
                    ui.label(f"{count} card{'s' * (count != 1)}").classes("muted num")

    @ui.page("/")
    def start_page() -> None:
        theme.mode(state.settings.theme)
        recent = state.settings.existing_recent()
        dialogs = ui.element("div")

        def new_set() -> None:
            with c.modal("md", "New set", parent=dialogs, persistent=False) as m:
                new_set_form(on_cancel=m.close)
            m.open()

        with ui.element("div").classes("ds-start"):
            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                ui.icon("style").classes("text-[30px]").style("color: var(--accent)")
                ui.label("Set Designer").classes("display text-[30px]")
                ui.space()
                if app.native.main_window is not None:
                    c.button("Open folder…", kind="secondary", icon="folder_open", on_click=choose_folder)
                if recent:
                    c.button("New set", kind="primary", icon="add", on_click=new_set)
            c.hint("Design a Magic set: its cards, mechanics, cycles and balance, in one place.") \
                .classes("mb-6 block")

            if recent:
                ui.label("Recent sets").classes("ds-form-h")
                with ui.element("div").classes("ds-set-grid"):
                    for folder in recent:
                        set_card(folder)
            else:
                with ui.element("div").classes("ds-section ds-start-first"):
                    ui.label("Start your first set").classes("ds-section-title")
                    c.hint("Everything can be changed later in Set settings.").classes("mb-3 block")
                    new_set_form()

            with ui.expansion("Open a set by its folder", icon="folder").classes("w-full mt-6") \
                    .props("dense"):
                with ui.row().classes("w-full items-center no-wrap gap-2"):
                    path = ui.input("Set folder").props("outlined dense").classes("grow")
                    c.button("Open", kind="secondary", on_click=lambda: open_folder(Path(path.value)))
