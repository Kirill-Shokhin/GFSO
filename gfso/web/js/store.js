// What the person is pointing at, shared by every view: the node hovered and the node selected.
// A view publishes a gesture and redraws its own emphasis on change — views never call each other.
const subs = new Set(), state = {hover: null, select: null};

export const focus = () => state;
export const watch = fn => (subs.add(fn), () => subs.delete(fn));
export function point(key, id) {
    if (state[key] === id) return;
    state[key] = id;
    subs.forEach(fn => fn(state, key));
}

// Any element carrying `data-node` inside `el` takes part: hovering it points, clicking selects, and
// it wears `is-hover` / `is-select` while it is the one pointed at. `onMove(e)` adds the view's own tip.
export function bindFocus(el, onMove = () => {}, onLeave = () => {}) {
    const paint = st => {
        el.querySelectorAll('[data-node]').forEach(g => {
            g.classList.toggle('is-hover', g.dataset.node === st.hover);
            g.classList.toggle('is-select', g.dataset.node === st.select);
        });
        el.classList.toggle('has-focus', !!(st.hover || st.select));
    };
    el.onmousemove = e => (point('hover', e.target.closest('[data-node]')?.dataset.node || null), onMove(e));
    el.onmouseleave = () => (point('hover', null), onLeave());
    el.onclick = e => { const n = e.target.closest('[data-node]'); if (n) point('select', n.dataset.node); };
    el._unwatch?.();
    el._unwatch = watch(paint);
    paint(state);
}
