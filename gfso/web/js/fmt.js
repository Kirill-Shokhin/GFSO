// How the page writes a figure, a moment, a count of things and a text cut short — one spelling for every view.
export const LOCALE = 'en-GB';                     // the page's language, not the browser's

export const hm = t => new Date(t).toTimeString().slice(0, 5);
export const hms = t => new Date(t).toTimeString().slice(0, 8);
export const dayLong = t => new Date(t).toLocaleDateString(LOCALE, {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric'});
export const day = t => new Date(t).toLocaleDateString(LOCALE, {day: 'numeric', month: 'short'});
export const moment = t => new Date(t).toLocaleString(LOCALE);
// WHEN SOMETHING HAPPENED is said as the moment, never as an age: «13s ago» stood frozen until a reload, the moment stays
// true (the author, 2026-10-31: «висит эта цифра до тех пор пока не обновишь страницу»); the day only when not today's
// …against a day the reader already has (today by default; a launch's, in the project list)
export const clockAt = (t, ref = Date.now()) => new Date(t).toDateString() === new Date(ref).toDateString() ? hm(t) : `${day(t)} ${hm(t)}`;
export const when = t => new Date(t).toLocaleString(LOCALE, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
// an ISO stamp as written, to the minute (`from` 5 drops the year, `to` 19 keeps the seconds)
export const stamp = (iso, from = 0, to = 16) => String(iso).slice(from, to).replace('T', ' ');
export const dur = ms => ms < 90e3 ? `${Math.round(ms / 1e3)}s` : ms < 90 * 60e3 ? `${Math.round(ms / 60e3)}m` : `${(ms / 3600e3).toFixed(1)}h`;

// money and token counts; a count a provider did not report says so (`none`)
export const usd = x => `$${x.toFixed(2)}`;
export const NOT_REPORTED = 'not reported';
// a sum over sessions none of which reported a price is not reported, never $0.00 (another provider's case)
export const money = (cost, procs, unpriced) => procs > 0 && unpriced === procs ? NOT_REPORTED : usd(cost);
export const tok = (x, none = NOT_REPORTED) => x == null ? none : !x ? '0' : x >= 1e6 ? `${(x / 1e6).toFixed(1)}M` : x >= 1e3 ? `${Math.round(x / 1e3)}k` : `${x}`;
export const pct = x => `${Math.round(x * 100)}%`;
// a share of the CPUs Docker counts, one decimal
export const cpu = x => x == null ? '—' : `${x.toFixed(1)}%`;
// a size in memory or on disk; one Docker did not give says so
export const bytes = (x, none = NOT_REPORTED) => x == null ? none : x >= 1e9 ? `${(x / 1e9).toFixed(1)} GB`
    : x >= 1e6 ? `${Math.round(x / 1e6)} MB` : `${Math.round(x / 1e3)} kB`;

export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
export const cap = s => s ? s[0].toUpperCase() + s.slice(1) : s;
export const trim = (s, n = 20) => s.length > n ? s.slice(0, n - 1) + '…' : s;
