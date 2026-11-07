// The plan's tree, read off the nodes' parents (split edges are drawn from it, never the reverse): its root, a node's
// parts, its ancestors nearest first, and every node's depth — the goal 0.
export const isRoot = t => !t.parent_id;
export const rootOf = nodes => nodes.find(isRoot);
export const childrenOf = (nodes, id) => nodes.filter(t => t.parent_id === id);
export const ancestorsIn = nodes => { const up = Object.fromEntries(nodes.map(t => [t.id, t.parent_id]));
    return id => { const out = []; for (let x = up[id]; x; x = up[x]) out.push(x); return out; }; };
export function depths(nodes) {
    const by = Object.fromEntries(nodes.map(n => [n.id, n])), d = {};
    const of = id => d[id] ??= by[id]?.parent_id ? of(by[id].parent_id) + 1 : 0;
    nodes.forEach(n => of(n.id));
    return d;
}
