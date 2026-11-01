// The run's course: one row per node, its work as bars on the folded clock and every verdict as a mark
// standing ABOVE the bar it answers — the carrier and the mark kept apart — and over the rows how many
// executors ran at once. Del names who is accountable for a node; this names what ran, when, and beside what.
import {esc, unseen} from './dom.js';
import {bindFocus, bringSelected} from './store.js';
import {tip, untip} from './tip.js';
import {frame, axisWidth, mark} from './draw.js';
import {trim, bare} from './fmt.js';
import {S} from './state.js';
import {failedOf} from './run.js';
import {label} from './vocab.js';
import {TIP, KIND, waitWords} from './hints.js';

// an outlined bar (an issuer's turn, a consent) is drawn over the filled ones: it can run beside an execution or a
// validation (a challenge answered while the work goes on), and beneath them it hid; its outline shows what lies under it
const HOLLOW = new Set(['consent', 'issuer']);
// an outlined kind narrower than THIN px is drawn as a filled tick of its outline's ink: a few px of outline read as «0»
// beside a name (audit B3)
const OUTLINED = new Set([...HOLLOW, 'plan']), THIN = 6;
const ROW = 26, CONC = 34, TOP = 30 + CONC + 14, LEFT = 140, AXIS = 20, BAR = {exec: 9, consent: 5, val: 4, issuer: 5, plan: 5};
const STEM = 9, JOIN = 3 * 60e3;                                   // a verdict's mark stands this far above its row's bar line

// Rows: the goal's first; then what is at work now; then every node that has worked, in the order it
// first started; the nodes that never ran last, saying what they wait on.
function rows(run, nodes) {
    const first = id => Math.min(...run.sessions.filter(s => s.node === id).map(s => s.start), Infinity);
    const now = run.now.work, rank = id => run.depth[id] === 0 ? 0 : now.has(id) ? 1 : first(id) < Infinity ? 2 : 3;
    return nodes.map(n => n.id).sort((a, b) => rank(a) - rank(b) || first(a) - first(b) || run.depth[a] - run.depth[b]);
}

// One bar per piece of work: the engine validates a delivery in batches (`validation_batch` probes a session), and
// a call may be retried — so the sessions of one kind on one node that no delivery or verdict separates are ONE
// a handover: when the session wrote its note, and how full its context stood then against its model's whole window
const cut = s => ({t: s.end, peak: s.peak, window: s.window, budget: s.budget});

// stretch of work, drawn once; its batches are counted in the tip, its cost summed.
function stretches(run) {
    const cuts = id => (run.rounds[id] || []).flatMap(r => [r.delivered, r.at]).filter(Boolean);
    const out = [];
    for (const s of [...run.sessions].sort((a, b) => a.node.localeCompare(b.node) || a.kind.localeCompare(b.kind) || a.start - b.start)) {
        const last = out.at(-1);
        // back to back only: batches and retries follow each other within a minute or two, a later session is new work
        if (last && last.node === s.node && last.kind === s.kind && s.start - last.end < JOIN
            && !cuts(s.node).some(t => t > last.end - 1e3 && t <= s.start + 1e3)) {
            Object.assign(last, {end: Math.max(last.end, s.end), cost: last.cost + s.cost, tokens: last.tokens + s.tokens,
                                 open: last.open || s.open, parts: last.parts + 1, busy: last.busy + (s.ms ?? s.end - s.start),
                                 continued: (last.continued || 0) + (s.resumed ? 1 : 0)});
            if (s.agent && !last.agents.includes(s.agent)) last.agents.push(s.agent);
            if (s.handover) last.handed.push(cut(s));
            last.members.push(s);
        } else out.push({...s, parts: 1, busy: s.ms ?? s.end - s.start, agents: s.agent ? [s.agent] : [], handed: s.handover ? [cut(s)] : [], members: [s]});
    }
    // what is left of its processes once those that continued or were handed over are counted: retries
    for (const x of out) x.retried = x.parts - 1 - (x.continued || 0) - x.handed.length;
    return out;
}

export function render(el, run, nodes) {
    const ids = rows(run, nodes), name = run.name, work = stretches(run);
    const W = axisWidth(el), H = TOP + ids.length * ROW + AXIS, f = frame(run, W, LEFT);
    const Y = id => TOP + ids.indexOf(id) * ROW + ROW / 2 + 4;
    // A STRETCH PASSED ON from session to session is drawn as its sessions, each its own piece of the bar between the cuts and
    // its own tip — its time, cost, tokens, its round, and where it stood when it passed on, against its budget and window
    // (the author, 2026-10-31: «вместо того чтобы показывать инфу на самом исполнении, она отображается между ними в
    // разделении, а на самом исполнении одна и та же длинная инфа»); the cut is only the line between two pieces
    const rect = (s, i, a, b, p) => { const w = f.X(b) - f.X(a), thin = OUTLINED.has(s.kind) && w < THIN;
        return `<rect class="tl-s tl-${s.kind}${thin ? ' tl-thin' : ''}${s.open ? ' tl-open' : ''}" data-i="${i}"${p == null ? '' : ` data-p="${p}"`}`
        + ` data-k="b|${esc(s.node)}|${s.kind}|${a}" x="${f.X(a)}" y="${Y(s.node) - BAR[s.kind] / 2}" width="${Math.max(w, thin ? 3 : 2)}" height="${BAR[s.kind]}" rx="1.5"/>`; };
    const bar = (s, i) => !s.handed.length ? rect(s, i, s.start, s.end)
        : s.members.map((m, p) => rect(s, i, m.start, s.members[p + 1]?.start ?? s.end, p)).join('')
          + s.handed.map(({t}) => `<line class="tl-hand" x1="${f.X(t)}" x2="${f.X(t)}" y1="${Y(s.node) - BAR[s.kind] / 2 - 2}" y2="${Y(s.node) + BAR[s.kind] / 2 + 2}"/>`).join('');
    // a verdict: a hairline stem up from the bar line, the glyph on top — a mark, not a piece of the work
    const marks = id => (run.rounds[id] || []).filter(r => r.verdict).map(r => { const x = f.X(r.at), y = Y(id);
        return `<g class="tl-v" data-v="${r.n}" data-k="v|${esc(id)}|${r.n}"><line class="tl-stem" x1="${x}" x2="${x}" y1="${y - 2}" y2="${y - STEM}"/>${mark(r.verdict, x, y - STEM - 3.5, 3.5)}</g>`; }).join('');
    const state = Object.fromEntries(nodes.map(n => [n.id, n.state]));
    // the names it waits on cut to fit: the whole of them on hover
    const waitsOn = (id, cut) => `waits on ${waitWords(run.waits[id], d => cut ? trim(name(d), 24) : name(d))}`;
    const idle = id => run.sessions.some(s => s.node === id) || state[id] === 'DONE' ? '' : !run.waits[id]?.deps.length
        ? `<text class="tl-wait" x="${LEFT + 8}" y="${Y(id) + 4}">${esc(label(state[id]).toLowerCase())}</text>`
        : `<text class="tl-wait" x="${LEFT + 8}" y="${Y(id) + 4}"${TIP.cell(waitsOn(id))}>${esc(waitsOn(id, true))}</text>`;
    // the bar kinds are a LABEL (hints.js): read each time, so drawn beside the bars; PASS and FAIL are the key's
    // consent shown only where a run has it: rows recorded before it was booked apart have none
    // …and planning only where the run planned (audit B4: 25 planning bars stood with no word for them)
    const has = k => run.sessions.some(s => s.kind === k);
    const kinds = ['exec', ...(has('consent') ? ['consent'] : []), 'val', 'issuer', ...(has('plan') ? ['plan'] : [])], legendW = kinds.length * 92;
    const legend = kinds.map((k, i) =>
        `<rect class="tl-${k}" x="${i * 92}" y="${4 - BAR[k] / 2}" width="16" height="${BAR[k]}" rx="1.5"/><text x="${i * 92 + 21}" y="8">${KIND[k].name}</text>`).join('');
    const row = id => `<g class="tl-row" data-node="${esc(id)}">
        <rect class="tl-band" x="0" y="${Y(id) - ROW / 2 - 4}" width="${W}" height="${ROW}"/>
        <text class="tl-name${run.depth[id] ? '' : ' tl-goal'}" data-k="n|${esc(id)}" x="${LEFT - 10}" y="${Y(id) + 4}"${name(id) !== trim(name(id)) ? TIP.cell(name(id)) : ''}>${esc(trim(name(id)))}</text>
        ${work.map((s, i) => s.node === id && !HOLLOW.has(s.kind) ? bar(s, i) : '').join('')}${work.map((s, i) => s.node === id && HOLLOW.has(s.kind) ? bar(s, i) : '').join('')}${marks(id)}${idle(id)}</g>`;
    // how many executors ran at once: its own band with its own scale, a line — not one more row of bars
    const c0 = 30 + CONC, peak = Math.max(run.exec.peak, 1), cy = k => c0 - (k / peak) * (CONC - 6);
    let line = `M${LEFT},${c0}`;
    for (const [t, k] of run.exec.steps) line += `H${f.X(t)}V${cy(k)}`;
    const top = run.exec.steps.find(([, k]) => k === run.exec.peak);
    el.innerHTML = `<svg class="tl" width="${W}" height="${H}">
        ${f.ticks(30, H - AXIS, 22)}${f.folds(30, H - AXIS, H - 6)}
        <g class="tl-legend" transform="translate(${W - legendW},0)">${legend}</g>
        <text class="tl-peak" x="${LEFT - 10}" y="${cy(peak) + 3}"><tspan class="tl-fig">${run.exec.peak}</tspan> at once</text>
        <text class="tl-peak tl-sub" x="${LEFT - 10}" y="${c0}">executors</text>
        <line class="tl-base" x1="${LEFT}" x2="${W - 16}" y1="${c0}" y2="${c0}"/>
        <line class="tl-base dash" x1="${LEFT}" x2="${W - 16}" y1="${cy(peak)}" y2="${cy(peak)}"/>
        <path class="tl-conc" d="${line}"/>
        ${top ? `<circle class="tl-peakdot" cx="${f.X(top[0])}" cy="${cy(peak)}" r="2.5"/>` : ''}
        ${ids.map(row).join('')}
        <line class="tl-split" x1="0" x2="${W}" y1="${TOP + ROW - 4}" y2="${TOP + ROW - 4}"/></svg>`;
    // who ran a stretch, only where its node had more than one for that kind of work, without the project's name its id
    // carries (a prefix common to every agent was none: the user's own `agent` shares nothing — critic 17)
    const who = x => new Set(work.filter(w => w.node === x.node && w.kind === x.kind).flatMap(w => w.agents)).size > 1 && x.agents.map(a => bare(a, S.project)).join(', ');
    // the row's name in a tip only where its label is off the screen
    const named = id => unseen(el.querySelector(`.tl-row[data-node="${CSS.escape(id)}"] .tl-name`)) && name(id);
    bindFocus(el, e => {
        // a verdict: its round, what it failed, and how many of the node's own criteria pass after it
        const v = e.target.closest('[data-v]');
        if (v) {
            const id = v.closest('[data-node]').dataset.node, r = run.rounds[id].find(r => String(r.n) === v.dataset.v);
            const T = run.criteria.track[id], m = T?.marks.find(m => m.t === r.at), f = failedOf(run, id, r.failed);
            return tip(TIP.verdict(r.verdict, r, r.at, f, m, T?.total, named(id)), e);
        }
        const s = e.target.closest('.tl-s');
        if (!s) return untip();
        // the round a stretch belongs to: the delivery an execution ended in, the verdict a validation gave
        const x = work[+s.dataset.i], key = x.kind === 'val' ? 'at' : 'delivered', round = end => (run.rounds[x.node] || []).find(r => r[key] >= end - 1e3);
        if (s.dataset.p != null) { const p = +s.dataset.p, m = x.members[p];      // one session of a stretch passed on
            const r = round(m.end); return tip(TIP.session(m, x, p, r, r?.failed?.length ? failedOf(run, x.node, r.failed) : null, named(x.node), who(x)), e); }
        const r = round(x.end);
        tip(TIP.bar(x, r, r?.failed?.length ? failedOf(run, x.node, r.failed) : null, named(x.node), who(x)), e);
    }, untip);
    bringSelected(el, id => el.querySelector(`.tl-row[data-node="${CSS.escape(id)}"] .tl-band`));
}
