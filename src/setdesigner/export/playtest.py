"""Printer-friendly cards: text only, like playtest cards, to save ink.

    draw = playtest_drawer(project, overflow)      # an export.pdf Drawer
    plain_symbols("{2}{W}, {T}")                    # "2W, T"

No art and no frame: a thin border, the name and cost, the type line, the rules (with
the set's reminder text, as the renders show it; parenthesized text in italics, as on
real cards), the flavor text after a thin rule, P/T or loyalty, and the rarity, number
and set code. Drawn as PDF text in Helvetica (built into every PDF reader, so no font
file is needed). Rules shrink from 9 pt to 6 pt to fit; text that still doesn't fit is
cut off with an ellipsis and its card name added to `overflow`.
"""
from __future__ import annotations

import re
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from ..app.mechanics import with_reminders
from ..model import Rarity, SetProject
from ..mse.mechanics import reminder_choices
from .pdf import Drawer
from .selection import PrintFace

PAD = 3 * mm                            # inside the border
BORDER = 0.3 * mm
RADIUS = 2.5 * mm
SIZES = [9 - 0.5 * i for i in range(7)]  # rules text sizes, 9 pt down to 6 pt
RARITY_LETTERS = {Rarity.COMMON: "C", Rarity.UNCOMMON: "U", Rarity.RARE: "R",
                  Rarity.MYTHIC: "M", Rarity.SPECIAL: "S"}
# Helvetica's encoding (WinAnsi) lacks a few characters cards use
REPLACE = {"−": "-", "∞": "inf", "→": "->", "★": "*"}


def plain_symbols(text: str) -> str:
    """Mana and other symbols as plain characters: {2}{W} -> 2W, {T} -> T, {W/U} -> (W/U)."""
    return re.sub(r"\{([^{}\s]+)\}", lambda m: f"({m.group(1)})" if "/" in m.group(1) else m.group(1),
                  text)


def printable(text: str) -> str:
    """Only characters Helvetica can show."""
    out = []
    for ch in text:
        ch = REPLACE.get(ch, ch)
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            ch = "?"
        out.append(ch)
    return "".join(out)


def markup(text: str) -> str:
    """Paragraph markup: escaped, parenthesized text in italics."""
    return re.sub(r"\([^()]*\)", lambda m: f"<i>{m.group(0)}</i>", escape(text))


def fit_font(canvas: Canvas, text: str, font: str, size: float, width: float, floor: float = 5) -> float:
    while size > floor and canvas.stringWidth(text, font, size) > width:
        size -= 0.25
    return size


def playtest_drawer(project: SetProject, overflow: list[str]) -> Drawer:
    choices = reminder_choices(project)
    code = project.info.code

    def draw(canvas: Canvas, item: PrintFace, width: float, height: float, bleed: float) -> None:
        card, face = item.card, item.card.faces[item.face]
        left, bottom = bleed, bleed
        right, top = bleed + width, bleed + height
        inner = width - 2 * PAD
        canvas.setStrokeGray(0)
        canvas.setFillGray(0)
        canvas.setLineWidth(BORDER)
        canvas.roundRect(left, bottom, width, height, RADIUS, stroke=1, fill=0)

        # name and cost
        y = top - PAD - 9
        cost = printable(plain_symbols(face.mana_cost))
        cost_w = canvas.stringWidth(cost, "Helvetica-Bold", 9) + (2 if cost else 0)
        name = printable(face.name or "(no name)")
        size = fit_font(canvas, name, "Helvetica-Bold", 9, inner - cost_w)
        canvas.setFont("Helvetica-Bold", size)
        canvas.drawString(left + PAD, y, name)
        if cost:
            canvas.setFont("Helvetica-Bold", 9)
            canvas.drawRightString(right - PAD, y, cost)
        y -= 4
        canvas.setLineWidth(0.4)
        canvas.line(left + PAD, y, right - PAD, y)

        # type line
        type_line = printable(face.type_line)
        size = fit_font(canvas, type_line, "Helvetica", 7.5, inner)
        y -= size + 2
        canvas.setFont("Helvetica", size)
        canvas.drawString(left + PAD, y, type_line)
        y -= 4
        canvas.line(left + PAD, y, right - PAD, y)

        # footer: rarity, number, code; P/T or loyalty
        foot = bottom + PAD
        side = "" if len(card.faces) == 1 else (" · front" if item.face == 0 else " · back")
        canvas.setFont("Helvetica", 6)
        canvas.drawString(left + PAD, foot, printable(
            f"{RARITY_LETTERS[card.rarity]} {card.collector_number or '—'}{side} · {code}"))
        stats = (f"{face.power or ''}/{face.toughness or ''}" if face.power or face.toughness
                 else face.loyalty or "")
        if stats:
            stats = printable(stats)
            stats_w = canvas.stringWidth(stats, "Helvetica-Bold", 9) + 6
            canvas.roundRect(right - PAD - stats_w, foot - 2.5, stats_w, 12.5, 2, stroke=1, fill=0)
            canvas.setFont("Helvetica-Bold", 9)
            canvas.drawCentredString(right - PAD - stats_w / 2, foot + 0.5, stats)

        # rules and flavor, shrunk to fit between the type line and the footer
        box_top, box_bottom = y - 3, foot + 13
        rules = with_reminders(project, card, face.rules_text, choices.get(card.id, {}))
        rules = printable(plain_symbols(rules.replace("CARDNAME", face.name)))
        flavor = printable(face.flavor_text)
        lines = [line for line in rules.split("\n") if line.strip()]
        cut = False
        for size in SIZES:
            body = ParagraphStyle("rules", fontName="Helvetica", fontSize=size, leading=size * 1.18,
                                  alignment=TA_LEFT, spaceAfter=size * 0.35)
            paragraphs = [Paragraph(markup(line), body) for line in lines]
            flavor_p = (Paragraph(f"<i>{escape(flavor)}</i>".replace("\n", "<br/>"), body)
                        if flavor.strip() else None)
            heights = [p.wrap(inner, 10_000)[1] + body.spaceAfter for p in paragraphs]
            flavor_h = flavor_p.wrap(inner, 10_000)[1] + 5 if flavor_p else 0
            if sum(heights) + flavor_h <= box_top - box_bottom:
                break
        else:
            cut = True
            overflow.append(face.name or card.id)
        canvas.saveState()
        clip = canvas.beginPath()
        clip.rect(left + PAD, box_bottom, inner, box_top - box_bottom)
        canvas.clipPath(clip, stroke=0, fill=0)
        y = box_top
        for p, h in zip(paragraphs, heights):
            p.drawOn(canvas, left + PAD, y - (h - body.spaceAfter))
            y -= h
        if flavor_p is not None:
            canvas.setLineWidth(0.3)
            canvas.line(left + PAD + inner * 0.2, y - 1.5, right - PAD - inner * 0.2, y - 1.5)
            flavor_p.drawOn(canvas, left + PAD, y - flavor_h)
        canvas.restoreState()
        if cut:
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawRightString(right - PAD, box_bottom - 1, "…")
    return draw
