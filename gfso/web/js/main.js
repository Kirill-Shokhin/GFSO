// Wiring: the page's start, its refresh policy, and the one dispatch from `data-action` controls and
// live messages to the units that own them. No unit imports another's handlers; they meet here.
import {$} from './dom.js';
import {TASK, GOAL, getJSON} from './api.js';
import {S, myRole, rememberedRole, rememberRole, procs} from './state.js';
import {focus, watch, point} from './store.js';
import {loadCheckMap} from './vocab.js';
import {initGraph, refreshGraph, restyle, annotate, graphNeeds} from './graph.js';
import {refreshHeader, refreshQuality, toggleQuality, toggleReports, stopRun, startRun} from './header.js';
import {refreshProjects, switchProject, busyByProject, toggleProjects, closeProjects, moreProjects, searchProjects} from './projects.js';
import {selectTask, closeSidebar, resign} from './panel.js';
import {openReader} from './reader.js';
import {sendAction, submitActionForm, closeForm, recordVerdict, submitVerdict, aiDecompose, aiReview} from './acts.js';
import * as author from './author.js';
import * as goal from './goal.js';
import {mountDeck, refreshDeck, onPipeline, onInflight, suggestHeight} from './deck.js';
import {connectWS} from './live.js';

const refreshAll = async () => { await refreshGraph(); goal.labelGoalButton(); await refreshQuality(); await refreshHeader(); };
S.reload = async () => { await refreshAll(); if (focus().select) await selectTask(focus().select); };
const projects = () => refreshProjects().then(onInflight);
// what reads the run once the deck has rebuilt it
const afterDeck = () => { annotate(); refreshHeader(); if (focus().select) resign(focus().select); };

// THE COUNT OF WORK IN FLIGHT IS THE SERVER'S registry, not inferred from token ticks (an executor running
// tools sends none; author, 2026-09-24). A run starting or ending elsewhere changes the picker's line.
// The server's processes, as the server pushes them on every start and end (and as read once on load or reconnect).
async function applyInFlight(list) {
    const before = JSON.stringify(busyByProject()), here = () => JSON.stringify(procs().map(w => [w.verb, w.task_id]));
    const was = here();
    S.inflight = list || [];
    if (JSON.stringify(busyByProject()) !== before) projects();
    onInflight(); annotate();
    // a process starting or ending here re-reads the graph and the header: a plan authored, or a session ending,
    // moves no transition this page hears, and the header said "no goal yet" through a whole planning (live run)
    if (here() !== was) { await refreshAll(); refreshDeck().then(afterDeck); }
    if (S.runState?.state === 'stopping') refreshHeader();   // until the last session the stop let finish has ended
}
const readInFlight = () => getJSON('/api/runtime').then(r => applyInFlight(r.in_flight))
    .catch(() => { /* the strip keeps its last count; the socket banner says when the server is gone */ });

const ACT = {
    'run-stop': stopRun, 'run-start': startRun,
    close: () => point('select', null), select: d => point('select', d.id), read: (d, b) => openReader(d.facet, b.classList.contains('fchip')),
    signal: sendAction, 'send-signal': submitActionForm, 'form-cancel': closeForm,
    verdict: recordVerdict, 'send-verdict': submitVerdict, 'ai-decompose': aiDecompose, 'ai-review': aiReview,
    edit: author.openEdit, decompose: author.openDecompose,
    help: () => $('tb-help').classList.toggle('open'), quality: toggleQuality, reports: toggleReports, 'close-modal': author.closeModal,
    projects: toggleProjects, 'projects-close': closeProjects, 'projects-more': moreProjects,
    'project-new': () => (closeProjects(), switchProject('__new__')),
    goal: goal.openGoal, 'goal-close': goal.closeGoal, 'gp-crit': () => goal.addCrit(), 'gp-suggest': goal.suggestCrits,
    'gp-scope': goal.addScope, 'gp-risk': goal.addRisk, 'gp-create': goal.createGoal, 'gp-plan': goal.planGoal,
    'edit-add-criterion': () => author.addEditCriterion(), 'edit-add-risk': () => author.addEditAcceptedRisk(),
    'submit-edit': author.submitEdit, 'add-child': author.addChildForm, 'submit-decompose': author.submitDecompose,
    'child-suggest': author.suggestChildCriteria, 'child-criterion': author.addChildCriterion, 'child-risk': author.addChildAcceptedRisk,
};
// Esc closes an open popover too, as it closes the panels
document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.hd-quality.open').forEach(p => p.classList.remove('open')); });
document.addEventListener('click', e => {
    const b = e.target.closest('[data-action]'), mine = e.target.closest('.hd-quality');
    // one popover at a time: a click anywhere else, or on a link inside one, closes the open ones
    document.querySelectorAll('.hd-quality.open').forEach(p => { if (p !== mine || (b && b.dataset.action === 'select')) p.classList.remove('open'); });
    if (b) ACT[b.dataset.action](b.dataset, b);
    // a header popover opens below the toolbar, not over it: over it, it covered the toolbar's own "?" (critic 9).
    // Set on the header, not on the popover: the quality chip is rebuilt on every transition and took an inline top with it.
    const open = document.querySelector('.header .hd-quality.open');
    if (open) document.querySelector('.header').style.setProperty('--below-toolbar',
        `${document.querySelector('.toolbar').getBoundingClientRect().bottom - open.getBoundingClientRect().top + 8}px`);
});
$('goal-panel').addEventListener('input', goal.recheck);
$('goal-panel').addEventListener('click', goal.recheck);   // a row removed by its ×
$('pl-search').addEventListener('input', searchProjects);
// …AND THE BAR IS ASKED AGAIN: the frontier's `mine` is computed FOR the identity in the box.
$('current-role').addEventListener('input', () => { rememberRole(myRole()); refreshHeader(); });
watch((st, key) => { if (key === 'select') st.select ? selectTask(st.select) : closeSidebar(); });

const LIVE = {
    // a stop or start made anywhere — the page, the CLI, MCP — is the engine's `pause` line: the header re-reads the run
    pipeline: d => { onPipeline(d); if (d.source === 'pause') { refreshHeader(); projects(); } },
    projects,                                          // a project appeared
    // this tab's own project came to exist while the feed was refused: nothing of it was pushed here, so read it all
    async reopened() { await S.reload(); await readInFlight(); refreshDeck().then(afterDeck); },
    inflight: d => applyInFlight(d.in_flight),         // a process of the server started or ended
    opened: () => readInFlight(),
    // the feed was lost and is back: what happened meanwhile reached no one, so read it all once
    async resync() { await readInFlight(); await refreshAll(); refreshDeck().then(afterDeck); },
    async transition(d) {
        const t = S.tasks.find(x => x.id === d.task_id);
        if (t) t.state = d.new_state;                  // the tooltip reads the cache
        // A node that SETTLES changes more than its colour — how it closed is drawn on it — so terminal
        // transitions take the long way round, which is one read.
        if (!restyle(d.task_id, d.new_state) || ['DONE', 'ABANDONED', 'ESCALATED'].includes(d.new_state)) await refreshGraph();
        await refreshQuality(); await refreshHeader();
        // …AND THE OPEN PANEL IS RE-READ ON ANY TRANSITION: its checks are computed from the CHILDREN.
        if (focus().select) await selectTask(focus().select);
        refreshDeck().then(afterDeck);
    },
};

async function init() {
    // THE PAGE MUST FAIL LOUDLY, NOT BLANKLY: the graph library is a remote script, and with the CDN
    // unreachable a first-time user saw a toolbar over an empty page and no error (2026-09-02).
    if (!window.cytoscape || !window.dagre) {
        $('cy').innerHTML = '<div style="padding:24px;max-width:60ch">'
            + '<b>The graph library did not load.</b><br><br>This page fetches cytoscape and dagre from '
            + 'unpkg.com, so it needs the network the first time. Everything else works: the API is '
            + 'local (<code>/api/tasks</code>, <code>/api/graph</code>), and <code>gfso status</code> '
            + 'prints the same graph in a terminal with no browser at all.</div>';
        return refreshHeader();                        // …and the header still comes: it is a local read
    }
    // YOUR OWN ID IS THE SERVER'S, not the placeholder `pm` registered nowhere — and what you typed wins.
    try {
        const rt = await getJSON('/api/runtime'), box = $('current-role');
        if (rt && rt.agent_id && (!box.value || box.value === 'pm')) box.value = rt.agent_id;
        box.value = rememberedRole() || box.value;
    } catch (e) { /* the box keeps what it had; the engine still refuses a stranger */ }
    await loadCheckMap();
    mountDeck();
    await initGraph();
    await refreshAll();
    suggestHeight(graphNeeds());
    refreshDeck().then(afterDeck);
    if (TASK) point('select', TASK);                   // `?task=` makes one node linkable
    if (GOAL && !S.tasks.length) goal.openGoal();     // a new project's first act: its goal
    connectWS(LIVE);
    projects();
}

// …AFTER the deferred graph libraries have run, or every load reports them missing.
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
