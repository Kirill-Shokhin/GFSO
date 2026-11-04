// THE PAGE'S MODEL, READ: the graph and its tasks, the frontier the engine names, and the run built from the log and
// the ledger. Each read writes S (state.js) and draws nothing; the views render what S holds, and main.js orders the
// reads and the drawings.
import {S, procs, myRole, begun} from './state.js';
import {api, getJSON, post} from './api.js';
import {buildRun, busyNow} from './run.js';
import {contested, isVerdict} from './vocab.js';

// A STATE THE FEED PUSHED WHILE A READ WAS OUT outlives that read: the read may have left before the transition and come
// back after it — a node BLOCKED at 05:21:20 read EXECUTING for three minutes (a live row). The feed is the order of events.
const heard = new Map();
let reading = 0;
export const hear = (id, state) => { if (reading) heard.set(id, state); };

// The graph and its tasks. A REFUSAL HAS TO REACH THE PERSON: a mistyped `?project=` is a 404, not an empty canvas under
// their project's name (the header says it) — false then, and the graph keeps its last read.
export async function loadGraph() {
    reading++;
    try { return await readGraph(); } finally { if (!--reading) heard.clear(); }
}
async function readGraph() {
    const [gr, tr] = await Promise.all([api('/api/graph?next=0'), api('/api/tasks')]);
    if (gr.status === 404) {
        S.missing = (await gr.json().catch(() => ({}))).detail || 'no such project';
        S.tasks = [];
        return false;
    }
    const g = await gr.json(), tasks = await tr.json();
    for (const [id, state] of heard) for (const x of [...tasks, ...g.nodes]) if (x.id === id) x.state = state;
    S.tasks = tasks;
    S.graph = g;
    S.missing = '';
    // HOW THE DONES REST: an instrument's proof and a signature are not one kind of green (§15.7)
    S.closures = g.nodes.filter(n => n.closure && (n.closure.by_hand || contested(n.closure))).map(n => ({id: n.id, ...n.closure}));
    return true;
}

// The system's reports about itself and the plan's quality metrics: reads, kept in S until the next one answers.
export async function loadReports() {
    try { S.reports = S.tasks.length ? (await (await post('/api/run/tech_reports', {})).json()).reports || [] : []; }
    catch (e) { /* a read: the last answer stands */ }
}
export async function loadMetrics() { try { S.metrics = await getJSON('/api/metrics'); } catch (e) { /* the last numbers stand */ } }

// WHAT THE ENGINE SAYS IS OWED, asked AS WHOEVER THIS PAGE IS: `mine` is computed for `actor`, the box that signs. The
// answer is S.frontier, null when it was not asked or did not answer — the chips from the graph still stand then.
export async function loadFrontier() {
    const mySteps = new Map();       // node → the steps next_steps names as this person's, with their directives
    // the last answer stands while this one is out: a header drawn in the gap read the system's move as a person's (critic)
    if (!begun()) S.frontier = null;
    else try {
        const r = await post('/api/run/next_steps', myRole() ? {actor: myRole()} : {});
        if (!r.ok) throw r.status;
        const f = await r.json();
        // the nodes where the move is this page's person's, with the move: their panel keeps that move under a mode (panel.js)
        (f.steps || []).filter(x => x.mine).forEach(x => mySteps.set(x.task_id, [...(mySteps.get(x.task_id) || []), x]));
        S.runState = f.run;
        // the engine's Dep waits (run.js) — from an answer that lists steps or carries `waiting` (every answer does since
        // 9853468; before it, one with nothing actionable held the other kinds alone and a Dep wait vanished); only the
        // `dependency` kind, whose `waits_on` are node ids — the others' are sentences
        S.waiting = (f.steps || []).length || f.waiting ? new Map((f.waiting || []).filter(w => w.kind === 'dependency')
            .map(w => [w.task_id, [...(w.waits_on || [])]])) : null;
        // …and each node's step as the engine names it: whose move it is (run.js `owes`)
        S.steps = new Map((f.steps || []).filter(x => x.task_id).map(x => [x.task_id, x]));
        // …and a verdict arriving by itself is the validator's, in the engine's kind: it read «waits on the issuer» under AUTO (critic)
        for (const w of f.waiting || []) if (w.kind === 'validator' && !S.steps.has(w.task_id)) S.steps.set(w.task_id, {task_id: w.task_id, role: 'validator'});
        S.frontier = f;
    } catch (e) { S.frontier = null; }   // the frontier is a read: not heard is said as not heard
    // the panel keeps its moves on these only (panel.js): what the ENGINE says is this person's move — a state chip is
    // a call to look, and under AUTO the engine refuses a person's Cancel or Edit on an escalated root (critic)
    S.mySteps = mySteps;
}

// THE RUN: the log, the ledger and the narration, read and built into one model (run.js) — S.run, null when the read
// failed. What was read last is kept, so the run is rebuilt from it with nothing read (`rebuildRun`).
let read = null;
const verdicts = {};
export async function loadRun() {
    try {
        const [audit, usage, pl] = await Promise.all([getJSON('/api/audit'), getJSON('/api/usage?detail=true'), getJSON('/api/pipeline?limit=2000')]);
        S.pipeline = pl;
        await currentVerdicts(audit);
        read = {audit, calls: usage.calls_detail || []};
        rebuildRun();
    } catch (e) { S.run = null; read = null; }
}
export const rebuildRun = () => { if (read) S.run = buildRun({nodes: S.graph.nodes, edges: S.graph.edges, tasks: S.tasks, ...read,
    pipeline: S.pipeline, verdicts, waiting: S.waiting, steps: S.steps, procs: procs(), auto: S.graph.mode?.mode === 'auto'}); };
// something runs, so the run's ages and open bars grow with time alone
export const runIsOpen = () => !!read && busyNow(procs(), S.run?.sessions);

// Each node's CURRENT verdict per criterion — the log keeps only what a FAIL named, and an undecidable
// criterion is ⊥, not pass. Re-read only for a node whose verdicts changed since the last read.
async function currentVerdicts(audit) {
    const seen = {};
    for (const a of audit) if (isVerdict(a)) seen[a.task_id] = (seen[a.task_id] || 0) + 1;
    const ids = Object.keys(seen).filter(id => verdicts[id]?.n !== seen[id]);
    if (!ids.length) return;
    try {
        const r = await post('/api/verdicts', ids);
        if (r.ok) for (const [id, v] of Object.entries(await r.json())) verdicts[id] = {n: seen[id], ...v};
    } catch (e) { /* the log's reading stands */ }
}
