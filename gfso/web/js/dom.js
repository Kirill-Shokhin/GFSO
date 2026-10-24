// Markup primitives every view builds with.
export const $ = id => document.getElementById(id);

// EVERY STRING ON THIS PAGE THAT A MODEL WROTE GOES THROUGH HERE. Panels are built by concatenation,
// and a validator's evidence quoting `a<=f>=g` lost `<=f>` to the parser (author, 2026-09-12): a page
// that renders its evidence as HTML cannot be read as evidence. Not a security claim.
export const esc = s => String(s).replace(/[&<>"']/g, ch => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));

// An element filled by ASSIGNMENT, never re-parsed: a form that writes back must not cut a criterion
// at its first `"` and save the stump (an Edit + Save once shortened a node's own contract).
export const el = (tag, props = {}, ...kids) => {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...kids);
    return e;
};

export const section = (title, body) =>
    `<div class="section"><div class="section-title">${title}</div>${body}</div>`;
export const ul = (cls, items) => `<ul class="${cls}">${items.join('')}</ul>`;
// `data-*` attributes for a delegated control (main.js dispatches `data-action`); empty values are left out.
export const data = o => Object.entries(o).filter(([, v]) => v).map(([k, v]) => ` data-${k}="${esc(v)}"`).join('');

// Redraw `box` keeping what the reader unfolded (`details[data-key]`) and, on the same `key`, its scroll —
// the panel is rebuilt on every transition, and a reader mid-text must not be thrown to the top.
export function rebuild(box, key, html) {
    const open = new Set([...box.querySelectorAll('details[open][data-key]')].map(x => x.dataset.key));
    const top = box.dataset.key === key ? box.scrollTop : 0;
    box.innerHTML = html;
    box.querySelectorAll('details[data-key]').forEach(x => { x.open = open.has(x.dataset.key); });
    box.scrollTop = top;
    box.dataset.key = key;
}
