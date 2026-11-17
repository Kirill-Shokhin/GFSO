// The canvas: cytoscape, drawn from the graph read, every colour from the brand tokens (tokens.css).
import {$, esc, tally} from './dom.js';
import {S, taskOf, whoOwes, mineNames, keep, nowOf, stateWord, handAsks, hasKids, goTo, goUp} from './state.js';
import {bucketOf, contested, cancelled, nameOf, criteriaOf, delivered, closedByFail} from './vocab.js';
import {banner} from './overlays.js';
import {tip, untip, TOUCH} from './tip.js';
import {point, watch, focus, rebring} from './store.js';
import {failingNow, failedOf} from './run.js';
import {card, TIP, waitWords, failedWords} from './hints.js';
import {css, beat} from './draw.js';
import {childrenOf, ancestorsIn} from './tree.js';
import {planChanged, decide, decidedBefore, foldInto, isHidden, foldOf, asking, viewed} from './fold.js';
import {FOCUS} from './api.js';

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
const closureStyle = (st, cl, n) => !cl ? st
    : contested(cl) ? {...st, bw: 3, bc: ACC, bs: 'solid', bo: 1}
    : cl.by_hand && handAsks(n) ? {...st, bw: 2, bc: PAPER, bs: 'dotted', bo: 1}
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

// at most the type's own size: fitted at 2.2 an 11-part plan drew 20 px blocks (audit E2)
const fitCapped = (eles, pad = 30) => { cy.fit(eles, pad); if (cy.zoom() > 1) { cy.zoom(1); cy.center(eles); } };
const collect = ids => cy.collection(ids.map(id => cy.getElementById(id)));
const askingOf = eles => collect(asking(eles.map(n => n.id())));
// …and at least the size a name is read at: where the whole plan fits only smaller, the first view is centred on what asks
// for the reader, else on the goal; the rest a pan away
const FLOOR = 0.6;
// centred on them all where they fit together, else on the first: centred between two far apart, both stood off a phone (critic)
function atFloor(eles) {
    cy.zoom(FLOOR);
    const b = eles.renderedBoundingBox(BODY);
    cy.center(b.w <= cy.width() - 48 && b.h <= cy.height() - 48 ? eles : eles.first());
}
function home() {
    fitCapped();
    if (cy.zoom() >= FLOOR) return;
    const asks = askingOf(cy.nodes());
    // …the view's own top in a view of one part, whose nodes all have parents (critic 4)
    atFloor(asks.length ? asks : FOCUS && cy.getElementById(FOCUS).length ? cy.getElementById(FOCUS) : cy.nodes().filter(n => !taskOf(n.id()).parent_id));
    // …and no side stands blank while the plan runs off the other (the goal centred: half a canvas empty above a plan cut
    // below); never further than the plan's own edge, so what was centred stays in sight
    const b = cy.elements().renderedBoundingBox(BODY), m = 24;
    const slack = (lo, hi, size) => lo > m && hi > size - m ? -Math.min(lo - m, hi - size + m)
        : hi < size - m && lo < m ? Math.min(size - m - hi, m - lo) : 0;
    cy.panBy({x: slack(b.x1, b.x2, cy.width()), y: slack(b.y1, b.y2, cy.height())});
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
            // …nor on an arrow: a finger panning across the graph lit every arrow it crossed (the author's phone, 2026-11-17)
            {selector: 'edge:active', style: {'overlay-opacity': 0}},
            {selector: 'core', style: {'active-bg-opacity': 0}},
            // ABANDONED tombstone: kept for provenance but visibly NOT an active node.
            {selector: 'node.cancelled', style: {'opacity': 0.4, 'background-color': TOMB, 'border-color': TOMB_LINE,
                                                  'border-style': 'dashed', 'text-opacity': 0.6}},
            {selector: 'node.dimmed', style: {'opacity': 0.22}},
            // a node outside a view of one part, drawn only for the Dep edge that crosses into it
            {selector: 'node.outside', style: {'opacity': 0.5, 'border-style': 'dashed'}},
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
    // (a press on a fold's tag is no tap on the background: the panel stays, and the redraw gives the node its border back)
    cy.on('unselect', 'node', () => setTimeout(() => { if (cy.nodes(':selected').empty() && !pressed?.id) point('select', null); }));
    // a hover ON the canvas needs no halo there — the pointer is on the node; the halo answers a hover from elsewhere
    let own = false;
    // a node is clicked to select it: the pointer says so, as on every row the deck lets one pick a node by
    cy.on('mouseover', 'node', evt => { own = true; point('hover', evt.target.id()); $('cy').style.cursor = 'pointer'; });
    cy.on('mouseout', 'node', () => { own = false; point('hover', null); untip(); $('cy').style.cursor = ''; });
    const edgeTip = evt => { const d = evt.target.data(); tip(TIP.edge(d.type, nameOf(taskOf(d.source)), nameOf(taskOf(d.target)), d.inner), evt.originalEvent); };
    cy.on('mouseover mousemove', 'edge', edgeTip);
    cy.on('mouseout', 'edge', () => untip());
    // …a finger's tap on a fold's tag passes to the canvas (an arrow under it said its meaning over the move): not an arrow's
    cy.on('tap', 'edge', evt => TOUCH.matches && !pressed?.id && edgeTip(evt));
    cy.on('mouseover mousemove', 'node', evt => {
        const t = taskOf(evt.target.id());
        if (t.id) tip(nodeTip(t), evt.originalEvent);
    });
    // what another view points at is pointed at here too — and a node chosen there is brought into sight here
    watch((st, key) => {
        cy.nodes().removeClass('focus');
        if (st.hover && !own) cy.getElementById(st.hover).addClass('focus');
        cy.nodes(':selected').filter(n => n.id() !== st.select).unselect();
        // a node chosen in another view, folded here, is gone to: the part it stands in is opened, and it is chosen there
        // …a node chosen elsewhere opens its panel and moves no view: In work moved the page into the node's part while the
        // graph's own tap did not — two logics (the author, 2026-11-17). Its part is gone to on a second press (`bring`) or
        // the panel's «Show it on the graph»
        if (key === 'bring' && st.select && isHidden(st.select)) { goTo(taskOf(st.select).parent_id); return; }
        if (st.select) cy.getElementById(st.select).select();
        if ((key === 'select' || key === 'bring') && st.select) { fresh = false; inSight(cy.getElementById(st.select)); }
    });
    // the marks ride the canvas: moved in the very frame it draws, redrawn only when what they say changes (the author, 11-04: a tag redrawn a frame
    // behind on every render «пересовывается рывками»). A render with the view unchanged is news about the nodes.
    let seen = '';
    // …and none placed while a drawing is under way: its nodes stand at the origin until the layout has run
    cy.on('render', () => { const v = `${cy.zoom()}|${cy.pan().x}|${cy.pan().y}`, moved = v !== seen; seen = v; moved ? ride() : drawing || placeBadges(); });
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
    // A DRAG BEGUN ON A NODE PANS, as one begun on the background does: nodes are not moved here (autoungrabify), and the
    // library left such a drag doing nothing — on a phone a graph is mostly nodes (the author, 2026-11-17: «если от ноды
    // просто не двигается»). A press without a drag stays a tap.
    // …and a drag is no press: the graph follows the finger, so the node stays under it and the library took the release
    // for a tap and opened the node (the author, 2026-11-17: «по отпускании все равно она будет открыта»). Past a few
    // pixels from where it began, the gesture selects nothing.
    let from = null, start = null, dragging = false;
    cy.on('tapstart', 'node', e => { from = {...e.renderedPosition}; start = {...from}; dragging = false; });
    cy.on('tapdrag', e => { if (!from || fingers > 1) return; const p = e.renderedPosition;
        if (!dragging && Math.hypot(p.x - start.x, p.y - start.y) > 8) { dragging = true; cy.autounselectify(true); untip(); }
        cy.panBy({x: p.x - from.x, y: p.y - from.y}); from = {...p}; });
    cy.on('tapend', () => { from = null; if (dragging) { dragging = false; setTimeout(() => cy.autounselectify(false)); } });
    // the reader's first press or wheel ANYWHERE ends the untouched view; a `?task=` link presses nothing
    addEventListener('pointerdown', () => { fresh = false; }, true);
    addEventListener('wheel', () => { fresh = false; }, true);
    addEventListener('pointerup', () => { held = false; }, true);
    // a double-click's own first click opens or closes the panel, and the frame is redone for the canvas it leaves
    const reseat = () => held ? (frame = setTimeout(reseat, 120))
        : (cy.resize(), want ? framed() : fresh ? home() : inSight(cy.nodes(':selected')));
    // WHILE THE DECK IS DRAGGED the canvas already spans what the deck can uncover and the deck slides over it (deck.js): one
    // resize at the drag's start, none under it, the view kept — a canvas resized after the drag left the uncovered strip
    // blank for a while (the author, 2026-11-17: «с задержкой в секунду перерисовывается то что под ней было»), resized on
    // every step it rippled
    new ResizeObserver(() => { clearTimeout(frame);
        // …drawn in the same frame: a resize clears the canvas and the library redraws a frame later — the graph blinked (critic);
        // forceRender only asks for that later frame, the renderer's own render draws now (cytoscape pinned at 3.28.1)
        if (document.body.classList.contains('deck-drag')) { cy.resize(); cy.renderer().render(); } else frame = setTimeout(reseat, 120); }).observe($('cy'));
    // a double-click's own first click opens or closes the panel: the frame waits for that resize and is drawn ONCE —
    // drawn at once and again after it, a node was zoomed twice (author, 2026-10-25)
    let wantT;
    // …set at once, not animated: the library's animated frames are heavier than a hand's pan and stuttered beside it (the
    // author, 2026-11-17: «автоматический перенос как то по другому работает и кривее ручного»)
    const framed = () => { clearTimeout(wantT); if (want) { fitCapped(want, 40);
        // short of room, the opened subtree is centred at the floor (the author, 11-04: «не центруется открытое поддерево»)
        if (cy.zoom() < FLOOR) { cy.zoom(FLOOR); cy.center(want); } } want = null; };
    // …and waiting for the panel's resize only where a first click opens a panel — a mouse; a finger's double tap frames at once
    const framing = eles => { want = eles; clearTimeout(wantT); wantT = setTimeout(framed, TOUCH.matches ? 0 : 450); };
    // A DOUBLE-CLICK GOES DOWN into a node that has parts, and up from the part's own top; a leaf is framed. The graph is read
    // by going down and up, never unfolded in place: an unfolding re-laid every node and kept every edge as noise (the author,
    // 11-15: «при разворачивании помимо того что остается шум так еще и ноды все перестраиваются по расположению»)
    // …a move lets go of the node its first click chose: a panel stood open on the new top, or on the part left behind (critic)
    // …after the canvas has finished its own double-click: a drawing removed under it threw inside cytoscape, and its second
    // tap chose the node again
    const moving = go => setTimeout(() => { point('select', null); go(); });
    // …with a mouse: under a finger the first tap opens the node's panel over the screen, so a double-tap would have to beat
    // the panel to move (the author, 11-15: «надо обходить другую функцию скоростью»); a finger goes down by the fold's tag
    // or the panel's own «From this part down»
    const opening = id => TOUCH.matches ? framing(subtree(cy.getElementById(id))) : id === FOCUS ? moving(goUp) : hasKids(id) && taskOf(id).parent_id ? moving(() => goTo(id)) : framing(subtree(cy.getElementById(id)));
    // THE TAG GOES DOWN, and its press opens no panel: under a finger the same tap also reached the node beneath
    const goDown = goTo;
    // the press's hold on selection ends with it, however it ends; a second finger makes it a pinch, no press (critic: a stuck hold left no node selectable)
    let fingers = 0;
    const release = () => { cy.autounselectify(false); pressed?.el?.classList.remove('pressing'); pressed = null; const s = focus().select; if (s) cy.getElementById(s).select(); };
    addEventListener('pointerdown', () => { if (++fingers > 1 && pressed?.id) release(); }, true);
    // …a press that turns into a pan is no press on the tag: its dark goes as the finger leaves (the author, 2026-11-17:
    // «партс подсвечивается при любом касании хотя и не срабатывает»)
    addEventListener('pointermove', e => { if (pressed?.el && Math.hypot(e.clientX - pressed.x, e.clientY - pressed.y) >= 8) pressed.el.classList.remove('pressing'); }, true);
    const ended = e => { fingers = Math.max(0, fingers - 1); const p = pressed; if (!p?.id) return;
        if (e.type === 'pointerup' && !p.held && Math.hypot(e.clientX - p.x, e.clientY - p.y) < 8) goDown(p.id);
        setTimeout(release, 400); };
    addEventListener('pointerup', ended, true); addEventListener('pointercancel', ended, true);
    cy.on('dbltap', 'node', evt => opening(evt.target.id()));
    // a press and release in place on the tag: a pan begun on it moves the graph and unfolds nothing (critic 7). Found by where
    // it stands, not by the event's target: under a finger the tag lets every gesture through to the canvas (gfso.css), or a
    // tag across a phone's width could not be panned from (critic 8)
    // …and under a finger with room around it: a tag a few pixels tall had to be aimed at (the author, 2026-11-17: «в неё
    // ещё попасть надо»)
    // …never above it, where its node stands: a margin there took a tap on a node zoomed out for a press on its tag (critic)
    const at = sel => e => { const m = TOUCH.matches ? 12 : 0; return [...$('cy').querySelectorAll(sel)].find(t => { const r = t.getBoundingClientRect();
        return e.clientX >= r.left - m && e.clientX <= r.right + m && e.clientY >= r.top && e.clientY <= r.bottom + m; }); };
    const tagAt = at('.cy-fold');
    // …a finger's long press reads its tip the same way: the tag lets it through to the canvas too
    $('cy').addEventListener('contextmenu', e => { const t = TOUCH.matches && tagAt(e);
        if (t?.dataset.tip) { e.preventDefault(); if (pressed) pressed.held = true; const [head, ...rows] = t.dataset.tip.split('\n'); tip(card(head, rows), e); } });
    // …and the tag answers the press at once, before the view changes: it «не реагирует никак» (the author)
    $('cy').addEventListener('pointerdown', e => { if (fingers > 1) return; const t = tagAt(e); pressed = {x: e.clientX, y: e.clientY, id: t?.dataset.node, el: t};
        if (pressed.id) { cy.autounselectify(true); t.classList.add('pressing'); } }, true);
    // …the background's: the plan as first drawn, its parts folded again
    cy.on('dbltap', async evt => { if (evt.target !== cy) return;
        framing(cy.elements()); });
    // A node under the strip the panel opens over: the first click opens the panel there and the second lands on it,
    // so the canvas never saw a double-click — and the click could press a button of the panel (critics 7, 9). A press
    // on the panel within the double-click's time, where that node was pressed, is the node's second click. Delaying
    // the selection instead lost clicks and blinked the outline (refuted, 97cfd80).
    // The same when the first click's panel made the canvas pan the node into sight: the second click then met the
    // background, which unselected the node and framed the whole graph.
    let last = null, swallow = false;
    const moved = () => { const p = last.n.renderedPosition(); return Math.hypot(p.x - last.p.x, p.y - last.p.y) > 4; };
    // …a finger's tap is a TouchEvent: its point is its changed touch
    cy.on('tap', 'node', evt => { const o = evt.originalEvent?.changedTouches?.[0] ?? evt.originalEvent, p = evt.target.renderedPosition();
        last = o && {n: evt.target, x: o.clientX, y: o.clientY, t: Date.now(), p: {x: p.x, y: p.y}}; });
    addEventListener('pointerdown', e => {
        const hit = last && Date.now() - last.t < DBL && Math.hypot(e.clientX - last.x, e.clientY - last.y) < 8
            && (e.target.closest?.('#sidebar') || (e.target.closest?.('#cy') && moved()));
        if (!hit) return;
        // …a finger's: swallowed only — a double-tap is no gesture under a finger, and its second tap pressed what the panel
        // just opened had under it (critic)
        e.preventDefault(); e.stopPropagation(); if (!TOUCH.matches) opening(last.n.id()); last = null;
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
let pressed = null;                    // where the last press on the canvas began, and the fold's tag under it
let drawn = '', drawnIn = null;       // the node set last drawn, and whose: a redraw of the same keeps the view
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
    const words = w?.deps.length ? w.deps.map(d => nameOf(taskOf(d)) || d) : w && waitWords(w, d => d, whoOwes(t, w.owes));
    const shown = readableLabel(nameOf(t)) === nameOf(t) && cy.zoom() * 11 >= READABLE;
    return TIP.node(t, !shown && nameOf(t), `<span class="tt-status state-badge b-${bucketOf(t.state)}">${stateWord(t)}</span>`,
        words !== '—' && words, rs, criteriaOf(t).length,
        last?.verdict === 'FAIL' && failingNow(rs, t.state) && failedWords(failedOf(S.run, t.id, last.failed)),
        foldOf(t.id).failing.map(x => nameOf(taskOf(x)) || x));
}

// Badges over the canvas: a pulse on a node being worked right now, and its rounds when it took more
// than one — a node's history at a glance, without opening it.
let layer, plane;
const ride = () => { if (!plane) return; const z = cy.zoom(), p = cy.pan();
    plane.style.transform = `translate(${p.x}px,${p.y}px) scale(${z})`; plane.style.setProperty('--unz', 1 / z); };
const TAG_IN = 8;   // the tag hangs inside the node's rounded corners, so it reads as a part of it
function placeBadges() {
    if (!cy) return;
    layer ??= $('cy').appendChild(Object.assign(document.createElement('div'), {className: 'cy-badges'}));
    plane ??= layer.appendChild(Object.assign(document.createElement('div'), {className: 'cy-plane'}));
    // at work by the run's one rule; the pulse in the accent when this server has a process on it
    // (the graph may draw before the run is read: the same rule over the registry then)
    const now = nowOf(), work = now.work;
    // a narrow tag keeps its word in a smaller type: a bare «404» on the largest node read as an error's code (critic)
    const count = (w, n, word) => { const need = 22 + 6 * String(n).length + 6 * word.length;
        return tally(n, word, w < need ? ` style="font-size:${Math.max(7, 10 * w / need).toFixed(1)}px"` : ''); };
    const html = cy.nodes().map(n => {
        // the count wears the accent only while the node is failing now: a history of FAILs behind a PASS asks for nothing
        const id = n.id(), rs = S.run?.rounds[id] || [], failing = failingNow(rs, n.data('state') ?? taskOf(id).state);
        const b = n.boundingBox(BODY), f = foldOf(id), w = b.x2 - b.x1 - 2 * TAG_IN, hang = `left:${b.x1 + TAG_IN}px;top:${b.y2 - 1}px;width:${w}px`;
        // the folded parts hang under the node: their count, and those failing now in the accent
        // …each a count as every count on the page (`tally`: the figure at its line's size — critic 5); a click on it unfolds
        const tag = f.n ? `<div class="cy-fold${f.decide.length + f.shut.length + f.contested.length + f.failing.length ? ' asks' : ''}" data-node="${esc(id)}" style="${hang}"${TIP.fold([f.held.length && `${f.held.length} in work`, f.work.length && `${f.work.length} acted on now`, f.decide.length && `${f.decide.length} waiting on a decision`, f.shut.length && `${f.shut.length} closed by FAIL`,
                f.contested.length && `${f.contested.length} contested`, f.failing.length && `${f.failing.length} sent back`])}>${count(w, f.n, f.n > 1 ? 'parts' : 'part')}`
            + (f.work.length ? `<i class="cy-live${f.work.some(now.lit) ? ' on' : ''}"${beat()}></i>` : '') + '</div>' : '';
        // A PART CLOSED BY FAIL keeps the closed fill and wears the FAIL cross every view gives a FAIL, on its corner
        // (audit E8): the accent ring already says «PASS contested», an accent fill would read as a call on a person
        const shut = closedByFail(taskOf(id));
        const cross = shut ? `<div class="cy-badge cy-shut" style="left:${b.x1}px;top:${b.y1}px;--dx:-9px"><svg viewBox="-6 -6 12 12"><path class="mk-fail" d="M-2.5,-2.5l5,5m0,-5l-5,5"/></svg></div>` : '';
        if (!work.has(id) && rs.length < 2 && !failing) return cross + tag;
        return cross + `<div class="cy-badge" style="left:${b.x2}px;top:${b.y1}px">`
            // the pulse keeps the page's one clock: a badge redrawn on every render restarted it mid-beat
            + (work.has(id) ? `<i class="cy-live${now.lit(id) ? ' on' : ''}"${beat()}></i>` : '')
            + (rs.length > 1 || failing ? `<span${failing ? ' class="cy-fails"' : ''}>${rs.length}</span>` : '') + '</div>' + tag;
    }).join('');
    if (html !== shown) plane.innerHTML = shown = html;
    ride();
}
let shown = '', drawing = false;
// the run is read after the first drawing: an untouched view is framed again on what asks now
export const annotate = () => { if (cy?.nodes().length && fresh) home(); placeBadges(); };
// The canvas height the drawn graph needs for its labels to read (zoom ≈ 0.8), framing included.
export const graphNeeds = () => cy && cy.nodes().length ? cy.elements().boundingBox().h * 0.8 + 70 : 0;

// The nodes standing under the fold as it is, and their edges; what could not be drawn is returned.
function place(g) {
    const rep = foldInto(g.nodes);
    cy.elements().remove();
    const tomb = new Set(g.nodes.filter(cancelled).map(n => n.id));
    for (const n of g.nodes.filter(n => rep[n.id] === n.id))
        cy.add({data: {id: n.id, label: readableLabel(nameOf(n)), state: n.state, ...closureStyle(styleOf(n.state), n.closure, n)},
                classes: [tomb.has(n.id) && 'cancelled', n.outside && 'outside'].filter(Boolean).join(' ') || undefined});
    // ONE BAD EDGE MUST NOT COST THE WHOLE PICTURE: a dangling edge threw before the layout ran and
    // left fifteen nodes stacked at the origin (2026-09-06). Draw what can be drawn, SAY what cannot.
    // an edge into a folded part is drawn to the node it is folded into — once, and never inside one fold
    const ids = new Set(g.nodes.map(n => n.id)), undrawable = [], seen = new Set();
    for (const e of g.edges) {
        if (!ids.has(e.source) || !ids.has(e.target)) { undrawable.push(e); continue; }
        const source = rep[e.source], target = rep[e.target], k = `${source}>${target}>${e.type}`;
        if (source === target || seen.has(k)) continue;
        seen.add(k);
        // an arrow is not chosen by a click — a lit arrow said nothing (the author, 11-15: «функционально не дает ничего, только
        // шум»); its hover says what it means instead
        cy.add({data: {source, target, type: e.type, inner: source !== e.source || target !== e.target}, selectable: false,
                classes: tomb.has(e.source) ? 'fromCancelled' : undefined});
    }
    return undrawable;
}
const laid = animate => new Promise(done => { const lay = cy.layout({...LAYOUT, animate, animationDuration: 200});
    lay.one('layoutstop', done); lay.run(); });

// THE PATH OVER A VIEW OF ONE PART: where it stands in the whole, each step a way up — the context a cut would lose
let pathEl;
function drawPath() {
    const t = FOCUS && taskOf(FOCUS);
    pathEl ??= $('cy').parentElement.insertBefore(Object.assign(document.createElement('nav'), {className: 'cy-path'}), $('cy'));
    pathEl.hidden = !t?.id;
    if (!t?.id) return;
    const up = ancestorsIn(S.tasks)(t.id).reverse().slice(1);   // the goal is the whole graph: named once, first
    pathEl.innerHTML = `<button data-focus=""${TIP.pathWhole}>The whole graph</button>`
        + up.map(id => `<span>›</span><button data-focus="${esc(id)}">${esc(nameOf(taskOf(id)) || id)}</button>`).join('')
        + `<span>›</span><b>${esc(nameOf(t) || t.id)}</b>`;
    pathEl.onclick = e => { const b = e.target.closest('[data-focus]'); if (b) goTo(b.dataset.focus, true); };   // the path goes up
}

// The graph as last read (model.js loadGraph); `found` false: the project does not exist (yet), and nothing is drawn.
const redraw = () => drawGraph(true);
// `anew`: a move to another part — its drawing is framed as a first one
export async function drawGraph(found, anew = false) {
        if (!found) {
            // a project not on disk yet: nothing of a run to show nor a move to sign, only the wait for it (a goal stated here)
            document.body.classList.add('project-missing');
            cy.elements().remove();
            return;
        }
        const g = viewed(S.graph);
        drawing = true;
        // a move to another part: the last part's marks go with it, not left over the new drawing while it is laid (critic)
        if (anew && plane) plane.innerHTML = shown = '';
        drawPath();
        // a project with a mode is moved by agents and the system; the person's own moves, and the name they sign
        // them with, belong to a project without one, where a node is held by whoever it names (author, 2026-10-26)
        document.body.classList.toggle('manual', !g.mode?.mode);
        document.body.classList.remove('project-missing');
        // a changed plan is measured whole before anything is painted, and only then folded; the layout runs unanimated and
        // the moves below stay in one task, so the whole drawing is never seen
        const view = {zoom: cy.zoom(), pan: {...cy.pan()}}, sameProject = S.project === drawnIn;
        if (planChanged(g.nodes)) {
            cy.resize();
            if (!decidedBefore(g, [cy.width(), cy.height(), FLOOR])) {
                place(g);
                if (cy.nodes().length) { await laid(false); cy.fit(undefined, 30); decide(g.nodes, cy.zoom() < FLOOR); cy.viewport(view); }
            }
        }
        const undrawable = place(g);
        // the same nodes drawn again keep the view; so does a plan that changed under a view the reader has touched (the view
        // is theirs: a push moved it, critic 7); an untouched one, or another project, is framed anew
        const key = cy.nodes().map(n => n.id()).sort().join('|');
        const kept = !anew && sameProject && (key === drawn || !fresh);
        drawn = key; drawnIn = S.project;
        if (cy.nodes().length) {
            // framed once the layout knows where things are — and the read resolves only then, so a caller
            // measuring the drawing measures the finished one
            // …a move to another part is drawn in place, never flown in from the last part's positions: a part flew in from the
            // side, another opened centred (the author, 2026-11-17: «то прилетает сбоку граф то сразу по центру»)
            await laid(!kept && !anew);
            if (kept) cy.viewport(view); else { home(); fresh = true; }
        }
        // a redraw removes and re-adds every node, and the chosen one lost its border while its panel stayed open
        if (focus().select) cy.getElementById(focus().select).select();
        // the marks placed once the layout has put the nodes: a render during the drawing placed them at the origin, the
        // framing after it only moved their plane, and the tags hung at the canvas's side until a click or the deck redrew
        // them (the author, 11-15: «пару кнопок parts висит оторвано сбоку … только после прогрузки встает на свое место»)
        drawing = false; placeBadges();
        applyMineDim();
        const one = undrawable[0];
        banner('undrawable', one && `${undrawable.length} edge(s) not drawn — they name a node this graph does not `
            + `contain (e.g. ${one.source} → ${one.target}). The rest of the graph is shown.`, $('cy'));
}

// "Mine only": the nodes held by the names this page signs as (one of them, as «Mine» chose, or all) — a view in a
// project without a mode, signing nothing
export function applyMineDim() {
    if (!cy) return;
    const names = mineNames();
    cy.elements().removeClass('dimmed');
    if (!S.mineOnly || !names.length || S.graph.mode?.mode) return;
    const mine = new Set(S.tasks.filter(t => names.includes(t.assignee)).map(t => t.id));
    cy.nodes().forEach(n => { if (!mine.has(n.id())) n.addClass('dimmed'); });
    cy.edges().forEach(e => { if (!mine.has(e.source().id()) || !mine.has(e.target().id())) e.addClass('dimmed'); });
}
export function toggleMine() {
    S.mineOnly = !S.mineOnly;
    keep(`gfso.mineOnly:${S.project}`, S.mineOnly ? '1' : '');   // …kept per project, as the name chosen is (critic 4)
    $('queue-toggle').classList.toggle('active', S.mineOnly);
    applyMineDim();
}

// A transition patches its node in place; false when the node is not drawn (the caller re-reads).
export function restyle(id, state) {
    const node = cy.getElementById(id);
    if (node.length) node.data({state, ...styleOf(state)});
    return node.length > 0;
}

