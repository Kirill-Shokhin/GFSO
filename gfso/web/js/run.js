// The run as one model: who worked on which node when, what each delivery was answered with, and
// how the clock reads once the idle stretches are folded. Every view of the run (timeline,
// progress, cost, events, the graph's badges) reads this and nothing else, so two views can never
// disagree on a fact. Pure: payloads in, model out — no fetch, no DOM, no words (hints.js says
// them); it imports the protocol's vocabulary only.

import {terminal, delivered, working, consented, nameOf, criteriaOf, isVerdict, TOKENS, WRITES} from './vocab.js';
import {childrenOf, ancestorsIn, depths} from './tree.js';

// Sent back NOW: the last round failed and the node is neither closed nor escalated (the issuer's wait says that one)
// or being cancelled — one rule for the strip's «sent back» and the graph's red rounds badge.
export const failingNow = (rounds, state) => rounds?.at(-1)?.verdict === 'FAIL' && !terminal(state) && state !== 'ESCALATED' && state !== 'CANCELLING';

// Who owes the next move: the role the engine names for the node's step (next_steps `role`, asked of engineering
// 2026-10-26 — a node whose executor stopped twice without a report is its issuer's to revise in any state); until it is
// served, the state's owner (§12.13). Not the step's signer: in solo and with no mode the issuer and the executor are one
// name, and every issuer move read as the executor's (critic).
const owes = (n, step) => ({executor: 'executor', issuer: 'issuer', validator: 'validator'})[step?.role] || OWES[n.state] || null;
const OWES = {OFFERED: 'executor', EXECUTING: 'executor', REWORKING: 'executor', CANCELLING: 'executor',
              CHALLENGED: 'issuer', BLOCKED: 'issuer', VALIDATING: 'issuer', ESCALATED: 'issuer'};
// …and where the move owed is work in course, not a wait on the owner's decision: a verdict being validated (`decides`)
const OWES_IN_COURSE = new Set(['VALIDATING']);

const KIND = {executor: 'exec', consent: 'consent', validate_result: 'val', validator: 'val', issuer: 'issuer'};
const kindOf = stage => KIND[stage] || 'plan';
// An idle stretch longer than this is folded to FOLD on the axis: a run's clock is its work, and a
// host asleep overnight is not part of the run. The cut is the page's own display parameter.
export const GAP = 20 * 60e3, FOLD = 2 * 60e3;

export const at = s => Date.parse(s.includes('T') ? s : s.replace(' ', 'T'));
// The narration names its node first ("root.sort: …"); the rest is what was said.
export const said = msg => { const m = /^([\w.\-]+):\s*(.*)$/s.exec(msg); return m ? {node: m[1], text: m[2]} : {node: null, text: msg}; };

const sum = (xs, f) => xs.reduce((s, x) => s + f(x), 0);
export const median = xs => { const s = [...xs].sort((a, b) => a - b); return s[(s.length - 1) >> 1]; };
// a figure a provider may not report: null stays null ("not reported") until something reported adds to it
const add = (a, b) => b == null ? a : (a ?? 0) + b;
export const total = (xs, f) => xs.reduce((s, x) => add(s, f(x)), null);

// The acts that close each kind of session — whoever signed the first of them after it is who ran it.
const SIGNS = {exec: ['DELIVER', 'BLOCK', 'CHALLENGE'], consent: ['ACCEPT', 'CHALLENGE'], val: ['PASS', 'FAIL'],
               issuer: ['ASSIGN', 'CANCEL', 'RESOLVE_BLOCK', 'ACCEPT_CHALLENGE', 'REJECT_CHALLENGE']};
// Sessions from the usage ledger: a row is stamped when it is booked, so it starts `duration` before. FALLBACK until
// the ledger stamps each call's own end: an executor's rounds are booked together when its run ends, one ts for all —
// they ran one after another, so each ends where the next began, counted back from the booking. A booking stamps each
// row as it writes it, so one drain may cross a second, and another node's drain may interleave (critic): the next round
// is the node's next row of that stage booked within a second. The rounds' durations do not fill the run: each round
// starts a process and a handover reads the place — 14 of a run's 36 min (tnkkww064 select, 65 rounds) — so a chain
// counted back by durations alone began 14 min after its process did (the author: «пустоты»). The run began when its
// executor was spawned (the narration says when); its rounds are drawn end to end from there, the time between their
// model calls shared out among them — one process at work throughout, as the server's in-flight record has it.
function spans(calls, spawns) {
    const span = new Map(), next = {}, chain = new Map();
    for (let i = calls.length - 1; i >= 0; i--) {
        const c = calls[i], k = `${c.node_id}
${c.stage}`, n = next[k];
        const linked = n && kindOf(c.stage) === 'exec' && at(n.ts) - at(c.ts) <= 1e3;
        chain.set(c, linked ? [c, ...chain.get(n)] : [c]);
        if (linked) for (const x of chain.get(n)) chain.set(x, chain.get(c));
        next[k] = c;
    }
    // …a spawn is this run's only when it follows the node's previous run of that stage: one missing from the page, or
    // a resumed run with none, would else reach back over the earlier run (critic)
    const prev = {};
    for (const rs of [...new Set(chain.values())].sort((a, b) => at(a.at(-1).ts) - at(b.at(-1).ts))) {
        let e = at(rs.at(-1).ts);
        const work = rs.reduce((s, c) => s + c.duration_ms, 0), from = e - work, k = `${rs[0].node_id}
${rs[0].stage}`;
        const spawn = rs.length > 1 ? Math.max(-Infinity, ...(spawns[rs[0].node_id] || []).filter(t => t <= from && t >= (prev[k] ?? -Infinity))) : -Infinity;
        const gap = spawn > -Infinity ? (from - spawn) / rs.length : 0;
        for (let i = rs.length - 1; i >= 0; i--) { const d = rs[i].duration_ms + gap; span.set(rs[i], [e - d, e]); e -= d; }
        prev[k] = at(rs.at(-1).ts);
    }
    return span;
}
function sessions(calls, audit, pipeline, tasks = []) {
    // a turn that led to no signal, a declined one, is its issuer's: Del of the parent, a root's own (§10.1)
    const byId = new Map(tasks.map(t => [t.id, t])), issuerOf = id => (byId.get(byId.get(id)?.parent_id) ?? byId.get(id))?.assignee;
    calls = calls.filter(c => c.duration_ms > 0 && c.node_id);
    const spawns = {};
    for (const p of pipeline) { const {node, text} = said(p.message); if (node && /^executor \S+ spawned/.test(text)) (spawns[node] ??= []).push(at(p.ts)); }
    const spanOf = spans(calls, spawns);
    return calls.map(c => {
        const [start, end] = spanOf.get(c), kind = kindOf(c.stage);
        // the ledger names no agent: the one who signed the node's next act after the call is it
        const signer = audit.find(a => a.task_id === c.node_id && !a.rejected && a.t >= end - 1e3
            && SIGNS[kind]?.includes(a.signal));
        return {node: c.node_id, kind, stage: c.stage, start, end, ms: c.duration_ms, cost: c.cost_usd || 0,
                tokens: [c.input_tokens, c.output_tokens, c.cache_input_tokens].reduce(add, null),
                out: c.output_tokens ?? null, model: c.model, agent: signer?.source || (kind === 'issuer' && issuerOf?.(c.node_id)) || null, priced: (c.cost_usd || 0) > 0,
                handover: c.handover || 0, resumed: !!c.resumed, peak: c.peak_context ?? null, window: c.context_window ?? null, budget: c.context_budget ?? null};
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
export const PROC_KIND = {delegated_execution: 'exec', delegated_consent: 'consent', validate_result: 'val', validate_scope: 'val',
                   issuer_turn: 'issuer', auto_decompose: 'plan', plan: 'plan', refine_plan: 'plan', review_decomposition: 'plan'};
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
        if (terminal(n.state)) return [n.id, {owes: null, decides: null, deps: [], parts: []}];
        const deps = n.state === 'ESCALATED' ? [] : engine ? engine.get(n.id) || []
            : edges.filter(e => e.type !== 'parent-child' && e.target === n.id && !delivered(by[e.source])).map(e => e.source);
        const parts = consented(n.state) ? childrenOf(nodes, n.id).filter(k => !terminal(k.state)).map(k => k.id) : [];
        const o = deps.length || parts.length ? null : owes(n, steps?.get(n.id));
        return [n.id, {owes: o, decides: o === 'issuer' && !OWES_IN_COURSE.has(n.state) ? o : null, deps, parts}];
    }));
}
// WHAT RUNS NOW, one reading for the strip, the graph and the timeline: the processes this server has in flight here, the
// nodes at work, and for a node the process on it or on the nearest ancestor that carries it (one session may run a whole
// part of the plan). At work: a node with a session open, or a leaf in a working state (its executor may be a person or a
// process elsewhere). A parent EXECUTING waits on its parts. A node a process runs on is at work whatever its state (a plan
// authored over an offered root, one session carrying a part of the plan on its top node).
// Under AUTO every executor is this server's, so a working state with no session of it open is not work but a stall —
// read as "at work" it stood beside the header's "stalled — nothing at work for 3.3h" (critic, a rewound night).
// a set of roles' totals, the costliest first, each with its share of their sum
export const byRole = parts => { const all = Object.values(parts).reduce((s, p) => s + p.cost, 0) || 1;
    return Object.entries(parts).sort((a, b) => b[1].cost - a[1].cost).map(([k, p]) => [k, p, p.cost / all]); };
// Something runs here now: a process in flight or a session open — the stall's test and the clock's, one rule
export const busyNow = (procs, sessions = []) => procs.length > 0 || sessions.some(s => s.open);
export function runNow(tasks, procs = [], sessions = [], auto = false) {
    const parent = new Set(tasks.map(t => t.parent_id)), open = new Set(sessions.filter(s => s.open).map(s => s.node));
    const on = new Map(), up = ancestorsIn(tasks);
    for (const w of procs) if (!on.has(w.task_id)) on.set(w.task_id, w);
    // …but a leaf one scope session carries is at work: a process or an open session on an ancestor is its session
    // …a session of execution: an issuer's turn or a consent on the parent marked an idle leaf as worked, and could hide a dead one (critic)
    const carries = new Set([...procs.filter(w => PROC_KIND[w.verb] === 'exec').map(w => w.task_id), ...sessions.filter(s => s.open && s.kind === 'exec').map(s => s.node)]);
    const carried = id => up(id).some(x => carries.has(x));
    const work = new Set(tasks.filter(t => on.has(t.id) || open.has(t.id)
        || (working(t.state) && !parent.has(t.id) && (!auto || carried(t.id)))).map(t => t.id));
    const carrier = id => { const x = [id, ...up(id)].find(x => on.has(x)); return x ? [x, on.get(x)] : []; };
    return {procs, work, on: id => on.get(id), carrier};
}
// What holds the most back: following each waiting node's Dep producers up to the ones that wait on
// nothing themselves — those are the work everything behind them is queued on — and counting, per such
// producer, the nodes it holds (directly or through others).
export function blockers(waits) {
    const roots = (id, seen = new Set()) => seen.has(id) ? [] : (seen.add(id), waits[id]?.deps.length
        ? waits[id].deps.flatMap(d => roots(d, seen)) : [id]);
    const held = {};
    for (const [id, w] of Object.entries(waits))
        if (w.deps.length) new Set(w.deps.flatMap(d => roots(d))).forEach(r => (held[r] ||= []).push(id));
    return Object.entries(held).sort((a, b) => b[1].length - a[1].length);
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
    const span = merged.length ? x(merged.at(-1)[1]) : 0;
    // …while the run is open its span grows with time: `from` is the moment it counts from, for a figure set as it grows
    // the run's time, as said: its work, the room a fold keeps on the axis left out, so work and idle add to the wall clock (critic: 30m + 24m over 52m)
    const worked = span - folds.length * FOLD;
    return {t0, x, span, worked, workedFrom: now ? now - worked : null, from: now ? now - span : null, folds: folds.map(f => ({at: x(f.from), from: f.from, to: f.to}))};
}

// How many sessions of a kind ran at once, as a step series; its peak is the parallelism figure.
export function concurrency(list) {
    const ev = list.flatMap(s => [[s.start, 1], [s.end, -1]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let cur = 0, peak = 0;
    // one step per moment: a round ending where the next begins (a run's rounds drawn end to end) is no drop to idle
    const steps = ev.map(([t, d]) => (cur += d, peak = Math.max(peak, cur), [t, cur])).filter((x, i, xs) => xs[i + 1]?.[0] !== x[0]);
    return {steps, peak};
}

// Totals of a set of sessions, grouped by `key` and, inside each group, by role — so the cost of
// checking always stands beside the cost of doing.
function rollup(list, key) {
    const out = {};
    for (const s of list) {
        const o = (out[key(s)] ??= {})[s.kind] ??= {calls: 0, procs: 0, cost: 0, unpriced: 0, tokens: null, busy: 0};
        o.calls += s.resumed ? 0 : 1; o.procs++; o.cost += s.cost; o.unpriced += s.priced ? 0 : 1; o.tokens = add(o.tokens, s.tokens); o.busy += s.ms ?? s.end - s.start;
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
    // A ROUND THE SYSTEM CUT TO READ ITS CONTEXT AND CONTINUED is no ending: the handover cuts every executor session into
    // rounds, and a cut round continued in the same conversation (the next row on its node and stage `resumed`) carried the
    // CLI's `max_turns` until the record said `continued` (engineering, 2026-10-27) — read «out of turns», it named a cause
    // that was none. The role's real cap keeps `max_turns`.
    const continued = new Set(calls.filter((c, i) => c.ended === 'continued' || (/max_turns$/.test(c.ended || '')
        && calls.slice(i + 1).find(n => n.node_id === c.node_id && n.stage === c.stage)?.resumed)));
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
        r.calls++; r.resumed += c.resumed ? 1 : 0; r.handed = (r.handed || 0) + (c.handover ? 1 : 0); r.cost += c.cost_usd || 0; r.unpriced += c.cost_usd ? 0 : 1; if (c.ended && c.ended !== 'answered' && !continued.has(c)) r.ends[c.ended] = (r.ends[c.ended] || 0) + 1;
        r.input = add(r.input, c.input_tokens); r.output = add(r.output, c.output_tokens); r.turns += c.turns || 0; r.turned += c.turns ? 1 : 0;
        if (c.cache_read_tokens == null) r.unsplit += c.cache_input_tokens || 0;
        else { r.read += c.cache_read_tokens; r.write += c.cache_write_tokens || 0; }
        if (c.peak_context && (c.context_window || window[model])) {
            r.fills.push(c.peak_context / (c.context_window || window[model]));
            r.window = c.context_window || window[model];         // a share says nothing without the window it is of
        }
        // a resumed process continues its session: counted once, as everywhere else
        if (c.node_id && !c.resumed) (((byNode[c.node_id] ??= {})[kind] ??= {})[model] = (byNode[c.node_id][kind][model] || 0) + 1);
        // what the cost went to: a priced Claude call with its cache kept apart, weighed by the price structure
        // …its tokens by kind kept, weighed in `split` (the cache write's weight is the row's to find)
        if (/^claude-/.test(model) && c.cost_usd && c.input_tokens != null && c.cache_read_tokens != null)
            (r.weighed ??= []).push({t: Object.fromEntries(TOKENS.map(([k]) => [k, c[k] || 0])), cost: c.cost_usd, resumed: !!c.resumed});
    }
    for (const r of Object.values(rows)) r.split = split(r);
    // …a row its own sessions cannot tell (one session, no writes) takes the price its model's other rows paid, where they agree
    for (const r of Object.values(rows)) if (r.split && r.split.write == null) {
        const told = new Set(Object.values(rows).filter(x => x.model === r.model && x.split?.write != null).map(x => x.split.write));
        if (told.size === 1) r.split = split(r, [...told][0]);
    }
    return {rows: Object.values(rows).sort((a, b) => b.cost - a.cost), byNode, unanswered, unansweredOn,
            total: sum(calls, c => c.cost_usd || 0)};
}

// A session's cost is reported as one sum. Its split by kind of token is read off Anthropic's price structure (vocab.js
// TOKENS) over the sessions
// it prices: those whose implied input rate is within 2% of the row's median. Measured 2026-10-27 over every E3 row
// with the cache kept apart: 807 of 820 fresh sessions price within 2%. The ones that do not are resumed rounds booked
// before 7213607, which recorded the whole conversation's cost (the CLI's running total) — their predecessor's cost
// counted twice; the split leaves them out and says which share of the row's cost it covers, and why.
// Another provider's sessions are not split: its price structure is not known here.
// A CACHE WRITE HAS TWO PRICES — ×1.25 input for the 5-minute cache, ×2 for the 1-hour one (WRITES) — and which one a run
// paid is not recorded: each row is weighed at the one its own sessions price at. Fixed at ×2, a haiku 5.5 run of 5-minute
// writes priced 20 of 91 issuer sessions and drew the rest as «not split» (critic, 2026-11-01; ×1.25 prices 91/91, while an
// older run of 1-hour writes prices 75/77 at ×2 and 34/77 at ×1.25).
function weigh(r, write) {
    const x = Object.fromEntries(TOKENS.map(([k, , p]) => [k, k === 'cache_write_tokens' ? write : p]));
    const ws = r.weighed.map(s => ({...s, w: Object.fromEntries(TOKENS.map(([k]) => [k, s.t[k] * x[k]]))}))
        .map(s => ({...s, rate: s.cost / sum(Object.values(s.w), v => v)}));
    const rate = median(ws.map(s => s.rate));
    return {write, rate, ws, held: ws.filter(s => Math.abs(s.rate / rate - 1) <= 0.02)};
}
function split(r, given) {
    if (!r.weighed) return null;
    // …the one that prices more of the row's sessions; where both price as many, which was paid is not told (`write` null)
    const [a, b] = (given ? [given] : Object.keys(WRITES).map(Number).sort((x, y) => y - x)).map(w => weigh(r, w));
    const best = b && b.held.length > a.held.length ? b : a;
    const {rate, ws, held} = best, write = given ?? (a.held.length === b.held.length ? null : best.write);
    r.weighed = ws;
    const parts = TOKENS.map(([k]) => [k, rate * sum(held, x => x.w[k])]);
    const out = r.weighed.filter(x => !held.includes(x));
    return {parts, write, covered: sum(held, x => x.cost) / Math.max(r.cost, 1e-12), sessions: held.length,
            out: out.length, resumedOut: out.filter(x => x.resumed).length, unweighed: r.calls - r.weighed.length};
}

// Criteria passing at their latest verdict, one track per tree level: a part's verdict is its
// issuer's signature at that seam, the root's is the goal delivered — never summed into one curve.
// The log keeps only what a FAIL named (Inv-3), so an unnamed criterion of a past verdict is read as
// standing; a node's CURRENT verdict is read per criterion (`/verdict`), where an undecidable one is
// ⊥, not pass. A Dep edge's bare declaration is no criterion (vocab.js `conjunct`).
// What a FAIL named, read by that rule: the node's criteria it failed, and the bare Dep edges an older engine judged.
export const failedOf = (run, id, failed = []) => ({own: failed.filter(c => run.criteria.names[id]?.includes(c)),
                                                     edges: failed.filter(c => !run.criteria.names[id]?.includes(c))});
const V = {pass: 'pass', fail: 'fail'};
// A CRITERION'S VALUE AT ONE VERDICT, one rule for Progress, the coverage and the panel's rounds: [value, why ⊥]. The
// verdict's own per-criterion record where it has one; else a PASS is every criterion passing (V, §2.3), and a FAIL's
// record keeps only what it named (Inv-3), so the rest of a past FAIL is ⊥, not pass — read as pass, a root's curve rose
// to 14/16 over rounds whose own record was 0/16. A delivery not answered yet has no value.
export const critAt = (r, c) => !r.verdict ? ['⊥', 'unanswered']
    : r.per ? (v => V[v] ? [v] : ['⊥', v ? 'undecided' : 'unrecorded'])(r.per.find(x => x.criterion === c)?.verdict)
    : r.verdict === 'PASS' ? ['pass'] : r.failed.includes(c) ? ['fail'] : ['⊥', 'unkept'];
// A verdict's per-criterion record: its own (the node's verdict history joined to its signal); else, for the node's last
// verdict, its current record when that is the same verdict — rounds recorded before the history was kept have neither
export const recordOf = (own, last, current, signal) =>
    own?.length ? own : last && current?.verdict === signal && current.per_criterion?.length ? current.per_criterion : undefined;
function criteria(audit, tasks, verdicts) {
    const names = Object.fromEntries(tasks.map(t => [t.id, criteriaOf(t)]));
    // one track per NODE, its own criteria at its own verdicts: a count across a level summed parts of unrelated
    // parents, one closed beside one not begun (author, 2026-10-25: «два внука от разного родителя … что отобразится»)
    const status = {}, verdictRows = audit.filter(a => isVerdict(a) && names[a.task_id]);
    const last = Object.fromEntries(verdictRows.map(a => [a.task_id, a])), joined = joinHistory(verdictRows, verdicts);
    const track = Object.fromEntries(tasks.map(t => [t.id, {total: names[t.id].length, steps: [], marks: []}]));
    for (const a of verdictRows) {
        const failed = new Set((a.failed_criteria || []).filter(c => names[a.task_id].includes(c))), T = track[a.task_id];
        // a round without a record of its own reads as a bound
        const r = {verdict: a.signal, failed: [...failed],
                   per: recordOf(a.per_criterion || joined.get(a), last[a.task_id] === a, verdicts[a.task_id], a.signal)};
        status[a.task_id] = Object.fromEntries(names[a.task_id].map(c => [c, critAt(r, c)[0]]));
        const known = !!r.per || a.signal === 'PASS' || failed.size === T.total,
              k = known ? Object.values(status[a.task_id]).filter(v => v === 'pass').length
                        : T.total - failed.size;                      // unknown: at most the criteria it did not name
        // an unrecorded FAIL still caps the curve, never above its bound — after a PASS it may not stand at the PASS's level;
        // under-reading is the safe side, as a false FAIL is (§8.4)
        if (known) T.steps.push([a.t, k]); else if (T.steps.length) T.steps.push([a.t, Math.min(T.steps.at(-1)[1], k)]);
        T.marks.push({t: a.t, node: a.task_id, signal: a.signal, failed: [...failed], k, atMost: !known});
    }
    return {track, status, names};
}

// A verdict of the node's history (`/api/tasks/{id}/verdicts`) answers the first PASS/FAIL row of that node at or after
// its `log_at` — the length of the project's log when the validator read the node (engineering, 2026-10-27); a verdict
// that never became a signal (a refused report) has no row, and none is forced on it.
function joinHistory(rows, verdicts) {
    const out = new Map(), used = new Set();
    for (const [id, v] of Object.entries(verdicts)) for (const h of v?.history || []) {
        const a = rows.find(a => a.task_id === id && a.pos >= h.log_at && !used.has(a));
        if (a && a.signal === h.verdict) { used.add(a); if (h.per_criterion?.length) out.set(a, h.per_criterion); }
    }
    return out;
}

export function buildRun({nodes, edges = [], tasks = [], audit, calls, pipeline = [], verdicts = {}, waiting = null, steps = null, procs = [],
                          auto = false, now = Date.now()}) {
    // `pos`: a row's place in the project's whole log, which a verdict's `log_at` counts in
    audit = audit.map((a, pos) => ({...a, pos, t: at(a.timestamp)})).sort((a, b) => a.t - b.t || a.pos - b.pos);
    // …each verdict row carries its own per-criterion record from the node's history, so every round read off the log
    // has it — the panel's criterion histories too, not only Progress (critic: the panel drew ⊥ for a criterion kept as pass)
    const per = joinHistory(audit.filter(isVerdict), verdicts);
    audit = audit.map(a => per.has(a) && !a.per_criterion ? {...a, per_criterion: per.get(a)} : a);
    // AN ATTEMPT AN ACCOUNT'S LIMIT REFUSED AND THE NEXT CREDENTIAL CARRIED (`ended: moved`, engineering 2026-10-29) is no
    // session and no ending: the call ran on, so it draws no bar and counts in no sessions — only Models says how many
    const moved = calls.filter(c => c.ended === 'moved');
    calls = calls.filter(c => c.ended !== 'moved');
    const ss = sessions(calls, audit, pipeline, tasks), open = openSessions(procs, pipeline, now);
    const all = [...ss, ...open], depth = depths(nodes), names = Object.fromEntries(nodes.map(n => [n.id, nameOf(n)]));
    return {
        name: id => names[id] || id, auto, now: runNow(tasks, procs, all, auto),
        sessions: all, rounds: rounds(audit), audit, depth, waits: waitsOf(nodes, edges, waiting, steps),
        clock: clock(all, audit.map(a => a.t), open.length ? now : null),
        exec: concurrency(all.filter(s => s.kind === 'exec')), val: concurrency(all.filter(s => s.kind === 'val')),
        criteria: criteria(audit, tasks, verdicts), work: {...work(calls), moved: moved.length},
        cost: {total: sum(ss, s => s.cost), tokens: total(ss, s => s.tokens), untold: ss.filter(s => s.tokens == null).length, busy: sum(ss, s => s.ms ?? s.end - s.start),
               unpriced: ss.filter(s => !s.priced).length,
               byKind: rollup(ss, () => 'all').all || {}, byNode: rollup(ss, s => s.node), byDepth: rollup(ss, s => depth[s.node] ?? 0), byAgent: rollup(ss, s => s.agent || '—')},
    };
}
