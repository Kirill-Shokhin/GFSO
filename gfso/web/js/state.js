// What the page knows between reads: the last graph read and who signs. WHICH node is selected is
// store.js's — one source for every view.
import {$} from './dom.js';
import {PROJECT} from './api.js';
import {conjunct} from './run.js';

// `reload` is the page's refresh policy, set by main.js — units that change the graph call it.
export const S = {tasks: [], graph: {nodes: [], edges: []}, run: null, closures: [], missing: '', mineOnly: false,
                  inflight: [], project: PROJECT, reload: async () => {}};

// the processes this server runs in this project now — the in-flight registry, the one reading of it
export const procs = () => S.inflight.filter(w => w.project === S.project);

export const taskOf = id => S.tasks.find(t => t.id === id) || {};
// the criteria a verdict is over — a Dep edge's bare declaration is none, and a FAIL may not name it
export const critNames = id => (taskOf(id).criteria || []).filter(conjunct).map(c => c.name || c);
export const hasKids = id => S.tasks.some(t => t.parent_id === id && t.state !== 'ABANDONED');

// The box SIGNS every signal the page sends, so what was typed survives a reload (wave 26) — kept per
// browser, and wrapped because a browser with site data blocked THROWS on the accessor.
// an emptied box is the server's own agent again, as on load — never a move signed by nobody
// …and under a mode the page acts as that agent only: the box is hidden there, and a name remembered from another
// project would sign unseen and ask the engine for someone else's steps (critic)
export const myRole = () => (S.graph.mode?.mode ? '' : $('current-role').value.trim()) || S.agentId || '';
export function rememberedRole() { try { return localStorage.getItem('gfso.role') || ''; } catch (e) { return ''; } }
export function rememberRole(v) { try { localStorage.setItem('gfso.role', v); } catch (e) { /* nameless is fine */ } }
