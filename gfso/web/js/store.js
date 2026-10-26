// What the person is pointing at, shared by every view: the node hovered and the node selected.
// A view publishes a gesture and redraws its own emphasis on change — views never call each other.
// A watcher owned by an element lives as long as what is drawn there: the deck releases its view before it
// draws the next one — a watcher left from another tab threw on markup that was gone and silenced every
// watcher after it.
const subs = new Map(), state = {hover: null, select: null, picks: 0};   // picks: selections made so far

export const focus = () => state;
export const watch = (fn, owner = null) => (subs.set(fn, owner), () => subs.delete(fn));
export const release = root => subs.forEach((owner, fn) => owner && root.contains(owner) && subs.delete(fn));
export function point(key, id) {
    if (state[key] === id) return;
    state[key] = id;
    if (key === 'select') state.picks++;
    subs.forEach((_, fn) => fn(state, key));
}

// The selected node's row in a deck view is brought into the deck's sight: among fifty rows it sat below the fold.
// Only a selection not yet brought on this drawing of the view — a redraw on a feed event must not pull the reader's
// scroll back; the deck forgets what was brought when it opens a view, so a tab returned to brings it again.
// `find(id)` is the row's element.
export function bringSelected(el, find) {
    const bring = () => {
        const box = el.closest('.dk-body'), row = state.select && find(state.select);
        if (!box || !row) return;
        el._brought = state.picks;
        const b = row.getBoundingClientRect(), v = box.getBoundingClientRect();
        if (b.top < v.top || b.bottom > v.bottom) box.scrollTop += b.top - v.top - (v.height - b.height) / 2;
    };
    if (el._brought !== state.picks) bring();
    watch((st, key) => key === 'select' && bring(), el);
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
    watch(paint, el);
    paint(state);
    return paint;
}
