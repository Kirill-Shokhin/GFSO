// The log as events: grouped by node, newest first, filtered by kind. A group's head says where the
// node stands and, when it has failed, what its last FAIL named — the usual question answered
// without opening anything; one click opens the node's own trail, its narration nested in.
import {esc} from './dom.js';
import {bindFocus, focus, watch, point} from './store.js';
import {glyph} from './draw.js';
import {hm, day} from './fmt.js';
import {at, said, failedOf} from './run.js';
import {roundsLine, failedWords, TIP} from './hints.js';
import {CARRIED} from './vocab.js';

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
    if (r.p) return `<li class="ev ev-narration${r.kind === 'run' ? ' ev-run' : ''}"><time>${hm(r.t)}</time><span class="ev-src">${esc(r.p.source)}</span><span class="ev-text">${esc(r.p.text)}</span></li>`;
    // what it carried, folded — but its failed criteria, drawn as chips, and an error the move line already says
    const a = r.a, prose = CARRIED.filter(([k]) => a[k] && k !== 'failed_criteria' && (k !== 'error' || a.rejected)).map(([k, l]) => [l, a[k]]);
    const sig = a.signal === 'PASS' || a.signal === 'FAIL' ? glyph(a.signal, 3.5) : '';
    return `<li class="ev ev-${r.kind}${a.rejected ? ' ev-rejected' : ''}"><time>${hm(r.t)}</time>
        <span class="ev-sig">${sig}${a.signal}${a.rejected ? ' · refused' : ''}</span>
        <span class="ev-move">${a.old_state && a.new_state ? `${a.old_state} → ${a.new_state}` : a.rejected ? 'nothing changed' : esc(a.error || '')}</span>
        <span class="ev-src">${esc(a.source || '')}</span>
        ${a.failed_criteria?.length ? `<span class="ev-failed">${a.failed_criteria.map(c => `<em>${esc(c)}</em>`).join('')}</span>` : ''}
        ${prose.length ? `<details data-key="${esc(`r|${a.task_id}|${a.timestamp}|${a.signal}`)}"${opened.has(`r|${a.task_id}|${a.timestamp}|${a.signal}`) ? ' open' : ''}><summary>${prose.map(p => p[0]).join(' · ')}</summary>${prose.map(([k, v]) => `<p><b>${k}</b> ${esc(v)}</p>`).join('')}</details>` : ''}</li>`;
}

function head(id, name, node, run, rs) {
    if (id === RUN) return `<summary><span class="ev-node">the run</span><span class="ev-rounds">on no node — stops, starts, the mode, tech reports</span>
        <time>${rs[0] ? `${day(rs[0].t)} ${hm(rs[0].t)}` : ''}</time></summary>`;
    const rounds = run.rounds[id] || [], fails = rounds.filter(r => r.verdict === 'FAIL'), lastFail = fails.at(-1);
    const last = rounds.at(-1), why = lastFail && `${last?.verdict === 'FAIL' ? 'failing' : 'last FAIL'} (round ${lastFail.n}): ${failedWords(failedOf(run, id, lastFail.failed))}`;
    // one line each, cut at its end: the whole of it on hover
    return `<summary><span class="ev-node"${TIP.cell(name)}>${esc(name)}</span>
        <span class="state-badge ev-state">${esc(node.state)}</span>
        <span class="ev-rounds">${rounds.length ? roundsLine(rounds) + (last?.verdict ? ` · last ${last.verdict}` : '') : 'no delivery yet'}</span>
        ${why ? `<span class="ev-why${last?.verdict === 'FAIL' ? '' : ' was'}"${TIP.cell(why)}>${esc(why)}</span>` : ''}
        <time>${rs[0] ? `${day(rs[0].t)} ${hm(rs[0].t)}` : ''}</time></summary>`;
}

// What the reader set here outlives the view's redraw — every event of a live run redraws the deck, and a group opened,
// a kind switched off or a search typed was undone a few seconds later (the author, 2026-10-27).
const on = new Set(Object.keys(KINDS).filter(k => k !== 'narration')), opened = new Set();
let query = '', shown = null;

export function render(el, run, nodes, tasks, pipeline = []) {
    const name = run.name, by = streams(run, nodes, pipeline), ids = [...nodes.map(n => n.id), RUN];
    el.innerHTML = `<div class="ev-bar">${Object.keys(KINDS).map(k => `<button class="ev-chip${on.has(k) ? ' on' : ''}" data-kind="${k}">${k}</button>`).join('')}
        <input class="ev-find" type="search" placeholder="find in events…"><span class="ev-only"></span></div><div class="ev-groups"></div>`;
    const box = el.querySelector('.ev-groups'), find = el.querySelector('.ev-find');
    find.value = query;
    // a details opened or closed by the reader is remembered by its key; a node newly selected opens its own group
    box.addEventListener('toggle', e => { const k = e.target.dataset?.key; if (k) e.target.open ? opened.add(k) : opened.delete(k); }, true);
    const draw = () => {
        const q = find.value.trim().toLowerCase(), sel = focus().select;
        if (sel !== shown) { shown = sel; if (sel) opened.add(`g|${sel}`); }
        // a group's time and its place among the newest are its newest row the filter shows: hidden narration (a
        // migration's batch) stamped every group one minute and put the goal's verdict last (critic)
        const kept = Object.fromEntries(ids.map(id => [id, by[id].filter(r => on.has(r.kind) && (!q || JSON.stringify(r.a || r.p).toLowerCase().includes(q)))]));
        box.innerHTML = ids.filter(id => !sel || id === sel).sort((a, b) => (kept[b][0]?.t || 0) - (kept[a][0]?.t || 0)).map(id => {
            const rs = kept[id];
            if (!rs.length && (q || sel !== id)) return '';
            return `<details class="ev-group" data-key="${esc(`g|${id}`)}"${id === RUN ? '' : ` data-node="${esc(id)}"`}${opened.has(`g|${id}`) ? ' open' : ''}>${head(id, name(id), nodes.find(n => n.id === id), run, rs)}
                <ol><li class="ev ev-cols"><span>time</span><span>signal</span><span>state</span><span>by</span></li>${rs.map(row).join('')}</ol></details>`;
        }).join('') || '<p class="ev-none">nothing matches</p>';
        el.querySelector('.ev-only').innerHTML = sel ? `only <b>${esc(name(sel))}</b> <button data-clear>show all</button>` : '';
    };
    el.querySelector('.ev-bar').onclick = e => {
        const k = e.target.dataset.kind;
        if (k) { on.has(k) ? on.delete(k) : on.add(k); e.target.classList.toggle('on'); draw(); }
        if (e.target.matches('[data-clear]')) point('select', null);
    };
    find.oninput = () => { query = find.value; draw(); };
    draw();
    watch((st, key) => key === 'select' && draw(), el);   // before the focus paint: draw rebuilds what paint marks
    bindFocus(box);
}
