// WHILE THE GOAL'S PLAN IS AUTHORED there is no graph to draw, and minutes of an empty canvas read as nothing running
// (the author, 2026-10-30: «не вижу в ui прогон»). The canvas then says what the server already records: the authoring
// in flight and since when (`in_flight`, auto_decompose), and its stages as the planner narrates them (the log's
// `decompose` lines — «1/1 searcher…», «1/1 searcher done · this call 154s …»), each once, as its last line says.
import {$, esc, tally} from './dom.js';
import {S, procs} from './state.js';
import {rootOf} from './tree.js';
import {at} from './run.js';
import {dur, hm} from './fmt.js';
import {PLAN} from './hints.js';

const STEP = /^\d+\/\d+\s+(.+?)(?:…|\s+done\s+·\s+this call\s+(\d+)s)/;

export function drawPlanning() {
    let box = $('cy-plan');
    const w = !rootOf(S.tasks) && procs().find(p => p.verb === 'auto_decompose');
    if (!w) return void box?.remove();
    box ??= $('cy').appendChild(Object.assign(document.createElement('div'), {id: 'cy-plan', className: 'cy-plan'}));
    const steps = new Map();
    for (const p of S.pipeline || []) {
        const m = p.source === 'decompose' && STEP.exec(p.message);
        if (m) steps.set(m[1], {took: m[2] ? +m[2] * 1e3 : null, t: at(p.ts)});
    }
    // …how long so far is the strip's chip and the sum's: said here too, two clocks drifted apart (critic)
    box.innerHTML = `<div class="cp-head"${PLAN.since(hm(w.since * 1e3))}><b>${PLAN.title}</b></div>`
        + (!steps.size ? `<div class="cp-row cp-now">${PLAN.starting}</div>` : [...steps].map(([name, s]) => s.took != null
            ? `<div class="cp-row"><span>${esc(name)}</span>${tally(dur(s.took), 'took')}</div>`
            : `<div class="cp-row cp-now"><i></i><span>${esc(name)}</span>${tally(dur(Date.now() - s.t), 'running', PLAN.since(hm(s.t)))}</div>`).join(''));
}
