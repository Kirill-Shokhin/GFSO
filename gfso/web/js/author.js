// Authoring contracts: a revision of a node (Edit) and a split into children (Decompose), and the rows
// every authoring form writes with — this one builder and reader, shared with the goal constructor.
import {$, el, esc} from './dom.js';
import {getJSON, post} from './api.js';
import {S, myRole} from './state.js';
import {notice} from './overlays.js';

// ── rows: built by assignment (dom.el), read back by position ──
const del = cls => el('button', {className: cls, type: 'button', innerHTML: '&times;', onclick() { this.parentElement.remove(); }});
const input = (className, placeholder, value, width) => {
    const i = el('input', {className, placeholder, value});
    if (width) i.style.width = width;
    return i;
};
// A pair row — a criterion (name, description), or an accepted risk (item, justification). Returns the row.
export const pairRow = (box, a = '', b = '', {cls = 'cr', rowCls = '', width, ph = ['name', 'description']} = {}) => {
    const row = el('div', {className: 'criterion-row' + rowCls},
                   input(`${cls}-name`, ph[0], a, width), input(`${cls}-desc`, ph[1], b), del('cr-del'));
    box.append(row);
    return row;
};
export const listRow = (box, placeholder, value = '') =>
    box.append(el('div', {className: 'list-item'}, input('', placeholder, value), del('li-del')));
// `both`: a criterion needs its description; a risk's justification may come later. `more(row)` adds a
// kind's own fields under the pair.
export const readPairs = (box, [ka, kb] = ['name', 'description'], both = true, more = () => ({})) =>
    [...box.querySelectorAll('.criterion-row')].map(r => {
        const [a, b] = r.querySelectorAll('input');
        return {...more(r), [ka]: a.value.trim(), [kb]: b.value.trim()};
    }).filter(c => c[ka] && (!both || c[kb]));

// A CRITERION IS A CONTRACT ONLY WITH ITS CHECK PINNED (A1, §2): the engine refuses one with no probe, so
// every form that writes criteria — the goal, Edit, Decompose — carries the probes under each row. What a
// read brought beyond the form's fields (a probe's `inputs`, a seam's `depends_on`) rides back untouched.
const PROBE = ['behaviour', 'command', 'expect'];
function probeRow(box, p = {}) {
    const row = el('div', {className: 'probe-row'}, ...PROBE.map(k => input(`pr-${k}`, k, p[k] || '')), del('cr-del'));
    row._was = p;
    box.append(row);
}
const readProbes = row => [...row.querySelectorAll('.probe-row')].map(r => ({...r._was,
    ...Object.fromEntries(PROBE.map((k, i) => [k, r.querySelectorAll('input')[i].value.trim()]))})).filter(p => PROBE.every(k => p[k]));
export function critRow(box, c = {}, opts = {}) {
    const row = pairRow(box, c.name, c.description, opts), probes = el('div', {className: 'probes'});
    // a seam (`depends_on`) decides nothing about this node, so it pins no check (procedure.py)
    const mark = () => row.classList.toggle('no-check', !c.depends_on && !readProbes(row).length);
    row._was = c;
    row.lastElementChild.before(el('button', {className: 'cr-check', type: 'button', textContent: '+ check',
                                              onclick() { probeRow(probes); }}));
    row.append(el('span', {className: 'cr-need', textContent: 'needs a check'}), probes);
    (c.check || []).forEach(p => probeRow(probes, p));
    row.oninput = row.onclick = mark;
    mark();
}
// a row with a name is a criterion even before its description — admission must judge what is on the screen
export const readCrits = box => readPairs(box, undefined, false, r => ({...r._was, check: readProbes(r)}));
export const readList = box => [...box.querySelectorAll('.list-item input')].map(i => i.value.trim()).filter(Boolean);
export const iso = v => v ? new Date(v).toISOString() : null;

// The model's proposal for a description, or null (nothing asked, or the call failed).
export async function suggest(btn, desc) {
    if (!desc) return null;
    const label = btn.textContent;
    btn.textContent = '…'; btn.disabled = true;
    try { return (await (await post('/api/suggest-criteria', {description: desc})).json()).criteria; }
    catch (e) { console.error('suggest:', e); return null; }
    finally { btn.textContent = label; btn.disabled = false; }
}

// The engine's no, as the engine wrote it, or '' — a refusal is a 200 whose body says so (`refused`,
// `error`, `accepted: false`), a malformed call a 422 carrying the verb's own dict.
export async function refusal(r) {
    const out = await r.json().catch(() => ({}));
    const no = !r.ok || out.refused || out.error || out.accepted === false;
    return !no ? '' : String(out.error || (typeof out.detail === 'string' ? out.detail : JSON.stringify(out.detail ?? out)) || r.status);
}

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
        let r = {ok: true};
        if (critsMoved) r = await send('edit_criteria', {criteria, agent});
        if (r.ok && risksMoved) r = await send('edit_accepted_risks', {accepted_risks: riskItems.map(i => edit.recorded[i] || i), agent});
        if (r.ok && assignee && assignee !== edit.assignee) r = await send('reassign', {assignee});
        if (r.ok && !critsMoved && !risksMoved && assignee === edit.assignee) notice('Nothing changed — no revision sent.', 'ok');
        if (!r.ok) {
            const e = await r.json().catch(() => ({}));
            notice('Edit rejected: ' + (e.detail || r.status) + '\n(a delegated/committed node → cancel + re-assign)', 'bad');
        }
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
        <input placeholder="Assignee" class="dc-assignee" style="width:120px">
        <input type="datetime-local" class="dc-deadline" style="width:180px" title="deadline">
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
        assignee: f.querySelector('.dc-assignee').value.trim(), deadline: iso(f.querySelector('.dc-deadline').value),
    })).filter(c => c.spec.description && c.assignee);
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
