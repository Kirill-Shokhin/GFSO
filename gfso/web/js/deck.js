// The run deck under the graph: a strip that always says what is running now and what it has cost,
// and four views of the run read from one model — its course in time, its progress by criteria, its
// cost, its events. It replaces the observation console: the same feed, read as the run it describes.
import {$, esc} from './dom.js';
import {getJSON, singleFlight} from './api.js';
import {S} from './state.js';
import {point} from './store.js';
import {buildRun, said, blockers, atWork} from './run.js';
import {dur, trim} from './draw.js';
import * as timeline from './timeline.js';
import * as progress from './progress.js';
import * as cost from './cost.js';
import * as work from './work.js';
import * as events from './events.js';

const VIEWS = {timeline, progress, cost, work, events}, KEY = 'gfso.deck';
const isTick = m => / tokens · \d+s$/.test(m);         // live token ticks: shown in place, never persisted
const pref = (() => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } })();
const keep = () => { try { localStorage.setItem(KEY, JSON.stringify(pref)); } catch (e) { /* per-viewer nicety */ } };
let run = null, pipeline = [], verdicts = {}, view = VIEWS[pref.view] ? pref.view : 'timeline';
const ticks = new Map();                               // `source|node` → {node, source, msg, t}

// The strip: the nodes in consented work or awaiting a verdict now — by their state, since an executor
// may be a person or a process on another server — each pulsing when THIS server's registry has a process
// on it (an executor running tools sends no ticks), its freshest tick beside it; then what waits on the issuer.
function strip() {
    const mine = S.inflight.filter(w => w.project === S.project), now = Date.now() / 1000;
    const work = atWork(run, S.tasks), busy = S.tasks.filter(t => work.has(t.id)), name = t => trim(t.name || t.id, 26);
    // waiting on the issuer's decision — a verdict being validated is work, not a wait, so VALIDATING is left out
    const issuer = S.tasks.filter(t => run?.waits[t.id]?.owes === 'issuer' && t.state !== 'VALIDATING');
    const live = busy.map(t => {
        const w = mine.find(w => w.task_id === t.id), tk = [...ticks.values()].find(k => k.node === t.id);
        const what = t.state === 'VALIDATING' ? 'validating' : t.state === 'REWORKING' ? 'reworking' : 'executing';
        return `<button class="dk-live${w ? ' on' : ''}" data-node="${esc(t.id)}" title="${esc(tk?.msg || (w ? w.verb : 'no process on this server'))}"><i></i>${esc(name(t))}`
            + `<span>${what}${w ? ' · ' + dur((now - w.since) * 1e3) : ''}</span></button>`;
    });
    // at most three chips, the rest counted: what waits and what it cost must stay on the line however much runs
    const more = live.length > 3 ? `<span class="dk-more" title="${esc(busy.slice(3).map(name).join('\n'))}">+${live.length - 3}</span>` : '';
    return (live.length ? `<span class="dk-now" title="a node with a session open, or a leaf in a working state — a parent EXECUTING waits on its parts and is not counted">${live.length} at work</span><span class="dk-chips">${live.slice(0, 3).join('')}${more}</span>`
        : '<span class="dk-now dk-idle">nothing at work</span>')
        // what holds the most back: the producer most nodes wait on, the count beside it
        + (run ? blockers(run.waits).slice(0, 2).map(([id, n]) => { const part = run.waits[id]?.parts.find(p => work.has(p));
            return `<button class="dk-block" data-node="${esc(id)}" title="${n} node${n > 1 ? 's' : ''} queued behind it along Dep — none starts until what it waits on passes">${n} wait on <b>${esc(trim(run.name(id), 24))}</b>`
                + (part ? `<span> ← its part ${esc(trim(run.name(part), 20))} at work</span>` : '') + '</button>'; }).join('') : '')
        + (issuer.length ? `<span class="dk-wait" title="${esc(issuer.map(t => `${name(t)} — ${t.state}`).join('\n'))}">${issuer.length} wait${issuer.length > 1 ? '' : 's'} on the issuer</span>` : '')
        + (run ? `<span class="dk-sum">$${run.cost.total.toFixed(2)} · ${dur(run.clock.span)} run</span>` : '');
}

function paint() {
    const d = $('deck');
    d.classList.toggle('closed', !!pref.closed);
    d.querySelector('.dk-strip').innerHTML = strip();
    d.querySelectorAll('.dk-tab').forEach(b => b.classList.toggle('on', b.dataset.view === view));
    if (!pref.closed && run) VIEWS[view].render(d.querySelector('.dk-view'), run, S.graph.nodes, S.tasks, pipeline);
}

export const refreshDeck = singleFlight(async () => {
    try {
        const [audit, usage, pl] = await Promise.all([getJSON('/api/audit'), getJSON('/api/usage?detail=true'), getJSON('/api/pipeline?limit=2000')]);
        pipeline = pl;
        await currentVerdicts(audit);
        run = S.run = buildRun({nodes: S.graph.nodes, edges: S.graph.edges, tasks: S.tasks, audit, calls: usage.calls_detail || [], pipeline, verdicts});
    } catch (e) { run = S.run = null; }
    paint();
});

// Each node's CURRENT verdict per criterion — the log keeps only what a FAIL named, and an undecidable
// criterion is ⊥, not pass. Re-read only for a node whose verdicts changed since the last read.
async function currentVerdicts(audit) {
    const seen = {};
    for (const a of audit) if (!a.rejected && (a.signal === 'PASS' || a.signal === 'FAIL')) seen[a.task_id] = (seen[a.task_id] || 0) + 1;
    await Promise.all(Object.entries(seen).filter(([id, n]) => verdicts[id]?.n !== n).map(async ([id, n]) => {
        try { verdicts[id] = {n, ...(await getJSON(`/api/tasks/${encodeURIComponent(id)}/verdict`))}; } catch (e) { /* the log's reading stands */ }
    }));
}

// The deck's first height, when the person has not dragged one: what the graph leaves over at a
// zoom its labels can be read at, within bounds — a wide plan keeps its graph, a small one gives room.
export function suggestHeight(graphNeeds) {
    if (pref.h) return;
    const d = $('deck'), stage = d.parentElement.clientHeight;
    d.style.height = `${Math.round(Math.max(stage * 0.25, Math.min(stage * 0.42, stage - graphNeeds)))}px`;
}

let soon = null;
const later = () => (clearTimeout(soon), soon = setTimeout(refreshDeck, 1500));

export function onPipeline(d) {
    const node = said(d.msg).node;
    if (isTick(d.msg)) ticks.set(`${d.source}|${node}`, {node, source: d.source, msg: d.msg, t: Date.now()});
    else later();
    $('deck').querySelector('.dk-strip').innerHTML = strip();
}
export const onInflight = () => { $('deck').querySelector('.dk-strip').innerHTML = strip(); };

export function mountDeck() {
    const d = $('deck');
    d.innerHTML = `<div class="dk-grip" title="drag to resize"></div><div class="dk-head">
        <nav>${Object.keys(VIEWS).map(k => `<button class="dk-tab" data-view="${k}">${k}</button>`).join('')}</nav>
        <div class="dk-strip"></div><button class="dk-fold" title="fold / unfold">▾</button></div><div class="dk-body"><div class="dk-view"></div></div>`;
    if (pref.h) d.style.height = `${pref.h}px`;
    d.querySelector('nav').onclick = e => {
        const v = e.target.dataset.view;
        if (!v) return;
        view = pref.view = v; pref.closed = false; keep(); paint();
    };
    d.querySelector('.dk-fold').onclick = () => { pref.closed = !pref.closed; keep(); paint(); };
    d.querySelector('.dk-strip').onclick = e => { const n = e.target.closest('[data-node]')?.dataset.node; if (n) point('select', n); };
    d.querySelector('.dk-grip').onmousedown = e => {
        const y0 = e.clientY, h0 = d.offsetHeight;
        const move = m => { d.style.height = `${Math.max(120, Math.min(innerHeight * 0.8, h0 + y0 - m.clientY))}px`; };
        const up = () => { removeEventListener('mousemove', move); removeEventListener('mouseup', up); pref.h = d.offsetHeight; keep(); paint(); };
        addEventListener('mousemove', move); addEventListener('mouseup', up);
    };
    let w = 0;
    new ResizeObserver(([e]) => { if (Math.abs(e.contentRect.width - w) > 4) { w = e.contentRect.width; if (run) paint(); } }).observe(d);
    setInterval(() => { for (const [k, v] of ticks) if (v.t < Date.now() - 12e3) ticks.delete(k); }, 5e3);
    setInterval(refreshDeck, 30e3);                     // the ledger is written when a call ends: re-read it now and then
}
