// Dev only (SETDESIGNER_DEV=1): after the page settles, report text that overlaps other
// text, spills out of its box, or is cut off without an ellipsis, into
// <pre id="overlap-report"> (JSON), for tests/ui_visual/test_overlaps.py to read from a
// headless browser's DOM dump.
//
// ?dev_click=Matrix|Tune…  clicks those (by their visible text, in order) first, so a URL
// can land in a dialog, a tab or a mode.
(() => {
  const IGNORE = ".ds-hotspot, .card-stack, .stack-card, .ds-tile img, .q-tooltip, .ds-badge, .ds-nav-badge, " +
                 ".ds-card-box, .q-menu, .ds-renderer-notice-host, [aria-hidden=true], .q-field__native, " +
                 ".echarts, canvas, svg";
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.opacity !== "0";
  };
  // with a modal open, only it is in view (the page behind is blurred out)
  const root = () => [...document.querySelectorAll(".q-dialog .ds-modal, .q-dialog .q-card")].pop() || document.body;
  const inViewport = (r) => r.left + r.width / 2 >= 0 && r.left + r.width / 2 < innerWidth &&
                            r.top + r.height / 2 >= 0 && r.top + r.height / 2 < innerHeight;
  // not covered by something else; anything off screen (below the fold, scrolled away in a
  // scroll container) counts as shown, since scrolling reaches it
  const shown = (el, r) => {
    if (!inViewport(r)) return true;
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !hit || hit === el || el.contains(hit) || hit.contains(el) || !!hit.closest(IGNORE);
  };
  // where text is really cut off: by ancestors that hide overflow (not ones that scroll)
  const clipOf = (el) => {
    let box = { left: -1e9, right: 1e9, top: -1e9, bottom: 1e9 };
    for (let a = el; a && a !== document.body; a = a.parentElement) {
      const s = getComputedStyle(a);
      const hx = s.overflowX === "hidden" || s.overflowX === "clip";
      const hy = s.overflowY === "hidden" || s.overflowY === "clip";
      if (!hx && !hy) continue;
      const r = a.getBoundingClientRect();
      if (hx) { box.left = Math.max(box.left, r.left); box.right = Math.min(box.right, r.right); }
      if (hy) { box.top = Math.max(box.top, r.top); box.bottom = Math.min(box.bottom, r.bottom); }
    }
    return box;
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
      const clip = clipOf(el);
      for (const full of range.getClientRects()) {
        const left = Math.max(full.left, clip.left), right = Math.min(full.right, clip.right);
        const top = Math.max(full.top, clip.top), bottom = Math.min(full.bottom, clip.bottom);
        const r = { left, right, top, bottom, width: right - left, height: bottom - top };
        if (r.width > 1 && r.height > 1 && shown(el, r)) out.push({ text: text.slice(0, 40), el, r });
      }
    }
    for (const input of root().querySelectorAll("input, textarea")) {   // values and placeholders
      if (!visible(input) || input.closest(".ds-hotspot, .q-menu, [aria-hidden=true]")) continue;
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
  const hasOwnText = (el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  const report = () => {
    const boxes = textBoxes();
    const found = [...missed];
    const seen = new Set();
    const add = (f) => { const k = JSON.stringify(f); if (!seen.has(k)) { seen.add(k); found.push(f); } };
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j];
        if (a.el === b.el || a.el.contains(b.el) && b.input || b.el.contains(a.el) && a.input) continue;
        const field = (x) => x.el.closest(".q-field");          // a field's own label and value
        if ((a.input || b.input) && field(a) && field(a) === field(b)) continue;
        if (a.text !== b.text && overlap(a.r, b.r)) add({ kind: "overlap", a: a.text, b: b.text });
      }
    }
    for (const el of root().querySelectorAll("*")) {
      if (!hasOwnText(el) || el.closest(IGNORE) || !visible(el)) continue;
      const s = getComputedStyle(el);
      if (s.display === "inline" || el.scrollWidth <= el.clientWidth + 1) continue;
      const text = el.textContent.trim().slice(0, 40);
      if (s.overflowX === "visible") add({ kind: "spills", a: text, by: el.scrollWidth - el.clientWidth });
      else if (s.textOverflow !== "ellipsis") add({ kind: "clipped", a: text });
    }
    // a field whose prefix, suffix or label leaves its value no room to show
    for (const input of root().querySelectorAll(".q-field input")) {
      if (!visible(input) || input.closest(IGNORE)) continue;
      const w = input.getBoundingClientRect().width;
      if (w < 16) add({ kind: "squeezed-field", a: (input.value || input.placeholder || "").slice(0, 40), width: Math.round(w) });
    }
    // the overview toolbar stays one row from 1000px up
    if (window.innerWidth >= 1000) {
      for (const bar of root().querySelectorAll(".ds-toolbar")) {
        const kids = [...bar.children].filter(visible);
        if (!kids.length) continue;
        const tops = kids.map((k) => k.getBoundingClientRect().top);
        if (Math.max(...tops) - Math.min(...tops) > 20) add({ kind: "toolbar-wraps" });
      }
    }
    let pre = document.getElementById("overlap-report");
    if (!pre) { pre = document.createElement("pre"); pre.id = "overlap-report"; pre.hidden = true; document.body.append(pre); }
    pre.textContent = JSON.stringify(found);
  };
  // the element showing exactly this text (the innermost), clickable
  const byText = (text) => {
    const all = [...document.querySelectorAll("button, .q-btn, .q-tab, [role=button], .q-item, label, div, span, a")]
      .filter((el) => visible(el) && el.textContent.trim() === text);
    const el = all.pop();
    return el && (el.closest("button, .q-btn, .q-tab, [role=button], .q-item, a") || el);
  };
  const missed = [];
  let loaded = Date.now();
  const clicks = (new URLSearchParams(location.search).get("dev_click") || "").split("|").filter(Boolean);
  const run = (i) => {
    if (i >= clicks.length) return settled(report);
    if (!(window.socket && window.socket.connected) && Date.now() - loaded < 30000)
      return setTimeout(() => run(i), 250);          // a click needs the server connection
    const el = byText(clicks[i]);
    if (el) el.click(); else missed.push({ kind: "click-missed", a: clicks[i] });
    settled(() => run(i + 1));
  };
  // views build in steps (loading states, dialogs animating in): wait until the page has
  // stopped changing for a while (at most 30 s)
  const settled = (then) => {
    let last = Date.now();
    const started = last;
    const watch = new MutationObserver(() => { last = Date.now(); });
    watch.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
    const tick = () => {
      if (Date.now() - last > 2000 || Date.now() - started > 30000) { watch.disconnect(); then(); }
      else setTimeout(tick, 250);
    };
    setTimeout(tick, 1000);
  };
  window.addEventListener("load", () => (loaded = Date.now()) && setTimeout(() => settled(() => run(0)), 1000));
})();
