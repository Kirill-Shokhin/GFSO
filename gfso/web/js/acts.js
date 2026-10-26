// Acts on an existing node: its FSM signals, a recorded verdict, and the two AI runs over its subtree.
// EVERY SIGNAL THAT CARRIES TEXT ASKS FOR IT IN THE PANEL: a native `prompt()` is one line, unstylable,
// and BLOCKS the page — a tester's tab froze on `Deliver` and the delivery was lost (wave 26).
import {$, esc, data} from './dom.js';
import {post, refusal} from './api.js';
import {S, taskOf, critNames, hasKids, myRole} from './state.js';
import {mark, PLAN_COST} from './vocab.js';
import {notice, clearNotice, askInPage} from './overlays.js';

const form = html => {
    const f = $('inline-form');
    if (f) f.innerHTML = `<div class="section" style="border-top:1px solid var(--ui-line,#3334);padding-top:8px">${html}</div>`;
};
export const closeForm = () => { const f = $('inline-form'); if (f) f.innerHTML = ''; };
const buttons = (attrs, label) => `<div class="actions" style="margin-top:8px">`
    + `<button class="btn btn-sm"${data(attrs)}>${label}</button>`
    + `<button class="btn btn-sm btn-muted" data-action="form-cancel">Cancel</button></div>`;
const faint = (text, style = '', tag = 'div') => `<${tag} style="${style}font-size:12px;color:var(--ui-text-faint)">${text}</${tag}>`;

// `Fail` asked for failed criteria as free text, and a name outside the contract is refused (Inv-3) —
// so they are the node's own criteria, as checkboxes.
export function sendAction(a) {
    if (!a.prompt && !a.fail) return submitAction(a.id, a.sig, {});
    form(`<div class="section-title">${a.sig}</div>`
        + (a.prompt ? faint(a.prompt, 'display:block;', 'label')
            + `<textarea id="sa-text" rows="4" style="width:100%;box-sizing:border-box" placeholder="${
                a.prompt === 'result' ? 'what you delivered, and what you checked about it' : a.prompt}"></textarea>` : '')
        + (a.fail ? faint("Which criteria failed — a FAIL must name at least one, and only this node's own (Inv-3).", 'margin-top:6px;')
            + critNames(a.id).map((c, i) => `<label style="display:block;font-size:13px"><input type="checkbox" id="sa-fail-${i}"> ${esc(c)}</label>`).join('') : '')
        + buttons({...a, action: 'send-signal'}, `Send ${a.sig}`));
}

export function submitActionForm(a) {
    const body = {};
    if (a.prompt) {
        const v = $('sa-text')?.value || '';
        if (!v.trim()) return notice(`${a.prompt} is required`, 'bad');
        body[a.prompt] = v;
    }
    if (a.fail) {
        body.failed_criteria = critNames(a.id).filter((c, i) => $('sa-fail-' + i)?.checked);
        if (!body.failed_criteria.length) return notice('a FAIL must name at least one failed criterion (Inv-3)', 'bad');
    }
    return submitAction(a.id, a.sig, body);
}

// A REFUSAL IS THE ENGINE TALKING TO YOU: it arrives as a 200 whose body says no, and the page used to
// drop it and refresh — the node did not move and nothing said why.
async function send(url, body, what) {
    clearNotice();
    try {
        const no = await refusal(await post(url, body));
        if (no) return notice(`${what}: ${no}`, 'bad');
        closeForm();
        await S.reload();
    } catch (e) { console.error(url, e); }
}
const submitAction = (id, signal, extra) =>
    send('/api/run/signal', {task_id: id, signal, source: myRole(), ...extra}, 'the engine refused that signal');

// A verdict is per CRITERION: the engine refuses a PASS silent about one, and text that only restates
// the verdict ("ok") — neither of which a one-line prompt could avoid.
export function recordVerdict({id}) {
    const d = taskOf(id), me = myRole();
    const rows = critNames(id).map((c, i) => `<div style="margin:6px 0">${faint(esc(c), 'display:block;', 'label')}`
        + `<input id="obs-${i}" style="width:100%;box-sizing:border-box" placeholder="what you ran and what it printed">`
        + `<label style="font-size:12px"><input type="checkbox" id="fail-${i}"> this criterion FAILED</label></div>`).join('');
    form(`<div class="section-title">Record a verdict</div>`
        + faint('One line per criterion, naming what you ran and what it showed. "ok" is refused: it restates the verdict instead of recording a check.', 'margin-bottom:6px;')
        + `<input id="rv-reviewer" style="width:100%;box-sizing:border-box" value="${esc(d.assignee && me === d.assignee ? '' : me)}"`
        + ` placeholder="reviewer — must NOT be this node's executor (${esc(d.assignee || '?')})">`
        + (rows || '<div style="font-size:12px">This node has no criteria, so there is nothing a verdict could be about.</div>')
        + buttons({action: 'send-verdict', id}, 'Record'));
}

export function submitVerdict({id}) {
    const reviewer = ($('rv-reviewer')?.value || '').trim();
    if (!reviewer) return notice('name the reviewer', 'bad');
    const crits = critNames(id), failed = crits.filter((c, i) => $('fail-' + i)?.checked);
    const observed = Object.fromEntries(crits.map((c, i) => [c, $('obs-' + i)?.value || '']));
    // e.g. reviewer == executor — the engine refuses
    return send('/api/run/record_verdict', {task_id: id, reviewer, observed, verdict: failed.length ? 'FAIL' : 'PASS',
                                            failed_criteria: failed}, 'the engine refused that verdict');
}

export async function aiDecompose({id}) {
    const kids = hasKids(id);
    if (!(await askInPage(`${kids ? 'Refine the existing decomposition (one search↔audit round over the graph)'
            : 'Auto-decompose this node (search↔audit → verified subtree)'}? ${PLAN_COST}`))) return;
    // WHAT IT DID TO YOUR CONTRACT, SAID: authoring a subtree REWRITES the node's own criteria, and a tester's
    // four hand-written ones were replaced with no warning (wave 27). The old set is in the log (Inv-7).
    const before = critNames(id);
    try {
        const r = await post('/api/run/auto_decompose', {request: taskOf(id).description || '', root_id: id, depth: 1});
        const no = await refusal(r);
        if (no) notice('Decomposition refused: ' + no, 'bad');
        await S.reload();
        const after = critNames(id), gone = before.filter(n => !after.includes(n));
        if (gone.length)
            notice(`This rewrote ${id}'s own criteria: ${gone.join(', ')} ${gone.length > 1 ? 'are' : 'is'} no longer in the set `
                   + `(the previous contract is in the node's history). Edit restores anything you meant to keep.`, 'bad');
    } catch (e) { console.error('aiDecompose:', e); }
}

export async function aiReview({id}) {
    if (!(await askInPage('Run the L2 checker over this decomposition (L0/L1 gate + one causal-entailment call)? It spends one model call.'))) return;
    try {
        const d = await (await post('/api/run/review_decomposition', {task_id: id})).json();
        if (!d.gate_passed) notice('Gate FAILED — fix L0/L1 first:\n' + (d.l0l1_failures || []).join('\n'), 'bad');
        else if ((d.criteria_verdicts || []).length) {
            const lines = [...d.criteria_verdicts.map(v => `${mark(v.verdict)} ${v.criterion} — ${v.why}`),
                           ...(d.conflicts || []).map(c => `⚡ conflict [${(c.between || []).join(', ')}]: ${c.why}`)];
            // The register is NOT a discharge: an uncarried parent criterion (FM-1.d) is repaired on the PLAN or
            // refuted in writing; §9.2 holds risk EVENTS with an estimable P, and this forbids nothing (§1.3).
            notice((d.semantic_covered ? 'L2 checker: no gaps found (advisory — the real Level-2 verdict is execution; q_D watches it).\n\n'
                : 'L2 verdicts (advisory — repair the PLAN (edit criteria / map or add a child), or record why the finding is wrong (dispute_finding). NOT the risk register — §9.2 holds risk events, not uncovered entailment):\n\n')
                + lines.join('\n').slice(0, 1800));
        } else if (d.semantic_findings) notice('L2 (advisory):\n\n' + d.semantic_findings.slice(0, 1500));
        else notice('Structurally clean; checker not run (no LLM on this server).');
        await S.reload();     // the panel's stored L2-review section shows the fresh verdict
    } catch (e) { console.error('aiReview:', e); }
}
