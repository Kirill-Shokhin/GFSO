# Embeddability acceptance — the pre-registered spec

> "Embedding" here = embedding the CORE AS A LIBRARY into a foreign host (as in an embedded
> database) — nothing to do with ML vector embeddings.

> The embeddability claim ("the core drops into a foreign host as-is") is judged by THIS suite,
> fixed before any embedding attempt — not by impression. The test subject is a FRESH agent (or
> engineer) with no project context, working ONLY from the public docs (README →
> architecture.md → this file). Needing to ask the authors = a documentation defect.

## The toy host

An **asyncio service** that embeds the GFSO core as a library — deliberately mismatching every
stdlib default so the ports are exercised, not bypassed:

- **Own StoragePort**: a JSON-lines file store (not sqlite, not memory) — must implement the
  MANDATORY core including `append_audit`/`load_audit` (the port refuses it otherwise).
- **Own ClockPort**: virtual time under test control.
- **Own runtime**: NO `Engine.start()` — the host pumps its own `asyncio.Queue` and calls
  `gfso.engine.loop.process_signal` per item from its event loop (no engine threads).

## The acceptance suite (pass/fail, written first)

The embedder makes THIS suite green without modifying anything under `gfso/core/` or
`gfso/engine/` (the layer gate stays green too):

1. **Build**: a root with ≥3 nodes (one Dep seam between siblings) is created through signals
   only; every mutation appears in the audit log (`state = fold(log)`: replaying the JSONL log
   through `process_signal` on a fresh store reproduces the same states).
2. **Drive**: ASSIGN→ACCEPT→DELIVER→PASS to root DONE/PASS, respecting the Dep order (the
   consumer cannot be driven before its producer delivers).
3. **Reject**: an executor signal from a non-Del source is rejected and audited as rejected.
4. **Timeout**: with the virtual clock advanced past a deadline, the sub-FSM escalates
   (OFFERED→OVERDUE→ESCALATED) — no real waiting.
5. **Checks**: an intentionally cyclic Dep declaration is refused; a BLOCK naming a sibling
   records the discovered edge and CHECK-2 names the resulting cycle in `graph_holes`.
6. **Restart**: a new host process over the same JSONL store hydrates the audit log and
   continues (T11 over restarts).

## Protocol

1. The suite is IMPLEMENTED: `tests/acceptance_embeddability/` (the host contract lives in its
   conftest docstring). Without a host it skips with the named reason; against an attempt,
   `GFSO_EMBED_HOST=<host.py> pytest tests/acceptance_embeddability` is the verdict.
2. The embedder (fresh context) writes the host + adapters only from public docs.
3. Verdict = the suite's exit code. Questions the embedder had to ask are logged as doc-gaps —
   each one is a documentation defect to fix, regardless of the exit code.

## The embedder's wiring reference (from the first acceptance run's doc-gap log)

The first fresh-agent run went 6/6 green with zero stuck points — but logged 9 places where
the docs alone were not enough and the library source had to be read. The SCHEMAS are pointed
at, not duplicated (a copied field list is a mirror that rots); the SEMANTIC rules below were
genuinely undocumented:

**The minimal host wiring (no Engine, no threads):**

```python
from gfso.core.graph import Graph
from gfso.engine.audit import AuditLog
from gfso.engine.events import EventBus
from gfso.engine.loop import process_signal

graph, audit, events = Graph(my_storage), AuditLog(my_storage), EventBus()
# pump: for each SignalData (yours or a follow-up) —
process_signal(sd, graph, my_agent_port, None, my_sink, audit, events, validate=True)
# my_sink needs only .put(SignalData) — follow-ups (cascades, dispatch replies) land there
```

**Authoritative schema sources (read these, do not transcribe them):**
`gfso/core/types/ports.py` — the FULL StoragePort contract (mandatory abstracts + optional
extensions) and the Clock/Runner ports · `gfso/core/types/primitives.py` — SignalData / Task /
Spec / Criteria / DepEdge field sets · `gfso/core/protocol/fsm.py` — the live transition table
(the one in architecture.md is prose; the table module is the truth).

**Semantic rules a from-scratch host must reproduce:**
- **Verdict staleness**: the verifier≠executor gate compares the recorded exec-verdict's
  `iteration` against the node's current iteration — a rework stales the verdict; record shape
  = `{verdict, failed_criteria, validator, iteration, ts}` (see `Engine.record_reviewer_verdict`
  and `engine/validation.py`).
- **Timeout dedup**: the trigger fires once per `(task_id, state)` and re-arms when the state
  changes — that is what makes repeated-timeout → ESCALATED work (see
  `engine/loop.py::timeout_monitor`).
- **Checks refresh on Dep mutations**: RECORD_DEP/ADJUDICATE_DEP must refresh the seam-parents'
  CACHED checks, or a contact-discovered cycle stays recorded-but-invisible in `graph_holes`
  (`process_signal` already does this; a reimplementation of the effects layer must not lose it).

## Status

- [x] Suite implemented (red against an empty attempt)
- [x] Fresh-agent run executed (2026-07-12: 6/6 green first pass, 0 stuck points, 0 author questions; 9 doc-gaps logged)
- [x] Doc-gaps triaged → the wiring reference above (semantics documented, schemas pointed at)
- [x] **Checked on every run, not only when a volunteer host exists.** A reference host ships beside
      the suite (`tests/acceptance_embeddability/reference_host.py`) and is its default subject: a
      JSON-lines store, a virtual clock, and its own signal pump over `gfso.engine.loop.process_signal`
      — no Engine, no engine threads, and nothing imported outside the public ports. So the claim is
      now falsified by a red CI the moment the embedding contract breaks, rather than skipped.
      `GFSO_EMBED_HOST` still overrides it, which is how a fresh-agent acceptance run is judged.

  The reference host is a **client** of the ports, not a mirror of them: it duplicates no engine
  logic, so it can only break when the contract it consumes does.
