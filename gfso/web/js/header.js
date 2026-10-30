// The header, by significance: the project's goal and where it stands, then ONLY what needs a person
// (each a chip that selects its first node), then the quality metrics folded into one chip whose
// popover carries the meanings the server sends beside them.
import {$, esc, data, tally} from './dom.js';
import {H, QUALITY} from './hints.js';
import {post, GOAL} from './api.js';
import {S, taskOf, myRole, procs, begun} from './state.js';
import {label, closureNote, contested, modeDoc, terminal, delivered, modelName, cancelled, goalWord, nameOf} from './vocab.js';
import {GAP, at, busyNow} from './run.js';
import {dur, trim, cap, pct, stamp, plural} from './fmt.js';
import {rootOf, isRoot, depths} from './tree.js';
import {askInPage, act} from './overlays.js';

const named = id => taskOf(id).name ? `${taskOf(id).name} (${id})` : id;

// A CLOSED GOAL IS A VERDICT, said as one word in the header's own voice — DONE, FAILED, CANCELLED — the one thing a
// person opening a finished project looks for; an open goal is a sentence of where it stands, which caps would not carry
// (the author, 2026-10-27: «это ключевой вердикт … разные статусы можно и отображать по-разному»).
// …in the project list's words (vocab.js `goalWord`): done, failed, abandoned
// The open root: where it stands in one phrase, in vocab's words where it has them, and — a mark of its own, never
// threaded into the phrase — how many of its parts are done, the figure large (the author, 2026-10-29: «цифры опять
// спрятаны между букв … статус стоит через тире»). A cancelled part is not owed, so it leaves N: counted, a finished
// goal read "11 of 12" forever.
function standing(root) {
    const parts = S.tasks.filter(t => !isRoot(t) && !cancelled(t)), k = parts.filter(t => t.state === 'DONE').length;
    const said = s => label(s).toLowerCase();
    const phrase = {
        // a split goal not yet taken has its parts at work: "not started" alone read beside "1 at work" (live AUTO row)
        OFFERED: parts.length ? `the goal itself ${said('OFFERED')}` : said('OFFERED'), IDLE: said('OFFERED'),
        REWORKING: "reworking: the goal's validation failed",
        VALIDATING: 'delivered, awaiting the verdict',
        CHALLENGED: `${said('CHALLENGED')}, waiting on the issuer`, BLOCKED: `${said('BLOCKED')}, waiting on the issuer`,
        ESCALATED: 'escalated, the issuer decides',
        CANCELLING: 'being cancelled',
    }[root.state] || said(root.state);
    return `<span class="hd-phrase">${cap(phrase)}</span>`
        + (parts.length ? tally(`${k}/${parts.length}`, 'parts done') : '');
}

let status = '';                   // the root's standing, set by goal(), shown in the middle
async function goal() {
    status = '';
    const root = rootOf(S.tasks), mode = S.graph.mode?.mode;
    // a project named to state its goal in does not exist until that goal is created — not an error
    if (!root) return GOAL && S.missing ? '<span class="hd-phrase">A new project — it exists once its goal is created</span>'
        : `<span class="hd-phrase${S.missing ? ' acc' : ''}">${esc(S.missing
            || (procs().some(w => w.verb === 'auto_decompose') ? 'The goal is being planned' : 'No goal yet'))}</span>`;
    const doc = mode ? await modeDoc() : {};
    // …and how THIS project's mode was set: by whom, when, the model the system's own roles run on, its settings
    const m = S.graph.mode, st = m?.settings || {};
    const set = [m?.by && ['set by', `${m.by}${m.at ? ' · ' + stamp(m.at) : ''}`],
        m?.boundary && ['boundary', `depths 0…${m.boundary - 1} held by the user's agent`], m?.perform && ['perform', m.perform],
        m?.hands && ['hands', m.hands], st.system_model && ['system model', `the system's roles run on ${modelName(st.system_model)}`],
        // a setting in seconds is said as a time (deadline_s 29160 → deadline 8.1h)
        ...Object.entries(st).filter(([k]) => k !== 'system_model').map(([k, v]) => /_s$/.test(k) && typeof v === 'number'
            ? [k.slice(0, -2).replace(/_/g, ' '), dur(v * 1e3)] : [k.replace(/_/g, ' '), String(v)])].filter(Boolean);
    // the goal's short name — up to its first parenthesis or colon — the whole of it on hover
    const full = nameOf(root), short = full.split(/\s[(:—]/)[0].slice(0, 40);
    const done = delivered(root);
    // left: WHICH goal and who holds its work; where it stands goes to the middle, beside what needs a person —
    // the brand's dot marking the one real done: the goal delivered
    const word = goalWord(root);
    status = word ? `<span class="hd-verdict${word === 'failed' ? ' bad' : ''}">${word}${done ? '<i class="brand-dot"></i>' : ''}</span>`
        : standing(root);
    return `<button class="hd-root"${data({action: 'select', id: root.id})}${H.root(full)}>${esc(short)}</button>`
        + (mode ? `<span class="hd-quality hd-left"><button class="hd-mode" data-action="pop">${esc(mode)}</button>${H.mode(doc, mode, set)}</span>` : '');
}

// One chip per kind of call on a person; `ids` are the nodes it is about, the first one is selected.
const need = (n, text, ids, rows, cls = '', kind = text) => !n ? '' : `<button class="need${cls}"${data({action: ids[0] && 'select', id: ids[0]})}`
    + `${H.need(kind, rows)}><b>${n}</b> ${esc(text)}</button>`;
const CALLS = ['ESCALATED', 'CHALLENGED', 'BLOCKED'];
// Under AUTO the system makes every issuer move below the root (set_mode), so a challenge or a block there is the
// machine issuer's to answer — in the strip as its turn or its wait, never here as a call on a person (critic).
// …and under SEMI only the top the user's agent holds (`boundary` = k holds depths 0…k−1; the root by default): below it
// a registered executor issues, and the engine refuses a person's move there (critic)
const onAPerson = t => { const m = S.graph.mode; return m?.mode === 'auto' ? isRoot(t)
    : m?.mode === 'semi' ? (S.run?.depth ?? depths(S.tasks))[t.id] < (m.boundary || 1) : true; };
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
    if (!r || !begun()) return '';
    if (r.state === 'running') return `<button class="hd-run" data-action="run-stop"${H.stop}>stop</button>`;
    const who = `stopped by ${r.by} ${ago(r.at)} ago${r.why ? ` — ${r.why}` : ''}`;
    const text = r.state === 'stopping' ? `stopping · ${r.working.length} still at work` : 'stopped';
    const tip = r.state === 'stopping' ? H.stopping(who, r.working.map(w => `${w.verb} · ${w.task_id || '—'} · ${ago(w.since)}`)) : H.stopped(who);
    return `<span class="hd-run-state${r.state === 'stopping' ? ' live' : ''}"${tip}>${text}</span>`
        + `<button class="hd-run" data-action="run-start"${H.start}>start</button>`;
}
// '' when the switch moved — the page then re-reads its header (main.js)
const switchRun = (verb, body) => act(post(`/api/run/${verb}`, body), {ok: null});
export async function stopRun() {
    const why = await askInPage('Stop this run? Nothing new starts — no executor, validator or issuer session, no '
        + 'timeout. Sessions running now finish and their signals land; the graph is not changed.',
        {yes: 'Stop', field: 'why — kept with the stop, shown to whoever looks (optional)'});
    return why === false ? false : switchRun('stop_project', {why, ...(myRole() ? {by: myRole()} : {})});
}
// Start sets the system working again — under AUTO its issuer and executors act and spend — so it is asked, as Stop is
export async function startRun() {
    const auto = S.graph.mode?.mode === 'auto';
    return await askInPage('Start this run again? The system starts sessions here once more'
        + (auto ? ' — under AUTO its executors, validators and issuer act and spend on their own.' : '.')
        + ' The time it stood stopped does not count against any deadline.', {yes: 'Start'})
        && switchRun('start_project', myRole() ? {by: myRole()} : {});
}

// The system's reports about ITSELF (a check contradicting its contract, a tool that cannot run): a quiet channel —
// they stop and move nothing — so a quiet chip, and none at all while there is none.
// Laid out beside the quality chip as a list one click opens — each report whole, its node one click away.
function drawReports() {
    const reports = S.reports;
    const seen = `${reports.length}|${reports.at(-1)?.at || ''}`;
    if ($('hd-reports').dataset.seen === seen) return;
    $('hd-reports').dataset.seen = seen;
    $('hd-reports').innerHTML = !reports.length ? '' : `<button class="hd-q" data-action="reports">${plural(reports.length, 'tech report')}</button>`
        + H.reports([...reports].reverse().map(r => ({head: r.role || 'the system',
            val: `<span class="hq-when"><span data-at="${esc(r.at)}">${esc(ago(r.at))}</span> ago</span>`,
            link: r.node ? `<button class="pn-link" ${data({action: 'select', id: r.node})}>${esc(r.node)} →</button>` : '', means: r.text})));
}
// the list is rebuilt only when a report arrives (it kept its scroll), so its ages are re-read when it is opened
export const toggleReports = () => {
    if ($('hd-reports').classList.toggle('open')) $('hd-reports').querySelectorAll('[data-at]').forEach(e => { e.textContent = ago(e.dataset.at); });
};

// A goal still open with nothing at work, no call on anyone, and no event for longer than the run folds as idle
// is STALLED — the one quiet that must not read "leave it" (a json-parser run sat 642h so, under "nothing needs you").
function stalled(calls) {
    const root = rootOf(S.tasks), run = S.run;
    // at work HERE means a session open or a process in flight — a leaf left EXECUTING by an executor that died is
    // exactly the stall to name, so a working STATE does not count
    // …and a run the person stopped is not stalled: it is stopped, and says so beside the goal
    if (calls || !run || !root || terminal(root.state) || busyNow(procs(), run.sessions)
        || S.runState?.state !== 'running') return '';
    const last = Math.max(...run.audit.map(a => a.t), ...run.sessions.map(s => s.end), 0), idle = Date.now() - last;
    return idle > GAP ? need(1, `stalled — nothing at work for ${dur(idle)}`, [root.id],
        H.stalled, '', 'stalled') : '';
}

export async function drawHeader() {
    // the left side is written ONCE, after every read: written first and the switch added after the frontier's
    // answer, the Stop button was missing for the length of each read — a blinking button on a live run
    const left = await goal();
    let chips = CALLS.map(byState).join('')
        + closures(S.closures.filter(contested), 'contested', '')
        + closures(S.closures.filter(c => c.by_hand && !contested(c)), 'closed by hand', ' paper');
    // WHAT THE ENGINE SAYS IS OWED (model.js loadFrontier): `stuck` comes with its `directive`. NAME WHO — "you" is
    // nobody on a shared graph. "Nothing needs you" is said only when the engine was asked.
    const f = S.frontier, heard = !!f;
    if (f) {
        // …and a node a state chip already shows is not counted twice.
        // (dropped only where that chip IS shown: under AUTO a person's own move below the root has none — critic)
        const shown = t => CALLS.includes(t.state) && onAPerson(t);
        // the engine's `mine`, as it is: under AUTO it marks the customer's own rulings on the root (a user's dispute) —
        // and today also a system dispute there, which /actions does not narrow by the mode lock: engineering's to fix
        const own = (f.steps || []).filter(x => x.mine);
        const mine = own.filter(x => !shown(taskOf(x.task_id))), me = myRole() || 'you', blocked = f.blocked_by || [];
        chips = (f.stuck ? need(1, `stuck${blocked.length ? ': ' + blocked.map(named).join(', ') : ''}`, blocked,
                                f.directive || H.stuck, '', 'stuck') : '')
            + need(mine.length, `for ${me}`, mine.map(x => x.task_id),
                   mine.map(x => `${x.action} ${named(x.task_id)}`)) + chips;
    }
    chips += stalled(chips);
    drawReports();
    $('hd-goal').innerHTML = left + runSwitch(S.runState);
    $('hd-needs').innerHTML = status + (chips || (heard ? '<span class="hd-quiet">nothing needs you</span>' : ''));
}

// The quality metrics. What each MEANS, how far it can be trusted (§15.8's grade) and which of them call a person are the
// server's (`means`, `grades`, `alarm`, from the module computing them) — a copy kept here drifted (2026-09-02).

// the server's `means` is a paragraph: its first sentence says what the metric counts and stands under the heading,
// the rest — how to read it, what it is not — one click away (a popover of five paragraphs read as prose, not a list);
// the server's own short name before a colon goes where it says what the heading already says
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

export function drawQuality() {
    const m = S.metrics;
    if (m) {
        // ⊥ is an empty population (§15.4) — a dash, not a fake 100%
        const means = m.means || {}, alarm = m.alarm || {}, ffs = m.false_fail_share;
        $('hd-quality').innerHTML = `<button class="hd-q${m.calls_person ? ' acc' : ''}" data-action="pop">quality</button>`
            + H.quality(Object.entries(m.grades || {}).flatMap(([k, grade]) => [{head: QUALITY[k] || k, tag: `${k}, ${grade}`, means: means[k] || '', none: m[k] == null,
                val: m[k] == null ? '<span class="hq-val">—</span><span class="hq-nil">no observations yet</span>'
                    : `<span class="hq-val${alarm[k] ? ' acc' : ''}">${pct(m[k])}</span>`},
                // §15.4: a low q_D is read TOGETHER with the false-FAIL share (an over-strict validator inflates it).
                ...k === 'q_D' && ffs != null ? [{head: QUALITY.false_fail_share, tag: 'high is bad', val: `<span class="hq-val">${pct(ffs)}</span>`, means: means.false_fail_share || ''}] : []]).map(readMeans));
    }
}
