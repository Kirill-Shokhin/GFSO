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
// consented work in course (§12.1): a parent in it waits on its parts
export const consented = s => s === 'EXECUTING' || s === 'REWORKING';
// cancelled: ABANDONED, or the legacy DoneReason of pre-v3.7 rows
export const cancelled = t => t?.state === 'ABANDONED' || t?.done_reason === 'CANCELLED';
// a closed goal in one word: done only when delivered, failed by a FAIL, else abandoned; '' while it is open
// ONE WORD for the state the engine calls ABANDONED: «cancelled», as its label, its key row and the Cancel that reaches it
// say — the timeline wrote the engine's name and the list «abandoned» beside «Cancelled» (the author, 2026-10-31)
export const goalWord = root => !terminal(root?.state) ? '' : delivered(root) ? 'done' : root.done_reason === 'FAIL' ? 'failed' : 'cancelled';
// a node the plan left unnamed is said by its id, never as nothing
export const nameOf = t => t?.name || t?.id;
// A Dep edge's bare declaration (`dep__…` with no check) is no criterion of its consumer — V leaves it out (Spec.conjuncts);
// a `dep__` that pins a check on this result is one, like any other. The criteria a verdict is over, by name.
export const conjunct = c => !c?.depends_on || !!c.check?.length;
export const criteriaOf = t => (t?.criteria || []).filter(conjunct).map(c => c.name || c);
// the verdicts in a log: a PASS or a FAIL the engine took
export const isVerdict = a => !a.rejected && (a.signal === 'PASS' || a.signal === 'FAIL');
const row = s => ROWS[s] || ['quiet', s, ''];
export const bucketOf = s => row(s)[0];
// the states one look of a node stands for — the key under «?» names them from here, never from a copy
export const statesIn = bucket => Object.keys(ROWS).filter(s => ROWS[s][0] === bucket);
export const label = s => row(s)[1];
export const can = (s, move) => row(s)[2].includes(move);
// V(t), never a table of state → V — the state is orthogonal to V (§12.1): a CHALLENGE before any delivery read V = fail.
// A PASS is V = pass, a FAIL V = fail (§11.2); a delivery awaiting its verdict or a contract installed since (ASSIGN,
// ACCEPT_CHALLENGE) is ⊥ (§2.3). The states those signals enter carry V by that entry and are read off the fresh state:
// DONE by its done_reason (a legacy CANCELLED is a cancellation), REWORKING (entered by FAIL), VALIDATING and OFFERED (no
// verdict on this version), ABANDONED (⊥, §12.1). The rest — entered by signals that leave V as it was — read the node's
// log, which may be a read behind (a part's row reads the run's); without one they are ⊥.
const BY_ENTRY = {REWORKING: 'fail', VALIDATING: 'undef', OFFERED: 'undef', IDLE: 'undef', ABANDONED: 'undef'};
export const vNow = (t, audit) => {
    if (delivered(t)) return 'pass';
    if (t?.state === 'DONE') return t.done_reason === 'CANCELLED' ? 'undef' : 'fail';
    if (BY_ENTRY[t?.state]) return BY_ENTRY[t.state];
    if (!audit) return 'undef';
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
    return x ? `${x[1]} ${x[2]}${x[3] ? '.' + x[3] : ''}` : /^(haiku|sonnet|opus|fable)$/.test(m || '') ? `${m} (version not recorded)` : m || 'model not recorded'; };
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
        FM.loaded = true;
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

// THE KINDS OF TOKEN a cost goes to, one table, in the order the Models bar draws them: the ledger's field, the kind's name,
// its weight in Anthropic's price structure (Claude Code writes the one-hour cache), and the Models row's field.
export const TOKENS = [['input_tokens', 'input', 1, 'input'], ['output_tokens', 'output', 5, 'output'],
    ['cache_read_tokens', 'cache read', 0.1, 'read'], ['cache_write_tokens', 'cache written', 2, 'write']];

// What a signal carries beyond its move, in the log's words: the field, and what it is called where it is shown.
export const CARRIED = [['error', 'why refused'], ['reason', 'reason'], ['justification', 'justification'], ['action', 'resolution'],
    ['result', 'report'], ['failed_criteria', 'failed criteria'], ['in_flight', 'in flight']];

// What a planning verb costs, said before it runs — the same words wherever one is offered.
export const PLAN_COST = 'Runs ~2–6 min and spends model calls; its progress shows in the deck (Events, with narration on).';

// WHAT EACH MODE MEANS, said to a person: set_mode's own doc is written to the agent («you (the user-agent) hold…»), and
// read to a person it named the wrong reader (audit A10). What each mode NEEDS stays the engine's (`/api/modes`).
export const MODES = {
    solo: "The user's agent holds every node and performs it; the system validates the goal and every part larger than one session.",
    semi: "The user's agent holds the top of the plan — the goal, by default — and makes the issuer's moves there; the project's registered executors hold every part below it.",
    auto: "The system holds every node, the goal included. The user's agent is the customer: it states the goal and reads where it stands, and does not intervene.",
};
