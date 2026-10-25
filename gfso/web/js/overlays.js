// What the page says back, IN the page. `alert`/`confirm`/`prompt` block every event in the tab, and the
// thing said most often is a refusal — so the most common message froze the page and no automated pass
// got past its first refusal (wave 26, 2026-09-06). One floating box, styled in gfso.css (.overlay).
import {$, el} from './dom.js';

const box = (id, kind = '', parent = document.body) => {
    $(id)?.remove();
    return parent.appendChild(el('div', {id, className: `overlay ${kind}`}));
};

// Long text is kept: a refusal names the rule, the section and the way out. It does not outlive the
// act it refused — a stale one sat over a whole cancel handshake — but the bad kind lasts longer.
export function notice(text, kind) {
    const b = box('page-notice', kind === 'bad' ? 'bad' : '');
    Object.assign(b, {textContent: text, title: 'Click to dismiss', onclick: () => b.remove()});
    setTimeout(() => b.remove(), kind === 'bad' ? 45000 : 12000);
}
export const clearNotice = () => $('page-notice')?.remove();

// `field`: a line of text to ask for beside the question — then the answer is that text ('' allowed), false on Cancel
export const askInPage = (question, {yes = 'Run it', field} = {}) => new Promise(resolve => {
    const b = box('ask-box');
    b.innerHTML = `<div style="margin-bottom:10px">${question}</div>`
        + (field ? `<input id="ask-text" style="width:100%;box-sizing:border-box;margin-bottom:10px" placeholder="${field}">` : '')
        + `<div class="actions"><button class="btn btn-sm" id="ask-yes">${yes}</button><button class="btn btn-sm btn-muted" id="ask-no">Cancel</button></div>`;
    const done = v => { b.remove(); resolve(v); };
    $('ask-text')?.focus();
    $('ask-yes').onclick = () => done(field ? $('ask-text').value.trim() : true);
    $('ask-no').onclick = () => done(false);
});

// A standing statement about the page itself; empty text takes it down.
export const banner = (id, text, parent) => text ? (box(id, 'bad', parent).textContent = text) : $(id)?.remove();
