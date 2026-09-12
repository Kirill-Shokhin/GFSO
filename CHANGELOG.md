# Changelog

Notable changes to the reference implementation. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The **canon** (`docs/applied_gfso_v4_en.md`) is versioned separately from this package and carries
its own Changelog section; where a release re-anchors the code to a canon version, that is stated
below. Nothing in this file states a measured effect of using GFSO on real work: the experiment that
would establish one (E3) is open, and what has been run so far is a calibration tier with its own
stated boundaries — `docs/EVIDENCE_LOG.md` §13, and §3/§9/§11 for the earlier ones.

## [Unreleased]

### Fixed

- **The two answers everything else is guarded by could be starved out.** The server's verb routes
  are synchronous and some of them run for minutes, so the liveness reads — the session lease and
  the runtime switches — queued behind them on the same worker threads: measured, three-second
  client timeouts against a fourteen-second answer, while a lease expires in twelve. Three things
  unlock at once when it lapses: the shutdown endpoint stops refusing, so the server can be stopped
  with work in flight; the dispatcher stops spawning for the roles whose owner it thinks is gone;
  and a new session reads the slow answer as "something else is on this port" and gets no tools at
  all. Both handlers now answer on the event loop, where a busy pool cannot delay them.
- **The roster was written in place, so a reader could see half of it — and a kill could freeze it
  that way.** Registrations are a json file that readers re-read on every access and hold no lock
  on; a plain rewrite leaves it empty for the length of the write (measured: 31% of concurrent
  reads). A process killed in that window — and the shutdown path exits a third of a second after
  the request — left the file truncated permanently, after which every node reports that its
  executor is not registered and the run stalls with nothing to point at. It is now written beside
  and moved over, and where the move itself is refused the registration fails out loud rather than
  quietly.
- **A validation severed mid-flight was recognised by a race.** A contract with more criteria than
  the batch size is judged in concurrent batches that report in completion order, and the question
  "was this call cut?" was asked of whichever answered last. Read as a cut, the call is redialled
  for free; read as an answer that did not parse, it spends the node's one retry and the next one
  parks the node with no verdict ever coming. The question is now asked of the whole judgement.
- **A verdict decided differently depending on the case of a letter.** The word a validator
  returns travels as a string and was compared with `== PASS`, so `"pass"` matched neither arm:
  every integrity check fell through as a no-op, the string was stored as it arrived, and nothing
  downstream recognised it — the parent's AND never closed, no signal was ever sent, and the node
  waited in VALIDATING for ever with a verdict on its own record. Per criterion the same field had
  five readers and one of them lowered the case, so `"pass"` skipped the check that a criterion's
  probe was actually run — recording a pass over a probe nobody executed — while `"FAIL"` was
  refused for carrying no reproducible probe, throwing a genuine refutation away and sending the
  work back looking accepted. The schemas declare the enumeration and the reply parser does not
  read it, so this is an ordinary answer from a model, not a malformed one. The word is now coerced
  to the enumeration where every door lands, or refused; the per-criterion field has one reader.
- **A run could wait for something that had already settled, for ever.** A delivered parent one of
  whose children is ESCALATED or ABANDONED can never satisfy the AND over its children (Thm 1), so
  no verdict will arrive — and the frontier answered that with an ordinary wait: `stuck: false`,
  "the graph is working, poll again in a minute". A driver polling that loops until it is stopped
  by hand. The wait is now reported as what it is, with the move that exists named (FAIL the
  delivered node and re-decompose, or REOPEN the settled child while it has reopens left).
- **Three ways for a round to end with nothing signalled, and only one of them was handled.** An
  unreadable executor report got one retry and then an honest park; an exception anywhere in the
  spawn, and a report whose `status` is a word the contract does not define, got neither — the node
  stayed in EXECUTING with its round already spent, so the dispatcher never picked it up again
  while the frontier went on advertising the step. The second of those is reachable from a
  perfectly well-formed answer: an executor reporting that it could not do the work. All three now
  answer to one rule.
- **A delegated executor was started with nowhere to work.** The roster is a json file the
  registry invites people to edit by hand and re-reads on every access, so an entry can reach it
  without passing the registration check, and a directory that existed when a role was registered
  can be gone by the time its node is picked up. Neither was asked: the transport raised into a
  handler that only logged, no signal was sent, and the node was never retried — the run stopped
  with nothing said about why. The question is now asked where the answer still costs nothing, one
  step before ACCEPT fixes the obligation, so the node is genuinely left in OFFERED and its round
  is freed: putting the directory back is enough for the next pass to dispatch it. The place is
  named in the refusal.
- **A role could be registered against a directory that is not there.** The roster refused an
  *empty* `workdir` and read any non-empty string as an answer, so a path naming nothing
  registered cleanly — and a role registered against a place that does not exist is spawned into
  nothing: the executor dies in the transport, and a validator opens an empty tree and FAILs
  correct work over every criterion. The spelling that actually occurs is a POSIX path on
  Windows (`/c/Users/...`), which resolves against the *current drive root* rather than the C:
  drive, so the roster looks right while pointing somewhere else, and whatever runs there writes
  outside the project. The check sits on the registry itself, where both doors pass, and the
  refusal names the path and, when it points somewhere else, where that is. Validator selection
  matches workspaces the same way, so a validator registered under one spelling of a directory is
  still the validator for work registered under another. One exemption, stated because it is a real
  hole and not a detail: a path on a network share is NOT checked, at registration or at dispatch.
  Asking costs seven to twenty-one seconds against a host that does not answer, on a thread holding
  one of the dispatcher's slots, so a slow file server would stall the graph and a momentary outage
  would read as "this role has nowhere to work". Such a workdir is taken as given; it fails where
  it always failed, in the transport.
- **The affordance surface named signals a standing rule would refuse — in three more places.**
  `available_actions` answers "what can be done with this node from where you stand", and the list
  is documented as what would actually be ACCEPTED. It offered PASS on a parent whose children have
  not passed, which Thm 1 (§11.1) forbids outright; it offered PASS on a delivered seam with no
  verdict on the record to anyone on the validator roster, an exemption for *who signs* that the
  engine has never had; and it offered PASS on a node whose own decomposition had since gone red
  (§13.4). The two rules that do not depend on the asker are now asked of the engine
  (`pass_blocked_by`), beside the one the plan gate already had, so the two surfaces that used to
  re-derive them no longer can. Stated exactly: the enforcer is still the validation layer, and
  `pass_blocked_by` is a second spelling that agrees with it — the count of hand-written copies went
  from three to two, not to one. Collapsing the last two needs the owner to live on the graph rather
  than the engine, which the validation layer is the one caller that cannot reach.
- **Every asker was the ISSUER of a root.** The role filter granted the issuer role to anyone at all
  on a node with no parent, while the engine resolves a root's issuer to its own assignee and
  refuses everybody else — so a stranger was shown FAIL and CANCEL, and told in as many words that
  FAIL was open, on a node the engine would not move for them.
- **A refusal's KIND changed on the round trip.** The engine distinguishes three: the state does not
  admit this signal, the transition's own guard said no, and a rule above the machine refused it.
  The classifier read the kind off *whether an error sentence existed*, so a guard refusal coming
  back through the door was relabelled as a rule refusal — the identical refusal answered `guard`
  computed directly and `rule` through `signal`. A refusal for a task that does not exist also came
  back with an empty reason; it now says so, and says to check the project.
- **ASSIGN on a live node had no door.** A re-ASSIGN is a revision and carries a contract, which the
  `signal` verb has no field for — so the signal was listed as available in every reassignable state
  and guard-refused in all of them. It stays listed, because it is genuinely admissible, and the
  surface now names `revise` (and `reassign` for a Del change) as what performs it.
- **An executor that reported it could not do the work had its node moved on as a delivery.** The
  executor's report declares its `status` with an enumeration of three — delivered, blocked,
  challenge — and the reply parser validates the presence of keys, never their types or their
  enumerations, so the declaration was a comment. Six of the package's seven such declarations fail
  closed when a model answers outside them; this one failed open, because the dispatch read
  everything that was neither a challenge nor a block as a delivery. A node whose executor
  disclaimed its own work went to validation, where an independent validator is then paid to assess an
  artifact its author said does not exist. A word the contract does not define decides nothing: no
  signal is sent, the node stays where it is, and the issuer is told which word arrived.
- **An INTERNAL node closed DONE/PASS on a signature with no verdict of any kind behind it.** §14.5
  makes such a node self-verify and §11.2 makes ⊥ not a pass, and the engine held both — but only
  against the node's own executor, because the guard was written against the SIGNER rather than
  against the record. On an internal node the role rules admit one other party, a registered
  validator, and that party walked past it; the seam rule does not apply to an internal node, so
  nothing was left. A child delivered with nothing done reached DONE with `verdict record: None`,
  and its DONE is a conjunct of its parent's conjunction, so it did not stay put. The guard now asks
  for the record whoever signs — the rule the seam already carries: a roster id is a claim about who
  signs, the record is the evidence that validation happened. The affordance surface asks the same way:
  it had its own copy of the old condition and went on offering the PASS the engine had begun to
  refuse. Both legitimate paths are unchanged: a
  DELIVER carrying `self_validation`, and a validator that records before it signs.
- **A refinement round emptied the root's risk register, and that turned its own check green.** The
  contract a refine writes was built by hand and omitted `risk_components` — the fourth positional
  field of a Spec — so every refine defaulted it to none. CHECK-5 (STD-3) quantifies over exactly
  that tuple: a root with two uncovered components reads red before the refine and green after it,
  with nothing covered and no child added. The construction now has a name, so what the decomposer
  does not author is carried rather than dropped by omission.
- **On a node with no executor, the surface said there was no move and the engine moved it.** Both
  role rules are guarded as "if there is a holder and you are not them", so an unassigned node
  accepts issuer and executor signals from anybody; the affordance surface matched on neither half,
  then on one. A caller who is told they have no action gets no refusal to lead them back, which
  makes this the worse direction of the same defect.
- **When several gates applied to one node, the caller got whichever fired last.** The reason was a
  single slot each gate overwrote. All the reasons are now returned, with the ones that removed a
  signal first and the ones that only explain a signal still on offer after.
- **`gfso up` exited non-zero in silence.** Every branch of the reconciler composes a sentence — left
  alone because another session is connected, because work is in flight, because the server refused
  to stop, because reporting was asked for instead — and four of the five returned without it, so
  the exit code was the whole of what a caller could read. Every outcome now carries its reason in
  what it RETURNS, so a caller that is not a terminal can read it too, and every outcome is narrated
  exactly once — by the verb that makes the decision, the door owning only the exit code.

- **A PASS could be recorded, and a node closed, with no observation of any criterion.** Two guards
  were vacuous at once: the floor that asks for one observation per criterion computed its
  requirement over the criteria that are not dependency links, so a contract left holding only an
  engine-authored `dep__*` criterion asked for nothing; and the engine's report battery ran under
  `if per_criterion is not None`, which an empty observation set switched OFF rather than failed.
  A FAIL is unchanged — Inv-3 asks it for the failed set, not for a line per conjunct.
- **A child that reached DONE on the timeout locked its whole ancestry.** The canon makes auto_pass
  an acceptance (§12.2, §14.3), and the parent's conjunction was reading "DONE with a verdict
  somebody gave", so the child was terminal, consumed, and un-reopenable while the frontier reported
  the graph as working. Composition and readiness now read acceptance; the metrics still exclude
  auto_pass (§15.2), and every surface names the nodes a result stands on that nobody checked.
- **Two of the three surfaces answering "may the children start?" could say yes over ⊥.**
  `get_review` wrote `verified and not open_findings`, and an unreadable Level-2 verdict is `None`,
  which is falsy — so the reading doors admitted execution while the engine refused the child in the
  same second. One owner now, on the engine, where the refusal is decided.
- **CHECK-7 read a child bound's number and dropped its operator**, so two children bounded `<= 100`
  entailed a parent bounded `< 200` — a positive verdict on the Semantic level for an entailment
  that does not hold, in the exact arithmetic §13.4 annotates. CHECK-8 had the mirror defect and
  reported `x <= 5` with `x >= 5` as a contradiction.
- **A structured reply was matched by required keys, and the two patch schemas require none** —
  so any JSON object in the reply, including an echo of the schema itself, could be taken as the
  answer. In a refinement round that surfaced as "empty fold — converged" over a round that had
  answered nothing.
- **A validation call cut mid-flight was charged against the node's one retry** and escalated to a
  costlier tier, which repairs a thin report and not a severed pipe. The provider now reports a
  stream that ended without its result event, and a cut call gets its own small, finite budget.
- **The two doors sent a validator to different working directories** for the same node: the
  dispatcher asked the graph first, the manual verb asked the roster first. One owner; the graph
  answers first because where the work is is a fact about the graph, and the roster still answers
  when the graph cannot.
- **A revision could not move the deadline** — a packet field Inv-1 names, and §14.6 walks — leaving
  CANCEL, which cascades, as the only way to reschedule. `revise` now carries it; omitting it keeps
  the node's own.
- **Questions scoped to a subtree were answered by an id-prefix convention** rather than by the
  parent edges, so a graph whose nodes are not named `root.child` fell out of every scoped answer.
- Internal `claude -p` calls no longer inherit the operator's hooks, for the reason they already do
  not inherit the operator's MCP servers: a hook written for an interactive console injects its own
  instructions into an internal call, and on the Stop event can refuse the call's exit.

### Changed

- `docs/EVIDENCE_LOG.md` §13.10's bill figures now read: validation is **0.710** of a closed run's
  spend and the run costs **$10.40**. They were wrong, and in both directions before they were
  right: a run's model calls are recorded in two places, whether those two overlap depends on which
  regime spawned the executor, and neither file says so where they are read. §13.10 states that
  difference where the numbers stand. §13.8's own share figures are unchanged; its label is
  sharpened to say they cover validation of the delivery rather than all validation. The account of
  how the figures were arrived at is process and lives outside the public record.

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
