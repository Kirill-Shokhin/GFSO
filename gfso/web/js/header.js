// The header, by significance: the project's goal and where it stands, then ONLY what needs a person
// (each a chip that selects its first node), then the quality metrics folded into one chip whose
// popover carries the meanings the server sends beside them.
import {$, esc, data} from './dom.js';
import {getJSON, post, singleFlight, GOAL} from './api.js';
import {S, taskOf, myRole} from './state.js';
import {label, closureNote, contested, modeDoc} from './vocab.js';
import {GAP} from './run.js';
import {dur} from './draw.js';

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
        : `<span class="hd-phrase${S.missing ? ' acc' : ''}">${esc(S.missing || 'no goal yet')}</span>`;
    const doc = mode ? await modeDoc() : {};
    const who = Object.entries(doc).map(([m, text]) => `${m === mode ? '▸ ' : ''}${m}: ${text}`).join('\n\n');
    // the goal's short name — up to its first parenthesis or colon — the whole of it on hover
    const full = root.name || root.id, short = full.split(/\s[(:—]/)[0].slice(0, 40);
    const delivered = root.state === 'DONE' && !['FAIL', 'CANCELLED'].includes(root.done_reason);
    // left: WHICH goal and who holds its work; where it stands goes to the middle, beside what needs a person —
    // the brand's dot marking the one real done: the goal delivered
    status = `<span class="hd-phrase">${phrase(root)}${delivered ? '<i class="brand-dot" title="the goal is delivered: the root passed"></i>' : ''}</span>`;
    return `<button class="hd-root"${data({action: 'select', id: root.id})} title="${esc(full)}">${esc(short)}</button>`
        + (mode ? `<span class="hd-mode" title="${esc('who holds the work —\n\n' + who)}">${esc(mode)}</span>` : '');
}

// One chip per kind of call on a person; `ids` are the nodes it is about, the first one is selected.
const need = (n, text, ids, why, cls = '') => !n ? '' : `<button class="need${cls}"${data({action: ids[0] && 'select', id: ids[0]})}`
    + ` title="${esc(why)}"><b>${n}</b> ${esc(text)}</button>`;
const CALLS = ['ESCALATED', 'CHALLENGED', 'BLOCKED'];
const byState = s => { const ts = S.tasks.filter(t => t.state === s);
    return need(ts.length, label(s).toLowerCase(), ts.map(t => t.id), ts.map(t => named(t.id)).join(' · ')); };
// …AND HOW THOSE DONES REST: an instrument's proof and a signature are not one kind of green (§15.7).
const closures = (list, text, cls) => need(list.length, text, list.map(c => c.id), list.map(c => `${c.id} — ${closureNote(c)}`).join(' · '), cls);

// A goal still open with nothing at work, no call on anyone, and no event for longer than the run folds as idle
// is STALLED — the one quiet that must not read "leave it" (a json-parser run sat 642h so, under "nothing needs you").
function stalled(calls) {
    const root = S.tasks.find(isRoot), run = S.run;
    // at work HERE means a session open or a process in flight — a leaf left EXECUTING by an executor that died is
    // exactly the stall to name, so a working STATE does not count
    if (calls || !run || !root || ['DONE', 'ABANDONED'].includes(root.state) || run.sessions.some(s => s.open)
        || S.inflight.some(w => w.project === S.project)) return '';
    const last = Math.max(...run.audit.map(a => a.t), ...run.sessions.map(s => s.end), 0), idle = Date.now() - last;
    return idle > GAP ? need(1, `stalled — nothing at work for ${dur(idle)}`, [root.id],
        'the goal is open, nothing is at work, nobody owes a move the engine names, and nothing has happened since — '
        + 'a run that stopped without an end; look at the deck (Events) for its last act') : '';
}

export const refreshHeader = singleFlight(async () => {
    $('hd-goal').innerHTML = await goal();
    let chips = CALLS.map(byState).join('')
        + closures(S.closures.filter(contested), 'contested', '')
        + closures(S.closures.filter(c => c.by_hand && !contested(c)), 'closed by hand', ' paper');
    // WHAT THE ENGINE SAYS IS OWED, asked AS WHOEVER THIS PAGE IS: `mine` is computed for `actor`, the YOU
    // ARE box that signs; `stuck` comes with its `directive`. NAME WHO — "you" is nobody on a shared graph.
    let heard = false;                // "nothing needs you" is said only when the engine was asked
    if (S.tasks.length) try {
        const r = await post('/api/run/next_steps', myRole() ? {actor: myRole()} : {});
        if (!r.ok) throw r.status;
        const f = await r.json();
        // …and a node a state chip already shows is not counted twice.
        const mine = (f.steps || []).filter(x => x.mine && !CALLS.includes(taskOf(x.task_id).state)), me = myRole() || 'you', blocked = f.blocked_by || [];
        chips = (f.stuck ? need(1, `stuck${blocked.length ? ': ' + blocked.map(named).join(', ') : ''}`, blocked,
                                f.directive || 'no actionable node and the root is not DONE') : '')
            + need(mine.length, `for ${me}`, mine.map(x => x.task_id),
                   mine.map(x => `${x.action} ${named(x.task_id)}`).join(' · ')) + chips;
        heard = true;
    } catch (e) { /* the frontier is a read; the chips from the graph still stand */ }
    chips += stalled(chips);
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
