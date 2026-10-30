// What this installation's containers take of the machine now — memory, CPU, disk, how many stand and how many are
// busy — as Docker holds it (`GET /api/resources`, the security stream's backend, 2026-10-29). Read from Docker alone, so
// no project's engine wakes. The author, 2026-10-29: «всю инфу действительно выносить в ui … оперативная дисковая память,
// колво агентов, проекты». One reading serves every view: a view asks again when it is drawn, and shares a read in flight.
// What Docker did not answer is null in the reading and says so here — never a 0 (no `docker info`: no machine; no
// container listing: no containers, nodes or system rows).
import {esc, tally} from './dom.js';
import {getJSON} from './api.js';
import {RES} from './hints.js';
import {S} from './state.js';
import {nameOf} from './vocab.js';
import {bytes, pct, trim} from './fmt.js';

let last = null, pending = null;
export function readResources(then) {
    pending ??= getJSON('/api/resources').then(d => { last = d; }, () => {}).finally(() => { pending = null; });
    pending.then(then);
}

// a sum over figures none of which Docker gave is none, not 0
const total = (xs, f) => xs.some(x => f(x) != null) ? xs.reduce((s, x) => s + (f(x) || 0), 0) : null;
const cpu = x => x == null ? '—' : `${x.toFixed(1)}%`;
const mark = (figure, label, counted) => tally(figure, label, RES.counted(counted));
// each role's containers as their own marks, the busy ones beside them
const roles = cs => {
    const by = {};
    for (const x of cs) { const r = by[x.role] ??= {n: 0, busy: 0}; r.n++; r.busy += x.busy ? 1 : 0; }
    return Object.entries(by).map(([k, r]) => tally(r.n, k) + (r.busy ? tally(r.busy, 'busy', RES.busy) : '')).join('');
};
const notes = d => [!(d.read.containers && d.read.stats && d.read.disk) && RES.unread,
    d.older_build?.containers && RES.older(d.older_build.containers)].filter(Boolean)
    .map(n => `<div class="pn-meta">${esc(n)}</div>`).join('');

// THE DECK'S VIEW: this project, node by node, then the project's own containers
export function render(el) {
    readResources(() => { if (el.isConnected && el._drawn === 'resources') draw(el); });
    draw(el);
}
function draw(el) {
    const d = last, p = d?.projects.find(x => x.project === S.project);
    if (!d) return void (el.innerHTML = '<div class="pn-meta">reading Docker…</div>');
    if (!p) return void (el.innerHTML = `<div class="pn-meta">${RES.none}</div>${notes(d)}`);
    const c = p.containers, disk = `<span${RES.volumes((p.volumes || []).map(v => [v.role, bytes(v.bytes, '—')]))}>`
        + `${mark(bytes(p.disk_bytes, '—'), 'disk', p.disk_counted)}</span>`;
    if (!c) return void (el.innerHTML = `<div class="wk"><div class="rs-tallies">${disk}</div>${notes(d)}</div>`);
    const rows = [...(p.nodes || []).map(n => [nameOf(S.tasks.find(t => t.id === n.node) || {id: n.node}), n.containers, n]),
        ['the project itself', p.system || [], null]].filter(([, cs]) => cs.length);
    el.innerHTML = `<div class="wk"><div class="rs-tallies">${mark(c.running, 'containers running')}`
        + `${c.busy != null ? mark(c.busy, 'busy', c.busy_counted) : ''}${mark(bytes(p.memory_bytes, '—'), 'memory', p.memory_bytes_counted)}`
        + `${mark(cpu(p.cpu_percent), 'CPU', p.cpu_percent_counted)}${disk}</div>`
        + `<table class="wk-table"><thead><tr><th>node</th><th>containers</th><th>memory</th><th>CPU</th></tr></thead><tbody>`
        + rows.map(([name, cs, n]) => `<tr><td${RES.full(name)}><b>${esc(trim(name, 56))}</b></td><td class="rs-roles">${roles(cs)}</td>`
            + `<td>${bytes(n ? n.memory_bytes : total(cs, x => x.memory_bytes), '—')}</td>`
            + `<td>${cpu(n ? n.cpu_percent : total(cs, x => x.cpu_percent))}</td></tr>`).join('')
        + `</tbody></table>${notes(d)}</div>`;
}

// THE PROJECT LIST'S HEAD: the whole machine — what GFSO's containers take of it, and the orphans
export function machine() {
    const d = last;
    if (!d) return '';
    const ps = d.projects, orphans = ps.filter(p => !p.known);
    const mem = total(ps, p => p.memory_bytes), of = d.machine?.memory_bytes;
    return `<div class="rs-machine"${RES.machine}>${mark(total(ps, p => p.containers?.running) ?? '—', 'containers running')}`
        + mark(bytes(mem, '—'), 'memory') + (mem != null && of ? tally(pct(mem / of), "of the machine's memory", RES.ofMachine(bytes(of))) : '')
        + mark(bytes(total(ps, p => p.disk_bytes), '—'), 'disk')
        + (orphans.length ? tally(orphans.length, orphans.length > 1 ? 'orphans' : 'orphan', RES.orphan(bytes(total(orphans, p => p.disk_bytes), '—'))) : '')
        + `</div>${notes(d)}`;
}
// …and each row's own: memory while it runs, disk always
export const ofProject = name => {
    const p = last?.projects.find(x => x.project === name);
    return !p ? '' : `${p.containers?.running ? `${bytes(p.memory_bytes, '—')}<i>memory</i>` : ''}${bytes(p.disk_bytes, '—')}<i>disk</i>`;
};
