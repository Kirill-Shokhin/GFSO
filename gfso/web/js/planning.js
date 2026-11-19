// WHILE THE GOAL'S PLAN IS AUTHORED there is no graph to draw, and minutes of an empty canvas read as nothing running
// (the author, 2026-10-30: «не вижу в ui прогон»). The canvas then says what the server records: the authoring in flight,
// since when, and the stage it has reached — the engine's own field on that entry (`in_flight[].stage`: {stage, done, of,
// since}, pushed on the inflight feed), not the narration's prose read by a pattern, a copy register §2 forbids.
// ONCE WRITTEN, the plan is the page until the go (`GET /api/plan`): the person read it only in the client's words, and a
// dropped criterion went unsaid (INSTRUCTION_AUDIT row 1). It reads as a document under the header, not a box on the
// graph's canvas — there it read through a keyhole and the graph's library took its wheel and its taps (critics). First
// what decides the go — what it refuses, what the repair took back, what stays open — then the parts and the notes; every
// paragraph (a document the goal names, a reason, a note's answer) one press away, never cut. The go stays the client's.
import {$, esc, tally, since} from './dom.js';
import {S, procs, heard} from './state.js';
import {rootOf} from './tree.js';
import {hm} from './fmt.js';
import {PLAN} from './hints.js';
import {PROC_KIND} from './run.js';

// the documents a goal names are written under it by the server (tools_llm `_named_documents`), each under `## path`
const DOCS = '\n\n# THE DOCUMENTS THIS REQUEST NAMES';
const more = (k, summary, body, cls = '') => `<details class="cp-more${cls}" data-k="${esc(k)}"><summary>${summary}</summary>`
    + `<div class="cp-body">${esc(body)}</div></details>`;
const sec = (head, items, cls = '') => !items.length ? '' : `<section class="cp-sec${cls}"><h3>${esc(head)}</h3>${items.join('')}</section>`;
const line = t => `<div class="cp-row"><span>${esc(t)}</span></div>`;
const first = t => String(t || '').split('\n')[0];
// an answer's verdict on its note, as the round wrote it (`NOT ANSWERED`, `NOT REPAIRED`)
const unmet = a => (String(a || '').match(/NOT (ANSWERED|REPAIRED)/) || [])[0];

// …each document by its path where the server sends them apart (`documents: [{path, text}]`); else all of them in one
// fold: a document's own `## ` headings cannot be told from the server's, and split there they read as documents that do
// not exist (critic)
function goal(text, documents) {
    const [own, docs = ''] = String(text || '').split(DOCS);
    const named = documents?.length ? documents.map(d => more(`doc|${d.path}`, esc(PLAN.doc(d.path)), d.text))
        : docs.trim() ? [more('doc|*', esc(PLAN.docs), docs.replace(/^[^\n]*\n+/, ''))] : [];
    return `<div class="cp-goal">${esc(own.trim())}</div>` + named.join('');
}

function written(p, go) {
    const parts = p.parts || [], notes = p.notes || [];
    return `<header class="cp-title"><b>${PLAN.written}</b><span>${esc(PLAN.when(hm(p.written_at * 1e3)))}</span></header>`
        + goal(p.goal, p.documents)
        // …where the parts will run, said before the go is given: that is where the person decides it (row 5)
        + (heard().runs_on_host ? `<div class="cp-row cp-warn"><span>${esc(PLAN.host)}</span></div>` : '')
        + sec(PLAN.refused, (p.refused_by_the_go || []).map(line), ' cp-red')
        + sec(PLAN.takenBack, (p.taken_back || []).map(line), ' cp-warn')
        // …an open criterion by its name, the review's reason under it (the server cuts it at 300 characters)
        + sec(PLAN.open, (p.open || []).map((x, i) => { const [what, ...why] = x.split(' — ');
            return why.length ? more(`open|${i}`, esc(what), why.join(' — ')) : line(x); }), ' cp-warn')
        + (p.undecided ? `<div class="cp-row cp-warn"><span>${esc(PLAN.undecided(p.undecided))}</span></div>` : '')
        // …what the goal is accepted by, each criterion with its checks as agreed — what the go is given on (a critic, 11-19:
        // before the go the page showed only the goal); a name alone where the server sends no checks
        + sec(PLAN.criteria, (p.root_criteria || []).map(c => typeof c === 'string' ? line(c) : more(`crit|${c.name}`,
            `<span>${esc(c.name)}</span>` + tally((c.check || []).length, (c.check || []).length === 1 ? 'check' : 'checks'),
            // …each check in words first (`behaviour`), then what runs and what it expects
            [c.description, ...(c.check || []).map(k => [`– ${k.behaviour || k.command || ''}`, k.behaviour && k.command && `  ${PLAN.runs(k.command)}`,
                k.expect && `  ${PLAN.expect(k.expect, k.exact)}`].filter(Boolean).join('\n'))].filter(Boolean).join('\n'))))
        + sec(PLAN.parts(parts.length), parts.map(x => more(`part|${x.id}`,
            `<span>${esc(x.name || x.id)}</span>${x.split_after?.length ? `<em>${esc(PLAN.after(x.split_after))}</em>` : ''}`
            + tally((x.criteria || []).length, (x.criteria || []).length === 1 ? 'check' : 'checks'),
            [x.description, ...(x.criteria || []).map(c => `– ${c}`)].filter(Boolean).join('\n'))))
        + sec(PLAN.notes, notes.map((n, i) => more(`note|${i}`,
            `<span>${esc(first(n.note))}</span>${unmet(n.answer) ? `<em class="cp-bad">${esc(unmet(n.answer).toLowerCase())}</em>` : ''}`,
            `${n.note}\n\n${PLAN.answer}\n${n.answer || '—'}`)))
        + (go ? '' : `<footer class="cp-foot">${esc(PLAN.go)}</footer>`);
}

// what runs now over the plan: an authoring, a note's round, or the go being built
function running(w, p) {
    const s = w.stage, go = w.verb === 'auto_decompose' && p;
    // …how long so far is the strip's chip and the sum's: said here too, two clocks drifted apart (critic)
    return `<div class="cp-head"${PLAN.since(hm(w.since * 1e3))}><b>${go ? PLAN.building : PLAN.title}</b></div>`
        + (!s ? `<div class="cp-row cp-now">${PLAN.starting}</div>`
            : `<div class="cp-row cp-now"><i></i><span>${esc(s.stage)}</span>${s.of > 1 ? tally(`${s.done}/${s.of}`, 'done') : ''}`
              + `${tally(since(s.since * 1e3), 'running', PLAN.since(hm(s.since * 1e3)))}</div>`);
}

// …the page starts where the header ends, and the header grows as its goal and chips are read: drawn before, it stood
// under the header's second line on a phone
let watched = null;
const underHeader = box => { const h = document.querySelector('.header'); if (!h) return;
    const put = () => { const b = $('cy-plan'); if (b) b.style.top = `${h.getBoundingClientRect().bottom}px`; };
    if (!watched) (watched = new ResizeObserver(put)).observe(h);
    put(); };

export function drawPlanning() {
    const none = !rootOf(S.tasks), w = none && procs().find(x => PROC_KIND[x.verb] === 'plan'), p = none && S.plan?.goal ? S.plan : null;
    let box = $('cy-plan');
    // a written plan is a page of its own under the header; an authoring alone stays the canvas's note
    if (box && box.classList.contains('cp-written') !== !!p) { box.remove(); box = null; }
    if (!w && !p) return;
    box ??= (p ? document.body : $('cy')).appendChild(Object.assign(document.createElement('div'), {id: 'cy-plan', className: p ? 'cy-plan cp-written' : 'cy-plan'}));
    // …what was opened stays open across the redraws a running round pushes
    const open = new Set([...box.querySelectorAll('details[open]')].map(d => d.dataset.k));
    if (p) underHeader(box);
    box.innerHTML = p ? `<div class="cp-page">${w ? running(w, p) + '<div class="cp-gap"></div>' : ''}${written(p, w?.verb === 'auto_decompose')}</div>` : running(w, p);
    for (const d of box.querySelectorAll('details')) if (open.has(d.dataset.k)) d.open = true;
}
