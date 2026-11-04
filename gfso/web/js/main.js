// Wiring: the page's start, its refresh policy, and the one dispatch from `data-action` controls and
// live messages to the units that own them. No unit imports another's handlers; they meet here.
import {$, ages, phone} from './dom.js';
import {PROJECT, TASK, GOAL, getJSON, singleFlight} from './api.js';
import {S, myRole, rememberedRole, rememberRole, procs} from './state.js';
import {focus, watch, point} from './store.js';
import {loadCheckMap, terminal, FM} from './vocab.js';
import {loadGraph, hear, loadFrontier, loadReports, loadMetrics, loadRun, rebuildRun, runIsOpen} from './model.js';
import {initGraph, drawGraph, restyle, applyMineDim, toggleMine, annotate, graphNeeds} from './graph.js';
import {drawHeader, drawQuality, toggleReports, stopRun, startRun} from './header.js';
import {refreshProjects, busyByProject, toggleProjects, closeProjects, moreProjects, searchProjects, deleteProject, listOnly} from './projects.js';
import {selectTask, panelOpened, closeSidebar, resign, openReader, closeReader} from './panel.js';
import {sendAction, submitActionForm, closeForm, recordVerdict, submitVerdict, aiDecompose, aiReview} from './acts.js';
import * as author from './author.js';
import * as goal from './goal.js';
import {mountDeck, paint as paintDeck, onPipeline, onInflight, suggestHeight, foldDeck} from './deck.js';
import {connectWS} from './live.js';
import {askProjectName, clearNotice} from './overlays.js';
import {mountHints, LEAVING} from './hints.js';
import {untip, TOUCH} from './tip.js';
import {drawPlanning} from './planning.js';
import {onReading, rereadResources} from './resources.js';
import {said} from './run.js';

// THE REFRESHES, each a read of the page's model (model.js) and then the drawing of what it read. SERIALISED (api.js
// singleFlight): a WebSocket transition and an ordinary refresh interleaving cleared the canvas under each other.
let graphRead = () => {};
const refreshGraph = singleFlight(async () => {
    try { const ok = await loadGraph(); graphRead(); rebuildRun(); await drawGraph(ok); } catch (e) { console.error('refreshGraph:', e); } });
const refreshHeader = singleFlight(async () => { await loadFrontier(); await loadReports(); await drawHeader(); });
const refreshQuality = singleFlight(async () => { await loadMetrics(); drawQuality(); });
const runRead = singleFlight(loadRun);
const refreshDeck = singleFlight(async () => { await runRead(); paintDeck(); });
const refreshAll = async () => { await refreshGraph(); goal.labelGoalButton(); await refreshQuality(); await refreshHeader(); };
// A LOAD READS WHILE IT DRAWS: the rest needs the graph's read, not its drawing, which held every read behind it for over a
// second on a phone. Nothing is painted over a drawing still under way: a chip pressed there would lose its unfolding.
async function firstLoad() {
    const read = new Promise(go => { graphRead = go; }), drawn = refreshGraph();
    await Promise.race([read, drawn]);
    goal.labelGoalButton();
    // …the run is built on the frontier (what waits on what), so it is painted once both have answered
    const run = runRead(), asked = Promise.all([refreshQuality(), refreshHeader()]);
    const deck = Promise.all([run, asked, drawn]).then(() => { rebuildRun(); paintDeck(); });
    await Promise.all([drawn, asked]);
    suggestHeight(graphNeeds());
    if (TASK) point('select', TASK);                   // `?task=` makes one node linkable
    within(panelOpened()).then(() => deck).then(afterDeck);   // …the view framed on the canvas its panel leaves
}
S.reload = async () => { await refreshAll(); if (focus().select) await selectTask(focus().select); };
const projects = () => refreshProjects().then(onInflight);
// NEWS ON THE NARRATION re-reads, once a burst of it has settled, as much as its widest line asked: the run always; the
// header; the open node's panel when a line names it (a dispute, a verdict, a validation change it with no transition);
// all of it — plan, header, panel, the goal form — for a mode or a plan changed. Each line read at once read the panel
// twice and the plan ten times over a burst of ten (critic 6)
let soon = null, paneled = 0;
const want = {header: false, panel: false, all: false};
const later = (o = {}) => {
    for (const k in o) want[k] ||= o[k];
    clearTimeout(soon);
    soon = setTimeout(async () => {
        const w = {...want};
        for (const k in want) want[k] = false;
        if (w.all) { await S.reload(); goal.recheckHolds(); w.header = true; }   // …and the header again over the run read below
        if (!w.all && w.header) await refreshHeader();
        // …a transition read the panel just now: the line narrating it adds nothing
        if (!w.all && w.panel && focus().select && Date.now() - paneled > 3e3) await selectTask(focus().select);
        refreshDeck().then(drawPlanning);
    }, 1500);
};
// what reads the run once the deck has rebuilt it
const afterDeck = () => { annotate(); refreshHeader(); drawPlanning(); if (focus().select) resign(focus().select); };
// A MOVE IS READ AT ONCE; moves arriving meanwhile share one more read: five at once read 21 times, a move every second never caught up (measured)
let settling = false, again = null;
// a read that hangs on a dead link holds no later move past this: the next read goes on without it
const within = read => Promise.race([read, new Promise(go => setTimeout(go, 5e3))]);
const settle = async o => {
    if (settling) { again = {graph: again?.graph || o.graph}; return; }
    settling = true;
    try { for (let cur = o; cur; cur = again) { again = null;
        if (cur.graph) await within(refreshGraph());
        await within(refreshQuality()); await within(refreshHeader());
        // …AND THE OPEN PANEL IS RE-READ ON ANY TRANSITION: its checks are computed from the CHILDREN.
        if (focus().select) { await within(selectTask(focus().select)); paneled = Date.now(); }
        // …the run read, the header drawn over it from the frontier just read, whenever it lands: the bound holds only the queue
        await within(refreshDeck().then(() => {
            annotate(); S.frontier ? drawHeader() : refreshHeader(); drawPlanning();   // a frontier read that failed is asked again
            if (focus().select) resign(focus().select);
        }));
    } } finally { settling = false; }
};

// THE COUNT OF WORK IN FLIGHT IS THE SERVER'S registry, not inferred from token ticks (an executor running
// tools sends none; author, 2026-09-24). A run starting or ending elsewhere changes the picker's line.
// The server's processes, as the server pushes them on every start and end (and as read once on load or reconnect).
async function applyInFlight(list) {
    const before = JSON.stringify(busyByProject()), here = () => JSON.stringify(procs().map(w => [w.verb, w.task_id]));
    const was = here();
    S.inflight = list || [];
    if (JSON.stringify(busyByProject()) !== before) projects();
    rebuildRun(); onInflight(); annotate();      // what runs now, read again from the run's last read
    drawPlanning();                              // …and the stage an authoring has reached comes on this same push
    // a process starting or ending here re-reads the graph and the header: a plan authored, or a session ending,
    // moves no transition this page hears, and the header said "no goal yet" through a whole planning (live run)
    if (here() !== was) { await S.reload(); refreshDeck().then(afterDeck); }
    if (S.runState?.state === 'stopping') refreshHeader();   // until the last session the stop let finish has ended
}
const readInFlight = () => getJSON('/api/runtime').then(r => applyInFlight(r.in_flight))
    .catch(() => { /* the strip keeps its last count; the socket banner says when the server is gone */ });

const ACT = {
    'run-stop': async () => { if (await stopRun() === '') await refreshHeader(); },
    'run-start': async () => { if (await startRun() === '') await refreshHeader(); },
    close: () => point('select', null), select: d => point('select', d.id), read: (d, b) => openReader(d.facet, b.classList.contains('fchip')),
    signal: sendAction, 'send-signal': submitActionForm, 'form-cancel': closeForm,
    verdict: recordVerdict, 'send-verdict': submitVerdict, 'ai-decompose': aiDecompose, 'ai-review': aiReview,
    edit: author.openEdit, decompose: author.openDecompose,
    mine: toggleMine, pop: (d, b) => b.setAttribute('aria-expanded', b.closest('.hd-quality').classList.toggle('open')), reports: toggleReports, 'close-modal': author.closeModal,
    projects: toggleProjects, 'projects-close': closeProjects, 'projects-more': moreProjects, 'project-delete': deleteProject,
    'project-new': () => (closeProjects(), askProjectName({goal: true})),
    goal: goal.openGoal, 'goal-close': goal.closeGoal, 'gp-crit': () => goal.addCrit(), 'gp-suggest': goal.suggestCrits,
    'gp-scope': goal.addScope, 'gp-risk': goal.addRisk, 'gp-create': goal.createGoal, 'gp-plan': goal.planGoal,
    'edit-add-criterion': () => author.addEditCriterion(), 'edit-add-risk': () => author.addEditAcceptedRisk(),
    'submit-edit': author.submitEdit, 'add-child': author.addChildForm, 'submit-decompose': author.submitDecompose,
    'child-suggest': author.suggestChildCriteria, 'child-criterion': author.addChildCriterion, 'child-risk': author.addChildAcceptedRisk,
};
// Esc closes whatever is open over the page: a popover, the reader, the goal form, the projects list
document.addEventListener('keydown', e => { if (e.key !== 'Escape' || WATCHES) return;
    // …one at a time, the node's panel last: its × says Esc
    const over = document.querySelector('.hd-quality.open') || $('reader')?.hidden === false || $('goal-panel')?.hidden === false;
    document.querySelectorAll('.hd-quality.open').forEach(p => { p.classList.remove('open'); p.querySelector('[aria-expanded]')?.setAttribute('aria-expanded', false); });
    closeReader(); goal.closeGoal(); closeProjects();
    if (!over && focus().select) point('select', null); });
document.addEventListener('click', e => {
    const b = e.target.closest('[data-action]'), mine = e.target.closest('.hd-quality');
    // one popover at a time: a click anywhere else, or on a link inside one, closes the open ones
    document.querySelectorAll('.hd-quality.open').forEach(p => { if (p !== mine || (b && b.dataset.action === 'select')) { p.classList.remove('open'); p.querySelector('[aria-expanded]')?.setAttribute('aria-expanded', false); } });
    if (b) ACT[b.dataset.action](b.dataset, b);
    // a header popover opens below the toolbar, not over it: over it, it covered the toolbar's own "?" (critic 9).
    // Set on the header, not on the popover: the quality chip is rebuilt on every transition and took an inline top with it.
    const open = document.querySelector('.header .hd-quality.open');
    if (open) document.querySelector('.header').style.setProperty('--below-header', `${document.querySelector('.header').getBoundingClientRect().bottom + 8}px`);
    if (open) document.querySelector('.header').style.setProperty('--below-toolbar',
        `${(document.querySelector('.toolbar') || document.querySelector('.header')).getBoundingClientRect().bottom - open.getBoundingClientRect().top + 8}px`);
});
$('goal-panel').addEventListener('input', goal.recheck);
$('goal-panel').addEventListener('click', goal.recheck);   // a row removed by its ×
$('pl-search').addEventListener('input', searchProjects);
// …AND THE BAR IS ASKED AGAIN: the frontier's `mine` is computed FOR the identity in the box.
$('current-role').addEventListener('input', () => { rememberRole(myRole()); if (S.mineOnly) applyMineDim(); refreshHeader(); });
watch((st, key) => { if (key === 'select') st.select ? selectTask(st.select) : closeSidebar(); });
// ON A PHONE THE BROWSER'S BACK IS THE WAY OUT A HAND REACHES FOR: it closes what is open, topmost first — a tip, a popover, the reader,
// a panel, the deck — and with nothing open says once that the next one leaves (the author, 2026-10-31: «интуитивно жмешь кнопку назад
// а не крестик»; 11-04: «любое движение привычное и вкладка у тебя слетела в пустую страницу»).
const STEPS = 12;
let warned = 0;
const closeTop = () => {
    if ($('ask-no')) return $('ask-no').click(), true;
    const modal = document.querySelector('.modal-bg.active');
    if (modal) return modal.classList.remove('active'), true;
    if ($('new-project-box')) return $('new-project-box').remove(), true;
    if ($('page-notice')) return clearNotice(), true;
    if ($('inline-form')?.innerHTML) return $('inline-form').innerHTML = '', true;
    const tipBox = $('tooltip');
    if (tipBox?.classList.contains('visible')) return untip(), true;
    const pop = document.querySelector('.hd-quality.open');
    if (pop) return pop.classList.remove('open'), pop.querySelector('[aria-expanded]')?.setAttribute('aria-expanded', 'false'), true;
    if ($('reader') && !$('reader').hidden) return closeReader(), true;
    if ($('goal-panel') && !$('goal-panel').hidden) return goal.closeGoal(), true;
    if (PROJECT && $('project-panel') && !$('project-panel').hidden) return closeProjects(), true;
    if (focus().select) return point('select', null), true;
    return !!PROJECT && foldDeck();
};
// A hand, not a width: a phone held sideways has one too. Back is not a history trick: Chrome's Back skips any entry a page laid without a gesture,
// so steps re-laid as Back was handled let the second Back leave (the author, 11-04: «как и с любыми двумя панелями подряд»). The browser's own
// answer is a close request: Back asks the open watcher, no history touched. Where it is missing, steps laid only under gestures, one per tap.
const hand = () => phone() || TOUCH.matches;
const say = () => { warned = Date.now();
    const note = document.body.appendChild(Object.assign(document.createElement('div'), {className: 'back-note', textContent: LEAVING}));
    setTimeout(() => note.remove(), 3000); };
const WATCHES = hand() && 'CloseWatcher' in window;
if (WATCHES) {
    let w = null;
    const arm = () => { w = new CloseWatcher(); w.onclose = () => { w = null;
        if (closeTop()) return arm();
        if (Date.now() - warned < 3000) return history.back();
        say(); arm(); }; };
    arm();
    addEventListener('pointerup', () => { if (!w) arm(); }, true);
} else if (hand()) {
    addEventListener('pointerup', () => { const n = history.state?.gfsoSteps || 0; if (n < STEPS) history.pushState({gfsoSteps: n + 1}, ''); }, true);
    addEventListener('popstate', () => { if (closeTop()) return;
        if (Date.now() - warned < 3000) return history.go(-(history.state?.gfsoSteps || 0) - 1);
        say(); });
}

const NEWS = {
    // a stop or start made anywhere — the page, the CLI, MCP — is the engine's `pause` line: the header re-reads the run
    pause: () => (projects(), {header: true}),
    // a mode or its settings set anywhere: who holds what, what each node offers, the goal form's readiness
    mode: () => ({all: true}),
    tech_report: () => ({header: true}),
    // a call booked: a project that "never ran" has run now, and its Delete goes
    usage: () => { if (!$('project-delete').hidden) projects(); },
    // the plan changed with no transition — a Dep edge, an assignee, a criterion, a node created, an agent registered
    graph: () => ({all: true}),
    // the accepted result reached the user's repository, a moment after the verdict that closed the goal
    landed: () => ({all: true}),
};
const LIVE = {
    // NEWS ON THE NARRATION re-reads what it changed — no reload is ever needed to see what the server holds (the author,
    // 2026-10-31: «если пользователю требуется руками нажать обновление страницы - это либо перезапущен сервер, либо баг»)
    pipeline: d => { if (onPipeline(d)) later({panel: said(d.msg).node === focus().select, ...NEWS[d.source]?.()}); },
    reject: d => later({panel: d.task_id === focus().select}),   // a refused move is in the run's log: its row comes in
    projects,                                          // a project appeared
    resources: onReading,                              // the server took a new reading of Docker
    // this tab's own project came to exist while the feed was refused: nothing of it was pushed here, so read it all
    async reopened() { await S.reload(); await readInFlight(); refreshDeck().then(afterDeck); },
    inflight: d => applyInFlight(d.in_flight),         // a process of the server started or ended
    opened: () => readInFlight(),
    // the feed was lost and is back: what happened meanwhile reached no one, so read it all once
    async resync() { await readInFlight(); await S.reload(); refreshDeck().then(afterDeck); rereadResources(); if (!FM.loaded) loadCheckMap(); },
    async transition(d) {
        const t = S.tasks.find(x => x.id === d.task_id);
        if (t) t.state = d.new_state;                  // the tooltip reads the cache
        // …and so do Events' word and the panel's wait, off the graph read: with no process moving they stayed stale (critic)
        const drawn = S.graph.nodes.find(x => x.id === d.task_id); if (drawn) drawn.state = d.new_state;
        hear(d.task_id, d.new_state);                  // …and a graph read already out does not undo it
        rebuildRun();                                  // …and what runs now is read again over the new state
        // A node that SETTLES changes more than its colour — how it closed is drawn on it — so terminal
        // transitions take the long way round, which is one read.
        settle({graph: !restyle(d.task_id, d.new_state) || terminal(d.new_state) || d.new_state === 'ESCALATED'});
    },
};

async function init() {
    mountHints();
    if (!PROJECT) return listOnly();
    // THE PAGE MUST FAIL LOUDLY, NOT BLANKLY: the graph library is a remote script, and with the CDN
    // unreachable a first-time user saw a toolbar over an empty page and no error (2026-09-02).
    if (!window.cytoscape || !window.dagre) {
        $('cy').innerHTML = '<div class="cy-failed">'
            + '<b>The graph library did not load.</b><br><br>This page fetches cytoscape and dagre from '
            + 'unpkg.com, so it needs the network the first time. Everything else works: the API is '
            + 'local (<code>/api/tasks</code>, <code>/api/graph</code>), and <code>gfso status</code> '
            + 'prints the same graph in a terminal with no browser at all.</div>';
        return refreshHeader();                        // …and the header still comes: it is a local read
    }
    // YOUR OWN ID IS THE SERVER'S, not the placeholder `pm` registered nowhere — and what you typed wins.
    const asked = getJSON('/api/runtime'), checks = loadCheckMap();
    try {
        const rt = await asked, box = $('current-role');
        S.agentId = rt?.agent_id || '';
        if (rt && rt.agent_id && (!box.value || box.value === 'pm')) box.value = rt.agent_id;
        box.value = rememberedRole() || box.value;
    } catch (e) { /* the box keeps what it had; the engine still refuses a stranger */ }
    await checks;
    mountDeck();
    // A DISPLAY CLOCK, not a poll: while something runs, the ages it shows ("validating · 2m") and the open bars grow
    // with time and with nothing pushed — a session busy with tools streams no tokens. Minutes are the coarsest unit
    // shown, so 30 s keeps every figure within half its own step; no server read. A call booked in the ledger arrives
    // as the engine's `usage` line, which re-reads the run.
    setInterval(() => { if (runIsOpen()) { rebuildRun(); paintDeck(); } drawPlanning(); }, 30e3);
    // …and a figure in seconds is set each second, in place (dom.js `since`): nothing is redrawn, nothing read
    setInterval(ages, 1e3);
    await initGraph();
    await firstLoad();
    if (GOAL && !S.tasks.length) goal.openGoal();     // a new project's first act: its goal
    // the picker's name is its own read, so a feed that cannot open does not leave it blank
    projects();
    connectWS(LIVE);
}

// …AFTER the deferred graph libraries have run, or every load reports them missing.
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
