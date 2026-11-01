// Progress by criteria along the split: the goal's own criteria, then one track per part with ITS own criteria, and a
// part unfolds into its parts. Each track counts one node's criteria passing at its own verdicts — a part's PASS is its
// issuer's signature at that seam, the root's PASS the goal delivered — never a sum across a level, which added parts
// of unrelated parents (author, 2026-10-25). Counts, not percentages: a share is not a verdict (canon §7.4).
import {esc, unseen, tallySvg} from './dom.js';
import {TIP, CELLS} from './hints.js';
import {label, cancelled} from './vocab.js';
import {failingNow} from './run.js';
import {bindFocus, bringSelected, focus, watch} from './store.js';
import {tip, untip, firstTap} from './tip.js';
import {frame, axisWidth, mark, glyph, pinLeft} from './draw.js';
import {hm, trim} from './fmt.js';
import {rootOf, isRoot, childrenOf, ancestorsIn} from './tree.js';

const LEFT = 220, GOAL = 54, PART = 30, GAP = 12, TOP = 22, INDENT = 12;
const unfolded = new Set();                      // parts the reader opened; the goal is always open
// …and the parts the reader folded: a path to a part failing NOW stands open unless the reader shut it — folded by
// default, the one red part of a run sat inside «▸ Recursive-descent parser 0 of 3» under 13 empty tracks (audit B2)
const folded = new Set();

// the rows in tree order: the goal, its parts, and the parts of every part the reader unfolded
function rows(tasks, track, hot) {
    const out = [];
    // siblings that have a verdict first, by their first one, then the rest in plan order — as the timeline orders its
    // rows; in plan order the one part at work sat under nine empty tracks, below the fold of a short deck (critic)
    const first = id => track[id]?.marks[0]?.t ?? Infinity;
    // …and a sibling over a part failing now before them all
    const kids = id => childrenOf(tasks, id).map(t => t.id).sort((a, b) => hot.has(b) - hot.has(a) || first(a) - first(b));
    const walk = (id, d) => {
        const ks = kids(id);
        if (track[id]?.total) out.push({id, d, kids: ks.length});
        if (shown(id, d, hot)) for (const k of ks) walk(k, d + 1);
    };
    for (const t of tasks) if (isRoot(t)) walk(t.id, 0);
    return out;
}

const shown = (id, d, hot) => d === 0 || unfolded.has(id) || (hot.has(id) && !folded.has(id));
// a node failing now and every node above it
const hotIn = (run, tasks) => { const up = ancestorsIn(tasks), hot = new Set();
    for (const t of tasks) if (failingNow(run.rounds[t.id], t.state)) [t.id, ...up(t.id)].forEach(x => hot.add(x));
    return hot; };

function tracks(el, run, name, tasks, hot) {
    const tr = run.criteria.track, rs = rows(tasks, tr, hot), h = r => r.d ? PART : GOAL;
    const W = axisWidth(el), f = frame(run, W, LEFT);
    let y = TOP;
    const body = rs.map(r => {
        const T = tr[r.id], y0 = (y += h(r)), top = y0 - h(r), at = k => y0 - (k / T.total) * h(r), lm = T.marks.at(-1);
        // a FAIL recorded before every verdict was kept whole names only what failed: its height is a bound, said on hover
        // only — such rounds are the old runs', and the page does not draw them apart (the author, 2026-10-27)
        const last = T.steps.at(-1)?.[1] ?? (lm ? lm.k : 0);
        y += GAP;
        const lx = 8 + Math.max(r.d - 1, 0) * INDENT;
        const caret = r.kids && r.d ? `<tspan class="pg-caret">${shown(r.id, r.d, hot) ? '▾' : '▸'} </tspan>` : '';
        // a name cut to the track's width: the whole of it on hover (the caret makes the text differ, so only when cut)
        const title = r.d ? name(r.id) : "the goal's criteria", fits = 34 - Math.max(r.d - 1, 0) * 2;
        // A CANCELLED PART owes nothing: its track is kept for its history, faint as its tombstone on the graph, and says
        // the word where a count would read as work left undone («0 of 1» on a DONE parent — the author, 2026-10-31)
        const gone = cancelled(tasks.find(t => t.id === r.id));
        return `<g class="pg-track${r.d ? ' pg-part' : ''}${gone ? ' pg-gone' : ''}" data-node="${esc(r.id)}">
            <rect class="pg-band" x="0" y="${top - GAP / 2}" width="${W}" height="${h(r) + GAP}"/>
            <text class="pg-level" data-k="l|${esc(r.id)}" x="${lx}" y="${top + 10}" ${r.kids && r.d ? `data-unfold="${esc(r.id)}"` : ''}${title.length > fits ? TIP.cell(title) : ''}>${caret}${esc(trim(title, fits))}</text>
            ${tallySvg(gone ? '' : last, gone ? label('ABANDONED').toLowerCase() : `of ${T.total}`, 'pg-count', LEFT - 10, top + (r.d ? 24 : 28))}
            <line class="pg-base" x1="${LEFT}" x2="${W - 16}" y1="${y0}" y2="${y0}"/>
            <line class="pg-full" x1="${LEFT}" x2="${W - 16}" y1="${at(T.total)}" y2="${at(T.total)}"/>
            <path class="pg-area" d="${f.area(T.steps, y0, h(r), T.total)}"/>
            ${T.marks.map((m, j) => `<g data-m="${esc(r.id)}:${j}" data-k="m|${esc(r.id)}|${m.t}">${m.signal === 'FAIL'   // a FAIL above the area stands on a stem, so its height reads
                ? `<line class="pg-stem" x1="${f.X(m.t)}" x2="${f.X(m.t)}" y1="${y0}" y2="${at(m.k)}"/>` : ''}${mark(m.signal, f.X(m.t), at(m.k), r.d ? 3.5 : 5)}</g>`).join('')}</g>`;
    }).join('');
    // the axis labelled as the timeline's is (ticks without times read as a grid of nothing — audit B7); the goal's done
    // mark said under the tracks, clear of the labels
    const H = y + 18, root = rs.find(r => !r.d);
    const miles = (root ? tr[root.id].marks : []).filter(m => m.signal === 'PASS').map(m => `<g class="pg-mile"><line x1="${f.X(m.t)}" x2="${f.X(m.t)}" y1="${TOP - 8}" y2="${H}"/>
        <text x="${f.X(m.t) - 4}" y="${H - 3}" text-anchor="end">goal done ${hm(m.t)}</text></g>`).join('');
    return `<svg class="pg" width="${W}" height="${H}">${f.ticks(TOP - 6, H - 14, TOP - 10)}${f.folds(TOP - 6, H - 14, H - 3)}${miles}${body}</svg>`;
}

// The goal's coverage: each root criterion, the parts the split made responsible for it (§2.4), the
// state each of them stands in, and the root's own value for it at its latest verdict.
function coverage(run, nodes, tasks) {
    const root = rootOf(tasks);
    if (!root) return '';
    const maps = root.criterion_mappings || [], st = Object.fromEntries(nodes.map(n => [n.id, n.state]));
    const kids = [...new Set(maps.map(m => m.child_id))], self = run.criteria.status[root.id] || {}, name = run.name;
    // a cancelled part first: a legacy one stands DONE with its reason CANCELLED, and its track already reads cancelled
    const kind = k => cancelled(tasks.find(t => t.id === k)) ? 'gone' : st[k] === 'DONE' ? 'done' : st[k] === 'REWORKING' ? 'rework' : 'open';
    const cell = (c, k) => !maps.some(m => m.criterion_name === c && m.child_id === k) ? '<td></td>'
        : `<td data-node="${esc(k)}" data-k="${esc(`cov|${c}|${k}`)}"${TIP.cell(name(k), c)}><i class="cv cv-${kind(k)}"></i></td>`;
    const rows = run.criteria.names[root.id].map(c => `<tr><th${c.length > 30 ? TIP.cell(c) : ''}>${esc(trim(c, 30))}</th>
        ${kids.map(k => cell(c, k)).join('')}<td class="cv-self">${self[c] === 'pass' || self[c] === 'fail' ? glyph(self[c].toUpperCase())
            : `<span${TIP.noValue((run.rounds[root.id] || []).some(r => r.verdict) ? 'current' : 'unchecked')}>⊥</span>`}</td></tr>`).join('');
    return `<table class="pg-cov"><thead><tr><th class="sec">the goal's criteria</th>
        ${kids.map(k => `<th class="kid" data-node="${esc(k)}"${name(k).length > 14 ? TIP.cell(name(k)) : ''}><span>${esc(trim(name(k), 14))}</span></th>`).join('')}<th class="kid"><span>the goal</span></th></tr></thead>
        <tbody>${rows}</tbody></table>
        <p class="pg-legend">${CELLS.filter(([k]) => k !== 'gone' || kids.some(x => kind(x) === 'gone')).map(([k, t]) => `<i class="cv cv-${k}"></i>${t}`).join(' ')}</p>`;
}

export function render(el, run, nodes, tasks) {
    const name = run.name;
    el.innerHTML = `<div class="pg-wrap"><div class="pg-tracks"></div><div class="pg-side">${coverage(run, nodes, tasks)}</div></div>`;
    let lit;   // the shared selection's paint, re-applied to tracks drawn anew
    const hot = hotIn(run, tasks);
    const tr = el.querySelector('.pg-tracks'), paint = () => { tr.innerHTML = tracks(tr, run, name, tasks, hot); pinLeft(tr.querySelector('svg.pg'), LEFT); lit?.(focus()); };
    // a node selected under a folded part unfolds the path to it, so its track is there to light
    const up = ancestorsIn(tasks);
    const open = id => { let shut = false; for (const x of up(id).slice(0, -1)) if (!unfolded.has(x)) unfolded.add(x), folded.delete(x), shut = true; return shut; };
    if (focus().select) open(focus().select);
    paint();
    watch((st, key) => (key === 'select' || key === 'bring') && st.select && open(st.select) && paint(), el);
    // a part's name unfolds it into its own parts, and folds it again
    tr.onclick = e => { const id = e.target.closest('[data-unfold]')?.dataset.unfold;
        // …a finger's first tap on a cut name shows its whole first (tip.js), its second unfolds
        if (id && !firstTap(e)) { e.stopPropagation(); const d = up(id).length;
            shown(id, d, hot) ? (unfolded.delete(id), folded.add(id)) : (unfolded.add(id), folded.delete(id)); paint(); } };   // unfolding is no selection
    lit = bindFocus(el, e => {
        const g = e.target.closest('[data-m]');
        if (!g) return untip();
        const i = g.dataset.m.lastIndexOf(':'), id = g.dataset.m.slice(0, i), L = run.criteria.track[id], m = L.marks[+g.dataset.m.slice(i + 1)];
        const r = (run.rounds[m.node] || []).find(r => r.at === m.t);
        tip(TIP.verdict(m.signal, r, m.t, {own: m.failed, edges: []}, m, L.total,
            unseen(g.closest('.pg-track')?.querySelector('.pg-level')) && (id === rootOf(tasks)?.id ? "the goal's criteria" : name(id))), e);
    }, untip);
    bringSelected(el, id => tr.querySelector(`.pg-track[data-node="${CSS.escape(id)}"] .pg-band`));
}
