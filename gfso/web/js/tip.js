// The one floating tip every view uses — the graph's `#tooltip`, so a hover reads the same anywhere.
import {esc} from './dom.js';

const box = () => document.getElementById('tooltip');
let mine = false;          // the tip on screen is a `title`'s, not a view's own

export function tip(html, e) {
    const el = box();
    el.innerHTML = html;
    el.classList.add('visible');
    const r = el.getBoundingClientRect(), x = e.clientX + 14, y = e.clientY + 14;
    el.style.left = `${Math.min(x, innerWidth - r.width - 8)}px`;
    el.style.top = `${y + r.height > innerHeight - 8 ? e.clientY - r.height - 10 : y}px`;
    e.tipped = true;
    mine = false;
}
export const untip = () => box().classList.remove('visible');

// Every `title` on the page is read through the same tip: the browser's own box (square, system font, default
// colours) is the one surface outside the brand. A title is moved to `data-tip` on first hover so the browser never
// draws it; a view's own tip for the same event wins, since views listen below the document.
const own = e => {
    if (e.tipped) return;
    const t = e.target.closest?.('[title], [data-tip]');
    if (t?.hasAttribute('title')) { t.dataset.tip = t.getAttribute('title'); t.removeAttribute('title'); }
    if (t?.dataset.tip) { tip(`<div class="tt-text">${esc(t.dataset.tip)}</div>`, e); mine = true; }
    else if (mine) { untip(); mine = false; }
};
const drop = () => { if (mine) { untip(); mine = false; } };
document.addEventListener('mouseover', own);
document.addEventListener('mousemove', own);
document.addEventListener('mousedown', drop);
document.addEventListener('mouseleave', drop);
