// Markup primitives every view builds with.
import {dur} from './fmt.js';
export const $ = id => document.getElementById(id);
// a phone's layout: the width is decided in gfso.css alone, the script reads its verdict, never the number
export const phone = () => getComputedStyle(document.documentElement).getPropertyValue('--phone').trim() === '1';

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
// A COUNT IS ITS OWN MARK — the figure large, its label small beside it, never threaded into a sentence nor joined to
// another figure by a dot or a dash (the author, 2026-10-29: «цифры опять спрятаны между букв … статус стоит через тире»)
export const tally = (figure, label, attrs = '') => `<span class="tally"${attrs}><b>${figure}</b><i>${label}</i></span>`;
// …the same mark inside a drawing: its figure in the brand's display face, its label in the line's; the size is the line's
// (a view's class) — one owner for the views that draw it (audit B16: tally, .tl-fig and .pg-count were three)
export const tallySvg = (figure, label, cls, x, y) => `<text class="tally-svg ${cls}" x="${x}" y="${y}">`
    + `${figure === '' ? '' : `<tspan class="ts-fig">${figure}</tspan>`}<tspan class="ts-lab">${figure === '' ? '' : ' '}${label}</tspan></text>`;
// A FIGURE TIME MOVES with nothing pushed — how long what runs now has run, whether a deadline has passed — carries its
// moment, and the page's one display clock (`ages`, main.js) sets it again in place: drawn once, it read as true until a
// reload (the author, 2026-10-31: «обновление страницы никогда не должно требоваться вручную»)
export const since = t => `<span data-since="${t}">${dur(Date.now() - t)}</span>`;
// a span that grows while its run is open (`from` its moment) and stands when it is closed — one figure for every view
export const lasting = (from, ms) => from ? since(from) : dur(ms);
// a view saying today's moments without their day draws again once the day turns
export const daily = f => { let t; const arm = () => { clearTimeout(t); const m = new Date(); m.setHours(24, 0, 1, 0);
    t = setTimeout(() => { f(); arm(); }, m - Date.now()); }; arm(); };
export const due = t => ` data-due="${t}"`;
export function ages() {
    const now = Date.now();
    for (const e of document.querySelectorAll('[data-since]')) { const s = dur(now - +e.dataset.since); if (e.textContent !== s) e.textContent = s; }
    for (const e of document.querySelectorAll('[data-due]')) e.classList.toggle('overdue', now > +e.dataset.due);
}
// a label the reader cannot see right now — scrolled out of the deck's view (a phone's deck scrolls sideways)
export const unseen = e => { if (!e) return true; const a = e.getBoundingClientRect(), b = (e.closest('.dk-body') || document.documentElement).getBoundingClientRect();
    return a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom; };
export const ul = (cls, items) => `<ul class="${cls}">${items.join('')}</ul>`;
// `data-*` attributes for a delegated control (main.js dispatches `data-action`); empty values are left out.
export const data = o => Object.entries(o).filter(([, v]) => v).map(([k, v]) => ` data-${k}="${esc(v)}"`).join('');

// Redraw `box` keeping what the reader unfolded (`details[data-key]`) and, on the same `key`, its scroll —
// the panel is rebuilt on every transition, and a reader mid-text must not be thrown to the top.
// A VIEW REDRAWN EVERY SECOND changes only what changed: the new markup is laid over the old node by node — a text or an
// attribute that differs is set, a node of another shape replaced — so the element under the pointer, its tip and the
// scroll stay as they are while the figures move (a live reading pushed once a second, resources.js)
export function morph(box, html) {
    const t = document.createElement('template');
    t.innerHTML = html;
    const lay = (a, b) => {
        if (a.nodeType !== b.nodeType || a.nodeName !== b.nodeName) return a.replaceWith(b.cloneNode(true));
        if (a.nodeType === Node.TEXT_NODE) { if (a.data !== b.data) a.data = b.data; return; }
        if (a.nodeType !== Node.ELEMENT_NODE) return;
        for (const {name} of [...a.attributes]) if (!b.hasAttribute(name)) a.removeAttribute(name);
        for (const {name, value} of [...b.attributes]) if (a.getAttribute(name) !== value) a.setAttribute(name, value);
        const ac = [...a.childNodes], bc = [...b.childNodes];
        bc.forEach((n, i) => ac[i] ? lay(ac[i], n) : a.appendChild(n.cloneNode(true)));
        ac.slice(bc.length).forEach(n => n.remove());
    };
    const ac = [...box.childNodes], bc = [...t.content.childNodes];
    bc.forEach((n, i) => ac[i] ? lay(ac[i], n) : box.appendChild(n.cloneNode(true)));
    ac.slice(bc.length).forEach(n => n.remove());
}

export function rebuild(box, key, html) {
    const open = new Set([...box.querySelectorAll('details[open][data-key]')].map(x => x.dataset.key));
    const top = box.dataset.key === key ? box.scrollTop : 0;
    box.innerHTML = html;
    box.querySelectorAll('details[data-key]').forEach(x => { x.open = open.has(x.dataset.key); });
    box.scrollTop = top;
    box.dataset.key = key;
}
