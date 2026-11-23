// What the page knows between reads: the last graph read and who signs. WHICH node is selected is
// store.js's — one source for every view.
import {$} from './dom.js';
import {PROJECT, FOCUS, TOP, topOf, openFocus} from './api.js';
import {childrenOf, depths, ancestorsIn, rootOf} from './tree.js';
import {cancelled, statusLabel, delivered, contested, closedByFail} from './vocab.js';
import {runNow, heldByPerson, inWork} from './run.js';
import {bare} from './fmt.js';

// THE WHOLE SURFACE, written by its owners and read by the views:
//   model.js — tasks, graph, closures, missing (the graph read); frontier, runState, waiting, steps, mySteps (the
//              engine's next_steps); run, pipeline (the run read and built); reports, metrics (the system's own reads)
//   main.js  — inflight (the server's processes), me (whoami), reload (the page's refresh policy: units that change the
//              graph call it); projects.js — project; graph.js — mineOnly, mineName
// an agent's id without the project's name, as everywhere; whole where the cut would read as a node: «Del root» beside the node root read backwards (live critic)
export const agentName = id => { const b = bare(id, S.project); return S.tasks.some(t => t.id === b) ? id : b; };
// WHO MADE A LOGGED MOVE, as the log says (`by_system`, §11.6): the signer alone read «by agent» on a decision no agent of the
// user's made. A verdict the system signs is two things: who checked, where that is the validator, and who signed; any
// other move of the system is the system's, its signer only a name it signs under (`as`). An older record says nothing: its signer.
// …and a person's move says how its name signed (`via`, the credential the door resolved): his click on the page apart from
// his console's move under the same name, which a typed signer never told (docs/notes/SIGN_IN.md)
// …the page itself signs as `session` (signed in) or `local-peer` (its own account's process, no sign-in); a token's id starts `tok`
export const viaWord = v => !v ? '' : v === 'session' || v === 'local-peer' ? 'on the page' : v === 'default' ? 'by a local client'
    : String(v).startsWith('tok') ? 'by its token' : `by ${v}`;
export const moverOf = a => {
    const by = a.source && agentName(a.source);
    if (!a.by_system) return {word: by || (a.signal === 'TIMEOUT' ? 'clock' : ''), as: null, via: viaWord(a.via)};
    const validator = a.source !== 'user' && !S.tasks.some(t => t.assignee === a.source);
    return ['PASS', 'FAIL'].includes(a.signal) && by && validator
        ? {word: `${by}, signed by the system`, as: null, via: ''} : {word: 'the system', as: by, via: ''};
};
// a node's word now, as `enteredWord` says it of the move: a contract the log shows brought back by anything but its first offer has started
// …`audit` where the caller holds the node's own: a panel draws before the run is rebuilt (critic)
export const stateWord = (t, audit = S.run?.audit) => t.state === 'OFFERED' && audit?.some(a => (a.task_id ?? t.id) === t.id && a.new_state === 'OFFERED' && a.old_state && a.old_state !== 'IDLE')
    ? 'Offered again' : statusLabel(t.state, delivered(t) ? null : t.done_reason);
export const S = {tasks: [], graph: {nodes: [], edges: []}, closures: [], missing: '',
                  frontier: null, runState: null, waiting: null, steps: null, mySteps: new Map(),
                  run: null, pipeline: [], reports: [], metrics: null,
                  inflight: [], me: null, project: PROJECT, mineOnly: false, mineName: '', plan: {}, reload: async () => {}};

// the processes this server runs in this project now — the in-flight registry, the one reading of it
export const procs = () => S.inflight.filter(w => w.project === S.project);
// who holds a node under the mode, a person or the system (run.js heldByPerson, the one rule)
export const personHolds = t => heldByPerson(S.graph.mode, S.run?.depth ?? depths(S.tasks))(t);
// A verdict asserted by hand asks for a look only on a node the system holds, where an instrument was to sign it: on a
// node a person holds every PASS is by hand, and the mark counted all of them (the author, 2026-11-13: «90 closed by hand
// … зачем там эта кнопка вообще»). The panel still names each signer, as the record does.
export const handAsks = t => !personHolds(t);
// WHOSE ANSWER a node waits on — a challenge, a block, a decision, a verdict: its issuer's, the holder of its parent
// (§10.1), the goal's issuer for the root; under AUTO every issuer move below the root is the system's. One rule for the
// header's calls and the strip's waits — the header asked the node's own holder, and hid a SEMI dispute the engine
// says is the person's (critic 4).
// a delivery no process validates whose issuer is a person waits on that person's verdict (§12.1: one wait on the issuer):
// it is on the issuer, not in work — one rule for the strip and the list of what is in work
export const owedVerdict = (t, at = nowOf()) => t.state === 'VALIDATING' && !at.lit(t.id) && !at.carrier(t.id).length && issuerIsPerson(t);
// IN WORK, the page's one reading: what the log holds in work (run.js `inWork`), less a delivery
// owed to a person, which is on the issuer — the deck's line, its IN WORK tab and the fold tags read this and nothing else
export const inWorkOf = (tasks = S.tasks) => { const at = nowOf(); return inWork(tasks, S.run?.audit, at, t => owedVerdict(taskOf(t.id), at)); };
export const issuerIsPerson = t => !t.parent_id || (S.graph.mode?.mode !== 'auto' && personHolds(taskOf(t.parent_id)));
// what runs now is the run's one reading; before the run is read, the same rule over the registry
export const nowOf = () => S.run?.now ?? runNow(S.tasks, procs(), []);
// the project's work has begun: a node exists, or a process runs here — the goal's own plan authored before its root
// exists is work; read as «nothing yet», the page offered «Pose the goal» and no Stop over a planning run (a live row)
export const begun = () => S.tasks.length > 0 || procs().length > 0;

export const taskOf = id => S.tasks.find(t => t.id === id) || {};
// THE GOAL AS THE PERSON GAVE IT (`mode.goal_as_given`), beside the root's own words where those are the client's
// restatement (INSTRUCTION_AUDIT row 8): '' where they say the same, the documents the goal names left to the root
// WHAT THE GO HEARD (`graph.heard`: where the work runs, what its copy lacks, the goal as given), whatever the mode —
// the mode block carried it alone, and a project with no mode said none of it (critic); the mode's copy where the server is older
export const heard = () => S.graph.heard || S.graph.mode || {};
// WHETHER A GO ADDS THE CHECK AGAINST THE PERSON'S WORDS, as the engine acts on it, set or by default, a mode or none
// (`heard.intent_check`; the mode's copy where the server is older); undefined where the server says nothing
export const intentOn = () => S.graph.heard?.intent_check ?? S.graph.mode?.intent_check;
// …per goal (`by_root`): one setting a project gave every goal the latest go's words; an older server's flat keys only
// where the project has one goal
export const atTheGo = root => heard().by_root?.[root?.id] || (heard().by_root || S.tasks.filter(t => !t.parent_id).length > 1 ? {} : heard());
export const asGiven = root => { const g = String(atTheGo(root).goal_as_given || '').split('\n\n# THE DOCUMENTS THIS REQUEST NAMES')[0].trim();
    return g && root && !String(root.description || '').startsWith(g) ? g : ''; };
// WHO HOLDS the role a node waits on, by the same rule as `issuerIsPerson`: the executor is its Del, the issuer its
// parent's (§10.1); the goal's issuer is outside the graph and under AUTO the system's, so neither is named
export const whoOwes = (t, role) => role === 'executor' ? t.assignee || ''
    : role === 'issuer' && t.parent_id && S.graph.mode?.mode !== 'auto' ? taskOf(t.parent_id).assignee || '' : '';
// IN THIS VIEW: the whole graph, or in a view of one part (`?focus=`) that part and what lies under it — one rule for every
// count the header and the deck give, so a view of a part counts the part (the header said 105/434 over Engineering's view)
// …and in a view of «N closed» (`closed:<part>`), the part and the parts its group holds, with all under them
export const inView = id => { if (!FOCUS || id === TOP) return true;
    const chain = [id, ...ancestorsIn(S.tasks)(id)], i = chain.indexOf(TOP);
    return i > 0 && (FOCUS === TOP || closedOf(TOP).some(t => t.id === chain[i - 1])); };
// QUIET: settled and asking nothing, inside it included — what «N closed» gathers. What asks keeps a node and every node
// above it drawn: a live one, a contested PASS, one closed by FAIL, a PASS by hand on what the system holds (critic 2,
// 11-19). One reading for the drawing's groups and for the view that opens one.
let quietOf = null, quietIds = new Set();
export const quiet = () => { const nodes = S.graph.nodes || [];
    if (quietOf === nodes) return quietIds;
    const up = ancestorsIn(nodes), asks = new Set();
    const asking = n => !(n.state === 'DONE' || n.state === 'ABANDONED') || contested(n.closure || {}) || closedByFail(n) || (n.closure?.by_hand && handAsks(n));
    for (const n of nodes) if (asking(n)) [n.id, ...up(n.id)].forEach(a => asks.add(a));
    quietOf = nodes; quietIds = new Set(nodes.filter(n => !asks.has(n.id)).map(n => n.id));
    return quietIds; };
export const viewTasks = () => FOCUS ? S.tasks.filter(t => inView(t.id)) : S.tasks;
// the server's processes on what is in the view (a process on no node is the project's, so a part's view leaves it out)
export const viewProcs = () => FOCUS ? procs().filter(w => w.task_id && inView(w.task_id)) : procs();
// THE VIEW'S OWN TREE, the part as its top (no parent): the part's run is built over it (model.js `S.viewRun`) for the
// deck's figures; the project's facts stay on the project's run (critic, three rounds)
const asTop = t => t.id === TOP ? {...t, parent_id: null} : t;
export const viewTree = () => FOCUS ? viewTasks().map(asTop) : S.tasks;
export const viewNodes = () => FOCUS ? S.graph.nodes.filter(n => inView(n.id)).map(asTop) : S.graph.nodes;
// a part opened as its own view, the goal's being the whole graph; up: the part above the one viewed
// …a view of «N closed» stands inside its part
// …a group's view holds the parts its group holds, and what lies under them — never its own part (critic: Back after Up
// into a group skipped the part's view, counted inside its own group)
export const inside = (id, part) => { const g = topOf(part), x = topOf(id);
    if (part !== g) return id === part || closedOf(g).some(t => [x, ...ancestorsIn(S.tasks)(x)].includes(t.id));
    return !part || x === part || (!!x && ancestorsIn(S.tasks)(x).includes(part)); };
export const goTo = (id, up = false) => openFocus(id && (id !== topOf(id) || taskOf(id).parent_id) ? id : '', up);   // …or «N closed»'s view
// what the view's top is called, one word for every place that names it (Progress, Spend's levels, the done mark) — the goal
// in its own «N closed» too
export const topWord = () => FOCUS && taskOf(TOP).parent_id ? 'the part' : 'the goal';
// THE PARTS A NODE'S «N CLOSED» HOLDS, the one rule the drawing, its view and every way to it read: its cancelled parts
// always (the author, 11-23: «отмененные задачи также по умолчанию не уходят в отдельную группу») — a cancelled part is no
// work —, and its done ones three or more (11-19: «уже закрытые задачи сейчас в ряд стоят и … будут мешать»); a lone done
// part or two keep their own nodes, the work's result (critic: one hidden in «1 closed»). Save the done parts of a closed
// node that is the view's own top — the goal of a finished graph, a settled part gone into: gathered, the view would be
// the node and its group, a second press at every level of a settled branch (critics).
const CLOSED_AT = 3;
export const closedOf = p => { if (!p) return [];
    const xs = childrenOf(S.tasks, p).filter(t => quiet().has(t.id));
    const top = FOCUS === TOP && p === (TOP || rootOf(S.tasks)?.id) && quiet().has(p);
    return xs.length >= CLOSED_AT && !top ? xs : xs.filter(cancelled); };
// THE VIEW A NODE IS DRAWN IN, one step down from its parent: the parent's own, or its «N closed» where it is gathered there
export const whereDrawn = id => { const p = taskOf(id).parent_id || '';
    return closedOf(p).some(t => t.id === id) ? `closed:${p}` : p; };
// THE STEPS DOWN TO THIS VIEW, each a view: every part below the goal, its group's view before it where it is gathered — a
// part opened from «N closed» goes up into that group, the way it came (critic: Up skipped it, Back did not)
export const pathSteps = () => { if (!FOCUS) return [];
    const steps = [], ids = [...ancestorsIn(S.tasks)(TOP).reverse().slice(1), ...taskOf(TOP).parent_id ? [TOP] : []];
    for (const id of ids) { const w = whereDrawn(id); if (w !== topOf(w)) steps.push(w); steps.push(id); }
    if (FOCUS !== TOP) steps.push(FOCUS);
    return steps; };
export const goUp = () => goTo(pathSteps().at(-2) || '', true);
export const hasKids = id => childrenOf(S.tasks, id).some(t => !cancelled(t));

// What this browser keeps for its viewer — wrapped, because a browser with site data blocked THROWS on the accessor.
export const kept = (k, read = x => x) => { try { return read(localStorage.getItem(k)); } catch (e) { return null; } };
export const keep = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* a per-viewer nicety */ } };

// THE PARTIES OF THIS GRAPH, as the engine names them — each holder and each issuer, with who makes its moves (`person`,
// `holder`, `machine`, validation.party_kind): the one reading of whether the system holds anything, never a list
// the page builds of its own (two such lists disagreed about the agent — ui critic, 2026-11-14)
export const parties = () => S.graph.parties || [];
export const partyKind = name => parties().find(p => p.name === name)?.kind;
// WHO THIS PAGE IS, as its credential says (`/api/whoami`): the names a move made here may be signed as. The page sends no
// signer — the server signs as the holder of the role the move needs, among these — and a browser not signed in moves
// nothing (`lift` says how to sign in). The author, 2026-11-15: «логининг определяет имя а не запись в интерфейсе».
export const signsAs = () => S.me?.signs_as || [];
export const owns = name => !!name && signsAs().includes(name);
// a move is this page's where its performer is a name it signs as; one the engine leaves unnamed is anyone's — the one rule
// the frontier's steps and the panel's moves both read (critic 4: it was written twice)
export const minePerformer = n => signsAs().length > 0 && (!n || owns(n));
// «Mine»: a VIEW over those names — the one chosen, all of them ('*'), or with no choice made the name holding the view's
// top (a part opened as a view, else the goal) where it is one of them: locally a person owns every stream's name, and all
// of them read 235 red «for you» on his own graph (critic 2) — who holds what he looks at is who he is there; another is
// one choice away. It signs nothing.
export const mineNames = () => {
    if (S.mineName === '*') return signsAs();
    if (owns(S.mineName)) return [S.mineName];
    const top = (FOCUS ? taskOf(TOP) : rootOf(S.tasks))?.assignee;
    return owns(top) ? [top] : signsAs();
};
// what the choice of name shows: the one the view holds, else «all»
export const mineShown = () => mineNames().length === 1 && signsAs().length > 1 ? mineNames()[0] : '*';
// …and how this browser signs in where it does not: the server's own sentence, said where a move would be
// …and a page whose server did not say who it is is told that, not to sign in: on a local server there is no sign-in (critic)
const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]']);
// …and one reached past this machine's loopback READS (the author, 2026-11-16: «чтение графа … по дефолту может быть
// открыто на локалке», «ходы пускай и будут со входом»): it is told how to move from here, the host it came by filled in
export const lift = () => signsAs().length ? '' : !S.me ? 'the server has not said who this page is: its moves come back when it does'
    : reader() ? `to make moves from this device: on the computer run \`gfso ui --host ${here()}\` and open the link it prints`
    : S.me.lift || '';
// a server's sentence naming the host this page was reached at, by the placeholder the server writes for it
export const hereIn = line => line.replace(/<the name you reached it at>|<front>/g, here());
// …the host as `gfso ui --host` takes it: a bare name it opens over https (a front such as tailscale serve), so a page
// reached over plain http — a LAN address, the server's own bind — is named with its scheme, or the link it prints fails (critic)
const here = () => location.protocol === 'https:' ? location.host : location.origin;
// a page reached past loopback with no name to sign as: a reader, its moves made from the computer
export const reader = () => !!S.me && !signsAs().length && !LOOPBACK.has(location.hostname);
