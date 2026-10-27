"""Adding art by drag and drop or paste: one upload route plus a small page script.

Dropped and pasted files are sent with fetch() to POST /api/art/<card id> (raw bytes,
file name in the X-Filename header) instead of over the page's websocket, which limits
message sizes. Any element with a `data-art-card="<card id>"` attribute accepts dropped
images (editor art area and preview, overview tiles); pasting an image anywhere on a page
whose body has `data-art-card` sets that card's art. The file picker uses ui.upload.

The route can't talk to the page that sent the file, so it records what happened in
`session.art_version` / `session.art_notice`; pages poll those in their timers.
"""
from __future__ import annotations

from urllib.parse import unquote

from fastapi import Request
from fastapi.responses import JSONResponse
from nicegui import app, ui

from ..app.assets import AssetError, import_art

ART_SCRIPT = """
<style>
  [data-art-card].art-drop { outline: 3px dashed #3b82f6; outline-offset: 3px; }
  .q-uploader__subtitle { display: none; }   /* "0.0B / 0.00%": files are added at once */
</style>
<script>
if (!window.sdArt) {
  window.sdArt = true;
  const target = (e) => e.target.closest ? e.target.closest('[data-art-card]') : null;
  const hasFiles = (e) => e.dataTransfer && [...e.dataTransfer.types].includes('Files');
  const send = (cardId, file) => fetch('/api/art/' + encodeURIComponent(cardId), {
    method: 'POST', body: file,
    headers: {'X-Filename': encodeURIComponent(file.name || 'pasted.png')},
  });
  document.addEventListener('dragover', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();                       // allow dropping (and never open the file)
    const t = target(e);
    if (t) t.classList.add('art-drop');
  });
  document.addEventListener('dragleave', (e) => {
    const t = target(e);
    if (t && !t.contains(e.relatedTarget)) t.classList.remove('art-drop');
  });
  document.addEventListener('drop', (e) => {
    if (!hasFiles(e)) return;
    const handled = e.defaultPrevented;       // e.g. the file picker took it already
    e.preventDefault();
    const t = target(e);
    document.querySelectorAll('.art-drop').forEach((el) => el.classList.remove('art-drop'));
    if (!t || handled) return;
    const file = [...e.dataTransfer.files].find((f) => f.type.startsWith('image/'));
    if (file) send(t.dataset.artCard, file);
  });
  document.addEventListener('paste', (e) => {
    const cardId = document.body.dataset.artCard;
    if (!cardId || !e.clipboardData) return;
    const file = [...e.clipboardData.files].find((f) => f.type.startsWith('image/'));
    if (!file) return;                        // text pastes as usual
    e.preventDefault();
    send(cardId, file);
  });
}
</script>
"""


def add_art_script() -> None:
    """Call on a page that accepts dropped or pasted art."""
    ui.add_body_html(ART_SCRIPT)


def set_paste_target(card_id: str | None) -> None:
    """Which card a pasted image goes to on this page (None: pasting images does nothing)."""
    if card_id:
        ui.run_javascript(f"document.body.dataset.artCard = {card_id!r};")
    else:
        ui.run_javascript("delete document.body.dataset.artCard;")


def receive_art(session, card_id: str, data: bytes, filename: str, face: int = 0) -> tuple[int, dict]:
    """What the upload route does: (HTTP status, JSON body). Also leaves a notice for the page."""
    if session is None:
        return 409, {"error": "No set is open"}
    card = next((c for c in session.project.cards if c.id == card_id), None)
    if card is None or not 0 <= face < len(card.faces):
        return 404, {"error": f"No card {card_id!r}"}
    try:
        path = import_art(session, card, data, filename, face)
    except AssetError as e:
        session.art_notice = ("negative", str(e))
        return 400, {"error": str(e)}
    session.art_notice = ("positive", f"Art added to “{card.faces[face].name}”")
    return 200, {"path": path}


def register(state) -> None:

    @app.post("/api/art/{card_id}")
    async def upload_art(card_id: str, request: Request, face: int = 0):
        name = unquote(request.headers.get("x-filename", "image"))
        status, body = receive_art(state.session, card_id, await request.body(), name, face)
        return JSONResponse(body, status_code=status)
