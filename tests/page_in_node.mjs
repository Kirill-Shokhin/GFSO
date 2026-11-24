// The page's modules run under node for a test: what a browser gives them at import, stubbed, and nothing drawn. A test
// imports this first, then the page's module by its file URL, calls an export and prints what it said.
const kept = {};
globalThis.localStorage = {getItem: k => kept[k] ?? null, setItem: (k, v) => { kept[k] = String(v); }, removeItem: k => { delete kept[k]; }};
globalThis.location = new URL('http://127.0.0.1:8000/?project=p');
globalThis.history = {replaceState() {}, pushState() {}, state: null};
globalThis.addEventListener = () => {};
globalThis.matchMedia = () => ({matches: false, addEventListener() {}});
globalThis.getComputedStyle = () => ({getPropertyValue: () => ''});
// …any element the module reaches for at import is a sink that answers everything
const sink = () => new Proxy(function () {}, {get: (t, k) => k === Symbol.toPrimitive ? () => '' : sink(), apply: () => sink()});
globalThis.document = sink();
globalThis.window = globalThis;
export const page = name => new URL(`../gfso/web/js/${name}`, import.meta.url);
// the page arms timers at import: the test ends when it has printed
export const say = value => { console.log(JSON.stringify(value)); process.exit(0); };
