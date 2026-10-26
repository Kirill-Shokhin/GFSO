// Progress by criteria along the split: the goal's own criteria, then one track per part with ITS own criteria, and a
// part unfolds into its parts. Each track counts one node's criteria passing at its own verdicts — a part's PASS is its
// issuer's signature at that seam, the root's PASS the goal delivered — never a sum across a level, which added parts
// of unrelated parents (author, 2026-10-25). Counts, not percentages: a share is not a verdict (canon §7.4).
import {esc, hint} from './dom.js';
import {bindFocus, bringSelected, focus, watch} from './store.js';
import {tip, untip} from './tip.js';
import {frame, hm, mark, glyph, trim} from './draw.js';
import {countWords} from './run.js';

const LEFT = 220, GOAL = 54, PART = 30, GAP = 12, TOP = 22, INDENT = 12;
const unfolded = new Set();                      // parts the reader opened; the goal is always open

// the rows in tree order: the goal, its parts, and the parts of every part the reader unfolded
function rows(tasks, track) {
    const kids = {}, out = [];
    for (const t of tasks) if (t.parent_id) (kids[t.parent_id] ??= []).push(t.id);
    // siblings that have a verdict first, by their first one, then the rest in plan order — as the timeline orders its
    // rows; in plan order the one part at work sat under nine empty tracks, below the fold of a short deck (critic)
    const first = id => track[id]?.marks[0]?.t ?? Infinity;
    for (const ks of Object.values(kids)) ks.sort((a, b) => first(a) - first(b));
    const walk = (id, d) => {
        if (track[id]?.total) out.push({id, d, kids: (kids[id] || []).length});
        if (d === 0 || unfolded.has(id)) for (const k of kids[id] || []) walk(k, d + 1);
    };
    for (const t of tasks) if (!t.parent_id) walk(t.id, 0);
    return out;
}

function tracks(el, run, name, tasks) {
    const tr = run.criteria.track, rs = rows(tasks, tr), h = r => r.d ? PART : GOAL;
    const W = Math.max(el.clientWidth, 480), f = frame(run, W, LEFT);
    let y = TOP;
    const body = rs.map(r => {
        const T = tr[r.id], y0 = (y += h(r)), top = y0 - h(r), at = k => y0 - (k / T.total) * h(r), lm = T.marks.at(-1);
        const last = lm?.atMost ? `≤ ${lm.k}` : T.steps.at(-1)?.[1] ?? (lm ? lm.k : 0);   // an unrecorded FAIL gives a bound only
        y += GAP;
        const lx = 8 + Math.max(r.d - 1, 0) * INDENT;
        const caret = r.kids && r.d ? `<tspan class="pg-caret">${unfolded.has(r.id) ? '▾' : '▸'} </tspan>` : '';
        return `<g class="pg-track${r.d ? ' pg-part' : ''}" data-node="${esc(r.id)}">
            <rect class="pg-band" x="0" y="${top - GAP / 2}" width="${W}" height="${h(r) + GAP}"/>
            <text class="pg-level" x="${lx}" y="${top + 10}" ${r.kids && r.d ? `data-unfold="${esc(r.id)}"` : ''}>${caret}${esc(trim(r.d ? name(r.id) : "the goal's criteria", 34 - Math.max(r.d - 1, 0) * 2))}</text>
            <text class="pg-count" x="${LEFT - 10}" y="${top + (r.d ? 24 : 28)}">${last}<tspan> of ${T.total}</tspan></text>
            <line class="pg-base" x1="${LEFT}" x2="${W - 16}" y1="${y0}" y2="${y0}"/>
            <line class="pg-full" x1="${LEFT}" x2="${W - 16}" y1="${at(T.total)}" y2="${at(T.total)}"/>
            <path class="pg-area" d="${f.area(T.steps, y0, h(r), T.total)}"/>
            ${T.marks.map((m, j) => `<g data-m="${esc(r.id)}:${j}">${m.atMost
                ? `<line class="pg-range" x1="${f.X(m.t)}" x2="${f.X(m.t)}" y1="${y0}" y2="${at(m.k)}"/>` : ''}${mark(m.signal, f.X(m.t), at(m.k), r.d ? 3.5 : 5)}</g>`).join('')}</g>`;
    }).join('');
    const H = y + 6, root = rs.find(r => !r.d);
    const miles = (root ? tr[root.id].marks : []).filter(m => m.signal === 'PASS').map(m => `<g class="pg-mile"><line x1="${f.X(m.t)}" x2="${f.X(m.t)}" y1="${TOP - 8}" y2="${H}"/>
        <text x="${f.X(m.t) - 4}" y="${TOP - 10}">goal delivered ${hm(m.t)}</text></g>`).join('');
    return `<svg class="pg" width="${W}" height="${H}">${f.ticks(TOP - 6, H)}${f.folds(TOP - 6, H, H)}${miles}${body}</svg>`;
}

// The goal's coverage: each root criterion, the parts the split made responsible for it (§2.4), the
// state each of them stands in, and the root's own value for it at its latest verdict.
function coverage(run, nodes, tasks) {
    const root = tasks.find(t => !t.parent_id);
    if (!root) return '';
    const maps = root.criterion_mappings || [], st = Object.fromEntries(nodes.map(n => [n.id, n.state]));
    const kids = [...new Set(maps.map(m => m.child_id))], self = run.criteria.status[root.id] || {}, name = run.name;
    const cell = (c, k) => !maps.some(m => m.criterion_name === c && m.child_id === k) ? '<td></td>'
        : `<td data-node="${esc(k)}" title="${hint(name(k), st[k])}"><i class="cv cv-${st[k] === 'DONE' ? 'done' : st[k] === 'REWORKING' ? 'rework' : 'open'}"></i></td>`;
    const rows = run.criteria.names[root.id].map(c => `<tr><th title="${esc(c)}">${esc(trim(c, 30))}</th>
        ${kids.map(k => cell(c, k)).join('')}<td class="cv-self">${self[c] === 'pass' || self[c] === 'fail' ? glyph(self[c].toUpperCase()) : '⊥'}</td></tr>`).join('');
    return `<table class="pg-cov"><thead><tr><th class="sec">the goal's criteria</th>
        ${kids.map(k => `<th class="kid" data-node="${esc(k)}"><span>${esc(trim(name(k), 14))}</span></th>`).join('')}<th class="kid"><span>root</span></th></tr></thead>
        <tbody>${rows}</tbody></table>
        <p class="pg-legend"><i class="cv cv-done"></i>part done <i class="cv cv-open"></i>part open <i class="cv cv-rework"></i>part in rework
        — a cell is the STATE of a part responsible for the row (§2.4), not a verdict on it; the row's value is the root's own, right.</p>`;
}

export function render(el, run, nodes, tasks) {
    const name = run.name;
    el.innerHTML = `<div class="pg-wrap"><div class="pg-tracks"></div><div class="pg-side">${coverage(run, nodes, tasks)}</div></div>`;
    let lit;   // the shared selection's paint, re-applied to tracks drawn anew
    const tr = el.querySelector('.pg-tracks'), paint = () => { tr.innerHTML = tracks(tr, run, name, tasks); lit?.(focus()); };
    // a node selected under a folded part unfolds the path to it, so its track is there to light
    const parent = Object.fromEntries(tasks.map(t => [t.id, t.parent_id]));
    const open = id => { let shut = false; for (let x = parent[id]; x && parent[x]; x = parent[x]) if (!unfolded.has(x)) unfolded.add(x), shut = true; return shut; };
    if (focus().select) open(focus().select);
    paint();
    watch((st, key) => (key === 'select' || key === 'bring') && st.select && open(st.select) && paint(), el);
    // a part's name unfolds it into its own parts, and folds it again
    tr.onclick = e => { const id = e.target.closest('[data-unfold]')?.dataset.unfold;
        if (id) { e.stopPropagation(); unfolded.has(id) ? unfolded.delete(id) : unfolded.add(id); paint(); } };   // unfolding is no selection
    lit = bindFocus(el, e => {
        const g = e.target.closest('[data-m]');
        if (!g) return untip();
        const i = g.dataset.m.lastIndexOf(':'), id = g.dataset.m.slice(0, i), L = run.criteria.track[id], m = L.marks[+g.dataset.m.slice(i + 1)];
        const r = (run.rounds[m.node] || []).find(r => r.at === m.t);
        tip(`<div class="tt-name">${esc(name(m.node))}</div>
            <div class="tt-row">${m.signal}${r ? ` · round ${r.n}` : ''} · ${hm(m.t)}</div>
            ${m.failed.length ? `<div class="tt-row">failed: ${esc(m.failed.join(', '))}</div>` : ''}
            <div class="tt-row">${countWords(m, L.total)}</div>`, e);
    }, untip);
    bringSelected(el, id => tr.querySelector(`.pg-track[data-node="${CSS.escape(id)}"] .pg-band`));
}
