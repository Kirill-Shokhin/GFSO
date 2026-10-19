# GFSO (General Framework for Structured Operations): Formal Guarantees for Compositional Task Validation in Hierarchical Organizations

> v4.1. Every reference in Chapters 0–20 points backward; this front matter is the only forward index.

## Abstract

Hierarchical task management has no formal standard: goal-setting, decomposition and acceptance are ad-hoc. GFSO is a theory of **directed action** and a protocol derived from it that makes planning falsifiable.

Directed action is a chain of five links — goal, build-Ŝ, plan, execution, contact — over two objects: **S**, the real composition structure of the domain, contingent and not given, and **Ŝ**, the explicit estimate an agent builds and acts over. Exactly one operation reads S: the **contact seam**. A failure of directed action is a used edge e ∈ Ŝ∖S, a passage the map asserts and the territory denies. The apparatus generates no domain content, so an **agent** — a carrier of empirically learned domain content, human or LLM alike — is necessary as its only source; this is derived, not assumed.

The apparatus operationalizes the theory. Two axioms, A1 (verifiability) and A2 (decomposability), are also the contact seam's two conditions of existence and nontriviality. From them follow a minimal basis of primitives (Task, Decomposition, Dependency, Delegation, with Validation derived); binary validation (|L| = 2) and the uniqueness of AND aggregation; **six failure modes, proved complete as a basis** modulo one covering axiom, CA1; standards with three verification levels (Syntactic, Semantic, Pragmatic); a minimal protocol of 12 signals and 11 induced states; the task graph with five self-measuring quality metrics; and an AI layer (Solver + LLM) whose necessity follows from the finite capacity of a human context [5].

Under the premises and conditions named at each result, the protocol informationally dominates the status quo; its constraints improve expected payoff; its information weakly grows with adherence and with time, and validation lowers the error bound of an n-level cascade by the factor γⁿ; honest use of its signals is a dominant strategy on the deviations it detects and prices, outside fifteen named exceptions; and it improves decomposition quality through four independent mechanisms. The protocol with its self-measurement and the AI layer form one feedback loop: removing the protocol breaks it outright, removing the AI layer breaks it once the accumulated information outgrows what a human can process in one context.

The primary value is **making-explicit**: decomposition moves out of private intuition into one axiom-derived, consistency-checkable, faithfulness-graded discipline, so that a plan is a set of pre-registered, separately falsifiable claims. In this sense GFSO is the scientific method with its theory-model made explicit and mandatory and its domain lifted from nature to any directed action: **science : nature = GFSO : any directed action** — a structural positioning (§19.7).

A Lean 4 development on the language kernel audits the axiomatic surface: exactly three covering axioms appear in `#print axioms`, the placement of every other assumption, inside the development or outside it, is disclosed.

## Introduction

### The problem

In a hierarchy the task-acceptance transaction has no standard (§19.1); GFSO supplies one, derived from a theory of directed action (§20.11).

### What GFSO is

**A theory of directed action.** A1 and A2 delimit its domain (Ch. 1); the apparatus is S-free, so faithfulness is opened only by contact (§3.5); every failure is FORM or FAITHFULNESS (§3.6); the agent is derived by elimination (§4.1); the theory-model explains and predicts falsifiably (§4.6).

**A protocol derived from the theory.** The primitives are the operational precipitate of the five links and of the axioms read as the seam's conditions (Ch. 5). The twelve signals carry what a transaction meets at contact to the party who can act on it, and close the incentive seams a signal can close, the rest named as exceptions (§11.4, §16.9). One protocol serves human and AI agents alike, Del choosing per task who decides (§10.4).

**Making-explicit.** GFSO's primary value is making-explicit, earned only through three dividends — coverage against the real joints, localization and attribution of a failure, verify-vs-explore by stakes (§19.3); its new formal machinery is narrow, planning ⊂ GFSO (§19.2).

**The scientific method, generalized.** GFSO is the scientific method's falsificationist core with its theory-model explicit and mandatory and its domain lifted to any directed action, a structural positioning (§19.7).

### Results

The canon establishes fourteen formal results — six original theorems and eight further results (§20.11).

**Theorems**

| Result | Claim | Grade | Ch. |
|---|---|---|---|
| Thm 1 (compositionality) | V(t) = AND(V(t₁), …, V(tₙ)) for a correct decomposition | derived; machine-checked | 7 |
| Thm 2 (uniqueness of AND) | on {0, 1}, under commutativity, associativity and absorbing fail, AND is the only nontrivial aggregation | derived by enumeration; machine-checked | 7 |
| \|L\| = 2 (binary validation) | V is two-valued, sourced in A1; the pigeonhole over \|Act\| = 2 is its defense against a graded scale | derived; its defense machine-checked | 7 |
| Completeness of the six failure modes | FM-1…FM-6 are a complete, independent basis of the failures of compositional validation | covering axiom (CA1); independence derived | 8 |
| Thm 10 (self-measurement) | Q is computable from the execution trace, bar the post-hoc runs of q_V's later-fail term | derived, constructive-definitional | 15 |
| Thm 11 (structural transparency) | every decision has a record | derived, definitional | 11 |

**Further results**

| Result | Claim | Support | Premises |
|---|---|---|---|
| Prop 3 (information dominance) | for α₂ > α₁ the protocol's experiment Blackwell-dominates | Blackwell [1] | §16.2 |
| Prop 4 (constraint improvement) | when Δ > c, the constraints improve expected payoff for ℙ(θ_bad) > c/Δ | Simon [5] | §16.3 |
| Cor 5 (α-monotonicity) | a rational agent's expected payoff is non-decreasing in adherence, gross of compliance cost | Prop 3; [8] | §16.5 |
| Prop 6 (temporal monotonicity) | at fixed α the protocol's information weakly grows over time | Blackwell [1] | §16.6 |
| Prop 7 (scale bounds) | ‖eₙ‖ ≤ (Λ·γ)ⁿ·‖e₀‖ with the protocol against Λⁿ·‖e₀‖ without | submultiplicativity of the gains | §16.7 |
| Prop 8 (incentive compatibility) | honest use of every signal is a dominant strategy against any non-colluding counterparty on the deviations detected and priced independently of its strategy, when p·cost(undetected defect) > cost(signal), outside the fifteen named exceptions | Hurwicz [3] | §16.8–§16.11 |
| Prop 9 (decomposition quality) | four independent mechanisms improve decomposition quality | Props 3, 7, 4, 6 | §16.16 |
| Basis minimality | {T, D, Dep, Del} is minimal | constructive | §7.5 |

All eight are derived. Nine of the fourteen are the formal guarantees: Prop 3, 4, 6–9, Cor 5, Thm 10 and Thm 11.

Beside them the chapters establish, each at its grade where it is stated: the five links minimal and complete modulo CA-Links (Ch. 5); the twelve signals minimal and the eleven states induced (Ch. 11–12); an owner with a move in every state where work has begun and is not over (Inv-8) and "done" only as the issuer's PASS (Inv-7, Ch. 12); the transition table forced over the log relative to named conditions (§13.4), up to REWORKING's attribution label, bare adequacy pinning no destination (§13.2); the five metrics minimal (Ch. 15); the IC-minimality of eleven features (Ch. 16); the inseparability of the two pillars (Ch. 17); and the two methodological mechanisms (Ch. 18).

The canon names three boundaries, each shown by an impossibility argument (§20.8): the Pragmatic-level boundary, the completeness-of-the-carve wall and the edge of the domain; the one bearing on use, the faithfulness half of decomposition-method quality, is left to measurement (§20.10).

### Formal status

The formal skeleton is checked in Lean 4 on the language kernel, an audit of the axiomatic surface that proves none of GFSO's substantive claims (§20.4).

The completeness of the six failure modes, the three verification levels and the five links is checked modulo exactly three covering axioms — CA1, CA-Morris and CA-Links; the postulate closure (Ch. 0) is laid out in §20.5.

### Reading map

Chapters 0–6 lay the ground: grades, axioms, primitives and the theory of directed action; 7–9 validation, failure and standards; 10–15 the protocol, its graph and its metrics; 16–18 the guarantees, the AI layer and the methodology; 19–20 positioning and the canon's limits.

- **Ch. 0, Conventions: grades** — the eight grades every claim carries, and the design decision as a canon choice.
- **Ch. 1, Axioms** — directed action; A1 with its two clauses, decidability and domain-correctness; A2 as a capacity cost.
- **Ch. 2, Primitives** — the HVP; task, validation, decomposition with its correctness and ACCEPTED_RISKS, the deadline, delegation, dependency; the basis.
- **Ch. 3, World, map and the contact seam** — S, Ŝ, faithfulness, failure as e ∈ Ŝ∖S; the S-free apparatus, Lemmas 1–2, Contact and SINGLE-SEAM; FORM ⊕ FAITHFULNESS; the axioms as the seam's conditions, κ and the leaf test.
- **Ch. 4, Agent necessity** — d1–d6; the agent as a scope-bundle; distributed falsifiability, two-sided attribution, the anatomy of a decomposition and EXTERNALIZE; what the model explains and predicts.
- **Ch. 5, The five links** — the chain, its minimality, its completeness under CA-Links, its falsifiers.
- **Ch. 6, The continuous substrate** — the borrowed control and viability ground: the functional scale, basin chaining, AND-soundness, separators, the three axes of faithfulness, attainment and maintenance with the generator.
- **Ch. 7, Basis and validation** — |L| = 2, Thm 2, Thm 1, informativeness, the minimality of the basis.
- **Ch. 8, Failure modes** — CA1 and the dissection; FM-1…FM-6 with FM-1.a–f; the integration cases; completeness as a basis, independence, the verdict face.
- **Ch. 9, Standards and checks** — the three verification levels under CA-Morris; STD-1…4; the nine CHECKs; discharging a Semantic flag; verify vs explore.
- **Ch. 10, Parties and seams** — issuer and executor, check and signature, public and internal nodes, verifier ≠ executor, agent-agnosticity.
- **Ch. 11, Signals and the log** — the twelve signals, their minimality, admission and root creation, Thm 11.
- **Ch. 12, The machine and its invariants** — the eleven states, the clock, Inv-1…Inv-8, ESCALATED, cancellation, revisions, terminality, finality and R′, Φ1–Φ3, conformance.
- **Ch. 13, The machine forced over the log** — bare adequacy pins no destination; the backbone; the table forced over the log; R′ over the log.
- **Ch. 14, A worked example** — one release cycle through the battery, a dispute, a block and two FAILs at two seams.
- **Ch. 15, Graph and metrics** — the task graph 𝒢, one goal one root, D a forest, Q and its minimality, Thm 10, the limits of the metrics, triage.
- **Ch. 16, Guarantees** — Prop 3, Prop 4, universal improvement, Cor 5, Prop 6, Prop 7, Prop 8 with its fifteen named exceptions, IC-minimality, the threat model, Prop 9, applicability.
- **Ch. 17, The AI layer** — necessity from capacity, Solver and LLM, cross-impossibility, the feedback loop, inseparability.
- **Ch. 18, Methodology** — the two mechanisms and their optimality under a named cost model.
- **Ch. 19, Positioning** — the problem, the [known]/[GFSO] ratio, making-explicit, Scrum as a relaxation, stratification by horizon, decidability and severity, the science mapping, related work.
- **Ch. 20, Limits and closure** — the boundary criterion and the three boundaries, the machine-checked core, the covering axioms and the postulate closure, Beth canonicity, the carve wall, what lies around the canon, requirements not yet built, the tier backbone.

The Changelog and the References close the document.

---

## 0. Conventions: grades

### 0.1. The grades

A claim's grade is marked once, where the claim is made, by one of these tags.

- **Defined** — the claim fixes what an object or a term is; an axiom that delimits the theory's domain has this grade.
- **Derived** — the claim follows, by an argument the canon states, from what precedes it; one derived with a covering axiom, an adopted choice or a premise is derived relative to it, and the dependence is named at the claim.
- **Machine-checked** — a derived claim whose proof a machine checks: a Lean theorem, cited by its name, or a property the TLA+ model checker TLC checks over bounded models. A claim checked **by the kernel** is a finite statement Lean evaluates by `decide` and its kernel verifies.
- **Covering axiom** — the claim asserts that a list is complete over a space of candidates that no case split inside the theory delimits; it is postulated, not derived, and a completeness claim resting on one carries this grade and names it.
- **Adopted** — the claim is a choice the canon makes, neither derived nor postulated: a **design decision** — a point where the canon picks one of two or more alternatives, each meeting every requirement stated before it, marked where it is made — or a clause or reading the canon adopts.
- **Premise** — a condition one result carries, named at that result; it conditions that result only and is not a postulate of the canon.
- **Boundary** — a question inside the theory, about its own objects and claims, that the canon shows cannot be carried further from inside, by an impossibility argument: a result, not a gap.
- **By citation** — taken from the cited source, not re-derived.

What the formal layer encodes rather than proves — axioms, types, hypotheses in theorem signatures — together with the canon's adopted choices, each placement disclosed, is its **postulate closure**.

---

## 1. Axioms

### 1.1. Directed action

**Directed action** is a system acting in a real domain so that a goal is reached; two axioms delimit its domain *(defined)*.

### 1.2. The two axioms

**Axiom A1 (verifiability).** Any organized activity is directed at a goal whose attainment is checkable by a finite set of conditions, each decidable in finite time and returning pass or fail.

**Axiom A2 (decomposability).** There exist goals whose complexity exceeds the capacity of a single agent; they are attainable only by splitting them into parts, each within the capacity of some agent.

Both axioms are definitional postulates *(defined)*. A1 is a fact about goals (*what*), A2 about complexity and agents (*who*): two orthogonal dimensions.

### 1.3. A1's two clauses

A1 has two clauses *(defined)*: **(i) decidability**, A1's **structural half** — the predicate yields pass or fail mechanically in finite time; **(ii) domain-correctness** — passing coincides with the real outcome. Its conditions are predicated of an activity's result.

Clause (i) is the decidability conjunct of Popper's falsifiability requirement in its decidable form [40]: it constrains the verdict's codomain, not its attained image, so a criterion whose fail is never attained satisfies it and forbids nothing. The prohibition conjunct, a non-empty fail-extension, is carried by clause (ii), which forces fail wherever the goal is really unattained, so the fail-extension is non-empty exactly under the contingency of attainment. So the strengthening over Popper's "in principle" is A1's, and neither conjunct entails the other *(derived)*.

### 1.4. A2 as a capacity cost

A goal splits because doing it whole exceeds the agent's capacity budget, so cost is constitutive of directed action — what A2 asserts — not an add-on *(defined)*.

---

## 2. Primitives

### 2.1. The hierarchical verifiable process

**Definition (HVP).** A Hierarchical Verifiable Process is a process satisfying A1 ∧ A2 (Ch. 1): a verifiable goal that requires decomposition *(defined)*.

The model is needed iff A1 ∧ A2: a goal is inside it iff A1 holds of the goal as its criteria state it and the goal lies within one agent's capacity or splits into parts within it, and needs it iff it also exceeds that capacity *(derived)*.

### 2.2. Task

**Task (T).** A task is t = (spec, criteria, deadline), criteria = {c₁, …, cₖ} being a finite nonempty set of decidable predicates cᵢ : Result → {pass, fail} *(defined)*.

From A1: activity is goal-directed → spec; its outcome is checkable → criteria *(derived)*.

A capability outside the goal's scope is absent from it: no criterion demands it, and extending the scope means giving the goal new criteria.

### 2.3. Validation

**Validation (V).** V : T → {pass, fail} is induced by T, not a separate primitive *(defined)*:

```
V(t) = pass  ⟺  ∀ cᵢ ∈ criteria(t): cᵢ = pass
```

Until checking completes V(t) = ⊥, the absence of a value rather than a third value of the scale, so in-progress is not a value of V but its absence *(defined)*.

### 2.4. Decomposition

**Decomposition (D).** D : T → 𝒫(T) splits a task into subtasks, D(t) = ∅ meaning t is atomic; from A2, complex tasks demand splitting *(defined)*.

**Correctness of a decomposition** — the central definition. D(t) = {t₁, …, tₙ} is correct under *(defined)*:

1. **Joint sufficiency (coverage):** ∀ cᵢ ∈ criteria(t): [∀ tⱼ ∈ D(t): V(tⱼ) = pass] → cᵢ = pass.
2. **Non-redundancy (necessity):** ∀ tⱼ ∈ D(t): V(tⱼ) = fail → ∃ cᵢ ∈ criteria(t): cᵢ = fail.

Joint sufficiency ranges over the written criteria.

The split D(t) carries the register **ACCEPTED_RISKS(t)**: the risk events, uncertain when the split is made, that its claim of joint sufficiency accepts *(defined)*.

A split maps each child to the criteria of t it is **responsible** for, and may declare for a criterion cᵢ the **composition function** fᵢ by which its responsible children's criteria secure it *(defined)*. A task created as no split's child is a **root** *(defined)*.

Non-redundancy is a requirement on criteria design: a child that can fail without affecting the parent demands more than the parent needs — an unrelated condition or a bound stricter than needed — and is a decomposition defect.

### 2.5. The deadline

That the deadline, the bound of a finite activity, is a field of T is a design decision *(adopted)*; activity without a time bound is indistinguishable from inactivity.

Since T carries the deadline as the bound of the activity and a bound already passed leaves no activity that can meet it, the task is given out — the first time and each later one — with a live deadline, one still ahead *(derived)*.

An implementation of the protocol may write in a default deadline, logged as supplied and within the parent's deadline, a design decision *(adopted)*.

### 2.6. Delegation

**Delegation (Del).** Del : T → A assigns each task exactly one agent of the set A; from A2, subtasks must be executed, so each has an executor *(defined)*.

The uniqueness of Del — exactly one accountable party — is a design decision: an ambiguous Del diffuses accountability *(adopted)*.

Recursive D and Del generate a hierarchy, a consequence rather than a presupposition [6] *(derived)*.

### 2.7. Dependency

**Dependency (Dep).** Dep ⊂ T × T is an acyclic relation: if criteria(t_b) references the result of t_a, then (t_a, t_b) ∈ Dep *(defined)*.

Coherence: (t_a, t_b) ∈ Dep ⟹ deadline(t_a) < deadline(t_b) *(defined)*.

D fixes the vertical links, Dep the horizontal ones between branches; Dep carries causal dependence D does not contain, so it is an independent primitive, from T + D *(derived)*.

### 2.8. The basis

The canonical representation of an HVP is the tuple (T, D, Dep, Del, V) *(defined)*: T from A1, D and Del from A2, fundamental; Dep from T + D, independent; V derived, induced by T's criteria.

The plane {T, D, Dep, V} is authority-free by construction: none of their signatures references the set of agents A, and agency enters through the single primitive Del : T → A *(derived)*.

Dep-reachability Dep\*, the transitive closure of Dep, is not first-order definable [49] *(by citation)* and is no primitive but a derived query *(derived)*.

---

## 3. World, map and the contact seam

### 3.1. S and Ŝ

**S** is the real composition/transition structure of the domain: what actually composes and what reaches what. It is real, contingent and not given in advance. *(defined)*

Its operational primitive is the composition relation

```
(t, {tⱼ}) ∈ S   ⟺   really completing all children tⱼ attains the parent t
```

joint sufficiency as a fact of the domain, which Ch. 2 states over criteria as a claim. *(defined)*

**Ŝ** is the explicit estimate of S that the agent builds and acts over. *(defined)* A decomposition is chosen and built on Ŝ.

### 3.2. Faithfulness and failure

**Faithfulness** is `Ŝ_used ⊆ S`: every edge of Ŝ the action uses is real. This edge axis is its general form. *(defined)*

A decomposition is **causally correct** iff every composition edge `(t, {tⱼ})` it asserts lies in S. *(defined)*

The **failure root**: a **failure** of directed action is a used edge `e ∈ Ŝ ∖ S`, a **wall** the map promised as a passage and the territory denies. *(defined)*

### 3.3. The apparatus

The **apparatus** 𝒜 is the family of operations run over the map — operations on the decidable criteria as written (A1(i), Ch. 1), the conjunction V over their values (Ch. 2) and its aggregation along D, every check, composition and search over Ŝ — each a function `α : Ŝᵏ → Ŝ`. *(defined)* Hence 𝒜 is syntactically S-free: nothing in it refers to S.

### 3.4. The two lemmas

**Lemma 1 (domain structure lies beyond the axioms).** S is not definable from A1 + A2. *(derived)*

*Proof.* Two domains with one formal graph and different real composition laws, S₁ ≠ S₂, satisfy A1 and A2 identically in the structural reading of clause (i), and that language cannot tell them apart. Only clause (ii) would require S. ∎

**Lemma 2 (declaration has no bottom).** Pure declaration grounds no correctness. *(derived)*

*Proof.* A declared decomposition is itself a decomposition, whose correctness is a fresh instance of the same question: a regress. ∎

### 3.5. The contact seam

**Contact.** On a used edge `e ∈ Ŝ_used`

```
Contact : (e, [e ∈ S]) ↦ (verdict, Ŝ′)
```

takes the edge and the world's ontic fact `[e ∈ S] ∈ {tt, ff}` and returns `verdict ∈ {pass, fail}` with the revised estimate Ŝ′. *(defined)*

**SINGLE-SEAM.** Contact is the only operation that reads S; S enters only through its second argument. *(derived)* SINGLE-SEAM follows from the S-freeness of 𝒜 (§3.3) and Contact's signature; by Lemma 1 no operation of 𝒜 can stand in for Contact.

So `(t, {tⱼ}) ∈ S` is reality's verdict, at contact, on a composition posited on Ŝ.

Contact is necessary: an edge acquires ground only when Contact touches it, so without it `Ŝ_used ⊆ S` is unverifiable and directedness degenerates into an open-loop guess. *(derived)* Contact is unique up to re-application on other edges, since any operation that reads S converts an ontic fact into an epistemic sanction, which is what Contact is. *(defined)*

Contact is homogeneous modulo delay, being defined on every used edge *(derived)*: every node is checked against its own realized aggregate, and leaf and non-leaf differ in when contact arrives, not in whether it arrives.

Faithfulness is opened only by contact: no a-priori discipline certifies it (Lemma 1), so causal correctness is a permanent boundary, and no probability model certifies that a criterion discriminates — the faithfulness residue. *(boundary)*

### 3.6. FORM and FAITHFULNESS

A failure is there for one of two reasons, by excluded middle on whether its edge violates Ŝ's own well-formedness: **FORM**, a wall on one's own map, catchable a priori over Ŝ; or **FAITHFULNESS**, a clean map whose edge S denies, opened only by contact (Lemma 1). *(derived)* This cut, FORM ⊕ FAITHFULNESS, is the validity ⊥ faithfulness axis.

### 3.7. The axioms as the seam's conditions

A second reading of the axioms asks what must hold for Contact to exist and be nontrivial. *(defined)*

**A1 is the solvability of Contact's output.** Clause (i), a verdict in {pass, fail} in finite time, is Contact's signature: read off, not derived. Clause (ii), the verdict coinciding with the real `[e ∈ S]`, is the nontrivial half: 𝒜 does not supply it (SINGLE-SEAM), only the world does through Contact (Lemma 1), so it stays open.

**Capacity κ** is the largest region or step one act can directly realize-and-check: A2's "capacity of a single agent" as a parameter, the budget of its capacity cost (Ch. 1), a property of the actor and of contact, not of bare dynamics. *(defined)*

**A2 is the constructibility of Contact's input.** A transition above κ is not a leaf, so it splits into sub-edges within κ, recursively, into a tree. "Every above-κ transition admits a split into κ-leaves" is A2's constructive clause; its existential clause, some goal exceeds κ, makes the construction nontrivial.

**The leaf test.** Any node may be a leaf only if its goal is within its holder's κ to execute-and-check directly (A2); a node above that κ owes a split, before execution or in performance. So the depth κ forces is agent-relative: a stronger agent, with a larger κ, has a shallower forced floor. *(derived)*

**A1 ∧ A2 is the existence and nontriviality of Contact** *(derived)*: Contact exists and some goal reaches it only through the κ-recursion ⟺ per-edge contact is solvable (A1) and the κ-bounded leaf input is constructible and needed somewhere (A2). Under ¬A2 Contact still exists, its κ-bounded input unneeded or unconstructible (Ch. 2).

The reading adds to the axioms, postulates still, the role of interface conditions of Contact, without deriving them; for A2 that role is κ and the factorization: bare reachability gives a trajectory, not its factorization into jointly sufficient, separately Contact-checkable κ-leaves, which is A2 itself.


Two loci are irreducibly empirical, both rooted in contact: whether a goal lies inside the model (Ch. 2), falsified as a scope boundary, and the faithfulness of Ŝ to S, falsified at contact as a wall (§3.2).

---

## 4. Agent necessity

### 4.1. The derivation (d1–d6)

A1 asserts that a correct predicate exists, not which one; the choice of criteria is delegated to whoever writes them. d1–d6 derive what that writer must be.

- **d1.** A faithful decomposition must agree with S: the definition of causal correctness (Ch. 3).
- **d2.** S is a contingent fact about the world (Lemma 1).
- **d3.** By excluded middle, not an added axiom, the grounding of any contingent knowledge about S either reaches back to the world — contact, direct or mediated/inherited — or does not.
- **d4.** Not reaching the world, the grounding is derived by the apparatus, or else declared, or else the residual class, coincidence (luck): a nested excluded middle, so the three are exhaustive. Derivation is excluded because S lies outside the language of A1, A2 (Lemma 1); declaration, as a regress (Lemma 2); luck is filtered out under a demand of reliable success because S is contingent.
- **d5.** Hence reliable knowledge of S reaches back to the world: empirical contact. The derivation is pinned, its single thin local residue being d4's "luck is unstable".
- **d6.** The apparatus generates no Ŝ-content (Lemma 1), so contact is carried by the agent. A1(i) fixes only a verdict's codomain (Ch. 1), not its sensitivity to divergence from S, so discrimination remains the open part of clause (ii).

**Conclusion.** Clause (ii) comes only from contact, so the agent, human or LLM alike, is necessary as the sole source of domain content for Ŝ and as its interpreter. *(derived)*

Contact is a joint event: its form comes from the criterion, its verdict from the world, its positing and interpretation from the agent.

### 4.2. The agent

The agent is no primitive of its own: the model sees it only through Del, as a scope-bundle — the block of the task tree Del assigns it, one scope of responsibility — and, beside its κ (Ch. 3), tells two agents apart only by the chosen scope boundary. *(defined)*

### 4.3. Distributed falsifiability

Every node carries a falsifiable claim: a leaf's world is the domain; a non-leaf's claim is compositional — "the children's criteria holding on its delivered result ⟹ the goal is delivered" — and its world is the layer below. *(defined)* A non-leaf's contact (Ch. 3) is therefore a compositional test of that claim.

### 4.4. Two-sided attribution

Attribution runs forward (top-down), a node's error propagating into its children's criteria level by level, and backward (bottom-up). *(defined)* Backward, a refutation is attributed along the explicit composition to the node whose compositional claim it breaks — not provably the lowest. A failure (Ch. 3) is placed at the map's own claim, where this attribution reaches it.

The two directions close a feedback loop; bidirectionality is a consequence of the structure, not an addition.

### 4.5. The anatomy of a decomposition

**φ** is a decomposition's claim of joint sufficiency (Ch. 2): "these children, plus their integration, satisfied, constitute the parent". *(defined)* The goal underdetermines the decomposition: many bases exist over Ŝ.

A decomposition has three owners. *(defined)* **Content** — which children, which φ — is the agent's, through Ŝ, since the apparatus does not generate it (Lemma 1). **Form**, well-posedness, is GFSO's: checkable over Ŝ before execution and discharged as far as the built checks reach. **Truth** — whether φ holds in S — is the world's.

Form consists of six items *(defined)*: (1) decidable child criteria (A1(i)); (2) an explicit φ — the split's mapping of children to criteria, with its composition functions where declared (Ch. 2); (3) non-redundancy; (4) an explicit Dep, the couplings written, the children need not be orthogonal; (5) the ACCEPTED_RISKS register (Ch. 2) as the claim's boundary; (6) deadline coherence, child < parent. Inside FORM (Ch. 3), the **load-bearing** interior of well-posedness over the map is {connectivity/Dep, φ-composition, non-redundancy} — (4), (2), (3), the items that carry the composition claim; (1), (5) and (6) are FORM by the same test but carry no claim.

GFSO ranks decompositions only structurally — well-posedness, attribution purity — and issues no one-true decomposition (Lemma 1): the world filters, colleagues compare. *(boundary)* The tree is a snapshot of an ongoing estimate; re-decomposition is a structural update from the backward signal at the attributed level (§4.4).

Producing a decomposition is EXTERNALIZE ∘ EXPAND ∘ CONSTRUCT-Ŝ: build Ŝ, search and refine over it, write the result out. *(defined)* **EXTERNALIZE** is writing the beliefs the split rests on — φ, Dep, ACCEPTED_RISKS — out as A1-checkable, separately falsifiable, locally repairable edges, graded by faithfulness, not plausibility. *(defined)* EXTERNALIZE does not make a seam faithful: how to invent a faithful seam is the layer it omits.

### 4.6. What the model explains and predicts

The model **explains** pre-theoretical success — the agent carried sufficient Ŝ-content plus implicit structure — and failure: a thin structural half, out-of-distribution Ŝ-content, or poor solitary induction.

It **predicts**, falsifiably:

- agent interchangeability, relative to a faithfulness proxy independent of the outcome; the agent-relative forced depth (§3.7) is the depth-dependence behind it;
- applicability: structural success-content ⟺ applicable, which sharpens A1 ∧ A2;
- a global falsifier: sustained out-of-distribution success without the structural half and without learned faithfulness, the latter measured independently of the success itself.

The (ii)-faithfulness discipline — criteria track reality — is the premise a result depends on exactly when it uses clause-(ii) faithfulness. *(premise)*

The model names residues: the agent's solitary induction, the agent-relative forced depth, which slicing is faithful (Lemma 1), and a criterion's discrimination, the last two being boundaries. *(boundary)* It localizes them and does not close them: closing clause (ii) would be "incomplete by design, therefore complete", which §4.1 refutes.


---

## 5. The five links

### 5.1. The chain

The **five links** of directed action (Ch. 1), over S and Ŝ (Ch. 3), are *(defined)*:

- **Link-1, goal:** a goal G is set — *directed*;
- **Link-2, build-Ŝ:** Ŝ is built — *informed*;
- **Link-3, plan:** D (Ch. 2) is chosen over Ŝ — *structured*;
- **Link-4, execution:** the plan is rolled out in S — *actual*;
- **Link-5, contact:** a verdict comes from S — *real*.

Link-5 is Contact (Ch. 3), the operator.

The agent, the necessary carrier of domain content (Ch. 4), carries Link-2 and Link-5, where by Lemma 1 (Ch. 3) content and faithfulness enter only there.

Cost decorates an edge: estimated in Ŝ, realized at contact.

The primitives (Ch. 2) are the operational precipitate of the links and of A1, A2 as the seam's conditions (Ch. 3): Link-1 becomes a task's criteria, Link-3 the decomposition D, A2's κ-recursion delegation Del and the hierarchy, cross-branch couplings Dep. The axioms ground each structure's necessity; its concrete form is a consequence or a design decision (Ch. 0).

### 5.2. Minimality

The five links are minimal *(derived)*, by per-element counterexample: without the goal, bare dynamics; without build-Ŝ, blind reaction; without the plan, no route; without execution, an unexecuted plan; without contact, an open-loop guess.

### 5.3. Completeness: CA-Links

**CA-Links** *(covering axiom)*. Directed action is an intentional relation of a system-with-a-model to the world for a goal. Its two relata give, by excluded middle on map versus territory, two modal sides — **REPRESENTATION** (in Ŝ) and **REALIZATION** (in S), the theory's own Ŝ-versus-S axis — summing to exactly five links:

- **REPRESENTATION = {Link-1, Link-2, Link-3}**, the ternary argument structure of `Reaches(route, target ; medium)` = D · G · Ŝ;
- **REALIZATION = {Link-4, Link-5}** = ⟨execution (system → world), contact (world → system)⟩.

Its three branches are graded separately:

- the modal branch — two relata, two sides — is an excluded middle *(derived)*;
- the realization branch — in or out, one link per direction — is an excluded middle *(derived)*;
- the representational branch has no narrowing argument, so the completeness of ⟨goal, Ŝ, D⟩ holds modulo **REACHES-ternarity**, the bare assertion that REACHES has three argument roles *(covering axiom)*.

START, the source of reaching, is a genuine constitutive relatum of REACHES, folded into the execution-anchored present — a degenerate relatum pinned by the current world state (Link-4) — by a choice CA-Links carries. Rejecting the fold breaks 3 ⊕ 2 = 5.

With START folded, the triple ⟨goal, Ŝ, D⟩ is the planning definition ⟨initial, goal, model⟩ together with the plan that solves it; inherited by that definition, the representational branch is, with START's fold, CA-Links' disclosed residue *(covering axiom)*.

### 5.4. Falsifiers

Minimality falls to a real directed action lacking one of the five links; completeness to one carrying an independent sixth feature — a third modality, a fourth REACHES role or a third realization direction — open from inside *(boundary)*.

---

## 6. The continuous substrate

### 6.1. Standing

The substrate is known ground, a control and viability apparatus borrowed from [29] and [28], not GFSO's contribution *(by citation)*.

The discrete apparatus (Ch. 3) remains the operative layer, the substrate its causal ground.

### 6.2. The field of directed action

The field of directed action (Ch. 1) is the tuple `(M, U, f, x₀, G, S, Ŝ, D)` *(defined; by citation [29])*:

- `M`, a smooth manifold of domain states, implicit;
- `U`, the admissible controls, `u(·) ∈ 𝒰`;
- `f : M × U → TM`, a controlled vector field, `ẋ = f(x,u)`;
- `x₀ ∈ M`, the start, the current state;
- `G ⊆ M`, the real goal region — ontic, exogenous, not given to the agent exactly.

S (Ch. 3) read continuously is the flow of admissible trajectories `{ x(·) : ẋ = f(x,u), u ∈ 𝒰 }`, causality being the restriction of `f` to reachable directions.

The field is stated without A1 and A2; it is the field of which the seam conditions (Ch. 3) ask what must hold for Contact.

The **capture basin** `Capt_S(A) = { x ∈ M : ∃u ∈ 𝒰, ∃T ≥ 0, x(0)=x, x(T) ∈ A }`, with M as the constraint set, is the field's derived object *(defined; by citation [28])*.

### 6.3. The functional scale

`x ∼_G y` iff x and y have the same G-relevant futures under any admissible control; a reference class is `[x]_{∼_G}`, and discreteness is real on `M/∼_G`, not on atoms *(defined)*.

The map works over a coarsening `≈_G` of its own positing, **sound** iff `≈_G` is a bisimulation w.r.t. `f` on the G-relevant σ-algebra; a **scale leak** is `≈_G` failing to be one — two states the map treats as one having different G-relevant futures *(defined)*.

Soundness is the well-definedness of the quotient dynamics on `M/≈_G`, which needs `≈_G` to merge only states with the same G-relevant futures; `∼_G` has that property by definition, so `M/∼_G` is always sound and a coarsening answers to it exactly where it has the property *(derived)*.

Everything discrete lives on the functional scale, on `≈_G`, inside Ŝ.

### 6.4. Basin chaining

A chain of regions `B₁, …, Bₙ ⊆ M` is **S-correct** for `(x₀, G)` if `x₀ ∈ Capt_S(B₁)`, `Bᵢ ⊆ Capt_S(Bᵢ₊₁)` and `Bₙ ⊆ Capt_S(G)`; then `x₀ ∈ Capt_S(G)` by transitivity of reachability *(by citation)*.

The composition relation `(t,{tⱼ}) ∈ S` (Ch. 3) is the discrete shadow of this flow on the functional scale.

### 6.5. AND-soundness

**AND-soundness**, the GFSO kernel *(defined)*. A link i whose next region is reached through m co-children carries the conjunctive fact
`AND-soundness(i): ( ⋀ₖ [∈ Capt_S(Bᵢ⁽ᵏ⁾) and attained] ) ⟹ ∈ Capt_S(Bᵢ₊₁)`.

Compressing the children into one option `o = ⊗ₖ Bᵢ⁽ᵏ⁾` gives the single fact `Reach(o) ⊆ Capt_S(Bᵢ₊₁)` and loses which component failed; option models [26] and HTN methods [12] formalize one composite transition, with one truth-maker and one falsifier *(by citation)*.

AND-soundness yields m separately falsifiable truth-makers plus the integration implication `(⋀ children) ⟹ Capt_S(parent)`, a separate failure carrier, not derivable from the m Reach facts and attributable (Ch. 4) to no single child, whose failures are those of Ch. 3 *(derived)*.

`Capt_S` of a conjunctive goal is standard viability; what AND-soundness adds is the integration implication's mandatory writing-out at every level, which standard models can express but neither oblige nor attribute.

### 6.6. The representational branch over the basin

No narrowing argument for CA-Links' representational branch (Ch. 5) is available from the canon's ground: every such argument reads reaching through the capture basin, which is the planning definition ⟨initial, goal, model⟩ read as reachability *(derived)*.

Counting the roles of §6.4's chain predicate — start, flow, chain, target, each basin a function of S and its target alone — gives four, START among them; the count unfolds a predicate whose choice is itself the covering *(derived)*.

The field's `x₀` grounds START's source role at substrate level, not its fold at the REACHES level (Ch. 5).

### 6.7. Separators

A closed `B ⊆ M` is a **separator** for `(x₀, G)` iff every admissible trajectory `x₀ → G` crosses B, equivalently `x₀ ∉ Capt_{S∖B}(G)` — an ontic fact, not the agent's choice *(defined)*.

Joints are usually few: the flow funnels through narrow separators — inclusion-minimal, thin along the flow — with known analogues in bottleneck states [30] and landmarks [31] *(by citation)*.

The joints are forced, granularity beyond them is free, and a faithful decomposition cuts at the joints *(derived)*.

Non-redundancy (Ch. 2) is the discrete shadow of separator-hood: an unremovable subgoal is a separator of the flow into the region its parent's criteria state, a ballast subgoal a non-separator; these separators are the split's joints *(derived)*. A demand the criteria make beyond what G needs lies in them, not in the split.

### 6.8. The three axes of faithfulness

Faithfulness, the edge axis of Ch. 3, unfolds continuously into three orthogonal axes *(defined)*:

- **Edge.** A believed passage `(B, B′) ∈ Ŝ` is faithful iff `B ⊆ Capt_S(B′)`.
- **Node.** A vertex of Ŝ — the goal (`Ĝ ≠ G`) or any waypoint — fails to answer to S in two halves: **illusory**, a class answering to no real separator or region; **absent**, a separator the faithful map requires, missing from it.
- **Scale.** The posited coarsening `≈_G` leaks.

Node and scale are correctness conditions on Ŝ's carrier, edge the correctness of its connections; carrier failures generate edge failures, not conversely *(derived)*.

### 6.9. Two goal topologies

The canon works over **attainment**, `x₀ ∈ Capt_S(G)`, topology **TREE** — the κ-recursion (Ch. 3) terminates. The second goal type is **maintenance**, staying inside a viability domain `Ω ⊆ M`; its object is the viability kernel `Viab_S(Ω) = { x ∈ Ω : ∃u ∈ 𝒰, ∀t ≥ 0, x(t) ∈ Ω }`, topology **CYCLE**, an invariant set *(defined; by citation [28])*.

Attainment has shape `∃u ∃T`: its satisfaction is an event on which the predicate expires and the node freezes. Maintenance has shape `∃u ∀t`, its object the largest closed subset of Ω from which Ω is holdable, refutable by exit and never completable *(defined)*.

Attainment represents the liveness class `◇G` (pass absorbing), maintenance the safety class `□Ω` (fail absorbing, no terminal pass). Exit from Ω is attainment of the complement, `Ω ∖ Viab_S(Ω) = { x ∈ Ω : ∀u ∃t, x(t) ∉ Ω }`, so maintenance is attainment's standing, non-consumable dual, not its subspecies *(derived)*.

Every trace property is the intersection of a safety and a liveness property [38], so the two classes are exhaustive; the classes, not the two object forms, are a basis of every goal *(by citation)*.

`◇G` and `□Ω` are the one-sidedly finitely decidable representatives of liveness and safety, neither two-sidedly decidable; a general goal is richer — the recurrent `□◇A` is liveness, yet reduces neither to `◇G` nor to `◇G ∧ □Ω` *(derived)*.

`Capt`'s unbounded `∃T` is liveness; the deadline (Ch. 2) sharpens it to `◇≤dl G`, a safety tightening, and the class dichotomy is stated on the deadline-free object.

### 6.10. The generator

Exit from `Viab_S(Ω)` is collapse regardless of tree progress, and the cycle generates trees because a safety parent `□Ω` emits liveness subgoals `◇(return to Ω)`.

**The generator** *(defined)*. Under disturbances, `ẋ = f(x,u,w)`, choose a safe core `Ω_safe ⊂ Viab_S(Ω)` with a margin and a watch surface `Σ = ∂Ω_safe`. At the k-th crossing `t_k = inf{ t > t_{k−1} : x(t) ∈ Σ }` a Capt-task `τ_k` — return from `x(t_k)` to `Ω_safe`, topology TREE — is emitted. The stream `Gen(Ω) = {τ_k}` is indexed by events: the `τ_k` are independent roots, not children of one parent in D.

**Serviceability**, maintenance's analogue of κ and A2: the margin `dist(Σ, ∂Viab_S(Ω))` is at least the state's excursion during one return, and the emission rate at most the return throughput *(defined)*.

Under the generator, maintenance is viable if `x₀ ∈ Ω_safe` and the stream is forever serviceable — a sufficient, worst-case condition relative to Σ; serviceability is where maintenance fails with sound trees *(derived)*.

With only an absorbing fail, maintenance is not a task but a standing generator emitting root Capt-tasks *(derived)*.

Maintenance admits no static AND-decomposition: `Viab_S(Ω₁ ∩ Ω₂) ⊆ Viab_S(Ω₁) ∩ Viab_S(Ω₂)`, in general strictly, because the glue is shared control at every moment, not an addable child criterion *(derived)*.

The temporal generator is the compositional handle reducing maintenance to attainment.

The execution of maintenance is fully subsumed — a stream of ordinary Capt-trees over which V (Ch. 2) works unchanged *(derived)*.

Maintenance is thus an independent goal-object and generator — its predicate safety, not AND-composing, which forces the generator, and carrying the emission schedule — not an independent executor *(derived)*.

A1's conditions being predicated of a result (Ch. 1), a goal enters the apparatus only through tasks whose verdict is two-sided at a deadline (Ch. 2): bounded attainment `◇≤dl G` directly, maintenance `□Ω` through the bounded-attainment tasks its generator emits; a goal with neither reading lies outside A1 *(derived)*.

### 6.11. Maintenance failure

The invariant can be breached while every `τ_k` passed and every tree was faithful, by **(a)** a margin below the excursion — the generator's own estimate of it, or a real excursion larger than estimated — or an overestimated kernel, **(b)** an emission rate above the return throughput — by the generator's own estimates, or by disturbances denser than estimated — or **(c)** Σ missing the real exit direction *(derived)*.

By the coarse cut (Ch. 3) a maintenance failure is a used edge in Ŝ∖S of the generator's Ŝ, the schedule map, not of any `τ_k`: FORM where serviceability fails by the generator's own estimates, a-priori checkable as deadline consistency, though the form list (Ch. 4) is stated over a split and the `τ_k` are independent roots, so no item covers it, its kin being deadline coherence; FAITHFULNESS for the rest of (a)–(c), (c) being the node axis's absent half (§6.8) *(derived)*.

The novelty is the scope, not the axis: the carrier of maintenance failure is a predicate over the stream — the coupling emission-schedule ⨯ kernel-geometry — invisible to per-node validation, so maintenance is measured over the stream, above any node, by serviceability's terms — worst-case margin, return latency, service rate against disturbance density; `□Ω` is held only by the liveness-soundness of the regulator *(derived)*.

### 6.12. Survival

Goals in a working environment are in general exogenous — an SLA, a regime corridor, holding formation *(premise)*.

Survival, maintaining `Viab(Ω_survival)` with Ω = "the operator keeps existing", is maintenance's degenerate limit, because its emission source is reflexive — the generator is powered by the operator itself — so it is not load-bearing where Ω is exogenous *(derived)*.

The quantitative service-rate theory is control-theoretic, set invariance [35] *(by citation)*.

---

## 7. Basis and validation

### 7.1. Binarity of validation

**The scale.** *(derived)* V : T → L, and L is fixed by V's definition (Ch. 2): each cᵢ : Result → {pass, fail} is decidable (A1) and V(t) = ⋀ᵢ cᵢ, so |L| = 2 follows from A1 directly, with no appeal to the action space. |L| = 2 is the theorem form of contact's two-valued output (Ch. 3).

|L| = 2 is the codomain d6 (Ch. 4) separates from sensitivity.

**Decision-relevance.** *(premise)* Validation exists to decide whether to intervene.

**|Act| = 2.** *(covering axiom)* An agent's action at a node either changes the task's trajectory or does not, both classes nonempty: Act = {intervene, ¬intervene}. Waiting is ¬intervene; a partial intervention is binary at each node. That no finer partition of actions is wanted is the covering claim.

**Pigeonhole.** *(derived; machine-checked, `Binarity.L_forced_two`)* For act : L → Act with |Act| = 2, surjective (both actions reachable) and injective (distinct values, distinct actions), |L| = 2: surjectivity gives |L| ≥ 2, injectivity |L| ≤ 2. ∎

| Weaken | Consequence |
|---|---|
| \|Act\| = 2 | a third action would neither change the trajectory nor leave it; a finer action set is carried by decomposition, not by L |
| surjectivity | an unreachable action makes the system defective |
| injectivity | decision-irrelevant values: an arbitrary threshold, positional dependence, redundancy |

**Injectivity is forced.** *(derived)* By decision-relevance a value that changes no action collapses into an existing one. A value separating retry from escalate — whether a failed task is reworked or handed up for a decision above it — is not a value of V, the conjunction of the criteria: encoding it in L redefines V. Granularity is carried by decomposition, so within GFSO's architecture a graded scale adds nothing.

**Forcing function.** Forced binarity exposes bad criteria: whoever validates and cannot decide pass or fail has found a spec defect, which no warning value can defer.

### 7.2. Uniqueness of the aggregation

With |L| = 2, V(parent) = ⊗(V(t₁), …, V(tₙ)).

**Requirements.** *(derived)* ⊗ is commutative and associative, the children's order not mattering, and fail is absorbing: ⊗(fail, x) = fail, by non-redundancy (Ch. 2) — a necessary child's fail fails the parent. The absorbing element is pinned to fail because OR and const₁ absorb at pass.

**Theorem 2 (uniqueness of AND).** *(derived; machine-checked, `AndUniqueness.and_unique`)* On {0, 1}, under commutativity, associativity and absorbing fail, AND is the only nontrivial operation.

*Proof (enumeration).* 16 binary operations; 8 commutative; 6 of those associative (AND, OR, XOR, XNOR, const₀, const₁); 0 absorbing leaves AND, const₀; nontriviality leaves AND. ∎

### 7.3. The compositionality theorem

**Theorem 1 (compositionality).** *(derived; machine-checked, `Compositionality.T1`)* For a non-atomic task t with a correct decomposition D(t) = {t₁, …, tₙ} (Ch. 2):

```
V(t) = pass  ⟺  ∀ tⱼ ∈ D(t): V(tⱼ) = pass,   i.e.  V(t) = AND(V(t₁), …, V(tₙ))
```

Thm 1 operates only on tasks with V ≠ ⊥ (Ch. 2).

*Proof.* (←) All children pass ⟹ by joint sufficiency every cᵢ passes ⟹ V(t) = pass. (→) V(t) = pass; a failing child would by non-redundancy fail some cᵢ — contradiction. ∎

**Corollary.** *(derived)* If every leaf passes and every decomposition is correct, the root passes: the global check is a consequence of the local ones.

**Locality of correction** — a correct upper node survives — follows from composition together with attribution (Ch. 4) *(derived)*.

**Characterization.** *(derived; machine-checked, `Compositionality.T1_characterization`)* Joint sufficiency and non-redundancy are precisely the conditions under which compositionality holds.

**Form and substance.** *(derived)* The verificational form V(p) = AND(V(c)) propagates up tautologically from the two conditions: a characterization, S-independent, the apparatus over Ŝ (Ch. 3). Thm 1's substance is each node's domain soundness (AND-soundness, Ch. 6). For a link with co-children, joint sufficiency read in S, over criteria that capture the goal, is AND-soundness(i) (Ch. 6), and (t, {tⱼ}) ∈ S iff it is true.

The interventionist reading applies to this domain-soundness half, never to the S-free Thm 1: joint sufficiency is the conjunctive intervention succeeding in S; non-redundancy is difference-making at the one background joint sufficiency fixes — ontically separator-hood (Ch. 6), needing no variable set.

A1 (Ch. 1) divides the same way: clause (i) composes upward by Thm 1; clause (ii) is the substance, which only the agent carries (Ch. 4).

**Causal correctness.** Domain soundness at every node is the decomposition's causal correctness (Ch. 3), which the apparatus cannot certify (clause (ii)): Thm 1 holds given a correct decomposition and does not produce one.

### 7.4. Informativeness

**Inf-A.** *(derived)* Binary validation with decomposition locates a problem better than a continuous score without it, a failing child naming its part where a score names none — "7 of 10 subtasks pass" against "73%" — though the two are not Blackwell-comparable in general.

**Inf-B.** *(derived relative to |Act| = 2 and decision-relevance; its Blackwell half by citation [1])* Binary validation captures all decision-relevant information: a continuous scale over the same decomposition is at least as Blackwell-informative, strictly where it is not a garbling of the verdict, but its surplus is decision-irrelevant.

### 7.5. Minimality of the basis

**The basis.** *(derived)* {T, D, Dep, Del} is a derived basis with V derived: induced by T's criteria (Ch. 2), V is composed along D by Thm 1, and validation — |L| = 2, AND, Thm 1 — is derived.

**Minimality.** *(derived)* Removing any element of {T, D, Dep, Del} loses expressiveness. Constructively, each has a class of HVPs not describable without it:

| Remove | Loss | Counterexample |
|---|---|---|
| T | no objects | any HVP |
| D | no hierarchy; Thm 1 impossible | any task of more than one level |
| Dep | causal dependence: deadlines order times, not that one task consumes another's result, and only a criterion referencing the result implies the edge | "B builds on A's result" across branches, no criterion of B referencing it |
| Del | no accountable parties | any HVP with more than one agent |

**Completeness.** *(derived)* Both axioms are exhausted by the basis (§2.8's sources). That no fifth primitive from A1–A2 irreducible to the basis exists is not derived; each candidate examined reduces to it — resources through Dep or criteria, time through the deadline and Dep, a verdict through V, in-progress being its absence (Ch. 2) — and its global form is the basis's uniqueness.

---

## 8. Failure modes

### 8.1. Failure, failure mode and the verdict face

**The computation.** *(defined)* The compositional validation of a non-atomic node t is a computation with inputs criteria(t) and the children tⱼ with their criteria and values V(tⱼ), and rule V(t) := ⋀ⱼ V(tⱼ). It executes as an application: from the fixing f of the split D(t), through the latest evaluation event e, to the verdict as it then stands. At an atomic node (Ch. 2) it degenerates to the node's own contact verdict (Ch. 3).

**Failure.** *(defined)* A failure at t is the failure root (Ch. 3) read on one node: an edge t's validation uses, from f through e to the verdict as it stands, that S denies. The used edges are the split's composition edge, traversed at e by the delivered result; each child's necessity to the parent's criteria — non-redundancy (Ch. 2) read in S — which the rule uses at e; its realizability edge — one result passing all the children's criteria — used from f; each child's value; the rule; and, from e, the verdict. The first three are the split's edges.

```
correct(t) :≡ no edge that t's validation uses lies in Ŝ∖S
```

**Failure mode.** *(defined)* A condition C on (D, V, context) that guaranteed correct evaluation needs, whose violation, the other such conditions held, can yield ¬correct(t).

**Verdict face.** *(defined)* CVC(t) :≡ [computed V(t) = true V*(t)], per node, read at e and as the verdict stands after. It is a consequence of correct(t), not its definition.

**Two ways to fail.** *(derived)* A violation either (a) makes the formula wrong — a split's edge, a value or the rule asserts what S denies — or (b) leaves it not correctly computed, run on a split whose truth nothing obtainable at its fixing showed or on a ground that changed before e. Excluded middle makes the dichotomy exhaustive.

The failure-mode taxonomy classifies the validation computation over the failure root: the modes name the site and phase of a failure's bite — arguments, values, rule, time phase.

### 8.2. The dissection and CA1

**The function.** *(defined)* V(parent) = ⊗({V(tⱼ)}) is a function, determined by its arguments, their values and its rule, and by definition by nothing else.

**The arguments.** A set of arguments is characterized by its membership and the relations — compatibility — among its elements; that it carries no third property the rule could read is argued (extensionally a set is its elements) and carried by CA1.

**The phases.** *(derived)* The application is a process in time with three phases — before, during, after — and no others; pre-condition, invariant and post-condition name these regions of the causal order, not their source.

**The operational axis.** *(derived)* The phases partition events by the strict causal order ≺ relative to the application [f, e]: wholly-before, concurrent (overlapping, causally incomparable) or wholly-after — exhaustive by excluded middle, disjoint since ≺ is irreflexive and transitive and f is not after e. A1 ("pass/fail in finite time") gives the interval its connectedness. The deadline coherence of Dep (Ch. 2) corroborates.

**The phases need only causality.** *(derived; machine-checked, `Time.app_phases_exhaustive`, `Time.app_phases_disjoint`)* The three phases rest on a strict causal order alone, which is causality's definition: a single global clock, **CA2**, only collapses the middle cell into "during [f, e]", and atomicity of the evaluation act is not needed.

**Atomicity.** *(derived)* Atomicity belongs to the dynamics, not the taxonomy: an event partially overlapping a non-atomic evaluation still falls in one of the three classes, and atomicity is needed only for a pure, untorn verdict.

**CA1 (Evaluation Completeness).** *(covering axiom)* A computation is fully characterized by its denotational (domain, values, rule) ⊕ operational (execution in time) semantics, its domain by its arguments' membership and the relation among their criteria; there is no third independent dimension. CA1 covers without asserting disjointness, so it yields a basis, not a partition. That t's validation uses no edge beyond those of §8.1 is CA1's content.

**No third axis.** A decidable predicate over a result is a function of the result's content (denotational) and the check's temporal position (operational); a single result has no other assessable degree of freedom, and cross-task relations are Dep (Ch. 2), a separate primitive. *(covering axiom)* The argument narrows the candidate space without delimiting it, so CA1 is argued, not a bare stipulation, and stays a covering axiom. Its thin residue is the value/time partition for predicates over the execution trace.


### 8.3. The arguments: FM-1 and FM-2

A membership defect of the arguments is FM-1; a relation defect is FM-2.

**FM-1 (Correspondence).** *(defined)* {tⱼ} corresponds incorrectly to criteria(parent), in either direction: *insufficiency* — joint sufficiency (Ch. 2) violated on the split's claim; *redundancy* — non-redundancy violated on it.

**The correspondence condition.** *(defined)* Joint sufficiency ∧ non-redundancy, whose violation is FM-1, has two faces. The apparatus face is the children's correspondence to the written criteria, S-free and checkable a priori. The domain face is the condition read in S — the composition edge, the children's criteria securing the written ones and the written ones capturing the goal, and each child's necessity — as what was obtainable at the fixing shows it. FM-1 is the violation of either. The condition is read on the split's claim as its register (Ch. 2) bounds it, over every result the children can deliver, the delivered result among them.

**Grounding.** *(derived)* The condition is Ch. 2's two conditions read on the split's claim — each criterion through the children mapped to it (Ch. 2) — which grounds its apparatus face; it entails Ch. 2's correctness over all the children and is not entailed by it, a split correct over all its children whose mapping misstates the securing violating it with its verdict correct, the guarantee its claim licenses missing; its domain face is the part of Thm 1's domain soundness (Ch. 7) that what was obtainable at the fixing shows.

A criterion the goal requires and nobody wrote denies the composition edge while every written criterion passes: FM-1.f where what was obtainable at the fixing showed the requirement.

**The FM-1 sub-taxonomy.** *(defined)* A secondary tag, not new modes: each sub-type is ¬(joint sufficiency ∧ non-redundancy) read on one face. In the rows, a risk is statistical when its P is estimable and the event infrequent.

| Sub-type | Sub-clause |
|---|---|
| FM-1.a uncovered-criterion | some cᵢ has no responsible child |
| FM-1.b missing-resilience-vs-predictable-external | a predictable external risk to an outcome a written criterion states, with no mitigation child and — where the risk is statistical — no declared acceptance either |
| FM-1.c missing-risk-grouping | a correlated component, threatening an outcome a written criterion states, whose factors are handled one by one, its common root mitigated by no child and accepted by no declared entry |
| FM-1.d insufficient-entailment | children exist, but ⋀criteria(tⱼ) ⊭ cᵢ — formally, under fᵢ where declared (apparatus face), or in S, the entailment or fᵢ false there (domain face) |
| FM-1.e redundancy | the over-coverage direction — apparatus face: a child addressing no cᵢ, or a child whose criteria can fail while the parent's pass (formal over-strictness); domain face: a child no separator into the region its parent's criteria state (§6.7) where what was obtainable at the fixing showed it, refuted at contact |
| FM-1.f unwritten-criterion | the goal requires a criterion that no cᵢ carries |

**FM-1.d is not a coverage hole.** *(derived)* Every cᵢ has a responsible child; on the domain face the children's criteria entail it formally and S denies the securing.

**FM-1.b and the extraordinary.** *(defined)* An unmitigated event (row FM-1.b) is FM-1.b iff its mitigation or acceptance is required by a faithful map of the domain as obtainable at the fixing, i.e. iff the event then had a precedent in the domain or was derivable from known models, an industry standard or competent neighbours' mitigation being the usual evidence. Otherwise the event is extraordinary at the fixing and it is no FM-1.b.

Maintenance's lack of a static AND-decomposition (Ch. 6) is no repairable FM-1.

**Where FM-1.f is read.** *(derived)* Only where the requirement is read: at contact, by whoever meets and reports the omission, and at the nearest ancestor whose criteria write it, whose validation fails over passing children.

On the node axis (§6.8), the illusory half at the goal vertex — a criterion demanding beyond what G needs — is by itself no mode of a split, the demand lying in the goal's criteria (§6.7); each other half is a mode where what was obtainable at the fixing showed it: the illusory half at a waypoint FM-1.e's domain face, the absent half FM-1.b's missing mitigation, a passage the composition needs that no child's criteria carry (FM-1.d's domain face), or a requirement of G, or of a waypoint, that no criterion writes (FM-1.f). At an atomic root, whose validation is its own contact over the written criteria (§8.1), no validation uses the edge from the written criteria to the goal: the omission is no failure mode of that validation, whose verdict is true, but a FAITHFULNESS failure of the goal's setting (§3.6), read only at contact.

**FM-2 (Consistency).** *(defined)* The children's criteria are jointly unsatisfiable, no result passing them all: on the map, criteria(t_a) demands X, criteria(t_b) demands ¬X — its apparatus face — or in S, which admits no such result — its domain face, the realizability edge denied as what was obtainable at the fixing shows it. The compatibility condition on the children's criteria is the one whose violation is FM-2. On the failure root, FM-2 is used edges jointly asserting a passage no result can take, on the map's own terms or in S as the fixing could show it.

**Grounding.** *(covering axiom)* The compatibility condition is not Ch. 2's but argued: the one relation among the children the rule's inputs carry is the mutual satisfiability of their criteria, and that they carry no further one belongs to CA1.

### 8.4. The values: FM-3

**Truth.** *(derived)* By A1 and |L| = 2 (Ch. 7) a decidable predicate's only semantic content is its truth, binarity forbidding a second; so a value's single property relative to reality is truth, and truth is two-directional.

**FM-3 (Veracity).** *(defined)* *(v3.9: Verifiability)* A value is untrue in either direction — false PASS or false FAIL. Its object is a value a verdict is formed from: a child's verdict as its parent reads it, and the node's own verdict where it **stands alone** as a contact (Ch. 3), AND of the children's true values giving none — at an atomic node, and where an active child's recorded value is not of the delivered work, at ⊥ or true of work the delivery has since replaced. The truth condition holds on every such value; its violation is FM-3. At an atomic node it is the only condition that bears.

**False FAIL is guarantee-safe.** *(derived)* AND absorbs fail (Thm 2, Ch. 7), so a false FAIL creates no false acceptance.

The slack of an over-strict split (FM-1.e's apparatus face) is priced in this direction: under 100 + 100 ≤ 200 a backend at 120 beside a frontend at 50 fails its child and passes the parent, at the cost of a possible false FAIL of the parent.

**A1's residue.** A binary but insensitive criterion yields a false PASS, FM-3's wherever a verdict is formed from it: A1 (i) buys no sensitivity (d6, Ch. 4) and A1 (ii) is apparatus-uncertifiable (§3.7). Of the seam conditions' residues, A1 (ii)'s thus coincides with a named boundary, FM-3's uncertifiability; A2's (§3.7) with none.

### 8.5. The rule: FM-4

**FM-4 (Propagation).** *(defined)* The rule's single property is correctness of transmission; AND being fixed (Thm 2, Ch. 7), its only possible defect is computing something else *(derived)*. FM-4: ⊗ does not compute AND, in either direction — it drops a child's fail, or fails where every child passes. A verdict departing from the AND of the children's values is FM-4 where a rule computes it from those values, whatever its truth, and where it is a contact over the delivered result (Ch. 3), only if untrue. A contact's true departure is the mode of what it departs over: a child's untrue value, FM-3; else no failure where AND of the children's criteria read on the delivered result gives the verdict, which arises only where the verdict stands alone (§8.4); otherwise a denied edge — a child's necessity under a true PASS, the composition edge under a true FAIL. The propagation condition, the rule computing AND, is the one whose violation is FM-4. On the failure root, FM-4 is a verdict endorsing a composition edge its leaves have refuted, or refusing one they all support.

**Internal completeness.** *(covering axiom)* Three components with four defining properties — correspondence and consistency (arguments), truth (values), correctness (rule) — give four modes, FM-1 to FM-4; a component cannot be defective otherwise than through its defining property, modulo CA1.

### 8.6. The computation: FM-6, FM-5 and the after phase

**FM-6 (Feasibility).** *(defined)* [before] D(t) is not definable when fixed, the information determining it not yet obtainable; a split fixed anyway is a guess whose composition edge holds only by luck (d4, Ch. 4). The definability condition — the truth of the split's edges was obtainable when it was fixed — is the one whose violation is FM-6. On the failure root, FM-6 is a split's edge (§8.1) posited and used before its ground is determinable.

**Remedy for FM-6.** Defer the split until contact has made it definable.

**FM-5 (Freshness).** *(defined)* *(v3.9: Currency)* [during] Between the split's fixing and e something its edges rest on — the spec, an input, a world condition — changed and D(t) was not updated, so the function computes over stale data. The freshness condition — nothing the split's edges rest on changed over [f, e] — is the one whose violation is FM-5. On the failure root, FM-5 is the referent of a used edge changing under it.

Under concurrency the middle phase reads as a race, which FM-5 generalizes to rather than weakening; a torn read is FM-3 or FM-5, inside the taxonomy. A coupling a decomposition leaves out of Dep is no mode of its own. Met at execution by a consumer running against an input its map did not connect, the input changing under it over [f, e], it is FM-5, the race above. Where it also makes the children's criteria jointly unsatisfiable it denies the realizability edge, FM-2; where it leaves them not securing the parent's, formally or in S, it denies the composition edge, FM-1.d; each where the denial was obtainable at the fixing, and FM-6's or FM-5's by its ground otherwise. Where it denies none of these edges — a producible prerequisite the work lacks, a passage the children's criteria carry with no producer in the plan, nothing changing under it — it is a failure of the plan's Dep that no validation uses, instantiating no mode.

**The after phase.** *(derived)* It holds no condition: the verdict is a value of criteria over the result as delivered, so it is true after e exactly when at e, and a failure of t's validation found after e is that of a condition violated at or before e, found late. A defect that arose after e because the world moved is not this node's: it is a consumer's, read in the consumer's own phases, or a task a maintenance generator emits (Ch. 6).

**External completeness.** *(derived)* Three phases with a condition in two — definability before, freshness during — give FM-6 and FM-5: a split's edge (§8.1) false at e is FM-1's, FM-2's for the realizability edge, or, with that mode held, FM-5's where it rests on something that changed and FM-6's where its falsity was not obtainable at the fixing — three causes of one denial. FM-6 and FM-5 are process-phase mishandlings of the map, not exceptions to the root.

**Where each condition is read.** *(defined)* Correspondence and compatibility on the split as fixed (§8.3); truth and propagation at e; the operational conditions over their phases (§8.2).

### 8.7. The integration cases

**Carriage names the mode.** *(defined)* For a used composition edge whose integration S denies, how the map carries the integration names the mode. A written integration criterion the children's criteria do not entail is FM-1.d's apparatus face, a FORM wall (Ch. 3). On a split clean in form the integration is carried by no criterion, or by one the children's criteria entail, whose check decides how the denial shows:
- (i) *coverage hole:* no criterion carries the integration (forgotten glue) — FM-1.f;
- (ii) *insensitive edge:* the check cannot distinguish the divergence and passes — FM-1.d's domain face; its false PASS is FM-3's as §8.4 reads it;
- (iii) *refuted edge:* the check discriminates and fails truly over passing children — FM-1.d's domain face.

A denial not obtainable at the fixing is routed by §8.6.

Cases (i) and (ii) pass silently; (iii) is the apparatus catching the wall. Case (ii) is the irreducible residue of faithfulness (Ch. 3).

AND-soundness's integration implication (Ch. 6) fails through these three cases. The composition function's verificational face V(p) = AND(V(c)) (Thm 1) is clean only if its integrational face, the glue, is itself carried by a criterion. A decomposition is a pre-registered hypothesis whose failure (§4.3) is attributed to the split, not the executors (Ch. 4): FM-1's insufficiency, or FM-6 or FM-5 by its ground.

### 8.8. Completeness and independence

**Theorem (completeness as a basis).** *(covering axiom)* The conjunction of the six conditions ⟹ correct(t); hence ¬correct(t) ⟹ at least one fails: FM-1…FM-6 are six failure modes, proved complete as a basis analytically, modulo CA1. The converse is not claimed and fails instance by instance.

*Proof (coverage).* A failure violates the formula or its computation (§8.1). Formula: arguments → correspondence (FM-1) or consistency (FM-2); values → truth (FM-3), of a child's value or the node's own verdict; rule → transmission (FM-4). Computation: before → FM-6; during → FM-5; after → none (§8.6). Each step is an exhaustive dissection modulo CA1, so the six leaves cover the failure space. ∎

**Independence.** *(derived)* Each mode has a scenario where it alone is violated and a used edge is denied, so none can be dropped. The six independence witnesses:

| FM | Isolated scenario |
|---|---|
| 1 | every criterion has a responsible child, but a subtask a written criterion needs is forgotten: every child passes and that criterion fails (FM-1.d) |
| 2 | D sufficient and non-redundant over every result it can produce, but two children's criteria contradict, each handing down one of two demands the parent's criteria make, so no result passes them all and none attains the goal as written; the FAIL is true, the route is the wall |
| 3 | D correct, but a child's pass was given without checking: a false pass |
| 4 | D correct, values true, but a child's fail is not transmitted to the parent |
| 5 | D correct when fixed, but the spec changed before the verdict and D was not updated |
| 6 | the information for D was not obtainable at its fixing; D, consistent with all that was, is false in S with nothing it rests on changed |

**Corollary.** *(covering axiom)* Modulo CA1 the six modes are a complete independent basis; 6 is its dimension, not a count of labels per failure.

The six modes are the spectrum of the structural half's thinness (Ch. 4). The five links are falsifiable as this basis is, by their falsifiers (§5.4).

### 8.9. The verdict face

A failure can leave the verdict right: a true FAIL over a split no result of which can pass (FM-2), the unwritten criterion (FM-1.f), V being the conjunction of the written ones, a false PASS absorbed by a truly failing sibling.

**Coincidence.** *(derived)* Violated correspondence, definability or freshness can leave every traversed edge true, the evaluation then correct by coincidence (d4's luck, Ch. 4). A violation of FM-2, FM-3 or FM-4 is itself a denied edge and always a failure; only its verdict can be right by coincidence.

**Corollary (without CA1).** *(derived)* With FM-6, FM-1 and FM-5 absent the composition edge holds at e for the delivered result; with FM-3 and FM-4 absent too, Thm 1 (Ch. 7) gives CVC at e where the node's own verdict does not stand alone, and the truth condition on it gives CVC where it does (§8.4); CVC holds after e. Five conditions bear on the verdict; FM-2 bears on the route alone.

### 8.10. Summary

**Geometry.** The six modes, a fine cut beneath the coarse FORM ⊕ FAITHFULNESS cut (Ch. 3), split 4 denotational ⊕ 2 operational (§8.5, §8.6), a partition orthogonal to the coarse cut.

**Scope.** A goal outside the model (Ch. 2) is the model's boundary, not a failure mode *(boundary)*. A maintenance failure's carrier (§6.11) instantiates no per-tree mode, nor does, by itself, a defect of a root's own criteria — a demand beyond what the goal needs (§6.7), or at an atomic root a requirement none writes (§8.3) or criteria jointly unsatisfiable, its true FAIL using no denied edge — a failure of the goal's setting.

---

## 9. Standards and checks

### 9.1. Standards and the three verification levels

Standards are the checkable rules a decomposition must meet, each addressing a failure mode (Ch. 8).

A standard is checked at one of three verification levels, set by the information the check reads:

- the **Syntactic level** (Level 0) reads the graph and the task's fields, never what a criterion means;
- the **Semantic level** (Level 1) reads besides the criteria's formal content — their entailment and joint satisfiability, with the composition function fᵢ (Ch. 2) where one is declared;
- the **Pragmatic level** (Level 2) reads a domain model: causal correctness, the children's criteria securing the parent's in the real world, unverifiable without domain knowledge.

The Syntactic and Semantic levels are a priori over Ŝ — FORM (Ch. 3); the Pragmatic level is the faithfulness axis (Ch. 3), checkable only by execution. The first two therefore discharge what is dischargeable a priori of D's correctness.

**Exhaustiveness.** A decomposition is a formula, and knowledge about a formula is exhausted by its syntax (how it is written), semantics (what it means formally) and pragmatics (what it means in the real world) [18] — the covering axiom CA-Morris, taken from Morris with no argument of its own narrowing the candidate space, unlike CA1 (Ch. 8) and like CA-Links' representational branch (Ch. 5) *(covering axiom; by citation)*.

### 9.2. STD-1: the ACCEPTED_RISKS register

**STD-1.** Every decomposition carries its ACCEPTED_RISKS register (Ch. 2) as an explicit list of consciously accepted risk factors, each entry with four fields *(defined)*.

```
accepted_risks:
  - factor: <name>
    estimate: <P, impact>
    justification: <why we accept it>
    invalidation_condition: <when to revisit>
```

On the functional scale (Ch. 6) an entry names a difference the map's coarsening ≈_G merges that may prove a scale leak: the register declares the leaks the split's claim risks.

As the split's attribute (Ch. 2), the register is its decomposer Del(t)'s statement about his own split, authored and changed only with it; a leaf's is vacuous. A register carried in the task's own fields, a pre-filled one, is task data, not the split's register.

An entry is one of the register's risk events (Ch. 2), with an estimable P, never a criterion, and the register exempts none from validation. A factor already materialized is no entry: with no uncertainty left, it is a report bearing on a criterion's value. The register **admits** an entry whose risk is statistical (§8.3), other than the split's own denial by S, the claim's negation; only an admitted event bounds the split's claim, its bite FM-5 or FM-6 by its ground (§8.6), charging the split's author nothing; an entry not admitted licenses nothing.

A conscious scope boundary of the goal has no materialization P, so it is no entry; the goal's own criteria carry it, an unobvious exclusion optionally marked by a SCOPE tag in the goal's spec. EXTERNALIZE (Ch. 4) writes the register out as risk events, never as scope.

With its invalidation conditions, the register is the declared range of perturbations with an estimable P over which the split's claim is asserted. That the declared range lies inside the real one is itself an Ŝ-claim, not certifiable a priori (Lemma 1, Ch. 3) — hence an invalidation condition, not a guarantee.

### 9.3. STD-2: predictability

**STD-2.** Events are classified by predictability, with the burden of proof shifted *(defined)*:

| Category | Criterion | Status in the decomposition |
|---|---|---|
| Ordinary | Occurs regularly in the domain (P estimable from data) | Mandatory in the decomposition |
| Statistical | (§8.3) | In the decomposition, or in ACCEPTED_RISKS with justification |
| Extraordinary | No precedent in the domain AND not derivable from known models | Admissible to omit |

"Not derivable from known models" means that no known causal chain or statistical model predicts the event with an estimable probability. Predictability is presumed: whoever asserts unpredictability proves it — not "I didn't know" but "it was impossible to know". With FM-1.b's test (Ch. 8) the criterion becomes a checkable question about domain norms, its residue a local, empirical threshold of domain precedent.

STD-2 is an admissibility criterion for omission: it adds and removes no children, and decides whether a non-covered external trigger to an outcome a written criterion states is FM-1.b or a licensed omission; an outcome no criterion states is FM-1.f where the fixing showed the requirement (Ch. 8), whatever the trigger's grade. The grade judges the decomposer, not the event: an extraordinary event that bites is still a failure, FM-5 or FM-6 by its ground (Ch. 8), and what the grade acquits is FM-1.b.


### 9.4. STD-3: risk grouping

**STD-3.** Correlated factors are grouped into components with a common root cause, factorizing the risk space; the components cover a threshold share of historical problems — 90% by default, a parameter the standard does not derive, calibrated in deployment *(defined)*. The grouping method (PCA, clustering, expert taxonomy) is an implementation choice.

Each component is either mitigated by a risk node — a child addressing the parent criterion that states the goal's outcome under the component's events — or, where STD-2 grades it statistical, accepted by one grouped ACCEPTED_RISKS entry. A risk node is an ordinary child of the split (Ch. 2). Where the task carries no criterion on the component's events, a mitigation child would address no criterion: where what was obtainable at the fixing showed the requirement, the omission is the task's own FM-1.f (Ch. 8), sourced in its criteria, which the decomposer reports to its author, no register entry standing in for a criterion (§9.2).

The register turns an implicit assumption (P = 0, unstated) into an explicit one (P ≈ ε, justified) that is refutable (the invalidation condition), auditable (the justification) and aggregable: over independent components P(≥ 1) = 1 − ∏(1 − Pᵢ). The roll-up runs over STD-3's components, not over correlated raw factors.

### 9.5. STD-4 and the Syntactic level

*(v3.9: "Structural validation")*

**STD-4.** The form is checked automatically, as far as the built checks reach (Ch. 4), at the levels of §9.1, by a battery that counts **nine** CHECKs — CHECK-1, 1b, 2–8 *(defined)*. A battery arrow names the mode the check guards or proxies.

The Syntactic level reads topology, the mapping of children to criteria, deadlines, the register's form and the Del the split names for each leaf.

```
CHECK-1 (coverage):       ∀ cᵢ ∈ criteria(t), ∃ tⱼ ∈ D(t) responsible for cᵢ → FM-1.a
CHECK-1b (no-orphan):     ∀ tⱼ ∈ D(t) addresses ≥ 1 cᵢ → FM-1.e
CHECK-2 (acyclicity):     the graph of D is a forest (each node at most one parent), Dep acyclic → FM-5
CHECK-3 (deadlines):      ∀ (t_a, t_b) ∈ Dep: deadline(t_a) < deadline(t_b) → FM-5
CHECK-4 (accepted risks): for D(t) ≠ ∅: the register exists, is nonempty, and each entry carries STD-1's four fields with its estimate (a P and an impact) filled → FM-1
CHECK-5 (risk nodes):     ∀ component K from STD-3: ∃ a risk node ∨ K's grouped ACCEPTED_RISKS entry → FM-1
CHECK-6 (delegation):     ∀ leaf t of the split: Del(t) named → no FM
```

CHECK-4 and CHECK-5 are proxies of FM-1.b and FM-1.c: they check the form their standard requires, so a lone failure of either need not be the mode's.

CHECK-2 holds of the whole graph: any Dep edge that closes a cycle violates it — declared by a split, discovered in execution, or a criterion come to reference another node's result, that reference being a Dep edge (Ch. 2).

**CHECK-4's "nonempty".** Premise: the split's denial carries an estimate *(premise)*. Every split is a pre-registered hypothesis (Ch. 8) whose composition edge no discipline certifies a priori (Lemma 1, Ch. 3), so at least one uncertain event stands behind every split — its denial by S *(derived)*. The denial's P is the recorded refutation rate of comparable splits where one exists, otherwise the decomposer's stated estimate with its justification; writing it is a true report. The denial entry is correlated with the others — a materialized entry raises the chance of denial without forcing it — so it is grouped with none and stands beside the roll-up of §9.4, not in it.

**CHECK-6 guards no failure mode** *(derived)*. Del being total (Ch. 2), a leaf without Del would leave only what an owned leaf whose work never starts leaves: the parent computes no verdict, using no edge of Ŝ∖S (Ch. 3), or is validated over the missing work, an untrue PASS there being FM-3 and FM-4 at the parent (Ch. 8) — which CHECK-6 holding does not exclude.

The battery does not check form item (4), what a declared Dep edge carries (Ch. 4), because Dep is stated in one direction only — a referencing criterion ⟹ an edge (Ch. 2) — and the form list does not fix where the integration criterion lives.

### 9.6. The Semantic level: CHECK-7 and CHECK-8

```
CHECK-7 (formal sufficiency): ⋀{criteria(tⱼ) : tⱼ mapped to cᵢ} ∧ fᵢ ⊨ cᵢ → FM-1
CHECK-8 (consistency):        ⋀{criteria(tⱼ) : tⱼ ∈ D(t)} is satisfiable → FM-2
```

| Criteria type | CHECK-7 (sufficiency) | CHECK-8 (consistency) |
|---|---|---|
| Numeric bounds | Arithmetic: O(n) | Interval intersection: O(n) |
| Boolean flags | Substitution: O(n) | Conjunction: O(n) |
| Set membership | Subset check: O(m), m the set's size | Set intersection: O(m) |
| Arbitrary formulas | undecidable in general; decidable theories via SMT (co-NP-hard already for propositional) | undecidable in general; decidable theories via SMT (NP-hard already for propositional) |

A1 makes each criterion decidable, not entailment or joint satisfiability between criteria. Where those are undecidable, CHECK-7 and CHECK-8 run at the Semantic level's **informal end**, a judgment no procedure mechanizes.

```
parent criterion: response_time < 200ms
composition:      response_time = backend_time + frontend_time
child_1 criteria: backend_time < 100ms
child_2 criteria: frontend_time < 100ms
CHECK-7:          backend < 100 ∧ frontend < 100 ⟹ sum < 200 ✓
```

Two non-strict child bounds would not entail the strict parent criterion. "backend < 150ms + frontend < 150ms" passes CHECK-1 but not CHECK-7, since 150 + 150 > 200; CHECK-7 decides FM-1.d's apparatus face (Ch. 8). No pre-execution CHECK tests non-redundancy's formal face, the over-strict slack of FM-1.e (Ch. 8).

A mode falls on the side its object sits on: the children's mutual satisfiability — FM-2's apparatus face, read by CHECK-8 — is on the map, within φ-composition.

Prohibition has no form guard: a criterion forbidding nothing on the map — its fail-extension empty (Ch. 1), its negation unsatisfiable, decidable where CHECK-8's satisfiability, the dual, is — is FORM no built CHECK reads; one whose fail, possible on the map, S never attains while the goal it checks goes unattained is A1's residue (§8.4), met only at contact; FM-3's truth condition, demanding discrimination, is prohibition's semantic strengthening.

### 9.7. Discharging a Semantic flag

A Semantic flag is FORM found a priori: acting over it carries a FORM defect on a map already known to be false. It is discharged by the party who owns its source: the decomposer repairs his split, or enters the gap in his register where it is an uncertain event STD-2 grades statistical; a flag sourced in the task — its criteria jointly unsatisfiable — only the task's author repairs, the decomposer reporting it. At the informal end a flag is a judgment the decomposer owes.

### 9.8. The levels, each irremovable

Each level fails with the other two holding *(derived)*: a split with no register, its entailment and its composition in S intact (Level 0 alone, CHECK-4); criteria not entailing the parent's (150 + 150 > 200) in a domain where the frontend never exceeds 40 ms (Level 1 alone, CHECK-7); a split clean in form that S denies (Level 2 alone, FAITHFULNESS, Ch. 3). The per-element argument is the canon's, as for the links (Ch. 5); CA-Morris carries only "no fourth".

### 9.9. The cost of checking: verify vs explore

The checking cost `c_check`, the price at which FORM is caught a priori over Ŝ (Ch. 3), is graded by level. The Syntactic level is mechanical, cheap and mandated. The Semantic level is cheap on numeric bounds (SMT: 100 + 100 ≤ 200); its informal end is expensive. Latent in A2's capacity cost (Ch. 1), the cost is here a per-unit magnitude.

Above κ (Ch. 3) one always decomposes (A2), so the real decision at every node and level is

> **VERIFY** (pay `c_check`, cut the FORM risk before acting) **vs EXPLORE** (act on the under-checked plan and let contact check it).

Exploration is a conscious substitution of contact for the a-priori check: contact alone opens faithfulness (Ch. 3), so acting buys information unobtainable otherwise *(derived)*.

**The rule.** VERIFY down to the level ℓ where the marginal `c_check(ℓ)` < the marginal prevented FORM risk; above it, EXPLORE. The Syntactic level and cheap-SMT Semantic checks (`c_check ≈ 0`) always run; the informal end runs only where the prevented risk justifies it.

The tradeoff's structure is derived; its cost and probability values are contextual, contingent as S is (Ch. 3), and the canon fixes none. The cost is the edge decoration of Ch. 5.

### 9.10. The standards and FM-1

STD-1 and STD-3 are coverage standards operationalizing FM-1's joint-sufficiency clause: STD-1 makes the declared boundary of coverage visible, STD-3 contributes risk nodes. They guard FM-1 without being it.

Ch. 8's FM-1 witness passes the whole Syntactic level. By sub-type:

| Sub-type | Level | Guard |
|---|---|---|
| FM-1.a uncovered criterion | Syntactic (L0, topological) | CHECK-1 |
| FM-1.b missing resilience vs a predictable external | Pragmatic (L2) | STD-2, the decomposer's own rule; CHECK-4 (L0) its proxy (§9.5) |
| FM-1.c missing risk grouping | Pragmatic (L2) | STD-3, the decomposer's own grouping; CHECK-5 (L0) its proxy (§9.5) |
| FM-1.d insufficient entailment | apparatus face: Semantic (L1); domain face: Pragmatic (L2) | CHECK-7 on the apparatus face; no CHECK on the domain face |
| FM-1.e redundancy | apparatus face: Syntactic (L0) the orphan, Semantic (L1) formal over-strictness; domain face: Pragmatic (L2) | CHECK-1b for the orphan; no CHECK for formal over-strictness or the domain face |
| FM-1.f unwritten criterion | Pragmatic (L2) | no check over the written criteria |

Read off the battery's arrows, FM-3, FM-4 and FM-6 are guarded by no structural CHECK; FM-1, FM-2 and FM-5 have structural guards.

---

## 10. Parties and seams

### 10.1. Roles

Task transfer is a peer-to-peer transaction between two roles. The **Issuer** forms the task's **packet** — spec, criteria, deadline, the pre-filled ACCEPTED_RISKS (Ch. 9), a rework bound and Del, the executor it is handed to — and validates the result. The **Executor** executes it and delivers the result. *(defined)*

A node's issuer is Del(parent) (Ch. 2); a root's issuer is the goal's issuer, outside the graph — at a self-assigned root its own executor. *(defined)* The composition functions fᵢ (Ch. 2) are therefore declared by the holder of the parent, the children's issuer.

Authority is not a primitive: it is the accountability edge Del(t) → Del(tⱼ), tⱼ ∈ D(t), over the hierarchy recursive D and Del generate (Ch. 2), present exactly where Del changes along an edge. *(derived)*

The issuer role outlives the parent's own contract: a child's contract is with its issuer and does not lapse when the parent's own work ends, so a child keeps an issuer until its own contract ends, a change of Del(parent) moving the role at that change. Del, not consent, names the role's holder, so the role holds before he has agreed to the parent task himself: a window in which one who has not agreed acts as issuer, a disclosed cost. *(derived)*

### 10.2. Check and signature

Validating a node is two acts. The **check** evaluates the node's criteria on the result as delivered: V's evaluation (Ch. 2). The **signature** issues the verdict, accepting or rejecting the result, and belongs to the node's issuer. *(defined)*

An implementation may run a check of its own on every delivery, at any node.

In the protocol the rule's slot is the issuer's check, a contact verdict (Ch. 3), so FM-4 is FAITHFULNESS — its untrue departure from AND (§8.5), FM-3 as the parent sees it — not the FORM a rule computing on the map makes it.

### 10.3. Seams

A node is **public** iff it is a delegation seam: Del(child) ≠ Del(parent), or a root not self-assigned. A node with Del(child) = Del(parent) lies inside one scope and is **internal**. *(defined)* The labeling is derived from Del and needs no mechanism of its own.

A public node's issuer is never its executor, and its result crosses into an independent scope. There the seam requires **separation of duties (verifier ≠ executor)**: the verdict is signed independently, over a check that is not the executor's. *(derived)*

Separation of duties is therefore not a property of {D, Dep, V} but a boundary term of the Del hierarchy: the verifier ≠ executor gate fires at the seam, on an authority edge (§10.1), not at every node. *(derived)*

An internal node self-verifies: its verdict, signed by its own executor, reads a check whoever performs it — he, an instrument or an implementation, another agent whose per-criterion record the signature reads *(derived)*; below the seam the canon requires no further check.

Internal self-verification is safe. The public node is validated directly against its own criteria at the seam, and under a correct decomposition public V = pass is equivalent to all children passing (Thm 1, Ch. 7, non-redundancy direction). The agent stakes all internal work its public delivery carries on one public validation. *(derived)*

Separation of duties is a property of the seam, not a ban on internal self-checking. A verdict signed by its own executor is **carried** while its node is internal and a delivery of its agent's public node, validated by another party, follows it — made, or still possible; separation of duties is violated exactly at a self-signed verdict not carried *(derived)*. One context that sets the contract, delivers and accepts its own delivery violates it — a dispute against oneself is meaningless; what is forbidden is the coincidence of the roles, not the issuer's own pair of duties, forming the task and signing its verdict.

An agent, the scope-bundle of Ch. 4, is a compression of domain structure, unpacking the five links (Ch. 5), with no seam inside it.

Under a fully self-assigned agent, one Del over its whole graph, what remains is explicit derived criteria and verdicts reading their checks: a discipline, not a guarantee of method quality. *(derived)*

Separation of duties is per-transaction and leaves a residue one level up. Where the parent's issuer also executes the child that alone discharges one of the parent's criteria, that criterion is in effect self-validated one level up. No seam is breached, the child being independently validated at its own seam; "separation of duties at every seam" claims no more than that. *(derived)*

The public/internal boundary is scope-relative, the scope boundary chosen (Ch. 4): the criterion tells this seam under this Del, not the right granularity; κ forces only the agent-relative floor of the leaf test (Ch. 3), and the canon requires no seam below the root, an added check (§10.2) being no handoff.

### 10.4. Agent-agnosticity

Any agent — human, AI, robot — implementing the Agent interface is a valid participant; H→H, H→AI, AI→H and AI→AI run one protocol. *(defined)*

```
Interface Agent:
    receive(packet) → Signal
    deliver() → ResultPacket
    validate(result, criteria) → Verdict
    handle_signal(signal) → Signal
```

Autonomy is a per-task, per-role property, not a global mode. *(defined)*

| Level | Issuer/Executor | LLM role | Human role |
|---|---|---|---|
| manual | Human | Not involved | Decides everything |
| assisted | Human + LLM | Proposes (draft → approve) | Decides |
| autonomous | LLM | Decides | Oversight at the level above |

The protocol and the CHECK battery (Ch. 9) are identical at all levels, switching being Del(t), who occupies the role: GFSO is not an autopilot by default.

Thm 1 (Ch. 7) and the whole plan {T, D, Dep, V} are checkable independently of who is assigned, since V references criteria, not the executor; this grounds agent-agnosticity. *(derived)*

The agent Ch. 4 derives as the necessary carrier of domain content is any such participant, human or LLM, and no result changes with the carrier.

Agent-agnosticity is interchangeability at the interface; the agent interchangeability the model predicts (Ch. 4) is conditional, equal only at equal faithfulness of Ŝ-content.

---

## 11. Signals and the log

### 11.1. The protocol and its log

The protocol operationalizes the primitives (Ch. 2) and the standards (Ch. 9) at runtime: a standard task-acceptance transaction between the roles of Ch. 10, conducted by signals. *(defined)*

The protocol keeps one append-only log; every signal and every protocol act is appended to it with its data and a timestamp. *(defined)*

### 11.2. The twelve signals

The protocol has 12 signals: five from the executor to the issuer, seven from the issuer to the executor. *(defined)*

**Executor → Issuer:**

| Signal | What it carries and does |
|---|---|
| ACCEPT | The task accepted; fixes the start of the obligation |
| CHALLENGE(reason) | The spec is defective; names the packet fields it questions. The channel for a spec defect met at contact — FM-1 or FM-2, FM-6 or FM-5 by its ground (§8.6), or a criterion not decidable, form item (1) of Ch. 4 and no mode — before delivery, or as its repair after a FAIL computed over it |
| BLOCK(reason) | A blocker to the work. Answers FM-5 as the channel for changed conditions met at contact; may record a discovered Dep edge |
| DELIVER(result, self_validation) | The result is ready; hands over the artifact and a self-check |
| CONFIRM_CANCEL(in_flight_state) | Confirms the cancellation, fixing the wind-down and the in-flight state at the moment of cancellation, its provenance |

**Issuer → Executor:**

| Signal | What it carries and does |
|---|---|
| ASSIGN(packet, reason) | The task handed over; initiates the transaction |
| ACCEPT_CHALLENGE(new_spec) | The dispute's positive closure: the executor learns his challenge was accepted |
| REJECT_CHALLENGE(justification) | Dispute resolution with justification |
| PASS | Result accepted: V(t) = pass; a true PASS departing from AND over a child the check shows unneeded carries a split's denial met at the node's own check to its decomposer, as FAIL does |
| FAIL(criteria[]) | Not accepted: V(t) = fail. Answers FM-3 by citing the failed criteria, and carries a split's denial met at the node's own check to its decomposer |
| CANCEL(reason) | Cancellation, the refusal of the task. Answers FM-5 by invalidating the task and its subtree |
| RESOLVE_BLOCK(action) | The blocker's in-contract resolution: the work's conditions restored, answering the BLOCK |

The signals the Agent interface exchanges (Ch. 10) are these twelve.

### 11.3. What each signal carries

**ASSIGN.** Each ASSIGN installs a version of the task's packet, and a re-ASSIGN is an ASSIGN under an id already issued. *(defined)* An ASSIGN's reason is signal data logged with it, not part of the packet.

**ACCEPT.** Consent, once given, stands for its version.

**CHALLENGE.** A CHALLENGE may be sent before consent and after it, while the work is under way, because a spec defect the a-priori check misses surfaces at contact. *(derived)* A rejected CHALLENGE forces nothing; the dispute has no counter of its own.

**ACCEPT_CHALLENGE** installs a packet exactly as an ASSIGN does, and the executor again ACCEPTs or CHALLENGEs the new contract.

**REJECT_CHALLENGE.** It returns the task to the wait the challenge interrupted — consented work, or the offer before consent — under the same packet version with the rework count unchanged.

**BLOCK.** A BLOCK is a report, not a question on the packet: it questions no field, and a re-ASSIGN adjudicates it only as far as its reason states an adjudication.

A BLOCK that exposes an undeclared cross-task prerequisite records a provisional discovered edge — source the prerequisite node, target the blocked task — adopted into Dep only when the issuer's answer confirms it, its provenance the BLOCK event.

Promoting a blocker into a node is mandatory when it is a producible in-scope artifact, one with a candidate producer. Only the non-producible — force majeure, a vendor failure — counts as external, with no Dep edge. Below a root the promotion is owed by the blocked task's issuer, who adjudicates the BLOCK, by changing the split he holds.

The backward attribution (Ch. 4) is carried by CHALLENGE and BLOCK.

**DELIVER.** A delivery presents the result as it stands at DELIVER; work its executor continues in his subtree while it is validated reaches a verdict only through a new delivery. This is the after phase (Ch. 8) in the protocol.

At an internal node (Ch. 10), the check the verdict reads may be the self_validation DELIVER carries.

**CANCEL.** A parent's acceptance settles none of its children; the issuer's remedy for a child no longer needed is CANCEL.

**RESOLVE_BLOCK** is the pure unblock; a resolution changing a packet field, such as moving the deadline, is a re-ASSIGN for re-consent.

**A signal is a report,** never a verdict on its sender or its receiver: an unanswered BLOCK or CHALLENGE stays an unadjudicated claim, and reading the log for fault is a reader's act outside the protocol.

### 11.4. Why these twelve

Contact is the one operation that reads S (Ch. 3), and an agent must carry it (Ch. 4). A protocol forcing honest directed action (Ch. 1) must therefore (i) route every contact verdict met in a transaction, (ii) give every failure mode met at contact, while its finder's report is admissible, a channel to the party who can act on it — FM-4, the issuer's own verdict, needing none, and a split's denial reaching its decomposer by his node's verdict (§11.2) or a child's CHALLENGE — and (iii) close the incentive seams a signal can close, the deviations profitable to one party for which the transaction offers the other no detecting channel though a signal could carry one; a report no check reads stays open whatever signal is added. The twelve signals are that closure. *(derived)* The protocol is thus derived from A1 + A2 (+ CA1) through the failure modes to the signals, relative to the adopted design decisions (Ch. 0).

**Minimality.** Removing any signal yields a defect of one of four types: **operation** — the protocol cannot start; **FM** — a failure mode (Ch. 8) loses its channel; **IC** — such an incentive seam stays open; **FSM** — the signal is the only non-degenerate move toward the transaction's forward target under the unchanged contract, without which the target is reached only by a degenerate route — through a **catch-all**: a re-ASSIGN, a CANCEL or the expiry of a wait — or not at all. *(defined)*

| Remove | Type | Consequence |
|---|---|---|
| ASSIGN | Operation | No initiation: the protocol is empty |
| ACCEPT | IC (also FSM) | The contract is not fixed, and the executor later repudiates the terms unilaterally |
| CHALLENGE | FM-1/2 | A spec defect met at contact is computed over unreported, and a FAIL computed over it has no dedicated channel to its repair |
| BLOCK | FM-5 | The executor cannot report a blocker |
| DELIVER | FSM | The result never reaches validation, and no task is ever accepted |
| CONFIRM_CANCEL | FSM | A cancellation completes with no in-flight report, which only the executor can give |
| ACCEPT_CHALLENGE | IC | The dispute has no positive closure: a re-ASSIGN still updates the spec, but the executor cannot tell an accepted challenge from an unrelated rewrite |
| REJECT_CHALLENGE | IC (also FSM) | The dispute has no negative closure: a challenge ends only by changing the contract or closing the task, so a false CHALLENGE becomes a free veto |
| PASS | FSM | No task is ever accepted |
| FAIL | FM-3 (also FSM) | No rejection cites the failed criteria: the issuer can still CANCEL or re-ASSIGN, but the executor never learns what failed |
| CANCEL | FM-5 | Stale tasks are never cancelled by the issuer's decision |
| RESOLVE_BLOCK | FSM | The blocker has no in-contract resume path |

12 is minimal — no signal removable, in the sense Ch. 7 gives minimality; the count is of acts, each answering its own defect, by type FM (4: CHALLENGE, BLOCK, FAIL, CANCEL), FSM (4: DELIVER, CONFIRM_CANCEL, PASS, RESOLVE_BLOCK), IC (3: ACCEPT, REJECT_CHALLENGE, ACCEPT_CHALLENGE), operation (1: ASSIGN) *(derived)*.

A signal's primary type is the defect its own removal row rests on. REJECT_CHALLENGE, ACCEPT and FAIL carry a second type, FSM, that follows from their content — the unchanged contract resumed, consent the one way into work, the one way into rework *(derived)*.


By strength, a removal is **fatal** — its target unreachable — for ASSIGN, ACCEPT, CHALLENGE, BLOCK, DELIVER and PASS, and **sole-provider** — the target still reached through a catch-all, without what only the signal provides — for CANCEL, CONFIRM_CANCEL, RESOLVE_BLOCK, REJECT_CHALLENGE, ACCEPT_CHALLENGE and FAIL *(derived; the fatal removals machine-checked, `FsmCanon.noAssign_strands_start`, `noBlock_strands_blocked`, `noChallenge_strands_challenged`, `nodeliver_strands_done`, `noPass_strands_done`, `LogLanguage.accept_fatal`; of the sole-provider ones, all but FAIL, machine-checked only which content edges carry the source to the target — for REJECT_CHALLENGE its return to consented work, for ACCEPT_CHALLENGE its offer, reached besides only by REJECT_CHALLENGE before consent — `FsmCanon.noCancel_keeps_the_silence`, `noCancel_leaves_only_the_silence`, `noConfirm_only_timeout_into_abandoned`, `resolveBlock_sole_content_resume`, `rejectChallenge_sole_content_resume`, `acceptChallenge_sole_content_reoffer`, what only the signal provides being derived)*.

### 11.5. Admission and root creation

Outside the twelve signals the protocol has two acts that are not transactions and carry no signal: a split's admission and a root's creation. That they are acts of their own, both logged, is a design decision *(adopted)*.

A split's **admission** is the decomposer's act on his own node: Del(t) records D(t) with its register, ACCEPTED_RISKS (Ch. 9), and the battery of STD-4 (Ch. 9) admits it. *(defined)* The fixing of D(t) — in Ch. 8's compositional validation and in Ch. 9's register, flags and checks — is its admission, the latest re-admission.

The admission is where the Syntactic level (Ch. 9) runs: a split is admitted to execution only if it passes that level, save what no act of its decomposer lifts, which is reported rather than gated. CHECK-3 reads the split's Dep edges against the deadlines the admission sets, its unissued children's, live and, while the parent's deadline is ahead, below it (item (6)): a crossing gates the admission where some such choice orders every edge, and is otherwise reported to the issuers whose deadlines bound the choice, of the ends the admission does not set and the parent's, whose revision lifts it. It reads no edge one of whose ends is settled, a settled end's deadline ordering nothing still to come. Form item (4), what a declared Dep edge carries (Ch. 4), reports for the same reason, a discovered edge arriving by a BLOCK in mid-execution with no criterion; item (6), deadline coherence along D, gates the deadlines the admission sets, its unissued children's, while the parent's deadline is ahead; past it, where no live deadline precedes the parent's, it reports to the parent's issuer, whose revision alone lifts it.

A Semantic flag (Ch. 9) is discharged before admission; the decomposer's report of a defect sourced in the packet (§9.4, §9.7) is a CHALLENGE to the packet's issuer. A split admitted with a Semantic flag undischarged carries that FM-1.d or FM-2.

A node's split need not exist at its ASSIGN: D(t) may be authored by the node's executor in performing it, which is FM-6's guard (Ch. 8). A split may be drafted and the battery run over the draft before issue; the node's executor admits it at or after the node's issue.

The split — its children, the draft fields of those not yet issued, and its register — changes only by a re-admission, the battery running over the split as it will then stand. A first ASSIGN departing from the draft is therefore a re-admission. A re-admission does not re-check what is settled: under CHECK-1b (Ch. 9) a child whose verdict is settled, which no act of the decomposer drops, and under CHECK-3, as at any admission, a Dep edge one of whose ends is.

An implementation may instead admit and issue in one act, so that no child stands unissued.

A re-admission can drop only a child not yet terminal — accepted, or its cancellation completed — and the child leaves as its progress allows: an issued one by CANCEL; one already being cancelled as the abandoned node it becomes; an unissued one by leaving the split, the log keeping it.

Below a root, recovery from a mistaken CANCEL is re-issuing, a re-admission of the parent's split: a new node, the cancelled one staying abandoned in the log, its subtree rebuilt, not resurrected.

### 11.6. The log and Theorem 11

**Theorem 11 (structural transparency; definitional).** If the organization follows the protocol, every decision d has a record R(d) = (author, spec, criteria, accepted_risks, timestamp), accepted_risks being the split's register, versioned by its admission, and the packet's pre-fill, both logged. *(derived)*

*Proof.* ASSIGN fixes the spec, the criteria and Del, and every re-ASSIGN is appended to the log (§11.1). The register is mandatory for a decomposed node (STD-1, Ch. 9) and is carried by the admission, appended like any act. FAIL carries the failed criteria. Every CHALLENGE, BLOCK, CONFIRM_CANCEL and re-ASSIGN records a reason, or the in-flight state, with a timestamp. ∎

**Corollary.** Opacity inside the protocol is a protocol violation and a measurable defect: a decision without its record. *(derived)*

With the register logged, a factor written nowhere is a falsifiable absence, found at contact or by a reader of the log, never by a CHECK, which reads only what is written.

---

## 12. The machine and its invariants

### 12.1. The states

The protocol's machine has 11 states: IDLE, OFFERED, CHALLENGED, EXECUTING, BLOCKED, VALIDATING, REWORKING, CANCELLING, DONE, ABANDONED, ESCALATED *(defined)*. DONE (V = pass) and ABANDONED (V = ⊥) are terminal; CANCELLING is non-terminal, and **ESCALATED is non-terminal**.

The states are induced, not postulated: each is a waiting point between signals or a terminal outcome *(defined)*. IDLE: no packet issued. OFFERED: a version its executor has not consented to. EXECUTING, REWORKING: consented work, REWORKING entered through a FAIL taken into rework. CHALLENGED, BLOCKED, VALIDATING: one wait on the issuer — a challenge, a block, a delivery awaiting its verdict. CANCELLING: a closing not yet acknowledged. ESCALATED: the issuer's decision. Below, *the decision* is ESCALATED, *the closing* CANCELLING, a *lapse* a timeout out of a party's wait, a node *live* when issued and not terminal, and a *version in force* the current packet version of a node neither in IDLE, in CANCELLING nor terminal.

A node's state is orthogonal to its verdict V(t), in-progress being V's absence (Ch. 2): the state is the protocol's machine over the basis (Ch. 7) *(derived)*.

DONE is the attainment shape (Ch. 6). A maintenance goal, never completable, runs through this machine only as the root tasks its generator emits (§6.10).

### 12.2. The clock

A system mechanism, not a signal, bounds each wait: a monitor fires a timeout when a state's bound has passed *(defined)*. The bounds:
- **work states** (EXECUTING, REWORKING): the packet deadline (Ch. 2), which runs across every state of the contract and is never suspended;
- **answer states** (OFFERED, CHALLENGED, BLOCKED): the deadline or a per-state bound — how long the party owing the answer may take — whichever comes first;
- **VALIDATING**: its per-state bound T_validate alone, counted from DELIVER;
- **protocol states** (ESCALATED, CANCELLING): a per-state bound only; ESCALATED's may depend on how it was entered;
- **IDLE**: none; deadlines attach at ASSIGN, so the clock starts with the node's first bounded state — OFFERED, or CANCELLING for a node cancelled from IDLE.

The deadline does not cut VALIDATING: a delivery inside the contract has met it, and a deadline cutting VALIDATING would let a last-moment delivery reach ESCALATED with no verdict, around the rework bound (Ch. 10) *(derived)*.

A bound already passed fires on entry: the state admits no signal before its timeout, a zero-length transit *(defined)*. So REWORKING entered after a FAIL past the deadline goes to ESCALATED at once, the verdict on the record.

A timeout bounds one visit of one state, a wait being a waiting point between two signals (§12.1), so a state re-entered poses a new wait; one fired for a visit already left does not act on the state entered after it *(derived)*.

The per-state bounds are protocol parameters: the canon requires them to exist and fire and fixes no numbers *(defined)*.

⊥ is not an event of the machine: a validation attempt that yields no verdict is not a signal, and the bounds end VALIDATING's wait *(defined)*.

A timeout's consequences are its routing and its record: the log carries every signal, every entry into a state, and the bound that fired and when (Thm 11), a clock-made move carrying that bound in place of an author *(defined)*.

No expiry is attributed to a party, a lapse in the executor's own work included, a design decision *(adopted)*.

### 12.3. Inv-1: the packet and its versions

**Inv-1 (Packet-Immutability).** The packet is immutable after ASSIGN, and **the executor is bound to a version's work only by his ACCEPT of it**. Changing any packet field — criteria, deadline, the pre-filled ACCEPTED_RISKS, the rework bound `max_iterations`, **Del** — is a **re-ASSIGN under the same id**: a **revision**, a new version entering at OFFERED, which the executor ACCEPTs or CHALLENGEs anew *(derived)*, from FM-5: no contract goes stale silently.

A revision is admissible wherever a version is in force — every non-terminal state but IDLE and CANCELLING, the *reassignable* states *(defined)*.

`max_iterations` is a packet field, counted per version, a design decision *(adopted)*.

ACCEPTED_RISKS adds no primitive *(derived)*: the split's register is an annotation the decomposition carries, and the packet's pre-fill (Ch. 10) is packet data, immutable under Inv-1; neither is a relation over tasks, though D's signature as stated does not display the register.

### 12.4. Inv-6: the admissible sets

**Inv-6 (Determinism):** the admissible signal set is defined in every state *(defined)*. For the base machine it is this table, the timeout a system trigger, not a signal *(defined)*:

| State | Admissible signals (→ target) |
|---|---|
| IDLE | ASSIGN→OFFERED · CANCEL→CANCELLING |
| OFFERED | ACCEPT→EXECUTING · CHALLENGE→CHALLENGED · timeout→ESCALATED · CANCEL→CANCELLING · ASSIGN→OFFERED |
| CHALLENGED | ACCEPT_CHALLENGE→OFFERED · REJECT_CHALLENGE→EXECUTING (after consent) ∨ OFFERED (before consent) · timeout→ESCALATED · CANCEL→CANCELLING · ASSIGN→OFFERED |
| EXECUTING | DELIVER→VALIDATING · BLOCK→BLOCKED · CHALLENGE→CHALLENGED · timeout→ESCALATED · CANCEL→CANCELLING · ASSIGN→OFFERED |
| BLOCKED | RESOLVE_BLOCK→EXECUTING · timeout→ESCALATED · CANCEL→CANCELLING · ASSIGN→OFFERED |
| VALIDATING | PASS→DONE · FAIL→REWORKING (retries left) ∨ ESCALATED (exhausted) · timeout→ESCALATED · CANCEL→CANCELLING · ASSIGN→OFFERED |
| REWORKING | DELIVER→VALIDATING · **BLOCK→BLOCKED** · **CHALLENGE→CHALLENGED** · timeout→ESCALATED · CANCEL→CANCELLING · ASSIGN→OFFERED |
| CANCELLING | CONFIRM_CANCEL→ABANDONED · timeout→ABANDONED |
| ESCALATED | ASSIGN→OFFERED · CANCEL→CANCELLING · timeout→CANCELLING |
| DONE / ABANDONED | — (terminal) |

The catch-alls (Ch. 11) are the issuer's CANCEL from any non-terminal state other than CANCELLING and re-ASSIGN from the reassignable states, and the timeout *(defined)*.

The rows carry these rules *(defined)*:
- REJECT_CHALLENGE(justification) returns to the wait the challenge interrupted (Ch. 11): after consent EXECUTING, out of REWORKING too, which only a FAIL enters (§12.1); before consent OFFERED, its version's deadline still running, since Inv-1 binds the executor only by his ACCEPT *(derived)*.
- REWORKING carries BLOCK and CHALLENGE as EXECUTING does, being work-active under the same consented version: without BLOCK a blocker met in rework is unreportable (FM-5), without CHALLENGE a FAIL computed over a defective spec loses its dedicated repair (FM-1, FM-2) *(derived)*.
- A resolution changing a packet field is a re-ASSIGN (§11.3) → OFFERED, which BLOCKED's row admits, and the same rule pins ACCEPT_CHALLENGE → OFFERED, its new contract a revision *(derived)*.
- The timeout column is one rule: a party's wait (OFFERED, CHALLENGED, EXECUTING, REWORKING, BLOCKED, VALIDATING) lapses into ESCALATED, ESCALATED into CANCELLING, CANCELLING into ABANDONED. A missed bound hands the decision to the issuer at once; VALIDATING's timeout leaves the delivery in the log without a verdict.

False FAIL's guarantee-safety (Ch. 8) holds in the machine: DONE is entered only through PASS *(derived)*.

The table fixes the referents of Ch. 11's FSM type *(derived)*: DELIVER the work states' only exit into VALIDATING, PASS the only entry into DONE, CONFIRM_CANCEL CANCELLING's only exit besides its timeout, RESOLVE_BLOCK BLOCKED's only in-contract exit; ACCEPT on every path into consented work, REJECT_CHALLENGE after consent CHALLENGED's only return to it and FAIL VALIDATING's only way into rework — the second type those three carry.

### 12.5. ESCALATED: the issuer's decision

ESCALATED is entered when a party's wait on a version in force has lapsed or the budget is spent, short of a PASS *(defined)*. It hands the decision to the issuer; it settles nothing.

The issuer has two moves *(defined)*. He continues by a re-ASSIGN → OFFERED, raising the bound and changing criteria being one act by Inv-1. Or he closes by CANCEL.

Escalation cascades nothing: the node's children stay live under their own contracts until a cascade settles them *(defined)*.

The clock never invents a verdict, and closing invents none: silence is the default among the issuer's moves and takes the closing move's path, ESCALATED ──timeout──> CANCELLING ──> ABANDONED, logged as the timeout it is *(defined)*. A route straight to ABANDONED would settle the node and leave its children working for a goal that no longer exists — ballast if the refusal is right, a stranded plan if not *(derived)*.

The way back to work on the node runs through the handover, never around it.

### 12.6. Cancellation

Cancellation is a two-step handshake *(defined)*: CANCEL (issuer) into CANCELLING, CONFIRM_CANCEL (executor) into ABANDONED (§12.4) — assignment walked backwards: ASSIGN ↔ CANCEL, ACCEPT ↔ CONFIRM_CANCEL, OFFERED ↔ CANCELLING, EXECUTING ↔ ABANDONED. Unanswered, the cancellation completes by timeout without the in-flight report.

A child is **active** unless ABANDONED or dropped by a re-admission (§11.5): a settled cancellation, or the drop, takes it out of the plan. The compositional validation (Ch. 8) and the battery's CHECK-1, 5, 7 and 8 (Ch. 9) read the active children *(defined)*.

CANCEL withdraws the version in force, and a report (CHALLENGE, BLOCK, DELIVER) is made on a version in force, so none is made from CANCELLING *(derived)*.

Entering CANCELLING — by CANCEL or by ESCALATED's timeout — cascades the subtree, and the cascade is no separate signal: the protocol sends CANCEL to every non-terminal descendant not already in CANCELLING *(defined)* — unissued ones included, which settle by CANCELLING's own bound, an admitted child being in D(t) before its issue (§11.5) *(derived)*.

### 12.7. Issuing children

An admitted split's children wait in IDLE until their first ASSIGN (§11.5).

**The issuing condition.** A child's first ASSIGN and a split's admission are admissible only while the parent is live and not in CANCELLING: a child issued after the cascade fired would escape it, and under a settled parent nothing is owed, a promotion a BLOCK would make mandatory (Ch. 11) included, the blocked child's issuer keeping his answers to the BLOCK *(derived)*. It is the base table's one condition reading another node's state, carried by IDLE's ASSIGN.

### 12.8. Inv-2 and Inv-3: the verdict's record

**Inv-2 (Binarity):** V(c) ∈ {pass, fail}, from binarity (Ch. 7) *(derived)*. A verdict may carry per-criterion values; any other status on a criterion — "residue", "waived", "an accepted risk" — is ⊥ until decided, an observed divergence between result and criterion is that criterion's fail, and no register turns either into pass.

A PASS recorded over such a criterion stands on no value its own record gives and is untrue wherever that criterion's true value is fail: FM-3's false PASS where the node's own verdict is FM-3's object (§8.4), and otherwise the mode of the input Ch. 8 reads as denied *(derived)*. The protocol can refuse what the record carries structurally: a per-criterion value other than pass under a PASS, or a non-empty observed divergence under pass where the record carries divergences per criterion. A waiver written in prose inside a pass is visible to audit, not to a structural check, as FM-3 has no structural guard (Ch. 9) *(derived)*.

**Inv-3 (Failure-Transparency):** FAIL ⇒ failed_criteria ≠ ∅, from FM-3: validation may not be unsubstantiated *(derived)*.

The check's record (Ch. 10) is bound by Inv-2 and Inv-3.

The issuer's check (§10.2) holds t's verdict of record — a contact over the delivered result reading no child state — and FM-4's departure from AND is read against the active children's recorded values, ⊥ read as not passing: the departure is read off the log, its untruth is not *(derived)*. So an untrue PASS over missing work — an active child at ⊥ whose work the delivered result lacks, such as a leaf never issued (CHECK-6) — is FM-4 and FM-3 at the parent; one over an abandoned responsible child's hole, the child out of the plan, is FM-5's (§8.6) until a re-admission fixes the split again.

### 12.9. Inv-4 and its reading

**Inv-4 (Obligation-Symmetry):** Issuer and Executor are equally accountable to the protocol *(defined)*. Its text alone is symmetry, which a protocol in which neither party can move satisfies: it is an invariant that operates only through its reading *(derived)*.

**Inv-4's reading**, not derived from the text, a design decision *(adopted)*:
1. accountability to the protocol is discharged by a protocol act, so the **owner** of a state, the party who owes its next move, has a move;
2. each party holds a channel over a contract that is his: the executor CONFIRM_CANCEL in CANCELLING; the issuer his decision in ONE waiting state, ESCALATED, whatever route enters it, the route's added time being ESCALATED's bound;
3. no state leaves its owner only dishonest or work-destroying moves.

One named exception to (1) and (3): in OFFERED an executor who cannot perform a sound spec discharges by abstention — the offer lapses to ESCALATED, where re-ASSIGN is open, and the log records the lapse without its reason. The rule that no expiry is attributed (§12.2) is grounded in this abstention, which an attribution would price.

### 12.10. Revisions

A revision takes the node, under the same id, into OFFERED, not through CANCELLING: nothing cascades, and the new contract binds only on ACCEPT, so the issuer cannot silently swap criteria under a node in work *(derived)*.

A revision re-runs the structural guards over the split and Dep, which flag instead of refusing: CHECK-1 an uncovered criterion (FM-1.a's shape) and CHECK-1b a dangling cover (FM-1.e's shape) — FM-5's staleness in FM-1's shape — and CHECK-3 a new deadline crossing a consumer's along Dep, FM-5's freshness, and item (6)'s guard (§11.5) a new deadline crossing along D *(defined)*. A flagged node keeps its contract and owner; CHECK-3's flag goes to the consumer's issuer, who may re-ASSIGN it or let it run on its deadline. Only CHECK-2's Dep clause refuses: a revision whose criteria would close a Dep cycle. CHECK-2 guards FM-5 by that one clause, CHECK-3's order along Dep excluding cycles only while revisions keep it.

The guards read packet fields, not work: a consumer whose input changed in content meets the change at contact, by BLOCK or its own FAIL *(derived)*.

A revision of an issued child's criteria re-runs no Semantic check over the parent's split, which is not re-admitted; a defect it introduces is FM-5, met by the parent's own check *(derived)*.

Only its issuer can repair a defect sourced in the packet (§9.7), since only he revises it.

**A re-ASSIGN never answers an open question; it re-presents it** *(derived)*. A question stands on the packet fields it concerns — a CHALLENGE on those it names, a delivery awaiting its verdict on the criteria. A re-ASSIGN keeping them leaves it standing, the executor free to re-raise the challenge or re-deliver the logged result; only its own answering signal (ACCEPT_CHALLENGE or REJECT_CHALLENGE, PASS or FAIL) answers it; a re-ASSIGN changing them supersedes it. Ground, relative to Inv-4's reading: in ESCALATED, where the issuer owns the decision, a re-ASSIGN refused while a question stands would leave him only the destroying CANCEL (clause (3)).

Every re-presentation is an issuer's act and costs the executor one re-consent and the re-delivery of an identical artifact, provided its deadline leaves time for both; one that does not disposes of the delivery.

### 12.11. Inv-7: identity and the log

**Inv-7 (Identity-Stability).** A task's id is stable over its whole life cycle, including revision: one node carries the successive versions of its spec *(defined)*. The immutable record is the log (Thm 11), not the node: every re-ASSIGN appends a version, the node's current attributes (T, Del, V, state) project the latest, and past versions live in the log. Splits, Dep edges and criterion mappings reference the id, so "change = re-ASSIGN" is consistent only as in-place re-authorship, never delete + create *(derived)*.

**A state is what stands on the log** *(adopted)*: a challenge, block or delivery stands only by its asking; an offer is an unconsented version, and a logged consent stands for its version; a closing stands only by a CANCEL or the clock; acceptance only by a PASS; abandonment only by settling a closing, whose entry cascades; a missed bound only by the clock.

So the pure RESOLVE_BLOCK resumes in EXECUTING, not re-offered, consent standing for its version (Ch. 11) *(derived)*.

Partition refinement of the transition rows — observable: every admissible signal and the timeout with its target, plus the settlement mode — makes "induced" a behavioural check *(defined)*. Ten of the eleven states are irredundant: the terminals separated by the settlement mode alone, ESCALATED from them by its non-empty row and from IDLE by its timeout alone *(derived; machine-checked with FAIL's retries left and REJECT_CHALLENGE's consent read as inputs, `FsmCanon.canon_ten_pairwise_distinct`)*. REWORKING agrees with EXECUTING on every signal: an attribution label for work-active behaviour entered through a FAIL taken into rework, induced by history, its content in the log *(derived; machine-checked, `FsmCanon.canon_exec_rework_same`)*.

CHALLENGED is two behaviour classes over the log, before and after consent, its REJECT_CHALLENGE routing reading the consent datum as FAIL's reads the budget; so over the log the machine has eleven behaviour classes over eleven states, §12.11's ten with CHALLENGED split by its consent record *(derived)*. Consent is a record and the budget an input: consent is one fact of the version's log, while the budget compares an unbounded count of FAILs with a packet field and has no finite record *(derived)*.


### 12.12. Inv-5: finiteness

**Inv-5 (Finiteness):** every non-terminal state **except IDLE** has a timeout, and the clock moves a node only toward its settlement *(defined)*:
- (a) a timeout ends the wait it fires on;
- (b) the clock makes no party's report or answer: its target is ESCALATED or CANCELLING — Inv-4's two channels — or, from CANCELLING, ABANDONED;
- (c) it closes only where the issuer holds the decision.

Inv-5 is not breached at IDLE: an IDLE child gates its parent only through the parent's AND, and the parent's contract carries the clock; under a live parent IDLE starvation surfaces as the parent's timeout, and under a settled parent or at an unissued root nothing is owed *(derived)*.

Clause (a) is "waits end" made a condition on the table: a lapse state timing out to itself meets the first sentence and ends no wait *(derived)*.

Clauses (b) and (c) are adopted *(adopted)*: they make "the way back to work runs through the handover" a condition and, with clause (2)'s one decision state, send every lapse to ESCALATED at once.

The machine has no OVERDUE, a state of its own for a missed bound; that removal rests, beside the one decision state, on either of two readings of Inv-4's reading, each sufficient, neither derived: the clock enters only the two channels (b); or the decision's routes are a party's lapsed wait or a spent budget, an alternative reading *(adopted)*.

No clock path returns to a wait it left: the decision's timeout can only close, the closing's only settle, a closing not being a route into the decision (§12.5). So Inv-5's second clause with the decision's entries is the whole of §12.4's timeout routing; (a) alone would admit a decision ⇄ closing cycle *(derived)*.

With CONFIRM_CANCEL's meaning, reports made only on a version in force (§12.6) and a closing not a route into the decision, cancellation is authoritative — a closing leaves only into ABANDONED — without being a separate decision *(derived)*.

### 12.13. Inv-8: ownership

**Inv-8 (Obligation-Ownership).** In every state where the work has begun and is not over — all but IDLE, DONE, ABANDONED — one party is the owner (§12.9), with at least one own admissible signal; **and no transition leads to a state that has neither an owner nor a settlement** — the per-state clause derived from Inv-4's reading, clause (1), an obligation standing in each such state *(derived; the edge clause adopted)*. It is read over states that admit a signal before their timeout: a state entered past its bound is a zero-length transit (§12.2), not a wait.

The edge clause is not redundant: a machine routing a live node to IDLE (no owner, no clock) meets the per-state clause vacuously together with deadlock-freedom and Inv-5 *(derived)*. Its defect is weaker than an empty decision row — in IDLE the issuer still holds ASSIGN and CANCEL, so what is missing is the obligation, not the means — but it sits where the per-state clause cannot see. The canon's table has no transition into IDLE.

A decision state admitting no act of the deciding party leaves the obligation ownerless with Inv-6 holding vacuously — a terminal ESCALATED — and Inv-8 excludes it; so Inv-6 and Inv-8 are independent *(derived)*.

**Besides the clock and the cascade, a state moves only by its owner's signals and the issuer's catch-alls (re-ASSIGN, CANCEL); IDLE only by the issuer's first ASSIGN and CANCEL. The owner is read off the log** *(adopted)*: the addressee of the standing offer, challenge, block or delivery, or the party the obligation binds (consented work: the executor).

The two channels' owners are clause (2); CANCELLING's also follows from Inv-8's first sentence, the reassignable set and CANCEL's domain, since where a closing stands no issuer signal is admissible *(derived)*.

| State | Owner | The owner's moves |
|---|---|---|
| OFFERED | executor | ACCEPT · CHALLENGE — or abstention (§12.9) |
| CHALLENGED | issuer | ACCEPT_CHALLENGE · REJECT_CHALLENGE (· re-ASSIGN · CANCEL) |
| EXECUTING, REWORKING | executor | DELIVER · BLOCK · CHALLENGE |
| BLOCKED | issuer | RESOLVE_BLOCK (· re-ASSIGN · CANCEL) |
| VALIDATING | issuer | PASS · FAIL (· re-ASSIGN · CANCEL) |
| CANCELLING | executor | CONFIRM_CANCEL (entered from IDLE, or by a cascade over unissued children, it names an executor never offered anything, his move still admissible) |
| ESCALATED | issuer | re-ASSIGN · CANCEL; silence closes (§12.5) |

The OFFERED abstention is an exception to Inv-4's reading, not to Inv-8.

A missed bound is no waiting point of its own: it stands only by the clock, the clock enters only the two channels (Inv-5 (b)), and an ownerless wait admits no transition *(derived)*.

The folds that drop ESCALATED or CANCELLING are deadlock-free, finite and satisfy Inv-8; folding ESCALATED into ABANDONED removes the issuer's channel (clause (2)) and leaves him only destroying moves (clause (3)). So ESCALATED and CANCELLING are held by Inv-4's reading — its clause (2), the issuer's decision and the executor's CONFIRM_CANCEL — not by these invariants *(derived, relative to that reading)*.

One owner per state carries Del's grade (Ch. 2).

Inv-7 makes a node's issuer Del(parent) as the parent's current version gives it (Ch. 10), so every live child keeps its owner in every parent state. Keeping the previous Del as issuer would break Inv-7's single current Del, and a stand-in from above could coincide with a child's executor in one public transaction (§10.3). That the role holds before its holder's consent (Ch. 10) is forced here: gating it until his ACCEPT would leave the children's issuer-owned states with an owner and no move *(derived)*. These links, with the re-presentation rule (§12.10), are derived relative to the adopted items.

Inv-8 guarantees that a move exists, not that it is adequate or that the owner has time for it: the bounds are parameters.

### 12.14. Terminality, finality and R′

ABANDONED is terminal: base cancellation is irreversible — terminality, `max_reopens` = 0, re-issuing its recovery, a design decision *(adopted)*. Ground: an outcome revocable at will guarantees nothing, so what is forced is only that a reversal be non-arbitrary — issuer-authorized, bounded by a counter, appended forward (Inv-7, Thm 11); terminality meets this with zero reversals, the strongest compatible edge.

The invariants cannot choose `max_reopens`: 0 and a positive value each give a machine meeting every invariant, trading a settlement's finality against recovery from a mistaken settlement at a root *(derived)*. Base and R′ are two machines, not one protocol with two payloads: 0 at every node fixes the gate false and so changes the admissible sets at the settlements (Inv-6), whereas `max_iterations` ranges over values across payloads *(derived)*.

A terminal reversal is non-local: a pass's through AND (Ch. 7) and Dep (Ch. 2), a cancellation's through the cascade. At a root the base has no recovery short of a new goal.

**R′** adds REOPEN edges DONE → OFFERED and ABANDONED → OFFERED, outside the 12-signal minimum *(defined)*. REOPEN is a named re-ASSIGN, not a thirteenth signal: recovery, not failure, it adds no defect class and leaves minimality untouched *(derived)*. Its form — REOPEN the gated signal under one counter per node, `max_reopens`, counting DONE → OFFERED and ABANDONED → OFFERED alike — is chosen, a design decision *(adopted)*.

**Finality** *(derived)*: a terminal is **final** ⟺ it is consumed, or its `max_reopens` is spent, or, below a root, its parent is final — a parent in CANCELLING read as the ABANDONED it must become, its only exit; otherwise it is **locally reversible**. Finality is a property of a settlement, the one a reversal would unmake, so a live parent not in CANCELLING is not final.

A terminal is **consumed** from the first logged moment at which it is terminal and *(derived)*:
- something rests on its pass (DONE only): its parent has delivered upward through AND, or a Dep consumer builds on the result;
- or a re-admission of the parent's split covers around it: gives a criterion of the parent's to which it is mapped a responsible child it did not have before, read off the logged mappings on either side, a sibling co-covering in the split as first admitted consuming nothing;
- or a re-admission drops it;
- or it is mapped to no criterion of the parent's current version.

In the last three the plan has moved past it or rests on it: a reopen would put FM-1.e into it — a live orphan or, over a replanned hole, a child whose criterion the re-admission covered without it (§11.5) — or unmake a settlement a co-covering child admitted beside it may rest on. A settled cascade alone consumes nothing. At a root the AND legs have no referent: a root terminal is consumed only through Dep, and `max_reopens` is otherwise its finality.

Consumption is logged (Inv-7), hence decidable, and once logged stands; past it, reversing the node reverses its downstream cone.

The moment of the threshold is chosen, a design decision *(adopted)*: the first log-visible event making reliance possible — for AND the parent's DELIVER, for Dep a consumer in work or validated after the result's PASS (the read is not logged), for a replan the re-admission or re-ASSIGN — a visible over-approximation.

An attained node's freezing (Ch. 6) is not this consumption, which gates finality.

**REOPEN is admissible** only through the finality gate — the terminal not final — and, below a root, under the issuing condition (§12.7) *(defined)*. DONE and ABANDONED become quasi-terminal, an explicit extension of the admissible sets (Inv-6).

REOPEN is the issuer's re-ASSIGN (§10.1); consumption is not his alone, being the parent's act, a Dep consumer's, or, where a parent's re-ASSIGN leaves the node mapped to no criterion, the parent's own issuer's.

The finality check and the REOPEN edge are one log-serialized atomic step (Inv-7), else a concurrent DELIVER could consume the node between them.

REOPEN leads into OFFERED, not DONE: the verdict is re-earned by fresh contact, and for a positive terminal V = pass is removed, not carried forward; a delivery whose PASS it erased stands again as an open question (§12.10).

REOPEN does not make the new verdict correct: it inherits the verifier ≠ executor seam (Ch. 10) and adds nothing to the base guarantee *(derived)*.

REOPEN is no cascade rollback: a cascaded child reopened carries the in-flight state that enables resume from provenance where CONFIRM_CANCEL settled it, none where the timeout did. Past consumption recovery is the issuer's re-decomposition, at a root a new goal. The positive reopen has one gate and no settling race, DONE having cascaded nothing.

No consensus is needed: the single history is the single-sequencer append-only log (Inv-7, Thm 11).

An issuer can unmake his own unconsumed PASS by REOPEN, then CANCEL, or by a REOPEN writing the divergence out of the criteria; the log keeps the PASS and what followed.

R′'s gate reads consumption, a log fact, not a state-resident datum, so no finite composite of states and counters is a deterministic automaton on it *(derived)*.

Whether a failure found after the verdict is corrected is a property of this machine, not of the computation: past a PASS only a REOPEN while the node is not final, none in the base — a named residue.

Pre-registration is carried by Inv-1: criteria change only by a logged, re-consented re-ASSIGN and only while the node is not final — before settlement with the delivery in hand, after it through R′'s gated REOPEN.

### 12.15. Finiteness: Φ1–Φ3

**(Φ1) Waits end** — Inv-5 with its clause (a) (§12.12) *(defined)*.

**(Φ2) Every contract ends** *(derived)*. Premise: signals take time, so no run carries infinitely many before a bound *(premise)*. A run under one packet version, whatever loops it runs, settles, is replaced by a new version, or reaches ESCALATED at the latest by its deadline plus the per-state bounds of the states it passes — at most one T_validate beyond the deadline, plus the protocol states' bounds.

A packet version enters only through OFFERED and only by the issuer's act — first ASSIGN, re-ASSIGN (revision, REOPEN) or ACCEPT_CHALLENGE — with a live deadline (§2.5); every new version resets the rework budget. The post-consent dispute loop has no counter: Φ2 bounds it.

**(Φ3) The counters are not finiteness devices**: waits end by Φ1 and contracts by Φ2 whatever the counters. `max_iterations` bounds the DELIVER → FAIL loop as the issuer's per-version forecast of rounds — some finite bound required, not its value — so exhausting it hands him a question, not a verdict. An executor who holds a true report back until his rounds run low gets only the fresh draws the issuer's accepting version grants. `max_reopens` bounds the unmaking of settlements, R′'s quasi-terminals included: a verdict erasable without bound certifies nothing; it is a per-node protocol parameter, 0 in the base, not raisable by the issuer.

ESCALATED's re-ASSIGN unmakes no settlement and is not counted: a counter there would, exhausted, leave the owner of a live goal only CANCEL or silence — the fold Inv-4's reading excludes, re-created by fiat *(derived)*.

Run-level, per node: every run is finite, or contains infinitely many new versions, each an issuer's act, or rests in IDLE, binding no one; no run cycles through waits alone or erases verdicts without bound *(derived)*.

Over two or more nodes the TLA models check the issuing condition's closed-parent half — no child issued under a parent in CANCELLING or terminal. They check less: Φ3 at one node, R′ being off over two or more; one flag for deadline and bounds (T_validate-alone and fire-on-entry unchecked); no Del identities ("issuer = Del(parent)" unchecked); liveness only under a reduced queue bound. They admit a child issued under an unissued parent, a stale timeout crossing into a new version and a cascade skipping unissued children.

### 12.16. Conformance

A **move** is a signal with its payload *(defined)*. An implementation **conforms** iff in every state *(defined)*:
- (i) its admissible set is a subset of the canon's (base, or base with R′);
- (ii) it refuses a move the canon admits from the sender only by naming the requirement it operationalizes, and only where the sender can lift the refusal in time by his own admissible, truthful, work-keeping moves — a lift changing a delivered artifact discarding work unless a standing verdict under the current version's criteria indicts that artifact (Inv-3);
- (iii) every invariant holds, notably Inv-8, Inv-5, and Inv-6 with §12.4's routing.

Ground of (ii): a signal is a report of an observation, so a refusal liftable only by misreporting or discarding work makes honesty non-conforming *(derived)*.

Stricter admission, so bounded, is how an implementation operationalizes a requirement the canon states but does not gate.

Conformance governs the refusal of admission and root creation as a signal's (Ch. 11). ACCEPT_CHALLENGE installing a packet as ASSIGN does (Ch. 11), what an implementation requires of a packet it requires of new_spec — else the dispute's answer would bypass the gate *(derived)*. Guards an implementation adds for unchecked form items refuse only under (ii); a mechanical flag may gate admission only where the decomposer's own repair or entry lifts it.
A packet with no deadline does not conform, a logged default (Ch. 2) being admissible; under a parent whose deadline has passed the issuer types one.

The bound values (§12.2) lie outside conformance.

---

## 13. The machine forced over the log

### 13.1. Adequacy and the currency

A cell is a state with a signal or the timeout; its content is the destination. A machine is **bare-adequate** when each signal's row (Ch. 11) has its exit in every work-active state under the contract, the machine is deadlock-free, and Inv-5's first clause, Inv-6 and Inv-8 hold per state *(defined)*. Adequacy so read includes Inv-8, clause (1) of Inv-4's reading, so every grade here is relative to that reading. A cell is **bare-adequate** when bare adequacy holds it, **pinned** when clauses (2)–(3) of Inv-4's reading hold it beyond that *(defined)*.

Inv-8 is stronger than "no state may be stuck", which a timeout-only state meets.

Protocol minimality (Ch. 11) is separate from uniqueness: is every adequate protocol behaviourally equivalent to this machine? **Bi-interpretability** — each structure interpreting the other, the round trip recovering each up to definable isomorphism *(defined)* — cannot carry the question *(derived)*: every adequate protocol is rigid — initialized by ASSIGN, deterministic by Inv-6, reachable, so every automorphism fixes the initial state and propagates along reachability — and finite rigid structures with ≥ 2 elements are mutually bi-interpretable, so it is vacuous over finite protocols; against an infinite rival with an unbounded retry counter in its state it is false, Φ2 bounding runs, not state. The currency is behavioural equivalence: isomorphism of minimal reachable-reduced realizations.

Over the 12 signals and the timeout trigger the base machine is the table of Ch. 12 with one input bit — the retry guard at FAIL, the consent datum at REJECT_CHALLENGE — counters and bounds being packet and log data *(defined)*. Its behavioural quotient is §12.11's ten classes.

### 13.2. Bare adequacy pins no destination

Bare adequacy pins no destination *(derived)*: its clauses read which cells are admissible, which no destination changes, and whether every live state still reaches a settlement, which no one cell decides — from every live state no single cell lies on every route to a settlement — so a change of one cell's destination to any state leaves the machine bare-adequate. The machine routing VALIDATING's timeout to DONE(auto_pass) is bare-adequate and behaviourally distinct *(derived; its timeout exits, Inv-8 and distinctness machine-checked, `FsmCanon.variant_*`)*. So uniqueness holds only relative to a fully pinned design vector, which the canon pins by design principles and Ch. 12's clauses, the FM and IC types of Ch. 11's rows forcing an edge's existence where a mode needs one — REWORKING's BLOCK, the post-consent CHALLENGE — never its destination, which only a row's content fixes. The freedom is multi-dimensional — the timeout geometry, the resolution destinations, FAIL's routing.

### 13.3. The backbone

The ten states other than REWORKING are the backbone *(derived)*: eight — DONE and ABANDONED among them, separated by the verdict — are the roles their rows demand (ASSIGN, ACCEPT, DELIVER, PASS, BLOCK, CHALLENGE, ACCEPT_CHALLENGE, CANCEL/CONFIRM_CANCEL, re-ASSIGN); CANCELLING and ESCALATED are pinned by Inv-4's reading (§12.13), not by adequacy. The rows force roles, not distinct states: a machine merging two of the issuer's answer waits meets them and bare adequacy, so no lower bound on the states follows from the rows alone. The states outside it are decorations: REWORKING, agreeing with EXECUTING on every signal (§12.11), and OVERDUE, removed (§12.12).

ESCALATED is no decoration: its fold into ABANDONED (`FsmCanon.noEscalated_*`) gives up only an attribution distinction where the issuer owes no answer, and under Inv-4's reading his decision channel.

The post-consent CHALLENGE edges are forced by CHALLENGE's row read in every work-active state; the machine without them keeps every timeout and Inv-8 (`FsmCanon.preC1_adequate_without_the_edges`) and is deadlock-free and finite *(derived)*, a predicate weaker than bare adequacy.

### 13.4. The machine forced over the log

A **record** is the fold of the log to what the table reads: the open wait, consent to the current version, a FAIL taken into rework on it *(defined)*. A **principle** is a condition on one transition *(defined)*; a cell whose admitted outcome is unique is then forced whatever the other cells are. The principles *(defined)*: the signals' meanings (Ch. 11); the general sentences — terminality, universal CANCEL, ASSIGN initiates, IDLE has no clock, Inv-5's first clause, Inv-8's edge clause, the reassignable set, CHALLENGE's reach, the work states' reports, reports only on a version in force; Inv-4's reading, sharpened by the alternative reading of its routes (§12.12), as the entries into the decision; and four clauses — a state is what stands on the log (Inv-7), owner-exclusivity with the owner read off the log (Inv-8), consent before obligation (Inv-1), the clock moves a node only toward its settlement (Inv-5).

The forcing's **conditions** are the adopted among these — two design decisions, Inv-4's reading and terminality; the alternative reading of the decision's routes (§12.12); the adopted parts of three of the four clauses, Inv-1's being derived, and Inv-8's edge clause (`LogLanguage.clauses`, `general`, `pTerminal`) — and the per-state inputs: each signal's question and each wait's owner, the two channels, the work states' BLOCK and DELIVER, no report under a closing, CHALLENGE's reach *(defined)*. The forcing is relative to them.

A cell is **forced** when these admit exactly one outcome in it *(defined)* — the third class of cell.

The missed bound is kept as a record, its owner a reading: none, the executor, the issuer. Under every reading, over the records reachable from IDLE, every cell is forced, the missed bound is never entered — the same 22 records each time — and the machine is the table of Ch. 12 up to REWORKING's label *(machine-checked, `LogLanguage.forced`, `never_lapses`, `agrees_with_the_canon`)*. The record cannot tell a rework after a FAIL from a resumption after a block on one version, so REWORKING stays a label the log carries and the table does not force.

Without Inv-4's entries or any one of the four clauses, 11, 16, 27, 12, 16 cells are left open with no owner for the missed bound; 11, 26, 27, 12, 26 with the executor; 11, 19, 27, 12, 19 with the issuer; the signals' meanings with the general sentences and the reassignable set leave 107 open over 37 reachable records *(machine-checked, `loads_none`, `loads_executor`, `loads_issuer`, `general_sentences_leave_it_open`)*.

Counting an owned missed-deadline state as a channel of its own — equivalently, reading Inv-5 (b) on a fixed list of waits omitting it — leaves 26 cells without exactly one outcome with the executor as owner and 19 with the issuer, the lapse's own timeouts admitting no destination *(machine-checked, `the_lapse_as_a_channel_leaves_cells_open`, `the_lapse_has_no_timeout`)*. No second machine appears: the routes bar the lapse from the decision and (c) closes only from it, so a machine reaching the lapse leaves it no timeout, and the one completion keeping every principle is the table (`LogLanguageLapse.the_lapse_as_a_channel_admits_no_second_machine`). So the second reading of the decision's routes suffices for OVERDUE's removal, a missed-bound channel having no timeout.

ESCALATED's timeout destination is not pinned: bare adequacy with Inv-4's reading leaves it open, Inv-5 (a)–(c) fix it (§12.12), and it is forced with the four clauses.

Authoritative cancellation splits into §12.12's three one-transition sentences, and adding it back changes no cell (`authority_is_derived`) *(machine-checked)*. It is not derived from nothing: a closing not being a route into the decision is clause (2) made sharper, and CONFIRM_CANCEL's meaning is new, with its ground: it settles the closing, as PASS settles a delivery.

CHALLENGE is refused in VALIDATING in both forms *(derived)*: one moving the node would move a state its sender does not own, and one standing over the unvalidated delivery would put two open questions on one record, a machine with more memory than this one.

### 13.5. R′ over the log

Read as an input at the settlements, as the retry bit is at FAIL, R′'s gate gives a deterministic automaton; with R′'s form — a settlement unmade only by the issuer's re-ASSIGN where the gate holds — in place of terminality, every cell is forced, and the machine differs from the base in exactly the two R′ edges, five cells, which stay open without its admission half, the re-ASSIGN admitted where the gate holds *(machine-checked, `LogLanguageReopen.forced`, `the_only_exit_is_an_offer`, `off_the_settlements_nothing_moves`, `admission_carries_five`)*. Their target is forced by ASSIGN's meaning, a version entering as an unconsented offer, so anti-fake follows.

A rival R′ gating CANCEL is equally forced, so R′'s form and terminality stay design decisions (§12.14).

### 13.6. Scope

Outside the forcing: machines with more memory, another state inventory, stricter-admission refusals, and timing — the record does not tell a lapse with a live deadline from a missed deadline. Outside the table are the other routes to a false "done": who sends the PASS, what it carries (Inv-2), the graph (roots, AND, REOPEN).

Uniqueness over bare adequacy being false (§13.2), what is not settled is canonicity over a natural subclass, one fixed by a condition strictly weaker than the conclusion: "adequacy pins the behaviour map" is inter-derivable with it; Myhill–Nerode [50], which gives a behaviour its unique minimal automaton, presupposes that map; and that the conditions forcing the table over the log (§13.4) each read one transition does not make them natural, a full table being such a set too *(derived)*.

---

## 14. A worked example

### 14.1. The parties

Task: "Prepare release v2.0"; at the root the issuer is the PM and the executor the Tech Lead. The Tech Lead decomposes, so he issues the children (Ch. 10), and every seam keeps separation of duties, Demo's included: issuer Tech Lead ≠ executor PM.

Read seam-locally, the example leaves the residue one level up of §10.3: the PM executes Demo, the one child discharging c₃ ("demo ready"), and validates the root against c₃, while the Tech Lead validates Demo at its own seam.

### 14.2. The packet and the battery

```
spec:     a release with features A and B
criteria: (c₁) features A and B implemented per spec ∧ all tests pass,
          (c₂) documentation current, (c₃) demo ready
deadline: 20 days
max_iterations: 2
accepted_risks: the external API may change (P ≈ 0.1, impact ≈ 2d of rework;
                justification: adapting after the fact cost 2d on v1.5, below an
                abstraction layer's cost; invalidation condition: the vendor
                changelog announces a breaking major version)
```
The accepted risk is the PM's pre-fill; the register is tied to the split (Ch. 9), so the Tech Lead re-authors it at D(root). The v1.5 precedent makes P estimable and the event is infrequent, so STD-2 grades it statistical (Ch. 9), and the register is the route chosen.

The battery runs over the drafted split before the root packet goes out. CHECK-1 passes (c₁ ← Feature A, Feature B, Testing; c₂ ← Docs; c₃ ← Demo), and CHECK-1b: every child addresses a criterion.

CHECK-3: the child deadlines d5 (A), d7 (B), d12 (Testing), d15 (Docs), d17 (Demo) are ordered along Dep, Docs and Demo carrying slack for one rework cycle, since an overrun goes to ESCALATED. Item (6)'s gate (§11.5) passes each child before the parent's d20.

CHECK-7 flags "coverage ≥ 80%" ≢ "all tests pass". The repair is two-sided, each side forced by a different rule:
- A1 forces the parent edit: "all tests pass" is undecidable while its suite is unfixed, so the PM pins c₁'s test conjunct — the release's pinned suite passes, with 0 critical and 0 high among the issues filed against the release at its delivery. A1 forces only the pinning; "0 high" is his addition, and the conjunct keeps its pass requirement, the root's criteria being the goal's (Link-1, Ch. 5), not what Testing delivers.
- CHECK-7 forces the child edit, Testing's criteria matched to c₁: the pinned suite passes on the release build, with 0 critical and 0 high among the issues filed at Testing's delivery. Dropping the coverage bound is non-redundancy's, whose formal face no CHECK tests (§9.6): kept, it would let Testing fail while c₁ passes (FM-1.e).

A parent-only repair leaves FM-1.d; a child-only repair leaves c₁ undecidable. After both, the children entail c₁ only over the release as Testing delivered it: the window between the two deliveries' issue counts, which no child can carry, CHECK-7 still flags, and the Tech Lead enters it in his register, an uncertain, infrequent event whose P the issues filed late against past releases estimate, so STD-2 grades it statistical (Ch. 9); the PM's root check still meets it. The c₂ and c₃ arms are immediate; the feature conjuncts give non-redundancy (V(Feature A) = fail forces c₁ to fail). Both edits land before either ASSIGN — after it, each would be an Inv-1 re-ASSIGN.

```
v2.0
├── Feature A    [dev1, 5d]
├── Feature B    [dev2, 7d, ← the root's accepted-risk entry bears on this child]
├── Testing      [qa, 3d, Dep: A, B]
├── Docs         [writer, 2d, Dep: A, B]
└── Demo         [pm, 1d, Dep: Testing, Docs]
```

### 14.3. A dispute and a block

Feature B's detailed criteria, authored at its ASSIGN, depart from the draft, so that ASSIGN re-admits the root's split and the root's CHECK-8 re-runs. c_B1 ("new API only") and c_B2 ("legacy format supported") are FM-2 by mutual satisfiability, missed by the formal check on natural language and caught by the executor: CHALLENGE → ACCEPT_CHALLENGE removing c_B2 → OFFERED → ACCEPT.

Day 6: the API breaks and dev2 BLOCKs — the accepted risk fired. The Tech Lead answers by re-ASSIGN(adapt to API v3, deadline +2d), a revision, not a RESOLVE_BLOCK (§11.3): → OFFERED, re-ACCEPT. CHECK-3 re-runs: d9 < Testing's d12.

Beyond CHECK-3's order (§9.5), Testing waits on Feature B's PASS, owed within T_validate of delivery, so the schedule holds only because dev2 delivers before d9 and the Tech Lead validates at once, Testing's float spent.

### 14.4. Two FAILs at two seams

Day 13: the Tech Lead DELIVERs with self_validation, presenting verdicts earned at the children's own seams — A, B, Testing PASS; Docs FAIL (not updated after API v3); Demo waiting on Docs.

Two FAILs at two seams: the Tech Lead FAILs Docs → REWORKING; the PM FAILs the root on [c₂, c₃] → REWORKING — c₂ by his direct check, non-redundancy saying only that some criterion fails with Docs, c₃ by direct check alone, Demo's V being ⊥ (§7.3). The reworks pass, and v2.0 reaches DONE inside d20.

---

## 15. Graph and metrics

### 15.1. The task graph

**Definition (task graph).** The system state is a graph 𝒢 = (N, E_D, E_Dep, σ): nodes N (tasks), each carrying T, Del, V ∈ {pass, fail, ⊥} and its FSM state (Ch. 12); decomposition edges E_D ⊂ N × N; dependency edges E_Dep ⊂ N × N; global state σ (timestamps, counters). *(defined)*

The graph is the system: every signal (Ch. 11) and each act of §11.5 is a deterministic mutation of 𝒢. *(defined)*

The mutations *(defined)*:
- a root's creation adds a parentless IDLE node;
- an admission adds the split's children as IDLE nodes with their E_D edges and its declared E_Dep edges;
- a re-admission's dropped unissued child leaves the current projection (§11.5);
- ASSIGN issues a node; a re-ASSIGN on a live node re-authors it in place (Inv-1, Inv-7), its subtree kept (§12.10);
- PASS sets V = pass, FAIL V = fail, and a settled closing V = ⊥;
- an adopted discovered edge enters E_Dep (Ch. 11);
- REOPEN re-authors a terminal into OFFERED (§12.14);
- a revision whose criteria come to reference another node's result adds that Dep edge (Ch. 2);
- entering CANCELLING cascades the subtree (§12.6).

𝒢 is the log's projection onto the latest versions (Thm 11, Inv-7). Work kept outside 𝒢, unlike opacity inside the protocol (Thm 11's corollary), leaves no event in it.

𝒢 is not agent-invariant: its depth depends on the agent (§3.7).

### 15.2. One goal, one root

A root (Ch. 2), created by the goal's issuer (§10.1, §11.5), carries the goal's criteria (Link-1) and an executor (Del total, Ch. 2); V(root) is the verdict on the goal. *(defined)*

**Two parentless nodes are two goals.** *(derived)* The only law composing verdicts (Thm 1) runs along E_D and needs a parent, so over two parentless nodes no object says whether the goal is reached. A goal's identity is its node's, not its text's (Inv-7), so a second parentless node with the same criteria is a second goal, never a second attempt at the first.

The issuer being a role, not a checkable property of an actor, an implementation enforces one root per goal's graph.

At a root, whose issuer holds no split, the canon fixes no owner of a mandatory promotion (Ch. 11): the prerequisite may be a root of its own, a second goal the goal's issuer creates and joins to the blocked root by Dep, or a child the root's executor admits into D(root) — a freedom, each placement meeting every requirement stated.

### 15.3. D is a forest

**The graph of D is acyclic.** A cycle is a recursion that never reaches a leaf, against A2's κ-recursion into a tree (Ch. 3) *(derived)*. Goal attainment's TREE topology (Ch. 6) is this forest.

**A node has at most one parent.** *(derived)* A node has one packet, hence one transaction with one issuer, the executor of the parent whose split holds it. A child of two parents would get two issuers after one admissible Del revision (Inv-1), an undefined public/internal status, and a CANCEL of either parent cascading into a child the other needs; a result two branches need goes through Dep. D is thus a forest relative to the issuer role.

CHECK-2 (Ch. 9) operationalizes this forest. Its two D clauses guard no mode.

Retry-hysteresis, which §7.1 keeps out of V, is carried by the machine (Ch. 12): REWORKING, FAIL's retry guard, the counter in packet and log.

### 15.4. The quality metric Q

**Definition (Q).** Q = (q_T, q_D, q_V, q_Dep, q_Del) ∈ ([0,1] ∪ {⊥})⁵, one component per primitive, each catching defects of its type. *(defined)*

| Component | Primitive | What it reads | Formula |
|---|---|---|---|
| q_T | T | the spec defects CHALLENGE reports (§11.2) | 1 − \|criteria challenged (a CHALLENGE no REJECT_CHALLENGE refuted) ∨ changed for a spec defect\| / \|contract issued (ASSIGN)\| |
| q_D | D | the pattern a composition claim refuted at contact leaves, whatever caused it | 1 − \|non-atomic, own validation FAIL while children passed\| / \|non-atomic, own validation returned a verdict while children passed\| |
| q_V | V | a recorded PASS later failed, whatever caused it | 1 − \|a PASS recorded, later failed as delivered under the criteria it passed\| / \|a PASS recorded\| |
| q_Dep | Dep | the plan's undeclared couplings a BLOCK names, whatever their mode (§8.6) | \|Dep_declared\| / \|Dep_declared ∪ Dep_discovered\| |
| q_Del | Del | the capability mismatches reassignments name | 1 − \|reassignment for capability_mismatch\| / \|contract issued (ASSIGN)\| |

Each metric is a ratio of two sets read off the log (of nodes; of edges for q_Dep); a node belongs to a set iff the log records the set's event for it, whatever state it reaches later; an empty denominator gives ⊥. *(defined)* A node's children passed when at least one was active and every active one had V = pass. *(defined)* A scope extension (a re-ASSIGN of the goal with new criteria) is sanctioned, not a spec defect. *(defined)* A later fail is a fail of the artifact as delivered under the criteria it passed: a FAIL after a REOPEN under unchanged criteria over the logged result re-delivered, or the fail of a **post-hoc run**, an independent validation over a completed node, triggered externally (a complaint, an incident, an audit), which the log carries as the discovery event — a log entry, not an act on the node, DONE and its V standing (§12.14). *(defined)*

q_V covers the false-PASS direction, a node's own PASS over a dropped fail among its children (FM-4 there) included; false FAIL is outside q_V, its share a diagnostic, not a mode gap, a design decision *(adopted)*. A false FAIL is guarantee-safe (Ch. 8), contestable under A1 and self-recorded as a criteria-cited FAIL (Thm 11); its unaggregated share diagnoses an over-strict validator or an issuer failing sound work to harm the executor.

q_Del answers none of the six modes, by the argument that takes CHECK-6 out of them (Ch. 9): a capability mismatch surfaces as a lapse or a FAIL, and an untrue PASS over work its holder could not do is read by q_V, of the mode §8.4 and §12.8 give it. A leaf its holder cannot realize is a claim of Del's, not of the split's: q_Del's.

**Minimality.** *(derived)* The five metrics are in bijection with the tuple's five components (T, D, Dep, Del, and V derived), and removing any leaves a blind zone:

| Remove | Blind zone | The invisible defect |
|---|---|---|
| q_T | criteria quality | challenged or changed specs |
| q_D | decomposition quality | the refuted composition claim (a parent that should have failed and passed stays invisible with q_D too: the shared blindness) |
| q_V | validation reliability | rubber-stamping, pass → later fail |
| q_Dep | dependency completeness | hidden dependencies, surprise BLOCKs |
| q_Del | delegation correctness | capability mismatch |

Each metric reads its own numerator events (the table's formulas); q_T and q_Del share the ASSIGN denominator, but with different numerators none is expressible through the rest; Q is minimal in the sense of the basis and the alphabet.

Calibrated bounds on Q come from a binomial or concentration bound on each rate.

The stream Gen(Ω) of a maintenance goal's independent roots (Ch. 6) is a forest in 𝒢, each τ_k a goal with its own root, and the six modes and the event metrics work on it unchanged, as V and Thm 1 do (Ch. 6, Ch. 12). *(derived)* The aggregate layer over the stream (Ch. 6) is scoped above any node as the false-FAIL diagnostic is. *(derived)*

### 15.5. Populating q_Dep

Without discovered edges q_Dep cannot fall below 1; BLOCK's provisional discovered edge (Ch. 11) is the carrier. A BLOCK exposing a missed dependency falsifies the plan's implicit independence claim, a promised passage of Ŝ∖S (Ch. 3), and contact adds a real S edge. A producible prerequisite (§11.3) is a Dep edge q_Dep counts.

**Definition (Dep_discovered).** The prerequisites the BLOCKs at a node name, one per distinct prerequisite, undeclared before the first BLOCK naming it, less those whose latest adjudication — the issuer's confirm or refute in RESOLVE_BLOCK's action or a re-ASSIGN's or CANCEL's reason — refutes them; a repeated BLOCK naming it reopens it. *(defined)*

**Definition (Dep_declared).** The edges the plan declared before any BLOCK named them; a discovered edge never joins it, whether confirmation adopts it into E_Dep or a later admission writes it. *(defined)*

A confirmed discovery whose adoption would close a Dep cycle (CHECK-2) is not adopted: it refutes the plan's ordering, which only a re-decomposition restores. *(defined)*

q_Dep measures the share of the dependency structure declared in advance of the discoveries made, not a share of S: nothing adjudicates a declared edge, and an edge no criterion references may be declared.

### 15.6. Self-measurement

**Theorem 10 (self-measurement).** Q is computable from the execution trace with no additional data collection, bar the post-hoc runs of q_V's later-fail term, triggered externally; four components are trace-closed. *(derived)*

*Proof (constructive-definitional).* Every verdict is a contact event the protocol records on the log. Each set in Q is defined by logged events — CHALLENGE, REJECT_CHALLENGE, a cause-typed re-ASSIGN, a parent's verdict over its children's, PASS and a later fail, BLOCK and its adjudication — and signals are written into 𝒢 by construction, so each component is a count over the log 𝒢 projects, q_V's later-fail term once its post-hoc runs are on the log. ∎

A timeout's record (§12.2) is on the log Thm 10 counts over; no q-metric counts expiries, none being attributed (§12.2).

**Corollary 1.** For the four trace-closed components measurement costs nothing, the protocol being both workflow and instrument. *(derived)*

**Corollary 2.** Faking a metric by signals is faking the process, costlier and more visible than faking a report. *(derived)* A metric also moves with choices the protocol permits but does not price — five dials, named rather than closed, four a graph act or label, the fifth outside the graph:
1. **Granularity.** A finer split of easy work, an admission nothing counts or bounds, raises the node-population denominators of q_T, q_Del and q_V; only added depth moves q_D; a fully declared finer split pushes q_Dep toward 1. Granularity is ranked only structurally (Ch. 4), so nothing fires on it.
2. **Padding declared Dep edges.** An edge no criterion references may be declared (§15.5), refused only for a cycle (CHECK-2) or a crossing order (CHECK-3), so the plan's author can drive his own Dep sensor toward 1.
3. **Self-typed causes.** Where a revision's or a reassignment's cause is the issuer's own judgement — a criterion's defect or the scope's extension, a capability mismatch or not — the type he gives decides whether a criterion's unchallenged change puts its node in q_T's numerator, and a reassignment its node in q_Del's.
4. **Individuation.** Three true BLOCKs on facets of one missing producible prerequisite make three records in Dep_discovered where a coarse report makes one.
5. **Which graph is the report.** An issuer may run the same criteria as several roots and report the cleanest; Q is a statement about one graph, and selecting among attempts conditions on the sensor itself, invisibly to any query over the reported trace.

Q is therefore comparable across nodes only under one decomposition discipline, one labelling discipline and one reporting granularity, and only where the graph reported is the graph that ran; a cross-agent comparison compares splits, labels and reports as much as work.

### 15.7. What each metric senses

Beyond its standards and CHECKs (Ch. 9), FM-1 is guarded at runtime by CHALLENGE (counted by q_T) and q_D.

On FM-1.d's domain face q_D counts the refuted edge, integration case (iii), where it bites; case (ii)'s denial stands silent in q_D's shared blindness (§15.4), its false PASS FM-3's where a verdict is formed from it (§8.7); a later fail of that PASS is q_V's.

q_V reads every PASS a later fail finds, whatever made it untrue (§8.4, §12.8), and is biased by a later fail itself untrue. As no structural CHECK guards FM-3, at runtime q_V senses its false-PASS direction only, and Inv-2 refuses a pass over a criterion recorded non-pass.

FM-4 has no structural guard (Ch. 9). Its trace, the departure from AND, is read off the log (§12.8); its drop-a-fail direction reaches q_V (§15.4); and the departure is shared with the cases §8.5 names, which contact tells apart.

FM-5 is guarded by CHECK-3, CHECK-2's Dep clause and the protocol (BLOCK → RESOLVE_BLOCK, a revision's flagging guards, §12.10, and the cascade, §12.6); q_Dep reads the undeclared couplings BLOCKs name, an FM-5 race among them (§8.6).

A refutation after contact is a later evaluation's fail on the same result, q_V's later-fail term: a REOPEN's FAIL is the node's verdict, its untruth FM-3's where §8.4 places it; a post-hoc run's fail forms no verdict (§15.4), its untruth no mode but a bias of q_V.

A reopened node's false PASS, FM-3's where §8.4 places it, is sensed by q_V — R′'s anti-fake residue (§12.14).

In the worked example (Ch. 14): dev2's CHALLENGE is a q_T event against the disputed criteria's issuer, the Tech Lead, in the slice of q_T's populations taken by the ASSIGN's author, which the formula admits but does not define. The BLOCK on the declared accepted risk leaves q_Dep unaffected: the blocker is non-producible, so no Dep edge was missed. The FAIL on Docs is a leaf's ordinary contact verdict, caused by Feature B's revision along a declared edge — FM-5's freshness as the root's split sees it; q_Dep is untouched, and it is no q_D defect.

### 15.8. Limits of the metrics

Without external validation of Q against real outcomes the system is closed.

**q_V** is retrospective: informative given a trigger, optimistic without one, moved by dials 1 and 5, blind to a false PASS its issuer takes out of reach while unconsumed (§12.14). 1 − q_V is an observed lower bound on P(goal false | pass) only where the later-fail runs are themselves true (§15.7) and the criteria track the goal, the (ii)-faithfulness premise (§4.6). Without deployment data this ceiling stands.

**q_Dep** is a proxy: its numerator is what the plan's author declares, its denominator adds only the discovered Deps as the executor individuates them, adjudicated by the plan's author. It over-estimates declared-completeness, is not comparable across executors, bounds nothing once the declared side may exceed S, is optimistic by unchecked refutations and pessimistic by an unanswered false BLOCK.

Of the five metrics two are genuine observables (q_D of a parent's FAIL over passing children, q_V of later-failed passes), two proxies with known biases (q_T, q_Dep), one weak (q_Del). *(derived)*

### 15.9. Triage order

The protocol names where to intervene: the failing node with its criteria and author (Inv-3, Thm 11). In what order, when several fail and capacity is short, splits into two halves, only one answerable from the apparatus.

**Definition (dependency cone).** What a node's failure holds: upward along E_D its whole ancestor chain (a failing child denies every ancestor's pass, Thm 1), forward along E_Dep the consumers reading its result. *(defined)*

Repair first the failing node whose cone blocks the most, the nearest binding deadline breaking ties; the cone is a reachability query over 𝒢 and the deadlines are packet fields. The rule is a heuristic under a premise named here: repair cost roughly uniform across the failing nodes, the canon carrying no cost model to weigh differing ones. *(premise)*

The rule orders by the reach a failure holds, not by the work one repair unblocks — where cones overlap, a repair unblocks nothing until its co-failing siblings are repaired — and says nothing about which failure is worse. Ranking by how badly a node failed needs a calibrated probability model A1 and A2 do not supply, binary V leaving no intra-node gradient; no claim of the canon uses one, and consequence in the graph and magnitude of failure coincide only by accident.

---

## 16. Guarantees

### 16.1. Adherence and the information structure

**Definition (adherence).** An organization O is a DAG of agents of depth n; its adherence α ∈ [0,1] is the share of tasks run through the GFSO protocol. *(defined)*

**Definition (information structure).** ℐ(α) is all information available to an agent for decisions at adherence α: ℐ(0) the informal status quo (experience, calls, meetings, memory); ℐ(1) the full log with its projection 𝒢 (Ch. 15) — per task the spec, criteria, split with authorship, register, every timestamped signal, Q, analytics over the history; ℐ(α) the informal channels with the protocol signals of the covered share, and the meta-information of coverage. *(defined)*

**Definition (experiment).** θ = (θ₁, …, θₙ) ∈ Θ is the tasks' hidden state (quality, progress, blockers); at adherence α the agent observes s_α from ℰ_α = (S_α, π_α), with S₀ = S^inf the informal signals and S_α = S^inf × S^prot_α. *(defined)*

**Definition (Blackwell dominance).** ℰ₁ ≥_B ℰ₂ iff ℰ₂ is a garbling of ℰ₁ — a Markov kernel M with π₂(·|θ) = M · π₁(·|θ) for all θ — equivalently E[u | ℰ₁] ≥ E[u | ℰ₂] for every utility u; strict where not also ℰ₂ ≥_B ℰ₁ [1]. *(by citation)*

### 16.2. Information dominance

**Rationality.** The agent reading the information is rational; Blackwell dominance presumes it. *(premise)* **Invariant, nested channels.** The informal channels are invariant in α (the protocol does not forbid calling), and the α₁-share of tasks is a subset of the α₂-share, without which no projection makes the lower experiment a garbling of the higher. *(premise)*

**Prop 3 (information dominance).** For any α₂ > α₁ ≥ 0, ℰ_{α₂} ≥_B ℰ_{α₁}. *(derived)*

*Proof.* With proj_{α₁} discarding the protocol signals of the tasks in (α₁, α₂], the deterministic projection

```
M(s_{α₁} | s_{α₂}) = 𝟙[s^inf_{α₁} = s^inf_{α₂}] · 𝟙[s^prot_{α₁} = proj_{α₁}(s^prot_{α₂})]
```

gives π_{α₁}(·|θ) = M · π_{α₂}(·|θ) for all θ, so ℰ_{α₁} is a garbling of ℰ_{α₂} [1]. ∎

### 16.3. Improvement through constraints

**Bounded rationality.** The agent may take options costlier in expectation. *(premise)*

**Game.** Issuer and executor; θ ∈ {θ_good, θ_bad}; u = outcome − cost; compliance costs c > 0. Each constraint costs c under θ_good and averts a cost Δ under θ_bad:

| Constraint | θ_good: protocol vs without | θ_bad: protocol vs without |
|---|---|---|
| criteria mandatory | u − c vs u | u − c vs u − Δ_dispute |
| deadline mandatory | u − c vs u | u − c vs u − Δ_inaction |
| criteria immutable | u − c vs u | u − c vs u − Δ_rework |
| accepted-risks register mandatory | u − c vs u | u − c vs u − Δ_defect |

**Prop 4 (constraint improvement).** When Δ > c, the protocol's constraints improve the expected payoff for any ℙ(θ_bad) > c/Δ — in expectation, not state by state [5]. *(derived)*

*Proof.* Under θ_good the protocol costs c more; under θ_bad it is cheaper by Δ − c, Δ being the averted part of the loss — for the register, what acting on an entry's invalidation condition averts, an act no signal forces. So E[u_protocol] > E[u_without] ⟺ ℙ(θ_bad) · Δ > c. ∎ Δ > c and ℙ(θ_bad) > c/Δ stay premises. *(premise)*

**Formalization overhead.** Criteria, the register and the CHECK battery add cognitive load, part of c; at what overhead the protocol pays off is an empirical question: a measured overhead places Prop 4's threshold and changes no claim.

Prop 3 and Prop 4 are independent improvement mechanisms: information via Blackwell under rationality, and removal of options costlier in expectation above the threshold under bounded rationality. *(derived)*

### 16.4. Universal improvement

**Non-adversariality.** Agents act in their own interest and do not sabotage; the scope is permissioned — authenticated transport, one sequencer. *(premise)*

**Corollary (Universal Improvement).** For a non-adversarial agent, GFSO at α > 0 is weakly better than the status quo in what his premise licenses. *(derived)*

*Proof.* A rational agent gains through information (Prop 3), strictly as a dominance relation where the new protocol signals carry information about θ the rest does not; the payoff comparison is weak and gross of compliance cost, so net of it the gain must exceed c. A bounded-rational agent gains through constraints above Prop 4's threshold. ∎

The corollary assumes that the protocol does not degrade the informal channels, that Prop 4's threshold holds for the constraint arm, and non-adversariality. *(premise)*

### 16.5. α-monotonicity

**Sustained adherence.** α is exogenous: nothing in the model sets it, adherence aggregating compliance decisions whose cost c is individual and immediate while Δ accrues later and collectively; every guarantee stated in α is monotone in it, and the premise stands wherever those results are used. *(premise)* Its closure needs adherence dynamics, a utility model over actors A1 and A2 do not supply; no guarantee uses one, each needing only α measurable.

**Corollary 5 (α-monotonicity).** For a rational agent with any u, E[u | ℐ(α)] is non-decreasing in α, by Prop 3 and the Blackwell equivalence [8]. *(derived)*

Cor 5 is gross of compliance cost (§16.4). There is no *information* threshold, only the constraint arm's ℙ(θ_bad) > c/Δ (Prop 4).

Non-adherence inside the protocol is observable from inside (Thm 11's corollary); α's denominator is not (§15.1), so the share needs an outside count, and the premise is measured and falsifiable on the graph's side and an unmeasured requirement on the other. *(derived)* The agent's solitary induction (Ch. 4) gets from Cor 5 only weak monotonicity in aggregate.

### 16.6. Temporal monotonicity

**Non-decay.** The informal channels do not decay. *(premise)*

**Prop 6 (temporal monotonicity).** At fixed α, ℐ(α, t₂) ≥_B ℐ(α, t₁) for t₂ > t₁: for the protocol's component outright, for the whole under non-decay. *(derived)*

*Proof.* The protocol's information set only grows, the log being append-only (Thm 11); forget the records after t₁ [1]. ∎

The strict reading, that new signals inform rather than add noise, rests on the (ii)-faithfulness premise (Ch. 4).

### 16.7. Scale monotonicity

**Correctness of D.** Thm 1 and what rests on it — Prop 7 and the strict readings of the information results — are conditional on the correctness of D. *(premise)* Prop 7 — γ < 1 only where a validation's criteria track reality — and the strict information readings carry the (ii)-faithfulness premise (Ch. 4).

**Definitions.** e₀ is the initial deviation from the intended policy; at each level an operator Ψᵢ amplifies error with gain Λ > 1 and validation suppresses it with gain γ < 1, a gain being the induced norm gᵢ = sup ‖Ψᵢ(e)‖/‖e‖ in ℓ∞. *(defined)* The model takes Λ uniform, the operators linear and feedforward; real hierarchies being heterogeneous and adaptive, the result is a worst-case upper bound. *(premise)*

**Prop 7 (scale bounds).** In a feedforward hierarchy of depth n *(derived)*:

```
Without the protocol:  ‖eₙ‖ ≤ Λⁿ · ‖e₀‖
With the protocol:     ‖eₙ‖ ≤ (Λ·γ)ⁿ · ‖e₀‖   — exponential suppression when Λ·γ < 1
```

*Proof.* eₙ = Ψₙ ∘ … ∘ Ψ₁(e₀), and by submultiplicativity ‖eₙ‖ ≤ ∏ᵢ gᵢ · ‖e₀‖, with gᵢ = Λ without validation and gᵢ ≤ Λ·γ with it. ∎

At partial adherence, each level's task covered with probability α, E_α(n) ≤ (1−α)·Λⁿ + α·(Λ·γ)ⁿ under any dependence of coverage across levels: the product of same-direction factors is largest in expectation when the levels are covered together, and the bound is reached where a chain is covered or not as a whole; independent coverage gives the smaller (Λ·(1 − α + αγ))ⁿ. *(derived)*

CHALLENGE and BLOCK form upward feedback, BIBO-stable by the small-gain theorem when gain-up · gain-down < 1 [9] — no infinite challenge-override spiral. *(by citation)* With the cascade bound this gives only the channel's stability.

**Corollary 1 (sparse validation).** Checking every k-th level requires γ ≤ Λ^{−k}; whether that is cheaper than review at every level depends on a validator cost model the canon does not carry. *(derived)*

**Corollary 2 (validator composition).** γ(V₂ ∘ V₁) ≤ γ₁ · γ₂, by the submultiplicativity Prop 7's proof runs on, with equality only where the validators' worst cases align; several imperfect validators suffice where no perfect expert exists. *(derived)*

**Corollary 3.** Validation lowers the guaranteed bound by the factor γⁿ, for one validation operator per level. *(derived)*

Forward attribution (Ch. 4) is this error cascade, and damping Λ·γ is a decomposition's third structural rank beside Ch. 4's two. Monotonicity thus runs along three independent axes — adherence, time, scale — weakly in α and t, and in n exponentially under the discipline.

### 16.8. The incentive game

**Setup.** For each signal the agent picks an honest or dishonest reporting policy; the honest one is state-contingent (signal iff you observe the condition); the reporter knows his state, θ being hidden from the counterparty only. *(defined)*

**Definition (price).** A deviation's price p is the probability that the first check by another party of a delivery carrying it fails it while the deviator's contract there is open (under R′, while an unconsumed ancestor is reopenable): that check's sensitivity as a verdict (Inv-2). *(defined)*

Detection is structural — a claim about the channel, not about p = 1: the verifier ≠ executor seam and q_V catch a one-sided deviation whatever the counterparty plays, θ being a move of nature over which expectation does not demote DSIC to BIC; how often the channel fires is p. The timeout bounds a one-sided stall and detects no one. *(derived)*

**Definition (exposure).** The exposure of a false PASS at node i is 1 − ∏_{j ∈ cone(i)}(1 − p_j) under independent detections, p_j being the sensitivity of an honest validator j in i's **validation cone**, the validations of i's dependency cone (Ch. 15), each reading i's result; under correlated detections only max_j p_j ≤ exposure is guaranteed, the independent aggregate being an upper bound where they correlate positively. *(defined)*

### 16.9. The named exceptions

**Definition.** A named exception is a deviation lacking the detect-and-price property: a party's gain rests on the counterparty's assessment, on a record no metric reads, or on a cost the protocol does not price. There are fifteen, each unpriced unless stated. *(defined)*

1. **Issuer-false-FAIL.** A false rejection only its issuer can reverse, q_V reading only acceptance and q_D charging one over passing children to the split.
2. **The issuer-response exception.** A false, late or missing answer to a true BLOCK or CHALLENGE, adjudicated only by the issuer's own answer, while the honest report costs the executor contract time; after consent the silent route gains only with 1 − p, before consent without bound.
3. **The executor-false-report direction.** A false BLOCK or CHALLENGE, detected only by the issuer's adjudication: ε if caught, what the answer grants if not; caught in OFFERED it returns the node to the offer with a fresh bound, so the before-consent regime can be held to the deadline.
4. **Issuer-replaces-the-asker.** A Del-changing re-ASSIGN over an unvalidated delivery or an unanswered CHALLENGE or BLOCK, needing no answering signal (Inv-1), counted by q_Del only when typed capability_mismatch; the new executor may re-deliver the logged result and take the verdict on work not his, the log showing whose it was.
5. **Issuer-keeps-the-artifact.** Holding a delivery or work in flight with no verdict, by any move or silence above the node that settles it or supersedes its delivery unvalidated (Ch. 12), CONFIRM_CANCEL handing him the in-flight state; no check reads an absent verdict.
6. **The withheld in-flight report.** Silence or a false report under CANCEL, which no check reads, CANCELLING's bound settling the node as CONFIRM_CANCEL does: the executor keeps his work from the issuer as exception 5 lets the issuer keep it from him.
7. **The false record.** Not declaring a foreseen factor, or writing a materialized one in as an entry, a false register dated by its re-admission; or typing a revision's or a reassignment's cause falsely, a false reason on the re-ASSIGN. No check reads whether either record is true (dial 3), so the record is evidence only against its author.
8. **The false self-check.** A self_validation the executor knows is false, gaining the pass with 1 − p, or an issuer's PASS over an implementation's check recorded as failing; no metric reads either record.
9. **Silence over a passing defect.** Silence over a spec defect the verdict does not read — before delivery a requirement no criterion writes, after it any defect — at p = 0 on the node; it surfaces through q_T, where FM-1.f is read (§8.3) or in a consumer's validation cone, a post-delivery report re-entering only by an issuer's move returning the node (§12.4, §12.14).
10. **Revise-to-meet.** A revision changing a questioned field supersedes an open challenge (Inv-1) with no answering signal or justification, pocketing a challenge it meets and dismissing one it does not, repeatably within the deadline, back before consent, at a root too.
11. **Work outside the contract.** Before consent, splitting and issuing children to see what they return, then ACCEPTing or abstaining (Inv-4's named exception); after consent, an ACCEPT the executor cannot vouch for; past his bound (ESCALATED, or VALIDATING after a delivery at the deadline), work through his subtree. No lapse is attributed and no q-term reads consent. No face can be gated: "no split before consent" is lifted by ACCEPT, a true report from an executor who can perform, but from one who cannot yet know — splitting being how he would find out — only by the second face, a lift §12.16 (ii) refuses; the last face's only lift is the counterparty's move.
12. **Cancel-and-re-issue.** A CANCEL, or a re-decomposition dropping the issued child, then a new node with the same criteria for the same work, which no metric links to the old; priced only by restarting the work. It stands in for a rejection without cited criteria (Inv-3 bypassed, a fresh budget) or a silently accepted challenge; at a root it runs under a new goal id, the old goal ABANDONED.
13. **The unvalidated child.** Leaving a child unvalidated when the parent's verdict arrives: q_D's precondition, every active child passing (§15.4), is the split's author's to set as the children's issuer, so the attribution of a materialized undeclared risk is withheld while the divergence is still caught — a gain resting on the parent's issuer's assessment of the split.
14. **The unstaked verdict.** A PASS without looking by an issuer who bears no Δ at his nearest public seam above the child — that node settled and final (Ch. 12) while the child waits, handed over, or lacking his consent — so the check there no longer prices him; exposed only through the consumer's validation cone and q_V.
15. **The re-publicized self-issued verdict.** A verdict signed while the child was internal, left standing when a revision makes it public; no seam checked it, and only the parent's validation cone exposes it.

Thm 10's five dials (Ch. 15) are not exceptions: each is a choice the protocol leaves to its maker, made honestly, so no deviation in the game's sense (§16.8), however it moves a metric a reader of the log relies on; exception 13 is a deviation, the validation it withholds being owed.

Four metrics are bounded by these exceptions. **q_D** reads a pattern, not its cause (§15.4, §8.5), so charging the split needs the cause (§9.2); it is masked by correlated errors, and its precondition can be withheld (exception 13). **q_T**, reading silence from incompetence or fear as clear criteria, is optimistic by false rejections (exception 2) and pessimistic by unanswered false challenges (exception 3). **q_Dep**'s two biases (§15.8) are exceptions 2 and 3. **q_Del**, significant only at scale, is bounded by exception 4.

### 16.10. The rows

**The executor's silence.** Over his own defect or blocker the check is his node's validation, whose consequence the FSM forces — a FAIL on unsatisfiable criteria (Inv-3) — so p = 1 under a validator sensitive to the defect, below one by FM-3's residue; a delivery around an unreported blocker meets the same check, and a contract run out on it detects no one (§16.8) and gains him nothing. *(derived)*

**CHALLENGE.** θ₁: the spec is defective; θ₂: it is fine.

| | θ₁ (defect) | θ₂ (none) |
|---|---|---|
| CHALLENGE | the defect is fixed: u₁ | a false alarm: u₂ − ε |
| Silence | a FAIL on unsatisfiable criteria: u₁ − Δ, for a defect the verdict reads | works fine: u₂ |

A defect the written criteria pass over is exception 9. Per state, silence dominates under θ₂ and CHALLENGE under θ₁ at the grade the issuer's answer allows (next row), with no prior and no Δ/ε ratio; Δ > cost(signal) makes the θ₁ column bite. *(derived)* Ex ante even always-CHALLENGE beats silence, ℙ(θ₁)·u₁ + ℙ(θ₂)·(u₂ − ε) > ℙ(θ₁)·(u₁ − Δ) + ℙ(θ₂)·u₂, whenever ℙ(θ₁)·Δ > ℙ(θ₂)·ε. *(derived)*

**BLOCK and CHALLENGE under a defect** or a blocker only the issuer can remove: the honest report reaches the one party who can act while the deadline runs and no DELIVER is admissible (Inv-8); the silent executor may deliver around it and is failed with p cumulated over rounds. If the answer removes the defect in time, honesty is strictly dominant; if it leaves contract and defect with the executor, honesty is weakly dominant at p = 1 and below it silence passes with 1 − p (exception 2); if it takes the contract, by CANCEL or a Del change, the report loses at every p (exceptions 5, 4). *(derived)*

**BLOCK and CHALLENGE without a defect.** A false report, caught by the issuer's adjudication (REJECT_CHALLENGE, a refuting RESOLVE_BLOCK), costs ε and buys nothing, so silence dominates; what it buys uncaught, or caught in OFFERED, is exception 3. *(derived)*

**ACCEPTED_RISKS.** No state, timeout or verdict turns on the register: a factor that materializes is met the same way — a BLOCK, a FAIL, q_D's pattern — whether or not it was declared, so the row's price is 0 and honesty wins only as far as the record costs its author outside the protocol (exception 7). *(derived)*

**CONFIRM_CANCEL.** No check reads the in-flight report, so its honest use has no p and is not dominant (exception 6). *(derived)*

**PASS/FAIL.** An honest FAIL leads to recorded rework; a fake PASS is priced at p and exposed, so honesty is dominant exactly where p·Δ > cost(signal). *(derived)* The fake PASS's deviator is the child's issuer, Del(parent), priced by the check at his own nearest public seam above the child, below which his nodes are signed by himself; the rest of the cone and q_V reach him only through the record. A signer with no check by another party above him is the goal's owner: a false PASS costs him his own goal, which puts the case outside the incentive surface, not among its exceptions.

### 16.11. Incentive compatibility

**Prop 8 (incentive compatibility).** On the deviations the protocol detects and prices independently of the counterparty's strategy, when p · cost(undetected defect) > cost(signal), honest use of every protocol signal maximizes expected payoff for any ℙ(defect) > 0 against any non-colluding counterparty — a dominant strategy, not a Bayes equilibrium [3]. *(derived)*

*Proof.* The rows of 16.10, each at its p; what lacks the detect-and-price property is the fifteen exceptions. ∎

Prop 8's inequality, for every covered signal at its p, is its premise. *(premise)* Detection being independent of the counterparty's strategy, the non-sabotage half of non-adversariality (16.4) is needed only against collusion, which removes that independence, and griefing, harm with no gain the protocol prices, criteria-lowering among it, its permissioned scope supplying the identities and the order the detection reads. *(premise)*

### 16.12. IC-minimality

**Claim (IC-minimality).** Removing any IC-critical feature makes the dishonest behaviour it closes free for a specific agent, where with it the behaviour is reachable only through a named exception at its cost (exceptions 12, 10); five rows carry their own grade in-cell. *(derived)*

| Remove | Agent | The dishonest behaviour that becomes free |
|---|---|---|
| CHALLENGE | Executor | Silence about a spec defect; with the channel, silence stays free over a defect the verdict does not read (exception 9). |
| BLOCK | Executor | Silence about a blocker, the deadline ticking unnoticed. |
| DELIVER's self_validation | Executor | Delivering unchecked; with it, sloppiness closed only as far as the record costs its sender (exception 8). |
| The mandatory register | Decomposer, Del(t) (STD-1) | Hiding risks; closed only as far as the record costs its author (exception 7). |
| FAIL's criteria[] | Issuer | An unjustified rejection; a re-ASSIGN under unchanged criteria and Del only re-presents (Inv-1). |
| Criteria immutability | Issuer | Goalpost-shifting after ASSIGN. |
| REJECT_CHALLENGE's justification | Issuer | Ignoring feedback, making CHALLENGE pointless. |
| Timeouts | Executor after consent | Stalling; an IC closure only for the executor after consent, whose own contract a delay spends as far as he means to deliver; his delay before consent and the issuer's anywhere are only bounded (Φ1). |
| max_iterations | Executor | Unbounded resubmission within the contract, each a new draw against a validator of sensitivity below one. |
| ACCEPT | Executor | Repudiating the terms after the fact, with no fixed acceptance point. |
| ACCEPT_CHALLENGE | Issuer | Silently pocketing a correct challenge; closed only as far as the issuer chooses the signal over exception 10's revision. |

The timeouts row is the timeout mechanism of Ch. 12 as a whole.

**Independence.** The 11 features each protect against a distinct dishonest behaviour, none compensated by the rest; the routes standing in for a row (exceptions 4, 10, 12) exist with the rows as without them, each visible in the log. *(derived)*

**Not rows.** CONFIRM_CANCEL: silence under a CANCEL is as free with the feature as without (exception 6); the signal is FSM-typed and Inv-8-forced given CANCELLING. ESCALATED's answer channel: removing it frees no dishonest behaviour, silence already closing the state; Inv-4's reading pins it. max_reopens is R′'s IC feature against reopen-griefing, outside the base count.

Outside the rows of §16.10 and this table, each at its grade, and inside the fifteen exceptions, honesty is dominant only as far as someone reads the log.

The IC defect type of Ch. 11 is a deviation Prop 8 cannot price, detection being its premise; of the three signals of that type, ACCEPT and ACCEPT_CHALLENGE are rows of this table, and REJECT_CHALLENGE's content, a false CHALLENGE no longer a free veto, is priced by §16.10's row without a defect.

These rows ground parts of the machine (Ch. 12): CHALLENGED is entered after consent from EXECUTING and REWORKING, not through BLOCK, because through BLOCK the dispute would lose both closures after consent; a revision binding only on ACCEPT is ACCEPT's IC protection; a re-ASSIGN answering a question on fields it keeps would be a rejection without FAIL's criteria or REJECT_CHALLENGE's justification; and the backbone roles the ACCEPT, CHALLENGE and ACCEPT_CHALLENGE rows demand stand on those rows' IC-minimality. A conformance refusal liftable only by the clock can push a report past where the contract can act on its answer (exception 2); one liftable only by the counterparty removes the feature the signal carries.

### 16.13. IC at the seam

The seam's check (Ch. 10) is another party's because Prop 8 rests on detection by another party. IC applies where separation of duties fires (§10.3), at every public node; of the self-signed verdicts not carried (§10.3), the re-publicized self-issued verdict is exception 15, an internal verdict no delivery of the public node above carries is exception 14 once that node is final, and a self-assigned root's signer is the goal's owner, outside the incentive surface (§16.10). *(derived)*

An implementation check whose record binds the signature adds a second damper at its level (Cor 2) and a detection probability for a false PASS below the seam; one logged beside a PASS adds a record against the signer and no damping; which, is the implementation's freedom within conformance.

A holder who has accepted nothing moves inside the exceptions: his PASS is exception 14, his FAIL exception 1, his CANCEL or Del-changing re-ASSIGN over an open question exception 5 or 4; a cascading CANCEL over children that delivered nothing is the rule's plain price.

### 16.14. Issuer silence at validation

A VALIDATING timeout routed to acceptance would let a parent's executor, as his child's issuer, obtain an acceptance nobody made, read upward by AND, by letting the child's VALIDATING lapse; routed to ESCALATED (§12.4), it is exception 5's silence, and a re-ASSIGN under unchanged criteria re-presents the delivery (§12.10), bypassing no FAIL row but by exception 5's short re-presentation. *(derived)*

### 16.15. The threat model

**The stratification.** *(derived)* Claims about form over the log and the graph are adversarial-independent and survive the failure of Prop 8: the finality criterion (Ch. 12), Thm 1, the six-mode coverage, Thm 10, the minimalities of the basis, the alphabet and the IC feature set, Inv-6 and Inv-8; sabotage merely instantiates an FM form. The other guarantees are adversarial-conditional, each resting on one of three assumptions with a cheap resolution and an import replacing it:

| Dropped | Attack → locus | Import |
|---|---|---|
| Prop 8 | collusion → the verifier ≠ executor seam; criteria-lowering; reopen-griefing → R′, bounded by max_reopens | a bond restoring Prop 8's inequality at the exposure; against collusion, a quorum |
| single-Del | forged Del / Sybil | crypto-identity (the FSM rejects a signal whose source is not the Del it answers for, sound only as far as identity is authenticated); permissionless, Sybil resistance |
| single-sequencer | history fork → log canonicity | BFT-SMR or fork choice (PBFT or Nakamoto) agreeing one canonical log |

Each incentive-surface import reduces to Prop 8 by restoring Prop 8's inequality as a cost gradient — a bond forfeited wherever in the cone detection fires, priced at the exposure (§16.8) where p alone is too small, a quorum multiplying the verifiers a collusion must co-opt; the identity and ordering imports are its preconditions, which the substrate supplies in the permissioned scope. *(derived)*

A colluding false PASS at node i must still pass every honest validator in i's validation cone — the AND-parent's substantive integration criterion and the Dep consumers — and survives with probability 1 − its exposure (§16.8), so the incentivized core localizes to the **sensitivity-sparse frontier** *(derived)*: the nodes whose validation cone carries few validators whose criteria distinguish the corruption *(defined)* — non-constructive, p_j being a faithfulness quantity Lemma 1 forbids reading off the apparatus.

Criteria immutability (Inv-1) imports only the weighting asymmetry, a prediction confirming more strongly; adversarial criteria-lowering before settlement remains a named residue of the threat model.

R′'s cheap resolution of who may reverse and of history canonicity rests on the same three assumptions *(derived)*. A consumer's read-and-build that locks the node finally before its issuer reopens it (§12.14) leaves the false PASS exposed through the consumer's own validation cone.

### 16.16. Decomposition quality

**Prop 9 (decomposition quality).** GFSO improves decomposition quality through four independent mechanisms, each under the premises of its source result, the failure of one not cancelling the rest. *(derived)*

**Mechanism 1 (from Prop 3).** Decomposition is a decision under incomplete information about the task's causal structure; the protocol adds the history of analogous tasks, q_D's patterns and the causes of past FAILs, a set the agent's own experience garbles, so the decision is weakly better, strictly where the added records inform under the (ii)-faithfulness premise. *(derived)*

**Mechanism 2 (from Prop 7's Cor 2).** A split passes a cascade of stages ending in the CHECK battery (STD-4), each a gain γᵢ < 1 on the errors it reaches, so γ_total ≤ ∏ᵢ γᵢ: strictly below any single factor on errors every stage reaches, over the reaching stages otherwise; a defect is found before execution, and a wall no stage reaches passes undamped (γ = 1), met only at contact. *(derived)* As Prop 7 does, it rests on the correctness of D and the (ii)-faithfulness premise.

**Mechanism 3 (from Prop 4).** The protocol excludes splits without subtask criteria (A1), without the register (STD-1), without coverage of the parent's criteria (CHECK-1), or with a declared risk neither mitigated nor accepted (CHECK-5), each dominated as Prop 4 states: a type system for decompositions. *(derived)*

**Mechanism 4 (from Prop 6).** A q_D violation is the recorded pattern of a refuted composition claim (§15.4) with authorship, context and broken criteria, its cause read where the log records one; by Prop 6 and the Blackwell equivalence (§16.1) a rational agent learning on it makes recommendations of non-decreasing quality. *(derived)*

### 16.17. Applicability

Applicability is read off the model's conditions. A task is inside the model on Ch. 2's condition: a creative or research task with no verifiable outcome lies outside, by ¬A1, one whose decomposition alone is unknown inside, the protocol carrying it by deferral (FM-6's remedy, Ch. 8). The constraints pay where Prop 4's threshold holds, the formalization overhead counted in its cost c (§16.3), which a very small team can miss, and Prop 8 rests on its inequality (§16.11), which a punishment culture breaks by raising the cost of an honest signal. That GFSO pays in hierarchies of three or more levels whose outcomes depend on planning quality is a forecast, unmeasured.

---

## 17. The AI layer

### 17.1. Necessity from capacity

ℐ(α, t) (Ch. 16) accumulates: the log grows and nothing is deleted from it, Prop 6 guaranteeing the non-degradation of content, not the growth of volume. *(derived)* Human cognitive capacity being finite [5], a nontrivial organization reaches some t* at which |ℐ(α, t*)| exceeds any human's capacity. *(by citation)* Splitting ℐ among humans, A2's move, does not recover it: interpreting ℐ has no finite pass/fail, so it lies outside A1, and no composition law (Thm 1) reassembles the parts' readings into the whole's. *(derived)*

**One-context reading.** A pattern across branches is read only by a processor that holds them together. *(premise)*

Past t* the information exists but is not processed: Prop 6's dominance still holds of the trace, and its payoff, which needs a processor, goes vacuous. *(derived)* **Capacity necessity:** a processor whose capacity in one context grows with |ℐ| is necessary — an AI layer. *(derived)*

### 17.2. Two components

Processing information about the composition formula V(parent) = ⊗({V(tⱼ)}) (Thm 1) requires inference. Inference has three types — deduction, induction, abduction [19] — and no further kind: a completeness claim over an undelimited space, carried by no Lean axiom and conditioning this one result *(covering axiom; by citation)*. Induction without semantic understanding is counting, which self-measurement (Thm 10) already does, and meaningful induction needs abduction, so the AI layer has two components, not three *(derived; complete at the covering grade)*.

**Definition (Solver).** The deduction component: it derives consequences from rules — CHECK-7 and CHECK-8 by constraint propagation and SMT — a deterministic algorithm, sound and complete for decidable theories, at Chollet Level 0, needing no generalization. *(defined)*

**Definition (LLM).** The induction-and-abduction component: it turns context into understanding, recommendations and semantic checks — decomposition assistant, detection of unaccounted factors, interpretation of Q's patterns, semantic consistency. *(defined)* It is formalized as in-context learning read as implicit Bayesian inference estimating P(recommendation | the log) [22]. *(by citation)* At sufficient capacity an LLM implements learning algorithms in its forward pass [23], which supports the formalism. *(by citation)*

**The LLM premise.** The LLM processes the log Bayes-rationally, with a correct model of its signals and capacity ≥ |ℐ(α, t)| at every t, under which clause alone it is the processor capacity necessity asks for; prior quality is a condition, as D's correctness is for Thm 1. *(premise)* It is required at Chollet Level ≥ 2 (General Emerging+ [25]): it adapts to the organization's task distribution from the log even outside its training distribution, a generalization more training data does not buy [24]. *(by citation)*

### 17.3. Cross-impossibility

The Solver cannot reason semantically, having no domain axioms; the LLM, an estimator of P(recommendation | the log), guarantees no formal check at zero error probability. *(derived)*

### 17.4. Integration into the protocol

| Protocol point | Solver | LLM |
|---|---|---|
| ASSIGN | a revision's guards (Ch. 12); a first ASSIGN departing from the draft re-admits the split | propose criteria and the pre-filled accepted risks; warn of risks |
| Decomposition | the battery at admission: the Syntactic level, and CHECK-7, CHECK-8 as far as Ch. 9's rule runs them | propose a split; find forgotten Deps and unaccounted factors |
| OFFERED, EXECUTING, REWORKING | — | help understand the spec; suggest a CHALLENGE |
| VALIDATING | auto-check the machine-verifiable criteria | flag an unresolved Dep |
| Continuous | — | interpret Q's patterns; check semantic consistency |

Beyond CHECK-8 (Ch. 9) and CHALLENGE at contact (q_T, Ch. 15), FM-2's semantic residual is guarded by LLM review, which can also name a requirement no criterion writes (§8.3), as any agent reading it does: a guard of the agent's Ŝ-content, not of the apparatus.

On the worked example (Ch. 14), the LLM's move at decomposition is recommending the external API's change, non-producible (§11.3), into ACCEPTED_RISKS with an invalidation condition, the producible alternative being a mitigation child (an adapter, a version pin).

### 17.5. The feedback loop

**Definition (the loop).** The protocol generates the log and its projection 𝒢; both feed the Solver and the LLM, which propose criteria and splits and run the checks back into the protocol; Q is a readout of the log (Thm 10) the LLM interprets. *(defined)*

LLM(t+1) ≥ LLM(t) by Blackwell inside the LLM: more data in context, a sharper posterior, under the LLM premise. *(derived)*

The loop runs at fixed adherence. That the LLM, lowering the protocol's overhead, also raises α is an expectation about adherence dynamics: where it holds every α-monotone guarantee gains, and none needs it.

### 17.6. The AI layer in the guarantees

The LLM grounds the rationality premise the dominance is read through without changing ≥_B — so bounded rationality plus the LLM approximates rationality. *(derived)* For Universal Improvement's bounded-rational agent below c/Δ this is a mitigation moving him toward the rational arm, not a third mechanism; the LLM also reduces the formalization overhead, the assistant proposing and the human approving.

The weak forms of Ch. 16 hold of any added signal for a processor with a correct model of it. *(derived)* In Prop 9 the LLM joins the protocol in bringing the records of Mechanism 1 to the decomposer, is a stage of Mechanism 2's cascade — agent → LLM → Solver + CHECK battery — and can be Mechanism 4's rational learner, Mechanism 4 then carrying the LLM premise.

### 17.7. The safety net

An LLM error with a formal signature is caught by the protocol: a bad recommendation gives a bad D that q_D records, a bad semantic check draws the executor's CHALLENGE, and what is caught enters the log and sharpens the posterior. *(derived)* A domain-wrong but formally clean D — integration cases (i) and (ii) (§8.7) — is not caught by the apparatus; only contact grounds it. *(derived)*

### 17.8. Who is who

The AI layer's necessity is capacity — a processor, because ℐ outgrows a human; the agent's (Ch. 4) is provenance — a carrier-agent, because the apparatus generates no domain content for Ŝ (Lemma 1). The two lie on different axes and add. *(derived)* The Solver is pure apparatus, S-independent deduction; the LLM and the human are agents in Ch. 4's sense, carriers of learned Ŝ-content mounted on the protocol interface. *(derived)* The protocol bounds the worst case; the LLM improves the average case.

### 17.9. Inseparability

**Result (inseparability).** The pillars are two, the protocol with its self-measurement and the AI layer: removing the protocol breaks the loop outright, removing the AI layer breaks it past t*, where what Prop 6 guarantees goes unread. *(derived)* Below t* the loop runs without the AI layer, bounded by human capacity. Self-measurement is not removable apart from the protocol: its queries run at any time; leaving them unrun forgoes a readout, not the loop, and under the LLM premise the LLM can compute Q from the log.

---

## 18. Methodology

### 18.1. The two mechanisms

A discipline of producing and executing decompositions follows from the ontology: the agent-free ontology of Ch. 5 forces its methodology of stop-and-replan and verify-vs-explore, and the coarse cut FORM ⊕ FAITHFULNESS (Ch. 3) forces its two mechanisms. Three facts force them *(derived)*:

- **(F1)** the two error classes have orthogonal epistemic access;
- **(F2)** error compounds down the tree, multiplicatively in Prop 7's model (Ch. 16);
- **(F3)** discharging FORM has a nonzero cost `c_check`, graded by level (Ch. 9).

**Mechanism 1 — front-load FORM** *(derived)*. FORM is discharged on the **executable segment** — the part of the plan whose leaves are within their holders' κ (Ch. 3) and can be issued now *(defined)* — to the level verify-vs-explore sets (Ch. 9). It dominates strictly only as `c_check → 0`; above that it is the verify-vs-explore tradeoff (Ch. 9).

**Mechanism 2 — stop, mark, re-derive** *(derived)*. At a wall — a contact verdict `e ∈ Ŝ∖S` — STOP, breaking the cascade; MARK locally, the locality coming from the EXTERNALIZE form (Ch. 4); RE-DERIVE, re-running the FORM check over the updated Ŝ; only then proceed.

There are exactly two mechanisms, one per point of access in time *(derived)*: before acting, over Ŝ, only FORM is reachable; at contact FAITHFULNESS first shows, and FORM is re-run over the updated map, the record's departures from AND (Ch. 7) flagging where a verdict or an edge may be denied. A sharper instrument at either point — a cheaper check, a more sensitive validator, γ (Ch. 16) — improves its mechanism. The LLM lowers the cost of running the four mechanisms of Ch. 16, how often being the verify-vs-explore question; those mechanisms improve the material of decomposition, and the discipline of producing and executing it is this chapter's.

### 18.2. Optimality under a named cost model

**The cost model** *(premise)*: `c_check` graded by level (Ch. 9); error compounding as Prop 7 models it — uniform Λ, linear, feedforward (Ch. 16); and the marginal premise that, with the level, the marginal `c_check` does not fall and the marginal prevented risk does not rise. A policy's realized cost is `c_check + E_FORM + E_FAITH`, `E_FORM` and `E_FAITH` being the FORM and FAITHFULNESS errors it leaves *(defined)*.

Under this model front-loaded FORM is optimal in its depth and stop-and-replan dominant at every revealed wall: the discipline minimizes the knowable part of the realized cost — `c_check + E_FORM` by (a), and by (b) the guaranteed bound on `E_FAITH` for the walls S fixes — the realized `E_FAITH` being known only at contact (Lemma 1, Ch. 3) *(derived)*.

- **(a)** Under the marginal premise §9.9's rule minimizes `c_check + E_FORM` *(derived)*.
- **(b)** At a wall a written, sensitive criterion reveals, stopping replaces the local gain Λ by Λ·γ. With the walls fixed by S, whatever the policy, where they are revealed at m of the n levels on a path (m ≤ n), the guaranteed bound on `E_FAITH` along it falls from Λⁿ to Λⁿ·γᵐ, and to (Λ·γ)ⁿ where every level reveals one (Prop 7, Corollary 3, Ch. 16). Where no criterion reveals the wall (the integration residue, Ch. 8) nothing stops and γ = 1 *(derived)*.

Stop-mark-re-derive is the temporal realization of Prop 7's bound, giving the gain's magnitude; the correction's locality is §7.3's. `E_FAITH` has its runtime record in q_D's refuted composition claims and q_V's later fails (Ch. 15).

The discipline leaves free the speed, the route among faithful decompositions (Ch. 4), and the front-load granularity above the executable-segment floor.

---

## 19. Positioning

### 19.1. The problem and what GFSO is not

In a hierarchy every assignment is negotiated and every acceptance is a subjective assessment, with no standard for the transaction; the control dilemma — interfere, or learn of a problem late — lacks a third mode, "trust, but see".

GFSO tracks decisions — who decomposed, into what, why, under which criteria — and manages the decision process; its AI layer joins an LLM to the protocol, an LLM without a protocol being advice without context and a protocol without an LLM bureaucracy. The work is self-contained: its results rest on the classics directly, through no intermediate formalism.

### 19.2. The [known]/[GFSO] ratio

An element is tagged [known] where existing theory supplies it and [GFSO] where the canon does. GFSO absorbs standard planning as one sub-step — EXPAND, search over Ŝ, which is Link-3 (Ch. 5) — rewritten in its own formalism, so planning ⊂ GFSO. The sub-step reuses textbook planning and control (STRIPS, MDP, HTN [12], A*, MPC, model-based RL) for the state space, the type of the S/Ŝ relation, plan-as-search, hierarchical recursion, replan-on-mismatch and model ≠ world *(by citation)*. EXPAND is [known]; CONSTRUCT-Ŝ (Ch. 4) is [known] as library reuse and [known]-as-heuristic as the bare positing of a new seam, which LLM planners perform corpus-free and guarantee-free, Lemma 1 (Ch. 3) yielding only its non-derivability by the apparatus. The continuous substrate and the quantitative theory of maintenance (Ch. 6) are absorbed sub-steps, not the delta.

Around the planning sub-step GFSO supplies what planning lacks: the faithfulness ontology (Ch. 3), the failure taxonomy of Ŝ∖S (Ch. 8), the composition law (Thm 1, Ch. 7), the derived agent necessity (Ch. 4) and the methodology of Ch. 18.

The delta of new formal machinery is narrow:

1. **Joint sufficiency** `(t,{tⱼ}) ∈ S`: AND-soundness's mandatory writing-out of the integration implication (§6.5).
2. **The failure root Ŝ∖S** (Ch. 3), with Thm 1's form/substance split (§7.3) and the carriage of a denied integration (§8.7).
3. **Constitutivity.** The S/Ŝ split is constitutive of directed action by modality plus singularity: the pair is Link-2 ⊕ Link-5 of a chain none of whose members is removable (Ch. 5), and rival estimates are tested through one seam against one ontic S (SINGLE-SEAM, Ch. 3) with one failure locus and a binary verdict, so a defect is a wall, not a dissimilarity. This separates GFSO from an error minimized around a privileged true model (MPC, model-based RL) and from model-based philosophy of science [52, 53, 54], whose models are instruments answering to functional adequacy or graded similarity *(by citation)*.
4. **Agent-free recursion**: contact homogeneous modulo delay, the agent a scope-bundle (Ch. 4).
5. **The EXTERNALIZE form** (Ch. 4).

Method learning does not subsume the kernel *(by citation)*: ABSTRIPS [32] re-grades given predicates, HTN-MAKER [33] learns seams with φ given as annotation, goal regression [34] yields preimages of existing operators, HRL discovery [61] grades intermediates by return, and LLM decomposition [60] posits seams heuristically — none yields a new A1-seam with a falsifiable φ graded by `Ŝ_used ⊆ S`. So GFSO's single remainder of generation is the EXTERNALIZE form with the faithfulness grading.

### 19.3. The value: making-explicit

GFSO's primary value is making-explicit: moving decomposition out of an agent's private, unexamined intuition into one axiom-derived, consistency-checkable, faithfulness-graded system, mandatory at every level, so that a plan is a set of pre-registered, separately falsifiable claims about the chaining, each with a truth-maker in S and a defined falsifier-contact (Ch. 4) *(defined)*.

The ratio of §19.2 measures the machinery's novelty, not the value: narrow as machinery and large as a universalized checkable discipline, the kernel and the value are one object.

The frame earns its keep only through three dividends and claims no value beyond them:

1. **Coverage against the real joints** *(derived)*. Every requirement of the goal is a written criterion with a responsible child, a written accepted risk (STD-1, Ch. 9) or an exclusion no goal criterion demands, so an omission is a falsifiable absence and a seam cut off the joints is refuted at contact (FM-1.e, §8.3); integration cases (i) and (ii) (§8.7) lie beyond it.
2. **Localization and attribution**: a failure pins the false belief and its owner (Ch. 4).
3. **Verify-vs-explore by stakes** (Ch. 9): no over-planning of the cheap-reversible, no under-planning of the catastrophic.

For a fully self-assigned agent, which has no seam, what remains of GFSO (Ch. 10) is making-explicit, the log included.

The value rests on typical working methodologies being assemblies of past plans, usually never checked for internal consistency *(premise)*. The generation method is an unaided search proposal checked by GFSO's form audit (STD-4, Ch. 9), iterated *(defined)*.

### 19.4. Scrum embedded: restriction and relaxation

Scrum [27] embeds semantically into GFSO's structure: it restricts freedoms GFSO allows and relaxes requirements GFSO keeps, so a Scrum run maps into GFSO's vocabulary without being an admissible GFSO run as it stands *(derived)*. The differences:

- depth(D) ≤ 2, an item above its holder's κ being a leaf in the image (the leaf test, Ch. 3, relaxed);
- ACCEPTED_RISKS = ∅ (the register and CHECK-4 relaxed, Ch. 9);
- CHECK-7 and CHECK-8 not enforced;
- the audit trail informal (Thm 11, Ch. 11);
- deadlines a uniform sprint length;
- the vertical deadline rule, child < parent (form item (6), Ch. 4), unmet;
- CHECK-3's strict order unmet between two dependent items of one sprint.

| Scrum | GFSO |
|---|---|
| Product Owner | the issuer at the top T |
| Scrum Master | an executor whose T is ensuring protocol compliance |
| Developers | executors at task level |
| Product Goal | the spec at the top T |
| Sprint Goal | the aggregated spec at the sprint-level T |
| Sprint | a T with deadline = the sprint length |
| Product Backlog | the set of pending children under the top T |
| Sprint Backlog | the batch of Ts chosen for the current sprint |
| Sprint Planning | ASSIGN, batched |
| Daily Scrum | an operational cadence for continuous V re-check |
| Sprint Review | DELIVER + V |
| Sprint Retrospective | a qualitative review of the q-metrics |
| Increment | the output of DELIVER |
| Definition of Done | criteria, typically weak |
| User Story | a spec template for the weak-A1 regime |
| Story points | a specific estimation scheme |
| Velocity | empirical throughput, outside Q |
| Burndown chart | a visualization of the audit trail |
| Empiricism (three pillars) | the audit trail + continuous V + the CHALLENGE cycle |
| Self-organizing team | execution-time decomposition by the executor, informal and off the graph below depth 2 |
| No mid-sprint changes | spec immutability between ASSIGN and DELIVER |

Every Scrum component examined is a direct mapping, an implementation choice, a restriction or a relaxation — a mapping exhibited constructively, not an exhaustion theorem; "A1 weak" means criteria articulated late, not ¬A1.

The differences are justified where A2 is marginal, A1 weak, the team small, errors cheap and compliance low; they break where A2 or A1 is strong, teams coordinate formally, an audit trail is mandated or stakes are high, and there Scrum's failure modes are GFSO failure modes (Ch. 8) the omitted checks leave unaddressed. Scrum, worked out in full, postulates part of the discipline of §19.3; GFSO derives it.

**The rule of relaxation:** a neighbour that embeds into GFSO's structure while leaving unwritten what GFSO requires written is a relaxation of GFSO; Scrum is one.

### 19.5. Adaptive stratification by horizon

In a GFSO system of depth h with deadline coherence along D, under the premises of steps 2–5, the expected frequency of CHALLENGE (Ch. 11) strictly increases with depth: E[freq_challenge(k)] < E[freq_challenge(k+1)] *(derived)*.

1. Deadline coherence along D — form item (6), child < parent (Ch. 4) — makes the horizon strictly decrease with depth.
2. On a shorter horizon criteria are more concrete; A1 bounds the time a check takes, not how abstract its predicate is — concreteness *(premise)*.
3. The more concrete the criteria, the more they depend on the exact state of the environment — sensitivity *(premise)*.
4. The environment changes at a rate r independent of level — stationarity, empirical *(premise)*; a change registers as a divergence from a node's criteria with a probability s_k that grows with their concreteness (step 3), hence strictly with depth (step 2).
5. Divergences surface as spec defects that CHALLENGE reports in a level-independent share ρ, a change that leaves the criteria sound and stops the work being a BLOCK, FM-5 (Ch. 8); so E[freq_challenge(k)] = ρ · r · s_k — routing *(premise)*.
6. Hence freq_challenge increases strictly with depth, as s_k does. ∎

**Corollary.** Upper levels need stable abstract criteria and rare CHALLENGE cycles, lower levels concrete criteria and frequent ones; "long-range plans are stable, operational ones change daily" is a consequence of GFSO under the four premises, not a separate agile principle.

### 19.6. Decidability and severity

A1(i) fixes that a verdict is obtainable, not that it discriminates (§1.3, §8.4); severity is a separate axis.

`Probe(t)`, the probes a passed node t survived — its own criterion, the integration implication (Ch. 6), recursively the children's — is a set of decidable discriminators; `t ⪰_dom t′` iff `Probe(t) ⊇ Probe(t′)` over the non-redundant probes *(defined)*. `⪰_dom` is reflexive, transitive and antisymmetric on probe-sets for every probe-set, by induction and axiom-free (`Grading.dom_refl_all`, `dom_trans_all`, `dom_antisymm_all`) — a preorder on nodes and a partial order on probe-sets *(machine-checked)*.

Only nested probe-sets compare, so no probe count yields severity: `⪰_dom` is the skeleton severity must respect, partial and not cardinal, with no value or threshold *(derived)*. On a fixed tree it runs largely with ancestry and rival decompositions of one goal stay unordered; hence triage orders by the dependency cone (Ch. 15). Its severity reading assumes probe independence, whose surrogate is structural scope-disjointness, so under correlated errors a ⊇-superset need not be the more probative, while the relation itself is untouched *(premise)*.

Severity needs a discordance ordering and a measure. A1 supplies only the two-point ordering and no measure, and over it severity equals `SEV = 1 − sup P(pass | ·)` over the composite goal-false region — the worst-case power, the complement of the false-PASS rate; Mayo's severity [39] is strictly finer in general, coinciding at the cutoff *(derived)*. A finer ordering would live on the result space, which no apparatus object carries, any surplus above pass/fail being decision-irrelevant under Inf-B (Ch. 7), a conditional claim; so the measure is contingently absent and the finer ordering unrepresented *(derived)*. Where no probability model is importable the cardinal is undefined and `⪰_dom` still orders; q_V is a runtime frequency, not severity.

Where an independent probe corpus written from the contract exhibits a divergence in a PASSed artifact x, re-running the validator on x independently of the selecting pass estimates `P(pass | x)`, a lower bound on `1 − SEV` at that node — `SEV = 0` there under a deterministic validator; the corpus's pass fraction and q_V's later-fail term are other quantities *(derived)*.

The one import-in-principle layer is graded confirmation — cardinal error statistics, predictivism, consilience-as-support, Lakatos's verdict. GFSO is pass/fail (|L| = 2, Ch. 7), grades by faithfulness, not credence, accumulates no support, and its skeleton is probability-free from A1 + A2.

### 19.7. Science : nature = GFSO : any directed action

The GFSO core — falsifiability checked by contact — is the formal content of the scientific method's falsificationist core: prohibition, pre-registration, decidability; its graded-confirmation layer (§19.6) is imported.

Science is the method over one domain held implicitly — domain = nature, with S/Ŝ, φ and contact implicit. GFSO is the same method with the theory-model explicit and mandatory and the domain lifted to any directed action (Ch. 1):

**science : nature = GFSO : any directed action.**

Science is a relaxation of GFSO by §19.4's rule, leaving implicit what GFSO requires written. The mapping is a structural positioning *(defined)*.

The core is analytic: A1 was built as a falsifiability criterion, so falsifiability → A1, hypothesis → φ (Ch. 4) and falsification → contact could not fail to be found *(derived)*. The mapping's single substantive addition is decidability, the rest of its substance the unfoldings and the generalization.

A1 [40] demarcates the theory's own domain, which A1 ∧ A2 delimit (Ch. 2), and there A1(i) is Contact's signature (§3.7). The critique of falsifiability as a single criterion demarcating science — holism, the statistical case, Laudan [41], Pigliucci–Boudry's multi-criterial cluster [42] *(by citation)* — retires the science/non-science partition, another object, and leaves this demarcation standing.

The surviving Popperian core is inherited: the prohibition structure — a claim forbidding no outcome is empty — and, from the predesignation/use-novelty line, pre-registration, which Inv-1 carries (Ch. 12).

A probabilistic hypothesis acquires a decidable verdict once a rejection rule is fixed: the residual rule↔hypothesis gap is the clause-(ii) gap, FM-3, and the rule's error rate on the passing branch — type II or type I by the side the goal-claim sits on — is that criterion's false-PASS probability at that point of the goal-false region. Statistical testing thus instantiates the criterion↔truth split, only its calibration imported.

GFSO makes explicit what science carries implicitly:

- **composition** — a tree of hypotheses with joint-sufficiency chainings and a separately falsifiable, node-attributable integration implication per node (Thm 1, Ch. 7): the Duhem–Quine bundle [57] made explicit, "which premise is false" having the structure of the tree + Dep;
- **attribution** of a refutation to the node with the broken compositional claim (Ch. 4), the holism recursing inside a node (Lemma 2, Ch. 3);
- **the mandatory ACCEPTED_RISKS register** with invalidation conditions (Ch. 9) — the auxiliary assumptions written out;
- **the theory-model** — S/Ŝ, faithfulness, the necessity of contact (Ch. 3).

| Notion | Where in GFSO | Status |
|---|---|---|
| Falsifiability [40] | A1 clause (i), the decidability conjunct; prohibition rides on clause (ii) | as above; mechanical only on a criterion presented with its decision procedure — whether a domain admits one is decided by neither clause (Lemma 1) |
| Holism [57] | composition, attribution and the register (above): the bundle finitely enumerated per node | a structural answer |
| Underdetermination [57] | the goal underdetermines the decomposition (Ch. 4; Lemma 1) | present |
| Unification / consilience [58] | the minimal non-redundant `Ŝ_used` — the structural rank — coinciding typically, not identically, with low faithfulness risk | unification present; the confirmational component imported |
| Research programmes [55] | correction dynamics = backward attribution + locality + Λ·γ damping (loop-gain stability, not growth of empirical content); hard core / belt = a partition re-derived by STOP → MARK → RE-DERIVE, the core kept only while un-attributed | the dynamics a structural analogue; the progressive/degenerating verdict imported |

Lakatos's verdict is imported, deriving it from the damping double-counting novelty. The core/belt analogue keeps an upper node only while it is un-attributed, where Lakatos protects the core by decision.

Replication as an operation is falsification by an independent agent, carried by contact + verifier ≠ executor (Ch. 10). Institutional enforcement is an institution's act and aesthetics a virtue of choice among candidates, both outside the method.

The mapping presupposes *(premise)*: (i) that science's method is covered only where the outcome is decidable (A1), understanding as a non-instrumental goal lying outside it; (ii) a stable exogenous S and a fixed A1 standard — the rational-reconstruction reading against strong Kuhnian incommensurability [56], rival Ŝ frames commensurable through S (SINGLE-SEAM, Ch. 3).

GFSO applied to itself checks its own consistency, a soft corroboration of the frame.

Each element of the method — prediction and accommodation, novel facts, consilience, explanation and IBE, measurement, replication, theory-ladenness, research programmes and paradigms, and causal discovery — is captured by existing structure — theory-ladenness by SINGLE-SEAM, explanation by composition plus the Semantic/Pragmatic gap (Ch. 9), Lakatos's dynamics by backward attribution + Λ·γ — or falls into the causal remainder at the Pragmatic level, into the graded-confirmation layer, or outside A1 — a structural placement, as the mapping is.

### 19.8. Related work

Planning was formalized for machines as optimization over a given model, not as a universal axiom-derived discipline of consistency + faithfulness for any agent at any level; domain neighbours — formal methods, TLA+, design-by-contract [13] — each carry part of it and leave the register, the per-decision log and the seam unwritten, so each is, by §19.4's rule, a relaxation.

- Blackwell [1] and Blackwell–Girshick [2] ground Prop 3; Marschak–Radner's team decision theory [7] frames GFSO as improving the team's information structure.
- Hurwicz [3] and Myerson [4] ground Prop 8 (§16.11).
- Simon [5] grounds Prop 4; A2 formalizes Simon's near-decomposability [6].
- The small-gain theorem [9, 10] grounds the stability of the upward feedback beside Prop 7's cascade, a hierarchy as a chain of amplification and damping (§16.7).
- The Good Regulator Theorem [36] is a precedent for half of Lemma 1 — S is not supplied by the apparatus and enters only through contact; GFSO adds the primitive basis of directed action (Ch. 2), the composition law and the failure taxonomy, complete as a basis modulo CA1 (Ch. 8).
- Petri and workflow nets [11, 17]: the FSM (Ch. 12) is a workflow pattern; they carry no quality metrics.
- HTN [12] shares `D : T → 𝒫(T)` but searches for a plan, whereas GFSO validates one with a runtime protocol.
- Contract-based design [13, 14]: issuer/executor ≈ assume/guarantee, criteria ≈ postconditions; GFSO adds, for organizations, CHALLENGE, BLOCK and self-measurement.
- Goal-oriented requirements engineering [15, 16] has goal trees and criteria; GFSO is the full cycle with a runtime protocol and metrics.
- Empirical failure taxonomies of agentic systems [37] cluster observed failures into orthogonal categories; GFSO's taxonomy is an analytically proved complete basis modulo CA1, the coincidence of form corroborating the categories' naturalness, the novelty being the completeness result, not the list.
- GFSO formalizes the unit operational frameworks leave undefined, the act of task transfer (Ch. 11); ISO, CMMI and Six Sigma work on top, none providing a transaction standard with self-measurement. Non-adherence inside the protocol being observable from inside as a graph event (Ch. 16) separates GFSO from every comparator.

| | Kanban | Scrum | CMMI | Six Sigma | ISO 9001 | GFSO |
|---|---|---|---|---|---|---|
| Unit | ticket | user story | maturity level | defect rate | documented procedure | the act of decomposition |
| Acceptance | "done" | DoD (weak) | assessment | σ-bound | audit | binary V on criteria |
| Decomposition depth | flat | ≤ 2 | org-level | n/a | n/a | unbounded (a forest) |
| Composition theorem | — | — | — | — | — | V(p) = AND(V(c)) |
| Failure taxonomy | — | — | — | — | — | 6 FM, complete as a basis modulo CA1 |
| Quality | not measured | velocity | maturity score | statistical | conformance | Q = (q_T, q_D, q_V, q_Dep, q_Del) |
| Scope | team | team | organization | repeating processes | procedures | every decision |
| Formal foundation | none | none | none | statistical | conformance | A1 ∧ A2 + minimality |

---

## 20. Limits and closure

### 20.1. The boundary criterion

An item lies **around** the canon when its answer would change no claim of the canon, whatever would close it — an imported theory (a probability model over outcomes, a utility model over actors, an optimal mechanism) or a further theorem *(defined)*. A requirement the canon states whose satisfaction is settled by a check an implementation adds or a measurement a deployment makes is **not yet built** while that check or measurement is missing *(defined)*.

The four forms of a boundary's impossibility argument *(defined)*:

- **Lemma 1 form**: a fact about S that no discipline certifies a priori — the apparatus does not define it (Lemma 1, Ch. 3) and even contact need not reach it (integration case (ii), Ch. 8); its measurement after contact is a requirement not yet measured, a different item.
- **Lemma 2 form**: every declarative closure is a fresh instance of the same question (Lemma 2, Ch. 3).
- **Covering form**: completeness over an undelimited space of candidates, which no case split inside the theory reaches; the covering axioms CA-Links (Ch. 5), CA1 (Ch. 8) and CA-Morris (Ch. 9), with |Act| = 2 (Ch. 7) and the AI layer's covering of the inference types (Ch. 17), are the canon's placements against it, each at its own argument's grade.
- **Domain form**: the goal lies outside the model (Ch. 2), which the axiom's own clause shows (Ch. 1).

What earns a boundary is the argument; "we looked and did not find", "known to be hard" and "not yet built" do not. Closing an item that meets the criterion is the mistake "incomplete by design, therefore complete" (Ch. 4). The criterion keeps the framework falsifiable in aggregate: without it any failure could be filed as a mode, a boundary or outside the model, and the taxonomy would close itself by fiat *(derived)*.

The adopted design decisions (Ch. 0) are choices the canon makes, neither boundaries, nor items around it, nor requirements not yet built. The named exceptions of IC (Ch. 16) are not boundaries: the canon shows no non-derivability of any of them, and most are disclosed costs of the adopted choices and of what follows from them — the issuer role following a Del change, terminality's recovery by re-issuing, the re-presentation rule.

### 20.2. The Pragmatic-level boundary

Level-2 causal correctness — the Pragmatic level (Ch. 9), securing Thm 1's conditions against the real domain (§7.3) — is the permanent boundary of §3.5 — Lemma 1 + Lemma 2 forms *(boundary)*.

Underivable from A1 + A2 (Lemma 1), it is closed by no declarative extension, each a fresh instance (Lemma 2) *(derived)*. Keeping the (ii)-faithfulness discipline is the agent's clause-(ii) task (Ch. 4), and its violation falls in this boundary.

The approach runs through the empirically learned — LLM induction and abduction (Ch. 17), domain ontologies under verification, q_D as runtime convergence (Ch. 15), institutional learning (Prop 6, Ch. 16) — which lies with the agents and the records the apparatus keeps, and is no closure.

The Pragmatic level's claim is interventionist [43, 44]. The composition edge `(t,{tⱼ}) ∈ S` (Ch. 6) is a conjunctive-intervention counterfactual whose do-reading is licensed by the children being completed (Link-4, Ch. 5), not observed; where a child's criterion-pass is not domain-correct it degrades to a see-reading over verdicts and inherits the clause-(ii)/FM-3 residue (Lemma 1). Its presupposition (a), modularity — a conjunctive intervention is well-posed only read surgically — is declared, not assumed — by Dep and CHECK-8 (Ch. 9), an undeclared coupling read by §8.6 and an unwritten integration criterion being FM-1.f — its residue this boundary. Its presupposition (b), scale: the claim lifts from `≈_G` to `M/∼_G` only where `≈_G` is a bisimulation (Ch. 6), which the canon does not certify. Its presupposition (c), the invariance range, is the register's declared range of perturbations (§9.2). A separator (Ch. 6) is the claim's structural counterpart, a reachability cut, not a d-separator; both are shadows of `ẋ = f(x,u)`, whose handle `u` the intervention variable formalizes without being it, and on `≈_G` `u` is not a variable. So formulation and verification separate: the Pragmatic level is a claim well-posed relative to a fixed carve, of which only verification from inside is unavailable *(derived)*. do-calculus computes from a given graph, but here the graph is Ŝ, posited, not given; the counter-move that bites is causal discovery, an instance of the approach vector, which fails because it presupposes the carve (CONSTRUCT-Ŝ, Ch. 4).

In the science mapping (§19.7), `⋀children ⟹ parent` is the deductive skeleton — the formal-entailment check is D-N validity — and the causal surplus D-N cannot draw [59] is the Semantic↔Pragmatic gap, an interventionist claim statable in that currency and not verifiable from inside: the skeleton is inherited, the causal asymmetry is this boundary.

**Face on the value — the faithfulness residue** (§3.5) — Lemma 1 form *(boundary)*: a check forbidding something on the map (§9.6) that cannot discriminate the divergence, silent even at contact — integration case (ii) (§8.7), its false PASS domain-silent, FM-3's as §8.4 reads it. An FM-1.f no Q term reads and §17.7's clean D fall into the Pragmatic-level boundary. Mayo's severity [39] reads qualitatively as FM-3 and its cardinal `SEV` (§19.6) is an import of this genus; Prop 8 at zero exposure, where a colluding false PASS survives on the sensitivity-sparse frontier (§16.15), is this face; a near-0 price under positive exposure is the threshold not cleared.

**Face on the production of a split — decomposition-method quality, its faithfulness half** — Lemma 1 form *(boundary)*. No a-priori discipline certifies that a seam is faithful, a seam's faithfulness being the causal correctness of the split it cuts. How to invent a faithful seam is the layer EXTERNALIZE omits (§4.5). Of the residues Ch. 4 names, which slicing is faithful and a criterion's discrimination are this boundary's two faces. Generating a faithful seam is this face for science and GFSO alike: science has no theory certifying a hypothesis faithful before contact either.

The rest of generation separates into (a) the generation method (§19.3), not a logic of discovery; (b) form, the a-priori CHECK; (c) faithfulness, contact only, measured on execution, not derived. Discovery sits in (a); (b) and (c) are justification. What stays logic-free is the first positing of a concrete candidate joint for a genuinely new goal, the bare CONSTRUCT-Ŝ leap science has too; it is no boundary of its own, bare positing being [known]-as-heuristic and its lack of logic Reichenbach's [51] *(by citation)*.

The canonical scaffold localizes the leap without closing it: (1) cut at the joints (§6.7), a norm-target non-constructive but not vacuous, its ballast refuted at contact (FM-1.e, §8.3); (2) the form filter (Ch. 18); (3) the structural rank, faithfulness-agnostic (Ch. 4); (4) reuse of previously contacted joints. IBE is a selection move inside that logic-free throw, which the scaffold compresses; the interventionist literature itself names the choice of the variable set, the carve, an open problem.

### 20.3. The edge of the domain

`□◇A` recurrence and other non-finitely-decidable goals have a finite verdict in neither direction: they fail A1's decidability clause (Ch. 1) and lie outside the model (Ch. 2), a generator reaching them only as an attainment-reducing handle — domain form *(boundary)*. A standing goal's generator (§6.10) has a schedule that is an Ŝ-claim contact adjudicates only through the goal's own finite verdict. Understanding as a non-instrumental goal (§19.7) sits on this edge.

### 20.4. The machine-checked core

The formal skeleton is checked in Lean 4 on the language kernel, without mathlib, as an audit of the axiomatic surface: which claims are definitional, which irreducible, how many; it proves none of GFSO's substantive claims *(defined)*. `#print axioms` shows no axiom outside the whitelist and Lean's three foundations (`propext`, `Quot.sound`, `Classical.choice`), and the development uses no `opaque`, `sorryAx` or `native_decide`; "axiom-free" throughout the canon means no GFSO axiom *(defined)*. The whitelist has six entries: CA1, CA-Morris, CA-Links and three uninterpreted-predicate carriers (`correct`, `Directed`, `fullyKnown`) that the axioms quantify over and that localize the empirical residue.

Checked *(machine-checked)*:

- Thm 1 and its converse (`Compositionality.T1`, `T1_characterization`), and Thm 2 over the 16 operations (`AndUniqueness.and_unique`) (Ch. 7).
- |L| = 2, its source definitional, its defense `Binarity.L_forced_two` over act-surjectivity and act-injectivity.
- The 4+2 geometry of the six FMs, with one independence witness per mode over six free conditions; that the scenarios of Ch. 8 realize them is argued.
- `⪰_dom`'s order (§19.6), with witnesses of partiality and count-independence, a fixed-arity carrier and a negative control (`Grading.*`).
- The admissible sets of the machine (Ch. 12) are the object of `formal/GFSO/FsmCanon.lean`; on it and its conformance mirror `Fsm.lean` Lean checks Inv-6, Inv-1 (revision = re-ASSIGN), the cancellation handshake, Inv-8 with its control (`inv8_canon`, `inv8_mirror`, `control_inv8_fails_on_empty_escalated`), the 4/4/3/1 signal counts, decided over the hand-entered defect typing (`Protocol.defectOf`), `state = fold(log)` with the shape of Thm 10 and Thm 11, the post-consent CHALLENGE and its grade, and the per-cell witnesses of Ch. 13, each satisfying Inv-8 (`witnesses_satisfy_inv8`).
- The behavioural quotient of Ch. 12: under `FsmCanon`'s bit abstraction the eleven states carry ten behaviour classes (`FsmCanon.canon_ten_pairwise_distinct`, `canon_exec_rework_same`); the eleven over the log are derived (§12.11).
- The removals' grades (§11.4) as far as §11.4 marks them machine-checked — the fatal ones, and of the sole-provider ones, FAIL aside, the content edges — each a canon-internal necessary condition, the catch-alls (`isCatchAll`) aside, with the genuine-edge contrast `canon_pass_is_genuine`; Inv-8-forced — `noConfirm_breaks_inv8`, `inv8_forces_exactly`; the Inv-1 destinations the table carries — `canon_reassign_to_offered`, `acceptChallenge_dest_inv1_forced`. Forcedness over every adequate protocol is not derived: it quantifies over an unbounded class of protocols.
- ESCALATED's fold (Ch. 12) and the one-step cancel without CANCELLING give every non-terminal state but IDLE a timeout (`FsmCanon.noEscalated_*`, `oneStepCancel_*`), their deadlock-freedom derived (§12.13), and satisfy Inv-8 over their reachable states (`witnesses_satisfy_inv8`).
- The kernel results of Ch. 13, R′ over the log among them, in `LogLanguage.lean` with its agreement and load modules, `LogLanguageLapse.lean` and `LogLanguageReopen.lean`.
- Lean decides that timeout chains terminate; Φ1–Φ3 and Inv-8 are checked by TLC over bounded models, Φ3 at one node (`WaitsEnd`, `NoOwnerlessDivergence`, with negative controls), which assume Φ2's premise (Ch. 12) through fairness.

Of Inv-8, what is machine-checked is the existence of the owner's move and the forcing of the machine over the log relative to its conditions (§13.4). The machine decides off the table, axiom-free, that no CHECK lives at the Pragmatic level and which failure modes have a structural guard (Ch. 9).

Lemma 1 is definitional in Lean, the apparatus being defined S-free; checked is its consequence `no_apparatus_yields_S`, which `agent_necessary` takes as a separate hypothesis *(defined)*. Prop 3–9, stated over ℝ, information structures and probability, are outside the Lean scope (no mathlib) and cited as classics. That a Lean statement matches its canon section is argued, not machine-checked.

### 20.5. The covering axioms and the postulate closure

The postulate closure (Ch. 0) has four kinds and no single scalar *(defined)*.

**The (T)/(P) sorting principle** *(defined)*. A count is either (T) the unfolding of a definition inside a delimited space, which the kernel checks, or (P) a covering principle over an undelimited space, unprovable from inside. "No fifth primitive" is not postulated: its global form is a boundary in the covering form (§20.1). CA-Links's role count (Ch. 5) is sorted by this principle.

**Kind (a), the Lean axioms in `#print axioms`** *(defined)*. The closure yields **exactly three covering axioms**, plus the three carriers:

| Axiom (Lean) | Canon | Yields |
|---|---|---|
| `evaluation_completeness` — CA1 | Ch. 8 | the six failure modes |
| `morris_trichotomy` — CA-Morris | Ch. 9 | the three verification levels, by citation [18], below CA1's grade |
| `directed_action_completeness` — CA-Links | Ch. 5 | the five links, carrying REACHES-ternarity and START's fold |

The six FMs, the three levels and the five links are checked modulo their covering axiom, the theorems around each adding only De-Morgan localization, while the structure — the 4+2 geometry, the six witnesses, the 3⊕2 count — is axiom-free *(covering axiom)*. CA1, over six uninterpreted conditions, carries the whole sufficiency of the six FMs, their dissection argued and fixed by the encoding; since `correct` reads the verdict as it stands after the evaluation, it also asserts that nothing after makes a verdict wrong, the after phase mapped to no mode being encoded (`after_holds_none`). A closure branch has CA1's grade when an argument inside the theory narrows its candidate space, as CA1's does (§8.2) *(defined)*. START's fold, a choice carried by CA-Links, is disclosed under (a) and not counted in kind (d).

CA2, the single clock, is not a covering axiom: the count of the three operational phases is axiom-free (`app_phases_exhaustive`, `app_phases_disjoint`), so the clock is the hypothesis `SingleClock` of `op_trichotomy_of_total` *(machine-checked)*.

The count of three is a fact about the encoding, not about GFSO: which basket a claim lands in is the encoder's choice, with counterexamples both ways — |Act| = 2, a covering principle in substance, is a two-constructor type invisible to `#print axioms` (as an axiom the count would be four), and the single clock, once the fourth axiom, is a dischargeable hypothesis. The encoding invariant is not the number but that the covering principles are finite and enumerated, each placement disclosed.

**Kind (b), definitional postulates baked into the types** *(defined)*: A1 (verdicts are Boolean), A2 (decompositions exist), |Act| = 2 and the d3/d4 knowledge-source space. The d3/d4 source space {apparatus, declaration, luck, contact} (`KnowledgeSource`, Ch. 4) is likewise invisible to `#print axioms`, but its exhaustiveness is derived by nested excluded middle (d3–d5), unlike |Act| = 2's undelimited candidate space; the kernel takes the split as a type.

**Kind (c), hypotheses in theorem signatures, dischargeable** *(defined)*: act-surjectivity and act-injectivity, the |L| = 2 defense; not-apparatus, no-declaration and no-luck, carried by agent necessity (Ch. 4) (the first, §20.4); and `SingleClock`, which buys only the reading of the time axis's middle cell.

**Kind (d), adopted** — neither derived nor a Lean postulate, each marked where it is made (Ch. 0) *(adopted)* — comprises:

- the eleven design decisions:
  1. the deadline as a field of T (Ch. 2);
  2. the uniqueness of Del (Ch. 2);
  3. Inv-4's reading (Ch. 12);
  4. terminality, `max_reopens` = 0 with re-issuing its recovery (Ch. 12);
  5. R′'s form, REOPEN the gated signal under one sign-agnostic counter per node (Ch. 12);
  6. the moment of R′'s consumption threshold (Ch. 12);
  7. no expiry attributed to a party (Ch. 12);
  8. `max_iterations` a packet field, counted per version (Ch. 12);
  9. a split's admission and a root's creation as acts of their own (Ch. 11);
  10. an implementation's default deadline, logged as supplied (Ch. 2);
  11. q_V's scope, the acceptance direction only, the false-FAIL share left a diagnostic (Ch. 15);
- the adopted clauses: Inv-5 (b)–(c), Inv-7's "a state is what stands on the log", Inv-8's edge clause, and Inv-8's owner-exclusivity with the owner read off the log (Ch. 12);
- the one alternative reading: the decision's routes as a party's lapsed wait or a spent budget, a second ground for OVERDUE's removal (Ch. 12) and one of the forcing's conditions (§13.4).

Kind (a) shows in `#print axioms`; kinds (b)–(d), and outside the development the AI layer's covering of Peirce's three inference types (Ch. 17), are disclosed here, so no assumption hides unnamed.

Premises (Ch. 0) stand outside the closure.

### 20.6. Beth canonicity

An HVP (Ch. 2) is a structure in the first-order signature σ = ⟨T, D, Dep, Del⟩, V derived; σ″ is **adequate** iff mutually interpretable with σ over Mod(A1 ∧ A2), and **definitionally equivalent** to σ iff bi-interpretable with it (§13.1) without added sorts or parameters *(defined)*. **Minimality** — no proper sub-signature bi-interpretable with σ — is the constructive result of Ch. 7; **uniqueness** — every adequate σ′ bi-interpretable with σ — turns "no fifth primitive was found" into a question decidable in principle.

**σ-canonicity over the Beth class** *(derived)*. An FO parameter-free signature σ″ over the same domain whose relations are L_σ-definable over Mod(A1 ∧ A2) and over which σ is implicitly definable is definitionally equivalent to σ. *Proof.* σ interprets σ″ by hypothesis; by Beth's definability theorem [47] σ is explicitly L_σ″-definable, so σ″ interprets σ; one domain with no parameters gives definitional equivalence. ∎ At bounded quantifier rank the candidates are finite up to equivalence [48], so canonicity over the class is a finite case split.

The result is σ-centric and holds under the strong reading of adequacy, implicit definability, the weak reading leaving the mutual-vs-bi gap; it needs Mod(A1 ∧ A2) to be an elementary class, which the canon does not state it to be — a well-founded D is not first-order, and Beth fails over finite structures *(premise)*.

### 20.7. The completeness-of-the-carve wall

Four questions ask whether the carve is the only one: the uniqueness of the primitives; the admissible validation scales, |Act| = 2 being the action-side stipulation; why this many lists — six FMs, three levels, five links, the AI layer's two components; and the uniqueness of the protocol over a fully pinned design vector — covering form *(boundary)*.

Each quantifies over an undelimited space of candidates, and delimiting that space is a stipulation of frame, circular or frame-relative *(derived)*. Completeness inside a delimited space is a finite case split, but proving that no adequate σ′ fails to be bi-interpretable with σ requires delimiting the admissible signatures — the same quantifier one level up; so the reformulation of §20.6 fixes a checkable form of the answer and the point where it is unprovable, a shown boundary, not a failed search. The circular delimitation defines sameness as bi-interpretability, and the frame boundary coincides with two loci: whether a goal lies inside the model, one of §3.7's two empirical loci (§20.3), and the stipulation of a logical frame, kin to |Act| = 2 and CA1 *(derived)*.

Dep\*, non-FO (Ch. 2), is not recovered by the deadline order: in FO σ ∪ {Dep\*} is not mutually interpretable with σ and no adequate rival, in FO+TC or MSO it is definable and bi-interpretable — either way no falsifier and no fifth-primitive candidate, under FO a derived non-FO query of the V tier *(derived)*. Quotient interpretations open the mutual-vs-bi gap only with many sorts or weak adequacy; under strong adequacy Beth on both sides closes it, and no witness for organizational primitives is exhibited. The wall is thus pinned to one stipulation, the FO frame.

Uniqueness of the basis and of the protocol is uniqueness up to the right equivalence, and both share this wall — global uniqueness over undelimited signatures, alphabets and observables. Basis minimality (Ch. 7) closes minimality only, global uniqueness of the basis being this boundary. Within a frame (a) the basis is canonical over the Beth class; (b) the protocol is underdetermined over bare adequacy and forced over the log by named conditions whose naturalness is unsettled (Ch. 13). Beth bridges a real gap in (a), whose hypothesis is strictly weaker than its conclusion, and none in (b), behavioural equivalence, whose hypothesis is inter-derivable with its conclusion (§13.6).

The canon carries against the wall the covering axioms at their grades (§20.5) and the within-frame results (a)–(b). Under it stand disclosed residues, each a covering placement at its own grade and not a boundary of its own: CA-Links's representational branch (Ch. 5) and CA-Morris (Ch. 9), both below CA1's grade, and the AI layer's covering of the inference types (Ch. 17).

### 20.8. The boundary list

The boundary list has three entries, each tagged by its form:

1. the Pragmatic-level boundary (Lemma 1 + Lemma 2 forms), with its two faces, on the value and on the production of a split (§20.2);
2. the completeness-of-the-carve wall (covering form), with the covering axioms' disclosed residues under it (§20.7);
3. the edge of the domain (domain form, §20.3).

Of these, the one that bears on use is the faithfulness half of decomposition-method quality (§20.2), left to measurement.

### 20.9. Around the canon

Cardinal severity, adherence dynamics α and the optimal collusion-proof mechanism lie around the theory because no answer changes a claim *(derived)*. No claim reads a severity number: the apparatus runs on FM-3's binary discrimination, Prop 8 is stated conditional on its detection probability, and a `SEV` value would need a probability model and the base rate bridging `P(goal false | pass)`, which the graph bounds only as §15.8 states, to `sup P(pass | goal false)` (§19.6). No guarantee needs a law of α's motion (§16.5). No optimal bond or quorum changes which import restores Prop 8's inequality (§16.15).

Around the theory lie:

- the cardinal of severity, `SEV` (§19.6), its calibration absent;
- the agent's solitary induction and the agent-relative forced depth, residues the model localizes (§4.6);
- calibration: benchmarks, STD-3's default 90% threshold (Ch. 9), measurement periods, and the per-state bound values the canon requires to exist and fire but does not fix (Ch. 12);
- the incentivized core beyond §16.15's imports — a bond, a BFT quorum k-of-n (n ≥ 3f+1): the optimal bond or collusion-proof quorum over an authenticated insider [45]; criteria-lowering, read at clause-(ii) faithfulness and q_V, met by the proposed audit standard and peer review; reopen-griefing, bounded also by Φ3 and measurable by Thm 11 and q_V; against collusion and griefing transparency (Thm 11) and q_V protect only partially;
- an audit standard — procedures, audit, cross-industry comparability, a GAAP analogue — proposed, not operative;
- adherence dynamics `α(t+1) = f(α(t), c, observed Δ, enforcement)` and the conditions for a non-zero fixed point, an import of the Prop 3/4/8 layer; the adherence premise's closure (Ch. 16) and the LLM's raising of α (Ch. 17) lie here;
- cold start: the feedback loop's monotonicity holds from the first task, but at |𝒢| = 0 the LLM has only its prior and the Q-pattern layer no data, and at what |𝒢| its recommendations beat the prior significantly is open;
- peer review of decompositions — the colleagues' comparison of Ch. 4 as horizontal exchange — proposed, not operative, its benefit bounded by γ₁·γ₂ (Prop 7, Corollary 2, Ch. 16);
- the proxy metrics Λ and γ computed from system data: Prop 7 is stated in Λ·γ, and Λ·γ > 1 on a segment says validation is not coping;
- the CA1 residue (§8.2), local, touching neither the coarse cut, the count of six, nor "the two axes exhaust the unit";
- the within-frame remainder of uniqueness: the quotient route, and whether the log's class of named conditions (Ch. 13) is natural in Beth's sense, unsettled (§13.6);
- the formalization overhead (Ch. 16);
- how often to validate (§16.7);
- ranking by how badly a node failed (Ch. 15);
- whether GFSO generates Scrum's exploratory dynamics, a behavioural claim the structural embedding of §19.4 does not make.

### 20.10. Requirements not yet built or measured

These are requirements the canon states, settled by an implementation's check or a deployment's measurement; the boundaries are §20.8's.

- The LLM's Chollet Level ≥ 2 generalization (Ch. 17), unchecked.
- Empirical validation: a deployment measuring feasibility, the correlation Q ↔ real outcomes, the value of the made-explicit discipline (§19.3) against private assembly, α's denominator, and the faithfulness of seams to a real domain, which the a-priori boundary (§20.2) leaves to measurement.
- The form items (§4.5) with no dedicated pre-exec CHECK are implementation gaps, closed by a guard beside the battery under the conformance clause (Ch. 12) *(derived)*: item (1), decidability of each criterion, by pinning a decision procedure per criterion; item (3), non-redundancy's formal face (§9.6), decidable where CHECK-7 is; item (4), what a declared Dep edge carries, reported, not gated; the availability a Dep edge implies, unguarded — a pair with `deadline(t_a) + T_validate ≥ deadline(t_b)` passes CHECK-3 though the consumer may receive no passed input in time; item (6), deadline coherence along D, gated, reported and flagged as Ch. 11 and Ch. 12 place it, CHECK-3 guarding only the horizontal rule.
- The revision cause the metrics' cause-typed terms read (Ch. 15), not yet typed.
- A criterion forbidding nothing on the map (§9.6), or an atomic root's criteria jointly unsatisfiable on the map (§8.10), FORM that no form item and no CHECK covers: guards that each criterion's negation and each atomic root's criteria are satisfiable, decidable where CHECK-8's satisfiability is.
- The schedule of a maintenance generator (Ch. 6), FORM that no form item and no CHECK covers: a guard on serviceability by the generator's own estimates; and maintenance's measure over the stream (§6.11), which no Q term reads, not yet measured.

### 20.11. The tier backbone and the closure

The derivation stack, machine-anchored in `formal/GFSO/Postulates.lean`, arranges the canon in tiers 0–7b, each with a kind and its chapters; a tier's kind names what its completeness clause rests on, the rest of a covering-axiom-headed tier being derived, machine-checked structure, and the stack is not a generation order *(defined)*.

| Tier | Name | Kind | Chapters |
|---|---|---|---|
| 0 | Axioms | postulated (definitional) | 1, 3 |
| 1 | Primitives | derived basis; the deadline field and Del's uniqueness adopted; D a forest relative to the issuer role | 2, 7, 15 |
| 2 | Validation | derived | 7 |
| 3 | Failure modes | covering-axiom-headed (CA1) | 8 |
| 3b | Time | derived, CA2 discharged | 8 |
| 4 | Standards | covering-axiom-headed (CA-Morris) | 9 |
| 5 | Protocol | derived: signals minimal, states induced, the table forced over the log relative to its conditions (§13.4), up to REWORKING's label | 10–13 |
| 6 | Measurement | derived | 11, 15 |
| 7 | Theory model | derived, with d1–d6 by elimination | 3, 4, 6 |
| 7b | Links | covering-axiom-headed (CA-Links) | 5 |

The logical map runs knowledge-first:

```
directed action = 5 links (Ch. 5) over S (real) / Ŝ (built)
  → ONE seam: Contact reads S; the apparatus is S-free (Ch. 3)
  → A1, A2 = the seam's conditions of existence and nontriviality (Ch. 1, 3)
  → agent necessary as the carrier of domain content (Ch. 4, d1–d6)
  → a failure := a used edge e ∈ Ŝ∖S; FORM ⊕ FAITHFULNESS (Ch. 3, 18)
  → value = making-explicit; science = the same method over nature, implicit (Ch. 19); boundaries (Ch. 20)
———————————————— operationalization ————————————————
  → {T, D, Dep, Del} minimal basis; V derived (Ch. 2, 7)
  → |L| = 2 (source: A1), AND unique, Thm 1 (Ch. 7)
  → 6 FM complete as a basis modulo CA1 (Ch. 8)
  → standards + Syntactic/Semantic/Pragmatic verification (Ch. 9)
  → protocol: 12 signals (minimal) + 11 states (induced) (Ch. 10–13)
  → graph 𝒢 + 5 metrics Q (self-measuring) + AI layer (Ch. 15, 17)
  → nine formal guarantees (Ch. 11, 15, 16)
```

The contribution is a theory of directed action and, derived from it, a standard for the task-acceptance transaction. From A1 and A2, with CA1, relative to the adopted decisions and under premises named where each result is stated, a protocol is derived with 14 formal results — six original theorems (Thm 1, Thm 2, |L| = 2, the completeness of the 6 FM, Thm 10, Thm 11) and eight further results (Prop 3, 4, 6–9, Cor 5, basis minimality).

---

## Changelog

> Each entry says what the version changed in the canon; what reopens this document is a falsifier, not a plan. v4.0 is the flagship statement, completed over the numbered passes below.

**v4.1** (2026-10-03) — relative to v4.0. **Form:** the same theory and protocol, restated once per object in dependency order — every object defined in the first chapter after everything it needs, a link between two objects stated in the later of the two, every reference pointing backward, the Abstract and Introduction the only forward index; the twenty-eight chapters of four Parts became Chapters 0–20, led by the eight grades of Ch. 0, as the table below maps. **Added:** Inv-8 (Obligation-Ownership), its owner table and adopted edge clause (§12.13); ESCALATED the issuer's non-terminal decision, its silence closing through CANCELLING (§12.5); Inv-4's reading, a design decision (§12.9); no expiry attributed to a party (§12.2); a state as what stands on the log (§12.11); a node's issuer Del(parent), a root's the goal's issuer (§10.1); a root, one goal one root (§2.4, §15.2); the issuing condition (§12.7); Inv-5's clock moving a node only toward its settlement, and Φ1–Φ3 (§12.12, §12.15); the re-presentation rule (§12.10); validation as check and signature (§10.2); admission and root creation as logged acts, and what a re-admission re-checks (§11.5); the active child (§12.6); conformance (§12.16); the machine forced over the log relative to named conditions, and R′ given its form (§13.4, §13.5); each child's necessity a used edge (§8.1); the fifteen named exceptions and Cor 2's dials (§15.6, §16.9); kind (d) of the postulate closure (§20.5); the class of requirements not yet built or measured (§20.1, §20.10); TLC-checked finiteness and Inv-8, and the Lean development of the forcing over the log (§12.15, §20.4). **Removed:** OVERDUE and auto_pass, VALIDATING's timeout going to ESCALATED (§12.4); FM-7, the modes six, 4 ⊕ 2 (Ch. 8); the infinite adequate family over `max_iterations` (§13.2); the summary sites (old §1.2, §1.5, Ch. 23, Ch. 28); E1 and E2; the CI guard; the section pointing to the falsifiability register; restatements outside their homes and qualifiers answering critics' cases. **Readings changed**, each at its home: §2.1 when the model is needed, a goal within one agent's capacity inside it; §3.3, §8.3 what 𝒜 holds, the modes' domain faces read in S; §3.5 what contact gives an edge; §3.7 the axioms' second reading, a role added to postulates, and the leaf test at every node; §4.2 what tells two agents apart; §4.3, §8.7 a non-leaf's claim, read on the delivered result; §4.6, §16.7 the (ii)-faithfulness premise, conditioning Prop 7, Mechanism 2 and the strict information readings; §5.3 the triple ⟨goal, Ŝ, D⟩; §6.7 a split's joints; §6.10 where maintenance under the generator is viable from; §6.11, §20.10 a generator's schedule, FORM no form item covers; §7.4 the grade of Inf-A and Inf-B; §8.3 FM-1's condition through the split's mapping, FM-1.b and FM-1.c over a written criterion's outcome, FM-1.f at a waypoint and sensed by no verdict at its node, FM-1.b's test read at the fixing, FM-2's and FM-1.d's domain faces; §8.3, §8.10 a demand beyond what the goal needs, and an atomic root's unwritten or unsatisfiable criteria, failures of the goal's setting; §8.4 FM-3's object and A2's seam residue; §8.5 the grade of internal completeness, and FM-4's departure over a child whose recorded value is not of the delivered work; §8.6 the modes of an undeclared coupling; §8.7 three integration cases and the glue's carrier; §9.1, §9.9 what the Semantic level reads; §9.2 what a register entry names, and the acquitting cause; §9.3, §9.4 the route for a component no criterion carries; §9.5 CHECK-4's denial and STD-4 beside the coverage standards; §9.6 CHECK-7/8's decidability, and a criterion forbidding nothing on the map; §9.7, §12.10 who repairs a defect sourced in a packet's criteria, and its mode; §10.1 the issuer role outliving the parent's contract; §10.2 FM-4 in the protocol FAITHFULNESS, the issuer's check in the rule's slot; §10.3 where separation of duties breaks; §11.2 BLOCK's scope and an undecidable criterion's channel; §11.3 a signal as a report; §11.4 the incentive closure's scope; §11.3, §12.7 who owes a promotion, and when; §11.4 FAIL's, ACCEPT's and REJECT_CHALLENGE's second type and the strength grade of every removal; §11.5 what the Syntactic level gates at admission, item (6) included; §12.2 per-kind bounds, the deadline never suspended, VALIDATING on T_validate alone, a passed bound firing on entry, one visit per timeout, and when the clock starts; §12.3 `max_iterations` a packet field counted per version; §12.4 CHALLENGE after consent and REJECT_CHALLENGE before it; §12.6 the cascade over unissued children; §12.8 a PASS over a criterion at ⊥ or over an abandoned child's hole; §12.9 OFFERED's abstention, a named exception; §12.10 revision guards that flag, CHECK-2's Dep cycle alone refusing; §12.11 eleven states, ten classes under the bit abstraction and eleven over the log; §12.12 the timeout routing and authoritative cancellation derived; §12.14 finality, consumption, a cascaded child's reopen and R′'s counter; §13.2 bare adequacy pinning no destination; §13.3 what the rows force; §13.6 canonicity over a natural subclass, unsettled; §14.2, §14.4 the worked example's checks and how its root FAIL reads c₂; §15.1 what mutates 𝒢; §15.3 D a forest and the ground of its acyclicity; §15.4, §15.7 what q_V, q_D and q_Dep read, a pattern on the log whatever its mode, and a post-hoc run's fail; §15.6 Thm 10 and its Corollary 1, bar the post-hoc runs of q_V's later-fail term, four components trace-closed; §15.7 FM-4 guarded by no CHECK; §15.8 the premise of q_V's bound; §16.10 a blocker's lapse attributed to no one, and p = 1; §16.12 the timeouts row; §16.13 a self-assigned root's signer; §16.15 what a quorum and a bond buy; §16.16, §17.6 Mechanism 4's ground and premise; §16.7 Prop 7 at partial adherence an upper bound under any dependence; §16.17 applicability read off the model's conditions, a task with no verifiable outcome outside it (¬A1) and an unknown decomposition alone inside, carried by deferral; §17.1–§17.5 the log as the growing object, 𝒢 its projection; §17.2 the grade of Peirce's three types; §17.9 two pillars; §19.3 the generation method's grade; §19.4 Scrum a relaxation of GFSO, its embedding a mapping exhibited constructively, not a proven special case; §19.7 the science mapping, a defined mapping with an analytic core, science a relaxation of GFSO, not its special case; §19.8 the ground of the upward feedback's stability; §20.1, §20.9 the boundary criterion's four forms and what lies around the canon; §20.5 d3/d4's exhaustiveness derived; §20.7 the frame stipulation; §20.9 a deployment's duration, a calibration.

| v4.0 chapter | v4.1 chapters carrying most of it | Also (single statements) |
|---|---|---|
| Abstract | Abstract | — |
| 1. Introduction | Introduction; 20, 19, 4, 7 | 0, 8, 10, 12, 13 |
| 2. The world and the map: S, Ŝ, faithfulness, and the contact seam | 3, 8, 1 | 2, 9 |
| 3. Agent necessity | 4, 3 | 1, 8, 19, 20 |
| 4. The five constitutive links and their completeness | 5, 4 | 3, 20 |
| 5. The continuous substrate | 6 | 2, 3, 5, 9, 20 |
| 6. Positioning: the honest delta, the value, and the scientific method | 19, 20 | 1, 6, 7, 9, 12, 15, 16 |
| 7. Methodology: the forced discipline | 18, 3, 8, 9 | 5 |
| 8. Named boundaries | 20 | 0, 5, 9, 17 |
| 9. Axioms, operationally | 2, 1 | — |
| 10. Primitives and the basis | 2, 7, 10, 15 | 5, 9 |
| 11. Compositional validation | 7, 2 | 3 |
| 12. Failure modes of compositional validation | 8 | 2, 15 |
| 13. Standards and verification levels | 9, 8 | 2, 11, 12, 15, 20 |
| 14. The protocol | 12, 11, 10, 14 | 2, 3, 13, 15 |
| 15. Graph, metrics, and the AI layer | 15, 17 | 3, 10, 11, 16 |
| 16. Information dominance | 16 | 17 |
| 17. Improvement through constraints | 16 | — |
| 18. Monotonicity | 16 | — |
| 19. Incentive compatibility | 16 | — |
| 20. Decomposition quality | 16 | — |
| 21. Self-measurement | 15 | — |
| 22. Structural transparency | 11 | — |
| 23. Inseparability of the components | 17 | Introduction |
| 24. Assumptions and limitations | 16, 15, 12 | — |
| 25. Related work | 19 | — |
| 26. Where the canon stops | 20, 13, 12 | 8, 11, 16, 19 |
| 27. The machine-checked core | 20, 8, 12, 13, 7 | 3, 19 |
| 28. Conclusion | Introduction; 20 | — |
| Changelog | Changelog | — |
| References | References | — |

*The chapters carrying most of an old chapter are listed by the share of its theses they carry. Old Ch. 23, Ch. 28 and old §1.2 and §1.5 were summaries: their results are indexed in the Introduction, the pillars' inseparability is §17.9, and the logical map and the contribution are §20.11. Old §1.4 was the home of the tier backbone and the postulate closure, now §20.11 and §20.5. Section and chapter numbers inside the entries below v4.1 refer to the numbering of v4.0.*

**v4.0 · pass 1** (2026-07-16) — the English knowledge-first re-authoring of the frozen v3.9 canon: the theory of directed action leads as Part I and the operational apparatus follows as its consequence (Part II), every formal result carried unchanged and the discrete apparatus keeping its operative primacy. The naming contract applied: FM-3 Verifiability→Veracity, FM-5 Currency→Freshness, REVIEW→OFFERED, TIMEOUT state→OVERDUE, CANCELLED→ABANDONED, CANCEL_ACK→CONFIRM_CANCEL, REWORK→REWORKING, NEGLECTED→ACCEPTED_RISKS, AUTO→AUTO_PASS; HBP→HVP; verification levels led by Syntactic/Semantic/Pragmatic; covering axioms CA1/CA2/CA-Morris/CA-Links; theorem/proposition labels Thm/Prop/Cor; loop gain Λ·γ; task graph 𝒢; contact seam operator "Contact"; SOLITUDE→SINGLE-SEAM; EMIT→EXTERNALIZE; objectification→making-explicit; [STD]→[known]; the v3.9 "Lemma 3" renumbered Lemma 2; the C1–C7 condition labels folded into their FM statements. The Level-2 causal-correctness boundary moved to Chapter 8; the tier backbone and the postulate closure lifted into the front matter.

**v4.0 · pass 2** (2026-07-28) — §26.9(b) written: the bi-interpretation currency does not transport to the protocol (every adequate finite protocol is rigid), behavioural equivalence is the working currency, and the closing lemma is false over bare adequacy (the auto_pass sibling); (b) is not symmetric to (a) on the uniqueness axis. §14.3's per-state admissible sets written out; `FsmCanon.lean` added.

**v4.0 · pass 3** (2026-08-02) — §26.9(b)'s inner forced-vs-free enumeration over the fixed alphabet, each cell graded by strength and function with a necessary-condition witness; ACCEPT_CHALLENGE → OFFERED is Inv-1-forced, and RESOLVE_BLOCK → EXECUTING is the pure-unblock edge, a contract-changing resolution being an Inv-1 revision.

**v4.0 · pass 4** (2026-08-03) — Chapter 6 re-anchored: from Popper the prohibition structure and pre-registration are inherited, not falsifiability as the criterion of demarcation; decidability separated from probative force; the Pragmatic level stated as an interventionist claim; constitutivity defended against models-as-mediators; statistical testing shown to instantiate the criterion ↔ truth split. Repaired: the `SEV` gloss, prohibition located on clause (ii), pre-registration attributed to Inv-1, A1 stated as "decidable", ⪰_dom's antisymmetry on probe-sets, and the direction of §24.5's conditional.

**v4.0 · pass 5** (2026-08-03) — whole-canon sweep: A1 fixes only FM-3's verdict form; §6.2's first dividend restated; Prop 4's threshold ℙ(θ_bad) > c/Δ restored at every site; Cor 2 and Mechanism 2 corrected to `≤`; §25.1 rests on the vertical deadline rule of §3.4; Inv-5 exempts IDLE; FM-1 made two-faced (FM-1.f); an undeclared dependency routed to FM-2 or FM-5; the FORM interior's three stated as the load-bearing members.

**v4.0 · pass 6** (2026-08-04) — grades carried across sites: Prop 8 carries the detection probability `p`; Cor 3 no longer subtracts bounds; the pillars' inseparability carries `t*`; the front matter states the body's grades; the boundary criterion is stated at Chapter 8; triage becomes §15.4; ACCEPT_CHALLENGE survives on IC grounds, so 12 stays the minimum and the signal split becomes 4/4/3/1; the α exogeneity premise is named at §18.1. Follow-up repairs: CA1 graded argued; A1's decidability clause predicated of a task's result, maintenance being a generator of attainment tasks; §19.1 at 11 features with ACCEPT and ACCEPT_CHALLENGE; the d3/d4 source space disclosed in §1.4; §14.1–§14.6's worked example repaired against the rules it illustrates; Chapter 27 and `Postulates.lean` carry the fourth definitional postulate.

*(The v3.2–v3.9 changelog is the provenance record of the frozen Russian draft, kept in the repository's history.)*

---
## References

[1] D. Blackwell. Equivalent Comparisons of Experiments. *Ann. Math. Stat.*, 24(2):265–272, 1953.

[2] D. Blackwell, M. A. Girshick. *Theory of Games and Statistical Decisions*. Wiley, 1954.

[3] L. Hurwicz. Optimality and Informational Efficiency in Resource Allocation Processes. In *Math. Methods in Soc. Sci.*, 27–46, 1960.

[4] R. Myerson. Optimal Auction Design. *Math. Oper. Res.*, 6(1):58–73, 1981.

[5] H. A. Simon. A Behavioral Model of Rational Choice. *QJE*, 69(1):99–118, 1955.

[6] H. A. Simon. The Architecture of Complexity. *Proc. APS*, 106(6):467–482, 1962.

[7] J. Marschak, R. Radner. *Economic Theory of Teams*. Yale UP, 1972.

[8] J. Marschak, K. Miyasawa. Economic Comparability of Information Systems. *IER*, 9(2):137–174, 1968.

[9] G. Zames. On the Input-Output Stability of Time-Varying Nonlinear Feedback Systems. *IEEE TAC*, 11(2):228–238, 1966.

[10] Z.-P. Jiang, A. R. Teel, L. Praly. Small-Gain Theorem for ISS Systems and Applications. *MCSS*, 7(2):95–120, 1994.

[11] C. A. Petri. *Kommunikation mit Automaten*. PhD thesis, U. Bonn, 1962.

[12] K. Erol, J. Hendler, D. Nau. HTN Planning: Complexity and Expressivity. *AAAI*, 1152–1157, 1994.

[13] B. Meyer. Applying "Design by Contract". *Computer*, 25(10):40–51, 1992.

[14] A. Benveniste et al. Contracts for System Design. *Found. Trends EDA*, 12(2–3):124–400, 2018.

[15] A. van Lamsweerde. Goal-Oriented Requirements Engineering: A Guided Tour. *RE*, 249–262, 2001.

[16] E. Yu. Towards Modelling and Reasoning Support for Early-Phase RE. *RE*, 226–235, 1997.

[17] W. van der Aalst. The Application of Petri Nets to Workflow Management. *JCSC*, 8(1):21–66, 1998.

[18] C. W. Morris. Foundations of the Theory of Signs. *Int. Encyclopedia of Unified Science*, 1(2), 1938.

[19] C. S. Peirce. Pragmatism as a Principle and Method of Right Thinking. Harvard Lectures, 1903. In *Collected Papers*, Vol. 5 (esp. CP 5.145), Harvard UP, 1934.

[20] L. de Moura, N. Bjørner. Z3: An Efficient SMT Solver. *TACAS*, 337–340, 2008.

[21] A. N. Angelopoulos, S. Bates. Conformal Prediction: A Gentle Introduction. *Found. Trends ML*, 16(4):494–591, 2023.

[22] S. M. Xie, A. Raghunathan, P. Liang, T. Ma. An Explanation of In-Context Learning as Implicit Bayesian Inference. *ICLR*, 2022.

[23] S. Garg, D. Tsipras, P. Liang, G. Valiant. What Can Transformers Learn In-Context? A Case Study of Simple Function Classes. *NeurIPS*, 2022.

[24] F. Chollet. On the Measure of Intelligence. arXiv:1911.01547, 2019.

[25] M. R. Morris et al. Levels of AGI: Operationalizing Progress on the Path to AGI. *ICML*, 2024.

[26] R. Sutton, D. Precup, S. Singh. Between MDPs and Semi-MDPs: A Framework for Temporal Abstraction in Reinforcement Learning. *Artificial Intelligence*, 112(1–2):181–211, 1999.

[27] K. Schwaber, J. Sutherland. *The Scrum Guide*. 2020.

[28] J.-P. Aubin. *Viability Theory*. Birkhäuser, 1991. (See also J.-P. Aubin, A. Bayen, P. Saint-Pierre. *Viability Theory: New Directions*. Springer, 2011.)

[29] E. D. Sontag. *Mathematical Control Theory: Deterministic Finite Dimensional Systems*. 2nd ed., Springer, 1998.

[30] A. McGovern, A. G. Barto. Automatic Discovery of Subgoals in Reinforcement Learning using Diverse Density. *ICML*, 361–368, 2001.

[31] J. Hoffmann, J. Porteous, L. Sebastia. Ordered Landmarks in Planning. *JAIR*, 22:215–278, 2004.

[32] E. D. Sacerdoti. Planning in a Hierarchy of Abstraction Spaces. *Artificial Intelligence*, 5(2):115–135, 1974.

[33] C. Hogg, H. Muñoz-Avila, U. Kuter. HTN-MAKER: Learning HTNs with Minimal Additional Knowledge Engineering Required. *AAAI*, 950–956, 2008.

[34] R. Waldinger. Achieving Several Goals Simultaneously. In *Machine Intelligence 8*, Ellis Horwood, 1977.

[35] F. Blanchini. Set Invariance in Control. *Automatica*, 35(11):1747–1767, 1999.

[36] R. C. Conant, W. R. Ashby. Every Good Regulator of a System Must Be a Model of That System. *International Journal of Systems Science*, 1(2):89–97, 1970.

[37] The Long-Horizon Task Mirage? Diagnosing Where and Why Agentic Systems Break. arXiv:2604.11978, 2026.

[38] B. Alpern, F. B. Schneider. Defining Liveness. *Information Processing Letters*, 21(4):181–185, 1985.

[39] D. G. Mayo. *Error and the Growth of Experimental Knowledge*. U. Chicago Press, 1996.

[40] K. R. Popper. *The Logic of Scientific Discovery*. Hutchinson, 1959.

[41] L. Laudan. The Demise of the Demarcation Problem. In R. S. Cohen, L. Laudan (eds.), *Physics, Philosophy and Psychoanalysis*, 111–127, Reidel, 1983.

[42] M. Pigliucci, M. Boudry (eds.). *Philosophy of Pseudoscience: Reconsidering the Demarcation Problem*. U. Chicago Press, 2013.

[43] J. Woodward. *Making Things Happen: A Theory of Causal Explanation*. Oxford UP, 2003.

[44] J. Pearl. *Causality: Models, Reasoning, and Inference*. 2nd ed., Cambridge UP, 2009.

[45] J.-J. Laffont, D. Martimort. *The Theory of Incentives: The Principal-Agent Model*. Princeton UP, 2002.

[46] J. Green, J.-J. Laffont. *Incentives in Public Decision-Making*. North-Holland, 1979.

[47] E. W. Beth. On Padoa's Method in the Theory of Definition. *Indagationes Mathematicae*, 15:330–339, 1953.

[48] A. Ehrenfeucht. An Application of Games to the Completeness Problem for Formalized Theories. *Fundamenta Mathematicae*, 49:129–141, 1961. (With R. Fraïssé, Sur quelques classifications des systèmes de relations, *Publ. Sci. Univ. Alger*, 1:35–182, 1954.)

[49] N. Immerman. *Descriptive Complexity*. Springer, 1999.

[50] A. Nerode. Linear Automaton Transformations. *Proc. AMS*, 9(4):541–544, 1958. (With J. Myhill, Finite Automata and the Representation of Events, WADD Tech. Rep. 57-624, 1957.)

[51] H. Reichenbach. *Experience and Prediction*. U. Chicago Press, 1938.

[52] R. N. Giere. *Explaining Science: A Cognitive Approach*. U. Chicago Press, 1988.

[53] M. Weisberg. *Simulation and Similarity: Using Models to Understand the World*. Oxford UP, 2013.

[54] M. S. Morgan, M. Morrison (eds.). *Models as Mediators*. Cambridge UP, 1999.

[55] I. Lakatos. Falsification and the Methodology of Scientific Research Programmes. In I. Lakatos, A. Musgrave (eds.), *Criticism and the Growth of Knowledge*, 91–196, Cambridge UP, 1970.

[56] T. S. Kuhn. *The Structure of Scientific Revolutions*. U. Chicago Press, 1962.

[57] P. Duhem. *The Aim and Structure of Physical Theory*. Princeton UP, 1954 (1906); W. V. O. Quine. Two Dogmas of Empiricism. *Philosophical Review*, 60(1):20–43, 1951.

[58] W. Whewell. *The Philosophy of the Inductive Sciences*. Parker, 1840; P. Kitcher. Explanatory Unification. *Philosophy of Science*, 48(4):507–531, 1981.

[59] W. C. Salmon. *Scientific Explanation and the Causal Structure of the World*. Princeton UP, 1984.

[60] S. Yao et al. ReAct: Synergizing Reasoning and Acting in Language Models. *ICLR*, 2023; S. Yao et al. Tree of Thoughts: Deliberate Problem Solving with Large Language Models. *NeurIPS*, 2023; D. Zhou et al. Least-to-Most Prompting Enables Complex Reasoning in Large Language Models. *ICLR*, 2023.

[61] P.-L. Bacon, J. Harb, D. Precup. The Option-Critic Architecture. *AAAI*, 1726–1734, 2017; A. S. Vezhnevets et al. FeUdal Networks for Hierarchical Reinforcement Learning. *ICML*, 2017; Ö. Şimşek, A. G. Barto. Skill Characterization Based on Betweenness. *NeurIPS*, 2009.
