// The run's course: one row per node, its work as bars on the folded clock and every verdict as a mark
// standing ABOVE the bar it answers — the carrier and the mark kept apart — and over the rows how many
// executors ran at once. Del names who is accountable for a node; this names what ran, when, and beside what.
import {esc} from './dom.js';
import {bindFocus} from './store.js';
import {tip, untip} from './tip.js';
import {frame, hm, dur, mark, trim} from './draw.js';
import {KIND_NAME, waitWords, atWork} from './run.js';

const ROW = 26, CONC = 34, TOP = 30 + CONC + 14, LEFT = 140, AXIS = 20, BAR = {exec: 9, val: 4, issuer: 5, plan: 5};
const STEM = 9, JOIN = 3 * 60e3;                                   // a verdict's mark stands this far above its row's bar line

// Rows: the goal's first; then what is at work now; then every node that has worked, in the order it
// first started; the nodes that never ran last, saying what they wait on.
function rows(run, nodes) {
    const first = id => Math.min(...run.sessions.filter(s => s.node === id).map(s => s.start), Infinity);
    const now = atWork(run, nodes), rank = id => run.depth[id] === 0 ? 0 : now.has(id) ? 1 : first(id) < Infinity ? 2 : 3;
    return nodes.map(n => n.id).sort((a, b) => rank(a) - rank(b) || first(a) - first(b) || run.depth[a] - run.depth[b]);
}

// One bar per piece of work: the engine validates a delivery in batches (`validation_batch` probes a session), and
// a call may be retried — so the sessions of one kind on one node that no delivery or verdict separates are ONE
// stretch of work, drawn once; its batches are counted in the tip, its cost summed.
function stretches(run) {
    const cuts = id => (run.rounds[id] || []).flatMap(r => [r.delivered, r.at]).filter(Boolean);
    const out = [];
    for (const s of [...run.sessions].sort((a, b) => a.node.localeCompare(b.node) || a.kind.localeCompare(b.kind) || a.start - b.start)) {
        const last = out.at(-1);
        // back to back only: batches and retries follow each other within a minute or two, a later session is new work
        if (last && last.node === s.node && last.kind === s.kind && s.start - last.end < JOIN
            && !cuts(s.node).some(t => t > last.end + 1e3 && t < s.start - 1e3)) {
            Object.assign(last, {end: Math.max(last.end, s.end), cost: last.cost + s.cost, tokens: last.tokens + s.tokens,
                                 open: last.open || s.open, parts: last.parts + 1, busy: last.busy + (s.end - s.start)});
            if (s.agent && !last.agents.includes(s.agent)) last.agents.push(s.agent);
        } else out.push({...s, parts: 1, busy: s.end - s.start, agents: s.agent ? [s.agent] : []});
    }
    return out;
}

export function render(el, run, nodes) {
    const ids = rows(run, nodes), name = run.name, work = stretches(run);
    const W = Math.max(el.clientWidth, 480), H = TOP + ids.length * ROW + AXIS, f = frame(run, W, LEFT);
    const Y = id => TOP + ids.indexOf(id) * ROW + ROW / 2 + 4;
    const bar = (s, i) => `<rect class="tl-s tl-${s.kind}${s.open ? ' tl-open' : ''}" data-i="${i}" x="${f.X(s.start)}"
        y="${Y(s.node) - BAR[s.kind] / 2}" width="${Math.max(f.X(s.end) - f.X(s.start), 2)}" height="${BAR[s.kind]}" rx="1.5"/>`;
    // a verdict: a hairline stem up from the bar line, the glyph on top — a mark, not a piece of the work
    const marks = id => (run.rounds[id] || []).filter(r => r.verdict).map(r => { const x = f.X(r.at), y = Y(id);
        return `<line class="tl-stem" x1="${x}" x2="${x}" y1="${y - 2}" y2="${y - STEM}"/>${mark(r.verdict, x, y - STEM - 3.5, 3.5)}`; }).join('');
    const state = Object.fromEntries(nodes.map(n => [n.id, n.state]));
    const idle = id => run.sessions.some(s => s.node === id) || state[id] === 'DONE' ? '' : `<text class="tl-wait" x="${LEFT + 8}" y="${Y(id) + 4}">${
        run.waits[id]?.deps.length ? `waits on ${esc(waitWords(run.waits[id], d => trim(name(d), 24)))}` : esc(state[id].toLowerCase())}</text>`;
    const legend = [['exec', 'execution'], ['val', 'validation'], ['issuer', 'issuer']].map(([k, t], i) =>
        `<rect class="tl-${k}" x="${i * 92}" y="${4 - BAR[k] / 2}" width="16" height="${BAR[k]}" rx="1.5"/><text x="${i * 92 + 21}" y="8">${t}</text>`).join('')
        + `${mark('PASS', 262, 4, 3.5)}<text x="269" y="8">PASS</text>${mark('FAIL', 308, 4, 3.5)}<text x="315" y="8">FAIL</text>`;
    const row = id => `<g class="tl-row" data-node="${esc(id)}">
        <rect class="tl-band" x="0" y="${Y(id) - ROW / 2 - 4}" width="${W}" height="${ROW}"/>
        <text class="tl-name${run.depth[id] ? '' : ' tl-goal'}" x="${LEFT - 10}" y="${Y(id) + 4}">${esc(trim(name(id)))}</text>
        ${work.map((s, i) => s.node === id ? bar(s, i) : '').join('')}${marks(id)}${idle(id)}</g>`;
    // how many executors ran at once: its own band with its own scale, a line — not one more row of bars
    const c0 = 30 + CONC, peak = Math.max(run.exec.peak, 1), cy = k => c0 - (k / peak) * (CONC - 6);
    let line = `M${LEFT},${c0}`;
    for (const [t, k] of run.exec.steps) line += `H${f.X(t)}V${cy(k)}`;
    const top = run.exec.steps.find(([, k]) => k === run.exec.peak);
    el.innerHTML = `<svg class="tl" width="${W}" height="${H}">
        ${f.ticks(30, H - AXIS, 22)}${f.folds(30, H - AXIS, H - 6)}
        <g class="tl-legend" transform="translate(${W - 350},0)">${legend}</g>
        <text class="tl-peak" x="${LEFT - 10}" y="${cy(peak) + 3}">${run.exec.peak} at once</text>
        <text class="tl-peak tl-sub" x="${LEFT - 10}" y="${c0}">executors</text>
        <line class="tl-base" x1="${LEFT}" x2="${W - 16}" y1="${c0}" y2="${c0}"/>
        <line class="tl-base dash" x1="${LEFT}" x2="${W - 16}" y1="${cy(peak)}" y2="${cy(peak)}"/>
        <path class="tl-conc" d="${line}"/>
        ${top ? `<circle class="tl-peakdot" cx="${f.X(top[0])}" cy="${cy(peak)}" r="2.5"/>` : ''}
        ${ids.map(row).join('')}
        <line class="tl-split" x1="0" x2="${W}" y1="${TOP + ROW - 4}" y2="${TOP + ROW - 4}"/></svg>`;
    bindFocus(el, e => {
        const s = e.target.closest('.tl-s');
        if (!s) return untip();
        // the round a stretch belongs to: the delivery an execution ended in, the verdict a validation gave
        const x = work[+s.dataset.i], key = x.kind === 'val' ? 'at' : 'delivered';
        const r = (run.rounds[x.node] || []).find(r => r[key] >= x.end - 1e3);
        tip(`<div class="tt-name">${esc(name(x.node))}</div><div class="tt-row">${KIND_NAME[x.kind]}${x.agents.length ? ' · ' + esc(x.agents.join(', ')) : ''}</div>
            <div class="tt-row">${hm(x.start)}–${x.open ? 'now' : hm(x.end)} · ${dur(x.end - x.start)}${x.cost ? ` · $${x.cost.toFixed(2)}` : ''}${x.tokens ? ` · ${Math.round(x.tokens / 1e3)}k tok` : ''}</div>
            ${x.parts > 1 ? `<div class="tt-row">${x.parts} sessions (${x.kind === 'val' ? 'the validator works in batches of probes' : 'retried or continued'}) · ${dur(x.busy)} busy</div>` : ''}
            ${r ? `<div class="tt-row">round ${r.n}${r.verdict ? ' → ' + r.verdict + (r.failed?.length ? ': ' + esc(r.failed.join(', ')) : '') : ''}</div>` : ''}
            ${x.priced === false ? '<div class="tt-row">no cost recorded for this call</div>' : ''}`, e);
    }, untip);
}
