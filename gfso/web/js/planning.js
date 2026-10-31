// WHILE THE GOAL'S PLAN IS AUTHORED there is no graph to draw, and minutes of an empty canvas read as nothing running
// (the author, 2026-10-30: «не вижу в ui прогон»). The canvas then says what the server records: the authoring in flight,
// since when, and the stage it has reached — the engine's own field on that entry (`in_flight[].stage`: {stage, done, of,
// since}, pushed on the inflight feed), not the narration's prose read by a pattern, a copy register §2 forbids.
import {$, esc, tally, since} from './dom.js';
import {S, procs} from './state.js';
import {rootOf} from './tree.js';
import {hm} from './fmt.js';
import {PLAN} from './hints.js';

export function drawPlanning() {
    let box = $('cy-plan');
    const w = !rootOf(S.tasks) && procs().find(p => p.verb === 'auto_decompose');
    if (!w) return void box?.remove();
    box ??= $('cy').appendChild(Object.assign(document.createElement('div'), {id: 'cy-plan', className: 'cy-plan'}));
    const s = w.stage;
    // …how long so far is the strip's chip and the sum's: said here too, two clocks drifted apart (critic)
    box.innerHTML = `<div class="cp-head"${PLAN.since(hm(w.since * 1e3))}><b>${PLAN.title}</b></div>`
        + (!s ? `<div class="cp-row cp-now">${PLAN.starting}</div>`
            : `<div class="cp-row cp-now"><i></i><span>${esc(s.stage)}</span>${s.of > 1 ? tally(`${s.done}/${s.of}`, 'done') : ''}`
              + `${tally(since(s.since * 1e3), 'running', PLAN.since(hm(s.since * 1e3)))}</div>`);
}
