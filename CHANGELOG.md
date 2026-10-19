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

## [0.2.0] — 2026-10-15

### Added

- **`auto_decompose(spec=…)` builds a plan already authored.** A plan read off one graph (`extract_spec`)
  builds into another as it stands — the same builder, with no search and no authoring call — so one plan
  can be executed twice, under two modes, and the executions compared with the plan's own price in neither.
- **The user-agent dispatches the nodes it holds.** `set_mode(..., perform="dispatch")`, the default in solo and
  semi: the user-agent consents to each node it holds and stays its executor, and the system performs the node in a
  clean session of the project's registered executor, started only after that consent, in the node's own place, with
  every signal in the holder's name; `next_steps` tells it to wait rather than build. `perform="in_chat"` keeps the
  user-agent doing the work in its own chat. Solo with dispatch needs one registered executor of the project.

- **`unregister_agent`** takes a role off the server-wide delegation roster, on every door the roster
  verbs are on. Until now roles could be added and never removed.
  - With `workdir`, the role goes only while it still points at that directory.
  - Without it, a role another project registered is refused.
  - The answer names the live nodes the role carried or issued.

### Changed

- **A rework order shows what the next PASS runs.** The reason an executor is given for a FAIL that still stands no
  longer includes a run of a pinned probe its contract's revision withdrew, a finding its issuer retired, or one that
  cannot run over the inputs the validation lays down (the node's own and its parts'), nor an observation made only
  through such probes; the issuer reads such a criterion as not demanded. Shown as an order, such a probe was disputed
  until the node was closed by its answer count. A machine issuer's acceptance that installs no change and retires
  nothing is refused with the reason, a finding may be named by its hash where no other standing finding shares it,
  and a child a repair adds carries the corpus its node or split pinned under the same criterion and probe command;
  the probes the next PASS no longer runs are named to the executor as settled.
- **A criterion whose every pinned probe is a literal `echo`, `printf` or `true` is not admitted.** Such a procedure
  cannot come out false, so the criterion forbids nothing; the contract is refused where a contract is installed, with
  the commands named. A constant beside a probe that runs the work is still only noted. A plan's author had pinned
  `echo` lines as the whole procedure of every criterion of a root.
- **A goal's first plan, written by the system, is written from the work's place.** Before it, a read-only run in the place where the
  work will be done names the files that define it — the statement, the interface, the stubs and build files — and
  their text enters the goal's contract verbatim, `Makefile`-like names included. Given a customer's summary that named
  no file, the plan's author had never seen the program's name, input or output.
- **What writing a plan spends is recorded on every path.** A build that raised took its calls with it, and a row's
  ledger showed no plan while its author and auditors had spent $0.56.
- **A model subprocess has room for a long reply.** `CLAUDE_CODE_MAX_OUTPUT_TOKENS` defaults to 64,000 in the
  environment of every model run; the client's default cut a plan of fourteen parts, and only its re-emission was kept.
- **A dispute naming a probe by its hash disputes it wherever it stands.** A finding's hash is its probe's command, so
  a hash written bare, or after a criterion spelled otherwise, names every standing finding that carries it; a full id
  still names only itself. A machine issuer's ruling lands the findings the dispute named and leaves the rest demanded,
  instead of being refused whole. One probe refuted under two criteria was disputed by its hash, every ruling on it was
  refused, and the node was closed by its answer count.
- **A structured reply that wrote a top-level field inside its last entry is read.** Where a field the schema keeps
  only at the top appears deeper, the containers left open are closed before the comma that precedes it; a reply cut
  short or broken any other way is still unread, and what is read is still held to the schema. A validator batch
  closing its last probe list and going straight on to the report's own fields was run again whole.
- **An empty entry about a non-criterion no longer voids a validation report.** A `pass` entry with no probe,
  behaviour or divergence under a name that is not a criterion observes nothing and is no conjunct of the verdict; an
  entry under such a name that carries any of them is still refused as answering another contract.
- **An unreadable batch is run again alone.** A validation cut into batches runs a batch whose report does not parse
  once more inside the same validation, instead of the whole validation running again — a root of seven batches was
  validated fifteen times in an hour, each time one or two batches' JSON short of a bracket. The run again works in a
  fresh scratch place of its own.
- **A report on a revised contract is not applied.** An executor session that began on one version of its node's
  contract signals nothing when the contract was revised while it worked — no ACCEPT is sent for the executor and no
  delivery answers a version its session never saw; the node waits under the new version. What that session wrote is
  committed in the node's place as work under a superseded version, never inside a later delivery, and a node gets no
  second session while one is still running in its place.
- **A part's pinned check is observed once for every criterion that rests on it.** A whole's validation still runs
  each done part's pinned probes over the whole's delivery; cited as holding under any one of the criteria resting on
  the part (and failing under none), the observation serves all of them, and the validator's packet writes each such
  probe out once and names it under the others. Reports that had run and cited every part probe once were refused for
  not repeating it under each criterion.
- **A validation the system has taken on is in flight from that moment.** Waiting for a slot behind other sessions,
  it reads as the system's wait on every surface; it was offered to the node's holder as a move of its own.

- **Entering a project answers with the move its graph waits on.** `use_project` returns the project's mode and the
  next move, read the way every signal's reply reads it (`next`, with the same ownership filter). On an empty
  project with no mode set, the move is to ask the user for the mode before any plan; on a finished project, it says
  the graph is finished and that a new goal is a new root, rather than "Execution finished".
- **An executor writes only in the place it is given.** Every executor packet, for a node or a scope, ends with the
  system's place: write here and below, read any other directory the contract names, never write there. In a node's
  own checkout a path the contract names under the base is the same path here, and what the base holds beyond the
  commit the place was cut from is read in the base; the validator's and the machine issuer's packets carry the same
  reading of the base's paths.
- **A machine issuer answers from contact.** A dispute, an escalation, a block or a parked node is answered in the
  node's own workspace, as its validator works there: the node's pinned inputs laid down, its checks runnable, a
  shell. A dispute it rejects without having run anything is not taken and is asked again; a run cut before it
  answered is no answer; a check it writes anew keeps the files the old one was pinned with. Where no such place
  exists — no directory, or a provider without agent runs — it is asked as before.
- **A covering part closed before its whole failed leaves the whole's split refuted,** so the failure opens a repair
  of the split instead of sending the whole's executor to do the closed part's work inside the aggregate.
- **A validator that returned no verdict twice is asked again in 30 s, not 10 min** (10 min where no model ran), one
  rule for a node and for a scope.
- **A validator's report is judged whole, every part of it.** A report over several nodes, and each batch of one
  node's long contract, is a verdict only where its word is PASS or FAIL and agrees with its own entries; a node's
  verdict is the conjunction of its batches' decided words, in any order. A report whose word decided nothing used to
  be recorded as PASS on one path and refused on the other; a retry after a refused report now reads what it saw
  over the entries it kept, so a kept "pass" no longer hides a fresh "fail".
- **Which criteria a child covers belongs to its parent's split (§2.4).** Mapping, re-mapping or rebuilding coverage
  re-admits the split and revises no child — a child in work keeps its work, a delivered or passed one its delivery
  and verdict. What reads "the coverage changed" — reopening a settled child, a parent's re-delivery after a FAIL over
  passing children — reads the logged admissions.
- **Every new version of a contract resets its rework budget (§12.15),** one that changes no field included.
- **q_Dep and q_D count what the log recorded, whatever the node became later (§15.4):** a declared dependency of a
  cancelled consumer stays counted, and a whole that passed stays in q_D after a reopen. A dependency a later version
  drops stays declared; a dependency record keeps whether its pair was declared before the block that first named it,
  and a refuted one is kept and marked rather than erased, so a pair a block named first is never counted declared
  and a repeated block reopens it (§15.5). Dropping a discovered dependency closes its record instead of erasing it.
- **A system-held node's decomposer can challenge its own contract (§11.5).** A defect the plan gate holds that no
  split can repair — the node's criteria jointly unsatisfiable, one no procedure decides, a requirement of its goal no
  criterion writes — goes to the contract's issuer as a CHALLENGE. A rejected one is shown to the next plan turn and
  spends the plan's budget.
- **A criterion's verdict word has one reading.** `failed` reads as `fail` everywhere (a word read as a fail costs at
  most a round; read as a pass it could close a node, so `passed` is not a pass); a criterion a report speaks twice
  passes only if every entry says pass.
- **The server's build fingerprint is the same on every platform** for the same source bytes (files were ordered
  case-insensitively on Windows and byte-wise on Linux).
- **The HTTP door answers in the shape every door does.** `/api/holes` → `{holes, count}`; `/api/usage?detail=true`
  keeps `calls` a count, the rows in `calls_detail`; `/api/tasks/{id}/actions` → the `available_actions` answer
  (names and the reasons a move is missing); `/api/metrics` adds `q_T_from`/`q_V_from`; `/api/graph` nodes carry
  `name` (was `label`), dependency edges `discovered`; a node read carries the same fields as `get_task`
  (`criteria[].depends_on` was missing over HTTP; the deprecated `accepted_risks_detail` alias is gone).
- **The core distribution is checked by what it ships:** its closure test reads every import, relative ones and
  `from gfso import x` included, against the modules the wheel contains, and drives the protocol with no site, so
  a module left out of the wheel is no longer served from the repository.

- **Deadline coherence follows v4.1 §11.5 and §12.10.** A crossing along a dependency, and a child's deadline not
  inside a live parent's, are refused only by the admission that sets those deadlines, where a choice of them can
  order the edge; met afterwards — a revision, a re-issue, a dependency declared later — a crossing is CHECK-3's flag
  for the consumer's issuer and refuses nothing. An edge with a settled end is not read. A deadline already passed is
  refused at every door that installs a version, and the system's own re-issue writes its deadline inside the
  parent's.
- **q_T counts a challenge no rejection refuted (§15.4, v4.1),** read off the log; the system's issuer types the cause
  of every revision it makes, so its re-issues are not counted as capability mismatches. An accepted dispute keeps
  the rework bound in force.
- **A part that passes before its whole has begun joins the whole's place, not the user's base;** the base changes only
  by the root's join, and the graph says complete only once the root's result has landed there.
- **A split's ACCEPTED_RISKS register carries what STD-1 asks of every entry, and the split's own denial
  (§9.2, §9.5).** Each entry has its estimate — `p` in (0, 1] and `impact` — with its justification and
  invalidation condition, and may name the STD-3 component it accepts as a group, which meets CHECK-5 as a
  risk node does. Every split also states the odds of its own refutation at contact, `{denial: true, p,
  justification}`, from the recorded rate of comparable splits or the decomposer's estimate; CHECK-4 gates
  admission on all of it, and `auto_decompose` is asked for the denial with the plan.
- **A terminal's consumption is read off the log and, once logged, stands (§12.14).** A child its parent
  delivered over stays final through the parent's later FAIL; a re-admission that covers around a settled
  child, or a parent version that maps it to nothing, consumes it too; a sibling covering the same criterion
  from the first admission does not. Recovery past consumption is the issuer's re-decomposition.
- **A node an executor runs works in a place of its own when the project is a git repository.** The
  executors registered on one directory shared its live tree while the dispatcher ran them in parallel,
  so a validator's build could read a sibling's half-edited file: a false FAIL, or a PASS over a tree that
  was not the node's delivery. Where the registered directory is a repository's top, each node's session
  (or a scope's one session) runs in its own worktree, made from where its parent works and reused on
  rework; its delivery is a commit; its validation runs there; and a part that PASSes is merged
  `--no-ff` into its parent's place. A conflicting merge is aborted and the branch left unmerged, named
  in the parent's packet as the whole's integration work. At the root's PASS the joined worktrees are
  removed and the rest named. A directory that is not a repository behaves as before, said once.
- **A scope one executor session carries is run by one session and validated by one validation.** Where a
  registered executor holds a split whose whole was judged to fit one of its sessions, the dispatcher
  spawns nothing per piece: the scope's top gets ONE session, handed every open node in build order (parts
  before the whole, producers before consumers) with each node's criteria and rework feedback, and its one
  report is signalled node by node — consent top-down at the start, deliveries parts first at the end,
  with no piece self-settled. Then ONE validator run (batched across nodes as one node's contract is)
  validates every delivered node against its own criteria, pinned probes and regression lines; each
  node's own verdict is recorded through the same record every node's goes through, and the verdicts are
  signed parts first. A failing part fails every whole above it on the criteria mapped to it (a whole is not
  attained while a part fails), and the whole's rework says it failed through that part, not by its own
  check; it is re-delivered once its parts have passed, so a part's rework rounds after the first do not
  spend the whole's budget. A block the session reports on a
  node of its own scope is not signalled — that node is the session's own work; a scope whose split contact
  refuted gets no session until its repair; delivered nodes are validated without waiting for siblings that
  cannot be delivered now (a dispute, a block); a recorded verdict stands for a signature only while
  nothing it is built from — a part below it, a producer it reads — has been delivered again or failed since,
  and a consumer beside a failing producer waits for the producer's fix; a producer inside the scope no longer makes its consumer wait
  for a verdict, and the session is capped by the earliest deadline it holds. Nodes nobody judged, SOLO, and
  SEMI's held boundary keep their own sessions and seams.

- **A childless node judged larger than one session is split, not delivered as a leaf.** Above κ a node is
  not a leaf (§3.4) and its split is owed (§14.3): its executor's DELIVER is refused naming that, the lift
  being his own split (`auto_decompose` or `decompose` on the node); the issuer's PASS is refused on it only
  where the issuer is the executor. No executor session is spawned on such a node while someone will split
  it: where the system makes its executor's moves (AUTO) the split is made for it — the refine round on the
  node — and where its issuer is a person or the holder, his next step names the split.

- **An independent validation stands where one executor session's capacity ends — not on every piece.**
  The plan's author writes, in the same call, each piece's volume (the obvious count of what it writes and
  checks) and whether one session of the named executor builds and checks it; the node as a whole gets the
  same question. A split whose whole one session carries is that executor's own work: under a mode where
  the system holds it, its pieces keep the parent's executor, and they are validated once, at the scope's
  top, rather than each with a wait of its own. Past one session the pieces are seams as before, and in
  SOLO the top of every such scope is validated, not only the root. Nodes nobody judged keep today's seams.
  The executor's model is an input of the judgement, so the seams move with the model. Observing every
  delivery (`GFSO_VALIDATE_INTERNAL`) is now off by default and on for measurement: it made a task a bare
  agent does in under three minutes take 39 to 70, and what SOLO lacked was a validation at each scope
  beyond one session, not one per piece.

- **An observed divergence binds the signature where the node's issuer is its executor; at a seam the
  latest appointed record stands.** Where the issuer is the executor — an internal node, a self-issued
  root — the holder still cannot sign past the system's check: the refused party has lifts of his own
  (repair and re-deliver, or revise his own procedure). At a seam binding would leave the issuer none,
  since a revision needs the executor's re-consent (§14.4 (ii)); there the issuer's own observation
  (`record_verdict`) stands past it, and the earlier divergence stays on the node's ledger as a logged
  disagreement (§14.1). Only his, and only by hand: another run of the instrument, even one recorded under his
  name, does not undo a refutation.
- **A pinned probe the issuer withdrew leaves the node's regression set.** A pinned probe's run enters
  the set like any refutation; when the issuer takes the probe out — an accepted challenge that the probe
  was wrong, or a re-ASSIGN — its runs no longer have to be re-run to pass. That holds where the issuer is
  the node's executor too: a refutation by a probe the version in force no longer carries is not a
  standing verdict under the current criteria, and revising his own procedure was his named lift, which
  lifted nothing while the run stayed. The move is not silent — `claim_drift` and the closure record name
  a criterion whose procedure changed after it was refuted; at a self-issued root that record is the
  whole safeguard. Kept, the withdrawn command also failed
  the node on every later round and the accepted challenge came back in a loop. The validator's own
  findings stay.
- **A regression probe is shown runnable, and matched however it is re-run.** A probe the validator found
  that once refuted a node must be re-run before that criterion passes; a pinned probe's run is not one of
  them — the pinned probe is demanded every round as itself, and its run under a second id was a demand no
  report could meet. It was shown to the next validator as stored: a
  multi-line program collapsed onto one line, over a probe-inputs directory that is laid down fresh every
  round — a command that could not run as shown, so the validator ran its own version, nothing matched, and
  one pass was refused three times. The command is now stored as run, with the round's inputs directories
  named rather than spelled, shown over this round's directories, and matched by its id or by the command
  the validator ran over them. The executor's rework packet shows each refuting probe as it was run. A
  finding over the inputs of a probe the contract no longer pins is shown, not demanded.
- **A criterion's withdrawn pinned probe takes only that criterion's findings with it.** Another
  criterion's finding by the same command stays in the regression set.
- **Two probes of one criterion on one command are refused at admission.** A probe is named by its
  command, so the second was laid down over the first and never run while the record said it was. The
  plan's authoring asks for such a pair to be repaired before the build; a pair still standing after the
  repair rounds ends the call with the refusal that names it.
- **The plan's author holds criteria to the goal's own quantifier and does not pose checks as work.**
  A criterion is never narrower than the goal's clause: an input the goal describes, at any size the
  environment holds, is decided in a criterion with probes at that range's boundary — never moved into
  ACCEPTED_RISKS, which holds only events the goal does not describe. A subtask whose only work is to re-run
  its siblings' checks is ballast (a checking artifact the goal names is still work); a criterion over two
  independent subtasks' joint behaviour goes to the parent rather than ordering them; a probe program is
  pinned as an input file of its own instead of being inlined in quoted shell. Measured on json_parser: a
  plan that filed deep invalid nesting as an accepted risk, against a contract that asks for ValueError on
  any invalid input, carried the defect through both modes' closed trees.
- **The log carries the contract a dispute installs.** An accepted CHALLENGE puts a new version of the
  contract in force, and until now only an ASSIGN's version was written to the log: what a dispute
  replaced could not be read back, and the readers of "the version in force at a delivery" went on
  reading the one before it. `claim_drift` now counts an accepted challenge as a version, with the
  challenge's reason on it, so its `narrowed` and `reworded_after_refutation` read differently on
  logs written before and after this change.
- **The validator's retry no longer escalates to a larger model by default.** A report that came back
  without a verdict is retried on the node's own tier; `GFSO_VALIDATOR_RETRY_MODEL` names a tier for an
  installation that wants the escalation. The escalation also stuck: once a node refused one report, every
  later delivery of it was validated on the larger model — 13 of 19 validations on a small automatic run.
  It priced over the cause of the refusal rather than removing it, and the doors no longer advise it.

- **Every delivery is observed, whoever holds the node; the issuer decides.** The instrument now observes every
  delivery by default, internal nodes included (`GFSO_VALIDATE_INTERNAL=0` narrows it to the seams) — §14.5
  decides who signs an internal node, not whether anyone looks at it. SOLO used to observe nothing below its
  root: the protocol text called a validator on an internal node "pure overhead" and an internal node closed
  on its executor's own self-check. Now every mode needs a validator (`set_mode` says so); under a mode a PASS
  stands on an APPOINTED observer's record of that delivery — the instrument, or the node's issuer where he
  is not its executor — never on the executor's self-check or a hand record by anyone else, and the refusal is
  lifted by the issuer's own move, `validate_result`. Under SOLO and SEMI, where the user's agent is a node's
  issuer, the instrument observes and records and the agent signs; under AUTO the system signs. A divergence
  an appointed observer recorded is that criterion's value: no later record turns it into a pass (Inv-2) —
  a hand PASS no longer overrules an instrument's FAIL — and every record of a delivery is kept, so a later
  record cannot launder an earlier refutation away. Where the observer's own pinned probe is wrong, a revision
  of the criterion's procedure is admitted through the same plan re-check an edited criterion gets. With no
  mode set, a project with a validator registered is now observed at every node too; its seams keep the older
  rule (a current PASS on the record).

- **Modes: the user chooses who holds the work.** `set_mode(solo | semi | auto)` on every door records the
  choice on the project (numbered and stamped). SOLO: the user's agent holds every node. SEMI: it holds
  the top of the tree (by default the root; `boundary=k` holds depths 0…k−1) and registered executors of
  the project hold the rest. AUTO: the system holds every node, the root included, and the user's agent
  is the goal's customer — the root's issuer — who states the goal and reads its status. Under a mode a
  node's Del comes from the mode at issue (each system node's executor differs from its parent's, so
  every one is a seam), and the doors refuse any move the mode gave to the system, whatever name the
  call is signed with. With no mode set nothing changes. The mode is chosen before the plan, so
  `set_mode` on a name the server does not have yet creates that project, on the HTTP and CLI doors as
  `use_project` does on MCP.
- **The root's issuer is the goal's issuer.** A root created under a mode records who created it;
  `issuer_of(root)` answers that party, so a root handed to a system executor is not its own issuer.
- **The machine issuer** (`gfso.issuer`): where the issuer of a node is a machine, the system makes the
  issuer's moves — the plan gate's findings, disputes, escalations, a refuted decomposition, a parked
  executor, an external block — from one context assembled from the graph (the goal, why the node
  exists, its contract, what happened to it, the open question), and only by moves the protocol gives
  the issuer in that state, checked before anything is signalled. Under AUTO the root's criteria are
  append-only for the system; every loop it can enter is bounded, and a node it cannot bring to a
  verdict is closed by its issuer rather than left waiting.
- **The machine issuer can reshape a split** (`drop_child`): an unsettled child is cancelled, the split then
  covers around it — the re-decomposition §14.2 names. Before, its moves only added to a child, so children
  that needed each other (a Dep cycle closed by a BLOCK) left it restating a child it may not narrow. A child
  it adds names the siblings whose results its checks read (`reads`), each a Dep (Ch. 10), so it runs after
  them instead of blocking on them; a child it revises can take on this node's criteria it carries (`covers`),
  so a criterion the issuer adds is mapped rather than left a hole it can only restate around. Its answers
  keep to the language of the user's own opening sentence, whatever else the packet carries.
- **A system executor consents to its own contract.** A decomposed node held by a registered executor
  is asked ACCEPT or CHALLENGE by a round of its own; a cancelled one is confirmed by its executor.

- **CHECK-6 routes to no failure mode**, as §13.4 now states it: a leaf with no executor is one that was
  never issued, so what the check guards is Del's own definition, not a mode. `/api/check_map` carries it
  with an empty list and the page groups it apart from the checks outside the battery.
- **The registered role that validates a delivery is called the validator everywhere** — in the code, the
  prompts the product sends, the API's fields (`will_be_validated_by`, `validated_by`, …) and the tests.
- **The product's own agents run without the operator's personal configuration** (`--safe-mode`: no
  CLAUDE.md, skills, plugins, hooks or MCP servers), in every mode — nor the operator's configured
  answer language, which that flag keeps: an issuer on an English goal had written its reasons into the
  graph in the operator's language.
- **A verdict recorded without a reviewer's name is recorded as the caller**, so an executor cannot
  validate its own delivery by leaving its name out.
- **An authoring round that returns no criteria leaves the root's contract standing** instead of
  re-authoring it to an empty one, over which V is vacuously true.

- **A lapse hands the node to its issuer at once, and a rejected dispute returns to the wait it
  interrupted.** `OVERDUE` is gone: the first timeout of `OFFERED`, `CHALLENGED`, `EXECUTING` or
  `REWORKING` goes straight to `ESCALATED`, and re-ASSIGN is admitted in every live state but `IDLE`
  and `CANCELLING`. A node a database holds in `OVERDUE` is moved to `ESCALATED` when the database
  opens, logged as a migration rather than a signal; audit rows naming it read as `ESCALATED`.
  `REJECT_CHALLENGE` returns to `OFFERED` when no `ACCEPT` of the current packet version stands in
  the log, and to `EXECUTING` otherwise — packet, deadline and rework count unchanged — so a
  challenge raised from the offer no longer puts the executor to work on terms he never accepted.
  The table is held by four property tests (entry-exclusivity, owner-only moves, no work without
  consent, what a timeout may do), each with a one-cell mutation control.
- **The engine follows canon v4.1: the clock never issues a verdict, and the dispute stays open
  after consent.** `VALIDATING` no longer closes `DONE(auto_pass)` when the issuer does not validate in
  time — the one timeout that invented an acceptance, and one a parent's executor could obtain over
  his own child by letting its validation lapse. It is bounded by `T_validate` alone, counted from
  the delivery, and it routes to `ESCALATED`: the delivery stays in the log, the issuer is asked
  again, and his silence closes the node without ever passing it (§24.7). `AUTO_PASS` remains a
  readable value for rows written before this change; nothing produces it.
  - Every non-terminal state now carries the bound §14.2 gives it — the packet deadline in the work
    states, the deadline and the state's own bound in the answer states, `T_validate` in
    `VALIDATING`, their own bound in the protocol states — and the bounds are ON by default
    (`GFSO_BOUND_<STATE>` overrides each). A bound that can be switched off is not a bound.
  - Every entry into `OFFERED` carries a live deadline: the engine writes a default inside the
    parent's own deadline when the issuer typed none, and marks it as supplied so no check reads the
    engine's default as the issuer's ordering claim.
  - A timeout names the visit it bounds and does not act on a state entered after it; a bound
    already passed fires on entry, so a state entered after its time admits no signal before its own
    timeout.
  - `CHALLENGE` is admitted after consent, from `EXECUTING` and `REWORKING`: the spec defects the
    a-priori battery cannot see are met in the work, and routed through `BLOCK` the dispute lost the
    two closures that answer it. `REJECT_CHALLENGE` returns the node to work under the same packet
    version with the rework count as it was; every new packet version resets that budget, which is
    the issuer's forecast for one contract.
  - A criterion that pins no procedure is refused where the **packet** lands — the first ASSIGN, a
    revision, a split's children and the contract an accepted dispute installs — and not at the
    executor's `ACCEPT`: a refusal must be liftable by the refused party's own moves, and the
    executor cannot author the contract he was handed.
  - The rework budget starts over when a packet FIELD moves, and not on a re-presentation of the
    same contract: resetting on any re-ASSIGN made `max_iterations` evadable without end.
  - A child is not issued — first `ASSIGN`, or `REOPEN` — under a parent that is unissued, settling
    or settled; a re-decomposition that drops an issued child cancels it, with its subtree; the
    cascade reaches every live descendant, including those under a child that has already settled.
  - A pinned probe carries the files it reads (`inputs`), written by the system at validation time into
    a directory the validator owns — at the machine door and, through `probe_inputs(task_id)`, at
    the by-hand one. Measured on `c_compiler`: two central probes iterated over test corpora the
    executor wrote, which grew from 60 and 36 files to 79 under a node that closed with
    `procedure_moved_since_authoring: false` — a fixed command whose object moved while its digest
    did not. The corpus is part of the procedure's digest and of the criterion's version, so a
    swapped corpus is visible to `claim_drift`; an input path that would land outside its probe's
    own directory is refused at ASSIGN rather than dropped at validation time; and a command that
    iterates over a set the contract does not pin is NAMED on the node — it is not refused, because
    whether a probe can see a divergence is FM-3, which no structural check guards. The closure
    record carries the same fact (`probes_over_unpinned_sets`), so a verdict can be weighed for it
    after the fact.
  - In a delegated graph the issuer's own moves are made: a dispute is answered with a corrected
    contract (re-consented) or a rejection with its reason, instead of waiting out its bound — and
    an adjudication that would DROP a criterion is refused, because a dispute is not a licence to
    narrow the goal.

- **`ESCALATED` is no longer a terminal state, and a project has exactly one root.** The two are one
  defect in two places: the protocol did not guarantee that the obligation to act always has an
  OWNER. Inv-6 asks that the admissible signal set be *defined* in every state, and that was met by
  defining it empty — which is right only where the work is over (DONE, ABANDONED). `ESCALATED`
  means the executor stopped and the issuer must decide, and it admitted no act of the issuer:
  `revise` refused it, it was absent from the reassignable states, and the engine said in as many
  words that its resolution was "outside the FSM". A state whose meaning is "someone must decide"
  that names neither the someone nor the decisions leaves the next move to whatever sits outside the
  protocol. Measured cost, on a `c_compiler` run: the root escalated, the agent built a second root
  beside it, then a third, and closed the whole goal on a childless leaf while the work hung under
  the dead one.
  - `ESCALATED` is now the ISSUER's waiting state, the mirror under Inv-4 of `OFFERED` where the
    EXECUTOR owes the answer. It admits his three moves: a re-ASSIGN → `OFFERED` (raising the rework
    bound and changing or narrowing the criteria are both packet fields, so Inv-1 makes them one
    act, and from this state the re-ASSIGN may carry no spec at all); the universal `CANCEL`, which
    closes it and cascades the live subtree the escalation never touched; and its own timeout, which
    settles it — through `CANCELLING`, because escalation cascades nothing and the node's children
    are still live under their own contracts, so silence takes the cancellation's own path and the
    subtree goes with it. The issuer's silence closes a task; it never drifts toward a pass. His
    window is the state's own grace, held apart from the opt-in per-state age clock for the reason
    `CANCELLING`'s grace already is: the other exits belong to a party who may never answer.
  - A parentless node is not a free-standing task, it is THE goal: `V(root)` is the project's
    verdict, and the canon's one composition rule needs a parent, so a second root is a second
    verdict with no rule combining them. Creating one is refused, and the refusal names the two acts
    that were meant — give the node a parent, or open another project.
  - The guarantee, not just the two repairs: `tests/test_the_obligation_to_act_always_has_an_owner.py`
    enumerates every state and holds that a state where the work is not over admits at least one
    signal, and that the door names the owner and the acts. The enumeration is over STATES and every
    remaining hole was found at a DOOR, by somebody driving the product — so the file also pins those:
    that `revise(id, max_iterations=…)` exists (it was named by the escalation directive and did not
    exist on any door), that the frontier asks an escalated PARENT for a decision rather than for a
    plan check it cannot take, that a settled goal is not reported as a structural block while
    `reopen` goes unnamed, and that the silence has a bottom on a default install.
  - Carried into `gfso/decompose/`, which was the layer an agent actually drives: `auto_decompose`
    refused an escalated root as "terminal … a completed goal is frozen; start a NEW goal (new root)"
    — the literal instruction the measured run followed, twice — and a refine fold froze an escalated
    child. Narrowing the criteria of an escalated node is the issuer's second move, so it is now what
    that door does.
  - Two states whose meaning is "a decision is owed" now say whose and what: `ESCALATED` names the
    issuer's three moves wherever a reader meets it (the frontier, the action surface, the page, the
    decomposition verbs), route-aware — only the exhausted-loop route offers the bound, the clock
    routes offer the deadline — and `OVERDUE`, one tick earlier, says the clock is about to hand the
    node over rather than answering "no actionable node … check `list_holes`" over a childless leaf.
    A settled goal likewise reports itself as settled and names `reopen` with the budget left,
    instead of calling itself a structural block.
  - Canon §14.3-bis derives it; §26.9(b) is corrected with it — `ESCALATED` moves from the free
    timeout-geometry decorations to the tier forced by IC, where `CANCELLING` already sits, and the
    forced backbone is ten states rather than nine. `Fsm.lean`, `FsmCanon.lean` and the TLA table
    move with the code; Inv-5's deadline path is now three timeouts instead of two, because it ends
    in a handover before it ends in a settlement.

- `docs/EVIDENCE_LOG.md` §13.10's bill figures now read: validation is **0.710** of a closed run's
  spend and the run costs **$10.40**. They were wrong, and in both directions before they were
  right: a run's model calls are recorded in two places, whether those two overlap depends on which
  regime spawned the executor, and neither file says so where they are read. §13.10 states that
  difference where the numbers stand. §13.8's own share figures are unchanged; its label is
  sharpened to say they cover validation of the delivery rather than all validation. The account of
  how the figures were arrived at is process and lives outside the public record.

### Fixed

- **An accepted dispute can correct an automatic root's pinned probe.** The text of an automatic root's criteria is
  the user's and is kept exactly; a machine issuer that accepts a dispute may re-pin the check of the criteria the
  dispute questioned — named by the challenge, or cited by the failure it answers — never with fewer probes, and the
  move shows in the claim's drift. Before, a corrected probe under the same criterion was dropped as "no change", and a
  root whose probe its own criterion's text refuted was closed by its count of unproductive answers.
- **A session that names no project is told which projects exist.** Where its fallback is `default` and the server
  holds other projects, an MCP call with no `project` and no `use_project` is answered with their names instead of
  being answered from `default`, where a goal stated by mistake is planned and never executed.
- **A validator's failed list shorter than its failing entries is read off the entries.** A FAIL report whose
  `failed_criteria` omits some of its own non-pass entries is recorded with those entries' criteria; before, the whole
  report was refused and the nodes it covered were left with no verdict until the clock escalated them. A list naming a
  criterion its entries pass is still refused.
- **A machine issuer's move finds the child it names.** A child is found by its stored id, or by the name the issuer
  gave it when it added it, a live child first — in the child it revises or drops and in the siblings a new child
  reads; before, a child the issuer had just added, or a sibling named without its parent, was "not a child" of its
  parent.
- **A model call is ended at its cap even when the child goes silent.** The cap was checked only as a line of
  the stream arrived, so a child that stopped writing held the call past its cap until the node's own state
  bound ended the wait around it (a root validation stood 340 minutes with no answer across a sleep of the
  machine). A timer now ends the process tree at the cap.

- **The machine issuer can clear a register entry that names the node's own criterion.** CHECK-4 refuses such an
  entry (a unilateral amendment of the contract, not a risk), and no plan move reached the node's own register:
  an automatic run answered `revise_child` eighteen times over that hole at its root and stopped with the whole
  tree offered. The plan episode now shows the node's own ACCEPTED_RISKS and has `drop_risk`, which removes
  exactly the flagged entries — it cannot add one (that would narrow the goal at the plan gate) or empty the
  register.

- **A pinned probe is read by its hash inside its own criterion.** A validator that ran every pinned probe of
  a node and cited them as `568a2aaa` was refused as "the procedure was not run" and paid again on the retry
  tier; the pinned check, the regression check and the coverage count now read one way — a bare hash under
  the criterion it is reported with, the full `criterion#hash`, or the command itself.
- **An agent run loads only the tools it may use.** The approval list alone loaded every built-in tool, so a
  read-only validator held Write, Edit and PowerShell and re-read ~30 tool schemas on every call; runs now
  pass `--tools` with the same names.
- **A register entry never decides how a criterion's behaviour comes out.** The plan author filed "lone
  surrogates are accepted rather than rejected" as an accepted risk; the decomposer, the plan checker, the
  validator and the executor are now told that ACCEPTED_RISKS holds uncertain events only (§13.1) — a behaviour
  on an input the goal describes is decided in a criterion, and changing what a criterion demands is a
  revision of the criteria.
- **A delegated executor sent back to rework is told why.** Its packet named the failed criteria and nothing
  else, so it re-ran its own checks, found them green and re-delivered the unchanged work round after round.
  It now carries, per failed criterion, what the validator observed and the probes that refuted it — the
  same findings the human door's directive already read.
- **A dependency a BLOCK discovers enters the plan only when its issuer confirms it** (§14.2, §15.2). The
  plan's checks, the execution order, consumption and the dispatcher read E_Dep — the declared edges and the
  confirmed discoveries; a confirmed discovery that would close a cycle is not adopted. Every record still
  counts in q_Dep. CHECK-2 used to run over the provisional record as well, so a BLOCK naming a sibling that
  already waited on the blocked node turned the plan red and stopped every sibling. Such a record now tells
  the blocked node's issuer that what it names cannot come first — in the BLOCK's reply, the BLOCKED
  directive and, under AUTO, the machine issuer's question on that node, whose answer refutes it; once a
  block of the same contract has been answered, such a block — and a confirmed discovery against the
  plan's order — is the split's repair. The waits read are E_Dep, the blocks
  that stand and a parent's wait on its children, each while its producer is unfinished — so two blocks
  naming each other, or a block naming its own ancestor, is asked as well. A record whose block no longer
  stands (the node was re-issued, cancelled, or its bound fired) is closed unanswered: counted, and never
  again read as the reason for a later block.
- **A block clears itself by one rule.** The dispatcher confirms a block once its producers pass, and the
  machine issuer asks about the others: a block naming nothing still to be produced, a repeat block on
  producers that had already passed (it was confirmed again and again, a paid executor run each time), or
  one whose producers wait on it.
- **The machine issuer's closing count no longer counts the checker's disagreement.** A review of a changed
  plan that raised again only findings already answered by a dispute counted as a review that moved nothing,
  so a few re-issued children could close a converging root.
- **"Touched since the FAIL" is read off the log's order, not the clock.** The rework gate and the
  dispatcher's automatic block resolution compared state timestamps; on a coarse clock tick a child that
  passed after its parent's FAIL read as untouched, and the parent's repaired re-delivery was refused.
- **Under AUTO the system validates the deliveries of the work the mode handed it.** The dispatcher's
  validation went through the doors' mode lock and was refused as a customer's move, so no node could
  pass. Where the system is a node's issuer, two validations with no verdict no longer park the node for
  an issuer told to decide; the validator is asked again until VALIDATING's own bound hands it on.
- **A mode changes on the user's word.** Refusals no longer offer `set_mode` as the agent's way out; once a
  project has work in it, `set_mode` takes `user_said` — the user's own words, recorded with the mode.
- **In semi-auto the holder does not take or hand in a node it holds with no split**: the mode means the
  system executes below the plan, and one person's work is the solo mode. A node it holds with a split is
  handed in only when its PASS could follow — every active child passed and no criterion left without a
  child to carry it — so the holder cannot deliver its own work and cancel or extend the split under it.
  What no structural rule sees is who wrote the files; the root is still validated independently at its
  seam. The engine enforces it on the node, whatever
  door the signal comes through, and the next step and `available_actions` ask the same rule; work first
  consented to before the mode was chosen is kept without a split; the decomposition verb accepts a root
  only after its split, and an issued node is split by its own contract with the caller's request as
  guidance.
- **A plan is admitted only on a Level-2 verdict about that plan.** A review round the checker ran and
  read nothing replaces the last record instead of leaving it to be read as current, and a contract
  installed by an accepted dispute stales the verdicts over it, as a revision does. The record keeps the
  plan's verdict and the goal's reading apart: a round that did not read the goal carries the obligations
  already named, a goal reading that failed is no reading, and a round with no verdict is no baseline for
  progress. A dispute needs a verdict that stands.
- **Refusals under a mode name the caller's own way on** (leave `executor` / `assignee` out; name one of
  the project's executors), not the user's choice of mode.
- **The machine issuer is shown what a plan decision rests on**: each child's whole contract with its
  checks and every open finding with its reason; an absent review is said to be absent. Not carried: the
  source statement a goal points to and files in the workspace.
- **The machine issuer's budgets are bounded without cancelling a converging goal**: a plan episode takes
  at most 24 answers and is never closed on a fix no review has read; disputes do not spend it, and a
  dispute of a finding already disputed is refused; a question whose calls keep failing is retried at a
  doubling interval up to two hours instead of being muted.
- **A regression probe is handed back to be run**, with what was recorded when it refuted, not as an output
  the delivery "must show" — a recorded expectation is sometimes the requirement and sometimes the
  failing output.
- A bare block is not resumed by a producer that was already done when it was raised; a new contract
  version tells its executor which criteria failed on the last one.

- **A stopped or killed server left its executors and validators running and spending.**
  `gfso.adapters.children` gives the server's descendants its lifetime.
  - On Windows, a job object the server puts itself in ends them with it, a hard kill included.
  - On POSIX, each child's process group is killed at `gfso down`, at shutdown and at exit. A SIGKILL
    of the server is not covered there, and the module says so.
  - Every call ends the tree it started.
  - A graceful stop waits five seconds, not for every paid call.
- **A refused validation was retried whole.** A report is refused for a single gap. The next attempt
  on the same delivery now keeps the entries that decide their criterion on their own, under the same
  checks the merged report faces, including each one's own run's tool ledger. It validates only the rest,
  and records which part it reused and who validated it.
- **The drift report called a claim unnarrowed when a refuted criterion had been rewritten.**
  `claim_drift` now answers ⊥ (`narrowed: null`) and names the criterion in
  `reworded_after_refutation`. Every FAIL verdict keeps the version it validated, taken at the last
  DELIVER, and a version includes each probe's `expect`.
- **The rework bound had four spellings and two of them still said 3.** The default moved 3 → 12,
  but `Engine.assign_task` carried its own `if max_iterations is None: 3` — the door
  `create_task` uses and the door `auto_decompose` authors the ROOT through — so the node the raise
  was made for kept the old bound while the change was reported as shipped. One constant now
  (`core.types.DEFAULT_MAX_ITERATIONS`), and the storage DDL carries no default of its own.

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
  the batch size is validated in concurrent batches that report in completion order, and the question
  "was this call cut?" was asked of whichever answered last. Read as a cut, the call is redialled
  for free; read as an answer that did not parse, it spends the node's one retry and the next one
  parks the node with no verdict ever coming. The question is now asked of the whole validation.
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
- **Level-2 review of a decomposition (§13.4).** `review_decomposition` checks, per parent criterion,
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
  over a report that records nothing does not become the record an internal node is validated on
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
  a previous run had named — the graph looked healthy while the verdicts validated the wrong tree.
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
  one: otherwise both ran where the SERVER stands — the state home — and validated or wrote work that
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
  that one run cannot validate another's leftovers — had made that scratch the validator's working
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

[0.2.0]: https://github.com/Kirill-Shokhin/GFSO/releases/tag/v0.2.0
[0.1.0]: https://github.com/Kirill-Shokhin/GFSO/releases/tag/v0.1.0
