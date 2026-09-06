# Changelog

Notable changes to the reference implementation. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The **canon** (`docs/applied_gfso_v4_en.md`) is versioned separately from this package and carries
its own Changelog section; where a release re-anchors the code to a canon version, that is stated
below. Nothing in this file states a measured effect of using GFSO on real work: the experiment that
would establish one (E3) is open, and what has been run so far is a calibration tier with its own
stated boundaries — `docs/EVIDENCE_LOG.md` §13, and §3/§9/§11 for the earlier ones.

## [0.1.0] — 2026-09-06

The first published version. Nothing before this was published — there was no 0.1 and no 0.2 to install — so the public line
starts here, at the number that says so rather than at one implying a history that does not exist.
Earlier work lives in the git log.

`0.x` is a statement, not a placeholder: the protocol and the state machine are stable because they
are the canon's and the canon is closed, while the Python API, the CLI surface and the UI may still
change under a minor bump. The release policy, and the procedure that enforces it, are the
comments at the top of `.github/workflows/release.yml`.

### Added

- **Protocol engine.** The 12-signal / 12-state FSM of canon Chapter 14, with the transition table as
  the single source of truth for behaviour, over a task graph with criteria, coverage mappings,
  dependencies, deadlines and an accepted-risks register.
- **Verifier ≠ executor gate.** A `PASS` signed by a node's own executor is rejected at every
  delegation seam — and at the root — until an independent verdict for the current delivery is on
  record (§14.5). `record_verdict` is the human counterpart; `validate_result` spawns a read-only
  validator that runs the criteria.
- **A green that is not green does not stay quiet.** A node can stand at `PASS` while its own current
  record says `FAIL` — the signature landed, and the instrument's verdict arrived seconds later at a
  node the state machine had already closed. The engine had always detected this (it is `q_V`'s
  numerator) and only a metric said so. Now `next_steps` refuses to answer *complete* over such a
  node and names it under `refuted_passes`, `gfso status` renders it as `[X] … PASS CONTRADICTED by
  its own current verdict` rather than the tick an earned node gets, and `get_verdict` carries
  `contradicts_state`. A verdict that lands after a node closed is kept beside the one it closed on
  (`closed_on`) instead of replacing it: a later record is evidence about the same delivery, never a
  replacement for the one that was acted on.
- **A verdict says which of three kinds of party produced it.** Asserted by hand, self-reported by the
  node's own executor (§14.5 D6), or produced by a registered instrument that is not the executor —
  three different weights of evidence, where the read used to collapse the middle into the last. The
  dispatcher will not replay a hand-asserted verdict under an instrument's name.
- **An observation has to observe, and a dispute has to give a reason.** A `PASS` whose per-criterion
  text only restates the verdict (`"ok"`, `"looks green"`) is refused the way a `PASS` with no text
  already was — over an empty conjunction of criteria too, where the rule was otherwise vacuously
  satisfied — and a Level-2 finding cannot be discharged by `"nah"`. `get_review` now says which
  findings were closed by argument rather than by changing the plan. The floor is on ASSERTION, not
  on evidence: it cannot refuse a sentence that names a command nobody ran, and it says so.
- **Every metric arrives with what it means.** `/api/metrics` and the `metrics` verb serve `means`
  from the module that computes the formulas, so a number and its explanation cannot drift apart, and
  they carry `false_fail_share` — the diagnostic the canon says to read beside a low `q_D`, which the
  door had documented and silently dropped. `⊥` renders as a dash, never as a score of zero.
- **Replacing a node's criteria says what coverage that destroyed**, and whether the loss is final —
  a mapping to a child that has already finished cannot be re-made, because adding a coverage to a
  terminal contract is a revision of it.
- **The bridge survives a server restart under it.** The client's side of the stdio bridge is opened
  once and outlives every rebuild of the HTTP leg; a call in flight when the leg breaks is answered
  rather than left waiting, including the one whose failure discovered the break. Before this, the
  first call after a restart sat silent until the client's own idle ceiling — thirty minutes — while
  the server was up and serving others.
- **Level-2 review of a decomposition (§13.4).** `review_decomposition` judges, per parent criterion,
  whether the mapped children's criteria causally carry it, and the engine will not let a child begin
  executing until the parent's review is current and its findings are dispositioned —
  by a plan edit or by a written `dispute_finding`.
- **`auto_decompose`.** One decomposition verb, dispatched by the target's state: it authors a
  verified subtree from a request, or runs refine rounds over an existing one, folding new findings in
  as a revision that preserves ids, owners and accepted risks.
- **Delegation by assignment.** Register executor and validator roles once; a node assigned to a
  registered executor is dispatched, its report wrapped into canonical signals, its delivery
  auto-validated, and a failed criterion re-entered into a bounded rework loop. People are never
  registered — a node assigned to a person waits for their signals.
- **Three doors over one engine**, generated from a single tool registry: HTTP+WS API, CLI
  (`gfso run <tool>`), and an MCP surface for agent sessions. The web UI is a client of that API,
  not a fourth door — which is why every write, whichever door made it, appears in it live.
- **One shared server.** `gfso up` reconciles the single server at `127.0.0.1:8000` against the
  working tree — starting it, restarting it when it serves stale code or the wrong switches, and doing
  nothing when it is already correct. Projects, not ports, are the isolation boundary.
- **Embeddable pure core.** The zero-dependency `gfso-core` distribution, built from a manifest whose
  closure is proven on every test run, with a pre-registered acceptance suite for embedding it into a
  foreign host (`docs/embeddability_acceptance.md`).
- **Guards in CI.** Four of them: three check that the citations, names and counts in this
  repository's prose and code still match the canon, and the fourth is the fail-closed Lean axiom
  whitelist. The Lean development is built in CI too. The three TLA+ models are model-checked by
  hand and their runs are recorded in `formal/tla/README.md` — TLC is not a CI step, and the state
  spaces it produced are not in the repository.
- **Installed from PyPI, and usable from anywhere.** `pipx install gfso` carries the engine, the UI,
  the agent door and the examples; `gfso setup` registers the door with Claude Code, brings the one
  server up and reports; `gfso doctor` states what this installation is and what blocks it —
  version, state home, who holds the address, whether the Claude Code CLI answers; `gfso --version`
  reads the single place the version is written; `gfso demo <name>` runs a shipped example.
- **One state home per user.** An installed package keeps the database, the log and the agent
  registry in `~/.gfso` (a source checkout keeps them in the tree), and `GFSO_HOME` overrides it on
  **every** door — including `gfso connect`, the one an agent client runs, which honoured only the
  caller's working directory. Separate pieces of work are separate projects in the one home.
- **The distribution itself is tested**, not the field that describes it: the wheel and the sdist are
  built, opened, and the wheel installed into a fresh environment and driven from a directory that is
  not the repository. Both directions are checked — every runtime asset arrives, and no internal
  document leaves.
- **A scope boundary can be declared through the agent's door.** `scope` was written back but never
  read on input, so the only place left for a capability the goal excludes was the risk register —
  which refuses it, correctly, for having no materialization probability (§13.1).
- **This documentation surface**: `README.md`, `docs/USING_GFSO.md`, `docs/TASK_PACKET.md`, `docs/architecture.md`,
  `gfso/examples/`, `SECURITY.md`, and this file.

- **A closed node says HOW it closed, on every surface that draws it.** One record answers who
  produced the standing verdict — an instrument, the node's own executor, or a person who named
  themselves — whether a hand verdict displaced an instrument's opposite one, and whether the node
  stands at `PASS` over its own current `FAIL`. It rides on the node reads and on the graph the UI
  draws, so a contested closure is ringed, a hand-asserted one is dotted, and the header counts them
  apart from the plain tally of finished nodes. `gfso status` reads the same field, so the marks no
  longer disappear while a project still has work in it.
- **A check answers four words, not two.** `met`, `unmet`, `skipped` — and `met_vacuously` for a
  check whose subject set is empty: deadline coherence on a plan with no dependency edges is true,
  and true of nothing. The page draws it `∅`.
- **A wholesale contract replacement can refuse to land on a contract that moved.** `revise` and
  `edit_criteria` take `expect_criteria` — the criterion names the caller read — and refuse, naming
  what was added or removed since, instead of silently dropping a concurrent author's work.
- **A self-reported `PASS` has to say what it checked.** A `DELIVER` carrying `self_validation=PASS`
  over a report that records nothing does not become the record an internal node is judged on
  (§14.5 D6): the floor is the one already applied to a reviewer's observations, in one place that
  both doors read. Reporting your own failure is never gated.
- **The plan gate stops re-litigating what a stronger plan already settled.** A criterion ruled
  sufficient carries forward when its own text is unchanged and the children covering it have only
  GAINED criteria — a conjunction that entailed the parent still entails it with a conjunct added
  (§13.4 CHECK-7). Rewording or removing one re-derives it, as it must.
- **An unobserved conjunct still cannot carry a `PASS` — but a paraphrase is not an unobserved
  conjunct.** The link between a named behaviour and the probe that observed it is matched against
  the shorter of the two descriptions, so a probe that ran and reported under different words is no
  longer thrown away, and a demotion names the labels it compared.
- **The project you chose survives a restart.** The switch is remembered, so a new server process
  starts where the last one was pointed instead of moving every reconnecting session to `default`.
  An explicit `GFSO_PROJECT` still wins.
- **The web UI is a door, not a picture.** A node is linkable (`?task=<id>`); the identity the page
  signs with survives a reload; one edit sends one revision; the Level-2 findings that block a graph
  are rendered where the review is read, instead of a green tick counted from the wrong fields; the
  control that repairs a plan is offered wherever the engine admits a revision; the graph is
  refreshed one call at a time, so a live update cannot leave it half-drawn; and the canvas is
  framed and resized around the detail panel.

### Changed

- **The vocabulary is the canon's, from the enum to the model checker.** `OFFERED`, `REWORKING`,
  `ABANDONED`, `OVERDUE`, `CONFIRM_CANCEL`, `ACCEPTED_RISKS`, `AUTO_PASS` and the rest now spell in
  code what v4.0 spells in prose — one vocabulary, written and read. The value-level shim that
  decoded the previous spellings on the way in is gone with the migration that needed it. (The one
  read-map that remains is older and unrelated: a pre-v3.7 database stored cancellation as
  `DONE(reason=CANCELLED)`, and that row is still mapped to `ABANDONED` on read.)
- **A verdict must state what it observed.** Every criterion carries the command that was run and the
  output it must show, and the engine refuses a verdict that omits it.
- **Each validation gets a fresh scratch directory** to copy into, so a validator that works on a
  copy cannot pick up one an earlier run left behind by accident. (It is offered by name, not
  imposed as the working directory — see below.)
- **An exhausted validation loop escalates** rather than settling as done: `FAIL` at the iteration
  limit reaches `ESCALATED` carrying its reason, since acceptance is the only route to `DONE`
  (§12.2, §14.3).
- **`IDLE` has no timeout**, per Inv-5's explicit exemption; an interrupted transition is instead
  finished at engine startup by orphan recovery.
- **The execution gate is the canon's whole Syntactic level.** It used to be four of the seven
  Level-0 checks; ACCEPTED_RISKS, risk nodes and leaf delegation were surfaced but never blocked a
  start, so a decomposition with an empty register was admitted where §13.1 calls one without the
  register incomplete by definition. All seven gate now (§13.4); `list_holes` names which one, and
  the anti-mock check — an addition with no canon row — deliberately stays out of the gate.
- **The deadline check now also enforces the vertical rule** — a child cannot fall due after its
  parent (§3.4 item 6). It rides in the same check function as CHECK-3, whose own definition stays
  the horizontal Dep rule the canon gives it (§26.5-bis; `formal/README.md`, corner 6).
- **An address held by something else is said out loud.** An open port was read as a running server,
  so `gfso up` on a machine where anything already listened spawned nothing, waited out its retry
  budget, and then reported a server that did not exist — measured at 114 seconds of silence
  followed by a success line.
- **An empty build is not a clean one.** A decomposition that produced no subtasks reported "verified
  clean" — the checks had simply had nothing to fail on — in exactly the case where the model
  provider was unreachable or unauthenticated. It now says that nothing was built.
- **The CLI prints on a Windows console.** This product's own vocabulary (`verifier ≠ executor`)
  could not be encoded in the default code page, and printing it killed the command mid-output; and
  a diagnostic reading a child process's output decoded it with that same code page, so `gfso
  doctor` could crash inside the one command whose job is to work when nothing else does.
- **An upgrade takes effect.** The agent door asked only whether the address was open, so after
  `pip install -U gfso` every session went on driving the process from before the upgrade, with
  nothing said. It now reconciles what is served against what is installed, exactly as `gfso up`
  does — and the server it reconciles is a background service that outlives the session rather than
  exiting twelve seconds after the last one closes, which used to take the open UI with it.
- **The UI says when it has lost the server.** Its only reaction to a closed socket was a silent
  retry, so a stopped server looked exactly like a quiet one: the last graph stayed on screen with
  no indication that nothing behind it was live.
- **`gfso serve` is a whole server.** Typed by hand it mounted no agent door and resolved its
  database against the caller's directory, so it held the one address while every agent session got
  a 404, and it seeded a demo graph into an empty database where the user's work should have been.
  The door is on by default, the database follows the installation, and seeding is opt-in.
- **Stored state carries a schema version.** A database written by a newer gfso is refused by name
  instead of failing as a `KeyError` behind a blank page. The refusal knows one value it must not
  read that way: databases converted by the v4.0 rename tooling carry its "already migrated" mark in
  the same field, written before the field meant a schema version, and are opened and normalised
  rather than turned away as newer than the build that made them.
- **`TIMEOUT` cannot be sent by an agent.** It is the system's finiteness trigger, not one of the
  twelve signals (§14.2), and the tool surface took it like any other: sent on a node awaiting
  validation it settled that node as done-by-timeout, around the AND law, around the independent
  verdict the seam requires, and around the rule that a rejection names its criteria. The tool door
  now admits the twelve signals by name, and the engine refuses a system trigger that carries a
  sender.
- **A decomposition's own graph is checked for cycles.** The acyclicity check walked the dependency
  edges and reported them as the check on `D` — so the rule the canon states about the decomposition
  graph (§10, §13.4) was verified nowhere, and a node could be created as its own parent. Both halves
  are now decided where each is visible: the split's shape when its checks run, and the ancestor
  chain when the edge that would close a cycle is created.
- **Leaf delegation is checked over leaves.** CHECK-6 asked every child for an executor where the
  canon asks it of leaves (§13.4) — a node that decomposes further is accountable through its own
  children — and never checked the one node the canon names when that node had no parent to check it.
- **An unreadable executor report is retried once, then parked out loud.** No signal may be forged
  from a report that does not parse, so the node stays where it is — and the dispatcher's spent key
  meant it was never picked up again: one leaf of a delegated run sat waiting for the rest of the run
  on a single unreadable report, in a graph that looked merely busy. It now gets one retry, and if
  the second report is unreadable too the node is parked with a line saying so and naming what it
  needs (its issuer), instead of silently.
- **The project picker shows what you are working on.** Projects are listed by when each was last
  worked in, newest first, and the picker shows the recent ones rather than every database ever
  created — an installation with a history offered 271 alphabetical entries with the live project
  69th. Nothing is deleted for it: `?project=<name>` opens any of them, and those files are the
  record of finished work.
- **One node, one dispatch.** Two defects met in the delegated path: the dedup claim was a bare
  check-then-add over a set while `dispatch_once` runs from two places by design (the poll loop and
  the transition wake), and the mechanism that made a REVISED node fresh work marked *every* ASSIGN —
  creation included — so a node's claim could be dropped moments after it was made. Together they
  executed one contract twice: two paid agent runs writing the same files. The node's generation
  (iteration, reopens, revisions) now rides in the key, so a revision is a new round with nothing to
  un-remember, and the claim itself is atomic.
- **A roster edited on disk takes effect.** The registry promised a file "editable by hand" and read
  it once, at server start: a rewritten roster was invisible, so agents kept working in the directory
  a previous run had named — the graph looked healthy while the verdicts judged the wrong tree.
- **What a graph COST is now a question the system can answer.** The numbers existed per model
  call, inside whichever verb happened to run, were summarised into a progress line as text and then
  dropped — so nothing could say what a decomposition, a review or a delivery had cost, and anything
  that needed the answer had to reconstruct it from its own side of the wire. Every internal call is
  recorded with the ROLE that made it (decomposer / Level-2 review / validator / executor) and served
  at `/api/usage`, totals and per-role split, with `costed_calls` beside the money so a transport
  that reports no price can never read as free. The UI shows it in the observation window, where the
  model runs already are — not beside the quality metrics, which describe the graph itself and read
  the same for a graph worked entirely by people.
- **An executor's step budget is declared with its role.** `register_agent(..., max_turns=N)` rides
  into the delegated run, so an executor the engine spawns can be given the same envelope as one
  driven from outside; without it two runs of "the same agent" differed in a way nothing recorded.
- **A reconcile that did not stop the server no longer reports a restart.** It returns what actually
  happened — the drift stands, the server was left alone — instead of telling the caller it is now
  talking to current code.
- **A verdict is stamped with the delivery it read.** The record of an independent validation took
  its generation when it was written, not when the run began, so a validator finishing after the node
  had moved on — reworked, reopened, or revised under it — recorded a verdict that read as current and
  satisfied the gate that requires an independent one. The generation is captured at the start of the
  run and now also counts revisions, which neither of the other two counters does.
- **A contract can be revised while its delivery waits.** The canon admits it (§14.3) and prices it
  (§6.3): the node returns for fresh consent and re-delivery. It was refused outright; it is admitted
  now, and the price is charged — a recorded pass for the superseded delivery is voided, so nothing
  completes on a verdict about a contract that no longer stands.
- **The UI reads the check-to-failure-mode routing from the product** instead of a copy in the page,
  which had drifted: a delegation hole was shown as a correspondence defect where the canon routes it
  to feedback (§13.4), and the checks added since were unknown to it. The Level-2 panel also no
  longer offers the risk register as a way to close a causal finding — the register holds risk events
  (§13.1), and an uncovered entailment written into it forbids nothing.
- **Entering a graph hands back its local link.** `use_project`, `create_task` and `auto_decompose`
  return the UI address for the project just acted on; it used to live only in the agent's
  instructions, so whether a human was ever offered a link depended on the model recalling one.
- **One address, computed once.** The server's port was written literally in the CLI defaults and in
  the browser-origin allowance; both now read the single address the rest of the tooling reconciles.
- **An unreadable agent registry, and a dispatcher that fails to start, both say so.** Silent, each
  left every delegated node waiting forever with no line anywhere — the shape that reads as an
  executor doing nothing. A dispatch that raises now reaches the observation panel too, since a node
  whose dispatch failed is never retried.
- **An agent role is registered with the directory it works in.** `register_agent` refuses an
  executor or a validator with no `workdir`, and the transport refuses to spawn an agent without
  one: otherwise both ran where the SERVER stands — the state home — and judged or wrote work that
  is not there. The two failures were silent in different ways: the executor's node was never
  dispatched again, and the validator's node sat in `VALIDATING` with the cause discarded.
- **The server is loopback-only.** It has no authentication and its tool surface can spawn a model
  with shell access in a caller-named directory; with wildcard CORS, any page open in the user's
  browser could drive that chain.
- **No tool call can freeze the server.** Every MCP tool runs in a worker thread: the SDK awaits a
  synchronous tool inline on the event loop, so the Level-2 review — the verb an agent is told to
  run first — stalled the UI, the API and every other session for as long as its model call took.
- **Validating every internal node is a measurement setting, and ships off.** The guarantee sits at
  the delegation seams (§14.5); with the dial on, every node inside one scope got its own
  minutes-long validator, which is the opposite of what the protocol tells the agent to do.
- **Examples do not run when imported**, so walking the package tree no longer spends the reader's
  model tokens, and the shipped `app` object no longer writes a demo graph when it is imported.
- **The validator runs where the work is.** Giving each validation a fresh scratch directory — so
  that one run cannot judge another's leftovers — had made that scratch the validator's working
  directory, and it opened in an empty one: it could not see the delivery and failed correct work,
  citing the empty directory as its evidence. A false `FAIL` at the seam is worse than no
  validation. The scratch is still per-validation and is now offered by name, for copies.
- **`gfso run` goes through the running server.** It opened the database directly, always — a
  second engine over the file the server holds, and therefore a second sequencer over a log whose
  guarantees assume one (Inv-7; §14.3 wants the consumption check and the edge it authorizes in a
  single log-serialized step). With no server up the direct path is still what runs, and is the only
  one there is. `project=<name>` now selects the graph from the shell.
- **A `unittest-checker` is registered with its oracle map.** Without one it could never return a
  verdict, and as the first registered validator it silently disabled any `llm-validator`
  registered after it.

### Removed

- `gfso serve --api-key`, which set a variable nothing read; billing rides `GFSO_BILLING` and the
  ambient `ANTHROPIC_API_KEY`, as documented in `gfso/runtime.py`.
- The shipped default pointing the hidden-test validator at one experiment's oracle map. A
  registration that names no map now says so instead of silently finding nothing.

[0.1.0]: https://github.com/Kirill-Shokhin/GFSO/releases/tag/v0.1.0
