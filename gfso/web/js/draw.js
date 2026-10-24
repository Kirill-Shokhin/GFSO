// The drawing vocabulary of the views laid on the run's time: the folded clock as one x-scale (so a
// moment sits at the same x in all of them), its ticks and idle folds, and the verdict glyphs.
export const hm = t => new Date(t).toTimeString().slice(0, 5);
export const dur = ms => ms < 90e3 ? `${Math.round(ms / 1e3)}s` : ms < 90 * 60e3 ? `${Math.round(ms / 60e3)}m` : `${(ms / 3600e3).toFixed(1)}h`;

// A verdict as a glyph: PASS an ink dot, FAIL an accent cross — the one colour that asks for a look.
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
        ticks(y0, y1, ly) {
            const n = Math.max(2, Math.floor((W - left) / 110)), lo = run.clock.t0;
            return Array.from({length: n + 1}, (_, i) => lo + ((end - lo) * i) / n)
                .filter(t => !run.clock.folds.some(f => t > f.from && t < f.to))
                .map(t => `<g class="ax-tick"><line x1="${X(t)}" x2="${X(t)}" y1="${y0}" y2="${y1}"/>${ly == null ? '' : `<text x="${X(t)}" y="${ly}">${hm(t)}</text>`}</g>`).join('');
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
