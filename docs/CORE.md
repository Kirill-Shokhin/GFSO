# GFSO — core definition (for agents and future-self)

> Read this BEFORE writing code, prompts, or commits. One page, on purpose.
> If you find yourself confused about what GFSO is, re-read this file.

---

## In one sentence

**GFSO is a formal language for the minimum a verifiable task-handoff
transaction must carry**, derived from two axioms (verifiability +
decomposability) and proven minimal.

Analog: TCP/IP for hierarchical work coordination, or Codd 1970 for
relational databases. Tractable math; the framing enables a domain.

## Unpacked

GFSO is a **mathematically defined** structure (with primitives,
operations, laws), the **smallest possible** (nothing can be removed
without losing expressiveness), describing **what must be present** in
one handoff of a task from an issuer to an executor **so that the
handoff can be verified and composed**. It is **not chosen** — it is
**derived** from two simple statements: that goals are verifiable and
that complex work decomposes. If those two statements hold for a
domain, GFSO necessarily describes its handoffs. If they don't, GFSO
doesn't apply, and that boundary is explicit (§9).

The unit of analysis is **one handoff transaction**, not a project,
not a process, not a team. Everything else (hierarchy, multi-agent,
organization) is composition of such transactions.

What it must carry: a Spec, a finite set of decidable Criteria, a
Deadline, a Delegation, and — when it is decomposed — an explicit
ACCEPTED_RISKS register (the register belongs to the split, so a leaf
has none: §13.1), Dependencies plus a composition function. Drop any of
these and a specific failure mode (of the seven proven exhaustive
as a basis, modulo the covering CA1 — §12.8) becomes unavoidable.

When a critic attacks one part, the theory has a defense ready —
constructive counterexamples for minimality, exhaustive case splits
for completeness, the §9 boundary for "doesn't apply to my case".
If those defenses don't satisfy the critic, the disagreement is
about scope, not about the math.

---

## What GFSO IS

1. A **formal protocol** for the Issuer ↔ Executor transaction
2. A **discipline shift**: criteria-articulation responsibility moves
   from Executor (who currently has to guess) to Issuer (who must
   specify before delegation)
3. A **standardized vocabulary** (12 signals, 12 FSM states, 7 failure
   modes) usable across any hierarchical work system
4. A **compositional law**: `V(parent) = AND(V(children))` under
   explicit correctness conditions (joint sufficiency + non-redundancy).
   Derived, not postulated.
5. A **theory-model**, not only a standard: planning is absorbed as one
   rewritten sub-step (planning ⊂ GFSO), the agent's necessity as
   source of domain content is *derived* (not assumed), and the primary
   value is **making-explicit** — moving decomposition discipline out of
   private, unchecked intuition into one axiom-derived, consistency- and
   faithfulness-checkable system. The new *mechanic* is narrow; the
   value is the universalized checkable discipline (§6.1–§6.2, §2–3).

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
| Failure taxonomy | 7 FM, a basis provably exhaustive modulo the covering CA1 (falsifiable claim) |
| Spec quality forcing function | Forced binary V — defects pushed out, no "warning" |
| Protocol vocabulary | 12 signals (minimal) × 12 states (induced) |
| Self-measurement | Q metrics computed from audit graph alone |
| Adaptive stratification | §25.1, derived from deadline coherence along D (§3.4 item 6) + A1, under a named premise (environmental stationarity across levels) |

---

## Two axioms — and the honest postulate closure

- **A1 — Verifiability**: any directed activity has a finite set of
  decidable predicates that return pass/fail in finite time
- **A2 — Decomposability**: some activities exceed a single agent's
  capacity and require splitting

Almost everything else is a consequence — but not *everything*, and the canon
refuses the tidy version: "how many postulates does GFSO have" has no single
number (§1.4). Three kinds:
- **Three covering axioms** — CA1 (the 7 FM, §12.8), CA-Morris (the 3 verification
  levels, §13.4), CA-Links (the 5 constitutive links, §4.2). Each carries a
  "there is no further kind" claim; none follows from A1 ∧ A2.
- **Definitional** — A1, A2 themselves, and |Act| = 2, baked into the types.
- **Hypothesis-form** — dischargeable, carried in theorem signatures (Lemma 2,
  luck-instability, the single clock — the last one already discharged).

If A1 ∧ A2 hold for a domain, GFSO applies. If not, GFSO is out of scope.

---

## Where GFSO applies

| | Applies? | Why |
|---|---|---|
| Hierarchical work with multiple agents | YES | A1 ∧ A2 both hold |
| Compliance-heavy domains (medical, aviation, banking) | YES | Audit trail + binary V already required by law |
| Multi-team code projects | YES | Decomposition + cross-team interfaces |
| Multi-agent LLM systems | YES | This is what we're testing |
| Solo work on a single task | OVERHEAD > VALUE | A2 doesn't apply |
| Exploratory product development (Scrum's domain) | OPTIONAL | Special case of GFSO with constraints (§25.2) |
| Creative work without verifiable criteria | NO | A1 fails |
| Pure research / open-ended exploration | NO | A1 fails |

---

## Common drift traps (things I have already gotten wrong)

1. **"GFSO loop adds the value"** — NO. The loop is a fallback for weak
   criteria. With explicit criteria on a competent model, the loop is
   dormant. Value sits in Issuer-side spec articulation + compositional
   validation across decomposition.

2. **"GFSO is alternative to Scrum"** — NO. Scrum is a special case of
   GFSO under specific constraints (§25.2). Where Scrum's constraints
   are cheap (exploratory, small team, low stakes), Scrum is fine.
   Where they're costly (large org, multi-team, compliance), Scrum
   breaks and GFSO's missing pieces matter.

3. **"This is just TDD/contracts/composition"** — NO at the integration
   level. DBC describes the atom (predicate on function). GFSO describes
   the molecule (structure of the transaction itself). And only GFSO
   has the formal correctness conditions for decomposition + 7 FM
   completeness + standardized protocol.

4. **"Bench result +34pp validates GFSO"** — NO. That result is about
   the Issuer-side discipline of explicit criteria — a known principle
   in spirit (TDD/DBC). It is good empirical signal for ONE component
   of GFSO. It is not validation of: 7 FM exhaustiveness, compositional
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

## Status check before extending

Before adding more theory, more code, more experiments — ask:

- Does this address one of E1, E2, E3, or a §26 open problem?
- If not, am I just polishing? Polishing isn't progress.
- Does this validate or falsify a specific claim? Or just illustrate one?

Empirically, **E1 (postmortem taxonomy validation) is closed** (0/216
cases need an 8th failure mode). **E2 (decomposition convergence) ran**:
it established the convergence *method* — bare SEARCH ⊕ gfso
AUDIT, iterated, productized as `decompose()` — but **not** the method's value
over bare (coverage-to-a-bare-built reference can't read it; that is **E3**).
The next move is **E3 (multi-agent compositional validation, under execution)** —
falsifiable, the biggest signal-per-effort available now.

---

## When in doubt

- Re-read this file
- Then re-read `applied_gfso_v4_en.md` §1 + §9–§11 (axioms + composition theorem)
- Then re-read `EVIDENCE_LOG.md` §4 (what's actually proven vs not)

If still confused, the operational test is: **can I state the claim
being tested in the form "if X, then Y, falsifiable by Z"?** If not,
you're not doing GFSO empirically — you're doing something else and
calling it GFSO.
