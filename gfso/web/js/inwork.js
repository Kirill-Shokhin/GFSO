// IN WORK, by stream: what the log holds in work under each part of the view's top — a node at the deepest level that is
// worked, who holds it, its state, since when, the same whoever works it (the author, 11-15: «как из ui
// понимать над чем вообще идет работа?»). Read from the log alone, it holds through a restart and a closed console.
import {esc, tally, since, morph} from './dom.js';
import {nowOf, stateWord, viewProcs, inWorkOf} from './state.js';
import {nameOf, cancelled, terminal} from './vocab.js';
import {hover} from './hints.js';
import {ancestorsIn, childrenOf, isRoot} from './tree.js';
import {clockAt} from './fmt.js';
import {beat} from './draw.js';
import {point} from './store.js';
import {firstTap} from './tip.js';

export function render(el, run, nodes, tasks) {
    const top = tasks.find(isRoot), up = ancestorsIn(tasks), now = nowOf(), by = Object.fromEntries(tasks.map(t => [t.id, t]));
    // before the goal's root exists only its plan can be in work: the strip's «the goal» chip, said here too (critic)
    if (!top) return void morph(el, `<div class="pn-meta">${viewProcs().length ? "The goal's plan is being authored; no node exists yet" : 'Nothing in work'}</div>`);
    // a row's stream: the part of the top it lies under; the top itself in work stands as its own
    const streamOf = id => [id, ...up(id)].find(x => by[x]?.parent_id === top.id) ?? top.id;
    // …owed by the node's real issuer: a part's top stands parentless in the view's tree and read as the goal's (critic)
    const rows = inWorkOf(tasks), groups = {};
    // …a part in work with no worked part under it stands among the top's own rows: one header a leaf over its one row,
    // its own name twice, read as noise inside a part of leaves (critic)
    for (const r of rows) { const s = streamOf(r.t.id); (groups[s === r.t.id ? top.id : s] ??= []).push(r); }
    // one mark for whatever is in work, a session of this server or a node someone took (the author, 11-18)
    const row = r => { const path = up(r.t.id).slice(0, -2).reverse().map(x => nameOf(by[x]));
        return `<button class="iw-row on" data-node="${esc(r.t.id)}"><i${beat()}></i><em>${esc(nameOf(r.t))}`
            + (path.length ? `<small>${esc(path.join(' › '))}</small>` : '') + '</em>'
            + `<span>${esc(r.holder || '—')}</span><span>${esc(stateWord(r.t))}</span>`
            + `<span${r.since ? hover('Since', clockAt(r.since)) : ''}>${r.since ? since(r.since) : ''}</span></button>`; };
    const order = (a, b) => (b.since ?? 0) - (a.since ?? 0);   // by the log alone, whoever works it (JOINT W2)
    const block = (id, rs = []) => `<section class="iw-s"><h4>${esc(nameOf(by[id]))}${by[id].assignee ? `<span>${esc(by[id].assignee)}</span>` : ''}`
        + `${rs.length ? tally(rs.length, 'in work') : '<span class="iw-none">nothing in work</span>'}</h4>${rs.sort(order).map(row).join('')}</section>`;
    // the parts with work first, those with none named once on one line: a part of a dozen leaves read as a dozen headers
    // «nothing in work» over the one row looked for (critic)
    const parts = childrenOf(tasks, top.id).filter(c => !cancelled(c)), worked = new Set(rows.map(r => r.t.id));
    // …named idle only if open and neither in work itself nor over work: a part listed above stood below as «nothing in work»
    // too, and a finished goal's done parts read as standing idle (critic)
    const idle = parts.filter(c => !groups[c.id] && !worked.has(c.id) && !terminal(c.state));
    morph(el, `<div class="iw">${groups[top.id] ? block(top.id, groups[top.id]) : ''}`
        + parts.filter(c => groups[c.id]).map(c => block(c.id, groups[c.id])).join('')
        + (idle.length ? `<p class="iw-idle"><span class="iw-none">nothing in work</span> ${esc(idle.map(c => nameOf(c)).join(' · '))}</p>` : '')
        + (rows.length || idle.length ? '' : '<span class="iw-none">nothing in work</span>') + '</div>');
    el.onclick = e => { const n = e.target.closest('[data-node]')?.dataset.node; if (n && !firstTap(e)) point('select', n); };
}
