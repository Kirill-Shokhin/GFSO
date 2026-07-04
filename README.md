<div align="center">

# GFSO

**Make a plan falsifiable — so when it fails, you know exactly which part was wrong.**

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Status](https://img.shields.io/badge/status-preliminary-orange)

<img src="docs/hero.gif" alt="A task graph building itself, each node stepping through review → in-progress → validating → done, live" width="860">
<br>
<sub>A goal becomes a live graph; each node is driven through its states to <code>DONE</code> — the protocol as agents and humans operate the same graph. <em>(temporary capture; a full walkthrough is coming)</em></sub>

</div>

---

**A plan is usually an unfalsifiable story.** It fails, and no one can say which part was wrong — the estimate, the interface, a missed dependency, or the one subtask everyone assumed was trivial. The post-mortem argues. The plan offered nothing to check against.

GFSO turns a decomposition into **pre-registered, separately refutable claims** — every subtask a decidable pass/fail criterion with a named owner, every join between subtasks an explicit claim that *these children, together, make the parent*. Something breaks, and the structure points at the exact false claim and who made it — not at "the project."

Two properties carry that promise, and neither is a design choice you could tune away.

**Failure localizes.** A parent passes only when every child passes: `V(parent) = AND(V(children))`. One false leaf cannot hide behind a green parent; the failure pins to the node whose claim broke, at any depth.

**A claim cannot pass on its author's word.** Your agent reports its task done; the engine does not take its word. A `PASS` from a node's own executor is rejected until a separate validator has run every criterion against the real deliverable — here, live:

<p align="center"><img src="docs/gate.png" alt="The engine rejecting a self-signed PASS — verifier ≠ executor (§6.5)" width="820"></p>

Self-approval is not discouraged. It is structurally impossible.

*New here? The one-page primer is [`CORE.md`](docs/CORE.md).*

---

## Why those two properties hold

GFSO is not a good design. It is **derived** — from two axioms: that goals are verifiable (A1), and that complex tasks decompose (A2). Fix those, and almost none of the protocol is a choice.

**Why `AND`, and not a weighted score?** Enumerate the sixteen binary aggregations. Require commutativity, associativity, and that one failed necessary child fails the parent. `AND` is the sole survivor (§3.3). Localization is not a feature bolted on — it is the only aggregation the axioms allow: a passing parent cannot cover a failing leaf, and the failure has exactly one address.

**Why binary acceptance, and not a percentage?** A verdict that maps to no distinct action is not a verdict. Keep only the values that change what you do, and the scale collapses to pass/fail by the pigeonhole principle (§3.2). There is no "80% done" to shelter in; "in progress" lives in the state machine, not the scale.

**Why trust that you've listed every way it can break?** A decomposition's failures are not collected from experience — they are a proven basis. Compositional validation is a computation, characterized on two orthogonal axes: the function it evaluates, and the process in time that evaluates it. Split each, and you get **seven failure modes with no room for an eighth** (§4.2–4.8). A study of 216 public post-mortems found 0 that needed one.

**Why can't the agent just game the protocol?** Because the protocol is minimal and incentive-compatible. One handoff runs as a peer-to-peer transaction over 12 signals and 12 states; remove any signal and a specific defect returns. Drop any incentive-critical rule and dishonesty becomes a dominant strategy for one party (§6, §11). Honesty is made rational by the rules — not asked of people.

Two things then come for free. Quality is a five-vector read straight from the execution trace, so gaming a metric costs as much as gaming the work (§13). And every decision leaves a record by construction: the way double-entry bookkeeping structurally forbids an unbalanced ledger, GFSO forbids an unrecorded decision (§14).

---

## Where the guarantee stops

None of this proves your decomposition is *correct*. It proves only that the plan is checkable, and that failure localizes.

Whether these children truly compose into that parent in the real world, the framework cannot decide — by construction. Two domains with the same formal graph can obey different real laws (Lemma 1), so the axioms do not fix which decomposition is faithful, and no amount of declaring it so grounds it (Lemma 3). That knowledge comes only from contact with the domain.

That gap is where your agent — human or LLM — carries the weight. GFSO **derives** its necessity rather than assuming it: reliable domain knowledge cannot come from the apparatus, so an agent must supply it, and the exact thing it must supply is named (§18.10). A standard would stop at prescribing. This one also *explains* why competent work already succeeded — the agent carried enough tacit structure — and *predicts*, falsifiably, when an agent can be swapped and where the framework stops applying.

The framework names exactly what it guarantees and exactly what it hands to the agent. Nothing in between is waved away.

---

## What it is, and is not

**Planning ⊂ GFSO.** Classical planning and control — STRIPS, MDPs, HTN, A\*, MPC, RL — enter as a single sub-step, rewritten in GFSO's own terms: search over the estimated structure is one link in a longer chain (§17.4). The new mechanics are a narrow delta.

The value is not novelty of mechanism. It is **objectification** — moving decomposition out of private intuition into one axiom-derived, checkable, faithfulness-graded discipline that holds at every level. That is what makes planning falsifiable (§17.5). Scrum, in turn, is a special case under relaxed axioms (§17.2).

It is not a task tracker — Jira tracks tasks; GFSO tracks *decisions*: who split what, on what criteria, why. Not an ERP, not a chatbot, not an autopilot.

---

## The reference implementation

The two properties above are not a paper. They run.

A reference implementation exercises the protocol end-to-end — a way to run the theory, not a finished product. One engine holds the logic; four front-ends are generated from it — a web UI, an HTTP+WS API, a CLI, and an MCP surface for agents — so humans and agents drive the *same* graphs and every write is mirrored live.

```bash
pip install -e ".[mcp]"

# register the MCP server — starts a shared engine + live UI at http://localhost:8000
claude mcp add gfso -- python -m gfso.mcp.connect
```

Or, without an agent, run just the web UI:

```bash
gfso serve
```

The verifier ≠ executor gate from the opening runs in both of the system's regimes:

- **Sequential** — one agent session structures a goal (`auto_decompose` runs the search↔audit method in one call), executes the frontier itself, and after each delivery gets a verdict from a fresh read-only validator that *runs* the criteria. Its own `PASS` is not enough; the gate demands the independent verdict.
- **Delegated** — register executor and validator roles once, and assignment *is* delegation: a node assigned to a registered executor is picked up automatically, its report wrapped into the canonical signals, the validator auto-runs on delivery, and a failed criterion re-enters a bounded rework loop with the failure as feedback. Humans are never registered — a node assigned to a person simply waits for *their* signals. Mixed human/agent graphs are the normal case.

The UI (shown at the top) surfaces every write live. It is a working reference for exercising the protocol, not a finished product — visual design and role workflows are out of scope at this stage.

---

## Status — preliminary

This is a preliminary release. The theory is close to complete; the two things that will make it fuller and stronger — the empirical base and the English canon — are both in progress.

**Theory.** Formal framework (6 theorems + 8 further results), impossibility results (binary scale, `AND`, the 7-mode basis), the agent-free theory-model (§18.10), and a falsifiability register are in place. The canon is a Russian working draft; the English translation is pending.

**Implementation.** Protocol engine, production adapters, the web UI, `auto_decompose`, independent execution validation with the verifier ≠ executor gate, delegation with auto-validation and bounded rework, multi-project isolation, and a shared multi-session server — all working, under 248 tests.

**Empirical.**
- **E0** — on 148 BCB-Hard tasks, explicit unit-test criteria raise Haiku 4.5's zero-shot solve rate from 29.1% to 63.5% at the same compute.
- **E1** — the 7-mode taxonomy against 216 public post-mortems: **0 / 216** need an eighth mode.
- **E2** — coverage of a completeness-audited reference decomposition rises 74 → 81% and 78 → 96% across runs of the search↔audit cycle, productized as `decompose()`.
- **E3** *(open)* — whether compositional validation holds on real multi-agent engineering, where a decomposition's *faithfulness* to its domain is exercised, not just its structure. Long-horizon deployment validation follows.

The permanent boundaries are stated, not buried: a domain-silent false-`pass` cannot be caught a priori by any discipline (Lemma 1); the causal correctness of a decomposition is a characterized boundary, not an open algorithm; uniqueness of the basis is open (§18.9).

---

## Documents

**Canon** — [`applied_gfso_v3.md`](docs/applied_gfso_v3.md): the framework itself (axioms → theorems → protocol → metrics → theory-model), the single source of truth. Distilled for an operator in [`method_gfso.md`](docs/method_gfso.md); each load-bearing claim typed by what would refute it in [`falsifiability.md`](docs/falsifiability.md).

**Onboarding** — [`CORE.md`](docs/CORE.md): one-page primer and common-objection answers (read first). [`applied_gfso_vision.md`](docs/applied_gfso_vision.md): applied FSM, per-metric analysis, intuition.

**Derivation & evidence** — [`gfso_dependency_map.md`](docs/gfso_dependency_map.md) · [`EVIDENCE_LOG.md`](docs/EVIDENCE_LOG.md) · [`architecture.md`](docs/architecture.md).

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
