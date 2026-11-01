// What this installation's containers take of the machine now — memory, CPU, disk, how many stand and how many are
// busy — as Docker holds it (`GET /api/resources`, the security stream's backend, 2026-10-29). Read from Docker alone, so
// no project's engine wakes. The author, 2026-10-29: «всю инфу действительно выносить в ui … оперативная дисковая память,
// колво агентов, проекты». One reading serves every view: a view asks again when it is drawn, and shares a read in flight.
// What Docker did not answer is null in the reading and says so here — never a 0 (no `docker info`: no machine; no
// container listing: no containers, nodes or system rows).
import {esc, tally, morph, daily} from './dom.js';
import {getJSON} from './api.js';
import {RES} from './hints.js';
import {S} from './state.js';
import {nameOf} from './vocab.js';
import {bytes, pct, trim, cpu, clockAt} from './fmt.js';
import {total} from './run.js';

let last = null, pending = null, asked = false;
const shown = new Set();      // the views drawing the reading now: each redraws itself when a new one arrives
const take = d => { if (Array.isArray(d?.projects)) { last = d; shown.forEach(f => f()); } };
// …a reading is taken only in its shape: a server without the door answers no reading, and the views say so. The page
// ASKS once, for what the server holds; every reading after that the server PUSHES as it takes it (`resources` on the
// live feed) — a look never makes the server read Docker (the author, 2026-10-30: «интерфейс не должен тригерить новый
// опрос докера. он должен отобразить текущее число»)
export function readResources(then) {
    if (last) return void then?.();
    // …and whatever the answer, the views draw again: a failed read left «reading Docker…» until the tab was reopened (audit C5)
    pending ??= getJSON('/api/resources').then(take, () => {}).finally(() => { pending = null; asked = true; shown.forEach(f => f()); });
    pending.then(then);
}
export const onReading = take;                        // main.js: the live feed's `resources`
// …and after the feed was lost a reading may have been missed: the server pushes only a CHANGED one, so ask once more
export const rereadResources = () => { last = null; if (shown.size) readResources(() => shown.forEach(f => f())); };
export const whileShown = f => shown.add(f);
daily(() => shown.forEach(f => f()));   // «last read» said without its day gains it at midnight

const mark = (figure, label, counted) => tally(figure, label, RES.counted(counted));
// a count's noun in its number: «1 container running», «2 executors» (audit C12)
const many = (n, one, more = `${one}s`) => n === 1 ? one : more;
const ROLE = {door: 'model door'};
// each role's containers as their own marks, the busy ones beside them
const roles = cs => {
    const by = {};
    for (const x of cs) { const r = by[x.role] ??= {n: 0, busy: 0}; r.n++; r.busy += x.busy ? 1 : 0; }
    return Object.entries(by).map(([k, r]) => tally(r.n, many(r.n, ROLE[k] || k), RES.role[k] || '') + (r.busy ? tally(r.busy, 'busy', RES.busy) : '')).join('');
};
// HOW OLD THE READING IS, said only when it is old: the server pushes each fresh reading, so a figure on screen is now — but
// where Docker did not answer, the reading shown is the last it gave, and the moment it was read says so (`read_at`) — never an age, which
// stood frozen; no clock of the page's own (the author, 2026-10-30: «зачем он сам обновляет таймер по своим часам … опять костыли»)
const read = t => t == null ? 'never' : clockAt(t * 1e3);
const age = d => { const r = d.read_at || {}, stale = Object.keys(r).filter(k => r[k] != null && !d.read[k]);
    return stale.length ? tally(read(Math.min(...stale.map(k => r[k]))), 'last read', RES.ages(stale.map(k => [k, read(r[k])]))) : ''; };
// …the server's poller keeps the last reading (security 8746d6a): before its first, nothing is read yet — no failure
const notes = d => [!Object.values(d.read_at || {}).some(t => t != null) ? RES.first
    : !(d.read.containers && d.read.stats && d.read.disk) && RES.unread,
    d.older_build?.containers && RES.older(d.older_build.containers)].filter(Boolean)
    .map(n => `<div class="pn-meta">${esc(n)}</div>`).join('');

// THE DECK'S VIEW: this project, node by node, then the project's own containers
export function render(el) {
    if (!el._reading) el._reading = true, whileShown(() => { if (el.isConnected && el._drawn === 'resources') draw(el); });
    readResources();
    draw(el);
}
function draw(el) {
    const d = last, p = d?.projects.find(x => x.project === S.project);
    if (!d) return void morph(el, `<div class="pn-meta">${asked ? RES.unserved : 'reading Docker…'}</div>`);
    // …nothing of the project where Docker listed nothing says nothing of the project
    if (!p) return void morph(el, `${d.read.containers ? `<div class="pn-meta">${RES.none}</div>` : ''}${notes(d)}`);
    const c = p.containers, disk = `<span${RES.volumes((p.volumes || []).map(v => [v.role, bytes(v.bytes, '—')]))}>`
        + `${mark(bytes(p.disk_bytes, '—'), 'disk', p.disk_counted)}</span>`;
    if (!c) return void morph(el, `<div class="wk"><div class="rs-tallies">${disk}</div>${notes(d)}</div>`);
    const rows = [...(p.nodes || []).map(n => [nameOf(S.tasks.find(t => t.id === n.node) || {id: n.node}), n.containers, n]),
        ['the project itself', p.system || [], null]].filter(([, cs]) => cs.length);
    morph(el, `<div class="wk"><div class="rs-tallies">${age(d)}${mark(c.running, many(c.running, 'container running', 'containers running'))}`
        + `${c.busy != null ? mark(c.busy, 'busy', c.busy_counted) : ''}${mark(bytes(p.memory_bytes, '—'), 'memory', p.memory_bytes_counted)}`
        + `${mark(cpu(p.cpu_percent), 'CPU', p.cpu_percent_counted)}${disk}</div>`
        + (!rows.length ? '' : `<table class="wk-table"><thead><tr><th>node</th><th>containers</th><th>memory</th><th>CPU</th></tr></thead><tbody>`
        + rows.map(([name, cs, n]) => `<tr><td${RES.full(name)}><b>${esc(trim(name, 56))}</b></td><td class="rs-roles">${roles(cs)}</td>`
            + `<td>${bytes(n ? n.memory_bytes : total(cs, x => x.memory_bytes), '—')}</td>`
            + `<td>${cpu(n ? n.cpu_percent : total(cs, x => x.cpu_percent))}</td></tr>`).join('')
        + `</tbody></table>`) + `${notes(d)}</div>`);
}

// THE PROJECT LIST'S HEAD: the whole machine — what GFSO's containers take of it, and the orphans
export function machine() {
    const d = last;
    if (!d) return '';
    const ps = d.projects, orphans = ps.filter(p => !p.known);
    const mem = total(ps, p => p.memory_bytes), of = d.machine?.memory_bytes;
    const run = total(ps, p => p.containers?.running);
    // the line's caption said once at its start, not as every figure's tip (audit C11)
    return `<div class="rs-machine"><span class="rs-cap"${RES.machine}>this machine</span>${age(d)}${mark(run ?? '—', many(run, 'container running', 'containers running'))}`
        + mark(bytes(mem, '—'), 'memory') + (mem != null && of ? tally(pct(mem / of), "of the machine's memory", RES.ofMachine(bytes(of))) : '')
        + mark(bytes(total(ps, p => p.disk_bytes), '—'), 'disk')
        + (orphans.length ? tally(orphans.length, orphans.length > 1 ? 'orphans' : 'orphan', RES.orphan(bytes(total(orphans, p => p.disk_bytes), '—'))) : '')
        + `</div>${notes(d)}`;
}
// …and each row's own: memory while it runs, disk always
export const ofProject = name => {
    const p = last?.projects.find(x => x.project === name);
    return !p ? '' : `${p.containers?.running ? tally(bytes(p.memory_bytes, '—'), 'memory') : ''}${tally(bytes(p.disk_bytes, '—'), 'disk')}`;
};
