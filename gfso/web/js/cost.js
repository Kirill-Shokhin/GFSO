// What the run cost and where it went: money, tokens and session time, by role, by node, by level.
// Every figure comes from the usage ledger through the run model; one measure per chart, no dual axes.
import {esc, tally, lasting} from './dom.js';
import {TIP, meter, sessionsOf, KIND, levelName} from './hints.js';
import {bindFocus, bringSelected} from './store.js';
import {tip, untip} from './tip.js';
import {dur, trim, money as reported, NOT_REPORTED, tok} from './fmt.js';
import {concurrency, byRole} from './run.js';


// the shared head of the assignee ids (the project's name), cut at a '-' so the distinct tail stays
const commonPrefix = ids => { if (ids.length < 2) return 0;
    let n = 0; while (ids.every(s => s[n] === ids[0][n]) && n < ids[0].length) n++;
    return ids[0].lastIndexOf('-', n - 1) + 1; };
// money for sessions some of which reported no price: never a $0.00 for "not reported" (another provider's case)
const money = ps => { const calls = ps.reduce((s, p) => s + p.calls, 0), un = ps.reduce((s, p) => s + (p.unpriced || 0), 0);
    const procs = ps.reduce((s, p) => s + (p.procs ?? p.calls), 0);
    const m = reported(ps.reduce((s, p) => s + p.cost, 0), calls && procs, un);
    return m === NOT_REPORTED || !un ? m : `${m} + ${un} not priced`; };
// a tile's notes each on a line of its own, never joined to one another by a dot
const tile = (v, label, ...notes) => `<div class="cs-tile"><b>${v}</b><span>${label}</span>${notes.filter(Boolean).map(n => `<i>${n}</i>`).join('')}</div>`;

// One bar chart: rows of [key, label, parts{exec,val,…}], the bar split by role so the cost of
// checking stands beside the cost of doing. Roles keep their place in every row.
function bars(title, rows, measure, fmt, attr) {
    const max = Math.max(...rows.map(r => Object.values(r.parts).reduce((s, p) => s + measure(p), 0)), 1e-9);
    return `<section class="cs-chart"><h4>${title}</h4>${rows.map(r => {
        const total = Object.values(r.parts).reduce((s, p) => s + measure(p), 0);
        return `<div class="cs-row" ${attr(r)}><span class="cs-label"${r.label.length > 22 ? TIP.cell(r.label) : ''}>${esc(trim(r.label, 22))}</span>
            <span class="cs-bar">${Object.entries(r.parts).map(([k, p]) => `<i class="cs-${k}" style="width:${(measure(p) / max) * 100}%"></i>`).join('')}</span>
            <span class="cs-num">${fmt(total, r)}</span></div>`; }).join('')}</section>`;
}

export function render(el, run, nodes) {
    const c = run.cost, name = run.name;
    const node = c.byNode, level = c.byDepth;
    // An assignee (Del) is who is accountable for the nodes, not one process: its sessions overlap, so it
    // is shown by how many it ran and how many at once — never as one bar of hours that reads as serial.
    const ids = Object.keys(c.byAgent), cut = commonPrefix(ids);
    const agentRows = ids.map(id => ({id, label: id.slice(cut) || id, parts: c.byAgent[id],
        peak: concurrency(run.sessions.filter(s => (s.agent || '—') === id && !s.open)).peak}))
        .sort((a, b) => b.peak - a.peak || a.label.localeCompare(b.label));
    const rounds = id => (run.rounds[id] || []).length;
    const nodeRows = Object.entries(node).map(([id, parts]) => ({id, label: name(id), parts}))
        .sort((a, b) => Object.values(b.parts).reduce((s, p) => s + p.cost, 0) - Object.values(a.parts).reduce((s, p) => s + p.cost, 0));
    const levelRows = Object.entries(level).sort(([a], [b]) => a - b).map(([d, parts]) => ({label: levelName(d), parts}));
    const kinds = Object.keys(KIND).filter(k => c.byKind[k]);
    el.innerHTML = `<div class="cs">
        <div class="cs-tiles">
            ${tile(money(Object.values(c.byKind)), 'spent', c.unpriced && tally(c.unpriced, 'with no cost recorded'))}
            ${tile(tok(c.tokens), 'tokens', 'cache included', c.untold && c.tokens != null && tally(c.untold, 'reported none'))}
            ${tile(lasting(run.clock.from, run.clock.span), 'run time', run.clock.folds.length && tally(dur(run.clock.folds.reduce((s, f) => s + f.to - f.from, 0)), 'idle, folded'))}
            ${tile(dur(c.busy), 'session time', tally(`${(c.busy / Math.max(run.clock.span, 1)).toFixed(1)}×`, 'the run'))}
            ${tile(run.exec.peak, 'executors at once', tally(run.val.peak, 'validators'))}
        </div>
        <div class="cs-legend">${kinds.map(k => `<span><i class="cs-${k}"></i>${KIND[k].name} <b>${money([c.byKind[k]])}</b>`
            + `<em>${tally(c.byKind[k].calls, (KIND[k]?.count || k) + (c.byKind[k].calls === 1 ? '' : 's'))}${tally(dur(c.byKind[k].busy), 'busy')}</em></span>`).join('')}</div>
        <div class="cs-grid">
            ${bars('cost by node', nodeRows, p => p.cost, (t, r) => money(Object.values(r.parts)), r => `data-node="${esc(r.id)}"`)}
            ${bars('session time by node', nodeRows, p => p.busy, dur, r => `data-node="${esc(r.id)}"`)}
            ${bars('cost by level', levelRows, p => p.cost, (t, r) => money(Object.values(r.parts)), () => '')}
            ${bars(`sessions by assignee${cut ? ` <span${TIP.prefix(ids[0].slice(0, cut))}>(${esc(ids[0].slice(0, cut))}…)</span>` : ''}`, agentRows, p => p.calls,
                   (n, r) => `${n}, ${r.peak} at once`, () => '')}
        </div></div>`;
    bindFocus(el, e => {
        const row = e.target.closest('.cs-row[data-node]');
        if (!row) return untip();
        const parts = node[row.dataset.node], all = Object.values(parts);
        tip(TIP.cost(name(row.dataset.node), [...byRole(parts).map(([k, p, share]) => meter(sessionsOf(k, p.calls), share, money([p]))),
                     `${dur(all.reduce((s, p) => s + p.busy, 0))} of sessions, ${tok(all.reduce((s, p) => s + (p.tokens || 0), 0))} tokens`],
                     rounds(row.dataset.node), money(all)), e);
    }, untip);
    bringSelected(el, id => el.querySelector(`.cs-row[data-node="${CSS.escape(id)}"]`));
}
