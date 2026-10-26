// Authoring contracts: a revision of a node (Edit) and a split into children (Decompose); their rows are forms.js.
import {$, el, esc} from './dom.js';
import {getJSON, post, refusal} from './api.js';
import {S, myRole} from './state.js';
import {notice} from './overlays.js';
import {critRow, listRow, readCrits, readList, iso, suggest} from './forms.js';

const modal = (id, on) => $(id).classList.toggle('active', on);
export const closeModal = ({modal: id}) => modal(id, false);

// ── Edit: a revision (RMW over edit_criteria / edit_accepted_risks / reassign) ──
const edit = {id: null, assignee: '', crits: [], risks: [], recorded: {}};
export const addEditCriterion = c => critRow($('edit-criteria-rows'), c, {cls: 'ec'});
export const addEditAcceptedRisk = value => listRow($('edit-accepted_risks-list'), 'excluded factor…', value);

export async function openEdit({id}) {
    const d = await getJSON(`/api/tasks/${encodeURIComponent(id)}`);
    // WHOSE list this form edits is whose word it writes (§9.2, §10.1): the executor over its own split edits
    // the split's register; anyone else — its issuer — the packet's pre-fill. The server routes the same way.
    const own = myRole() === (d.assignee || '') && (d.children || []).length > 0;
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
    const agent = myRole();
    if (!agent) return notice('Set your role (agent) above first — only the self-owner may edit.', 'bad');
    const criteria = readCrits($('edit-criteria-rows')), riskItems = readList($('edit-accepted_risks-list'));
    const assignee = $('edit-assignee').value.trim();
    const send = (tool, body) => post(`/api/run/${tool}`, {task_id: edit.id, ...body});
    // ONE ACT, ONE REVISION: each verb is a re-ASSIGN (Inv-1), and posting all of them every time sent the
    // node back to OFFERED twice for one edit (wave 26). Only what CHANGED is sent.
    const critsMoved = JSON.stringify(criteria) !== JSON.stringify(edit.crits);
    const risksMoved = JSON.stringify(riskItems) !== JSON.stringify(edit.risks);
    try {
        let no = '';
        if (critsMoved) no = await refusal(await send('edit_criteria', {criteria, agent}));
        if (!no && risksMoved) no = await refusal(await send('edit_accepted_risks', {accepted_risks: riskItems.map(i => edit.recorded[i] || i), agent}));
        if (!no && assignee && assignee !== edit.assignee) no = await refusal(await send('reassign', {assignee}));
        if (!no && !critsMoved && !risksMoved && assignee === edit.assignee) notice('Nothing changed — no revision sent.', 'ok');
        if (no) notice('Edit rejected: ' + no + '\n(a delegated/committed node → cancel + re-assign)', 'bad');
    } catch (e) { console.error('edit:', e); }
    modal('edit-modal', false);
    await S.reload();
}

// ── Decompose: children, each with its own criteria and risks, and the parent's criteria mapped onto them ──
const dec = {id: null, crits: []};
const childForms = () => [...document.querySelectorAll('.child-form')];

export async function openDecompose({id}) {
    dec.id = id;
    try { dec.crits = (await getJSON(`/api/tasks/${encodeURIComponent(id)}`)).criteria || []; } catch (e) { dec.crits = []; }
    $('decompose-children').innerHTML = '';
    addChildForm();
    modal('decompose-modal', true);
}

export function addChildForm() {
    const f = el('div', {className: 'child-form'});
    f.innerHTML = `
        <input placeholder="Subtask description" class="dc-desc">
        <input placeholder="Assignee" class="dc-assignee manual-only" style="width:120px">
        <input type="datetime-local" class="dc-deadline" style="width:180px" title="Deadline&#10;when this part is due — before its parent is">
        <button class="btn btn-sm btn-purple" data-action="child-suggest" style="margin-left:4px">AI</button>
        <div class="dc-criteria-rows" style="margin-top:4px"></div>
        <button class="btn btn-sm btn-muted" data-action="child-criterion" style="font-size:10px">+ criterion</button>
        <div class="dc-accepted_risks-rows" style="margin-top:6px"></div>
        <button class="btn btn-sm btn-muted" data-action="child-risk" style="font-size:10px">+ accepted_risks</button>`;
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
    const kids = childForms().map((f, i) => (f.querySelector('.dc-desc').value || `Child ${i + 1}`).slice(0, 30));
    box.innerHTML = `<div class="section-title" style="border-color:var(--hair);padding-bottom:4px;margin:14px 0 8px">Criterion mappings (CHECK-1, joint sufficiency)</div>`
        + dec.crits.map(c => `<div class="crit-mapping"><span class="crit-name">${esc(c.name)}</span><select data-crit="${esc(c.name)}">`
            + `<option value="">— unmapped —</option>` + kids.map((k, i) =>
                `<option value="${i}"${kept[c.name] === String(i) ? ' selected' : ''}>${esc(k)}</option>`).join('')
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
    if (!children.length) return;
    // The API maps criteria to EXISTING child ids, and these are about to be created: ids are minted here.
    children.forEach((c, i) => { c.task_id = `c${Date.now().toString(36)}-${i}`; });
    const sels = [...$('decompose-mappings').querySelectorAll('select')];
    // WHAT THE ENGINE WILL REFUSE, REFUSED HERE, WHILE THE FORM IS STILL OPEN: a plan sent unmapped or with
    // no register created children whose every Accept is refused, and re-opening Decompose could only
    // duplicate them — the project became unrecoverable through the page (wave 26 UI pass, 2026-09-06).
    const unmapped = sels.filter(s => s.value === '').map(s => s.dataset.crit);
    if (unmapped.length)
        return notice(`every criterion of this node must be mapped to the child that delivers it `
                      + `(CHECK-1, joint sufficiency). Still unmapped: ${unmapped.join(', ')}.`, 'bad');
    if (children.every(c => !c.spec.accepted_risks.length))
        return notice('a decomposition needs its ACCEPTED_RISKS register (CHECK-4, §9.2: a decomposition '
                      + 'without one is incomplete by definition). Add at least one factor — `+ accepted_risks` '
                      + 'on a subtask — or say in it that none is known.', 'bad');
    const no = await refusal(await post('/api/run/decompose', {parent_id: dec.id, children,
        mappings: sels.map(s => ({criterion_name: s.dataset.crit, child_id: children[+s.value].task_id}))}));
    // …AND THE ENGINE'S OWN REFUSAL REACHES THE USER — a rejected plan closed the modal like an accepted one.
    if (no) return notice(no, 'bad');
    modal('decompose-modal', false);
    await S.reload();
}
