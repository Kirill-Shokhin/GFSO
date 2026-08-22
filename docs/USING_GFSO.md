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
  does not: a decomposition is an estimate `Ŝ` of a real structure `S` (§2.2), and the estimate can
  only come from contact with the domain. Nothing in the apparatus can supply that for you.

The two mix. Hand-build the parts that need your context, let `auto_decompose` refine over what you
built, and keep your ids, owners and accepted risks — a refine round folds new findings in as a
revision rather than replacing your structure.

---

## 1. Say what "done" is, before anything else

A node carries a spec, a finite set of criteria, a deadline and an owner (§10). The criteria are the
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
rests on, each with what would invalidate it (§13.1). A leaf has none. An empty register on a
decomposed node is a hole the engine will show you, not a clean bill.

## 2. Build the graph

From an agent session these are MCP tools; from a shell the same verbs are `gfso run <tool> …`; in
the UI they are the Decompose and Edit Node panels. Same engine, same audit log, whichever door.

```
create_task("api", {"name": "…", "description": "…", "criteria": [{"name": "…", "description": "…"}]})
decompose("api", children=[{"task_id": "schema", "spec": {…}}, …], mappings=[…])
map_criterion("api", "schema", "…")     # bind a child to a parent criterion after the fact
edit_criteria("api", [...])             # replace criteria, carry the rest
add_dependency("schema", "handlers", glue="handlers deserialize the published schema")
```

One difference between the doors is worth knowing before you copy a call: on the **MCP** door the
actor parameters are not yours to pass. `source` on `signal`, `reviewer` on `record_verdict`, and `agent` on `revise` /
`edit_criteria` / `edit_accepted_risks` / `reopen`, are removed from the schema
and filled with the session's own identity — everything arriving over MCP *is* the agent, so it
cannot sign an act as someone else. From the CLI, the unpinned developer door, you name the actor
yourself (`gfso run signal schema DELIVER human`).

Every parent criterion must be **mapped** to the child that delivers it. That mapping is the claim
the whole composition rests on: the parent passes exactly when its children do (§11.1), so an
unmapped criterion is a parent obligation nobody has agreed to carry.

Assign a node to someone else only when the work is really theirs. Ownership is load-bearing: a node
owned by another party moves only on *their* signals, and a node owned by a person the engine does
not know simply waits for that person — which is the honest state of the graph, not a stall.

## 3. Check the plan before writing any code

Two levels, and the engine will not let a child start executing until both are clear for its
parent's decomposition.

**Level 0 — structure.** `list_holes()` returns every unmet structural check across the graph at
once: an uncovered criterion, an orphan child, a cycle, incoherent deadlines, a missing risk
register. Fix them or declare them consciously, up front, rather than meeting them one rejected
`PASS` at a time. (`get_checks(node)` is the per-node view; the UI groups the same checks by the
failure mode each one guards.)

**Level 2 — causality (§13.4).** `review_decomposition(node)` asks, per parent criterion, whether
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
`get_review(node)` is a free read: it returns the stored verdict and whether it is still fresh for
the current shape of the decomposition.

One refine round of `auto_decompose` over your hand-built graph is worth running here for a different
reason than the review: the review repairs entailment between criteria that exist, and a refine round
is the hole-hunt for content that is missing altogether. They answer different questions.

## 4. Execute, and deliver evidence rather than intent

Work the frontier: `next_steps(root)` returns every actionable node at once, ordered, marking which
are yours and which the graph is waiting on someone else for. An empty list is not a dead graph: what
is being judged or worked on comes back under `in_flight`, what a node waits on and what would open it
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

One thing decides whether that is safe, and it is a property of your PLAN, not of the machinery: two
nodes that will write the same file are not independent, whatever their topics. Give each node its
own artifact, or declare the dependency between them — otherwise both run and the later write
silently takes the earlier one's work. If it happens anyway, `BLOCK` is how it becomes visible: the
blocked node names the one that got in its way, the edge the plan omitted appears in the graph, and
`q_Dep` counts it.

What all this costs is on the record: `/api/usage` totals the model calls per project, split by the
role that made them — decomposer, plan review, validator, executor. The UI shows it in the observation
window, beside the runs it is made of — and a graph worked by people has no calls and shows nothing
there, which is the point: the quality metrics describe the graph, the spend describes one way of
working it.

## 5. The verdict is not yours to sign

Validation fires at the **seams** — the root, and every node whose executor differs from its parent's
(§14.5). There, a `PASS` needs a verdict for the delivery that stands, **whoever signs it**: being
someone other than the executor is a rule about the signature, not evidence about the work. A stale
verdict does not count — a rework, a reopen or a revision under it makes the record about an earlier
delivery.

* From an agent session: `validate_result(task_id, workdir=…)` spawns one read-only validator that
  *runs* the criteria and reports per-criterion. You then relay `PASS`, or
  `FAIL(failed_criteria=[…])`. A report with no verdict is never a pass.
* With a registered `llm-validator`, that happens automatically on every delivery.
* With people: the reviewer presses Record verdict in the UI (`record_verdict`), which is also how you
  put your OWN observation on the record when you judged by hand — one line per criterion, saying what
  you ran and what it showed. The engine refuses a reviewer who is the node's executor, and refuses a
  verdict with nothing observed behind it.

A node whose executor is the same as its parent's is *internal* — your own private decomposition. It
self-verifies on evidence you put in the delivery, and its guarantee is carried by the seam above it.
Independent validation is for the seams, and the root is always one.

**When a criterion fails, the rework flows down, not around.** If the failed criteria are covered by
children, the engine refuses a re-delivery over an untouched subtree: contact refuted the split, not
the aggregate (§15.2). Reopen the covering child, fix it there — or revise its contract, remap it, or
add a child that covers the gap — and re-aggregate.

## 6. When reality disagrees with the plan

| Situation | Verb | What it means |
|---|---|---|
| You need something that does not exist yet | `signal(…, "BLOCK", blocker_task_ids=[…])` | Every blocker named; an unlisted one is an invisible edge (§14.2) |
| The contract is wrong | `CHALLENGE`, or `revise` / `edit_criteria` | Same node id, subtree retained — a spec change is a revision, not an abandonment |
| The goal is genuinely dropped | `CANCEL` | Cascades to the subtree; this is `⊥`, not "done" |
| A closed node has to be re-earned | `reopen(task_id)` | Only while nothing has been staked on it, and only within its reopen budget (§14.3) |

A node in `ESCALATED` is asking for a human. That is the design: the automatic path failed and says
so, rather than closing something to look finished.

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

---

## The commands

Three are for using it; the rest are for running it, and you can ignore them until you need one.

| | |
|---|---|
| `gfso setup [--desktop]` | Register the agent door, bring the server up, open the UI, report. Idempotent. |
| `gfso doctor` | What this installation is and what blocks it: version, state home, who holds the address, whether the Claude Code CLI answers, whether the assets are present. Paste it into a bug report. |
| `gfso demo [name]` | Run a shipped example; no name lists them. |
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
