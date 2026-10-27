// The run as one model: who worked on which node when, what each delivery was answered with, and
// how the clock reads once the idle stretches are folded. Every view of the run (timeline,
// progress, cost, events, the graph's badges) reads this and nothing else, so two views can never
// disagree on a fact. Pure: payloads in, model out — no fetch, no DOM, no imports.

import {terminal, delivered, working} from './vocab.js';

// Sent back NOW: the last round failed and the node is neither closed nor escalated (the issuer's wait says that one)
// or being cancelled — one rule for the strip's «sent back» and the graph's red rounds badge.
export const failingNow = (rounds, state) => rounds?.at(-1)?.verdict === 'FAIL' && !terminal(state) && state !== 'ESCALATED' && state !== 'CANCELLING';

// Who owes the next move: the role the engine names for the node's step (next_steps `role`, asked of engineering
// 2026-10-26 — a node whose executor stopped twice without a report is its issuer's to revise in any state); until it is
// served, the state's owner (§12.13). Not the step's signer: in solo and with no mode the issuer and the executor are one
// name, and every issuer move read as the executor's (critic).
const owes = (n, step) => ({executor: 'executor', issuer: 'issuer'})[step?.role] || OWES[n.state] || null;
const OWES = {OFFERED: 'executor', EXECUTING: 'executor', REWORKING: 'executor', CANCELLING: 'executor',
              CHALLENGED: 'issuer', BLOCKED: 'issuer', VALIDATING: 'issuer', ESCALATED: 'issuer'};

const KIND = {executor: 'exec', consent: 'consent', validate_result: 'val', validator: 'val', issuer: 'issuer'};
const kindOf = stage => KIND[stage] || 'plan';
export const KIND_NAME = {exec: 'execution', consent: 'consent', val: 'validation', issuer: 'issuer', plan: 'planning'};
// the tree's levels by what they are: the goal (the root), its parts, then parts of parts, one level down each time
export const levelName = d => +d === 0 ? 'the goal' : +d === 1 ? 'its parts' : `parts, level ${d}`;
// An idle stretch longer than this is folded to FOLD on the axis: a run's clock is its work, and a
// host asleep overnight is not part of the run (mode_cost.py measures wall time by the same cut).
export const GAP = 20 * 60e3, FOLD = 2 * 60e3;

export const at = s => Date.parse(s.includes('T') ? s : s.replace(' ', 'T'));
// The narration names its node first ("root.sort: …"); the rest is what was said.
export const said = msg => { const m = /^([\w.\-]+):\s*(.*)$/s.exec(msg); return m ? {node: m[1], text: m[2]} : {node: null, text: msg}; };
export const roundsLine = rs => !rs.length ? '' : `${rs.length} round${rs.length > 1 ? 's' : ''}`
    + (rs.some(r => r.verdict === 'FAIL') ? ` · ${rs.filter(r => r.verdict === 'FAIL').length} FAIL` : '');

const sum = (xs, f) => xs.reduce((s, x) => s + f(x), 0);
// a figure a provider may not report: null stays null ("not reported") until something reported adds to it
const add = (a, b) => b == null ? a : (a ?? 0) + b, total = (xs, f) => xs.reduce((s, x) => add(s, f(x)), null);

function depths(nodes) {
    const by = Object.fromEntries(nodes.map(n => [n.id, n])), d = {};
    const of = id => d[id] ??= by[id]?.parent_id ? of(by[id].parent_id) + 1 : 0;
    nodes.forEach(n => of(n.id));
    return d;
}

// The acts that close each kind of session — whoever signed the first of them after it is who ran it.
const SIGNS = {exec: ['DELIVER', 'BLOCK', 'CHALLENGE'], consent: ['ACCEPT', 'CHALLENGE'], val: ['PASS', 'FAIL'],
               issuer: ['ASSIGN', 'CANCEL', 'RESOLVE_BLOCK', 'ACCEPT_CHALLENGE', 'REJECT_CHALLENGE']};
// Sessions from the usage ledger: a row is written when its call ends, so it starts `duration` before.
function sessions(calls, audit) {
    return calls.filter(c => c.duration_ms > 0 && c.node_id).map(c => {
        const end = at(c.ts), start = end - c.duration_ms, kind = kindOf(c.stage);
        // the ledger names no agent: the one who signed the node's next act after the call is it
        const signer = audit.find(a => a.task_id === c.node_id && !a.rejected && a.t >= end - 1e3
            && SIGNS[kind]?.includes(a.signal));
        return {node: c.node_id, kind, stage: c.stage, start, end, cost: c.cost_usd || 0,
                tokens: [c.input_tokens, c.output_tokens, c.cache_input_tokens].reduce(add, null),
                out: c.output_tokens ?? null, model: c.model, agent: signer?.source || null, priced: (c.cost_usd || 0) > 0};
    });
}

// A session still running has no ledger row yet. Its START is in the narration — "executor …
// spawned", "independent validator …" — so a start with no end of its kind strictly after it (a
// respawn lands in the same second the last call ended), on a node still in that kind of work, is
// open until now. A parent EXECUTING while its parts work is not a session, and draws none.
// What runs now is the server's own record of its processes (`in_flight`: every session the engine spawns enters it and
// leaves it), never a start line read off the log — a call cut before it answered booked nothing and left its "spawned"
// line standing, and a node parked for its issuer drew an open execution for 40 min (a void row, 2026-10-26). The log
// gives only who was spawned, for the bar's label.
const PROC_KIND = {delegated_execution: 'exec', delegated_consent: 'consent', validate_result: 'val', validate_scope: 'val',
                   issuer_turn: 'issuer', auto_decompose: 'plan', review_decomposition: 'plan'};
function openSessions(procs, pipeline, now) {
    const who = {};
    for (const p of pipeline) { const {node, text} = said(p.message), hit = node && /^executor (\S+) spawned/.exec(text); if (hit) who[node] = hit[1]; }
    return procs.filter(w => w.task_id && PROC_KIND[w.verb]).map(w => ({node: w.task_id, kind: PROC_KIND[w.verb], start: w.since * 1e3,
        agent: PROC_KIND[w.verb] === 'exec' ? who[w.task_id] || null : null, end: now, open: true, cost: 0, tokens: 0, out: 0}));
}

// A round is one delivery and the verdict it got; the counter on the task resets on a re-ASSIGN, so
// rounds are read off the log, not off `iteration`.
function rounds(audit) {
    const r = {};
    for (const a of audit) {
        if (a.rejected) continue;
        const list = r[a.task_id] ??= [];
        if (a.signal === 'DELIVER') list.push({n: list.length + 1, delivered: a.t, verdict: null, by: a.source});
        else if ((a.signal === 'PASS' || a.signal === 'FAIL') && list.length && !list.at(-1).verdict)
            Object.assign(list.at(-1), {verdict: a.signal, at: a.t, failed: a.failed_criteria || [], validator: a.source, per: a.per_criterion});
    }
    return r;
}
// One node's rounds straight from its own slice of the log (the panel reads it without the run).
export const roundsOf = (audit, id) => rounds(audit.map(a => ({...a, t: at(a.timestamp)})).sort((a, b) => a.t - b.t))[id] || [];

// What a node waits on, ONE rule for every view: the Dep producers not yet passed (the engine hands
// no such node to anyone — frontier.py), else the parts of a parent still working, else whoever owes
// the next move (canon §12.13). A finished node waits on nothing.
// A producer is passed as the engine reads it (settled_positive): a DONE closed by FAIL or a cancellation still holds
// its consumer. An ESCALATED node waits on its issuer's decision, not on its producers (frontier._waiting_on).
// `engine`: next_steps' own `waiting` (node → producers) where the page has it — the engine reads adopted edges only
// (a BLOCK's discovered edge stays provisional until resolved) and never lists a node on the frontier; the graph's
// edges carry no such mark, so the page's own reading is the fallback before the engine is asked.
export function waitsOf(nodes, edges, engine = null, steps = null) {
    const by = Object.fromEntries(nodes.map(n => [n.id, n]));
    return Object.fromEntries(nodes.map(n => {
        if (terminal(n.state)) return [n.id, {owes: null, deps: [], parts: []}];
        const deps = n.state === 'ESCALATED' ? [] : engine ? engine.get(n.id) || []
            : edges.filter(e => e.type !== 'parent-child' && e.target === n.id && !delivered(by[e.source])).map(e => e.source);
        const parts = ['EXECUTING', 'REWORKING'].includes(n.state) ? nodes.filter(k => k.parent_id === n.id && !terminal(k.state)).map(k => k.id) : [];
        return [n.id, {owes: deps.length || parts.length ? null : owes(n, steps?.get(n.id)), deps, parts}];
    }));
}
// What is AT WORK now, one rule for the strip and the graph: a node with a session open, or a leaf in a
// working state (its executor may be a person or a process elsewhere). A parent EXECUTING waits on its parts.
// `procs`: the processes this server has in flight here — a node one runs on is at work whatever its state (a plan
// authored over an offered root, one session carrying a part of the plan on its top node).
// Under AUTO every executor is this server's, so a working state with no session of it open is not work but a stall —
// read as "at work" it stood beside the header's "stalled — nothing at work for 3.3h" (critic, a rewound night).
export function atWork(run, tasks, procs = []) {
    const parent = new Set(tasks.map(t => t.parent_id)), open = new Set((run?.sessions || []).filter(s => s.open).map(s => s.node));
    const on = new Set(procs.map(w => w.task_id)), elsewhere = !run?.auto, up = Object.fromEntries(tasks.map(t => [t.id, t.parent_id]));
    // …but a leaf one scope session carries is at work: a process or an open session on an ancestor is its session
    const carried = id => { for (let x = up[id]; x; x = up[x]) if (on.has(x) || open.has(x)) return true; return false; };
    return new Set(tasks.filter(t => on.has(t.id) || open.has(t.id)
        || (working(t.state) && !parent.has(t.id) && (elsewhere || carried(t.id)))).map(t => t.id));
}
// The same fact in words, for every view that says it: "Floor compiler", "its 2 parts", "the executor".
export const waitWords = (w, name) => !w ? '—' : w.deps.length ? w.deps.map(name).join(', ')
    : w.parts.length ? `its ${w.parts.length} part${w.parts.length > 1 ? 's' : ''}` : w.owes ? `the ${w.owes}` : '—';
// What holds the most back: following each waiting node's Dep producers up to the ones that wait on
// nothing themselves — those are the work everything behind them is queued on — and counting, per such
// producer, the nodes it holds (directly or through others).
export function blockers(waits) {
    const roots = (id, seen = new Set()) => seen.has(id) ? [] : (seen.add(id), waits[id]?.deps.length
        ? waits[id].deps.flatMap(d => roots(d, seen)) : [id]);
    const held = {};
    for (const [id, w] of Object.entries(waits))
        if (w.deps.length) new Set(w.deps.flatMap(d => roots(d))).forEach(r => (held[r] = (held[r] || 0) + 1));
    return Object.entries(held).sort((a, b) => b[1] - a[1]);
}

// The folded clock: activity intervals merged, gaps over GAP shrunk to FOLD.
function clock(spans, points, now) {
    const iv = [...spans.map(s => [s.start, s.end]), ...points.map(t => [t, t])].sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const [a, b] of iv) {
        const last = merged.at(-1);
        if (last && a - last[1] <= GAP) last[1] = Math.max(last[1], b); else merged.push([a, b]);
    }
    if (now && merged.length) merged.at(-1)[1] = Math.max(merged.at(-1)[1], now);
    const folds = merged.slice(1).map((m, i) => ({from: merged[i][1], to: m[0]}));
    const t0 = merged[0]?.[0] ?? now ?? 0;
    const x = t => t - t0 - sum(folds, f => Math.min(Math.max(t - f.from - FOLD, 0), f.to - f.from - FOLD));
    return {t0, x, span: merged.length ? x(merged.at(-1)[1]) : 0, folds: folds.map(f => ({at: x(f.from), from: f.from, to: f.to}))};
}

// How many sessions of a kind ran at once, as a step series; its peak is the parallelism figure.
export function concurrency(list) {
    const ev = list.flatMap(s => [[s.start, 1], [s.end, -1]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let cur = 0, peak = 0;
    const steps = ev.map(([t, d]) => (cur += d, peak = Math.max(peak, cur), [t, cur]));
    return {steps, peak};
}

// Totals of a set of sessions, grouped by `key` and, inside each group, by role — so the cost of
// checking always stands beside the cost of doing.
function rollup(list, key) {
    const out = {};
    for (const s of list) {
        const o = (out[key(s)] ??= {})[s.kind] ??= {calls: 0, cost: 0, unpriced: 0, tokens: null, busy: 0};
        o.calls++; o.cost += s.cost; o.unpriced += s.priced ? 0 : 1; o.tokens = add(o.tokens, s.tokens); o.busy += s.end - s.start;
    }
    return out;
}

// WHO DID THE WORK: every model call, by the model that made it and the role it served — the model is the
// node's real executor (author, 2026-10-25: «модель это реальный исполнитель ноды»). One row per (model,
// role): sessions, turns, tokens by kind, cost, and how full each session's context got against its model's
// window. A call recorded before those were kept carries cache read and write as one sum, and no fill.
// A SESSION THAT SPENT NOTHING is no model's work — an account limit, a context grown past the window, a refusal
// come back as zero tokens at zero cost under the name it was asked by (13% of the agent traces since
// 2026-10-15): counted apart by why it ended (`ended`, kept since 2026-10-25), never signed onto a node. A session
// that did work and still gave no answer — cut mid-stream, out of turns — is counted, and says how it ended.
function work(calls) {
    const rows = {}, byNode = {}, unanswered = {}, unansweredOn = {};
    // a model's window, from any of its sessions that reported one — a cut session reports none
    const window = Object.fromEntries(calls.filter(c => c.context_window).map(c => [c.model, c.context_window]));
    for (const c of calls) {
        const kind = kindOf(c.stage), model = c.model || '';
        // spent nothing = SAID zero; a call that reported none of these spent an unknown amount and is still work
        const said = [c.cost_usd, c.input_tokens, c.output_tokens, c.cache_input_tokens];
        if (said.some(v => v != null) && !said.some(v => v)) {
            const why = unanswered[kind] ??= {}, w = c.ended || '';
            why[w] = (why[w] || 0) + 1;
            if (c.node_id) (unansweredOn[c.node_id] ??= {})[kind] = (unansweredOn[c.node_id][kind] || 0) + 1;
            continue;
        }
        const r = rows[`${model}|${kind}`] ??= {model, kind, calls: 0, resumed: 0, cost: 0, unpriced: 0, ends: {}, input: null, output: null, read: 0, write: 0, unsplit: 0, turns: 0, turned: 0, fills: []};
        r.calls++; r.resumed += c.resumed ? 1 : 0; r.cost += c.cost_usd || 0; r.unpriced += c.cost_usd ? 0 : 1; if (c.ended && c.ended !== 'answered') r.ends[c.ended] = (r.ends[c.ended] || 0) + 1;
        r.input = add(r.input, c.input_tokens); r.output = add(r.output, c.output_tokens); r.turns += c.turns || 0; r.turned += c.turns ? 1 : 0;
        if (c.cache_read_tokens == null) r.unsplit += c.cache_input_tokens || 0;
        else { r.read += c.cache_read_tokens; r.write += c.cache_write_tokens || 0; }
        if (c.peak_context && (c.context_window || window[model])) {
            r.fills.push(c.peak_context / (c.context_window || window[model]));
            r.window = c.context_window || window[model];         // a share says nothing without the window it is of
        }
        if (c.node_id) (((byNode[c.node_id] ??= {})[kind] ??= {})[model] = (byNode[c.node_id][kind][model] || 0) + 1);
    }
    return {rows: Object.values(rows).sort((a, b) => b.cost - a.cost), byNode, unanswered, unansweredOn,
            total: sum(calls, c => c.cost_usd || 0)};
}

// Criteria passing at their latest verdict, one track per tree level: a part's verdict is its
// issuer's signature at that seam, the root's is the goal delivered — never summed into one curve.
// The log keeps only what a FAIL named (Inv-3), so an unnamed criterion of a past verdict is read as
// standing; a node's CURRENT verdict is read per criterion (`/verdict`), where an undecidable one is
// ⊥, not pass. A Dep edge's bare declaration (`dep__…` with no check) is no criterion of its consumer — V leaves it
// out (Spec.conjuncts); a `dep__` that pins a check on this result is one, like any other.
export const conjunct = c => !c?.depends_on || !!c.check?.length;
// What a FAIL named, read by that rule: the node's criteria it failed, and the bare Dep edges an older engine judged.
export const failedOf = (run, id, failed = []) => ({own: failed.filter(c => run.criteria.names[id]?.includes(c)),
                                                     edges: failed.filter(c => !run.criteria.names[id]?.includes(c))});
export const EDGE_NOTE = 'a Dep edge with no check, judged by an older engine — no criterion now';
export const countWords = (m, total) => m.atMost
    ? `at most ${m.k} of ${total} of its own criteria passing after it — this FAIL's record keeps only what it named`
    : `${m.k} of ${total} of its own criteria passing after it`;
export const failedWords = (run, id, failed) => { const {own, edges} = failedOf(run, id, failed);
    return [own.join(' · '), edges.length && `${edges.join(', ')}: ${EDGE_NOTE}`].filter(Boolean).join('; ') || 'no criterion named'; };
const V = {pass: 'pass', fail: 'fail'};
function criteria(audit, tasks, verdicts) {
    const names = Object.fromEntries(tasks.map(t => [t.id, (t.criteria || []).filter(conjunct).map(c => c.name || c)]));
    // one track per NODE, its own criteria at its own verdicts: a count across a level summed parts of unrelated
    // parents, one closed beside one not begun (author, 2026-10-25: «два внука от разного родителя … что отобразится»)
    const status = {}, verdictRows = audit.filter(a => !a.rejected && (a.signal === 'PASS' || a.signal === 'FAIL') && names[a.task_id]);
    const last = Object.fromEntries(verdictRows.map(a => [a.task_id, a]));
    const track = Object.fromEntries(tasks.map(t => [t.id, {total: names[t.id].length, steps: [], marks: []}]));
    for (const a of verdictRows) {
        const failed = new Set((a.failed_criteria || []).filter(c => names[a.task_id].includes(c))), T = track[a.task_id];
        // each verdict's own per-criterion record where its audit row carries one; else the node's current verdict for its last
        const rec = a.per_criterion || (last[a.task_id] === a && verdicts[a.task_id]?.verdict === a.signal && verdicts[a.task_id].per_criterion);
        const per = rec && Object.fromEntries(rec.map(c => [c.criterion, V[c.verdict] || '⊥']));
        // a PASS is every criterion passing (V, §2.3); a FAIL's record keeps only what it named (Inv-3), so the rest of a
        // past FAIL is ⊥, not pass — read as pass, a root's curve rose to 14/16 over rounds whose own record was 0/16
        status[a.task_id] = Object.fromEntries(names[a.task_id].map(c => [c, per ? per[c] || '⊥'
            : a.signal === 'PASS' ? 'pass' : failed.has(c) ? 'fail' : '⊥']));
        const known = !!per || a.signal === 'PASS' || failed.size === T.total,
              k = known ? Object.values(status[a.task_id]).filter(v => v === 'pass').length
                        : T.total - failed.size;                      // unknown: at most the criteria it did not name
        // an unrecorded FAIL still caps the curve, never above its bound — after a PASS it may not stand at the PASS's level;
        // under-reading is the safe side, as a false FAIL is (§8.4)
        if (known) T.steps.push([a.t, k]); else if (T.steps.length) T.steps.push([a.t, Math.min(T.steps.at(-1)[1], k)]);
        T.marks.push({t: a.t, node: a.task_id, signal: a.signal, failed: [...failed], k, atMost: !known});
    }
    return {track, status, names};
}

export function buildRun({nodes, edges = [], tasks = [], audit, calls, pipeline = [], verdicts = {}, waiting = null, steps = null, procs = [],
                          auto = false, now = Date.now()}) {
    audit = audit.map(a => ({...a, t: at(a.timestamp)})).sort((a, b) => a.t - b.t);
    const ss = sessions(calls, audit), open = openSessions(procs, pipeline, now);
    const all = [...ss, ...open], depth = depths(nodes), names = Object.fromEntries(nodes.map(n => [n.id, n.name || n.id]));
    return {
        name: id => names[id] || id, auto,
        sessions: all, rounds: rounds(audit), audit, depth, waits: waitsOf(nodes, edges, waiting, steps),
        clock: clock(all, audit.map(a => a.t), open.length ? now : null),
        exec: concurrency(all.filter(s => s.kind === 'exec')), val: concurrency(all.filter(s => s.kind === 'val')),
        criteria: criteria(audit, tasks, verdicts), work: work(calls),
        cost: {total: sum(ss, s => s.cost), tokens: total(ss, s => s.tokens), untold: ss.filter(s => s.tokens == null).length, busy: sum(ss, s => s.end - s.start),
               unpriced: ss.filter(s => !s.priced).length,
               byKind: rollup(ss, () => 'all').all || {}, byNode: rollup(ss, s => s.node), byDepth: rollup(ss, s => depth[s.node] ?? 0), byAgent: rollup(ss, s => s.agent || '—')},
    };
}
