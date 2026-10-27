// THE PAGE'S MODEL, READ: the graph and its tasks, the frontier the engine names, and the run built from the log and
// the ledger. Each read writes S (state.js) and draws nothing; the views render what S holds, and main.js orders the
// reads and the drawings.
import {S, procs, myRole} from './state.js';
import {api, getJSON, post, task, taskUrl} from './api.js';
import {buildRun, busyNow} from './run.js';
import {contested, isVerdict} from './vocab.js';

// The graph and its tasks. A REFUSAL HAS TO REACH THE PERSON: a mistyped `?project=` is a 404, not an empty canvas under
// their project's name (the header says it) — false then, and the graph keeps its last read.
export async function loadGraph() {
    const [gr, tr] = await Promise.all([api('/api/graph'), api('/api/tasks')]);
    if (gr.status === 404) {
        S.missing = (await gr.json().catch(() => ({}))).detail || 'no such project';
        S.tasks = [];
        return false;
    }
    const g = await gr.json();
    S.tasks = await tr.json();
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
    S.frontier = null;
    if (S.tasks.length) try {
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
        S.frontier = f;
    } catch (e) { /* the frontier is a read */ }
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
    await Promise.all(Object.entries(seen).filter(([id, n]) => verdicts[id]?.n !== n).map(async ([id, n]) => {
        try { verdicts[id] = {n, ...(await task(id, '/verdict'))}; } catch (e) { /* the log's reading stands */ }
        // every verdict the node got, each with its own per-criterion record (a server before it answers 404: none)
        try { const h = await api(taskUrl(id, '/verdicts')); if (h.ok && verdicts[id]) verdicts[id].history = await h.json(); } catch (e) { /* none */ }
    }));
}
