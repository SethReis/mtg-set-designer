"""The MSE adapter: a card + its MSE stylesheet -> a CardLayout.

For each `card style` / `extra card style` entry (one per field), its properties
are evaluated as MSE does: scripts run with the card's variables, `input` bound to
the field's value, and `card_style` giving other entries' properties and laid-out
content sizes (e.g. the name box ends where the mana cost's content begins).
Everything MSE-specific stays here; the drawing engine only sees the layout.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..mse.environment import ScriptEnvironment
from ..mse.objects import CardObject, ScriptObject, canonical
from ..mse.script import images as I
from ..mse.script.values import (Color, ErrorValue, ScriptError, to_bool, to_color, to_double,
                                 to_str)
from .layout import (Alignment, Box, CardLayout, FontSpec, ImageLayer, SymbolFontSpec,
                     TextLayer)
from .stylesheet import EntryStyle, Stylesheet, load_stylesheet
from .symbol_font import SymbolRenderer, load_symbol_font
from .text import layout_text

CHOICE_KINDS = ("choice", "multiple choice", "boolean", "package choice")
UNSET = object()


def _rgba(value: object, default: tuple) -> tuple:
    if value is None or value is UNSET or isinstance(value, ErrorValue) or value == "":
        return default
    try:
        c = to_color(value)
    except ScriptError:
        return default
    return (c.r, c.g, c.b, c.a)


class EntryObject(ScriptObject):
    """`card_style.<field>` in scripts: an entry's properties and content size."""
    type_label = "style"

    def __init__(self, builder: "MSELayoutBuilder", entry: EntryStyle):
        self.builder, self.entry = builder, entry

    def script_member(self, name: object) -> object:
        key = canonical(name)
        if key in ("content width", "content height", "content lines"):
            w, h, lines = self.builder.content(self.entry)
            return {"content width": w, "content height": h, "content lines": lines}[key]
        value = self.builder.prop(self.entry, key)
        return self.no_member(name) if value is UNSET else value


class CardStyleObject(ScriptObject):
    type_label = "card style"

    def __init__(self, builder: "MSELayoutBuilder"):
        self.builder = builder

    def script_member(self, name: object) -> object:
        entry = self.builder.entry(canonical(name))
        return EntryObject(self.builder, entry) if entry else self.no_member(name)


class MSELayoutBuilder:
    def __init__(self, env: ScriptEnvironment, card: CardObject):
        self.env = env
        self.card = card
        self.root = env.root
        self.ss: Stylesheet = load_stylesheet(env.root, card.style, env.game)
        self.card_style = CardStyleObject(self)
        self.warnings: list[str] = []
        self._props: dict[tuple[str, bool, str], object] = {}
        self._content: dict[tuple[str, bool], tuple[float, float, int]] = {}
        self._computing: set[tuple[str, bool]] = set()
        self._guard_hits = 0                # times content() was asked for while computing it
        self._by_name = {canonical(e.field): e for e in self.ss.entries if not e.extra}
        self._by_name.update({canonical(e.field): e for e in self.ss.entries
                              if e.extra and canonical(e.field) not in self._by_name})

    # ---------------------------------------------------------- evaluation

    def entry(self, name: str) -> EntryStyle | None:
        return self._by_name.get(name)

    def value(self, entry: EntryStyle) -> object:
        fields = self.card.extra_card.fields if entry.extra else self.card.fields
        return fields.get(entry.field) if entry.field in fields else None

    def evaluate(self, entry: EntryStyle, node) -> object:
        bindings = self.card.bindings(self.value(entry))
        bindings["input"] = bindings["value"]
        bindings["card_style"] = self.card_style
        return self.env.evaluate(node, self.card.style, bindings)

    def prop(self, entry: EntryStyle, key: str, default: object = UNSET, within: str = "") -> object:
        """An evaluated property (`within` = a nested block such as "font")."""
        cache_key = (entry.field, entry.extra, f"{within}>{key}")
        if cache_key in self._props:
            return self._props[cache_key]
        block = entry.props.get(within, {}) if within else entry.props
        node = block.get(key) if isinstance(block, dict) else None
        if node is None or isinstance(node, dict):
            return default if node is None else node
        self._props[cache_key] = default             # guards against self-reference
        guard_hits = self._guard_hits
        try:
            value = self.evaluate(entry, node)
        except (ScriptError, RecursionError) as e:
            self.warnings.append(f"{entry.field} > {within + ' > ' if within else ''}{key}: {e}")
            value = default
        if isinstance(value, ErrorValue):
            value = default
        if self._guard_hits != guard_hits:
            del self._props[cache_key]                # depended on a half-computed content size
        else:
            self._props[cache_key] = value
        return value

    def number(self, entry: EntryStyle, key: str, default: float | None = None,
               within: str = "") -> float | None:
        value = self.prop(entry, key, UNSET, within)
        if value is UNSET or value is None or value == "":
            return default
        try:
            return to_double(value)
        except ScriptError:
            return default

    def text_prop(self, entry: EntryStyle, key: str, default: str = "", within: str = "") -> str:
        value = self.prop(entry, key, UNSET, within)
        if value is UNSET or value is None:
            return default
        try:
            return to_str(value)
        except ScriptError:
            return default

    # --------------------------------------------------------------- boxes

    def box(self, entry: EntryStyle) -> Box | None:
        """Any two of left/width/right (top/height/bottom) give the third."""
        def axis(start: str, size: str, end: str) -> tuple[float, float] | None:
            a, s, b = (self.number(entry, k) for k in (start, size, end))
            given = [v is not None for v in (a, s, b)]
            if sum(given) < 2:
                return None
            if a is not None and s is not None and b is None:
                return a, s
            if a is not None and b is not None and s is None:
                return a, b - a
            if s is not None and b is not None and a is None:
                return b - s, s
            return (a + b - s) / 2, s                  # all three: centered
        h, v = axis("left", "width", "right"), axis("top", "height", "bottom")
        if h is None or v is None:
            return None
        return Box(h[0], v[0], abs(h[1]), abs(v[1]))

    def visible(self, entry: EntryStyle) -> bool:
        value = self.prop(entry, "visible", True)
        try:
            return to_bool(value)
        except ScriptError:
            return True

    # ------------------------------------------------------------- layers

    def font(self, entry: EntryStyle) -> FontSpec:
        within = "font"
        size = self.number(entry, "size", 12.0, within) or 12.0
        weight = self.text_prop(entry, "weight", "", within)
        style = self.text_prop(entry, "style", "", within)
        return FontSpec(
            name=self.text_prop(entry, "name", "", within),
            size=size,
            color=_rgba(self.prop(entry, "color", UNSET, within), (0, 0, 0, 255)),
            italic_name=self.text_prop(entry, "italic name", "", within),
            bold=weight == "bold", italic=style == "italic",
            scale_down_to=self.number(entry, "scale down to", 100000.0, within),
            max_stretch=self.number(entry, "max stretch", 1.0, within),
            shadow_color=_rgba(self.prop(entry, "shadow color", UNSET, within), (0, 0, 0, 0)),
            shadow_dx=self.number(entry, "shadow displacement x", 0.0, within),
            shadow_dy=self.number(entry, "shadow displacement y", 0.0, within),
            shadow_blur=self.number(entry, "shadow blur", 0.0, within),
            stroke_radius=self.number(entry, "stroke radius", 0.0, within),
            stroke_color=_rgba(self.prop(entry, "stroke color", UNSET, within), (0, 0, 0, 255)),
            stroke_blur=self.number(entry, "stroke blur", 0.0, within),
        )

    def symbol_font(self, entry: EntryStyle) -> SymbolFontSpec | None:
        if "symbol font" not in entry.props:
            return None
        name = self.text_prop(entry, "name", "", "symbol font")
        if not name:
            return None
        try:
            font = load_symbol_font(self.root, name)
        except Exception as e:
            self.warnings.append(f"{entry.field}: symbol font {name}: {e}")
            return None
        renderer = SymbolRenderer(font, lambda node: self.evaluate(entry, node), self.root)
        size = self.number(entry, "size", 12.0, "symbol font") or 12.0
        # spacing is in the symbol images' own units, scaled like them (fits MSE's output)
        spacing = font.horizontal_space * size / max(1.0, font.image_font_size)
        return SymbolFontSpec(renderer, size=size,
                              scale_down_to=self.number(entry, "scale down to", 1.0, "symbol font"),
                              alignment=Alignment.parse(self.text_prop(entry, "alignment", "",
                                                                       "symbol font"),
                                                        Alignment("center", "middle")),
                              spacing=spacing)

    def mask(self, entry: EntryStyle, box: Box) -> Image.Image | None:
        """The style's mask at the box size, as an "L" image (white = inside)."""
        if "mask" not in entry.props:
            return None
        value = self.prop(entry, "mask", None)
        if value is None or value == "":
            return None
        try:
            raster = I.as_image(value).generate_conform(self.options(box))
        except ScriptError as e:
            self.warnings.append(f"{entry.field} > mask: {e}")
            return None
        grey = raster.rgb[..., 0].astype(np.int32) * raster.alpha_or_opaque().astype(np.int32) // 255
        return Image.fromarray(grey.astype(np.uint8), "L")

    def options(self, box: Box, fit: bool = False) -> I.ImageOptions:
        return I.ImageOptions(width=max(1, round(box.width)), height=max(1, round(box.height)),
                              preserve_aspect="fit" if fit else "stretch", root=self.root,
                              package=self.root / f"{self.card.style}.mse-style")

    def text_layer(self, entry: EntryStyle, box: Box, text: str) -> TextLayer:
        fd = self.env.card_field_defs.get(entry.field)
        multi_line = fd.multi_line if fd and not entry.extra else False
        n = lambda key, default: self.number(entry, key, default)
        return TextLayer(
            box=box, text=text, font=self.font(entry), symbol_font=self.symbol_font(entry),
            always_symbol=to_bool(self.prop(entry, "always symbol", False) or False),
            alignment=Alignment.parse(self.text_prop(entry, "alignment", "top left")),
            padding=(n("padding left", 0.0), n("padding top", 0.0), n("padding right", 0.0),
                     n("padding bottom", 0.0)),
            line_height_soft=n("line height soft", 1.0), line_height_hard=n("line height hard", 1.0),
            line_height_line=n("line height line", 1.0),
            line_height_soft_max=n("line height soft max", 0.0),
            line_height_hard_max=n("line height hard max", 0.0),
            line_height_line_max=n("line height line max", 0.0),
            paragraph_height=n("paragraph height", -1.0),
            multi_line=multi_line, mask=self.mask(entry, box), angle=n("angle", 0.0),
        )

    def content(self, entry: EntryStyle) -> tuple[float, float, int]:
        """Laid-out content size of an entry (text width/height/lines; image size)."""
        key = (entry.field, entry.extra)
        if key in self._content:
            return self._content[key]
        if key in self._computing:
            self._guard_hits += 1
            return (0.0, 0.0, 0)
        self._computing.add(key)
        try:
            result = (0.0, 0.0, 0)
            box = self.box(entry)
            if box is not None and entry.kind == "text":
                layer = self.text_layer(entry, box, to_str(self.value(entry) or ""))
                if not layer.multi_line:         # natural width, not limited by the box
                    layer.box = Box(box.left, box.top, 100000.0, box.height)
                laid = layout_text(layer)
                pl, _, pr, _ = layer.padding
                result = (laid.content_width + pl + pr, laid.content_height, len(laid.lines))
            elif box is not None and entry.kind in CHOICE_KINDS:
                image = self.choice_image(entry, box)
                if image is not None:
                    result = (float(image.width), float(image.height), 0)
        finally:
            self._computing.discard(key)
        self._content[key] = result
        return result

    def choice_image(self, entry: EntryStyle, box: Box) -> Image.Image | None:
        render = self.text_prop(entry, "render style", "text")
        if "image" not in render and render != "both":
            return None
        value = self.prop(entry, "image", None) if "image" in entry.props else None
        if value is None:
            images = entry.props.get("choice images", {})
            node = images.get(to_str(self.value(entry) or "")) if isinstance(images, dict) else None
            if node is None or isinstance(node, dict):
                return None
            try:
                value = self.evaluate(entry, node)
            except ScriptError as e:
                self.warnings.append(f"{entry.field} > choice image: {e}")
                return None
        if value is None or value == "" or isinstance(value, ErrorValue):
            return None
        alignment = Alignment.parse(self.text_prop(entry, "alignment", "stretch"), Alignment("stretch"))
        try:
            recipe = I.as_image(value)
            raster = recipe.generate_conform(self.options(box, fit=alignment.horizontal != "stretch"))
        except ScriptError as e:
            self.warnings.append(f"{entry.field} > image: {e}")
            return None
        return raster.to_pil().convert("RGBA")

    def image_layer(self, entry: EntryStyle, box: Box) -> ImageLayer | None:
        kind = entry.kind
        combine = None
        if kind in CHOICE_KINDS:
            image = self.choice_image(entry, box)
            value = self.prop(entry, "image", None) if "image" in entry.props else None
            combine = getattr(value, "combine", None) if value is not None else None
            alignment = Alignment.parse(self.text_prop(entry, "alignment", "stretch"), Alignment("stretch"))
        elif kind == "image":
            image = self.art_image(entry, box)
            alignment = Alignment("stretch")
        elif kind == "color":
            image = self.color_image(entry, box)
            alignment = Alignment("stretch")
        else:
            return None
        if image is None:
            return None
        combine = self.text_prop(entry, "combine", "") or combine
        mask = self.mask(entry, box) if kind != "color" else None
        if mask is not None:
            mask = mask.resize(image.size) if mask.size != image.size else mask
            alpha = np.asarray(image.getchannel("A"), np.int32) * np.asarray(mask, np.int32) // 255
            image.putalpha(Image.fromarray(alpha.astype(np.uint8), "L"))
        return ImageLayer(box, image, combine if combine not in ("", "normal") else None, alignment,
                          self.number(entry, "angle", 0.0))

    def art_image(self, entry: EntryStyle, box: Box) -> Image.Image | None:
        size = (max(1, round(box.width)), max(1, round(box.height)))
        path = to_str(self.value(entry) or "")
        if path:
            try:
                with Image.open(path) as img:
                    return cover_fit(img.convert("RGBA"), size)
            except OSError as e:
                self.warnings.append(f"{entry.field}: art {path}: {e}")
        if "default" not in entry.props:
            return None
        value = self.prop(entry, "default", None)
        if value is None or value == "":
            return None
        try:
            return I.as_image(value).generate_conform(self.options(box)).to_pil().convert("RGBA")
        except ScriptError as e:
            self.warnings.append(f"{entry.field} > default: {e}")
            return None

    def color_image(self, entry: EntryStyle, box: Box) -> Image.Image | None:
        value = self.value(entry)
        if not isinstance(value, Color):
            try:
                value = to_color(value)
            except ScriptError:
                return None
        w, h = max(1, round(box.width)), max(1, round(box.height))
        color = (value.r, value.g, value.b, value.a)
        image = Image.new("RGBA", (w, h), color)
        mask = self.mask(entry, box)
        if mask is not None:                        # the mask's shape, tinted
            alpha = np.asarray(mask, np.int32) * value.a // 255
            image.putalpha(Image.fromarray(alpha.astype(np.uint8), "L"))
            return image
        lw, rw, tw, bw = (self.number(entry, k, 0.0) for k in
                          ("left width", "right width", "top width", "bottom width"))
        if lw < w and rw < w and tw < h and bw < h and (lw or rw or tw or bw):
            alpha = np.full((h, w), value.a, np.uint8)
            alpha[round(tw):h - round(bw), round(lw):w - round(rw)] = 0   # a ring
            image.putalpha(Image.fromarray(alpha, "L"))
        return image

    # ------------------------------------------------------------------ all

    def build(self) -> CardLayout:
        layout = CardLayout(self.ss.card_width, self.ss.card_height)
        entries = sorted(self.ss.entries,
                         key=lambda e: (self.number(e, "z index", 0.0) or 0.0, e.extra, e.order))
        for entry in entries:
            if entry.kind in ("info", "unknown"):
                continue
            try:
                if not self.visible(entry):
                    continue
                box = self.box(entry)
                if box is None or box.width <= 0 or box.height <= 0:
                    continue
                if entry.kind == "text":
                    text = to_str(self.value(entry) or "")
                    if text:
                        layout.layers.append(self.text_layer(entry, box, text))
                else:
                    layer = self.image_layer(entry, box)
                    if layer is not None:
                        layout.layers.append(layer)
            except (ScriptError, RecursionError) as e:
                self.warnings.append(f"{entry.field}: {e}")
        layout.warnings = self.warnings
        return layout


def cover_fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Scale to cover `size` and crop the middle (our art is any aspect ratio;
    MSE expects art already cropped to the box)."""
    w, h = size
    scale = max(w / img.width, h / img.height)
    resized = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                         Image.Resampling.LANCZOS)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def mse_layout(env: ScriptEnvironment, card: CardObject) -> CardLayout:
    return MSELayoutBuilder(env, card).build()
