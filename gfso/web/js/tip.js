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
document.addEventListener('click', e => { if (!TOUCH.matches) return;
    if (!e.tipped) { if (tipOf(e) && (e.showTip || !e.target.closest(ACTS))) own(e); else { untip(); mine = false; } }
    shown = box().classList.contains('visible') ? thing(e) : null;     // what this tap left in sight
});
// THE THING A TIP IS OF: its node and its tip's heading — never the element, which a redraw (a token tick, the run read
// again) replaces between two taps, so the second tap read as a first (critic 12). This tap's: a view's own tip it just
// drew, else its `data-tip`'s first line, as the card sets it (heading and figure, no tab).
const thing = e => { const head = e.tipped ? box().querySelector('.tt-name')?.textContent : tipOf(e)?.dataset.tip.split('\n')[0].replace('\t', '');
    return head ? `${e.target.closest?.('[data-node]')?.dataset.node || ''}|${head}` : null; };
let shown = null, prior = null;
// …and what stood in sight when this tap BEGAN: a view clearing its tip during the tap does not disarm it (critic 12)
addEventListener('pointerdown', () => { prior = box().classList.contains('visible') ? shown : null; }, true);
// THE FIRST TAP on a thing that has a tip shows it (true); a second on that same thing — its tip still in sight — acts
// (false), and the tip goes with the act; a thing with no tip acts at once.
export function firstTap(e) {
    const k = TOUCH.matches && thing(e);
    if (k && k !== prior) return (e.showTip = true, true);
    if (TOUCH.matches) { untip(); mine = false; }   // a mouse's tip follows the pointer as it always did
    e.tipped = true;                       // acted on: the document's tap does not show a tip over what it opened
    return false;
}
// a press held on a control shows its tip, where its tap is its act — a tab, Stop, a project's row (the usual long-press)
document.addEventListener('contextmenu', e => { if (!TOUCH.matches || !tipOf(e)) return; e.preventDefault(); own(e); });
// a tip stands where its thing stood: a scroll moves the thing away from it
addEventListener('scroll', () => { if (TOUCH.matches) untip(); }, true);
