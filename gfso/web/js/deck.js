import {FOCUS} from './api.js';
// The run deck under the graph: a strip that always says what is running now and what it has cost,
// and four views of the run read from one model — its course in time, its progress by criteria, its
// cost, its events. It replaces the observation console: the same feed, read as the run it describes.
import {$, esc, tally, since, lasting, phone} from './dom.js';
import {frame, frameText, TAB, STRIP, doing} from './hints.js';
import {S, nowOf, kept, keep, owedVerdict, whoOwes, inWorkOf, viewTasks, inView, stateWord, viewNodes, viewTree, viewProcs} from './state.js';
import {nameOf, label, working} from './vocab.js';
import {point, release, forgetBrought} from './store.js';
import {firstTap} from './tip.js';
import {said, blockers, failingNow, PROC_KIND, byRole} from './run.js';
import {dur, clockAt, trim, money, plural} from './fmt.js';
import {beat} from './draw.js';
import * as timeline from './timeline.js';
import * as progress from './progress.js';
import * as cost from './cost.js';
import * as work from './work.js';
import * as events from './events.js';
import * as resources from './resources.js';
import * as inwork from './inwork.js';

// Each tab is named by the question it answers, so two views that both show money are not read as one:
// `spend` is where the money and time went (by node, level, role), `models` is who did the work.
const SESSIONS = new Set(['spend', 'models', 'resources']);
const VIEWS = {'in work': inwork, timeline, progress, spend: cost, models: work, events, resources}, KEY = 'gfso.deck';
const isTick = m => / tokens · \d+s$/.test(m);         // live token ticks: shown in place, never persisted
const pref = kept(KEY, JSON.parse) || {}, save = () => keep(KEY, JSON.stringify(pref));
// …a first look opens on what is in work: on a graph people hold the timeline was all but empty (critic)
let view = VIEWS[pref.view] ? pref.view : 'in work';
const ticks = new Map();                               // `source|node` → {node, source, msg, t}

// The strip: the nodes in consented work or awaiting a verdict now — by their state, since an executor
// may be a person or a process on another server — each pulsing when THIS server's registry has a process
// on it (an executor running tools sends no ticks), its freshest tick beside it; then what waits on the issuer.
// …and any node THIS server has a process on is at work, whatever its state says: a plan being authored over an
// offered root read "nothing at work" while the system worked (a live run, 2026-10-25). The process names the work.
// What runs now is the run's one reading (run.js `runNow`); before the run is read, the same rule over the registry.
const doingOf = w => doing(w.verb, PROC_KIND[w.verb]);
function strip() {
    const run = S.run, at = nowOf(), mine = viewProcs();
    // …with no run read at all, only the server's processes say what runs: states alone said «at work» beside Stopped (critic)
    const work = run ? at.work : new Set(mine.map(w => w.task_id)), name = t => trim(nameOf(t), 26), runs = t => at.lit(t.id);
    // waiting on the issuer's decision — a verdict being validated is work, not a wait, so VALIDATING is left out…
    // …unless no process validates it and its issuer is a person: then the delivery waits on that person's verdict
    // (§12.1: "one wait on the issuer"), and outside both lists it vanished from the strip (critic)
    const owed = t => owedVerdict(t, at);
    // IN WORK by the log (run.js `inWork`), the latest taken first, whoever works it — what this server runs is told by the
    // chip's tip and the timeline, never by the order (JOINT in-work rework 11-18, W2/W3)
    // …one reading with the list the count opens (inwork.js): the count and the list say the same nodes (critic)
    const held = Object.fromEntries((run ? inWorkOf(viewTasks()) : []).map(h => [h.t.id, h]));
    const busy = viewTasks().filter(t => (run ? held[t.id] : work.has(t.id)) && !owed(t))
        .sort((a, b) => run ? (held[b.id]?.since ?? 0) - (held[a.id]?.since ?? 0) : runs(b) - runs(a));   // by the log alone (JOINT W2)
    const issuer = viewTasks().filter(t => (run?.waits[t.id]?.decides === 'issuer' || owed(t)) && !runs(t));
    const live = busy.map(t => {
        const w = at.on(t.id), tk = [...ticks.values()].find(k => k.node === t.id), [top, by] = w ? [] : at.carrier(t.id);
        // the chip says the log's — who holds it, since when — whoever works it; what this server runs is its tip (JOINT W3);
        // a node no one took that a session acts on (a consent, the issuer's turn, a plan) says the act: no holder to name
        const h = held[t.id], taken = h && working(t.state), k = !w && !by && h,
              what = taken ? esc(h.holder || stateWord(t).toLowerCase()) : w ? doingOf(w) : doing(t.state);
        return `<button class="dk-live on" data-node="${esc(t.id)}" data-k="live|${esc(t.id)}"${w && taken ? ` data-run="${esc(doingOf(w))}"` : ''}${STRIP.live(nameOf(t), tk?.msg || (w ? STRIP.running(clockAt(w.since * 1e3), PROC_KIND[w.verb], doingOf(w)) : by ? STRIP.carried(nameOf(S.tasks.find(x => x.id === top)), doingOf(by)) : k ? STRIP.held(k.holder, stateWord(t), k.since && clockAt(k.since)) : STRIP.idle))}><i${beat()}></i><em>${esc(name(t))}</em>`
            + `<span>${what}${taken && h.since ? `<b class="dk-age">${since(h.since)}</b>` : w ? `<b class="dk-age">${since(w.since * 1e3)}</b>` : ''}</span></button>`;
    });
    // a process on no node drawn yet — the goal's own plan being authored before its root exists — is work too
    const drawn = new Set(S.tasks.map(t => t.id));
    for (const w of mine.filter(w => !w.task_id || !drawn.has(w.task_id)))
        live.push(`<span class="dk-live on"${STRIP.live('The goal', STRIP.running(clockAt(w.since * 1e3), PROC_KIND[w.verb], doingOf(w)))}><i${beat()}></i><em>the goal</em>`
            + `<span>${doingOf(w)}<b class="dk-age">${since(w.since * 1e3)}</b></span></span>`);
    // as many chips as the line holds, the rest counted (`drawStrip`): what waits and what it cost stay on the line
    const more = '<span class="dk-more"></span>';
    // the sessions are said only where they are not one per node at work (one carrying a whole part, a node worked
    // elsewhere): «1 at work · 1 session» read as the line repeating itself (the author, 2026-10-27)
    // …the count opens the whole list, by stream (inwork.js)
    const now_ = live.length ? `<span class="dk-now${live.length === 1 && mine.length <= 1 ? ' dk-one' : ''}" data-open="in work"${STRIP.list}>${tally(live.length, 'in work')}${mine.length && mine.length !== live.length ? tally(mine.length, mine.length > 1 ? 'sessions' : 'session') : ''}</span><span class="dk-chips">${live.join('')}${more}</span>`
        // …and before the log is read a graph held by people has no process to tell by: «Nothing in work» stood there for
        // seconds over 34 in work on a phone through a tailnet (critic, 2026-11-17) — it says it is reading instead
        : !run && viewTasks().length ? '<span class="dk-now dk-idle">reading what is in work…</span>'
        : '<span class="dk-now dk-idle">Nothing in work</span>';
    // sent back NOW: the last round failed and the node is neither closed nor escalated (the issuer's wait says that one) —
    // the red rounds badge's rule; a count of every FAIL ever never went away on a green run (critic)
    const state = id => S.tasks.find(t => t.id === id)?.state;
    const back = run ? Object.entries(run.rounds).filter(([id, rs]) => inView(id) && failingNow(rs, state(id)))
        .map(([id, rs]) => [id, rs.filter(r => r.verdict === 'FAIL').length]).sort((x, y) => y[1] - x[1]) : [];
    // what is sent back now: its marks sit in the timeline below the fold (a newcomer reading the page mid-run could not
    // tell anything had failed, 2026-10-26); the hover counts each one's FAILs so far
    const red = back.length ? `<button class="dk-block" data-node="${esc(back[0][0])}" data-k="back|${esc(back[0][0])}"${STRIP.back(back.map(([id, n]) => `${run.name(id)}: ${plural(n, 'FAIL')}`))}>${tally(back.length, 'sent back')}${back.length === 1 ? `<b>${esc(trim(run.name(back[0][0]), 20))}</b>` : ''}</button>` : '';
    // what is red comes first: the line scrolls, and what stands past its width is behind its fade — one session's chip took
    // a phone's whole line, and at 1024 with a panel open the red stood past the edge under what was at work (critics)
    return red + now_
        // …its tip names each whole under its state's word, never cut to a chip's width nor a raw state by a dash (audit B9)
        + (issuer.length ? `<span class="dk-wait"${STRIP.issuer(issuer.length, [...new Set(issuer.map(t => label(t.state)))]
            .flatMap(word => [`${word}:`, ...issuer.filter(t => label(t.state) === word).map(t => `– ${nameOf(t)}${whoOwes(t, 'issuer') ? ` (${whoOwes(t, 'issuer')})` : ''}`)]))}>${tally(issuer.length, 'on the issuer')}</span>` : '')
        // what holds the most back: the producer most nodes wait on, the count beside it
        + (run ? blockers(run.waits).map(([id, held]) => [id, held.filter(inView)]).filter(([, held]) => held.length).slice(0, 2).map(([id, held]) => { const part = run.waits[id]?.parts.find(p => work.has(p));
            // the count is every node held, so the tip lists every one: the direct users first, the rest through them
            const direct = held.filter(u => run.waits[u].deps.includes(id)), through = held.filter(u => !direct.includes(u));
            return `<button class="dk-block" data-node="${esc(id)}" data-k="wait|${esc(id)}"${STRIP.block(held.length, run.name(id), direct.map(run.name), through.map(run.name))}>${tally(held.length, 'wait on')}<b>${esc(trim(run.name(id), 24))}</b>`
                + (part ? `<span> ← its part ${esc(trim(run.name(part), 20))} at work</span>` : '') + '</button>'; }).join('') : '');
}
// THE RUN'S SUM, in a place of its own at the head's right — never laid over the line, which scrolls beside it. A session's
// cost is booked when it ENDS: the running ones are said on its hover, not as «+N running» beside «N at work», which
// counted the same sessions twice (the author, 2026-10-30)
const sum = () => { const run = S.viewRun || S.run; if (!run) return '';   // the part's own figures in a part's view
    const booked = Object.values(run.cost.byKind).reduce((n, p) => n + p.procs, 0);
    return `<span${STRIP.spend(byRole(run.cost.byKind), viewProcs().filter(w => PROC_KIND[w.verb]).length)}>`
        // …nothing booked yet is no sum: «$0.00 spent» stood under seven minutes of a plan being authored
        + (booked ? tally(money(run.cost.total, booked, run.cost.unpriced), 'spent') : '')
        // …and a run's time only where sessions ran: over a graph people hold it summed their moves' gaps (critic: «2.9h run»)
        + (run.clock.t0 && run.sessions.length ? tally(lasting(run.clock.workedFrom, run.clock.worked), 'run') : '') + '</span>'; };

// THE LINE SCROLLS IN ITS OWN PLACE, its bar hidden: a soft fade at the edge where more of it lies says there is more, and
// a mouse's wheel moves it sideways (the author, 2026-10-30: «подписи … даже не все влезают и не понятно что там дальше»)
const fades = box => {
    box.classList.toggle('more-r', box.scrollLeft + box.clientWidth < box.scrollWidth - 1);
    box.classList.toggle('more-l', box.scrollLeft > 1);
};

// The strip drawn, then its chips fitted: those the line holds are shown, the rest counted with their names on hover —
// three at a fixed cap were cut mid-word, their state with them, on 1280 px beside the panel.
function drawStrip() {
    const box = $('deck').querySelector('.dk-strip');
    box.innerHTML = strip();
    $('deck').querySelector('.dk-sum').innerHTML = sum();
    requestAnimationFrame(() => { fades(box); fades($('deck').querySelector('.dk-head')); });
    // …from scratch each time: a `.fit` left by a line that had chips held the wait lines at full width once the chips
    // were gone, and pushed the spend out of the strip (1280 px beside the panel)
    box.classList.remove('fit');
    const chips = box.querySelector('.dk-chips'), more = chips?.querySelector('.dk-more');
    if (!chips) return;
    // fitted while only the chips give way, each down to a name still read (`.fit`): shrunk without a floor, five
    // processes read «S…», «the …», a node lost to its verb (1440 px, a live moment); at full width one chip stood beside
    // 250 px of nothing (critic). One chip left that still does not fit is cut like the rest of the line.
    const all = [...chips.querySelectorAll('.dk-live')], gone = [];
    const over = () => [chips, ...chips.querySelectorAll('.dk-live')].some(e => e.scrollWidth > e.clientWidth + 1);
    box.classList.add('fit');
    while (all.length > 1 && over()) gone.unshift(all.pop()), gone[0].remove(), more.textContent = `+${gone.length}`;
    if (over()) box.classList.remove('fit');
    if (gone.length) more.outerHTML = `<span class="dk-more"${STRIP.more(gone.map(c => `${c.dataset.tip.split('\n')[0]}: ${[...c.querySelector('span').childNodes].map(n => n.textContent).join(', ')}${c.dataset.run ? ` — ${c.dataset.run} now` : ''}`))}>+${gone.length}</span>`;   // a session under «+N» still said
}

const TIMED = new Set(['timeline', 'progress']);
// the deck closed by the browser's Back; false when it stands closed
export const foldDeck = () => { if (pref.closed) return false; pref.closed = true; save(); paint(); return true; };
// the deck drawn from the run as last read (model.js loadRun)
export function paint() {
    const d = $('deck');
    d.classList.toggle('closed', !!pref.closed);
    // the fold's tip says what a press does now (audit B13)
    d.querySelector('.dk-fold').dataset.tip = frameText(pref.closed ? 'unfold' : 'fold');
    drawStrip();
    // A TAB ABOUT SESSIONS STANDS ONCE A SESSION HAS RUN: spend, models and resources tell of sessions — their money, their
    // models, their containers — and on a graph people hold, where none ran, they were three empty tabs. The difference is
    // the operation (a session ran here), not the mode (the author, 11-14: «отличие операциональное а не выдуманное»)
    const ran = !!(S.run?.sessions.length || viewProcs().length);
    d.querySelectorAll('.dk-tab').forEach(b => { b.hidden = SESSIONS.has(b.dataset.view) && !ran; });
    if (!ran && SESSIONS.has(view)) view = 'in work';
    d.querySelectorAll('.dk-tab').forEach(b => b.classList.toggle('on', b.dataset.view === view));
    const run = S.viewRun || S.run, el = d.querySelector('.dk-view'), drawn = pref.closed || !run ? null : view;
    release(el);
    const opened = el._drawn !== drawn;
    if (opened) forgetBrought(el), el._drawn = drawn;   // a view opened brings the selection again
    el.style.minWidth = '';
    el.dataset.view = drawn || '';
    // a view opened starts at its top: Events opened 99 px down, its filters and the why-head above the fold (audit D11)
    if (opened) { const box = el.closest('.dk-body'); box.scrollTop = 0; box.scrollLeft = 0; }
    // …over the view's own tree: the run is built over it too (model.js), so a part's tabs are the part's
    if (!pref.closed && run) VIEWS[view].render(el, run, viewNodes(), viewTree(), S.pipeline);
    // a view on the run's time opened on a phone shows its latest first, the legend with it — at its start, a run of hours
    // showed the empty first minutes (audit B11)
    // …the time axis's end at the box's right, not the view's (Progress keeps its coverage table past it)
    // …on a phone or beside a node's panel alike: whenever the axis starts to overflow its box — a view opened so, or a panel
    // opened beside it (critic 2: beside a panel the timeline opened at the run's start, its node's crosses off the screen)
    const axis = TIMED.has(view) && el.querySelector('.pin-left + svg'), was = el._overflow;
    el._overflow = !!axis;
    if (axis && (opened || !was)) { const box = el.closest('.dk-body'); box.scrollLeft += axis.getBoundingClientRect().right - box.getBoundingClientRect().right; }
}


// The deck's first height, when the person has not dragged one: what the graph leaves over at a
// zoom its labels can be read at, within bounds — a wide plan keeps its graph, a small one gives room.
// …and while the stage changes under it (a phone's header filled after the first frame), the deck gives or takes the
// difference within its share, so the canvas the graph was framed on keeps its height: sized once, it kept a height 51 px
// past its share (critic); sized again by the rule, the canvas shrank and the graph re-zoomed under the finger (probe)
const share = () => phone() ? [0.5, 0.6] : [0.25, 0.42];
let stageWas = null;
export function suggestHeight(graphNeeds) {
    if (pref.h) return;
    const d = $('deck'), stage = d.parentElement.clientHeight;
    if (stageWas === null) new ResizeObserver(() => {
        const now = d.parentElement.clientHeight, [lo, hi] = share();
        if (pref.h || document.body.classList.contains('deck-drag') || now === stageWas) return;
        const canvas = stageWas - d.offsetHeight;
        d.style.height = `${Math.round(Math.max(now * lo, Math.min(now * hi, now - canvas)))}px`;
        stageWas = now;
    }).observe(d.parentElement);
    stageWas = stage;
    // …on a phone the deck holds the first screen's answer (what runs, what waits): half of it at least — at a quarter it
    // showed 131 px of body under a graph no fit makes readable (audit E1)
    const [lo, hi] = share();
    d.style.height = `${Math.round(Math.max(stage * lo, Math.min(stage * hi, stage - graphNeeds)))}px`;
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
        <div class="dk-strip"></div><div class="dk-sum"></div><button class="dk-fold"${frame('fold')}>▾</button></div><div class="dk-body"><div class="dk-view"></div></div>`;
    if (pref.h) d.style.height = `${pref.h}px`;
    // THE DECK KEEPS ITS LAYOUT WHILE A NODE'S PANEL IS OPEN: its width with no panel is remembered, and a view laid out by
    // width (Spend's columns, Models' table) keeps it and scrolls sideways — at 1024 Spend restacked to one column and Models
    // squeezed beside the panel (critic, 2026-11-01; the author 2026-10-30: «прокрутки влево вправо не появляется»)
    const main = d.closest('.main');
    new ResizeObserver(() => d.style.setProperty('--deck-free', `${main.clientWidth - 32}px`)).observe(main);
    d.querySelector('nav').onclick = e => {
        const v = e.target.dataset.view;
        if (!v) return;
        // the open tab pressed again folds the deck; any tab unfolds it (author, 2026-10-25)
        pref.closed = v === view && !pref.closed;
        view = pref.view = v; save(); paint();
    };
    d.querySelector('.dk-fold').onclick = () => { pref.closed = !pref.closed; save(); paint(); };
    const line = d.querySelector('.dk-strip');
    line.onclick = e => { const o = e.target.closest('[data-open]')?.dataset.open;
        if (o && !firstTap(e)) { pref.closed = false; view = pref.view = o; save(); return paint(); }
        const n = e.target.closest('[data-node]')?.dataset.node; if (n && !firstTap(e)) point('select', n); };
    // …and so does the head around it, short of room beside a node's panel: the wheel moves the line while it can move, then
    // the head — the run's sum and the fold lay past a 1024 px edge with no way to them by a mouse (critic 5)
    const head = d.querySelector('.dk-head');
    for (const box of [line, head]) box.onscroll = () => fades(box);
    const sideways = e => {
        const box = [line, head].find(b => b.contains(e.target) && (e.deltaY > 0 ? b.scrollLeft + b.clientWidth < b.scrollWidth - 1 : b.scrollLeft > 0));
        if (!e.deltaY || !box) return;
        box.scrollLeft += e.deltaY; e.preventDefault();
    };
    head.onwheel = sideways;
    // …by a pointer of any kind: a finger on a phone drags it as a mouse does on a desk (it took a mouse only)
    d.querySelector('.dk-grip').onpointerdown = e => {
        const y0 = e.clientY, h0 = d.offsetHeight;
        // …a mouse's press starts no text selection: the drag swept the deck's words into one (the author, 2026-11-18)
        e.preventDefault(); getSelection()?.removeAllRanges();
        // …over a canvas already as tall as the lowest deck leaves it (graph.js, gfso.css): nothing under the deck waits to be drawn
        const cv = document.getElementById('cy');
        cv.style.height = `${d.parentElement.clientHeight - 120}px`; document.body.classList.add('deck-drag');
        const move = m => { d.style.height = `${Math.max(120, Math.min(innerHeight * 0.8, h0 + y0 - m.clientY))}px`; };
        const up = () => { document.body.classList.remove('deck-drag'); cv.style.height = ''; removeEventListener('pointermove', move); removeEventListener('pointerup', up); removeEventListener('pointercancel', up); pref.h = d.offsetHeight; save(); paint(); };
        // …a touch the system takes back ends the drag too: it left the deck following the next finger anywhere (critic)
        addEventListener('pointermove', move); addEventListener('pointerup', up); addEventListener('pointercancel', up);
    };
    let w = 0;
    new ResizeObserver(([e]) => { if (Math.abs(e.contentRect.width - w) > 4) { w = e.contentRect.width; if (S.run) paint(); } }).observe(d);
    setInterval(() => { for (const [k, v] of ticks) if (v.t < Date.now() - 12e3) ticks.delete(k); }, 5e3);
}
