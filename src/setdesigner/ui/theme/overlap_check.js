// Dev only (SETDESIGNER_DEV=1): after the page settles, report text that overlaps other
// text, or is cut off without an ellipsis, into <pre id="overlap-report"> (JSON), for
// tests/ui_visual/test_overlaps.py to read from a headless browser's DOM dump.
(() => {
  const IGNORE = ".ds-hotspot, .card-stack, .stack-card, .ds-tile img, .q-tooltip, .ds-badge, .ds-nav-badge, " +
                 ".ds-card-box, .q-menu, .ds-renderer-notice-host, [aria-hidden=true]";
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.opacity !== "0";
  };
  // with a modal open, only it is in view (the page behind is blurred out)
  const root = () => [...document.querySelectorAll(".q-dialog .ds-modal")].pop() || document.body;
  // really on screen: not scrolled away or covered (what's at its middle is it, or inside it)
  const shown = (el, r) => {
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return hit && (hit === el || el.contains(hit) || hit.contains(el));
  };
  const textBoxes = () => {
    const out = [];
    const walker = document.createTreeWalker(root(), NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const text = n.textContent.trim();
      const el = n.parentElement;
      if (!text || !el || el.closest(IGNORE) || !visible(el)) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      const box = el.getBoundingClientRect();         // truncated text: only what's shown
      for (const full of range.getClientRects()) {
        const left = Math.max(full.left, box.left), right = Math.min(full.right, box.right);
        const r = { left, right, top: full.top, bottom: full.bottom, width: right - left, height: full.height };
        if (r.width > 1 && r.height > 1 && shown(el, r)) out.push({ text: text.slice(0, 40), el, r });
      }
    }
    for (const input of root().querySelectorAll("input, textarea")) {   // values and placeholders
      if (input.closest(IGNORE) || !visible(input)) continue;
      const text = (input.value || input.placeholder || "").trim();
      const r = input.getBoundingClientRect();
      if (text && shown(input, r)) out.push({ text: text.slice(0, 40), el: input, r, input: true });
    }
    return out;
  };
  const overlap = (a, b) => {
    const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return x > 2 && y > 3;
  };
  const report = () => {
    const boxes = textBoxes();
    const found = [];
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j];
        if (a.el === b.el || a.el.contains(b.el) && b.input || b.el.contains(a.el) && a.input) continue;
        const field = (x) => x.el.closest(".q-field");          // a field's own label and value
        if ((a.input || b.input) && field(a) && field(a) === field(b)) continue;
        if (a.text !== b.text && overlap(a.r, b.r)) found.push({ kind: "overlap", a: a.text, b: b.text });
      }
    }
    for (const el of root().querySelectorAll("label, .q-field__label, th, .head, .ds-label, .ds-form-h")) {
      if (el.closest(IGNORE) || !visible(el)) continue;
      const s = getComputedStyle(el);
      if (el.scrollWidth > el.clientWidth + 1 && s.textOverflow !== "ellipsis" && s.overflow !== "visible")
        found.push({ kind: "clipped", a: el.textContent.trim().slice(0, 40) });
    }
    let pre = document.getElementById("overlap-report");
    if (!pre) { pre = document.createElement("pre"); pre.id = "overlap-report"; pre.hidden = true; document.body.append(pre); }
    pre.textContent = JSON.stringify(found);
  };
  window.addEventListener("load", () => setTimeout(report, 4000));
})();
