// The server, as this tab sees it. The TAB owns its project (?project= in the URL): two tabs are two
// projects at once, so every call carries it — ONCE (a doubled `project=` was seen in wave 27).
const q = new URLSearchParams(location.search);
export const PROJECT = q.get('project') || '';
export const TASK = q.get('task') || '';
export const GOAL = q.has('goal');                    // arrived to state this project's goal
// …and the tab goes to another project by its URL alone; `goal` opens the goal constructor there — a new project's first
// act is stating its goal. Leaving names none: the list of projects.
export const openProject = (name, {goal} = {}) => { location.search = '?project=' + encodeURIComponent(name) + (goal ? '&goal=1' : ''); };
export const leave = () => { location.search = ''; };
// A PART OF THE GRAPH OPENED AS ITS OWN VIEW (`?focus=` beside the project): the same graph and log drawn from that part
// down, never a project of its own (the author, 2026-11-13: «не просто тупая кнопка которая срежет все сверху роды и
// наплодит сотню проектов»). None: the whole graph.
// Going down and up is the way a large graph is read (the author, 11-15: «хождение по графу туда сюда … максимально юзер
// френдли - быстрым и интуитивным. тогда раскрытие окажется лишней функцией»): a move is no load — the same graph and
// log are drawn again from the new part (`whenMoved`, main.js), the address and the browser's Back follow it.
export let FOCUS = q.get('focus') || '';
// what the view's top is called, one word for every place that names it (Progress, Spend's levels, the done mark)
export let TOP_WORD = FOCUS ? 'the part' : 'the goal';
let moved = () => {}, within = () => false;
// `inside(id, part)`: id is the part or lies under it — the tree is the page's (state.js), not this door's
export const whenMoved = (f, inside) => { moved = f; within = inside; };
const at = id => { id = id || ''; if (id === FOCUS) return false;
    FOCUS = id; TOP_WORD = FOCUS ? 'the part' : 'the goal'; moved(); return true; };
const address = id => { const p = new URLSearchParams(location.search); p.delete('task');
    id ? p.set('focus', id) : p.delete('focus'); return '?' + p; };
const focusHere = () => new URLSearchParams(location.search).get('focus') || '';

// THE TAB'S HISTORY, ONE ENTRY A STEP, EACH KNOWING ITS PLACE from the page's first (`gfsoAt`). Down pushes an entry. UP
// UNWINDS the entries of the part being left — a finger's steps included (main.js) — back to the view above; where the
// page's first entry is reached still inside the part, that entry becomes the view above; where the unwinding lands
// outside the part elsewhere, the view above is gone to from there. Back is the browser's own: it shows the entry it
// lands on. (Guessing an entry's origin made Back go up and then down into the same part again on a phone — critics 2–4.)
const place = () => history.state?.gfsoAt ?? 0;
history.replaceState({...history.state, gfsoAt: place()}, '');
// …and a part opened by its link stands one step above the whole graph: with no entry under it, Back left the page. The
// entry is laid at the first touch, click or key — never at load: a browser's Back skips any entry a page laid with no
// gesture (Chromium's history intervention; critic 2 measured it through the browser's own Back), so before any touch
// Back leaves by the browser's rule and no page can change that. Laid once, the address as it came kept on the part's own.
const layUnder = () => {
    if (!FOCUS || place() !== 0 || history.state?.gfsoUnder) return;
    const came = location.search;
    history.replaceState({gfsoAt: 0}, '', address(''));
    history.pushState({gfsoAt: 1, gfsoUnder: 1}, '', came);
};
for (const k of ['pointerdown', 'keydown']) addEventListener(k, layUnder, {capture: true, once: true});
export const pushStep = state => history.pushState({...history.state, ...state, gfsoAt: place() + 1}, '');
let leaving = null, popped = null;
const unwind = () => {
    const here = focusHere(), l = leaving;
    // …every entry below the view gone to, not only the deepest part's: a path click up two levels left the middle one in
    // Back, which went down into it (critic 5)
    if (here !== l.to && within(here, l.to) && place() > 0) return history.back();   // its popstate unwinds on
    leaving = null;
    if (here === l.to) return at(here);
    if (within(here, l.to)) history.replaceState({...history.state, gfsoAt: 0}, '', address(l.to));
    else history.pushState({gfsoAt: place() + 1}, '', address(l.to));
    at(l.to);
};
export const openFocus = (id, up = false) => { id = id || ''; if (id === FOCUS || leaving) return;
    if (up) { leaving = {from: FOCUS, to: id}; return unwind(); }
    history.pushState({gfsoAt: place() + 1}, '', address(id)); at(id); };
// …a Back taken by an unwinding or that moved the view is that move, and no other listener acts on it (main.js)
export const movedBy = e => e === popped;
addEventListener('popstate', e => { if (leaving) { popped = e; return unwind(); } if (at(focusHere())) popped = e; });

export const api = (url, opts) => fetch(PROJECT && !url.includes('project=')
    ? url + (url.includes('?') ? '&' : '?') + 'project=' + encodeURIComponent(PROJECT) : url, opts);
// A READ THAT NEVER ANSWERS ENDS AS A FAILED ONE: one read at a time (`singleFlight`) means a hung one silences every later one
export const bounded = () => ({signal: AbortSignal.timeout(30e3)});
export const getJSON = async url => (await api(url, bounded())).json();
// one node's record, or a facet of it (`/verdict`, `/critique`, `/actions?…`)
export const taskUrl = (id, sub = '') => `/api/tasks/${encodeURIComponent(id)}${sub}`;
export const task = (id, sub) => getJSON(taskUrl(id, sub));
export const post = (url, body, opts) => api(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                                   body: JSON.stringify(body), ...opts});

// The engine's no, as the engine wrote it, or '' — the server's contract (server.py): a malformed call or a `refused`
// is a 422 carrying `detail` or the verb's dict, an `accepted: false` / `recorded: false` / `error` a 200 saying so.
// Read once here: five call sites read it five ways, two of them took a 422 with no `error` for success.
export async function refusal(r) {
    const out = await r.json().catch(() => ({}));
    const no = !r.ok || out.refused || out.error || out.accepted === false || out.recorded === false;
    const said = out.error || out.reason || (typeof out.detail === 'string' ? out.detail : out.detail ?? (Object.keys(out).length ? out : null));
    return !no ? '' : String(said == null ? `the server answered ${r.status}` : typeof said === 'string' ? said : JSON.stringify(said));
}

// SERIALISED: a WebSocket transition and an ordinary refresh interleaving cleared the canvas under each
// other's `cy.add` (wave 27, 2026-09-06). A caller arriving mid-run waits for the run doing its work.
// …and a caller arriving mid-run is answered by ONE more run after it, never by the run already under way: that run
// read the state before the caller's news — five ACCEPTs in 40 ms left the header saying "not started" for the
// length of a run (a live run, 2026-10-25). Callers arriving meanwhile share that one trailing run.
// The trailing run starts inside the finishing one's `finally`, so no caller finds the flight empty between the two
// and starts a second, concurrent one (critic: two runs at once once the gap was hit).
export const singleFlight = fn => {
    let run = null, next = null, release;
    const go = () => run = fn().finally(() => {
        run = null;
        if (next) { const r = release; next = null; r(go()); }
    });
    return () => !run ? go() : next ??= new Promise(res => { release = res; });
};
