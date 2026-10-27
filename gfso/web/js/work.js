// Who did the work: each model, in each role it served — how many sessions and turns, what it cost and what share of
// the run that is, what that cost went to, and how close its sessions came to its window. The model is the node's real
// executor, so the run is signed by it (author, 2026-10-25). From the run model only.
// A model is named once — its tile says its window, its rows are grouped under it — and a row's figures are bars whose
// numbers are on hover: the same «median 27% of 200k» on every row was noise (the author, 2026-10-27).
import {esc} from './dom.js';
import {KIND_NAME as KIND} from './run.js';
import {modelName} from './vocab.js';
import {usd, tok as fmtTok} from './draw.js';
import {MODELS, TOKENS, COST_CLS} from './hints.js';

// what a provider did not report is said so; a reported 0 is a 0
const NOT = '<span class="wk-none">not reported</span>';
const tok = x => fmtTok(x, NOT);
const pct = x => `${Math.round(x * 100)}%`;
const median = xs => { const s = [...xs].sort((a, b) => a - b); return s[(s.length - 1) >> 1]; };

// how full the sessions' contexts got: the median session's fullest turn dark, the fullest session's light behind it
function fill(r) {
    if (!r.fills.length) return `<span class="wk-none"${MODELS.unrecorded}>not recorded</span>`;
    const max = Math.max(...r.fills), med = median(r.fills), w = r.window, of = x => [x, w ? fmtTok(Math.round(x * w)) : ''];
    const part = (which, x) => MODELS.fillOf(which, of(x), w && fmtTok(w), r.fills.length, r.calls);
    return `<span class="wk-fill${max > 0.8 ? ' high' : ''}">`
        + `<i class="max" style="width:${pct(max)}"${part('fullest', max)}></i><i style="width:${pct(med)}"${part('median', med)}></i></span>`;
}

// what the cost went to: one bar, a segment per kind of token; a segment's hover says that kind alone — its name, cost,
// share and tokens — so the figure looked for is the one under the cursor (the author, 2026-10-27); a row the price
// structure does not cover is said so, with its tokens
function where(r) {
    const s = r.split, total = s ? s.parts.reduce((x, [, v]) => x + v, 0) : 0;
    const counts = TOKENS.map(([k, name]) => [name, k === 'cache_read_tokens' ? r.read : k === 'cache_write_tokens' ? r.write
        : k === 'input_tokens' ? r.input : r.output]);
    if (!s || !total) return `<span class="wk-none"${MODELS.split(counts.map(([n, c]) => [n, '—', fmtTok(c)]), r.unsplit ? MODELS.unsplit : MODELS.foreign)}>—</span>`;
    const note = s.covered < 0.99 && MODELS.covers(pct(s.covered), s);
    return `<span class="wk-cost">${s.parts.map(([k, v], i) => `<i class="${COST_CLS(k)}" style="width:${pct(v / total)}"`
        + `${MODELS.part(counts[i][0], usd(v), v / total, fmtTok(counts[i][1]), note)}></i>`).join('')}</span>`;
}

export function render(el, run) {
    const {rows, total, unanswered} = run.work;
    if (!rows.length) return void (el.innerHTML = '<div class="pn-meta">no model call recorded yet</div>');
    const byModel = {};
    rows.forEach(r => { const m = byModel[r.model] ??= {cost: 0, calls: 0, priced: 0, roles: [], rows: [], window: null};
        m.cost += r.cost; m.calls += r.calls; m.priced += r.calls - r.unpriced; m.roles.push(KIND[r.kind]); m.rows.push(r); m.window ??= r.window; });
    const models = Object.entries(byModel).sort((a, b) => b[1].cost - a[1].cost);
    // a price no session of it reported is no $0.00 and no 0% of the run
    const price = (x, priced) => priced ? usd(x) : NOT, share = (x, priced) => priced && total ? pct(x / total) : '—';
    const row = (r, i, m) => `<tr${i ? '' : ' class="wk-first"'}>${i ? '<td></td>' : `<td${MODELS.id(r.model)}><b>${esc(modelName(r.model))}</b></td>`}`
        + `<td>${KIND[r.kind]}</td><td>${r.calls}${r.resumed ? ` <span class="wk-none"${MODELS.contexts}>· ${r.calls - r.resumed} contexts</span>` : ''}`
        + `${Object.keys(r.ends).length ? ` <span class="wk-none"${MODELS.ends}>(${Object.entries(r.ends).map(([w, n]) => `${n} ${esc(WHY[w] || w.replace(/_/g, ' '))}`).join(', ')})</span>` : ''}</td>`
        + `<td>${!r.turned ? NOT : r.turned < r.calls ? `<span${MODELS.turns(r.turned, r.calls)}>${r.turns} in ${r.turned}</span>` : r.turns}</td>`
        + `<td>${price(r.cost, r.calls - r.unpriced)}${r.unpriced && r.unpriced < r.calls ? ` <span class="wk-none"${MODELS.unpriced}>+ ${r.unpriced} unpriced</span>` : ''}</td>`
        + `<td>${share(r.cost, r.calls - r.unpriced)}</td><td>${where(r)}</td><td>${fill(r)}</td></tr>`;
    el.innerHTML = `<div class="wk">
        <div class="cs-tiles">${models.map(([m, x]) =>
            `<div class="cs-tile"><b>${esc(modelName(m))}${x.window ? ` <em${MODELS.window}>${fmtTok(x.window)}</em>` : ''}</b><span>${esc(x.roles.join(' · '))}</span>`
            + `<i>${price(x.cost, x.priced)}${x.priced && total ? ` · ${pct(x.cost / total)} of the run` : ''} · ${x.calls} sessions</i></div>`).join('')}</div>
        <table class="wk-table"><thead><tr><th>model</th><th>role</th><th${MODELS.sessions}>sessions</th><th>turns</th><th>cost</th><th>share</th>
            <th${MODELS.cost}>cost split</th>
            <th${MODELS.fill}>context filled</th></tr></thead><tbody>
        ${models.map(([m, x]) => x.rows.map((r, i) => row(r, i, m)).join('')).join('')}
        </tbody></table>${unansweredLine(unanswered)}</div>`;
}

// sessions no model answered, said once under the table rather than counted as anyone's work
const WHY = {limit: 'an account limit', prompt_too_long: 'the context outgrew the window', cut: 'cut', max_turns: 'out of turns',
             error_max_turns: 'out of turns', error: 'an error', '': 'cause not recorded'};
const unansweredLine = u => !Object.keys(u).length ? '' : `<div class="pn-meta wk-note">not counted above — sessions that spent `
    + `nothing: ${Object.entries(u).map(([k, why]) => `${KIND[k]}: ` + Object.entries(why).sort((a, b) => b[1] - a[1])
        .map(([w, n]) => `${n} ${esc(WHY[w] || w.replace(/_/g, ' '))}`).join(', ')).join(' · ')}</div>`;
