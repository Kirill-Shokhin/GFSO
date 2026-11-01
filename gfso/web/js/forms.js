// The rows every authoring form writes with — criteria with their pinned probes, pairs, lists — built by assignment and
// read back by position: one builder and reader for the Edit and Decompose modals (author.js) and the goal form (goal.js).
import {el} from './dom.js';
import {post} from './api.js';

// ── rows: built by assignment (dom.el), read back by position ──
const del = cls => el('button', {className: cls, type: 'button', innerHTML: '&times;', onclick() { this.parentElement.remove(); }});
const input = (className, placeholder, value, width) => {
    const i = el('input', {className, placeholder, value});
    i.setAttribute('aria-label', placeholder);   // a field named only by its placeholder has no name once typed in (audit AQ6)
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
