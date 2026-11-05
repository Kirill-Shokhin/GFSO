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
