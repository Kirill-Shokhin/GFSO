// Progress by criteria, one track per tree level on the run's clock, and the goal's own coverage.
// A part's PASS is its issuer's signature at that seam; the root's PASS is the goal delivered — so
// each level is its own count ("k of N criteria passing at their latest verdict"), never one curve,
// and the root's verdicts cross every track as the milestones they are. Counts, not percentages:
// a share is not a verdict (canon §7.4).
import {esc, hint} from './dom.js';
import {bindFocus} from './store.js';
import {tip, untip} from './tip.js';
import {frame, hm, mark, glyph, trim} from './draw.js';
import {levelName} from './run.js';
// a track counts CRITERIA passing, not nodes: "its parts 3 of 31" read as parts (critic)
const criteriaOf = d => +d === 0 ? "the goal's criteria" : +d === 1 ? "its parts' criteria" : `criteria, level ${d}`;

const LEFT = 140, TRACK = 54, GAP = 14, TOP = 22;

function tracks(el, run, name) {
    const ls = Object.entries(run.criteria.levels).filter(([, L]) => L.total).sort(([a], [b]) => a - b);
    const W = Math.max(el.clientWidth, 480), H = TOP + ls.length * (TRACK + GAP) + 6, f = frame(run, W, LEFT);
    const goal = run.criteria.levels[0]?.marks.filter(m => m.signal === 'PASS') || [];
    const body = ls.map(([d, L], i) => {
        const y0 = TOP + i * (TRACK + GAP) + TRACK, y = k => y0 - (k / L.total) * TRACK, last = L.steps.at(-1)?.[1] ?? 0;
        return `<g class="pg-track">
            <text class="pg-level" x="${LEFT - 10}" y="${y0 - TRACK + 10}">${criteriaOf(d)}</text>
            <text class="pg-count" x="${LEFT - 10}" y="${y0 - TRACK + 28}">${last}<tspan> of ${L.total}</tspan></text>
            <line class="pg-base" x1="${LEFT}" x2="${W - 16}" y1="${y0}" y2="${y0}"/>
            <line class="pg-full" x1="${LEFT}" x2="${W - 16}" y1="${y(L.total)}" y2="${y(L.total)}"/>
            <path class="pg-area" d="${f.area(L.steps, y0, TRACK, L.total)}"/>
            ${L.marks.map((m, j) => `<g data-node="${esc(m.node)}" data-m="${d}:${j}">${mark(m.signal, f.X(m.t), y(m.k), +d ? 3.5 : 5)}</g>`).join('')}</g>`;
    }).join('');
    const miles = goal.map(m => `<g class="pg-mile"><line x1="${f.X(m.t)}" x2="${f.X(m.t)}" y1="${TOP - 8}" y2="${H}"/>
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
    const tr = el.querySelector('.pg-tracks');
    tr.innerHTML = tracks(tr, run, name);
    bindFocus(el, e => {
        const g = e.target.closest('[data-m]');
        if (!g) return untip();
        const [d, j] = g.dataset.m.split(':'), m = run.criteria.levels[d].marks[j], L = run.criteria.levels[d];
        const r = (run.rounds[m.node] || []).find(r => r.at === m.t);
        tip(`<div class="tt-name">${esc(name(m.node))}</div>
            <div class="tt-row">${m.signal}${r ? ` · round ${r.n}` : ''} · ${hm(m.t)}</div>
            ${m.failed.length ? `<div class="tt-row">failed: ${esc(m.failed.join(', '))}</div>` : ''}
            <div class="tt-row">${levelName(d)}: ${m.k} of ${L.total} criteria passing after it</div>`, e);
    }, untip);
}
