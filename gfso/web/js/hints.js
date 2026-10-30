// EVERY HINT AND POPOVER THE PAGE GIVES, written here — what is said where, and why there.
// The rule (the author, 2026-10-27): what is easy to remember once read goes to the KEY under «?»; what a reader needs
// almost every time stands as a LABEL beside the thing; a HOVER adds what the thing itself does not show and never
// repeats it; a POPOVER a click opens carries its title and caption set apart from its items. So four kinds:
//   KEY      — the «?» popover: the graph's arrows, the marks (dot, cross, ⊥), the deck's counts.
//   LABEL    — words drawn beside a thing because the reader needs them each time: the timeline's bar kinds (KIND), the coverage cells' states (CELLS). The kinds of token (TOKENS) are the key's: the Models bar
//              says each on its own segment's hover. PASS and
//              FAIL are no label: the key says them once.
//   HOVER    — `hover(head, …rows)`: one thing's detail, the first line its heading; `card()` lays it out for a view
//              that draws its own tip (the graph, the timeline, progress, spend, models).
//   POPOVER  — `pop(title, caption, items)`: the header's mode, tech reports and quality, and the key itself.
// No other module writes a `title`, a tip card or a popover row: tests/test_hints_live_in_one_place.py is red on one.
// WHAT ELSE THE PAGE SAYS, AND WHERE — so an analysis starting here misses nothing:
//   here too — the words for a run's facts, shown as content in the panel, the deck and Events and reused by the tips:
//              KIND, levelName, roundsLine, waitWords, failedWords, EDGE_NOTE.
//   vocab.js — the protocol's words: state labels, closureNote/byHand (how a node closed), PLAN_COST.
//   dialogs  — askInPage questions and notices, the text of an act being confirmed (header.js stop/start,
//              projects.js delete, acts.js, goal.js); forms' own field help (index.html goal panel, goal.js).
//   work.js  — the line under the Models table naming sessions that spent nothing (content, not a hint).
import {esc} from './dom.js';
import {dur, hm, usd, money, NOT_REPORTED, tok, pct, cap, plural, moment} from './fmt.js';
import {statesIn, label, TOKENS, nameOf} from './vocab.js';

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
    const [label, share, figure] = r.slice(1).split('\t'), p = pct(+share);
    return `<div class="tt-meter"><span>${esc(label)}</span><i><b style="width:${p}"></b></i><em>${esc(figure || p)}</em></div>`; };
export const card = (head, rows = [], badge = '') => { const [h, figure] = head.split('\t');
    return `<div class="tt-name${figure ? ' tt-split' : ''}"><span>${esc(h)}</span>${figure ? `<b>${esc(figure)}</b>` : ''}</div>${badge}`
        + lines(rows).map(row).join(''); };
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
// the kinds of token a cost went to (vocab.js TOKENS), each drawn in its own class
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
    {glyph: '<b class="kt">⊥</b>', head: 'No value', means: 'not checked yet, checked and undecided, or not kept for that round — a mark\'s hover says which; not a third value (§2.3)'},
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
    resources: hover("What this project's containers take now", 'Memory, CPU and disk by node, read from Docker'),
};

// ── the plan being authored, on the canvas while there is no graph yet (planning.js) ──
export const PLAN = {
    title: 'The plan is being authored',
    starting: 'starting',
    since: t => hover(`Since\t${t}`),
};

// ── resources: what Docker holds for this installation (`GET /api/resources`) ──
export const RES = {
    // a figure Docker gave for some of the containers only is a lower bound, and says of how many
    counted: c => c && c.split('/')[0] !== c.split('/')[1] ? hover(`Counted\t${c} containers`, 'Docker gave no figure for the rest') : '',
    busy: hover('Busy', 'A model call runs in it now'),
    full: name => hover(name),
    unread: 'Docker did not answer: what it gave last is shown, nothing where it never did',
    ofMachine: size => hover(`The machine's memory\t${size}`),
    ages: rows => hover('Read from Docker', rows.map(([k, a]) => `${k}: ${a === 'never' ? 'never' : `${a} ago`}`)),
    older: n => `${n} containers started by an older build carry no project: the counts here leave them out`,
    none: 'No container or volume of this project',
    unserved: 'No reading of Docker: this server does not serve one',
    first: 'No reading of Docker yet: the server takes its first in a few seconds',
    orphan: size => hover(`Orphans\t${size}`, "Volumes of a project this installation no longer holds"),
    volumes: vs => hover('On disk', vs.map(([role, size]) => `${size} ${role}`)),
    machine: hover('This machine', "What GFSO's containers take of it now — every project of this installation"),
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
    quality: rows => pop('Quality', 'How far the plan and its validation can be trusted, each metric with its grade (§15.8).', rows),
};

// what each quality metric measures, as its row's heading — its code (q_D…) and grade go beside it as the tag; the server
// says the rest (`means`)
export const QUALITY = {q_D: 'Splits that held', q_V: 'Verdicts that held', q_T: 'Criteria that held as issued',
    q_Dep: 'Dependencies foreseen', q_Del: 'Delegations that fit', false_fail_share: 'Over-strict FAILs'};

// ── a run's facts in words ──
// THE KINDS OF SESSION (run.js), one row a kind, in the order the deck lists them: the bar's label, a count of them, who
// ran a node in that kind, what one running now is doing
const K = (name, count, by, doing) => ({name, count, by, doing});
export const KIND = {
    exec:    K('execution',  'execution',   'executed',  'executing'),
    consent: K('consent',    'consent',     'consented', 'reading the contract'),
    val:     K('validation', 'validation',  'validated', 'validating'),
    issuer:  K('issuer',     'issuer turn', 'issued',    "the issuer's turn"),
    plan:    K('planning',   'planning',    'planned',   'planning'),
};
// a role's sessions counted in words — «46 executions», «9 issuer turns» — so a count needs no line explaining it
export const sessionsOf = (kind, n) => plural(n, KIND[kind]?.count || kind);
// the tree's levels by what they are: the goal (the root), its parts, then parts of parts, one level down each time
export const levelName = d => +d === 0 ? 'the goal' : +d === 1 ? 'its parts' : `parts, level ${d}`;
export const roundsLine = rs => !rs.length ? '' : plural(rs.length, 'round')
    + (rs.some(r => r.verdict === 'FAIL') ? `, ${rs.filter(r => r.verdict === 'FAIL').length} failed` : '');
// What a node waits on (run.js waits), for every view that says it: "Floor compiler", "its 2 parts", "the executor".
export const waitWords = (w, name) => !w ? '—' : w.deps.length ? w.deps.map(name).join(', ')
    : w.parts.length ? `its ${plural(w.parts.length, 'part')}` : w.owes ? `the ${w.owes}` : '—';
// What a FAIL named (run.js failedOf): the node's own criteria, and the bare Dep edges an older engine judged — in one
// line, or one criterion a row for a tip (names carry commas of their own, and joined they read as more)
export const EDGE_NOTE = 'a Dep edge with no check, judged by an older engine — no criterion now';
export const failedWords = ({own, edges}) =>
    [own.join(' · '), edges.length && `${edges.join(', ')}: ${EDGE_NOTE}`].filter(Boolean).join('; ') || 'no criterion named';
const failedRows = ({own, edges}) => own.length || edges.length ? [`Failed (${own.length + edges.length}):`, ...own.map(c => `– ${c}`),
    ...edges.map(c => `– ${c}: ${EDGE_NOTE}`)] : [];

// ── the deck's strip ──
// what a node at work is doing: its process's verb, else that verb's kind of session (run.js PROC_KIND), else — no process
// of this server on it — its working state
const DOING = {review_decomposition: 'reviewing the plan', join_whole: 'joining the parts',
    // the system runs the node's pinned checks once before its executor session: no model, no bar on the timeline
    observation: 'observing its place',
    EXECUTING: 'executing', REWORKING: 'reworking', VALIDATING: 'validating'};
export const doing = (verb, kind) => DOING[verb] || KIND[kind]?.doing || verb.replace(/_/g, ' ');
export const STRIP = {
    live: (name, row) => hover(name, row),
    held: hover('Stopped', 'Nothing runs here until the run is started again', 'These nodes keep the state their work was in'),
    block: (n, of, users) => hover(`${n} wait on ${of}`, 'None starts until it passes:', users),
    onIssuer: n => `${n} wait${n > 1 ? '' : 's'} on the issuer`, sentBack: n => `${n} sent back`,
    issuer: rows => hover(STRIP.onIssuer(rows.length), rows),
    back: rows => hover(STRIP.sentBack(rows.length), rows, 'Their last round failed'),
    more: rows => hover(`${rows.length} more at work`, rows),
    running: verb => `${verb} — a session running on this server`,
    carried: (top, verb) => `Carried by the session on ${top} (${verb})`,
    idle: 'In a working state; no process of this server runs it',
    // a role a line: its share of the spend drawn, its sum at the end; sessions in the label (the author: no figures run on
    // after each other with dots)
    spend: (roles, running) => hover('Spend by role', roles.map(([k, p, share]) => meter(sessionsOf(k, p.calls), share,
            money(p.cost, p.procs, p.unpriced))),
        running && `+ ${running} running, booked when ${running > 1 ? 'they end' : 'it ends'}`),
};

// ── the node's panel and reader ──
export const ISSUER_MOVES = "The executor stopped and the decision is the issuer's: raise the rework bound (Revise → max_iterations) "
    + 'if the forecast was short, change or narrow the criteria (Revise) if the plan is wrong, or close it (Cancel — it cascades '
    + "the live subtree). Silence closes it too, by this state's own timeout; it never drifts to a pass.";
// why a criterion has no value at a round (run.js `critAt`, and the panel's reading of the current verdict)
const NO_VALUE = {unchecked: 'not checked yet', unanswered: 'no verdict on this delivery', current: 'not decided at this verdict',
    undecided: 'checked, could not be decided', unrecorded: "not in this verdict's record",
    unkept: "not kept: this round's record names only what failed"};
export const PANEL = {
    refusedSaid: 'a validator reported and the report was REFUSED as ⊥ — ',
    escalated: hover('The issuer decides', ISSUER_MOVES),
    contested: hover('Read the verdict', 'Legitimate (§10.3), and nothing can check it (§15.7)'),
    deadline: (due, now) => hover(due < now ? `Overdue by ${dur(now - due)}` : `Due in ${dur(due - now)}`, moment(due)),
    earlier: hover('An earlier delivery', 'This verdict is about a delivery the current one replaced'),
    refused: note => hover('A later report was refused', note),
    // a ⊥ says WHY there is no value: the engine's reasons differ, and «not kept» is true only of an old round (critic)
    round: (n, v, why) => hover(`${v || 'No value'}\tRound ${n}`, !v && cap(NO_VALUE[why])),
    full: text => hover(text),
    directive: text => hover(text),
    model: id => hover(id),
    signed: hover('Who signed it (§10.3)'),
    // the L2 review's way out, said under its findings (a label: it is needed exactly when the review fails)
    twoWays: 'Two ways out: EDIT the criteria this names (the fix retires this verdict — run the review again after it), '
        + 'or record why a finding is wrong (<code>dispute_finding</code>).',
    probe: bhs => hover('What it checks', bhs),
};

// ── the views' own tips ── the heading carries what is looked for — the verdict and its count, the cost, the time —
// and the rows under it say where and why (the author, 2026-10-27: «ни одна цифра не должна быть в помойке»)
const passing = (m, total) => `${m.atMost ? '≤ ' : ''}${m.k}/${total} pass`;
export const TIP = {
    // a node on the graph: what the drawing does not say — its full name, who holds it, what it waits on, its rounds
    node: (t, badge, waits, rs, criteria, failing) => card(nameOf(t),
        [rs.length && roundsLine(rs), failing && `Failing: ${failing}`, waits && `Waits on ${waits}`,
         criteria && `${criteria} criteria`, t.assignee && `Del: ${t.assignee}`], badge),
    rounds: rs => hover(roundsLine(rs)),
    // a stretch of work on the timeline
    bar: (name, x, r, f) => card(`${cap(KIND[x.kind].name)}, ${dur(x.end - x.start)}${x.cost ? `\t${usd(x.cost)}` : ''}`, [
        name, `${hm(x.start)}–${x.open ? 'now' : hm(x.end)}`, x.tokens && `${tok(x.tokens)} tokens`, x.agents.length && x.agents.join(', '),
        r && `Round ${r.n}${r.verdict ? ' → ' + r.verdict : ''}`, f && failedRows(f),
        x.parts > 1 && `${x.parts} processes, ${dur(x.busy)} busy: ${x.kind === 'val' ? 'the validator works in batches of probes'
            : [x.continued && `${x.continued} continued ${x.continued > 1 ? 'their' : 'its'} session`, x.handed?.length && `${x.handed.length} handed over`,
               x.retried > 0 && `${x.retried} retried`].filter(Boolean).join(', ')}`,
        x.priced === false && 'No cost recorded for this call']),
    // a verdict's mark, on the timeline or a progress track
    verdict: (name, signal, r, t, f, m, total) => card(`${signal}${m ? `\t${passing(m, total)}` : ''}`, [
        name, `${r ? `Round ${r.n}, ` : ''}${hm(t)}`, failedRows(f)]),
    cell: (name, also) => hover(name, also),
    // a node's row in spend
    cost: (name, rows, rounds, all) => card(`${plural(rounds, 'delivery round')}\t${all}`, [name, ...rows]),
    prefix: p => hover(p + '…', 'The start every assignee id shares, cut from the bars'),
    project: (name, id) => hover(name, id),
    where: why => hover(why),
};

// ── the models tab ──
export const MODELS = {
    sessions: hover('Sessions', 'Each with a context of its own; one resumed in its conversation counts once'),
    cost: hover('Cost split', `By kind of token: ${TOKENS.map(([, n]) => n).join(' · ')}, left to right`,
        `Priced by Anthropic's structure: per ${TOKENS.map(([, n, p], i) => `${n}${i ? '' : ' token'} ${p}`).join(', ')}`, 'Another provider\'s rows are not split'),
    part: (kind, cost, share, tokens, note) => hover(`${cap(kind)}\t${cost}`, meter('of the row', share), `${tokens} tokens`, note),
    id: id => hover(id),
    window: hover('The model\'s context window'),
    fill: hover('Context filled', "Each session's fullest turn against its model's window: the dark bar the median session, the light one the fullest"),
    // a session resumed in its own conversation is ONE session, however many processes the CLI ran it in (engineering, the
    // author 2026-10-27: «чем это не обычные сессии? почему отдельный счёт?») — the processes are a hover at most
    processes: n => hover(`Run in ${n} processes`, 'A session resumed in its own conversation is one session'),
    handed: n => hover(`${n} handed over`, 'Its context reached the budget: it wrote a note, and a fresh session went on from it'),
    moved: hover('Moved to the next credential', "Attempts an account's limit refused; the call ran again on the provider's next credential",
        'Not counted as sessions above'),
    ends: hover('Worked, gave no answer', "A cut session's tokens are its turns' own, its price unknown", 'One out of turns is taken up by the next round'),
    turns: (turned, calls) => hover(`Turns recorded\t${turned}/${calls} sessions`, 'The rest were recorded before turns were kept'),
    unpriced: hover('Unpriced', 'Sessions that spent tokens with no cost recorded — a cut stream among them', 'The share is of what was priced'),
    unrecorded: hover('Not recorded', 'Kept only for sessions run on a build that records it'),
    // the cost split: what each kind of token cost, and how many; or why it cannot be split
    split: (parts, note) => hover('Where the cost went', parts.map(([k, usd_, n]) => `${k}: ${usd_} · ${n} tokens`), note),
    unsplit: 'Cache read and written kept as one sum on this build: not split',
    foreign: "Not split: its provider's prices are not known here",
    // why a split does not cover its row, each cause counted apart — none is said that the row does not have
    covers: (share, s) => [`The split covers ${share} of the row's cost — the ${s.sessions} sessions its tokens price`,
        s.resumedOut && `${plural(s.resumedOut, 'resumed round')} booked the whole conversation's cost (recorded before the fix): the round before counted twice`,
        s.out - s.resumedOut && `${plural(s.out - s.resumedOut, 'session')} not priced by ${s.out - s.resumedOut > 1 ? 'their' : 'its'} own tokens`,
        s.unweighed && `${plural(s.unweighed, 'session')} not split: recorded without the cache kept apart, without tokens, or unpriced`],
    // each part of the context bar says itself, in the cost split's form: what was hovered and its figure, its share as a
    // filled line — the median session's peak (the dark part) or the fullest session's (the light one)
    fillOf: (which, [share, at], w, n, calls) => hover(`${which === 'median' ? 'Median session' : 'Fullest session'}${at ? `\t${at}` : ''}`,
        meter(w ? `of ${w} window` : 'of its window', share), n < calls && `Recorded for ${n}/${calls} sessions`),
};
