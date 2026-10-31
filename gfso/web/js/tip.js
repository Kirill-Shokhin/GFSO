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
// a hover that would only repeat the words it is on, shown whole, says nothing — a name is hovered for its full text
const tipOf = e => { const t = e.target.closest?.('[data-tip]');
    return t && !(t.dataset.tip === t.textContent.trim() && t.scrollWidth <= t.clientWidth) ? t : null; };
const own = e => {
    if (e.tipped) return;
    const t = tipOf(e);
    if (t) { const [head, ...rows] = t.dataset.tip.split('\n'); tip(card(head, rows), e); mine = true; }
    else if (mine) { untip(); mine = false; }
};
const drop = () => { if (mine) { untip(); mine = false; } };
document.addEventListener('mouseover', own);
document.addEventListener('mousemove', own);
document.addEventListener('mouseleave', drop);

// A FINGER: a tap is the hover a phone has (the author, 2026-10-31: «попапы инфу дают невозможно получить»). The mousedown a
// tap makes does not drop the tip that tap just showed; the tap's click, if no view answered it, shows the thing's own
// `data-tip` or clears whatever tip an earlier tap left — on every view alike, the Models tab and the toolbar included.
export const TOUCH = matchMedia('(hover: none)');
document.addEventListener('mousedown', () => { if (!TOUCH.matches) drop(); });
// …but a control's tap is its act, not its tip — a tab, the «?», a button — unless a first tap chose the tip (store.js)
const ACTS = 'button, a, input, select, [data-action]';
document.addEventListener('click', e => { if (!TOUCH.matches || e.tipped) return;
    if (tipOf(e) && (e.showTip || !e.target.closest(ACTS))) own(e); else { untip(); mine = false; } });
// …and whether a tap on this thing shows a tip: a view's own (`tip()` marked the event) or its `data-tip`
export const hasTip = e => !!(e.tipped || tipOf(e));
