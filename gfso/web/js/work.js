// Who did the work: each model, in each role it served — how many sessions, how many turns, what it read and
// wrote, what it cost and what share of the run that is, and how close its sessions came to its window. The
// model is the node's real executor, so the run is signed by it (author, 2026-10-25). From the run model only.
import {esc} from './dom.js';
import {KIND_NAME as KIND} from './run.js';
import {modelName} from './vocab.js';

const usd = x => `$${x < 10 ? x.toFixed(2) : x.toFixed(1)}`;
const tok = x => !x ? '—' : x >= 1e6 ? `${(x / 1e6).toFixed(1)}M` : x >= 1e3 ? `${Math.round(x / 1e3)}k` : `${x}`;
const pct = x => `${Math.round(x * 100)}%`;
const median = xs => { const s = [...xs].sort((a, b) => a - b); return s[(s.length - 1) >> 1]; };

// how full the sessions' contexts got: the fullest turn of each, against the window of the model that ran it
function fill(r) {
    if (!r.fills.length) return '<span class="wk-none" title="recorded only for sessions run on a build that keeps it">not recorded</span>';
    const max = Math.max(...r.fills);
    return `<span class="wk-fill${max > 0.8 ? ' high' : ''}" title="each session's fullest turn against its window: median ${pct(median(r.fills))}, `
        + `fullest ${pct(max)}, ${r.fills.length} of ${r.calls} sessions recorded"><i style="width:${pct(max)}"></i></span>`
        + `${pct(median(r.fills))} · max ${pct(max)}`;
}

// cache read / written, apart where the session kept them apart — summed in the calls before that was kept
const cache = r => (r.read || r.write ? `${tok(r.read)} / ${tok(r.write)}` : '')
    + (r.unsplit ? `${r.read || r.write ? ' + ' : ''}<span title="read and written, one sum: recorded before they were kept apart">${tok(r.unsplit)} r+w</span>` : '');

export function render(el, run) {
    const {rows, total, unanswered} = run.work;
    if (!rows.length) return void (el.innerHTML = '<div class="pn-meta">no model call recorded yet</div>');
    const byModel = {};
    rows.forEach(r => (byModel[r.model] ??= {cost: 0, calls: 0, roles: []}, byModel[r.model].cost += r.cost,
        byModel[r.model].calls += r.calls, byModel[r.model].roles.push(KIND[r.kind])));
    el.innerHTML = `<div class="wk">
        <div class="cs-tiles">${Object.entries(byModel).sort((a, b) => b[1].cost - a[1].cost).map(([m, x]) =>
            `<div class="cs-tile"><b>${esc(modelName(m))}</b><span>${esc(x.roles.join(' · '))}</span>`
            + `<i>${usd(x.cost)}${total ? ` · ${pct(x.cost / total)} of the run` : ''} · ${x.calls} sessions</i></div>`).join('')}</div>
        <table class="wk-table"><thead><tr><th>model</th><th>role</th><th title="each model call is a session with a context of its own, unless it continued a conversation (marked)">sessions</th><th>turns</th><th>input</th><th>output</th>
            <th title="what the sessions read from the prompt cache / wrote to it">cache read / written</th><th>cost</th><th>share</th>
            <th title="each session's fullest turn against its model's window">context filled</th></tr></thead><tbody>
        ${rows.map(r => `<tr><td title="${esc(r.model)}">${esc(modelName(r.model))}</td><td>${KIND[r.kind]}</td><td>${r.calls}${r.resumed ? ` <span class="wk-none" title="a call that continued its round's conversation (cut at its turn cap) is no context of its own">· ${r.calls - r.resumed} contexts</span>` : ''}${Object.keys(r.ends).length ? ` <span class="wk-none" title="sessions that worked and gave no answer: a cut one's tokens are its turns' own and its price unknown; one out of turns is taken up by the next round">(${Object.entries(r.ends).map(([w, n]) => `${n} ${esc(WHY[w] || w.replace(/_/g, ' '))}`).join(', ')})</span>` : ''}</td>`
            + `<td>${!r.turned ? '—' : r.turned < r.calls ? `<span title="turns are recorded for ${r.turned} of the ${r.calls} sessions">${r.turns} in ${r.turned}</span>` : r.turns}</td><td>${tok(r.input)}</td><td>${tok(r.output)}</td><td>${cache(r) || '—'}</td>`
            + `<td>${usd(r.cost)}${r.unpriced ? ` <span class="wk-none" title="sessions that spent tokens with no cost recorded — a cut stream among them; the share is of what was priced">+ ${r.unpriced} unpriced</span>` : ''}</td><td>${total ? pct(r.cost / total) : '—'}</td><td>${fill(r)}</td></tr>`).join('')}
        </tbody></table>${unansweredLine(unanswered)}</div>`;
}

// sessions no model answered, said once under the table rather than counted as anyone's work
const ended = n => `${n} session${n > 1 ? 's' : ''}`;
const WHY = {limit: 'an account limit', prompt_too_long: 'the context outgrew the window', cut: 'cut', max_turns: 'out of turns',
             error_max_turns: 'out of turns', error: 'an error', '': 'cause not recorded'};
const unansweredLine = u => !Object.keys(u).length ? '' : `<div class="pn-meta wk-note">not counted above — sessions that spent `
    + `nothing: ${Object.entries(u).map(([k, why]) => `${KIND[k]}: ` + Object.entries(why).sort((a, b) => b[1] - a[1])
        .map(([w, n]) => `${n} ${esc(WHY[w] || w.replace(/_/g, ' '))}`).join(', ')).join(' · ')}</div>`;

// Who ran a node, in one line for its panel: by role, each model with its sessions on it.
// A node whose own sessions are booked nowhere — run inside a scope's session booked to its top, or done by the
// user's agent or a person, whose model the system is not told — is signed by who delivered it, and says so.
const deliveredBy = (run, id) => { const by = (run?.rounds[id] || []).map(r => r.by).filter(Boolean).at(-1);
    return by && !run.work.byNode[id]?.exec ? [`executed by <b>${esc(by)}</b> <span class="wk-none">· no session booked to this node — its model is not reported here</span>`] : []; };
export const signedBy = (run, id) => [
    ...deliveredBy(run, id),
    ...Object.entries(run?.work.byNode[id] || {}).map(([kind, ms]) =>
        `${{exec: 'executed', val: 'validated', issuer: 'issued', plan: 'planned'}[kind]} by `
        + Object.entries(ms).map(([m, n]) => `<b title="${esc(m)}">${esc(modelName(m))}</b>${n > 1 ? ` ×${n}` : ''}`).join(', ')),
    ...Object.entries(run?.work.unansweredOn[id] || {}).map(([k, n]) => `<span class="wk-none">${ended(n)} of ${KIND[k]} unanswered</span>`),
].join(' · ');
