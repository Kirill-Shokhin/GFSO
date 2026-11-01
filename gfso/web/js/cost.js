// What the run cost and where it went: money, tokens and session time, by role, by node, by level.
// Every figure comes from the usage ledger through the run model; one measure per chart, no dual axes.
import {esc, tally, lasting} from './dom.js';
import {TIP, KIND, levelName, sessionsOf} from './hints.js';
import {bindFocus, bringSelected} from './store.js';
import {dur, trim, money as reported, NOT_REPORTED, tok, bare} from './fmt.js';
import {S} from './state.js';
import {concurrency} from './run.js';


// money for sessions some of which reported no price: never a $0.00 for "not reported" (another provider's case)
const money = ps => { const calls = ps.reduce((s, p) => s + p.calls, 0), un = ps.reduce((s, p) => s + (p.unpriced || 0), 0);
    const procs = ps.reduce((s, p) => s + (p.procs ?? p.calls), 0);
    const m = reported(ps.reduce((s, p) => s + p.cost, 0), calls && procs, un);
    return m; };   // …the figure alone: how many went unpriced is one mark of its own, said once (audit C7)
// a chart's rows by its own measure, the largest first: in another chart's order a bar chart reads as noise (audit CQ4)
const byOwn = (rows, m) => [...rows].sort((a, b) => Object.values(b.parts).reduce((s, p) => s + m(p), 0) - Object.values(a.parts).reduce((s, p) => s + m(p), 0));
// a tile's notes each on a line of its own, never joined to one another by a dot
const tile = (v, label, ...notes) => `<div class="cs-tile"><b>${v}</b><span>${label}</span>${notes.filter(Boolean).map(n => `<i>${n}</i>`).join('')}</div>`;

// One bar chart: rows of [key, label, parts{exec,val,…}], the bar split by role so the cost of
// checking stands beside the cost of doing. Roles keep their place in every row.
// …and EACH PART SAYS ONLY ITSELF on its hover — its role, its figure, its share of the row — as the Models tab's cost split
// does; the row's name stands at its left and is said again only where it is cut (the author, 2026-10-31: «первая показывает
// общую мусорную инфу. вторая раздельно по каждой»; «во многих попапах дублируется имя ноды»)
function bars(title, rows, measure, fmt, attr, part, says) {
    const max = Math.max(...rows.map(r => Object.values(r.parts).reduce((s, p) => s + measure(p), 0)), 1e-9);
    const ck = title.replace(/<[^>]*>/g, '');           // the chart, by its title's words: a node's cost and time bars are two things
    return `<section class="cs-chart"><h4>${title}</h4>${rows.map(r => {
        const total = Object.values(r.parts).reduce((s, p) => s + measure(p), 0);
        const rk = `${ck}|${r.id || r.label}`;
        return `<div class="cs-row" ${attr(r)}><span class="cs-label" data-k="${esc(`l|${rk}`)}"${r.label.length > 22 ? TIP.cell(r.label) : ''}>${esc(trim(r.label, 22))}</span>
            <span class="cs-bar">${Object.entries(r.parts).filter(([, p]) => measure(p) > 0).map(([k, p]) => `<i class="cs-${k}" data-k="${esc(`p|${rk}|${k}`)}" style="width:${(measure(p) / max) * 100}%"`
                + `${TIP.part(k, part(p, k), measure(p) / (total || 1), p, says)}></i>`).join('')}</span>
            <span class="cs-num">${fmt(total, r)}</span></div>`; }).join('')}</section>`;
}

export function render(el, run, nodes) {
    const c = run.cost, name = run.name;
    const node = c.byNode, level = c.byDepth;
    // An assignee (Del) is who is accountable for the nodes, not one process: its sessions overlap, so it
    // is shown by how many it ran and how many at once — never as one bar of hours that reads as serial.
    // ids without the project's name, as everywhere (f76e1a9) — no caption naming the cut: `agent` and the system's own
    // sessions never carried it (audit C3); the sessions no assignee ran are the system's planning and issuer turns (C4)
    const ids = Object.keys(c.byAgent);
    const agentRows = ids.map(id => ({id, label: id === '—' ? 'the system' : bare(id, S.project), parts: c.byAgent[id],
        peak: concurrency(run.sessions.filter(s => (s.agent || '—') === id && !s.open)).peak}))
        .sort((a, b) => b.peak - a.peak || a.label.localeCompare(b.label));
    const nodeRows = Object.entries(node).map(([id, parts]) => ({id, label: name(id), parts}))
        .sort((a, b) => Object.values(b.parts).reduce((s, p) => s + p.cost, 0) - Object.values(a.parts).reduce((s, p) => s + p.cost, 0));
    const levelRows = Object.entries(level).sort(([a], [b]) => a - b).map(([d, parts]) => ({label: levelName(d), parts}));
    const kinds = Object.keys(KIND).filter(k => c.byKind[k]);
    el.innerHTML = `<div class="cs">
        <div class="cs-tiles">
            ${tile(money(Object.values(c.byKind)), 'spent', c.unpriced && tally(c.unpriced, 'unpriced', TIP.unpriced))}
            ${tile(tok(c.tokens), 'tokens', 'cache included', c.untold && c.tokens != null && tally(c.untold, 'reported none'))}
            ${tile(lasting(run.clock.from, run.clock.span), 'run time', run.clock.folds.length && tally(dur(run.clock.folds.reduce((s, f) => s + f.to - f.from, 0)), 'idle, folded'))}
            ${tile(dur(c.busy), 'session time', tally(`${(c.busy / Math.max(run.clock.span, 1)).toFixed(1)}×`, 'the run'))}
            ${tile(run.exec.peak, 'executors at once', tally(run.val.peak, 'validators'))}
        </div>
        <div class="cs-legend">${kinds.map(k => `<span><i class="cs-${k}"></i>${KIND[k].name} <b>${money([c.byKind[k]])}</b>`
            + `<em>${tally(c.byKind[k].calls, (KIND[k]?.count || k) + (c.byKind[k].calls === 1 ? '' : 's'))}${tally(dur(c.byKind[k].busy), 'busy')}</em></span>`).join('')}</div>
        <div class="cs-grid">
            ${bars('cost by node', nodeRows, p => p.cost, (t, r) => money(Object.values(r.parts)), r => `data-node="${esc(r.id)}"`, p => money([p]), 'cost')}
            ${bars('session time by node', byOwn(nodeRows, p => p.busy), p => p.busy, dur, r => `data-node="${esc(r.id)}"`, p => dur(p.busy), 'busy')}
            ${bars('cost by level', levelRows, p => p.cost, (t, r) => money(Object.values(r.parts)), () => '', p => money([p]), 'cost')}
            ${bars('sessions by assignee', agentRows, p => p.calls,
                   (n, r) => `${n}<span class="cs-also">${r.peak} at once</span>`, r => r.id === '—' ? TIP.system : '', (p, k) => sessionsOf(k, p.calls), 'calls')}
        </div></div>`;
    bindFocus(el);
    bringSelected(el, id => el.querySelector(`.cs-row[data-node="${CSS.escape(id)}"]`));
}
