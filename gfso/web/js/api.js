// The server, as this tab sees it. The TAB owns its project (?project= in the URL): two tabs are two
// projects at once, so every call carries it — ONCE (a doubled `project=` was seen in wave 27).
const q = new URLSearchParams(location.search);
export const PROJECT = q.get('project') || '';
export const TASK = q.get('task') || '';
export const GOAL = q.has('goal');                    // arrived to state this project's goal

export const api = (url, opts) => fetch(PROJECT && !url.includes('project=')
    ? url + (url.includes('?') ? '&' : '?') + 'project=' + encodeURIComponent(PROJECT) : url, opts);
export const getJSON = async url => (await api(url)).json();
export const post = (url, body) => api(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                             body: JSON.stringify(body)});

// SERIALISED: a WebSocket transition and an ordinary refresh interleaving cleared the canvas under each
// other's `cy.add` (wave 27, 2026-09-06). A caller arriving mid-run waits for the run doing its work.
// …and a caller arriving mid-run is answered by ONE more run after it, never by the run already under way: that run
// read the state before the caller's news — five ACCEPTs in 40 ms left the header saying "not started" for the
// length of a run (a live run, 2026-10-25). Callers arriving meanwhile share that one trailing run.
export const singleFlight = fn => {
    let run = null, next = null;
    const go = () => run = fn().finally(() => { run = null; });
    return () => !run ? go() : next ??= run.catch(() => {}).then(() => { next = null; return go(); });
};
