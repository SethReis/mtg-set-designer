"""Start page: create a new set or open one."""
from __future__ import annotations

from pathlib import Path

from nicegui import app, ui

from ..app.session import SessionError, SetSession
from ..model.project import slug


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

    @ui.page("/")
    def start_page() -> None:
        ui.label("Set Designer").classes("text-3xl font-bold mt-6 mx-auto")
        with ui.row().classes("w-full justify-center gap-8 mt-6 items-start"):
            with ui.card().classes("w-96"):
                ui.label("New set").classes("text-xl font-semibold")
                name = ui.input("Set name").props("autofocus").classes("w-full")
                code = ui.input("Code (3-4 letters)").classes("w-full")
                frame = ui.select(FRAME_LABELS, value="m15", label="Default frame").classes("w-full")
                folder = ui.input("Folder").classes("w-full")

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

                ui.button("Create set", on_click=create).props("color=primary").classes("mt-2")

            with ui.card().classes("w-96"):
                ui.label("Open a set").classes("text-xl font-semibold")
                if app.native.main_window is not None:
                    ui.button("Choose folder…", on_click=choose_folder).props("outline")
                path = ui.input("Set folder").classes("w-full")
                ui.button("Open", on_click=lambda: open_folder(Path(path.value))).props("flat")
                recent = state.settings.existing_recent()
                if recent:
                    ui.label("Recent").classes("text-sm text-gray-500 mt-4")
                    for folder_path in recent:
                        ui.button(folder_path.name, on_click=lambda p=folder_path: open_folder(p)) \
                            .props("flat no-caps align=left").classes("w-full") \
                            .tooltip(str(folder_path))
