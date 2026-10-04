# GFSO — the core definition, on one page

> What GFSO is, what it is not, and what it does and does not claim — deliberately one page. The
> canon is `applied_gfso_v4_en.md`; this is the orientation that fits in a reader's head first, and
> a working reference for anyone writing code, prompts or documents against the framework.

---

## In one sentence

**GFSO is a formal language for the minimum a verifiable task-handoff
transaction must carry**, derived from two axioms (verifiability +
decomposability). Each element of the basis is shown necessary; that the
basis is the ONLY one cannot be derived from inside — a named boundary
(§20.8, §20.7, `formal/README.md`) — "minimal", not "proven unique".

Analog: TCP/IP for hierarchical work coordination, or Codd 1970 for
relational databases. Tractable math; the framing enables a domain.

## Unpacked

GFSO is a **mathematically defined** structure (with primitives,
operations, laws), **minimal** (nothing can be removed
without losing expressiveness), describing **what must be present** in
one handoff of a task from an issuer to an executor **so that the
handoff can be verified and composed**. It is **derived**, not assembled —
from two simple statements: that goals are verifiable and
that complex work decomposes — with three covering axioms, relative to
eleven named design decisions (§20.5), the choices it does make. If those two statements hold for a
domain, GFSO describes its handoffs — the basis minimal, and complete as far as the search has gone (§7.5). A goal within one agent's
capacity is inside but needs none of it; a goal failing A1, or above capacity with no split into parts within
it, is outside, and that boundary is explicit (§2.1).

The unit of analysis is **one handoff transaction**, not a project,
not a process, not a team. Everything else (hierarchy, multi-agent,
organization) is composition of such transactions. One goal's graph
composes them under one root, whose verdict is the verdict on the goal
(§15.2).

What it must carry: a Spec, a finite set of decidable Criteria, a
Deadline, a Delegation, and — when it is decomposed — an explicit
ACCEPTED_RISKS register (the register belongs to the split, so a leaf
has none: §9.2), Dependencies, and — where a criterion's securing is not plain conjunction — the composition function CHECK-7 then uses (§2.4, §9.6). Drop the criteria, the
register, the deadline or the dependencies and a failure mode (of the six
proven exhaustive as a basis, modulo the covering CA1 — §8.8) loses its
guard; drop the delegation and the handoff loses its accountable party
(Ch. 2), which guards no mode.

When a critic attacks one part, the theory has a defense ready —
constructive counterexamples for minimality, exhaustive case splits
for completeness, the §2.1 boundary for "doesn't apply to my case".
If those defenses don't satisfy the critic, the disagreement is
about scope, not about the math.

---

## What GFSO IS

1. A **formal protocol** for the Issuer ↔ Executor transaction
2. A **discipline shift**: criteria-articulation responsibility moves
   from Executor (who currently has to guess) to Issuer (who must
   specify before delegation)
3. A **standardized vocabulary** (12 signals, 11 FSM states, 6 failure
   modes) usable across any hierarchical work system
4. A **compositional law**: `V(parent) = AND(V(children))` under
   explicit correctness conditions (joint sufficiency + non-redundancy).
   Derived, not postulated.
5. A **theory-model**, not only a standard: planning is absorbed as one
   rewritten sub-step (planning ⊂ GFSO), the agent's necessity as
   source of domain content is *derived* (not assumed), and the primary
   value is **making-explicit** — moving decomposition discipline out of
   private, unchecked intuition into one axiom-derived, consistency-checkable,
   faithfulness-graded system. The new *mechanic* is narrow; the
   value is the universalized checkable discipline (§19.2–19.3, §3–4).

---

## What GFSO is NOT

- NOT a productivity tool. "What metric does it boost?" is the wrong
  question (category mismatch — same as "what metric does TCP/IP boost?")
- NOT a project-management methodology (it sits at a lower layer)
- NOT "yet another standard" at ISO 9001 / Scrum level. GFSO is derived
  from axioms; those are chosen conventions.
- NOT an algorithm, an ML technique, or "agentic framework v2"
- NOT a retry loop. The loop is a fallback when criteria are weak.
  When criteria are explicit, the loop is dormant. **The loop is not
  where GFSO's value sits.**

---

## What GFSO uniquely provides over its parts

Decomposition exists. Tests exist. Contracts exist (DBC, Meyer 1992).
Audit trails exist. What none of them give together:

| Piece | Where GFSO uniquely formalizes it |
|---|---|
| Compositional validation | Theorem 1 with explicit correctness conditions |
| Failure taxonomy | 6 FM, a basis provably exhaustive modulo the covering CA1 (falsifiable claim) |
| Spec quality forcing function | Forced binary V — defects pushed out, no "warning" |
| Protocol vocabulary | 12 signals (minimal) × 11 states (induced; the table forced over the log, up to REWORKING's attribution label, by the four clauses of §13.4 — three carrying adopted parts — with Inv-8's adopted edge clause, relative to two design decisions, the alternative reading of the decision's routes and named per-state inputs, §20.5 (d)) |
| Self-measurement | Q metrics computed from the protocol's log alone, bar the post-hoc runs of q_V's later-fail term |
| Adaptive stratification | §19.5, derived from deadline coherence along D (§4.5 item 6) under four named premises (concreteness, sensitivity, environmental stationarity across levels, routing of divergence to CHALLENGE) |

---

## Two axioms — and the honest postulate closure

- **A1 — Verifiability**: any directed activity has a finite set of
  decidable predicates that return pass/fail in finite time
- **A2 — Decomposability**: some activities exceed a single agent's
  capacity and require splitting

Almost everything else is a consequence — but not *everything*, and the canon
refuses the tidy version: "how many postulates does GFSO have" has no single
number (§20.5). Four kinds:
- **Three covering axioms** — CA1 (the 6 FM, §8.2), CA-Morris (the 3 verification
  levels, §9.1), CA-Links (the 5 constitutive links, §5.3). Each carries a
  "there is no further kind" claim; none follows from A1 ∧ A2.
- **Definitional** — A1, A2 themselves, |Act| = 2 and the d3/d4 source space (its exhaustiveness
  derived by nested excluded middle), baked into the types.
- **Hypothesis-form** — dischargeable, carried in theorem signatures (act-surjectivity
  and act-injectivity for |L| = 2's defense; no-declaration (Lemma 2's regress), no-luck and
  not-apparatus — the arms of agent necessity; the single clock — the last one already discharged).
- **Adopted** — eleven design decisions (the deadline, the uniqueness of Del, Inv-4's reading,
  terminality, R′'s form, the moment of R′'s threshold, no expiry attributed to a party, `max_iterations` as a packet field, a split's admission
  and a root's creation as acts, an implementation's default deadline, q_V's scope), the clauses Ch. 12 adopts with its
  invariants (§12.11–§12.13), and one alternative reading; the forced protocol machine is relative to two of the decisions (Inv-4's
  reading, terminality), to the adopted clauses and to the alternative reading.

Outside the four kinds stands one covering principle the formal development does not carry: the AI layer's
three inference types (§17.2).

A goal for which A1 ∧ A2 hold needs GFSO. A goal within one agent's capacity is inside but needs none
of it; a goal failing A1, or above one agent's capacity with no split into parts within it, is out of
scope (§2.1).

---

## Where GFSO applies

Membership is read off the goal, not the domain (§2.1, §16.17); the rows give the typical case.

| | Inside the model? | Why |
|---|---|---|
| Hierarchical work with multiple agents | YES, needed | its goals typically meet A1 and exceed one agent's capacity |
| Compliance-heavy domains (medical, aviation, banking) | YES, needed | decidable acceptance and an audit trail are already required |
| Multi-team code projects | YES, needed | decomposition + cross-team interfaces |
| Multi-agent LLM systems | YES where the goal has decidable criteria | A1 is a property of the goal, not of the agents |
| Solo work on a task within one agent's capacity (one act) | YES, not needed | inside, A2's split unneeded (§2.1) |
| Exploratory product development (Scrum's domain) | YES | A1 weak, criteria articulated late, not ¬A1; Scrum's practice a relaxation of GFSO (§19.4) |
| Creative work, open-ended exploration with no verifiable outcome | NO | A1 fails |

---

## Common drift traps (each one has been walked into)

1. **"GFSO loop adds the value"** — NO. The loop is a fallback for weak
   criteria. With explicit criteria on a competent model, the loop is
   dormant. Value sits in Issuer-side spec articulation + compositional
   validation across decomposition.

2. **"GFSO is alternative to Scrum"** — not as an account: Scrum's
   components are GFSO's, with some freedoms restricted and some
   requirements relaxed — the risk register, the per-decision log,
   the deadline rules (§19.4). Where that is cheap (exploratory, small
   team, low stakes), Scrum is fine. Where it is costly (large org,
   multi-team, compliance), Scrum breaks and GFSO's missing pieces matter.

3. **"This is just TDD/contracts/composition"** — NO at the integration
   level. DBC describes the atom (predicate on function). GFSO describes
   the molecule (structure of the transaction itself). And only GFSO
   has the formal correctness conditions for decomposition + 6 FM
   completeness + standardized protocol.

4. **"Bench result +34pp validates GFSO"** — NO. That result is about
   the Issuer-side discipline of explicit criteria — a known principle
   in spirit (TDD/DBC). It is good empirical signal for ONE component
   of GFSO. It is not validation of: 6 FM exhaustiveness, compositional
   theorem, multi-agent decomposition benefit, q-metrics calibration.

5. **"Test it on a benchmark"** — only if criteria for that benchmark
   are real GFSO criteria (semantic predicates), not just hidden test
   pairs. competitive programming domains (LiveCodeBench) are mostly
   wrong shape; unit-test-based (BCB) is closer but still measures
   adjacent things.

---

## Where the work actually targets

The under-optimized space of **human/agent work coordination at scale**.
Algorithms and neural nets are heavily optimized; the protocol of "how
two parties agree on what counts as done" remains ad hoc in 2026.

The optimization opportunity here is plausibly larger than another
percentage point on a ML benchmark — but uncoordinated, uneven, slow
to converge because there's no formal substrate. GFSO is an attempt
at that substrate.

---

## What is settled empirically, and what is not

Empirically, **E1 (postmortem taxonomy validation) is closed** (0/216
cases need a mode outside the six). **E2 (decomposition convergence) ran**:
it established the convergence *method* — bare SEARCH ⊕ gfso
AUDIT, iterated, productized as `auto_decompose()` — but **not** the method's value
over bare (coverage-to-a-bare-built reference can't read it; that is **E3**).
**E3 (multi-agent compositional validation, under execution) ran its first pair in which a false "done" can arise
at all** (`EVIDENCE_LOG` §13.15, §13.16). Earlier cells handed the arm its visible suite — the issuer's work already
done — so the arm's own check coincided with the oracle and saturation followed (`EVIDENCE_LOG` §13.14, §13.12-ter); they are not a
reading on value. With the suite withheld on one task (`c_compiler`, one contract digest, n=1 per arm): bare 0.632
held-out, the same agent over the product 0.816, and 0.903 once each criterion carried a pinned decision procedure.
No tree closed in that third run: the root carrying the decomposition ended ESCALATED and a childless third root
passed — the recovery gap the canon's v4.1 closes (§12.5). An independent 205-probe corpus, written from the
contract before any procedure existed, finds 15 real divergences in that workspace against 34 in the previous one;
all 15 are FM-3 false passes on a criterion that names the behaviour — 9 where the pinned procedure is blind to it,
6 contract requirements the executor filed as accepted risks after the first FAIL, which §9.2 does not admit as
exclusions. None is a requirement no criterion writes — at this atomic root no failure mode but the goal's
setting (§8.3) — which says little here: one criterion names the whole contract. Five things moved at once — procedures, the root authored by `auto_decompose`, a rework bound of 3, two
replacement roots, a stronger validator model. The first delegated cell (`json_parser`, `EVIDENCE_LOG` §13.17) validated every seam with
its pinned procedures; its plan was a linear chain, so parallel execution is untested. E3's own question — how often
a false "done" arises with the structure and without it, no suite handed over — has one run per arm and no rate yet.

---

## Reading order, and the test that settles an argument

`applied_gfso_v4_en.md` the Introduction + Ch. 1, 2 and 7 (the axioms and the composition theorem) is the framework
itself; `EVIDENCE_LOG.md` §4 is what has and has not been shown.

The operational test for any claim made in GFSO's name: **can it be stated as "if X, then Y,
falsifiable by Z"?** If not, whatever is being done empirically is not this framework.
