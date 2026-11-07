// What the page says back, IN the page. `alert`/`confirm`/`prompt` block every event in the tab, and the
// thing said most often is a refusal — so the most common message froze the page and no automated pass
// got past its first refusal (wave 26, 2026-09-06). One floating box, styled in gfso.css (.overlay).
import {$, el} from './dom.js';
import {frameText} from './hints.js';
import {refusal, openProject} from './api.js';
import {S} from './state.js';

const box = (id, kind = '', parent = document.body) => {
    $(id)?.remove();
    return parent.appendChild(el('div', {id, className: `overlay ${kind}`}));
};

// Long text is kept: a refusal names the rule, the section and the way out. It does not outlive the
// act it refused — a stale one sat over a whole cancel handshake — but the bad kind lasts longer.
export function notice(text, kind) {
    const b = box('page-notice', kind === 'bad' ? 'bad' : '');
    Object.assign(b, {textContent: text, onclick: () => b.remove()});
    b.dataset.tip = frameText('dismiss');
    setTimeout(() => b.remove(), kind === 'bad' ? 45000 : 12000);
}
export const clearNotice = () => $('page-notice')?.remove();

// AN ACT ON THE ENGINE, one way for every unit that sends one. A REFUSAL IS THE ENGINE TALKING TO YOU: it arrives as a
// 200 whose body says no, and the page used to drop it and refresh — the node did not move and nothing said why. So the
// request is sent; the engine's no is said as the engine wrote it, after what was refused (`what`) and before what to
// do about it (`note`) — in a notice, or where `to` says; a yes runs `ok` (the page re-read unless said otherwise). A
// server that does not answer is said too, as itself: no refusal was made, and the act may have landed. Returns the
// no, '' for a yes.
export const NO_ANSWER = 'The server did not answer — the act may have landed; re-read the page before sending it again.';
export async function act(req, {what = '', note = '', ok = () => S.reload(), to = no => notice(no, 'bad')} = {}) {
    let no;
    try { no = await refusal(await req); } catch (e) { no = NO_ANSWER; }
    if (no) to(no === NO_ANSWER ? no : `${what ? what + ': ' : ''}${no}${note}`); else await ok?.();
    return no;
}

// `field`: a line of text to ask for beside the question — then the answer is that text ('' allowed), false on Cancel
export const askInPage = (question, {yes = 'Run it', field} = {}) => new Promise(resolve => {
    const b = box('ask-box');
    b.innerHTML = `<div class="ask-q">${question}</div>`
        + (field ? `<input id="ask-text" class="ask-text" placeholder="${field}">` : '')
        + `<div class="actions"><button class="btn btn-sm" id="ask-yes">${yes}</button><button class="btn btn-sm btn-muted" id="ask-no">Cancel</button></div>`;
    const done = v => { b.remove(); resolve(v); };
    $('ask-text')?.focus();
    $('ask-yes').onclick = () => done(field ? $('ask-text').value.trim() : true);
    $('ask-no').onclick = () => done(false);
});

// A NEW PROJECT'S NAME, asked beside the picker; the tab then goes there (`then.goal`: to state its goal). A name is
// required: an empty one landed silently in `default` (reached programmatically, wave 26).
const NAME = /^[A-Za-z0-9_-]+$/;
export function askProjectName(then = {}) {
    if ($('new-project-name')) return;
    const input = el('input', {id: 'new-project-name', placeholder: 'new project name', pattern: '[A-Za-z0-9_-]+'});
    const go = () => NAME.test(input.value.trim()) ? openProject(input.value.trim(), then)
                                                   : notice('a project name is [A-Za-z0-9_-]', 'bad');
    const box = el('span', {id: 'new-project-box'}, input, el('button', {className: 'hd-q', id: 'new-project-go',
                                                                         textContent: 'Open', onclick: go}));
    input.onkeydown = ev => { if (ev.key === 'Enter') go(); };
    $('project-open').after(box);
    input.focus();
}

// A standing statement about the page itself; empty text takes it down.
export const banner = (id, text, parent) => text ? (box(id, 'bad', parent).textContent = text) : $(id)?.remove();
