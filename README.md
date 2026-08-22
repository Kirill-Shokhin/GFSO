<div align="center">

# GFSO

**Make a plan falsifiable — so when it fails, you know exactly which part was wrong.**

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.11%20%E2%80%93%203.13-blue)
![Status](https://img.shields.io/badge/status-preliminary-orange)

<img src="https://raw.githubusercontent.com/Kirill-Shokhin/GFSO/main/docs/hero.gif" alt="A task graph building itself, each node stepping through its states to Done, live" width="860">
<br>
<sub>A goal becomes a live graph; each node is driven through its states to <code>DONE</code> — the protocol as agents and humans operate the same graph. <em>(a short capture, not the full flow)</em></sub>

</div>

---

**A plan is usually an unfalsifiable story.** It fails, and no one can say which part was wrong — the estimate, the interface, a missed dependency, or the one subtask everyone assumed was trivial. The post-mortem argues. The plan offered nothing to check against.

GFSO turns a decomposition into **pre-registered, separately refutable claims** — every subtask a decidable pass/fail criterion with a named owner, every join between subtasks an explicit claim that *these children, together, make the parent*. Something breaks, and the structure points at the exact false claim and who made it — not at "the project."

Two properties carry that promise, and neither is a design choice you could tune away.

**Failure localizes.** A parent passes only when every child passes: `V(parent) = AND(V(children))`. One false leaf cannot hide behind a green parent; the failure pins to the node whose claim broke, at any depth.

**A claim cannot pass on its author's word.** Your agent reports its task done; the engine does not take its word. A `PASS` from a node's own executor is rejected at every **delegation seam** — and the result handed out of a scope is always one — until a separate validator has run every criterion against the real deliverable — here, live:

<p align="center"><img src="https://raw.githubusercontent.com/Kirill-Shokhin/GFSO/main/docs/gate.png" alt="The engine rejecting a self-signed PASS — verifier ≠ executor (§14.5)" width="820"></p>

Self-approval is not discouraged. At a seam it is structurally impossible. Inside one scope an agent does check its own work — and stakes every bit of it on the single public verdict at that scope's edge (§14.5).

---

## Why those two properties hold

GFSO is not a good design. It is **derived** — from two axioms: that goals are verifiable (A1), and that complex tasks decompose (A2). Fix those, and almost none of the protocol is a choice.

**Why `AND`, and not a weighted score?** Enumerate the sixteen binary aggregations. Require commutativity, associativity, that one failed necessary child fails the parent, and that the result not be constant. `AND` is the sole survivor (§11.3). Localization is not a feature bolted on — it is the only aggregation the axioms allow: a passing parent cannot cover a failing leaf, and the failure has exactly one address.

**Why binary acceptance, and not a percentage?** Because A1 already says it: a criterion is a decidable predicate returning pass/fail, and a conjunction of two-valued things is two-valued — the scale is fixed by the axiom, with no appeal to what you do about it (§11.2). The familiar argument — a verdict that maps to no distinct action is not a verdict, so by pigeonhole the scale collapses to two — is the *defense* against a graded scale, not the source, and it rests on there being exactly two actions (an architectural choice: granularity lives in the tree). There is no "80% done" to shelter in; "in progress" lives in the state machine, not the scale.

**Why trust that you've listed every way it can break?** A decomposition's failures are not collected from experience — they are a proven basis. Compositional validation is a computation, characterized on two orthogonal axes: the function it evaluates, and the process in time that evaluates it. Split each, and you get **seven failure modes with no room for an eighth** (§12.2–§12.8). A study of 216 public post-mortems found 0 that needed one.

**Why can't the agent just game the protocol?** Because the protocol is minimal and incentive-compatible. One handoff runs as a peer-to-peer transaction over 12 signals and 12 states; remove any signal and a specific defect returns. Drop any incentive-critical rule and honesty stops being the dominant strategy for one named party (§14, §19.1). Honesty is made rational by the rules — not asked of people.

Two things then come for free. Quality is a five-vector read straight from the execution trace, so gaming a metric costs as much as gaming the work (§21). And every decision leaves a record by construction: the way double-entry bookkeeping structurally forbids an unbalanced ledger, GFSO forbids an unrecorded decision (§22).

---

## Where the guarantee stops

None of this proves your decomposition is *correct*. It proves only that the plan is checkable, and that failure localizes.

Whether these children truly compose into that parent in the real world, the framework cannot decide — by construction. Two domains with the same formal graph can obey different real laws (Lemma 1), so the axioms do not fix which decomposition is faithful, and no amount of declaring it so grounds it (Lemma 2). That knowledge comes only from contact with the domain.

That gap is where your agent — human or LLM — carries the weight. GFSO **derives** its necessity rather than assuming it: reliable domain knowledge cannot come from the apparatus, so an agent must supply it, and the exact thing it must supply is named (§2–3). A standard would stop at prescribing. This one also *explains* why competent work already succeeded — the agent carried enough tacit structure — and *predicts*, falsifiably, where the framework stops applying — and when an agent can be swapped, measured against a faithfulness proxy independent of the outcome, without which the test is one of the protocol's verifier-separation instead (§3.6).

The framework names exactly what it guarantees and exactly what it hands to the agent. Nothing in between is waved away.

---

## What it is, and is not

**Planning ⊂ GFSO.** Classical planning and control — STRIPS, MDPs, HTN, A\*, MPC, RL — enter as a single sub-step, rewritten in GFSO's own terms: search over the estimated structure is one link in a longer chain (§6.1). The new mechanics are a narrow delta.

The value is not novelty of mechanism. It is **making-explicit** — moving decomposition out of private intuition into one axiom-derived, checkable, faithfulness-graded discipline that holds at every level. That is what makes planning falsifiable (§6.2). Scrum, in turn, is a special case under a named set of restrictions (§25.2).

It is not a task tracker — Jira tracks tasks; GFSO tracks *decisions*: who split what, on what criteria, why. Not an ERP, not a chatbot, not an autopilot.

---

## The reference implementation

The two properties above are not a paper. They run.

A reference implementation exercises the protocol end-to-end — a way to run the theory, not a finished product. One engine holds the logic; three doors are generated from one shared tool registry — an HTTP+WS API, a CLI, and an MCP surface for agents — and a web UI rides the same API, so humans and agents drive the *same* graphs and every write is mirrored live.

```bash
pipx install gfso        # or: uv tool install gfso — pip install gfso also works
gfso setup               # registers the agent door, brings the one server up, opens the UI
```

<sub>**Before the first release is tagged**, `gfso` is not on PyPI yet — install from a checkout
instead: `git clone … && cd GFSO && pip install -e .`, then the same `gfso setup`. This note comes
out with the release.</sub>

`gfso setup` is idempotent. It registers the door with Claude Code for your user — by the console script's absolute path, so it resolves from every directory and survives your leaving a virtualenv — and `--desktop` also writes the entry into Claude Desktop's configuration, keeping a backup. When something is wrong later, `gfso doctor` says what — and its output is what a bug report should carry. From a source checkout, `pip install -e .` and the same two commands.

The engine, the UI and the gate cost nothing to run: no API key, no model. The four verbs that do call one — `auto_decompose`, `review_decomposition`, `validate_result`, and delegation to agent executors — ride the [Claude Code CLI][cc] as a subprocess, so they need no key of their own and spend the usage of whatever account that CLI is signed in to. Without it on your `PATH` they report that the provider answered nothing, and everything else still works.

The gate, in one second and with no AI involved:

```bash
gfso demo human_only
```

Two people, one node: `ann` executes and signs her own `PASS`; the engine refuses it; `bob` records an independent verdict; the same `PASS` then lands and the node reaches `DONE`. Everything printed comes from the engine, not from the script.

There is **one server**, always at `http://127.0.0.1:8000`, and the everyday commands take no port — projects, not ports, are the isolation boundary. `gfso up` makes it correct and current (start it if down, restart it if it serves stale code, leave a busy one alone); `gfso down` stops it. State lives in one home per user — `~/.gfso`, or the tree in a source checkout, overridable with `GFSO_HOME`. The working loop on a real project — hand-built decomposition, the Level-2 review before code, driving the graph from an agent session — is [`USING_GFSO.md`][using].

The verifier ≠ executor gate from the opening runs in both of the system's regimes:

- **Sequential** — one agent session structures a goal (`auto_decompose` runs the search↔audit method in one call), executes the frontier itself, and after each delivery gets a verdict from a fresh read-only validator that *runs* the criteria. The gate is on the node, not on the name signing it: at a seam a `PASS` needs a verdict for the delivery that stands, from the instrument or from a person recording what they observed.
- **Delegated** — register executor and validator roles once, and assignment *is* delegation: a node assigned to a registered executor is picked up automatically, its report wrapped into the canonical signals, the validator auto-runs on delivery, and a failed criterion re-enters a bounded rework loop with the failure as feedback. Humans are never registered — a node assigned to a person simply waits for *their* signals. Mixed human/agent graphs are the normal case.

The UI (shown at the top) surfaces every write live; visual design and role workflows are out of scope at this stage.

---

## Status — preliminary

This is a preliminary release. The theory is complete at v4.0; the thing that will make it fuller and stronger — the empirical base — is in progress.

**Theory.** Formal framework (6 theorems + 8 further results), the binary scale (sourced in A1) and the uniqueness of `AND` and the 7-mode basis (complete modulo one named covering axiom), the agent-free ontology of the five links (§4), and a falsifiability register are in place. The canon is English (v4.0); the Russian working draft it was re-authored from stays frozen as the provenance record. **v4.0 is the final statement of the theory**: what remains open in it is not unfinished work but named boundaries — results about what the axioms cannot deliver — and open problems filed as such, the two kept apart by a criterion the document states and applies entry by entry (§8). Its every load-bearing claim carries what would refute it in [`falsifiability.md`][fals]; that register, not a roadmap, is what would reopen the canon. The formal spine is a Lean 4 development on the language kernel — no mathlib, no `sorry` — that audits the axiomatic surface rather than standing in for the arguments: exactly three covering axioms carry the "no further kind" results, every other postulate's placement is disclosed, and a fail-closed CI guard rejects any axiom outside that whitelist ([`formal/README.md`][formal]). Three TLA+ models are model-checked, and of the four guards CI runs, that whitelist is one — the other three hold this README, the mirrors and the code to the canon's sections, names and counts.

**Implementation.** Protocol engine, production adapters, the web UI, `auto_decompose`, independent execution validation with the verifier ≠ executor gate, the Level-2 review of a decomposition before code exists, delegation with auto-validation and bounded rework, multi-project isolation, and a shared multi-session server — all working, across 829 tests (6 of them exercise embedding the core into a foreign host, against a reference host carried in the suite; 6 more build the distribution, install the wheel into a fresh environment and drive it from a directory that is not this repository).

**Empirical.**
- **E0** — on 148 BCB-Hard tasks, explicit unit-test criteria raise Haiku 4.5's zero-shot solve rate from 29.1% to 63.5% — one attempt each, no rework loop; the spec-carrying prompt costs ×1.85 the tokens.
- **E1** — the 7-mode taxonomy against 216 public post-mortems: **0 / 216** need an eighth mode.
- **E2** — the search ↔ audit cycle raises coverage of a completeness-audited reference decomposition on 9 of 10 domains (74 → 81% average across ten diverse domains) and is productized as `auto_decompose`. Measured against a bare-built reference, this shows the cycle *converges* — not that the discipline itself pays off, which is **E3**.
- **E3** *(open)* — whether compositional validation holds on real multi-agent engineering, where a decomposition's *faithfulness* to its domain is exercised, not just its structure. Long-horizon deployment validation follows.

Each of those is recorded run by run, with its own boundaries, in [`EVIDENCE_LOG.md`][evidence]; what GFSO does to real engineering work is **not** among them — that is E3, and it is open.

The permanent boundaries are stated, not buried: a domain-silent false-`pass` cannot be caught a priori by any discipline (Lemma 1); the causal correctness of a decomposition is a characterized boundary, not an open algorithm; uniqueness of the basis is open, while on the protocol side the same question is **settled negatively over bare adequacy** (it stays open only over a fully pinned design vector) — requirements pin which exits must exist, not where they go, so a nine-state skeleton is forced and the rest is free design (§26.9).

---

## Documents

**Canon** — [`applied_gfso_v4_en.md`][canon]: the framework itself (the theory of directed action → axioms → theorems → protocol → metrics), the single source of truth. Distilled for an operator in [`method_gfso.md`][method]; each load-bearing claim typed by what would refute it in [`falsifiability.md`][fals].

**Using it** — [`USING_GFSO.md`][using]: the working loop on a real project. [`TASK_PACKET.md`][packet]: what a node must carry and the exact keys the engine reads. [`ORCHESTRATOR.md`][orch] is the same protocol as an agent session receives it.

**Onboarding** — [`applied_gfso_vision.md`][vision]: applied FSM, per-metric analysis, intuition **(in Russian)**.

**Derivation & evidence** — [`gfso_dependency_map.md`][depmap] · [`EVIDENCE_LOG.md`][evidence] · [`architecture.md`][arch]: the code-side mirror, starting from the FSM transition table that *is* the architecture.

**Machine-checked core** — [`formal/README.md`][formal]: the Lean 4 audit of the axiomatic surface — what is checked, what is checked only modulo a named covering axiom, what is out of scope, and the code ↔ canon corners, with a per-result coverage table.

**Embedding & examples** — [`embeddability_acceptance.md`][embed]: embedding the core as a library into your own host — the pre-registered acceptance suite that judges the claim, plus the embedder's wiring reference. [`gfso/examples/`][examples]: one working script per entry door (human-only · mixed · autonomous org · async precompute), shipped with the package so `gfso demo` runs them wherever it is installed.

What the engine does on your machine, and how to report a vulnerability: [`SECURITY.md`][security]. Release notes: [`CHANGELOG.md`][changelog].

---

## Citation

```bibtex
@article{shokhin2026gfso,
  title  = {GFSO: Formal Guarantees for Compositional Task Validation
            in Hierarchical Organizations},
  author = {Shokhin, Kirill},
  year   = {2026},
  note   = {Preprint in preparation}
}
```

## License

MIT

<!-- Absolute URLs: this file is also the package's PyPI description, where relative links do not
     resolve. Reference style keeps the prose readable and the addresses in one place. -->
[canon]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/applied_gfso_v4_en.md
[method]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/method_gfso.md
[fals]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/falsifiability.md
[vision]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/applied_gfso_vision.md
[depmap]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/gfso_dependency_map.md
[evidence]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/EVIDENCE_LOG.md
[arch]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/architecture.md
[using]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/USING_GFSO.md
[packet]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/TASK_PACKET.md
[embed]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/embeddability_acceptance.md
[formal]: https://github.com/Kirill-Shokhin/GFSO/blob/main/formal/README.md
[orch]: https://github.com/Kirill-Shokhin/GFSO/blob/main/gfso/mcp/ORCHESTRATOR.md
[examples]: https://github.com/Kirill-Shokhin/GFSO/tree/main/gfso/examples
[security]: https://github.com/Kirill-Shokhin/GFSO/blob/main/SECURITY.md
[changelog]: https://github.com/Kirill-Shokhin/GFSO/blob/main/CHANGELOG.md
[cc]: https://claude.com/claude-code
