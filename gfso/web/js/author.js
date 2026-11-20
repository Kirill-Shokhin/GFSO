// Authoring contracts: a revision of a node (Edit) and a split into children (Decompose); their rows are forms.js.
import {$, el, esc} from './dom.js';
import {task, post} from './api.js';
import {S} from './state.js';
import {notice, act} from './overlays.js';
import {frame} from './hints.js';
import {critRow, listRow, readCrits, readList, iso, suggest} from './forms.js';
import {terminal} from './vocab.js';

const modal = (id, on) => $(id).classList.toggle('active', on);
export const closeModal = ({modal: id}) => modal(id, false);

// ── Edit: a revision (RMW over edit_criteria / edit_accepted_risks / reassign) ──
const edit = {id: null, assignee: '', crits: [], risks: [], recorded: {}};
export const addEditCriterion = c => critRow($('edit-criteria-rows'), c, {cls: 'ec'});
export const addEditAcceptedRisk = value => listRow($('edit-accepted_risks-list'), 'excluded factor…', value);

export async function openEdit({id, risks: risksAs}) {
    const d = await task(id);
    // WHOSE list this form edits is whose word it writes (§9.2, §10.1): the executor over its own split edits
    // the split's register; anyone else — its issuer — the packet's pre-fill. The server routes the same way, and signs
    // it as the name the panel was told (`moves.edit_accepted_risks`); a page that owns no such name has no list here
    const own = risksAs === (d.assignee || '') && (d.children || []).length > 0;
    edit.risksAs = risksAs || '';
    $('edit-risks').hidden = !edit.risksAs;
    $('edit-risks-as').textContent = edit.risksAs;
    const risks = own ? (d.accepted_risks_recorded || []) : (d.prefilled_accepted_risks || []);
    // a kept row posts its RECORDED form, so an edit elsewhere does not strip P, impact, denial (critic r4, 2026-10-04)
    Object.assign(edit, {id, assignee: d.assignee || '', risks: risks.map(n => n.item),
                         recorded: Object.fromEntries(risks.map(n => [n.item, n]))});
    $('edit-criteria-rows').innerHTML = '';
    (d.criteria || []).forEach(addEditCriterion);
    edit.crits = readCrits($('edit-criteria-rows'));       // what the form holds untouched — "changed" is against this
    $('edit-accepted_risks-list').innerHTML = '';
    edit.risks.forEach(addEditAcceptedRisk);
    $('edit-assignee').value = edit.assignee;
    modal('edit-modal', true);
}

export async function submitEdit() {
    const criteria = readCrits($('edit-criteria-rows')), riskItems = readList($('edit-accepted_risks-list'));
    const assignee = $('edit-assignee').value.trim();
    const send = (tool, body) => post(`/api/run/${tool}`, {task_id: edit.id, ...body});
    // ONE ACT, ONE REVISION: each verb is a re-ASSIGN (Inv-1), and posting all of them every time sent the
    // node back to OFFERED twice for one edit (wave 26). Only what CHANGED is sent.
    const critsMoved = JSON.stringify(criteria) !== JSON.stringify(edit.crits);
    const risksMoved = !!edit.risksAs && JSON.stringify(riskItems) !== JSON.stringify(edit.risks);
    const sends = [critsMoved && ['edit_criteria', {criteria}],
        risksMoved && ['edit_accepted_risks', {accepted_risks: riskItems.map(i => edit.recorded[i] || i)}],
        assignee && assignee !== edit.assignee && ['reassign', {assignee}]].filter(Boolean);
    if (!critsMoved && !risksMoved && assignee === edit.assignee) notice('Nothing changed — no revision sent.', 'ok');
    // the first refusal stops the rest
    for (const [tool, body] of sends)
        if (await act(send(tool, body), {what: 'Edit rejected', note: '\n(a delegated/committed node → cancel + re-assign)', ok: null})) break;
    modal('edit-modal', false);
    await S.reload();
}

// ── Decompose: children, each with its own criteria and risks, and the parent's criteria mapped onto them ──
// …a re-admission maps onto the children standing too (§11.5): a criterion added to the node by a revision is flagged
// uncovered (CHECK-1, §12.10) and mapped onto a child at work, which only this form's options let the page do
const dec = {id: null, crits: [], standing: [], mapped: {}};
const childForms = () => [...document.querySelectorAll('.child-form')];
const STANDING = 's:';

export async function openDecompose({id}) {
    dec.id = id;
    try {
        const d = await task(id);
        Object.assign(dec, {crits: d.criteria || [], standing: (d.children || []).filter(c => !terminal(c.state)),
                            mapped: Object.fromEntries((d.criterion_mappings || []).map(m => [m.criterion_name, m.child_id]))});
    } catch (e) { Object.assign(dec, {crits: [], standing: [], mapped: {}}); }
    $('decompose-children').innerHTML = '';
    addChildForm();
    modal('decompose-modal', true);
}

export function addChildForm() {
    const f = el('div', {className: 'child-form'});
    f.innerHTML = `
        <input placeholder="Subtask description" class="dc-desc">
        <input placeholder="Assignee" class="dc-assignee manual-only">
        <input type="datetime-local" class="dc-deadline"${frame('deadline')}>
        <button class="btn btn-sm btn-purple dc-ai" data-action="child-suggest">AI</button>
        <div class="dc-criteria-rows"></div>
        <button class="btn btn-sm btn-muted dc-add" data-action="child-criterion">+ criterion</button>
        <div class="dc-accepted_risks-rows"></div>
        <button class="btn btn-sm btn-muted dc-add" data-action="child-risk">+ accepted_risks</button>`;
    f.querySelector('.dc-desc').oninput = renderMappings;
    $('decompose-children').appendChild(f);
    renderMappings();
}
const childCriterion = (f, c) => critRow(f.querySelector('.dc-criteria-rows'), c, {width: '100px'});
export const addChildCriterion = (_, b) => childCriterion(b.closest('.child-form'));
export const addChildAcceptedRisk = (_, b) => listRow(b.closest('.child-form').querySelector('.dc-accepted_risks-rows'), 'accepted risk factor…');
export async function suggestChildCriteria(_, b) {
    const f = b.closest('.child-form');
    (await suggest(b, f.querySelector('.dc-desc').value.trim()) || []).forEach(c => childCriterion(f, c));
}

function renderMappings() {
    const box = $('decompose-mappings');
    if (!dec.crits.length) { box.innerHTML = ''; return; }
    const kept = Object.fromEntries([...box.querySelectorAll('select')].map(s => [s.dataset.crit, s.value]));
    const kids = [...dec.standing.map(k => [STANDING + k.id, (k.description || k.id).slice(0, 30)]),
                  ...childForms().map((f, i) => [String(i), (f.querySelector('.dc-desc').value || `Child ${i + 1}`).slice(0, 30)])];
    const at = c => kept[c.name] ?? (dec.mapped[c.name] ? STANDING + dec.mapped[c.name] : '');
    box.innerHTML = `<div class="section-title map-title">Criterion mappings (CHECK-1, joint sufficiency)</div>`
        + dec.crits.map(c => `<div class="crit-mapping"><span class="crit-name">${esc(c.name)}</span><select data-crit="${esc(c.name)}">`
            + `<option value="">— unmapped —</option>` + kids.map(([v, k]) =>
                `<option value="${esc(v)}"${at(c) === v ? ' selected' : ''}>${esc(k)}</option>`).join('')
            + `</select></div>`).join('');
}

export async function submitDecompose() {
    const children = childForms().map(f => ({
        spec: {description: f.querySelector('.dc-desc').value.trim(), criteria: readCrits(f),
               accepted_risks: readList(f.querySelector('.dc-accepted_risks-rows'))},
        // under a mode the mode assigns every child and an `assignee=` is refused (tools.py del_by_mode): none is sent
        ...S.graph.mode?.mode ? {} : {assignee: f.querySelector('.dc-assignee').value.trim()},
        deadline: iso(f.querySelector('.dc-deadline').value),
    })).filter(c => c.spec.description && (S.graph.mode?.mode || c.assignee));
    const sels = [...$('decompose-mappings').querySelectorAll('select')];
    // …with no new child, a re-admission that maps onto the standing ones (`children: []`, its mappings and register)
    // …nothing to send says so: a press that did nothing read as a refusal unexplained
    if (!children.length && !sels.some(s => s.value.startsWith(STANDING) && dec.mapped[s.dataset.crit] !== s.value.slice(STANDING.length)))
        return notice('Nothing to change: add a part, or map a criterion onto a part other than the one it is on.', 'bad');
    // The API maps criteria to EXISTING child ids, and these are about to be created: ids are minted here.
    children.forEach((c, i) => { c.task_id = `c${Date.now().toString(36)}-${i}`; });
    // WHAT THE ENGINE WILL REFUSE, REFUSED HERE, WHILE THE FORM IS STILL OPEN: a plan sent unmapped or with
    // no register created children whose every Accept is refused, and re-opening Decompose could only
    // duplicate them — the project became unrecoverable through the page (wave 26 UI pass, 2026-09-06).
    const unmapped = sels.filter(s => s.value === '').map(s => s.dataset.crit);
    if (unmapped.length)
        return notice(`every criterion of this node must be mapped to the child that delivers it `
                      + `(CHECK-1, joint sufficiency). Still unmapped: ${unmapped.join(', ')}.`, 'bad');
    // THE SPLIT'S OWN REGISTER, the decomposer's: its odds of being refuted at contact and where they come from (§9.5,
    // CHECK-4) — the parts' pre-filled risks are their packets', and a split sent with only those was refused at the door
    // whatever was typed (a probe, 2026-11-14)
    const p = parseFloat($('dc-denial-p').value), why = $('dc-denial-why').value.trim();
    if (!(p >= 0 && p <= 1) || !why)
        return notice('say how likely this split is to be wrong once the work meets reality (0–1) and where that figure '
                      + 'comes from — the split carries it as its own risk (§9.5).', 'bad');
    // …AND THE ENGINE'S OWN REFUSAL REACHES THE USER — a rejected plan closed the modal like an accepted one.
    // …signed by the session as the split's holder (§11.5), never by a name sent
    await act(post('/api/run/decompose', {parent_id: dec.id, children,
        accepted_risks: [{denial: true, p, justification: why}],
        mappings: sels.map(s => ({criterion_name: s.dataset.crit, child_id: s.value.startsWith(STANDING)
            ? s.value.slice(STANDING.length) : children[+s.value].task_id}))}),
        {ok: async () => { modal('decompose-modal', false); await S.reload(); }});
}
