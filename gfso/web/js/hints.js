// EVERY HINT AND POPOVER THE PAGE GIVES, written here — what is said where, and why there.
// The rule (the author, 2026-10-27): what is easy to remember once read goes to the KEY under «?»; what a reader needs
// almost every time stands as a LABEL beside the thing; a HOVER adds what the thing itself does not show and never
// repeats it; a POPOVER a click opens carries its title and caption set apart from its items. So four kinds:
//   KEY      — the «?» popover: the graph's arrows, the marks (dot, cross, ring, ⊥), the deck's counts.
//   LABEL    — words drawn beside a thing because the reader needs them each time: the timeline's bar kinds (run.js
//              KIND_NAME), the coverage cells' states (CELLS), the kinds of token a cost went to (TOKENS). PASS and
//              FAIL are no label: the key says them once.
//   HOVER    — `hover(head, …rows)`: one thing's detail, the first line its heading; `card()` lays it out for a view
//              that draws its own tip (the graph, the timeline, progress, spend, models).
//   POPOVER  — `pop(title, caption, items)`: the header's mode, tech reports and quality, and the key itself.
// No other module writes a `title`, a tip card or a popover row: tests/test_hints_live_in_one_place.py is red on one.
// WHAT ELSE THE PAGE SAYS, AND WHERE — so an analysis starting here misses nothing:
//   run.js   — the words for a run's facts, shown as content in the panel and Events and reused by the tips here:
//              roundsLine, countWords, failedWords, EDGE_NOTE, KIND_NAME, levelName.
//   vocab.js — the protocol's words: state labels, closureNote/byHand (how a node closed), PLAN_COST.
//   dialogs  — askInPage questions and notices, the text of an act being confirmed (header.js stop/start,
//              projects.js delete, acts.js, goal.js); forms' own field help (index.html goal panel, goal.js).
//   work.js  — the line under the Models table naming sessions that spent nothing (content, not a hint).
import {esc} from './dom.js';
import {dur, hm, usd, tok} from './draw.js';
import {KIND_NAME, roundsLine, countWords, EDGE_NOTE} from './run.js';

// ── the renderers ──
const lines = xs => xs.flat(Infinity).filter(Boolean).map(String);
// a hover on any element: the page's one tip reads `data-tip` (tip.js); the browser's own `title` box is never drawn
export const hover = (head, ...rows) => head ? ` data-tip="${esc(lines([head, rows]).join('\n'))}"` : '';
// a tip's card: the heading, a state badge where one is given, then one row per line — plain text, escaped here
export const card = (head, rows = [], badge = '') => `<div class="tt-name">${esc(head)}</div>${badge}`
    + lines(rows).map(r => `<div class="tt-row">${esc(r)}</div>`).join('');
const cap = s => s ? s[0].toUpperCase() + s.slice(1) : s;
// a popover: its title and the caption saying what it lists, set apart from the items; an item is a heading (a glyph
// before it, a value and a tag after it, a link at its end) and what it means; `group` starts a new group of items
const item = it => it.group ? `<div class="hp-group">${esc(it.group)}</div>`
    : `<div class="hq-row${it.on ? ' on' : ''}"><div class="hq-head">${it.glyph || ''}<b>${esc(it.head)}</b>${it.val || ''}`
      + `${it.tag ? `<i>${esc(it.tag)}</i>` : ''}${it.link || ''}</div>${it.means ? `<div class="hq-means">${esc(cap(it.means))}</div>` : ''}</div>`;
export const pop = (title, caption, items) => `<div class="hd-pop"><div class="hp-top"><b>${esc(title)}</b>`
    + `${caption ? `<p>${esc(caption)}</p>` : ''}</div>${items.map(item).join('')}</div>`;

// ── the key under «?» ──
const svg = (body, h = 11) => `<svg class="glyph" width="11" height="${h}" viewBox="-5.5 -5.5 11 ${h}">${body}</svg>`;
const KEY = [
    {group: 'The graph'},
    {glyph: '<i class="lg-split"></i>', head: 'node → its part', means: 'a solid arrow runs from a node to one of its parts — the split'},
    {glyph: '<i class="lg-dep"></i>', head: 'producer → its user', means: 'a dashed arrow runs from a part to the one that uses its result; that one waits for it to pass (Dep)'},
    {head: 'pulse', means: 'a node at work; filled in the accent when a process of this server runs it'},
    {head: 'number', means: 'how many delivery rounds a node took; in the accent while its last one failed'},
    {head: 'double-click', means: 'a node: frame it with all its parts · the background: the whole graph'},
    {group: 'The marks'},
    {glyph: svg('<circle class="mk-pass" cx="0" cy="0" r="3.5"/>'), head: 'dot', means: 'a PASS — in a criterion\'s row and its history, on the timeline and on a progress track'},
    {glyph: svg('<path class="mk-fail" d="M-3.5,-3.5l7,7m0,-7l-7,7"/>'), head: 'cross', means: 'a FAIL — the same mark in every view'},
    {glyph: svg('<circle class="mk-open" cx="0" cy="0" r="2.5"/>'), head: 'ring', means: 'a criterion\'s round with no value: not checked, or not named by that round\'s FAIL'},
    {head: 'V', means: 'a node\'s verdict: pass only when every criterion passes, fail when one fails'},
    {head: '⊥', means: 'no verdict yet — not a third value: V is pass or fail once checked (§2.3)'},
    {glyph: '<i class="brand-dot"></i>', head: 'brand dot', means: 'the goal delivered: its root passed'},
    {head: 'Del', means: 'the one party accountable for a node — its executor (§2.6); one assignee may run many sessions at once'},
    {group: 'The deck'},
    {head: 'at work', means: 'a node a process of this server runs, a session open on it, or a leaf in a working state; a parent waiting on its parts is not counted'},
    {head: 'sessions', means: 'the processes this server runs — said beside «at work» only when they are not one per node (one may carry a whole part)'},
    {head: 'spend', means: 'booked when each session ends — the model reports its cost then; a running one is counted, not priced'},
    {head: 'coverage cell', means: 'the STATE of a part responsible for the goal\'s criterion in its row (§2.4), not a verdict; the row\'s mark is the root\'s own'},
];
export const keyPop = () => pop('How to read the page', 'Each mark means one thing in every view.', KEY);

// ── LABELS drawn beside a thing ──
export const CELLS = [['done', 'part done'], ['open', 'part open'], ['rework', 'part in rework']];
export const TOKENS = [['input_tokens', 'input'], ['output_tokens', 'output'], ['cache_read_tokens', 'cache read'], ['cache_write_tokens', 'cache written']];

// ── the page's frame: index.html names these by `data-hint`, `mountHints()` writes them; the views use `frame()` ──
const FRAME = {
    projects: ['Projects', 'Find a run by its goal, when it ran, where it stands'],
    goal: ['Pose the goal', 'A project is one goal: you state it, the system plans its parts'],
    mine: ['Mine only', 'Dim every node the name in «acting as» does not hold'],
    actingAs: ['Acting as', "The name this page signs your moves with — the server's own agent unless you name yourself"],
    help: ['How to read the page'],
    close: ['Close', 'Esc'],
    grip: ['Drag to resize'],
    fold: ['Fold the deck', 'The open tab pressed again folds it too'],
    dismiss: ['Click to dismiss'],
    deadline: ['Deadline', 'When this part is due — before its parent is'],
    deleteProject: ['Delete this project', 'Offered only for a project that never ran: no model call, nothing spent',
                    'Irreversible — its database goes with its whole history; asks for its name'],
};
export const frame = k => hover(...FRAME[k]);
export const frameText = k => FRAME[k].join('\n');
export function mountHints() {
    document.querySelectorAll('[data-hint]').forEach(e => { e.dataset.tip = frameText(e.dataset.hint); });
    document.getElementById('tb-help').insertAdjacentHTML('beforeend', keyPop());
}
// a deck tab is named by the question it answers: the hover asks it, the tab's name is not said again
export const TAB = {
    timeline: hover('Which nodes ran when, and at once'),
    progress: hover("How the goal's criteria came to pass"),
    spend: hover('Where the money and session time went', 'By node, by level of the plan, by role'),
    models: hover('Who did the work', 'Each model in each role: sessions, what the cost went to, how full its contexts got'),
    events: hover('The log, grouped by node and kind', 'Newest first; a node\'s group opens its trail'),
};

// ── the header ──
export const H = {
    root: full => hover(full, 'Click to open the goal'),
    // one chip per kind of call on a person: the hover says why it calls and on which nodes; the chip already says how many
    need: (kind, rows) => hover({
        escalated: 'The issuer decides on these', challenged: 'A challenge waits on its issuer', blocked: 'A block waits on its issuer',
        contested: 'A PASS its own record contradicts, or a hand over an instrument', 'closed by hand': 'Closed by a hand, not an instrument',
        stuck: 'Nothing can move', stalled: 'Stalled: the goal is open and nothing has happened',
    }[kind] || 'Your moves, as the engine names them', rows),
    stuck: 'No actionable node and the root is not DONE',
    stalled: 'Nobody owes a move the engine names, nothing is at work — a run that stopped without an end; Events shows its last act',
    stop: hover('Stop the run', 'Nothing new starts: no executor, validator or issuer session, no timeout',
                'The sessions running now finish and their signals land'),
    start: hover('Start the run again', 'A bound that passed meanwhile fires as any passed bound does'),
    stopping: (who, working) => hover(`Stopping — ${working.length} still at work`, who, 'Each finishes and its signal lands:', working),
    stopped: who => hover('Stopped', who, 'Nothing runs and no timeout fires until it is started again'),
    // the mode: the three modes as items, this project's marked, then how this project's was set
    mode: (doc, mode, set) => pop('Who holds the work', 'The mode is set once per project; it decides which nodes a person holds and which the system does.',
        [...Object.entries(doc).map(([m, text]) => ({head: m, tag: m === mode ? 'this project' : '', on: m === mode, means: text})),
         ...set.length ? [{group: 'How it was set'}, ...set.map(([head, v]) => ({head, val: `<span class="hq-kv">${esc(v)}</span>`}))] : []]),
    reports: rs => pop('Tech reports', 'What the system reported about itself — a check contradicting its contract, a tool that cannot run. '
        + 'A report stops and moves nothing. Newest first.', rs),
    quality: rows => pop('Quality', 'How far the plan and its validation can be trusted, each metric with its grade (§15.8).', rows),
};

// ── the deck's strip ──
export const STRIP = {
    live: (name, row) => hover(name, row),
    held: hover('Stopped', 'Nothing runs here until the run is started again', 'These nodes keep the state their work was in'),
    block: (n, of, users) => hover(`${n} wait on ${of}`, 'None starts until it passes:', users),
    issuer: rows => hover('Waiting on the issuer', rows),
    back: rows => hover('Sent back — their last round failed', rows),
    more: rows => hover(`${rows.length} more at work`, rows),
    running: verb => `${verb} — a session running on this server`,
    carried: (top, verb) => `Carried by the session on ${top} (${verb})`,
    idle: 'In a working state; no process of this server runs it',
    spend: (byKind, running) => hover('Spend so far', byKind.map(([k, p]) => `${KIND_NAME[k]}: ${p.calls && p.unpriced === p.calls ? 'not reported' : usd(p.cost)} · ${p.calls} session${p.calls > 1 ? 's' : ''}`),
                                      running && `${running} running now, not booked yet`),
};

// ── the node's panel and reader ──
export const ISSUER_MOVES = "The executor stopped and the decision is the issuer's: raise the rework bound (Revise → max_iterations) "
    + 'if the forecast was short, change or narrow the criteria (Revise) if the plan is wrong, or close it (Cancel — it cascades '
    + "the live subtree). Silence closes it too, by this state's own timeout; it never drifts to a pass.";
export const PANEL = {
    escalated: hover('The issuer decides', ISSUER_MOVES),
    contested: hover('Read the verdict', 'Legitimate (§10.3), and nothing can check it (§15.7)'),
    deadline: (due, now) => hover(due < now ? `Overdue by ${dur(now - due)}` : `Due in ${dur(due - now)}`, new Date(due).toLocaleString()),
    earlier: hover('An earlier delivery', 'This verdict is about a delivery the current one replaced'),
    refused: note => hover('A later report was refused', note),
    rounds: n => hover(`This criterion over its last ${Math.min(n, 12)} of ${n} rounds`, 'Oldest left'),
    full: text => hover(text),
    directive: text => hover(text),
    model: id => hover(id),
    signed: hover('Who signed it (§10.3)'),
    // the L2 review's way out, said under its findings (a label: it is needed exactly when the review fails)
    twoWays: 'Two ways out: EDIT the criteria this names (the fix retires this verdict — run the review again after it), '
        + 'or record why a finding is wrong (<code>dispute_finding</code>).',
    probe: bhs => hover('What it checks', bhs),
};

// ── the views' own tips ──
export const TIP = {
    // a node on the graph: what the drawing does not say — its full name, who holds it, what it waits on, its rounds
    node: (t, badge, waits, rs, criteria, failing) => card(t.name || t.description || t.id,
        [t.assignee && `Del: ${t.assignee}`, waits && `Waits on ${waits}`, rs.length && roundsLine(rs), failing && `Failing: ${failing}`,
         criteria && `${criteria} criteria`], badge),
    rounds: rs => hover(roundsLine(rs)),
    // a stretch of work on the timeline
    bar: (name, x, r, failed) => card(name, [
        `${KIND_NAME[x.kind]}${x.agents.length ? ' · ' + x.agents.join(', ') : ''}`,
        `${hm(x.start)}–${x.open ? 'now' : hm(x.end)} · ${dur(x.end - x.start)}${x.cost ? ` · ${usd(x.cost)}` : ''}${x.tokens ? ` · ${tok(x.tokens)} tok` : ''}`,
        x.parts > 1 && `${x.parts} sessions (${x.kind === 'val' ? 'the validator works in batches of probes' : 'retried or continued'}) · ${dur(x.busy)} busy`,
        r && `Round ${r.n}${r.verdict ? ' → ' + r.verdict + (failed ? ': ' + failed : '') : ''}`,
        x.priced === false && 'No cost recorded for this call']),
    // a verdict's mark, on the timeline or a progress track
    verdict: (name, signal, r, t, own, m, total, edges) => card(name, [
        `${signal}${r ? ` · round ${r.n}` : ''} · ${hm(t)}`, own.length && `Failed: ${own.join(', ')}`,
        m && countWords(m, total), edges.length && `${edges.join(', ')}: ${EDGE_NOTE}`]),
    cell: (name, state) => hover(name, state),
    // a node's row in spend
    cost: (name, rows, rounds, all) => card(name, [...rows, `${rounds} delivery round${rounds === 1 ? '' : 's'} · ${all} in all`]),
    prefix: p => hover(p + '…', 'The start every assignee id shares, cut from the bars'),
    project: (name, id) => hover(name, id),
    where: why => hover(why),
};

// ── the models tab ──
export const MODELS = {
    sessions: hover('Sessions', 'Each model call is a session with a context of its own, unless it continued a conversation (marked)'),
    cost: hover('What the cost went to', "The row's cost split by kind of token, priced by Anthropic's structure: per input token 1, "
        + 'output 5, cache read 0.1, cache written 2', 'Another provider\'s rows are not split'),
    id: id => hover(id),
    window: hover('The model\'s context window'),
    fill: hover('Context filled', "Each session's fullest turn against its model's window: the dark bar the median session, the light one the fullest"),
    contexts: hover('Contexts', "A call that continued its round's conversation (cut at its turn cap) is no context of its own"),
    ends: hover('Worked, gave no answer', "A cut session's tokens are its turns' own, its price unknown", 'One out of turns is taken up by the next round'),
    turns: (turned, calls) => hover('Turns', `Recorded for ${turned} of the ${calls} sessions`),
    unpriced: hover('Unpriced', 'Sessions that spent tokens with no cost recorded — a cut stream among them', 'The share is of what was priced'),
    unrecorded: hover('Not recorded', 'Kept only for sessions run on a build that records it'),
    // the cost split: what each kind of token cost, and how many; or why it cannot be split
    split: (parts, note) => hover('Where the cost went', parts.map(([k, usd_, n]) => `${k}: ${usd_} · ${n} tokens`), note),
    unsplit: 'Cache read and written kept as one sum on this build: not split',
    foreign: "Not split: its provider's prices are not known here",
    // why a split does not cover its row, each cause counted apart — none is said that the row does not have
    covers: (share, s) => [`The split covers ${share} of the row's cost — the ${s.sessions} sessions its tokens price`,
        s.resumedOut && `${s.resumedOut} resumed round${s.resumedOut > 1 ? 's' : ''} booked the whole conversation's cost (recorded before the fix): the round before counted twice`,
        s.out - s.resumedOut && `${s.out - s.resumedOut} session${s.out - s.resumedOut > 1 ? 's' : ''} not priced by ${s.out - s.resumedOut > 1 ? 'their' : 'its'} own tokens`,
        s.unweighed && `${s.unweighed} session${s.unweighed > 1 ? 's' : ''} not split: recorded without the cache kept apart, without tokens, or unpriced`],
    fillOf: (med, max, w, n, calls) => hover('Context filled', `Median session ${med}${w ? ` of a ${w} window` : ''}`, `Fullest ${max}`,
                                              n < calls && `${n} of ${calls} sessions recorded`),
};
