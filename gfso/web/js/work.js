// Who did the work: each model, in each role it served — how many sessions and turns, what it cost and what share of
// the run that is, what that cost went to, and how close its sessions came to its window. The model is the node's real
// executor, so the run is signed by it (author, 2026-10-25). From the run model only.
// A model is named once — its tile says its window, its rows are grouped under it — and a row's figures are bars whose
// numbers are on hover: the same «median 27% of 200k» on every row was noise (the author, 2026-10-27).
import {esc, tally} from './dom.js';
import {modelName, TOKENS} from './vocab.js';
import {usd, tok as fmtTok, pct, money, NOT_REPORTED} from './fmt.js';
import {median} from './run.js';
import {MODELS, COST_CLS, KIND} from './hints.js';

// what a provider did not report is said so; a reported 0 is a 0
const NOT = `<span class="wk-none">${NOT_REPORTED}</span>`;
const tok = x => fmtTok(x, NOT);

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
    const kind = Object.fromEntries(TOKENS.map(([k, name, , field]) => [k, [name, fmtTok(r[field])]]));
    // NOT SPLIT: its tokens by kind as recorded — the cache a build kept as one sum said as one, never «0 read, 0 written»
    // beside the millions it holds (audit C1)
    if (!s || !total) return `<span class="wk-none"${MODELS.split(r.unsplit ? MODELS.unsplit : MODELS.foreign,
        [kind.input_tokens, kind.output_tokens, ...(r.unsplit ? [['cache, read and written as one', fmtTok(r.unsplit)]]
            : [kind.cache_read_tokens, kind.cache_write_tokens])])}>—</span>`;
    // the split's segments take the share of the row's cost they price, the rest one hatched segment saying why: drawn full
    // width, a split of 11% of a row read as the whole row's (audit C2)
    const rest = 1 - s.covered;
    return `<span class="wk-cost">${s.parts.map(([k, v]) => `<i class="${COST_CLS(k)}" style="width:${pct(s.covered * v / total)}"`
        + `${MODELS.part(kind[k][0], usd(v), s.covered * v / total, kind[k][1], k === 'cache_write_tokens' && MODELS.write(s.write))}></i>`).join('')}`
        + `${rest > 0.01 ? `<i class="wk-unsplit" style="width:${pct(rest)}"${MODELS.rest(rest, s)}></i>` : ''}</span>`;
}

export function render(el, run) {
    const {rows, total, unanswered, moved} = run.work;
    if (!rows.length) return void (el.innerHTML = '<div class="pn-meta">no model call recorded yet</div>');
    const byModel = {};
    rows.forEach(r => { const m = byModel[r.model] ??= {cost: 0, calls: 0, priced: 0, booked: 0, unpriced: 0, roles: [], rows: [], window: null};
        m.cost += r.cost; m.calls += r.calls - r.resumed; m.priced += r.calls - r.unpriced; m.booked += r.calls; m.unpriced += r.unpriced; m.roles.push(KIND[r.kind].name); m.rows.push(r); m.window ??= r.window; });
    const models = Object.entries(byModel).sort((a, b) => b[1].cost - a[1].cost);
    // a price no session of it reported is no $0.00 and no 0% of the run
    const price = (x, calls, unpriced) => (m => m === NOT_REPORTED ? NOT : m)(money(x, calls, unpriced)),
          share = (x, priced) => priced && total ? pct(x / total) : '—';
    const row = (r, i, m) => `<tr${i ? '' : ' class="wk-first"'}>${i ? '<td></td>' : `<td${MODELS.id(r.model)}><b>${esc(modelName(r.model))}</b></td>`}`
        + `<td>${KIND[r.kind].name}</td><td>${r.resumed ? `<span${MODELS.processes(r.calls)}>${r.calls - r.resumed}</span>` : r.calls}${r.handed ? tally(r.handed, 'passed on', MODELS.handed(r.handed)) : ''}`
        + `${Object.entries(r.ends).map(([w, n]) => tally(n, esc(WHY[w] || w.replace(/_/g, ' ')), MODELS.ends)).join('')}</td>`
        + `<td>${!r.turned ? `<span class="wk-none"${MODELS.unrecorded}>not recorded</span>` : r.turned < r.calls ? `<span${MODELS.turns(r.turned, r.calls)}>${r.turns} in ${r.turned}</span>` : r.turns}</td>`
        + `<td>${price(r.cost, r.calls, r.unpriced)}${r.unpriced && r.unpriced < r.calls ? tally(r.unpriced, 'unpriced', MODELS.unpriced) : ''}</td>`
        + `<td>${share(r.cost, r.calls - r.unpriced)}</td><td>${where(r)}</td><td>${fill(r)}</td></tr>`;
    el.innerHTML = `<div class="wk">
        <div class="cs-tiles">${models.map(([m, x]) =>
            `<div class="cs-tile"><b>${esc(modelName(m))}${x.window ? ` <em${MODELS.window}>${fmtTok(x.window)}</em>` : ''}</b><span>${esc(x.roles.join(' · '))}</span>`
            // its share of the run on a line of its own, and only beside another model — one model's 100% says nothing
            + `<i>${tally(price(x.cost, x.booked, x.unpriced), 'spent')}</i>${models.length > 1 && x.priced && total ? `<i>${tally(pct(x.cost / total), 'of the run')}</i>` : ''}<i>${tally(x.calls, 'sessions')}</i></div>`).join('')}</div>
        <table class="wk-table"><thead><tr><th>model</th><th>role</th><th${MODELS.sessions}>sessions</th><th>turns</th><th>cost</th><th>share</th>
            <th${MODELS.cost}>cost split</th>
            <th${MODELS.fill}>context filled</th></tr></thead><tbody>
        ${models.map(([m, x]) => x.rows.map((r, i) => row(r, i, m)).join('')).join('')}
        </tbody></table>${unansweredLine(unanswered)}${moved ? `<div class="pn-meta wk-note">${tally(moved, 'moved to the next credential', MODELS.moved)}</div>` : ''}</div>`;
}

// sessions no model answered, said once under the table rather than counted as anyone's work
const WHY = {limit: 'stopped at an account limit', prompt_too_long: 'outgrew the window', cut: 'cut', max_turns: 'out of turns',
             error_max_turns: 'out of turns', error: 'ended in an error', '': 'cause not recorded'};
const unansweredLine = u => !Object.keys(u).length ? '' : `<div class="pn-meta wk-note">not counted above — sessions that spent `
    + `nothing: ${Object.entries(u).map(([k, why]) => `${KIND[k].name}: ` + Object.entries(why).sort((a, b) => b[1] - a[1])
        .map(([w, n]) => `${n} ${esc(WHY[w] || w.replace(/_/g, ' '))}`).join(', ')).join(' · ')}</div>`;
