// The drawing vocabulary of the views laid on the run's time: the folded clock as one x-scale (so a
// moment sits at the same x in all of them), its ticks and idle folds, and the verdict glyphs.
export const hm = t => new Date(t).toTimeString().slice(0, 5);
const hms = t => new Date(t).toTimeString().slice(0, 8);
// round steps for the time axis: seconds on a short run, then minutes, hours, a day
const STEPS = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400].map(s => s * 1e3);
export const dur = ms => ms < 90e3 ? `${Math.round(ms / 1e3)}s` : ms < 90 * 60e3 ? `${Math.round(ms / 60e3)}m` : `${(ms / 3600e3).toFixed(1)}h`;

// A verdict as a glyph: PASS a dot, FAIL a cross — two shapes that never blend, whatever lies under them.
export const mark = (v, x, y, r = 4) => v === 'PASS' ? `<circle class="mk-pass" cx="${x}" cy="${y}" r="${r}"/>`
    : `<path class="mk-fail" d="M${x - r},${y - r}l${2 * r},${2 * r}m0,-${2 * r}l-${2 * r},${2 * r}"/>`;
// the same glyph standing alone in text or a table cell
export const glyph = (v, r = 4) => `<svg class="glyph" width="${2 * r + 4}" height="${2 * r + 4}" viewBox="${-r - 2} ${-r - 2} ${2 * r + 4} ${2 * r + 4}">${mark(v, 0, 0, r)}</svg>`;
export const trim = (s, n = 20) => s.length > n ? s.slice(0, n - 1) + '…' : s;


export function frame(run, W, left, right = 16) {
    const span = Math.max(run.clock.span, 60e3), k = (W - left - right) / span;
    const X = t => left + run.clock.x(t) * k;
    const end = Math.max(run.clock.t0, ...run.sessions.map(s => s.end), ...run.audit.map(a => a.t));
    return {
        X,
        // ticks on round clock times, a step from the ladder that keeps them ~110 px apart over the FOLDED span: equal
        // fractions of the span labelled to the minute repeated a label on a short run (02:27, 02:27, 02:28… — a
        // newcomer reading the page, 2026-10-26)
        ticks(y0, y1, ly) {
            const n = Math.max(2, Math.floor((W - left) / 110)), lo = run.clock.t0;
            const step = STEPS.find(s => span / s <= n) || STEPS.at(-1), tz = new Date(lo).getTimezoneOffset() * 60e3;
            // a run over days names the day on its first tick of each new day — at midnight, or after an overnight fold that
            // swallowed midnight: 12:00 … 12:00 were two different noons (critic, 2026-10-26)
            const day = t => new Date(t).toLocaleDateString('en', {month: 'short', day: 'numeric'}), ts = [];
            for (let t = Math.ceil((lo - tz) / step) * step + tz; t <= end; t += step) ts.push(t);
            const shown = ts.filter(t => !run.clock.folds.some(f => t > f.from && t < f.to));
            const days = new Set(shown.map(t => new Date(t).toDateString())).size > 1;
            const label = (t, i) => { const d = new Date(t);
                if (step < 60e3) return hms(t);
                if (!days || (i && new Date(shown[i - 1]).toDateString() === d.toDateString())) return hm(t);
                return d.getHours() || d.getMinutes() ? `${day(t)} ${hm(t)}` : day(t); };
            return shown.map((t, i) => `<g class="ax-tick"><line x1="${X(t)}" x2="${X(t)}" y1="${y0}" y2="${y1}"/>${ly == null ? '' : `<text x="${X(t)}" y="${ly}">${label(t, i)}</text>`}</g>`).join('');
        },
        folds(y0, y1, ly) {
            return run.clock.folds.map(f => { const x = left + f.at * k;
                return `<g class="ax-fold"><path d="M${x},${y0}V${y1}"/><text x="${x + 4}" y="${ly}">${dur(f.to - f.from)} idle</text></g>`; }).join('');
        },
        // a step series as a filled area from the baseline y0, scaled so `max` reaches height h
        area(steps, y0, h, max) {
            let d = `M${X(steps[0]?.[0] ?? run.clock.t0)},${y0}`;
            for (const [t, c] of steps) d += `H${X(t)}V${y0 - (c / max) * h}`;
            return d + `H${X(end)}V${y0}Z`;
        },
    };
}
