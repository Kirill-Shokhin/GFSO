// EVERY HINT AND POPOVER THE PAGE GIVES, written here — what is said where, and why there.
// The rule (the author, 2026-10-27): what is easy to remember once read goes to the KEY under «?»; what a reader needs
// almost every time stands as a LABEL beside the thing; a HOVER adds what the thing itself does not show and never
// repeats it; a POPOVER a click opens carries its title and caption set apart from its items. So four kinds:
//   KEY      — the «?» popover: the graph's arrows, the marks (dot, cross, ⊥), the deck's counts.
//   LABEL    — words drawn beside a thing because the reader needs them each time: the timeline's bar kinds (run.js
//              KIND_NAME), the coverage cells' states (CELLS). The kinds of token (TOKENS) are the key's: the Models bar
//              says each on its own segment's hover. PASS and
//              FAIL are no label: the key says them once.
//   HOVER    — `hover(head, …rows)`: one thing's detail, the first line its heading; `card()` lays it out for a view
//              that draws its own tip (the graph, the timeline, progress, spend, models).
//   POPOVER  — `pop(title, caption, items)`: the header's mode, tech reports and quality, and the key itself.
// No other module writes a `title`, a tip card or a popover row: tests/test_hints_live_in_one_place.py is red on one.
// WHAT ELSE THE PAGE SAYS, AND WHERE — so an analysis starting here misses nothing:
//   run.js   — the words for a run's facts, shown as content in the panel and Events and reused by the tips here:
//              roundsLine, failedWords, EDGE_NOTE, KIND_NAME, levelName.
//   vocab.js — the protocol's words: state labels, closureNote/byHand (how a node closed), PLAN_COST.
//   dialogs  — askInPage questions and notices, the text of an act being confirmed (header.js stop/start,
//              projects.js delete, acts.js, goal.js); forms' own field help (index.html goal panel, goal.js).
//   work.js  — the line under the Models table naming sessions that spent nothing (content, not a hint).
import {esc} from './dom.js';
import {dur, hm, usd, tok} from './draw.js';
import {KIND_NAME, roundsLine, EDGE_NOTE} from './run.js';
import {statesIn, label} from './vocab.js';

// ── the renderers ──
const lines = xs => xs.flat(Infinity).filter(Boolean).map(String);
// a hover on any element: the page's one tip reads `data-tip` (tip.js); the browser's own `title` box is never drawn
export const hover = (head, ...rows) => head ? ` data-tip="${esc(lines([head, rows]).join('\n'))}"` : '';
// a tip's card: the heading, a state badge where one is given, then one row per line — plain text, escaped here
// …a heading may carry its figure apart, at the right (`head\tfigure`), and a row may be a SHARE drawn as a filled line
// with its percent at the end (`meter()`): a percent run on after a sum in one line read as mush (the author, 2026-10-27)
const METER = '\u0007';
// …its figure at the end is the percent, or the sum the share is of (a role's cost)
export const meter = (label, share, figure = '') => `${METER}${label}\t${share}\t${figure}`;
const row = r => { if (!r.startsWith(METER)) return `<div class="tt-row">${esc(r)}</div>`;
    const [label, share, figure] = r.slice(1).split('\t'), p = `${Math.round(+share * 100)}%`;
    return `<div class="tt-meter"><span>${esc(label)}</span><i><b style="width:${p}"></b></i><em>${esc(figure || p)}</em></div>`; };
export const card = (head, rows = [], badge = '') => { const [h, figure] = head.split('\t');
    return `<div class="tt-name${figure ? ' tt-split' : ''}"><span>${esc(h)}</span>${figure ? `<b>${esc(figure)}</b>` : ''}</div>${badge}`
        + lines(rows).map(row).join(''); };
const cap = s => s ? s[0].toUpperCase() + s.slice(1) : s;
// a popover: its title and the caption saying what it lists, set apart from the items; an item is a heading (a glyph
// before it, a value and a tag after it, a link at its end) and what it means; `group` starts a new group of items
const item = it => it.group ? `<div class="hp-group">${esc(it.group)}</div>`
    : it.key ? `<div class="hk-row"><span class="kg">${it.glyph || ''}</span><b>${esc(it.head)}</b>${it.means ? `<span>${esc(it.means)}</span>` : ''}</div>`
    : `<div class="hq-row${it.on ? ' on' : ''}"><div class="hq-head">${it.glyph || ''}<b>${esc(it.head)}</b>${it.val || ''}`
      + `${it.tag ? `<i>${esc(it.tag)}</i>` : ''}${it.link || ''}</div>${it.means ? `<div class="hq-means">${esc(cap(it.means))}</div>` : ''}`
      + `${it.more ? `<details class="hq-more"><summary>how it is read</summary>${esc(it.more)}</details>` : ''}</div>`;
export const pop = (title, caption, items) => `<div class="hd-pop"><div class="hp-top"><b>${esc(title)}</b>`
    + `${caption ? `<p>${esc(caption)}</p>` : ''}</div>${items.map(item).join('')}</div>`;

// ── the key under «?» ──
const svg = (body, h = 11) => `<svg class="glyph" width="11" height="${h}" viewBox="-5.5 -5.5 11 ${h}">${body}</svg>`;
// the kinds of token a cost went to, in the order the Models bar draws them (a LABEL's words, and the key's)
export const TOKENS = [['input_tokens', 'input'], ['output_tokens', 'output'], ['cache_read_tokens', 'cache read'], ['cache_write_tokens', 'cache written']];
export const COST_CLS = k => `wk-${k.split('_')[0] + (k.includes('write') ? 'w' : '')}`;

// THE KEY reads by meaning: each row is one glyph, drawn as the page draws it, and in bold WHAT IT MEANS — the reader
// scans for the meaning beside the shape, not for a description of the shape; the small line under it only where the
// meaning alone does not settle it (the author, 2026-10-27: «на ключевое место ты ставишь воду»). One glyph per row.
// The brand dot is no row: it only ever stands beside the word DONE, which says it, and keyed it read as a second PASS.
// A node's look: a swatch drawn by the graph's own rule (gfso.css .kn-*, after graph.js NODE_STYLE), its states named by
// vocab — a cancelled node keeps the quiet bucket's state but is drawn as a tombstone, so it is left out there.
const node = (look, head, bucket, means) => ({glyph: `<i class="kn kn-${look}"></i>`, head,
    means: [bucket && statesIn(bucket).filter(s => s !== 'ABANDONED').map(label).join(' · '), means].filter(Boolean).join(' — ')});
const KEY = [
    {group: 'The graph'},
    {glyph: '<i class="lg-split"></i>', head: 'Split into its parts', means: 'from a node to each of its parts'},
    {glyph: '<i class="lg-dep"></i>', head: 'Uses the result of', means: 'the user waits until its producer passes (Dep)'},
    {glyph: '<i class="cy-live"></i>', head: 'At work', means: 'counted in the deck as «N at work»; a parent only waiting on its parts is not'},
    {glyph: '<i class="cy-live on"></i>', head: 'Running on this server now', means: 'a process of this server works on it'},
    // one mark, the round count; its accent is a state of it, not a second mark (the author: «почему это две разные и одинаковой иконкой»)
    {glyph: '<span class="kb">3</span>', head: 'Delivery rounds', means: 'from the second on; in the accent while the last one failed'},
    {glyph: '<svg class="glyph" width="22" height="11" viewBox="0 0 22 11"><rect class="tl-exec" x="0" y="3" width="22" height="5" rx="1.5"/><line class="tl-hand" x1="11" x2="11" y1="1" y2="10"/></svg>',
     head: 'Session handed over', means: 'on the timeline: its context reached the budget, a fresh session went on from its note'},
    {glyph: '<b class="kt">2×</b>', head: 'Double-click', means: 'a node frames it with its parts · the background shows the whole graph'},
    {group: 'Verdicts'},
    {glyph: svg('<circle class="mk-pass" cx="0" cy="0" r="3.5"/>'), head: 'PASS', means: 'in a criterion\'s row, on the timeline, on a progress track'},
    {glyph: svg('<path class="mk-fail" d="M-3.5,-3.5l7,7m0,-7l-7,7"/>'), head: 'FAIL'},
    {glyph: '<b class="kt">V</b>', head: "The node's verdict", means: 'pass only when every criterion passes'},
    {glyph: '<b class="kt">⊥</b>', head: 'No value', means: 'not checked yet, or not named by that round\'s FAIL — not a third value: V is pass or fail once checked (§2.3)'},
    {group: 'The deck'},
    {glyph: '<b class="kt">· N</b>', head: 'Sessions', means: 'beside «at work» only when not one per node — one session may carry a whole part'},
    {glyph: `<span class="wk-cost kc">${TOKENS.map(([k]) => `<i class="${COST_CLS(k)}" style="width:25%"></i>`).join('')}</span>`,
     head: 'Cost split', means: `Models: ${TOKENS.map(([, n]) => n).join(' · ')}, left to right; a segment's hover gives its figures`},
    {glyph: '<b class="kt">$</b>', head: 'Spend', means: 'booked when a session ends; a running one is counted, not priced'},
    {glyph: '<i class="cv cv-done"></i>', head: "A part's state, not a verdict", means: 'a coverage cell: the part responsible for that criterion (§2.4); the row\'s mark is the root\'s own'},
    {group: 'Nodes'},
    node('done', 'Closed', '', 'passed or failed: its state badge says which'),
    node('busy', 'In work', 'busy'),
    node('attend', 'Handed over, not taken yet', 'attend'),
    node('pathology', 'Waits on a decision', 'pathology'),
    node('quiet', 'Not handed over yet', 'quiet'),
    node('cancelled', 'Cancelled', '', 'kept for its history'),
    node('contested', 'PASS contested', '', 'its own record contradicts it, or a hand overruled an instrument'),
    node('byhand', 'Closed by hand', '', 'on a person\'s word, not an instrument\'s check'),
    {glyph: '<b class="kt">Del</b>', head: 'Its executor', means: 'the one accountable party (§2.6); it may run many sessions at once'},
];
export const keyPop = () => pop('How to read the page', 'Each mark means one thing in every view.', KEY.map(it => it.group ? it : {...it, key: true}));

// ── LABELS drawn beside a thing ──
export const CELLS = [['done', 'part done'], ['open', 'part open'], ['rework', 'part in rework']];

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
    root: full => hover(full),
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
    // the server's `means` is a paragraph: its first sentence says what the metric counts and stands under the heading,
    // the rest — how to read it, what it is not — one click away (a popover of five paragraphs read as prose, not a list);
    // the server's own short name before a colon goes where it says what the heading already says
    quality: rows => pop('Quality', 'How far the plan and its validation can be trusted, each metric with its grade (§15.8).',
        rows.map(r => { const [, first, rest] = /^(.+?\.)\s+(?=[A-Z0-9⊥(])(.*)$/s.exec(r.means || '') || [, r.means];
            const words = s => s.toLowerCase().match(/[a-z]{4,}/g)?.map(w => w.slice(0, 5)) || [], head = words(r.head);
            const named = /^([a-z][^:()]{0,40}):\s+/i.exec(first || ''), said = named && words(named[1]).some(w => head.includes(w));
            return {...r, means: said ? first.slice(named[0].length) : first, more: rest}; })),
};

// what each quality metric measures, as its row's heading — its code (q_D…) and grade go beside it as the tag; the server
// says the rest (`means`)
export const QUALITY = {q_D: 'Splits that held', q_V: 'Verdicts that held', q_T: 'Criteria that held as issued',
    q_Dep: 'Dependencies foreseen', q_Del: 'Delegations that fit', false_fail_share: 'Over-strict FAILs'};

// ── the deck's strip ──
export const STRIP = {
    live: (name, row) => hover(name, row),
    held: hover('Stopped', 'Nothing runs here until the run is started again', 'These nodes keep the state their work was in'),
    block: (n, of, users) => hover(`${n} wait on ${of}`, 'None starts until it passes:', users),
    issuer: rows => hover(`${rows.length} wait${rows.length > 1 ? '' : 's'} on the issuer`, rows),
    back: rows => hover(`${rows.length} sent back`, rows, 'Their last round failed'),
    more: rows => hover(`${rows.length} more at work`, rows),
    running: verb => `${verb} — a session running on this server`,
    carried: (top, verb) => `Carried by the session on ${top} (${verb})`,
    idle: 'In a working state; no process of this server runs it',
    // a role a line: its share of the spend drawn, its sum at the end; sessions in the label (the author: no figures run on
    // after each other with dots)
    spend: (byKind, running) => { const all = byKind.reduce((s, [, p]) => s + p.cost, 0) || 1;
        return hover('Spend by role', byKind.sort((a, b) => b[1].cost - a[1].cost).map(([k, p]) => meter(sessionsOf(k, p.calls), p.cost / all,
            p.procs && p.unpriced === p.procs ? 'not reported' : usd(p.cost))),
            running && `+ ${running} running, booked when ${running > 1 ? 'they end' : 'it ends'}`); },
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
    round: (n, v) => hover(`${v || 'No value'}\tRound ${n}`, !v && 'Not checked, or not named by its FAIL'),
    full: text => hover(text),
    directive: text => hover(text),
    model: id => hover(id),
    signed: hover('Who signed it (§10.3)'),
    // the L2 review's way out, said under its findings (a label: it is needed exactly when the review fails)
    twoWays: 'Two ways out: EDIT the criteria this names (the fix retires this verdict — run the review again after it), '
        + 'or record why a finding is wrong (<code>dispute_finding</code>).',
    probe: bhs => hover('What it checks', bhs),
};

// a role's sessions counted in words — «46 executions», «9 issuer turns» — so a count needs no line explaining it
const SESSION = {exec: 'execution', val: 'validation', issuer: 'issuer turn', consent: 'consent', plan: 'planning'};
export const sessionsOf = (kind, n) => `${n} ${SESSION[kind] || KIND_NAME[kind] || kind}${n === 1 ? '' : 's'}`;
// ── the views' own tips ── the heading carries what is looked for — the verdict and its count, the cost, the time —
// and the rows under it say where and why (the author, 2026-10-27: «ни одна цифра не должна быть в помойке»)
// what a FAIL named: its count, then one criterion a row — names carry commas of their own, and joined they read as more
const failedRows = (own, edges) => own.length || edges.length ? [`Failed (${own.length + edges.length}):`, ...own.map(c => `– ${c}`),
    ...edges.map(c => `– ${c}: ${EDGE_NOTE}`)] : [];
const passing = (m, total) => `${m.atMost ? '≤ ' : ''}${m.k} of ${total} pass`;
export const TIP = {
    // a node on the graph: what the drawing does not say — its full name, who holds it, what it waits on, its rounds
    node: (t, badge, waits, rs, criteria, failing) => card(t.name || t.description || t.id,
        [rs.length && roundsLine(rs), failing && `Failing: ${failing}`, waits && `Waits on ${waits}`,
         criteria && `${criteria} criteria`, t.assignee && `Del: ${t.assignee}`], badge),
    rounds: rs => hover(roundsLine(rs)),
    // a stretch of work on the timeline
    bar: (name, x, r, f) => card(`${cap(KIND_NAME[x.kind])}, ${dur(x.end - x.start)}${x.cost ? `\t${usd(x.cost)}` : ''}`, [
        name, `${hm(x.start)}–${x.open ? 'now' : hm(x.end)}`, x.tokens && `${tok(x.tokens)} tokens`, x.agents.length && x.agents.join(', '),
        r && `Round ${r.n}${r.verdict ? ' → ' + r.verdict : ''}`, f && failedRows(f.own, f.edges),
        x.parts > 1 && `${x.parts} processes, ${dur(x.busy)} busy: ${x.kind === 'val' ? 'the validator works in batches of probes'
            : [x.continued && `${x.continued} continued ${x.continued > 1 ? 'their' : 'its'} session`, x.handed?.length && `${x.handed.length} handed over`,
               x.parts - 1 - (x.continued || 0) - (x.handed?.length || 0) > 0 && `${x.parts - 1 - (x.continued || 0) - (x.handed?.length || 0)} retried`].filter(Boolean).join(', ')}`,
        x.priced === false && 'No cost recorded for this call']),
    // a verdict's mark, on the timeline or a progress track
    verdict: (name, signal, r, t, own, m, total, edges) => card(`${signal}${m ? `\t${passing(m, total)}` : ''}`, [
        name, `${r ? `Round ${r.n}, ` : ''}${hm(t)}`, failedRows(own, edges)]),
    cell: (name, also) => hover(name, also),
    // a node's row in spend
    cost: (name, rows, rounds, all) => card(`${rounds} delivery round${rounds === 1 ? '' : 's'}\t${all}`, [name, ...rows]),
    prefix: p => hover(p + '…', 'The start every assignee id shares, cut from the bars'),
    project: (name, id) => hover(name, id),
    where: why => hover(why),
};

// ── the models tab ──
export const MODELS = {
    sessions: hover('Sessions', 'Each with a context of its own; one resumed in its conversation counts once'),
    cost: hover('Cost split', `By kind of token: ${TOKENS.map(([, n]) => n).join(' · ')}, left to right`,
        "Priced by Anthropic's structure: per input token 1, output 5, cache read 0.1, cache written 2", 'Another provider\'s rows are not split'),
    part: (kind, cost, share, tokens, note) => hover(`${cap(kind)}\t${cost}`, meter('of the row', share), `${tokens} tokens`, note),
    id: id => hover(id),
    window: hover('The model\'s context window'),
    fill: hover('Context filled', "Each session's fullest turn against its model's window: the dark bar the median session, the light one the fullest"),
    // a session resumed in its own conversation is ONE session, however many processes the CLI ran it in (engineering, the
    // author 2026-10-27: «чем это не обычные сессии? почему отдельный счёт?») — the processes are a hover at most
    processes: n => hover(`Run in ${n} processes`, 'A session resumed in its own conversation is one session'),
    handed: n => hover(`${n} handed over`, 'Its context reached the budget: it wrote a note, and a fresh session went on from it'),
    ends: hover('Worked, gave no answer', "A cut session's tokens are its turns' own, its price unknown", 'One out of turns is taken up by the next round'),
    turns: (turned, calls) => hover(`Turns of ${turned} of ${calls} sessions`, 'The rest were recorded before turns were kept'),
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
    // each part of the context bar says itself, in the cost split's form: what was hovered and its figure, its share as a
    // filled line — the median session's peak (the dark part) or the fullest session's (the light one)
    fillOf: (which, [share, at], w, n, calls) => hover(`${which === 'median' ? 'Median session' : 'Fullest session'}${at ? `\t${at}` : ''}`,
        meter(w ? `of ${w} window` : 'of its window', share), n < calls && `${n} of ${calls} sessions recorded`),
};
