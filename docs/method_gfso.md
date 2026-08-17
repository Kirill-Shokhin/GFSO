# THE GFSO CONSTITUTION

> **Layer = METHOD.** A two-layer system: the canon (*proves and derives* — the theory of directed
> action + the ontology + the methodology, `applied_gfso_v4_en.md`: §2–§8, §13.5) → **the method =
> the constitution (*governs*; this document)**. The constitution **reduces the canon** — a scattered
> collection of theorems and proofs — **into a single base of strict ENTITIES (definitions) and LAWS
> (rules)**.
> *(In v4.0 the theory leads as Part I and the methodology stands as its own chapter (§7) — the two
> layers remain: the canon proves, the constitution governs; methodological references point straight
> into the canon.)*
>
> **The proofs are removed.** They live in the canon as the justification owed to a skeptic; the
> constitution does not re-prove them. But the entities and laws keep the **full canonical rigor**:
> every article is stated so that two readers cannot diverge on what it requires. Canon references
> (of the form «§12.1», «FM-1.d», «Lemma 1») are given as **pointers** to the justification, not as
> proofs.
>
> The constitution **describes every GFSO action** (carrier: human, LLM, hybrid, machine) at every
> level of decomposition, independently of who reads it and in which domain it is applied.
>
> **Register.** The exposition is neutral-ontic: an article states *what* correct directed action is
> and *what holds* within it; it does not prescribe a sanction. Where an article's condition does not
> hold, the corresponding **failure mode** is named — a diagnostic fact about the action, not a
> punishment. Correct action IS that in which every condition of Section II holds.
>
> **Provenance.** Every article is marked with its source: **`[DERIVED]`** — the article follows from
> the theory-model / the canon (it is derivable); **`[ADDITION]`** — the article is a justified design
> choice, *not* derivable from the theory, stated with *where* and *why* it enters (canon §10: "the
> concrete form is a consequence OR a justified design decision"; §10.1: Fundamental/Derived). The
> derivational core and the named additions are thereby kept apart.

---

## PREAMBLE

This document describes directed action in the domain delimited by its jurisdiction (Art. I.15). It
defines (Section I) the entities of which every directed action consists, and derives in their terms
the domain conditions (A1, A2 — Art. I.14) and the jurisdiction itself (Art. I.15); it states
(Section II) the laws — the conditions that hold in correct action; it names (Section III) the
permanent boundaries whose "closure" is a logical error; and it establishes (Section IV) the rule of
its own amendment.

The constitution does not describe practice and does not prescribe techniques. It states that to
which practice and techniques answer. The implementation layer (12 signals, the 12-state FSM, the Q
metrics, the AI layer — canon §14, §15) is one admissible carrier of this description, not its
content; any other carrier is applicable if and only if the articles of Sections I–II hold in it.

Every decision in the domain is expressible in the constitution's entities and checkable by its laws.
A decision not expressible in these entities is either outside the domain (Art. I.15) or the
¬holding of a law (Section II) — a failure mode; there is no third case.

---

## SECTION I. ENTITIES

The entities are defined strictly and unambiguously: two readers cannot diverge on what each denotes.
Where the canon left a formulation implicit, the reading that opens no loophole is chosen; such a
choice is marked `[ADDITION]` in the article itself. First the field, the goal, the task, the
decomposition, the capacity κ and contact `Contact` (Art. I.1–I.13: the entities, among which
`Contact` is the only operation that reads the domain); then A1, A2 — the axioms, read as the
existence conditions of `Contact` (Art. I.14); then the jurisdiction — where the constitution applies
— as a reference to A1∧A2 (Art. I.15). A1/A2 are stated *after* `Contact` deliberately: that is how
their sense shows — the conditions under which the seam works; **their axiomatic status is
nevertheless primary** (§9), and the reading through the seam is a second reading, not a repeal
(theory-model §I.8 / canon §2.6).

**Art. I.1 (the field: S, Ŝ, the gap Ŝ\S).** `[DERIVED]` (ontology §2.2, Lemma 1 §2.5).
- **S — the real composition/transition structure of the domain.** `S` is the relation of real joint
  sufficiency: `(t,{tⱼ}) ∈ S` ⟺ really completing all children `tⱼ` really attains the parent `t` by
  *its* criteria (§9, §11.1). `S` is real, contingent and **not given in advance** (Lemma 1, §2.5):
  it is not a catalogue of routes and holds no "optimal path".
- **Ŝ — the built estimate of S.** `Ŝ` is the explicit model of `S` that the actor builds and acts
  over. The edges of `Ŝ` are *beliefs* in a real chaining (§2.2).
- **The gap Ŝ\S.** An edge `e ∈ Ŝ\S` is an edge `Ŝ` asserts and `S` denies: a passage the map
  promised and the domain does not carry (a "wall", §2.2). Every failure of compositional validation
  is at bottom a *used* gap edge `e ∈ Ŝ_used \ S` (Art. II.7).

**Art. I.2 (the goal: G real, Ĝ posited).** `[DERIVED]` (Link-1, §4).
- **G — the real goal region** of the domain (ontic, in general not given to the actor exactly).
- **Ĝ — the posited goal waypoint** in `Ŝ`: the place where the actor *believes* `G` lies. `G` and
  `Ĝ` are distinct; their divergence is node unfaithfulness (Art. I.9). The goal **underdetermines**
  the decomposition: one and the same `G` admits many faithful `D` (§3.4, multiplicity).

**Art. I.3 (the task).** `[DERIVED]`/`[ADDITION]` (mixed provenance by component — see below:
`spec`/`criteria` = `[DERIVED]` from A1; `deadline` = `[ADDITION]`; §10). A task
`t = (spec, criteria, deadline)`, where `spec` is the direction, `criteria = {c₁,…,cₖ}` is a finite
nonempty set of decidable predicates `cᵢ: Result → {pass, fail}`, and `deadline` is the time bound
(§10). Every `cᵢ` is a predicate **over Result** (the outcome of execution), not a description of an
action: a formulation of the form "do X" / "X is configured" / "the runbook is written" is not a
criterion (it is `spec`-direction or self-report, not a predicate about the outcome — Art. II.1).
`spec` and `criteria` are `[DERIVED]` from A1 (directedness + checkability, Art. I.14). `deadline` as
a primitive is `[ADDITION]`: **where** — a component of the task; **why** — the theory does not derive
time-as-a-primitive, but without an explicit `deadline` activity is indistinguishable from inactivity
(a non-terminal state without a bound is a loophole; canon §10 marks the deadline a design decision
explicitly). `deadline` is coherent per Art. II.4-Dep.

**Art. I.4 (decomposition, subgoal, joint, leaf).** `[DERIVED]` (D from A2, §10; the joints — §5).
- **Decomposition** `D: T → P(T)`. The graph of `D` is a DAG (a cycle ⟹ infinite recursion ⟹ an A1
  violation). `D(t) = ∅` ⟺ `t` is atomic (a leaf).
- **Subgoal** — an element of `D(t)`.
- **Joint (necessary passage)** — a state/region through which *every* successful path from the start
  to the goal must pass (a separator of the reachability flow, §5). Separatorhood is a
  **counterfactually checkable predicate** (§5): a subgoal `B` is a separator ⟺ removing it
  disconnects `G` from the start — there is no successful path to `G` bypassing `B`
  (`x₀ ∉ Capt_{S∖B}(G)`). The joints are ontic (a fact of the domain, not the actor's choice);
  granularity *beyond* the joints is the actor's free choice. A faithful decomposition cuts at the
  joints.
- **A checkability carrier (an instrument)** — the tooling that supplies a truth-maker for a parent's
  criterion (logs, dashboards, a runbook, harness). It is **not** a child subgoal of `D(t)`: it is
  part of the contact apparatus (Art. I.11), not a passage in `S`. It does not enter joint
  sufficiency / non-redundancy (Art. I.5) but is registered separately as contact tooling with its
  own A1 justification. Declaring a checkability instrument a child of the decomposition is a category
  error (FM-1.e).
- **Leaf (atom, the κ boundary)** — a subgoal attainable and checkable within the capacity κ of one
  executor in one act of contact (Art. I.6; §5). Tree depth is **agent-relative**: a larger κ ⟹ a
  flatter tree (§3.4, termination).

**Art. I.5 (joint sufficiency, non-redundancy; and the written couplings).** `[DERIVED]` (the
definition of correctness, §10; the couplings — §3.4 form list / §7 FORM interior). A decomposition
`D(t) = {t₁,…,tₙ}` is **correct** under **exactly two** conditions (§10; §11.1: joint sufficiency +
non-redundancy are *precisely* the conditions under which compositionality holds; §12.8: "exactly two"
is **derived**, not postulated):
1. **Joint sufficiency:** `∀cᵢ ∈ criteria(t): [∀tⱼ ∈ D(t): V(tⱼ)=pass] → cᵢ=pass`. All children `pass`
   ⟹ every parent criterion is satisfied.
2. **Non-redundancy:** `∀tⱼ ∈ D(t): V(tⱼ)=fail → ∃cᵢ ∈ criteria(t): cᵢ=fail`. Removing any child
   breaks the chaining; there is no ballast subgoal.

*Why exactly two, and where the couplings live (do not conflate two different cuts, §7).* The
canon keeps the *relations* among the children **outside** the definition of correctness on purpose:
membership defects → **FM-1**, relation defects → **FM-2**, and that separation is what grounds the
denotational leg of CA1 (§12.8). Folding a third condition into correctness would make §11.1's
"precisely" false. The written couplings are therefore a **separate** requirement of well-posedness,
not a clause of §10-correctness:

3′. **Connectivity (the couplings written explicitly)** — a member of the **FORM interior**
    {connectivity/Dep, φ-composition, non-redundancy} of the coarse cut (§7; Art. II.11), and the
    form-list item of §3.4: every relation under which the result of `tₐ` enters the check of `tᵦ` is
    written out as a `Dep` edge (Art. I.8); the children need not be orthogonal, but the links between
    them are not hidden. Its violation is FM-2 (mutual satisfiability, CHECK-8) or the hidden-coupling
    line FM-1/FM-5 (Art. II.3), not a defect of §10-correctness.

**Art. I.6 (capacity κ).** `[DERIVED]` (κ as a field parameter — the carrier of A2, §5). `κ` is the
largest region/step one executor is able to directly realize-and-check in one act of contact (§5).
`κ` is a property of the actor/contact, not of the domain `M`. A transition exceeding κ ⟹ the
transition is not a leaf ⟹ it must be split (Art. II.2). `κ` is the carrier of A2's capacity premise.

**Art. I.7 (criterion).** `[DERIVED]` (a consequence of A1 + |L|=2, §11.2, §12.2). A criterion `cᵢ` is
a decidable predicate over the result whose only semantic content is its **truth** relative to the
domain (a consequence of A1 + |L|=2, §11.2, §12.2). A criterion has no second property: a value that
does not change the `intervene/¬intervene` decision is not a criterial value. Truth is
**two-directional**: a criterion can be untrue in either of two directions (false-PASS and false-FAIL
— Art. II.8).

**Art. I.8 (dependency Dep, the seam).** `[DERIVED]` (an independent primitive from T+D, §10.1
"Independent"; the seam — §5). `Dep ⊂ T × T` is an acyclic relation. `(tₐ, tᵦ) ∈ Dep` if
`criteria(tᵦ)` references the result of `tₐ`. Coherence:
`(tₐ, tᵦ) ∈ Dep ⟹ deadline(tₐ) < deadline(tᵦ)` (§10). **The seam (the integration edge)** is the place
where the result of one subgoal is fed to the input of another; a seam carries its own integration
claim (Art. II.5). `Dep` carries information about causal order not contained in `D` (an independent
primitive).

**Art. I.9 (faithfulness: `Ŝ_used ⊆ S`, three axes).** `[DERIVED]` (§2.2; the three axes — §5.5).
**Faithfulness** is `Ŝ_used ⊆ S` — every *used* edge of `Ŝ` is real (§2.2). Faithfulness unfolds along
three orthogonal axes (§5):
- **Edge:** `(B,B′) ∈ Ŝ` is faithful ⟺ `B′ ⊆ Capt_S(B)` (the believed passage coincides with the real
  chaining). An unfaithful used edge = `(B,B′) ∈ Ŝ\S`.
- **Node:** the waypoint `B ∈ Ŝ` answers to a real region/separator of `S`. Node unfaithfulness = the
  posited `Ĝ` (or any other waypoint) does not answer to the real `G`/separator.
- **Scale:** the coarsening `∼_G` (ACCEPTED_RISKS) is a correct bisimulation on the G-relevant algebra.
  Scale unfaithfulness = the coarsening leaks (two equivalent states have distinguishable G-relevant
  futures).

Node and scale unfaithfulness **generate** edge unfaithfulness, not conversely; the edge axis is the
general form. Faithfulness is **opened only by contact** (Art. I.11) and is **not certified by the
apparatus** (Lemma 1, SINGLE-SEAM — Art. III.1).

**Art. I.10 (ACCEPTED_RISKS).** `[DERIVED]` (the requirement of an explicit assumption — §13.1, §13.2;
the concrete record schema — a chosen explicit form). `ACCEPTED_RISKS` is an explicit finite list of
accepted risk factors; every entry carries `factor`, `estimate (P, impact)`, `justification`,
`invalidation_condition`, `predictability_verdict` (§13.1; the predictability verdict — Art. II.6). An
entry missing any of these fields is incomplete (as is an entry without an `invalidation_condition`).
`ACCEPTED_RISKS` converts an implicit assumption `P=0` into an explicit `P≈ε` with a justification; an
explicit assumption is refutable, auditable and aggregable. A decomposition without an
`ACCEPTED_RISKS` register is incomplete by definition (Art. II.6).

**Art. I.11 (contact `Contact`, verdict, composition V=AND).** `[DERIVED]` (Lemma 1/SINGLE-SEAM —
§2.4–§2.5; V=AND — Thm 1–2, §11.1, §11.3). `Contact` is the operator whose existence conditions are
A1∧A2 (Art. I.14).
- **Contact `Contact`** — the only operation of the whole field that reads `S` (SINGLE-SEAM, the
  formalization of Lemma 1, §2.3–§2.5). On a used edge `e ∈ Ŝ_used`:
  `Contact: (e, [e∈S]) ↦ (verdict, Ŝ′)` — the actor puts the edge to the domain, the domain returns
  the fact `[e∈S]` as `verdict ∈ {pass, fail}`, the actor revises `Ŝ → Ŝ′`. All the rest of the
  apparatus `𝒜` (decidable criteria, `V`, the 7 FM, CHECK, search over Ŝ) are functions `Ŝᵏ → Ŝ` and
  do not syntactically read `S`.
- **Verdict** `V: T → {pass, fail, ⊥}`, defined through the criteria:
  `V(t)=pass ⟺ ∀cᵢ ∈ criteria(t): cᵢ=pass`. `⊥` is not a third value of the scale but the absence of a
  value (until checking completes); the verdict scale is binary (Art. II.1).
- **Composition V=AND.** Under a correct `D`: `V(t)=pass ⟺ ∀tⱼ ∈ D(t): V(tⱼ)=pass` (Thm 1, §11.1).
  `AND` is the only admissible aggregation under binarity and an absorbing `fail` (Thm 2, §11.3).

**Art. I.12 (the agent: a carrier-function, not a subject).** `[DERIVED]` for the agent-as-scope-bundle
(§4); **the uniqueness of `Del`** — `[ADDITION]` (see below). The agent is **not a primitive** but an
emergent scope-bundle: a window over the process, a block partition of the tree of units assigned as
one scope of responsibility (§4). Nothing in the ontology distinguishes "agent A's units" from "B's"
except the scope boundary. The necessary *carrier* of the domain content of `Ŝ` is relocated into the
links {build-Ŝ, contact} (Lemma 1: the apparatus does not generate `Ŝ`; content and faithfulness enter
only through these links).
- **Delegation** `Del: T → A` — assigning each task an accountable agent (§10). **Uniqueness** (exactly
  one per task) is `[ADDITION]`: **where** — on the relation `Del`; **why** — from A2 the theory
  derives only "every subgoal has an executor", not the *number*; uniqueness is chosen because under
  an ambiguous `Del` (two parties accountable for one task) accountability diffuses and the
  attribution of a failure (Art. II.10) loses its addressee — a loophole (canon §10 marks uniqueness a
  design decision explicitly).
- **Scope/accountability.** A failure is attributed to the node with the broken compositional claim
  (Art. II.10), not to the "lowest" executor.
- **The plane `{T,D,Dep,V}` is authority-free by construction.** The only primitive referencing agents
  is `Del: T → A`; the signatures of `T,D,Dep,V` do not mention agents. Hence authority is not a
  primitive but an **emergent edge** of the `Del` hierarchy (§10, Remark; the seam gate is §14.5), and separation of duties / IC is a
  **boundary term** on the `Del` seam: the `verifier≠executor` gate fires at the seam, not in the plane
  (Art. II.14).

**Art. I.13 (the five constitutive links).** `[DERIVED]` (§4; completeness — covering, Art. III.2).
Directed action *is* a chain of five irremovable links (§4): **Link-1 goal** (`G⊆X`, directed) ·
**Link-2 build-Ŝ** (informed) · **Link-3 plan `D` over Ŝ** (structured) · **Link-4 execution** (rollout
in `S`, actual) · **Link-5 contact** (the verdict from `S`, real). Removing any link yields non-action.
Contact is **homogeneous modulo delay**: during planning every node is an untested hypothesis (an edge
of `Ŝ`); during execution contact flows up from the leaves, each node checked against its own realized
aggregate. The completeness of the five links is covering (Art. III.2), not closed.

**Art. I.14 (A1, A2 — axioms; their second reading = the existence conditions of `Contact`).**
`[DERIVED]` (theory-model §I.8; canon §2.6, §9). A1 and A2 are **primary axioms** (§9); their **second
reading** (§2.6) gives the conditions under which the single seam `Contact` (Art. I.11) works,
extracted from the field `(M,U,f,x₀,G,S,Ŝ,D)` defined without them. Both are **read** as the conditions
of the existence and nontriviality of `Contact` (§2.6: `Contact` exists and is nontrivial ⟺ A1∧A2):

- **A1 (verifiability) = solvability of `Contact`'s OUTPUT.** For `Contact` to return a verdict
  `[e∈S] ∈ {pass, fail}` in finite time (else `Contact` is inert), a finite set of conditions is
  required, each checkable in finite time with outcome `pass`/`fail` — this is **exactly A1** (§9),
  extracted as a requirement on `Contact`'s interface. Half (i) *decidability* is co-extensive with
  `Contact`'s signature; half (ii) *domain-correctness* (the verdict coincides with the real `[e∈S]`)
  is not supplied by the apparatus (SINGLE-SEAM) — it stays open (FM-3, Art. III.1). A1 asserts the
  *existence* of such a set, not *which one*.
- **A2 (decomposability at a capacity bound) = κ-constructibility of `Contact`'s INPUT.** `Contact`'s
  input is an edge directly contact-checkable within the capacity `κ` (Art. I.6). A transition of
  "size" > κ is not a leaf ⟹ it admits a split into jointly-sufficient κ-leaves ⟹ recursion ⟹ a tree.
  The condition "every above-κ transition admits such a split" is **exactly A2** (§9), extracted as
  the constructibility condition of `Contact`'s κ-bounded input. Exceeding capacity is a *cost*
  premise: splitting is forced by the cost of whole execution, and that cost is constitutive of the
  action.

*The honest residue (theory-model §I.8):* the reading is not seed-free and the residue is named — A1.ii
is not certifiable by the apparatus (= FM-3, Art. III.1); κ is a property of the actor/contact (not
derived from M), and the decomposability clause is ≈ A2 itself, moved out of the field's definitions
into the condition of a nontrivial `Contact`. This is a **status change** (postulate → interface
condition of `Contact`), not a generation of A1/A2 from an empty field. The axiomatic status of A1/A2
(§9) **remains primary** — the second reading is the deep view, not a repeal (§2.6, anti-laundering: to
be held louder than the recast itself). What it gives is a *reason*: A1/A2 are the conditions of
`Contact`'s nontriviality.

**Art. I.15 (jurisdiction — the domain of applicability).** `[DERIVED]` (the A1∧A2 domain boundary —
§9; Art. I.14). The constitution applies where contact `Contact` exists, i.e. where A1∧A2 hold
(Art. I.14). This is the short definition of the domain; the axiomatics themselves are §9 and Art. I.14:
- **Inside the domain (A1∧A2).** The action is directed at a checkable (A1) goal beyond the capacity of
  one executor (A2); all articles of Sections I–II hold.
- **Outside the domain.** Under ¬A1 (no outcome checkable in finite time) there is no contact
  `Contact`: the constitution is inapplicable. Under ¬A2 (the goal is within one executor's capacity)
  the recursion is degenerate: the constitution is superfluous (applicable but not necessary). Outside
  the domain no law of Section II is demanded.
- **Reformulability and its limit.** A goal not satisfying A1 is brought into the domain by
  reformulation into a checkable predicate; the reformulation is itself directed action and is
  described by the constitution. The domain boundary (A1∧A2 membership) is one of the two irreducibly
  empirical loci (Art. III.5; the second is faithfulness, Art. III.1): it is established by contact
  with the domain, not by declaration.
- **Membership is a fact, not a choice.** An action directed at a checkable goal beyond one executor's
  capacity belongs to the domain regardless of whether its carrier declared it so. A false declaration
  of being outside the domain is a ¬holding, exposed by contact (an outcome that failed to materialize
  while a checkable goal was present) — a failure mode, not a choice-exemption.

---

## SECTION II. LAWS

Every law is an article-condition: what holds in correct action, and which failure mode (FM-k)
corresponds to ¬that condition. The failure mode is given with a canonical pointer to the failure mode
or the section — as a diagnostic fact, not a sanction. Where a law is accompanied by a permanent
boundary whose "closure" is a logical error, a reference to Section III is given. Every article is
marked with its provenance (`[DERIVED]` / `[ADDITION]`).

**Art. II.1 (verifiability — A1).** `[DERIVED]` (A1, Art. I.14; §11.2). In correct action every goal
and every subgoal carries `criteria` — a finite nonempty set of decidable predicates returning
`pass`/`fail` in finite time. The verdict scale is binary: `V(c) ∈ {pass, fail}`; `⊥` is the absence of
a value, not a third outcome (§11.2). An inability to determine `pass`/`fail` at the moment of checking
is a defect of the `criteria`, and in correct action it is pushed into the open (recorded), not masked
by an intermediate "warning" (§11.2). *Failure mode:* an undecidable predicate in the role of a
criterion — outside the domain (Art. I.15), or FM-3 (if the predicate issues a verdict not reflecting
the domain — Art. II.8).

- **(a) A criterion is a predicate over the result, not an action.** `criteria` are predicates OVER THE
  RESULT of execution, not descriptions of actions. A formulation of the form "do X" / "X is
  configured" / "the runbook is written" is not a criterion — a criterion is a checkable statement
  about the OUTCOME (e.g. "the 2→1 rollback dry-run makes the probe green"). An action-in-the-role-of-a-
  criterion is an A1 defect (a self-report of having acted instead of a verdict about the result — a
  mock, Art. II.5).
- **(b) Completeness of `criteria` relative to `spec`.** A parent's `criteria` must be **jointly
  sufficient for the `spec`** (not merely mutually consistent). The test: *does there exist a `Result`
  passing ALL `cᵢ` yet failing the `spec` direction?* If yes — the `criteria` are incomplete: the gap
  `spec \ criteria` is node unfaithfulness of Ĝ (Art. I.9) and is subject to declaration in
  ACCEPTED_RISKS; this is FM-1 at the level of GOAL-SETTING (not decomposition). Without this condition
  a thin set of `criteria` (e.g. a single predicate) honestly passes the whole constitution, while the
  `V=AND` cascade (Art. II.4) is vacuously sufficient for an underdetermined goal.
  **The split of the probe's residue `spec \ criteria`** (derivable from Art. II.9 + §13.4 Level 1/2):
  the probe has two halves. (i) **Formal incompleteness** — the `cᵢ` do not cover the *declared*
  `spec` direction: caught over `Ŝ` (Level 1, Art. II.11), decidable before contact — a closable FORM
  check. The half-(i) probe is presented not passively but **generatively** (admissible per Art. II.5
  anti-mock + Art. II.7, the FM basis as a generator of the dimensions of loss): for the `spec`
  direction, the axes of possible loss/distortion of the outcome are enumerated — by the 7-FM basis as
  a checklist of dimensions (argument / value / rule / phase, Art. II.7) — and for each axis a covering
  `cᵢ` OR an ACCEPTED_RISKS entry is presented. Declaring half (i) closed without the generative
  enumeration of axes over the `spec` (rather than over the already-written thin set of `cᵢ`) is a
  **¬holding** (vacuous-AND, `c_check ≈ 0`): a probe over a poor `Ŝ` finds nothing and passes the
  letter falsely. (ii) **Domain completeness of the `criteria` set** — that the list of conditions
  really exhausts the `spec` FOR THIS DOMAIN (e.g. whether the list of accountable events for this
  transaction is complete): this is a hypothesis about `S` (Art. II.9), NOT closable a priori by any
  probe over `Ŝ`; it is subject to a mandatory ACCEPTED_RISKS entry with a `predictability_verdict`
  (Art. I.10, II.6) and is checked only by contact (Art. I.11). Declaring half (ii) established without
  contact (the probe was run over `Ŝ`, nothing was found ⟹ "the criteria are complete") is a false
  certification of faithfulness (Art. III.1; ¬Art. III.1). Residue (ii) is a faithfulness boundary, not
  a FORM check: treating Art. II.1.b as wholly FORM-closable is a ¬holding.

**Art. II.2 (decomposability — A2).** `[DERIVED]` (A2, Art. I.14; Art. I.6). A goal exceeding the
capacity κ of one executor (Art. I.6) is, in correct action, split into subgoals within κ; the split
recurses to the leaves. A leaf is a subgoal directly realizable-and-checkable in one act of contact.
*Failure mode:* declaring a subgoal beyond κ a leaf (unexecutable as an atom) — FM-6 (indefinability at
the start) or forced false atomicity.

**Art. II.3 (a correct decomposition = a chain of necessary passages).** `[DERIVED]` (the definition of
correctness, Art. I.5; §10). A decomposition is correct if and only if both conditions of Art. I.5 hold
(§10; §11.1 — these two are *precisely* the conditions of compositionality): (1) the children are
jointly sufficient for the parent's criteria; (2) no child is removable without loss of the chaining
(non-redundancy — tested against the *parent's* criteria: removing the child breaks ≥1 criterion
`cᵢ ∈ criteria(t)`, and **not** the child's own injected criterion, Art. I.5.2). A faithful
decomposition cuts at the joints (Art. I.4): a subgoal that is not a necessary passage is removable ⟹
ballast (¬non-redundancy); a missed necessary passage ⟹ a coverage hole.

**Alongside correctness (a separate requirement, not a third clause — §7, Art. I.5.3′):** the graph `D`
is acyclic and the connectivity of the couplings is written out in `Dep` — a member of the FORM
interior, whose violation is its own failure mode. *Failure modes:* ¬(1) — FM-1 (insufficiency; FM-1.f where the required criterion was never written, §12.2); ¬(2) —
FM-1.e (redundancy); a cycle — FM-4 (via the DAG violation); a hidden coupling — FM-2 where it makes the children's criteria jointly unrealizable as written, FM-5 otherwise (§12.2);
incompatible criteria of two children — FM-2 (Art. II.4).

**Art. II.4 (composition — V=AND).** `[DERIVED]` (Thm 1–2, §11.1, §11.3). The parent's verdict under a
correct `D` is the conjunction of the children's verdicts: `V(t)=AND({V(tⱼ)})` (Thm 1). `AND` is the
only admissible aggregation (Thm 2); the absorbing element is `fail` (any child `fail` ⟹ the parent
`fail`). In correct action `fail` propagates up the tree. **Dep coherence:**
`(tₐ,tᵦ) ∈ Dep ⟹ deadline(tₐ) < deadline(tᵦ)`. *Failure modes:* non-propagation of `fail` — FM-4;
violation of the Dep deadlines — FM-5; incompatibility of two children's criteria (`criteria(tₐ)`
demands `X`, `criteria(tᵦ)` demands `¬X`) — FM-2.

**Art. II.5 (the seam — anti-mock).** `[DERIVED]` (§3.4 *The anatomy of a decomposition*; §5.2;
CHECK-7). In correct action every `Dep` edge (a seam, Art. I.8) carries a criterion whose truth-maker
is the *real adjacent pair* (the actual output of one node fed to the actual input of the adjacent
one), not two separate self-reports (§3.4; §5.2). The integration implication `(⋀ children) ⟹ parent`
is written out as a **separate, per-child-attributable, falsifiable claim**. A criterion able to pass
while the link is really broken is a mock and is not a criterion. *Failure modes:* the integration edge
is absent from `Ŝ_used` (forgotten glue) — **FM-1** (a coverage hole; the false PASS is a consequence,
"there is nothing to lie about", §3.4); the integration edge is present but insensitive (a mock) —
**FM-3 false-PASS** (Art. II.8; the faithfulness residue — Art. III.1); the children do not formally
entail the parent's criterion while the mapping exists — **FM-1.d** (`⋀criteria(tⱼ) ⊭ cᵢ`, CHECK-7).

**Art. II.6 (ACCEPTED_RISKS — declaring assumptions and exclusions).** `[DERIVED]` (§13.1, §13.2). In
correct action every assumption the decomposition rests on, and every excluded factor, is declared in
`ACCEPTED_RISKS` (Art. I.10); a decomposition without `ACCEPTED_RISKS` is incomplete. For every
assumption whose failure would break the goal, a fork holds (§13.2):
- **A declared failure** of an assumption that turned out false is **not a decomposition defect**: the
  boundary of the claim was named (a licensed ACCEPTED_RISKS entry).
- **An undeclared but foreseeable** leak is **FM-1.b**: a decomposition defect (a forgotten mitigation
  child).

The predictability criterion (FM-1.b ↔ the domain boundary, Art. I.15) is operational and pinned to the
domain's norm (§13.2): an event yields FM-1.b if a *faithful* `Ŝ` for the domain would have carried the
mitigation (an observable S-regularity exists: a precedent / an industry standard / the practice of
competent neighbors); it lies on the domain boundary only if *no* faithful `Ŝ` could contain it (no
S-regularity, genuinely unprecedented). The evidence of unpredictability is borne by whoever asserts it
(§13.2): predictability is presumed.

This criterion is carried operationally as a `predictability_verdict` field of an ACCEPTED_RISKS entry
(Art. I.10) — a Constitution field, not a canon schema element: §13.1 fixes four fields, and what the
canon mandates is STD-2's burden of proof, which this field records per factor: for each factor exactly one of two is stated explicitly — (i) an S-regularity exists
⟹ omitting the mitigation is FM-1.b, and the factor requires a mitigation child; or (ii) there is no
S-regularity ⟹ a named domain boundary. The burden of proving unprecedentedness is on the one
asserting it; unproven unprecedentedness defaults to foreseeable ⟹ FM-1.b. An entry without a
`predictability_verdict` is incomplete (as one without an `invalidation_condition`).

**The node gap Ĝ≠G — a mandatory ACCEPTED_RISKS entry.** If the posited waypoint `Ĝ` is demonstrably ≠
the real goal `G` along the node axis (Art. I.9), that gap is a **mandatory** ACCEPTED_RISKS entry with
its own `invalidation_condition`; omitting it is FM-1.b.

**Grouping correlated factors (FM-1.c).** `[DERIVED]` (§13.3 STD-3; §12.2, the FM-1 sub-taxonomy).
Correlated accepted factors with a common root (e.g. drought → water shortage → plant disease) are not
counted scattered but **grouped into a component** with a common root cause; each component carries its
own risk node (CHECK-5, Art. II.11 Level 0). Ungrouped correlated factors are **FM-1.c**
(`missing-risk-grouping`): the aggregate estimate `P(≥1 of the component)` is distorted (the factors are
counted independent while they share a root), and risk coverage is under-estimated. The grouping method
(factorization, clustering, an expert taxonomy) is an implementation choice, not part of the law.

*Failure modes:* omitting the declaration of a foreseeable factor — FM-1.b; omitting the register
entirely — FM-1 (CHECK-4); an entry without a `predictability_verdict`, or omitting the node gap Ĝ≠G —
FM-1.b; ungrouped correlated risks — FM-1.c (CHECK-5).

**A goal's scope boundary ≠ a risk (do not conflate with ACCEPTED_RISKS).** `ACCEPTED_RISKS` is a
register of uncertain *events* (factors with an estimable `P`, rolled up as `P(≥1)=1−∏(1−Pᵢ)`, governed
by STD-2 predictability). A conscious **scope boundary of the goal** (a capability out of scope — a
"payment gateway" for the goal "billing computation") is of another kind: it has no materialization `P`
(`estimate`/`predictability_verdict` would be vacuous), and it is governed not by predictability but by
*the goal's own criteria* through **CHECK-1** (§13.4). A capability out of scope that no goal criterion
demands is simply *absent* (optionally a non-risk **SCOPE tag** on the goal, for making-explicit, where
the exclusion is unobvious); a capability a goal criterion does demand is a coverage hole **FM-1.a**
(not ACCEPTED_RISKS). Scope extension = a re-ASSIGN of the goal with new criteria (§14.4 Inv-1), after
which CHECK-1 forces a child. ⟹ an "excluded factor" in Art. II.6 = a risk exclusion (an event); a scope
boundary does not go into the risk register.

**The auditor's discriminator (the P test).** It separates a risk from a scope boundary **mechanically,
not by eye**: does the item carry an estimable *probability of materialization* `P`? There is a `P` →
it is a risk *event* → `ACCEPTED_RISKS` (with a `predictability_verdict`, entering the roll-up). There
is no `P` (it is a design decision "we are not building this") → it is a scope boundary → a question of
the goal's criteria / CHECK-1, NOT `ACCEPTED_RISKS`. The auditor applies exactly this test; an item
without a `P` placed in the risk register is a category error (caught by the test).

**Dividing scope between siblings = Dep/a seam, NOT an exclusion field (for the decomposer).**
`[DERIVED, nontrivial — stated explicitly, since both the author and the decomposer read it otherwise]`.
On a node the area of activity is set by **its `criteria` alone** (`V(node)` = its criteria; another's
criterion is not in its V — "being harnessed to someone else's" is impossible). "What the neighbor
does" is NOT written out as an exclusion on this node — it is a **`Dep` edge / a seam** (the
producer-neighbor → this consumer-node). The executor **satisfies only the criteria**; `Dep` is a
complementary element of the picture (the seam's provenance), NOT a second obligation to reconstruct
"what comes into me / goes out". Keeping the criteria coherent with `Dep` is the **decomposer's** work
(CHECK-7 sufficiency, CHECK-8 consistency): if a node's criteria are written consistently with the
seam, the criteria suffice for the executor. **The integration (seam) criterion** — the one no sibling
closes alone (FM-1.d, anti-mock Art. II.5) — belongs to the **parent** (`V(parent)` demands the real
fusing of the outputs, not merely each of them separately). Therefore a child node has NO separate
"scope exclusion field": there are `criteria` (the area) + `Dep` (the interface to siblings) +
`ACCEPTED_RISKS` (the risks). The three "what I do not do" — the division (=`Dep`), the risk
(=`ACCEPTED_RISKS`), the scope boundary (= the goal level / CHECK-1) — live in different places, not in
one bloated field on the node.

**Art. II.7 (the root of failure).** `[DERIVED]` (§2.2, §12.4, §12.8; the 7-FM basis). Every failure of
compositional validation is at bottom a used gap edge `e ∈ Ŝ_used \ S` (§2.2). The seven failure modes
refine *where in the computation of validation* that edge bites: at the arguments (FM-1, FM-2), the
values (FM-3), the rule (FM-4) or the time phase (FM-5 during, FM-6 before, FM-7 after). The taxonomy
`{FM-1…7}` is a **complete independent basis** of failures (§12.4, §12.8): any failure violates ≥1 of
them; each is realizable in isolation (§12.5); one failure may violate several at once (conjunctions
are expressible — it is a basis, not a partition into singletons). *It holds:* every exposed failure
belongs to ≥1 FM of the basis; a failure attributable to none is either outside the domain (Art. I.15)
or a refutation of the basis's completeness (Art. III.2), and there is no third case (E1: 0/216
required an 8th FM).

**Art. II.8 (the truth of the verdict — two-directional).** `[DERIVED]` (FM-3 two-sided, §12.2, §11.2;
Art. I.7). In correct action a node's verdict reflects the domain (Art. I.7). Untruth of the verdict in
either of two directions is **FM-3**: *false-PASS* — `pass` where the domain gives `fail` (the false
pass propagates upward); *false-FAIL* — `fail` where the domain gives `pass` (over-rejection). Both are
defects of the value's single property (truth). A false-FAIL that additionally breaks propagation is
FM-3 ∧ FM-4. *Boundary:* the domain-silent false-PASS (a present but insensitive integration edge) is
**caught a priori by no discipline** (Art. III.1) — it is the faithfulness residue, a permanent
boundary, not a hole to be patched.

**Art. II.9 (faithfulness is opened only by contact).** `[DERIVED]` (SINGLE-SEAM, Lemma 1, §2.4–§2.5).
The correctness of a decomposition in the sense of faithfulness (`Ŝ_used ⊆ S`, Art. I.9) is **not
certified by the apparatus** (SINGLE-SEAM, Lemma 1, §2.5). No a-priori check over `Ŝ` establishes
faithfulness; its only verifier is contact `Contact` (Art. I.11). Every claim about a real chaining is
an untested hypothesis until contact. *It holds:* in correct action faithfulness is not declared
established without contact; declaring "checked" with respect to domain-correctness without execution
is a false certification (a ¬holding). *Boundary:* this article is **not closable** by strengthening the
apparatus (Art. III.1).

**Art. II.10 (attribution of a failure).** `[DERIVED]` (§3.5 *Two-sided attribution*; §18.3). A
failure is attributed to the node with the broken **compositional claim**, not to the "lowest" executor
(§3.5). Attribution is two-directional as a consequence of explicit composition:
- **Forward (top-down):** an upper node's error compounds multiplicatively down the tree
  (`‖eₙ‖ ≤ (Λ·γ)ⁿ‖e₀‖`, §18.3).
- **Backward (bottom-up):** a low-level refutation (a child's failure breaks ≥1 parent criterion) is
  attributed along the explicit composition to the node with the broken claim; that node carries the
  failure signal (§3.5; FM-7).

A top-level planner lives in compositional claims: its decomposition is a pre-registered hypothesis, and
the failure "the children passed, the goal did not arrive" is attributed to it (FM-1.d / FM-1.b), not to
the executors. *Failure modes:* attributing a failure to an agent instead of the node with the broken
claim; the absence of a channel by which the node carries the failure signal — FM-7.

**Art. II.11 (the check over Ŝ — FORM — is mandatory and cheap).** `[DERIVED]` (§13.4; the nine CHECKs). In
correct action every decomposition passes, before execution, an a-priori CHECK over `Ŝ` verifying the
**FORM** — the internal well-posedness of the decomposition (§13.4). FORM's **load-bearing** interior is
{connectivity/Dep, φ-composition, non-redundancy} — the members that carry the composition claim; the
form list's remaining members (decidable criteria, the register, deadline coherence) are a-priori over
`Ŝ` by the same test and so FORM as well (§7;
Art. I.5.3′ — *not* the §10 definition of correctness, which has exactly two conditions: these are two
different cuts of the failure space and the canon forbids conflating them, §7). The following hold:
- **The Syntactic level (Level 0; topology, CHECK-1, 1b, 2–6):** coverage of the criteria, the DAG,
  deadline coherence, the presence of a nonempty ACCEPTED_RISKS, risk nodes (one per component of
  correlated risks, Art. II.6 — FM-1.c), delegation of the leaves.
  **CHECK-1.5 (a passage ≠ a checkability carrier)** (derivable from Art. I.4; admissible per
  Art. IV.1.1 — one of the Constitution's own additions: the canon's battery is **nine** CHECKs, this
  one and its siblings are operational, not canon members): for each subgoal `tⱼ ∈ D(t)` it is presented that `tⱼ` is a **passage** in `S` (a change
  of the domain's state toward `G`), not a checkability carrier. The test: if the output of `tⱼ` is
  consumed only by the parent's criterion as a truth-maker (it supplies a verdict) but does not enter as
  a state into the `Capt_S` of the next joint — it is **contact tooling** (Art. I.4), registered
  separately with its own A1 justification, and declaring it a child of `D(t)` = **FM-1.e**. The
  instrument's separator counterfactual (col A) is invalid: removing the tooling disconnects the *check*
  of `G`, not the attainment of `G`; such a counterfactual passes col A falsely (the tooling plausibly
  separates the *checkable* `G` from the start) and does not legalize `tⱼ` as a passage. `c_check ≈ 0` ⟹
  it **always holds**.
  **Plus CHECK-separatorhood:** every subgoal `tⱼ ∈ D(t)` is a necessary passage (a separator, Art. I.4)
  — and separatorhood is presented by a **separator counterfactual** (removing `tⱼ` disconnects `G` from
  the start, `x₀ ∉ Capt_{S∖tⱼ}(G)`, Art. I.4). A milestone without a presented separator counterfactual
  is **FM-1.e ballast** — *even carrying a `[DERIVED]` mark* and *even carrying its own criterion* (a
  decorative milestone with an injected criterion is not legalized by it). The cost `c_check ≈ 0` ⟹ it
  **always holds**.
  **The bridging rule separator↔non-redundancy** (derivable from Art. I.5 + Art. II.1.b): the two
  removability tests of a milestone live over different referents — non-redundancy (Art. II.3) over the
  *posited* `criteria` of the parent, CHECK-separatorhood over the *real* `G`. The coincidence of the
  two tests (breaks `cᵢ` ⟺ disconnects `G`) is a property of correct goal-setting; their divergence is
  FM-1 at the level of GOAL-SETTING (not decomposition). The bridging rule is presented not
  passively-conditionally but as a **mandatory two-column artifact per node** for each subgoal
  `tⱼ ∈ D(t)`: **(col A)** the separation counterfactual `x₀ ∉ Capt_{S∖tⱼ}(G)`; **(col B)** the concrete
  parental `cᵢ` that breaks when `tⱼ` is removed (non-redundancy, Art. II.3). The incompleteness
  detector fires: if **A** is presented for `tⱼ` but **col B is empty** (a separator exists, no `cᵢ`
  breaks) — this is **not** a recording defect and does **not** legalize/ballast `tⱼ`, but a
  **mandatory firing of the DETECTOR of `criteria` incompleteness**: the criteria do not cover a real
  separator ⟹ **return to Art. II.1.b** (the gap `spec \ criteria`, half (i)) and adding the missing
  `cᵢ` is **mandatory before admission to Level 1**. A global assertion "there is no ballast / the tests
  coincide" without a per-node col B presented for every `tⱼ` is a **¬holding** (`c_check ≈ 0` ⟹ both
  columns are free; not presenting them = the detector did not fire, a loophole). Using the softer of
  the two tests to issue a verdict about a milestone when they diverge is a ¬holding.
  **The reverse test of the completeness of the separator list** (derivable from Art. I.4 + Art. II.1.b
  + Art. II.9; symmetric to the bridging rule): the bridging rule closes the gap `spec \ criteria` (a
  real separator without a `cᵢ`); the reverse test closes the gap *between* joints (a real separator
  without a milestone). For every pair of consecutive joints `(tⱼ, tⱼ₊₁)` in `Dep` it is presented that
  the transition between them is itself κ-atomic OR carries its own separator.
  **The burden of the κ-atomicity branch is not bare assertion** (derivable from Art. I.6-κ + Art. II.9;
  it equalizes the burden of the branches symmetrically to the presumption of predictability, Art. II.6):
  declaring a transition `(tⱼ, tⱼ₊₁)` κ-atomic presents that the transition is realizable-and-checkable
  in one act of contact within `κ` (Art. I.6) — otherwise it is itself above-κ ⟹ it must be split
  (Art. II.2) ⟹ it hides a joint. Unproven κ-atomicity defaults to a candidate missed separator =
  **[S-HYPOTHESIS]**, going into ACCEPTED_RISKS with a `predictability_verdict` (Art. II.6). Using the
  κ-atomicity branch without presenting the κ bound when two readers disagree is a **¬holding**.
  **Splitting the outcome by articulability** (derivable from Art. I.4 + the (i)/(ii) structure of
  Art. II.1.b; admissible per Art. IV.1.2 — it removes a point where two readers diverge): a discovered
  candidate omission splits symmetrically to (i)/(ii). **(a) An articulable intermediate separator** — a
  necessary passage is named (e.g. a reproducible root-cause repro between two joints): it is a
  **forced CHILD** (Art. I.4 — a faithful `D` cuts at the joints), added as a milestone with its own
  `criteria` before admission to Level 1 (**FORM-closable**), NOT an ACCEPTED_RISKS entry; parking a real
  necessary passage in ACCEPTED_RISKS ("an assumption") instead of cutting at it is inverted ballast — a
  missed joint disguised as a declared boundary. **(b) An inarticulable candidate** — a separator is
  suspected from the incompleteness of the list, but the passage cannot be named: only this is an
  **[S-HYPOTHESIS]** → a mandatory ACCEPTED_RISKS entry with a `predictability_verdict` (Art. II.6),
  **not FORM-closable** (the completeness of the joint list is a hypothesis about `S`, Art. II.9; a
  faithfulness boundary, Art. III.1/III.3). Declaring the joint list complete without this presentation
  is a domain `[DERIVED]` without contact (¬Art. III.1) — unlike the completeness of `criteria` vs
  `spec` (Art. II.1.b), whose domain half also goes into ACCEPTED_RISKS.
- **Level 1 (formal entailment and consistency, CHECK-7/8):** `⋀{criteria(tⱼ)} ⊨ cᵢ` and the consistency
  of the criteria; **plus the CHECK-anti-mock (structural):** for every `Dep` edge the receiving node's
  criterion SYNTACTICALLY references a concrete output artifact of the source node, rather than a
  standalone predicate re-describing the same fact (Art. II.5). The structural form of a mock (no
  reference to the source) FORM catches for free; semantic insensitivity remains a boundary
  (Art. III.1). It holds in the cheap-check limit (numeric bounds, SMT); its judgmental end is governed
  by the stakes rule (Art. II.13). **The cost of CHECKING ≠ the cost of FORMALIZING** (derivable from
  Art. I.5.1 + Art. II.4; it closes the Art. IV.1.2 loophole): the judgmental end of CHECK-7 by stakes
  (Art. II.13) concerns only the DEPTH of the proof instrument (SMT vs reasoning), NOT the fact of
  presentation. Joint sufficiency `⋀criteria(tⱼ) ⊨ cᵢ` is **presented per criterion** for each
  `cᵢ ∈ criteria(t)` (which children entail `cᵢ` and why); `c_check ≈ 0` for the presentation of the
  mapping itself ⟹ it **always holds**. What may be deferred (as EXPLORE, being expensive) is only the
  RIGOR of the implication's proof, not its writing-out. Coverage of the criteria by nodes (CHECK-1) is
  weaker than the implication and does not replace it. Asserting the implication in one line without a
  per-criterion carrier while a mapping exists is **FM-1.d** (`⋀criteria(tⱼ) ⊭ cᵢ`, CHECK-7); boundary
  III.1 is untouched by this (it remains the contact axis, not FORM).
  **The Art. II.1.b probe is recursive — per node, not only at the root** (derivable from Art. II.1.b +
  Art. II.9): the II.1.b test (*does there exist a `Result` passing all `criteria(tⱼ)` yet failing the
  parent's `cᵢ`?*) is presented NOT only at the root goal-setting but **per node for EVERY internal
  node** as part of the per-criterion mapping `⋀criteria(tⱼ) ⊨ cᵢ` — otherwise the vacuous-AND
  incompleteness (Art. II.1.b) reproduces one level down. The formal half (i) of the probe (Art. II.1.b)
  is decidable over `Ŝ` ⟹ `c_check ≈ 0` ⟹ it **always holds**; the domain half (ii) goes into the node's
  ACCEPTED_RISKS (Art. II.6) and is closed only by contact (Art. II.9). A `⟸` mapping table without a
  presented per-node probe (i) is **FM-1.d** (a nominal mapping without the implication), not
  joint-sufficiency.

FORM catches defects of form *for free* (over Ŝ, without contact). *It holds:* a decomposition that has
not passed Level 0 does not go to execution. *Failure mode:* admitting to execution a decomposition
whose Level 0 has not passed. **FORM does not establish faithfulness** (Art. II.9): Level 2 (causal
correctness) is the contact axis, not the FORM axis (Art. III.1).

**Art. II.12 (contact and repair — stop-and-replan).** `[DERIVED]` (the forced optimum, §7).
**The wall dichotomy (excluded middle).** Every wall `e ∈ Ŝ\S` belongs to **exactly one** of two classes,
by whether the edge violates its own well-formedness in `Ŝ`: **FORM** (catchable a priori over `Ŝ`,
Art. II.11) ⊕ **FAITHFULNESS** (opened only by contact, Art. II.9). There is no third class (§7); this is
exactly what gives repair its *completeness* — localization is the assignment of the wall to one of the
two. At a wall (a contact verdict `e ∈ Ŝ\S`) correct action (§7): **(1) STOPS** — it breaks the cascade
(it does not build further on a refuted claim; otherwise the error compounds, Art. II.10); **(2)
LOCALIZES** — it determines which claim exactly is false and to which of the two classes
(FORM ⊕ FAITHFULNESS) the wall belongs (by attribution, Art. II.10); **(3) REPAIRS LOCALLY** — contact
gave ground to the touched edges; the rest of `Ŝ`, if correct, survives; **(4) RE-DERIVES** — it re-runs
FORM (Art. II.11) over the updated `Ŝ`; **(5) only then proceeds**. *It holds:* movement over a graph
already known to be false does not occur (otherwise one re-carries an *avoidable* FORM class on a map
already known to be wrong). This regime is the forced optimum of the total cost over the knowable
`c_check + E_FORM + E_FAITH` (§7), and not "never fail" (Lemma 1 excludes that) and not uniqueness among
faithful `D` (the goal underdetermines `D`, Art. I.2). *Failure mode:* continuing execution on a refuted
claim without repair.

**Art. II.13 (the stakes — verify-vs-explore).** `[DERIVED]` (§13.5; the tradeoff's structure is derived,
the values are contingent). At every node and level the action chooses between **VERIFY** (pay
`c_check`, cut the FORM risk before acting) and **EXPLORE** (act on the under-checked plan and let
contact check faithfulness) — §13.5. Exploration is not the absence of a plan but a conscious
substitution of contact for the a-priori check (contact being faithfulness's only verifier, Art. II.9).
*It holds:* VERIFY down to the level ℓ where the marginal `c_check(ℓ)` < the marginal prevented FORM
risk; above that — EXPLORE. Level 0 (and the cheap SMT end of Level 1): `c_check ≈ 0` ⟹ always VERIFY
(Art. II.11). The judgmental Level 1: VERIFY only where the prevented risk justifies the cost. A node is
**cheaply reversible** ⟺ rolling back to the prior state (a) is within the capacity κ of one contact
(Art. I.6) and (b) leaves no trace in the `Ŝ_used` of the child subtree (no compounding cascade
downward, Art. II.10); otherwise the node is treated as irreversible ⟹ VERIFY-before-execution. **On a
cheaply reversible node the default choice is EXPLORE** (contact is cheaper than a-priori certification);
VERIFY-before-execution is prescribed only where the prevented risk (irreversibility / a downward
cascade, Art. II.10) justifies `c_check`. (Symmetry: "always VERIFY at L0" does not carry over to the
judgmental level — that would be gold-plating.) The *structure* of the tradeoff is derived; the concrete
cost/probability values are contextual (contingent, like `S` itself) and are not prescribed. *Failure
modes:* verifying a cheaply reversible node beyond the justified level (gold-plating), or refusing to
verify an expensively irreversible one (betting on catastrophe).

**Art. II.14 (delegation, the IC seam, the uniqueness of the accountable party).** The uniqueness of
`Del` — `[ADDITION]` (Art. I.12); IC as a property of the seam and the issuer/verifier separation at the
seam — `[DERIVED]` (§14.5, the structure of IC). Each task is assigned exactly one accountable agent
`Del: T → A` (Art. I.12; the **where/why** of uniqueness — Art. I.12). The plane `{T,D,Dep,V}` is
authority-free (Art. I.12); authority enters only as an edge of the `Del` hierarchy, and therefore IC/SoD
is a boundary term precisely on that seam. **Incentive compatibility is a property of the seam — of the
public transaction (§14.5) — and not a ban on all internal self-checking.** A node is **public ⟺ it is a
delegation seam:** its scope of responsibility differs from the parent's — operationally
**Del(child) ≠ Del(parent)** (§10) — or it is a root task assigned to the agent by an external Issuer. At
a public node the result crosses into an independent scope ⟹ the `verifier≠executor` gate applies and
**independent validation is required:** the validating Issuer and the Executor are different carriers —
the Issuer forms *and* validates by design (§14.1); what is forbidden is one context holding both roles
of one transaction (disputing yourself is contentless, §14.5). A node is **internal ⟺ the same scope** (Del(child) = Del(parent)): it
is the agent's private decomposition, it **self-verifies** by contact (DELIVER carries `self_validation`,
§14.2) and is NOT independently validated — the guarantee for the whole internal decomposition is carried
by the validation of the agent's public result (by Thm 1, §11.1: under a correct `D` the public `V=pass`
⟺ all children pass). The `verifier≠executor` gate is a **gate-at-the-seam:** it fires on public nodes,
not on every node of the graph; a review of the decomposition by a fresh independent context applies at
the seam (the public result the decomposition realizes), not link by link to every internal node.
*The degenerate case:* a fully self-assigned autonomous agent (the whole graph is one `Del`, no seam)
does not hold IC — what remains is only making-explicit (explicit derived criteria + the log, §6.2), not
a guarantee of quality. *Failure modes:* an ambiguous `Del` (diffusion of accountability); combining
goal-setting and checking in one context **at a seam** (a public transaction with coincident roles);
declaring a public seam internal in order to escape independent validation.

**Art. II.15 (contract immutability, revision ≠ refusal).** `[DERIVED]` (§14.4 Inv-1 — *from FM-5*; Inv-3
— *from FM-3*; Inv-5 — finiteness; Inv-7 — identity stability). After a task is assigned the `criteria`
are immutable; a change is a **revision** — a re-ASSIGN under the same id, the node → OFFERED, the
executor ACCEPTs/CHALLENGEs anew (this is NOT a cancellation/CANCEL) (§14.4, Inv-1: it prevents *silent*
contract staleness = FM-5). A revision **does not cascade**: the subtree is preserved, and staleness is
raised by the guards — CHECK-1 (a new uncovered criterion, FM-1.a) + no-orphan / CHECK-1b (a dangling
`covers`: a child mapped to a deleted criterion — the FM-1.e redundancy) + CHECK-3 (Dep consumers of the
changed contract, FM-5); only a terminal cancellation (refusal of the task) cascades. A node's id is
stable through revision — the immutable record is the append-only LOG (Inv-7, Art. II.16), not the node's
criteria. A refusal names the broken criteria (`FAIL ⟹ failed_criteria ≠ ∅`; Inv-3). Every non-terminal state except IDLE is finite (Inv-5). *Failure modes:* shifting the criteria after assignment (goalpost shift) — FM-5;
cascading destruction of the subtree on a revision (loss of valid work), or re-issuing the id (orphaning
the edges); an unsubstantiated refusal — ¬transparency; an infinite non-terminal state — ¬finiteness.

**Art. II.16 (transparency and the structural record).** `[DERIVED]` (Thm 11, §22; the concrete record
schema — a chosen explicit form). Every decision in the domain has a record
`R(d) = (author, spec, criteria, ACCEPTED_RISKS, timestamp)` (Thm 11, §22). Structural transparency is not
reporting bolted on top of the work but a property of the record itself: opacity is a missing node of the
graph, i.e. a measurable defect. **The provenance of load-bearing assumptions.** Every load-bearing
assumption and every structural choice of the decomposition carries in `R(d)` the provenance
`[DERIVED]` / `[ADDITION]` (derivable from the theory-model vs a named design choice): keeping the
derivational core apart from the named additions is a property of the *produced* decomposition, not only
of the constitution itself. **A structural `[DERIVED]` ≠ a domain `[DERIVED]`.** `[DERIVED]` marks only
derivability from the constitution/the canon (the structural form). All DOMAIN content (which joints/
assumptions this task actually has) is a hypothesis about `S`, untested until contact (Art. II.9): it is
marked as form-`[DERIVED]` + content-`[S-HYPOTHESIS]`, not a bare `[DERIVED]`. A domain `[DERIVED]`
without contact = a false certification of faithfulness (Art. III.1).
*It holds:* accountability separates a process defect from an agent defect (FAIL = the task did not meet
its criteria, not "the agent is bad"). *Failure modes:* an unrecorded decision in the domain; **an
unmarked design assumption passed off as derivable** (a transparency defect — it hides a named boundary
as a derivation).

**Art. II.17 (the time phases — definability, freshness, detectability).** `[DERIVED]` (the trichotomy of
the operational axis = a strict causal order, §12.3, §12.8). The computation of validation executes in
time; three phases relative to the evaluation act exhaust the operational axis (§12.3, §12.8): *before*,
*during*, *after*. Each phase is described as a full process state, not only as a source of failure:
- **Before (definability, FM-6).** If a node's decomposition is not definable at the start (the
  information does not yet exist), the node stays **open to deferred decomposition**: it is declared
  neither a leaf nor correctly decomposed until the information appears; until then it carries the
  explicit status "decomposition deferred", not a silent assumption of coverage. *Failure mode:*
  declaring coverage where `D` is not yet definable — FM-6.
- **During (freshness, FM-5).** If the `spec` changed after assignment, the former `D` is computed from
  stale inputs and is invalidated: a change of the contract is a **revision** — a re-ASSIGN under the
  same id (Art. II.15), WITHOUT a cascade: the subtree is preserved, staleness is raised by the checks
  (CHECK-1/1b/3); only a cancellation (CANCEL) cascades. Plus the coherence of the `Dep` deadlines
  (Art. II.4). *Failure mode:* executing on a `D` not updated to a changed `spec` — FM-5.
- **After (detectability, FM-7).** A defect found post hoc has a channel by which it reaches the node
  with the broken claim (Art. II.10). Every leaf has an accountable party (Art. II.14) able to carry the
  return signal. *Failure mode:* the absence of a return-signal channel — FM-7.

The completeness of the three phases is derived from the strict causal order by excluded middle, with no
assumptions about the shape of time (§12.8); the single clock is a discharged hypothesis (the linear
special case; under concurrency FM-5 generalizes rather than weakens), not a boundary (cf. Art. III.4).

---

## SECTION III. BOUNDARIES

The named permanent boundaries. Every article of this section is `[DERIVED]` (the boundaries are derived
by the theory-model as permanent). "Closing" a boundary is the logical error "incomplete by design,
therefore complete" (§3.6), which the model refutes; the *error* (not a sanction) is stated as "it is an
error to declare…".

**Art. III.1 (the faithfulness residue).** `[DERIVED]` (Lemma 1, SINGLE-SEAM, §8). The domain-silent FM-3
false-PASS — a present but insensitive integration edge (Art. II.8, II.5) — is **caught a priori by no
discipline** (Lemma 1, SINGLE-SEAM) and can pass silently even at contact. This is half (ii) of causal
correctness (§8), uncertifiable by the apparatus. The boundary is **permanent**. *It is an error:* to
declare it closed by strengthening CHECK, the apparatus or the safety net; to declare faithfulness
established without contact (cf. Art. II.9).

**Art. III.2 (completeness — covering, not closed; three closures).** `[DERIVED]` (the covering
principle, §12.8, §4). In v4 there are **three** such closures, each under its own covering axiom: the
five links (Art. I.13; CA-Links, §4.2), the 7-FM basis (Art. II.7; CA1, §12.8) and the three verification
levels (CA-Morris, §13.4 — Syntactic/Semantic/Pragmatic: the first two are the a-priori FORM check of
Art. II.11, the third is the contact axis, Art. II.9/III.1 — the levels are not one article each). All three are
established by a **covering principle**, not by a disjointness claim: CA1 — two orthogonal exhaustive axes
(§12.8); CA-Links — the two modal sides 3⊕2 (§4.2); CA-Morris — the trichotomy syntax ⊕ semantics ⊕
pragmatics, "there is no fourth dimension" (§13.4). The representational branch (the triple ⟨goal, Ŝ, D⟩)
is **below the §12.8 grade**: modulo the REACHES-ternarity axiom, with the loaded START residue (the
source point is a genuine constitutive relatum, folded, not eliminated). *It is an error:* to eliminate
START as a separate role (attempts at "start ⊂ route/medium" are question-begging; full parity is
unreachable this way, §4); to pass off "the 5 links" as a completeness theorem beyond the scope-choice.
The completeness is falsifiable from inside: exhibit a real directed action lacking one of the five links,
or carrying an independent 6th structural feature.

**Art. III.3 (decomposition-method quality).** `[DERIVED]` (Lemma 1, §8). EXTERNALIZE *formats and grades*
a seam (it writes out φ, Dep, ACCEPTED_RISKS as A1-checkable, separately falsifiable, locally repairable
edges, graded by faithfulness), but does **not guarantee** its faithfulness (Lemma 1, §8). "How to invent
a *faithful* seam" is the omitted decomposition-METHOD-quality layer; bare seam generation is a [known]
heuristic, not a [GFSO] guarantee. The method of generating a decomposition (bare-SEARCH ⊕ gfso-AUDIT,
`auto_decompose()`) converges to a completeness-audited reference, but **does not guarantee the seam's
faithfulness to the real domain** — a **permanent boundary** (§8, Lemma 1) + a blocker under execution
(E3, the engineering demo). *It is an error:* to pass off the EXTERNALIZE form or convergence-to-a-
reference as a guarantee of a faithful seam.

**Art. III.4 (the representational residue and the covering-axiom residue).** `[DERIVED]` (the sub-§12.8
branch; §12.8). (a) The representational branch is sub-§12.8 (Art. III.2). (b) The CA1 residue: the
value/time partition for predicates over the execution trace itself — an edge of the definition. The
single clock (CA2) is **not** in that residue: the count of the three operational phases is axiom-free (a
strict causal order + excluded middle, Art. II.17); the single clock is a discharged hypothesis, the
linear special case, and under concurrent time (happens-before, no global clock) the trichotomy
{before/during/after} **does not weaken but generalizes** (FM-5 passes into the read/write race of
distributed systems). The residue is local and does not touch the count of links/axes. *It is an error:*
to pass off the operational trichotomy as depending on a single clock (it does not).

**Art. III.5 (the irreducibly empirical loci).** `[DERIVED]` (§26; `docs/falsifiability.md`). The model's
whole empirical boundary is concentrated in two distinguishable loci with a common root (contact with the
domain): (1) A1∧A2 membership (the domain boundary, Art. I.15) and (2) the faithfulness of `Ŝ` to `S`
(Art. I.9, III.1). The other load-bearing claims are analytic (M), conditional on a named premise (C), or
established (§26, `docs/falsifiability.md`). *It is an error:* to declare an empirical locus resolved by
declaration; faithfulness is measured **independently of the success itself** (otherwise a counterexample
is re-explained after the fact — Art. III.1).

---

## SECTION IV. AMENDMENT

This section is the meta-rule of the document's own extension. Every article of the section is
`[ADDITION]`: **where** — the procedure for changing the constitution; **why** — the theory-model contains
no rule of its own extension, and without an explicit procedure amendment would be uncontrolled (any
article without derivability/consistency is a loophole). The criterion of *derivability from the canon*
(Art. IV.1.1) translates the canon's own requirement (§10.1); the procedural harness around it is a
choice.

**Art. IV.1 (the rule of amendment).** `[ADDITION]` (see the section preamble). A new article (an entity
of Section I, a law of Section II or a boundary of Section III) is admissible if and only if three
conditions hold simultaneously (Art. IV.1.1–IV.1.3):
- **Art. IV.1.1 (derivability from the canon).** The article is derivable from `applied_gfso_v4_en.md`
  (the theorems, the axioms A1/A2, the primitive basis, the 7 FM, the methodology §2–§8, §13.5). An
  article with no canonical justification is inadmissible.
- **Art. IV.1.2 (no loophole).** The article creates no point at which two readers can diverge on what it
  requires, and opens no process step at which action in the domain remains ungoverned (cf. Art. IV.3).
- **Art. IV.1.3 (preservation of consistency).** The article contradicts no article in force and closes no
  boundary of Section III (closing a boundary by a loophole is grounds for rejection, §3.6).

**Art. IV.2 (the priority of the boundaries).** `[ADDITION]` (see the section preamble). On a collision of
a new article with a boundary of Section III, priority goes to the boundary: an article requiring the
closure of a named boundary is inadmissible regardless of its other merits.

**Art. IV.3 (completeness of process coverage).** `[ADDITION]` (see the section preamble). An amendment is
admissible for adoption only if after it every step of directed action (goal-setting · building Ŝ ·
decomposition · the form check · execution · contact · repair) remains governed by some article. An
amendment leaving a process step outside the law is inadmissible; a discovered uncovered step is grounds
for a new amendment under Art. IV.1, not for a silent assumption.

**Art. IV.4 (repeal).** `[ADDITION]` (see the section preamble). Repealing or weakening an article in
force is admissible only on proof that its canonical ground has been withdrawn in the canon itself
(through the canon's own changelog). Until such a withdrawal the article stays in force.
