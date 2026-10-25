// The canvas: cytoscape, drawn from the graph read, every colour from the brand tokens (tokens.css).
import {$, esc} from './dom.js';
import {api, singleFlight} from './api.js';
import {S, taskOf, myRole} from './state.js';
import {bucketOf, statusLabel, contested} from './vocab.js';
import {banner} from './overlays.js';
import {tip, untip} from './tip.js';
import {point, watch, focus} from './store.js';
import {roundsLine, waitWords, atWork} from './run.js';

// Leaf tokens are hex literals; getComputedStyle returns the specified value of an unregistered property.
const cs = getComputedStyle(document.documentElement), tok = n => cs.getPropertyValue(n).trim();
const [INK, SOFT, FAINT, PAPER, BG, ACC] = ['--ink', '--ink-soft', '--ink-faint', '--paper', '--bg', '--acc'].map(tok);
// cytoscape refuses the stack with the quotes CSS requires and takes it unquoted (probed, 2026-09-06).
const FONT = tok('--font-body').replace(/['"]/g, '').replace(/\s+/g, ' ').trim();
const inkAlpha = a => `rgba(${[0, 2, 4].map(i => parseInt(INK.slice(1 + i, 3 + i), 16))},${a})`;   // cy needs rgba, not color-mix

const S_ = (bg, fg, bw, bc, bs = 'solid', bo = 1) => ({bg, fg, bw, bc, bs, bo});
const NODE_STYLE = {
    done:      S_(INK, BG, 0, INK),
    quiet:     S_(BG, FAINT, 1, FAINT, 'solid', 0),
    attend:    S_(SOFT, BG, 0, SOFT),
    fail:      S_(ACC, BG, 0, ACC),
    pathology: S_(SOFT, BG, 1.5, INK, 'dashed'),
    busy:      S_(BG, INK, 2, ACC),     // in flight: the accent border says "alive" without asking for attention
};
const styleOf = s => NODE_STYLE[bucketOf(s)];
// The drawing carries what the record carries (§15.7): contradicted → the accent, ringed (owed an
// answer); asserted by hand → dotted in paper (closed, on somebody's word).
export const closureStyle = (st, cl) => !cl ? st
    : contested(cl) ? {...st, bw: 3, bc: ACC, bs: 'solid', bo: 1}
    : cl.by_hand    ? {...st, bw: 2, bc: PAPER, bs: 'dotted', bo: 1}
    : st;

// A NAME CUT MID-WORD IS A NAME YOU HAVE TO GUESS AT: cut at the last word that fits and say so.
const LABEL_MAX = 38;
function readableLabel(text) {
    const t = String(text || '').trim();
    if (t.length <= LABEL_MAX) return t;
    const cut = t.slice(0, LABEL_MAX), sp = cut.lastIndexOf(' ');
    return (sp > LABEL_MAX * 0.5 ? cut.slice(0, sp) : cut).replace(/[ ,;:.-]+$/, '') + '…';
}

const LAYOUT = {name: 'dagre', rankDir: 'TB', spacingFactor: 1.4, nodeSep: 35, rankSep: 55};
let cy;

export async function initGraph() {
    // A canvas draws with whatever face is loaded NOW and never redraws for a late one: without this wait the
    // labels came out in the fallback face whenever the brand font lost the race (seen on the module split).
    await Promise.race([document.fonts.load(`500 11px ${FONT}`).catch(() => {}), new Promise(r => setTimeout(r, 1500))]);
    cy = cytoscape({
        container: $('cy'),
        style: [
            {selector: 'node', style: {
                'label': 'data(label)', 'background-color': 'data(bg)', 'background-opacity': 'data(bo)',
                'color': 'data(fg)', 'border-width': 'data(bw)', 'border-color': 'data(bc)',
                'border-style': 'data(bs)', 'font-family': FONT, 'text-valign': 'center', 'text-halign': 'center',
                'font-size': '11px', 'font-weight': '500',
                'width': 'label', 'height': 30, 'padding': '8px',
                'shape': 'round-rectangle', 'text-wrap': 'wrap', 'text-max-width': '140px'}},
            {selector: 'node:selected', style: {'border-width': 2, 'border-color': INK, 'border-style': 'solid'}},
            {selector: 'edge', style: {
                'width': 1, 'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
                'line-color': inkAlpha(0.30), 'target-arrow-color': inkAlpha(0.30), 'arrow-scale': 0.7}},
            {selector: 'edge[type="dependency"]', style: {'line-style': 'dashed', 'line-color': ACC, 'target-arrow-color': ACC}},
            {selector: 'node.focus', style: {'underlay-color': INK, 'underlay-opacity': 0.12, 'underlay-padding': 7}},
            // no grey press overlay: the selection border is the one mark a tap leaves
            {selector: 'node:active', style: {'overlay-opacity': 0}},
            {selector: 'core', style: {'active-bg-opacity': 0}},
            {selector: 'node.dimmed', style: {'opacity': 0.22}},
            {selector: 'edge.dimmed', style: {'opacity': 0.15}},
            // ABANDONED tombstone: kept for provenance but visibly NOT an active node.
            {selector: 'node.cancelled', style: {'opacity': 0.4, 'background-color': '#8a8a8a', 'border-color': '#6a6a6a',
                                                  'border-style': 'dashed', 'text-opacity': 0.6}},
            {selector: 'edge[type="dependency"].fromCancelled', style: {'opacity': 0.2, 'line-style': 'dotted'}},
        ],
        // nodes stay where the layout put them (a tap is a selection, never a drag); a wheel notch zooms gently
        layout: LAYOUT, minZoom: 0.3, maxZoom: 3, autoungrabify: true, boxSelectionEnabled: false, wheelSensitivity: 0.2,
    });
    // The page follows the canvas's OWN selection, not its `tap`: a press that moves a few pixels is no tap, yet
    // cytoscape selects the node — the border showed, the panel stayed, and the next redraw took the border back
    // (author, 2026-10-25: «то срабатывают сразу то только через повторное нажатие»; reproduced with a 4 px move).
    cy.on('select', 'node', evt => point('select', evt.target.id()));
    cy.on('unselect', 'node', () => setTimeout(() => { if (cy.nodes(':selected').empty()) point('select', null); }));
    // a hover ON the canvas needs no halo there — the pointer is on the node; the halo answers a hover from elsewhere
    let own = false;
    cy.on('mouseover', 'node', evt => { own = true; point('hover', evt.target.id()); });
    cy.on('mouseout', 'node', () => { own = false; point('hover', null); untip(); });
    cy.on('mouseover mousemove', 'node', evt => {
        const t = taskOf(evt.target.id());
        if (t.id) tip(nodeTip(t), evt.originalEvent);
    });
    // what another view points at is pointed at here too — and a node chosen there is brought into sight here
    watch((st, key) => {
        cy.nodes().removeClass('focus');
        if (st.hover && !own) cy.getElementById(st.hover).addClass('focus');
        cy.nodes(':selected').filter(n => n.id() !== st.select).unselect();
        if (st.select) cy.getElementById(st.select).select();
        if (key === 'select' && st.select && !fresh) inSight(cy.getElementById(st.select));
    });
    cy.on('render', () => requestAnimationFrame(placeBadges));
    // The canvas changes size when the panel opens or the deck folds or is dragged. The VIEW IS THE READER'S: the
    // canvas is told its new size and the graph stays where it was — a fit here made the graph jump each time a
    // click opened or closed the panel (author, 2026-10-25: «нажатие на некоторые ноды тригерит новую центровку»).
    // Only the selected node is kept in sight, by the least pan that does it (it sat under the opened panel,
    // 2026-09-06). Framing is the reader's own gesture: double-click a node for its subtree, the background for all.
    let frame;
    // …and never in the middle of a gesture: a tap that opens the panel resizes the canvas while the button is still
    // down, and a resize then left the press stuck — the next move dragged the whole graph (author, 2026-10-24)
    let held = false, want = null;
    cy.on('tapstart', () => { held = true; });
    // the reader's first press or wheel ANYWHERE ends the untouched view; a `?task=` link presses nothing
    addEventListener('pointerdown', () => { fresh = false; }, true);
    addEventListener('wheel', () => { fresh = false; }, true);
    addEventListener('pointerup', () => { held = false; }, true);
    // a double-click's own first click opens or closes the panel, and the frame is redone for the canvas it leaves
    const reseat = () => held ? (frame = setTimeout(reseat, 120))
        : (cy.resize(), want ? frameTo(want) : fresh ? cy.fit(undefined, 30) : inSight(cy.nodes(':selected')));
    new ResizeObserver(() => { clearTimeout(frame); frame = setTimeout(reseat, 120); }).observe($('cy'));
    const frameTo = eles => cy.animate({fit: {eles, padding: 40}, duration: 200});
    const framing = eles => { want = eles; frameTo(eles); setTimeout(() => { if (want === eles) want = null; }, 1500); };
    cy.on('dbltap', 'node', evt => framing(subtree(evt.target)));
    cy.on('dbltap', evt => { if (evt.target === cy) framing(cy.elements()); });
}

// A node and everything under it along D — the split's edges, never Dep (a leaf framed half the graph by its chains).
function subtree(n) {
    let all = n, front = n;
    while (front.length) all = all.union(front = front.outgoers('edge[type = "parent-child"]').targets());
    return all;
}

let drawn = '';                        // the node set last drawn: a redraw of the same keeps the view
// framed whole and not yet touched: a change of size re-frames it (the deck takes its height after the first
// drawing, and the graph's foot sat under it); once the reader taps, zooms or a node is chosen, the view is theirs
let fresh = true;

// The least pan that brings `eles` inside the canvas, a margin kept; nothing moves when they are already in sight.
function inSight(eles) {
    if (!eles.length) return;
    const b = eles.renderedBoundingBox(), m = 24, W = cy.width(), H = cy.height();
    const dx = b.x1 < m ? m - b.x1 : b.x2 > W - m ? Math.max(W - m - b.x2, m - b.x1) : 0;
    const dy = b.y1 < m ? m - b.y1 : b.y2 > H - m ? Math.max(H - m - b.y2, m - b.y1) : 0;
    if (dx || dy) cy.panBy({x: dx, y: dy});
}

function nodeTip(t) {
    const rs = S.run?.rounds[t.id] || [], w = S.run?.waits[t.id];
    return `<div class="tt-name">${esc(t.name || t.description || t.id)}</div>`
        + `<span class="tt-status state-badge b-${bucketOf(t.state)}">${statusLabel(t.state, t.done_reason)}</span>`
        + (t.assignee ? `<div class="tt-row">executor (Del): ${esc(t.assignee)}</div>` : '')
        + (w && waitWords(w, d => taskOf(d).name || d) !== '—' ? `<div class="tt-row">waits on: ${esc(waitWords(w, d => taskOf(d).name || d))}</div>` : '')
        + (rs.length ? `<div class="tt-row">${roundsLine(rs)}</div>` : '')
        + (t.criteria?.length ? `<div class="tt-row">${t.criteria.length} criteria</div>` : '')
        + '<div class="tt-row tt-hint">double-click: frame its subtree · on the background: the whole graph</div>';
}

// Badges over the canvas: a pulse on a node being worked right now, and its rounds when it took more
// than one — a node's history at a glance, without opening it.
let layer;
function placeBadges() {
    if (!cy) return;
    layer ??= $('cy').appendChild(Object.assign(document.createElement('div'), {className: 'cy-badges'}));
    // at work by the run's one rule; the pulse in the accent when this server has a process on it
    const work = atWork(S.run, S.tasks), proc = new Set(S.inflight.filter(w => w.project === S.project).map(w => w.task_id));
    proc.forEach(id => id && work.add(id));      // a process on a node is work on it, whatever its state (deck.js)
    layer.innerHTML = cy.nodes().map(n => {
        // the count wears the accent only while the node is failing now: a history of FAILs behind a PASS asks for nothing
        const id = n.id(), rs = S.run?.rounds[id] || [], failing = rs.at(-1)?.verdict === 'FAIL';
        if (!work.has(id) && rs.length < 2) return '';
        const b = n.renderedBoundingBox();
        return `<div class="cy-badge" style="left:${b.x2 - 6}px;top:${b.y1 - 9}px">`
            + (work.has(id) ? `<i class="cy-live${proc.has(id) ? ' on' : ''}"></i>` : '')
            + (rs.length > 1 ? `<span${failing ? ' class="cy-fails"' : ''} title="${roundsLine(rs)}">${rs.length}</span>` : '') + '</div>';
    }).join('');
}
export const annotate = placeBadges;
// The canvas height the drawn graph needs for its labels to read (zoom ≈ 0.8), framing included.
export const graphNeeds = () => cy && cy.nodes().length ? cy.elements().boundingBox().h * 0.8 + 70 : 0;

export const refreshGraph = singleFlight(async () => {
    try {
        const [gr, tr] = await Promise.all([api('/api/graph'), api('/api/tasks')]);
        // A REFUSAL HAS TO REACH THE PERSON: a mistyped `?project=` is a 404, not an empty canvas under
        // their project's name (the stats bar says it — header.js).
        if (gr.status === 404) {
            S.missing = (await gr.json().catch(() => ({}))).detail || 'no such project';
            cy.elements().remove();
            S.tasks = [];
            return;
        }
        const g = await gr.json();
        S.tasks = await tr.json();
        S.graph = g;
        S.missing = '';
        // the same nodes drawn again keep the reader's view; a new set (another project, parts added) is framed whole
        const key = g.nodes.map(n => n.id).sort().join('|'), kept = key === drawn && {zoom: cy.zoom(), pan: {...cy.pan()}};
        drawn = key;
        cy.elements().remove();
        // the state (+ the legacy DoneReason of pre-v3.7 rows)
        const cancelled = new Set(g.nodes.filter(n => n.state === 'ABANDONED' || n.done_reason === 'CANCELLED').map(n => n.id));
        S.closures = g.nodes.filter(n => n.closure && (n.closure.by_hand || contested(n.closure))).map(n => ({id: n.id, ...n.closure}));
        for (const n of g.nodes)
            cy.add({data: {id: n.id, label: readableLabel(n.name || n.id),   // a node the plan left unnamed is drawn by its id, never as nothing
 state: n.state, ...closureStyle(styleOf(n.state), n.closure)},
                    classes: cancelled.has(n.id) ? 'cancelled' : undefined});
        // ONE BAD EDGE MUST NOT COST THE WHOLE PICTURE: a dangling edge threw before the layout ran and
        // left fifteen nodes stacked at the origin (2026-09-06). Draw what can be drawn, SAY what cannot.
        const ids = new Set(g.nodes.map(n => n.id)), undrawable = [];
        for (const e of g.edges) {
            if (!ids.has(e.source) || !ids.has(e.target)) { undrawable.push(e); continue; }
            cy.add({data: {source: e.source, target: e.target, type: e.type},
                    classes: cancelled.has(e.source) ? 'fromCancelled' : undefined});
        }
        if (cy.nodes().length) {
            const lay = cy.layout({...LAYOUT, animate: !kept, animationDuration: 200});
            // framed once the layout knows where things are — and the read resolves only then, so a caller
            // measuring the drawing measures the finished one
            await new Promise(done => { lay.one('layoutstop', () => { kept ? cy.viewport(kept) : (cy.fit(undefined, 30), fresh = true); done(); }); lay.run(); });
        }
        // a redraw removes and re-adds every node, and the chosen one lost its border while its panel stayed open
        if (focus().select) cy.getElementById(focus().select).select();
        applyMineDim();
        const one = undrawable[0];
        banner('undrawable', one && `${undrawable.length} edge(s) not drawn — they name a node this graph does not `
            + `contain (e.g. ${one.source} → ${one.target}). The rest of the graph is shown.`, $('cy'));
    } catch (e) { console.error('refreshGraph:', e); }
});

// A transition patches its node in place; false when the node is not drawn (the caller re-reads).
export function restyle(id, state) {
    const node = cy.getElementById(id);
    if (node.length) node.data({state, ...styleOf(state)});
    return node.length > 0;
}

export function applyMineDim() {
    if (!cy) return;
    const me = myRole();
    cy.elements().removeClass('dimmed');
    if (!S.mineOnly || !me) return;
    const mine = new Set(S.tasks.filter(t => t.assignee === me).map(t => t.id));
    cy.nodes().forEach(n => { if (!mine.has(n.id())) n.addClass('dimmed'); });
    cy.edges().forEach(e => { if (!mine.has(e.source().id()) || !mine.has(e.target().id())) e.addClass('dimmed'); });
}
export function toggleMine() {
    S.mineOnly = !S.mineOnly;
    $('queue-toggle').classList.toggle('active', S.mineOnly);
    applyMineDim();
}
