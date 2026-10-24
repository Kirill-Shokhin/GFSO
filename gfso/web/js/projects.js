// Projects: the list a person finds a run in — what each one was (its goal), when it ran, where its root
// stands, what it cost — and how a new one comes into being: by name, in the URL, made by its first
// creating verb. Everything here is read from the files on disk by the server: listing a project never
// builds its engine, so a look sets nothing running.
import {$, el, esc} from './dom.js';
import {PROJECT, getJSON} from './api.js';
import {S} from './state.js';
import {notice} from './overlays.js';
import {modelName} from './vocab.js';

// How many pieces of long work each project has running, from the one registry the server keeps.
export const busyByProject = () => S.inflight.reduce((m, w) => (m[w.project] = (m[w.project] || 0) + 1, m), {});

const SHOWN = 40;           // rows before "more": the newest runs are the ones looked for
let all = null, shown = SHOWN;
const panel = () => $('project-panel');

export async function refreshProjects() {
    let d;
    try { d = await getJSON('/api/projects?limit=0'); } catch (e) { return; }   // single-project server
    S.project = PROJECT || d.active;
    all = d.projects.map(n => ({n, t: d.last_active?.[n], ...(d.about?.[n] || {})}));
    $('project-open').textContent = S.project;
    if (!panel().hidden) draw();
}

// Where the goal stands, in words a person reads without the canon: the brand's dot is the one real done,
// and every way of NOT being delivered is marked — the runs looked for are often the ones that did not make it.
function where(p, busy) {
    const r = p.goal;
    if (!r) return ['empty', 'no goal yet'];
    if (r.state === 'DONE' && !['FAIL', 'CANCELLED'].includes(r.done_reason)) return ['done', 'delivered'];
    if (r.done_reason === 'FAIL') return ['bad', 'failed'];
    if (r.state === 'DONE' || r.state === 'ABANDONED') return ['bad', 'abandoned · not delivered'];
    if (busy) return ['live', `running · ${busy}`];
    const since = p.t ? ` · last act ${when(p.t)}` : '';
    if (r.state === 'ESCALATED') return ['bad', `awaits a decision${since}`];
    // acted lately: a run another process drives (an AUTO dispatcher, an E3 container) is in no registry of
    // this server's, so its last act is all that can be said — whether it still lives, or a look woke it once
    if (recent(p)) return ['open', since.slice(3)];
    // NOT FINISHED, whatever its state says: most such roots are runs whose process is long gone, and
    // "in progress" said the opposite
    return ['bad', `unfinished${since}`];
}

const DAY = 86400e3, LOCALE = 'en-GB';   // the page's language, not the browser's
const day = t => { const d = new Date(t * 1e3); d.setHours(0, 0, 0, 0); return d.getTime(); };
function dayName(ms) {
    const today = day(Date.now() / 1e3);
    return ms === today ? 'Today' : ms === today - DAY ? 'Yesterday'
        : new Date(ms).toLocaleDateString(LOCALE, {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric'});
}
const clock = t => new Date(t * 1e3).toLocaleTimeString(LOCALE, {hour: '2-digit', minute: '2-digit'});
const date = t => new Date(t * 1e3).toLocaleDateString(LOCALE, {day: 'numeric', month: 'short'});
const recent = p => p.t && Date.now() / 1e3 - p.t < DAY / 1e3;
const when = t => day(t) === day(Date.now() / 1e3) ? clock(t) : `${date(t)} ${clock(t)}`;

// A row is timed by what its group is about: the last day's band by the last act, the launch beside it (an
// old run woken today reads as woken); a launch group by the launch, a finished run's last act beside it when
// that came on another day (how long it ran). An unfinished one says its last act in its status.
function row(p, busy, active) {
    const [cls, text] = where(p, busy), r = p.goal, cur = p.n === S.project;
    const acted = active ? r?.started && `launched ${when(r.started)}`
        : ['DONE', 'ABANDONED'].includes(r?.state) && r.started && p.t && day(r.started) !== day(p.t) && `last act ${when(p.t)}`;
    const t = active ? p.t : r?.started;
    return `<a class="pl-row${cur ? ' cur' : ''}" href="?project=${encodeURIComponent(p.n)}" title="${esc((r?.name ? r.name + '\n' : '') + p.n)}">`
        + `<span class="pl-time">${t ? clock(t) : ''}</span>`
        + `<span class="pl-what"><b>${esc(r?.name || p.n)}</b><i>${[p.n, acted, (p.models || []).map(modelName).join(' + ')].filter(Boolean).map(esc).join(' · ')}</i></span>`
        + `<span class="pl-where ${cls}">${esc(text)}${cls === 'done' ? '<i class="brand-dot"></i>' : ''}</span>`
        + `<span class="pl-mode">${esc(p.mode || '')}</span>`
        + `<span class="pl-cost">${p.cost ? '$' + p.cost.toFixed(2) : ''}</span></a>`;
}

function draw() {
    const q = $('pl-search').value.trim().toLowerCase(), busy = busyByProject();
    const hits = (all || []).filter(p => !q || [p.n, p.goal?.name || '', ...(p.models || []).map(modelName)]
        .some(x => x.toLowerCase().includes(q)));
    // TWO QUESTIONS, TWO AXES: what is acting now — the last day's acts, newest first, the server's own order —
    // and what each run was, by when it was launched (author, 2026-10-24: «мои текущие или последние прогоны …
    // хотя бы от какой даты»). By the last act alone, old runs a read woke buried the day's launches; by the
    // launch alone, the runs acting today sank under September. A project with no goal is no run: it goes last.
    const active = hits.filter(p => p.goal && recent(p));
    const runs = hits.filter(p => p.goal && !recent(p)).sort((a, b) => b.goal.started - a.goal.started);
    let last = null, html = '';
    [...active, ...runs, ...hits.filter(p => !p.goal)].slice(0, shown).forEach(p => {
        const on = active.includes(p), d = on ? 'active' : p.goal ? day(p.goal.started) : 0;
        if (d !== last) html += `<div class="pl-day">${on ? 'acted in the last 24 hours'
            : d ? 'launched ' + dayName(d).toLowerCase() : 'no goal'}</div>`;
        last = d;
        html += row(p, busy[p.n], on);
    });
    $('pl-list').innerHTML = html || '<div class="pn-meta">no project matches</div>';
    $('pl-count').textContent = `${hits.length} of ${(all || []).length}`;
    $('pl-more').hidden = hits.length <= shown;
    $('pl-more').textContent = `show ${Math.min(SHOWN, hits.length - shown)} more`;
}

export async function openProjects() {
    panel().hidden = false;
    shown = SHOWN;
    await refreshProjects();
    draw();
    $('pl-search').focus();
}
export const closeProjects = () => { panel().hidden = true; };
export const moreProjects = () => { shown += SHOWN; draw(); };
export const searchProjects = () => { shown = SHOWN; draw(); };
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !panel().hidden) closeProjects(); });

export const NAME = /^[A-Za-z0-9_-]+$/;
// TAB-local switch; `goal` opens the goal constructor there — a new project's first act is stating its goal
export const openProject = (name, {goal} = {}) => { location.search = '?project=' + encodeURIComponent(name) + (goal ? '&goal=1' : ''); };

export async function switchProject(name, then = {}) {
    // A NAME IS REQUIRED: an empty one landed silently in `default` (reached programmatically, wave 26).
    if (name && name !== '__new__') return openProject(name);
    if (!name || $('new-project-name')) return;
    // In the page, beside the picker: a native `prompt()` blocks every other event.
    const input = el('input', {id: 'new-project-name', placeholder: 'new project name', pattern: '[A-Za-z0-9_-]+'});
    input.style.width = '150px';
    const go = () => NAME.test(input.value.trim()) ? openProject(input.value.trim(), then)
                                                                   : notice('a project name is [A-Za-z0-9_-]', 'bad');
    const box = el('span', {id: 'new-project-box'}, input, el('button', {className: 'btn btn-sm', id: 'new-project-go',
                                                                         textContent: 'Open', onclick: go}));
    box.style.cssText = 'display:inline-flex;gap:4px;margin-left:6px';
    input.onkeydown = ev => { if (ev.key === 'Enter') go(); };
    $('project-open').after(box);
    input.focus();
}
