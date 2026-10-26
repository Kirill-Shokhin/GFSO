// The protocol's words, written once: what each FSM state is called, how it is drawn, what V a node
// carries and what the panel may offer on it; how a closure is described; how a check is routed.
import {getJSON} from './api.js';

const A = (s, cls, label, prompt = '', needsCriteria = false) =>
    ({s, cls: 'btn-' + cls, label, prompt, needsCriteria});
const BLOCK = A('BLOCK', 'red', 'Block', 'reason');

// Rows are in the stats bar's order. Bucket: canon §7.1 + §8 (see gfso.css). WHAT IS RUNNING MUST NOT
// LOOK LIKE WHAT IS DEAD — EXECUTING is `busy`, waiting to be taken is `attend` (2026-09-02). OFFERED is
// ASSIGNED AND NOT YET TAKEN: labelled "In Review" it sent a user waiting 25 min on a reviewer who did
// not exist. REWORKING is consented
// work like EXECUTING (§12.1) and a FAIL sends to it by itself: in the accent it read as "step in" beside
// "nothing needs you", and flipped colour with its own validation. CHALLENGED is a wait on the issuer, as
// BLOCKED is (§12.1); under a mode that issuer is the machine.
// Moves — the panel's controls that are no signal: E Edit (a re-ASSIGN, §12.3), D Decompose, V Record verdict (the
// human counterpart of validate_result).
const ROWS = {
    //           bucket       label          moves
    DONE:       ['done',      'Done',        ''],
    EXECUTING:  ['busy',      'In Progress', 'ED'],
    OFFERED:    ['attend',    'Not started', 'ED'],
    BLOCKED:    ['pathology', 'Blocked',     'ED'],
    REWORKING:  ['busy',      'Rework',      'ED'],
    CHALLENGED: ['pathology', 'Challenged',  'ED'],
    VALIDATING: ['busy',      'Validating',  'EV'],
    IDLE:       ['quiet',     'Waiting',     ''],
    CANCELLING: ['pathology', 'Cancelling',  ''],
    ABANDONED:  ['quiet',     'Cancelled',   ''],
    ESCALATED:  ['pathology', 'Escalated',   'E'],
};
// WHICH signals a node admits is the engine's answer (`/api/tasks/{id}/actions`): a copy of the FSM here had drifted —
// no Challenge after consent (ortho audit). What stays here is how each signal is offered; ASSIGN is not offered as a
// signal (Edit is the re-ASSIGN; a DONE's reopen has no control here yet).
const LOOK = Object.fromEntries([
    A('ACCEPT', 'green', 'Accept'), A('CHALLENGE', 'orange', 'Challenge', 'reason'), A('DELIVER', 'blue', 'Deliver', 'result'),
    BLOCK, A('RESOLVE_BLOCK', 'blue', 'Resolve Block', 'action'), A('ACCEPT_CHALLENGE', 'green', 'Accept Challenge'),
    A('REJECT_CHALLENGE', 'muted', 'Reject Challenge', 'justification'), A('PASS', 'green', 'Pass'), A('FAIL', 'red', 'Fail', '', true),
    A('CANCEL', 'muted', 'Cancel', 'reason'), A('CONFIRM_CANCEL', 'muted', 'Confirm Cancel', 'in_flight'),
].map(a => [a.s, a]));
export const look = sig => LOOK[sig];
// The state predicates every view reads, written once: terminal (§12.1), delivered — the engine's settled_positive,
// DONE by a PASS or the timeout's AUTO_PASS — and working (consented work or its validation in course).
export const terminal = s => s === 'DONE' || s === 'ABANDONED';
export const delivered = t => t?.state === 'DONE' && (t.done_reason === 'PASS' || t.done_reason === 'AUTO_PASS');
export const working = s => s === 'EXECUTING' || s === 'REWORKING' || s === 'VALIDATING';
const row = s => ROWS[s] || ['quiet', s, ''];
export const bucketOf = s => row(s)[0];
export const label = s => row(s)[1];
export const can = (s, move) => row(s)[2].includes(move);
// V(t) as the log says it, not as a state implies it — the state is orthogonal to V (§12.1): a CHALLENGE before any
// delivery read V = fail. A PASS is V = pass and a FAIL V = fail (§11.2); a delivery awaiting its verdict, or a contract
// installed since (ASSIGN, ACCEPT_CHALLENGE), is ⊥ (§2.3), and so is a cancelled node (§12.1). Without the node's log
// (a part listed under its parent) only the states that carry V by entry: DONE by its done_reason, REWORKING by a FAIL.
export const vNow = (t, audit) => {
    if (delivered(t)) return 'pass';
    if (t?.state === 'ABANDONED') return 'undef';
    if (!audit) return t?.state === 'DONE' || t?.state === 'REWORKING' ? 'fail' : 'undef';
    let v = 'undef';
    for (const a of audit) if (!a.rejected)
        v = a.signal === 'PASS' ? 'pass' : a.signal === 'FAIL' ? 'fail' : ['DELIVER', 'ASSIGN', 'ACCEPT_CHALLENGE'].includes(a.signal) ? 'undef' : v;
    return v;
};
export const V_SYMBOL = {pass: '✓', fail: '✗', undef: '⊥'};
// A terminal DONE is discriminated by its done_reason (PASS/FAIL/AUTO_PASS — canon §12).
// A model id as a person says it — claude-haiku-4-5-20251001 → haiku 4.5; a bare alias, recorded before the model
// that ran was kept, says the version is unknown; any other id — another provider's — as written.
export const modelName = m => { const x = /^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$/.exec(m || '');
    return x ? `${x[1]} ${x[2]}${x[3] ? '.' + x[3] : ''}` : /^(haiku|sonnet|opus|fable)$/.test(m || '') ? `${m} · version not recorded` : m || 'model not recorded'; };
export const statusLabel = (s, doneReason) => (s === 'DONE' && doneReason) ? doneReason : label(s);

// A CLOSED NODE IS NOT ONE KIND OF THING (§15.7): what the drawing says about a closure, in words.
export const byHand = who => `asserted by hand — ${who || 'someone'}, not an instrument`;
export const closureNote = cl => !cl ? ''
    : cl.refuted   ? 'PASS CONTRADICTED by its own current record'
    : cl.overruled ? `asserted by hand over an instrument's ${cl.overruled_verdict || 'opposite'}`
    : cl.by_hand   ? byHand(cl.validator)
    : cl.provenance === 'self' ? 'self-reported by its own executor (§10.3 internal node)'
    : '';
export const contested = cl => !!(cl && (cl.refuted || cl.overruled));
// A Level-2 checker's word on one criterion.
export const mark = v => v === 'sufficient' ? '✓' : v === 'insufficient' ? '✗' : '?';

// CHECK → failure-mode routing (§9.5) and FM names (§8.10) come FROM THE PRODUCT: a copy kept here
// drifted (CHECK-6 → FM-1, no CHECK-1b/7/8). tests/test_canon_check_map.py guards the table.
export const FM = {route: {}, label: {}};
export async function loadCheckMap() {
    try {
        const m = await getJSON('/api/check_map');
        FM.route = m.check_to_fm || {};
        FM.label = m.fm_label || {};
    } catch (e) { /* offline: render the codes bare rather than a wrong name */ }
}
// Absent from the map ≠ mapped to nothing: CHECK-1c is an engineering addition with no canon row,
// CHECK-6 is a battery row guarding no mode (§9.5). Neither is `FM-?`, a defect it is not.
export const FM_NONE = 'engineering checks (outside the canon battery)';
export const FM_NO_MODE = 'battery checks that guard no failure mode';
export const fmOf = name => {
    const fm = FM.route[name];
    return !fm ? FM_NONE : !Array.isArray(fm) ? fm : fm.length ? fm.join(' · ') : FM_NO_MODE;
};

// What a planning verb costs, said before it runs — the same words wherever one is offered.
export const PLAN_COST = 'Runs ~2–6 min and spends model calls; its progress shows in the deck (Events, with narration on).';

// WHO HOLDS THE WORK, in the server's words: the `set_mode` doc's three bullets, read once.
let modes;
export const modeDoc = () => modes ??= getJSON('/api/tools').then(d => {
    const doc = (d.tools || []).find(t => t.tool === 'set_mode')?.doc || '';
    return Object.fromEntries([...doc.matchAll(/- `(\w+)` — ([\s\S]*?)(?=\n\s*- `|\n\s*\n|$)/g)]
        .map(([, m, text]) => [m, text.replace(/\s+/g, ' ').trim()]));
}).catch(() => (modes = null, {}));
