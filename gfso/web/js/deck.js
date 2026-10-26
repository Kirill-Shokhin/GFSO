// The run deck under the graph: a strip that always says what is running now and what it has cost,
// and four views of the run read from one model — its course in time, its progress by criteria, its
// cost, its events. It replaces the observation console: the same feed, read as the run it describes.
import {$, esc, hint} from './dom.js';
import {getJSON, singleFlight} from './api.js';
import {S, procs} from './state.js';
import {point, release} from './store.js';
import {buildRun, said, blockers, atWork, failingNow} from './run.js';
import {dur, trim} from './draw.js';
import * as timeline from './timeline.js';
import * as progress from './progress.js';
import * as cost from './cost.js';
import * as work from './work.js';
import * as events from './events.js';

// Each tab is named by the question it answers, so two views that both show money are not read as one:
// `spend` is where the money and time went (by node, level, role), `models` is who did the work.
const VIEWS = {timeline, progress, spend: cost, models: work, events}, KEY = 'gfso.deck';
const ASKS = {timeline: 'which nodes ran when, and at once', progress: "how the goal's criteria came to pass",
    spend: 'where the money and session time went — by node, level and role',
    models: 'who did the work — each model in each role: sessions, tokens, context filled, its share of the spend',
    events: "the log, grouped by node and kind"};
const isTick = m => / tokens · \d+s$/.test(m);         // live token ticks: shown in place, never persisted
const pref = (() => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } })();
const keep = () => { try { localStorage.setItem(KEY, JSON.stringify(pref)); } catch (e) { /* per-viewer nicety */ } };
let run = null, pipeline = [], verdicts = {}, view = VIEWS[pref.view] ? pref.view : 'timeline';
const ticks = new Map();                               // `source|node` → {node, source, msg, t}

// The strip: the nodes in consented work or awaiting a verdict now — by their state, since an executor
// may be a person or a process on another server — each pulsing when THIS server's registry has a process
// on it (an executor running tools sends no ticks), its freshest tick beside it; then what waits on the issuer.
// …and any node THIS server has a process on is at work, whatever its state says: a plan being authored over an
// offered root read "nothing at work" while the system worked (a live run, 2026-10-25). The process names the work.
const DOING = {auto_decompose: 'planning', review_decomposition: 'reviewing the plan', delegated_execution: 'executing',
    delegated_consent: 'reading the contract', validate_result: 'validating', validate_scope: 'validating',
    join_whole: 'joining the parts', issuer_turn: "the issuer's turn"};
// the session on this node, or on the nearest ancestor that carries it (one session may run a whole part of the plan)
const carrier = (t, mine) => { for (let n = t; n?.id; n = S.tasks.find(x => x.id === n.parent_id)) {
    const w = mine.find(w => w.task_id === n.id); if (w) return [n, w]; } return []; };
function strip() {
    const mine = procs(), now = Date.now() / 1000;
    const work = atWork(run, S.tasks, mine), name = t => trim(t.name || t.id, 26), runs = t => mine.some(w => w.task_id === t.id);
    // what a process runs on first: a session hidden under "+2" behind the leaves it carries told nothing (critic)
    const busy = S.tasks.filter(t => work.has(t.id)).sort((a, b) => runs(b) - runs(a));
    // waiting on the issuer's decision — a verdict being validated is work, not a wait, so VALIDATING is left out
    const issuer = S.tasks.filter(t => run?.waits[t.id]?.owes === 'issuer' && t.state !== 'VALIDATING' && !runs(t));
    const live = busy.map(t => {
        const w = mine.find(w => w.task_id === t.id), tk = [...ticks.values()].find(k => k.node === t.id), [top, by] = w ? [] : carrier(t, mine);
        const what = w ? DOING[w.verb] || w.verb.replace(/_/g, ' ')
            : t.state === 'VALIDATING' ? 'validating' : t.state === 'REWORKING' ? 'reworking' : 'executing';
        return `<button class="dk-live${w ? ' on' : ''}" data-node="${esc(t.id)}" title="${hint(t.name || t.id, tk?.msg || (w ? `${w.verb} — a session running on this server` : by ? `carried by the session on ${top.name || top.id} (${by.verb})` : 'in a working state; no process of this server runs it'))}"><i style="animation-delay:-${Date.now() % 1600}ms"></i>${esc(name(t))}`
            + `<span>${what}${w ? ' · ' + dur((now - w.since) * 1e3) : ''}</span></button>`;
    });
    // a process on no node drawn yet — the goal's own plan being authored before its root exists — is work too
    const drawn = new Set(S.tasks.map(t => t.id));
    for (const w of mine.filter(w => !w.task_id || !drawn.has(w.task_id)))
        live.push(`<span class="dk-live on" title="${hint('The goal', `${w.verb} — a session running on this server`)}"><i style="animation-delay:-${Date.now() % 1600}ms"></i>the goal`
            + `<span>${DOING[w.verb] || w.verb.replace(/_/g, ' ')} · ${dur((now - w.since) * 1e3)}</span></span>`);
    // at most three chips, the rest counted: what waits and what it cost must stay on the line however much runs
    const more = live.length > 3 ? `<span class="dk-more" title="${hint(`${live.length - 3} more at work`, busy.slice(3).map(name))}">+${live.length - 3}</span>` : '';
    // A STOPPED RUN RUNS NOTHING: its nodes still hold their working states, and the strip read "2 at work" over a run
    // with no process left (a live run, 2026-10-25) — said as held, not as work
    // …under AUTO only, where the system holds every node: a stop pauses the system, never a person's own work (critic)
    const held = S.runState?.state === 'stopped' && !mine.length && S.graph.mode?.mode === 'auto';
    const now_ = held && live.length
        ? `<span class="dk-now dk-idle" title="Stopped&#10;nothing runs here until the run is started again&#10;these nodes keep the state their work was in">stopped · ${live.length} held mid-work</span>`
          + `<span class="dk-chips">${busy.slice(0, 3).map(t => `<button class="dk-live" data-node="${esc(t.id)}"><i style="animation-delay:-${Date.now() % 1600}ms"></i>${esc(name(t))}<span>${t.state.toLowerCase()}</span></button>`).join('')}${more}</span>`
        : live.length ? `<span class="dk-now" title="At work&#10;a node a process of this server runs on, with a session open, or a leaf in a working state&#10;a parent in EXECUTING with no process of its own waits on its parts and is not counted&#10;sessions: the processes this server runs on them — one session may carry a whole part of the plan">${live.length} at work${mine.length ? ` · ${mine.length} session${mine.length > 1 ? 's' : ''}` : ''}</span><span class="dk-chips">${live.slice(0, 3).join('')}${more}</span>`
        : '<span class="dk-now dk-idle">nothing at work</span>';
    // …and what waits on what is said whether the run runs or is held
    // sent back NOW: the last round failed and the node is neither closed nor escalated (the issuer's wait says that one) —
    // the red rounds badge's rule; a count of every FAIL ever never went away on a green run (critic)
    const state = id => S.tasks.find(t => t.id === id)?.state;
    const back = run ? Object.entries(run.rounds).filter(([id, rs]) => failingNow(rs, state(id)))
        .map(([id, rs]) => [id, rs.filter(r => r.verdict === 'FAIL').length]).sort((x, y) => y[1] - x[1]) : [];
    return now_
        // what holds the most back: the producer most nodes wait on, the count beside it
        + (run ? blockers(run.waits).slice(0, 2).map(([id, n]) => { const part = run.waits[id]?.parts.find(p => work.has(p));
            return `<button class="dk-block" data-node="${esc(id)}" title="${hint(`${n} wait on ${run.name(id)}`, 'queued behind it along Dep', 'none starts until what it waits on passes')}">${n} wait on <b>${esc(trim(run.name(id), 24))}</b>`
                + (part ? `<span> ← its part ${esc(trim(run.name(part), 20))} at work</span>` : '') + '</button>'; }).join('') : '')
        + (issuer.length ? `<span class="dk-wait" title="${hint('Waiting on the issuer', issuer.map(t => `${name(t)} — ${t.state}`))}">${issuer.length} wait${issuer.length > 1 ? '' : 's'} on the issuer</span>` : '')
        // what is sent back now: its marks sit in the timeline below the fold (a newcomer reading the page mid-run could not
        // tell anything had failed, 2026-10-26); the hover counts each one's FAILs so far
        + (back.length ? `<button class="dk-block" data-node="${esc(back[0][0])}" title="${hint('Sent back', back.map(([id, n]) => `${run.name(id)} — ${n} FAIL${n > 1 ? 's' : ''}`))}">${back.length} sent back${back.length === 1 ? `: ${esc(trim(run.name(back[0][0]), 20))}` : ''}</button>` : '')
        // a session's cost is booked when it ENDS (the CLI reports it then): a running one is said, not guessed
        + (run ? `<span class="dk-sum" title="Spend&#10;booked when each session ends — the model reports its cost then${mine.length ? `&#10;${mine.length} running now, not booked yet` : ''}">`
                 + `$${run.cost.total.toFixed(2)}${mine.length ? ` + ${mine.length} running` : ''} · ${dur(run.clock.span)} run</span>` : '');
}

function paint() {
    const d = $('deck');
    d.classList.toggle('closed', !!pref.closed);
    d.querySelector('.dk-strip').innerHTML = strip();
    d.querySelectorAll('.dk-tab').forEach(b => b.classList.toggle('on', b.dataset.view === view));
    const el = d.querySelector('.dk-view'), drawn = pref.closed || !run ? null : view;
    release(el);
    if (el._drawn !== drawn) el._brought = null, el._drawn = drawn;   // a view opened brings the selection again
    if (!pref.closed && run) VIEWS[view].render(el, run, S.graph.nodes, S.tasks, pipeline);
}

export const refreshDeck = singleFlight(async () => {
    try {
        const [audit, usage, pl] = await Promise.all([getJSON('/api/audit'), getJSON('/api/usage?detail=true'), getJSON('/api/pipeline?limit=2000')]);
        pipeline = pl;
        await currentVerdicts(audit);
        read = {audit, calls: usage.calls_detail || []};
        rebuild();
    } catch (e) { run = S.run = null; read = null; }
    paint();
});
let read = null;                                 // what the deck last read: the display clock rebuilds from it, reading nothing
const rebuild = () => { run = S.run = buildRun({nodes: S.graph.nodes, edges: S.graph.edges, tasks: S.tasks, ...read, pipeline, verdicts}); };
// A DISPLAY CLOCK, not a poll: while something runs, the ages it shows ("validating · 2m") and the open bars grow
// with time and with nothing pushed — a session busy with tools streams no tokens. Minutes are the coarsest unit
// shown, so 30 s keeps every figure within half its own step; no server read.
const retime = () => { if (read && (procs().length || run?.sessions?.some(s => s.open))) { rebuild(); paint(); } };

// Each node's CURRENT verdict per criterion — the log keeps only what a FAIL named, and an undecidable
// criterion is ⊥, not pass. Re-read only for a node whose verdicts changed since the last read.
async function currentVerdicts(audit) {
    const seen = {};
    for (const a of audit) if (!a.rejected && (a.signal === 'PASS' || a.signal === 'FAIL')) seen[a.task_id] = (seen[a.task_id] || 0) + 1;
    await Promise.all(Object.entries(seen).filter(([id, n]) => verdicts[id]?.n !== n).map(async ([id, n]) => {
        try { verdicts[id] = {n, ...(await getJSON(`/api/tasks/${encodeURIComponent(id)}/verdict`))}; } catch (e) { /* the log's reading stands */ }
    }));
}

// The deck's first height, when the person has not dragged one: what the graph leaves over at a
// zoom its labels can be read at, within bounds — a wide plan keeps its graph, a small one gives room.
export function suggestHeight(graphNeeds) {
    if (pref.h) return;
    const d = $('deck'), stage = d.parentElement.clientHeight;
    d.style.height = `${Math.round(Math.max(stage * 0.25, Math.min(stage * 0.42, stage - graphNeeds)))}px`;
}

let soon = null;
const later = () => (clearTimeout(soon), soon = setTimeout(refreshDeck, 1500));

export function onPipeline(d) {
    const node = said(d.msg).node;
    if (isTick(d.msg)) ticks.set(`${d.source}|${node}`, {node, source: d.source, msg: d.msg, t: Date.now()});
    else later();
    $('deck').querySelector('.dk-strip').innerHTML = strip();
}
export const onInflight = () => { $('deck').querySelector('.dk-strip').innerHTML = strip(); };

export function mountDeck() {
    const d = $('deck');
    d.innerHTML = `<div class="dk-grip" title="Drag to resize"></div><div class="dk-head">
        <nav>${Object.keys(VIEWS).map(k => `<button class="dk-tab" data-view="${k}" title="${hint(k, ASKS[k])}">${k}</button>`).join('')}</nav>
        <div class="dk-strip"></div><button class="dk-fold" title="Fold / unfold">▾</button></div><div class="dk-body"><div class="dk-view"></div></div>`;
    if (pref.h) d.style.height = `${pref.h}px`;
    d.querySelector('nav').onclick = e => {
        const v = e.target.dataset.view;
        if (!v) return;
        // the open tab pressed again folds the deck; any tab unfolds it (author, 2026-10-25)
        pref.closed = v === view && !pref.closed;
        view = pref.view = v; keep(); paint();
    };
    d.querySelector('.dk-fold').onclick = () => { pref.closed = !pref.closed; keep(); paint(); };
    d.querySelector('.dk-strip').onclick = e => { const n = e.target.closest('[data-node]')?.dataset.node; if (n) point('select', n); };
    d.querySelector('.dk-grip').onmousedown = e => {
        const y0 = e.clientY, h0 = d.offsetHeight;
        const move = m => { d.style.height = `${Math.max(120, Math.min(innerHeight * 0.8, h0 + y0 - m.clientY))}px`; };
        const up = () => { removeEventListener('mousemove', move); removeEventListener('mouseup', up); pref.h = d.offsetHeight; keep(); paint(); };
        addEventListener('mousemove', move); addEventListener('mouseup', up);
    };
    let w = 0;
    new ResizeObserver(([e]) => { if (Math.abs(e.contentRect.width - w) > 4) { w = e.contentRect.width; if (run) paint(); } }).observe(d);
    setInterval(() => { for (const [k, v] of ticks) if (v.t < Date.now() - 12e3) ticks.delete(k); }, 5e3);
    // no data clock: a call booked in the ledger arrives as the engine's `usage` line, which re-reads the deck
    setInterval(retime, 30e3);
}
