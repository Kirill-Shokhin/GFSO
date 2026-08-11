# GFSO (General Framework for Structured Operations): Formal Guarantees for Compositional Task Validation in Hierarchical Organizations

> v4.0 — the English final version. Knowledge-first exposition: the theory of directed action leads; the operational apparatus (primitives, protocol, metrics) is presented as its consequence. The frozen Russian working draft (v3.9, `applied_gfso_v3.md`) is the provenance record; all formal results are carried unchanged.

## Abstract

Task management in hierarchical organizations has no formal standard: goal-setting, decomposition, and acceptance are ad-hoc processes. We present a theory of **directed action** and derive from it a formal protocol that makes planning falsifiable.

The theory first. Directed action is a chain of five constitutive links — goal, build-Ŝ, plan, execution, contact — over one pair of objects: **S**, the real composition structure of the domain (contingent, not given), and **Ŝ**, the explicit estimate an agent builds and acts over. Exactly one operation reads S: the **contact seam**. From this, the necessity of an **agent** — a carrier of empirically learned domain content (a human or an LLM; the protocol treats them identically) — is *derived*, not assumed (the apparatus is provably S-free; declaration regresses; luck is unstable), and every failure of directed action is located at a used edge `e ∈ Ŝ∖S` — a passage the map asserts and the territory denies.

The apparatus follows as the theory's operationalization. Two axioms — A1 (verifiability) and A2 (decomposability), read equivalently as the two existence conditions of the contact seam — yield: a minimal basis of primitives (Task, Decomposition, Dependency, Delegation; Validation derived) → binary validation (|L| = 2, sourced in A1) → uniqueness of AND-aggregation → **seven failure modes, proved complete as a basis** analytically, modulo one named covering axiom (both axes are derived and "no third" is argued, not derived — hence the axiom; the residue is the value/time edge of trace predicates; the single clock is discharged) → standards with three verification levels (Syntactic / Semantic / Pragmatic) → a minimal protocol (12 signals minimal, 12 states induced) → the task graph → self-measuring quality metrics → an AI layer (Solver + LLM, its necessity from capacity, Simon 1955).

Original results: binarity and AND are the only constructions under the axioms; the seven failure modes are exhaustive; the protocol, metrics, and AI layer are minimal. Classical support: the design is consistent with Blackwell (1953), Simon (1955), Hurwicz (1960). The three pillars (protocol, AI, self-measurement) form a feedback loop — removing the protocol or self-measurement makes improvement through the framework impossible outright, and removing the AI layer does so past the capacity threshold at which the accumulated information outgrows what a human can process. The formal layer is a Lean 4 development on the language kernel (no `sorry`, no mathlib) that **audits the axiomatic surface** rather than carrying the substantive claims: exactly **three covering axioms** carry the "no further kind" results, every postulate's placement — axiom, type, or dischargeable hypothesis — is disclosed, the tables and invariants are machine-checked, and the negative result of §26.9(b) is contributed there; a fail-closed CI guard defends that enumeration. Everything else is derived.

The primary value is **making-explicit**: decomposition moves out of private intuition into a single axiom-derived, consistency-checked, faithfulness-graded discipline — a GFSO plan is a set of pre-registered, separately falsifiable claims, not an unfalsifiable story. In this exact sense GFSO is the scientific method formalized and generalized — **science : nature = GFSO : any directed action** — a positioning that is mostly inheritance (stated as such; the single substantive in-mapping delta is decidability), earned through the theory-model made explicit and mandatory.

---

## 1. Introduction

### 1.1. The problem

Task management in hierarchical organizations is barter: every assignment is a negotiation (what to do? how to check? what counts as done?), every acceptance a subjective judgment. There is no standard for the transaction. The result: systemic losses — delays discovered late, specifications lost, acceptance a formality, responsibility diffuse.

**The control dilemma:** a manager has two modes — **interfere** (call, check, prod) or **not interfere** (learn of the problem when it is late). There is no third mode. A third mode is needed: **trust, but see.**

### 1.2. Contribution

A theory of directed action (Part I) and, derived from it, a formal protocol — a standard for the task-acceptance transaction (Parts II–III). Six original theorems plus eight further results (six propositions supported by classical theory; Cor 5 and basis minimality — derivative/constructive):

**Theorems (original results):**

| # | Result | Claim | Proof type |
|---|---|---|---|
| Thm 1 | Compositionality | V(parent) = AND(V(children)) under a correct D | Characterization (the propagating form is tautological from the two conditions — §11.1; the substance is the domain soundness it leaves open) |
| Thm 2 | Uniqueness of AND | AND is the only nontrivial aggregation | Exhaustive enumeration |
| — | \|L\| = 2 (binary validation) | Source — A1 (V is a conjunction of 2-valued predicates); the pigeonhole argument is the defense (Ch. 11) | A1-conjunction |
| — | Completeness of the 7 FM | proved as a basis, modulo the covering axiom CA1 (residue — the value/time edge of trace predicates, Ch. 12; the single clock discharged, Ch. 27) | Exhaustive case split |
| Thm 10 | Self-measurement | Q computable from the trace | Constructive-definitional (Q *is* defined as queries over the trace) |
| Thm 11 | Structural transparency | Every decision has a record | Definitional (the log is defined to record every decision) |

**Propositions (the P-series is supported by classical theory; minimality — constructive):**

| # | Result | Claim | Support |
|---|---|---|---|
| Prop 3 | Blackwell dominance | GFSO informationally dominates the status quo | Blackwell 1953 |
| Prop 4 | Constraint improvement | Constraints improve payoff when ℙ(θ_bad) > c/Δ | Simon 1955 |
| Cor 5 | α-monotonicity | Quality ↑ with adherence | Corollary of Prop 3 |
| Prop 6 | Temporal monotonicity | Quality ↑ over time | Blackwell |
| Prop 7 | Scale bounds | Cascade: ‖eₙ‖ ≤ (Λ·γ)ⁿ · ‖e₀‖ | Operator composition |
| Prop 8 | IC (dominant strategy) | Honesty optimal when p·cost(undetected defect) > cost(signal) at that signal's detection probability p; detection structural (the channel's independence of the counterparty's strategy, **not** p = 1) ⟹ dominant against any non-colluding counterparty | Hurwicz 1960 |
| Prop 9 | Decomposition quality | 4 independent improvement mechanisms | Prop 3 + 7 + 4 + 6 |
| — | Minimality | the basis {T, D, Dep, Del} is minimal: each element necessary (constructive); uniqueness open, Ch. 26 (the wall narrowed to the frame choice) | Constructive |

*The P-series numbering matches the "Prop N" labels in the body (Prop 3 = Ch. 16, …, Prop 9 = Ch. 20); indices 3–9 are inherited. P1/P2 are not members of this series — the corresponding results (binarity, AND) stand as theorems in Ch. 11. The informativeness claims of Ch. 11 (Inf-A/B) are methodological and outside the headline eight.*

> **Formal status.** The formal skeleton is machine-checked in Lean 4 (language kernel, no mathlib): Thm 1, Thm 2, |L| = 2, and the geometry of the 7 FM / FSM invariants are checked; the completeness of the 7 FM, the Morris trichotomy, and the completeness of the five links are checked *modulo* their named covering axiom (exactly **three covering axioms**, machine-enumerated); Prop 3–9 are out of scope (they need ℝ/probability) and cited as classics. The register of irreducible assumptions is CI-guarded — Chapter 27. What the development *is* — an **audit of the axiomatic surface** (which claims are definitional, which irreducible, and how many), not a proof of the substantive claims — is stated at Chapter 27, and `formal/README.md` grades every row.

**The theory-model layer (Part I; it changes no formal result):** agent necessity is derived (Chapters 2–3); the five-link ontology over the continuous substrate (Chapters 4–5), completeness modulo REACHES-ternarity (the representational branch, sub-CA1 grade); the methodology as a forced optimum over `c_check + E_FORM + E_FAITH` (Chapter 7); the honest [known]/[GFSO] ratio and value = making-explicit (Chapter 6); the named boundaries (Chapter 8).

### 1.3. Positioning

- **Not a task tracker.** Jira tracks tasks. GFSO tracks *decisions*: who decomposed, into what, why, under what criteria.
- **Not an ERP.** It does not manage resources. It manages the decision-making process.
- **Not a chatbot.** An LLM without a protocol is advice without context. A protocol without an LLM is bureaucracy.
- **Not an autopilot.** The LLM helps think; people decide.
- **Not only a standard — a theory-model.** The necessity of the agent-as-carrier-of-domain-content is **derived** (Chapter 3), not presumed; the model does not only prescribe — it explains the observed and predicts falsifiably. The theory leads this document; the apparatus follows as its consequence.
- **The scientific method, generalized.** GFSO presents itself as the scientific method with the theory-model made explicit, its domain lifted from nature to **any directed action** — `science : nature = GFSO : any directed action`. This is positioning, not a derivation: the mapping's core is analytic inheritance of the *surviving* Popperian core — the prohibition structure (pre-registration entering from the neighbouring predesignation line), not the criterion demarcating science (stated as such — the one substantive in-mapping delta is *decidability*); its content, bounds, and imports are developed beside the foundation in Chapter 6.

The work is self-contained and rests on the classics directly (no result depends on an external formalism).

### 1.4. The tier backbone and the postulate closure

The canon's derivation stack, made explicit (a stack, not a generation order — see the note below the table; machine-anchor = `formal/GFSO/Postulates.lean`):

| Tier | Name | Kind | Contains | Chapters |
|---|---|---|---|---|
| 0 | AXIOMS | postulated (definitional) | A1, A2 (= the two conditions of the contact seam, Ch. 2) | 2, 9 |
| 1 | PRIMITIVES | derived basis | T, D, Dep, Del — V derived | 10 |
| 2 | VALIDATION | derived (theorems) | L (\|L\|=2), AND, Thm 1 | 11 |
| 3 | FAILURE MODES | covering-axiom-headed (CA1) | FM-1…FM-7 (4 denotational ⊕ 3 operational) | 12 |
| 3b | TIME | derived + discharged hypothesis | the operational axis (before/during/after) | 12 |
| 4 | STANDARDS | covering-axiom-headed (Morris) | STD-1..4, the nine CHECKs, Syntactic/Semantic/Pragmatic | 13 |
| 5 | PROTOCOL | derived (induced) | 12 signals, 12 states, Inv-1..7 | 14 |
| 6 | MEASUREMENT | derived (self-measuring) | Q (5 metrics), Thm 10, Thm 11 | 15, 21, 22 |
| 7 | THEORY MODEL | derived + elimination (Lemma 1 definitional; d1–d6 by elimination) | S/Ŝ, Contact, Lemma 1, d1–d6 | 2, 3, 5 |
| 7b | LINKS | covering-axiom-headed | the five constitutive links (3 ⊕ 2) | 4 |

*(The tier "kind" is a structural label — a covering-axiom-headed tier still consists mostly of derived, machine-checked structure; only its completeness clause rests on the axiom. This document's exposition reads the stack knowledge-first: Tiers 7/7b lead as Part I; Tiers 0–6 follow as Part II. The table itself is direction-neutral — a protocol-first reading path remains available through it.)*

**The honest postulate closure — three kinds, no single scalar.** "How many postulates does GFSO have" has no one number; it has this table (machine-audit: `#print axioms` + a fail-closed CI guard — Chapter 27):

| Kind | Members | Where it lives |
|---|---|---|
| (a) Lean AXIOMS — in `#print axioms`. **Three covering axioms** (+ their three uninterpreted carriers — the whitelist's six, below). | CA1 `evaluation_completeness` (7 FM, Ch. 12) · CA-Morris `morris_trichotomy` (3 levels, Ch. 13) · CA-Links `directed_action_completeness` (5 links, Ch. 4) | explicit axioms |
| (b) DEFINITIONAL — baked into the types | A1 (verdicts are Boolean) · A2 (decompositions exist) · \|Act\| = 2 (a two-constructor type; a covering principle in substance, invisible to `#print axioms`) · the d3/d4 source space {apparatus, declaration, luck, contact} (a four-constructor type, `KnowledgeSource`, likewise invisible — but at a **different grade**: its exhaustiveness is *argued* by nested excluded middle — derivable from the apparatus? if not, declared? if neither, coincidence — where \|Act\| = 2's candidate space is undelimited; disclosed here so the two encodings are not read as one) | the types |
| (c) HYPOTHESIS-FORM — carried in theorem signatures; dischargeable | act-surjectivity + act-injectivity (\|L\|=2 defense) · no-declaration + no-luck (agent necessity) · `SingleClock` (CA2, discharged — buys only the reading of the middle cell) | signatures |

The whitelist the CI guard defends has **six** entries = the 3 covering axioms + 3 uninterpreted-predicate carriers (`correct`, `Directed`, `fullyKnown`) — the free predicates the axioms quantify over, localizing the empirical residue; the same fact at two granularities. An earlier "four covering axioms" count predates the discharge of the single clock and is stale.

### 1.5. The logical map (knowledge-first)

```
directed action = 5 links (Ch. 4)  over  S (real) / Ŝ (built)              Part I
  → ONE seam: Contact reads S; the apparatus is S-free (Ch. 2)
  → A1, A2 = the seam's two existence conditions (Ch. 2)  [= the axioms, Ch. 9]
  → agent necessary as the carrier of domain content (Ch. 3, d1–d6)
  → every failure = a used edge e ∈ Ŝ∖S; FORM ⊕ FAITHFULNESS (Ch. 7)
  → value = making-explicit; science = the special case (Ch. 6); boundaries (Ch. 8)
—————————————————————— operationalization ——————————————————————————————— Part II
  A1, A2 (operational reading, Ch. 9)
  → {T, D, Dep, Del} minimal basis; V derived (Ch. 10)
  → |L| = 2 (source: A1), AND unique, Thm 1 (Ch. 11)
  → 7 FM complete-as-basis modulo CA1 (Ch. 12)
  → standards + Syntactic/Semantic/Pragmatic verification (Ch. 13)
  → protocol: 12 signals (minimal) + 12 states (induced) (Ch. 14)
  → graph 𝒢 + 5 metrics Q (self-measuring) + AI layer (Ch. 15)
  → 9 formal guarantees (Ch. 16–22)                                        Part III
```

Design decisions (deadline, uniqueness of Del) are marked explicitly. The theory-model does not change the formal results; it grounds them.

---

# Part I. The Theory of Directed Action

## 2. The world and the map: S, Ŝ, faithfulness, and the contact seam

### 2.1. The object and the two axioms

The object of this theory is **directed action**: a system acting in a real domain so that a goal is reached.

Two axioms delimit the domain of the theory. They are stated here as given objects; §2.6 below reads them a second way — as the two existence conditions of the contact seam — and Chapter 9 states their operational reading over tasks. All three appearances are one fact.

**Axiom A1 (verifiability).** Any organized activity is directed at a goal whose attainment is checkable: there exists a finite set of conditions, each decidable in finite time, each returning pass or fail.

**Axiom A2 (decomposability).** There exist goals whose complexity exceeds the capacity of a single agent. Such goals are attainable only by splitting them into parts, each within the capacity of some agent.

A1 is a fact about goals (*what*); A2 is a fact about complexity and agents (*who*). Two orthogonal dimensions.

**What the clause is predicated of (used later to adjudicate goal topologies).** The conditions are over a **task's result** — an object that arrives. A *standing* predicate that never terminates is therefore not an A1 condition as it stands, and this is what places the goal topologies of Chapter 5: bounded attainment `◇≤dl G` is two-sidedly decidable at its deadline and is an A1 condition directly; **maintenance `□Ω` is not a task node at all** (§5.6 — it is a standing generator) and enters the apparatus through the bounded-attainment tasks it emits, each of which is; a goal that admits *neither* reading is outside A1 (Chapter 8's `□◇A` entry). One-sided finite decidability (§5.6) is a property of the continuous *objects*; the deadline is what sharpens the emitted task to the two-sided verdict A1 asks for.

**A1 as two clauses.** "Returns pass/fail" joins two independent things: **(i) decidability** — the predicate yields pass/fail mechanically in finite time; this is the **decidability conjunct** of the decidable form of Popper's falsifiability requirement (it constrains the verdict's codomain, not its attained image: a criterion whose fail value is never attained satisfies it and forbids nothing; the other conjunct, **prohibition** — a non-empty fail-extension — is carried by clause (ii): domain-correctness forces *fail* wherever the goal is really unattained, so the fail-extension is non-empty exactly under the contingency of attainment (§7's "**NOT** 'never fail'"); the strengthening over Popper's *in principle* is therefore **A1's**, not clause (i)'s, and neither conjunct entails the other); **(ii) domain-correctness** — passing coincides with the real outcome. A1 asserts the *existence* of a correct predicate, not *which one* it is; the choice of criteria is silently delegated to whoever writes them. Here is where the agent was hidden — Chapter 3 makes this precise.

### 2.2. S and Ŝ: the real structure and the built estimate

**S** is the real composition/transition structure of the domain — what actually composes what, what actually reaches what. S is real, contingent, and **not given in advance** (Lemma 1 below). Ontically, S is a controlled continuous flow (`ẋ = f(x,u)` — Chapter 5 develops this deep view); the discrete composition relation

```
(t, {tⱼ}) ∈ S   ⟺   really completing all children tⱼ actually attains the parent t
```

is its **derived shadow** on the functional scale and the **operationally primary primitive** of the apparatus: real joint sufficiency — the same joint sufficiency that Chapter 11 states over criteria, but as a fact about the domain, not as a claim. (In the deep view it is the shadow of one chained capture-basin step — Chapter 5.)

**Ŝ** is the explicit estimate of S that the agent *builds* and acts over. S is **not a catalogue of routes** and not the seat of an "optimal path": the route/decomposition is chosen and built on Ŝ (the goal underdetermines it — Chapter 3); subtasks exist only mediately — they are generated by composition over Ŝ and then adjudicated by contact against S. `(t,{tⱼ}) ∈ S` is reality's verdict on a composition that was *posited on Ŝ*, not a lookup of a pre-existing edge.

**Faithfulness** is the relation `Ŝ_used ⊆ S` — every edge of Ŝ that the action actually uses is real. This is the **edge axis** of faithfulness, its general form; the deep view unfolds it into three orthogonal axes — edge / node / scale (Chapter 5) — where the node and scale axes are correctness conditions on the *carrier* of Ŝ and generate edge failures, not vice versa. Faithfulness is opened **only by contact**: no a-priori discipline certifies it (Lemma 1).

**The root of failure.** Any failure of directed action is, at bottom, a **used edge `e ∈ Ŝ \ S`** — an edge the map asserts and the territory denies: a wall the map promised as a passage. The complete taxonomy of *where in the validation computation* that edge bites is a Part-II result (the seven failure modes, Chapter 12, complete modulo the named covering axiom CA1); the root itself splits on one ontic fact — whether the integration edge is a *member* of `Ŝ_used` at all: **(i) a coverage hole** — the edge is absent (forgotten glue; the integration criterion was never written): a false PASS here is a *consequence*, there is nothing to lie about — the mode later named FM-1; **(ii) an insensitive edge** — the edge is present but asserts a passage that S denies (the criterion cannot distinguish the real divergence) — the mode later named FM-3 false-PASS. Case (ii) is the irreducible residue of faithfulness (Chapter 8).

### 2.3. The apparatus is S-free

Name the **apparatus** 𝒜: decidable criteria, the conjunction law `V(parent) = AND(V(children))`, the failure-mode taxonomy, the CHECK battery, composition/search over the map (all derived in Part II). As a family of operations, every `α ∈ 𝒜` is a function `α : Ŝᵏ → Ŝ` — domain and codomain entirely inside Ŝ. **𝒜 is syntactically S-free: nothing in the apparatus refers to S.**

### 2.4. The contact seam

**The operator.** On a used edge `e = (B, B′) ∈ Ŝ_used`, the operator

```
Contact : (e, [e ∈ S]) ↦ (verdict, Ŝ′)
```

takes the edge `e` and the ontic fact `[e ∈ S] ∈ {tt, ff}` — the world's verdict — and returns `verdict ∈ {pass, fail}` together with the updated estimate Ŝ′. Execution puts the edge to the world; the world returns `[e ∈ S]`; the system revises Ŝ → Ŝ′. Contact is the canonical fifth link of directed action (Chapter 4), named as an operator.

**SINGLE-SEAM.** Contact is the **only** operation of the whole field that reads S. S enters exclusively through `[e ∈ S]` — the second argument of Contact. Consequence: before Contact is applied, any Ŝ is a projection without ground; after it, the touched edges acquire a **truth-maker** in S. This is epistemology glued to ontology at exactly one seam — Lemma 1, named.

**Necessity and uniqueness.** *Necessity (substantive):* without Contact the field is closed inside Ŝ — no edge ever acquires ground — faithfulness `Ŝ_used ⊆ S` is unverifiable — directedness degenerates into an open-loop guess. *Uniqueness (by definition, not a theorem):* any operation that reads S converts an ontic fact into an epistemic sanction, which is what Contact *is*; so Contact is unique up to re-application on different edges. The load-bearing half is necessity; the uniqueness is tautological.

### 2.5. The two lemmas

**Lemma 1 (domain structure lies beyond the axioms).** Let S be the real composition structure of a domain. Two domains with the same formal graph but different real composition laws (S₁ ≠ S₂) satisfy A1 and A2 in the structural (clause-(i)) reading identically; in that language they cannot be distinguished ⟹ S is not definable from A1 + A2. (It is exactly clause (ii) that would require S — that is the point.) Equivalently: SINGLE-SEAM — the apparatus 𝒜 is syntactically S-free (§2.3–2.4).

**Lemma 2 (declaration has no bottom).** A declared decomposition is itself a decomposition, whose correctness is a fresh instance of the same question ⟹ regress. Pure declaration grounds no correctness. *(Numbering note: v3.9 carried this as "Lemma 3" with no Lemma 2 in the document; v4.0 renumbers — see Changelog.)*

### 2.6. A1 and A2 as the two conditions of the seam

The field of directed action (Chapter 5 defines it fully) is stated **without** A1/A2 baked into its definitions — a bare controlled system plus an epistemic graph of beliefs: no checkability of outcomes, no decomposability, only dynamics, basins, and a graph. Ask instead: what must be true of the field for the operator Contact — the single seam — to exist and be nontrivial? This is a **second reading** of the axioms, not a replacement of their axiomatic status.

**A1 = solvability of Contact's OUTPUT.** Canonically A1 is two clauses (§2.1): (i) **decidability** — Contact *returns* a verdict in `{pass, fail}` on `[e ∈ S]` mechanically in finite time — co-extensive with Contact's signature, i.e. clause (i) is *read off* Contact rather than derived; (ii) **domain-correctness** — Contact's verdict *coincides* with the real `[e∈S]` — the **nontrivial half**: it is not supplied by the apparatus (SINGLE-SEAM), only by the world through Contact (Lemma 1) ⟹ it stays open (the mode later named FM-3). Here, again, is where the agent was hidden.

**A2 = constructibility of Contact's INPUT.** Contact's input is an edge `e` directly checkable within one act (atomic for a single contact). **Capacity κ** — the largest region/step one act can directly realize-and-check ("capacity of a single agent" from A2, as a *field parameter*). An above-κ transition is not a leaf ⟹ it splits into sub-edges ≤ κ ⟹ recursion ⟹ a tree; a leaf = a κ-edge = a direct input to Contact. The condition "every above-κ transition *admits* such a split into κ-leaves" is **exactly A2**, extracted as the constructibility condition of Contact's κ-bounded input.

**A1 ∧ A2 = existence + nontriviality of Contact.** Contact exists and is nontrivial ⟺ (solvability of the per-edge contact = A1) ∧ (κ-bounded constructibility of the leaf input = A2).

**The honest residue (anti-laundering — TO BE HELD LOUDER THAN THE RECAST).** This is **not** "A1/A2 derived from the empty field" — it is a **status change** (postulate → interface condition of Contact), and the residue is ≈ the axioms themselves: (1) **A1-residue.** "Contact returns pass/fail" gives binarity and finiteness of the verdict but **not** domain-correctness (ii): binarity gives the falsifiable form's **codomain** condition, not the attained fail-extension that makes a criterion forbid — that rides on clause (ii) under contingency — and not *sensitivity* (a binary-but-insensitive criterion = the FM-3 false-PASS). This is the same residue as clause (ii) everywhere: part (ii) is apparatus-uncertifiable. (2) **A2-residue (two-part).** (a) κ as a field parameter is a cost-capacity premise, latent in A2 (Chapter 13 makes it an explicit per-unit magnitude), a property of the *actor/contact*, not of the state space — **not** derived from bare dynamics. (b) The decomposability clause (that every above-κ transition admits splitting into jointly-sufficient, separately Contact-checkable κ-leaves) does **not** follow from bare reachability (a trajectory exists, but not its factorization into contact-checkable κ-segments) — this is **≈ A2 itself**, merely moved from the field's definitions into the existence condition of a nontrivial Contact. The reading is still a **strengthening** — A1/A2 acquire a *reason*: to be the conditions of Contact — but honestly: **not derived from nothing; re-read as conditions of the seam** (status: postulate → condition); the new content is the status change, **not** a generation of A1/A2 from the empty field. The residue coincides with boundaries already named (FM-3-uncertifiability for A1(ii); the latent κ-cost for A2). **The axiomatic status of A1/A2 (Chapter 9) remains primary; this reading is the deep view, not a repeal.**

---

## 3. Agent necessity

Up to this point directed action has a world (S), a map (Ŝ), and one seam between them (Contact). This chapter derives what the theory of the seam forces: a necessary functional link that *supplies domain content* — the link whose carrier is called an **agent** (a human or an LLM; the protocol treats them identically, Chapter 14). The agent's status changes here from presupposed to derived; no formal result of Part II–III changes.

### 3.1. Where the agent was hidden

The two clauses inside A1 (§2.1): (i) decidability — the structural half (composition upward — Thm 1, Chapter 11); (ii) domain-correctness — passing ⟺ the real outcome. A1 grants the *existence* of a correct predicate, not *which one*; "correct" silently delegated the choice of criteria to an agent. **Causal correctness of a decomposition** — the notion this delegation is about — is defined here and used throughout: a decomposition is causally correct iff its claimed composition edges lie in S (each `(t,{tⱼ})` it asserts is real). Its full characterization as a *permanent boundary* — not an algorithm to be found — is developed in Chapter 8.

### 3.2. The derivation (steps d1–d6)

- **d1.** A faithful decomposition must agree with S (otherwise you verify the wrong thing) — the definition of causal correctness (§3.1).
- **d2.** S is a contingent fact about the world (Lemma 1).
- **d3 (excluded middle, not an added axiom).** The grounding of any contingent knowledge about S either *reaches back to the world* (contact — direct or mediated/inherited) or it does not. Complete by construction (excluded middle on "did the ground reach the world").
- **d4 (structure clears the "not-to-the-world" branch).** "Not to the world" = either purely formal derivation (but S ∉ the language of {A1, A2} — Lemma 1, ✗), or declaration (regress — Lemma 2, ✗), or coincidence (luck). Luck is unstable: S is contingent (Lemma 1: many S over one formal graph) ⟹ under a demand of *reliable* success luck is filtered out (probability → 1).
- **d5.** ⟹ reliable knowledge of S *reaches back to the world* = empirical contact. The derivation is **pinned** (Lemmas 1+2 + luck-instability + excluded middle), not "modulo a large epistemic premise". The single thin local residue is the step "luck is unstable" itself, and it is argued from the contingency of S.
- **d6.** The apparatus does not generate Ŝ-content (Lemma 1) ⟹ contact is carried by the agent. Binarity (Chapter 11) gives a probe its falsifiable form's **codomain** condition (a FAIL value exists in the scale; whether it is ever *attained* rides on clause (ii) under contingency) but not *sensitivity* to divergence from S (a binary-but-insensitive criterion = the FM-3 false-PASS) — discrimination remains the open part of clause (ii).
- **Conclusion.** Clause (i) ← the apparatus over Ŝ (S-independent; the Syntactic/Semantic verification levels, Chapter 13); clause (ii) ← only through contact ⟹ **the agent is necessary as the sole source of domain content for Ŝ** and as its interpreter. Contact is a **joint event**: the form ← the criterion (apparatus); the verdict ← the world; the positing/interpretation ← the agent (the agent is not "the sole source of contact").

### 3.3. Distributed falsifiability

Every node carries a falsifiable claim: a leaf (world = the domain), or a **compositional** claim (a non-leaf): "the children passed ⟹ the goal is delivered", whose world is the layer below. A top-level planner lives in compositional claims; its decomposition is a pre-registered hypothesis, and its failure (children passed, goal did not arrive) is attributed *to it*, not to the executors (the modes later named FM-1.d / FM-1.b). The composition law propagates the *verification form* up the tree (Thm 1); the *domain-correctness* of each node it does not certify (the Pragmatic level, Chapter 13) — that is falsifiable only by execution.

### 3.4. The anatomy of a decomposition

A decomposition is not a "slicing of work" but a **falsifiable claim of joint sufficiency** φ: "these children, plus their integration, satisfied, *constitute* the parent". The heart is φ, not the slicing; φ is what gets tested and what falls. *Three owners* pull apart what the single word mixes: **content** (which children, which φ) — the agent / Ŝ (the apparatus does not generate it, Lemma 1); **form** (well-posedness) — GFSO, certified by CHECK *before* execution; **truth** (does φ hold in S) — the world, never exact. Form is the negative space of the failure modes: (1) decidable criteria for the children (else FM-2); (2) explicit φ / joint sufficiency (else FM-1); (3) non-redundancy (part of well-posedness; the guard of FM-1.e); (4) explicit Dep — the couplings written, not hidden (children need not be orthogonal, but their links go into Dep); (5) ACCEPTED_RISKS (the boundary of the claim); (6) deadline coherence child < parent. *Two faces of the composition function:* the verificational `V(p) = AND(V(c))` (Thm 1) and the substantive/integrational (Dep, the "glue"). `V(p) = AND(V(c))` is clean only if the integration is itself covered by a criterion: **a forgotten glue criterion = FM-1** (a coverage hole, tagged FM-1.f in §12.2; the false PASS is a *consequence*, not FM-3, for there is nothing to lie about); an existing-but-insensitive integration criterion = the FM-3 false-PASS. *Termination:* a node becomes a leaf when its goal is within one agent's capacity to execute-and-check directly (A2) ⟹ **tree depth is agent-relative** (a stronger agent → a flatter tree; this meshes with interchangeability, §3.6). *Multiplicity:* the goal **underdetermines** the decomposition (many bases out of Ŝ); GFSO ranks only structurally (well-posedness, damping Λ·γ, attribution purity) and does not issue the one-true-decomposition (Lemma 1) — the world filters (faithfulness), colleagues compare (Chapter 26). A decomposition is dynamic: the tree is a snapshot of an ongoing estimate, a forward pass; re-decomposition is a structural update from the backward signal at the attributed level (§3.5).

**The generative act (what is irreducible in producing Ŝ/D).** Production of a decomposition = EXTERNALIZE ∘ EXPAND ∘ CONSTRUCT-Ŝ. **EXPAND** (search/refinement over Ŝ: A*/HTN) — [known]. **CONSTRUCT-Ŝ** — building the abstraction: reuse of a library/hierarchy is [known]; the bare *positing* of a new seam for a new goal out of a domain model is **[known]-as-heuristic** (LLM planners already do it, corpus-free and guarantee-free). Lemma 1 yields only *non-derivability* of the seam by the apparatus — **not** a GFSO tag for bare positing. The single GFSO remainder is **EXTERNALIZE**: writing out the load-bearing beliefs of the decomposition — **φ** (joint sufficiency), **Dep** (the couplings), **ACCEPTED_RISKS** (the scope exceptions) — as A1-checkable, *separately falsifiable, locally repairable* edges, *graded by faithfulness, not plausibility*. EXTERNALIZE does not *guarantee* the seam's faithfulness (Lemma 1; a seam is a pre-registered hypothesis, §3.3); "how to invent a *faithful* seam" = the omitted layer of decomposition-method quality (Chapter 8).

### 3.5. Two-sided attribution

Forward (top-down) = the error cascade (Chapter 18: ‖eₙ‖ ≤ (Λ·γ)ⁿ‖e₀‖). Backward (bottom-up) = a low-level refutation is attributed along the explicit composition (a child's failure breaks ≥ 1 criterion of *some* node — the node with the broken compositional claim, not provably the lowest); its carrier is the CHALLENGE/BLOCK signals (Chapter 14). Locality of correction (a correct upper node survives) is derived from composition/attribution, not from the cascade bound; the cascade result plus the feedback loop give only the stability of the channel (small-gain: gain↑ · gain↓ < 1 ⟹ BIBO, no infinite spiral). Bidirectionality is a **consequence of the structure**, not an addition.

### 3.6. What the model explains, what it predicts

**Explains.** Pre-theoretical success: the agent carried sufficient Ŝ-content plus implicit structure ("it worked because he was enacting the generation process's role"); "not always" — the thin structural half (the failure modes), out-of-distribution Ŝ-content, or poor solitary induction. The seven failure modes = the spectrum of the structural half's thinness (E1: 0/216 incidents needed an eighth). The Pragmatic-level boundary (Chapter 8) = half (ii), apparatus-uncertifiable ⟹ open-from-inside — the model supplies the *reason*.

**Predicts (falsifiably).** Agent interchangeability — but only relative to a faithfulness proxy *independent of the outcome*; otherwise it is a test of the protocol's verifier-separation, not a new prediction. Applicability boundary: structural success-content ⟺ applicable (sharpens the A1∧A2 domain condition). Global falsifier: sustained out-of-distribution success without the structural half and without learned faithfulness — the model asserts impossibility; *to avoid circularity*, "learned faithfulness" must be measured **independently of the success itself**, else any counterexample is re-explained after the fact.

**Consequence for the guarantees (a discipline-tie, not a weakening).** The results that use clause-(ii) faithfulness — Prop 6 ("signals are not noise"), Prop 7 / Mechanism 2 (γ < 1), Mechanisms 1/4 (enrichment) — hold **under the (ii)-faithfulness discipline**, exactly as Thm 1 does. This is not a hedge: the discipline (criteria track reality) is the agent's clause-(ii) task, and its violation is precisely the characterized FM-3 / Pragmatic-level boundary, not an external gap. The dependency is named explicitly and exactly — the guarantee is strong *under the protocol's own discipline*.

**Honest residues (boundaries of the model, not defects).** The agent's solitary induction (in aggregate — weak monotonicity, Chapter 18); tree depth is agent-relative; *which* slicing is faithful — non-derivable (Lemma 1); probe discrimination — the open part of clause (ii). The full register of named boundaries is Chapter 8. The model *explains/localizes* these residues, it does not close them: closing clause (ii) would be the re-labeling "incomplete by design, therefore complete" — exactly the mistake §3.2 refutes.

---

## 4. The five constitutive links and their completeness

### 4.1. The five links

Directed action *is* a chain of five links, none removable: **Link-1 goal** (G ⊆ X — *directed*) · **Link-2 build-Ŝ** (*informed*) · **Link-3 plan D over Ŝ** (*structured*) · **Link-4 execution** (rollout in S — *actual*) · **Link-5 contact** (verdict from S — *real*). Remove any one and what remains is not directed action (bare dynamics, blind reaction, no route, an unexecuted plan, or an open-loop guess). Minimality — by per-element counterexample, on a par with the basis-minimality argument of Chapter 10 and the independence witnesses of Chapter 12.

**The agent is not a primitive but an emergent scope-bundle:** a window over the process — a block partition of the tree of units, assigned as one scope of responsibility; nothing in the ontology distinguishes "agent A's units" from "agent B's" except the chosen scope boundary. The Chapter-3 result is *preserved while the subject dissolves*: the necessary *carrier* of domain content relocates into the links {Link-2 build-Ŝ, Link-5 contact} (Lemma 1: the apparatus does not generate; content and faithfulness enter only through these links).

**Contact is homogeneous modulo delay:** during planning every node is an untested hypothesis (edges of Ŝ); during execution contact flows up from the leaves, each node checked against its own realized aggregate; leaf vs non-leaf = *when* the contact arrives plus an extra compositional test, not *whether* there is one.

### 4.2. Completeness of the five links (covering axiom; honest grading)

Are the five links *all* of them? Yes — not by "we did not find a sixth", but by a covering principle in the same architecture as the failure-mode completeness (Chapter 12), built on the theory-model's own axis:

> **Axiom (completeness of directed action — covering).** Directed action is an intentional relation of a system-with-a-model to the world for the sake of a goal; exactly **two relata** ⟨system-with-model⟩ ; ⟨world⟩ ⟹ exactly **two modal sides** by excluded middle on map/territory: **REPRESENTATION** (what is in Ŝ) ⊕ **REALIZATION** (what is in S). This modal axis **is** the Ŝ-vs-S axis of the theory-model itself. The sum of the sides = exactly five links.

- **REPRESENTATION = {Link-1, Link-2, Link-3}** = the ternary argument structure of the predicate `Reaches(route, target ; medium)` = D · G · Ŝ.
- **REALIZATION = {Link-4, Link-5}** = the pair ⟨execution (system→world), contact (world→system)⟩.

**Honest grading against the CA1 standard.** Two of the three closure branches are **derived** to full covering-axiom strength (excluded middles): the modal branch (two relata ⟹ two sides) and the realization branch (direction in/out, no third). **The representational branch is BELOW that grade**: the completeness of the triple ⟨goal, Ŝ, D⟩ holds *modulo* the named covering axiom of **REACHES-ternarity**, which (a) is *poorer* than CA1 (no preceding orthogonality-and-exhaustion theorem — a bare assertion "REACHES has exactly three argument roles") and (b) carries a **loaded residue**: **START (the source point) is a genuine constitutive relatum** of REACHES (reaching has a source as much as a terminus), *folded* — not eliminated — into the "execution-anchored present" (the source = a degenerate relatum pinned by the current world state — Link-4) **by a declared modeling choice**. Reject the folding and the count 3⊕2=5 *breaks*; CA1's residue (the value/time edge) is local and does not touch its count. The triple is **co-extensive** with the planning-textbook definition ⟨initial, goal, model⟩ — an upgrade in *framing* (read as a reachability claim), **not** an independent derivation; the status "inherited by definition" is *re-stated and named as the axiom's residue*, not removed. Minimality is at full parity. **Full parity is NOT reachable this way** (attempts to eliminate START as a separate role are unsound: "start ⊂ route/medium, tertium non datur" begs the question; "start-unknown ⟹ contingent" conflates epistemic givenness with constitutive role). Full parity would need a from-scratch exhaustion theorem "what a representation of directed action must contain" that does not re-cite the planning definition — an open question, not a "push harder". What falsifies the completeness: exhibit a real directed action lacking one of the five links (yet still really directed), or carrying a genuinely independent sixth structural feature (a third modality / a fourth REACHES role / a third realization direction) — open-from-inside, like the Pragmatic-level boundary.

---

## 5. The continuous substrate (borrowed ground, marked [known])

> **Status of this chapter (three sentences that govern it).** The substrate below is a **[known]-borrowed control/viability apparatus** (Sontag; Aubin) — an absorbed sub-step ⊂ GFSO (Chapter 6), explicitly **not** GFSO's delta. **The operational discrete apparatus remains the operative primitive layer** — every formal result of Parts II–III is stated over it, the protocol is what executes, and the substrate is its *causal ground*, **not its replacement**; what this document reverses relative to v3.9 is only the *order of exposition* (the theory-model now leads), never the operative standing of the discrete pair. **This chapter is therefore deep ground, not the load-bearing path: a first-pass reader may go from Chapter 4 directly to Chapter 6 (or to Part II) and lose no derivation** — everything downstream cites this chapter only as ground, and the density here (basins, kernels, safety⊕liveness) is the borrowed machinery's own, not an entry fee of the theory.

### 5.1. The field of directed action

**The field is the tuple `(M, U, f, x₀, G, S, Ŝ, D)`**: `M` — a smooth manifold of domain states (implicit, never enumerated); `U` — admissible controls; `f : M × U → TM` — a controlled vector field, dynamics `ẋ = f(x,u)`, `u(·) ∈ 𝒰` (a controlled dynamical system, Sontag [29]); on this view **S is the flow of admissible trajectories** `S = { x(·) : ẋ = f(x,u), u ∈ 𝒰 }` — causality = the restriction of `f` to reachable directions. `x₀ ∈ M` — the start (the current state); `G ⊆ M` — the real goal region (ontic, exogenous, not given to the agent exactly). S is ontic, contingent, not given in advance — this is *the same* S as §2.2, read continuously. The derived object is the **capture basin** `Capt_S(A) = { x ∈ M : ∃u ∈ 𝒰, ∃T ≥ 0, x(0)=x, x(T) ∈ A }` — the capture basin in Aubin's sense (*Viability Theory*, 1991 [28]; Aubin–Bayen–Saint-Pierre 2011), standardly equal to the largest closed viability domain from which A is reachable.

### 5.2. The discrete relation is the shadow of basin chaining

In the bare field there are no goal points, no milestones, no decomposition — only the controlled flow; everything discrete lives on the functional scale `M/∼_G` inside the epistemic graph Ŝ. Continuously, a chain of regions `B₁, …, Bₙ ⊆ M` is **S-correct** for `(x₀, G)` if the basins chain: `x₀ ∈ Capt_S(B₁)`, `B₁ ⊆ Capt_S(B₂)`, …, `Bₙ ⊆ Capt_S(G)` ⟹ `x₀ ∈ Capt_S(G)` (composition of basins ⟹ reachability; the reachability variant of the Bellman principle / transitivity of reachability, [known]). **The canonical operational fact `(t,{tⱼ}) ∈ S` (§2.2) remains primary and is here unfolded as the discrete shadow of one link of this chain:** for a link with a *set* of co-children `{Bᵢ⁽¹⁾, …, Bᵢ⁽ᵐ⁾}`, joint sufficiency is `( ⋀ₖ Bᵢ⁽ᵏ⁾ attained ) ⟹ ∈ Capt_S(Bᵢ₊₁)`; `(t,{tⱼ}) ∈ S` ⟺ this implication is true (all children pass ⟹ the parent is really attained by *its* criteria — exactly the joint sufficiency of Chapter 11). On the operational view the edge stays a primitive of the apparatus; on the theory-model view it is the shadow of a continuous chaining fact. Nothing under Thm 1 changes.

**AND-soundness (the GFSO kernel) — the same thing as Chapter 11's reading, re-described over the shadow.** The object of each link with m co-children is the conjunctive set-level reachability fact `AND-soundness(i): ( ⋀ₖ₌₁ᵐ [∈ Capt_S(Bᵢ⁽ᵏ⁾) and attained] ) ⟹ ∈ Capt_S(Bᵢ₊₁)`. One *may* compress the m children into a single option `o = ⊗ₖ Bᵢ⁽ᵏ⁾`, and then AND-soundness ⟺ `Reach(o) ⊆ Capt(Bᵢ₊₁)` — a single fact; **but** the compression loses exactly the information the conjunction carries: which of the m components failed. Option models (Sutton–Precup–Singh [26]) / HTN methods (Erol–Hendler–Nau) formalize the correctness of *one* composite transition — one truth-maker, one falsifier; AND-soundness as a conjunction yields **m separately falsifiable** truth-makers plus the **integration implication** `(⋀ children) ⟹ Capt(parent)` — a separate failure carrier, not derivable from the m single Reach facts and not attributable to any single child. **Honestly:** `Capt_S` of a conjunctive goal is standard viability; the GFSO delta is **narrow** — not a new mathematical object but the **mandatory separate writing-out of the integration implication** as a self-standing, per-child-attributable, falsifiable claim (whose failure has two distinct routes, kept apart in Chapter 12: the implication *not written at all* = the coverage hole, **FM-1** at top level (§2.2-root, "a forgotten glue criterion = FM-1") — **not** FM-1.a, whose sub-clause presupposes an existing cᵢ with no responsible child; *written but not entailing* = the canonical FM-1.d "children exist but ⋀criteria ⊭ cᵢ"; the never-written case is tagged FM-1.f (§12.2)). Standard models *can* express it but do not *oblige* or *attribute* it; GFSO makes it **constitutive and mandatory at every level** (= the making-explicit value, Chapter 6). This is *exactly* the Chapter-11 reading — re-described over the continuous shadow, not replaced.

### 5.3. The functional scale `M/∼_G` (the ground of ACCEPTED_RISKS)

The micro-trajectory is neither observable nor needed in full. The **goal-relative equivalence** `∼_G` on M: `x ∼_G y` ⟺ x and y are functionally indistinguishable *for the goal G* (the same set of future G-relevant outcomes under any admissible control). A reference class ("the finish") = `[x]_{∼_G}` (~10²³ microstates). Discreteness is **real, but on the functional scale** `M/∼_G`, not on atoms. The discarded micro (differences *inside* a class) is the **canonical ACCEPTED_RISKS register (Chapter 13), read exactly:** the coarsening is **sound ⟺ `∼_G` is a bisimulation** with respect to `f` on the G-relevant σ-algebra (the quotient dynamics on `M/∼_G` is well-defined); a **scale leak = `∼_G` is not a bisimulation** (two ∼_G-equivalent states have different G-relevant admissible futures — "the detail bit the goal"). This gives the exact condition for *when* an accepted-risk coarsening is safe vs leaky.

### 5.4. Real joints = separators of the reachability flow (the ground of non-redundancy)

A closed `B ⊆ M` is a **separator** for `(x₀, G)` if every admissible trajectory `x₀ → G` crosses B; equivalently, through basins: **B is a separator ⟺ removing B disconnects G from x₀**, i.e. `x₀ ∉ Capt_{S∖B}(G)` ("forbid B — G is unreachable"). This is an **ontic fact**, the world's structure on the functional scale, **not the agent's choice**; joints are usually few — the flow "funnels" through narrow separators (reachability bottlenecks; [known] analogues: bottleneck states in option discovery [30], landmarks in planning [31]). Narrowness is defined (inclusion-minimality + small thickness along the flow). This reconciles "is decomposition a choice or a fact": **the joints are forced (ontic); granularity BEYOND the joints is free choice; a faithful decomposition cuts at the joints.** The canonical **non-redundancy** condition (Chapter 10) is the discrete shadow of this: an unremovable subgoal = a separator (removing it breaks the chain); a ballast subgoal = a non-separator. The operational condition stays primary; here is its continuous ground.

### 5.5. Faithfulness unfolds into three orthogonal axes

The canonical faithfulness `Ŝ_used ⊆ S` (§2.2) is the **edge** axis — the general form; continuously it unfolds into three orthogonal axes. **(1) Edge:** an edge `(B, B′) ∈ Ŝ` — a believed passage *from* B *to* B′ — is faithful ⟺ `B ⊆ Capt_S(B′)`, the orientation of §5.2's chain (the believed passage coincides with the real basin chaining); an unfaithful used edge `(B, B′) ∈ Ŝ∖S` is a wall. **(2) Node:** the waypoint itself is illusory — a class `B ∈ Ŝ` answers to no real separator/region of S; node unfaithfulness = the posited `Ĝ` (or any waypoint) does not answer to the real `G`/separator (the node gap `Ĝ ≠ G`; at the level of goal-setting = FM-1.b (defined §12.2; its predictability line and guard — STD-2, Ch. 13) — the "missing mitigation child" of the operational reading and the illusory waypoint here are one defect read at two scales: a node the faithful map required is absent or mis-posited) ⟹ edges into/out of B evaluate a nonexistent object. **(3) Scale:** the coarsening `∼_G` (the accepted-risk register) leaks — `∼_G` is not a bisimulation (§5.3). **How the axes relate:** node and scale are correctness conditions on the *carrier* of Ŝ itself (right vertices, right coarsening); edge is the correctness of the connections; node/scale **generate** edge failures (a bad vertex/coarsening ⟹ edges evaluate the wrong thing), not conversely — which is why `Ŝ_used ⊆ S` is the general form and the two other axes are its continuum extension (preconditions on Ŝ's carrier).

### 5.6. Two goal topologies: tree-attainment ⊥ cycle-maintenance

The canon works over goal-**attainment**: `x₀ ∈ Capt_S(G)`, reach `G` once — topology **TREE/DAG** (the κ-recursion terminates, a leaf = a κ-edge; = the operational D-DAG, Chapter 10). Continuously this is one of two goal types. The second is **maintenance (viability/invariance):** stay inside a viability domain `Ω ⊆ M` (`∀t ≥ 0: x(t) ∈ Ω` under suitable control; the object = the **viability kernel** `Viab_S(Ω)`, Aubin [28]) — topology **CYCLE** (an invariant set; it does not terminate). **The stitching:** the cycle is a *generator* of goals; the tree is the attainment structure of one generated goal: maintaining `x ∈ Viab_S(Ω)` under disturbances generates a **stream of reachability tasks** ("return to Ω", "parry threat j"), each a Capt-task with a tree; drop one link of the cycle = exit `Viab(Ω)` = collapse regardless of tree progress. **Do not confuse this with a graph cycle:** the viability cycle is a class of **GOAL** (an invariant set in state space), **not** a forbidden cycle in the decomposition graph D (that one ⟹ infinite recursion = an A1 violation, caught by the acyclicity check — a different object; D stays a DAG). Goals in a working environment are in general **exogenous**; self-generation of goals by persistence (**survival** = maintaining `Viab(Ω_survival)`) is a **degenerate limiting** case, not the center. *(The explicit `x₀` of the field grounds the source-role of START as the current state at substrate level; the representational residue — START as a folded relatum at the REACHES-framing level, §4.2 — remains a named boundary, not closed by this.)*

**The maintenance object (viability kernel), cleanly — parity with `Capt`.** Attainment is the predicate `x₀ ∈ Capt_S(G)` of quantifier shape `∃u ∃T` (a control and a *finite* time into G exist): satisfaction is an **event** (the moment T), the predicate **expires on that event** (a leaf = a κ-edge, the node freezes; this modal "spending" of an attainment predicate is a different notion from the graph-level *consumption* of a verdict that gates finality, §14.3). Maintenance is the predicate `∀t ≥ 0: x(t) ∈ Ω` of shape `∃u ∀t`; the object is `Viab_S(Ω) = { x ∈ Ω : ∃u ∈ 𝒰, ∀t ≥ 0, x(t) ∈ Ω }` (the largest closed subset of Ω from which Ω is holdable; Aubin [28]). Satisfaction is **never an event**: a standing condition, only *refutable* (by exiting Ω), never *completable* — the predicate **never expires; there is no terminal pass**. The asymmetry is strict and load-bearing: **attainment is a representative of the liveness class `◇G`** (positively satisfiable by an event, pass absorbing) ⊥ **maintenance is a representative of the safety class `□Ω`** (only-falsifiable, fail absorbing, pass never final). Dually (Aubin): exit from Ω is attainment of the complement — `Ω ∖ Viab_S(Ω) = { x ∈ Ω : ∀u ∃t, x(t) ∉ Ω }` (the region of guaranteed capture by the "bad"), and maintaining Ω ⟺ perpetually denying `Capt`-capture of the exit boundary. Maintenance is the **standing (non-consumable) dual** of attainment, not its subspecies.

**The generator relation (cycle ⟹ stream of trees), cleanly.** The field is disturbed (`ẋ = f(x,u,w)`); under disturbances the state drifts toward the kernel boundary. Choose a **safe core** `Ω_safe ⊂ Viab_S(Ω)` with a margin from the true boundary `∂Viab_S(Ω)` and a **watch surface** `Σ = ∂Ω_safe`. **Emission:** at the k-th crossing `t_k = inf{ t > t_{k−1} : x(t) ∈ Σ }` a task `τ_k` is generated = "from `x(t_k)` return to `Ω_safe`" — a **Capt-task** `x(t_k) ∈ Capt_S(Ω_safe)`, topology TREE, decomposable by the ordinary canon. The stream `Gen(Ω) = {τ_k}` is **indexed by time/events, not by decomposition**: the `τ_k` are not children of one parent in D but a sequence of *independent* D-DAGs, one per disturbance (each `D(τ_k)` remains a DAG — no violation; this is NOT a graph cycle). **The serviceability condition (the maintenance analogue of κ/A2):** the margin `dist(Σ, ∂Viab_S(Ω))` ≥ the state's excursion during one return execution **and** the emission rate ≤ the return throughput — the reaction must fit into the buffer between Σ and `∂Viab` *before* the next event. Maintenance is viable ⟺ `x₀ ∈ Viab_S(Ω)` **and** the stream is forever serviceable. The second is where maintenance fails with *sound* trees.

**The apparatus over maintenance vs attainment.** *Verdicts:* attainment — `V ∈ {pass, fail, ⊥}` with **absorbing pass** (terminal); maintenance — only **absorbing fail**, no terminal pass ⟹ operationally a maintenance goal is **not a task node** (a node would need an unreachable DONE) but a **standing generator** emitting root Capt-tasks. *AND-composition:* each `τ_k` composes normally (Chapter 11 unchanged). Maintenance itself **admits no static AND-decomposition into sub-maintenances:** `Viab_S(Ω₁ ∩ Ω₂) ⊆ Viab_S(Ω₁) ∩ Viab_S(Ω₂)`, in general **strictly** (a control holding Ω₁ may eject from Ω₂; Aubin) — and this is **not** a repairable FM-1 (a forgotten glue child): the "glue" here is instantaneous *shared control at every moment*, not an addable child criterion. Hence **the compositional handle that reduces maintenance to attainment is the temporal generator** (emission of attainments): it reuses the attainment machinery of trees, which already compose (this is **not** a claim that the generator is the *only possible* control of maintenance in general; quantitative set-invariance is an absorbed sub-step, Chapter 6). *Metrics:* on the `τ_k` — the event-based metrics as usual; over maintenance — an **aggregate layer over the stream** (worst-case margin, return latency, service rate vs disturbance density), scoped above any node (the analogue of the aggregate false-FAIL diagnostic, Chapter 24), not an event-on-completion.

**Maintenance failure (aggregate scope; the methodology holds).** The invariant can be breached — `x` exits `Viab_S(Ω)` — **while every `τ_k` passed and every tree was faithful.** Causes: **(a)** the margin `dist(Σ, ∂Viab)` was small — returns "succeed" against an overestimated kernel; **(b)** disturbances denser than the return budget (the real excursion > the estimated); **(c)** Σ did not cover the real exit direction. This is **still** a failure by the coarse cut (Chapter 7) — a used edge `e ∈ Ŝ∖S` — but the edge's carrier lies in the **Ŝ of the GENERATOR** (the schedule map: "margin/rate adequate"), NOT in the Ŝ of any `τ_k`. The cut holds, and each cause lands inside a class already named: **(c)** = FM-1.b (the watch surface answers to no real exit separator — the node axis, §5.5) / FORM class; **(b)** = FAITHFULNESS (real excursion > estimated — a wall the map did not show); **(a)** — margin/rate on the generator's *own* map — is **not** one of the three load-bearing FORM members {connectivity/Dep, φ-composition, non-redundancy}; it is a defect of **budget/deadline coherence of the generator's schedule** — item (6) of the §3.4 form list (a-priori checkable as deadline consistency, kin to the CHECK-3 deadline rule and horizon coherence — Chapter 13 / Chapter 25 pointers), routed there explicitly. **The novelty is the scope, not the axis:** the carrier is invisible to per-node validation (all `τ_k` pass) and lives in the coupling **emission-schedule ⨯ kernel-geometry** — a predicate over the *stream*, scoped above any tree; no per-tree failure mode instantiates it, though its class is the already-named FAITHFULNESS boundary (Chapter 8) at aggregate scope. The structural inversion: the safety invariant `□Ω` is held only by the **liveness-soundness of the regulator** — every disturbance parried *soon enough*.

**Completeness of the two topologies — at the level of CLASSES (safety ⊕ liveness).** A goal as a set of acceptable trajectories = a trace property; by Alpern–Schneider [known] every trace property = an intersection of **safety** (`□`, closed sets of traces) and **liveness** (`◇`, dense) — **the two CLASSES are exhaustive**. Attainment `◇G` and maintenance `□Ω` are the **one-sidedly finitely-decidable representatives** of the liveness and safety classes respectively: their verdicts are obtained in finite time only one-sidedly — attainment by a positively-absorbing event T (`◇G`), maintenance by a negatively-absorbing finitely-checkable boundary exit (`□Ω`); two-sided decidability does not exist. Alpern–Schneider is a **substantive decomposition theorem** (not a trivial excluded-middle partition): it makes **two classes** exhaustive — it does **not** declare the two object forms `◇G` and `□Ω` an orthogonal basis of every goal. A general goal is in general **richer** than the conjunction of these two representatives: the recurrent goal `□◇A` ("return to A infinitely often") is liveness, yet reduces neither to a single attainment `◇G` nor to `◇G ∧ □Ω`. ⟹ the canon carries **two one-sidedly finitely-decidable representatives of two exhaustive classes** — which is *why* maintenance generates trees: liveness subgoals `◇(return to Ω)` emitted by a safety parent `□Ω`. *(On the continuous object `Capt` has `∃T` without a bound = liveness; the operational deadline sharpens it to bounded attainment `◇≤dl G` — a safety tightening — but the class dichotomy is stated on the deadline-free object and untouched by this.)*

**The independence verdict (delineated) and the remainder.** Maintenance is **neither** purely subsumed **nor** purely independent: **the execution of maintenance is fully subsumed** (serviced by a temporal stream of ordinary Capt-trees over which the apparatus — V, AND, the seven failure modes, the metrics — works UNCHANGED); **the object and the generator of maintenance are genuinely independent:** (1) the predicate is safety (`∀t`, only-falsifiable, no terminal pass), not expressible as a root DONE; (2) it does not AND-compose (`Viab(∩) ⊊ ∩Viab` — a structural, not FM-1, gap) ⟹ it **forces** the generator; (3) it carries the emission-schedule object (watch margin + service rate vs disturbances) whose failure (a breach with all passes) instantiates no per-tree failure mode. Verdict: **the second topology is not an independent EXECUTOR but an independent GOAL-OBJECT-AND-GENERATOR.** **Survival** (`Viab(Ω_survival)`, Ω = "the operator keeps existing") is a **degenerate limit**: the emission source is reflexive, the generator is powered by the operator itself; the working environment centers on an **exogenous** Ω (an SLA, a regime corridor, holding formation) — survival is not load-bearing. The quantitative service-rate theory is control-theoretic (set invariance, Blanchini [35]), an absorbed sub-step ⊂ GFSO (Chapter 6), not a GFSO delta. Goals outside the two finitely-decidable representatives (`□◇A` and other non-finitely-decidable ones) are **not** covered by the object apparatus — a named boundary; the generator generalizes to them only as an *attainment-reducing* handle.

---

## 6. Positioning: the honest delta, the value, and the scientific method

*(This chapter develops, with its bounds, the identity stated in one sentence in the Introduction — the preview→full relation is deliberate; nothing here is derived from the frame, and nothing below is load-bearing for the formal results.)*

### 6.1. The honest [known]/[GFSO] ratio

The theory-model audit (Chapters 2–5, 7) checked, object by object, the boundary between the absorbed standard sub-step and the irreducible kernel. **GFSO absorbs standard planning as ONE sub-step** (EXPAND / search over Ŝ = Link-3), **rewritten in its own formalism** (Ŝ/S, faithfulness `Ŝ_used ⊆ S`, the edge `(t,{tⱼ}) ∈ S`); **GFSO is the encompassing frame, not a layer on top of planning** (containment: **planning ⊂ GFSO**). The absorbed sub-step reuses large and honestly-standard machinery: state space / goal / start, the *type* of the S/Ŝ relation (LTS / HTN-method relation), plan-as-search (A*, HTN refinement), hierarchical recursion (options / HRL), the Ŝ-vs-S loop / replan-on-mismatch, and the very *split* model ≠ world (MPC/RL carry it as an error-to-minimize) — all reductions to textbook planning and control (STRIPS, MDP, HTN [12], A*, MPC, model-based RL; only the HTN citation [12] is given here, the rest is common textbook machinery). But it enters **as a contained sub-step**, not as the frame: around it GFSO supplies what planning lacks — the faithfulness ontology, the failure taxonomy of Ŝ∖S, the composition law, the derived agent necessity, the methodology (verify-vs-explore / stop-and-replan). (The continuous control/viability substrate: `ẋ = f(x,u)`, Capt/Viab — Chapter 5, [known].)

**The irreducible delta of new machinery is narrow, concentrated in:**
1. **Joint sufficiency / AND-soundness** `(t,{tⱼ}) ∈ S` — that a *set* of children *jointly* constitutes the parent by its criteria; option models [26] formalize the correctness of *one* composite transition, not the joint sufficiency of a set (Chapter 11).
2. **The failure root `Ŝ∖S`** + the composition law `V(p)=AND(V(c))`-is-sound-iff-edge∈S (the propagating form itself is tautological, Chapter 11); the split (i) forgotten glue = FM-1 / (ii) insensitive = FM-3 (§2.2).
3. **Constitutivity** — the S/Ŝ (map/territory) split made *constitutive of directed action*: neither an error-to-minimize around a privileged true model (MPC / model-based RL), nor a vehicle of representation or an autonomous instrument of intervention (model-based philosophy of science — Giere, Weisberg; in its strongest form models-as-mediators, Morgan–Morrison, where the model already *is* an instrument for acting). The differentia is not action versus representation — those accounts have action too — nor plurality of models, which this theory also permits (rival Ŝ frames, §6.3). It is **modality plus singularity**: "constitutive" is a modal claim, not an emphasis — the S/Ŝ pair is Link-2 ⊕ Link-5 of a five-link chain none of whose members is removable (§4.1), whereas a mediator is an instrument one may put down; and rival estimates are judged through **one** seam (Contact) against **one** ontic S, with **one** failure locus (`Ŝ∖S`) and a verdict that is binary — a defect here is a **wall, not a dissimilarity**, where those accounts answer to functional adequacy or graded similarity.
4. **Agent-free recursion** — contact homogeneous-modulo-delay, the agent dissolved into a scope-bundle (Chapter 4).
5. **The EXTERNALIZE form** — the generative remainder: φ / Dep / ACCEPTED_RISKS as A1-checkable, separately falsifiable, locally repairable edges, graded by faithfulness rather than plausibility (Chapter 3).

**Why standard abstraction/method-learning does not subsume the kernel (per candidate).** Producing a decomposition = EXTERNALIZE ∘ EXPAND ∘ CONSTRUCT-Ŝ (Chapter 3). The candidates for reducing the generative act were checked object by object: **ABSTRIPS** [32] re-grades *given* predicates into a hierarchy → closes the reuse regime, not a *new* seam; **HTN-MAKER** [33] learns seams from a *corpus* with φ given as annotation (needs corpus + φ); **goal regression** [34] yields only preimages of *existing* operators; **HRL discovery** (option-critic, betweenness, feudal nets) invents intermediates, but in the reward-bottleneck grade, validated by *return*, not as an A1-seam with a falsifiable φ (by `Ŝ_used ⊆ S`); **LLM decomposition** (ReAct/ToT/least-to-most) posits new seams heuristically, corpus-free and guarantee-free = **[known]-as-heuristic**, isolating (not pre-empting) the EXTERNALIZE delta. In sum: bare seam generation is a [known] heuristic; the single GFSO remainder of generation is the **EXTERNALIZE form + the faithfulness grading**; there is no separate "invent-seam" primitive and no faithfulness guarantee (= the open decomposition-method-quality layer, Chapter 8). Lemma 1 gives only non-derivability by the apparatus, not a GFSO tag for bare positing (§3.4).

**What the ratio means (important).** The [known]-heavy ratio measures the *novelty of the machinery*, **not** the value — that is the making-explicit positioning (§6.2). "Narrow" qualifies **only the delta of new formal machinery** (the kernel above), **not** the scope, the value, or the containment direction (planning ⊂ GFSO).

### 6.2. The value = making-explicit

GFSO's primary value is **not** methodological novelty (the kernel is narrow, §6.1) but **making-explicit**: moving decomposition/planning OUT of an agent's private, unexamined, idiosyncratic intuition INTO a single *axiom-derived, consistency-checkable, faithfulness-graded* formal SYSTEM — applicable and mandatory at EVERY level. **Operationally this makes planning FALSIFIABLE** (the scientific method as a planning protocol): a GFSO plan is a set of pre-registered, separately falsifiable claims about the chaining (each with a real truth-maker in S and a defined falsifier-contact, §3.3) — not an irrefutable narrative of "it failed — but which part was wrong, nobody can say". The frame earns its keep **only** through three concrete dividends: (1) **coverage against the real joints** → the plan's silences become claims: everything the goal requires is either a written criterion with a responsible child, or a written accepted risk or scope boundary (§13.1) — so an omission is a *falsifiable absence*, and a seam cut off the joints is refuted post-contact as a ballast non-separator subgoal (the FM-1.e guard; the joints-target is non-constructive but **not vacuous** — Ch. 8). What coverage does not reach is the criterion nobody wrote (repairable once contact shows it — §2.2 (i)) and the criterion that cannot discriminate (§2.2 (ii)) — the latter being the irreducible residue, named, not unexamined; (2) **localization + attribution** → a failure pins the exact false belief and its owner, not diffusely; (3) **verify-vs-explore by stakes** (Chapter 13) → do not over-plan the cheap-reversible, do not under-plan the catastrophic. "A narrow kernel" and "a large value" are one object from two sides: narrow *as machinery*, large *as a universalized checkable discipline*.

**Positioning against the literature.** The planning literature formalized planning FOR MACHINES as optimization-over-a-given-model; it did **not** deliver a universal, axiom-derived discipline of consistency + faithfulness for *any* agent at *any* level. Domain instances exist (formal methods, TLA+, design-by-contract, Scrum — Chapter 25), but they are **instances**; GFSO is the general axiom-derived account of which they are instances (continuing the line **Scrum ⊂ GFSO**: Scrum *postulates and operationalizes* the discipline; GFSO *derives* it).

**The load-bearing empirical premise (→ E3).** Typical working methodologies are assemblies of past plans, usually never checked for internal consistency. **E2 tested the CONVERGENCE** of decomposition to a completeness-audited reference and yielded the method (bare-SEARCH ⊕ gfso-AUDIT, productized as `decompose()`); but **the value of the made-explicit discipline against private-unchecked assembly on coverage is NOT yet read off** (the reference was built bare — a confound); that measurement requires EXECUTION and is assigned to **E3**.

### 6.3. GFSO as the scientific method, formalized and generalized

**Claim.** A1 clause-(i) (§2.1) — a finite set of pass/fail criteria decidable in finite time — carries **one conjunct** of the decidable form of Popper's falsifiability requirement, and the pair must be stated exactly: falsifiability demands a *potential refuter* — **prohibition**, a non-empty fail-extension: the criterion must be able to come out false — and decidability demands that the verdict be *mechanically obtainable in finite time*. A1 carries both conjuncts, split across its clauses — prohibition under the contingency of failure; the derivation is given once, at §2.1. Hence the GFSO core (falsifiability checked by contact — Link-5 / the operator Contact, Chapter 2) is the formal content of the scientific method. **Science is the special case:** domain = nature; the theory-model (S/Ŝ, φ, contact) is held implicitly. GFSO is the same method with the theory-model made **explicit and mandatory**, and the domain lifted from "nature" to any directed action. The proportion: **science : nature = GFSO : any directed action.** *Decidability is orthogonal to probative force:* A1(i) fixes that a verdict is **obtainable**, never that it **discriminates** — a decidable-but-insensitive criterion is exactly the FM-3 false-PASS (§2.6; §3.2 d6); severity is the separate axis, below. What §6.3 owns beyond the split itself is the **guard question**: prohibition has no form guard — no CHECK tests a non-empty fail-extension, CHECK-8 testing the dual, satisfiability — so it is guarded only at runtime, through FM-3, whose discrimination demand is prohibition's *semantic* strengthening; and `docs/falsifiability.md` applies the same requirement **reflexively to this canon's own claims**, which is why that register is load-bearing rather than ornamental.

**What is inherited — and at what grade.** The mapping of the Popperian core is analytic: A1 was *built* as a falsifiability criterion, so "falsifiability requirement → A1", "hypothesis → φ" (§3.4) and "falsification → contact" (Chapter 2) could not fail to be found; this *positions* GFSO as a formalization of the method and by itself proves nothing. The single substantive addition inside the mapping is **decidability**; the other substantive content — the unfoldings and the generalization below — is what could have been absent. But the inheritance must be taken at the grade that survived. Falsifiability as a **single criterion of demarcation** between science and non-science did not survive its critique (holism — one never refutes a lone hypothesis; the historical objection that one anomaly does not rationally retire a theory; and the statistical case, below); Laudan pronounced the demarcation *problem* dead, and its revival (Pigliucci–Boudry and after) concedes the point about a single criterion while rejecting the abandonment of the problem — reinstating demarcation only as a multi-criterial cluster. **GFSO does not use A1 to demarcate science.** What Popper's critique retires is the target partition (science / non-science), not the demarcating *operation*: that survives here over **this theory's own domain** — the model applies ⟺ A1 ∧ A2 (Chapter 9). What is mechanical is narrower than that boundary and must not be confused with it (the **Popper row below** states the grade). A1(i) is nonetheless not ad hoc, being co-extensive with Contact's signature and forming, **with A2**, Contact's existence-and-nontriviality condition — A2 supplying the κ-bounded constructibility of Contact's input, clause (ii) being the apparatus-uncertifiable residue §2.6 names (§2.6; per that section's own residue clause a postulate re-read, not a derivation). The objections to demarcation therefore do not transport. What *is* inherited is the surviving core: the **prohibition structure** (a claim forbidding no outcome is empty — the register `docs/falsifiability.md` is its audit) and, from the neighbouring predesignation/use-novelty line rather than from the demarcation programme itself, **pre-registration** (§14). And the classical objections have structural answers here rather than concessions: the Duhem–Quine answer is structural, not a concession — its grade is stated in the **holism row below**; and a **probabilistic hypothesis**, which has no pass/fail of its own, acquires a decidable verdict once a **rejection rule is fixed** — whereupon the residual gap rule↔hypothesis is precisely GFSO's own clause-(ii) gap (a criterion may pass where reality fails — FM-3), and its quantification is exactly the one imported layer: the rule's error rate *on the passing branch* (type-II where the goal-claim is the retained null, type-I where it is the accepted alternative) **is** that criterion's false-PASS probability *at that point of the goal-false region*, the composite-region form being stated with the cardinal below. Statistical testing is thus neither excluded nor absorbed: it **instantiates** the canon's criterion↔truth split, and only its calibration is imported.

**What GFSO makes explicit (science carries implicitly).**
- **Composition.** A tree of hypotheses with joint-sufficiency chainings and a *separately falsifiable* integration implication `(⋀ children) ⟹ parent` per node, not derivable from the individual facts and attributable to the node (Chapter 11; §5.2 AND-soundness). This makes the **Duhem–Quine bundle explicit**: "which premise is false" — a question science carries informally — here has the structure of the tree + Dep.
- **Attribution of a refutation** to the node with the broken compositional claim (§3.5) — to the node, not to the premise; inside a node the holism recurses (Lemma 2).
- **The mandatory ACCEPTED_RISKS register** with invalidation conditions (Chapter 13) — the auxiliary assumptions are written out, not oral; science is not obliged to write them.
- **The theory-model**, usually implicit in a professional, — explicit and mandatory (Chapters 2–3): S/Ŝ, faithfulness, the necessity of contact.

**Classical notions — pointers, not re-description.**

| Notion (philosophy of science) | Where in GFSO | Status |
|---|---|---|
| Falsifiability requirement (Popper) | A1 clause-(i) (§2.1) = the **decidability** conjunct; the **prohibition** conjunct rides on clause (ii) under contingency (§7) — a condition on this theory's own domain (Ch. 9), **not** a criterion demarcating science from non-science | the prohibition structure inherited (as a conjunct A1(i) does not carry); the *science/non-science* partition not — the demarcating **operation** survives over the theory's own domain (mechanical only on a criterion presented with its decision procedure; whether a domain *admits* one is decided by **neither** clause — Ch. 9; Lemma 1) |
| Holism (Duhem–Quine) | explicit composition + Dep + ACCEPTED_RISKS (Ch. 11, 13): the bundle is **finitely enumerated per node**, its integration implication **separately falsifiable and node-attributable** (§5.2) | a structural answer, not only made explicit |
| Underdetermination (Quine) | the goal underdetermines the decomposition (§3.4); Lemma 1 | present |
| Test severity (Mayo) | *qualitative-binary* = FM-3 (a criterion must be able to discriminate, else it is not a test — decidability alone does not discriminate); the *ordinal skeleton* = the A2-tree induces a **dominance preorder** ⪰_dom on passed nodes (a node that survived a ⊇-superset of the **non-redundant** discriminating probes — its own criterion + the integration implication + the children's probes; non-redundancy per Ch. 10 / the pre-exec check — dominates; probability-free, but **coarser than Mayo**: equal-severity on same-region probes of different strength, which is exactly the cardinal gap). The *cardinal* (`SEV` = the probative force of a pass — `inf` over the goal-false region of the probability of a *more discordant* result; what it reduces to at `\|L\| = 2` — the paragraph below) — an import (nearest sibling = the FM-3-(ii) sensitivity / faithfulness residue, Chapter 8; the genus = the Pragmatic-level boundary) | the ordinal **skeleton** is internal; the cardinal — outside |
| Unification / consilience (Whewell, Kitcher) | *unification* (few mechanisms — wide reach) = the minimal non-redundant `Ŝ_used` (the structural ranking, §3.4; the E_FAITH term, Chapter 7); the *confirmational* component (converging support ↑ credence) — an import | unification present (coincides *typically*, not identically — a strongly-unifying decomposition need not minimize faithfulness risk); support — imported |
| Explanation / causation (D-N; Salmon; Woodward, Pearl) | the composition `⋀children ⟹ parent` = the deductive skeleton (the formal-entailment check = D-N validity); the causal surplus D-N cannot draw (the flagpole/barometer asymmetry) = the gap Semantic↔Pragmatic (Chapter 8): the Pragmatic level demands *real* composition — an **interventionist** claim, drawable in that currency but not *verifiable* from inside the apparatus (below) | the skeleton is inherited; the causal asymmetry = a named boundary, stated in the received currency |
| Research programmes (Lakatos) | the *correction dynamics* = backward attribution + locality + Λ·γ damping (§3.5; Ch. 7, 18) — a **structural analogue** (loop-gain stability, not growth of empirical content); the *normative verdict* "progressive vs degenerating" (novelty-defined) — an **import** (the graded-confirmation layer; deriving it from Λ·γ would double-count novelty); hard core / protective belt = a **partition** analogue (core = the non-attributed correct nodes, belt = the attributed sub-decomposition, locally re-derivable — STOP → MARK → RE-DERIVE, Ch. 7), **not** an immunization mechanism: Lakatos protects the core by decision, GFSO keeps upper nodes only while they are genuinely un-attributed — the opposite mechanism | the dynamics — a structural analogue; the verdict — imported |

**Severity, the import, and what is not method at all.** FM-3 yields not only the binary "discriminates / does not" but a **dominance preorder** `⪰_dom`: the probes a passed node survived — its own criterion, the separately falsifiable integration implication `(⋀ children) ⟹ Capt(parent)` (§5.2), recursively the children's — form `Probe(t)`, a set of *decidable* discriminators (A1 + FM-3), and `t ⪰_dom t′` iff `Probe(t) ⊇ Probe(t′)` over the **non-redundant** probes. It is **sound as an order** — reflexive, transitive, antisymmetric on probe-sets, only nested sets being compared: a probe *count* yields no severity ("10 weak < 1 strong") and incomparable sets are correctly left unordered. **It is the skeleton severity must respect, not severity itself** — it is *partial*, and *not cardinal* — no value, no threshold, and not the worst-case power the cardinal reduces to here. What **correlated** errors defeat is not the order but its **severity-reading**: the independence surrogate is structural scope-disjointness rather than statistical, so a ⊇-superset of probes need not be the more probative one and `⪰_dom` mis-orders *as a severity claim* (the q_D blind zone, Chapter 24) — a defect of the interpretation, not of the relation, which is why the machine-checked half is untouched by it. Its partiality is moreover not incidental: `Probe(t)` is built recursively over the children, so on a *fixed* tree the order runs largely with the ancestor–descendant relation, while the comparisons that matter most — **rival decompositions of one goal** — have typically non-nested probe-sets and are exactly the ones left unordered — whose operational consequence is drawn at §15.4: triage orders by the dependency cone, not by severity. *(Reflexivity, transitivity and **antisymmetry on probe-sets** are machine-checked axiom-free for **every** probe-set, by induction (`Grading.dom_refl_all`, `dom_trans_all`, `dom_antisymm_all`); partiality and count-independence are witnesses, and a fixed-arity carrier plus a negative control guards against vacuity — so `⪰_dom` is a preorder on nodes and a **partial order** on their probe-sets; the cardinal `SEV` over ℝ is deliberately absent, being the imported half.)* **The one import-in-principle layer is graded confirmation:** cardinal error statistics, predictivism / novel facts, consilience-as-support, and Lakatos's normative verdict. GFSO is pass/fail (|L| = 2, derived — Chapter 11), grades by **faithfulness, not credence** (Chapter 2), and accumulates no degrees of support; the ordinal skeleton stays internal (the row above) — **probability-free from A1 + A2** — while what is imported is exactly the **cardinal** — `SEV` as the Mayo row defines it, which here **equals** `1 − sup P(pass | ·)`. **Severity needs two things, and they stand at different modal grades here.** A1 supplies the discordance ordering only in its degenerate two-point form (fail is more discordant than pass) and **no measure at all**; A2 is structure, not measure. Over that ordering severity is definable and **equals** `1 − sup P(pass | ·)` — the results more discordant than an obtained pass being exactly `{fail}` — i.e. the worst-case power over the composite false region, the complement of the false-PASS rate; Mayo's severity is strictly finer *in general*, being evaluated at the result actually obtained rather than at the cutoff, and the two coincide only when the obtained result sits at the cutoff. A finer ordering would have to live on the **result** space, which no object of the apparatus carries: `|L| = 2` fixes the verdict's codomain, and any surplus above pass/fail is decision-irrelevant to intervene/¬intervene under the decision model of §11.4 (Inf-B — a claim conditional on that model, with its own falsifier). So the two imports stand at different grades: the measure is **contingently absent** — importable wherever a probability model exists — while the finer ordering is **unrepresented** here, absent rather than impossible. "Coarser than the cardinal" is only half the relation: where **no probability model is importable the cardinal is undefined and `⪰_dom` still orders** — the skeleton reaches domains error statistics cannot, at the price of resolution inside a scope region. q_V (Chapter 15) is a runtime relative frequency, not this severity — a different object from `⪰_dom`, which is tree structure. Two things are meanwhile **not** imported: **pre-registration** (use-novelty) is made explicit and carried by a protocol mechanism — **Inv-1**, not verifier ≠ executor: criteria are fixed at ASSIGN and no change is silent, every change being a logged re-ASSIGN that returns the node to OFFERED, voids the pending delivery and requires fresh consent (§14.4 Inv-1; §14.3 for the VALIDATING admissibility). The enforcement is graded, and the grade is exactly this: **before settlement** ASSIGN is admissible from VALIDATING (§14.3), so an issuer may revise criteria with the delivery in hand — at the price of a logged event, a voided *delivery* (no verdict has been emitted on that path) and a fresh consent and re-delivery; **at settlement** the base machine is immutable, DONE being terminal and admitting no ASSIGN; and under the R′ extension a reopen is doubly gated by non-consumption and `max_reopens`, a consumed DONE being finally locked. So this is strictly more than non-silence, and less than blanket immutability — while adversarial criteria-lowering *before* settlement remains the named open item (§24.2; Chapter 26's peer review is proposed, not operative). Only the weighting asymmetry (a prediction confirms more strongly) is imported; and **institutional enforcement** (peer review as an institution, replication practice, reputation) is not imported because it is not method — those are ways to make people *execute* the method, i.e. sociology, while replication *as an operation* is falsification by an independent agent, already carried by contact + verifier ≠ executor (Chapter 14). Aesthetics is a virtue of choice, not a criterion of scientificity.

**The Pragmatic level's object, in the received currency.** The Pragmatic level's claim is an **interventionist** one (Woodward; Pearl's `do`), and the canon's objects already carry that content: the composition edge `(t,{tⱼ}) ∈ S` (§2.2) is a conjunctive-intervention counterfactual — the `do`-reading licensed by the antecedent's *mode of realization*, the children being **completed** (Link-4) rather than observed, so the see/do gap does not arise at the level of the act — though what is set is the child's *criterion-pass*: where that pass is not domain-correct the `do`-reading over children degrades to a `see`-reading over verdicts, so the reading **inherits** the clause-(ii)/FM-3 faithfulness residue rather than escaping it (Lemma 1) — and the separator of §5.4 is its structural counterpart, a **reachability cut**, not a d-separator (delete a region and every admissible path to G is blocked). Both are shadows of the controlled dynamics `ẋ = f(x,u)`, whose manipulation handle `u` is what the currency's intervention variable formalizes without being one: the claims here are made over the discrete objects on `M/∼_G` inside Ŝ, where `u` is not a variable at all. What is interventionist is the **domain-soundness** half of Thm 1's conditions — never Thm 1 itself, which is S-free over Ŝ (§11.1): **joint sufficiency** = the conjunctive intervention succeeds in S; **non-redundancy** = difference-making against a **canonical** background rather than an existentially-searched one: the non-redundancy implication of Chapter 10 (`∀ tⱼ: V(tⱼ) = fail → ∃ cᵢ: cᵢ = fail`) is unconditional on the siblings' state, and joint sufficiency pins the witnessing background — all siblings passing — where `tⱼ`'s verdict alone moves the parent. It is stronger than the received existential form in that the difference-making background is *supplied by the definition* rather than merely asserted to exist; it is **not** stronger in quantifier — at a background where another sibling already fails, the parent is insensitive to `tⱼ` by the AND law; ontically (§5.4) it is separator-hood in the flow, a formulation needing **no variable set at all**, so the received account's variable-relativity is absent from the definition and returns only at verification. The currency's three presuppositions are **located on already-named canon objects, not discharged by them**: (a) *modularity* — a conjunctive intervention is well-posed only read surgically, with no side path from the children to the parent's criteria, and only where setting one child does not rewrite another's mechanism; this is not assumed away but **declared** — Dep carries the known couplings, CHECK-8 the consistency of the joint setting, an undeclared coupling is a relation defect at the formula level (FM-2, §12.2/§12.8) exactly where it makes the children's criteria jointly unrealizable as written, and otherwise carries only its runtime face FM-5 (q_Dep asks "are all Deps declared?", and BLOCK registers the discovered edge — Ch. 15), a basis rather than a partition (§12.4); where the unwritten item is the *integration criterion itself* the case is the coverage hole of §2.2 case (i) — FM-1.f, not FM-1.a, whose sub-clause presupposes an existing cᵢ with no responsible child (§12.2) — and the residue is the faithfulness boundary (§2.2(ii), Chapter 8); (b) *scale* — such claims lift to `M/∼_G` only when the quotient is exact, the condition being `∼_G` a bisimulation (§5.3), which the canon states and does not certify, so a scale leak is a leak of the causal reading too (§5.5); (c) *invariance range* — a causal generalization is asserted over a declared range of interventions, and ACCEPTED_RISKS with its invalidation conditions is exactly that declaration for the perturbations that carry an estimable P (a scope boundary, having no such P, is a different object and goes to the goal's own criteria under CHECK-1 — §13.1 — an analogous writing-out, not the same register); the residue here is the same as everywhere: the declared range is itself an Ŝ-claim, so `declared ⊆ real` is not certifiable a priori (Lemma 1), and exceeding an undeclared range is a wall met at contact — which is why the register carries invalidation conditions rather than a guarantee. The gain is that **formulation and verification separate**: the Pragmatic level is not an appeal to "domain knowledge" but a claim well-posed *relative to a fixed carve*, of which only verification-from-inside is unavailable — an interventionist claim is a fact about S, which A1 + A2 do not fix (Lemma 1). `do`-calculus computes from a *given* graph; here it is Ŝ, **posited, not given** (faithfulness in this canon's sense, not the homonym of constraint-based discovery), so the counter-move that bites is **causal discovery** — an instance of Chapter 8's approach vector, failing for its reason: it presupposes the carve (CONSTRUCT-Ŝ).

**One shared boundary.** The context of discovery — how to *generate* a faithful seam/hypothesis — is outside the model for **both**: science has no formal theory of hypothesis generation (Reichenbach: discovery is not logic); in GFSO it is the omitted decomposition-METHOD-quality layer (Chapter 8); here too belongs IBE as a *selection move* and every generative act of seam-positing. The boundary is **shared**, not dividing — and the commonality reaches the boundary's **structure**, not only its existence: for both, what remains logic-free is just the throw of the concrete candidate, compressed by the writable scaffold (Chapter 8) — and this is confirmed from the other side: the choice of the variable set / carve is an acknowledged open problem of the interventionist literature itself, not a GFSO-specific concession. *(The classical image "carving nature at its joints" — Plato, Phaedrus 265d–e — is an illustrative pointer, like the other classical notions here, not a load-bearing parity.)*

**Named presuppositions of the mapping (honest, not discharged).** (i) The mapping covers science's method only where the outcome is **decidable** (A1); *understanding as a non-instrumental goal* without a finite pass/fail sits on GFSO's **own ¬A1 domain boundary**, not inside the captured method. (ii) The mapping presupposes a **stable exogenous S + a fixed A1 standard**, thereby taking the rational-reconstruction reading (Popper/Lakatos) **against** strong Kuhnian incommensurability: rival Ŝ frames are commensurable *through S* (Contact judges any posited edge against one ontic S — SINGLE-SEAM, Chapter 2). A substantive position, not a neutral transcription.

**The reflexivity trap.** GFSO applied to itself yields **consistency, not self-justification**; reflexion is soft corroboration, no proof (§3.6: measure independently of the success itself; "incomplete by design, therefore complete" is the forbidden move).

**The implication.** Science is neither an alternative to GFSO nor a superset: it is the same method, whose theory-model GFSO makes explicit and whose domain restriction GFSO lifts. Status — **structural positioning, adversarially tested ◪** (the core is analytic; the unfoldings and the generalization are substantive). The adversarial search for an escaping element of the method **was run** (prediction/accommodation, novel facts, consilience, explanation/IBE, measurement, replication, theory-ladenness, research programmes/paradigms, **causal discovery**): **no escaping primitive of the method was found** — every candidate is either captured by existing structure (theory-ladenness = SINGLE-SEAM; explanation = composition + the Semantic/Pragmatic gap; Lakatos's correction *dynamics* = backward attribution + Λ·γ) or folds into exactly **two already-named remainders** (the causal Pragmatic-level boundary; one graded-confirmation layer — where Lakatos's normative **verdict** also lands) or into the discovery boundary / the ¬A1 domain — **where causal discovery lands**: an approach vector to the causal boundary that does not close it (Chapter 8: "none of it a closure"), because it presupposes the carve (CONSTRUCT-Ŝ), and that carve *is* the discovery boundary. The mapping holds — under the two named presuppositions. The analyticity of the core and the absence of a *behavioral* derivation (that GFSO *generates* scientific practice) are **retained**. The Newton ⊂ GR analogy is bounded the same way (§25.2).

---

## 7. Methodology: the forced discipline

Out of the ontology (Chapters 2–5) a discipline of producing-and-executing decompositions follows *by force* — not a best practice but a forced optimum.

**Completeness of the failure points (the coarse cut, derived).** Any failure is a used edge `e ∈ Ŝ∖S` (§2.2). It is in Ŝ∖S for one of two reasons (excluded middle on "does the edge violate Ŝ's *own* well-formedness"): **FORM** (the decomposition is internally defective — a wall on *your own* map; catchable a priori over Ŝ at cost `c_check`) ⊕ **FAITHFULNESS** (the decomposition is clean, but the Ŝ-edge is denied by S — a wall the map did not show; opened only by contact, Lemma 1). The cut is **derived** (= the validity ⊥ faithfulness axis). Inside FORM — the **load-bearing** interior of well-posedness over the map is {connectivity/Dep, φ-composition, non-redundancy}, the three members that carry the composition claim (the Chapter 3 form list, compressed — joint sufficiency enters as the φ-composition member, the written couplings as Dep-connectivity); the list's remaining members — decidable criteria (A1), the ACCEPTED_RISKS register, and deadline coherence child < parent — are a-priori over Ŝ by the same test and therefore FORM as well, but they do not carry the claim. The FORM class is identical to the *validity* class — one fact, two labels. The a-priori-catchable faces of the internal modes sit on the same side by the same test — they violate the map's own well-formedness: mutual satisfiability of the children's criteria (FM-2's Semantic-level face, CHECK-8) belongs to the φ-composition member; the propagation shape (FM-4) is guarded structurally over the map (acyclicity + Thm 1). Inside FAITHFULNESS — (i) the coverage hole / (ii) the insensitive edge (§2.2). The fine seven-mode taxonomy is complete *modulo* the covering axiom CA1 (Chapter 12; E1 0/216). The irreducible remainder is the faithfulness residue.

**The forced discipline (two error classes → exactly two mechanisms).** (F1) the two classes have orthogonal epistemic access; (F2) error compounds multiplicatively down the tree (Chapter 18); (F3) discharging FORM has a nonzero graded cost `c_check` (Chapter 13; latent in A2). Hence:
1. **Front-load FORM** on the executable segment, discharging to the `c_check`-justified level (always the Syntactic level; into the judgmental Semantic level where the marginal cost < the prevented risk). Strict dominance holds only in the cheap-check limit `c_check → 0`; above it this is the **verify-vs-explore** tradeoff (Chapter 13), not "always to the end".
2. At a **wall** (a contact verdict `e ∈ Ŝ∖S`): **STOP** (break the cascade — Chapter 18) → **MARK** locally (make the verdict load-bearing; locality comes from the EXTERNALIZE form) → **RE-DERIVE** (re-run the FORM check over the updated Ŝ) → only then proceed. Never continue on an un-updated plan (else you re-carry an *avoidable* FORM class on a map you already know to be false).
Exactly two mechanisms because the coarse cut yields exactly two classes; *how far* to push the FORM mechanism is the verify-vs-explore slot.

**Optimality (exact, not inflated).** Stop-and-replan with front-loaded FORM **minimizes the total realized cost over the knowable** — `c_check + E_FORM + E_FAITH`, *not the error itself*: (a) FORM is discharged to the level where the marginal `c_check` undercuts the marginal prevented FORM risk (`E_FORM = 0` *only* in the cheap-check limit); (b) `E_FAITH` is damped to the cascade minimum `(Λ·γ)ⁿ` for the S-fixed set of walls. **NOT** "always E_FORM = 0", **NOT** "never fail" (Lemma 1), **NOT** a global optimum over all plans, **NOT** uniqueness among faithful decompositions (§3.4 multiplicity). The free remainder (orthogonal, forcedly free): speed, the route among faithful decompositions, the front-load granularity above the "executable segment" floor. The first-person stop-and-replan / front-load discipline is exhibited as a *forced instance* of this optimum (each load-bearing clause is a [FORCED] instance). Cost composes as an edge decoration (estimate-in-Ŝ vs realized-at-contact) — it is **not a sixth link** (Chapter 4; Chapter 13).

---

## 8. Named boundaries

**The criterion (stated once, applied uniformly).** An item is a **boundary** — a result rather than an open problem — iff the canon exhibits an **impossibility argument from A1 ∧ A2**: a demonstration that the closure is *unavailable from the axioms*, in the Lemma 1 form (the object is not definable in the language of A1 + A2) or the Lemma 2 form (every declarative closure is a fresh instance of the same question). "We looked and did not find", "known to be hard", and "not yet built" are **not** boundaries; they are open problems and live in Chapter 26. The criterion is stated because the alternative is a framework unfalsifiable *in aggregate* — if every failure may be filed as a named failure mode, or a named boundary, or outside A1 ∧ A2, and nothing says when the middle label is earned, the taxonomy closes itself by fiat. Applying the criterion **un-dilutes** the entries that do earn it.

Three kinds sit on this list, each tagged per entry, plus one entry that is a *split*. Besides the **boundaries** proper: **disclosed postulate residues** — the named edges of the covering axioms (§1.4, Chapter 27), not impossibilities but *declared placements*, listed here because silently closing one would be the same laundering, the disclosure being what keeps the postulate honest; and one **domain boundary**, the criterion's third bucket above (the goal lies outside A1 ∧ A2 rather than being un-closable within it). The split entry is decomposition-method quality, whose two halves fall on opposite sides of the criterion and are labelled as such.

Closing an item that meets the criterion = the mistake "incomplete by design, therefore complete" (§3.6), which the model itself refutes. These are **results** — permanent or characterized — not holes to be patched.

- **The faithfulness residue** — *boundary*. The domain-silent FM-3 false-PASS (a present-but-insensitive integration edge, §2.2 case (ii)): a priori catchable by *no* discipline (Lemma 1); it can pass silently even at contact. = half (ii) of the Pragmatic-level boundary below. A permanent boundary, not a hole to patch.
- **Level-2 causal correctness (the Pragmatic-level boundary; relocated here from the open-problems list — it is a boundary of the first kind, not an open task)** — *boundary* (Lemma 1 + Lemma 2). The Syntactic level (coverage/topology checks) is a mapping; the Semantic level (formal entailment under a declared composition function) is implication-checking. **The Pragmatic level — causal correctness — is a characterized boundary, not "an open problem" in the sense of "find an algorithm".** Causal correctness of a decomposition is a claim about the real composition of truths along the tree (§3.1) — the domain model; the axioms A1 (predicate decidability) and A2 (splittability) by construction do not determine that composition. So the Pragmatic level is formally underivable from A1 + A2 and cannot be closed by any purely declarative extension: every declaration is itself a decomposition whose causal correctness is a fresh Pragmatic-level instance (Lemma 2). The approach to it runs through the empirically learned: LLM induction/abduction, domain ontologies under verification, q_D as runtime convergence, institutional learning — all in the apparatus (Chapter 15), none of it a closure. This is a formally irreducible boundary, not a temporary gap; Chapters 2–3 supply the *reason* it is forced and what the agent must deliver.
- **The representational branch (sub-CA1)** — *disclosed postulate residue*, not an impossibility: the canon itself grades full parity "an open question, not a 'push harder'" (§4.2), so what is permanent here is the *disclosure* — the poorer REACHES-ternarity axiom and the loaded START relatum folded by a declared modeling choice — not the unavailability. The completeness of the triple {Link-1, Link-2, Link-3} holds only modulo that axiom. Not full parity.
- **The CA1 residue** — *disclosed postulate residue*. The value/time partition for trace predicates — an edge of the definition (Chapter 12); local, does not touch the coarse cut. The single clock is **off this residue** (discharged — Chapter 12/27): the count of the three operational phases is axiom-free; what stays outside the taxonomy is verdict atomicity/purity as protocol dynamics (Chapter 14), not axis completeness.
- **Decomposition-method quality** — *split*: the **faithfulness** half is a boundary (Lemma 1 — no a-priori discipline certifies it), while the **generation-procedure** half is empirical and partly E2-closed, i.e. an open problem in the Chapter-26 sense. "How to invent a *faithful* seam" — the omitted layer: EXTERNALIZE *formats and grades* a seam but does not *guarantee* its faithfulness (Chapter 3; Lemma 1). **E2 closed the effective PROCEDURE of generation** (bare-SEARCH ⊕ gfso-AUDIT → `decompose()`, empirical convergence to a reference) — a procedure, **not** the logic of discovery: the logic-free leap of first positing a seam **remains**. **The seam's faithfulness to the real domain** is a separate matter (E3, the engineering demo), **not** a finalization residue.

  What is omitted is the *method of generating a faithful* seam, not the *whole* structure of generation; the context of discovery (Reichenbach: discovery is not logic) is **neither formless nor "partially solved"** — it is already-present structure re-read from the discovery side, plus one status lift. Three conflated things, separated: **(a) the generation method** — E2-closed as a *procedure* (SEARCH proposal ⊕ AUDIT form-check; **not** a logic of discovery); **(b) form/well-posedness** — the GFSO a-priori CHECK (justification, `c_check`); **(c) faithfulness** — contact only (Lemma 1, permanent). Discovery sits in (a); (b), (c) are justification. What stays logic-free is exactly the **first positing of a concrete candidate joint for a genuinely new goal** (the bare CONSTRUCT-Ŝ leap) — the same one science has. It is **compressed by the already-canonical scaffold**: (1) **the status lift — the target norm "cut at the joints"**: a faithful seam *is* a real separator `x₀ ∉ Capt_{S∖B}(G)` (§5.4); read from the discovery side, "cut at the joints" rises from an ontic fact to a **non-constructive norm-target** of seam generation — the target is **non-constructive** (finding a separator is contact-bound, Lemma 1) but **not vacuous** (non-vacuity inherited from non-redundancy: a seam off the joints = a ballast non-separator subgoal, falsifiable post-contact, the FM-1.e guard) and is only *co-aimed at / approximated* by [known] heuristics (landmarks [31], bottlenecks [30] approach the joints without guarantee), never *steered-as-algorithm*; (2) **the form filter** (b) prunes candidates before contact (Chapter 7); (3) **the structural rank** (well-posedness, Λ·γ, attribution purity — §3.4), faithfulness-agnostic; (4) **reuse** of previously-contacted joints ([known]). The scaffold **localizes** the discovery remainder; it does **not** close it. *(The Plato pointer stays illustrative — §6.3.)*
- **Goals outside the two topologies** — *domain boundary*, the criterion's **third** bucket rather than its second: `□◇A` recurrence and other non-finitely-decidable goals have no one-sided finite-time verdict, so they fail A1's decidability clause and lie **outside** A1 ∧ A2 (Chapter 9), rather than being un-closable within it. It is listed here, not merely at Chapter 9, because it marks the edge of the *object* apparatus specifically, and because the contrast with maintenance is exact: `□Ω` is equally non-two-sidedly-decidable as a standing predicate, yet the canon carries its reduction — it is not a task node but a generator emitting bounded-attainment tasks, each an A1 condition (§2.1, §5.6). For `□◇A` no such reduction is carried: the generator reaches it only as an attainment-reducing handle, never covering it. Named-uncovered by the object apparatus (§5.6).
- **Cardinal severity** — *boundary*: A1 supplies the discordance ordering only in its degenerate two-point form and **no measure at all**; A2 is structure, not measure. A permanent import (needs a probability measure over outcomes / ℝ) — §6.3; read at the triage decision, §15.4.
- **Adherence dynamics (α)** — *boundary*. Every Part-III guarantee is monotone in α and nothing in the model sets it (§18.1). Closing this needs a utility model over actors — costs, horizons, discounting — which A1 ∧ A2 do not supply: the same species as cardinal severity. The measurable half (α is an observable of the graph) is derived and stated at §18.1; the decay dynamics themselves are an import of the Prop 3/4/8 layer, not a canon result.

---

# Part II. The Apparatus as Consequence

## 9. Axioms, operationally

*(These are the same two facts that Chapter 2 read as the two existence conditions of the contact seam — stated here in their primary, operational register over tasks. One fact, two readings; nothing is derived twice.)*

**Axiom A1 (verifiability).** Any organized activity is directed at a goal whose attainment is checkable: there exists a finite set of conditions, each decidable in finite time, each returning pass or fail.

**Axiom A2 (decomposability).** There exist goals whose complexity exceeds the capacity of a single agent. Such goals are attainable only by splitting into parts, each within the capacity of some agent.

**A1 as two clauses.** (i) **decidability** and (ii) **domain-correctness** — derived at §2.1, graded at §6.3. Clause (ii) is where the choice of criteria is delegated to whoever writes them, and so the entrance to the theory-model, Chapter 3.

**A2 as a capacity-cost boundary (S/Ŝ notation).** "Complexity exceeds the agent's capacity" is a *cost* premise: a goal splits because doing it whole exceeds the capacity budget. Cost is thereby **constitutive** of directed action (it is what A2 asserts), not an add-on; the theory-model makes it explicit as a *per-unit* magnitude (Chapters 7, 13). The S/Ŝ pair, faithfulness `Ŝ_used ⊆ S` and the edge `(t,{tⱼ}) ∈ S` — the operationally primary primitive of the apparatus — are stated at §2.2; A1/A2 are there read as the **existence conditions of the single contact seam** (SINGLE-SEAM, Chapter 2), which is not a replacement for the operational apparatus but two views of one object.

**Definition (HVP).** A Hierarchical Verifiable Process *(v3.9: HBP)* is a process satisfying A1 ∧ A2: a verifiable goal that requires decomposition.

**Boundaries of the model.** The model applies ⟺ A1 ∧ A2. Under ¬A1 (no verifiable outcome: "improve the culture") — outside the model. Under ¬A2 (the task is trivial: one agent suffices) — the model is superfluous. Reformulability: "improve the culture" → outside; "cut attrition from 25% to 15% in 6 months" → inside.

---

## 10. Primitives and the basis

*(From the foundation to the basis. Chapter 4 fixed the five links; Chapter 2 fixed A1/A2 as the seam's conditions. The primitives below are their operational precipitate: Link-1 (goal) precipitates as the criteria of a Task; Link-3 (plan over Ŝ) as the Decomposition function with its DAG; A2's κ-recursion as delegation and the hierarchy; the couplings between branches as Dependency. The derivation from the axioms below is the same derivation in its primary register — re-motivated, not repeated.)*

Each primitive is motivated by the axioms. The axioms ground the *necessity* of the structures; the concrete form is a consequence or a justified design decision.

**Task (T).** A structure t = (spec, criteria, deadline), where criteria = {c₁, …, cₖ} is a finite nonempty set of decidable predicates cᵢ : Result → {pass, fail}.

*From A1:* activity is goal-directed → spec. The outcome is checkable → criteria (a set of decidable predicates). Activity is finite → deadline (the deadline is a design decision, but activity without a time bound is indistinguishable from inactivity).

**Decomposition (D).** A function D : T → 𝒫(T) splitting a task into subtasks. D(t) = ∅ ⟹ t is atomic. The graph of D is a DAG (a cycle → infinite recursion → an A1 violation).

*From A2:* complex tasks demand splitting.

**Correctness of a decomposition** — the central definition. D(t) = {t₁, …, tₙ} is correct under two conditions:

1. **Joint sufficiency (coverage):** ∀ cᵢ ∈ criteria(t): [∀ tⱼ ∈ D(t): V(tⱼ) = pass] → cᵢ = pass. All children pass ⟹ every parent criterion is satisfied.

2. **Non-redundancy (necessity):** ∀ tⱼ ∈ D(t): V(tⱼ) = fail → ∃ cᵢ ∈ criteria(t): cᵢ = fail. No ballast subtasks: the failure of any child breaks the parent. (Continuous ground: an unremovable subgoal = a separator `x₀ ∉ Capt_{S∖B}(G)`; a faithful decomposition cuts at the joints — Chapter 5.)

Non-redundancy is a requirement on the design of criteria: if tⱼ can fail without affecting the parent, then criteria(tⱼ) contains conditions unrelated to criteria(parent) — a decomposition defect.

**Delegation (Del).** A function Del : T → A assigning each task exactly one agent.

*From A2:* subtasks must be executed → each has an executor. Uniqueness (exactly one accountable party) is a design decision: if Del(t) is ambiguous, accountability diffuses. Recursive D + Del generates a hierarchy — a consequence, not a presupposition (Simon, 1962: near-decomposability).

**Dependency (Dep).** An acyclic relation Dep ⊂ T × T. If criteria(t_b) references the result of t_a, then (t_a, t_b) ∈ Dep. Coherence: (t_a, t_b) ∈ Dep ⟹ deadline(t_a) < deadline(t_b).

*From T + D:* D fixes the vertical links (parent → children). Dep fixes the horizontal ones (between branches). Dep carries unique information about causal dependencies not contained in D — an independent primitive.

**Validation (V).** A function V : T → {pass, fail} defined through the criteria:

```
V(t) = pass  ⟺  ∀ cᵢ ∈ criteria(t): cᵢ = pass
```

V is not a separate primitive but a function induced by T. Until checking completes, V(t) = ⊥ (undefined). ⊥ is not a third value of the scale but the absence of a value: Thm 1 operates only on tasks with V ≠ ⊥. The *source* of V's binarity is the definition above (a conjunction of decidable predicates, A1); the *defense* against a graded scale is Chapter 11.

### 10.1. The structure of the basis

The canonical representation of an HVP: the tuple (T, D, Dep, Del, V).

| Source | Primitive | Status |
|---|---|---|
| A1 | T (tasks with criteria) | Fundamental |
| A2 | D (decomposition) | Fundamental |
| A2 | Del (delegation) | Fundamental |
| T + D | Dep (dependencies) | Independent |
| A1 + D | V (validation) | Derived |

### 10.2. Minimality of the basis

**Claim (minimality).** The basis {T, D, Dep, Del} is minimal: removing any element → a loss of expressiveness.

*Argument (constructive).* For each element, a counterexample: a class of HVPs not describable without it.

| Remove | Loss | Counterexample |
|---|---|---|
| T | No objects — an empty model | Any HVP |
| D | No hierarchy — Thm 1 impossible | A task with > 1 level |
| Dep | Causal order inexpressible | "A before B" across branches |
| Del | No accountable parties — no accountability | Any HVP with > 1 agent |

**Independence.** Each carries unique information: T = what/how to check, D = how to split, Dep = causal order, Del = who is accountable. None is expressible through the rest.

**Completeness (a claim).** Both axioms are exhausted: A1 → T; A1 + D → V (the §10.1 row: V is induced by the criteria along a decomposition); A2 → D, Del; T+D → Dep. The organizational concepts examined are expressible through the basis: resources → Dep/criteria, time → deadline + Dep, risks → the ACCEPTED_RISKS register, statuses → V. One honest note on that row: the register is an annotation the *decomposition* carries (§13.1) and a packet field (Inv-1), not a relation over tasks — so it adds no primitive, but neither is it displayed by the signature of D as stated here; it is named rather than hidden. No sixth primitive from A1–A2, irreducible to the basis, has been found.

**Remark (the uniqueness question is posed in Chapter 26).** A strict proof of minimality — and, a fortiori, of the *uniqueness* of the basis — would require defining the space of "all organizational primitives". The argument above is constructive (concrete losses on removal, independence, no counterexample found) and closes **minimality**. **Uniqueness is open**; its correct model-theoretic formulation (bi-interpretability of signatures) and the wall that makes the naive "there is no sixth primitive" unprovable from inside are in Chapter 26. Dep-reachability Dep\* (the transitive closure of Dep, non-FO) is **not** a sixth-primitive candidate — under either frame it fails to be an adequate rival basis (Chapter 26), and is a derived non-FO query of the V tier, not a primitive.

**Remark (decomposition ⊥ authority).** The plane {T, D, Dep, V} is authority-free by construction: none of the signatures references the set of agents A — T = (spec, criteria, deadline), D : T → 𝒫(T), Dep ⊂ T × T, V : T → {pass, fail} through criteria. Agency and accountability are introduced by the **single** primitive **Del : T → A**. Hence authority is not a primitive but an **emergent relation**: recursive D ∘ Del generates the hierarchy ("a consequence, not a presupposition" above), and authority is the accountability edge induced by that composition over the D-tree, materializing exactly where Del changes along an edge. Consequence: compositional validation (Thm 1) and the whole plan {T, D, Dep, V} are checkable **independently of who is assigned** — V references criteria, not the executor (this grounds agent-agnosticity, Chapter 14). Separation of duties (SoD) is not a property of {D, Dep, V} but a **boundary term** of the Del hierarchy: the verifier ≠ executor gate fires at the seam Del(child) ≠ Del(parent) (Chapter 14), i.e. on an authority edge, not at every node of the graph.

---

## 11. Compositional validation

*(From the foundation to the theorems. The joint sufficiency below is the discrete shadow of basin chaining (Chapter 5): all children attained ⟹ the parent's region captured — `(t,{tⱼ}) ∈ S`. And the binary codomain below is the seam's own shape: A1's decidability clause is what gives Contact a two-valued output (Chapter 2), of which |L| = 2 is the theorem-form; the pigeonhole argument that follows is the downstream defense, not the source.)*

### 11.1. The compositionality theorem

**Theorem 1 (compositionality).** For a non-atomic task t with a correct decomposition D(t) = {t₁, …, tₙ}:

```
V(t) = pass  ⟺  ∀ tⱼ ∈ D(t): V(tⱼ) = pass
```

*Proof.*

(→) Suppose ∀ tⱼ: V(tⱼ) = pass. By joint sufficiency: for each cᵢ ∈ criteria(t), all children pass ⟹ cᵢ = pass. All cᵢ pass ⟹ V(t) = pass.

(←) Suppose V(t) = pass. Assume ∃ tⱼ: V(tⱼ) = fail. By non-redundancy: V(tⱼ) = fail ⟹ ∃ cᵢ: cᵢ = fail. But all cᵢ = pass — contradiction. ∎

**Corollary.** If every leaf is validated (V = pass) and all decompositions are correct, the root is validated. The global check is a consequence of the local ones.

**Characterization.** Thm 1 is an exact characterization: joint sufficiency + non-redundancy are *precisely* the conditions under which compositionality holds. The value is the explicit statement of which properties are necessary and sufficient. The difficulty is securing them in practice: causal correctness of a decomposition is a **characterized boundary** (Chapter 8), not an "open problem" in the algorithm-hunting sense; securing it against the real domain is exactly what the apparatus cannot self-certify (clause (ii), Chapter 3).

**What Thm 1 carries and what it does not (the theory-model reading).** The *verificational form* `V(p) = AND(V(c))` propagates along the tree **tautologically** from the two conditions above — a characterization, not a deep theorem, and it is S-independent (apparatus over Ŝ). The substantive (non-tautological) part is the **domain soundness** of each node: that the children's *joint sufficiency* is real — the composition edge `(t,{tⱼ}) ∈ S` (all children pass ⟹ the parent is really attained, by *its* criteria; in the theory-model this edge is the discrete shadow of one basin-chaining link `( ⋀ₖ Bᵢ⁽ᵏ⁾ attained ) ⟹ ∈ Capt_S(Bᵢ₊₁)`, Chapter 5 — the operational formulation here is primary). This is AND-soundness: option models (Sutton–Precup–Singh 1999 [26]) formalize the correctness of *one* composite transition, but **not** that a *set* of children *jointly* constitutes the parent — that edge `(t,{tⱼ}) ∈ S` is the GFSO kernel (Chapters 3, 6). Its failure `(t,{tⱼ}) ∈ Ŝ∖S` (a false composition claim) is the root of the failure modes (Chapter 12).

**Conditionality.** Thm 1 works **given** a correct decomposition. Everything downstream (Chapters 12–15) is the systematic construction of what approximates the theorem's conditions.

### 11.2. Binarity of validation

V : T → L. What is the scale L?

**Source versus defense.** The scale L is already fixed by the definition of V (Chapter 10): the criteria are decidable predicates cᵢ : Result → {pass, fail} (A1), and V(t) = ⋀ᵢ cᵢ. A conjunction of two-valued things is two-valued ⟹ |L| = 2 — **directly from A1**, with no appeal to the action space. That is the *source* of binarity: it carries exactly the two-valuedness that is axiomatic in A1 (a leaf predicate returns pass/fail) and closes under conjunction. Everything further in this subsection (act : L → A, |Act| = 2, pigeonhole) is not a derivation of |L| = 2 but a *defense* against a separate objection: "why not a graded scale?" The defense's answer: even redefining V as continuous, its surplus is decision-irrelevant and collapses to two values (Inf-B below) — an argument about the *uselessness* of gradation, not about *why* V-as-defined is two-valued. The split prices the assumptions differently: the source rests on A1 (the axiom the whole basis stands on); the defense rests on |Act| = 2 — an **architectural stipulation** (no third action over an unrestricted action space — the same irreducible boundary as the sixth-primitive question, Chapter 10). Moving the derivation onto A1 therefore does not make |L| = 2 "derived from nothing": it moves the load-bearing assumption from |Act| = 2 to A1 and leaves |Act| = 2 carrying only the defense.

**Claim (|Act| = 2).** An agent's action at a node either changes the task's trajectory or does not (excluded middle). Both classes are nonempty. Act = {intervene, ¬intervene}. "Wait" = ¬intervene; "partially intervene" = intervene in subtask X + ¬intervene in Y — binary at each node. (An excluded-middle argument; |Act| = 2 as an architectural choice — see below.)

**Redundancy of a graded scale (defense, not source).** Let V : T → L, act : L → Act. Requirements:

1. **|Act| = 2** (shown above)
2. **Completeness:** act is surjective (both actions reachable)
3. **Non-redundancy:** act is injective (distinct V values → distinct actions)

Then |L| = 2.

*Proof.* |L| ≥ 2 from (2). |L| ≤ 2 from (3) by pigeonhole. ∎

| Weaken | Consequence |
|---|---|
| (1) | Act > 2 requires an action that neither changes nor leaves the trajectory — impossible |
| (2) | An unreachable action → the system is defective |
| (3) | L > 2, surplus values decision-irrelevant → an arbitrary threshold, positional dependence, redundancy (granularity lives in the tree) |

**Injectivity (3) is forced, not assumed.** A V value that does not change the action distinguishes, by decision-relevance (validation exists *in order to decide* intervene/¬intervene — a purpose that follows from A1), nothing at the decision level ⟹ it is not a validation value; it collapses into an existing one. So act is injective not by design taste but by validation's purpose. (|Act| = 2 is the separate, *architectural* step: action granularity is exported into the tree, and retry-hysteresis into the FSM state (Chapter 14); the grounds are attribution purity, not pure logic — a system encoding retry-vs-escalate *as L values* would have |L| > 2; this subsection calls that redundancy, not contradiction.) Net: injectivity is forced logically; |L| = 2 is **forced within GFSO's architecture** (granularity → tree), not a preference about V's scale.

**Separating V and state.** Objection: "there is fail, pass, and in-progress." In-progress is not a V value but the *absence* of one. Two orthogonal dimensions:

- **state(t)** ∈ FSM — where the task is in its process. Changes over time.
- **V(t)** ∈ {pass, fail, ⊥} — the result of checking. ⊥ = undefined.

"Yellow"/"warning" in traditional systems conflates the two: one value encodes both "we don't know yet" and "looks like trouble". GFSO separates them cleanly.

**Forced binarity as a forcing function.** If at the moment of VALIDATING the Issuer cannot determine pass/fail — the criteria are bad. In a system with "yellow": set a warning, defer the decision, the defect stays masked. In GFSO: forced to decide → the specification defect is pushed into the open → recorded in q_T → next time the criteria are written better. A1 supports this: criteria are decidable predicates (pass/fail in finite time). "The code is clean" is not a decidable predicate (outside the model). "Every function ≤ 50 lines" is (inside).

**Coverage completeness.** Joint sufficiency does not demand that the criteria address every conceivable outcome — but uncovered zones are risk: an unimportant zone → into ACCEPTED_RISKS (STD-1, Chapter 13); an important one, forgotten → a defect, q_D ↓. Incomplete coverage is admissible but must be conscious and documented.

### 11.3. Uniqueness of the aggregation

Given |L| = 2. An aggregation ⊗ is needed: V(parent) = ⊗(V(t₁), …, V(tₙ)). Requirements:

1. **Commutativity + associativity** (order must not matter)
2. **An absorbing element, pinned to `fail`:** ⊗(fail, x) = fail. Follows from non-redundancy: tⱼ is necessary, V(tⱼ) = fail → V(parent) = fail — so the absorbing element is not merely *some* element of L (which OR and const₁ also have, absorbing at `pass`) but `fail` specifically, which is what the enumeration below prunes on

**Theorem 2 (uniqueness of AND).** On {0, 1} under requirements 1–2, AND is the only nontrivial operation.

*Proof (enumeration).* 16 binary operations. Commutativity → 8. Associativity → 6: AND, OR, XOR, XNOR, const₀, const₁. Absorbing 0 → AND, const₀. Nontriviality → **AND**. ∎

### 11.4. Informativeness

*(The informativeness claims are methodological; they are not in the headline eight of the P-series, §1.2.)*

**Claim Inf-A.** Binary validation + decomposition is strictly more informative than a continuous score without decomposition. "The task is at 73%" is uninformative: where is the problem? "7 of 10 subtasks pass, 3 fail" — the WHERE is exact.

**Claim Inf-B.** Binary validation captures all decision-relevant information. A continuous scale over the same tree contains strictly more information by Blackwell — but the surplus is decision-irrelevant: "0.73 pass" and "1.0 pass" lead to the same action (¬intervene). The extra bits do not affect the protocol. Granularity lives in the structure of the tree, not in a number.

**The chain:** decidability of criteria (A1) → V = ⋀cᵢ → |L| = 2 (source); binarity of actions → the defense against gradation → AND (uniqueness) → decision-relevant completeness (Inf-B).

---

## 12. Failure modes of compositional validation

Thm 1 is conditional. The question: **what exactly can break?**

*(The two cuts, never conflated. The COARSE cut is upstream and already derived: every failure is a used edge `e ∈ Ŝ∖S`, and the cut partitions the root by the edge's own status — FORM (the edge violates the map's own well-formedness) ⊕ FAITHFULNESS (the edge is clean but denied by S) (Chapter 7). The FINE taxonomy below — the seven modes — is a downstream result of the apparatus plus one named covering axiom (CA1, §12.8): it refines WHERE in the validation computation the bad edge bites, including its process phases. And the denotational⊕operational "4⊕3" partition below is a THIRD thing — the internal geometry of the fine taxonomy, orthogonal to the coarse cut.)*

**The root of failure (the theory-model, Chapter 2).** In S/Ŝ notation, any failure of compositional validation is, at bottom, a **used edge `e ∈ Ŝ∖S`**: an edge Ŝ asserts and S denies (a wall the map promised as a passage). The seven FMs below refine *where in the computation of validation* that edge bites (arguments / values / rule / time phase). The operational modes instantiate the root as process-phase mishandlings of the map, not as exceptions to it: FM-6 — a composition edge posited and used *before* its ground is determinable (the premature D-claim is itself the used ungrounded edge); FM-5 — the referent of a used edge changes under it (the edge now asserts a passage of an S it was never adjudicated against); FM-7 — a world-refuted used edge that cannot be marked, and so stays in `Ŝ_used`. The remaining internal modes read the same way: FM-2 — the used edges jointly assert a passage that is unsatisfiable even on the map's own terms (the composite claim can answer to nothing in S); FM-4 — the computed verdict keeps endorsing a used composition edge its own leaves have already refuted (mis-transmission leaves the bad edge in force). In every mode the failure of the action is carried by a bad used edge; the seven modes name the site and phase of the bite. The root `Ŝ∖S` splits on one ontic fact — whether the integration edge is a member of `Ŝ_used` at all — into §2.2's coverage hole (i) and insensitive edge (ii), placed by §12.2 as FM-1.f and the FM-3 false-PASS respectively. The unfolding below details the basis; here is its single root. (The edge = the shadow of basin chaining, Chapter 5.)

### 12.1. Definition

**Definition.** A failure mode (FM) of compositionality is a condition C on (D, V, context) under which the computed V(parent) departs from the true V*(parent): either the rule misfires (V(parent) ≠ AND({V(tⱼ)})), or an argument value is itself untrue (the equation holds while the result does not — the FM-3 case), or the formula is inapplicable (cannot be computed). §12.8 states this exactly as ¬CVC against V*(t); the three faces here are that one condition read on the rule, on the values, and on the computation.

A violation is of two types: (a) the formula is *wrong* (V(parent) ≠ AND under a correct computation) or (b) the formula is *not correctly computable* (the computation cannot be run, or runs on stale data). The dichotomy is exhaustive: the formula is either computed and gives the wrong result, or not computed correctly (excluded middle on "the formula was correctly computed").

### 12.2. Internal FMs: dissecting the function

The formula: V(parent) = f({V(tⱼ) : tⱼ ∈ D(t)}). A function is determined by three components: the **arguments** (domain), the **values** of the arguments, the **rule** of mapping (body). A function has no other components — that is its definition.

**The arguments {tⱼ}.** A set is characterized by two properties: its **membership** (which elements) and the **relations among its elements** (are they compatible). A set has no third property — a set is determined by its elements and the relations on them. A membership defect → FM-1, a relation defect → FM-2.

- **FM-1 (Correspondence):** {tⱼ} corresponds incorrectly to criteria(parent). The property is **two-directional** (symmetric to FM-3's two directions — see FM-3 below):
  - *Insufficiency:* ∃ cᵢ ∈ criteria(parent) addressed by no child → joint sufficiency violated
  - *Redundancy:* ∃ tⱼ addressing no cᵢ → non-redundancy violated (child fails, parent passes → V ≠ AND)

  **The FM-1 sub-taxonomy** (a secondary tag; not new top-level FMs — all are ¬(joint sufficiency ∧ non-redundancy), read on **both faces** of the correspondence condition, §12.8; the completeness of §12.4 is untouched). It separates what would otherwise merge into one bloated FM-1:

  | Sub-type | Level (Ch. 13) | Guard | Sub-clause |
  |---|---|---|---|
  | FM-1.a uncovered-criterion | Syntactic (L0, topological) | CHECK-1 | ∃ cᵢ with no responsible child |
  | FM-1.b missing-resilience-vs-predictable-external | Syntactic (L0) | STD-2 (admissibility) | a predictable external risk with no mitigation child |
  | FM-1.c missing-risk-grouping | Syntactic (L0) | STD-3 | correlated risks not grouped |
  | FM-1.d insufficient-entailment | **Semantic (L1)** | CHECK-7 | children exist, but ⋀criteria(tⱼ) ⊭ cᵢ (e.g. 150+150 > 200) |
  | FM-1.e redundancy | Syntactic (L0) | non-redundancy | the over-coverage direction |
  | FM-1.f unwritten-criterion | **Pragmatic (L2)** | no a-priori CHECK; runtime q_D / LLM review (Ch. 15) | the goal requires a criterion that no cᵢ carries |

  FM-1.d is **not a coverage hole**: every cᵢ has a responsible child (CHECK-1 passes), but the children do not formally *entail* cᵢ (CHECK-7, Chapter 13: "CHECK-7 catches what CHECK-1 misses"). It is the joint-sufficiency-as-implication clause, distinct from the topological coverage of FM-1.a.

  **The two faces of the insufficiency clause — and which of them a CHECK can see.** "∃ cᵢ ∈ criteria(parent) addressed by no child" quantifies over the criteria that were *written*: that is the clause's **apparatus face** — the correspondence of the children to the transcript, S-free and a-priori checkable (§2.3, §11.1; CHECK-1/1b, CHECK-7). Its **domain face** is the other side of the same condition: that the transcript really captures the goal — the composition edge `(t,{tⱼ}) ∈ S` (§2.2; §11.1's domain soundness). A criterion the goal requires that *nobody wrote* violates the domain face while the apparatus face passes: CHECK-1 is **vacuously green**, its quantifier ranging over the written set — non-vacuous one level up wherever an ancestor's criteria do write the requirement (§13.1's scope-extension remedy), terminal at the root or where every ancestor omitted it too. This is the forgotten glue of §2.2 case (i) and §3.4, and it is **FM-1**, as both already route it — not FM-1.a, whose sub-clause presupposes an existing cᵢ, and not FM-3, there being nothing to lie about. It is tagged **FM-1.f**: no a-priori guard exists for it (sub-types a–e index Syntactic/Semantic guards), and its runtime guard is **q_D** exactly so far as the issuer's own verdict reaches past the written criteria; where it does not, the case falls into q_D's named blind zone — parent-and-children shared blindness (§15.2, §24.5) — and terminally into the Pragmatic-level boundary (Chapter 8). Nothing in §12.4/§12.8 moves: CVC is stated against the true `V*(t)`, and what ¬CVC violates here is the domain face — the same two-sided pattern the truth condition on values already carries. (Conscious under-coverage stays the licensed case: the ACCEPTED_RISKS register for a risk event with an estimable P, the goal's own criteria under CHECK-1 for a scope boundary — §11.2, §13.1.)
- **FM-2 (Consistency):** criteria(t_a) demands X, criteria(t_b) demands ¬X → simultaneous satisfaction impossible.

  *An undeclared dependency — where it lands, and why not in one place* (the pair is stated at §6.3; here is the defining chapter's version). The couplings a decomposition omits fall on the two orthogonal axes of §12.8 — a basis, not a partition (§12.4). **Denotationally** the relations slot holds exactly one predicate, the mutual satisfiability of the children's criteria (§12.8), so an omission lands on **FM-2** precisely where the hidden coupling makes those criteria jointly unrealizable *as written* — reachable a priori by CHECK-8 to the extent that incompatibility is expressed there, and otherwise only by §13.6's FM-2 semantic residual. Where the written criteria stay satisfiable, no denotational condition is violated at all: the omission is invisible at formula level and can surface only when a consumer runs against an input its map did not connect — the freshness condition, **FM-5**. Its carriers are **BLOCK**, which falsifies the plan's implicit independence claim, and q_Dep's denominator, which BLOCK populates (Chapter 15) — and only for a *producible, cross-task* prerequisite: a non-producible external (force majeure, a vendor failure) goes down the FM-5 line with no Dep edge and q_Dep untouched (§14.2, §14.6). So FM-2 is the face a pre-execution check can reach and FM-5 the face only execution reveals; and where the omission additionally leaves the children's criteria not entailing the parent's, the ordinary FM-1.d fires as well, by §12.4's conjunction licence.

**The values V(tⱼ).** The single property a value has relative to reality is **truth** (a consequence of A1 + |L| = 2, Chapter 11: cᵢ is a decidable predicate whose only semantic content is its truth; binarity forbids a second property). Truth is **two-directional**: a value can be untrue either way.

- **FM-3 (Veracity)** *(v3.9: Verifiability — renamed; the guarded property is the truth of the verdict, not checkability)*: V(tⱼ) does not reflect reality — the value is untrue in either of two directions. *False-PASS:* pass where reality fails (the false pass propagates upward). *False-FAIL:* fail where reality passes (over-rejection; e.g. a health check declaring a live node dead). Both are defects of the value's single property: truth. The defect is constituted *on the value*; downstream harm (e.g. a needless failover from a false-FAIL) is a *consequence*, and if it additionally breaks propagation — that is a separate FM-4 (false-FAIL + mis-propagation = FM-3 ∧ FM-4). The AND asymmetry (absorbing = fail, Chapter 11) lives in *propagation* (FM-4), not in the value's truth. *(q_V, Chapter 15, is the sensor of the **acceptance** (false-PASS) direction of FM-3. False-FAIL is guarantee-safe: DONE is reached through acceptance (PASS ∨ auto_pass), never through fail (Chapter 14), and AND absorbs fail (Chapter 11) ⟹ a false-FAIL creates no false acceptance — its untruth is localized at the node (if it additionally breaks transmission, that is a separate FM-4, guarded structurally by CHECK-2/Thm 1, not a second edge of q_V). A symmetric "counter" would only give the aggregate false-FAIL share as a diagnostic of an over-strict validator — **a named instrument-priority boundary, not a mode gap and not a detection gap**.)*

**The rule f.** The rule's single property is correctness of transmission.

- **FM-4 (Propagation):** f fails to propagate a fail → the AND semantics is violated.

**Completeness:** 3 components, 4 defining properties (arguments: sufficiency + consistency; values: truth; rule: correctness) = 4 FMs. A component cannot be defective otherwise than through its defining property.

### 12.3. External FMs: dissecting the computation

The formula is a mathematical object. Its application is a process in time. Three phases: **before**, **during**, **after** (pre-condition, invariant, post-condition in formal-verification terms). There are no other phases.

- **FM-6 (Feasibility):** [before] D(t) is not definable — the information does not exist → computation impossible.
- **FM-5 (Freshness)** *(v3.9: Currency — renamed; the property is "inputs not stale", and the money-homonym is gone)*: [during] the spec changed, D(t) was not updated → the function computes over stale data.
- **FM-7 (Feedback):** [after] an agent found a defect but has no channel to report it → the error is invisible.

**Completeness:** 3 phases × 1 applicability condition per phase = 3 FMs. *(A numbering note: the operational indices FM-6/FM-5/FM-7 do not follow the before/during/after phase order — the numbering is historical and documented here rather than renumbered.)*

### 12.4. The completeness theorem

**Theorem (FM completeness as a basis).** {FM-1..7} is a **complete independent basis** of compositional-validation failures: any failure violates **at least one** of FM-1–FM-7 (coverage); the FMs are independent (each realizable in isolation, §12.5); and one real failure **may** violate several at once (e.g. FM-3 ∧ FM-4) — conjunctions are expressible in the basis. This is **not** a partition into singletons.

> *Remark.* Empirics corroborate the conjunction reading: most E1 records required a secondary FM, and the protocol carries `secondary_failure_modes`. The formalization is §12.8.

*Proof (coverage).* An exhaustive case split along two dimensions.

Let C be an arbitrary failure. C violates either (a) the formula or (b) its computation.

**(a) The formula.** C touches one of the function's three components:
- Arguments → C violates the correspondence {tⱼ} ↔ criteria(parent) (FM-1: insufficiency or redundancy) or the internal consistency (FM-2)
- Values → C violates truth (FM-3)
- Rule → C violates transmission correctness (FM-4)

**(b) The computation.** C touches one of the three phases:
- Before → FM-6. During → FM-5. After → FM-7.

Each step is an exhaustive dissection: a function = {arguments, values, rule}; a process = {before, during, after}. The decision tree has 7 leaves covering the failure space; a failure may touch several leaves. ∎

*(The grounding of the dissection itself is not "trust me" but a derivation from upstream results, §12.8: arguments → {membership, relations} from Chapter 10; values → truth from A1 + Chapter 11; rule → propagation from the uniqueness of AND. The operational axis {before/during/after} is **derived** (the causal-order trichotomy, §12.8); Hoare's pre/invariant/post is a *naming* of the three order regions, not their source.)*

### 12.5. Independence

For each FMᵢ there is a scenario where FMᵢ holds and the others do not:

| FM | Isolated scenario |
|---|---|
| 1 | D correct in form, but a subtask forgotten. Values true, propagation works, timing fine |
| 2 | D sufficient, but two children's criteria contradict. Everything else correct |
| 3 | D correct, but the validator signed without looking. A false pass |
| 4 | D correct, values true, but a child's fail is not transmitted to the parent (AND broken) |
| 5 | D was correct, but the spec changed. D not updated |
| 6 | The information for D does not exist yet. Everything else would have been correct |
| 7 | D correct, values true, but the executor has no channel to report an error |

**Corollary.** The 7 FMs form a complete independent basis: any failure is covered by ≥ 1 of them, and none follows from the rest (each is realizable in isolation). 7 is the dimension of the basis, not "exactly this many labels per failure".

### 12.6. Summary

| # | FM | Dimension | Component | Property |
|---|---|---|---|---|
| 1 | Correspondence | Function | Arguments (membership) | Correspondence correctness (sufficiency + non-redundancy); two-directional; sub-types a–f (§12.2) |
| 2 | Consistency | Function | Arguments (relations) | Consistency |
| 3 | Veracity | Function | Values | Truth (both directions: false-PASS ∧ false-FAIL) |
| 4 | Propagation | Function | Rule | Correctness |
| 5 | Freshness | Computation | During | Freshness of inputs |
| 6 | Feasibility | Computation | Before | Definability |
| 7 | Feedback | Computation | After | Detectability of errors |

The meta-level ("the model does not apply") is the model's boundary (Chapter 9), not an FM.

### 12.7. Corollary

Each FM is a necessary condition of correctness. The defense against each = a construction: Chapter 13 (standards) and Chapter 14 (protocol). Each is tied to a specific FM.

### 12.8. Formalizing completeness as a basis

§12.4 gives a persuasive case split. Here it is turned into a *theorem-modulo-axioms*, isolating the residual assumptions into named, checkable principles — instead of a hidden "trust me".

**The object.** The compositional validation of a non-atomic t is a *computation*: inputs — criteria(t) {c₁..cₖ}, children {t₁..tₙ} with criteria and values V(tⱼ); the rule `V(t) := ⋀ⱼ V(tⱼ)`; executed as a process in time.

**The correctness predicate.** `CVC(t) :≡ [computed V(t) = true V*(t)]`. A failure mode = a condition under which ¬CVC(t).

**The necessary conditions (two axes).** *(v3.9 named these C1–C7; v4.0 drops the parallel labels and states each condition by the FM whose violation it is — one taxonomy, not two.)*
*Denotational* (what is computed = a function = domain/values/rule — the structural dissection):
- the two-sided correspondence condition — joint sufficiency + non-redundancy, args ↔ criteria — whose violation is **FM-1**; it is itself two-faced, as the truth condition below is: an **apparatus face** (the correspondence to the *written* criteria, S-free and a-priori checkable) and a **domain face** (that those criteria capture the goal — the composition edge in S, §11.1), FM-1 being the violation of either (§12.2: FM-1.a vs FM-1.f);
- the compatibility condition on the children's criteria — whose violation is **FM-2**;
- the truth condition on each V(tⱼ) (both directions) — whose violation is **FM-3**;
- the propagation condition — the rule computes AND (propagates fail) — whose violation is **FM-4**.

*Operational* (how it executes; phases relative to the evaluation event e):
- the definability condition [before] — D determinate when it was fixed — whose violation is **FM-6**;
- the freshness condition [during] — the inputs have not gone stale — whose violation is **FM-5**;
- the reportability condition [after] — a post-hoc defect is communicable — whose violation is **FM-7**.

**Theorem.** `CVC(t) ≡ the conjunction of the seven conditions`. Hence ¬CVC ⟹ at least one condition fails — a failure violates ≥ 1 condition; together with §12.5 (each violation realizable in isolation) this yields a **complete independent basis**, not a partition. ∎ *modulo:*

> **CA1 (Evaluation Completeness — covering).** A computation is fully characterized by its denotational (function: domain/values/rule) ⊕ operational (execution in time) semantics. There is no third independent dimension. This is a **covering** principle (it yields ¬CVC ⟹ some condition fails), not a disjointness claim — hence a basis, not a partition.

**What is grounded:**
- **The truth condition (values)** — a consequence of **A1 + |L| = 2 (Ch. 11)**: a decidable predicate whose only semantic content is its truth; binarity forbids a second property.
- **The propagation condition (rule)** — a consequence of **the uniqueness of AND (Ch. 11)**: AND is fixed; its only possible defect is failing to propagate the absorbing fail.
- **The correspondence and compatibility conditions (arguments → {membership, relations})** — a consequence of **Chapter 10**: correctness of a decomposition is defined there by *exactly two* conditions on the set of children (joint sufficiency + non-redundancy = membership → FM-1), and the only relational predicate that can fail at fixed membership is the mutual satisfiability of the criteria (→ FM-2). "Exactly two" is derived, not postulated. (Chapter 10 grounds the condition's *apparatus* face; its domain face — that the written criteria capture the goal — is the same S-fact Thm 1 leaves to domain soundness, §11.1, and is not a third condition.)
- **Both axes are internal.** The denotational axis (Ch. 10 + 11). **The operational axis {before/during/after} is DERIVED** and **free of assumptions about the shape of time**: the three phases are the partition of events by the strict **causal** order relative to the evaluation event e (wholly-before ⊕ concurrent/overlapping ⊕ wholly-after) by excluded middle — causality is a strict order by definition, so the partition is exhaustive and disjoint **without a single clock and without atomicity** (CA2 is redundant — below). A1 ("pass/fail in finite time") gives the connectedness of the evaluation interval; **linearity of time is not needed for the phase count** — a total order merely collapses the middle cell into "during [s,e]", while under concurrency it reads as a race (FM-5 **generalizes**, it does not weaken). The deadline coherence of Chapter 10 corroborates. Hoare pre/invariant/post is a *naming* of the three order regions, not their source.
- **No third axis — pinned (for the unit of analysis).** A decidable predicate over a task's result is a function of (a) the *content of the result* (what it is: values/membership/rule — the denotational axis) and (b) the *temporal position of the check* relative to execution (the operational axis). A single result has no other assessable degree of freedom: "what is checked × when" exhausts it. Cross-task relations are Dep (a separate primitive, → FM-2), not a third axis of node evaluation. So CA1 is an **argued** covering principle rather than a bare stipulation — the argument narrows the candidate space without delimiting it, which is exactly why it stays an axiom under the (T)/(P) sort (Chapter 27) and appears in `#print axioms`. The thin local residue: the value/time partition for predicates over the execution trace itself — an edge of the definition. (The single clock is NO LONGER in the residue: the count of the three operational phases is axiom-free, CA2 is redundant — see below; outside the taxonomy remains only verdict atomicity/purity as protocol dynamics, Chapter 14.) The residue is local and does not touch "the two axes exhaust the unit".

**CA2 is redundant for the operational taxonomy (the minimal variant).** The three operational phases need neither a global clock nor atomicity of the evaluation act. It suffices that event time is a **strict causal order** ≺ (irreflexive, transitive ⟹ asymmetric) — and that is the definition of causality, not an assumption. Relative to the evaluation event e, any event x is classified as **wholly-before** (x finished before e began), **concurrent** (overlaps e in time / causally incomparable), **wholly-after** (x began after e ended). The partition is exhaustive (excluded middle) and disjoint (asymmetry of ≺) — and that is FM-6 / FM-5 / FM-7. **Assumptions: zero.**

*Atomicity is a property of the dynamics, not the taxonomy.* Even if the evaluation act is not atomic — an interval [s,e] that an event partially overlaps — the partition {wholly-before / overlapping / wholly-after} remains three-way (a grouping of the interval relations into three classes). Atomicity is needed only to guarantee a **pure verdict** (an untorn read of the result against the criteria) — a liveness/safety matter of the protocol, a separate object; and a torn read is itself a failure mode (FM-3 untruth / FM-5 freshness), i.e. it falls INSIDE the taxonomy, not outside it. The completeness of the 7 FMs is untouched by concurrency.

**Empirical check (E1).** If CA1 were false, E1 would have shown failures outside all the conditions. It did not: 0 cases require an eighth FM (a true residual NONE is out of scope — Chapter 24 / Chapter 9 — not an uncovered FM). Corroboration of the covering axiom.

---

## 13. Standards and verification levels

Standards are necessary conditions of a correct decomposition, stated as checkable rules. Each addresses a specific failure mode (Chapter 12).

*(The FORM half, operationalized. Chapter 7 derived the coarse cut: the FORM class of failure is catchable a priori over Ŝ at cost `c_check`. The standards and the CHECK battery below are exactly that a-priori discharge, and the three verification levels grade how much of FORM is mechanically reachable — the Morris trichotomy caps the levels at three and the Pragmatic level at uncheckable-by-machine.)*

### 13.1. STD-1: Explicit assumptions (ACCEPTED_RISKS) → FM-1

**The problem.** A decomposition implicitly sets P(factor) = 0 for everything unaccounted. That claim may be false, but it cannot be contested unless it is spoken.

**The standard.** Every decomposition carries an ACCEPTED_RISKS register *(v3.9: NEGLECTED)* — an explicit list of consciously accepted risk factors:

```
accepted_risks:
  - factor: <name>
    estimate: <P, impact>
    justification: <why we accept it>
    invalidation_condition: <when to revisit>
```

A decomposition without the register is incomplete by definition. (Continuous ground: an accepted-risk coarsening is safe ⟺ ∼_G is a bisimulation; it leaks ⟺ it is not — Chapter 5.)

**The register is tied to the DECOMPOSITION of a node, not to the node as such (who authors it, and when).** ACCEPTED_RISKS(t) records the assumptions of the *split* D(t), authored by whoever decomposes t, at the moment D(t) is chosen (what this split ignores). Strictly therefore:
- an **atomic leaf** (D(t) = ∅) has no split ⟹ its register is vacuous, **CHECK-4 does not apply to it** (a leaf's correctness is established by execution / V(t) against its criteria — Chapters 11, 4; its contribution to the parent is covered by the parent's CHECK-1);
- **a parent does NOT author the children's registers** — it authors its own, for its own split; each level's register is local to its decomposition;
- decomposing t one level down, the author **does not know which children will be further decomposed** ⟹ a child's register is authored **lazily**, when/if the child is itself decomposed (by its decomposer); a register pre-filled by the parent is not final and is subject to re-authoring by the child's decomposer (by revision — re-ASSIGN under the same id, Chapter 14).

CHECK-4 (below) therefore fires ⟺ the node has a split (D(t) ≠ ∅); a freshly created child and a leaf are not gated by it.

**Formal content.** The register converts an implicit assumption (P = 0, unstated) into an explicit one (P ≈ ε, with justification). An explicit assumption is: (1) refutable (the invalidation condition), (2) auditable (the justification can be checked), (3) aggregable (the total risk: P(≥ 1 of the register) = 1 − ∏(1 − Pᵢ), taken over the independent components — correlated factors are first grouped by STD-3, §13.3, precisely so that the roll-up runs over a common-root component, not over correlated raw factors).

**ACCEPTED_RISKS is a register of RISKS, not of scope boundaries.** The register holds uncertain *events* (factors with an estimable P), governed by predictability (STD-2) and the aggregate roll-up above. A conscious **scope boundary of the goal** (a capability out of scope: a "payment gateway" for the goal "billing computation") is NOT an entry: it has no materialization P (the estimate field would be vacuous, breaking the roll-up and the STD-3 grouping). It is governed by *the goal's own criteria* through **CHECK-1** (cf. Chapter 11: "an unimportant zone → into the register; an important one, forgotten → a defect, q_D ↓"): an out-of-scope capability demanded by no goal criterion is simply *absent* (optionally marked by a non-risk SCOPE tag on the goal — the making-explicit value, Chapter 6, where the exclusion is unobvious); a capability a goal criterion does demand is a coverage hole **FM-1.a**. Scope extension = a re-ASSIGN of the goal with new criteria, after which CHECK-1 forces a child. Thus STD-2's predictability stays about risk events and does not misfire on scope boundaries.

**Tie to FM-1.** Non-coverage = a factor neither in the decomposition nor in the register. STD-1 makes the coverage boundary *visible*: everything not covered by subtasks must be explicitly listed with justification. A coverage hole → either a missing subtask or a missing register entry — both detectable.

### 13.2. STD-2: Predictability → FM-1

**The problem.** The self-fulfilling prophecy: a manager ignores a factor → the task fails → "it was unpredictable". No preparation → a blow-up → "I told you so". Without a formal predictability criterion this is irrefutable.

**The standard.** Classify events by predictability, with the burden of proof shifted:

| Category | Criterion | Status in the decomposition |
|---|---|---|
| Ordinary | Occurs regularly in the domain (P estimable from data) | Mandatory in the decomposition |
| Statistical | P(X) estimable, event infrequent | In the decomposition or in ACCEPTED_RISKS with justification |
| Extraordinary | No precedent in the domain AND not derivable from known models | Admissible to omit |

**Formal content.** "Not derivable from known models" is an operational criterion: no known causal chain or statistical model predicts the event with an estimable probability. The rigor is not in a formula but in the **shift of the burden of proof**: predictability is presumed; unpredictability must be proven by whoever asserts it. Not "I didn't know" (ignorance) but "it was impossible to know" (impossibility). The legal analogy: innocence is presumed; guilt is proven by the accuser.

**Tie to FM-1.** STD-2 blocks false "unpredictability" as an excuse for non-coverage.

**The principled FM-1.b ↔ domain-boundary criterion (pinned through the theory-model; = the node axis of faithfulness `Ĝ ≠ G`, Chapter 5).** The subjective line "we could not have foreseen it" is pinned to faithfulness. An event yields **FM-1.b** (a decomposition failure — a forgotten mitigation child) if a *faithful* Ŝ for the domain would have carried that mitigation — i.e. a structural regularity in S exists and is observable (a precedent / an industry standard / what competent neighbors did). It lies on the **domain boundary** (outside the model, Chapter 9) only if *no* faithful Ŝ could contain it — no S-regularity to be faithful to (genuinely unprecedented, non-relational). This operationalizes "not derivable from known models": a checkable question about domain norms — "does a faithful domain estimate carry this mitigation?" — instead of a gut "feels foreseeable". The residue is local and empirical (not gut): the threshold "faithful/competent Ŝ" is a domain-precedent threshold. The E1 tie: the former borderline NONEs (ovh-001 etc.) → **FM-1.b**, because the mitigation is standard for the domain (geo-redundancy, fire suppression), not a domain-boundary case.

### 13.3. STD-3: Risk grouping → FM-1

**The problem.** Risks accounted chaotically: 30 factors with no structure. Correlated factors (drought → water shortage → plant disease) counted separately despite a common root cause.

**The standard.** Correlated factors are grouped into **components** with a common root cause. The components cover ≥ 90% of historical problems. The decomposition contains a risk node per component.

**Formal content.** Components are a factorization of the risk space: each component = a group of factors with a common source. The grouping method (PCA, clustering, expert taxonomy) is an implementation choice, not part of the standard.

**Tie to FM-1.** STD-3 systematizes coverage: the register rolls up over components with a common root, not over correlated raw factors.

### 13.4. STD-4: Form verification → FM-1, FM-2, FM-4, FM-5, FM-7

*(v3.9: "Structural validation" — renamed: "structural" names only the Syntactic level while the standard spans the Semantic one, and "validation" collided with the V primitive while form checks are verification.)*

Automatically checkable conditions. STD-1–3 = content (the right words); STD-4 = form (the right grammar).

Three levels of checkability, determined by the information available. *(The battery below counts **nine** CHECKs — CHECK-1, 1b, 2–8; the historical numbering "CHECK-1–8" is retained, the count is nine.)*

**The Syntactic level (Level 0: graph topology only).**

```
CHECK-1 (coverage):       ∀ cᵢ ∈ criteria(t), ∃ tⱼ ∈ D(t) responsible for cᵢ        → FM-1.a
CHECK-1b (no-orphan):     ∀ tⱼ ∈ D(t) addresses ≥ 1 cᵢ (no orphaned covers)          → FM-1.e
CHECK-2 (acyclicity):     the graph of D is a DAG                                     → FM-4
CHECK-3 (deadlines):      ∀ (t_a, t_b) ∈ Dep: deadline(t_a) < deadline(t_b)           → FM-5
CHECK-4 (accepted risks): for D(t) ≠ ∅: the register exists and is nonempty (leaves not gated) → FM-1
CHECK-5 (risk nodes):     ∀ component K from STD-3: ∃ a risk node                     → FM-1
CHECK-6 (delegation):     ∀ leaf t: Del(t) ≠ ∅                                        → FM-7
```

Checks: the mapping exists, the graph is well-formed, the deadlines cohere. Does not check: that the mapping *secures* the criteria.

**The Semantic level (Level 1: a composition function is declared).**

For each cᵢ ∈ criteria(parent) the Issuer declares *how* the children's criteria secure cᵢ — a composition function fᵢ.

```
CHECK-7 (formal sufficiency): ⋀{criteria(tⱼ) : tⱼ mapped to cᵢ} ⊨ cᵢ      → FM-1
CHECK-8 (consistency):        ⋀{criteria(tⱼ) : tⱼ ∈ D(t)} is satisfiable   → FM-2
```

Complexity depends on the criteria type:

| Criteria type | CHECK-7 (sufficiency) | CHECK-8 (consistency) |
|---|---|---|
| Numeric bounds | Arithmetic: O(1) | Interval intersection: O(n) |
| Boolean flags | Substitution: O(n) | Conjunction: O(n) |
| Set membership | Subset check: O(S) | Set intersection: O(S) |
| Arbitrary formulas | co-NP (SMT) | SAT (SMT) |

In practice criteria are simple (A1: decidable predicates) → the check is trivial.

Example:
```
parent criterion: response_time < 200ms
composition:      response_time = backend_time + frontend_time
child_1 criteria: backend_time < 100ms
child_2 criteria: frontend_time < 100ms
CHECK-7:          backend < 100 ∧ frontend < 100 ⟹ sum < 200 ✓  (the bound 100 + 100 ≤ 200 with both child bounds STRICT; the non-strict test alone would not entail the strict parent criterion)
```

CHECK-7 catches what CHECK-1 misses: "backend < 150ms + frontend < 150ms" passes CHECK-1 (both address response_time) but not CHECK-7 (150 + 150 > 200).

**The Pragmatic level (Level 2: a domain model).**

Causal correctness: the children's criteria secure the parent's criteria *in the real world*. Formally unverifiable without domain knowledge. Addressed by: LLM review (Chapter 15), q_D (runtime detection), institutional learning (Prop 6). Its status as a characterized boundary — Chapter 8.

**Exhaustiveness of the levels.** A decomposition is a formula. Knowledge about a formula is exhausted by three dimensions: **syntax** (how it is written), **semantics** (what it means formally), **pragmatics** (what it means in the real world). This is the fundamental classification of knowledge about sign expressions (Morris, 1938 — the covering axiom CA-Morris, machine-carried as `morris_trichotomy`, Chapter 27). There is no fourth dimension — as a function has no fourth component (§12.2).

| Level | Dimension | What is checkable | CHECKs |
|---|---|---|---|
| Syntactic (0) | Syntax | Graph structure, mapping | 1, 1b, 2–6 |
| Semantic (1) | Semantics | Formal entailment and compatibility | 7–8 |
| Pragmatic (2) | Pragmatics | Causal correctness | LLM (Ch. 15) + q_D |

A decomposition that fails the Syntactic level is not admitted to execution. The Semantic level applies where a composition function is declared. The Pragmatic level is runtime detection + learning.

### 13.5. The cost of checking and the verify-vs-explore decision

CHECKs are not free. The checking cost `c_check` is **graded by level**: the **Syntactic** level (topology: coverage of the written criteria, DAG, deadlines — CHECK-1, 1b, 2–6; a *never-written* glue criterion is precisely what it cannot see — §12.2, FM-1.f) is mechanical and cheap → almost always justified; the **Semantic** level (formal φ-sufficiency / compatibility — CHECK-7/8) is cheap on numeric bounds (SMT: 100+100 ≤ 200), but its *judgmental* end (implication over criteria SMT cannot formalize) is expensive and not mechanizable. Both levels are *a priori over Ŝ* (this is **FORM**), unlike the Pragmatic level, which is the causal-domain *faithfulness* axis, checkable only by execution. The cost is **latent in A2** (Chapter 9: "exceeds capacity" = a cost boundary), made explicit here as a per-unit magnitude.

Hence the real decision is **not** "to decompose or not" (one always decomposes; A2 forces the tree) but, at every node and level:

> **VERIFY** (pay `c_check`, cut the FORM risk *before* acting) **vs. EXPLORE** (act on the under-checked plan and let **contact** check it).

Exploration is not the absence of a plan: it is a **conscious substitution of contact for the a-priori check** (the plan exists, one acts on it; the bet is that contact checks more cheaply here). It is **principled** (Lemma 1, Chapter 2): faithfulness is a-priori uncheckable, contact is its *only* verifier, so acting *buys* information about faithfulness unobtainable otherwise. The rule: **VERIFY down to the level ℓ where the marginal `c_check(ℓ)` < the marginal prevented FORM risk; above that — EXPLORE.** The Syntactic level (+ cheap-SMT Semantic): `c_check ≈ 0` ⟹ always verify (the canon mandates the Syntactic level). The judgmental Semantic level: verify only where the prevented risk justifies it; otherwise explore. The *structure* of the tradeoff is derived; the concrete cost/probability values are contextual (contingent, like S itself; Chapter 7). Cost composes as an **edge decoration** with its own estimate-vs-realized split (the estimate in Ŝ vs the realized at contact) — it does **not** add a sixth link (Chapter 4; Chapter 7).

### 13.6. Table: standards ↔ failure modes

**How the standards relate to FM-1.** STD-1 and STD-3 are *coverage standards*: they **operationalize the joint-sufficiency clause** of FM-1 (STD-1 makes holes visible through the register/CHECK-4; STD-3 contributes risk nodes/CHECK-5). STD-2 is **not** a coverage standard but an *admissibility criterion for omission* (§13.2, the burden of proof of predictability): it neither adds nor removes children; it decides which non-coverage is a **defect (FM-1)** and which is a *licensed acceptance*. It is therefore STD-2 that re-labels an "external trigger" into FM-1.b or into the domain boundary (Ch. 9 / §24.6) along the predictability axis. Note: STD-1/3 are *guards* of FM-1, not identical to it (the failure is the predicate ¬(joint sufficiency ∧ non-redundancy); a standard is its Syntactic-level guard). STD-4 is orthogonal.

| Failure mode | Standard | Mechanism |
|---|---|---|
| FM-1 (Correspondence) | Syntactic: STD-1–3 + CHECK-1, 1b, 4, 5. Semantic: CHECK-7 (formal sufficiency). Runtime: q_D | Mapping (coverage 1 + no-orphan 1b) → formal implication → runtime detection |
| FM-2 (Consistency) | Semantic: CHECK-8 (formal consistency). Residual: LLM review (Ch. 15) | Formal compatibility check; the semantic residual via LLM |
| FM-3 (Veracity) | A1 (criteria = decidable predicates) — the verdict's **form**; **no structural CHECK guards FM-3** (Ch. 27) | A1 clause (i) buys decidability and binarity, never *sensitivity* to a real divergence (§3.2 d6); clause (ii) asserts domain-correctness but is apparatus-uncertifiable (§2.6) ⟹ the domain-silent false-PASS is a-priori catchable by no discipline — the named faithfulness boundary (Ch. 8). Runtime: q_V, the false-PASS direction only (Ch. 24) |
| FM-4 (Propagation) | CHECK-2 (DAG) + Thm 1 | Acyclicity + compositionality |
| FM-5 (Freshness) | CHECK-3 + the protocol (Ch. 14: re-ASSIGN revision · CANCEL refusal) | Deadline coherence + invalidation (cascade on CANCEL; the CHECK-1/no-orphan/CHECK-3 guards on re-ASSIGN revision) |
| FM-6 (Feasibility) | The protocol (Ch. 14: deferred decomposition) | D may be undefined at the start |
| FM-7 (Feedback) | CHECK-6 + the protocol (Ch. 14: CHALLENGE, BLOCK) | Every leaf has an executor + an upward signal |

---

## 14. The protocol

The primitives (Chapter 10) define *what* exists. The standards (Chapter 13) define *which rules* secure correctness. The protocol operationalizes both at runtime: a standard task-acceptance transaction in which every signal answers a failure mode or an operational necessity (§14.2).

*(From contact-necessity to the signal alphabet. Chapter 2 proved contact is the only ground-giving operation; Chapter 3 proved an agent must carry it. A protocol that forces honest directed action must therefore (i) route every contact verdict, (ii) give every failure mode with a runtime signature its channel, (iii) close the incentive seams so honesty is structural — and the twelve signals below are exactly that closure: 4 answer failure modes, 4 close FSM deadlocks, 3 close incentive seams, 1 initiates. The independent-verification seam (verifier ≠ executor) is the Del boundary of Chapter 10, §14.5.)*

### 14.1. The transaction model

Task transfer is a P2P transaction between two roles:

| Role | Function |
|---|---|
| **Issuer** | Forms the task (spec, criteria, deadline, ACCEPTED_RISKS), validates the result |
| **Executor** | Executes the task, delivers the result |

### 14.2. The signals and their motivation

Every signal answers a failure mode or an operational necessity.

**Executor → Issuer:**

| Signal | Semantics | Motivation |
|---|---|---|
| ACCEPT | Task accepted | Fixes the start of the obligation |
| CHALLENGE(reason) | The spec is defective | **FM-7**: feedback on a spec defect |
| BLOCK(reason) | An external blocker | **FM-5**: changed conditions; **FM-7**: feedback; registers a provisional discovered-Dep (Ch. 15) |
| DELIVER(result, self_validation) | The result is ready | Hands over the artifact + self-check |
| CONFIRM_CANCEL(in_flight_state) | Confirms the cancellation | **FSM**: the only *normal* exit from CANCELLING (§14.3); fixes the wind-down + the in-flight state (Thm 11) |

**Issuer → Executor:**

| Signal | Semantics | Motivation |
|---|---|---|
| ASSIGN(packet) | Task handed over | Initiates the transaction / re-ASSIGN (revision, same id — Inv-1) |
| ACCEPT_CHALLENGE(new_spec) | Challenge accepted | **IC**: the positive closure of the dispute — the executor learns his challenge was *accepted*, not that the contract changed for unrelated reasons (the spec update itself is Inv-1's re-ASSIGN, §14.3) |
| REJECT_CHALLENGE(justification) | Challenge rejected | Dispute resolution with justification |
| PASS | Result accepted | V(t) = pass |
| FAIL(criteria[]) | Not accepted | V(t) = fail; **FM-3**: cite the failed criteria |
| CANCEL(reason) | Cancellation (refusal of the task) | **FM-5**: cascading invalidation (a revision is a re-ASSIGN, not a CANCEL, §14.4) |
| RESOLVE_BLOCK(action) | Reaction to the blocker | **FM-5**: conditions restored |

12 signals. Everything outside the set is noise.

**The finiteness mechanism (timeout).** Inv-5 (§14.4) demands finiteness of every non-terminal state except IDLE. The realization: a system deadline monitor generates a timeout trigger when a deadline is exceeded. The timeout is not a P2P signal (no agent sends it) but a system mechanism enforcing finiteness. The full routing — first timeout to OVERDUE, a repeat to ESCALATED, and the three states with a direct special target — is §14.3.

CASCADE_CANCEL is not a separate signal. The cascade fires on CANCEL (refusal of the task): the protocol sends CANCEL to every descendant. A **revision** (a re-ASSIGN under the same id — Inv-1, §14.4) does not cascade. Likewise **REOPEN** (§14.3) is a named effect of re-ASSIGN, not a thirteenth signal, and leaves the lower bound on the alphabet untouched.

**Hidden-dependency provenance (BLOCK → discovered-Dep).** A BLOCK that exposes an undeclared *cross-task* prerequisite registers a **provisional** discovered edge in E_Dep (source = the prerequisite node, target = the blocked task, `discovered = True`); provenance = the BLOCK event (Thm 11). Resolution adjudicates its truth; the two-phase record and the q_Dep denominator it populates are stated at §15.2. Promoting a blocker into a node is **mandatory** when it is a producible in-scope artifact (a candidate producer exists); only the non-producible (force majeure, a vendor failure) counts as "external" — it goes down the FM-5 freshness line, not as a Dep edge (no source node). The implication is for the metric; the effect's implementation is the verification layer (a declared debt).

**Minimality.** Removing any P2P signal → a defect. Four defect types:

| Remove | Type | Consequence |
|---|---|---|
| ASSIGN | Operation | No initiation → the protocol is empty |
| ACCEPT | IC | The contract is not fixed → the executor later disputes the terms |
| CHALLENGE | FM-7 | The executor cannot report a spec defect |
| BLOCK | FM-5/7 | The executor cannot report a blocker |
| DELIVER | FSM | Stuck in EXECUTING — the result is never handed over |
| CONFIRM_CANCEL | FSM | CANCELLING loses its only *non-degenerate* exit — cancellation still completes, but by timeout alone and with no in-flight report (the state is not stranded: §26.9(b), `FsmCanon.noConfirm_only_timeout_into_abandoned`); + IC: the executor repudiates the cancellation / disputes work done |
| ACCEPT_CHALLENGE | IC | The dispute has no positive closure. The *spec* still gets updated without it — §14.3 admits ASSIGN from CHALLENGED and Inv-1 makes any contract change a re-ASSIGN — but the executor cannot distinguish an accepted challenge from an unrelated rewrite: CHALLENGE becomes unanswerable in the positive direction, where REJECT_CHALLENGE answers it in the negative |
| REJECT_CHALLENGE | IC | CHALLENGE is meaningless without dispute resolution |
| PASS | FSM | VALIDATING loses its only *genuine* completion — DONE stays reachable, but by auto_pass (timeout) alone, so validation degenerates to always-auto-pass (not stranded: §26.9(b), `FsmCanon.noPass_only_autopass_into_done`) |
| FAIL | FM-3 | Everything auto-passes → false validation |
| CANCEL | FM-5 | Stale tasks are never cancelled |
| RESOLVE_BLOCK | FSM | BLOCKED loses its only in-contract resolution — the state is not stranded (timeout → ESCALATED and the catch-alls remain), but the blocker gains no resume path; §26.9(b) files this in the sole/genuine-provider tier, not the fatal one (`FsmCanon.resolveBlock_sole_content_resume`) |

12 = the minimum. Each addresses a unique defect: FM (4: CHALLENGE, BLOCK, FAIL, CANCEL), FSM deadlock (4: DELIVER, CONFIRM_CANCEL, PASS, RESOLVE_BLOCK), IC (3: ACCEPT, REJECT_CHALLENGE, ACCEPT_CHALLENGE), operation (1: ASSIGN). ACCEPT_CHALLENGE sits under IC, not FM-5, by the canon's own Inv-1 rule: the spec update its removal would seem to cost is carried by re-ASSIGN (§14.3 admits ASSIGN from CHALLENGED), exactly as REOPEN is "a named effect of re-ASSIGN, not a thirteenth signal"; what only ACCEPT_CHALLENGE carries is the dispute's positive closure, the arm REJECT_CHALLENGE answers in the negative. Finiteness is enforced by the system timeout (above / §14.3), which is not a P2P signal.

### 14.3. The finite-state machine

12 states: IDLE, OFFERED, CHALLENGED, EXECUTING, BLOCKED, VALIDATING, REWORKING, CANCELLING, DONE, ABANDONED, OVERDUE, ESCALATED. (CANCELLING is non-terminal; ABANDONED is terminal, V = ⊥.) *(v3.9 names: OFFERED was REVIEW; REWORKING was REWORK; ABANDONED was CANCELLED; the OVERDUE state was TIMEOUT — the system trigger keeps the name timeout, lowercase.)*

```
IDLE ──ASSIGN──> OFFERED ──ACCEPT──> EXECUTING ──DELIVER──> VALIDATING
                   │                     │                      │
                   │ CHALLENGE           │ BLOCK                │ PASS → DONE
                   ↓                     ↓                      │ FAIL → REWORKING
               CHALLENGED           BLOCKED                     │ timeout → DONE(auto_pass)
               │ ACCEPT_CHALLENGE    │ RESOLVE_BLOCK            │  (Ch. 24; recorded apart from pass —
               │ → OFFERED           │ → EXECUTING              │   issuer inaction)
               │ REJECT_CHALLENGE → EXECUTING                   │
                                         │        REWORKING ──DELIVER──> VALIDATING
                                         └── escalation ─────────────┐  (the FAIL↔REWORKING loop
  any non-terminal (except IDLE, BLOCKED, CANCELLING, VALIDATING, OVERDUE) ─first timeout─> OVERDUE │ bounded by max_iterations)
                  ──timeout──> ESCALATED <────────────────────────┘
  BLOCKED ──timeout──> ESCALATED directly;  VALIDATING ──timeout──> DONE(auto_pass) directly   (ESCALATED is terminal)

  Cancellation (a handshake mirroring ASSIGN→ACCEPT):
  any non-terminal ──CANCEL(issuer)──> CANCELLING ──CONFIRM_CANCEL(executor)──> ABANDONED
                                         CANCELLING ──timeout──> ABANDONED  (cancellation is authoritative)

  The R′ extension (over the base; NOT part of the 12-signal minimum — a named re-ASSIGN):
  DONE      ──REOPEN⟨finality gate: not consumed upward (AND/Dep)      ∧ reopens left⟩──> OFFERED  (positive quasi-terminal)
  ABANDONED ──REOPEN⟨finality gate: cascade not settled / not replanned ∧ reopens left⟩──> OFFERED  (negative quasi-terminal)
      both = one re-ASSIGN under the consumption gate; max_reopens (per node) ⇒ finiteness (Inv-5)
```

Timeouts on every non-terminal state except IDLE (finiteness — Inv-5). Deadlines attach at ASSIGN (the deadline is a packet field), so the timeout machinery starts with OFFERED — IDLE precedes any contract and carries no clock of its own; Inv-5 is not breached at this corner because an IDLE child gates its parent only through the parent's own AND, and the parent's contract carries the clock — IDLE starvation surfaces as the parent's timeout, not as a per-IDLE one. The system sub-FSM (§14.2): the first timeout of any non-terminal state — except IDLE (no clock at all, above), the three special-target states (BLOCKED, CANCELLING, VALIDATING), and OVERDUE itself, whose own timeout is the repeat and goes to ESCALATED — → OVERDUE (intermediate), a repeat → ESCALATED (terminal); three states have a direct special target: BLOCKED → ESCALATED, CANCELLING → ABANDONED, **VALIDATING → DONE(auto_pass)** (the issuer failed to check in time — auto-acceptance, recorded apart from pass as an issuer-inaction event; it lowers q_V only if the auto-accepted task *later* fails — through the same pass→later-fail term, Ch. 15/24). The timeout is a system trigger, not a P2P signal. max_iterations (default 3) bounds the DELIVER→FAIL loop. **OVERDUE (intermediate) accepts no progress signals** — out of it only the repeat timeout → ESCALATED or the universal CANCEL; a missed deadline is a no-return path to escalation (Inv-6).

**Spec-dispute resolution (the exits of CHALLENGED).** ACCEPT_CHALLENGE(new_spec) → OFFERED (the issuer accepted the dispute: a new contract; the executor again ACCEPTs/CHALLENGEs — this is a revision, §14.4); REJECT_CHALLENGE(justification) → EXECUTING (the issuer declined: the spec stands, the executor performs the original); timeout → OVERDUE (the dispute unresolved in time — escalation, not silent auto-acceptance). These exits plus the universal CANCEL (admissible from any non-terminal) are the admissible set of CHALLENGED (Inv-6).

**The admissible sets, per state (Inv-6).** The diagram above plus the two catch-alls (universal CANCEL from any non-terminal ≠ CANCELLING; re-ASSIGN from the reassignable states — every non-terminal except IDLE, CANCELLING, OVERDUE) fix, for each state, exactly which signals move it. Written out (the base machine; the system timeout is a trigger, not a P2P signal):

| State | Admissible signals (→ target) |
|---|---|
| IDLE | ASSIGN→OFFERED · CANCEL→CANCELLING |
| OFFERED | ACCEPT→EXECUTING · CHALLENGE→CHALLENGED · timeout→OVERDUE · CANCEL→CANCELLING · ASSIGN→OFFERED |
| CHALLENGED | ACCEPT_CHALLENGE→OFFERED · REJECT_CHALLENGE→EXECUTING · timeout→OVERDUE · CANCEL→CANCELLING · ASSIGN→OFFERED |
| EXECUTING | DELIVER→VALIDATING · BLOCK→BLOCKED · timeout→OVERDUE · CANCEL→CANCELLING · ASSIGN→OFFERED |
| BLOCKED | RESOLVE_BLOCK→EXECUTING · timeout→ESCALATED · CANCEL→CANCELLING · ASSIGN→OFFERED |
| VALIDATING | PASS→DONE · FAIL→REWORKING (retries left) ∨ ESCALATED (exhausted) · timeout→DONE(auto_pass) · CANCEL→CANCELLING · ASSIGN→OFFERED |
| REWORKING | DELIVER→VALIDATING · **BLOCK→BLOCKED** · timeout→OVERDUE · CANCEL→CANCELLING · ASSIGN→OFFERED |
| CANCELLING | CONFIRM_CANCEL→ABANDONED · timeout→ABANDONED |
| OVERDUE | timeout→ESCALATED · CANCEL→CANCELLING |
| DONE / ABANDONED / ESCALATED | — (terminal; the R′ quasi-terminal REOPEN edge is the extension, not the base) |

REWORKING carries **BLOCK** for the same reason EXECUTING does (§14.2): it is a work-active state under the same contract (Inv-1, a revision is not a new contract), so a blocker met during rework must be reportable — without the edge it would be an unreportable defect (an FM-7 instance), which is exactly what BLOCK exists to preclude. The admissible sets are the machine-checked object of `formal/GFSO/FsmCanon.lean`.

**RESOLVE_BLOCK → EXECUTING is the *pure-unblock* edge.** It routes the case where the blocker is cleared with the contract intact. A RESOLVE_BLOCK whose action *changes a packet field* — as in the §14.6 example `RESOLVE_BLOCK(action: "…, deadline +2d")`, which moves the deadline — is by Inv-1 a **revision**: a re-ASSIGN under the same id → OFFERED for re-consent (§14.4), not a silent resume. So the destination splits by whether the resolution touches the contract, under the *same* Inv-1 rule that pins ACCEPT_CHALLENGE → OFFERED (§26.9(b) reads this split as the resume-vs-re-consent freedom of the pure-unblock case against the Inv-1-forced destination of the contract-changing one).

**The induced states are irredundant — but one is induced by history, not by the alphabet.** The states are not postulated; they are induced — the waiting points between signals plus the terminal outcomes. Made a behavioural check (partition-refine the transition rows, `FsmCanon.lean`): **eleven of the twelve are behaviourally irredundant** — no two share the same transition behaviour under the admissible-set-and-settlement-mode observable (and the three terminals, which share the empty row, are separated by the settlement mode alone — DONE = pass, ABANDONED = abandoned, ESCALATED = timeout, three distinct values — not by the verdict V, which collapses ABANDONED and ESCALATED). The **twelfth**, REWORKING, is behaviourally identical to EXECUTING (they agree on every signal): it is not a distinct waiting point but an **attribution label** — the same work-active behaviour tagged with how the node arrived (a FAIL was consumed). It is induced by the *history*, not by the alphabet, and its content lives in the log (Ch. 15.1 / Inv-7: the state projects the log; the log carries strictly more). This is a checkable sharpening of "induced", not a minimality claim about the states — signal minimality (§14.2), not state minimality, is the load-bearing one.

**Cancellation — a two-step handshake mirroring assignment.** CANCEL (issuer) from any non-terminal state → CANCELLING; CONFIRM_CANCEL (executor) → ABANDONED (terminal, V = ⊥ — the task abandoned, distinct from DONE = pass and ESCALATED = timeout). CONFIRM_CANCEL carries the in-flight state at the moment of cancellation (provenance, Thm 11) and is the **only normal exit** from CANCELLING (hence its defect type — FSM deadlock, §14.2, like DELIVER/PASS/RESOLVE_BLOCK); if the executor does not answer, the cancellation still completes by timeout (CANCELLING → ABANDONED), but without the in-flight report. Cancellation is authoritative (the issuer's prerogative): the executor confirms it, not contests it. The symmetry: ASSIGN ↔ CANCEL, ACCEPT ↔ CONFIRM_CANCEL, OFFERED ↔ CANCELLING, EXECUTING ↔ ABANDONED — cancellation is assignment walked backwards (open → confirm → settle). CANCEL (refusal) cascades the subtree (Ch. 15); a revision (re-ASSIGN, same id — §14.4) does not (it is not a CANCEL).

**Revision ≠ cancellation by state path (executor protection).** Cancellation (the CANCEL signal) runs through CANCELLING → ABANDONED (termination). A **revision** (a re-ASSIGN — the issuer changes a live node's contract; NOT a CANCEL) takes the node, under the same id, into **OFFERED** with the new contract: the executor must **ACCEPT** anew (re-consent) or **CHALLENGE** — until acceptance the new contract does not bind. So the issuer cannot *silently* swap the criteria under a node someone holds in work: the node leaves its working state, and the executor consents again. Revisions do NOT pass through CANCELLING (no termination — the node continues). This is the same IC protection as ACCEPT on the first ASSIGN; the structural guards (CHECK-1 / no-orphan / CHECK-3, §14.4) are orthogonal to consent and simply re-run (the same ones the Solver runs on any ASSIGN, §14.6).

**Irreversibility of cancellation — a design boundary.** ABANDONED is terminal, V = ⊥: cancellation is authoritative and, in the base protocol, irreversible. The grounding runs from the contract guarantee, with an honest boundary. A contract (fixed criteria/deadline, Inv-1) is valuable only as a guarantee of the outcome; an outcome revocable by either side at any moment at will guarantees nothing. What is forced is exactly one thing: any admissible reversal must be *non-ARBITRARY* — authorized by the issuer, bounded by a counter (else a loop violates finiteness, Inv-5), and appended forward into the log (Inv-7/Thm 11; history is never rewritten). A reversal "of any state at any moment" violates all three and is excluded. The terminality of ABANDONED is a *conservative implementation* of that constraint (zero in-protocol reversals trivially excludes arbitrariness), not a standalone theorem: the guarantee forces non-arbitrariness; terminality is chosen by design as the strongest compatible edge. A terminal reversal is, moreover, non-local: of a positive one (pass) — through AND (Ch. 11) and Dep (Ch. 10); of a cancellation — through the subtree cascade (above). Recovery from a mistaken authoritative CANCEL is outside the protocol, by re-issuing (a new node; the abandoned one stays abandoned in the log; the subtree is rebuilt, not resurrected). A bounded, authorized REOPEN (ABANDONED → OFFERED, and symmetrically DONE → OFFERED, max_reopens) does NOT contradict the guarantee and is the named extension (undo/rollback-along-the-log + finality), priced by the loss of terminality without max_reopens; it is not part of the base protocol and is not a state rollback (it is a compensating event forward). See Chapter 24 (assumptions and limitations).

**Finality = the loss of local reversibility (the semantics of R′).** *The criterion* (derived, not postulated): a terminal is **locally reversible** ⟺ **not consumed in the graph AND reopens remain**; it is **final** ⟺ **consumed ∨ max_reopens exhausted**. "Consumed ⟺ the reversal stops being local" is exactly the non-locality above (through AND / Dep / the cascade): past the consumption point, reversing a node = reversing its whole downstream cone. Consumption is edge-typed and logged (Inv-7, hence decidable): the positive one (pass) is consumed when the parent has staked a guarantee on V = pass (delivered the aggregate upward through AND) OR a Dep consumer has read-and-built on the result; the negative one (ABANDONED, V = ⊥, no pass value) — when the cascade has **settled** AND the parent has **replanned around the hole** (resurrection would create double coverage, FM-1.e). The single design freedom is the *moment* of the threshold (conservatively: downstream delivery / settling, presuming the node) — a log-visible over-approximation, not arbitrariness.

*The form — not a thirteenth signal.* REOPEN introduces no new defect class (it is recovery, not failure); "12 = the minimum" (the lower bound on the alphabet, §14.2) is untouched. REOPEN = the re-ASSIGN mechanism over the new edge ABANDONED → OFFERED, doubly gated: (i) the finality gate = the consumption check (a local reopen ⟺ not consumed); (ii) max_reopens (beside max_iterations) — restoring finiteness now that ABANDONED has an outgoing edge (Inv-5). ABANDONED becomes **quasi-terminal** (an explicit extension of the admissible set, Inv-6). The finality criterion is sign-independent, so **the positive edge is named symmetrically: an unconsumed positive terminal (DONE) reopens by the same re-ASSIGN (DONE → OFFERED)** under the same two gates — (i) the finality gate in its **positive form** = DONE is reversible ⟺ the parent has **not** yet staked the guarantee on V = pass (not delivered the aggregate up through AND) AND **no** Dep consumer has read-and-built on the result AND reopens remain; **a consumed DONE is finally locked**; (ii) the same max_reopens restores finiteness for DONE's outgoing edge (Inv-5). DONE becomes **quasi-terminal** exactly like ABANDONED (the same admissible-set extension, Inv-6, named explicitly); the counter is one per node and sign-agnostic — it counts **all** quasi-terminal exits (DONE → OFFERED and ABANDONED → OFFERED interleaved). DONE and ABANDONED are both quasi-terminal. REOPEN is an option over the minimal base (recovery exists in the base too — by re-issuing), so minimality is not threatened. The check-and-edge is **one log-serialized atomic step** (Inv-7), else a concurrent DELIVER consumes the node between the check and the reopen (TOCTOU).

*Anti-fake = OFFERED, not resurrection.* REOPEN leads into OFFERED, not into DONE: a stale verdict is not resurrected — the node goes through ACCEPT → EXECUTE → DELIVER → VALIDATE anew; the verdict is re-earned by fresh contact. For a positive terminal this literally **removes V = pass** (the old verdict is not carried forward; a DONE reopen whose fresh run fails is exactly the pass→later-fail term of q_V, Ch. 15/24 — no new machinery). But REOPEN does **not** repair the correctness of the new verdict — it inherits exactly the verifier ≠ executor seam + q_V (§14.5 / Ch. 24): it removes the resurrection surface; beyond the base guarantee it adds zero. *Anti-flip-flop:* max_reopens is the guaranteed terminator (Inv-5); consumption is the early exit; "from above" one can re-reverse ≤ max_reopens times, each in the log (Thm 11).

*Cascade honesty.* REOPEN is **NOT a cascade rollback**: CANCEL cascades, and by settling time the subtree = ABANDONED terminals (reopening the root yields OFFERED over a dead subtree). The window of local reversibility = until settling + replanning; inside it, the CONFIRM_CANCEL that logged the in-flight state (Thm 11) enables resume-from-provenance. On a large tree the window is short; past consumption, recovery = re-decomposition (the authority is the issuer's, whose decomposition contains the hole), not a reopen. That is, R′ is a bounded convenience for unconsumed terminals, not an "undo button for a live tree". The positive reopen is **simpler**: DONE did not cascade, the subtree is intact, so the settling window does not apply to it — DONE → OFFERED has a single gate, consumption-upward (AND/Dep), with no settling race.

*Why no consensus.* "Who may reverse" = Del (the single authority over the node). "A single non-branching history" = the single-sequencer append-only log (Inv-7/Thm 11). Prop 8 (non-adversarial) supplies only "the issuer does not spam reopens". Blockchain machinery (fork choice, Sybil, quorums) is what would be imported if Prop 8 ∧ single-Del were dropped (Ch. 24); the consumption criterion itself survives that.

### 14.4. The protocol invariants

1. **Inv-1 (Packet-Immutability).** The packet is immutable after ASSIGN. Changing any packet field (criteria, deadline, ACCEPTED_RISKS, **Del** — the executor) = a **re-ASSIGN under the same id** (a **revision**) — the node returns to OFFERED; the executor ACCEPTs/CHALLENGEs anew. (Reassignment of the executor = a re-ASSIGN with a Del change; that event is what q_Del counts, Ch. 15.) *From FM-5:* prevents *silent* contract staleness — a change passes through a logged re-ASSIGN (Thm 11: the new version appended to the log), never quietly. **A revision does NOT cascade** (it is a re-ASSIGN, not a CANCEL — the node continues): the subtree is preserved, and staleness is raised by the full guard set: CHECK-1 (a new uncovered criterion, FM-1.a) + no-orphan / CHECK-1b (**dangling covers** — a child mapped to a *deleted* criterion: coverage passes, but the work is orphaned — the FM-1.e redundancy, exactly the case the cascade used to remove) + CHECK-3 (consumers along E_Dep whose input is the node's changed contract: FM-5 freshness, Ch. 13). Only **CANCEL** cascades the subtree (refusal of the task — a separate signal, §14.3).
2. **Inv-2 (Binarity):** V(c) ∈ {pass, fail}. *From Ch. 11.*
3. **Inv-3 (Failure-Transparency):** FAIL ⇒ failed_criteria ≠ ∅. *From FM-3:* validation may not be unsubstantiated.
4. **Inv-4 (Obligation-Symmetry):** Issuer and Executor are equally accountable to the protocol.
5. **Inv-5 (Finiteness):** every non-terminal state **except IDLE** has a timeout (IDLE is the pre-contract state — it carries no clock of its own; its starvation surfaces as its parent's timeout, §14.3). (For the two quasi-terminals of the R′ extension, whose exits are signals rather than waits, finiteness is restored by the max_reopens counter — §14.3.)
6. **Inv-6 (Determinism):** the admissible signal set is defined in every state.
7. **Inv-7 (Identity-Stability).** A task's id is stable over its whole life cycle, including revision (re-ASSIGN under the same id): one node n ∈ N carries the successive versions of its spec. The immutable record is the **LOG** (Thm 11, Ch. 22), not the node: every re-ASSIGN appends a version to the append-only log; the node's current attributes (T/Del/V/state) project the latest version; past versions live in the log. Graph edges (E_D, E_Dep, criterion mappings) reference the stable id; re-issuing the id would orphan them. *A consequence of Ch. 15 (edges over N × N) + Thm 11 (the log carries provenance): "change = re-ASSIGN" is consistent only as in-place re-authorship under a stable id, never delete + create.*

### 14.5. Agent-agnosticity

```
Interface Agent:
    receive(packet) → Signal
    deliver() → ResultPacket
    validate(result, criteria) → Verdict
    handle_signal(signal) → Signal
```

Any agent (human, AI, robot) implementing the interface is a valid participant. H→H, H→AI, AI→H, AI→AI — one protocol.

**Autonomy levels.** A per-task, per-role property, not a global mode:

| Level | Issuer/Executor | LLM role | Human role |
|---|---|---|---|
| manual | Human | Not involved | Decides everything |
| assisted | Human + LLM | Proposes (draft → approve) | Decides |
| autonomous | LLM | Decides | Oversight at the level above |

The protocol, FSM, signals, and the CHECK battery are identical at all levels. Switching = Del(t): who occupies the role. In autonomous AI→AI: Issuer and Executor are different instances (context separation). Self-checking — one context occupying **both** roles of one transaction, setting the contract as Issuer and then accepting its own delivery as Executor — violates IC: a CHALLENGE is meaningless if you dispute yourself. (Issuer *forms and validates* by design, §14.1; what is forbidden is the coincidence of the two roles, not the Issuer's own pair of duties.)

**IC is a property of the seam, not a ban on internal self-checking.** The ban above ("self-checking … violates IC") concerns the **seam** — the public transaction (§14.1): one result crosses a scope boundary to an *independent* Issuer who validates it. IC is violated exactly when the Issuer and Executor of **one and the same public transaction** coincide. It is NOT a ban on an agent checking its own **internal** decomposition.

**An agent is a compression of domain structure (unpacking Chapter 4).** An agent is an emergent scope-bundle: a block of the tree of units assigned as one scope of responsibility. Inside the boundary, contact flows up from the leaves, each node checked against its realized aggregate (Chapter 4) — that is self-checking of an internal decomposition, and it is **not a seam**: internal nodes are not public transactions, they have no independent Issuer, they live inside one κ-bounded scope (A2, Ch. 2). An agent absorbs domain structure **up to its capacity** and presents outward **one** result — public relative to it — validated by ordinary delegation at the level above. "Many tasks inside, one checkable result outward" is the **unpacking of the very concept of an agent**, not an exception to IC. Tree depth is agent-relative (Chapter 3): a stronger agent → a flatter tree → internalizes more → presents **fewer** seams.

**Self-delegation "under the same id" is legitimate iff the validating Issuer is independent.** Self-delegation is not "delegating to oneself" in the §14.1 sense (there the roles are distinct by definition): it is the same theory-model process as delegation, but by its meaning it does **not** require checking every internal link — the internal self-verifies by contact; what exits is a result at the level of ordinary delegation. It would violate IC **only** if the outward-presented result itself is set-and-accepted by one context (then the "internal" was in fact a public seam with coincident roles — the ban above holds literally). Legitimacy = the validating Issuer is an independent scope (the level above) — which is exactly the seam of ordinary delegation.

**The public/internal criterion (the seam = the Del/scope boundary).** The labeling "which node is independently validated and which self-verifies" needs no separate mechanism — it is *derived* from Del.

- **A public node ⟺ a delegation seam.** The node's scope of responsibility differs from the parent's — operationally **Del(child) ≠ Del(parent)** (Ch. 10), or the node is a root task assigned to the agent by an *external* Issuer. At the seam the result crosses into an **independent** scope, so IC applies (verifier ≠ executor) and **independent validation is required**. The verifier ≠ executor gate is a **gate-at-the-seam**: it fires on public nodes, not on every node of the graph.

- **An internal node ⟺ the same scope.** **Del(child) = Del(parent)**: the node lives inside one scope assigned to the agent — its private decomposition (Chapter 4: contact flows up from the leaves, each node checked against its realized aggregate). It **self-verifies** — DELIVER carries `self_validation` (§14.2) — and is **not** independently validated. Why this is safe: the guarantee for the whole internal decomposition is **carried by the validation of the agent's public result** — the public node is validated directly against its own criteria at the seam, independently of the internal structure; and under a correct decomposition the public V = pass is equivalent to all-children-pass (Thm 1, the non-redundancy direction), so one public validation is exactly the stake that covers the internal work — nothing further needs per-link external checking. The agent **stakes all internal work on one public validation** — which is the agent as a compression of domain structure up to its capacity (Chapter 4).

- **The degenerate case.** A fully self-assigned autonomous agent (no external Issuer; its whole graph is one Del) **has no seam** ⟹ independent validation exists nowhere ⟹ **IC does not hold**; what remains is only making-explicit (Chapter 6): explicit, derived criteria plus the log. This is exactly "self-checking violates IC" in the no-seam limit: without an independent Issuer there is no IC guarantee — only the discipline of explicit, logged criteria, not a guarantee of method quality.

*The public/internal boundary is scope-relative (an honest residue).* Chapter 4 (agent = scope-bundle): the scope boundary is **chosen**, not derived by the ontology — the same work is "internal" or "a set of public seams" depending on how Del is assigned. The criterion tells *this* seam under *this* Del; it does not tell the "right" scope granularity (a modeling choice, like the κ field parameter, Ch. 2).

### 14.6. A worked end-to-end example

Task: "Prepare release v2.0". Issuer = PM, Executor = Tech Lead — for the **root**. The Tech Lead decomposes, so he is the Issuer of the children and the child-level signals below are his; this keeps every seam IC-sound (§14.5), including Demo, whose executor is the PM: Issuer (Tech Lead) ≠ Executor (PM). Had the PM issued the children as well, Demo would have been a public node with coincident roles — the exact violation §14.5 names. Read it seam-locally, as §14.5 states it: the PM still executes Demo *and* validates the root against c₃ ("demo ready"), so c₃ is in effect self-validated one level up. The rule is per-transaction and unbreached — Demo is independently validated at its own seam by the Tech Lead — but the residue is worth seeing rather than reading "every seam IC-sound" as more than it says.

**ASSIGN.** The PM forms the packet:
```
spec:     a release with features A and B
criteria: (c₁) features A and B implemented per spec ∧ all tests pass,
          (c₂) documentation current, (c₃) demo ready
deadline: 20 days
accepted_risks: the external API may change (estimate: P ≈ 0.1, impact ≈ 2d of rework;
                justification: adapting after the fact cost 2d on v1.5, below the cost of an
                abstraction layer; invalidation_condition: the vendor changelog announces a
                breaking major version)
                — a pre-fill: §13.1 ties the register to the SPLIT, authored by whoever
                  decomposes, so the Tech Lead re-authors it at D(root)
```

**The Solver (the CHECK battery):**
- CHECK-1: c₁ ← Feature A, Feature B, Testing; c₂ ← Docs; c₃ ← Demo. Coverage ✓ (the features carry c₁ with Testing — they are what the tests run against). CHECK-1b: every child addresses ≥ 1 criterion — no orphaned cover ✓
- CHECK-3: the brackets below are **durations**; the deadlines the Issuer sets from them are d5 (Feature A), d7 (Feature B), d12 (Testing), d15 (Docs), d17 (Demo) — Docs and Demo carrying slack for one rework cycle, since a rework that overruns its node's deadline reaches OVERDUE, out of which no progress signal is admissible (§14.3). Along Dep: A=d5 and B=d7 < Testing=d12; A and B < Docs=d15; Testing=d12 and Docs=d15 < Demo=d17; and, by §3.4 item (6) rather than by CHECK-3 — which guards only the horizontal Dep rule (§26.5-bis) — every child < the parent's d20. Deadlines ✓ on the horizontal rule, the vertical one checked by hand
- CHECK-7: criteria(Feature A) = "feature A implemented per spec", criteria(Feature B) likewise, criteria(Testing) = "coverage ≥ 80%, 0 critical bugs". Does ⋀ of the three ⟹ c₁? **The Solver flags:** the feature conjuncts land, but "coverage ≥ 80%" ≢ "all tests pass". The repair is **two-sided**, and each side is forced by a *different* rule — which is why one-sided repairs, though they would satisfy CHECK-7, are not on the table. **A1 forces the parent edit:** c₁ is what the PM will validate the root against, and "all tests pass" is not a decidable predicate over a delivered release, so he sharpens c₁'s test conjunct → "coverage ≥ 80% ∧ 0 critical ∧ 0 high". **CHECK-7 then forces the child edit:** once c₁ asserts "0 high", the children must entail it, so the Tech Lead sharpens criteria(Testing) to match — two Issuers, one per level. After both, ⋀{criteria(A), criteria(B), criteria(Testing)} ⊨ c₁ holds, a genuinely *joint* sufficiency rather than one child carrying the criterion alone. Repairing only the parent leaves exactly the FM-1.d CHECK-7 was run to catch (§12.2); repairing only the child leaves c₁ itself undecidable, which A1 forbids. The c₂ and c₃ arms are elided as immediate: criteria(Docs) = "the documentation reflects the current API flow" ⊨ c₂ and criteria(Demo) = "the demo runs the release build end to end" ⊨ c₃, each a single child entailing its criterion. Note what the feature conjunct also buys: **non-redundancy** (§10) — V(Feature A) = fail now forces c₁ to fail, where a c₁ of test statistics alone would let a missing feature pass, which is the FM-1.e ballast case. Both edits land before *either* ASSIGN is emitted — the split is drafted and the battery green before the root packet goes out (§15.3.4's Decomposition row is what runs CHECK-7/8 over a split, its ASSIGN row running the battery on the node's own packet); the same edit after ASSIGN is an Inv-1 re-ASSIGN, as the deadline change below is.

**The LLM:** "Feature B depends on the external API. The API is **non-producible** — no candidate producer node — so by §14.2 it takes no Dep edge (E_Dep ⊂ N × N, §15.1); it belongs in ACCEPTED_RISKS with an invalidation condition, which the packet carries. Release v1.5 lost 2 days to an API change: with a P estimable from that precedent and the event infrequent, STD-2 grades it **statistical** — admissible in the decomposition *or* in ACCEPTED_RISKS with justification, and the disjunction is genuine, so the register is the route *chosen* here, not the only one available. Do not read §14.2's rule as closing the other branch: what cannot be a node is **the blocker itself** (no source node for a Dep edge); a *mitigation* child — an adapter, a version pin, an abstraction layer — is perfectly producible, which is why STD-2's *ordinary* grade can demand one at all (§13.2's own anchor is a datacenter fire, non-producible, whose mitigations are ordinary buildable nodes; FM-1.b is the missing-mitigation mode)."

**The decomposition (after corrections):**
```
v2.0
├── Feature A    [dev1, 5d]
├── Feature B    [dev2, 7d, ← the root's accepted-risk entry bears on this child]
├── Testing      [qa, 3d, Dep: A, B]
├── Docs         [writer, 2d, Dep: A, B]
└── Demo         [pm, 1d, Dep: Testing, Docs]
```

**OFFERED → CHALLENGE.** Feature B's *detailed* criteria are authored at its own ASSIGN, below the root's Solver pass above — so the **root's** CHECK-8 (mutual satisfiability over the children's criteria, the FM-2 guard, §13.4) re-runs at that ASSIGN, where `c_B1 ∧ c_B2` first exists — the battery runs over the split at Decomposition (§15.3.4's Decomposition row — CHECK-7/8; not its ASSIGN row, which runs on the node's own packet, and not Inv-1, whose enumerated guard set is CHECK-1 / CHECK-1b / CHECK-3). An instance *at* Feature B would be vacuous, it being a leaf (⋀∅ = ⊤). The incompatible pair sits inside **one** child's criteria, where §12.2 states FM-2 across two; it is FM-2 by §12.8's single relations-predicate — the mutual satisfiability of ⋀criteria over D(root) — which is what CHECK-8 actually tests. Here the executor catches what the formal check misses on natural-language criteria: §13.6 names that FM-2 semantic residual and routes it to LLM review; this run reaches it through the executor's CHALLENGE instead. dev2 reads the Feature B spec (detailed criteria: c_B1 "new API only", c_B2 "legacy format supported"): "c_B1 and c_B2 are incompatible." → CHALLENGE(reason: "c_B1 and c_B2 are incompatible"). The Tech Lead (Feature B's Issuer) → ACCEPT_CHALLENGE, removing the legacy requirement (c_B2). (The signal carries the new spec; what its *removal* would cost is the dispute's positive closure, not the update — §14.2.) Feature B is now in OFFERED with the revised contract; dev2 ACCEPTs it → EXECUTING.

**EXECUTING → BLOCK.** Day 6: the external API ships a breaking change. dev2 → BLOCK(reason: "API v3 incompatible, Feature B blocked"). The accepted risk fired — an expected event, not a surprise. Day 7 — and it has to be inside d7: BLOCKED times out **direct to ESCALATED** (§14.3), with no OVERDUE stage to absorb a late answer. The Tech Lead → RESOLVE_BLOCK(action: "adapt to API v3, deadline +2d"). The action moves a packet field, so by Inv-1 this is a **revision**, not a silent resume (§14.3): re-ASSIGN under the same id → OFFERED, dev2 ACCEPTs the new contract → EXECUTING. Feature B's deadline becomes d9, and the guard set re-runs on the re-ASSIGN (Inv-1) — CHECK-3 still holds, d9 < Testing's d12. It holds with nothing to spare: Testing's 3d now runs d9→d12, consuming its whole float, so Testing must be delivered *and* validated by d12 or its VALIDATING times out to DONE(auto_pass) instead of the narrated PASS (§14.3, §24.7).

**VALIDATING.** Day 13, inside the root's d20 — a delivery past it would have taken the root to OVERDUE, out of which no progress signal is admissible (§14.3, Inv-6). DELIVER from the Tech Lead. The children's own verdicts were earned at their own seams and deadlines, each on the day its node settled — this is the state the root's delivery presents, not five day-13 events:
- Feature A (by d5): PASS ("feature A implemented per spec" — its own criterion; c₁ is the *root's*, discharged by these three children jointly)
- Feature B (by d9, after the revision): PASS (its own criterion, after the API fix)
- Testing (by d12, its float spent): PASS (coverage 87%, 0 critical, 0 high)
- Docs (d13): **FAIL**(criteria: "the documentation reflects the current API flow" — not updated after API v3)
- Demo: waits on Docs

Two FAILs at two seams, not one signal doing both. At the child seam the Tech Lead → FAIL(Docs) → Docs to REWORKING; at the root seam PM → FAIL(failed_criteria: [c₂, c₃]) — c₃ ("demo ready") is unmet too, Demo still waiting on Docs — → the **root** to REWORKING (Thm 1 on c₂, whose child failed; c₃ fails on a direct check instead — Demo's V is still ⊥, and Thm 1 operates only on tasks with V ≠ ⊥, §10). The writer fixes → DELIVER on day 14, inside Docs' own d15 — had the rework overrun it, Docs would have gone to OVERDUE and could no longer have been delivered at all (§14.3) → PASS. Demo, which waited on Docs, runs and PASSes on day 16, inside its d17. The Tech Lead re-DELIVERs the release on day 17 → PASS. v2.0 → DONE, inside d20.

**Self-measuring events:**
- The CHALLENGE from dev2 → a q_T event: the disputed criteria are Feature B's (c_B1/c_B2), which the **Tech Lead** issued, so the event lands in the slice of §15.2's q_T populations taken by the ASSIGN's author — a slice the formula admits but does not itself define — which is the Tech Lead's, not the PM's → the **Tech Lead's** q_T ↓
- The BLOCK = a declared accepted risk → q_Dep unaffected — because the blocker is the **non-producible** external API: no source node, hence no Dep edge to have been missed (§14.2), not merely because it was expected
- The FAIL on Docs → ordinary validation / AND propagation (Thm 1): a child failed its criteria; the parent cannot pass — caught correctly. The root cause — the undeclared link API v3 → Docs: the external API is **non-producible** (no producer node), so this is **FM-5 freshness** (a surprise change of conditions), NOT a discovered-Dep edge (q_Dep is untouched — it is about cross-task dependencies, §14.2 / Ch. 15; discovered-Dep provenance = BLOCK, not FAIL). Not a q_D decomposition defect.

One cycle engages: CHECK-7 (Solver), an LLM recommendation, CHALLENGE, BLOCK, the accepted-risks register, FAIL with criteria, q_T.

---

## 15. Graph, metrics, and the AI layer

*(Self-measurement from contact. Chapter 2 made every verdict a contact event; the protocol (Chapter 14) records every such event as a graph mutation. Measurement is therefore free: the quality metrics below are queries over the record of contacts, and the E_FAITH term the methodology optimizes (Chapter 7) gets its runtime estimator here. The AI layer's necessity is the SECOND axis — capacity (Simon), distinct from the provenance necessity of Chapter 3; §15.3.7 keeps the two apart.)*

### 15.1. The task graph

The protocol (Chapter 14) induces a graph.

**Definition.** The system state is a graph 𝒢 = (N, E_D, E_Dep, σ), where:
- N — the nodes (tasks); each n ∈ N: T(n), Del(n), V(n) ∈ {pass, fail, ⊥}, state(n)
- E_D ⊂ N × N — the decomposition edges
- E_Dep ⊂ N × N — the dependency edges
- σ — the global state (timestamps, counters)

The graph is not a visualization. The graph **is** the system. Every P2P signal (§14.2) is a deterministic mutation of the graph (of the nodes/edges N, E_D, E_Dep — or, for purely-provenance signals, of the append-only log σ): ASSIGN adds a node (or, as a re-ASSIGN on a live node, re-authors the existing one under the same id → OFFERED = a revision); PASS sets V(n) = pass and triggers the cascading check; **CANCEL** (refusal) cascades the subtree (X → CANCELLING → ABANDONED). A revision (re-ASSIGN, same id) is not a CANCEL and preserves the subtree (Inv-1). Nodes carry a stable id for life (Inv-7): the immutable record is the LOG (Thm 11), and the current graph is its projection onto the latest versions.

### 15.2. The quality metric

Q = (q_T, q_D, q_V, q_Dep, q_Del) ∈ [0,1]⁵. Each component corresponds to one primitive and catches defects of that type:

| Component | Primitive | Failure mode | Question | Formula |
|---|---|---|---|---|
| q_T | T | FM-1 (Correspondence: specs) | Are the criteria clear? | 1 − \|{t : criteria challenged (CHALLENGE) ∨ changed for a spec defect}\| / \|{t : a contract was issued (ASSIGN)}\| |
| q_D | D | FM-1 (Correspondence: decomposition) | Is D good? | 1 − \|{t : non-atomic, own validation returned FAIL while all active children were passing}\| / \|{t : non-atomic, validation returned a verdict (pass ∨ fail) while all active children passing}\| (∅ → ⊥; auto_pass excluded) |
| q_V | V | FM-3 (Veracity) | Is acceptance reliable? | 1 − \|{t : V = pass, later fail}\| / \|{t : V = pass}\| |
| q_Dep | Dep | FM-5 (Freshness through dependencies) | Are all Deps declared? | \|Dep_declared\| / \|Dep_declared ∪ Dep_discovered\| |
| q_Del | Del | FM-7 (Feedback through delegation) | Is the assignment right? | 1 − \|{t : reassignment for capability_mismatch}\| / \|{t : a contract was issued (ASSIGN)}\| |

(q_V catches the **acceptance** (false-PASS) direction of FM-3; false-FAIL is the guarantee-safe direction, outside the Q scalar by design — Chapter 24.)

**Minimality and completeness.** 5 metrics ↔ the 5 components of the tuple (T, D, Dep, Del, V; the basis is 4 primitives, V derived — Chapter 10) — a bijection. Removing any → a blind zone:

| Remove | Blind zone | The invisible defect |
|---|---|---|
| q_T | Criteria quality | Challenged/changed specs untracked |
| q_D | Decomposition quality | The decomposition defect where all children pass but the parent should have failed (a false-positive D) is invisible |
| q_V | Validation reliability | Rubber-stamping (pass → later fail) is invisible |
| q_Dep | Dependency completeness | Hidden dependencies (surprise BLOCKs) are invisible |
| q_Del | Delegation correctness | Capability mismatch is invisible |

**Independence.** Each metric is a function of unique graph data: q_T ← CHALLENGE events; q_D ← child/parent pass patterns; q_V ← pass→fail patterns; q_Dep ← declared vs discovered edges; q_Del ← reassignment events. Different inputs → none expressible through the rest.

5 = the minimal number of self-measuring metrics: one per primitive, each from unique data. Calibrated bounds on Q (e.g. q_D ± ε at a stated confidence) — via conformal prediction (Angelopoulos & Bates, 2023): distribution-free, finite-sample guarantees.

**Populating q_Dep (else identically one).** The denominator divides by `Dep_declared ∪ Dep_discovered`, so someone must register the discovered edges — otherwise Dep_discovered = ∅ and q_Dep ≡ 1 degenerately. The carrier is **BLOCK** (§14.2, §15.2): a BLOCK exposes a missed dependency (a real edge of S∖Ŝ the plan omitted) — it **falsifies** the plan's implicit independence claim (a promised passage of Ŝ∖S, Chapter 12); contact adds a real S edge. The record is two-phase (recording ≠ confirmation): BLOCK registers a provisional edge (discovery provenance), RESOLVE_BLOCK adjudicates its truth (confirm / remove on mis-attribution); an escalated-unresolved provisional is counted. q_Dep thereby measures what share of S's dependency structure the plan declared in advance.

### 15.3. The AI layer

#### 15.3.1. Necessity

The information volume ℐ(α, t) **accumulates** (the graph grows; nothing is deleted; Prop 6 guarantees only *non-degradation* of content by Blackwell, not the volume growth itself). Human cognitive capacity is finite (Simon, 1955). For a nontrivial organization ∃ t*: |ℐ(α, t*)| exceeds any human's capacity. After t* the information exists but is not processed → the Prop 6 guarantees go vacuous. An AI layer with capacity growing with |ℐ| is necessary. *(This is the capacity necessity — Simon; distinct from the provenance necessity of the agent, Chapter 3 — Lemma 1; see "who is who" below.)*

#### 15.3.2. Two components

Computational processing of information about the formula V(parent) = f({V(tⱼ)}) requires inference. There are three types of inference: deduction, induction, abduction (Peirce, 1903; CP 5.145). But induction in isolation from semantic understanding is counting (the self-measurement infrastructure, §15.2), not inference. Meaningful induction ("q_D = 0.6 on backend tasks — why?") requires semantic understanding, i.e. abductive capacity. So the AI layer has two components, not three:

**The Solver (deduction).** From rules → consequences. CHECK-7 (formal sufficiency), CHECK-8 (consistency): constraint propagation, SMT (de Moura & Bjørner, 2008). A deterministic algorithm, not a neural net.

*Guarantee: sound + complete for decidable theories. Chollet Level 0: no generalization — none needed.*

**The LLM (induction + abduction).** From context → understanding, recommendations, semantic checks. A decomposition assistant, detection of unaccounted factors, interpretation of Q patterns, semantic consistency checking.

*Formalism:* in-context learning (ICL) as implicit Bayesian inference (Xie et al., 2022): the LLM performs posterior estimation P(recommendation | 𝒢) over the structured graph context. At sufficient capacity: implementing learning algorithms in the forward pass (Garg et al., 2022).

*Guarantee: Bayes-optimal given the prior. Prior quality is a condition, analogous to Thm 1's conditionality on the correctness of D.*

*The formal requirement on the LLM* (Chollet, 2019; Morris et al., 2024): **Chollet Level ≥ 2** (broad-to-extreme generalization; General Emerging+ in the Morris et al. classification). The system adapts to D_org (the task distribution of the specific organization) from the 𝒢 context, even if D_org ∉ D_train. Developer-aware generalization (Chollet, 2019): this level cannot be "bought" by enlarging D_train — it is a different class of generalization, not a different data volume.

#### 15.3.3. Cross-impossibility

| Task | The Solver cannot | The LLM cannot |
|---|---|---|
| A formal check (150+150 > 200) | — | P(error) > 0 (prior mismatch, hallucination) |
| Semantic reasoning ("forgot the deliveries") | No axioms for the domain | — |

#### 15.3.4. Integration into the protocol

| Protocol point | Solver | LLM |
|---|---|---|
| ASSIGN (goal-setting) | The CHECK battery on the packet | Propose criteria, accepted risks; warn of risks |
| Decomposition | CHECK-7 (sufficiency), CHECK-8 (consistency) | Assistant: propose a split, find forgotten Deps |
| OFFERED (executor) | — | Help understand the spec, suggest a CHALLENGE |
| VALIDATING | Auto-check machine-verifiable criteria | "Dep Y is not resolved — re-check" |
| Continuous | — | Interpret Q patterns, recommend improvements |

#### 15.3.5. The feedback loop

```
Protocol →(generates)→ 𝒢 →(feeds)→ Solver + LLM →(lowers overhead)→ higher α → Protocol
    ↑                                                                     |
    └──── Self-measurement ←──────────(measures)──────────────────────────┘
```

- α(t+1) ≥ α(t): the LLM lowers overhead → adherence grows
- 𝒢(t+1) ≥_B 𝒢(t): Prop 3 (Blackwell) → more adherence → a richer graph
- LLM(t+1) ≥ LLM(t): Blackwell inside the LLM → more data in context → a sharper posterior

A monotone system. Removing a link removes the GFSO improvement channel (Q does not grow *through GFSO*; the informal channels of Chapter 16 may still yield residual Q — hence not literally "Q = const", but "no improvement channel"):

| Remove | Consequence |
|---|---|
| The protocol | 𝒢 = ∅ → the Solver and LLM have no input |
| Solver + LLM | α = const → 𝒢 is not enriched (past `t*`; below it the loop still runs, bounded by human capacity — §15.3.1, Ch. 23) |
| Self-measurement | No quantitative feedback → the LLM does not improve |

#### 15.3.6. The safety net

An LLM error with a **formal signature** is caught by the protocol: a bad recommendation → a bad D → q_D records it; a bad semantic check → a CHALLENGE from the executor; what is caught is written into 𝒢 → updates the context → improves the posterior. **BUT:** a domain-wrong yet formally-clean D (the FM-3 false-PASS, Chapter 12; q_V catches only false-PASS) is **not** caught by the apparatus — that is the irreducible clause-(ii) boundary (Chapters 3, 8): only execution lifts it, not the safety net.

#### 15.3.7. Who is who (§15.3 ↔ Chapter 3)

The two "necessities" lie on **different axes** and add up, not duplicate: §15.3.1 = the **capacity** necessity (Simon: the volume ℐ outgrows a human → an AI layer is needed to process it); Chapter 3 = the **provenance** necessity (Lemma 1: domain content for Ŝ is not generated by the apparatus → a carrier-agent is needed). The entity mapping: **the Solver is pure apparatus** (S-independent, deduction from rules); **the LLM and the human are agents** in the Chapter-3 sense (carriers of learned Ŝ-content through contact), mounted on the protocol interface (Chapter 14). This dissolves a confusion: "agent-agnosticity" (Chapter 14) = *interface* interchangeability (any agent fills the slot); "interchangeability" (Chapter 3) = *conditional* (equal only at equal faithfulness of Ŝ-content). Two **different** claims about one word; and the graph 𝒢 is not agent-invariant (depth depends on the agent, Chapter 3).

The protocol bounds the worst case. The LLM improves the average case. Complementary.

### 15.4. Triage order over the graph

§1.1 opens with the control dilemma, and the protocol answers *where* to intervene — the failing node is named with its criteria and its author (Inv-3, Thm 11). It does not by itself answer *in what order*, when several nodes fail and capacity is short. The question splits, and only one half is answerable from the apparatus.

**Answerable — what to fix first is a graph question, not a severity question.** Both inputs are primitives already carried. The **dependency cone** of a node is what its failure holds: upward through E_D its whole ancestor chain (by Thm 1 a failing child denies every ancestor's pass), and forward through E_Dep the consumers that read its result (Chapter 10). The **deadline order** is the second: vertically child < parent (§3.4 item (6)), horizontally along Dep (Chapter 10's coherence, guarded by CHECK-3). The rule: **repair first the failing node whose cone blocks the most, with the nearest binding deadline as the tie-break.** It costs no new machinery — the cone is a reachability query over 𝒢 in Thm 10's own currency, and the deadlines are packet fields — and what it maximizes is unblocked work per repair, **under a premise worth naming: that repair cost is roughly uniform across the failing nodes.** Where costs differ sharply the cone ordering is a defensible heuristic rather than an optimum, and the canon supplies no cost model to weigh them by — the same measure-free limit the second half of this subsection names. (The vertical deadline rule it leans on is stated and derivable but has no dedicated pre-exec CHECK — §26.5-bis; CHECK-3 guards only the horizontal one.) It is explicitly *not* a claim about which failure is worse.

**A boundary — ranking by how badly a node failed.** That needs a measure over outcomes, which the apparatus deliberately lacks: |L| = 2 kills the intra-node gradient by design (Chapter 11), and ⪰_dom (§6.3) is partial in exactly the place that would matter — nodes with non-nested probe-sets are left unordered, which is the common case among siblings. This is the cardinal-severity boundary (Chapter 8) read at the triage decision. The ordering above does not close it: it orders by *consequence in the graph*, never by *magnitude of failure*, and the two coincide only by accident.

---

# Part III. Formal Guarantees

## 16. Information dominance

### 16.1. The information structure

**Definition.** Let O be an organization (a DAG of agents of depth n), α ∈ [0,1] — the share of tasks run through the GFSO protocol (adherence).

**The information structure ℐ(α)** — the totality of information available to an agent for decision-making at adherence level α:

- **ℐ(0)** = the status quo: personal experience, calls, meetings, memory, intuition — unstructured, ephemeral channels
- **ℐ(1)** = the full GFSO graph: for every task — the spec, criteria, the decomposition with authorship, the accepted-risks register, every CHALLENGE/BLOCK/PASS/FAIL with a timestamp, the Q metrics, LLM analytics over the history
- **ℐ(α)** for 0 < α < 1: tasks inside the protocol → structured signals; outside → informal channels. Includes the meta-information: the agent *knows* what is covered and what is not

### 16.2. Blackwell dominance

**Definition (Blackwell, 1953).** ℰ₁ **Blackwell-dominates** ℰ₂ (ℰ₁ ≥_B ℰ₂) if ℰ₂ = garbling(ℰ₁): there exists a Markov kernel M such that π₂(·|θ) = M · π₁(·|θ) for all θ. (The dominated experiment is a noising of the dominating one.)

Equivalently: ℰ₁ ≥_B ℰ₂ ⟺ for any utility function u: E[u | ℰ₁] ≥ E[u | ℰ₂].

**The formal setup.** Let θ = (θ₁, …, θₙ) ∈ Θ be the hidden state of the tasks (quality, progress, blockers). At adherence α the agent observes a signal s_α from the experiment ℰ_α = (S_α, π_α):

- S₀ = S^inf — the signals of the informal channels (calls, meetings, memory)
- S_α = S^inf × S^prot_α — informal + protocol signals for the α-share of tasks

Assumption: the informal channels are invariant in α (the protocol does not forbid calling).

**Prop 3 (information dominance, Blackwell 1953).** For any α₂ > α₁ ≥ 0: ℰ_{α₂} ≥_B ℰ_{α₁}.

*Proof.* Define the Markov kernel M : S_{α₂} → S_{α₁} as the deterministic projection:

```
M(s_{α₁} | s_{α₂}) = 𝟙[s^inf_{α₁} = s^inf_{α₂}] · 𝟙[s^prot_{α₁} = proj_{α₁}(s^prot_{α₂})]
```

proj_{α₁} discards the protocol signals for tasks in (α₁, α₂]. Then π_{α₁}(·|θ) = M · π_{α₂}(·|θ) for all θ. ℰ_{α₁} is a garbling of ℰ_{α₂}. By Blackwell (1953): ℰ_{α₂} ≥_B ℰ_{α₁}. ∎

The garbling is deterministic (a projection, not noise) — the strongest case.

**Corollary.** For any rational agent, with any utility function: E[u | ℐ(α₂)] ≥ E[u | ℐ(α₁)] for α₂ > α₁.

**The role of the AI layer (Ch. 15).** The LLM strengthens the dominance: (1) it processes the graph (a rational filter), (2) assists decomposition, (3) is institutional memory (does not forget). Formally: bounded rationality + LLM ≈ rationality → the Blackwell premise is better grounded.

---

## 17. Improvement through constraints

**Prop 4 (constraint improvement, Simon 1955).** When Δ > c (the cost of a breakdown exceeds the cost of compliance), GFSO's protocol constraints improve the expected payoff for any ℙ(θ_bad) > c/Δ.

**Game setup.** Players: Issuer (I), Executor (E). States: θ ∈ {θ_good, θ_bad}. Payoff: u = outcome − cost. Compliance cost: c > 0 (writing criteria, the register etc. costs time).

For each constraint:

| Constraint | θ_good: u(protocol) vs u(without) | θ_bad: u(protocol) vs u(without) |
|---|---|---|
| criteria mandatory | u − c vs u (the protocol costs c more) | u − c vs u − Δ_dispute (a dispute without criteria costs more) |
| deadline mandatory | u − c vs u | u − c vs u − Δ_inaction |
| criteria immutable | u − c vs u | u − c vs u − Δ_rework |
| the accepted-risks register mandatory | u − c vs u | u − c vs u − Δ_defect |

*Proof.* Under θ_good: the protocol costs c more (compliance). Under θ_bad: the protocol is cheaper by Δ − c, where Δ = cost(dispute/inaction/rework/defect). Expected payoff: E[u_protocol] > E[u_no_protocol] ⟺ ℙ(θ_bad) · Δ > c ⟺ ℙ(θ_bad) > c/Δ — the threshold of the statement. When Δ ≫ c (the cost of a blow-up ≫ the cost of compliance) the threshold is correspondingly *small*, so the condition holds at any realistic prior: what makes the constraint pay is the smallness of c/Δ, not its absence. (Simon, 1955: constraints help bounded-rational agents by removing harmful options at realistic ℙ.) ∎

**Assumption.** Δ > c — the cost of an organizational breakdown exceeds the cost of compliance — and with it the threshold ℙ(θ_bad) > c/Δ, which Δ ≫ c makes easy but does not by itself supply. Empirically realistic; formally, the condition of the theorem.

**Two independent improvement mechanisms:**

| | Prop 3 (Information) | Prop 4 (Constraints) |
|---|---|---|
| Channel | More information → better decisions | Bad actions removed → fewer errors |
| Premise | Rationality | Bounded rationality |
| Mechanism | Blackwell | Elimination of dominated strategies |

**Corollary (Universal Improvement).** For a non-adversarial agent, GFSO(α > 0) is weakly better than the status quo — by whichever arm his premise licenses:

- A rational agent: gains through information (Prop 3: Blackwell dominance — strict as a dominance *relation* wherever the projection actually discards a protocol signal, which is what α₂ > α₁ supplies; determinism of the garbling is what makes it the strongest *case*, not what makes it strict — §16.2; the payoff comparison it yields is weak)
- A bounded-rational one: gains through constraints (Prop 4: weak dominance removes harmful options) — **above Prop 4's own threshold** ℙ(θ_bad) > c/Δ
- The two mechanisms are independent and compatible, and their premises differ (rationality vs bounded rationality), so each arm covers the agent whose premise it names. The one cell neither arm reaches on its own — a bounded-rational agent at ℙ(θ_bad) below c/Δ — is where the canon's own mitigation applies: the LLM layer moves him toward the rational arm (§24.1, §15.3.1), a mitigation, not a third mechanism

Assumptions: (1) the protocol does not degrade the informal channels (§16.2), (2) for the constraint arm, Δ > c and ℙ(θ_bad) > c/Δ (Prop 4), (3) agents are non-adversarial (Ch. 24).

---

## 18. Monotonicity

Three axes. All independent.

### 18.1. α-monotonicity

**Corollary 5 (α-monotonicity, from Prop 3).** For a rational agent with any u: E[u | ℐ(α)] is monotonically non-decreasing in α. A direct consequence of Blackwell equivalence: ℰ_{α₂} ≥_B ℰ_{α₁} ⟹ E[u | ℰ_{α₂}] ≥ E[u | ℰ_{α₁}] (Marschak & Miyasawa, 1968).

There is no *information* threshold: every additional percent of tasks in the protocol weakly improves what a rational agent can condition on. This is the information arm and carries no compliance cost — the net-payoff arm is Prop 4's, with its own threshold ℙ(θ_bad) > c/Δ (§17).

**α is exogenous — the premise, its boundary, and the half that is derivable.** Every result of Part III is monotone in α and nothing in the model *sets* it: adherence is the aggregate of per-actor compliance decisions, where the cost c is paid now and individually while Δ accrues later and collectively. The premise "α is exogenous / adherence is sustained" is therefore named here, and stands wherever the monotonicity results are used (Cor 5, Prop 6, Chapter 23). Its closure is a **boundary** (Chapter 8): adherence dynamics need a utility model over actors — costs, horizons, discounting — which A1 ∧ A2 do not supply, the same species as cardinal severity. What *is* derivable, and is the difference from every comparator of §25.3, is that **α is observable from inside**: non-adherence is an event of the graph — a node without criteria, a PASS without independent validation, a decision without a record (Thm 10 / Thm 11) — so the premise is not merely assumed but measured, and therefore falsifiable. The decay dynamics themselves (α(t+1) = f(α(t), c, observed Δ, enforcement), and the conditions for a non-zero fixed point) are an import of the same layer as Prop 3/4/8, not a consequence of the axioms.

### 18.2. Temporal monotonicity

**Prop 6.** At fixed α: ℐ(α, t₂) ≥_B ℐ(α, t₁) for t₂ > t₁.

*Proof.* The information set ℐ(α, t) only grows: data arrives, nothing is deleted. ℐ(α, t₁) = garbling(ℐ(α, t₂)). New protocol signals carry information about θ (not noise): every PASS/FAIL/CHALLENGE is an observation refining the partition of states. ∎

Mechanisms: institutional memory, defect patterns, standard calibration. (At fixed α — the exogeneity premise and its measurable half are stated at §18.1.)

### 18.3. Scale monotonicity

**Prop 7 (exponential bounds).** In a feedforward hierarchy of depth n:

```
Without the protocol:  ‖eₙ‖ ≤ Λⁿ · ‖e₀‖        — exponential growth
With the protocol:     ‖eₙ‖ ≤ (Λ·γ)ⁿ · ‖e₀‖    — exponential suppression when Λ·γ < 1
```

**Definitions.** e₀ — the initial error (the deviation from the intended policy at level 0). At each level the operator Φᵢ acts: the error is amplified (gain Λ > 1: misinterpretation, context loss), then suppressed by validation (gain γ < 1). Gain = the induced operator norm: gᵢ = sup ‖Φᵢ(e)‖/‖e‖ in ℓ∞ (worst case over dimensions).

**Model assumptions:** (1) Λ uniform across levels (a homogeneous hierarchy); (2) the operators Φᵢ are linear (errors compose multiplicatively, not additively); (3) Φᵢ does not depend on prior errors (feedforward, no adaptation). Real hierarchies are heterogeneous and adaptive — the result is an upper bound for the worst case.

*Proof.* The feedforward cascade: eₙ = Φₙ ∘ … ∘ Φ₁(e₀). By submultiplicativity of operator norms: ‖eₙ‖ ≤ ∏ᵢ gᵢ · ‖e₀‖. Without validation: gᵢ = Λ → ‖eₙ‖ ≤ Λⁿ · ‖e₀‖. With validation: gᵢ ≤ Λ · γ → ‖eₙ‖ ≤ (Λ·γ)ⁿ · ‖e₀‖. When Λ·γ < 1: exponential decay. ∎

At partial adherence (assuming independence of covered and uncovered tasks): E_α(n) ≈ (1−α)·Λⁿ + α·(Λ·γ)ⁿ. In reality, cross-level dependence can amplify the effect of the uncovered tasks.

**Remark (feedback).** The main error flow is feedforward (top-down). CHALLENGE/BLOCK form upward feedback (bottom-up correction). For that feedback channel the small-gain theorem applies (Zames, 1966): if gain-up · gain-down < 1, the loop is BIBO-stable (no infinite challenge-override spiral).

**Remark (stop-and-replan as the temporal realization of damping).** The bound (Λ·γ)ⁿ vs Λⁿ is static; its *temporal* realization is the discipline **STOP → MARK → RE-DERIVE** at a wall (a contact verdict e ∈ Ŝ∖S): stopping is the single act that *inserts* the damper γ before the per-level amplification compounds, replacing the local gain Λ with Λ·γ. This yields the *magnitude* of the gain ((Λ·γ)ⁿ ≤ Λⁿ, strict when γ < 1) — but the **locality** of the correction (damage locked inside the dependent node's subtree, the correct top intact) is derived from explicit composition/attribution (two-sided attribution, Chapter 3), **not** from this bound. The full derivation of the discipline as a *forced* optimum — Chapter 7.

**Corollary 1 (sparse validation).** Checking every k-th level → the required validator gain: γ ≤ Λ^{−k}. P2P at every level (γ < 1) is cheaper than a rare strong review (γ ≪ 1).

**Corollary 2 (validator composition).** A validator cascade: γ(V₂ ∘ V₁) ≤ γ₁ · γ₂ — norm submultiplicativity, the same inequality Prop 7's proof runs on (equality only where the two validators' worst cases align). The bound is what the cascade buys: no perfect expert needed — several imperfect ones suffice.

**Corollary 3 (the guarantee improves exponentially where its price is linear).** With validation the *guaranteed* bound falls from Λⁿ·‖e₀‖ to (Λ·γ)ⁿ·‖e₀‖ — by the factor γⁿ, a guaranteed reduction of Λⁿ(1 − γⁿ)·‖e₀‖, exponential in n — while the checking cost is one validation per level, linear in n. *What this does not say:* Λⁿ and (Λ·γ)ⁿ are both upper bounds on ‖eₙ‖, and a difference of two upper bounds bounds nothing, so the realized benefit is not Λⁿ − (Λ·γ)ⁿ. The corollary is about the guarantee, exactly as Prop 7 is.

---

## 19. Incentive compatibility

**Prop 8 (IC as a dominant strategy — structural detection; Hurwicz 1960).** When `p·cost(undetected defect) > cost(signal)`, where `p` is the probability that the deviation is detected, honest use of every protocol signal maximizes the expected payoff for any ℙ(defect) > 0. Detection is **structural** — the claim is about the *channel*, not about `p = 1`: verifier ≠ executor + q_V + the timeout catch a one-sided deviation regardless of the counterparty's strategy (θ is a move of nature, and taking expectation over it does not demote DSIC to BIC), so the channel exists whatever the counterparty plays; how *often* it fires is the separate quantity `p`. So honesty is a **dominant strategy against any non-colluding counterparty** (consistent with §19.1) — not merely Bayes-equilibrium — wherever `p` clears the threshold; non-adversariality is required only against **collusion**. The Issuer-false-FAIL direction is a named boundary of q_V (Ch. 24), not dominant.

**Where `p` comes from, per signal.** For the rows whose consequence of silence is an event the FSM *forces*, `p = 1` and the threshold reduces to the plain Δ > cost(signal): a defective spec kept silent yields a FAIL on unsatisfiable criteria (validation is against the criteria, Inv-3), an unreported blocker yields the state's timeout with the responsibility on the executor (Inv-5). For the **acceptance** row `p < 1`: a fake PASS is discovered through q_V's pass→later-fail term, whose trigger is external (§24.5), and its aggregate over the validation cone is exactly §26.3's `p = 1 − ∏_{j ∈ cone(i)}(1 − p_j)` — over the per-validator sensitivities of the honest validators downstream. The **ACCEPTED_RISKS** row is a third case and neither of the first two: an undeclared factor materializing is forced by no state, no timeout and no verdict; its discovery runs through q_D's attribution of the parent's own FAIL, which is trigger-dependent in the same way, so `p < 1` there as well. At `p → 0` the case is not a separate adversarial gap but **collapses into the Pragmatic-level boundary** (§24.2, Ch. 8): no validator in the cone carries a criterion sensitive to the divergence.

**Game setup.** For each signal: the agent chooses a reporting policy ∈ {honest, dishonest}, where the **honest policy is state-contingent** — signal iff you observe the condition (an agent knows its own state when it signals: the executor has read the spec, knows its blocker, knows its own delivery — a signal is definitionally a report of an observation). The state θ ∈ {θ₁, θ₂} is hidden from the *counterparty*, not from the reporter. The payoff u(policy, θ) is determined by the protocol consequences.

**CHALLENGE.** θ₁ = the spec is defective, θ₂ = it is fine.

| | θ₁ (defect) | θ₂ (none) |
|---|---|---|
| CHALLENGE | The defect is fixed → u₁ | A false alarm → u₂ − ε |
| Silence | A FAIL on unsatisfiable criteria → u₁ − Δ | Works fine → u₂ |

**Per-state (the dominance form):** under θ₁ the honest policy CHALLENGEs (u₁ > u₁ − Δ); under θ₂ it stays silent (u₂ > u₂ − ε). Honest reporting is optimal **in each observed state**, whatever the counterparty does — no prior over θ and no Δ/ε ratio is needed for this; the Δ > cost(signal) condition is what makes the θ₁ column bite (an undetected defect must cost more than the signal). **Ex-ante (the coarse corollary):** even for an unconditional always-CHALLENGE reading, at ℙ(θ₁) > 0: E[u_CHALLENGE] = ℙ(θ₁)·u₁ + ℙ(θ₂)·(u₂−ε) > ℙ(θ₁)·(u₁−Δ) + ℙ(θ₂)·u₂ = E[u_silence] whenever ℙ(θ₁)·Δ > ℙ(θ₂)·ε — guaranteed when Δ ≫ ε (the cost of a fail ≫ the cost of a false alarm).

**BLOCK.** Analogously: honest → the deadline is suspended; silent → a timeout, the responsibility on the executor. E[u_honest] > E[u_silent] at ℙ(blocker) > 0.

**ACCEPTED_RISKS.** θ₁ = the factor materializes. Honest → an expected event; dishonest → a decomposition defect (q_D ↓, the Issuer's responsibility). E[u_honest] > E[u_dishonest] at ℙ(θ₁) > 0.

**PASS/FAIL.** θ₁ = the result does not meet the criteria. An honest FAIL → rework, recorded; a fake PASS → discovered with probability `p = 1 − ∏_{j ∈ cone}(1 − p_j)` through q_V's **pass → later-fail** term (Ch. 15; §24.5; §26.3) — trigger-dependent, hence optimistic, but recorded when it fires; honesty is dominant here exactly where `p·Δ > cost(signal)`, and the `p → 0` limit is the Pragmatic-level boundary, not an adversarial gap. (`auto_pass` is a different object — issuer inaction on a VALIDATING timeout, §14.3/§24.7: it enters q_V's population and is recorded apart from pass, but lowers the metric only through that same later-fail term; it is not a detector of a fake PASS. What it does detect is issuer inaction — §24.7.) E[u_honest] > E[u_dishonest].

**Assumption.** IC holds when: (1) ℙ(θ_bad) > 0 (a non-degenerate prior), (2) `p`·cost(undetected defect) > cost(honest signal) for every signal, at that signal's detection probability `p` (above). Both are realistic: (1) defects exist, (2) the cost of a blow-up exceeds the cost of a signal, and `p = 1` on every row whose consequence the FSM forces, while the acceptance row and the ACCEPTED_RISKS row carry the `p` explicitly, their discovery running through q_V and q_D respectively.

**The principle.** Not "people are good", but the *structure of rules* makes honesty rational. The protocol is a mechanism in Hurwicz's sense (1960): rules under which honest behavior is optimal at a non-degenerate prior.

### 19.1. IC-minimality

**Claim (IC-minimality).** For every IC-critical feature of the protocol: its removal → honesty stops being the dominant strategy for a specific agent.

| Remove | Agent | The dishonest behavior that becomes free |
|---|---|---|
| CHALLENGE | Executor | Silence about a spec defect: no channel → no obligation |
| BLOCK | Executor | Silence about a blocker: no channel → the deadline ticks unnoticed |
| DELIVER requires self_validation | Executor | Delivering unchecked: no self-check → sloppiness is free |
| The accepted-risks register mandatory | Issuer | Hiding risks: no record → no proof of knowledge |
| FAIL requires criteria[] | Issuer | A false rejection: no justification → rejection is free |
| criteria immutable | Issuer | Goalpost-shifting: changing criteria after ASSIGN → devalues the work |
| REJECT_CHALLENGE with justification | Issuer | Ignoring feedback: rejecting without reason → CHALLENGE is pointless |
| Timeouts on states | Both | Stalling: no per-state deadline → dishonest delay is free |
| max_iterations | Executor | Endless resubmission: delivering junk → waiting for the issuer to give up |
| ACCEPT | Executor | Repudiating the terms after the fact: with no fixed acceptance point the executor disputes what was agreed (the §14.2 IC row) |
| ACCEPT_CHALLENGE | Issuer | Pocketing a correct challenge silently: with no positive closure the executor cannot tell an accepted challenge from an unrelated rewrite, and the CHALLENGE channel loses its answering arm (the §14.2 IC row) |

**Independence.** 11 features, each protecting against a distinct dishonest behavior. Removing one is not compensated by the rest.

**Corollary.** The protocol is IC-minimal: no IC-critical feature can be removed without breaking incentive compatibility.

---

## 20. Decomposition quality

**Prop 9 (decomposition quality).** GFSO improves decomposition quality through 4 independent mechanisms. Each provably works; independence means the failure of any one does not cancel the rest.

### Mechanism 1: Information enrichment

**Source:** Prop 3 (Blackwell), applied to the act of decomposition.

An agent decomposes T. Let θ be the true causal structure of the task. Decomposition is a decision under incomplete information about θ. The information structure at decomposition:
- Without the protocol: the agent's own experience
- With the protocol + LLM (Ch. 15): + the history of analogous tasks in the graph + q_D patterns by task type + the concrete causes of past FAILs

The second set is strictly wider (a garbling of the second yields the first, not conversely). By Prop 3: more information about θ → a weakly better decision about D. ∎

### Mechanism 2: Validator composition

**Source:** Corollary 2 of Prop 7 (operator composition).

A decomposition D passes a validator cascade: the agent (γ_agent) → the LLM (γ_LLM) → the Solver + the CHECK battery (γ_checks). Each is an operator with gain γᵢ < 1. By Corollary 2:

```
γ_total ≤ γ_agent · γ_LLM · γ_checks
```

The bounding product is strictly smaller than any single factor (every γᵢ < 1), so the composed gain is at most that. A defect found before execution — compile-time instead of runtime.

### Mechanism 3: Space restriction

**Source:** Prop 4 (constraint improvement), applied to the space of decompositions.

The space of all possible D₀ ⊃ D_GFSO. The protocol excludes from D₀:
- D without criteria on subtasks (from A1: criteria are mandatory)
- D without the accepted-risks register (STD-1)
- D without coverage of the parent's criteria (CHECK-1)
- D without risk nodes (CHECK-5)

By Prop 4: each excluded option is dominated **in expectation above the threshold** ℙ(θ_bad) > c/Δ — not state by state (under θ_good the excluded option is cheaper by exactly the compliance cost c). This is a type system for decompositions — defective Ds are cut off before execution. ∎

### Mechanism 4: The feedback loop

**Source:** Prop 6 (temporal monotonicity).

q_D = "all children pass → does the parent pass?" A violation = a recorded defect with authorship, context, and the specific criteria it broke on. The LLM learns on the accumulated context → proposes improvements at the next decomposition of the same type.

By Prop 6: the information set ℐ(α, t) grows with t → every next LLM recommendation rests on strictly more data → recommendation quality is monotonically non-decreasing. ∎

The LLM drives the cost of running all four at once to near zero, so the optimal frequency is every decision.

**Remark (the forced optimum — Chapter 7).** The four mechanisms improve the *material* of decomposition; the *discipline* of producing-and-executing it is itself a forced optimum over `c_check + E_FORM + E_FAITH`, derived in Chapter 7.

---

## 21. Self-measurement

**Theorem 10 (self-measurement).** Q is computable from the execution trace with no additional data collection.

*Proof (constructive).* Every component of Q is a query over the graph 𝒢:

```
q_T   = 1 − |{n : CHALLENGE("spec") ∨ criteria changed for a spec defect}| / |{n : a contract was issued (ASSIGN)}|
        (scope extension — a re-ASSIGN of the goal with new criteria, Ch. 13 — is a sanctioned act, not a spec defect; it does not enter the numerator)
q_D   = 1 − |{n : non-atomic ∧ own validation returned FAIL while all active children were passing}|
            / |{n : non-atomic ∧ own validation returned a verdict (pass ∨ fail) while all active children passing}|
        (an ∅ denominator → ⊥; auto_pass = issuer inaction, not a verdict → excluded; q_D catches only the
         DETECTABLE false-positive D — the parent-and-children shared blindness is the Ch. 24 residue)
q_V   = 1 − |{n : V = pass, later fail}| / |{n : V = pass}|
q_Dep = |E_Dep(declared)| / |E_Dep(declared) ∪ E_Dep(discovered via BLOCK)|
q_Del = 1 − |{n : re-ASSIGN(capability_mismatch)}| / |{n : a contract was issued (ASSIGN)}|   (executor reassignment is a Del revision, not a CANCEL/refusal)
```

*(Three conventions, uniform across all five. Empty population: denominator = ∅ ⟹ the metric is **undefined** (⊥ — no observations; the same absence-of-value semantics as V = ⊥, Chapter 11: "100% on zero observations" would report a measurement where none occurred); a dash in reports; `metrics.py` returns None. Event-based: a metric records its defect at the moment of its protocol event (a CHALLENGE; a FAIL of the parent's own validation with children passing; the discovery of a false-PASS; a BLOCK; a re-ASSIGN with a Del change) over the population of nodes/edges where the event could be observed — a node's terminal outcome does not gate the observation: a defective trajectory that ended in ABANDONED/ESCALATED stays counted. Node-population denominators: the set-builders range over nodes, not signal events — t enters |{t : a contract was issued (ASSIGN)}| once, at its first ASSIGN; revisions (re-ASSIGN under the same id) do not multiply the denominator, while their defect events feed the numerators, attributed to the node.)*

The numerator and denominator are counts of 𝒢's nodes/edges annotated by protocol signals. P2P signals are written into the graph by construction (Ch. 15). ∎

**Corollary 1 (cost = 0).** Measurement is built into the work. The protocol is simultaneously the workflow and the instrument.

**Corollary 2 (gaming ≈ gaming the work).** To fake the metric is to fake the process (not sending a CHALLENGE on a crooked spec; not BLOCKing when blocked). Costlier and more visible than faking a report.

---

## 22. Structural transparency

**Theorem 11.** If the organization follows the protocol, then for every decision d there exists R(d) = (author, spec, criteria, accepted_risks, timestamp).

*Proof.* From the invariants (Ch. 14): ASSIGN fixes the spec, criteria, Del(t). The immutable record is the **append-only LOG** (Inv-7): a revision (re-ASSIGN under the same id) changes the node's spec in place, but every version is appended to the log, so R(d) for every version is preserved (immutability holds of the log, not of the node's current criteria). STD-1: the accepted-risks register is mandatory for a decomposed node (D(t) ≠ ∅). Inv-3: FAIL → failed_criteria. Every CHALLENGE/BLOCK/CONFIRM_CANCEL records a reason / the in-flight state + a timestamp. ∎

**Corollary.** Opacity = a protocol violation = a measurable defect (a missing node in the graph).

**Analogy.** Double-entry bookkeeping structurally admits no unbalanced postings. GFSO structurally admits no unrecorded decisions. Circumvention is possible, but costly and visible.

**Accountability without blame.** The protocol separates a process defect from an agent defect: FAIL(criteria) = the task failed specific criteria (not "a bad person"); CHALLENGE = the spec is defective (not "a difficult person"); BLOCK = an external dependency (not "a lazy person"). Every fact is recorded with context — no room for arbitrary interpretation.

---

# Part IV. Discussion

## 23. Inseparability of the components

The three components are derived from different levels of the framework, not postulated:

| Component | Derived from | Formal role |
|---|---|---|
| The protocol (Ch. 14) | A1 + A2 → FM → signals | Generates structured data (the graph 𝒢) |
| Self-measurement (Ch. 15) | Protocol + 𝒢 → Thm 10 | Makes the data machine-readable (Q from the trace) |
| The AI layer (Ch. 15) | Simon + the accumulation of ℐ → the capacity necessity (Prop 6 vacuous past t*) | The Solver (formal verification) + the LLM (cognitive processing) |

Removing any component → improvement *through the GFSO channel* becomes impossible — with the three removals standing at two different grades. Removing the **protocol** (𝒢 = ∅ — the Solver and the LLM have no input) or **self-measurement** (no quantitative feedback) breaks the loop outright. Removing the **AI layer** breaks it **beyond the capacity threshold `t*`** (§15.3.1): Prop 6's proof invokes only the accumulation of the trace and the informativeness of the signals — no AI layer — so below `t*` the loop runs without it, at a rate bounded by human capacity; past `t*` the accumulated ℐ exceeds any human's capacity, the information exists but is not processed, and the Prop 6 guarantees go **vacuous**. The removal table is §15.3.5.

---

## 24. Assumptions and limitations

### 24.1. Rationality (Prop 3)

Blackwell presumes rationality; the two arms and the cell neither reaches alone are the Universal-Improvement corollary (Ch. 17), the LLM-approximation mitigation §15.3.1.

### 24.2. Non-adversarial agents (Prop 8)

Incentive compatibility presumes: agents act in their own interest but do not sabotage. Adversarial scenarios (collusion, gaming, criteria-lowering) are partially protected by transparency (Thm 11) and q_V; peer review of decompositions (Ch. 26) is a proposed, not yet operationalized measure — not a current protection.

Detection is structural (Prop 8) — the channel is independent of the counterparty's strategy, at a detection probability `p` that Prop 8 now carries — ⟹ non-adversariality is needed only against **collusion** (agents coordinating to bypass it) and griefing, while the Issuer-false-FAIL direction remains a named q_V boundary (§24.5).

**The threat model — a characterized *stratification*, with one open problem inside it and one boundary at its limit** (the Chapter-8 criterion applied: the stratification is a result, the incentivized core is an open problem, and only its `p = 0` limit is a boundary). The guarantees stratify into adversarial-**INDEPENDENT** ones (claims about form over the log/graph — they survive the failure of Prop 8 as-is: the finality criterion (Ch. 14), the composition law Thm 1, the 7-FM coverage, self-measurement Thm 10, the minimalities of Ch. 10 / Ch. 14 / **§19.1 (the IC feature set)**, FSM determinism Inv-6; sabotage merely INSTANTIATES an FM form — intent is an orthogonal causal axis, not an eighth FM) and adversarial-**CONDITIONAL** ones — exactly three cheap resolutions off the three assumptions of Ch. 14:

| Dropped | Attack → locus | Import |
|---|---|---|
| Prop 8 | criteria-lowering → clause-(ii) faithfulness / q_V; issuer × executor collusion → the verifier ≠ executor seam; reopen-griefing → R′ (already bounded: max_reopens/Inv-5, measurable Thm 11/q_V §24.5) | mechanism design (a bond, restoring cost(defect) > cost(signal)); against collusion — a BFT quorum k-of-n (n ≥ 3f+1); criteria-lowering → the audit standard (Ch. 26) / recursive V |
| single-Del | forged Del / Sybil | crypto-identity (PKI; in the implementation identity is transport-derived and the FSM rejects source ≠ Del — its soundness is conditional on this); permissionless — Sybil resistance |
| single-sequencer | history fork → log canonicity | BFT-SMR / fork choice — PBFT (safety under an honest supermajority) or Nakamoto (longest chain, economic) — to agree one canonical log |

**Reduction to Prop 8 — by the nature of the import.** On the **incentive surface** (bond/slashing; criteria-lowering and griefing attacks) the import **restores the Hurwicz inequality** cost(undetected defect) > cost(signal) as a cost gradient (a bond raises cost(defect) at p > 0; a quorum multiplies the cost of collusion by f). The **identity** (Del/Sybil) and **ordering** (single-sequencer/fork) imports are not cost gradients but **preconditions** of that inequality: without authenticated identity no cost can be attached to forgery; without an agreed history there is no single cost-bearing chain; crypto-identity and BFT-SMR **create the arena** in which Hurwicz is formulable — they do not "restore" it. **The detection split:** p > 0 — mechanism design restores IC (the optimal design is open); p = 0 — collapses into the Pragmatic-level boundary (the domain-silent false-PASS, Ch. 8), not a separate adversarial gap. **In the permissioned scope (A1 ∧ A2 + an institutional boundary), single-Del and single-sequencer are protected for free** by the substrate (authenticated transport + one server); Sybil/fork require lifting the boundary (permissionless), outside A1 ∧ A2. The genuinely-open part is the behavioral core of Prop 8 over an authenticated **insider**: optimal collusion-proof mechanism design (known-hard — collusion in mechanism design, Laffont–Martimort; budget balance for Groves — Green–Laffont). By the Chapter-8 criterion this is an **open problem**, not a boundary — hardness is not impossibility from A1 ∧ A2 — and it is filed at §26.3, not a GFSO-specific gap; only its `p = 0` limit is a boundary, being the Pragmatic-level one.

**The R′ finality (Ch. 14) is conditional on the same three — the first of its two residues.** The consensus-free resolution of "who may reverse" rests on single-Del authority + non-adversariality (Prop 8) + the single-sequencer append-only log (Inv-7): one appointed authority per node, one non-branching history. An adversarial/permissionless setting would import the blockchain machinery (fork choice, Sybil resistance, quorums) — but the finality *criterion* itself (consumed ∨ counter exhausted) is adversarial-independent; only the cheap resolution of authority and history canonicity collapses. **R′'s second residue — anti-fake** — inherits the FM-3 false-PASS (§24.5): OFFERED-not-resurrection removes the *stale* verdict, but the correctness of the *new* one is carried by the verifier ≠ executor seam + q_V, not by the reopen (REOPEN adds zero guarantee beyond the base).

### 24.3. Causal correctness (Thm 1)

All guarantees are conditional on the correctness of D. The Syntactic and Semantic levels discharge what is discharge-able a priori (Ch. 13); the Pragmatic level is a characterized boundary with its approach vector, not an open task — Chapter 8.

### 24.4. The formalization overhead

Criteria, the register, the CHECK battery — cognitive load. The LLM reduces it (the assistant proposes, the human approves). An empirical question: at what overhead/benefit does the protocol pay off?

### 24.5. Closedness and limits of the metrics

Q is computable from the trace, but without external validation (Q vs real outcomes) the system is closed. Calibration of the metrics:

| Metric | Type | Informativeness | Blind zone |
|---|---|---|---|
| q_D | Ground truth | High | Correlated errors mask a D defect |
| q_V | Retrospective | High given a trigger | Without a trigger (a complaint, an incident): optimistic. The scope = the acceptance (false-PASS) direction of FM-3 **by design**: false-FAIL is guarantee-safe (it creates no false acceptance — Ch. 11/14), contestable under A1, self-recorded in the Thm 11 log (a criteria-cited FAIL). What goes unaggregated is only the false-FAIL **share** — a diagnostic of an over-strict validator / a griefing issuer (the systematics are contestable from the log, cf. §24.7), not a detection gap. **q_V is a relative frequency** (population statistics), **not Mayo severity** — and it sits on the *posterior* branch: `1 − q_V` is an observed (trigger-dependent, optimistic) lower bound on `P(goal false \| pass)`, whereas the cardinal import (Ch. 6) needs `sup P(pass \| goal false)` — the reverse conditional, unbridgeable without a base rate the canon does not fix. Severity as such presupposes an importable probability model. The ordinal skeleton (Ch. 6, ⪰_dom) is a different, probability-free object (tree structure) |
| q_T | Proxy | Medium | Incompetence/fear = silence → q_T = 1 with bad criteria |
| q_Dep | Lower-bound denominator (an optimistic metric) | Medium | Missed Deps that never caused a BLOCK are invisible — the denominator under-counts the true dependency universe, so the reported share over-estimates true declared-completeness |
| q_Del | Weak | Low (little data) | Small sample: significant only at scale |

Two genuine observables (q_D, q_V), two proxies with known biases (q_T, q_Dep), one weak (q_Del). The cause-typed terms of the formulas — re-ASSIGN(capability_mismatch) and "criteria changed for a spec defect" — require revision-cause typing in the packet: the field exists (`RevisionReason`, carried through the protocol and the graph mutations), but the metrics do not yet read it, so each keeps its documented bias until they do. The carrier of the "pass → later fail" mark for q_V is a post-hoc run of independent validation over a completed node (an existing instrument; its FAIL record over DONE(pass) is the discovery event): the run's trigger remains external (a complaint / an incident / an audit — the table above), but a recorded discovery is counted. Without deployment data, this ceiling stands.

### 24.6. Applicability boundaries

The model applies ⟺ A1 ∧ A2 (Ch. 9). Practical bounds:

**Where it works:** hierarchies of 3+ levels; outcomes dependent on planning quality (construction, manufacturing, logistics, IT projects).

**Where it may not:** creative/research tasks where decomposition is impossible in advance (¬A2); very small teams (3–5 people) where overhead > benefit; organizations with a punishment culture — transparency will amplify fear, not honesty (the IC assumption violated).

### 24.7. Auto-PASS

If the Issuer fails to check the result in time (T_validate expired) — auto_pass. Protection of the Executor from indefinite waiting. Countermeasures: (1) auto_pass is recorded apart from pass and counted in q_V; (2) notification upward (escalation of Issuer inaction); (3) systematic auto_passes by one Issuer — a measurable defect signal.

---

## 25. Related work

**Information economics.** Blackwell (1953), Blackwell & Girshick (1954): Prop 3. Marschak & Radner (1972): team decision theory; GFSO improves the team's information structure.

**Mechanism design.** Hurwicz (1960), Myerson (1981): Prop 8 — GFSO as a mechanism with dominant-strategy IC (structural detection; against any non-colluding counterparty).

**Bounded rationality.** Simon (1955): Prop 4. Simon (1962): A2 formalizes near-decomposability.

**Control theory.** The small-gain theorem (Zames, 1966; Jiang et al., 1994): Prop 7 — a hierarchy as a chain of amplification and damping.

**Cybernetics.** Conant–Ashby (1970) [36], the Good Regulator Theorem: every optimal regulator must carry a *model* of the regulated system — **a precedent for half of Lemma 1** (model/contact necessity: the domain structure S is not supplied by the apparatus and enters only through contact, Chapters 2–3). GFSO adds what the regulator theorem does not carry: the primitive basis of directed action, the composition law, and the provably complete failure taxonomy (the structure → completeness tree).

**Petri nets** (Petri, 1962; van der Aalst, 1998): the P2P FSM is a workflow pattern. Difference: no quality metrics.

**HTN** (Erol et al., 1994): D : T → 𝒫(T). Difference: HTN searches for a plan; GFSO validates, with a runtime protocol.

**Contract-based design** (Benveniste et al., 2018; Meyer, 1992): Issuer/Executor ≈ assume/guarantee, criteria ≈ postconditions. Difference: GFSO is for organizations, with CHALLENGE, BLOCK, self-measurement.

**Goal-oriented RE** (van Lamsweerde, 2001; Yu, 1997): goal trees + criteria. Difference: GFSO is the full cycle with a runtime protocol and metrics.

**AI formalization.** Chollet (2019): the generalization spectrum (Levels 0–3) → the formal requirement on the LLM component. Xie et al. (2022): ICL as implicit Bayesian inference → the mechanism realizing the Level ≥ 2 requirement (Ch. 15). Garg et al. (2022): transformers implement learning algorithms in the forward pass. Morris et al. (2024): the Levels-of-AGI taxonomy.

**Empirical failure taxonomies of agentic systems.** Recent work (e.g. [37], arXiv:2604.11978 — a long-horizon agentic-failure diagnosis) diagnoses the failures of decomposed / long-horizon agentic trajectories **empirically** — clustering observed traces into orthogonal multi-label categories. The contrast: GFSO's taxonomy is not an empirical cluster but an **analytically proved complete basis** from A1 (Ch. 12, modulo the named covering axiom CA1); the coincidence of form (orthogonality, multi-label) corroborates the naturalness of the categories, but GFSO's novelty is the completeness result itself, not the list.

**Semiotics.** Morris (1938): syntax/semantics/pragmatics → the three verification levels (Ch. 13). Peirce (1903): deduction/induction/abduction → the two components of the AI layer (Ch. 15).

**Operational frameworks** (the comparison table — §25.3). GFSO is orthogonal: it formalizes the unit everyone leaves undefined — **the act of task transfer**. ISO/CMMI/Six Sigma work on top (maturity, certification, statistical control); none provides a transaction standard + self-measurement.

### 25.1. Adaptive stratification by horizon (a derivative)

**Claim (adaptive stratification).** In a GFSO system of depth h with deadline coherence along D, the frequency of CHALLENGE signals strictly increases with level depth. Formally: for levels k < k+1 with horizons H_k > H_{k+1}: E[freq_challenge(k)] < E[freq_challenge(k+1)].

*Argument.*
1. From **deadline coherence along D** — item (6) of the §3.4 form list, child < parent (Ch. 10's Dep coherence is the *horizontal* rule between branches, guarded by CHECK-3, and does not order a parent against its child): deadline(child) < deadline(parent) ⟹ the horizon strictly decreases with depth.
2. From A1 (verifiability): criteria must be checkable within the horizon. On a short horizon, criteria are necessarily more concrete (no time for abstract predicates).
3. The more concrete the criteria, the more they depend on the exact state of the environment.
4. The environment changes at a rate independent of level (**an empirical premise, not from the axioms**: stationarity of environmental speed across levels). The share of a task touched by environmental change grows inversely with the horizon: share = Δt / H_k.
5. A CHALLENGE is generated when the environment diverges from the criteria. Divergence frequency ~ 1/H_k.
6. Hence freq_challenge is inverse in the horizon ⟹ increases with depth. ∎

**Corollary.** The upper levels of decomposition (vision, strategy) formally require **stable abstract criteria** and **rare CHALLENGE cycles**. The lower levels (sprint tasks, daily work) formally require **concrete criteria** and **frequent CHALLENGE cycles**. Not a methodological choice but a consequence of deadline coherence along D (§3.4, item (6)) + A1 **under the named stationarity premise (step 4)**.

**Implication.** The empirically observed practice "long-range plans are stable, operational ones change daily" is not a separate agile/lean principle but a **consequence** of GFSO (under the step-4 premise). Any system satisfying A1 ∧ A2 ∧ deadline-coherence-along-D ∧ environment-stationarity must exhibit this stratification.

### 25.2. Scrum as a special case of GFSO

**Claim.** The Scrum methodology [27] embeds semantically into GFSO as a special case under the following restrictions:

- depth(D) ≤ 2 (vision → sprint task; no further formal decomposition)
- ACCEPTED_RISKS = ∅ (risks discussed orally at the Daily Scrum, not recorded formally)
- CHECK-7, CHECK-8 not enforced (no formal sufficiency/consistency check of the decomposition)
- The audit trail informal (sprint notes instead of mandatory per-decision records)
- T.deadline restricted to a uniform sprint length

*The primitive mapping.*

| Scrum | GFSO equivalent |
|---|---|
| Product Owner | Issuer at the top-level T |
| Scrum Master | An Executor with T = "ensure protocol compliance" |
| Developers | Executors at task level |
| Product Goal | The spec at the top T |
| Sprint Goal | The aggregated spec at the sprint-level T |
| Sprint (event) | A T with deadline = sprint length |
| Product Backlog | The set of pending children under the top T |
| Sprint Backlog | The batch of Ts chosen for the current sprint |
| Sprint Planning | The ASSIGN signal, batched |
| Daily Scrum | An operational cadence for continuous V re-check (24h) |
| Sprint Review | DELIVER + V evaluation |
| Sprint Retrospective | A qualitative q-metrics review |
| Increment | The output of the DELIVER signal |
| Definition of Done | Criteria (typically weak) |
| User Story | A spec template for the weak-A1 regime |
| Story points | A specific estimation scheme |
| Velocity | Empirical throughput (outside the 5-tuple Q) |
| Burndown chart | A visualization of the audit trail |
| Empiricism (3 pillars) | Audit trail + continuous V + the CHALLENGE cycle |
| Self-organizing team | Execution-time decomposition by the Executor |
| No mid-sprint changes | Spec immutability between ASSIGN and DELIVER |

No Scrum primitive exceeding GFSO was found. Every Scrum component is either a direct mapping, a specific implementation choice, or a restriction of the general GFSO structure.

**Scrum's applicability regime.** The restrictions 1–5 are justified when: A2 is marginal (no deep decomposition needed); A1 is weak (criteria hard to articulate in advance; exploratory product development); a small team (3–9, internal coordination cheap); low error cost (quickly repairable); low compliance requirements. In these conditions the full GFSO apparatus is superfluous; the Scrum restrictions deliver the same semantics cheaper.

**The regime where the Scrum restrictions break.** When at least one of: A2 strong (systems demanding deep decomposition: compilers, OS kernels, payment systems); A1 strong (requirements known and important); multi-team coordination (formal interfaces between parallel branches needed); compliance-heavy domains (the audit trail legally mandatory); high stakes (errors expensive; formal preventive decomposition checking needed). In these regimes precisely the parts Scrum omits (CHECK-7/8, the risk register, depth > 2, the formal audit) become critical. Scrum's failure modes here are GFSO failure modes left unaddressed by the omitted checks.

**Implication.** Scrum is not an alternative methodology. **The structural embedding into GFSO is proven** (0 uncovered primitives in the mapping) — Scrum is a special case under relaxed axioms. The *behavioral* claim (that GFSO generates Scrum's exploratory dynamics) is an open frontier, not proven. The Newton ⊂ GR analogy is illustrative (GR *quantitatively* derives Newton in a limit; here a structural embedding is shown, not a limiting derivation of behavior).

### 25.3. The comparison table, extended

| | Kanban | Scrum | CMMI | Six Sigma | ISO 9001 | GFSO |
|---|---|---|---|---|---|---|
| Unit | Ticket | User story | Maturity level | Defect rate | Documented procedure | The act of decomposition |
| Acceptance | "Done" | DoD (weak) | Assessment | σ-bound | Audit | Binary V on criteria |
| Decomposition depth | flat | ≤ 2 | org-level | n/a | n/a | unbounded (DAG) |
| Composition theorem | — | — | — | — | — | V(p) = AND(V(c)) |
| Failure taxonomy | — | — | — | — | — | 7 FM (completeness proved as a basis **modulo CA1**; residue — the value/time edge of trace predicates) |
| Quality | Not measured | Velocity | Maturity score | Statistical | Conformance | Q = (q_T, q_D, q_V, q_Dep, q_Del) |
| Scope | Team | Team | Organization | Repeating processes | Procedures | Every decision |
| Formal foundation | none | none | none | statistical | conformance | A1 ∧ A2 + minimality |

---

## 26. Open problems

> This chapter lists genuinely open research problems. The characterized boundaries — formally irreducible, "closed" in the sense of being results — live with the foundation (Chapter 8); one relocation stub below keeps the historical numbering navigable. The criterion separating the two is stated at Chapter 8: a boundary carries an impossibility argument from A1 ∧ A2, while hardness, the absence of a construction, and "not yet built" are open problems and belong here.

**26.1. Level-2 causal correctness — relocated.** A boundary of the first kind, not an open task: its characterization lives with the foundation's named boundaries (Chapter 8); the approach vector (LLM induction/abduction, q_D as runtime convergence, domain ontologies under verification, institutional learning) — with the apparatus (Chapters 13, 15).

**26.2. Calibration.** Benchmarks: "q_D = 0.7 in IT vs construction". Periods: a project, a quarter, a year.

**26.3. Adversarial agents — a characterized stratification (Ch. 24); the incentivized core is open.** The stratification (adversarial-independent guarantee *forms*; three conditional resolutions importing mechanism design, BFT consensus and crypto-identity) is §24.2. Genuinely open = the detectable-incentivized core over an authenticated insider — the optimal bond / a collusion-proof quorum, Laffont–Martimort-hard, an **open problem** by the Chapter-8 criterion (hardness is not impossibility from A1 ∧ A2), which is why it lives here and not in Chapter 8; the undetectable part (`p = 0`) is the Pragmatic-level boundary (Ch. 8).

**Where the open kernel bites — the residue is attenuated along the validation cone, and localizes to the *sensitivity*-sparse frontier.** A colluding false-PASS at a node `i` (issuer_i co-opted, so verifier ≠ executor is bypassed) is still exposed by the *other* validators of `i`'s output — the AND-parent's **substantive integration criterion** (§11.1's domain-soundness part, *not* the tautological AND on verdicts, which propagates a false pass unread) and the Dep-consumers that build on it (at consumption time, carried in-protocol by CHALLENGE/BLOCK, §3.5 — a *delayed* channel, with q_V its retrospective, external-trigger-blind metric §24.5) — each of which catches it only if honest **and** if its criterion is *substantively sensitive* to `i`'s specific divergence. Under independence the false PASS survives all in-protocol detection with probability `∏_{j ∈ cone(i)}(1 − p_j)` over the honest validators `j` of `i`'s output, where `p_j` is `j`'s per-validator sensitivity — a **faithfulness** quantity (Lemma 1, Ch. 2), **not** a graph one (the aggregate detection probability of §24.2 is `1 − ∏(1−p_j)`). So the collusion residue is **redundancy-attenuated** by *sensitive* validation along the cone (a Prop 7 / §26.7 reading: more *sensitive* independent validation drives the survival probability down), and the genuinely-hard kernel localizes to the **sensitivity-sparse frontier** — nodes whose cone carries few validators with criteria that actually distinguish the corruption. This frontier is **non-constructive** (Lemma 1 forbids reading `p_j` off the apparatus, so it is not the *graph*-sparse set): it coincides with the **Pragmatic-level boundary** (Ch. 8) at aggregate `p = 0` (no sensitive validator — undetectable) and with the open **Laffont–Martimort** optimum for `0 < p < 1` (deterrable, the optimal bond/quorum still hard). The localization sharpens *where* the open kernel sits; it does not close it, and it does **not** reduce to graph connectivity — a large cone of *insensitive* validators attenuates nothing.

**26.4. An audit standard.** A GAAP analogue: procedures, audit, cross-industry comparability.

**26.5. Empirical validation.** Deployment ≥ 6 months: feasibility, the correlation Q ↔ real outcomes.

**26.5-bis. The un-operationalized form items.** Two members of the §3.4 form list have no *dedicated* pre-exec CHECK verifying them as stated: **non-redundancy** (part of well-posedness, Ch. 3 — CHECK-1b tests only its topological no-orphan proxy) and **deadline coherence along D** (item (6), child < parent — CHECK-3 guards only the *horizontal* Dep rule, and §25.1 rests on the vertical one). Both are implementation gaps, not model gaps: the requirement is stated and derivable, only its pre-exec check is unbuilt.

**26.6. Cold start.** At |𝒢| = 0 the LLM works on its prior alone (D_train), without organizational context. The Q-pattern layer has no data. The feedback loop's convergence (Ch. 15) starts with the first tasks — the question: at what |𝒢| do LLM recommendations become significantly better than the prior?

**26.7. Peer review of decompositions.** Horizontal exchange: "a colleague's analogous task had 5 steps, yours has 2 — want to look?" A free source of quality at no extra load. Formally motivated by the γ₁·γ₂ bound (Cor 2): an extra validator lowers the total gain.

**26.8. GFSO proxy metrics.** Computing Λ (amplification) and γ (damping) from system data. If Λ·γ > 1 on a segment — validation is not coping; strengthen control.

**26.9. Uniqueness: of the basis and of the protocol (the model-theoretic formulation).** Two questions of one *form* — uniqueness up to the right equivalence, each walled at a stipulation; but the frame-relative results are **opposite** (below): (a) a **positive** Beth-class canonicity, (b) a **negative** underdetermination (adequacy does not fix the behaviour map). **Global** uniqueness stays open on both sides for the one shared wall.

**(a) The basis — as a problem of model theory.** An HVP is a structure in the first-order **signature** σ = ⟨T, D, Dep, Del⟩ (V derived, Ch. 10); the primitives are the signature's relations/functions. "Another basis σ″ is adequate" is sharpened as: σ″ and σ are **mutually interpretable** over the class Mod(A1 ∧ A2) — each primitive of one signature definable in the other — and moreover the *round trip* recovers the original structure up to definable isomorphism, i.e. σ and σ″ are **bi-interpretable** (the classical model-theoretic notion; a strict strengthening of mutual interpretability — the relation under which two signatures are one structure "up to definability"; definitional equivalence is its special case without added sorts or parameters; the categorical analogue is Morita equivalence). In these terms:

- **Minimality** = σ has no proper sub-signature bi-interpretable with σ (no primitive definable from the rest). This is what Chapter 10 proves **constructively** (the loss table + independence).
- **Uniqueness** = **every** adequate signature σ′ is bi-interpretable with σ (canonicity up-to-bi-interpretation). This is **open**.

The reformulation turns "no sixth primitive from A1–A2 has been found" (Ch. 10 — a claim about a **search**) into a question decidable *in principle*: does there exist an adequate signature σ′ **not** bi-interpretable with σ? Exhibiting such a σ′ falsifies uniqueness; proving its absence establishes it. This supplies the right **object** of an answer (bi-interpretation is a checkable relation), not the answer.

**(b) The protocol — the same question at the FSM level.** The original formulation ("is any protocol addressing the 7 FMs under the Ch. 14 invariants isomorphic to the GFSO FSM?") lifts (a) to the transition structure. But the currency does **not** transport: bi-interpretation induces an isomorphism of automorphism groups, and on finite structures that is nearly all it measures — any two finite **rigid** structures with ≥ 2 elements interpret each other. Every adequate protocol *is* rigid: it is initialized (Ch. 14.2, the ASSIGN row — no initiation ⟹ the protocol is empty), deterministic (Inv-6), and reachable, and in such a system every automorphism fixes the initial state and propagates that along reachability to every state. So "every adequate protocol is bi-interpretable with the GFSO FSM" reduces to "is every adequate protocol rigid?" — and, **over the class of finite** such systems, is **vacuously true** (it identifies everything adequate and distinguishes nothing). The finiteness restriction is load-bearing and is a stipulation of the same species as the wall below: Inv-5 bounds *runs*, not the state space, so a rival with an unbounded retry counter is rigid, infinite, and not interpretable in the finite FSM — for it the statement is *false*. Either disposition kills the currency. The question (b) means to ask survives only in the currency proper to transition systems — **behavioural equivalence** (isomorphism of minimal reachable-reduced realizations): two adequate protocols may realize different behaviour maps while remaining bi-interpretable, and behavioural equivalence separates exactly those. So: protocol minimality (Ch. 14.2, no signal removable — analytic) is separated from uniqueness (every adequate protocol **behaviourally equivalent** to the GFSO FSM). Over *bare* adequacy this is settled **negatively** below (witnesses); it stays **open** only over a fully pinned design vector.

*What is established over the base machine* (`formal/GFSO/FsmCanon.lean`; the R′ extension excluded — its REOPEN gate is consumption, a graph fact, not a state-resident datum, so no finite composite is a deterministic automaton on it): over the alphabet of the 12 signals plus the timeout trigger, the deterministic automaton is the composite (state, retry-counter). Its behaviour identifies EXECUTING with REWORKING (§14.3: REWORKING is an attribution label, not a waiting point) and separates all other states; the observable that does so must carry the settlement mode (three distinct values: DONE = pass, ABANDONED = abandoned, ESCALATED = timeout), the verdict alone collapsing ABANDONED and ESCALATED. This measures the *irredundancy* half of protocol minimality (Ch. 14.3), not uniqueness. The step that would carry the canonicity of a behavioural class to *every adequate* protocol — the transition-system counterpart of part (a)'s σ-canonicity — is the closing lemma **does adequacy (the 7 FMs under the Ch. 14 invariants), over a fixed alphabet and observable, determine the behaviour map?** (inter-derivable with (b)-uniqueness itself, as (a)'s implicit-definability hypothesis is with Beth). Pushed through, it is **false over bare adequacy** — the (b)-side counterpart of (a)'s two excluded routes. Adequacy pins the *existence* of exits (the FSM-deadlock rows of Ch. 14.2: no state may be stuck — a behavioural necessary condition) and their finiteness (Inv-5, every non-terminal times out), but **not the *destination* of every timeout exit** — some destinations are forced (CANCELLING → ABANDONED, cancellation being authoritative; a genuine PASS → DONE), but the VALIDATING timeout is **free**: its geometry is a design choice, marked as such by the canon (§14.2/§14.3 "direct special target"; §24.7 lists auto-PASS in Assumptions-and-limitations with countermeasures). One free destination suffices. A protocol that routes VALIDATING-timeout to **ESCALATED** (escalate issuer inaction) instead of DONE(auto_pass) satisfies the identical deadlock-freedom and finiteness conditions yet differs behaviourally (settlement timeout vs pass on one history) — an adequate, behaviourally-distinct sibling (machine-checked, `FsmCanon.variant_*`). So bare adequacy underdetermines the map. And the freedom is **not one accident but multi-dimensional**: orthogonal to the timeout geometry, the retry bound `max_iterations` is a design parameter the canon fixes by fiat ("default 3", §14.3), pinned by no FM (any finite bound is deadlock-free and finite; *argued, not machine-checked*) — so already the bounds `{1, 2, 3, …}` give an **infinite family** of pairwise behaviourally-distinct adequate protocols (the prefix `ASSIGN·ACCEPT·DELIVER·FAIL·DELIVER·FAIL` settles into ESCALATED at bound 2 but is still live REWORKING at bound 3). Hence **(b)-uniqueness holds only relative to a fully pinned design vector** — every free cell (the timeout geometry *and* the retry bound *and* any further free target), not the timeout geometry alone; pinning a proper subset leaves a *decided* residual freedom (the `max_iterations` family is not an open question — Inv-5 demands only *some* finite bound, so the invariants provably do **not** exhaust it), and only once **all** free cells are pinned does what remains become the same undelimited-quantifier wall as (a). The FM and IC rows of the Ch. 14.2 table (the non-FSM-deadlock rows) constrain the payload, not the transition system, and do not close the gap.

**The asymmetry with (a) — on the *uniqueness* axis only, and demonstrated, not asserted.** First, what is *not* asymmetric: **minimality is positive on both sides** — (a) the constructive basis-minimality of Ch. 10, (b) the eleven-behaviour-class irredundancy above. The split is entirely on the **uniqueness/canonicity** half, and there the two questions share only the *wall* (uniqueness quantifies over an undelimited class, pinned to a stipulation — Ch. 8's boundary of the first kind); the *within-frame* verdicts are **opposite**. In (a), inside the FO/same-domain frame, Beth does real work — over structure-determining re-coordinatizations, semantic adequacy (implicit definability) **⟹** syntactic canonicity (definitional equivalence): a **positive** partial result over a **natural, non-circular** privileged subclass. In (b), inside the fixed-alphabet frame, the verdict is **negative**, and the reason is exact — not the coarse "adequacy is a looser constraint", but a difference of *logical position of the hypothesis*. In (a) the determination hypothesis (σ″ implicitly defines σ) is **strictly weaker** than the conclusion (bi-interpretability), so Beth bridges a genuine gap and the Beth class is a real, non-circular condition. In (b) the determination hypothesis ("adequacy pins the behaviour map") **coincides with** the conclusion — it is inter-derivable with (b)-uniqueness itself — so any would-be bridge would *be* the conclusion. The would-be minimization bridge (Myhill–Nerode) does not rescue this: MN converts "same behaviour map ⟹ isomorphic minimal realization", presupposing the behaviour map as input, whereas the (b)-gap is exactly one step earlier ("adequacy ⟹ behaviour map"), which the witnesses show adequacy fails to deliver. So the sharp, citable statement is stronger than "asymmetric": **(b)-canonicity holds over *no* natural non-circular subclass** — the only subclass on which it holds is defined *by its own conclusion* (protocols whose adequacy already pins the behaviour) — whereas (a) *has* such a subclass strictly weaker than its conclusion (the Beth class). The parity §26.9 asserts is therefore a parity of *form* (both are uniqueness-up-to-the-right-equivalence, both walled at a stipulation), not of *content*: (a) is canonical over a natural subclass, (b) is underdetermined over every natural one.

**What (b) *does* canonicalize — the minimality-forced skeleton (the positive core).** The negative verdict is not "nothing is canonical about the protocol". Adequacy pins a **skeleton**: the transition backbone every adequate protocol must share, each cell grounded in a Ch. 14.2 defect row (drawing on all four of its defect types — FM, FSM-deadlock, IC, Operation) — initiation (ASSIGN, Operation), accept → work (ACCEPT, IC), deliver → validate (DELIVER, FSM-deadlock: no state may be stuck — a delivered result must be routed to validation; the FM-3 "verify before complete" reading is the downstream consequence, not the §14.2 grounding), pass → complete (PASS, FSM), block → report (BLOCK, FM-5/7), challenge → dispute (CHALLENGE, FM-7), accept-challenge → close the dispute positively and re-offer the contract (ACCEPT_CHALLENGE, IC — the new spec it carries enters as an Inv-1 re-ASSIGN; what its removal would cost is the positive closure, §14.2), cancel → abandon (CANCEL/CONFIRM_CANCEL, authoritative), re-ASSIGN → offer (Inv-1). This forces **nine** behaviourally-distinct states — IDLE, OFFERED, EXECUTING, VALIDATING, BLOCKED, CHALLENGED, CANCELLING, DONE, ABANDONED — where the two terminals DONE and ABANDONED are forced *and separated in the verdict itself* (pass vs ⊥), not merely in the observable. What adequacy leaves free are **decorations**, and the design-freedom is exactly there: the **rework-loop** (whether to retry a FAIL at all, and the bound `max_iterations`) generates the REWORKING decoration, and the **timeout geometry** generates two free intermediate/attention states — OVERDUE (the first-timeout intermediate) and **ESCALATED** (which, unlike ABANDONED, is separated from it *only by the settlement mode* — both carry V = ⊥ — and settlement destinations are precisely what the negative witness shows free). The two timeout-geometry decorations are **machine-witnessed removable** while adequacy (deadlock-freedom + finiteness) holds — a protocol routing every first-timeout direct omits OVERDUE (`FsmCanon.noOverdue_*`), one folding the attention terminal into ABANDONED omits ESCALATED (`FsmCanon.noEscalated_*`), both checked deadlock-free; REWORKING's removability is **argued** (`max_iterations = 1` never enters it), not machine-checked. This **partitions the eleven measured classes exactly**: **9 forced** + **2 distinct-but-free** decorations (OVERDUE, ESCALATED) + **REWORKING ≡ EXECUTING** (an attribution label, no class) = 11 over 12 states. So (b) *has* a canonical object — the nine-state minimality-forced backbone, canonical **up to behavioural equivalence**; the *removability* of the two timeout-geometry decorations is machine-checked (REWORKING's is argued), while the *forcedness* of the nine (that no adequate protocol drops one) is the argued **lower bound** (a universal over protocols, outside `decide`) — and the underdetermination is precisely the decoration space; canonicity fails for the *whole protocol*, not for its forced core. **Over the *fixed* canonical alphabet the forced-vs-free split is a finite enumeration** (`FsmCanon.lean`) — distinct from the *outer* completeness "these are ALL the free cells over every admissible alphabet", which quantifies over the undelimited candidate space and stays walled (below). Each cell is graded on two orthogonal axes. *Strength:* **fatal** — removal makes the target unreachable (ASSIGN→OFFERED, BLOCK→BLOCKED, CHALLENGE→CHALLENGED, CANCEL→…→ABANDONED, DELIVER→VALIDATING: the initiation, the FM channels, and the terminals) — versus **sole/genuine-provider** — the target survives via a catch-all, so removal loses only the edge's *function* (ACCEPT, and the resolution/genuineness edges). *Function:* the **resolution** edges (RESOLVE_BLOCK, REJECT_CHALLENGE) are existence-forced (else FSM-deadlock) but destination-**free** — exactly the resume-vs-re-consent decoration; the **genuineness** edges (PASS, CONFIRM_CANCEL) stay catch-all-reachable, so removal leaves only the degenerate route (auto_pass; timeout-abandonment, losing in-flight provenance and the IC acknowledgment). Two destinations are **Inv-1-forced, not free**: re-ASSIGN→OFFERED and **ACCEPT_CHALLENGE→OFFERED** (it delivers a new spec ⟹ a contract change ⟹ re-consent — the unconditional case of the rule that routes a contract-changing RESOLVE_BLOCK to OFFERED). So the **free** set is *larger* than the timeout geometry + retry bound — it also carries the resolution/FAIL destination freedom — which *matches*, not overrides, the decoration hedge. And the grounding is **per-cell**: CANCELLING is forced by **IC** (Inv-4), *not* by deadlock — a one-step CANCEL→ABANDONED is deadlock-free and finite (`FsmCanon.oneStepCancel`), so CANCELLING is removable on the very axis OVERDUE/ESCALATED are; what holds it in the skeleton is the executor's CONFIRM_CANCEL acknowledgment, whereas OVERDUE/ESCALATED carry no FM/IC and are genuinely free. **The honest ceiling is unmoved:** every such witness is a canon-*internal* necessary condition (`FsmCanon.lean`, ~10 in the three functional kinds, with negative controls and the paired non-fatality `accept_not_fatal`); the sole/genuine-provider tier is honestly weaker than the fatal one; and the *outer* universal — necessary ⟹ forced over **every** adequate protocol — remains the argued lower bound. So the backbone is a lower bound on the canonical core and the decoration list a lower bound on the freedom; what is now enumerated (over the fixed alphabet) is *which* cells are forced, by *what* source, and *how strongly* — leaving only the undelimited-alphabet completeness walled.

**The wall (a characterized boundary, not a gap — cf. Ch. 8).** Completeness *inside* a delimited space is provable as a finite case split; completeness *of the labeling itself* — "no sixth primitive", "no other value scale", "why this many lists" — is **not** provable from inside, for it quantifies over an *undelimited* space of candidates. One wall stands behind four questions: (i) uniqueness of the primitives (here and Ch. 10); (ii) admissible validation scales — |L| = 2 is **derived** (Ch. 11), but "why not another scale" is the same quantifier over an unbounded class of scales, not an openness of |L| = 2 itself; (iii) "why this many lists" — the completeness of the 7 FM is **analytic** *modulo* CA1 (Ch. 12): the case split *inside* the delimited failure space is proved, while the completeness of the carve itself is exported into a **named** covering axiom — the boundary made explicit, not hidden; (iv) uniqueness of the protocol (b) — the same quantifier over the undelimited class of admissible **alphabets and observables**, the transition-system counterpart of (i)'s admissible signatures.

The reformulation (a) **localizes** the wall without demolishing it: to prove "no non-bi-interpretable σ′ exists" one must delimit the class of **admissible signatures** — what counts as an organizational primitive at all. That is the same undelimited quantifier, lifted one meta-level. Uniqueness therefore remains open in the exact sense: the reformulation fixes a checkable *form* of the answer (bi-interpretation) and an explicit *point* where the unprovability sits (delimiting the candidate class) — and precisely this distinguishes a **posed** open problem from "we looked and did not find".

**A partial result: σ-canonicity over the Beth class (the wall bites over a privileged subclass).** Take FO signatures σ″ over the same domain T, parameter-free, such that (i) every σ″-relation is L_σ-**definable** over Mod(A1 ∧ A2), and (ii) σ is **implicitly definable** over σ″ (any two models of A1 ∧ A2 with the same σ″-reduct agree on D, Dep, Del — σ″ *determines* the σ-structure). **Theorem.** Over this class, σ and σ″ are **definitionally equivalent**, hence bi-interpretable. *Proof:* (i) ⟹ σ interprets σ″; (ii) = implicit definability of σ over σ″, and by **Beth's definability theorem** (implicit ⟹ explicit for FO) every σ-relation is L_σ″-**explicitly** definable ⟹ σ″ interprets σ; one domain + no parameters ⟹ definitional equivalence (the special case of bi-interpretation "without sorts or parameters" above). ∎ At **bounded quantifier rank** the σ″-candidates are finite up to logical equivalence (Ehrenfeucht–Fraïssé) ⟹ canonicity over the class is a **finite case split** (the same shape as the CA1-completeness inside a delimited space). This is the **dual** of Chapter 10: minimality = σ is irredundant; Beth = every adequate *structure-determining* FO re-coordinatization is inter-definable with σ.

**The wall relocated, not removed — the exact dichotomy.** *Inside* a fixed FO/same-domain frame there **is** a fixed point (Beth converts semantic adequacy into syntactic canonicity without re-importing the equivalence itself). But *the frame itself* is not forced — and that is the true seat of the wall. Any delimitation of "admissible primitive" is **either circular** (the candidate "primitives = what is needed to state A1 ∧ A2" defines "the same labeling" *as* "bi-interpretable" — since "what A1 ∧ A2 states" is defined only up to inter-definability, i.e. it is the sought equivalence itself) **or frame-relative** (an unforced choice: FO vs second-order, same domain vs many-sorted, rank, *which* axioms). The frame boundary coincides exactly with the already-named empirical loci: membership in A1 ∧ A2 (Ch. 9; contact, not a theorem) and the stipulation of a logical frame (kin to |Act| = 2, Ch. 11, and to the covering axiom CA1, Ch. 12). **The honest limit of the result:** it is σ-centric (condition (i) takes σ as the yardstick), holds under FO + same-domain (excluding second-order primitives — e.g. **the transitive closure of Dep/D, reachability, provably non-FO** — and quotient interpretations, where mutual ≠ bi-interpretability genuinely diverge — both pushed through below: the two routes drain into a single frame locus; neither is a falsifier) and under the *strong* reading of "adequacy" = implicit definability; under the weak one ("σ″ merely carries the protocol") the result narrows to structure-determining FO re-coordinatizations, and the mutual-vs-bi gap remains. **Global uniqueness** ("every adequate σ′") stays open for exactly this reason — closing it requires stepping outside the frame, where the undelimited quantifier returns.

**Two excluded routes — pushed through: both drain into the frame locus; neither is a falsifier.** *Second order (Dep-reachability Dep\*).* Dep ⊂ T × T is an acyclic **FO** relation (Ch. 10); reachability Dep\* = the transitive closure, classically **non-FO** (the FO ≠ FO+TC separation, Immerman; the deadline order does not recover Dep\*). The leading test is **Chapter 26's own adequacy standard (mutual interpretability), frame-independently:** **(FO)** Dep\* is **inexpressible** in σ ⟹ σ does not interpret σ″ = σ ∪ {Dep\*} ⟹ σ, σ″ are **not mutually interpretable** ⟹ σ″ carries content **beyond** σ (not an equivalent re-coordinatization of the same labeling, but σ + an addition) ⟹ **not adequate** as a rival basis ⟹ **not a falsifier**. **(FO+TC / MSO)** Dep\* is **definable** ⟹ **redundant** ⟹ σ ∪ {Dep\*} is **bi-interpretable** with σ ⟹ **not a falsifier** (and "Beth fails for TC/MSO" is **beside the point** here: the definability of Dep\* is direct, not via Beth; Beth carries only the partial result above). Both frames ⟹ no adequate-and-non-bi σ′ on Dep\*; corroboratively, Dep\* is semantically **determined** by Dep (one closure of one relation) — under FO this "addition" is a derived non-FO query of the V tier (Ch. 10), not a forgotten sixth primitive. *Quotient interpretations (mutual ≠ bi).* The gap is real in the abstract, but it opens only under many-sortedness/quotients (σ inside σ′^eq) or weak adequacy; under **strong** adequacy (σ implicitly definable over σ′, FO, one domain, no parameters) **Beth on both sides ⟹ definitional equivalence ⟹ bi** — the gap closes. **No witness for organizational primitives exists** — the quotient route stays (b)-open, but without an exhibited witness. *The net of both:* the two routes are not two holes but **one** frame locus (the same unforced frame, already named); the second-order route is dismissed by Chapter 26's own adequacy standard, the quotient route lacks a witness. The wall is **narrowed and pinned** to a single screw — *the FO frame stipulation* (FO vs FO+TC/MSO; one domain vs many-sorted/quotient) — not to a general "every delimitation is circular". **Global uniqueness remains open** exactly here: under FO + same-domain there is no falsifier, but "no non-bi-interpretable adequate σ′ exists" is unprovable without delimiting the class of frames — the undelimited quantifier returns precisely as *the choice of frame*.

> **Falsifiability (the systematic register).** For every load-bearing claim of the canon — what observation would falsify it (type E empirical / M mathematical / C conditional-on-a-named-premise) — is maintained in `docs/falsifiability.md`. The register tracks the canon and is re-anchored to this document's numbering upon acceptance (its own policy: on any canon ↔ register disagreement, the canon is authoritative and the register is corrected). The completeness of the 7 FM is **analytic**: the case split is derived and the covering axiom CA1 is *argued* — which is why CA1 stays an axiom (§12.8, Chapter 27's (T)/(P) sort) — modulo the thin value/time residue, the single clock discharged; the theorems are derived. E1's 0/216 corroborates the *adequacy* of the derived categories to real failures (under the FM-1.b ↔ domain-boundary line) — it does not test an empirical postulate. Irreducibly empirical are exactly two **distinct** loci with a common root (contact with the world): membership in A1 ∧ A2 (Ch. 9) and the faithfulness of Ŝ to S (Ch. 2) — falsified differently (membership — a scope boundary; faithfulness — a dormant edge), but that is where the whole empirical boundary sits. The other claims are ◻ or conditional on a named premise. The completeness of the five links (Ch. 4) is falsifiable the same way the 7-FM basis is (a real directed action lacking a link, or with an independent sixth feature — open-from-inside); the named boundaries — Chapter 8; the methodology (Ch. 7) is [FORCED] over the ontology, while its cost/probability *values* are contextual (E, like S itself).

---

## 27. The machine-checked core

The formal skeleton of the canon (Chapters 10–15, 4) is checked in Lean 4 — on the language kernel, no mathlib, no `sorry`, no `native_decide`. Lean's kernel checks typing as judgment: "it compiles" already means "the types agree". This is not a proof of GFSO's substantive claims; it is an **audit of the axiomatic surface**: which canon claims are definitional, which are irreducible, and how many there are. The value is the map, not the depth: the proofs are elementary exactly where the canon's own arguments are elementary.

**The closure.** `#print axioms` over the whole development, plus a fail-closed CI guard (it walks the compiled environment and rejects any axiom outside the whitelist, any `opaque`, `sorryAx`, `native_decide` — in *any* namespace), yields **exactly three covering axioms**:

| Axiom (Lean) | Canon | Yields |
|---|---|---|
| `evaluation_completeness` — CA1 | Ch. 12 | the **7** failure modes |
| `morris_trichotomy` — CA-Morris | Ch. 13 | the **3** verification levels |
| `directed_action_completeness` — CA-Links | Ch. 4 | the **5** constitutive links (it bundles three closure branches; the representational one — REACHES-ternarity — is *sub-CA1*, §4.2 / Chapter 8) |

**CA2 (the single clock, Ch. 12) is NOT on this list.** The count of the three operational phases is axiom-free (`phases_exhaustive` — exhaustiveness with no assumptions; disjointness — from asymmetry, which is the definition of a strict causal order). Totality buys only the **reading** of the middle cell ("causally concurrent" ↦ "during") — a real price, but not a postulate about the *count*. So the single clock is carried as the hypothesis `SingleClock` in the signature of the axiom-free `op_trichotomy_of_total`, not as an axiom, and `#print axioms` does not show it. This is the (T)/(P) sorting applied honestly: a claim that does not cover a count is not listed as a covering axiom (`formal/GFSO/Time.lean` Part 2; the footprint confirmed by audit = 3 axioms + the carriers). Everything else is derived. The guard is not a one-off statement but an invariant the engine rejects violations of: it does not grep a named list of theorems (fail-open — forget a theorem and its axiom hides) but walks the entire environment and fails if the axiom set diverges from the whitelist. CI runs the guard on every change of `formal/` **and of the canon**.

**The (T)/(P) sorting principle.** Every "why exactly N?" in GFSO is one of two. **(T) An unfolding of a definition:** N is counted *inside an already-delimited space*; the kernel checks it (a function has exactly 3 parts — that is the definition of a function; 16 binary operations; |L| = 2 — a conjunction of two-valued predicates is two-valued). **(P) A covering principle:** "there is no third *kind*", where the candidate space is *not delimited*; unprovable from inside — a postulate (no third evaluation axis; no sixth primitive; no third action). Type theory sorts this mechanically.

**The honest caveat: "three" is a fact about the encoding, not about GFSO.** Which basket a claim lands in is the encoder's choice, and the development contains counterexamples both ways. |Act| = 2 ("no third action") is a covering principle in substance, but encoded as an inductive type with two constructors (definitionally) and therefore *invisible* to `#print axioms` — encode it as an axiom and the count becomes four. In the other direction: the single clock (CA2) *was* the fourth axiom, but the discharge showed the phase count is axiom-free ⟹ it is not a covering principle but a dischargeable hypothesis — and the correct encoding removes it from the list. The encoding invariant is **not the number but that the covering principles are finite and enumerated here with each one's placement disclosed** (what stands as an axiom, what is baked into a type, what is carried as a hypothesis). The guard makes *that enumeration* the thing the engine defends. (The definitional postulates of §1.4 kind (b) — A1, A2, |Act| = 2, and the d3/d4 source space (`KnowledgeSource`, at its own grade — §1.4) — are baked into *types* and cannot become Lean axioms without becoming vacuous; the hypothesis-form postulates of §1.4 kind (c) — act-surjectivity and act-injectivity (the \|L\| = 2 defense), no-declaration and no-luck (agent necessity), and the single clock / CA2 — are carried as *premises in signatures* of their theorems, visible in the type and dischargeable in principle, hence not axioms.)

**The wall** (§26.9). Type theory's one contribution: it **lets no assumption hide** — every such claim is forced to become an `axiom`, and `#print axioms` enumerates them.

**The honest formal status of the results.**
- *Checked (elementarily; some with no axioms at all):* Thm 1 and its converse, |L| = 2, Thm 2 (the 16-operation enumeration), the 4+3 geometry of the seven FMs with seven independence witnesses, **the operational trichotomy (before/during/after) — axiom-free** (exhaustiveness + asymmetry; the single clock discharged into a hypothesis), the FSM invariants (determinism Inv-6, finiteness Inv-5, revision = re-ASSIGN Inv-1, the cancellation handshake — checked over `Fsm.lean`, the conformance mirror of the engine table, whose single disclosed divergence from §14.3 does not touch any of them; the canon's own table is `FsmCanon.lean`), the signal counts 4/4/3/1, `state = fold(log)` (Thm 10/Thm 11), the base-machine behavioural quotient (Ch. 14.3 / §26.9(b): the twelve states carry eleven behaviour classes — EXECUTING ≡ REWORKING, the eleven states other than REWORKING pairwise-distinct under the joint admissible-set ⊕ settlement-mode observable — all pairs, cross-category included, in `FsmCanon.canon_eleven_pairwise_distinct`; with a negative control), and the §26.9(b) adequacy witnesses (bare adequacy does not determine the map): a one-edge timeout-destination perturbation behaviourally distinct from the canon on the same shared finiteness condition (`FsmCanon.variant_*`, its adequacy inherited by a one-cell edit), and two decoration-omitting variants that stay deadlock-free — one folding OVERDUE into ESCALATED (`FsmCanon.noOverdue_*`), one folding ESCALATED into ABANDONED (`FsmCanon.noEscalated_*`), each a uniform relabeling of one terminal's incoming destinations (machine-checked on the finiteness axis; for ESCALATED these include §14.3's exhausted-rework cell, so that path settles as ABANDONED — what is given up is the timeout-vs-abandonment *attribution*, not a channel, the FAIL row still existing and still settling; full adequacy argued from leaving every forced edge intact) — together witnessing OVERDUE and ESCALATED as free decorations on the nine-state minimality-forced skeleton. Also checked: the ordinal severity preorder ⪰_dom (§6.3) — reflexive, transitive and **antisymmetric on probe-sets** for *every* probe-set (proved by induction, not decided at one arity: `Grading.dom_refl_all`, `dom_trans_all`, `dom_antisymm_all`; ⪰_dom remains a preorder on *nodes*, distinct nodes with equal probe-sets dominating each other), plus witnesses for partiality (incomparable probe-sets left unordered) and count-independence (a larger survived-count does not dominate); axiom-free, `Grading.*`, with a negative control. And the per-edge forced/free classification (§26.9(b) inner) over the fixed alphabet, graded on two axes — strength (fatal vs sole/genuine-provider) × function (channel / resolution / genuineness): the **fatal** reachability witnesses `noAssign_strands_start`, `noBlock_strands_blocked`, `noChallenge_strands_challenged`, `noCancel_strands_abandoned`, `nodeliver_strands_done` (each with a paired positive `canon_*_reaches_*`, and the non-fatality `accept_not_fatal`); the **sole/genuine-provider** witnesses `accept_sole_content_consent`, `{resolveBlock,rejectChallenge}_sole_content_*`, `noPass_only_autopass_into_done`, `noConfirm_only_timeout_into_abandoned` (with genuine-edge contrasts); the **Inv-1-forced** destinations `canon_reassign_to_offered`, `acceptChallenge_dest_inv1_forced`; and `oneStepCancel_*` witnessing CANCELLING removable on the finiteness axis (forced by IC, not deadlock) — all canon-internal *necessary conditions* (negative controls included), the over-all-protocols forcedness staying argued.
- *Checked modulo a named covering axiom:* the completeness of the 7 FM (CA1), the three verification levels (CA-Morris), the completeness of the 5 links (CA-Links). The theorems *around* each axiom add only classical De-Morgan localization; the axiom itself — nothing. What is axiom-free around them is precisely the *structure*: the 4+3 geometry, the seven witnesses, the 3⊕2 count.
- *Out of scope (cited as classics, neither re-derived nor faked by a vacuous axiom):* Prop 3–9 (Blackwell, Simon, Hurwicz, the cascade) — stated over ℝ / information structures / probability, unavailable without mathlib.
- *Lemma 1 in Lean is definitional.* The apparatus is *defined* S-free (S is a free field; the apparatus sees only the formal projection), so the underdetermination of S is definitional, not derived; what is machine-checked is the axiom-free *consequence* `no_apparatus_yields_S` (no function FormalView → S exists), which step d4 uses. This is **not** "Lemma 1 proved" — it is its logical form plus an axiom-free consequence.
- *CA2 discharged into a hypothesis* — above; the footprint = 3 covering axioms.

**Two axiom-free facts already said in prose** (the machine *decides them off the table* rather than asserting): **no CHECK lives at the Pragmatic level** (pragmatics is mechanically uncheckable — Ch. 13, Ch. 8); **FM-3 and FM-6 are guarded by no structural CHECK** (FM-3 rests on A1 axiomatically, FM-6 on the protocol's deferred decomposition — Ch. 13). The other five FMs have structural guards.

**A green build is not a proof of the proof.** Hence the guard is fail-closed, and the semantic correspondence between a Lean statement and its canon section remains human/agent work — exactly as a passing `pytest` does not certify that the right tests were written. Details and the full coverage table — `formal/README.md`.

---

## 28. Conclusion

From two axioms (A1: verifiability, A2: decomposability) a protocol is derived with 14 formal results (6 theorems + 8 results: the 6 propositions Prop 3, 4, 6–9 + corollary Cor 5 + basis minimality). The exposition of this document runs knowledge-first: the theory of directed action (Part I) — the five links, the single contact seam, the derived agent, the failure root Ŝ∖S — grounds the chain axioms → primitives → compositionality (conditional) → failure modes → standards → protocol → graph → metrics → guarantees (Parts II–III). The formal results are unchanged by the order.

**The central results:**

1. GFSO Blackwell-dominates the status quo at any α > 0 (Prop 3). For any rational agent with any u — weakly better.
2. For the bounded-rational — improvement through constraints (Prop 4). For a non-adversarial agent at Δ > c and ℙ(θ_bad) > c/Δ: GFSO ≥ status quo.
3. Monotonicity of the information structure in α (Cor 5), t (Prop 6), and of the error bound exponentially in n (Prop 7) — **guaranteed under the protocol's discipline** (criteria track reality; a violation is the in-frame FM-3 — Chapter 3, not an external gap). No information threshold, no degradation; the net-payoff threshold is Prop 4's.
4. Incentive-compatible (Prop 8): honesty is optimal (IC as a dominant strategy, structural detection at a detection probability `p` — `p = 1` on the FSM-forced rows, the §26.3 cone aggregate on the acceptance row; non-adversariality needed only against collusion). Not morality — structure.

**Three pillars (inseparable — two immediately, the third beyond `t*`):** the protocol + the AI layer (Solver + LLM, Ch. 15) + self-measurement. Removing the protocol or self-measurement makes GFSO-channel improvement impossible outright; removing the AI layer does so past the capacity threshold `t*`, where the accumulated information outgrows what a human can process and the Prop 6 guarantees go vacuous (Ch. 23).

**The theory-model status (Part I).** Beyond the protocol: the necessity of the agent-as-carrier-of-domain-content is **derived** (the formal half cannot supply domain correctness by itself — Lemmas 1, 2; the alternatives eliminated, luck unstable; Chapter 3), not presumed. GFSO thereby not only prescribes but **explains** (pre-theoretical success, the 7 FMs, the Pragmatic-level boundary as open-from-inside) and **predicts** falsifiably (agent interchangeability, the applicability boundary). The agent-free ontology (five constitutive links, the agent an emergent scope-bundle; completeness by a covering axiom, the representational branch sub-CA1 — Chapter 4) forces the **methodology** (stop-and-replan + verify-vs-explore = the optimum over the knowable `c_check + E_FORM + E_FAITH`, Chapter 7). The honest audit localizes the narrow delta of new machinery; planning enters as an absorbed sub-step (planning ⊂ GFSO), not as the frame (Chapter 6); the primary value is **making-explicit** — the discipline, not mechanical novelty. The named boundaries and disclosed postulate residues — Chapter 8, where each entry carries its own tag; the real blocker is the *faithfulness* half of the decomposition-method-quality entry, that entry being a split whose generation-procedure half is an open problem, not a boundary. The continuous substrate (Chapter 5) grounds the same model: S unfolds into a controlled flow `ẋ = f(x,u)` with capture basins, the discrete `(t,{tⱼ}) ∈ S` its derived shadow of basin chaining, A1/A2 the conditions of the single contact seam (SINGLE-SEAM) — with the operational apparatus retaining its operative primacy and the formal results untouched.

---

## Changelog

> Each entry: what changed (driver) · affected chapters · downstream (code/API/UI).
> The empirical basis of the changes — `docs/EVIDENCE_LOG.md`.
>
> **v4.0 is the flagship and final statement of the theory.** It began as a knowledge-first
> re-authoring of the frozen v3.9 draft and was *completed* over the passes below. They are
> numbered rather than called addenda because none is an increment upon a shipped version: the
> version is what they jointly reached, and several of them repair drafting defects of the
> re-authoring itself, so a version boundary between "the move" and "its repairs" would cut one
> derivation in half. What would reopen this document is not a plan but a **falsifier**, and the
> falsifiers are enumerated per claim in `docs/falsifiability.md` — the register is the standing
> invitation, and closure here means the list of things we know how to do next is empty, never
> that the list of things that could refute it is.

**v4.0 · pass 1** (2026-07-16) — **the English final version: knowledge-first re-authoring of the frozen v3.9 canon.** The theory of directed action (formerly §18.10–§18.11, §17.4–§17.6) now LEADS as Part I; the operational apparatus follows as its consequence (Part II), with ten derivation bridges authored forward (foundation ⟹ apparatus) and the A1/A2 anti-laundering guard held louder than the recast. All formal results carried unchanged at their honest level; the operative primacy of the discrete apparatus is retained explicitly (Chapter 5 status note). The naming contract applied: FM-3 Verifiability→Veracity, FM-5 Currency→Freshness, REVIEW→OFFERED, TIMEOUT state→OVERDUE, CANCELLED→ABANDONED, CANCEL_ACK→CONFIRM_CANCEL, REWORK→REWORKING, NEGLECTED→ACCEPTED_RISKS, AUTO→AUTO_PASS (serialized; engineer-migrated at apply time with read shims); HBP→HVP; verification levels led by Syntactic/Semantic/Pragmatic; covering axioms CA1/CA2/CA-Morris/CA-Links; theorem/proposition labels Thm/Prop/Cor; loop gain Λ·γ; task graph 𝒢; contact seam operator "Contact"; SOLITUDE→SINGLE-SEAM; EMIT→EXTERNALIZE; objectification→making-explicit; [STD]→[known]; the v3.9 "Lemma 3" renumbered Lemma 2; the C1–C7 condition labels folded into their FM statements; the nine-CHECK count stated; the FM-6/5/7 phase-order note added. The Level-2 causal-correctness boundary relocated to the foundation's named boundaries (Chapter 8). The tier backbone (0–7b) and the three-kind postulate closure lifted into the front matter. The v3.6–v3.8 version-summary blockquotes of the RU draft not carried (provenance remains in `applied_gfso_v3.md`). Downstream: the 9 serialized renames = the engineer's migration contract (DB + shims, post-E3); `docs/falsifiability.md` re-anchored to this numbering upon acceptance; mirrors sync inside the version.

**v4.0 · pass 2** (2026-07-28) — **§26.9(b) done; a canon drafting gap closed.** The protocol side of the uniqueness question, previously one sentence ("the status is the same"), now carries a partial result parallel to (a)'s: the inherited bi-interpretation currency does not transport (every adequate finite protocol is rigid ⟹ the transported question is vacuously true), the working currency is behavioural equivalence, and over the base machine the twelve states carry eleven behaviour classes (EXECUTING ≡ REWORKING, an attribution label). The closing lemma — does adequacy determine the behaviour map — is pushed through and found **false over bare adequacy**: an adequate protocol routing VALIDATING-timeout to ESCALATED instead of DONE(auto_pass) is behaviourally distinct (adequacy pins exit existence, not destination — a §24.7 design choice), and the retry bound `max_iterations` is a second, orthogonal free design cell (an infinite adequate family), so uniqueness holds only relative to a fully pinned design vector. And the deeper finding: (b) is **not symmetric to (a)** — minimality is positive on both, but on the uniqueness axis (a) is canonical over a natural non-circular subclass (Beth), whereas (b) is canonical over *none* (its determination hypothesis coincides with its conclusion, so no Beth/Myhill–Nerode bridge applies). Driver: pushing the (b) closing lemma through against (a). Affected: §26.9(b), the 26.9 lead-in and "the wall" enumeration (four questions), §14.3 (the per-state admissible sets written out — a diagram-only gap; the forced REWORKING→BLOCK edge stated, derived from Ch. 14.2; the irredundancy sharpening of "induced"), Ch. 27 (Checked list), the Abstract ("12 states induced"). Machine-checked: `formal/GFSO/FsmCanon.lean` (the canon table, distinct from the `fsm.py`-mirroring `Fsm.lean`; axiom-free `decide`, a negative control, whitelist untouched). Downstream: `docs/falsifiability.md` protocol-uniqueness entries restated in the behavioural currency; `formal/README.md` protocol-uniqueness coverage row.

**v4.0 · pass 3** (2026-08-02) — **§26.9(b) inner enumeration; the RESOLVE_BLOCK destination sharpened.** The prior addendum left the forced-vs-free enumeration "walled"; that conflated the *outer* completeness (over undelimited alphabets — genuinely walled) with the *inner* enumeration over the **fixed** canonical alphabet, which is finite. The inner enumeration is now carried: each signal-destination cell is graded on two orthogonal axes — **strength** (fatal, removal strands the target; vs sole/genuine-provider, target survives via a catch-all) × **function** (channel-existence / resolution / genuineness) — each forced cell backed by a canon-internal necessary-condition witness (~10, in three kinds, with negative controls and a paired non-fatality witness). Two findings the enumeration forced out: **CANCELLING is forced by IC (Inv-4), not deadlock** (a one-step cancel is deadlock-free and finite — `oneStepCancel`), which is *why* it is skeleton while OVERDUE/ESCALATED are free decorations; and **ACCEPT_CHALLENGE→OFFERED is Inv-1-forced** (it delivers a new spec ⟹ a contract change ⟹ re-consent), the unconditional case of the rule that also splits RESOLVE_BLOCK — so **RESOLVE_BLOCK→EXECUTING is the *pure-unblock* edge**, a contract-changing resolution being an Inv-1 revision to OFFERED (§14.3 note; the §14.6 `deadline +2d` example). The 9-forced + 2-decoration count is unchanged — now *derived* per-cell, not asserted; the outer universal (forcedness over every adequate protocol) stays the argued lower bound. Driver: auditing the prior "walled" report against §26.9's own inner/outer distinction. Affected: §26.9(b) ("What (b) does canonicalize" — the closing enumeration), §14.3 (the RESOLVE_BLOCK pure-unblock note), Ch. 27 (Checked list). Machine-checked: `formal/GFSO/FsmCanon.lean` (the per-edge witnesses; axiom-free `decide`, negative controls, whitelist untouched). Downstream: `docs/falsifiability.md` + `formal/README.md` protocol-uniqueness rows extended with the per-edge classification.

**v4.0 · pass 4** (2026-08-03) — **the philosophy-of-science re-anchoring of Chapter 6, and six defects of the canon repaired along the way.** The Popper inheritance is restated at the grade that survived: falsifiability as a *single criterion of demarcation* did not survive its critique (holism; the statistical case; the historical objection), so what is inherited is the prohibition structure and pre-registration, while A1's office here is a condition on this theory's own domain — the objections to demarcation do not transport. Decidability is separated from probative force explicitly (a decidable-but-insensitive criterion is the FM-3 false-PASS). The Pragmatic level's object is stated in the received currency — an interventionist claim (Woodward; Pearl's `do`), the composition edge a conjunctive-intervention counterfactual and the §5.4 separator a reachability cut, both shadows of the controlled dynamics — which separates *formulation* from *verification*: the level is well-posed relative to a fixed carve, and only verification-from-inside is unavailable; the counter-move that bites is causal discovery, which lands on the discovery boundary because it presupposes the carve. Constitutivity is defended against model-based philosophy of science in its strongest form (models-as-mediators): the differentia is modality plus singularity — Link-2 ⊕ Link-5 are non-removable, and one seam judges rival estimates against one ontic S with a binary verdict. Statistical testing is shown to *instantiate* the canon's criterion↔truth split rather than to sit outside it: a fixed rejection rule supplies the decidable verdict, and only its calibration is imported. **Canon repairs:** the `SEV` gloss inverted its own formula and "sound" carried two incompatible senses (Ch. 6); the strengthening over Popper was mis-located on clause (i) when prohibition rides on clause (ii) under contingency (§2.1, Ch. 9, Ch. 6); pre-registration was attributed to verifier ≠ executor rather than to Inv-1 (Ch. 6); §5.2 mislabelled the never-written integration criterion FM-1.a, whose sub-clause presupposes an existing criterion; A1 was stated as "checkable" in Ch. 9 against "decidable" in §2.1 while both declare the appearances one fact; and Ch. 27 under-reported the machine-checked antisymmetry of ⪰_dom (on probe-sets — it remains a preorder on nodes). §24.5 now states the direction of its conditional: q_V furnishes the posterior branch, not the cardinal's likelihood. Three re-expanding paragraphs of §6.3 are folded into one, their clauses moved into the pointer table. Two questions are deliberately left open and flagged for a whole-canon pass: the scope of FM-1 for a criterion never written (Ch. 12 disagrees with itself between its root and its definition), and the routing of an undeclared dependency between FM-2 and FM-5. Machine-checked: no `formal/` source change; `#print axioms` = 3, whitelist 6. Downstream: `docs/falsifiability.md` restated at the same grades; `formal/README.md` and the `Grading.lean` header list antisymmetry on probe-sets.

**v4.0 · pass 5** (2026-08-03) — **the whole-canon sweep: eleven defects repaired, the two questions the previous pass deferred settled, and a drying pass.** Two sites closed permanent boundaries and now state their grade: §13.6's FM-3 row said "guaranteed axiomatically" where A1 clause (i) fixes only the verdict's *form* and no structural CHECK guards FM-3 at all (Ch. 27's wording), and §6.2's first dividend promised "no invisible blind spot" where coverage checks the *written* criteria — restated as what it does buy (an omission becomes a falsifiable absence; an off-joint seam is refuted post-contact as a ballast non-separator, the joints-target being non-constructive but **not vacuous**) with the insensitive edge named as the residue it is. Prop 4's proof dropped its own threshold ("holds for any ℙ(θ_bad) > 0", false below `c/Δ`), and the drop had propagated to the results table, the standalone assumption, the Universal-Improvement corollary and the Chapter-28 restatement; the threshold is now carried at every statement-level site, the corollary's two arms are separated by the premise each needs, and Mechanism 3's "strictly dominated" is corrected to dominance in expectation above the threshold. Cor 2 and Mechanism 2 wrote `=` where submultiplicativity — the inequality Prop 7's own proof runs on — gives `≤`. §25.1 derived a vertical deadline rule from Chapter 10's *horizontal* Dep coherence; it now rests on item (6) of the §3.4 form list, and §26.5-bis records both un-operationalized form items (non-redundancy, and this vertical rule) instead of one. §19 named `auto_pass` as the discovery mechanism for a fake PASS; the carrier is q_V's pass→later-fail term, `auto_pass` being the detector of issuer inaction. §14.2/§14.3 said "timeouts on every state" against Inv-5, which exempts IDLE by name. §13.5 filed "forgotten glue" under the Syntactic level, which is exactly what cannot see it. §5.5 cited FM-1.b to the chapter that guards it rather than the one that defines it, and the narrow-delta/large-value pair, stated twice in §6.1–§6.2, keeps the instance carrying the gloss. **The two settled questions.** The FM-1 insufficiency clause is **two-faced**, exactly as the truth condition on values already is: an *apparatus face* (the children against the *written* criteria — S-free, a-priori checkable, Chapter 10's two conditions) and a *domain face* (that those criteria capture the goal — the composition edge in S, §11.1). A criterion the goal requires that nobody wrote violates the domain face while CHECK-1 is vacuously green; it is FM-1, now tagged **FM-1.f** at the Pragmatic level, guarded at runtime by q_D so far as the issuer's verdict reaches past the written criteria and falling otherwise into q_D's named blind zone and the Chapter-8 boundary. Nothing in §12.4/§12.8 moves — CVC is stated against the true `V*(t)` — and the apparatus stays S-free, which is why the alternative route (re-quantifying joint sufficiency over the goal's criteria) was rejected. An undeclared dependency lands on **FM-2** exactly where the hidden coupling makes the children's criteria jointly unrealizable as written, and otherwise carries only its runtime face **FM-5**, whose carriers are BLOCK and q_Dep's denominator and only for a producible cross-task prerequisite (§14.2/§14.6); FM-1.d fires additionally where the omission also breaks entailment. §7 stated the FORM interior as an exhaustive "exactly three" while §13.5 puts the deadline and register checks inside FORM and §5.6 has to route an a-priori-checkable generator defect outside the three: the three are now stated as the **load-bearing** members — those that carry the composition claim — with the form list's remaining members (decidable criteria, the register, deadline coherence) a-priori over Ŝ by the same test and therefore FORM as well. **The drying pass** removed ≈11k characters of duplication that had no owner (an ontology recap in Chapter 9, the forced optimum restated in Chapter 20, a comparison table contained in its own extended version, a removal table printed twice, the single-clock discharge stated four times) and of text derivable in one step from what stands beside it; no result, boundary, grade, residue, falsifier or count was cut, and where a compression would have taken a unique clause with it, the compression was reverted. Machine-checked: no proof changed; `#print axioms` = 3, whitelist 6. Downstream: `formal/GFSO/Standards.lean` and `formal/GFSO/Fsm.lean` comment headers, `formal/README.md` (the IDLE corners are the canon's own, not divergences — the one live code divergence is untouched), `docs/falsifiability.md`, `docs/gfso_dependency_map.md`, `docs/CORE.md`, `docs/EVIDENCE_LOG.md`.

**v4.0 · pass 6** (2026-08-04) — **the post-sweep agenda executed: seven grade defects repaired, the boundary criterion stated, and the signal split corrected against the canon's own Inv-1 rule.** One class throughout: a grade fixed at one site and not carried to another. **Prop 8** concluded dominance from `Δ > cost(signal)` while §24.5 rates q_V's discovery trigger-dependent; the statement now carries the **detection probability `p`** and says what "structural" claims — the channel's independence of the counterparty's strategy, not `p = 1` — with `p = 1` on the rows whose consequence the FSM forces and the §26.3 cone aggregate `1 − ∏(1 − p_j)` on the acceptance row, whose `p → 0` limit is the Pragmatic-level boundary rather than a separate adversarial gap. **Cor 3** subtracted one upper bound from another ("net benefit → ∞"); it now states what Prop 7 licenses — the guaranteed bound falls by `γⁿ` while the checking cost grows linearly — and says explicitly that the difference of two bounds bounds nothing. **"Three pillars, inseparable"** was refuted by the canon's own Prop 6, whose proof invokes no AI layer; the claim now carries §15.3.1's threshold `t*`, immediate for the protocol and self-measurement, asymptotic for the AI layer. The **front matter** graded Thm 1/10/11 above the body's own standard (§11.1's "tautologically"; Q and the log are *defined* to make Thm 10/11 true) and the Abstract read as though the theorems carried the Lean load, where Chapter 27 calls the development an **audit of the axiomatic surface**; both now state the body's grade. **The boundary/gap criterion** — never stated, and applied where it was not earned — is now given once at Chapter 8 (an item is a boundary iff the canon exhibits an impossibility argument *from A1 ∧ A2*, in the Lemma 1 or Lemma 2 form; hardness and "not yet built" are open problems) and applied uniformly: every entry is tagged, the representational branch and the CA1 residue are re-filed as **disclosed postulate residues** rather than impossibilities, decomposition-method quality is filed as the split it already was in the body, and the adversarial optimum is re-filed to §26.3 as an **open problem** with only its `p = 0` limit a boundary. **Triage order** — unnamed at the decision §1.1 opens with — is now §15.4: what to fix first is derivable (the dependency cone through `E_D`/`E_Dep`, deadline order as tie-break), while ranking by *how badly* a node failed is the cardinal-severity boundary read at that decision. **The 12-signal minimum:** §14.2 justified ACCEPT_CHALLENGE by FM-5 ("the spec is never updated"), which is false under the canon's own rule — §14.3 admits ASSIGN from CHALLENGED and Inv-1 makes any contract change a re-ASSIGN, exactly the argument that denies REOPEN signal status. The signal survives on **IC** grounds (the dispute's positive closure, the arm REJECT_CHALLENGE answers in the negative), so **12 = the minimum stands and the split moves 5/4/2/1 → 4/4/3/1**. Beside the seven, the **adherence (α) debt**: the exogeneity premise is named at §18.1 and stands wherever the monotonicity results are used, its closure is filed as a boundary, and its derivable half is stated — α is an *observable of the graph*, which no §25.3 comparator can say; the decay dynamics stay an import of the Prop 3/4/8 layer. Machine-checked: `formal/GFSO/Protocol.lean` (`defectOf`, `defect_distribution` re-decided at 4/4/3/1); `#print axioms` = 3, whitelist 6. The claims guard gained a **rule for the signal split itself** — read off §14.2's count line at every run, with the retired ACCEPT_CHALLENGE↦FM-5 formulation anchored — after the old anchor's disappearance failed the guard, which is the guard working. Downstream: `docs/falsifiability.md` (Prop 8, Cor 1–3, §23, the boundary criterion, the α entry, protocol minimality), `docs/gfso_dependency_map.md`, `formal/README.md`, `formal/GFSO/Postulates.lean`, `formal/scripts/check_claims.sh`.

> **Repairs the cold passes surfaced alongside** (pre-existing, and one consequence of the split above). **CA1** was graded *derived* at §12.8 against Chapter 27's own (T)/(P) sort, which files "no third evaluation axis" as a covering principle — it is now *argued*, which is why it stays an axiom; the Abstract carries the same correction. **A1's decidability clause** was applied at two strengths: §5.6 states that neither goal topology is two-sidedly decidable, so the literal reading excluded maintenance exactly as it excludes `□◇A`. §2.1 now says what the clause is predicated of — a task's *result* — which places both: maintenance is not a task node but a generator emitting bounded-attainment tasks, each an A1 condition, while `□◇A` carries no such reduction. **§19.1's IC-minimality** quantified over "every IC-critical feature" while its table omitted **ACCEPT** (pre-existing) and **ACCEPT_CHALLENGE** (which the split above moved into IC): both rows added, 9 → **11 features**. The **d3/d4 source space** is now disclosed in §1.4 beside `|Act| = 2`, at its own grade — its exhaustiveness is *argued* by nested excluded middle, where `|Act| = 2`'s candidate space is undelimited, so the two four/two-constructor encodings are not read as one. Smaller: the CONFIRM_CANCEL and PASS minimality cells claimed a stranding that §26.9(b) machine-refutes (neither removal strands its target — what is lost is the non-degenerate exit); the worked example's CHECK-1 line omitted the feature children and so would have failed CHECK-1b as printed, and carried a `Dep` edge on a **non-producible** external API against §14.2's own rule and `E_Dep ⊂ N × N` — the coupling is now an accepted risk, as the example's own metric read-out already said it was; §10.2 sourced V to A1 where §10.1's table sources it to A1 + D; §17's Universal-Improvement corollary read strictness off the garbling's *determinism* rather than off its discarding a signal; the CHECK-7 illustration displayed the non-strict test for a strict parent criterion; and §12.1's definition of a failure mode did not literally cover FM-3 (a false PASS leaves the equation intact and breaks the truth), now stated against `V*` as §12.8 already does. The claims guard gained the **canon body** as a scan target for retired formulations — the omission that let two of these survive — with the Changelog excluded, that exclusion being load-bearing rather than cosmetic.

> **A further pass, mostly on the sites the grade repairs had not reached.** The CA1 regrade above had not propagated to §26's falsifiability blockquote (which still read "the covering axiom CA1 are derived") nor to four sites of `docs/falsifiability.md`, one of them quoting a canon sentence that no longer exists; all now read *argued*, and the contrast that entry draws with CA-Morris — argued from the unit of analysis versus inherited by citation — survives intact. `formal/check_axioms.lean` carried the retired **5 / 4 / 2 / 1** in a comment annotating the very theorem that now decides 4/4/3/1; the guard could not see it on two counts — the file was outside its watch set and its rule did not match the spaced form — so both were fixed and the rule re-controlled. §19.1's new count had not reached `falsifiability.md`'s "complete 9-feature enumeration"; `formal/README.md`'s definitional row said three where §1.4 now lists four, in a table that stakes itself on being falsifiably complete. **The worked example (§14.6) was repaired against the rules it exists to illustrate:** as printed it delivered on day 16 against a 14-day root deadline, which by §14.3 takes the root to OVERDUE — a state admitting no progress signal — so DONE was unreachable along the narrated path; the packet now carries d20 and the delivery lands at d13, the bracketed quantities are named **durations** with their derived deadlines printed, the contract-changing RESOLVE_BLOCK is shown as the Inv-1 revision §14.3 already said it was rather than a silent resume, the CHECK-8 seam is located at the child's own ASSIGN where the incompatible criteria were authored, and the q_Dep read-out now gives the canon's actual reason (the blocker is non-producible, hence no source node) instead of expectedness. Chapter 27's CA-Links row now says that the axiom bundles three closure branches and that the representational one is sub-CA1, which §4.2 and Chapter 8 state but that row did not.

> **And the pass after that, on what those repairs had themselves left half-done.** The §14.6 repair had moved the *root's* deadline and left the derived **child** deadlines where they were, so the narrated rework still overran them: Docs was FAILed on day 13 against a printed d11, which by §14.3 puts it in OVERDUE — no progress signal admissible — making the narrated fix-and-pass inadmissible and DONE unreachable a second time, one level down. The schedule now carries d5 / d7 / d12 / d15 / d17 under d20, with the slack on Docs and Demo stated as what it is (a rework cycle must fit inside its node's deadline or the node escalates), the day of each step named, and the Solver's CHECK-3 printing the ASSIGN-time d7 for Feature B rather than the d9 that a later revision produces — the +2d being recorded at the revision, where CHECK-3 re-runs by Inv-1. The **postulate closure** had gained its fourth definitional member in §1.4 and in `formal/README.md` but not in the two sites that carry the closure itself: Chapter 27's own parenthetical, which enumerated kind (b) short by one while citing kind (c) completely, and `formal/GFSO/Postulates.lean` — the register's designated machine anchor, which asserts "nine postulates, three kinds, none dropped". Both now carry `KnowledgeSource` at its own grade, and the anchor's enumeration runs 1–10. The **Conclusion** re-collapsed Chapter 8's four-way tagging into "the named permanent boundaries" and called the *split* entry the real blocker; it now names the boundaries and the disclosed residues separately and locates the blocker in the split's faithfulness half. Finally `check_naming.sh` claimed a scope it did not have — its header said the contract spans every addendum entry while the code read the first — and the honest resolution is not to widen it: the addenda use `→` for recounts, routings and **FSM edges**, which no shape test separates from a rename, so widening yields either false reds on the canon's own notation or a false green. The guard now reads the contract from the v4.0 entry and **says so**, recording that a rename introduced by a future addendum must be folded into that list or it will not be watched — a stated maintainer duty in place of a header that asserted the opposite.

> **The worked example, audited on its own.** Repaired four times and each repair leaving a residue one level down, §14.6 was verified line by line against every rule it illustrates, and four substantive defects came out — two of them residues of those repairs. Its **spec named three features and the decomposition built two**, so the canonical *passing* run shipped an unbuilt item under a printed "Coverage ✓"; the spec now names what is built. Sharpening c₁ to test statistics had **severed the last link between the root criterion and the feature children**, making them ballast: V(Feature A) = fail forced no cᵢ to fail, which is the §10 non-redundancy defect CHECK-1b tags FM-1.e. c₁ now carries a feature conjunct the feature children supply, which also makes the CHECK-7 demonstration genuinely *joint* — ⋀{criteria(A), criteria(B), criteria(Testing)} ⊨ c₁ — instead of one child carrying the criterion alone. The claim that a non-producible risk **cannot** take the decomposition branch of STD-2 was **false and is withdrawn**: what §14.2 forbids is promoting *the blocker* into a node, while a *mitigation* child is producible — which is why STD-2's ordinary grade can demand one at all, its own anchor being a datacenter fire with buildable mitigations (FM-1.b). And the register entry lacked the `justification` field that STD-1's schema mandates and the statistical grade turns on. Smaller: Inv-1's guard set is CHECK-1/1b/3 and does not contain CHECK-8, whose support at an ASSIGN is §15.3.4; the incompatible pair sits inside one child, so the FM-2 tag rides on §12.8's single relations-predicate rather than §12.2's two-node phrasing; §13.6 routes that semantic residual to LLM review where this run reaches it by executor CHALLENGE; CHECK-3's ✓ no longer silently covers the vertical deadline rule it does not guard (§26.5-bis); the BLOCK response is dated, BLOCKED timing out direct to ESCALATED with no OVERDUE to absorb a late answer; the +2d is noted as consuming Testing's entire float; the leaf's register pointer no longer reads as a leaf-level register (§13.1 makes that vacuous); dev2's re-consent after ACCEPT_CHALLENGE is narrated; and q_T's per-issuer attribution is marked as a slice the formula admits rather than one §15.2 defines. A second audit of the same section then caught an **unearned modal** in that very repair: "two-sided, and must be" was not forced by CHECK-7, which two one-sided repairs also satisfy. Rather than drop the claim, it is now *earned*, and the derivation is better than the assertion was — the two sides are forced by **different rules**: **A1** forces the parent edit (c₁ is what the PM validates the root against, and "all tests pass" is not a decidable predicate over a delivered release), and **CHECK-7** then forces the child edit (once c₁ asserts "0 high", the children must entail it). Repairing only the parent leaves the FM-1.d; repairing only the child leaves c₁ undecidable. With it: the elided CHECK-7 arms for c₂/c₃ are stated rather than skipped; §15.3.4's **Decomposition** row is cited for the split-level CHECK-7/8 in place of its ASSIGN row; the register entry is given STD-1's schema fields (estimate with impact, an invalidation *condition* rather than a source) and marked as a pre-fill the decomposer re-authors, per §13.1's rule that the register belongs to the split; the child verdicts are dated at their own seams, since three of the five could not be day-13 events; the REWORKING gloss separates the c₂ arm (Thm 1) from the c₃ arm (a direct check — Demo's V is still ⊥, and Thm 1 operates only on V ≠ ⊥); the precedent's magnitude is made consistent with the run's own +2d; and the seam-local reading of IC is stated with its residue named — the PM executes Demo and validates the root against c₃, so that criterion is in effect self-validated one level up, unbreached per-transaction but worth seeing.

> **The gate pass, on §14.6's remaining seams.** CHECK-7's demonstration repaired the entailment in the wrong direction: it sharpened the parent criterion c₁ with a conjunct (`0 high`) that no child criterion supplied, which can only make `⋀criteria(tⱼ) ⊨ cᵢ` harder — leaving **FM-1.d** standing in the one place the document shows CHECK-7 discharging. The repair is now two-sided, sharpening `criteria(Testing)` with c₁, and says why it must be. The closing FAIL read as one signal doing two things (`FAIL(c₂) → Docs to REWORKING`), where c₂ is a *root* criterion: the two seams are now separate — the Tech Lead FAILs Docs at the child seam, the PM FAILs the root at its own — and the tail is completed in days (Demo after Docs at d16, the re-DELIVER at d17, DONE inside d20). Role attribution is fixed at its source: the PM issuing the children would have made Demo, whose executor is the PM, a public node with coincident Issuer and Executor — the violation §14.5 names — so the Tech Lead, who decomposes, is stated as the children's Issuer and the child-level signals are his. And `formal/check_axioms.lean`, which opens by claiming it prints the footprint of *every* named result, did not cover the `FsmCanon` and `Grading` tiers that Chapter 27 cites as machine-checked; both are now listed, so the file's own claim is true of it.

*(The full v3.2–v3.9 changelog is the provenance record of the frozen Russian draft — `applied_gfso_v3.md`.)*

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










