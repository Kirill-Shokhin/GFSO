// The one floating tip every view uses — the graph's `#tooltip`, so a hover reads the same anywhere.
import {card} from './hints.js';

const box = () => document.getElementById('tooltip');
let mine = false;          // the tip on screen is a `data-tip`'s, not a view's own

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

// Every hover on the page is this one tip, read off `data-tip` (hints.js writes them): the browser's own `title` box
// (square, system font, default colours) is the one surface outside the brand. A view's own tip for the same event
// wins, since views listen below the document. The first line is the heading, each further line a row.
const own = e => {
    if (e.tipped) return;
    const t = e.target.closest?.('[data-tip]');
    if (t) { const [head, ...rows] = t.dataset.tip.split('\n'); tip(card(head, rows), e); mine = true; }
    else if (mine) { untip(); mine = false; }
};
const drop = () => { if (mine) { untip(); mine = false; } };
document.addEventListener('mouseover', own);
document.addEventListener('mousemove', own);
document.addEventListener('mousedown', drop);
document.addEventListener('mouseleave', drop);
