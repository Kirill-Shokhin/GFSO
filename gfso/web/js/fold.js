// THE PLAN AT A GLANCE: which parts of a plan stand folded into the node above them, and what the folded ones ask for.
// The canvas draws what this says and measures for it; nothing here knows of the canvas.
// A plan too large to read whole folds a part's own parts — a 49-part plan drawn whole was dust at zoom 0.24 (audit DQ1/E2);
// the goal's parts always stand, and the reader unfolds a part by its tag or a double-click.
import {S, taskOf, nowOf, kept, keep} from './state.js';
import {bucketOf, cancelled, contested, closedByFail} from './vocab.js';
import {failingNow} from './run.js';
import {depths, ancestorsIn} from './tree.js';

const unfolded = new Set();
let folding = false, plan = null, project = null;
let hidden = {};                                // id → the drawn node it is folded into

// Decided on the plan itself, never on what is drawn of it: the folded drawing of a plan fits by being folded (critic 7: a
// folded plan gaining one part came out whole at the next read, then folded at the next part). So a changed set of nodes
// is decided anew: `whole` says so and clears the fold, the canvas measures the whole drawing and answers `decide`.
export function planChanged(nodes) {
    const now = `${S.project}|${nodes.map(n => n.id).sort().join('|')}`;
    if (now === plan) return false;
    if (S.project !== project) { project = S.project; unfolded.clear(); }
    plan = now; folding = false;
    return true;
}
export const decide = (nodes, tooSmall) => {
    const parent = Object.fromEntries(nodes.map(n => [n.id, n.parent_id]));
    folding = tooSmall && nodes.some(n => parent[parent[n.id]]);
    keep(`fold:${S.project}`, JSON.stringify({measured, folding}));
};
// The same drawing on the same canvas measures the same, so a load of a plan this viewer has seen lays the whole out no more:
// on a phone that layout was a second of the load. False: measure, and `decide` answers.
let measured = null;
// its hash: the drawing itself is 15 kB a plan in a store no one empties, and a collision costs a look, never a word
const hashed = text => [...text].reduce((h, c) => (Math.imul(h, 31) + c.charCodeAt(0)) | 0, text.length);
export const decidedBefore = (g, canvas) => {
    measured = hashed(JSON.stringify([g.nodes.map(n => [n.id, n.name]), g.edges.map(e => [e.source, e.target, e.type]), canvas]));
    const was = kept(`fold:${S.project}`, JSON.parse);
    if (was?.measured !== measured) return false;
    folding = was.folding;
    return true;
};

// the drawn node standing for each node: itself, or the outermost ancestor whose parts are folded
export function foldInto(tasks) {
    const d = depths(tasks), up = ancestorsIn(tasks), open = id => !folding || d[id] === 0 || unfolded.has(id);
    const rep = Object.fromEntries(tasks.map(t => [t.id, up(t.id).reverse().find(a => !open(a)) ?? t.id]));
    hidden = Object.fromEntries(tasks.filter(t => rep[t.id] !== t.id).map(t => [t.id, rep[t.id]]));
    return rep;
}
export const isHidden = id => id in hidden;
export const unfold = ids => ids.forEach(id => unfolded.add(id));
export const refold = () => { const any = unfolded.size > 0; unfolded.clear(); return any; };
// one node's parts folded back, by its tag: an unfolded node keeps a tag that says how many lie under it
export const refoldOne = id => unfolded.delete(id);
export const openHere = id => !folding || !unfolded.has(id) || !depths(S.tasks)[id] ? 0
    : S.tasks.filter(t => ancestorsIn(S.tasks)(t.id).includes(id) && !cancelled(t)).length;

// A FOLD HIDES NOTHING THAT ASKS: whatever the drawing marks on a node is counted on the node it is folded into, by the same
// looks — so what asks is never a list of cases of its own (critic 4: work at depth 2 vanished; critic 5: an escalated part
// the header called the reader to; critic 7: a contested one). Parts are counted as the header counts them, the cancelled left out.
const partsOf = id => Object.keys(hidden).filter(k => hidden[k] === id && !cancelled(taskOf(k)));
const closureOf = id => S.graph.nodes.find(n => n.id === id)?.closure;
const LOOKS = {
    failing: x => failingNow(S.run?.rounds[x], taskOf(x).state),
    decide: x => bucketOf(taskOf(x).state) === 'pathology',
    contested: x => contested(closureOf(x) || {}),
    byHand: x => closureOf(x)?.by_hand && !contested(closureOf(x)),
    shut: x => closedByFail(taskOf(x)),
    work: x => nowOf().work.has(x),
};
export const foldOf = id => { const xs = partsOf(id);
    return {n: xs.length, ...Object.fromEntries(Object.entries(LOOKS).map(([k, f]) => [k, xs.filter(f)]))}; };

// What asks for the reader among drawn nodes, its own or folded inside: the most pressing look that any of them shows.
const PRESSING = [LOOKS.failing, x => LOOKS.decide(x) || LOOKS.contested(x), LOOKS.work];
export function asking(ids) {
    for (const f of PRESSING) {
        const c = ids.filter(id => [id, ...partsOf(id)].some(f));
        if (c.length) return c;
    }
    return [];
}
