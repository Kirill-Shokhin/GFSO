// The canvas: cytoscape, drawn from the graph read, every colour from the brand tokens (tokens.css).
import {$, esc, tally} from './dom.js';
import {S, taskOf, myRole, procs} from './state.js';
import {bucketOf, statusLabel, contested, cancelled, nameOf, criteriaOf, delivered} from './vocab.js';
import {banner} from './overlays.js';
import {tip, untip, TOUCH} from './tip.js';
import {point, watch, focus, rebring} from './store.js';
import {runNow, failingNow, failedOf} from './run.js';
import {TIP, waitWords, failedWords} from './hints.js';
import {css, beat} from './draw.js';
import {childrenOf, depths, ancestorsIn} from './tree.js';

// Leaf tokens are hex literals (draw.js css).
const [INK, SOFT, FAINT, PAPER, BG, ACC, TOMB, TOMB_LINE] = ['--ink', '--ink-soft', '--ink-faint', '--paper', '--bg', '--acc', '--ui-tomb', '--ui-tomb-line'].map(css);
// cytoscape refuses the stack with the quotes CSS requires and takes it unquoted (probed, 2026-09-06).
const FONT = css('--font-body').replace(/['"]/g, '').replace(/\s+/g, ' ').trim();
const inkAlpha = a => `rgba(${[0, 2, 4].map(i => parseInt(INK.slice(1 + i, 3 + i), 16))},${a})`;   // cy needs rgba, not color-mix

const S_ = (bg, fg, bw, bc, bs = 'solid', bo = 1) => ({bg, fg, bw, bc, bs, bo});
const NODE_STYLE = {
    done:      S_(INK, BG, 0, INK),
    quiet:     S_(BG, FAINT, 1, FAINT, 'solid', 0),
    attend:    S_(SOFT, BG, 0, SOFT),
    pathology: S_(SOFT, BG, 1.5, INK, 'dashed'),
    busy:      S_(BG, INK, 2, INK),     // consented work: an ink border — the accent is the pulse of a session running now
};
const styleOf = s => NODE_STYLE[bucketOf(s)];
// The drawing carries what the record carries (§15.7): contradicted → the accent, ringed (owed an
// answer); asserted by hand → dotted in paper (closed, on somebody's word).
const closureStyle = (st, cl) => !cl ? st
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

// tight enough that a whole plan fits at a zoom its names can be read at: at 1.4/35/55 an 11-part plan fitted at 0.58,
// its 11 px names at 6 px, which a newcomer could not read (2026-10-26); at 1.0/20/40 it fits at 0.93
const LAYOUT = {name: 'dagre', rankDir: 'TB', spacingFactor: 1.0, nodeSep: 20, rankSep: 40};
let cy;

// THE PLAN AT A GLANCE: a part's own parts are folded into it — a 49-part plan drawn whole was dust at zoom 0.24 (audit
// DQ1/E2). The goal's parts always stand; the reader unfolds a part by double-clicking it, and the background's
// double-click returns here. Unlike Progress, the path to a part failing now is not opened: opened, the plan was dust
// again at 0.42 — the fold says it instead, its count of parts failing now in the accent (the red is never folded away).
const unfolded = new Set();
let hidden = {};                                // id → the drawn node it is folded into
// the drawn node standing for each node: itself, or the outermost ancestor whose parts are folded
// …and only a plan that does not fit whole at the floor's zoom is folded: a plan that fits is drawn whole (decided once a
// project, on its first drawing: `folding`)
let folding = null, foldedFor = null;
function foldMap(tasks) {
    const d = depths(tasks), up = ancestorsIn(tasks), open = id => !folding || d[id] === 0 || unfolded.has(id);
    return Object.fromEntries(tasks.map(t => [t.id, up(t.id).reverse().find(a => !open(a)) ?? t.id]));
}
// A FOLD HIDES NOTHING THAT ASKS: its parts are counted by the same looks the drawing gives a node — at work, waiting on a
// decision (the key's look for blocked, challenged, escalated), closed by FAIL, failing now — so whatever the graph would
// mark on a drawn node it marks on the fold (critic 4: work at depth 2 vanished; critic 5: an escalated part the header
// called the reader to did). The parts are counted as the header counts them, the cancelled left out.
const foldOf = id => { const xs = Object.keys(hidden).filter(k => hidden[k] === id && !cancelled(taskOf(k)));
    const work = (S.run?.now ?? runNow(S.tasks, procs())).work;
    return {n: xs.length, failing: xs.filter(x => failingNow(S.run?.rounds[x], taskOf(x).state)), work: xs.filter(x => work.has(x)),
            decide: xs.filter(x => bucketOf(taskOf(x).state) === 'pathology'),
            shut: xs.filter(x => taskOf(x).state === 'DONE' && taskOf(x).done_reason === 'FAIL')}; };
// at most the type's own size: fitted at 2.2 an 11-part plan drew 20 px blocks (audit E2)
const fitCapped = (eles, pad = 30) => { cy.fit(eles, pad); if (cy.zoom() > 1) { cy.zoom(1); cy.center(eles); } };
// …and at least the size a name is read at: where the whole plan fits only smaller (a phone), the first view is centred on
// what asks for the reader — failing now, its own or folded inside, then at work — else on the goal; the rest a pan away
const FLOOR = 0.6;
function home() {
    fitCapped();
    if (cy.zoom() >= FLOOR) return;
    const work = (S.run?.now ?? runNow(S.tasks, procs())).work;
    const asks = [n => failingNow(S.run?.rounds[n.id()], taskOf(n.id()).state) || foldOf(n.id()).failing.length,
                  n => work.has(n.id()) || Object.keys(hidden).some(k => hidden[k] === n.id() && work.has(k)), n => !taskOf(n.id()).parent_id]
        .map(f => cy.nodes().filter(f)).find(c => c.length);
    cy.zoom(FLOOR); cy.center(asks);
}

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
            // the choice is an OUTLINE: a border moved the arrows' ends, and in ink it vanished on a dark node (author, 2026-10-25)
            {selector: 'node:selected', style: {'outline-width': 2, 'outline-color': ACC, 'outline-offset': 3}},
            {selector: 'edge', style: {
                'width': 1, 'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
                'line-color': inkAlpha(0.30), 'target-arrow-color': inkAlpha(0.30), 'arrow-scale': 0.7}},
            {selector: 'edge[type="dependency"]', style: {'line-style': 'dashed', 'line-color': ACC, 'target-arrow-color': ACC}},
            // a node pointed at from another view is marked in ONE colour, the palette's paper: a filled node's name dims to
            // it (what the accent tint did there — it barely touched an ink face), a light face takes it whole. The accent
            // over a light face was a pink no palette has, an outline read fainter, a paper face on a filled node read as
            // another node (the author, 2026-10-27). The box is unchanged: an underlay grew it and the edges re-anchored.
            {selector: 'node.focus', style: {'color': PAPER}},
            {selector: `node.focus[bg = "${BG}"]`, style: {'background-color': PAPER, 'background-opacity': 1, 'color': 'data(fg)'}},
            // no grey press overlay: the selection border is the one mark a tap leaves
            {selector: 'node:active', style: {'overlay-opacity': 0}},
            {selector: 'core', style: {'active-bg-opacity': 0}},
            // ABANDONED tombstone: kept for provenance but visibly NOT an active node.
            {selector: 'node.cancelled', style: {'opacity': 0.4, 'background-color': TOMB, 'border-color': TOMB_LINE,
                                                  'border-style': 'dashed', 'text-opacity': 0.6}},
            {selector: 'node.dimmed', style: {'opacity': 0.22}},
            {selector: 'edge.dimmed', style: {'opacity': 0.15}},
            {selector: 'edge[type="dependency"].fromCancelled', style: {'opacity': 0.2, 'line-style': 'dotted'}},
        ],
        // nodes stay where the layout put them (a tap is a selection, never a drag); a wheel notch zooms gently
        layout: LAYOUT, minZoom: 0.08, maxZoom: 3, autoungrabify: true, boxSelectionEnabled: false, wheelSensitivity: 0.2,
        // a double-click as people make it (Windows' default is 500 ms; cytoscape's own 250 ms dropped slow ones)
        multiClickDebounceTime: DBL,
    });
    // The page follows the canvas's OWN selection, not its `tap`: a press that moves a few pixels is no tap, yet
    // cytoscape selects the node — the border showed, the panel stayed, and the next redraw took the border back
    // (author, 2026-10-25: «то срабатывают сразу то только через повторное нажатие»; reproduced with a 4 px move).
    // …and its hover tip goes: it repeats what the panel the click opens says, over it (audit E3)
    cy.on('select', 'node', evt => { untip(); point('select', evt.target.id()); });
    // …and a tap on the node already selected picks it again: its row in the deck, scrolled away, is brought back
    cy.on('tap', 'node', evt => evt.target.id() === focus().select && rebring());
    // …and a finger's tap anywhere on the canvas is a tap elsewhere: a tip a deck view showed does not stay over the panel
    // (cytoscape makes no `click` of a touch, so the document never hears it — critic 11)
    cy.on('tap', () => { if (TOUCH.matches) untip(); });
    cy.on('unselect', 'node', () => setTimeout(() => { if (cy.nodes(':selected').empty()) point('select', null); }));
    // a hover ON the canvas needs no halo there — the pointer is on the node; the halo answers a hover from elsewhere
    let own = false;
    // a node is clicked to select it: the pointer says so, as on every row the deck lets one pick a node by
    cy.on('mouseover', 'node', evt => { own = true; point('hover', evt.target.id()); $('cy').style.cursor = 'pointer'; });
    cy.on('mouseout', 'node', () => { own = false; point('hover', null); untip(); $('cy').style.cursor = ''; });
    cy.on('mouseover mousemove', 'node', evt => {
        const t = taskOf(evt.target.id());
        if (t.id) tip(nodeTip(t), evt.originalEvent);
    });
    // what another view points at is pointed at here too — and a node chosen there is brought into sight here
    watch((st, key) => {
        cy.nodes().removeClass('focus');
        if (st.hover && !own) cy.getElementById(st.hover).addClass('focus');
        cy.nodes(':selected').filter(n => n.id() !== st.select).unselect();
        // a node chosen in another view, folded here, unfolds the path to it
        if (st.select && hidden[st.select]) { ancestorsIn(S.tasks)(st.select).forEach(a => unfolded.add(a));
            redraw().then(() => { fresh = false; inSight(cy.getElementById(st.select)); }); return; }
        if (st.select) cy.getElementById(st.select).select();
        if ((key === 'select' || key === 'bring') && st.select) { fresh = false; inSight(cy.getElementById(st.select)); }
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
        : (cy.resize(), want ? framed() : fresh ? home() : inSight(cy.nodes(':selected')));
    new ResizeObserver(() => { clearTimeout(frame); frame = setTimeout(reseat, 120); }).observe($('cy'));
    // a double-click's own first click opens or closes the panel: the frame waits for that resize and is drawn ONCE —
    // drawn at once and again after it, a node was zoomed twice (author, 2026-10-25)
    let wantT;
    const framed = () => { clearTimeout(wantT); if (want) { const z = cy.zoom(), p = {...cy.pan()}; fitCapped(want, 40);
        if (cy.zoom() < FLOOR) { cy.zoom(FLOOR); cy.center(want.length > 1 ? want.slice(1) : want); }
        const to = {zoom: cy.zoom(), pan: {...cy.pan()}}; cy.viewport({zoom: z, pan: p}); cy.animate({...to, duration: 200}); } want = null; };
    const framing = eles => { want = eles; clearTimeout(wantT); wantT = setTimeout(framed, 450); };
    // a double-click on a node shows it with its parts: a folded node unfolds first, then the subtree is framed
    const opening = async id => { if (foldOf(id).n) { unfolded.add(id); await redraw(); fresh = false; }
        framing(subtree(cy.getElementById(id))); };
    cy.on('dbltap', 'node', evt => opening(evt.target.id()));
    $('cy').addEventListener('pointerup', e => { const id = e.target.closest?.('.cy-fold')?.dataset.node; if (id) { e.stopPropagation(); opening(id); } });
    // …the background's: the plan as first drawn, its parts folded again
    cy.on('dbltap', async evt => { if (evt.target !== cy) return;
        if (unfolded.size) { unfolded.clear(); await redraw(); } framing(cy.elements()); });
    // A node under the strip the panel opens over: the first click opens the panel there and the second lands on it,
    // so the canvas never saw a double-click — and the click could press a button of the panel (critics 7, 9). A press
    // on the panel within the double-click's time, where that node was pressed, is the node's second click. Delaying
    // the selection instead lost clicks and blinked the outline (refuted, 97cfd80).
    // The same when the first click's panel made the canvas pan the node into sight: the second click then met the
    // background, which unselected the node and framed the whole graph.
    let last = null, swallow = false;
    const moved = () => { const p = last.n.renderedPosition(); return Math.hypot(p.x - last.p.x, p.y - last.p.y) > 4; };
    cy.on('tap', 'node', evt => { const o = evt.originalEvent, p = evt.target.renderedPosition();
        last = o && {n: evt.target, x: o.clientX, y: o.clientY, t: Date.now(), p: {x: p.x, y: p.y}}; });
    addEventListener('pointerdown', e => {
        const hit = last && Date.now() - last.t < DBL && Math.hypot(e.clientX - last.x, e.clientY - last.y) < 8
            && (e.target.closest?.('#sidebar') || (e.target.closest?.('#cy') && moved()));
        if (!hit) return;
        e.preventDefault(); e.stopPropagation(); opening(last.n.id()); last = null;
        swallow = true; setTimeout(() => { swallow = false; }, DBL);   // its own click only, never a later one
    }, true);
    addEventListener('click', e => { if (swallow) { swallow = false; e.preventDefault(); e.stopPropagation(); } }, true);
}

// A node and everything under it along D, read off the tasks' parents — never Dep (a leaf framed half the graph by its
// chains), and not off the drawn edges either: a part whose split edge was not drawn framed only itself (author).
function subtree(n) {
    const kids = id => childrenOf(S.tasks, id).map(t => t.id), ids = [n.id()];
    for (let i = 0; i < ids.length; i++) ids.push(...kids(ids[i]));
    return cy.collection(ids.map(id => cy.getElementById(id)).filter(e => e.length));
}

const BODY = {includeLabels: false, includeOverlays: false, includeUnderlays: false};   // the node itself
const DBL = 400;   // ms: a second press within it makes a double-click
let drawn = '';                        // the node set last drawn: a redraw of the same keeps the view
// framed whole and not yet touched: a change of size re-frames it (the deck takes its height after the first
// drawing, and the graph's foot sat under it); once the reader taps, zooms or a node is chosen, the view is theirs
let fresh = true;

// The least pan that brings `eles` inside the canvas, a margin kept; nothing moves when they are already in sight.
function inSight(eles) {
    if (!eles.length) return;
    const b = eles.renderedBoundingBox(BODY), m = 24, W = cy.width(), H = cy.height();
    const dx = b.x1 < m ? m - b.x1 : b.x2 > W - m ? Math.max(W - m - b.x2, m - b.x1) : 0;
    const dy = b.y1 < m ? m - b.y1 : b.y2 > H - m ? Math.max(H - m - b.y2, m - b.y1) : 0;
    if (dx || dy) cy.panBy({x: dx, y: dy});
}

// what the drawing does not say; how to frame a node is the key's, not every node's tip
// …its name only where the drawing does not say it: cut, or drawn too small to read (audit D2: «never the row's name its
// row shows», 10-31); its state in the panel's word — a passed node is DONE there, never PASS here (D5)
const READABLE = 8;
function nodeTip(t) {
    // what it waits on: its producers one a row — names carry commas, so joined by commas they could not be counted (D4)
    const rs = S.run?.rounds[t.id] || [], w = S.run?.waits[t.id], last = rs.at(-1);
    const words = w?.deps.length ? w.deps.map(d => nameOf(taskOf(d)) || d) : w && waitWords(w, d => d);
    const shown = readableLabel(nameOf(t)) === nameOf(t) && cy.zoom() * 11 >= READABLE;
    return TIP.node(t, !shown && nameOf(t), `<span class="tt-status state-badge b-${bucketOf(t.state)}">${statusLabel(t.state, delivered(t) ? null : t.done_reason)}</span>`,
        words !== '—' && words, rs, criteriaOf(t).length,
        last?.verdict === 'FAIL' && failingNow(rs, t.state) && failedWords(failedOf(S.run, t.id, last.failed)),
        (f => f.n && {...f, failing: f.failing.map(x => nameOf(taskOf(x)) || x)})(foldOf(t.id)));
}

// Badges over the canvas: a pulse on a node being worked right now, and its rounds when it took more
// than one — a node's history at a glance, without opening it.
let layer;
function placeBadges() {
    if (!cy) return;
    layer ??= $('cy').appendChild(Object.assign(document.createElement('div'), {className: 'cy-badges'}));
    // at work by the run's one rule; the pulse in the accent when this server has a process on it
    // (the graph may draw before the run is read: the same rule over the registry then)
    const now = S.run?.now ?? runNow(S.tasks, procs()), work = now.work;
    layer.innerHTML = cy.nodes().map(n => {
        // the count wears the accent only while the node is failing now: a history of FAILs behind a PASS asks for nothing
        const id = n.id(), rs = S.run?.rounds[id] || [], failing = failingNow(rs, n.data('state') ?? taskOf(id).state);
        const b = n.renderedBoundingBox(BODY), f = foldOf(id);
        // the folded parts hang under the node: their count, and those failing now in the accent
        // …each a count as every count on the page (`tally`: the figure at its line's size — critic 5); a click on it unfolds
        const tag = f.n ? `<div class="cy-fold" data-node="${esc(id)}" style="left:${(b.x1 + b.x2) / 2}px;top:${b.y2 - 1}px"${TIP.fold}>${tally(f.n, f.n > 1 ? 'parts' : 'part')}`
            + (f.work.length ? `<i class="cy-live${f.work.some(x => now.on(x)) ? ' on' : ''}"${beat()}></i>${tally(f.work.length, 'at work')}` : '')
            + (f.decide.length ? tally(f.decide.length, f.decide.length > 1 ? 'wait on a decision' : 'waits on a decision') : '')
            + (f.shut.length ? tally(f.shut.length, 'closed by FAIL') : '')
            + (f.failing.length ? `<span class="acc">${tally(f.failing.length, 'sent back')}</span>` : '') + '</div>' : '';
        // A PART CLOSED BY FAIL keeps the closed fill and wears the FAIL cross every view gives a FAIL, on its corner
        // (audit E8): the accent ring already says «PASS contested», an accent fill would read as a call on a person
        const t = taskOf(id), shut = t.state === 'DONE' && t.done_reason === 'FAIL';
        const cross = shut ? `<div class="cy-badge cy-shut" style="left:${b.x1 - 9}px;top:${b.y1 - 9}px"><svg viewBox="-6 -6 12 12"><path class="mk-fail" d="M-2.5,-2.5l5,5m0,-5l-5,5"/></svg></div>` : '';
        if (!work.has(id) && rs.length < 2) return cross + tag;
        return cross + `<div class="cy-badge" style="left:${b.x2 - 6}px;top:${b.y1 - 9}px">`
            // the pulse keeps the page's one clock: a badge redrawn on every render restarted it mid-beat
            + (work.has(id) ? `<i class="cy-live${now.on(id) ? ' on' : ''}"${beat()}></i>` : '')
            + (rs.length > 1 ? `<span${failing ? ' class="cy-fails"' : ''}${TIP.rounds(rs)}>${rs.length}</span>` : '') + '</div>' + tag;
    }).join('');
}
// the run is read after the first drawing: an untouched view is framed again on what asks now
export const annotate = () => { if (cy?.nodes().length && fresh) home(); placeBadges(); };
// The canvas height the drawn graph needs for its labels to read (zoom ≈ 0.8), framing included.
export const graphNeeds = () => cy && cy.nodes().length ? cy.elements().boundingBox().h * 0.8 + 70 : 0;

// The graph as last read (model.js loadGraph); `found` false: the project does not exist (yet), and nothing is drawn.
const redraw = () => drawGraph(true);
export async function drawGraph(found) {
        if (!found) {
            // a project not on disk yet has no mode: a mode set first would have created it (a goal stated here)
            document.body.classList.add('manual');
            cy.elements().remove();
            return;
        }
        const g = S.graph;
        // a project with a mode is moved by agents and the system; the person's own moves, and the name they sign
        // them with, belong to a project without one, where a node is held by whoever it names (author, 2026-10-26)
        document.body.classList.toggle('manual', !g.mode?.mode);
        // the same nodes drawn again keep the reader's view; a new set (another project, parts added) is framed whole
        hidden = {};
        const rep = foldMap(g.nodes);
        for (const n of g.nodes) if (rep[n.id] !== n.id) hidden[n.id] = rep[n.id];
        const key = g.nodes.filter(n => !hidden[n.id]).map(n => n.id).sort().join('|'), kept = key === drawn && {zoom: cy.zoom(), pan: {...cy.pan()}};
        drawn = key;
        cy.elements().remove();
        const tomb = new Set(g.nodes.filter(cancelled).map(n => n.id));
        for (const n of g.nodes.filter(n => !hidden[n.id]))
            cy.add({data: {id: n.id, label: readableLabel(nameOf(n)),
 state: n.state, ...closureStyle(styleOf(n.state), n.closure)},
                    classes: tomb.has(n.id) ? 'cancelled' : undefined});
        // ONE BAD EDGE MUST NOT COST THE WHOLE PICTURE: a dangling edge threw before the layout ran and
        // left fifteen nodes stacked at the origin (2026-09-06). Draw what can be drawn, SAY what cannot.
        // an edge into a folded part is drawn to the node it is folded into — once, and never inside one fold
        const ids = new Set(g.nodes.map(n => n.id)), undrawable = [], seen = new Set();
        for (const e of g.edges) {
            if (!ids.has(e.source) || !ids.has(e.target)) { undrawable.push(e); continue; }
            const source = rep[e.source], target = rep[e.target], k = `${source}>${target}>${e.type}`;
            if (source === target || seen.has(k)) continue;
            seen.add(k);
            cy.add({data: {source, target, type: e.type},
                    classes: tomb.has(e.source) ? 'fromCancelled' : undefined});
        }
        if (cy.nodes().length) {
            const lay = cy.layout({...LAYOUT, animate: !kept, animationDuration: 200});
            // framed once the layout knows where things are — and the read resolves only then, so a caller
            // measuring the drawing measures the finished one
            await new Promise(done => { lay.one('layoutstop', () => { kept ? cy.viewport(kept) : (home(), fresh = true); done(); }); lay.run(); });
            const plan = `${S.project}|${g.nodes.map(n => n.id).sort().join('|')}`;
            if (foldedFor !== plan) { foldedFor = plan; cy.fit(undefined, 30);
                folding = cy.zoom() < FLOOR && g.nodes.some(n => n.parent_id && g.nodes.find(p => p.id === n.parent_id)?.parent_id);
                if (folding) return redraw(); home(); }
        }
        // a redraw removes and re-adds every node, and the chosen one lost its border while its panel stayed open
        if (focus().select) cy.getElementById(focus().select).select();
        applyMineDim();
        const one = undrawable[0];
        banner('undrawable', one && `${undrawable.length} edge(s) not drawn — they name a node this graph does not `
            + `contain (e.g. ${one.source} → ${one.target}). The rest of the graph is shown.`, $('cy'));
}

// "Mine only": the nodes the name in "acting as" holds — a person's view in a project without a mode
export function applyMineDim() {
    if (!cy) return;
    const me = myRole();
    cy.elements().removeClass('dimmed');
    if (!S.mineOnly || !me || S.graph.mode?.mode) return;
    const mine = new Set(S.tasks.filter(t => t.assignee === me).map(t => t.id));
    cy.nodes().forEach(n => { if (!mine.has(n.id())) n.addClass('dimmed'); });
    cy.edges().forEach(e => { if (!mine.has(e.source().id()) || !mine.has(e.target().id())) e.addClass('dimmed'); });
}
export function toggleMine() {
    S.mineOnly = !S.mineOnly;
    $('queue-toggle').classList.toggle('active', S.mineOnly);
    applyMineDim();
}

// A transition patches its node in place; false when the node is not drawn (the caller re-reads).
export function restyle(id, state) {
    const node = cy.getElementById(id);
    if (node.length) node.data({state, ...styleOf(state)});
    return node.length > 0;
}

