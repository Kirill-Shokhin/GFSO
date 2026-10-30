// What this installation's containers take of the machine now — memory, CPU, disk, how many stand and how many are
// busy — as Docker holds it (`GET /api/resources`, the security stream's backend, 2026-10-29). Read from Docker alone, so
// no project's engine wakes. The author, 2026-10-29: «всю инфу действительно выносить в ui … оперативная дисковая память,
// колво агентов, проекты». One reading serves every view: a view asks again when it is drawn, and shares a read in flight.
import {esc} from './dom.js';
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
export const reading = () => last;

// a count as its own mark (the header's rule): the figure large, its label small; a partial one says so on hover
const tally = (figure, label, counted) => `<span class="tally"${RES.counted(counted)}><b>${figure}</b><i>${label}</i></span>`;
const cpu = x => x == null ? '—' : `${x.toFixed(1)}%`;
const roles = by => Object.entries(by || {}).filter(([, r]) => r.standing)
    .map(([k, r]) => `${k} ${r.standing}${r.busy ? `<span class="rs-busy"${RES.busy}>, ${r.busy} busy</span>` : ''}`).join(' · ');
const notes = d => [!(d.read.containers && d.read.stats && d.read.disk) && RES.unread,
    d.older_build?.containers && RES.older(d.older_build.containers)].filter(Boolean)
    .map(n => `<div class="pn-meta">${esc(n)}</div>`).join('');

// THE DECK'S VIEW: this project, node by node, then the project's own containers and its volumes
export function render(el) {
    readResources(() => { if (el.isConnected && el._drawn === 'resources') draw(el); });
    draw(el);
}
function draw(el) {
    const d = last, p = d?.projects.find(x => x.project === S.project);
    if (!d) return void (el.innerHTML = '<div class="pn-meta">reading Docker…</div>');
    if (!p) return void (el.innerHTML = `<div class="pn-meta">${RES.none}</div>${notes(d)}`);
    const c = p.containers;
    const rows = [...p.nodes.map(n => [nameOf(S.tasks.find(t => t.id === n.node) || {id: n.node}), n.containers, n]),
        ['the project itself', p.system, null]].filter(([, cs]) => cs.length);
    el.innerHTML = `<div class="wk"><div class="rs-tallies">${tally(c.running, 'containers running')}`
        + `${c.busy != null ? tally(c.busy, 'busy', c.busy_counted) : ''}${tally(bytes(p.memory_bytes, '—'), 'memory', p.memory_bytes_counted)}`
        + `${tally(cpu(p.cpu_percent), 'CPU', p.cpu_percent_counted)}<span${RES.volumes(p.volumes.map(v => [v.role, bytes(v.bytes, '—')]))}>${tally(bytes(p.disk_bytes, '—'), 'disk', p.disk_counted)}</span></div>`
        + `<table class="wk-table"><thead><tr><th>node</th><th>containers</th><th>memory</th><th>CPU</th></tr></thead><tbody>`
        + rows.map(([name, cs, n]) => {
            const by = {};
            for (const x of cs) { const r = by[x.role] ??= {standing: 0, busy: 0}; r.standing++; r.busy += x.busy ? 1 : 0; }
            const mem = n ? n.memory_bytes : cs.reduce((s, x) => s + (x.memory_bytes || 0), 0);
            return `<tr><td${RES.full(name)}><b>${esc(trim(name, 56))}</b></td><td>${roles(by)}</td><td>${bytes(mem, '—')}</td>`
                + `<td>${cpu(n ? n.cpu_percent : cs.reduce((s, x) => s + (x.cpu_percent || 0), 0))}</td></tr>`;
        }).join('')
        + `</tbody></table>${notes(d)}</div>`;
}

// THE PROJECT LIST'S HEAD: the whole machine — what GFSO's containers take of it, and the orphans' disk
export function machine() {
    const d = last;
    if (!d) return '';
    const ps = d.projects, sum = k => ps.reduce((s, p) => s + (p[k] || 0), 0), orphans = ps.filter(p => !p.known);
    const mem = sum('memory_bytes');
    return `<div class="rs-machine"${RES.machine}>${tally(ps.reduce((s, p) => s + (p.containers?.running || 0), 0), 'containers running')}`
        + tally(bytes(mem, '—'), 'memory') + tally(pct(mem / d.machine.memory_bytes), `of ${bytes(d.machine.memory_bytes)}`)
        + tally(bytes(sum('disk_bytes'), '—'), 'disk')
        + (orphans.length ? `<span${RES.orphan(bytes(orphans.reduce((s, p) => s + (p.disk_bytes || 0), 0)))}>`
            + `${tally(orphans.length, orphans.length > 1 ? 'orphans' : 'orphan')}</span>` : '')
        + `</div>${notes(d)}`;
}
// …and each row's own: memory while it runs, disk always
export const ofProject = name => {
    const p = last?.projects.find(x => x.project === name);
    return !p ? '' : `${p.containers?.running ? `${bytes(p.memory_bytes, '—')}<i>memory</i>` : ''}${bytes(p.disk_bytes, '—')}<i>disk</i>`;
};
