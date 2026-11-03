// The log as events: grouped by node, newest first, filtered by kind. A group's head says where the
// node stands and, when it has failed, what its last FAIL named — the usual question answered
// without opening anything; one click opens the node's own trail, its narration nested in.
import {esc, tally} from './dom.js';
import {bindFocus, focus, watch, point} from './store.js';
import {glyph} from './draw.js';
import {hm, day, unref} from './fmt.js';
import {S, kept, keep, moverOf} from './state.js';
import {PROJECT} from './api.js';
import {at, said, failedOf, failingNow} from './run.js';
import {failedWords, TIP} from './hints.js';
import {CARRIED, label, stateWord, delivered, enteredWord} from './vocab.js';

const KINDS = {
    verdict: ['PASS', 'FAIL'], delivery: ['DELIVER'], assignment: ['ASSIGN', 'ACCEPT', 'REOPEN'],
    clock: ['TIMEOUT'], dispute: ['CHALLENGE', 'ACCEPT_CHALLENGE', 'REJECT_CHALLENGE', 'BLOCK', 'RESOLVE_BLOCK'],
    close: ['CANCEL', 'CONFIRM_CANCEL'], refused: [], run: [], narration: [],
};
// the run's own course, on no node: a stop and its reason, a start, the mode set — kept, not dropped with the narration
const RUN = '';
// a move the engine refused changed nothing: its own kind, so the column of state moves holds only moves
const signalKind = a => a.rejected ? 'refused' : Object.keys(KINDS).find(k => KINDS[k].includes(a.signal)) || 'assignment';

// One stream of rows per node: signals from the audit, narration from the pipeline ("<node>: …").
function streams(run, nodes, pipeline) {
    const ids = new Set(nodes.map(n => n.id)), out = Object.fromEntries([...nodes.map(n => [n.id, []]), [RUN, []]]);
    for (const a of run.audit) if (out[a.task_id]) out[a.task_id].push({t: a.t, kind: signalKind(a), a});
    for (const p of pipeline) {
        const {node, text} = said(p.message);
        if (ids.has(node)) out[node].push({t: at(p.ts), kind: 'narration', p: {source: p.source, text}});
        else out[RUN].push({t: at(p.ts), kind: 'run', p: {source: p.source, text: p.message}});
    }
    Object.values(out).forEach(rs => rs.sort((x, y) => y.t - x.t));
    return out;
}

function row(r) {
    // …a long one folded to two lines, the whole of it on hover: hundreds of characters a row read as the console (audit D16)
    if (r.p) return `<li class="ev ev-narration${r.kind === 'run' ? ' ev-run' : ''}"><time>${hm(r.t)}</time><span class="ev-src">${esc(r.p.source)}</span><span class="ev-text"${r.p.text.length > 60 ? TIP.cell(unref(r.p.text)) : ''}>${esc(unref(r.p.text))}</span></li>`;
    // what it carried, folded — but its failed criteria, drawn as chips, and an error the move line already says
    const a = r.a, prose = CARRIED.filter(([k]) => a[k] && k !== 'failed_criteria' && (k !== 'error' || a.rejected)).map(([k, l]) => [l, a[k]]);
    const sig = a.signal === 'PASS' || a.signal === 'FAIL' ? glyph(a.signal, 3.5) : '', who = moverOf(a);
    return `<li class="ev ev-${r.kind}${a.rejected ? ' ev-rejected' : ''}"><time>${hm(r.t)}</time>
        <span class="ev-sig">${sig}${a.signal}${a.rejected ? ' · refused' : ''}</span>
        <span class="ev-move">${a.old_state && a.new_state ? `${label(a.old_state)} → ${enteredWord(a)}` : a.rejected ? 'nothing changed' : esc(a.error || '')}</span>
        <span class="ev-src"${who.as ? TIP.cell(`Signed as ${who.as}`) : ''}>${esc(who.word)}</span>
        ${a.failed_criteria?.length ? `<span class="ev-failed">${a.failed_criteria.map(c => `<em>${esc(c)}</em>`).join('')}</span>` : ''}
        ${prose.length ? `<details data-key="${esc(`r|${a.task_id}|${a.timestamp}|${a.signal}`)}"${opened.has(`r|${a.task_id}|${a.timestamp}|${a.signal}`) ? ' open' : ''}><summary>${prose.map(p => p[0]).join(' · ')}</summary>${prose.map(([k, v]) => `<p><b>${k}</b> ${esc(v)}</p>`).join('')}</details>` : ''}</li>`;
}

// the rows' times are hours: a day's first row stands under its day, unless every row is today's (audit D12)
const today = () => day(Date.now());
const days = (rs, i) => (i ? day(rs[i].t) !== day(rs[i - 1].t) : rs.some(r => day(r.t) !== today()))
    ? `<li class="ev-day">${day(rs[i].t)}</li>` : '';

function head(id, name, node, run, rs) {
    if (id === RUN) return `<summary><span class="ev-node">the run</span><span class="ev-rounds">on no node — the plan's writing, stops, starts, the mode, tech reports</span>
        <time>${rs[0] ? `${day(rs[0].t)} ${hm(rs[0].t)}` : ''}</time></summary>`;
    const rounds = run.rounds[id] || [], fails = rounds.filter(r => r.verdict === 'FAIL'), lastFail = fails.at(-1);
    const last = rounds.at(-1), why = lastFail && `${failingNow(rounds, node?.state) ? 'failing' : 'last FAIL'} (round ${lastFail.n}): ${failedWords(failedOf(run, id, lastFail.failed))}`;
    // one line each, cut at its end: the whole of it on hover
    return `<summary><span class="ev-node"${TIP.cell(name)}>${esc(name)}</span>
        <span class="state-badge ev-state">${esc(stateWord(S.tasks.find(t => t.id === node.id) ?? node))}</span>
        <span class="ev-rounds">${rounds.length ? tally(rounds.length, rounds.length > 1 ? 'rounds' : 'round') + (fails.length ? tally(fails.length, 'failed') : '') : 'no delivery yet'}</span>
        ${why ? `<span class="ev-why${last?.verdict === 'FAIL' ? '' : ' was'}"${TIP.cell(why)}>${esc(why)}</span>` : ''}
        <time>${rs[0] ? `${day(rs[0].t)} ${hm(rs[0].t)}` : ''}</time></summary>`;
}

// What the reader set here outlives the view's redraw — every event of a live run redraws the deck, and a group opened,
// a kind switched off or a search typed was undone a few seconds later (the author, 2026-10-27).
// what a search reads is what a row says, not its record's field names: «fail» found every row by `failed_criteria` (critic)
const said_ = o => o == null ? '' : typeof o === 'object' ? Object.values(o).map(said_).join(' ') : String(o);
// …and a reload: kept per project, as the deck keeps its tab
const KEY = `gfso.events.${PROJECT}`, saved = kept(KEY, JSON.parse) || {};
const save = () => keep(KEY, JSON.stringify({on: [...on], opened: [...opened], query}));
const on = new Set(saved.on || Object.keys(KINDS).filter(k => k !== 'narration')), opened = new Set(saved.opened || []);
let query = saved.query || '', shown = null;

export function render(el, run, nodes, tasks, pipeline = []) {
    const name = run.name, by = streams(run, nodes, pipeline), ids = [...nodes.map(n => n.id), RUN];
    // a kind's count over what is in view: the whole run, or the one node chosen
    const count = (k, sel) => (sel ? [by[sel] || []] : Object.values(by)).reduce((n, rs) => n + rs.filter(r => r.kind === k).length, 0);
    // …a redraw under the reader's typing keeps the box and the caret: each burst of narration took the search away (critic)
    const typing = el.querySelector('.ev-find'), caret = typing === document.activeElement ? typing.selectionStart : null;
    el.innerHTML =`<div class="ev-bar">${Object.keys(KINDS).filter(k => count(k)).map(k => `<button class="ev-chip${on.has(k) ? ' on' : ''}" data-kind="${k}">${k}<b>${count(k)}</b></button>`).join('')}
        <input class="ev-find" type="search" placeholder="find in events…"><span class="ev-only"></span></div><div class="ev-groups"></div>`;
    const box = el.querySelector('.ev-groups'), find = el.querySelector('.ev-find');
    find.value = query;
    if (caret != null) { find.focus(); find.setSelectionRange(caret, caret); }
    // a details opened or closed by the reader is remembered by its key; a node newly selected opens its own group
    box.addEventListener('toggle', e => { const k = e.target.dataset?.key; if (k) e.target.open ? opened.add(k) : opened.delete(k); save(); }, true);
    const draw = () => {
        const q = find.value.trim().toLowerCase(), sel = focus().select;
        if (sel !== shown) { shown = sel; if (sel) opened.add(`g|${sel}`); }
        // a group's time and its place among the newest are its newest row the filter shows: hidden narration (a
        // migration's batch) stamped every group one minute and put the goal's verdict last (critic)
        const kept = Object.fromEntries(ids.map(id => [id, by[id].filter(r => on.has(r.kind) && (!q || said_(r.a || r.p).toLowerCase().includes(q)))]));
        box.innerHTML = ids.filter(id => !sel || id === sel).sort((a, b) => (kept[b][0]?.t || 0) - (kept[a][0]?.t || 0)).map(id => {
            const rs = kept[id];
            if (!rs.length && (q || sel !== id)) return '';
            return `<details class="ev-group" data-key="${esc(`g|${id}`)}"${id === RUN ? '' : ` data-node="${esc(id)}"`}${opened.has(`g|${id}`) ? ' open' : ''}>${head(id, name(id), nodes.find(n => n.id === id), run, rs)}
                <ol><li class="ev ev-cols"><span>time</span><span>signal</span><span>state</span><span>by</span></li>${rs.map((r, i) => days(rs, i) + row(r)).join('')}</ol></details>`;
        }).join('') || '<p class="ev-none">nothing matches</p>';
        el.querySelectorAll('.ev-chip').forEach(c => c.querySelector('b').textContent = count(c.dataset.kind, sel));
        el.querySelector('.ev-only').innerHTML = sel ? `only <b>${esc(name(sel))}</b> <button data-clear>show all</button>` : '';
    };
    el.querySelector('.ev-bar').onclick = e => {
        const k = e.target.dataset.kind;
        if (k) { on.has(k) ? on.delete(k) : on.add(k); e.target.classList.toggle('on'); save(); draw(); }
        if (e.target.matches('[data-clear]')) point('select', null);
    };
    find.oninput = () => { query = find.value; save(); draw(); };
    draw();
    watch((st, key) => key === 'select' && draw(), el);   // before the focus paint: draw rebuilds what paint marks
    bindFocus(box);
}
