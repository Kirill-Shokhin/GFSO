// Projects: the list a person finds a run in — what each one was (its goal), when it ran, where its root
// stands, what it cost — and how a new one comes into being: by name, in the URL, made by its first
// creating verb. Everything here is read from the files on disk by the server: listing a project never
// builds its engine, so a look sets nothing running.
import {$, esc} from './dom.js';
import {TIP} from './hints.js';
import {PROJECT, getJSON, api, leave} from './api.js';
import {S, procs} from './state.js';
import {notice, askInPage, act} from './overlays.js';
import {modelName, goalWord, terminal} from './vocab.js';
import {LOCALE, hm, day as date, usd} from './fmt.js';

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
    $('project-delete').hidden = !neverRan(all.find(p => p.n === S.project), d.active);
    if (!panel().hidden) draw();
}

// A PROJECT THAT NEVER RAN — no model call, nothing spent — may be deleted, from its own page and never from the list
// (the author, 2026-10-27, through the engineering stream). The server's door is irreversible: the project's database
// goes with its whole history, so its name is typed to confirm; the door itself refuses `default` and the server's
// active project, and says so.
// …and nothing at work on it now: a ledger row is written when a session ENDS, so a goal being planned or a first session
// still running has no cost yet and is not "never ran"; the server's active project is refused by the door, so not offered
const neverRan = (p, active) => !!p && p.n !== 'default' && p.n !== active && !p.cost && !(p.models || []).length
    && !procs().length;
export async function deleteProject() {
    const name = S.project;
    const typed = await askInPage(`Delete the project <b>${esc(name)}</b>? It never ran — no model call, nothing spent. `
        + 'Its database goes with its whole history; this cannot be undone.', {yes: 'Delete', field: `type ${esc(name)} to confirm`});
    if (typed === false) return;
    if (typed !== name) return notice('the name typed is not this project — nothing was deleted', 'bad');
    await act(api(`/api/projects/${encodeURIComponent(name)}`, {method: 'DELETE'}), {ok: leave});
}

// Where the goal stands, in words a person reads without the canon: the brand's dot is the one real done,
// and every way of NOT being delivered is marked — the runs looked for are often the ones that did not make it.
function where(p, busy) {
    const r = p.goal;
    if (!r) return ['empty', 'no goal yet'];
    // a closed goal in the header's word; the list's row says what an abandoned one lacks
    // …and an open goal a FAIL left on the issuer's decision is marked failed too: the run looked for did not make it
    const word = goalWord(r) || (r.done_reason === 'FAIL' ? 'failed' : '');
    if (word) return [word === 'done' ? 'done' : 'bad', word === 'abandoned' ? 'abandoned · not delivered' : word];
    // a stop is the person's act on the run, not a failure: said as theirs, with why — and while sessions it let
    // finish still run, as stopping (the engine's three states, `run_state`)
    const stop = p.stopped;
    // …its why on hover: written by whoever stopped it, it ran to a paragraph where every other status is a phrase
    if (stop) return ['open', `${busy ? `stopping · ${busy} still at work` : 'stopped'} · by ${stop.by}`, stop.why];
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

const DAY = 86400e3;
const day = t => { const d = new Date(t * 1e3); d.setHours(0, 0, 0, 0); return d.getTime(); };
function dayName(ms) {
    const today = day(Date.now() / 1e3);
    return ms === today ? 'Today' : ms === today - DAY ? 'Yesterday'
        : new Date(ms).toLocaleDateString(LOCALE, {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric'});
}
const clock = t => hm(t * 1e3);
const recent = p => p.t && Date.now() / 1e3 - p.t < DAY / 1e3;
// a time said against a day the reader already has (today, the launch's): the clock alone on that day
const when = (t, ref = Date.now() / 1e3) => day(t) === day(ref) ? clock(t) : `${date(t * 1e3)} ${clock(t)}`;

// A row is timed by what its group is about, one rule a group: the last day's band by the last act, the launch beside
// it (an old run woken today reads as woken); a launch group by the launch, a finished or stopped run's last act beside
// it (how long it ran) — said only on another day before, which read as some rows having it and others not (the
// author). An unfinished one says its last act in its status. The model comes before the time: the line is cut at its end.
function row(p, busy, active) {
    const [cls, text, why] = where(p, busy), r = p.goal, cur = p.n === S.project;
    const acted = active ? r?.started && `launched ${when(r.started)}`
        : (terminal(r?.state) || p.stopped) && r?.started && p.t && `until ${when(p.t, r.started)}`;
    const t = active ? p.t : r?.started;
    return `<a class="pl-row${cur ? ' cur' : ''}" href="?project=${encodeURIComponent(p.n)}"${TIP.project(r?.name || p.n, r?.name && p.n)}>`
        + `<span class="pl-time">${t ? clock(t) : ''}</span>`
        + `<span class="pl-what"><b>${esc(r?.name || p.n)}</b><i>${[p.n, (p.models || []).map(modelName).join(' + '), acted].filter(Boolean).map(x => `<span>${esc(x)}</span>`).join(' · ')}</i></span>`
        + `<span class="pl-where ${cls}"${TIP.where(why)}>${esc(text)}${cls === 'done' ? '<i class="brand-dot"></i>' : ''}</span>`
        + `<span class="pl-mode">${esc(p.mode || '')}</span>`
        + `<span class="pl-cost">${p.cost ? usd(p.cost) : ''}</span></a>`;
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

// the picker's button opens it and, pressed again, closes it — as any drop-down does
export async function toggleProjects() {
    if (!panel().hidden) return closeProjects();
    panel().hidden = false;
    shown = SHOWN;
    await refreshProjects();
    draw();
    $('pl-search').focus();
}
export const closeProjects = () => { panel().hidden = true; };
export const moreProjects = () => { shown += SHOWN; draw(); };
export const searchProjects = () => { shown = SHOWN; draw(); };
