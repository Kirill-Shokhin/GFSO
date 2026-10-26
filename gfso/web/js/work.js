// Who did the work: each model, in each role it served — how many sessions, how many turns, what it read and
// wrote, what it cost and what share of the run that is, and how close its sessions came to its window. The
// model is the node's real executor, so the run is signed by it (author, 2026-10-25). From the run model only.
import {esc, hint} from './dom.js';
import {KIND_NAME as KIND} from './run.js';
import {modelName} from './vocab.js';
import {usd, tok as fmtTok} from './draw.js';

// what a provider did not report is said so; a reported 0 is a 0
const NOT = '<span class="wk-none">not reported</span>';
const tok = x => fmtTok(x, NOT);
const pct = x => `${Math.round(x * 100)}%`;
const median = xs => { const s = [...xs].sort((a, b) => a - b); return s[(s.length - 1) >> 1]; };

// how full the sessions' contexts got: the fullest turn of each, against the window of the model that ran it
function fill(r) {
    if (!r.fills.length) return '<span class="wk-none" title="Not recorded&#10;kept only for sessions run on a build that records it">not recorded</span>';
    const max = Math.max(...r.fills);
    return `<span class="wk-fill${max > 0.8 ? ' high' : ''}" title="${hint('Context filled', "each session's fullest turn against its window", `median ${pct(median(r.fills))} · fullest ${pct(max)}`,
        `${r.fills.length} of ${r.calls} sessions recorded`)}"><i style="width:${pct(max)}"></i></span>`
        + `${pct(median(r.fills))} · max ${pct(max)}`;
}

// cache read / written, apart where the session kept them apart — summed in the calls before that was kept
const cache = r => (r.read || r.write ? `${tok(r.read)} / ${tok(r.write)}` : '')
    + (r.unsplit ? `${r.read || r.write ? ' + ' : ''}<span title="Cache read + written&#10;one sum: recorded before the two were kept apart">${tok(r.unsplit)} r+w</span>` : '');

export function render(el, run) {
    const {rows, total, unanswered} = run.work;
    if (!rows.length) return void (el.innerHTML = '<div class="pn-meta">no model call recorded yet</div>');
    const byModel = {};
    rows.forEach(r => (byModel[r.model] ??= {cost: 0, calls: 0, priced: 0, roles: []}, byModel[r.model].cost += r.cost,
        byModel[r.model].calls += r.calls, byModel[r.model].priced += r.calls - r.unpriced, byModel[r.model].roles.push(KIND[r.kind])));
    // a price no session of it reported is no $0.00 and no 0% of the run
    const price = (x, priced) => priced ? usd(x) : NOT, share = (x, priced) => priced && total ? pct(x / total) : '—';
    el.innerHTML = `<div class="wk">
        <div class="cs-tiles">${Object.entries(byModel).sort((a, b) => b[1].cost - a[1].cost).map(([m, x]) =>
            `<div class="cs-tile"><b>${esc(modelName(m))}</b><span>${esc(x.roles.join(' · '))}</span>`
            + `<i>${price(x.cost, x.priced)}${x.priced && total ? ` · ${pct(x.cost / total)} of the run` : ''} · ${x.calls} sessions</i></div>`).join('')}</div>
        <table class="wk-table"><thead><tr><th>model</th><th>role</th><th title="Sessions&#10;each model call is a session with a context of its own&#10;unless it continued a conversation (marked)">sessions</th><th>turns</th><th>input</th><th>output</th>
            <th title="Cache read / written&#10;what the sessions read from the prompt cache, and wrote to it">cache read / written</th><th>cost</th><th>share</th>
            <th title="Context filled&#10;each session's fullest turn against its model's window">context filled</th></tr></thead><tbody>
        ${rows.map(r => `<tr><td title="${esc(r.model)}">${esc(modelName(r.model))}</td><td>${KIND[r.kind]}</td><td>${r.calls}${r.resumed ? ` <span class="wk-none" title="Contexts&#10;a call that continued its round's conversation (cut at its turn cap) is no context of its own">· ${r.calls - r.resumed} contexts</span>` : ''}${Object.keys(r.ends).length ? ` <span class="wk-none" title="Worked, gave no answer&#10;a cut session's tokens are its turns' own, its price unknown&#10;one out of turns is taken up by the next round">(${Object.entries(r.ends).map(([w, n]) => `${n} ${esc(WHY[w] || w.replace(/_/g, ' '))}`).join(', ')})</span>` : ''}</td>`
            + `<td>${!r.turned ? NOT : r.turned < r.calls ? `<span title="${hint('Turns', `recorded for ${r.turned} of the ${r.calls} sessions`)}">${r.turns} in ${r.turned}</span>` : r.turns}</td><td>${tok(r.input)}</td><td>${tok(r.output)}</td><td>${cache(r) || NOT}</td>`
            + `<td>${price(r.cost, r.calls - r.unpriced)}${r.unpriced && r.unpriced < r.calls ? ` <span class="wk-none" title="Unpriced&#10;sessions that spent tokens with no cost recorded — a cut stream among them&#10;the share is of what was priced">+ ${r.unpriced} unpriced</span>` : ''}</td><td>${share(r.cost, r.calls - r.unpriced)}</td><td>${fill(r)}</td></tr>`).join('')}
        </tbody></table>${unansweredLine(unanswered)}</div>`;
}

// sessions no model answered, said once under the table rather than counted as anyone's work
const WHY = {limit: 'an account limit', prompt_too_long: 'the context outgrew the window', cut: 'cut', max_turns: 'out of turns',
             error_max_turns: 'out of turns', error: 'an error', '': 'cause not recorded'};
const unansweredLine = u => !Object.keys(u).length ? '' : `<div class="pn-meta wk-note">not counted above — sessions that spent `
    + `nothing: ${Object.entries(u).map(([k, why]) => `${KIND[k]}: ` + Object.entries(why).sort((a, b) => b[1] - a[1])
        .map(([w, n]) => `${n} ${esc(WHY[w] || w.replace(/_/g, ' '))}`).join(', ')).join(' · ')}</div>`;

