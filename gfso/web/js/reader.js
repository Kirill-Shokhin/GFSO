// The reader: every long text about the selected node, one facet per tab, in a slide-over left of the
// panel. It renders what the panel read and fetches nothing, so it follows the selection by construction.
import {$, el, esc, section, ul, rebuild, hint} from './dom.js';
import {byHand, vOf, V_SYMBOL, mark, FM, fmOf, FM_NONE, FM_NO_MODE} from './vocab.js';

let cur = null, tab = null;
const txt = x => esc(typeof x === 'string' ? x : JSON.stringify(x, null, 1));


// Who produced a verdict: a hand or an instrument — nothing closes on impression (HTTP door, 2026-09-02).
export const signer = vr => vr.by_hand ? byHand(esc(vr.validator || ''))
    : `validated by ${esc(vr.validator || 'an instrument')}${vr.validator_model ? ' · ' + esc(vr.validator_model) : ''}`;
export const perCrit = vr => Object.fromEntries((vr?.per_criterion || []).map(c => [c.criterion, c]));

// A criterion's pinned check is what makes it a contract (A1, §2) — folded, the longest part of it.
export const pinned = (c, key) => (c.check || []).length
    ? `<details class="crit-check" data-key="${esc(key)}"><summary>check (${c.check.length} probe${c.check.length === 1 ? '' : 's'})</summary><pre>`
      + c.check.map(p => [p.behaviour && `# ${p.behaviour}`, `$ ${p.command}`, `→ ${p.expect}`,
                          Object.keys(p.inputs || {}).length && `inputs: ${Object.keys(p.inputs).join(', ')}`]
                         .filter(Boolean).map(esc).join('\n')).join('\n\n') + `</pre></details>`
    : `<div class="check-fail">no pinned check — nothing decides this criterion but a probe improvised at validation time (A1, §2)</div>`;

// THE EXECUTION VERDICT, criterion by criterion. ONE `<li>`, TWO FLEX CHILDREN: the icon, and one body
// block — siblings in a flex row tore the result apart (author, 2026-09-12). A command run for several
// behaviours is shown once, the behaviours as its tooltip; evidence is shown whole.
function verdict({vr}) {
    if (vr?.verdict) return section('Verdict on the work',
        `<div class="${vr.verdict === 'PASS' ? 'check-pass' : 'check-fail'}">${vr.verdict} — ${signer(vr)}`
        + `${vr.current === false ? ' <span class="check-fail">(validated an EARLIER delivery)</span>' : ''}</div>`
        + ((vr.failed_criteria || []).length ? `<div class="check-fail">failed: ${esc(vr.failed_criteria.join(', '))}</div>` : '')
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
                + (byCmd.size ? `<div class="verdict-probes">${[...byCmd].map(([cmd, bhs]) =>
                    `<code title="${hint('What it checks', bhs)}">${esc(cmd)}</code>`).join('')}</div>` : '')
                + `</div></li>`;
        })));
    // ⊥ IS NOT "NOT VALIDATED": a validator reported and the engine refused it — the issuer owes a decision.
    const rr = vr?.refused_report;
    return !rr ? '' : section('Verdict on the work',
        `<div class="check-fail">a validator reported and the report was REFUSED as ⊥ — ${esc(rr.note || 'the issuer decides')}</div>`
        + (rr.why_it_is_not_a_verdict ? `<div class="verdict-evidence">${esc(rr.why_it_is_not_a_verdict)}</div>` : ''));
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
        `<li class="${bad ? 'check-fail' : ''}">${status}${rev.model ? ' · ' + esc(rev.model) : ''}${rev.ts ? ' · ' + esc(rev.ts) : ''}</li>`,
        ...cv.map(v => `<li>${mark(v.verdict)} ${esc(v.criterion)} — ${esc(v.why || '')}</li>`),
        ...conflicts.map(c => `<li>⚡ [${esc((c.between || []).join(', '))}] ${esc(c.why || '')}</li>`),
        ...undecided.map(u => `<li class="check-fail">✗ this node's OWN criteria do not decide: ${esc(u.obligation || u.gap || '')}`
            + `${u.admits ? ` <div class="verdict-evidence">${esc(u.admits)}</div>` : ''}</li>`),
        bad ? `<li style="color:var(--ui-text-faint)">Two ways out: EDIT the criteria this names (the fix retires this verdict — `
            + `run the review again after it), or record why a finding is wrong (<code>dispute_finding</code>).</li>` : '']));
}

// The parts' states are a FORECAST of the parent: Theorem 1 holds under a correct decomposition only, and
// the parent's V is its own contact over the result (§12.8) — never AND-ed into it here.
const kids = d => d.children || [], passing = d => kids(d).filter(c => vOf(c.state) === 'pass').length;
const composition = ({d}) => section('Composition — the parts', `<div class="composition-panel"><div class="composition-formula">`
    + `${passing(d)} of ${kids(d).length} parts pass — a forecast: V(parent) = AND(parts) holds `
    + `under a correct decomposition (Th. 1), and the parent's V is its own verdict over the result (§12.8)</div>`
    + kids(d).map(c => { const v = vOf(c.state);
        return `<div class="composition-row v-${v}"><span class="v-sym">${V_SYMBOL[v]}</span>`
            + `<span class="child-name" data-action="select" data-id="${esc(c.id)}">${esc(c.name || c.description)}</span></div>`; }).join('')
    + `</div>`);

// The node's audit slice, newest first; what a signal carried is folded under its line.
const history = ({d}) => section('History — newest first', ul('item-list audit-list', [...d.audit].reverse().map(a => {
    const line = `${a.timestamp.slice(5, 19).replace('T', ' ')} ${a.signal} ${a.old_state || ''}→${a.new_state || 'rej'}${a.source ? ' · ' + esc(a.source) : ''}`;
    const more = ['reason', 'justification', 'result', 'error', 'failed_criteria', 'in_flight'].filter(k => a[k] && a[k].length !== 0)
        .map(k => `<div class="rd-field"><b>${k}</b>${txt(a[k])}</div>`).join('');
    return `<li class="${a.rejected ? 'check-fail' : ''}">${more ? `<details data-key="${esc(`h|${d.id}|${a.timestamp}|${a.signal}`)}">`
        + `<summary>${line}</summary>${more}</details>` : line}</li>`;
})));

const list = (k, title) => ({d}) => section(title, ul('facet-list', (d[k] || []).map(x => `<li>${esc(x)}</li>`)));

// Facet: what the tab is called, what its chip counts (falsy hides the chip), what it shows.
export const FACETS = [
    {id: 'desc', label: 'Description', n: ({d}) => !!d.description,
     body: ({d}) => section('Description', `<div class="rd-text">${esc(d.description)}</div>`)},
    {id: 'verdict', label: 'Verdict', n: ({vr}) => vr?.verdict || (vr?.refused_report && '⊥'), body: verdict},
    {id: 'scope', label: 'Scope', n: ({d}) => (d.scope || []).length, body: list('scope', 'Scope — boundary exclusions')},
    {id: 'risks', label: 'AcceptedRisk', n: ({d}) => (d.accepted_risks || []).length, body: list('accepted_risks', 'AcceptedRisk (STD-1)')},
    {id: 'components', label: 'Risk components', n: ({d}) => (d.risk_components || []).length, body: list('risk_components', 'Risk components (STD-3)')},
    {id: 'parts', label: 'Parts', n: ({d}) => kids(d).length && `${passing(d)}/${kids(d).length} pass`, body: composition},
    {id: 'checks', label: 'Checks', n: ({d}) => ran(d).length && `${ran(d).filter(c => !met(c)).length}/${ran(d).length} unmet`, body: checks},
    {id: 'l2', label: 'L2 review', n: ({cr}) => l2(cr)?.short, body: review},
    {id: 'recs', label: 'AI recommendations', n: ({d}) => d.recommendation?.suggestions?.length,
     body: ({d}) => section('AI Recommendations', `<div class="recs">${ul('', d.recommendation.suggestions.map(s =>
         `<li>${esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</li>`))}</div>`)},
    {id: 'history', label: 'History', n: ({d}) => d.audit.length, body: history},
];
export const chip = (f, ctx, on = false) => { const n = f.n(ctx);
    return !n ? '' : `<button class="fchip${on ? ' on' : ''}" data-action="read" data-facet="${f.id}">${f.label}${n === true ? '' : ` <i>${esc(n)}</i>`}</button>`; };

const box = () => $('reader') || $('sidebar').insertAdjacentElement('beforebegin', el('div', {id: 'reader', className: 'reader', hidden: true}));

function render() {
    const f = FACETS.find(x => x.id === tab && x.n(cur)) || FACETS.find(x => x.n(cur)), {d} = cur;
    tab = f.id;
    box().hidden = false;
    rebuild(box(), `${d.id}|${tab}`, `<div class="rd-top"><div class="sidebar-header"><h2>${esc(d.name || d.id)}</h2>`
        + `<button class="sidebar-close" data-action="read" title="Close&#10;Esc">&times;</button></div>`
        + `<div class="pn-meta">${esc(d.id)} · rework budget ${d.iteration} of ${d.max_iterations} used since the last re-ASSIGN · reopens ${d.reopens || 0}</div>`
        + `<div class="rd-tabs">${FACETS.map(x => chip(x, cur, x === f)).join('')}</div></div>${f.body(cur)}`);
}

// `facet` opens or switches the tab; none closes the reader.
// …and the facet open now, pressed again, closes it — as the deck's tabs and the project picker do
export function openReader(facet) {
    tab = facet && facet !== tab ? facet : null;
    tab && cur ? render() : closeReader();
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
document.addEventListener('keydown', e => { if (e.key === 'Escape' && tab) closeReader(); });
