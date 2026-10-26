// What the run cost and where it went: money, tokens and session time, by role, by node, by level.
// Every figure comes from the usage ledger through the run model; one measure per chart, no dual axes.
import {esc, hint} from './dom.js';
import {bindFocus, bringSelected} from './store.js';
import {tip, untip} from './tip.js';
import {dur, trim} from './draw.js';
import {KIND_NAME as KIND, levelName, concurrency} from './run.js';

const usd = x => `$${x < 10 ? x.toFixed(2) : x.toFixed(1)}`, tok = x => x == null ? 'not reported' : x > 1e6 ? `${(x / 1e6).toFixed(1)}M` : `${Math.round(x / 1e3)}k`;

// the shared head of the assignee ids (the project's name), cut at a '-' so the distinct tail stays
const commonPrefix = ids => { if (ids.length < 2) return 0;
    let n = 0; while (ids.every(s => s[n] === ids[0][n]) && n < ids[0].length) n++;
    return ids[0].lastIndexOf('-', n - 1) + 1; };
const tile = (v, label, note = '') => `<div class="cs-tile"><b>${v}</b><span>${label}</span>${note ? `<i>${note}</i>` : ''}</div>`;

// One bar chart: rows of [key, label, parts{exec,val,…}], the bar split by role so the cost of
// checking stands beside the cost of doing. Roles keep their place in every row.
function bars(title, rows, measure, fmt, attr) {
    const max = Math.max(...rows.map(r => Object.values(r.parts).reduce((s, p) => s + measure(p), 0)), 1e-9);
    return `<section class="cs-chart"><h4>${title}</h4>${rows.map(r => {
        const total = Object.values(r.parts).reduce((s, p) => s + measure(p), 0);
        return `<div class="cs-row" ${attr(r)}><span class="cs-label" title="${esc(r.label)}">${esc(trim(r.label, 22))}</span>
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
            ${tile(usd(c.total), 'spent', c.unpriced ? `${c.unpriced} call${c.unpriced > 1 ? 's' : ''} with no cost recorded` : '')}
            ${tile(tok(c.tokens), 'tokens', c.untold && c.tokens != null ? `cache included · ${c.untold} session${c.untold > 1 ? 's' : ''} reported none` : 'cache included')}
            ${tile(dur(run.clock.span), 'run time', run.clock.folds.length ? `idle ${dur(run.clock.folds.reduce((s, f) => s + f.to - f.from, 0))} folded` : '')}
            ${tile(dur(c.busy), 'session time', `${(c.busy / Math.max(run.clock.span, 1)).toFixed(1)}× the run`)}
            ${tile(run.exec.peak, 'executors at once', `validators ${run.val.peak}`)}
        </div>
        <div class="cs-legend">${kinds.map(k => `<span><i class="cs-${k}"></i>${KIND[k]} ${usd(c.byKind[k].cost)} · ${c.byKind[k].calls} sessions · ${dur(c.byKind[k].busy)}</span>`).join('')}</div>
        <div class="cs-grid">
            ${bars('cost by node', nodeRows, p => p.cost, usd, r => `data-node="${esc(r.id)}"`)}
            ${bars('session time by node', nodeRows, p => p.busy, dur, r => `data-node="${esc(r.id)}"`)}
            ${bars('cost by level', levelRows, p => p.cost, usd, () => '')}
            ${bars(`sessions by assignee${cut ? ` <span title="${hint(ids[0].slice(0, cut) + '…', 'the start every assignee id shares, cut from the bars')}">(${esc(ids[0].slice(0, cut))}…)</span>` : ''}`, agentRows, p => p.calls,
                   (n, r) => `${n} · ${r.peak} at once`, () => '')}
        </div></div>`;
    bindFocus(el, e => {
        const row = e.target.closest('.cs-row[data-node]');
        if (!row) return untip();
        const parts = node[row.dataset.node], all = Object.values(parts);
        tip(`<div class="tt-name">${esc(name(row.dataset.node))}</div>
            ${Object.entries(parts).map(([k, p]) => `<div class="tt-row">${KIND[k]}: ${usd(p.cost)} · ${p.calls} sessions · ${dur(p.busy)} · ${tok(p.tokens)} tok</div>`).join('')}
            <div class="tt-row">${rounds(row.dataset.node)} delivery round${rounds(row.dataset.node) === 1 ? '' : 's'} · ${usd(all.reduce((s, p) => s + p.cost, 0))} in all</div>`, e);
    }, untip);
    bringSelected(el, id => el.querySelector(`.cs-row[data-node="${CSS.escape(id)}"]`));
}
