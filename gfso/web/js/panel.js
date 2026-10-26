// The node panel, one screen: what the node is, whose move it is, how its last verdict went, where each
// criterion stands, and a chip per long text — those open in the reader (reader.js). Buttons carry
// `data-action` (dispatched in main.js); nothing here sends anything.
import {$, esc, data, section, rebuild, hint} from './dom.js';
import {getJSON} from './api.js';
import {S, hasKids, taskOf} from './state.js';
import {bucketOf, statusLabel, vOf, V_SYMBOL, can, signals, CANCEL, closureNote, contested} from './vocab.js';
import {roundsOf, at, waitsOf, waitWords, conjunct} from './run.js';
import {signedBy} from './work.js';
import {glyph, mark} from './draw.js';
import {FACETS, chip, signer, perCrit, pinned, showReader, closeReader} from './reader.js';

const when = iso => new Date(at(iso)).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
const link = (facet, label) => `<button class="pn-link" data-action="read" data-facet="${facet}">${label} →</button>`;
const ISSUER_MOVES = "the executor stopped and the decision is the issuer's: raise the rework bound (Revise → max_iterations) "
    + 'if the forecast was short, change or narrow the criteria (Revise) if the plan is wrong, or close it (Cancel — it cascades '
    + "the live subtree). Silence closes it too, by this state's own timeout; it never drifts to a pass.";

// Whose move it is (§12.13), else the Dep producers not passed yet — named beside the owner when both hold.
function waiting(d) {
    const words = waitWords(waitsOf(S.graph.nodes, S.graph.edges)[d.id], id => taskOf(id).name || id);
    return words === '—' ? '' : `<span title="${hint('Waiting on', d.state === 'ESCALATED' ? ISSUER_MOVES : words)}">waiting on <b>${esc(words)}</b></span> · `;
}

function head({d, rounds}) {
    const v = vOf(d.state), name = d.name || d.description || d.id, note = closureNote(d.closure), bad = contested(d.closure);
    const live = d.state !== 'DONE' && d.state !== 'ABANDONED', mode = S.graph.mode?.mode;
    return `<div class="sidebar-header"><h2 title="${esc(name)}">${esc(name)}</h2><button class="sidebar-close" data-action="close">&times;</button></div>`
        + `<div class="pn-meta" title="${hint('Executor (Del)', d.assignee || 'none')}">${[d.id, mode && `${mode} mode`, `Del ${d.assignee || '—'}`].filter(Boolean).map(esc).join(' · ')}</div>`
        + `<div class="pn-status"><span class="v-badge v-${v}" title="V(t) — the validation outcome&#10;pass only when every criterion passes; ⊥ while not yet checked (§2.3)"><span class="v-symbol">${V_SYMBOL[v]}</span>V = ${v}</span>`
        + `<span class="state-badge b-${bucketOf(d.state)}">${statusLabel(d.state, d.done_reason)}</span>`
        + (d.deadline ? `<span class="deadline-chip${live && at(d.deadline) < Date.now() ? ' overdue' : ''}" title="Deadline&#10;when this node is due">⏱ ${when(d.deadline)}</span>` : '')
        // a node in work after its last verdict is working on the NEXT round, not the one already answered
        + `</div><div class="pn-meta">${waiting(d)}${['EXECUTING', 'REWORKING'].includes(d.state) && (!rounds.length || rounds.at(-1).verdict)
            ? `round ${rounds.length + 1}, in work` : `round ${rounds.length}`}</div>`
        // WHO RAN IT: the model is the node's real executor, its validator another party (author, 2026-10-25)
        + `<div class="pn-meta pn-by" id="pn-by">${signedBy(S.run, d.id)}</div>`
        + (d.state === 'ESCALATED' ? `<div class="pn-note check-skip" title="${hint('The issuer decides', ISSUER_MOVES)}">issuer decides: raise the bound, change the criteria, or cancel</div>` : '')
        // HOW IT CLOSED, on the node itself — the same `closure` the drawing reads, no copy of the rule.
        + (note ? `<div class="pn-note ${bad ? 'check-fail' : 'check-skip'}"${bad ? ' title="Read the verdict&#10;legitimate (§10.3), and nothing can check it (§15.7)"' : ''}>`
                  + `${bad ? '⚠ ' : ''}${note}</div>` : '');
}

// THE EXECUTION VERDICT in one line — what, who, when, what failed; its evidence is the reader's.
function verdict({vr}) {
    if (vr?.verdict) return `<div class="pn-verdict ${vr.verdict === 'PASS' ? 'check-pass' : 'check-fail'}">${glyph(vr.verdict)}<b>${vr.verdict}</b>`
        + `<span class="pn-who" title="${hint('Validator', vr.validator)}">${signer(vr)}${vr.ts ? ' · ' + when(vr.ts) : ''}</span>`
        + `${vr.current === false ? '<span class="check-fail" title="An earlier delivery&#10;this verdict is about a delivery the current one replaced">earlier</span>' : ''}${link('verdict', 'evidence')}</div>`;
    // what failed is not repeated here: it is the ✗ rows of the criteria list just below
    // ⊥ IS NOT "NOT VALIDATED": a validator reported and the engine refused it — the issuer owes a decision.
    return vr?.refused_report ? `<div class="pn-verdict check-fail"><span class="pn-who">a validator reported and the report was REFUSED as ⊥ — `
        + `${esc(vr.refused_report.note || 'the issuer decides')}</span>${link('verdict', 'why')}</div>` : '';
}

// One mark per round (run.js): this criterion named in a FAIL → the cross; a PASS (every criterion passing) → an ink
// dot; a FAIL that did not name it, a delivery still unanswered, or a criterion the current verdict left undecided →
// hollow: the log of past rounds keeps only what a FAIL named, so an unnamed one is ⊥, not pass. The last 12.
const strip = (rounds, name, now) => { const rs = rounds.slice(-12), open = (x, i) => `<circle class="mk-open" cx="${x}" cy="0" r="2.5"/>`;
    return !rs.length ? '' : `<svg class="cr-strip" width="${rs.length * 8}" height="10" viewBox="0 -5 ${rs.length * 8} 10" title="${hint(`${rounds.length} rounds`, 'this criterion in each round: dot pass, cross fail, ring not checked or not recorded')}">`
        + rs.map((r, i) => !r.verdict || (i === rs.length - 1 && now && now !== 'pass' && now !== 'fail') ? open(i * 8 + 4)
            : r.per ? (v => v === 'pass' || v === 'fail' ? mark(v.toUpperCase(), i * 8 + 4, 0, 2.5) : open(i * 8 + 4))(r.per.find(c => c.criterion === name)?.verdict)
            : r.verdict === 'FAIL' && !r.failed.includes(name) && !(i === rs.length - 1 && now === 'pass') ? open(i * 8 + 4)
            : mark(r.verdict === 'FAIL' && !r.failed.includes(name) ? 'PASS' : r.verdict, i * 8 + 4, 0, 2.5)).join('') + '</svg>'; };

// A criterion is one line at the current verdict; unfolded (one at a time) it reads what it asks, what the
// verdict found, and its pinned check.
function criteria({d, vr, rounds}) {
    // a Dep edge's bare declaration is the edge the head's «waits on» already names, not a criterion with a verdict
    const cs = d.criteria.filter(conjunct);
    if (!cs.length) return '';
    const pc = perCrit(vr), k = cs.filter(c => pc[c.name]?.verdict === 'pass').length;
    return section(`Criteria${vr?.verdict ? ` · ${k}/${cs.length} pass` : ''}`, cs.map(c => {
        const v = pc[c.name]?.verdict, ev = pc[c.name]?.evidence, key = `${d.id}|${c.name}`;
        return `<details class="cr-row" name="crit" data-key="${esc(key)}"><summary>`
            + `<span class="cr-g">${v === 'pass' ? glyph('PASS', 3.5) : v === 'fail' ? glyph('FAIL', 3.5) : '⊥'}</span>`
            + `<span class="cr-name" title="${esc(c.name)}">${esc(c.name)}</span>${strip(rounds, c.name, vr?.current !== false && v)}</summary>`
            + `<div class="cr-more"><div class="crit-desc">${esc(c.description)}</div>`
            + (ev ? `<div class="verdict-evidence">${esc(ev)}</div>${link('verdict', 'full in reader')}` : '')
            + pinned(c, key + '|check') + `</div></details>`;
    }).join(''));
}

const facets = ctx => `<div class="pn-facets">${FACETS.map(f => chip(f, ctx)).join('')}</div>`;

const btn = (cls, label, action, attrs) => `<button class="btn btn-sm ${cls}"${data({action, ...attrs})}>${label}</button>`;
const sig = (id, a) => btn(a.cls, a.label, 'signal', {id, sig: a.s, prompt: a.prompt, fail: a.needsCriteria && 1});

// Every control the FSM admits on this state (vocab.js) — the plan-repair Edit wherever a re-ASSIGN is
// legal, not on OFFERED alone (a tester was trapped on an EXECUTING root, wave 27). The forms these open
// go in #inline-form, never a native dialog.
function actions({d}) {
    const s = d.state, id = {id: d.id}, kids = hasKids(d.id);
    const btns = [...signals(s).map(a => sig(d.id, a)),
        can(s, 'V') ? btn('btn-muted', 'Record verdict', 'verdict', id) : '',
        can(s, 'C') ? sig(d.id, CANCEL) : '',
        // ONE AI verb, dispatched by the node's state: undecomposed → author; decomposed → one refine round.
        // AI review is the standalone L2 door — hand-authored graphs never pass decompose's semantic pass.
        ...can(s, 'D') ? [btn('btn-purple', 'Decompose', 'decompose', id), btn('btn-purple', kids ? 'AI refine' : 'AI decompose', 'ai-decompose', id),
                          kids ? btn('btn-purple', 'AI review', 'ai-review', id) : ''] : [],
        can(s, 'E') ? btn('btn-muted', 'Edit', 'edit', id) : ''].join('');
    // under a mode the agents and the system move the nodes; a person's own moves stay where one is theirs (header.js)
    return btns ? `<div class="pn-foot${S.mySteps?.has(d.id) ? '' : ' manual-only'}"><div class="actions">${btns}</div><div id="inline-form"></div></div>` : '';
}

const PARTS = [head, verdict, criteria, facets, actions];

export async function selectTask(id) {
    try {
        const base = `/api/tasks/${encodeURIComponent(id)}`, soft = p => p.catch(() => null);
        const [d, vr, cr] = await Promise.all([getJSON(base), soft(getJSON(base + '/verdict')), soft(getJSON(base + '/critique'))]);
        const ctx = {d, vr, cr, rounds: roundsOf(d.audit, d.id)}, sb = $('sidebar');
        sb.classList.remove('hidden');
        rebuild(sb, d.id, PARTS.map(f => f(ctx)).join(''));
        showReader(ctx);
    } catch (e) { console.error('selectTask:', e); }
}

// …and again once the run is read: the panel can open before the deck has built it
export const resign = id => { const by = $('pn-by'); if (by) by.innerHTML = signedBy(S.run, id); };

export function closeSidebar() {
    closeReader();
    $('sidebar').classList.add('hidden');
}
