// The header, by significance: the project's goal and where it stands, then ONLY what needs a person
// (each a chip that selects its first node), then the quality metrics folded into one chip whose
// popover carries the meanings the server sends beside them.
import {$, esc, coded, data, tally, daily, phone} from './dom.js';
import {H, QUALITY, GRADES, doing, hover} from './hints.js';
import {post, GOAL, PROJECT, FOCUS} from './api.js';
import {S, taskOf, asGiven, heard, signsAs, lift, reader, mineNames, mineShown, viaWord, procs, begun, stateWord, issuerIsPerson, partyKind, viewTasks, inView, intentOn} from './state.js';
import {label, closureNote, contested, MODES, terminal, delivered, modelName, cancelled, goalWord, nameOf} from './vocab.js';
import {GAP, at, busyNow, PROC_KIND} from './run.js';
import {dur, trim, cap, pct, stamp, clockAt, spoken} from './fmt.js';
import {rootOf, isRoot, depths} from './tree.js';
import {askInPage, act, notice} from './overlays.js';

const named = id => taskOf(id).name ? `${taskOf(id).name} (${id})` : id;

// A CLOSED GOAL IS A VERDICT, said as one word in the header's own voice — DONE, FAILED, CANCELLED — the one thing a
// person opening a finished project looks for; an open goal is a sentence of where it stands, which caps would not carry
// (the author, 2026-10-27: «это ключевой вердикт … разные статусы можно и отображать по-разному»).
// …in the project list's words (vocab.js `goalWord`): done, failed, cancelled
// The open root: where it stands in one phrase, in vocab's words where it has them, and — a mark of its own, never
// threaded into the phrase — how many of its parts are done, the figure large (the author, 2026-10-29: «цифры опять
// спрятаны между букв … статус стоит через тире»). A cancelled part is not owed, so it leaves N: counted, a finished
// goal read "11 of 12" forever.
function standing(root) {
    const parts = viewTasks().filter(t => !isRoot(t) && t.id !== FOCUS && !cancelled(t)), k = parts.filter(delivered).length;   // closed by FAIL is not done: the engine holds its consumers (settled_positive)
    const said = s => label(s).toLowerCase(), word = stateWord(root).toLowerCase(), it = FOCUS ? 'the part' : 'the goal';
    // …the node's word is the one rule every view says (vocab ROWS, by the log) — the header said «Accepted» beside a strip
    // and a panel saying «in progress» (critic)
    const phrase = {
        // a split goal not yet taken has its parts at work: "not started" alone read beside "1 at work" (live AUTO row)
        OFFERED: parts.length ? `${it} itself ${word}` : word, IDLE: said('OFFERED'),
        REWORKING: `${word}: ${it}'s validation failed`,
        VALIDATING: `${word}, awaiting the verdict`,
        CHALLENGED: `${said('CHALLENGED')}, waiting on the issuer`, BLOCKED: `${said('BLOCKED')}, waiting on the issuer`,
        ESCALATED: 'escalated, the issuer decides',
        CANCELLING: 'being cancelled',
    }[root.state] || word;
    // …the phrase and its count are two marks of their own, set apart as what needs a person is (the author, 2026-10-30:
    // «статус и количество это два разных поинта … там что мало место их разнести?»)
    // (`hd-plain`: at work with its parts counted the count says it; a phone's status row has no room for the word)
    return `<span class="hd-phrase${root.state === 'EXECUTING' && parts.length ? ' hd-plain' : ''}">${cap(phrase)}</span>` + (parts.length ? tally(`${k}/${parts.length}`, 'parts done') : '');
}

// the mode's settings in words (set_mode's own names: l2_gate, observe, deadline_s, bounds, max_iterations)
const SETTING = {l2_gate: 'Plan review gate', observe: 'Checks observed before execution', deadline_s: 'Default deadline', network: 'Network',
    bounds: 'Waits before a timeout', max_iterations: 'Rework rounds', intent_check: 'A go adds the check against your words'};   // the switch for a go, not what a given goal carries (critic)
const SWITCH = new Set(['l2_gate', 'observe', 'intent_check']);   // switches, whatever their value's type
// the engine keeps a setting as a string and reads a switch on only at "1" (validation.py): by truth, "0" read «on», the
// opposite of the engine, on a real run; a time «29160», the network a line of JSON (critic)
function settingWord(k, v) {
    if (SWITCH.has(k) || typeof v === 'boolean') return v === true || /^(1|true)$/i.test(String(v)) ? 'on' : 'off';
    if (/_s$/.test(k) && Number.isFinite(+v)) return dur(+v * 1e3);
    // the states' own bounds, each said as a time: {VALIDATING: 604800} → «validating 7d»
    if (k === 'bounds' && v && typeof v === 'object') return Object.entries(v).map(([s, n]) => `${s.toLowerCase()} ${dur(n * 1e3)}`).join(', ') || "the server's";
    let o = v;
    if (typeof v === 'string') try { o = JSON.parse(v); } catch (e) { return v; }
    return o && typeof o === 'object' ? [o.mode, ...(o.hosts || o.allow || [])].filter(Boolean).join(', ') || JSON.stringify(o) : String(v);
}
const PERFORM = {dispatch: 'each node in a clean session of its executor', in_chat: "by the user's agent itself"};
// where the delivered goal's work is, the engine's record: a closed goal said DONE and nothing of where to take it from
const landedAt = root => { const l = S.graph.landed; return l && delivered(root)
    ? `<span class="hd-landed"${H.landed(l)}>${esc(l.branch ? `on ${l.branch}` : `in ${l.path}`)}</span>` : ''; };
let status = '';                   // the root's standing, set by goal(), shown in the middle
async function goal() {
    status = '';
    const root = rootOf(S.tasks), mode = S.graph.mode?.mode;
    // a project named to state its goal in does not exist until that goal is created — not an error
    if (!root) return GOAL && S.missing ? '<span class="hd-phrase">A new project — it exists once its goal is created</span>'
        // …nor is a link opened before its project is: the server's sentence spoke to an agent, in red, of a normal wait
        : `<span class="hd-phrase">${S.missing ? 'This project does not exist yet — the page comes alive when it does'
            : procs().some(w => w.verb === 'auto_decompose') && S.plan?.goal ? 'The go is given: the project is being built'
            : procs().some(w => PROC_KIND[w.verb] === 'plan') ? 'The goal is being planned' : S.plan?.goal ? 'A plan written, the go not given' : 'No goal yet'}</span>`;
    // …and how THIS project's mode was set: by whom, when, the model the system's own roles run on, its settings
    // …the words check as the engine acts on it (`mode.intent_check`, set or by default): the stored key alone left a
    // default that is on unsaid
    const m = S.graph.mode, kept = m?.settings || {}, byDefault = !!m && typeof intentOn() === 'boolean' && !('intent_check' in kept),
        st = byDefault ? {...kept, intent_check: intentOn()} : kept;
    // …each a capitalised head in words, its moment as the page says moments, an on/off as on/off (audit A10)
    const set = [m?.by && ['Set by', `${m.by}${m.at ? `, ${clockAt(at(m.at))}` : ''}`],
        // …the boundary the engine holds by, its default (the plan's middle) included: the record names only one set by hand
        m?.mode === 'semi' && (m.holds_above ?? m.boundary) && ['Boundary', `depths 0…${Math.ceil(m.holds_above ?? m.boundary) - 1} held by the user's agent${m.boundary ? '' : ' (the plan\'s middle, by default)'}`], m?.perform && ['Perform', PERFORM[m.perform] || m.perform],
        m?.hands && ['Hands', m.hands], st.system_model && ['System model', `the system's roles run on ${modelName(st.system_model)}`],
        st.planner_model && ['Planner model', `the plan is authored on ${modelName(st.planner_model)}`],
        // a setting in seconds is said as a time (deadline_s 29160 → deadline 8.1h)
        ...Object.entries(st).filter(([k]) => k !== 'system_model' && k !== 'planner_model').map(([k, v]) => [SETTING[k] || cap(k.replace(/_s$/, '').replace(/_/g, ' ')),
            settingWord(k, v) + (k === 'intent_check' && byDefault ? ' (by default)' : '')])].filter(Boolean);
    // the goal's short name — up to its first parenthesis or colon — the whole of it on hover
    const full = nameOf(root), short = full.split(/\s[(:—]/)[0].slice(0, 40);
    const done = delivered(root);
    // left: WHICH goal and who holds its work; where it stands goes to the middle, beside what needs a person —
    // the brand's dot marking the one real done: the goal delivered
    const word = FOCUS ? '' : goalWord(root);       // a part's view stands where the part stands, the goal closed or not (critic)
    status = word ? `<span class="hd-verdict${word === 'failed' ? ' bad' : ''}">${word}${done ? '<i class="brand-dot"></i>' : ''}</span>${landedAt(root)}`
        : standing(FOCUS ? taskOf(FOCUS) : root);   // a view of one part stands where the part stands (critic)
    const hd = heard(), ni = hd.not_imported || [];
    return `<button class="hd-root"${data({action: 'select', id: root.id})}${H.root(full, asGiven(root))}>${esc(short)}</button>`
        // …a project with work and no mode is put under one from here too: set_mode refuses an agent there as well
        // …the mode said to every viewer, a reader included; its change offered only where the page signs (critic)
        + `<span class="hd-quality hd-left"><button class="hd-mode" data-action="pop">${esc(mode || 'no mode')}</button>${H.mode(MODES, mode, set, changes(m), signsAs().length ? intentSwitch('at the go') : '')}</span>`
        + (hd.runs_on_host ? `<span class="hd-warn"${H.host}>outside Docker</span>` : '')
        + (ni.length ? `<span class="hd-warn"${H.notImported(ni)}>not all copied</span>` : '');
}

// One chip per kind of call on a person; `ids` are the nodes it is about, the first one is selected.
// …with no node to go to it is no control, so a finger's first tap shows its tip (a refused landing's reason hid behind a long press)
const need = (n, text, ids, rows, cls = '', kind = text, counted = true, tag = ids[0] ? 'button' : 'span') => !n ? '' : `<${tag} class="need${cls}"${data({action: ids[0] && 'select', id: ids[0]})}`
    + `${H.need(kind, rows)}>${counted ? tally(n, esc(text)) : esc(text)}</${tag}>`;
const CALLS = ['ESCALATED', 'CHALLENGED', 'BLOCKED'];
// Under AUTO the system makes every issuer move below the root (set_mode), so a challenge or a block there is the
// machine issuer's to answer — in the strip as its turn or its wait, never here as a call on a person (critic).
// …and under SEMI only the top the user's agent holds (`boundary` = k holds depths 0…k−1; the root by default): below it
// a registered executor issues, and the engine refuses a person's move there (critic)
// …and on the root the engine says: a move its mode gives the system (`performed_by`) is made without a person: a red chip stood
// on a dispute the system answered 54 s later (live critic); a user's own dispute stays his
const madeWithout = t => S.frontier?.steps?.some(x => x.task_id === t.id && !x.mine);
const onAPerson = t => issuerIsPerson(t) && !(S.graph.mode?.mode === 'auto' && madeWithout(t));
const byState = s => { const ts = viewTasks().filter(t => t.state === s && onAPerson(t));
    return need(ts.length, label(s).toLowerCase(), ts.map(t => t.id), ts.map(t => named(t.id))); };
// …AND HOW THOSE DONES REST: an instrument's proof and a signature are not one kind of green (§15.7).
const closures = (list, text, cls) => need(list.length, text, list.map(c => c.id), list.map(c => `${c.id} — ${closureNote(c)}`), cls);

// THE RUN'S SWITCH: the engine's one state of the run (`next_steps.run`, never inferred here) and the button that
// moves it. Three states, so a press of Stop is not read as done while the sessions it let finish still run:
// running · stopping (who is still at work, on hover) · stopped (by whom, when, why) — author, 2026-10-25.
// the stop's `at` is an ISO stamp, a working session's `since` epoch seconds (the in-flight registry's)
const when = t => clockAt(typeof t === 'number' ? t * 1e3 : at(t));
// …and none on a closed goal with nothing at work: there is nothing to stop or start (the author, 2026-10-30: «на done
// проекте незачем висит кнопка stop») — nor the system's stop a server's start puts on every project that stood
// WHERE THE SYSTEM HOLDS NOTHING — no mode, and no open node held by a party the system works (`machine`) — it starts
// nothing: the run is the clock alone, and the switch and its question say so (the author's door). The difference is the
// engine's own (who makes a party's moves), never "no mode": a no-mode node handed to an executor is dispatched (critic)
const clockOnly = () => !S.graph.mode?.mode && !S.tasks.some(t => !terminal(t.state) && partyKind(t.assignee) === 'machine');
function runSwitch(r) {
    // …but a stop someone made while the plan was written stands when the plan ends: it hid, and the Start with it (critic)
    const held = r && r.state !== 'running' && r.by !== 'system';
    if (!r || !(begun() || held) || (terminal(rootOf(S.tasks)?.state) && !procs().length)) return ['', ''];
    const clock = clockOnly();
    // …and on a graph the system carries nothing of, no switch while it runs: a packet's deadline is never suspended (§12.2)
    // and there is no run to stop (engineering 2bfcbab: a server's start no longer stops it); a stop that still stands keeps
    // its Start, the one way out of it
    if (r.state === 'running') return clock ? ['', ''] : ['', `<button class="hd-run" data-action="run-stop"${H.stop}>stop</button>`];
    // the count its own mark (audit A5); the tip headed by who and when, each session still at work by its node and what it
    // does — not the in-flight registry's verb and id joined by dots (A8, A9)
    const text = r.state === 'stopping' ? `Stopping${tally(r.working.length, 'still at work')}` : clock ? 'Clock stopped' : 'Stopped';
    // …who moved it said with how it signed (`via`, the stop's own record): the page, a console's token, a local client
    const by = [r.by, viaWord(r.via)].filter(Boolean).join(' ');
    const tip = r.state === 'stopping' ? H.stopping(by, when(r.at), r.why, r.working.map(w => `${w.task_id ? nameOf(taskOf(w.task_id)) || w.task_id : 'the system'}: ${doing(w.verb, PROC_KIND[w.verb])}, since ${when(w.since)}`))
        : (clock ? H.clockStopped : H.stopped)(by, when(r.at), r.why);
    return [`<span class="hd-run-state${r.state === 'stopping' ? ' live' : ''}"${tip}>${text}</span>`,
        `<button class="hd-run" data-action="run-start"${clock ? H.clockStart : H.start}>${clock ? 'start clock' : 'start'}</button>`];
}
// WHO HOLDS THE WORK, changed from the page: once a project has work, `set_mode` takes the change only from the person's
// page (audit rows 3/10) — each other mode, and `in_chat` for the modes a person holds nodes in; nothing to a reader
const OTHER = [['solo'], ['solo', 'in_chat'], ['semi'], ['semi', 'in_chat'], ['auto']];
const changes = m => !signsAs().length ? [] : OTHER.filter(([x, p = 'dispatch']) => x !== m?.mode || p !== (m?.perform || 'dispatch'))
    .map(([x, p]) => `<button class="hq-mode"${data({action: 'set-mode', mode: x, ...(p ? {perform: p} : {})})}>${x}${p ? ', in chat' : ''}</button>`);
export async function setMode(d) {
    let said = '';
    const to = `${d.mode}${d.perform ? ', in chat' : ''}`;
    return await askInPage(`Change who holds this project's work to <b>${esc(to)}</b>? It governs nodes issued after it; `
        + `a node already issued keeps its holder. Signed as <b>${esc(S.me?.name || '')}</b>.`, {yes: 'Change'})
        // …a SEMI boundary set by hand goes with a change that stays SEMI: sent without it, the plan's middle replaced it (critic)
        && act(post('/api/run/set_mode', {mode: d.mode, ...(d.perform ? {perform: d.perform} : {}),
            ...(d.mode === 'semi' && S.graph.mode?.mode === 'semi' && S.graph.mode.boundary != null ? {boundary: S.graph.mode.boundary} : {})})
            // …a yes may say something to the person (`say`: live nodes kept a short deadline the new mode would not give) — told
            .then(r => r.clone().json().then(b => (said = b?.say || '', r), () => r)), {what: `To ${to}`, ok: () => said && notice(spoken(said.replace(/^Tell the person:\s*/, '')))});   // …said to the person, as every engine sentence the page shows
}
// THE WORDS CHECK, switched from the page (the author, 11-19: «галочкой в ui и по умолчанию»): whether a go adds the root
// criterion read against the person's words — shown where it acts, before the go and in the mode; nothing to a reader
// …a box to tick, as he asked; the action on the box alone, so a press on its words clicks it once, not twice
export const intentSwitch = (words, plain = words) => { const on = intentOn();
    return typeof on !== 'boolean' ? '' : !signsAs().length ? `<span>${esc(plain)}</span>`
        : `<label class="act-check"><input type="checkbox"${data({action: 'intent', on: on ? '0' : '1'})}${on ? ' checked' : ''}> ${esc(words)}</label>`; };
export const setIntent = on => act(post('/api/run/set_mode', {intent_check: on}),
    {what: on ? 'The words check on' : 'The words check off'});
// '' when the switch moved — the page then re-reads its header (main.js); signed by the page's session, `via` telling it from a console
const switchRun = (verb, body) => act(post(`/api/run/${verb}`, body), {ok: null});
export async function stopRun() {
    const why = await askInPage('Stop this run? Nothing new starts — no executor, validator or issuer session, no '
        + `timeout. Sessions running now finish and their signals land; the graph is not changed. Signed as <b>${esc(S.me?.name || '')}</b>.`,
        {yes: 'Stop', field: 'why — kept with the stop, shown to whoever looks (optional)'});
    return why === false ? false : switchRun('stop_project', {why});
}
// Start sets the system working again — under AUTO its issuer and executors act and spend — so it is asked, as Stop is
export async function startRun() {
    const auto = S.graph.mode?.mode === 'auto';
    return await askInPage('Start this run again? The system starts sessions here once more'
        + (auto ? ' — under AUTO its executors, validators and issuer act and spend on their own.' : '.')
        + ` The time it stood stopped does not count against any deadline. Signed as <b>${esc(S.me?.name || '')}</b>.`, {yes: 'Start'})
        && switchRun('start_project', {});
}

// The system's reports about ITSELF (a check contradicting its contract, a tool that cannot run): a quiet channel —
// they stop and move nothing — so a quiet chip, and none at all while there is none.
// Laid out beside the quality chip as a list one click opens — each report whole, its node one click away.
function drawReports() {
    const reports = S.reports, said = S.recordsSay || [], n = reports.length + said.length;
    const seen = `${reports.length}|${reports.at(-1)?.at || ''}|${said.join()}|${new Date().toDateString()}`;
    if ($('hd-reports').dataset.seen === seen) return;
    $('hd-reports').dataset.seen = seen;
    $('hd-reports').innerHTML = !n ? '' : `<button class="hd-q" data-action="reports">${tally(n, (phone() ? '' : 'tech ') + (n > 1 ? 'reports' : 'report'))}</button>`
        + H.reports([...said.map(line => ({head: "the system's own records", val: '', link: '', means: line})), ...[...reports].reverse().map(r => ({head: r.role === 'mcp' ? r.actor || 'a client' : r.role || 'the system',   // a role says itself; a client's report says WHO filed it, not the door (the author: «не ясно кто»)
            val: `<span class="hq-when">${esc(when(r.at))}</span>`,
            link: r.node ? `<button class="pn-link" ${data({action: 'select', id: r.node})}>${esc(nameOf(taskOf(r.node)) || r.node)} →</button>` : '', means: r.text}))]);
}
export const toggleReports = () => $('hd-reports').classList.toggle('open');

// A goal still open with nothing at work, no call on anyone, and no event for longer than the run folds as idle
// is STALLED — the one quiet that must not read "leave it" (a json-parser run sat 642h so, under "nothing needs you").
function stalled(calls) {
    const root = rootOf(S.tasks), run = S.run;
    // at work HERE means a session open or a process in flight — a leaf left EXECUTING by an executor that died is
    // exactly the stall to name, so a working STATE does not count
    // …and a run the person stopped is not stalled: it is stopped, and says so beside the goal
    // …and a graph the system carries nothing of never stalls: its quiet is people's pace, not a run that stopped without an
    // end (the author, 11-15, on «stalled since» over a people's graph once its clock ran)
    if (calls || clockOnly() || !run || !root || terminal(root.state) || busyNow(procs(), run.sessions)
        || S.runState?.state !== 'running') return '';
    const last = Math.max(...run.audit.map(a => a.t), ...run.sessions.map(s => s.end), 0);
    // a run read before the first event says nothing of a stall: it read «stalled since 1 Jan 08:00» (critic)
    if (!last) return '';
    // …the quiet turns into a stall at a moment known now, with nothing pushed then: the header is drawn again at it
    clearTimeout(wake);
    if (Date.now() - last <= GAP) { wake = setTimeout(drawHeader, last + GAP - Date.now() + 1e3); return ''; }
    // the goal's one stall is no count: «1 stalled» read as one thing stalled among others (audit A6)
    return need(1, `stalled since ${clockAt(last)}`, [root.id], H.stalled, '', 'stalled', false);
}
let wake;
if (PROJECT) daily(() => drawHeader());   // a moment said without its day (today's) gains it at midnight

export async function drawHeader() {
    // the left side is written ONCE, after every read: written first and the switch added after the frontier's
    // answer, the Stop button was missing for the length of each read — a blinking button on a live run
    const left = await goal();
    let chips = CALLS.map(byState).join('')
        // a PASS by hand is no call and no figure: it is one verdict's fact — who checked and who signed (§10.2) — said on that
        // node's panel and drawn on it, never counted apart (the author, 2026-11-14: a chip «не уместно там ее держать в любом
        // случае», a Quality row «все ещё звучит как костыль»; Q's five metrics, §15.4, hold no such count)
        + closures(S.closures.filter(c => contested(c) && inView(c.id)), 'contested', '');
    // WHAT THE ENGINE SAYS IS OWED (model.js loadFrontier): `stuck` comes with its `directive`. NAME WHO — "you" is
    // nobody on a shared graph. "Nothing needs you" is said only when the engine was asked.
    const f = S.frontier, heard = !!f;
    let others = 0;
    if (f) {
        // …and a node a state chip already shows is not counted twice.
        // (dropped only where that chip IS shown: under AUTO a person's own move below the root has none — critic)
        const shown = t => CALLS.includes(t.state) && onAPerson(t);
        // the engine's `mine`, as it is: under AUTO it marks the customer's own rulings on the root (a user's dispute)
        // …and only the names «Mine» shows: locally a person owns every stream's name, and all of them read 230 «for you» (critic)
        const yours = (f.steps || []).filter(x => x.mine && inView(x.task_id));
        const own = yours.filter(x => !x.performed_by || mineNames().includes(x.performed_by));
        // …and a view narrowed to one name is no calm word over the moves of the person's other names (critic 3)
        others = yours.length - own.length;
        const mine = own.filter(x => !shown(taskOf(x.task_id))), me = mineShown() === '*' ? 'you' : mineShown(), blocked = f.blocked_by || [];
        // …a turn on what is stuck or above it: one elsewhere answers nothing here, and a stuck with no node named stays a call
        const above = id => { const up = []; for (let t = taskOf(id); t; t = t.parent_id && taskOf(t.parent_id)) up.push(t.id); return up; };
        const answering = S.graph.mode?.mode === 'auto' && procs().some(w => PROC_KIND[w.verb] === 'issuer' && blocked.some(id => above(id).includes(w.task_id)));
        // …under AUTO a goal settled undelivered is settled: no one moves it (the engine says so), so no red beside
        // CANCELLED; elsewhere the chip carries the way out, and a DONE whose work did not land is stuck by the engine's word
        const roots = S.tasks.filter(t => !t.parent_id), settled = S.graph.mode?.mode === 'auto' && roots.length && roots.every(t => terminal(t.state) && !delivered(t));
        chips = (f.stuck && !answering && !settled && (!FOCUS || !blocked.length || blocked.some(inView)) ? need(1, `stuck${blocked.length ? ': ' + blocked.map(named).join(', ') : ''}`, blocked,
                                spoken(f.directive || '') || H.stuck, '', 'stuck') : '')
            + need(mine.length, `for ${me}`, mine.map(x => x.task_id),
                   mine.map(x => `${x.action} ${named(x.task_id)}`)) + chips;
    }
    chips += stalled(chips);
    drawReports();
    const [runState, runButton] = runSwitch(S.runState), small = phone();
    // …its switch a move like any other: not offered to a browser that signs as no one
    $('hd-goal').innerHTML = left + (small ? '' : runState) + (lift() ? '' : runButton);
    // …and a goal closed undelivered is said by its verdict alone: «FAILED nothing needs you» read as leave it (critic)
    // …and a browser not signed in is asked about no one: «nothing needs you» was a calm word over nine deliveries waiting
    // on a verdict (critic) — it is told how to sign in instead
    const root = rootOf(S.tasks), failed = root && terminal(root.state) && !delivered(root);
    // …the sign-in line stands beside any chip: it says how to act at all, not that all is calm (critic 3)
    $('hd-needs').innerHTML = (small ? runState : '') + status + chips + (lift() ? (reader() ? `<span class="hd-quiet hd-signin"${hover('Read only', lift().replace(/`/g, ''))}>read only</span>` : `<span class="hd-quiet hd-signin">${coded(lift())}</span>`)
        : !chips && heard && !failed && !others && S.runState?.state === 'running' ? '<span class="hd-quiet">nothing needs you</span>' : '') + pastTheSystem();
}

// The quality metrics. What each MEANS, how far it can be trusted (§15.8's grade) and which of them call a person are the
// server's (`means`, `grades`, `alarm`, from the module computing them) — a copy kept here drifted (2026-09-02).

// the server's `means` is a paragraph: its first sentence says what the metric counts and stands under the heading,
// the rest — how to read it, what it is not — one click away (a popover of five paragraphs read as prose, not a list);
// the server's own short name before a colon goes where it says what the heading already says
// the server's prose said to a person: no § references (the canon is not on the page), no code quotes, no shouting — a
// protocol word (PASS, FAIL, BLOCK…) keeps its capitals (audit A12)
const SIGNALS = /^(PASS|FAIL|BLOCK|REOPEN|DONE|ASSIGN|DELIVER|ACCEPT|CHALLENGE|CANCEL|TIMEOUT)$/;
const plain = t => spoken(t)
    .replace(/\b[A-Z]{2,}(?:\s+[A-Z]{2,})*\b/g, w => w.split(/\s+/).every(x => SIGNALS.test(x)) ? w : w.toLowerCase());
const readMeans = r => { const [, first, rest] = /^(.+?\.)\s+(?=[A-Z0-9⊥(])(.*)$/s.exec(r.means || '') || [, r.means];
    // …only when the heading says every word of it: «delegation correctness» gone left a ratio read the wrong way
    const words = s => s.toLowerCase().match(/[a-z]{4,}/g)?.map(w => w.slice(0, 5)) || [], head = words(r.head);
    const named = /^([a-z][^:()]{0,40}):\s+/i.exec(first || ''), said = named && words(named[1]).every(w => head.includes(w));
    // …and a first sentence that only repeats the row's tag («high is bad») is no definition: the next one is
    const tw = words(r.tag || ''), tagged = tw.length && rest && tw.every(w => words(first).includes(w));
    const [, next, after] = tagged && /^(.+?\.)\s+(?=[A-Z0-9⊥(])(.*)$/s.exec(rest) || [, rest, ''];
    const row = tagged ? {...r, means: next.replace(/^It is (?:the )?/, 'The '), more: [first, after].filter(Boolean).join(' ')}
        : {...r, means: said ? first.slice(named[0].length) : first, more: rest};
    // …a metric with no value yet: the sentence saying when it gets one is the key line, not a fold's (critic)
    const when = r.none && /(?:^|\s)(⊥[^.]*\.)/.exec(row.more || '');
    // (said as words: the row's dash already marks the empty value)
    return when ? {...row, means: `${row.means} No value ${when[1].slice(1).trim()}`, more: row.more.replace(when[1], '').trim()} : row; };

// WORK PAST THE SYSTEM, the server's reading (`metrics`: past_the_system, witnessed): commits made by hand in a repository
// the project works in while no node there was taken, and writes a console's witness saw so — never refused, counted, as an
// unrecorded decision is a defect (Thm 11). A quiet line, not a call: nothing on the page clears it and the engine names no
// move for it (JOINT in-work 11-15 §2: «N commits outside any node»); the two measures apart (one edit may be both); the
// project's whole, so not in a part's view; said only when there is some
function pastTheSystem() {
    const m = S.metrics, all = m?.past_the_system || [], repos = all.filter(r => r.count), seen = m?.witnessed?.count || 0;
    // …commits no record decides either way are not «none past»: their own part of the line, never in the count (⊥ ≠ 0)
    const u = all.reduce((s, r) => s + (r.undecided?.count || 0), 0);
    if (FOCUS || !repos.length && !seen && !u) return '';
    const n = repos.reduce((s, r) => s + r.count, 0);
    const said = [n && `${n} commit${n > 1 ? 's' : ''} outside any node`, u && `${u} commit${u > 1 ? 's' : ''} not decided by any record`,
        seen && `${seen} write${seen > 1 ? 's' : ''} seen outside any node`].filter(Boolean);
    const rows = [...repos.map(r => `${r.count} in ${r.repository}${r.read_from ? ` (its record since ${clockAt(r.read_from * 1e3)})` : ''}${r.commits?.length ? `: ${r.commits.map(c => c.slice(0, 8)).join(', ')}` : ''}`),
        // …commits no record decides either way: never «past», said apart and never in the count
        ...all.filter(r => r.undecided?.count).map(r => `${r.undecided.count} in ${r.repository} not decided by any record: ${(r.undecided.commits || []).map(c => c.slice(0, 8)).join(', ')}`),
        ...(m.witnessed?.last || []).map(w => `${clockAt(at(w.at))} ${w.actor}: ${w.text}`)];
    return `<span class="hd-quiet hd-past"${H.past(rows)}>${said.join(' · ')}</span>`;
}

export function drawQuality() {
    const m = S.metrics;
    if (m) {
        // ⊥ is an empty population (§15.4) — a dash, not a fake 100%
        const means = m.means || {}, alarm = m.alarm || {}, ffs = m.false_fail_share;
        $('hd-quality').innerHTML = `<button class="hd-q${m.calls_person ? ' acc' : ''}" data-action="pop">quality</button>`
            + H.quality([...Object.entries(m.grades || {}).flatMap(([k, grade]) => [{head: QUALITY[k] || k, tag: grade, means: plain(means[k] || ''), none: m[k] == null,
                val: m[k] == null ? '<span class="hq-val">—</span><span class="hq-nil">no observations yet</span>'
                    : `<span class="hq-val${alarm[k] ? ' acc' : ''}">${pct(m[k])}</span>`},
                // §15.4: a low q_D is read TOGETHER with the false-FAIL share (an over-strict validator inflates it).
                ...k === 'q_D' && ffs != null ? [{head: QUALITY.false_fail_share, tag: 'high is bad', val: `<span class="hq-val">${pct(ffs)}</span>`, means: plain(means.false_fail_share || '')}] : []]).map(readMeans),
                {group: 'How far a figure goes'}, ...[...new Set(Object.values(m.grades || {}))].map(g => ({head: cap(g), means: GRADES[g] || ''}))]);
    }
}
