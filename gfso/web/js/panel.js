// The node inspector: the panel, one screen — what the node is, whose move it is, how its last verdict went, where each
// criterion stands, and a chip per long text — and the reader those chips open, every long text about the node one
// facet per tab, in a slide-over left of the panel. One unit: the reader renders what the panel read and fetches
// nothing (they were two modules with seven names across the cut). Buttons carry `data-action` (dispatched in main.js);
// nothing here sends anything.
import {$, el, esc, coded, data, section, ul, rebuild, tally, due} from './dom.js';
import {PANEL, H, frame, waitWords, KIND} from './hints.js';
import {task, FOCUS} from './api.js';
import {S, hasKids, taskOf, whoOwes, asGiven, owns, signsAs, minePerformer, lift, agentName, moverOf, stateWord, inWorkOf, atTheGo, personHolds} from './state.js';
import {bucketOf, vNow, V_SYMBOL, can, look, closureNote, contested, terminal, modelName, delivered,
        byHand, mark as l2Mark, FM, fmOf, FM_NONE, FM_NO_MODE, consented, conjunct, nameOf, CARRIED, label, enteredWord} from './vocab.js';
import {roundsOf, at, waitsOf, critAt, recordOf} from './run.js';
import {glyph, mark} from './draw.js';
import {when as at_, stamp, trim, plural, spoken} from './fmt.js';
import {childrenOf} from './tree.js';
import {isHidden} from './fold.js';

const when = iso => at_(at(iso));
const link = (facet, label) => `<button class="pn-link" data-action="read" data-facet="${facet}">${label} →</button>`;

// Whose move it is (§12.13), else the Dep producers not passed yet — named beside the owner when both hold.
function waiting(d) {
    const w = waitsOf(S.graph.nodes, S.graph.edges, S.waiting, S.steps)[d.id], words = waitWords(w, id => nameOf(taskOf(id)) || id, whoOwes(taskOf(d.id), w?.owes));
    // …its own parts as a count of its own, never «its 1 part» threaded into the words
    // …and several producers as a count too, their names one a row on the line's hover: names carry commas (audit D4)
    const deps = (w?.deps || []).map(id => nameOf(taskOf(id)) || id);
    const what = deps.length > 1 ? tally(deps.length, 'nodes')
        : !w?.deps.length && w?.parts.length ? tally(w.parts.length, w.parts.length > 1 ? 'parts' : 'part') : `<b>${esc(words)}</b>`;
    return words === '—' ? ['', ''] : [what, deps.length > 1 ? `Waiting on ${deps.length}:\n${deps.map(n => `– ${n}`).join('\n')}` : ''];
}
// The engine's deferral (`split_after`: the parts it names, `waits_on` those not passed yet, `why`) — said while it waits
const splitAfter = a => { const w = a?.waits_on || [];
    return w.length ? prop('Split after', `<b>${esc(w.map(id => nameOf(taskOf(id)) || id).join(', '))}</b>`, PANEL.splitAfter(a.why)) : ''; };
// a meta line is one line, cut at its end: the whole of it on hover
const meta = (html, text) => `<div class="pn-meta"${PANEL.full(text)}>${html}</div>`;

// THE STATE AS ONE PILL: the shape is the node's own look on the graph (the key's swatch — a mark keeps its meaning across
// views), the accent only where V = fail on a node still open: the red that asks the reader to step in.
const pill = (d, v) => `<span class="pn-pill k-${bucketOf(d.state)}${v === 'fail' && !terminal(d.state) ? ' fails' : ''}">`
    + `${stateWord(d, d.audit)}</span>`;
// a property is a label and its value, one row of the grid; an absent one is no row
const prop = (k, html, attrs = '') => html ? `<div class="pn-k">${k}</div><div class="pn-v"${attrs}>${html}</div>` : '';

function head({d, rounds}) {
    const v = vNow(d, d.audit), name = nameOf(d), note = closureNote(d.closure), bad = contested(d.closure), live = !terminal(d.state);
    // the round is an ordinal, its figure the eye looks for; «in work» where the page's one reading has it, whoever holds it
    // (audit D8: a parent waiting on its parts is not; JOINT in-work rework 11-18), no round 0 (D9)
    const [wait, waitText] = waiting(d), next = consented(d.state) && (!rounds.length || rounds.at(-1).verdict),
          n = rounds.length + (next ? 1 : 0), inWork = next && inWorkOf().some(r => r.t.id === d.id);
    return `<div class="sidebar-header"><h2${PANEL.full(name)}>${esc(name)}</h2><button class="sidebar-close" data-action="close"${frame('close')}>&times;</button></div>`
        + `<div class="pn-status">${pill(d, v)}<span class="v-badge v-${v}"><span class="v-symbol">${V_SYMBOL[v]}</span>V = ${v === 'undef' ? '⊥' : v}</span>`
        + `<span class="pn-id"${PANEL.full(d.id)}>${esc(d.id)}</span></div>`
        // GOING DOWN into a part, said where the eye lands first: a link inside the panel's table went unseen (the author,
        // 2026-11-17: «я так и не понял как падать внутрь ноды»); the goal's own view is the whole graph: nothing to go to
        + (hasKids(d.id) && d.id !== FOCUS && d.parent_id ? `<button class="pn-down" data-action="view" data-id="${esc(d.id)}"${PANEL.openView}>`
            + `Open its ${childrenOf(S.tasks, d.id).filter(t => t.state !== 'ABANDONED').length} parts ↓</button>` : '')
        // …and a node chosen where the graph does not draw it (In work, a report): its part one press away, never moved to unasked
        + (isHidden(d.id) ? `<button class="pn-down" data-action="view" data-id="${esc(d.parent_id || '')}">Show it on the graph →</button>` : '')
        + `<div class="pn-grid">`
        // …the goal as the person gave it, on the root: a tap on the header's goal opens this panel, never its hover (critic)
        + prop('As given', !d.parent_id && asGiven(d) ? `<span class="pn-given">${esc(asGiven(d))}</span>` : '')
        // …and the person's own words agreeing to the plan at the go (solo / semi: the go is theirs), as the go recorded them
        + prop('At the go', !d.parent_id && atTheGo(d).user_said ? `<span class="pn-given">${esc(atTheGo(d).user_said)}</span>` : '')
        // …a node moved under another by a re-admission (`replaces`), both ways, by name (JOINT-regroup 11-19)
        + prop('Replaces', (d.replaces || []).map(x => esc(nameOf(taskOf(x)) || x)).join(', '))
        + prop('Moved to', (d.replaced_by || []).map(x => esc(nameOf(taskOf(x)) || x)).join(', '))
        + prop('Del', `<code>${esc(d.assignee ? agentName(d.assignee) : '—')}</code>`)
        + prop('Round', n ? `<b class="pn-fig">${n}</b>${inWork ? ' in work' : ''}` : '')
        + prop('Result', !d.parent_id && delivered(d) && S.graph.landed ? `<code${H.landed(S.graph.landed)}>${esc(S.graph.landed.branch || S.graph.landed.path)}</code>` : '')
        // a deadline only where it still binds (audit D18)
        + prop('Deadline', d.deadline && live ? `<code class="${at(d.deadline) < Date.now() ? 'overdue' : ''}">${when(d.deadline)}</code>` : '',
               d.deadline && live ? due(at(d.deadline)) + PANEL.deadline(at(d.deadline)) : '')
        + prop('Waiting on', wait, waitText && PANEL.full(waitText))
        // a split deferred on named parts: until their results stand, the split itself waits — then its parts show
        + splitAfter(d.split_after)
        // WHO RAN IT: the model is the node's real executor, its validator another party (author, 2026-10-25)
        + `<div class="pn-by" id="pn-by">${signedBy(S.run, d.id)}</div></div>`
        + (d.state === 'ESCALATED' ? `<div class="pn-note check-skip"${PANEL.escalated}>issuer decides: raise the bound, change the criteria, or cancel</div>` : '')
        + (note ? `<div class="pn-note ${bad ? 'check-fail' : 'check-skip'}"${bad ? PANEL.contested : ''}>`
                  + `${bad ? '⚠ ' : ''}${note}</div>` : '');
}

// THE EXECUTION VERDICT in one line — what, who, when, what failed; its evidence is the reader's.
// WHAT WAS LIFTED: the engine's three records, each saying its own thing, for no sentence holds of all three: a finding ruled
// out leaves its check running, and none says this verdict skipped anything: it may have run it. A PASS read without them
// reads as wide as one still held to all that once failed (Thm 11). Each is one command however many criteria it stood
// under, with every reason given for it; a check taken off stands in the first record and the last, and is said once.
const LIFTED = [['checks_no_longer_run', 'check a ruling took off', 'checks a ruling took off', 'it no longer runs under the criteria named; the part it belongs to still holds it', 'they no longer run under the criteria named; the parts they belong to still hold them'],
                ['findings_not_reproduced', 'finding a later validator did not reproduce', 'findings a later validator did not reproduce', 'no later validation demands it', 'no later validation demands them'],
                ['retired_after_refutation', 'finding its issuer ruled out', 'findings its issuer ruled out', 'the same finding filed again refutes nothing; its check may still run', 'the same findings filed again refute nothing; their checks may still run']];
const liftedKey = r => `${r.check?.split('/')[0] ?? ''}\n${r.command || r.id || r.criterion}\n${r.expect ?? ''}`;
const lifted = vr => { const checks = vr?.checks_no_longer_run || [], taken = new Set(checks.flatMap(r => [`${r.criterion}\n${r.command}`, r.finding]));
    return LIFTED.map(([key, one, many, it, them]) => { const by = new Map();
        for (const r of vr?.[key] || []) {
            if (key === 'retired_after_refutation' && (taken.has(`${r.criterion}\n${r.command}`) || (r.id && taken.has(r.id)))) continue;
            const k = liftedKey(r);
            if (!by.has(k)) by.set(k, {...r, criteria: new Set(), said: new Map()});
            by.get(k).criteria.add(r.criterion);
            if (!by.get(k).said.has(r.why)) by.get(k).said.set(r.why, r);
        }
        const rows = [...by.values()], n = rows.length;
        return {rows, kind: n > 1 ? many : one, means: n > 1 ? them : it}; }).filter(k => k.rows.length); };
const liftedMark = vr => { const kinds = lifted(vr), n = new Set(kinds.flatMap(k => k.rows.map(liftedKey))).size;
    return n ? `<button class="pn-link pn-lifted" data-action="read" data-facet="verdict" data-to="rd-lifted"${PANEL.lifted(kinds.map(k => `${k.rows.length} ${k.kind}: ${k.means}`))}>${tally(n, 'lifted')}</button>` : ''; };
const ruling = r => (r.printed ? `<div class="verdict-evidence">printed: ${esc(trim(String(r.printed), 300))}</div>` : '')
    + (r.why ? `<div class="verdict-evidence">${esc(spoken(r.why))}</div>` : '')
    + `<div class="verdict-evidence">${esc([r.decided_by === 'system' ? 'the system' : r.by && agentName(r.by), r.at && stamp(r.at)].filter(Boolean).join(', '))}</div>`;
const liftedFull = ({d, vr}) => { const kinds = lifted(vr);
    return kinds.length ? `<div id="rd-lifted">` + section('Lifted', kinds.map(k => `<div class="verdict-evidence">${k.kind}: ${k.means}</div>`
        + ul('item-list', k.rows.map(r => `<li><div class="verdict-body"><strong>${esc([...r.criteria].join(', '))}</strong>`
            + (r.node && r.node !== d.id ? ` <span class="pn-who">in ${esc(nameOf(taskOf(r.node)) || r.node)}</span>` : '')
            + (r.check?.includes('/') ? ` <span class="pn-who">a check of ${esc(nameOf(taskOf(r.check.split('/')[0])) || r.check.split('/')[0])}</span>` : '')
            + (r.command ? `<div class="verdict-evidence"><code>${esc(r.command)}</code></div>` : '')
            + (r.expect ? `<div class="verdict-evidence">expected: ${esc(trim(String(r.expect), 300))}</div>` : '')
            + [...r.said.values()].map(ruling).join('') + `</div></li>`))).join('')) + `</div>` : ''; };

function verdict({vr}) {
    if (vr?.verdict) return `<div class="pn-verdict ${vr.verdict === 'PASS' ? 'check-pass' : 'check-fail'}">${glyph(vr.verdict)}<b>${vr.verdict}</b>`
        + `<span class="pn-who">${signer(vr)}</span>${vr.ts ? `<span class="pn-when">${when(vr.ts)}</span>` : ''}`
        + liftedMark(vr)
        + `${vr.current === false ? `<span class="check-fail"${PANEL.earlier}>earlier</span>` : ''}`
        // a refused report LATER than this verdict asks for a look; an earlier one is history this verdict answered
        + `${vr.refused_report && at(vr.refused_report.ts) > at(vr.ts) ? `<span class="check-fail"${PANEL.refused(vr.refused_report.note)}>a later report refused</span>` : ''}${link('verdict', 'evidence')}</div>`;
    // what failed is not repeated here: it is the ✗ rows of the criteria list just below
    // ⊥ IS NOT "NOT VALIDATED": a validator reported and the engine refused it — the issuer owes a decision.
    return vr?.refused_report ? `<div class="pn-verdict check-fail"><span class="pn-who">${PANEL.refusedSaid}`
        + `${esc(spoken(vr.refused_report.note || 'the issuer decides'))}</span>${link('verdict', 'why')}</div>` : '';
}

// One mark per round (run.js): this criterion named in a FAIL → the cross; a PASS (every criterion passing) → an ink
// dot; a FAIL that did not name it, a delivery still unanswered, or a criterion the current verdict left undecided →
// ⊥: the log of past rounds keeps only what a FAIL named, so an unnamed one is ⊥, not pass — drawn as the current line
// beside it draws it; a hollow ring said «at work» on the graph (critic). The last 12.
const strip = (rounds, name, now) => { const rs = rounds.slice(-12), open = x => `<path class="mk-none" d="M${x - 2.5},3h5M${x},3v-6"/>`;
    // a history of one round says what the mark beside the name says: drawn, it was a lone dot beside a dot (the author)
    // each mark says its own round on hover (a hover on the whole strip said the same line over every mark — critic)
    // the round's value by the run's one rule (`critAt`); the last round reads the current verdict beside it, which may
    // leave the criterion undecided or keep as passing what an old FAIL's record did not name
    const one = (r, i) => { const last = i === rs.length - 1, [v, why] = critAt(r, name);
        return r.verdict && last && now && now !== 'pass' && now !== 'fail' ? [null, 'current']
            : why === 'unkept' && last && now === 'pass' ? ['PASS'] : v === '⊥' ? [null, last && why === 'unanswered' ? 'unchecked' : why] : [v.toUpperCase()]; };
    return rs.length < 2 ? '' : `<span class="cr-strip">` + rs.map((r, i) => { const [v, why] = one(r, i);
        return `<svg width="8" height="10" viewBox="${i * 8} -5 8 10"${PANEL.round(r.n, v, why, r.per?.find(x => x.criterion === name)?.evidence)}>${v ? mark(v, i * 8 + 4, 0, 2.5) : open(i * 8 + 4)}</svg>`; }).join('') + '</span>'; };

// A criterion is one line at the current verdict; unfolded (one at a time) it reads what it asks, what the
// verdict found, and its pinned check.
function criteria({d, vr, rounds}) {
    // a Dep edge's bare declaration is the edge the head's «waits on» already names, not a criterion with a verdict
    const cs = d.criteria.filter(conjunct);
    if (!cs.length) return '';
    const pc = perCrit(vr), k = cs.filter(c => pc[c.name]?.verdict === 'pass').length;
    // ONE SCREEN at any count: what is not passing first, and past SHOWN the rest folded behind one line — 31 criteria
    // made a 1168 px panel whose prose chips sat below the fold (critic, root.integrate)
    const rank = c => ({fail: 0, undefined: 1, pass: 2})[pc[c.name]?.verdict] ?? 1, sorted = [...cs].sort((a, b) => rank(a) - rank(b));
    const row = c => {
        const v = pc[c.name]?.verdict, ev = pc[c.name]?.evidence, key = `${d.id}|${c.name}`;
        return `<details class="cr-row" name="crit" data-key="${esc(key)}"><summary>`
            + `<span class="cr-g">${v === 'pass' ? glyph('PASS', 3.5) : v === 'fail' ? glyph('FAIL', 3.5) : '⊥'}</span>`
            + `<span class="cr-name"${PANEL.full(c.name)}>${esc(c.name)}</span>${strip(rounds, c.name, vr?.current !== false && v)}</summary>`
            + `<div class="cr-more"><div class="crit-desc">${esc(c.description)}</div>`
            + (ev ? `<div class="verdict-evidence">${esc(ev)}</div>${link('verdict', 'full in reader')}` : '')
            + pinned(c, key + '|check') + `</div></details>`;
    };
    const SHOWN = 8, head_ = sorted.slice(0, SHOWN).map(row).join(''), rest = sorted.slice(SHOWN);
    return section(`Criteria${vr?.verdict ? tally(`${k}/${cs.length}`, 'pass') : ''}`, head_
        + (rest.length ? `<details class="cr-rest"><summary>${rest.length} more${rest.every(c => pc[c.name]?.verdict === 'pass') ? ', all passing' : ''}</summary>${rest.map(row).join('')}</details>` : ''));
}

const facets = ctx => `<div class="pn-facets">${FACETS.map(f => chip(f, ctx)).join('')}</div>`;

const btn = (cls, label, action, attrs) => `<button class="btn btn-sm ${cls}"${data({action, ...attrs})}>${label}</button>`;
const sig = (id, a) => btn(a.cls, a.label, 'signal', {id, sig: a.s, prompt: a.prompt, fail: a.needsCriteria && 1});

// Every signal the engine admits here (/actions) and the moves that are no signal (vocab.js) — the plan-repair Edit
// wherever a re-ASSIGN is legal, not on OFFERED alone (a tester was trapped on an EXECUTING root, wave 27). The forms
// these open go in #inline-form, never a native dialog.
// UNDER A MODE the panel says no more than the engine does: on a node next_steps names as this person's it offers the
// signals /actions admits whose `performed_by` is this person (or anyone) — the door's own mode lock, read, not copied
// (a table of the page's own hid moves the directives name and offered work the mode dispatches, two critics). The
// step's directive is shown beside them, but not on an AUTO project, whose prose may still name moves the door
// refuses (engineering, 9853468). Work the mode dispatches is read off its `perform`: the executor's steps but consent
// are the clean session's, whatever `performed_by` names (outside AUTO it names the holder).
const DISPATCHED = new Set(['execute', 'rework', 'deliver']);
function actions({d, acts, vr}) {
    const s = d.state, id = {id: d.id}, kids = hasKids(d.id), m = S.graph.mode;
    // …a browser that signs as no one is offered nothing — each move would be refused — and is told how to sign in
    if (!signsAs().length) return foot(`<div class="pn-note check-skip">${coded(lift())}</div>`, '');
    // WHO SIGNS EACH MOVE is the engine's to say — who performs a signal (`performed_by`, the mode's lock read, not copied), who
    // signs a structural move (`moves`: a split its holder's, an edit its issuer's, §10.1), who a check is signed as (`checks`)
    // — and the page offers a move only where that name is one it signs as (whoami), under that name, said: the server signs
    // it so (signin.py), the page sends none. A performer left unnamed is anyone's: the session's own name signs it.
    const by = acts?.performed_by || {}, mv = acts?.moves || {}, mine = minePerformer, as = n => n || S.me?.name || '';
    const open = (acts?.actions || []).filter(sg => mine(by[sg])).map(sg => [sg, look(sg, s)]).filter(([, a]) => a)
        .map(([sg, a]) => [as(by[sg]), sig(d.id, a.s === 'DELIVER' && s === 'REWORKING' ? {...a, label: 'Re-deliver'} : a)]);
    const may = (...vs) => as(vs.map(v => mv[v]).find(n => n && owns(n)) ?? null);
    const ownsAny = (...vs) => vs.some(v => owns(mv[v]));
    // a check is anyone's (§10.2), signed as the name the door gives it (`checks`: a verdict the issuer's, a review the split's
    // holder's) where that name is yours, else as the session itself
    const checker = v => owns(acts?.checks?.[v]) ? acts.checks[v] : as(null);
    const moves = m?.mode === 'auto' ? [] : [
        can(s, 'V') && [checker('record_verdict'), btn('btn-muted', 'Record verdict', 'verdict', {...id, as: checker('record_verdict')})],
        // ONE AI verb, dispatched by the node's state: undecomposed → author; decomposed → one refine round.
        // AI review is the standalone L2 door — hand-authored graphs never pass decompose's semantic pass.
        ...can(s, 'D') ? [ownsAny('decompose') && [may('decompose'), btn('btn-purple', 'Decompose', 'decompose', id)],
                          ownsAny('auto_decompose') && [may('auto_decompose'), btn('btn-purple', kids ? 'AI refine' : 'AI decompose', 'ai-decompose', id)],
                          kids && [checker('review_decomposition'), btn('btn-purple', 'AI review', 'ai-review', id)]] : [],
        // the split's own register (edit_accepted_risks) is its holder's, not an Edit
        // …its register part signed apart (`edit_accepted_risks`: the split's holder's where a person holds the node), told to the form
        can(s, 'E') && ownsAny('revise', 'edit_criteria', 'reassign') && [may('revise', 'edit_criteria', 'reassign'),
            btn('btn-muted', 'Edit', 'edit', {...id, risks: owns(mv.edit_accepted_risks) ? mv.edit_accepted_risks : ''})]].filter(Boolean);
    // …and why a move is not offered, each in the engine's own sentence (`withheld`, and `why_none` when nothing is):
    // a missing button said nothing (a probe: a Reject Challenge withheld for a Level-2 verdict the page never named);
    // `gate` also carries asides written for an agent's verbs, which a person's buttons already perform (critic)
    const why = [...Object.values(acts?.withheld || {}), ...(!open.length && acts?.why_none ? [acts.why_none] : [])];
    const gate = why.map(w => `<div class="pn-note check-skip">${esc(spoken(w))}</div>`).join('');
    if (!m?.mode) { const btns = signed([...open, ...moves]); return btns || gate ? foot(gate, btns) : ''; }
    const steps = (S.mySteps?.get(d.id) || []).filter(x => x.mine);
    if (!steps.length) return '';
    // …a step's directive is written for whoever asked — the session's own name — so it is said only on that name's steps:
    // under another of the person's names it read «NOT YOURS» beside the move offered (critic 3)
    const told = x => m.mode !== 'auto' && (!x.performed_by || x.performed_by === S.me?.name) ? spoken(x.directive || '') : '';
    // …a verdict the person signs over the validator's observation is said to the person, not in the words the engine
    // gives their agent («show them … signal root PASS|FAIL user_said=…» stood on their own page): what the validator
    // found is the Verdict above, the signature theirs
    // …only where the step IS that record on this delivery (frontier.py's on-the-record branch): a whole failing through
    // its part, or a record of an earlier delivery, keeps the engine's own sentence (critic: «PASS … sign it below» over
    // a root whose part had failed, Pass not even offered)
    const toThePerson = x => x.action === 'validate' && /^SIGN THE VERDICT .*verdict for THIS delivery is already on the record/.test(x.directive || '')
        && vr?.verdict && vr.current !== false
        ? PANEL.signYours(vr.verdict, (vr.outside || []).length) : '';
    const said = steps.map(x => toThePerson(x) ? `<div class="pn-step">${esc(toThePerson(x))}</div>`
        : `<div class="pn-step"${told(x) ? PANEL.directive(told(x)) : ''}>${esc(x.action)}`
        + `${told(x) ? ` — ${esc(trim(told(x), 220))}` : ''}</div>`).join('');
    // outside AUTO the engine's performed_by names the holder even for work its hands do, so the mode's perform still
    // decides that work is the clean session's (critic: Deliver offered beside «PERFORMED BY … WAIT»)
    const waits = m.perform !== 'in_chat' && steps.every(x => DISPATCHED.has(x.action));
    return foot(said, waits ? '' : signed([...open, ...moves]));
}
const foot = (note, btns) => `<div class="pn-foot">${note}${btns ? `<div class="actions">${btns}</div>` : ''}<div id="inline-form"></div></div>`;
// the buttons by the name each is signed as, that name said once before its own — read-only: the credential signs, never a box
const signed = pairs => [...pairs.reduce((g, [n, b]) => g.set(n, [...(g.get(n) || []), b]), new Map())]
    .map(([n, bs]) => `<span class="act-as"${PANEL.signedAs(n)}>as <b>${esc(agentName(n))}</b></span>${bs.join('')}`).join('');

// Who ran a node, in one line for its panel: by role, each model with its sessions on it.
// A node whose own sessions are booked nowhere — run inside a scope's session booked to its top, or done by the
// user's agent or a person, whose model the system is not told — is signed by who delivered it, and says so.
const deliveredBy = (run, id) => { const by = (run?.rounds[id] || []).map(r => r.by).filter(Boolean).at(-1);
    // …where the person's agent performs what the person holds (in_chat), their chat IS where it ran: «no session» read as a lack
    const sc = nodeOf(id).scope, chat = sc ? (S.graph.scopes || {})[sc]?.perform === 'in_chat' : S.graph.mode?.perform === 'in_chat' && personHolds(taskOf(id));
    return by && !run.work.byNode[id]?.exec ? [prop('Executed by', `<b>${esc(agentName(by))}</b> <span class="wk-none">${chat
        ? 'in their own chat — its model is not reported here' : 'no session booked to this node — its model is not reported here'}</span>`)] : []; };
// who ran it, one grid row per role: «Executed by · haiku 5.5 ×12»
const ROLE_ORDER = ['plan', 'consent', 'exec', 'issuer', 'val'];   // executed, issued, validated — one order on every node
const signedBy = (run, id) => [
    ...deliveredBy(run, id),
    ...Object.entries(run?.work.byNode[id] || {}).sort(([a], [b]) => ROLE_ORDER.indexOf(a) - ROLE_ORDER.indexOf(b)).map(([kind, ms]) =>
        prop(KIND[kind]?.by.replace(/^./, c => c.toUpperCase()) + ' by',
             Object.entries(ms).map(([m, n]) => `<b${PANEL.model(m)}>${esc(modelName(m))}</b>${n > 1 ? `<sup>×${n}</sup>` : ''}`).join(', '))),
    ...Object.entries(run?.work.unansweredOn[id] || {}).map(([k, n]) => prop('Unanswered', `<span class="wk-none">${tally(n, `${KIND[k].name} ${n > 1 ? 'sessions' : 'session'}`)}</span>`)),
].join('');

// why a node stands waiting on its issuer, while it does: a dispute's words, a block's
const WHY = {CHALLENGED: ['CHALLENGE', 'Challenged'], BLOCKED: ['BLOCK', 'Blocked']};
const dispute = ({d}) => { const w = WHY[d.state], c = w && [...(d.audit || [])].reverse().find(a => a.signal === w[0] && !a.rejected);
    return c ? `<div class="pn-verdict check-fail"><b>${w[1]}</b><span class="pn-who">${esc(trim(spoken(c.reason || ''), 200))}</span>${link('history', 'whole')}</div>` : ''; };
// WHO CHECKS A PART — the validator or its issuer themself, the signature the issuer's either way (§10.2, `set_checker`; the
// author, 11-20: «решает кто будет валидировать; если сам то сам и ставит подпись»). The engine says who checks now
// (`checker`, on the graph read only where it is the validator) and offers the choice only where one exists — a part the
// person's chat holds below the root; a seam owes the validator, no box there (critic)
const checkerOf = id => (S.graph.nodes || []).find(n => n.id === id)?.checker || 'self';   // validator · independent · self
function checkSetting({d, acts}) {
    if (!d.parent_id) return '';
    const who = checkerOf(d.id), on = who === 'validator', may = owns(acts?.moves?.set_checker);
    return may ? `<div class="pn-note"><label class="act-check"><input type="checkbox"${data({action: 'set-checker', id: d.id, on: on ? '0' : '1'})}${on ? ' checked' : ''}> ${esc(PANEL.checkAlways)}</label></div>`
        // …a seam no validator observes needs a verdict not its executor's (engineering 6bb0819): said too
        : on || who === 'independent' ? `<div class="pn-note check-skip">${esc(on ? PANEL.checkedAlways : PANEL.checkedApart)}</div>` : '';
}
// A SEAM HE ISSUES, HELD IN ITS HOLDER'S CHAT (§10.4: autonomy per task and role): no button sets it — the holder's own
// connection taking its name records that it works in a chat, and each seam he issues to it is a TOP, his word standing
// there. The page says so to anyone: who holds it and that its verdict is the person's
const nodeOf = id => (S.graph.nodes || []).find(n => n.id === id) || {};
function modeScope({d}) {
    const n = nodeOf(d.id);
    return n.mode_top === d.id && n.scope ? `<div class="pn-note check-skip">${esc(PANEL.scopeTop(agentName(d.assignee || ''), nameOf(taskOf(n.scope)) || n.scope))}</div>` : '';
}
const PARTS = [head, verdict, dispute, facets, criteria, checkSetting, modeScope, actions];   // the prose chips above the list, always on screen

let panelRead = 0, opening = Promise.resolve();
export const panelOpened = () => opening;
export const selectTask = id => opening = readPanel(id);
async function readPanel(id) {
    const mine = ++panelRead;
    try {
        const soft = p => p.catch(() => null);
        const [d, vr, cr, acts] = await Promise.all([task(id), soft(task(id, '/verdict')), soft(task(id, '/critique')),
            soft(task(id, '/actions?role=*'))]);     // every party's moves with who makes each: the page keeps those it signs
        if (mine !== panelRead) return;                // a read that came late says no more than the later one
        // a round's per-criterion record is the node's verdict history, which the deck's run has joined to the log
        // …else, for the last verdict, the node's current record when it is that verdict's — even after a rework made it
        // not current — as Progress reads it (critic: the strip said «not kept» beside the current line drawing it)
        const kept = S.run?.rounds[d.id] || [], all = roundsOf(d.audit, d.id), lastV = all.findLast(r => r.verdict);
        const rounds = all.map(r => r.per || !r.verdict ? r : {...r, per: recordOf(kept.find(k => k.at === r.at && k.verdict === r.verdict)?.per,
            r === lastV, vr, r.verdict)});
        const ctx = {d, vr, cr, acts, rounds}, sb = $('sidebar');
        // An open form outlives the re-read — any transition in the project re-reads the panel, and the text and ticks
        // being entered were wiped mid-entry on a live run — while nothing has happened to THIS node: a form opened on
        // one delivery must not be sent against the next (critic: a verdict form kept over VALIDATING → REWORKING).
        const last = JSON.stringify([d.state, d.audit.at(-1) || null]);
        // …and while its signal is still admitted to the one acting (a role or a mode changes that with no new record)
        const form = sb.dataset.key === d.id && sb.dataset.last === last && $('inline-form')?.firstChild ? $('inline-form') : null;
        const sig = form?.querySelector('[data-action="send-signal"]')?.dataset.sig;
        // …and the field being typed in keeps its focus and caret: a re-read moved it to the page and lost the keys (critic 6)
        const typing = form?.contains(document.activeElement) && document.activeElement, at = typing && [typing.selectionStart, typing.selectionEnd];
        sb.classList.remove('hidden');
        rebuild(sb, d.id, PARTS.map(f => f(ctx)).join(''));
        sb.dataset.last = last; sb.dataset.per = rounds.filter(r => r.per).length;
        if (form && (!sig || acts?.actions?.includes(sig))) {
            $('inline-form')?.replaceWith(form);
            if (typing) { typing.focus(); if (at[0] != null) typing.setSelectionRange(...at); }
        }
        showReader(ctx);
    } catch (e) { console.error('selectTask:', e); }
}

// …and again once the run is read: the panel can open before the deck has built it — its signer, and the per-criterion
// records of its rounds, which only the run joins from the verdict history (critic: a ?task= link drew ⊥ for a kept pass)
export const resign = id => { const by = $('pn-by'); if (by) by.innerHTML = signedBy(S.run, id);
    if ($('sidebar').dataset.key === id && +$('sidebar').dataset.per < (S.run?.rounds[id] || []).filter(r => r.per).length) selectTask(id); };

export function closeSidebar() {
    panelRead++;                                       // a read still out does not open it again when it lands (critic)
    closeReader();
    $('sidebar').classList.add('hidden');
}

// ── the reader ──
let cur = null, tab = null;
// …a list carried by a signal one item a row, never a JSON dump (audit D15)
const txt = x => Array.isArray(x) && x.every(i => typeof i === 'string') ? `<ul class="rd-items">${x.map(i => `<li>${esc(i)}</li>`).join('')}</ul>`
    : esc(typeof x === 'string' ? x : JSON.stringify(x, null, 1));


// Who produced a verdict: a hand or an instrument — nothing closes on impression (HTTP door, 2026-09-02).
// …and a node's own executor's report is no validation (§10.3): said as the record says it (critic: «validated by» stood
// over a SELF-REPORTED PASS)
export const signer = vr => vr.by_hand ? byHand(esc(vr.validator || ''))
    : vr.provenance === 'self' ? `self-reported by ${esc(vr.validator ? agentName(vr.validator) : 'its executor')}, not an independent check`
    : `validated by ${esc(vr.validator ? agentName(vr.validator) : 'an instrument')}${vr.validator_model ? `, ${esc(modelName(vr.validator_model))}` : ''}`;
export const perCrit = vr => Object.fromEntries((vr?.per_criterion || []).map(c => [c.criterion, c]));

// A criterion's pinned check is what makes it a contract (A1, §2) — folded, the longest part of it.
export const pinned = (c, key) => (c.check || []).length
    ? `<details class="crit-check" data-key="${esc(key)}"><summary>check (${plural(c.check.length, 'probe')})</summary><pre>`
      + c.check.map(p => [p.behaviour && `# ${p.behaviour}`, `$ ${p.command}`, `→ ${p.expect}`,
                          Object.keys(p.inputs || {}).length && `inputs: ${Object.keys(p.inputs).join(', ')}`]
                         .filter(Boolean).map(esc).join('\n')).join('\n\n') + `</pre></details>`
    : `<div class="check-fail">no pinned check — nothing decides this criterion but a probe improvised at validation time</div>`;

// THE EXECUTION VERDICT, criterion by criterion. ONE `<li>`, TWO FLEX CHILDREN: the icon, and one body
// block — siblings in a flex row tore the result apart (author, 2026-09-12). A command run for several
// behaviours is shown once, the behaviours as its tooltip; evidence is shown whole.
// ⊥ IS NOT "NOT VALIDATED": a validator reported and the engine refused it — the issuer owes a decision. A refused
// report stands beside a verdict too (a later report refused), and is shown there as well (critic: hidden beside a PASS).
const refusedOf = rr => !rr ? '' : `<div class="check-fail">${PANEL.refusedSaid}${esc(spoken(rr.note || 'the issuer decides'))}</div>`
    + (rr.why_it_is_not_a_verdict ? `<div class="verdict-evidence">${esc(spoken(rr.why_it_is_not_a_verdict))}</div>` : '');
function verdictFull({vr}) {
    if (vr?.verdict) return section('Verdict on the work',
        `<div class="${vr.verdict === 'PASS' ? 'check-pass' : 'check-fail'}">${vr.verdict} — ${signer(vr)}`
        + `${vr.current === false ? ' <span class="check-fail">(validated an EARLIER delivery)</span>' : ''}</div>`
        + (vr.independence ? `<div class="verdict-evidence"${PANEL.signed}>${esc(spoken(vr.independence))}</div>` : '')
        + refusedOf(vr.refused_report)
        // what failed is the ✗ rows below; said here only where no row per criterion was kept (audit DQ3)
        + ((vr.failed_criteria || []).length && !(vr.per_criterion || []).length ? `<div class="check-fail">failed: ${esc(vr.failed_criteria.join(', '))}</div>` : '')
        + ((vr.undecidable || []).length ? `<div class="check-skip">undecidable (never observed): ${esc(vr.undecidable.join(', '))}</div>` : '')
        + ul('item-list', (vr.per_criterion || []).map(c => {
            const byCmd = new Map();
            (c.probe || []).forEach(pr => {
                const cmd = String(pr.command || '').trim();
                if (cmd) byCmd.set(cmd, [...(byCmd.get(cmd) || []), ...(pr.behaviour ? [String(pr.behaviour)] : [])]);
            });
            const [cls, icon] = c.verdict === 'pass' ? ['check-pass', '✓'] : c.verdict === 'fail' ? ['check-fail', '✗'] : ['check-skip', '⊥'];
            return `<li class="${cls}"><span class="check-icon">${icon}</span><div class="verdict-body"><strong>${esc(c.criterion)}</strong>`
                + (c.evidence ? `<div class="verdict-evidence">${esc(c.evidence)}</div>` : '')
                // …the person's own words the result answers wrongly, quoted (`answers_the_persons_words`)
                + (c.quote ? `<div class="verdict-evidence pn-given">«${esc(c.quote)}»</div>` : '')
                + (c.reused_from_refused ? `<div class="check-skip">reused from a refused report (${esc(c.reused_from_refused.validator || '')}${c.reused_from_refused.ts ? ', ' + esc(stamp(c.reused_from_refused.ts)) : ''})</div>` : '')
                + ((c.divergences || []).length ? `<div class="check-fail">divergences: ${esc(c.divergences.map(x => typeof x === 'string' ? x : JSON.stringify(x)).join('; '))}</div>` : '')
                + (byCmd.size ? `<div class="verdict-probes">${[...byCmd].map(([cmd, bhs]) =>
                    `<code${PANEL.probe(bhs)}>${esc(cmd)}</code>`).join('')}</div>` : '')
                + `</div></li>`;
        }))
        // …and what the validator saw beyond the criteria, none of it a failed criterion: the person weighs it before
        // signing (engineering 2ca7f37: a client signed over «x.tar.gz counted as .gz» unseen)
        + ((vr.outside || []).length ? `<div class="verdict-evidence"><strong>${esc(PANEL.outside)}</strong></div>` + ul('item-list',
            vr.outside.map(o => `<li class="check-skip"><div class="verdict-body">${esc(o.what || '')}`
                + (o.evidence ? `<div class="verdict-evidence">${esc(o.evidence)}</div>` : '') + '</div></li>')) : ''));
    return vr?.refused_report ? section('Verdict on the work', refusedOf(vr.refused_report)) : '';
}

// Checks grouped by failure mode (§8). A SKIPPED check says nothing, and is not drawn; TRUE OVER NOTHING
// IS NOT THE SAME GREEN — `∅` marks a check that held over an empty set (2026-09-06).
const ran = d => d.checks.filter(c => !c.skipped);
const met = c => (c.verdict || (c.passed ? 'met' : 'unmet')).startsWith('met');
function checks({d}) {
    const byFm = {};
    ran(d).forEach(c => (byFm[fmOf(c.check_name)] ??= []).push(c));
    return section('Checks by failure mode', Object.keys(byFm).sort().map(fm =>
        `<div class="fm-group"><div class="fm-label">${fm === FM_NONE || fm === FM_NO_MODE ? fm
            : `<span class="fm-code">${fm}</span>${FM.label[fm] || ''}`}</div>`
        + ul('item-list', byFm[fm].map(c => {
            const [cls, icon] = !met(c) ? ['check-fail', '✗'] : c.verdict === 'met_vacuously' ? ['check-pass', '∅'] : ['check-pass', '✓'];
            return `<li class="${cls}"><span class="check-icon">${icon}</span>${esc(c.check_name.split(':')[1] || c.check_name)}`
                + `${c.details ? ' — ' + esc(c.details) : ''}</li>`;
        })) + `</div>`).join(''));
}

// L2 review — the STORED checker verdict + freshness. Gaps live in THREE places (uncarried criteria,
// conflicts, the node's OWN undecided obligations); counting two rendered "0 gap(s) ✓" beside "9 findings
// OPEN" (wave 27). And the verdict is the engine's `semantic_covered`, not a count of this page's.
const l2 = cr => {
    const rev = cr?.critique;
    if (!rev || rev.criteria_verdicts === undefined) return null;
    const cv = rev.criteria_verdicts || [], conflicts = rev.conflicts || [], undecided = rev.undecided_obligations || [];
    const gaps = cv.filter(v => v.verdict !== 'sufficient').length + conflicts.length + undecided.length;
    const [short, status] = !rev.gate_passed ? ['gate failed', 'gate failed (L0/L1)']
        : rev.semantic_covered === true ? ['no gaps', 'no gaps (advisory)']
        : rev.semantic_covered === false ? ['not covered', `NOT COVERED — ${gaps || 'unlisted'} finding(s) open; the children may not start`]
        : ['no verdict', 'no verdict'];
    return {rev, cv, conflicts, undecided, status, short: cr.verified ? short : 'stale', bad: rev.semantic_covered === false || !rev.gate_passed};
};
function review({cr}) {
    const {rev, cv, conflicts, undecided, status, bad} = l2(cr);
    return section(`L2 review${cr.verified ? '' : ' — STALE (decomposition changed)'}`, ul('item-list', [
        `<li class="${bad ? 'check-fail' : ''}">${status}</li>`,
        (rev.model || rev.ts) && `<li class="faint">${rev.model ? `reviewed by ${esc(modelName(rev.model))}` : 'reviewed'}${rev.ts ? `, ${when(rev.ts)}` : ''}</li>`,
        ...cv.map(v => `<li>${l2Mark(v.verdict)} ${esc(v.criterion)} — ${esc(v.why || '')}</li>`),
        ...conflicts.map(c => `<li>⚡ [${esc((c.between || []).join(', '))}] ${esc(c.why || '')}</li>`),
        ...undecided.map(u => `<li class="check-fail">✗ no pinned check its validation runs decides: ${esc(u.obligation || u.gap || '')}`
            + `${u.admits ? ` <div class="verdict-evidence">${esc(u.admits)}</div>` : ''}</li>`),
        bad ? `<li class="faint">${PANEL.twoWays}</li>` : '']));
}

// The parts' states are a FORECAST of the parent: Theorem 1 holds under a correct decomposition only, and
// the parent's V is its own contact over the result (§12.8) — never AND-ed into it here.
// a part's V read off the same log as its own panel's (the run's), else what its state carries
const kids = d => d.children || [], vPart = c => vNow(c, S.run?.audit.filter(a => a.task_id === c.id));
const passing = d => kids(d).filter(c => vPart(c) === 'pass').length;
const composition = ({d}) => section('Composition — the parts', `<div class="composition-panel">`
    + tally(`${passing(d)}/${kids(d).length}`, 'parts pass') + `<div class="composition-formula">`
    + `A forecast: V(parent) = AND(parts) holds under a correct decomposition, and the parent's V is its own `
    + `verdict over the result</div>`
    + kids(d).map(c => { const v = vPart(c);
        return `<div class="composition-row v-${v}"><span class="v-sym">${V_SYMBOL[v]}</span>`
            + `<span class="child-name" data-action="select" data-id="${esc(c.id)}">${esc(nameOf(c))}</span></div>`; }).join('')
    + `</div>`);

// The node's audit slice, newest first; what a signal carried is folded under its line.
const history = ({d}) => section('History — newest first', ul('item-list audit-list', [...d.audit].reverse().map(a => {
    const who = moverOf(a);
    const line = `${when(a.timestamp)} ${a.signal} ${a.old_state ? label(a.old_state) : ''}→${a.new_state ? enteredWord(a) : 'rej'}${who.word && who.word !== 'clock' ? ' by ' + esc(who.word) : ''}${who.via ? ` ${who.via}` : ''}${who.as ? ` (signed as ${esc(who.as)})` : ''}`;
    const more = CARRIED.filter(([k]) => a[k] && a[k].length !== 0).map(([k, l]) => `<div class="rd-field"><b>${l}</b>${txt(a[k])}</div>`).join('');
    return `<li class="${a.rejected ? 'check-fail' : ''}">${more ? `<details data-key="${esc(`h|${d.id}|${a.timestamp}|${a.signal}`)}">`
        + `<summary>${line}</summary>${more}</details>` : line}</li>`;
})));

const list = (k, title) => ({d}) => section(title, ul('facet-list', (d[k] || []).map(x => `<li>${esc(x)}</li>`)));

// Facet: what the tab is called, what its chip counts (falsy hides the chip), what it shows.
export const FACETS = [
    {id: 'desc', label: 'Description', n: ({d}) => !!d.description,
     body: ({d}) => section('Description', `<div class="rd-text">${esc(d.description)}</div>`)},
    {id: 'verdict', label: 'Verdict', n: ({vr}) => vr?.verdict || (vr?.refused_report && '⊥'), body: x => verdictFull(x) + liftedFull(x)},
    {id: 'scope', label: 'Scope', n: ({d}) => (d.scope || []).length, body: list('scope', 'Scope — boundary exclusions')},
    {id: 'risks', label: 'AcceptedRisk', n: ({d}) => (d.accepted_risks || []).length, body: list('accepted_risks', 'AcceptedRisk')},
    {id: 'components', label: 'Risk components', n: ({d}) => (d.risk_components || []).length, body: list('risk_components', 'Risk components')},
    {id: 'parts', label: 'Parts', n: ({d}) => kids(d).length && `${passing(d)}/${kids(d).length} pass`, body: composition},
    // all met reads as met, not «0/6 unmet» (audit D17)
    {id: 'checks', label: 'Checks', n: ({d}) => { const n = ran(d).length, un = ran(d).filter(c => !met(c)).length;
        return n && (un ? `${un}/${n} unmet` : `${n} met`); }, body: checks},
    {id: 'l2', label: 'L2 review', n: ({cr}) => l2(cr)?.short, body: review},
    {id: 'recs', label: 'AI recommendations', n: ({d}) => d.recommendation?.suggestions?.length,
     body: ({d}) => section('AI Recommendations', `<div class="recs">${ul('', d.recommendation.suggestions.map(s =>
         `<li>${esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</li>`))}</div>`)},
    {id: 'history', label: 'History', n: ({d}) => d.audit.length, body: history},
];
export const chip = (f, ctx, on = false) => { const n = f.n(ctx);
    return !n ? '' : `<button class="fchip${on ? ' on' : ''}" data-action="read" data-facet="${f.id}">${f.label}${n === true ? '' : ` <i>${esc(n).replace(/(\d+(?:\/\d+)?)/, '<b>$1</b>')}</i>`}</button>`; };

const box = () => $('reader') || $('sidebar').insertAdjacentElement('beforebegin', el('div', {id: 'reader', className: 'reader', hidden: true}));

function render() {
    const f = FACETS.find(x => x.id === tab && x.n(cur)) || FACETS.find(x => x.n(cur)), {d} = cur;
    tab = f.id;
    box().hidden = false;
    const budget = `Rework budget: ${d.iteration} of ${d.max_iterations} used since the last re-ASSIGN${d.reopens ? `\nReopened ${plural(d.reopens, 'time')}` : ''}`;
    rebuild(box(), `${d.id}|${tab}`, `<div class="rd-top"><div class="sidebar-header"><h2${PANEL.full(nameOf(d))}>${esc(nameOf(d))}</h2>`
        + `<button class="sidebar-close" data-action="read"${frame('close')}>&times;</button></div>`
        // the rework budget is no third round figure beside the panel's «round N» and the badge (audit D7); reopens only when any
        + meta(esc(d.id) + tally(`${d.iteration}/${d.max_iterations}`, 'rework budget used') + (d.reopens ? tally(d.reopens, d.reopens > 1 ? 'reopens' : 'reopen') : ''), budget)
        + `<div class="rd-tabs">${FACETS.map(x => chip(x, cur, x === f)).join('')}</div></div>${f.body(cur)}`);
}

// `facet` opens or switches the tab; none closes the reader.
// …and a facet CHIP pressed while its facet is open closes it — as the deck's tabs and the project picker do. A link
// that means "show it there" (evidence →, full in reader →) only shows: it closed an open verdict before (critic).
export function openReader(facet, toggle = false, to = '') {
    tab = facet && !(toggle && facet === tab) ? facet : null;
    tab && cur ? render() : closeReader();
    // …below the reader's own sticky head, or the heading and sentence that say what the list is stand under it
    const there = to && $(to);
    if (there) { there.style.scrollMarginTop = `${box().querySelector('.rd-top').offsetHeight}px`; there.scrollIntoView(); }
}
// The panel hands over each node it reads; an open reader follows it.
export function showReader(ctx) {
    cur = ctx;
    if (tab) render();
}
export function closeReader() {
    tab = null;
    if ($('reader')) $('reader').hidden = true;
}
