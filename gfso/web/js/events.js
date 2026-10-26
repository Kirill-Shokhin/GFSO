// The log as events: grouped by node, newest first, filtered by kind. A group's head says where the
// node stands and, when it has failed, what its last FAIL named — the usual question answered
// without opening anything; one click opens the node's own trail, its narration nested in.
import {esc} from './dom.js';
import {bindFocus, focus, watch, point} from './store.js';
import {hm, glyph} from './draw.js';
import {at, said, roundsLine, failedWords} from './run.js';

const KINDS = {
    verdict: ['PASS', 'FAIL'], delivery: ['DELIVER'], assignment: ['ASSIGN', 'ACCEPT', 'REOPEN'],
    clock: ['TIMEOUT'], dispute: ['CHALLENGE', 'ACCEPT_CHALLENGE', 'REJECT_CHALLENGE', 'BLOCK', 'RESOLVE_BLOCK'],
    close: ['CANCEL', 'CONFIRM_CANCEL'], refused: [], narration: [],
};
// a move the engine refused changed nothing: its own kind, so the column of state moves holds only moves
const signalKind = a => a.rejected ? 'refused' : Object.keys(KINDS).find(k => KINDS[k].includes(a.signal)) || 'assignment';
const day = t => new Date(t).toLocaleDateString(undefined, {day: 'numeric', month: 'short'});

// One stream of rows per node: signals from the audit, narration from the pipeline ("<node>: …").
function streams(run, nodes, pipeline) {
    const ids = new Set(nodes.map(n => n.id)), out = Object.fromEntries(nodes.map(n => [n.id, []]));
    for (const a of run.audit) if (out[a.task_id]) out[a.task_id].push({t: a.t, kind: signalKind(a), a});
    for (const p of pipeline) {
        const {node, text} = said(p.message);
        if (ids.has(node)) out[node].push({t: at(p.ts), kind: 'narration', p: {source: p.source, text}});
    }
    Object.values(out).forEach(rs => rs.sort((x, y) => y.t - x.t));
    return out;
}

function row(r) {
    if (r.p) return `<li class="ev ev-narration"><time>${hm(r.t)}</time><span class="ev-src">${esc(r.p.source)}</span><span class="ev-text">${esc(r.p.text)}</span></li>`;
    const a = r.a, prose = [a.rejected && a.error && ['why refused', a.error], a.reason && ['reason', a.reason], a.justification && ['justification', a.justification], a.result && ['report', a.result]].filter(Boolean);
    const sig = a.signal === 'PASS' || a.signal === 'FAIL' ? glyph(a.signal, 3.5) : '';
    return `<li class="ev ev-${r.kind}${a.rejected ? ' ev-rejected' : ''}"><time>${hm(r.t)}</time>
        <span class="ev-sig">${sig}${a.signal}${a.rejected ? ' · refused' : ''}</span>
        <span class="ev-move">${a.old_state && a.new_state ? `${a.old_state} → ${a.new_state}` : a.rejected ? 'nothing changed' : esc(a.error || '')}</span>
        <span class="ev-src">${esc(a.source || '')}</span>
        ${a.failed_criteria?.length ? `<span class="ev-failed">${a.failed_criteria.map(c => `<em>${esc(c)}</em>`).join('')}</span>` : ''}
        ${prose.length ? `<details><summary>${prose.map(p => p[0]).join(' · ')}</summary>${prose.map(([k, v]) => `<p><b>${k}</b> ${esc(v)}</p>`).join('')}</details>` : ''}</li>`;
}

function head(id, name, node, run, rs) {
    const rounds = run.rounds[id] || [], fails = rounds.filter(r => r.verdict === 'FAIL'), lastFail = fails.at(-1);
    const last = rounds.at(-1);
    return `<summary><span class="ev-node">${esc(name)}</span>
        <span class="state-badge ev-state">${esc(node.state)}</span>
        <span class="ev-rounds">${rounds.length ? roundsLine(rounds) + (last?.verdict ? ` · last ${last.verdict}` : '') : 'no delivery yet'}</span>
        ${lastFail ? `<span class="ev-why${last?.verdict === 'FAIL' ? '' : ' was'}">${last?.verdict === 'FAIL' ? 'failing' : 'last FAIL'} (round ${lastFail.n}): ${esc(failedWords(run, id, lastFail.failed))}</span>` : ''}
        <time>${rs[0] ? `${day(rs[0].t)} ${hm(rs[0].t)}` : ''}</time></summary>`;
}

export function render(el, run, nodes, tasks, pipeline = []) {
    const name = run.name, by = streams(run, nodes, pipeline);
    const order = nodes.map(n => n.id).sort((a, b) => (by[b][0]?.t || 0) - (by[a][0]?.t || 0));
    const on = new Set(Object.keys(KINDS).filter(k => k !== 'narration'));
    el.innerHTML = `<div class="ev-bar">${Object.keys(KINDS).map(k => `<button class="ev-chip${on.has(k) ? ' on' : ''}" data-kind="${k}">${k}</button>`).join('')}
        <input class="ev-find" type="search" placeholder="find in events…"><span class="ev-only"></span></div><div class="ev-groups"></div>`;
    const box = el.querySelector('.ev-groups'), find = el.querySelector('.ev-find');
    const draw = () => {
        const q = find.value.trim().toLowerCase(), sel = focus().select;
        box.innerHTML = order.filter(id => !sel || id === sel).map(id => {
            const rs = by[id].filter(r => on.has(r.kind) && (!q || JSON.stringify(r.a || r.p).toLowerCase().includes(q)));
            if (!rs.length && (q || sel !== id)) return '';
            return `<details class="ev-group" data-node="${esc(id)}"${sel === id ? ' open' : ''}>${head(id, name(id), nodes.find(n => n.id === id), run, by[id])}
                <ol><li class="ev ev-cols"><span>time</span><span>signal</span><span>state</span><span>by</span></li>${rs.map(row).join('')}</ol></details>`;
        }).join('') || '<p class="ev-none">nothing matches</p>';
        el.querySelector('.ev-only').innerHTML = sel ? `only <b>${esc(name(sel))}</b> <button data-clear>show all</button>` : '';
    };
    el.querySelector('.ev-bar').onclick = e => {
        const k = e.target.dataset.kind;
        if (k) { on.has(k) ? on.delete(k) : on.add(k); e.target.classList.toggle('on'); draw(); }
        if (e.target.matches('[data-clear]')) point('select', null);
    };
    find.oninput = draw;
    draw();
    watch((st, key) => key === 'select' && draw(), el);   // before the focus paint: draw rebuilds what paint marks
    bindFocus(box);
}
