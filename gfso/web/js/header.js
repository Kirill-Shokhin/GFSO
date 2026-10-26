// The header, by significance: the project's goal and where it stands, then ONLY what needs a person
// (each a chip that selects its first node), then the quality metrics folded into one chip whose
// popover carries the meanings the server sends beside them.
import {$, esc, data, hint} from './dom.js';
import {getJSON, post, refusal, singleFlight, GOAL} from './api.js';
import {S, taskOf, myRole, procs} from './state.js';
import {label, closureNote, contested, modeDoc, terminal, delivered, modelName} from './vocab.js';
import {GAP, at} from './run.js';
import {dur, trim} from './draw.js';
import {notice, askInPage} from './overlays.js';

const named = id => taskOf(id).name ? `${taskOf(id).name} (${id})` : id;
const isRoot = t => !t.parent_id;
const settled = t => t.state === 'ABANDONED' || t.done_reason === 'CANCELLED';

// The root in one phrase, in vocab's words where it has them. A cancelled part is not owed, so it leaves N:
// counted, a finished goal read "11 of 12" forever.
function phrase(root) {
    const parts = S.tasks.filter(t => !isRoot(t) && !settled(t)), k = parts.filter(t => t.state === 'DONE').length;
    const done = parts.length ? `${k} of ${parts.length} parts done` : 'not split yet', said = s => label(s).toLowerCase();
    return {
        DONE: {FAIL: 'goal closed — failed', CANCELLED: said('ABANDONED')}[root.done_reason] || 'goal delivered',
        OFFERED: said('OFFERED'), IDLE: said('OFFERED'),
        EXECUTING: `${said('EXECUTING')} — ${done}`,
        REWORKING: `the goal's validation failed — reworking (${done})`,
        VALIDATING: 'delivered — awaiting the verdict',
        CHALLENGED: `waiting on the issuer — ${said('CHALLENGED')}`, BLOCKED: `waiting on the issuer — ${said('BLOCKED')}`,
        ESCALATED: 'escalated — the issuer decides',
        CANCELLING: 'being cancelled',
    }[root.state] || said(root.state);
}

let status = '';                   // the root's standing, set by goal(), shown in the middle
async function goal() {
    status = '';
    const root = S.tasks.find(isRoot), mode = S.graph.mode?.mode;
    // a project named to state its goal in does not exist until that goal is created — not an error
    if (!root) return GOAL && S.missing ? '<span class="hd-phrase">a new project — it exists once its goal is created</span>'
        : `<span class="hd-phrase${S.missing ? ' acc' : ''}">${esc(S.missing
            || (procs().some(w => w.verb === 'auto_decompose') ? 'the goal is being planned' : 'no goal yet'))}</span>`;
    const doc = mode ? await modeDoc() : {};
    const who = Object.entries(doc).map(([m, text]) => `${m === mode ? '▸ ' : ''}${m}: ${text}`);
    // …and how THIS project's mode was set: by whom, when, the model the system's own roles run on, its settings
    const m = S.graph.mode, st = m?.settings || {};
    if (m?.by) who.push(`set by ${m.by}${m.at ? ' · ' + String(m.at).slice(0, 16).replace('T', ' ') : ''}${m.boundary ? ` · boundary ${m.boundary}` : ''}`
        + `${m.perform ? ` · perform ${m.perform}` : ''}${m.hands ? ` · hands ${m.hands}` : ''}`);
    if (st.system_model) who.push(`the system's roles run on ${modelName(st.system_model)}`);
    const rest = Object.entries(st).filter(([k]) => k !== 'system_model').map(([k, v]) => `${k} ${v}`);
    if (rest.length) who.push(rest.join(' · '));
    // the goal's short name — up to its first parenthesis or colon — the whole of it on hover
    const full = root.name || root.id, short = full.split(/\s[(:—]/)[0].slice(0, 40);
    const done = delivered(root);
    // left: WHICH goal and who holds its work; where it stands goes to the middle, beside what needs a person —
    // the brand's dot marking the one real done: the goal delivered
    status = `<span class="hd-phrase">${phrase(root)}${done ? '<i class="brand-dot" title="Delivered&#10;the root passed — the goal is reached"></i>' : ''}</span>`;
    return `<button class="hd-root"${data({action: 'select', id: root.id})} title="${hint(full, 'click to open the goal')}">${esc(short)}</button>`
        + (mode ? `<span class="hd-mode" title="${hint(`${mode} — who holds the work`, who)}">${esc(mode)}</span>` : '');
}

// One chip per kind of call on a person; `ids` are the nodes it is about, the first one is selected.
const need = (n, text, ids, why, cls = '') => !n ? '' : `<button class="need${cls}"${data({action: ids[0] && 'select', id: ids[0]})}`
    + ` title="${hint(`${n} ${text}`, why)}"><b>${n}</b> ${esc(text)}</button>`;
const CALLS = ['ESCALATED', 'CHALLENGED', 'BLOCKED'];
// Under AUTO the system makes every issuer move below the root (set_mode), so a challenge or a block there is the
// machine issuer's to answer — in the strip as its turn or its wait, never here as a call on a person (critic).
// …and under SEMI only the top the user's agent holds (`boundary` = k holds depths 0…k−1; the root by default): below it
// a registered executor issues, and the engine refuses a person's move there (critic)
const depthOf = t => { let d = 0; for (let n = t; n?.parent_id; n = taskOf(n.parent_id)) d++; return d; };
const onAPerson = t => { const m = S.graph.mode; return m?.mode === 'auto' ? isRoot(t)
    : m?.mode === 'semi' ? depthOf(t) < (m.boundary || 1) : true; };
const byState = s => { const ts = S.tasks.filter(t => t.state === s && onAPerson(t));
    return need(ts.length, label(s).toLowerCase(), ts.map(t => t.id), ts.map(t => named(t.id))); };
// …AND HOW THOSE DONES REST: an instrument's proof and a signature are not one kind of green (§15.7).
const closures = (list, text, cls) => need(list.length, text, list.map(c => c.id), list.map(c => `${c.id} — ${closureNote(c)}`), cls);

// THE RUN'S SWITCH: the engine's one state of the run (`next_steps.run`, never inferred here) and the button that
// moves it. Three states, so a press of Stop is not read as done while the sessions it let finish still run:
// running · stopping (who is still at work, on hover) · stopped (by whom, when, why) — author, 2026-10-25.
// the stop's `at` is an ISO stamp, a working session's `since` epoch seconds (the in-flight registry's)
const ago = t => dur(Date.now() - (typeof t === 'number' ? t * 1e3 : at(t)));
function runSwitch(r) {
    if (!r || !S.tasks.length) return '';
    if (r.state === 'running') return '<button class="hd-run" data-action="run-stop" title="Stop the run&#10;nothing new starts: no executor, validator or issuer session, no timeout&#10;'
        + 'the sessions running now finish and their signals land">stop</button>';
    const who = `stopped by ${r.by} ${ago(r.at)} ago${r.why ? ` — ${r.why}` : ''}`;
    const text = r.state === 'stopping' ? `stopping · ${r.working.length} still at work` : 'stopped';
    const title = r.state === 'stopping'
        ? [`Stopping — ${r.working.length} still at work`, who, 'each finishes and its signal lands:',
           ...r.working.map(w => `${w.verb} · ${w.task_id || '—'} · ${ago(w.since)}`)]
        : ['Stopped', who, 'nothing runs and no timeout fires until it is started again'];
    return `<span class="hd-run-state${r.state === 'stopping' ? ' live' : ''}" title="${hint(title)}">${text}</span>`
        + '<button class="hd-run" data-action="run-start" title="Start the run again&#10;a bound that passed meanwhile fires as any passed bound does">start</button>';
}
async function switchRun(verb, body) {
    try {
        const no = await refusal(await post(`/api/run/${verb}`, body));
        if (no) return notice(no, 'bad');
    } catch (e) { return notice(`${verb}: the server did not answer`, 'bad'); }
    await refreshHeader();
}
export async function stopRun() {
    const why = await askInPage('Stop this run? Nothing new starts — no executor, validator or issuer session, no '
        + 'timeout. Sessions running now finish and their signals land; the graph is not changed.',
        {yes: 'Stop', field: 'why — kept with the stop, shown to whoever looks (optional)'});
    if (why !== false) await switchRun('stop_project', {why, ...(myRole() ? {by: myRole()} : {})});
}
// Start sets the system working again — under AUTO its issuer and executors act and spend — so it is asked, as Stop is
export async function startRun() {
    const auto = S.graph.mode?.mode === 'auto';
    if (await askInPage('Start this run again? The system starts sessions here once more'
        + (auto ? ' — under AUTO its executors, validators and issuer act and spend on their own.' : '.')
        + ' The time it stood stopped does not count against any deadline.', {yes: 'Start'}))
        await switchRun('start_project', myRole() ? {by: myRole()} : {});
}

// The system's reports about ITSELF (a check contradicting its contract, a tool that cannot run): a quiet channel —
// they stop and move nothing — so a quiet chip, and none at all while there is none.
// Laid out beside the quality chip as a list one click opens — each report whole, its node one click away.
async function techReports() {
    let reports = [];
    try { reports = (await (await post('/api/run/tech_reports', {})).json()).reports || []; } catch (e) { /* a read */ }
    const seen = `${reports.length}|${reports.at(-1)?.at || ''}`;
    if ($('hd-reports').dataset.seen === seen) return;
    $('hd-reports').dataset.seen = seen;
    $('hd-reports').innerHTML = !reports.length ? '' : `<button class="hd-q" data-action="reports">${reports.length} tech report${reports.length > 1 ? 's' : ''}</button>`
        + `<div class="hd-pop"><div class="hq-means">What the system reported about ITSELF — a check contradicting its contract, a tool that `
        + `cannot run. A report stops and moves nothing; newest first.</div>${[...reports].reverse().map(r => `<div class="hq-row">`
        + `<div class="hq-head"><i><span data-at="${esc(r.at)}">${esc(ago(r.at))}</span> ago · ${esc(r.role || '')}</i>${r.node ? `<button class="pn-link" ${data({action: 'select', id: r.node})}>${esc(r.node)} →</button>` : ''}</div>`
        + `<div class="hq-means">${esc(r.text)}</div></div>`).join('')}</div>`;
}
// the list is rebuilt only when a report arrives (it kept its scroll), so its ages are re-read when it is opened
export const toggleReports = () => {
    if ($('hd-reports').classList.toggle('open')) $('hd-reports').querySelectorAll('[data-at]').forEach(e => { e.textContent = ago(e.dataset.at); });
};

// A goal still open with nothing at work, no call on anyone, and no event for longer than the run folds as idle
// is STALLED — the one quiet that must not read "leave it" (a json-parser run sat 642h so, under "nothing needs you").
function stalled(calls) {
    const root = S.tasks.find(isRoot), run = S.run;
    // at work HERE means a session open or a process in flight — a leaf left EXECUTING by an executor that died is
    // exactly the stall to name, so a working STATE does not count
    // …and a run the person stopped is not stalled: it is stopped, and says so beside the goal
    if (calls || !run || !root || terminal(root.state) || run.sessions.some(s => s.open)
        || S.runState?.state !== 'running'
        || procs().length) return '';
    const last = Math.max(...run.audit.map(a => a.t), ...run.sessions.map(s => s.end), 0), idle = Date.now() - last;
    return idle > GAP ? need(1, `stalled — nothing at work for ${dur(idle)}`, [root.id],
        'the goal is open, nothing is at work, nobody owes a move the engine names, and nothing has happened since — '
        + 'a run that stopped without an end; look at the deck (Events) for its last act') : '';
}

export const refreshHeader = singleFlight(async () => {
    // the left side is written ONCE, after every read: written first and the switch added after the frontier's
    // answer, the Stop button was missing for the length of each read — a blinking button on a live run
    const left = await goal();
    let chips = CALLS.map(byState).join('')
        + closures(S.closures.filter(contested), 'contested', '')
        + closures(S.closures.filter(c => c.by_hand && !contested(c)), 'closed by hand', ' paper');
    // WHAT THE ENGINE SAYS IS OWED, asked AS WHOEVER THIS PAGE IS: `mine` is computed for `actor`, the YOU
    // ARE box that signs; `stuck` comes with its `directive`. NAME WHO — "you" is nobody on a shared graph.
    let heard = false;                // "nothing needs you" is said only when the engine was asked
    const mySteps = new Map();       // node → the steps next_steps names as this person's, with their directives
    if (S.tasks.length) try {
        const r = await post('/api/run/next_steps', myRole() ? {actor: myRole()} : {});
        if (!r.ok) throw r.status;
        const f = await r.json();
        // …and a node a state chip already shows is not counted twice.
        // (dropped only where that chip IS shown: under AUTO a person's own move below the root has none — critic)
        const shown = t => CALLS.includes(t.state) && onAPerson(t);
        // the engine's `mine`, as it is: under AUTO it marks the customer's own rulings on the root (a user's dispute) —
        // and today also a system dispute there, which /actions does not narrow by the mode lock: engineering's to fix
        const own = (f.steps || []).filter(x => x.mine);
        const mine = own.filter(x => !shown(taskOf(x.task_id))), me = myRole() || 'you', blocked = f.blocked_by || [];
        // the nodes where the move is this page's person's, with the move: their panel keeps that move under a mode (panel.js)
        own.forEach(x => mySteps.set(x.task_id, [...(mySteps.get(x.task_id) || []), x]));
        chips = (f.stuck ? need(1, `stuck${blocked.length ? ': ' + blocked.map(named).join(', ') : ''}`, blocked,
                                f.directive || 'no actionable node and the root is not DONE') : '')
            + need(mine.length, `for ${me}`, mine.map(x => x.task_id),
                   mine.map(x => `${x.action} ${named(x.task_id)}`)) + chips;
        S.runState = f.run;
        // the engine's Dep waits (run.js) — only from an answer that lists steps: with nothing actionable (a validator
        // running, stuck, joining) `waiting` holds the other kinds alone and a Dep wait vanished (critic); and only the
        // `dependency` kind, whose `waits_on` are node ids — the others' are sentences
        S.waiting = (f.steps || []).length ? new Map((f.waiting || []).filter(w => w.kind === 'dependency')
            .map(w => [w.task_id, [...(w.waits_on || [])]])) : null;
        heard = true;
    } catch (e) { /* the frontier is a read; the chips from the graph still stand */ }
    // the panel keeps its moves on these only (panel.js): what the ENGINE says is this person's move — a state chip is
    // a call to look, and under AUTO the engine refuses a person's Cancel or Edit on an escalated root (critic)
    S.mySteps = mySteps;
    chips += stalled(chips);
    if (S.tasks.length) await techReports(); else $('hd-reports').innerHTML = '';
    $('hd-goal').innerHTML = left + runSwitch(S.runState);
    $('hd-needs').innerHTML = status + (chips || (heard ? '<span class="hd-quiet">nothing needs you</span>' : ''));
});

// The quality metrics. What each MEANS is the server's (`means`), from the module computing it — a copy
// kept here drifted (2026-09-02). How far each can be trusted is canon §15.8's grade.
const GRADE = {q_D: 'observed', q_V: 'observed', q_T: 'proxy', q_Dep: 'proxy', q_Del: 'weak'};
const pct = v => `${(v * 100).toFixed(0)}%`;

export async function refreshQuality() {
    try {
        const m = await getJSON('/api/metrics'), means = m.means || {}, ffs = m.false_fail_share;
        // ⊥ is an empty population (§15.4) — a dash, not a fake 100%. ONLY AN OBSERVED METRIC CALLS A PERSON
        // (§15.8): q_V low, or q_D low with no high false-FAIL share to say the validator, not the split, did it.
        const low = v => v != null && v < 0.5;
        const alarm = {q_V: low(m.q_V), q_D: low(m.q_D) && !(ffs >= 0.5)};
        $('hd-quality').innerHTML = `<button class="hd-q${alarm.q_V || alarm.q_D ? ' acc' : ''}" data-action="quality">quality</button>`
            + `<div class="hd-pop">${Object.entries(GRADE).map(([k, grade]) => `<div class="hq-row">`
                + `<div class="hq-head"><b>${k}</b><span class="hq-val${alarm[k] ? ' acc' : ''}">`
                + `${m[k] == null ? '—, no observations yet' : pct(m[k])}</span><i>${grade}</i></div>`
                + `<div class="hq-means">${esc(means[k] || '')}</div>`
                // §15.4: a low q_D is read TOGETHER with the false-FAIL share (an over-strict validator inflates it).
                + (k === 'q_D' && ffs != null ? `<div class="hq-means">false-FAIL share: ${pct(ffs)} — ${esc(means.false_fail_share || '')}</div>` : '')
                + `</div>`).join('')}</div>`;
    } catch (e) { /* metrics are a read; the chip keeps its last numbers */ }
}
export const toggleQuality = () => $('hd-quality').classList.toggle('open');
