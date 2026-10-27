// What the page knows between reads: the last graph read and who signs. WHICH node is selected is
// store.js's — one source for every view.
import {$} from './dom.js';
import {PROJECT} from './api.js';
import {childrenOf} from './tree.js';
import {cancelled} from './vocab.js';

// THE WHOLE SURFACE, written by its owners and read by the views:
//   model.js — tasks, graph, closures, missing (the graph read); frontier, runState, waiting, steps, mySteps (the
//              engine's next_steps); run, pipeline (the run read and built); reports, metrics (the system's own reads)
//   main.js  — inflight (the server's processes), agentId, reload (the page's refresh policy: units that change the
//              graph call it); projects.js — project; graph.js — mineOnly
export const S = {tasks: [], graph: {nodes: [], edges: []}, closures: [], missing: '',
                  frontier: null, runState: null, waiting: null, steps: null, mySteps: new Map(),
                  run: null, pipeline: [], reports: [], metrics: null,
                  inflight: [], agentId: '', project: PROJECT, mineOnly: false, reload: async () => {}};

// the processes this server runs in this project now — the in-flight registry, the one reading of it
export const procs = () => S.inflight.filter(w => w.project === S.project);
// the project's work has begun: a node exists, or a process runs here — the goal's own plan authored before its root
// exists is work; read as «nothing yet», the page offered «Pose the goal» and no Stop over a planning run (a live row)
export const begun = () => S.tasks.length > 0 || procs().length > 0;

export const taskOf = id => S.tasks.find(t => t.id === id) || {};
export const hasKids = id => childrenOf(S.tasks, id).some(t => !cancelled(t));

// What this browser keeps for its viewer — wrapped, because a browser with site data blocked THROWS on the accessor.
export const kept = (k, read = x => x) => { try { return read(localStorage.getItem(k)); } catch (e) { return null; } };
export const keep = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* a per-viewer nicety */ } };

// The box SIGNS every signal the page sends, so what was typed survives a reload (wave 26) — kept per browser.
// an emptied box is the server's own agent again, as on load — never a move signed by nobody
// …and under a mode the page acts as that agent only: the box is hidden there, and a name remembered from another
// project would sign unseen and ask the engine for someone else's steps (critic)
export const myRole = () => (S.graph.mode?.mode ? '' : $('current-role').value.trim()) || S.agentId || '';
export const rememberedRole = () => kept('gfso.role') || '';
export const rememberRole = v => keep('gfso.role', v);
