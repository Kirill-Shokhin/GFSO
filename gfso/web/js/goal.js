// The goal constructor: THIS tab's project's one goal, stated whole — its contract, and whether the system
// plans it. A slide-over from the left; nothing is sent until one of its two buttons. What the engine owns it
// READS: admission (`/api/admission`, the ladder every ASSIGN runs) and who holds the work (`/api/modes`).
import {$, esc} from './dom.js';
import {cap} from './fmt.js';
import {getJSON, post, refusal} from './api.js';
import {S, myRole, begun} from './state.js';
import {notice, askInPage, act, askProjectName, NO_ANSWER} from './overlays.js';
import {PLAN_COST, MODES} from './vocab.js';
import {critRow, readCrits, pairRow, listRow, readPairs, readList, iso, suggest} from './forms.js';
import {rootOf} from './tree.js';

const root = () => rootOf(S.tasks);
const panel = () => $('goal-panel');
const say = text => { $('gp-out').innerHTML = text ? `<div class="gp-say">${esc(text)}</div>` : ''; };
const mode = () => S.graph.mode?.mode || '';

// one goal is one project (one root): the button poses a project's goal while it has none; with one posed, a new project
// is the projects list's own «+ new project» — a second one here was a duplicate on the main page (the author, 2026-10-27)
export const labelGoalButton = () => { $('btn-goal').hidden = begun(); };

// ONE PROJECT HOLDS ONE GOAL: with a root here, a new goal means a new project — the tab goes there first,
// so the form always states the goal of the project it stands in.
export async function openGoal() {
    if (root()) {
        notice('This project holds its goal, and a project holds one: name a new project — its goal is stated there.');
        return askProjectName({goal: 1});
    }
    $('gp-project').innerHTML = `<p class="gp-note">The goal of <b>${esc(S.project || 'the active project')}</b>.</p>`;
    $('gp-assignee').value ||= myRole();
    panel().hidden = false;
    $('gp-title').focus();
    await whoHolds();
    check();
}
export const closeGoal = () => { panel().hidden = true; };
// a mode set or an agent registered while the form is open: what each mode needs is read again (main.js NEWS)
export const recheckHolds = () => { if (!panel().hidden) whoHolds().then(check); };

// ── who holds the work: shown, not chosen here — a mode is the user's choice made once before the plan, and
// set by their agent (`set_mode`) once its executors and validator are registered; the page reads what each
// mode needs from the rule set_mode enforces ──
async function whoHolds() {
    const doc = MODES, m = mode();
    const r = !m && await getJSON('/api/modes').catch(() => null);
    // readiness for the default way of working (dispatch); "I do the work myself" (in_chat) is the user's to ask for
    // …a want every mode shares said once above them, not three times under each (audit A11)
    const ms = r?.modes ? ['solo', 'semi', 'auto'].map(k => r.modes[k].dispatch) : [];
    const shared = ms.length && ms.every(s => !s.ready && s.missing === ms[0].missing) && ms[0].missing;
    const need = s => s.ready ? 'ready' : shared ? 'not ready' : esc(s.missing);
    $('gp-modes').innerHTML = m
        ? `<p class="gp-note">This project runs <b>${esc(m)}</b> — ${esc(doc[m] || '')}</p>`
        : `<p class="gp-note">No mode yet. A mode — who holds which nodes — is the user's choice, set by their agent `
          + `(<code>set_mode</code>) BEFORE the goal is created: it governs nodes issued after it, so a goal created here `
          + `first is held by you, and under AUTO the goal must be stated after the mode. Executors and a validator can be `
          + `registered for a project before it exists (<code>register_agent</code>).</p>`
          + (shared ? `<p class="gp-note gp-shared">${esc(shared)}</p>` : '')
          + ['solo', 'semi', 'auto'].map(k => `<div class="gp-mode off"><b>${cap(k)}</b><span>${esc(doc[k] || '')}</span>`
              + (r?.modes ? `<span class="gp-needs">${need(r.modes[k].dispatch)}</span>` : '') + '</div>').join('');
}

// ── the contract's rows ──
export const addCrit = c => { critRow($('gp-crits'), c, {rowCls: c ? ' ai-suggested' : ''}); check(); };
export const addScope = () => listRow($('gp-scope'), 'what the goal leaves out…');
export const addRisk = () => { pairRow($('gp-risks'), '', '', {ph: ['risk event', 'why it is accepted']}); };
export async function suggestCrits() {
    const cs = await suggest($('gp-suggest'), $('gp-desc').value.trim());
    if (!cs) return say('Write the description first — criteria are suggested from it.');
    cs.forEach(c => addCrit(c));
}

// What admission would refuse of the goal as written — asked of the engine as the form changes; the hand-made
// path stays shut while it answers anything. Under AUTO the system states the goal, so it stays shut too.
let asked = 0, soon;
export const recheck = () => (clearTimeout(soon), soon = setTimeout(check, 300));
export async function check() {
    const n = ++asked, auto = mode() === 'auto';
    const r = auto ? null : await post('/api/admission', {name: $('gp-title').value, description: $('gp-desc').value,
                                                         criteria: readCrits($('gp-crits'))}).then(x => x.ok ? x.json() : null).catch(() => null);
    if (n !== asked) return;                              // a later edit asked again
    const no = auto ? 'Under AUTO the goal is stated by the system: it authors the root, its criteria and their checks.'
        : r ? r.defects.join(' · ') : '';
    $('gp-create').disabled = !!no;
    $('gp-why').textContent = no || (r ? '' : "the engine's admission check is not reachable here — the server will say what it refuses");
    $('gp-assignee').disabled = !!mode();
    $('gp-assignee-note').textContent = mode() ? `— the ${mode()} mode decides who holds the root` : '';
}

// The statement as the form holds it, or the first thing missing from it.
function read(plan) {
    const v = {name: $('gp-title').value.trim(), description: $('gp-desc').value.trim(), criteria: readCrits($('gp-crits')),
               scope: readList($('gp-scope')), accepted_risks: readPairs($('gp-risks'), ['item', 'justification'], false),
               assignee: mode() ? '' : $('gp-assignee').value.trim(), deadline: iso($('gp-deadline').value)};
    v.error = !v.description ? ['gp-desc', 'Describe the task first — a node is its contract, and this is its goal.']
        : !plan && !mode() && !v.assignee ? ['gp-assignee', 'Name an assignee: every task has exactly one accountable executor '
                                             + '(Del, §2). Put your own name here if it is yours.'] : null;
    return v;
}
// The planner takes the statement as text — everything the form holds, so nothing typed is dropped.
const asText = v => [v.name, v.description,
    v.criteria.length && 'Criteria:\n' + v.criteria.map(c => `- ${c.name}: ${c.description}`
        + c.check.map(p => `\n  check: ${p.behaviour} — \`${p.command}\` → ${p.expect}`).join('')).join('\n'),
    v.scope.length && 'Out of scope:\n' + v.scope.map(s => `- ${s}`).join('\n'),
    v.accepted_risks.length && 'Accepted risks:\n' + v.accepted_risks.map(r => `- ${r.item}${r.justification ? ' — ' + r.justification : ''}`).join('\n'),
].filter(Boolean).join('\n\n');

// create_task | auto_decompose on this tab's project. The engine's refusals are written for people, so they are
// shown as they come. UNDER A MODE NO `assignee` IS SENT: the mode already answers whose the root is.
async function submit(plan) {
    const v = read(plan);
    if (v.error) { say(v.error[1]); return $(v.error[0]).focus(); }
    if (plan && !(await askInPage('Create the goal and let the system plan it (search↔audit → verified subtree)? ' + PLAN_COST))) return;
    say('');
    const who = v.assignee ? {assignee: v.assignee} : {}, done = () => { closeGoal(); S.reload(); };
    if (!plan) {
        return act(post('/api/run/create_task', {spec: {name: v.name, description: v.description,
            criteria: v.criteria, scope: v.scope, accepted_risks: v.accepted_risks}, deadline: v.deadline, ...who}), {to: say, ok: done});
    }
    // A plan runs for minutes and the server keeps running it whoever waits: a quick answer is a refusal and is
    // shown here; a slow one is a run, followed in the deck.
    const run = post('/api/run/auto_decompose', {request: asText(v), ...who}).then(refusal, () => NO_ANSWER);
    const quick = await Promise.race([run, new Promise(ok => setTimeout(() => ok(null), 5000))]);
    if (quick) return say(quick);
    if (quick === null) run.then(n => n ? notice(`The plan was refused: ${n}`, 'bad') : S.reload());
    done();
}
export const createGoal = () => submit(false);
export const planGoal = () => submit(true);
