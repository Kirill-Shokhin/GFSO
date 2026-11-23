// THE PLAN AT A GLANCE: which parts of a plan stand folded into the node above them, and what the folded ones ask for.
// The canvas draws what this says and measures for it; nothing here knows of the canvas.
// A plan too large to read whole folds a part's own parts — a 49-part plan drawn whole was dust at zoom 0.24 (audit DQ1/E2);
// the view's own parts always stand, and the reader goes down into a part by its tag or a double-click, never unfolds it.
import {S, taskOf, nowOf, kept, keep, inView, inWorkOf} from './state.js';
import {bucketOf, cancelled, contested, closedByFail} from './vocab.js';
import {failingNow} from './run.js';
import {depths, ancestorsIn, childrenOf} from './tree.js';
import {FOCUS, TOP} from './api.js';

let folding = false, plan = null;
// …remembered per view, so a move back to a part seen before lays it out once, not twice
const KEY = () => `fold:${S.project}|${FOCUS}`;
let hidden = {};                                // id → the drawn node it is folded into

// Decided on the plan itself, never on what is drawn of it: the folded drawing of a plan fits by being folded (critic 7: a
// folded plan gaining one part came out whole at the next read, then folded at the next part). So a changed set of nodes
// is decided anew: `whole` says so and clears the fold, the canvas measures the whole drawing and answers `decide`.
export function planChanged(nodes) {
    const now = `${S.project}|${nodes.map(n => n.id).sort().join('|')}`;
    if (now === plan) return false;
    plan = now; folding = false;
    return true;
}
export const decide = (nodes, tooSmall) => {
    const parent = Object.fromEntries(nodes.map(n => [n.id, n.parent_id]));
    folding = tooSmall && nodes.some(n => parent[parent[n.id]]);
    keep(KEY(), JSON.stringify({measured, folding}));
};
// The same drawing on the same canvas measures the same, so a load of a plan this viewer has seen lays the whole out no more:
// on a phone that layout was a second of the load. False: measure, and `decide` answers.
let measured = null;
// its hash: the drawing itself is 15 kB a plan in a store no one empties, and a collision costs a look, never a word
const hashed = text => [...text].reduce((h, c) => (Math.imul(h, 31) + c.charCodeAt(0)) | 0, text.length);
export const decidedBefore = (g, canvas) => {
    measured = hashed(JSON.stringify([g.nodes.map(n => [n.id, n.name]), g.edges.map(e => [e.source, e.target, e.type]), canvas]));
    const was = kept(KEY(), JSON.parse);
    if (was?.measured !== measured) return false;
    folding = was.folding;
    return true;
};

// THE VIEW FROM ONE PART (`?focus=`): that part and everything under it, drawn as the goal is — its own parts standing, a
// large plan folding below them — with the edges among them; what lies above it is said as its path, not drawn. What
// waits on whom across its border stays drawn: a node outside that a part inside uses, or that uses one, stands at the
// edge of the view, faint and alone, with its Dep edge — cut, the author's own part showed a flat row of calls while 17
// nodes elsewhere waited on them (critic 3). A part that is not in the graph (a stale link) shows the whole.
export function viewed(g) {
    if (!FOCUS || !g.nodes.some(n => n.id === TOP)) return g;
    const keep = new Set(g.nodes.filter(n => inView(n.id)).map(n => n.id));      // one rule of what is in the view (state.js)
    // …a WAIT, an edge with neither end settled: one whose end is done or cancelled orders nothing still to come (§11.5 reads
    // no edge one of whose ends is settled), and the cancelled parts of the author's own view drew twenty nodes from
    // elsewhere along their dead edges (the author, 11-20: «отменил кучу нод и они мусором висят на странице»)
    const live = id => { const s = g.nodes.find(n => n.id === id)?.state; return s !== 'DONE' && s !== 'ABANDONED'; };
    const across = g.edges.filter(e => e.type !== 'parent-child' && keep.has(e.source) !== keep.has(e.target) && live(e.source) && live(e.target));
    const outside = new Set(across.map(e => keep.has(e.source) ? e.target : e.source));
    return {...g, nodes: [...g.nodes.filter(n => keep.has(n.id)).map(n => n.id === TOP ? {...n, parent_id: null} : n),
                          ...g.nodes.filter(n => outside.has(n.id)).map(n => ({...n, parent_id: null, outside: true}))],
            edges: [...g.edges.filter(e => keep.has(e.source) && keep.has(e.target)), ...across]};
}
// the drawn node standing for each node: itself, or the outermost ancestor whose parts are folded
export function foldInto(tasks) {
    const d = depths(tasks), up = ancestorsIn(tasks), open = id => !folding || d[id] === 0;
    const rep = Object.fromEntries(tasks.map(t => [t.id, up(t.id).reverse().find(a => !open(a)) ?? t.id]));
    hidden = Object.fromEntries(tasks.filter(t => rep[t.id] !== t.id).map(t => [t.id, rep[t.id]]));
    return rep;
}
export const isHidden = id => id in hidden;
// A FOLD HIDES NOTHING THAT ASKS: whatever the drawing marks on a node is counted on the node it is folded into, by the same
// looks — so what asks is never a list of cases of its own (critic 4: work at depth 2 vanished; critic 5: an escalated part
// the header called the reader to; critic 7: a contested one). Parts are counted as the header counts them, the cancelled left out.
let grouped = null, groupedOf = null;   // the fold's parts by the node they are folded into, once a fold
const partsOf = id => { if (groupedOf !== hidden) { grouped = {}; for (const [k, v] of Object.entries(hidden)) (grouped[v] ??= []).push(k); groupedOf = hidden; }
    return (grouped[id] || []).filter(k => !cancelled(taskOf(k))); };
const closureOf = id => S.graph.nodes.find(n => n.id === id)?.closure;
// in work by the log (run.js `inWork`), one reading with the deck's line and list; kept per read of the plan and the log
let heldOf = null, held = new Set();
const inWorkNow = x => { if (heldOf?.[0] !== S.tasks || heldOf[1] !== S.run) { heldOf = [S.tasks, S.run]; held = new Set(inWorkOf().map(r => r.t.id)); } return held.has(x); };
const LOOKS = {
    held: inWorkNow,
    failing: x => failingNow(S.run?.rounds[x], taskOf(x).state),
    decide: x => bucketOf(taskOf(x).state) === 'pathology',
    contested: x => contested(closureOf(x) || {}),
    shut: x => closedByFail(taskOf(x)),
    work: x => nowOf().work.has(x),
};
export const foldOf = id => { const xs = partsOf(id);
    // `direct`: the parts one step down, the number the node's panel says and going down shows (the tag said every part on
    // every level — 430 against the panel's 18, the author 2026-11-18); the looks still read everything inside
    return {n: xs.length, direct: childrenOf(S.tasks, id).filter(t => t.state !== 'ABANDONED').length,   // …counted as the panel counts
        ...Object.fromEntries(Object.entries(LOOKS).map(([k, f]) => [k, xs.filter(f)]))}; };

// What asks for the reader among drawn nodes, its own or folded inside: the most pressing look that any of them shows.
const PRESSING = [LOOKS.failing, x => LOOKS.decide(x) || LOOKS.contested(x), x => LOOKS.held(x) || LOOKS.work(x)];   // in work by the log, whoever works it
export function asking(ids) {
    for (const f of PRESSING) {
        const c = ids.filter(id => [id, ...partsOf(id)].some(f));
        if (c.length) return c;
    }
    return [];
}
