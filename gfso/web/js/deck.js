// The run deck under the graph: a strip that always says what is running now and what it has cost,
// and four views of the run read from one model — its course in time, its progress by criteria, its
// cost, its events. It replaces the observation console: the same feed, read as the run it describes.
import {$, esc} from './dom.js';
import {frame, TAB, STRIP, doing} from './hints.js';
import {S, procs, kept, keep} from './state.js';
import {nameOf} from './vocab.js';
import {point, release, forgetBrought} from './store.js';
import {said, blockers, runNow, failingNow, PROC_KIND, byRole} from './run.js';
import {dur, trim, money, NOT_REPORTED, plural} from './fmt.js';
import {beat} from './draw.js';
import * as timeline from './timeline.js';
import * as progress from './progress.js';
import * as cost from './cost.js';
import * as work from './work.js';
import * as events from './events.js';

// Each tab is named by the question it answers, so two views that both show money are not read as one:
// `spend` is where the money and time went (by node, level, role), `models` is who did the work.
const VIEWS = {timeline, progress, spend: cost, models: work, events}, KEY = 'gfso.deck';
const isTick = m => / tokens · \d+s$/.test(m);         // live token ticks: shown in place, never persisted
const pref = kept(KEY, JSON.parse) || {}, save = () => keep(KEY, JSON.stringify(pref));
let view = VIEWS[pref.view] ? pref.view : 'timeline';
const ticks = new Map();                               // `source|node` → {node, source, msg, t}

// The strip: the nodes in consented work or awaiting a verdict now — by their state, since an executor
// may be a person or a process on another server — each pulsing when THIS server's registry has a process
// on it (an executor running tools sends no ticks), its freshest tick beside it; then what waits on the issuer.
// …and any node THIS server has a process on is at work, whatever its state says: a plan being authored over an
// offered root read "nothing at work" while the system worked (a live run, 2026-10-25). The process names the work.
// What runs now is the run's one reading (run.js `runNow`); before the run is read, the same rule over the registry.
const doingOf = w => doing(w.verb, PROC_KIND[w.verb]);
function strip() {
    const run = S.run, at = run?.now ?? runNow(S.tasks, procs()), mine = at.procs, now = Date.now() / 1000;
    const work = at.work, name = t => trim(nameOf(t), 26), runs = t => !!at.on(t.id);
    // what a process runs on first: a session hidden under "+2" behind the leaves it carries told nothing (critic)
    const busy = S.tasks.filter(t => work.has(t.id)).sort((a, b) => runs(b) - runs(a));
    // waiting on the issuer's decision — a verdict being validated is work, not a wait, so VALIDATING is left out
    const issuer = S.tasks.filter(t => run?.waits[t.id]?.decides === 'issuer' && !runs(t));
    const live = busy.map(t => {
        const w = at.on(t.id), tk = [...ticks.values()].find(k => k.node === t.id), [top, by] = w ? [] : at.carrier(t.id);
        const what = w ? doingOf(w) : doing(t.state);
        return `<button class="dk-live${w ? ' on' : ''}" data-node="${esc(t.id)}"${STRIP.live(nameOf(t), tk?.msg || (w ? STRIP.running(w.verb) : by ? STRIP.carried(nameOf(S.tasks.find(x => x.id === top)), by.verb) : STRIP.idle))}><i${beat()}></i><em>${esc(name(t))}</em>`
            + `<span>${what}${w ? ' · ' + dur((now - w.since) * 1e3) : ''}</span></button>`;
    });
    // a process on no node drawn yet — the goal's own plan being authored before its root exists — is work too
    const drawn = new Set(S.tasks.map(t => t.id));
    for (const w of mine.filter(w => !w.task_id || !drawn.has(w.task_id)))
        live.push(`<span class="dk-live on"${STRIP.live('The goal', STRIP.running(w.verb))}><i${beat()}></i><em>the goal</em>`
            + `<span>${doingOf(w)} · ${dur((now - w.since) * 1e3)}</span></span>`);
    // as many chips as the line holds, the rest counted (`drawStrip`): what waits and what it cost stay on the line
    const more = '<span class="dk-more"></span>';
    // A STOPPED RUN RUNS NOTHING: its nodes still hold their working states, and the strip read "2 at work" over a run
    // with no process left (a live run, 2026-10-25) — said as held, not as work
    // …under AUTO only, where the system holds every node: a stop pauses the system, never a person's own work (critic)
    const held = S.runState?.state === 'stopped' && !mine.length && S.graph.mode?.mode === 'auto';
    const now_ = held && live.length
        ? `<span class="dk-now dk-idle"${STRIP.held}>stopped · ${live.length} held mid-work</span>`
          + `<span class="dk-chips">${busy.map(t => `<button class="dk-live" data-node="${esc(t.id)}"${STRIP.live(nameOf(t))}><i${beat()}></i><em>${esc(name(t))}</em><span>${t.state.toLowerCase()}</span></button>`).join('')}${more}</span>`
        // the sessions are said only where they are not one per node at work (one carrying a whole part, a node worked
        // elsewhere): «1 at work · 1 session» read as the line repeating itself (the author, 2026-10-27)
        : live.length ? `<span class="dk-now">${live.length} at work${mine.length && mine.length !== live.length ? ` · ${plural(mine.length, 'session')}` : ''}</span><span class="dk-chips">${live.join('')}${more}</span>`
        : '<span class="dk-now dk-idle">nothing at work</span>';
    // …and what waits on what is said whether the run runs or is held
    // sent back NOW: the last round failed and the node is neither closed nor escalated (the issuer's wait says that one) —
    // the red rounds badge's rule; a count of every FAIL ever never went away on a green run (critic)
    const state = id => S.tasks.find(t => t.id === id)?.state;
    const back = run ? Object.entries(run.rounds).filter(([id, rs]) => failingNow(rs, state(id)))
        .map(([id, rs]) => [id, rs.filter(r => r.verdict === 'FAIL').length]).sort((x, y) => y[1] - x[1]) : [];
    return now_
        // what holds the most back: the producer most nodes wait on, the count beside it
        + (run ? blockers(run.waits).slice(0, 2).map(([id, n]) => { const part = run.waits[id]?.parts.find(p => work.has(p));
            const users = Object.entries(run.waits).filter(([, w]) => w.deps.includes(id)).map(([u]) => run.name(u));
            return `<button class="dk-block" data-node="${esc(id)}"${STRIP.block(n, run.name(id), users)}>${n} wait on <b>${esc(trim(run.name(id), 24))}</b>`
                + (part ? `<span> ← its part ${esc(trim(run.name(part), 20))} at work</span>` : '') + '</button>'; }).join('') : '')
        + (issuer.length ? `<span class="dk-wait"${STRIP.issuer(issuer.map(t => `${name(t)} — ${t.state}`))}>${STRIP.onIssuer(issuer.length)}</span>` : '')
        // what is sent back now: its marks sit in the timeline below the fold (a newcomer reading the page mid-run could not
        // tell anything had failed, 2026-10-26); the hover counts each one's FAILs so far
        + (back.length ? `<button class="dk-block" data-node="${esc(back[0][0])}"${STRIP.back(back.map(([id, n]) => `${run.name(id)} — ${plural(n, 'FAIL')}`))}>${STRIP.sentBack(back.length)}${back.length === 1 ? `: ${esc(trim(run.name(back[0][0]), 20))}` : ''}</button>` : '')
        // a session's cost is booked when it ENDS (the CLI reports it then): a running one is said, not guessed
        + (run ? `<span class="dk-sum"${STRIP.spend(byRole(run.cost.byKind), mine.length)}>`
                 + `${(m => m === NOT_REPORTED ? `spend ${m}` : m)(money(run.cost.total, Object.values(run.cost.byKind).reduce((n, p) => n + p.procs, 0), run.cost.unpriced))}`
                 + `${mine.length ? ` + ${mine.length} running` : ''} in ${dur(run.clock.span)}</span>` : '');
}

// The strip drawn, then its chips fitted: those the line holds are shown, the rest counted with their names on hover —
// three at a fixed cap were cut mid-word, their state with them, on 1280 px beside the panel.
function drawStrip() {
    const box = $('deck').querySelector('.dk-strip');
    box.innerHTML = strip();
    const chips = box.querySelector('.dk-chips'), more = chips?.querySelector('.dk-more');
    if (!chips) return;
    // fitted while only the chips give way, each down to a name still read (`.fit`): shrunk without a floor, five
    // processes read «S…», «the …», a node lost to its verb (1440 px, a live moment); at full width one chip stood beside
    // 250 px of nothing (critic). One chip left that still does not fit is cut like the rest of the line.
    const all = [...chips.querySelectorAll('.dk-live')], gone = [];
    const over = () => [chips, box, ...chips.querySelectorAll('.dk-live')].some(e => e.scrollWidth > e.clientWidth + 1);
    box.classList.add('fit');
    while (all.length > 1 && over()) gone.unshift(all.pop()), gone[0].remove(), more.textContent = `+${gone.length}`;
    if (over()) box.classList.remove('fit');
    if (gone.length) more.outerHTML = `<span class="dk-more"${STRIP.more(gone.map(c => `${c.dataset.tip.split('\n')[0]} — ${c.querySelector('span').textContent}`))}>+${gone.length}</span>`;
}

// the deck drawn from the run as last read (model.js loadRun)
export function paint() {
    const d = $('deck');
    d.classList.toggle('closed', !!pref.closed);
    drawStrip();
    d.querySelectorAll('.dk-tab').forEach(b => b.classList.toggle('on', b.dataset.view === view));
    const run = S.run, el = d.querySelector('.dk-view'), drawn = pref.closed || !run ? null : view;
    release(el);
    if (el._drawn !== drawn) forgetBrought(el), el._drawn = drawn;   // a view opened brings the selection again
    if (!pref.closed && run) VIEWS[view].render(el, run, S.graph.nodes, S.tasks, S.pipeline);
}


// The deck's first height, when the person has not dragged one: what the graph leaves over at a
// zoom its labels can be read at, within bounds — a wide plan keeps its graph, a small one gives room.
export function suggestHeight(graphNeeds) {
    if (pref.h) return;
    const d = $('deck'), stage = d.parentElement.clientHeight;
    d.style.height = `${Math.round(Math.max(stage * 0.25, Math.min(stage * 0.42, stage - graphNeeds)))}px`;
}

// a narration line: a live token tick is shown in place; anything else is news the run should be read again for (true)
export function onPipeline(d) {
    const node = said(d.msg).node, tick = isTick(d.msg);
    if (tick) ticks.set(`${d.source}|${node}`, {node, source: d.source, msg: d.msg, t: Date.now()});
    drawStrip();
    return !tick;
}
export const onInflight = drawStrip;

export function mountDeck() {
    const d = $('deck');
    d.innerHTML = `<div class="dk-grip"${frame('grip')}></div><div class="dk-head">
        <nav>${Object.keys(VIEWS).map(k => `<button class="dk-tab" data-view="${k}"${TAB[k]}>${k}</button>`).join('')}</nav>
        <div class="dk-strip"></div><button class="dk-fold"${frame('fold')}>▾</button></div><div class="dk-body"><div class="dk-view"></div></div>`;
    if (pref.h) d.style.height = `${pref.h}px`;
    d.querySelector('nav').onclick = e => {
        const v = e.target.dataset.view;
        if (!v) return;
        // the open tab pressed again folds the deck; any tab unfolds it (author, 2026-10-25)
        pref.closed = v === view && !pref.closed;
        view = pref.view = v; save(); paint();
    };
    d.querySelector('.dk-fold').onclick = () => { pref.closed = !pref.closed; save(); paint(); };
    d.querySelector('.dk-strip').onclick = e => { const n = e.target.closest('[data-node]')?.dataset.node; if (n) point('select', n); };
    // …by a pointer of any kind: a finger on a phone drags it as a mouse does on a desk (it took a mouse only)
    d.querySelector('.dk-grip').onpointerdown = e => {
        const y0 = e.clientY, h0 = d.offsetHeight;
        const move = m => { d.style.height = `${Math.max(120, Math.min(innerHeight * 0.8, h0 + y0 - m.clientY))}px`; };
        const up = () => { removeEventListener('pointermove', move); removeEventListener('pointerup', up); pref.h = d.offsetHeight; save(); paint(); };
        addEventListener('pointermove', move); addEventListener('pointerup', up);
    };
    let w = 0;
    new ResizeObserver(([e]) => { if (Math.abs(e.contentRect.width - w) > 4) { w = e.contentRect.width; if (S.run) paint(); } }).observe(d);
    setInterval(() => { for (const [k, v] of ticks) if (v.t < Date.now() - 12e3) ticks.delete(k); }, 5e3);
}
