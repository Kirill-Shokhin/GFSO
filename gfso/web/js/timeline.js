// The run's course: one row per node, its work as bars on the folded clock and every verdict as a mark
// standing ABOVE the bar it answers — the carrier and the mark kept apart — and over the rows how many
// executors ran at once. Del names who is accountable for a node; this names what ran, when, and beside what.
import {esc, unseen, tallySvg} from './dom.js';
import {bindFocus, bringSelected} from './store.js';
import {tip, untip} from './tip.js';
import {frame, axisWidth, mark, pinLeft} from './draw.js';
import {trim, bare} from './fmt.js';
import {S} from './state.js';
import {failedOf} from './run.js';
import {label} from './vocab.js';
import {TIP, KIND} from './hints.js';

// the side kinds (a consent, an issuer's turn, a planning session) run on a thin lane of their own under the row's work:
// drawn over an execution they hid what ran (audit BQ1); filled in their tone on the kinds' one ramp (gfso.css --k-*)
const SIDE = new Set(['consent', 'issuer', 'plan']), LANE = 9;
// the name column takes the room a wide screen has, so a name is read whole, not cut at 20 characters (BQ1)
const gutter = W => Math.round(Math.min(260, Math.max(140, W * 0.16)));
const ROW = 34, CONC = 34, TOP = 30 + CONC + 14, AXIS = 20, BAR = {exec: 9, consent: 5, val: 4, issuer: 5, plan: 5};
const STEM = 7, JOIN = 3 * 60e3;                                   // a verdict's mark stands this far above its row's bar line

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
    // …nor a dispute or a block: the work stood still through it, and one bar across it said «1 retried» (critic, on a real run)
    const halts = run.audit.filter(a => /CHALLENGE|BLOCK/.test(a.signal || ''));
    const cuts = id => [...(run.rounds[id] || []).flatMap(r => [r.delivered, r.at]), ...halts.filter(a => a.task_id === id).map(a => a.t)].filter(Boolean);
    const out = [];
    for (const s of [...run.sessions].sort((a, b) => a.node.localeCompare(b.node) || a.kind.localeCompare(b.kind) || a.start - b.start)) {
        const last = out.at(-1);
        // back to back only: batches and retries follow each other within a minute or two, a later session is new work
        if (last && last.node === s.node && last.kind === s.kind && s.start - last.end < JOIN
            && !cuts(s.node).some(t => t > last.end - 1e3 && t <= s.start + 1e3)) {
            Object.assign(last, {end: Math.max(last.end, s.end), cost: last.cost + s.cost, tokens: last.tokens + s.tokens,
                                 open: last.open || s.open, priced: last.priced !== false || s.priced !== false, parts: last.parts + 1, busy: last.busy + (s.ms ?? s.end - s.start),
                                 continued: (last.continued || 0) + (s.resumed ? 1 : 0)});
            if (s.agent && !last.agents.includes(s.agent)) last.agents.push(s.agent);
            if (s.handover) last.handed.push(cut(s));
            last.members.push(s);
        } else out.push({...s, parts: 1, busy: s.ms ?? s.end - s.start, agents: s.agent ? [s.agent] : [], handed: s.handover ? [cut(s)] : [], members: [s]});
    }
    // what is left of its processes once those that continued or were handed over are counted: retries
    // a plan's merged sessions are its stages, none a retry (critic: «10 processes: 9 retried»)
    for (const x of out) x.retried = x.kind === 'plan' ? 0 : x.parts - 1 - (x.continued || 0) - x.handed.length;
    return out;
}

export function render(el, run, nodes) {
    const ids = rows(run, nodes), name = run.name, work = stretches(run);
    const W = axisWidth(el), LEFT = gutter(W), cutN = Math.floor((LEFT - 18) / 6), H = TOP + ids.length * ROW + AXIS, f = frame(run, W, LEFT);
    const Y = id => TOP + ids.indexOf(id) * ROW + ROW / 2 + 4;
    // A STRETCH PASSED ON from session to session is drawn as its sessions, each its own piece of the bar between the cuts and
    // its own tip — its time, cost, tokens, its round, and where it stood when it passed on, against its budget and window
    // (the author, 2026-10-31: «вместо того чтобы показывать инфу на самом исполнении, она отображается между ними в
    // разделении, а на самом исполнении одна и та же длинная инфа»); the cut is only the line between two pieces
    const yb = s => Y(s.node) + (SIDE.has(s.kind) ? LANE : 0);
    // the side kinds share a lane: the longer drawn first, so none lies wholly under another and each keeps its hover (critic)
    const overLane = ([a], [b]) => SIDE.has(a.kind) - SIDE.has(b.kind) || (SIDE.has(a.kind) ? (b.end - b.start) - (a.end - a.start) : 0);
    const rect = (s, i, a, b, p) => { const w = f.X(b) - f.X(a);
        return `<rect class="tl-s tl-${s.kind}${s.open ? ' tl-open' : ''}" data-i="${i}"${p == null ? '' : ` data-p="${p}"`}`
        + ` data-k="b|${esc(s.node)}|${s.kind}|${a}" x="${f.X(a)}" y="${yb(s) - BAR[s.kind] / 2}" width="${Math.max(w, 3)}" height="${BAR[s.kind]}" rx="1.5"/>`; };
    const bar = (s, i) => !s.handed.length ? rect(s, i, s.start, s.end)
        : s.members.map((m, p) => rect(s, i, m.start, s.members[p + 1]?.start ?? s.end, p)).join('')
          + s.handed.map(({t}) => `<line class="tl-hand" x1="${f.X(t)}" x2="${f.X(t)}" y1="${yb(s) - BAR[s.kind] / 2 - 2}" y2="${yb(s) + BAR[s.kind] / 2 + 2}"/>`).join('');
    // a verdict: a hairline stem up from the bar line, the glyph on top — a mark, not a piece of the work
    const marks = id => (run.rounds[id] || []).filter(r => r.verdict).map(r => { const x = f.X(r.at), y = Y(id);
        return `<g class="tl-v" data-v="${r.n}" data-k="v|${esc(id)}|${r.n}"><line class="tl-stem" x1="${x}" x2="${x}" y1="${y - 2}" y2="${y - STEM}"/>${mark(r.verdict, x, y - STEM - 3.5, 3.5)}</g>`; }).join('');
    const state = Object.fromEntries(nodes.map(n => [n.id, n.state]));
    // the names it waits on cut to fit: the whole of them on hover
    // …its first producer and how many more, the whole list one name a row on hover — joined by commas, names that carry
    // commas ran a row out to 1000 px and could not be counted (audit B8; the graph's tip and the panel say it so too)
    const idle = id => { const deps = run.waits[id]?.deps || [];
        return run.sessions.some(s => s.node === id) || state[id] === 'DONE' ? '' : !deps.length
        ? `<text class="tl-wait" x="${LEFT + 8}" y="${Y(id) + 4}">${esc(label(state[id]).toLowerCase())}</text>`
        : `<text class="tl-wait" x="${LEFT + 8}" y="${Y(id) + 4}"${deps.length > 1 || name(deps[0]).length > 32 ? TIP.waits(deps.map(name)) : ''}>waits on ${esc(trim(name(deps[0]), 32))}${deps.length > 1 ? ` +${deps.length - 1}` : ''}</text>`; };
    // the bar kinds are a LABEL (hints.js): read each time, so drawn beside the bars; PASS and FAIL are the key's
    // consent shown only where a run has it: rows recorded before it was booked apart have none
    // …and planning only where the run planned (audit B4: 25 planning bars stood with no word for them)
    const has = k => run.sessions.some(s => s.kind === k);
    const kinds = ['exec', ...(has('consent') ? ['consent'] : []), 'val', 'issuer', ...(has('plan') ? ['plan'] : [])], legendW = kinds.length * 92;
    const legend = kinds.map((k, i) =>
        `<g><rect class="tl-${k}" x="${i * 92}" y="${4 - BAR[k] / 2}" width="16" height="${BAR[k]}" rx="1.5"/><text x="${i * 92 + 21}" y="8">${KIND[k].name}</text></g>`).join('');
    const row = id => `<g class="tl-row" data-node="${esc(id)}">
        <rect class="tl-band" x="0" y="${Y(id) - ROW / 2 - 2}" width="${W}" height="${ROW}"/>
        <text class="tl-name${run.depth[id] ? '' : ' tl-goal'}" data-k="n|${esc(id)}" x="${LEFT - 10}" y="${Y(id) + 4}"${name(id) !== trim(name(id), cutN) ? TIP.cell(name(id)) : ''}>${esc(trim(name(id), cutN))}</text>
        ${work.map((s, i) => [s, i]).filter(([s]) => s.node === id).sort(overLane).map(([s, i]) => bar(s, i)).join('')}${marks(id)}${idle(id)}</g>`;
    // how many executors ran at once: its own band with its own scale, a line — not one more row of bars
    const c0 = 30 + CONC, peak = Math.max(run.exec.peak, 1), cy = k => c0 - (k / peak) * (CONC - 6);
    let line = `M${LEFT},${c0}`;
    for (const [t, k] of run.exec.steps) line += `H${f.X(t)}V${cy(k)}`;
    const top = run.exec.steps.find(([, k]) => k === run.exec.peak);
    el.innerHTML = `<svg class="tl" width="${W}" height="${H}">
        ${f.ticks(30, H - AXIS, 22)}${f.folds(30, H - AXIS, H - 6)}
        <g class="tl-legend" transform="translate(${W - legendW},0)">${legend}</g>
        ${tallySvg(run.exec.peak, 'at once', 'tl-peak', LEFT - 10, cy(peak) + 3)}
        <text class="tl-peak tl-sub" x="${LEFT - 10}" y="${c0}">executors</text>
        <line class="tl-base" x1="${LEFT}" x2="${W - 16}" y1="${c0}" y2="${c0}"/>
        <line class="tl-base dash" x1="${LEFT}" x2="${W - 16}" y1="${cy(peak)}" y2="${cy(peak)}"/>
        <path class="tl-conc" d="${line}"/>
        ${top ? `<circle class="tl-peakdot" cx="${f.X(top[0])}" cy="${cy(peak)}" r="2.5"/>` : ''}
        ${ids.map(row).join('')}
        <line class="tl-split" x1="0" x2="${W}" y1="${TOP + ROW + 2}" y2="${TOP + ROW + 2}"/></svg>`;
    pinLeft(el.querySelector('svg.tl'), LEFT);
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
