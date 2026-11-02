# Using GFSO on a real project

This page is the working loop, not the theory. It assumes `pipx install gfso` (`pip install gfso` works too, except on the system
Pythons of macOS/Homebrew and Debian, which refuse it under PEP 668) and one `gfso setup`
— which registers the agent door and brings the engine and the UI up at `http://127.0.0.1:8000`.
One home holds your graphs (`~/.gfso`, or wherever `GFSO_HOME` says), and separate pieces of work
are separate projects inside it, not separate directories. The theory is in
[`applied_gfso_v4_en.md`](applied_gfso_v4_en.md); the protocol as an agent session receives it is
[`ORCHESTRATOR.md`](../gfso/mcp/ORCHESTRATOR.md).

There are two ways to get a graph, and they are not equal in what they cost you.

* **`auto_decompose(request)`** — one call authors a whole verified subtree from a sentence. Good
  when the goal is generic enough that a model's weights already carry its structure.
* **The manual mode** — you study the context and build the graph yourself, then run the checks over
  it. This is the mode below, and it is the primary one for work on a codebase you know and a model
  does not: a decomposition is an estimate `Ŝ` of a real structure `S` (§3.1), and the estimate can
  only come from contact with the domain. Nothing in the apparatus can supply that for you.

The two mix. Hand-build the parts that need your context, let `auto_decompose` refine over what you
built, and keep your ids, owners and accepted risks — a refine round folds new findings in as a
revision rather than replacing your structure.

---

## 1. Say what "done" is, before anything else

A node carries a spec, a finite set of criteria, a deadline and an owner (§2). The criteria are the
whole contract: they are what a validator will run, and they are the only thing a `PASS` can be
about.

A criterion has to be **decidable** — someone who is not you, holding only the criterion and the
deliverable, must be able to come back with pass or fail and no argument. In practice that means
naming the observation rather than the quality:

| Instead of | Write |
|---|---|
| "the parser is robust" | "`parse('')` returns `None` and does not raise" |
| "good test coverage" | "`pytest tests/test_parser.py` exits 0 with no skips" |
| "the endpoint works" | "`GET /health` returns 200 with `{\"status\":\"ok\"}`" |

The contract may name formats, APIs and terms — that is what a contract is. What it must not do is
hand over the answer to the work itself.

The exact keys an authoring call reads are [`TASK_PACKET.md`](TASK_PACKET.md).

Where a node is split, it also carries an **accepted-risks register**: the assumptions the split
rests on, each with what would invalidate it (§9.2). A leaf has none. An empty register on a
decomposed node is a hole the engine will show you, not a clean bill.

## 2. Build the graph

From an agent session these are MCP tools; from a shell the same verbs are `gfso run <tool> …`; in
the UI they are the Decompose and Edit Node panels. Same engine, same audit log, whichever door.

```
create_task("api", {"name": "…", "description": "…", "criteria": [
    {"name": "…", "description": "…",
     # what will be RUN to decide it — pinned now, before the work (A1, §2)
     "check": [{"behaviour": "…", "command": "…", "expect": "…"}]}]})
decompose("api", children=[{"task_id": "schema", "spec": {…}, "covers": ["…"]}, …],
          accepted_risks=[…])           # the split admitted whole: every criterion covered, its register given
decompose("api", children=[…], accepted_risks=[…], drops=["old"])   # re-admit: a hole a revision left
edit_criteria("api", [...])             # replace criteria, carry the rest
add_dependency("schema", "handlers", glue="handlers deserialize the published schema")
edit_scope("api", ["a capability this goal deliberately does NOT include — and why"])
claim_drift("api")                      # how the contract moved between authoring and now
```

One difference between the doors is worth knowing before you copy a call: on the **MCP** door the
actor parameters are not yours to pass. `source` on `signal`, `reviewer` on `record_verdict`, and `agent` on `revise` /
`edit_criteria` / `edit_accepted_risks` / `reopen`, are removed from the schema
and filled with the session's own identity — everything arriving over MCP *is* the agent, so it
cannot sign an act as someone else. From the CLI, the unpinned developer door, you name the actor
yourself (`gfso run signal schema DELIVER human`).

Every parent criterion must be **mapped** to the child that delivers it. That mapping is the claim
the whole composition rests on: the parent passes exactly when its children do (§7.3), so an
unmapped criterion is a parent obligation nobody has agreed to carry.

A plan can also exist before any project does, as a file of its own: `plan` authors and reviews a `.gfso` file with no project,
`refine_plan` answers your note on it, and `auto_decompose(plan=<file>)` is the go, which builds the project from the file as it
stands. The file is TOML you can read whole and edit by hand; its fields, and what `parse` checks in a file you edited, are in
[`PLAN_FORMAT.md`](PLAN_FORMAT.md).

Assign a node to someone else only when the work is really theirs. Ownership is load-bearing: a node
owned by another party moves only on *their* signals, and a node owned by a person the engine does
not know simply waits for that person — which is the honest state of the graph, not a stall.

## 3. Check the plan before writing any code

Two levels: the engine admits a split only whole and clean at Level 0, and a child does not start executing
until its parent's decomposition has a current Level-2 verdict.

**Level 0 — structure.** `list_holes()` answers `{holes, count}` — every unmet structural check
across the graph at once: an uncovered criterion, an orphan child, a cycle, incoherent deadlines, a missing risk
register. Fix them or declare them consciously, up front, rather than meeting them one rejected
`PASS` at a time. (`get_checks(node)` is the per-node view; the UI groups the same checks by the
failure mode each one guards.) A check answers one of four words, not two: `met`, `unmet`, `skipped`
(it did not run — never read that as passed), and `met_vacuously` — it held over an EMPTY subject,
such as deadline coherence on a plan with no dependency edges. True, and true of nothing; the page
draws it `∅` rather than a tick, because a row of ticks that verified nothing is not a checked plan.

**Level 2 — causality (§9.5).** `review_decomposition(node)` asks, per parent criterion, whether
the mapped children's criteria — taken as facts about the world — actually *carry* it, and names the
gap where they do not. Structure cannot see this: a criterion with a covering child passes Level 0
even when that child's criteria could not possibly deliver it, and you would then meet the hole in
code, as a refused delivery.

Every gap the review names must be dispositioned before work starts. Either fix the plan
(`edit_criteria` / `map_criterion` / add a child — any shape edit stales the review, so re-run it),
or say in writing why the checker is wrong:

```
dispute_finding("api", "<criterion>", "<why the entailment does hold>")
```

The checker is an a-priori approximation, not an oracle; contact keeps the last word. What the engine
enforces is that you *ran* it and dispositioned what it said — never that it was right.

**If you have no checker.** The review needs a model — the Claude CLI on your `PATH`, with a credential set by
`gfso credential claude`. With
none, `review_decomposition` answers with no verdict, and no verdict is never read as clean: the gate
stays shut and nothing executes. That is deliberate and it is not the only supported way to run. The
canon's other branch (§9.9, EXPLORE) buys the plan's verification with *contact* instead of with a
checker, and it is a deployment setting rather than a skipped step:

```jsonc
// data/serve.json — the switches the one server is raised with; then `gfso up` reconciles it
{ "GFSO_L2_GATE": "0" }
```

Under it the Syntactic level (Level 0) still gates every admission, so a split is still refused for an
uncovered criterion, an orphan, a cycle or a missing register — what you give up is the causal
pre-check, and you meet those gaps at the delivery instead. Choose it knowingly; the reason it is a
switch and not a default is that an agent must never be able to reach it by skipping a step.
`get_review(node)` is a free read: it returns the stored verdict and whether it is still fresh for
the current shape of the decomposition.

One refine round of `auto_decompose` over your hand-built graph is worth running here for a different
reason than the review: the review repairs entailment between criteria that exist, and a refine round
is the hole-hunt for content that is missing altogether. They answer different questions.

## 4. Execute, and deliver evidence rather than intent

Work the frontier: `next_steps(root)` returns every actionable node at once, ordered, marking which
are yours and which the graph is waiting on someone else for. An empty list is not a dead graph: what
is being validated or worked on comes back under `in_flight`, what a node waits on and what would open it
under `waiting`, and `stuck` means what it says — nothing is running and nothing is takeable. Loop it
until it reports complete — "done" is the root at `DONE/PASS` in the graph, never a summary in a chat
window.

Before signalling a delivery, run a check for each criterion and read what it actually printed. Then:

```
signal("schema", "DELIVER", result="<paths + for each criterion, the check run and its output>")
```

The `result` text is the validator's input. Write it so an independent reader needs nothing else.

### Doing several nodes at once

`next_steps` marks the execute-class steps `parallel_ok`, and they are independent by construction:
each is a leaf whose dependency producers have passed. You can work them concurrently yourself, or
hand them over — register executors once and assign nodes to them, and the engine runs them in
parallel, gates each start on its producers, wraps every report into the protocol and validates each
delivery:

```
register_agent("exec-1", "llm-executor", workdir="<project dir>", max_turns=50)
register_agent("val-1",  "llm-validator", workdir="<a scratch dir>")
reassign("parser", "exec-1")      # …and then just watch the graph
```

Those executors work with nobody watching their commands, so they run in a container. `gfso setup`
builds the agents' image and declares it as the execution `default` (Docker is part of the installation;
`gfso doctor` names what is missing), and `set_mode` places a project's executors that name no execution
into it; `execution=<name>` on `register_agent` picks another one you declared (below). The project's base
must be a git repository with a commit. On your machine instead, they start only with
`"GFSO_LOCAL_AGENTS": "allow"` in `data/serve.json` (then `gfso up`); without it or a container the first
round stops the project with that cause, nothing of the node run. A validator
judging work you do in your own chat runs on your machine either way.

The roster is the server's, shared by every session on it, so take your roles off when you are done:
`unregister_agent("exec-1", workdir="<project dir>")` removes the role only while it still points at
that directory (without `workdir` it removes it unconditionally, and refuses a role another project
registered — a guard against accidents, not an owner check; a role registered with no project can be
removed by anyone). The answer lists your live nodes the role was carrying or had issued.

Where the project dir is the top of a git repository with a commit, each node an executor runs gets a
place of its own: a worktree beside it (`../.gfso-nodes-<dir>/<project>/<node>`, branch
`gfso/<project>/<node>`), made when its first session starts from where its parent stood when the node
entered the split, with its producers by their Dep edges, and reused on rework: a
sibling's work it needs is an edge in the plan, or a BLOCK that makes one. Its delivery is committed there, its validation reads it there — never a sibling's half-edited
file — and when it PASSes its branch is merged into its parent's place (the parent's worktree once it
has one, else the project dir). A merge that conflicts is aborted and left to the whole: the parent's
session is told which branches did not join, and integrating them is its work. When the root PASSes,
the worktrees whose branches joined are removed; the others stay and are named. A project dir that is
not a repository is shared by every executor as it stands, and the log says so once.

**What a judge judges.** A delivery's validation — each of its batches, the system's own run of the exact
checks, an issuer's contact — runs in a copy that is a checkout of the commit DELIVER recorded and nothing else:
files the executor's `.gitignore` hides, binaries and environments it built, anything changed in its place after
DELIVER are not in it. Under a container execution the judge's container mounts three directories — its own round
or batch (holding the copy), a temp of its own, and read-only what the system laid for it from its record — and
not the project dir, the node's temp or place, another batch, or an earlier round, so a delivered link or build
step reaches nothing the executor can still change; the container ends when the run does, with whatever the run
left running. Where each input comes from: the copy's objects are streamed from the executor's container into a
git the system makes and hashed again against their ids (no size limit but the disk); Git LFS files are checked
out as their content, from objects streamed from the place's and the base's LFS stores and kept only where their
sha256 is the pointer's; a standing finding's probe files are recorded by the system as the finding is filed and
laid from that record for its re-run, which starts from a fresh copy of them in the judge's batch; pinned inputs
come from the contract. What the result needs built is built there by the system, in the judge's container,
before any check: DELIVER's `build` when the executor gave one (`""` = nothing to build), else `make` where the
delivered tree has a Makefile at its root, else nothing; the executor's DELIVER instructions ask it to declare one.
A build that fails, or still runs after 10 minutes, is the delivery's FAIL with its output as the cause, and no
check runs; the executor's next packet says which build ran and, where it failed, its output, and an issuer ruling
on a dispute of that FAIL gets the copy unbuilt with that output; nothing of a failed build stands as a finding — the
next delivery's own build re-checks it. Whatever the build leaves running ends before any check, and a delivered file
it changed is put back as delivered (said in the packet line). A checkout the delivery itself makes impossible (an
object missing or rewritten, a commit not carrying the recorded tree) is the delivery's FAIL too, its cause in the
executor's next packet, and its issuer rules on that cause; one that fails for another cause (Docker, a timeout, the
disk) gives no verdict and is asked again — never the live place in its stead. A standing finding whose file the
record could not keep is shown, not demanded. A delivery with no recorded
commit (a project dir with no git, a DELIVER an agent sends through the door) is copied as it stands, and nothing
is built.

Under a container execution (`register_agent(..., execution=<name>)`) none of that is on your disk, and
nothing of your disk is mounted into a container: the project's own directory — node places, validation
rounds, temps, the sessions' CLI state — and the project dir's working copy live in the project's Docker
volumes, named by the installation, the execution, the project and the base. When the project
first starts, your repository's HEAD is imported into the volume — committed work only, by your own git as a
bundle, checked out there with LF line endings and none of your config or hooks. Files your repository tracks
by Git LFS come in as their content: the LFS objects HEAD names that your repository holds are carried with the
bundle, and the system itself writes each file from its object once its size and sha256 match the pointer (no
git-lfs runs, yours or the image's); inside, every staging writes such a file back as its pointer, so a delivery
and the accepted branch hold pointers, as your repository expects — the system's own git and an agent's plain `git`
alike, the filter written into each repository's config there. An LFS object made inside (a file an agent changed)
travels with the commits that point to it: into the project's base when the change is delivered, so a parent that
joins it checks out its content, and into your repository's LFS store (`lfs.storage`, else `.git/lfs/objects`) when
the result lands, written by the system once its sha256 matches — your git-lfs then checks the accepted branch out
with no remote asked. An object that could not be carried (over 512 MiB, or lost inside) is named by its file in the
landing's log line, and that file reads as a pointer in your repository. The disk it takes grows with your LFS
content: the import passes it once through your system's temp folder, and the project's volume holds the base's store
and checkout plus one checkout per node place — roughly (2 + places) × the LFS content at HEAD. A partial clone is read with nothing fetched:
the system never reaches your remote with your credentials, so a clone whose history lacks objects is not imported
until you fetch them. The log names the commit and what did not come
in — files you changed or did not commit, submodules (empty inside), LFS files whose object your repository lacks
(pointers inside: `git lfs fetch` first), the objects a partial clone lacks — and the answer of the call that makes
the root (`auto_decompose`, or `create_task` building it by hand), and of `start_project` before any import, says the
same as `not_imported`. That import is the root's: no restart of the server, of Docker or of the container imports again, and
only a new root of the project does, once the earlier root no longer works there. A project dir with no git is
copied as a tree, once: nothing ever copies over the work done in it. Your working tree and your branches are
never written: when the root PASSes, its accepted result lands in your repository as the branch
`gfso/<project>/accepted` (a `git fetch` of a bundle, without submodules, nothing else), to read, diff and merge
when you choose; a later root's PASS moves that branch (its reflog keeps where it stood), and the landing is
refused while the branch is checked out in any worktree of yours. A project dir with no git lands its result
beside it, in `../.gfso-accepted-<dir>/<project>/`. So two projects on one project dir no longer see each other's
accepted work until you merge their branches. `perform="in_chat"` is refused under a container execution: work your own agent does
on this host is not in the volume, and only what stands there is judged. To read the places, write them out:
`gfso export-places <project> <dir>` puts them under `<dir>/<project>/` — the volume found by the project's
own record in the installation's data directory, whatever roster the shell points at —, each node's repository whole
(it no longer borrows objects from the project dir) and inert: no repository carries the config or hooks
an agent gave it, so reading the export runs nothing an agent wrote; the project's working copy is there as
`.gfso-base`, and its HEAD and `gfso/*` branches as `gfso-refs.bundle`, which your repository can `git fetch`;
what could not be exported as it stood is listed in `<dir>/.gfso-export-notes`. A project whose places stood beside the project dir
before it moved into volumes is copied in on its first start, and the host directory is renamed
`<dir>.copied-in-<time>`. To go back to host directories, export the places first — what the project did
since the copy-in exists only in the volumes — then remove the two volumes and the project's `volume:`
settings and rename the `.copied-in-` directories back. The volumes go when the project is deleted.

One thing decides whether that is safe, and it is a property of your PLAN, not of the machinery: two
nodes that will write the same file are not independent, whatever their topics. Give each node its
own artifact, or declare the dependency between them — otherwise both run, and the later one's join
conflicts (in a shared directory: the later write silently takes the earlier one's work). Build
products belong in `.gitignore`: a delivery commits everything else it finds, interpreter and compiler caches
(`__pycache__`, `*.pyc`, `*.o`) excepted. If it happens anyway,
`BLOCK` is how it becomes visible: the blocked node names the one that got in its way, the edge the
plan omitted appears in the graph, and `q_Dep` counts it.

What all this costs is on the record: `/api/usage` totals the model calls per project, split by the
role that made them — decomposer, plan review, validator, executor. The UI shows it in the observation
window, beside the runs it is made of — and a graph worked by people has no calls and shows nothing
there, which is the point: the quality metrics describe the graph, the spend describes one way of
working it.

### Who you are at each door

The actor a signal is signed as is decided by the door, not guessed:

* **MCP (the agent door)** pins it: everything arriving over MCP *is* the calling agent, so `source`
  on `signal`, `agent` on the authoring verbs and `reviewer` on `record_verdict` are not in the
  schema at all — you cannot sign as somebody else.
* **CLI** is the unpinned door: you name yourself (`source=<your name>`), and the FSM checks that
  name against the node's Del.
* **HTTP** is the same as the CLI — the parameters are yours to fill, and nothing infers them for
  you. The standing agent identity of the server is `agent` (`GET /api/runtime` says it under
  `agent_id`), which is what `auto_decompose` assigns nodes to unless you pass `assignee`. So a
  graph you build over HTTP and then drive as yourself needs either your own name on the nodes
  (`create_task assignee=…`, `reassign`) or your signals sent as `agent`; the automatic paths — the
  dispatcher running an executor, an `llm-validator` role relaying its verdict — only ever act for
  the identities registered on the roster, never for a name you use once in a call.

## 5. The verdict is not yours to sign

Validation fires at the **seams** — the root, and every node whose executor differs from its parent's
(§10.3). There, a `PASS` needs a verdict for the delivery that stands, **whoever signs it**: being
someone other than the executor is a rule about the signature, not evidence about the work. A stale
verdict does not count — a rework, a reopen or a revision under it makes the record about an earlier
delivery.

* From an agent session: `validate_result(task_id, workdir=…)` spawns one read-only validator that
  *runs* the criteria and reports per-criterion. You then relay `PASS`, or
  `FAIL(failed_criteria=[…])`. A report with no verdict is never a pass.
* With a registered `llm-validator`, that happens automatically on every delivery.
* With people: the reviewer presses Record verdict in the UI (`record_verdict`), which is also how you
  put your OWN observation on the record when you validated by hand — one line per criterion, saying what
  you ran and what it showed. At a seam the engine refuses a reviewer who is the node's executor, and
  it refuses a verdict with nothing observed behind it. What it cannot check is whether the party who
  named themselves is independent of the work, so it does not pretend to: a record made this way
  carries `by_hand`, and `get_verdict` says it was asserted rather than produced by an instrument.
  Observations that name no criterion of the node are kept out of the verdict and named back to you.

A node whose executor is the same as its parent's is *internal* — your own private decomposition. It
has no seam of its own — its guarantee is carried by the seam above it, and the root is always one —
but where it is not covered by one session's scope it is observed: the system's validator validates at
every seam and at the top of every part of the plan larger than one session (the plan's author judges
each part against the executor's model), and under a mode a PASS there stands on that observer's record,
not on the evidence the executor put in the delivery. Inside one session's scope the scope's validation at
its top runs every criterion of its pieces; `GFSO_VALIDATE_INTERNAL=1` observes every delivery.

**A green that is not green does not stay quiet.** A signature can land before the instrument's
verdict does — you sign, and the validator that was already running reports `FAIL` a few seconds later at
a node the protocol has closed. That verdict is refused as a signal, correctly, because the node is
terminal; it is not discarded. `next_steps` then refuses to call the graph complete and names the node
under `refuted_passes`; `gfso status` marks it `[X] … PASS CONTRADICTED by its own current verdict`
instead of the tick an earned node gets; and `get_verdict` says the state and the record disagree.
Recovery is `reopen` while the node is not consumed, and re-decomposition around it once it is.

Two things follow from that, and both are deliberate. A verdict arriving after a node closed is kept
BESIDE the one it closed on rather than replacing it (`closed_on`) — a later record is evidence about
the same delivery, never a substitute for the one that was acted on. And a report the engine refused
as ⊥ is named beside a completion rather than withholding it: a validator that could not decide is not
a validator that decided against you (§7.1).

**What is asked of an observation, and what is not.** A `PASS` whose text per criterion only restates
the verdict — `"ok"`, `"looks green"` — is refused the way a `PASS` with no text at all already was;
so is a Level-2 finding discharged with `"nah"`. This is a floor on ASSERTION, not a test of evidence.
It cannot refuse a sentence naming a command that was never run, and it does not pretend to: at a door
where you name yourself, the explicit record IS the guarantee (§10.3), and it carries your name.

**When a criterion fails, the rework flows down, not around.** If the failed criteria are covered by
children, the engine refuses a re-delivery over an untouched subtree: contact refuted the split, not
the aggregate (§15.4). Reopen the covering child, fix it there — or revise its contract, remap it, or
add a child that covers the gap — and re-aggregate.

## 6. When reality disagrees with the plan

| Situation | Verb | What it means |
|---|---|---|
| You need something that does not exist yet | `signal(…, "BLOCK", blocker_task_ids=[…])` | Every blocker named; an unlisted one is an invisible edge (§11.2) |
| The contract is wrong | `CHALLENGE` — before you consent AND while you work | The issuer answers it: a new contract (you consent again), or a rejection with its reason |
| You are the ISSUER and the contract is wrong | `revise` / `edit_criteria` | Same node id, subtree retained — a spec change is a revision, not an abandonment |
| The goal is genuinely dropped | `CANCEL` | Cascades to the subtree; this is `⊥`, not "done" |
| A closed node has to be re-earned | `reopen(task_id)` | Only while nothing has been staked on it, and only within its reopen budget (§12.14) |

A node in `ESCALATED` is asking its ISSUER, and asking is the design: the automatic path stopped and
says so rather than closing something to look finished. It is not a dead end — the issuer has three
answers, and the graph names them on the node. Raise the rework bound (`revise(id,
max_iterations=…)`) if the forecast was short rather than the plan wrong; change or narrow the
criteria (`revise`) if the plan is what is wrong; or close it (`signal(id, "CANCEL")`, which cascades
the live subtree). Silence closes it too, by the state's own timeout — it never drifts to a pass.

**Every state has a clock.** The packet carries a deadline — you give one or the engine writes a
default inside the parent's — and each waiting state has its own bound as well: an answer you owe
(`OFFERED`, `CHALLENGED`, `BLOCKED`) and the issuer's decision in `ESCALATED` are each a day by
default, a verdict in `VALIDATING` an hour, counted from the delivery. When `VALIDATING` runs out the
node is handed back to its issuer, never accepted: the clock does not sign a verdict for anyone. Set
`GFSO_BOUND_<STATE>` (seconds, `0` = no bound for that state) and `GFSO_DEFAULT_DEADLINE_S` to your
own working rhythm — the numbers are ours, the rule that a wait ends is the canon's.

`metrics()` reads the quality vector off the execution trace — including `q_D`, which is where a
decomposition that looked fine and did not hold shows up after the fact.

---

## Driving all of this from a Claude Code session

`gfso setup` already registered the MCP server. By hand it is:

```bash
claude mcp add --scope user gfso -- "$(command -v gfso)" connect
```

User scope, and the **absolute** path to the console script: a bare `gfso` resolves against whatever
`PATH` the client happens to have, and a venv you later leave takes the name with it — the session
then has no gfso tools and says nothing. `gfso setup` writes the absolute path for you.

The session receives the protocol as its instructions and gets the verbs above as tools. Its identity
is `agent`, so nodes it creates are its own and its signals are signed as itself; nodes owned by you
or by a teammate it cannot move, and it will surface them to you instead.

A session that works well on real code looks like this: it studies the part of the repository the
goal touches, builds or repairs the graph by hand, runs `list_holes` and `review_decomposition` and
closes what they name **before** editing a single file, then works `next_steps` until the root
closes — validating at the seams, and telling you what it is waiting on. You watch the same graph in
the UI while it does, and every write it makes appears there as it happens.

Useful things to say to it: *"decompose this manually — read `<paths>` first"*, *"run the Level-2
review and show me the gaps before you touch anything"*, *"what is the graph waiting on?"*, *"that
finding is wrong because …, dispute it"*.

One graph per project. `use_project(name)` switches the project for your session only; a dependency
across projects is deliberately unrepresentable, so related goals belong in one.

### Who holds which nodes: the mode

Asked once per project, before the plan, and set with `set_mode`:

| mode | who holds the nodes | your session |
|---|---|---|
| `solo` | your session holds every node | performs each one; the root is the seam |
| `semi` | your session holds the top (the root, or depths 0…k−1 with `boundary=k`), registered executors the rest | authors the plan and makes the issuer's moves over what it holds |
| `auto` | the system holds every node, the root included | states the goal (`auto_decompose` on an empty project) and reads the status |

Every mode needs a validator registered for the project; `semi` and `auto` need executors too — `set_mode`
says what is missing. A node your session holds is performed by `perform="dispatch"` (the default: your
session consents, a clean executor session of the project does the work in the node's own place) or
`perform="in_chat"` (your session does it with its own tools). A set mode is a lock: once the project has
work in it, changing it takes your own words as `user_said`.

### Which model runs a role, and on whose account

Each role names its model as `provider/model` — `register_agent("exec-1", "llm-executor", model="ollama/qwen3:32b")`;
a bare model name is Claude's, through the Claude Code CLI. `gfso provider-check <spec>` says which roles a
provider can hold. A provider's credentials live in one place: `gfso credential claude --kind token` (or
`--kind api`) reads the value from stdin and never prints it; a provider holds several named ones (`--name`),
one in use (`--use NAME`), the rest tried in order (`--order A,B`) when the one in force hits its limit — the
project stops only when every one is spent. Every recorded model call names the credential it ran on.

---

## The commands

Three are for using it; the rest are for running it, and you can ignore them until you need one.

| | |
|---|---|
| `gfso setup [--desktop]` | Register the agent door, bring the server up, open the UI, report. Idempotent. |
| `gfso doctor` | What this installation is and what blocks it: version, state home, who holds the address, whether the Claude Code CLI answers, whether the assets are present. Paste it into a bug report. |
| `gfso demo [name]` | Run a shipped example; no name lists them. |
| `gfso credential <provider> […]` | Set, name, choose or order a model provider's credentials (value on stdin, never shown). |
| `gfso provider-check <spec>` | Whether a model provider can run on gfso, and in which roles. |
| `gfso run <tool> …` | The same verbs as the MCP tools, headless from a shell — through the running server, so its writes are live in the UI, and straight against the database when none is up. `project=<name>` selects the graph. This is the door where you name the actor yourself. |
| `gfso up [--force]` | Start-or-reconcile the one server: start it if down, restart it if it serves stale code or the wrong switches, do nothing if it is already correct — and leave it alone rather than end someone else's run. `--force` restarts anyway. |
| `gfso down` | Stop the one server. |
| `gfso connect` | The MCP stdio door an agent client runs. You do not type this; a client does. |
| `gfso projects [-n N] [--match S]` | The project graphs this server holds, most recently worked in first — the name is what `project=` takes, and the isolation boundary of the whole product. |
| `gfso log [-f]` | The observation panel in the terminal: signals, verdicts and dispatches as they land. |
| `gfso mcp` | A standalone MCP server with an engine of its own, for a client that must not share. Not the normal door; `connect` is. |
| `gfso serve` | Run the server in *this* process — the primitive `up` calls. |

**The UI is always at `http://127.0.0.1:8000`.** Whichever door raised the server, it is the same
single process, and it is a background service: it stays until `gfso down`, so closing your agent
session does not take the UI with it. After `pipx upgrade gfso`, the next agent session reconciles
the running server against what is installed and restarts it if they differ — an upgrade takes
effect without your doing anything, and `gfso doctor` says whether the live server is this
installation.

**Your data.** Everything is in `~/.gfso` (`gfso doctor` prints the exact path): one SQLite file per
project, plus the agent registry and the server log. It survives uninstalling the package — to start
over, stop the server and delete that directory. To remove the agent door, `claude mcp remove gfso`;
a Claude Desktop entry comes out of `claude_desktop_config.json` by hand, and the backup
`gfso setup --desktop` left beside it is the file to restore.

**One thing the UI needs the network for.** The graph view loads its rendering libraries from a CDN,
so on a machine with no internet — or one where that host is blocked — the page comes up without the
graph. Everything else, including the engine, the API and every verb, is local and works offline.
