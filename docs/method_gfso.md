# THE GFSO CONSTITUTION

> **Layer = METHOD.** The canon (`applied_gfso_v4_en.md`) proves and derives; this constitution
> governs. It states, as articles, the procedure every carrier of directed action — human, LLM,
> hybrid, machine — follows at every level of decomposition: what to check, what to present, what to
> write, which error to avoid. Each article names the canon object it rests on by a pointer «§x.y»;
> the object's statement, conditions, cases and proof live there and are not restated here. The canon
> is authoritative on any disagreement.
>
> **Register.** Neutral-ontic: an article states what holds in correct action; where it does not
> hold, the failure mode is named by pointer — a diagnostic fact about the action, not a sanction.
>
> **Provenance.** Every article is marked **`[DERIVED]`** — it follows from the canon;
> **`[ADDITION]`** — a design choice not derivable from the canon, stated with *where* and *why* it
> enters (the canon's own adopted decisions, §0.1, §20.5 kind (d), are marked so too); or
> **`[COVERING]`** — a covering axiom's "no further kind", postulated, not derived (§0.1, §20.5).

---

## PREAMBLE

Section I names the entities of directed action by pointer and fixes the method's reading where the
canon leaves one open; Section II states the laws — what holds in correct action, what the agent
presents to show it, and the failure mode of its violation; Section III names the permanent
boundaries whose "closure" is a logical error; Section IV is the rule of this document's amendment.

The implementation layer (12 signals, the 11-state machine, the Q metrics, the AI layer — Ch. 11, 12,
15, 17) is one admissible carrier of this description; any other carrier is applicable iff the
articles of Sections I–II hold in it. A decision not expressible in these entities lies outside the
domain (Art. I.15) or is the ¬holding of a law (Section II).

---

## SECTION I. ENTITIES

Each entity is the canon's object at its home. A1, A2 are read after `Contact` (Art. I.14) because
that reading shows their sense; their axiomatic status stays primary (§1.2, §3.7).

**Art. I.1 (the field: S, Ŝ, the gap Ŝ\S).** `[DERIVED]` S and Ŝ (§3.1); faithfulness and the
failure root, a used edge `e ∈ Ŝ∖S` — a wall (§3.2); S is not definable from the axioms (Lemma 1,
§3.4). Every failure the method diagnoses is located on such an edge (Art. II.7).

**Art. I.2 (the goal: G real, Ĝ posited).** `[DERIVED]` G, the real goal region (§6.2); Ĝ, the
goal vertex of Ŝ, its divergence from G the node axis (§6.8; Art. I.9); the goal underdetermines the
decomposition (§4.5).

**Art. I.3 (the task).** `[DERIVED]` for `spec`, `criteria` (§2.2); `[ADDITION]` for `deadline` —
where: a field of the task; why: activity without a time bound is indistinguishable from inactivity
(the canon's adopted design decision, §2.5); coherent along Dep (Art. II.4). The method's reading of
a criterion: a predicate over the result of execution (§1.3), never a description of an action — the
test is Art. II.1(a).

**Art. I.4 (decomposition, subgoal, joint, leaf).** `[DERIVED]` D, atomicity, the root (§2.4); the
graph of D a forest — acyclic, one parent per node (§15.3); separators and the joints, a faithful
decomposition cutting at the joints, separatorhood checkable by the counterfactual
`x₀ ∉ Capt_{S∖B}(G)` (§6.7); the leaf, bounded by κ, its depth agent-relative (the leaf test, §3.7).
- **A checkability carrier (an instrument)** — the method's reading: tooling that supplies a
  truth-maker for a parent's criterion (logs, dashboards, a runbook, a harness) is part of the contact
  apparatus (Art. I.11), not a passage in S. It is registered separately as contact tooling with its
  own A1 justification and enters neither joint sufficiency nor non-redundancy; declared a child of
  D(t), it is FM-1.e (§8.3; the test is CHECK-1.5, Art. II.11). A criterion that demands the
  instrument itself delivered is another object: the child is then necessary to that criterion, a
  demand beyond the goal lying in the criteria, not in the split (§6.7; at a root, §8.10).

**Art. I.5 (joint sufficiency, non-redundancy; and the written couplings).** `[DERIVED]` A
decomposition is correct under exactly the two conditions of §2.4, precisely those under which
compositionality holds (Thm 1's characterization, §7.3):
1. **Joint sufficiency** — §2.4, condition 1.
2. **Non-redundancy** — §2.4, condition 2; tested against the parent's criteria (Art. II.3).

3′. **Connectivity (the couplings written explicitly)** — form item (4), an explicit Dep, a member of
FORM's load-bearing interior (§4.5): every relation under which the result of `tₐ` enters the check
of `tᵦ` is written as a Dep edge (Art. I.8). It is a separate requirement of well-posedness, not a
third clause of correctness — the canon keeps membership (FM-1) and relation (FM-2) defects apart
(§8.2, §8.3) — and its violation is no mode of its own (§8.6; Art. II.3).

**Art. I.6 (capacity κ).** `[DERIVED]` κ, a property of the actor and of contact, the carrier of
A2's capacity premise (§3.7); a transition above κ owes a split (Art. II.2).

**Art. I.7 (criterion).** `[DERIVED]` A criterion's single semantic property is its truth,
two-directional (§8.4 "Truth"; |L| = 2, §7.1); its untruth is FM-3 (Art. II.8).

**Art. I.8 (dependency Dep, the seam).** `[DERIVED]` Dep and its deadline coherence (§2.7); an
independent primitive, stated in one direction only — a criterion referencing a result implies the
edge (§7.5, §9.5). **The seam (the integration edge)** — where one subgoal's result is fed to
another's input — carries its own integration claim (§6.5; Art. II.5).

**Art. I.9 (faithfulness: `Ŝ_used ⊆ S`, three axes).** `[DERIVED]` Faithfulness (§3.2) and its
three axes — edge, node (its illusory and absent halves), scale (§6.8, §6.3). Which half names which
mode, and where none does: §8.3 ("On the node axis"), §8.10. Faithfulness is opened only by contact
and not certified by the apparatus (§3.5; Art. II.9, III.1).

**Art. I.10 (ACCEPTED_RISKS).** `[DERIVED]` for the register and STD-1's four fields — `factor`,
`estimate (P, impact)`, `justification`, `invalidation_condition` (§2.4, §9.2); `[ADDITION]` for the
fifth field, `predictability_verdict` (Art. II.6). An entry missing any of the five is incomplete
under this constitution. What an entry may be — a risk event with an estimable P, never a scope
boundary, a known fact or a criterion — what the register admits and what an admitted entry
licenses: §9.2; its roll-up: §9.4.

**Art. I.11 (contact `Contact`, verdict, composition V=AND).** `[DERIVED]` `Contact` and SINGLE-SEAM
(§3.5); the apparatus, S-free (§3.3); V and ⊥ (§2.3); |L| = 2 (§7.1); AND unique (Thm 2, §7.2);
compositionality (Thm 1, §7.3).

**Art. I.12 (the agent: a carrier-function, not a subject).** `[DERIVED]` for the agent as a
scope-bundle seen only through Del (§4.2), the carrier of domain content relocated into Link-2 and
Link-5 (§5.1); `[ADDITION]` for **the uniqueness of `Del`** — where: on the relation `Del`; why: under
an ambiguous Del accountability diffuses and the attribution of a failure (Art. II.10) loses its
addressee (the canon's adopted design decision, §2.6). The plane `{T,D,Dep,V}` is authority-free
(§2.8); authority is the accountability edge of the Del hierarchy (§10.1), separation of duties a
boundary term at its seams (§10.3; Art. II.14). A failure is attributed to the node with the broken
compositional claim (Art. II.10).

**Art. I.13 (the five constitutive links).** `[DERIVED]` The five links (§5.1), minimal (§5.2),
complete under CA-Links (§5.3; covering, Art. III.2); contact homogeneous modulo delay (§3.5).

**Art. I.14 (A1, A2 — axioms; their second reading = the existence-and-nontriviality conditions of
`Contact`).** `[DERIVED]` A1 and A2 (§1.2), A1's two clauses (§1.3), A2 as a capacity cost (§1.4);
their second reading as the solvability of `Contact`'s output and the constructibility of its input,
with its named residue (§3.7). The second reading adds a role, not a derivation: the axioms' status
stays primary (§3.7), and this is to be held louder than the recast itself.

**Art. I.15 (jurisdiction — the domain of applicability).** `[DERIVED]` The model is needed iff
A1 ∧ A2; whether a goal lies inside it and whether it needs it: §2.1.
- **Inside and needed** — all articles of Sections I–II hold.
- **Within one executor's capacity** — the constitution is superfluous; held whole, the goal is an
  atomic root, where only its own verdict's truth bears (§8.4); split anyway, it is an ordinary node.
- **Outside** — a goal whose criteria are not decidable as stated, or one above capacity with no
  split into parts within it (§2.1, §20.3): no law of Section II is demanded. A goal outside the model
  is the model's boundary, not a failure mode (§8.10).
- **Step: reformulate first.** A goal whose criteria are not decidable as stated is brought inside by
  reformulating them into decidable predicates; the reformulation is itself directed action under this
  constitution.
- **Membership is a fact, not a declaration** — one of the two irreducibly empirical loci (§3.7;
  Art. III.5), established by contact with the domain, never by declaring it.

---

## SECTION II. LAWS

Every law states what holds in correct action, what the agent presents to show it, and, by pointer,
the failure mode of its violation. Where a law meets a permanent boundary, Section III is cited.

**Art. II.1 (verifiability — A1).** `[DERIVED]` Every goal and every subgoal carries criteria —
a finite nonempty set of decidable predicates (A1, §1.2; §2.2); the scale is binary, ⊥ the absence of
a value (§2.3, §7.1). An inability to decide pass/fail at checking is a spec defect, recorded in the
open, never masked by an intermediate "warning" (§7.1, forcing function). *Failure mode:* an
undecidable child criterion — form item (1) (§4.5), no mode — reported by CHALLENGE and repaired by
pinning a decision procedure (§11.2, §20.10); a goal whose own criteria are not decidable as stated —
outside the domain until reformulated (Art. I.15).

- **(a) A criterion is a predicate over the result, not an action.** Test every criterion: is it a
  checkable statement about the OUTCOME (e.g. "the 2→1 rollback dry-run makes the probe green")? A
  formulation of the form "do X" / "X is configured" / "the runbook is written" is not a criterion: it
  is spec direction, or a self-report of having acted in place of a verdict about the result — a mock
  (Art. II.5).
- **(b) Completeness of `criteria` relative to `spec`.** The probe: *does a `Result` exist passing
  ALL `cᵢ` yet failing the `spec` direction?* If yes, the criteria are incomplete — the absent half of
  Ĝ's node axis (§6.8). Close a known gap by writing the missing criterion, never by a register entry,
  which holds uncertain events, not scope or known facts (§9.2). Left open, its mode is read at §8.3
  (where the goal is split; at an atomic root no mode — a FAITHFULNESS failure met only at contact).
  Without this probe a thin set of criteria passes the whole constitution while the `V=AND` cascade
  is vacuously sufficient. The residue `spec \ criteria` has two halves:
  - (i) **Formal incompleteness** — the `cᵢ` do not cover the *declared* `spec`: readable over Ŝ
    before contact, by an agent's reading of the spec, not by a CHECK (FM-1.f is Pragmatic, with no
    check over the written criteria, §9.10; §17.4). Present the half-(i) probe **generatively**: over
    the `spec` — not over the already-written `cᵢ` — enumerate the axes of possible loss or distortion
    of the outcome, using the six-FM basis as a checklist of dimensions (argument / value / rule /
    phase, Art. II.7), and for each axis present a covering `cᵢ` where the `spec` requires the outcome, no
    register entry standing in for a criterion (§9.4), or, for an uncertain event threatening an outcome
    a written `cᵢ` states, a mitigation child or an ACCEPTED_RISKS entry (§9.3). Declaring
    (i) closed without that enumeration is a **¬holding** (vacuous AND, `c_check ≈ 0`): a probe over a
    poor Ŝ finds nothing and passes the letter falsely.
  - (ii) **Domain completeness** — that the criteria exhaust the `spec` FOR THIS DOMAIN (e.g. whether
    the list of accountable events of this transaction is complete) is a hypothesis about S
    (Art. II.9): closable by no probe over Ŝ, and no register item — an unwritten requirement is the
    criteria's defect, not an event (§9.2). It is read only at contact (§8.3 "Where FM-1.f is read";
    q_T, q_D, §15.4). Declaring (ii) established without contact is a false certification of
    faithfulness (Art. III.1); treating Art. II.1(b) as wholly FORM-closable is a ¬holding.

**Art. II.2 (decomposability — A2).** `[DERIVED]` A goal above its holder's κ (Art. I.6) owes a
split into subgoals within κ, recursively to the leaves — the leaf test (§3.7) — authored before
execution or in performance (deferred decomposition, §11.5; Art. II.17). *Failure mode:* declaring a
subgoal beyond its holder's κ a leaf is a claim of Del's, not of the split's (§15.4).

**Art. II.3 (a correct decomposition = a chain of necessary passages).** `[DERIVED]` A decomposition
is correct iff both conditions of Art. I.5 hold (§2.4, §7.3). Test non-redundancy against the
*parent's* criteria: a child's failure must break ≥1 `cᵢ ∈ criteria(t)`, not only the child's own
injected criterion (Art. I.5.2). A faithful decomposition cuts at the joints (§6.7); a subgoal that
is no necessary passage into the region the parent's criteria state is ballast, while a passage of a
demand beyond the goal lies in the criteria, not in this split (§6.7; at the root, §8.10).

**Alongside correctness (a separate requirement, not a third clause — Art. I.5.3′):** D is acyclic
(§15.3) and the couplings are written out in Dep (§4.5). *Failure modes,* each routed by the canon
where what was obtainable at the fixing showed it, and to FM-6 or FM-5 by its ground otherwise
(§8.6): ¬joint sufficiency — FM-1's insufficiency, its sub-types at §8.3; ¬non-redundancy — FM-1.e
(§8.3); a cycle in D — against A2's κ-recursion, CHECK-2's D clauses guarding no mode (§15.3); a
hidden coupling — no mode of its own, routed at §8.6, which leaves one denying no edge in no mode; incompatible criteria of two children — FM-2
(§8.3).

**Art. II.4 (composition — V=AND).** `[DERIVED]` Under a correct D the parent's verdict is the AND of
its children's (Thm 1, §7.3), AND the only admissible aggregation, `fail` absorbing (Thm 2, §7.2):
in correct action `fail` propagates up the tree. Dep's deadline coherence: §2.7. *Failure modes:* a
verdict departing from AND, either way — FM-4 as §8.5 reads it (in the protocol, §10.2); a Dep
deadline crossing — FM-5 (CHECK-3, §9.5); two children's criteria incompatible — FM-2 (§8.3).

**Art. II.5 (the seam — anti-mock).** `[DERIVED]` The integration a used composition edge asserts is
written out as a **separate, node-attributable, falsifiable claim** (AND-soundness's integration
implication, §6.5), carried by a written criterion whose truth-maker is the *real adjacent pair* —
the actual output of one node fed to the actual input of the next — not two separate self-reports. A
criterion able to pass while the link is really broken is a mock, not a criterion. Where the
integration criterion lives the canon does not fix, and a Dep edge need not carry one (§9.5, §11.5);
this constitution places it at the parent (Art. II.6, dividing scope). *Failure modes:* how the map
carries the integration names the mode — no criterion (forgotten glue), an insensitive one (a mock),
one the check refutes, or a written one the children's criteria do not entail (CHECK-7): §8.7, a
denial not obtainable at the fixing routed by §8.6; the insensitive case is the faithfulness residue
(Art. III.1).

**Art. II.6 (ACCEPTED_RISKS — declaring assumptions and exclusions).** `[DERIVED]` Every uncertain
event with an estimable P that the split's claim accepts rather than mitigates is declared in the
register (Art. I.10; STD-1, §9.2); a split without one is refused by CHECK-4 (§9.5). For an assumption
whose failure would break the goal:
- **declared and admitted** — what the register admits and what its bite is: §9.2; an entry for the
  split's own denial, or for a suspected missed joint, is written (CHECK-4's nonempty register) but
  licenses nothing (§9.2, §9.5);
- **undeclared but foreseeable** — FM-1.b where a written criterion states the outcome it threatens; where none does,
  the task's FM-1.f if the fixing showed the requirement (§8.3, §9.4).

**Predictability** — STD-2's grades and its burden of proof (§9.3); FM-1.b's test, pinned to the
domain's precedent (§8.3 "FM-1.b and the extraordinary"); what the extraordinary grade acquits:
§9.3. Predictability is presumed.

**The `predictability_verdict` field.** `[ADDITION]` — where: an ACCEPTED_RISKS entry, beyond STD-1's
four fields (Art. I.10); why: it records per factor the burden STD-2 places (§9.3), which otherwise
goes unwritten. For each factor state exactly one: (i) a precedent or a derivation existed at the
fixing ⟹ the factor is ordinary or statistical — a mitigation child, or for a statistical one an
entry with its justification; omitting both is FM-1.b; where no criterion states the outcome it threatens, the
question is the requirement's — the task's FM-1.f if the fixing showed it (§9.4); or (ii) neither existed ⟹ STD-2's
extraordinary grade, admissible to omit. Unproven unprecedentedness defaults to foreseeable ⟹
FM-1.b. An entry without the field is an incomplete record under this constitution, not yet the
mode (the canon's CHECK-4 reads STD-1's four fields, §9.5).

**The node gap Ĝ≠G — written into the criteria, not the register.** A demonstrable node gap
(Art. I.9) is a known fact, which the register does not admit (§9.2): close it in the criteria — the
missing criterion added, or a demand beyond what `G` needs dropped — by the issuer's revision, or the
executor's CHALLENGE where the packet is his (§12.10). Left open, its mode is read at §8.3 ("On the
node axis") and §8.10.

**Grouping correlated factors (FM-1.c).** `[DERIVED]` STD-3 (§9.4): correlated factors are grouped
into components by common root, each mitigated or accepted as §9.4 states; ungrouped — FM-1.c,
Pragmatic, CHECK-5 its Level-0 proxy (§9.10). The grouping method is an implementation choice.

*Failure modes:* a foreseeable factor undeclared — FM-1.b, or, where no criterion
states the outcome it threatens, the task's FM-1.f if the fixing showed the requirement (§9.3); the register omitted — refused by CHECK-4,
its proxy (§9.5); an entry without a `predictability_verdict` — an incomplete record under this
constitution's own field; a demonstrable node gap left unwritten — §8.3; ungrouped correlated risks —
FM-1.c.

**A goal's scope boundary ≠ a risk (do not conflate with ACCEPTED_RISKS).** A conscious scope boundary
has no materialization P and is no register entry: the goal's own criteria carry it, an unobvious
exclusion optionally marked by a SCOPE tag in the goal's spec (§2.2, §9.2). A capability a goal
criterion demands is, mapped to no child, FM-1.a, and mapped to a child whose criteria leave it out,
FM-1.d (§8.3). Scope extension is a re-ASSIGN of the goal with new criteria (§2.2, §12.3): CHECK-1
then flags the uncovered criterion (§12.10) and gates the split's re-admission (§11.5). An "excluded
factor" in this article is a risk exclusion (an event); a scope boundary never goes into the register.

**The auditor's discriminator (the P test).** It separates a risk from a scope boundary mechanically,
not by eye. For each item: is it an *event* that may materialize, or a design decision "we are not
building this"? An event is graded by STD-2 (§9.3) — ordinary → mandatory in the decomposition;
statistical → a child or an entry with justification, entering the roll-up; extraordinary →
admissible to omit. A design decision has no P → a scope boundary → the goal's criteria and CHECK-1,
NOT the register. An item without a P placed in the register is a category error, caught by this test.

**Dividing scope between siblings = Dep/a seam, NOT an exclusion field (for the decomposer).**
`[DERIVED, nontrivial — stated explicitly, since both the author and the decomposer read it
otherwise]`. A node's area is set by its criteria alone (V(node) is its criteria, §2.3; another's
criterion is not in its V). "What the neighbour does" is not an exclusion on this node but a Dep edge
from the producing neighbour to this consumer (§2.7). The executor satisfies only the criteria; Dep is
the seam's provenance, not a second obligation to reconstruct "what comes in / goes out". Keeping the
criteria coherent with Dep is the decomposer's work (CHECK-7, CHECK-8, §9.6). The integration
criterion no sibling closes alone (Art. II.5) this constitution places at the **parent** — a placement
it chooses, not a derivation (§9.5). So a child carries no "scope exclusion field": `criteria` (the
area) + `Dep` (the interface to siblings) + `ACCEPTED_RISKS` (the risks). The three "what I do not
do" — the division (`Dep`), the risk (`ACCEPTED_RISKS`), the scope boundary (the goal level,
CHECK-1) — live in three places, not in one bloated field on the node.

**Art. II.7 (the root of failure).** `[DERIVED]` Every failure of a node's validation is a used edge
`e ∈ Ŝ∖S` read on that node (§3.2, §8.1); the six failure modes name where it bites — arguments
(FM-1, FM-2), values (FM-3), rule (FM-4), time phase (FM-6 before, FM-5 during, none after) — a
complete independent basis modulo CA1, conjunctions expressible (§8.2, §8.8). *It holds:* an exposed
failure of a node's validation attributable to none of the six is outside the domain (Art. I.15) or a
refutation of the basis's completeness (Art. III.2); what instantiates no mode and refutes nothing —
a maintenance breach, a failure of the goal's setting — is §8.10's. E1: 0/216 needed a mode outside
the six (`EVIDENCE_LOG`).

**Art. II.8 (the truth of the verdict — two-directional).** `[DERIVED]` In correct action every value
a verdict is formed from is true. Untruth is FM-3, in either direction — its object and its two
directions: §8.4; a false FAIL is guarantee-safe (§8.4); a node's own check departing untruly from AND
is FM-4 (§8.5); an untrue PASS over missing work, or over an abandoned child's hole: §12.8.
*Boundary:* the domain-silent false PASS of a present but insensitive integration edge (§8.7 (ii)) is
**caught a priori by no discipline** — the faithfulness residue, a permanent boundary, not a hole to
be patched (Art. III.1).

**Art. II.9 (faithfulness is opened only by contact).** `[DERIVED]` (SINGLE-SEAM, Lemma 1, §3.5,
§3.4). No a-priori check over Ŝ establishes faithfulness (Art. I.9); its only verifier is `Contact`,
and every claim of a real chaining is an untested hypothesis until contact. *It holds:* faithfulness is
not declared established without contact; declaring "checked" with respect to domain-correctness
without execution is a false certification (a ¬holding). *Boundary:* not closable by strengthening
the apparatus (Art. III.1).

**Art. II.10 (attribution of a failure).** `[DERIVED]` Two-sided attribution (§4.4): a failure is
attributed to the node whose compositional claim it breaks, not to the "lowest" executor. Forward, a
node's error propagates into its children's criteria, its bound under Prop 7's model and premises
(§16.7); backward, a refutation travels along the explicit composition to the node with the broken
claim, carried by CHALLENGE and BLOCK (§11.3). A top-level planner's decomposition is a
pre-registered hypothesis: "the children's criteria held on the delivered result, the goal did not
arrive" is attributed to the split, not the executors (§8.7). *Failure modes:* attributing a failure
to an agent instead of the node with the broken claim; a node with no channel to carry the failure
signal — the defect then goes unreported into the verdict, what CHALLENGE and BLOCK exist to preclude
(§11.4); past the verdict the base protocol has no route to a correction (§12.14).

**Art. II.11 (the check over Ŝ — FORM — is mandatory and cheap).** `[DERIVED]` Before execution
every decomposition passes the a-priori check of **FORM** over Ŝ (§3.6): the form list and its
load-bearing interior (§4.5), checked by STD-4's battery of nine CHECKs at the Syntactic and Semantic
levels as far as the built checks reach (§9.1, §9.5, §9.6), at the split's admission, with what that
gate reports rather than gates (§11.5). FORM is not the §2.4 definition of correctness: the canon
keeps the two cuts apart (§8.10; Art. I.5.3′). Beside the battery the agent presents the checks
below — this constitution's own operational checks, each derivable from the articles it names and
admissible per Art. IV.1, not members of the canon's battery:

- **Level 0 (Syntactic; CHECK-1, 1b, 2–6, §9.5)** — CHECK-5 and CHECK-1b the Level-0 proxies of FM-1.c
  and of FM-1.e's orphan, the rest of FM-1.e unchecked (§9.10). Plus:
  **CHECK-1.5 (a passage ≠ a checkability carrier).** For each subgoal `tⱼ ∈ D(t)` present that `tⱼ`
  is a **passage** in S (a change of the domain's state toward `G`), not a checkability carrier
  (Art. I.4). The test: if the output of `tⱼ` is consumed only by the parent's criterion as a
  truth-maker and does not enter as a state into the `Capt_S` of the next joint, it is **contact
  tooling** — registered separately with its own A1 justification; declaring it a child of `D(t)` is
  **FM-1.e** (a criterion demanding the instrument itself delivered is Art. I.4's other object, read
  by the bridging rule). The instrument's separator counterfactual (col A) is invalid: removing the
  tooling disconnects the *check* of `G`, not its attainment, and passes col A falsely. `c_check ≈ 0`
  ⟹ it **always holds**.
  **CHECK-separatorhood.** Every subgoal `tⱼ ∈ D(t)` is a necessary passage (Art. I.4), presented by
  a **separator counterfactual** `x₀ ∉ Capt_{S∖tⱼ}(G)` (§6.7). A milestone without one is unshown as a
  separator — FM-1.e ballast where it is in fact none and no `cᵢ` breaks (§6.7, the bridging rule) and
  the fixing could show it, which the missing counterfactual leaves unexcluded — *even carrying a
  `[DERIVED]` mark* and *even carrying its own criterion* (an injected criterion does not legalize a
  decorative milestone). `c_check ≈ 0` ⟹ it **always holds**.
  **The bridging rule separator↔non-redundancy.** The two removability tests of a milestone live over
  different referents — non-redundancy over the parent's *posited* criteria (Art. II.3),
  separatorhood over the *real* `G`; they coincide under correct goal-setting. Present, per node and
  for each `tⱼ ∈ D(t)`, a **mandatory two-column artifact**: **(col A)** the separation
  counterfactual `x₀ ∉ Capt_{S∖tⱼ}(G)`; **(col B)** the concrete parental `cᵢ` that breaks when `tⱼ`
  fails. **The incompleteness detector:** col A presented with col B empty (a separator, no `cᵢ`
  breaks) is not a recording defect but a **mandatory firing**: a separator of `G` no `cᵢ` breaks is
  this split's FM-1.e (§6.7), and FM-1.f too where no criterion carries what `G` requires of it —
  sourced in the task (§8.3), repaired by the missing `cᵢ`, not by dropping `tⱼ` ⟹ **return to
  Art. II.1(b)**, half (i): the decomposer reports it by CHALLENGE to the packet's issuer, who alone
  adds the missing `cᵢ` (§9.7, §11.5). FM-1.f gates no admission (§9.10); the split's own FM-1.e is
  the decomposer's to repair, a mechanical flag gating admission only where his own repair or entry
  lifts it (§12.16). A `cᵢ` broken by a non-separator of `G` is a demand beyond the goal, lying in the
  criteria, not in this split (§6.7). A global assertion "there is no ballast / the tests coincide"
  without col B presented for every `tⱼ` is a **¬holding** (`c_check ≈ 0` ⟹ both columns are free);
  using the softer test to issue a verdict on a milestone when they diverge is a ¬holding.
  **The reverse test of the completeness of the separator list** (symmetric to the bridging rule,
  which closes a real separator without a `cᵢ`; this closes a real separator without a milestone): for
  every pair of consecutive joints `(tⱼ, tⱼ₊₁)` in `Dep` present that the transition between them is
  itself κ-atomic OR carries its own separator.
  **The burden of the κ-atomicity branch is not bare assertion** (symmetric to the presumption of
  predictability, Art. II.6): declaring `(tⱼ, tⱼ₊₁)` κ-atomic presents that it is
  realizable-and-checkable in one act of contact within κ (Art. I.6) — else it is above κ, owes a
  split (Art. II.2) and hides a joint. Unproven κ-atomicity defaults to a candidate missed separator =
  **[S-HYPOTHESIS]**, an ACCEPTED_RISKS entry with a `predictability_verdict` (Art. II.6). Using the
  κ-atomicity branch without presenting the κ bound when two readers disagree is a **¬holding**.
  **Splitting the outcome by articulability** (admissible per Art. IV.1.2 — it removes a point where
  two readers diverge): a discovered candidate omission splits as (i)/(ii) of Art. II.1(b).
  **(a) An articulable intermediate separator** — a named necessary passage (e.g. a reproducible
  root-cause repro between two joints) — is a **forced CHILD** (a faithful D cuts at the joints,
  §6.7), added as a milestone with its own `criteria` before admission to Level 1 (**FORM-closable**),
  NOT an ACCEPTED_RISKS entry: parking a real necessary passage in the register is inverted ballast, a
  missed joint disguised as a declared boundary. **(b) An inarticulable candidate** — a separator
  suspected from the list's incompleteness, the passage unnameable — only this is an
  **[S-HYPOTHESIS]** → a mandatory ACCEPTED_RISKS entry with a `predictability_verdict`, part of the
  split's own denial, licensing nothing (§9.2, §9.5) — **not FORM-closable** (a hypothesis about S,
  Art. II.9; Art. III.1/III.3). Declaring the joint list complete without this presentation is a
  domain `[DERIVED]` without contact (¬Art. III.1) — unlike the domain half of criteria completeness
  (Art. II.1(b)), which is no register item.
- **Level 1 (Semantic; CHECK-7, CHECK-8, §9.6)**, read over the active children (§12.6). Plus:
  **CHECK-anti-mock** — a guard beside the battery, reporting without gating (§9.5, §20.10): for a
  declared `Dep` edge whose consumer carries the coupling's criterion, that criterion SYNTACTICALLY
  references a concrete output artifact of the source node, not a standalone predicate re-describing
  the same fact (Art. II.5). FORM catches the structural form of a mock for free; semantic
  insensitivity remains a boundary (Art. III.1). Its discretionary end is governed by the stakes rule
  (Art. II.13).
  **The cost of CHECKING ≠ the cost of FORMALIZING** (it closes the Art. IV.1.2 loophole): present
  joint sufficiency **per criterion** — for each `cᵢ ∈ criteria(t)`, which children entail it and
  why; the presentation's `c_check ≈ 0` ⟹ it **always holds**. Only the RIGOR of the implication's
  proof (SMT vs reasoning) may be deferred by stakes (Art. II.13; §9.9), never its writing-out.
  Coverage of the criteria (CHECK-1) is weaker than the implication and does not replace it. A
  one-line assertion of the implication without a per-criterion carrier, while a mapping exists,
  leaves **FM-1.d** unexcluded (§9.6) — the mode itself only where the entailment fails.
  **The Art. II.1(b) probe is recursive — per node, not only at the root.** Present the II.1(b) test
  (*does a `Result` pass all `criteria(tⱼ)` yet fail the parent's `cᵢ`?*) for EVERY internal node as
  part of the per-criterion mapping, else the vacuous-AND incompleteness reproduces one level down.
  Its formal half (i) runs always where it is cheap over Ŝ (`c_check ≈ 0`: numeric bounds, cheap SMT)
  and elsewhere — a costly decidable check, or the Semantic level's informal end — as far as the
  prevented risk justifies (§9.6, §9.9); its domain half (ii) goes into the node's ACCEPTED_RISKS as
  the split's own denial, licensing nothing (§9.5), and is closed only by contact (Art. II.9). A `⟸`
  mapping table without a presented per-node probe (i) leaves **FM-1.d** unexcluded.

FORM catches defects of form *for free* (over Ŝ, without contact). *It holds:* a decomposition that
has not passed Level 0 does not go to execution, save what §11.5 reports rather than gates. *Failure
mode:* admitting to execution a decomposition whose Level 0 has not passed. **FORM does not establish
faithfulness**: Level 2 is the contact axis (Art. II.9, III.1).

**Art. II.12 (contact and repair — stop-and-replan).** `[DERIVED]` (the two mechanisms, §18.1; their
optimality under Prop 7's named cost model, §18.2). **The wall dichotomy:** every wall belongs to
exactly one of FORM ⊕ FAITHFULNESS (§3.6); localization assigns it to one. At a wall (a contact
verdict `e ∈ Ŝ∖S`) correct action: **(1) STOPS** — breaks the cascade, building nothing further on a
refuted claim (else the error compounds, Art. II.10); **(2) LOCALIZES** — which claim exactly is false,
and its class (by attribution, Art. II.10); **(3) REPAIRS LOCALLY** — contact grounded the touched
edges; the rest of Ŝ, if correct, survives (§7.3) — (2)–(3) being §18.1's MARK; **(4) RE-DERIVES** —
re-runs FORM (Art. II.11) over the updated Ŝ; **(5) only then proceeds**. *It holds:* no movement over
a graph already known to be false. What the regime's optimality is and is not: §18.2. *Failure mode:*
continuing execution on a refuted claim without repair.

**Art. II.13 (the stakes — verify-vs-explore).** `[DERIVED]` The choice at every node and level
between VERIFY and EXPLORE, and its rule — the Syntactic level and cheap-SMT Semantic checks always,
the informal end only where the prevented risk justifies the cost (§9.9; front-loaded on the
executable segment, §18.1). Exploration is a conscious substitution of contact for the a-priori
check, not the absence of a plan. The structure is derived; the values are contextual and not
prescribed (§9.9). **Cheap reversibility — the method's test of the stakes** `[ADDITION]` — where: the
default at a node; why: a cheap reading of the stakes of §19.3, item 3, subordinate to §9.9's rule,
which it never overrides: a node is cheaply reversible ⟺ rolling it back (a) is within the κ of one
contact (Art. I.6) and (b) leaves no trace in the `Ŝ_used` of the child subtree (no downward cascade,
Art. II.10); otherwise its irreversibility enters the prevented FORM risk §9.9's rule weighs against
`c_check` before execution. On a cheaply reversible node the default is EXPLORE; "always VERIFY at Level 0" does not carry over to the discretionary level. *Failure modes:*
verifying a cheaply reversible node beyond the justified level (gold-plating); refusing to verify an
expensively irreversible one (betting on catastrophe).

**Art. II.14 (delegation, the IC seam, the uniqueness of the accountable party).** The uniqueness of
`Del` — `[ADDITION]` (Art. I.12); IC as a property of the seam — `[DERIVED]` (§10.3). Each task has
exactly one accountable agent (§2.6). Public and internal nodes, separation of duties at a public
node, self-verification at an internal one and when its self-signed verdict is carried: §10.3; check
and signature: §10.2. The `verifier≠executor` gate fires at the seam, not on every node (§10.3): the
public result's verdict is signed independently, not link by link at every internal node; a split's
admission is the decomposer's own act (§11.5). A fully self-assigned agent keeps making-explicit, not a
guarantee (§10.3, §16.13, §19.3). *Failure modes:* an ambiguous `Del` (diffusion of accountability);
"the coincidence of the roles" at a seam — one context that sets the contract, delivers and accepts its
own delivery — not "the issuer's own pair of duties, forming the task and signing its verdict" (§10.3);
declaring a public seam internal in order to escape an independent signature.

**Art. II.15 (contract immutability, revision ≠ refusal).** `[DERIVED]` Inv-1 — the packet immutable
after ASSIGN, a change a **revision**, a re-ASSIGN under the same id into OFFERED, not a CANCEL
(§12.3); a revision does not cascade, the structural guards flagging staleness and content staleness
met at contact (§12.10); only entering CANCELLING cascades (§12.6); Inv-7 — a stable id, the log the
immutable record (§12.11); Inv-3 — a FAIL names the failed criteria (§12.8); Inv-5 — finiteness
(§12.12). *Failure modes:* shifting the criteria after assignment without a revision (goalpost shift)
— FM-5; destroying the subtree on a revision (loss of valid work) or re-issuing the id (orphaning the
edges); an unsubstantiated refusal — ¬transparency; a non-terminal state other than IDLE without a timeout —
¬finiteness (IDLE is no breach, §12.12).

**Art. II.16 (transparency and the structural record).** `[DERIVED]` Thm 11 — every decision has its
record `R(d)` (§11.6); opacity inside the protocol is a measurable defect (its corollary). **The
provenance of load-bearing assumptions:** every load-bearing assumption and every structural choice of
the *produced* decomposition carries in `R(d)` its provenance `[DERIVED]` / `[ADDITION]` — keeping the
derivational core apart from the named additions is a property of the produced decomposition, not only
of this document. **A structural `[DERIVED]` ≠ a domain `[DERIVED]`:** `[DERIVED]` marks derivability
from the canon (the form) only; all DOMAIN content — which joints and assumptions this task actually
has — is a hypothesis about S until contact (Art. II.9), marked form-`[DERIVED]` +
content-`[S-HYPOTHESIS]`, never a bare `[DERIVED]`. A domain `[DERIVED]` without contact is a false
certification of faithfulness (Art. III.1). *It holds:* accountability separates a process defect from
an agent defect — FAIL means the task did not meet its criteria, not "the agent is bad" (§11.3, a
signal is a report). *Failure modes:* an unrecorded decision in the domain; **an unmarked design
assumption passed off as derivable** (a transparency defect — it hides a named boundary as a
derivation).

**Art. II.17 (the time phases — definability, freshness, and none after).** `[DERIVED]` The three
phases relative to the application — before, during, after — exhaust the operational axis with no
assumption about the shape of time (§8.2, §8.6):
- **Before (definability, FM-6).** Where a node's decomposition is not yet definable, the node stays
  **open to deferred decomposition** (§8.6, its remedy; §11.5): it carries the explicit status
  "decomposition deferred", declared neither a leaf nor correctly decomposed until the information
  appears — not a silent assumption of coverage. *Failure mode:* declaring coverage where `D` is not
  yet definable — FM-6.
- **During (freshness, FM-5).** A changed `spec` makes the former `D` stale: the contract changes by a
  revision (Art. II.15), without a cascade; plus Dep's deadline coherence (Art. II.4). *Failure mode:*
  executing on a `D` not updated to a changed `spec` — FM-5.
- **After (no condition).** What a failure found later is, and whose: §8.6; which metric reads it:
  §15.4. What the after phase needs is the protocol's: a route from the finder to the node's issuer
  and his move to correct it (Art. II.10) — past a PASS a REOPEN where §12.14 admits it — the node not final and, below a root, under the
  issuing condition (§12.7); in the base protocol none, a named residue (§12.14).

The single clock is a discharged hypothesis, not a boundary (§8.2, §20.5; Art. III.4).

---

## SECTION III. BOUNDARIES

The canon's boundary list (§20.8) and what lies around it (§20.9): the Pragmatic-level boundary —
Art. III.1, III.3; the completeness-of-the-carve wall, with its covering placements and their residues
— Art. III.2, III.4(a); the edge of the A1∧A2 domain — Art. I.15. Every article of this section is
`[DERIVED]`, save Art. III.2's `[COVERING]` closures. "Closing" a boundary is the logical error
"incomplete by design, therefore complete" (§4.6, §20.1), stated here as "it is an error to…".

**Art. III.1 (the faithfulness residue).** `[DERIVED]` The Pragmatic-level boundary's face on the
value (§20.2; §3.5): the domain-silent false PASS of a present but insensitive integration edge
(§8.7 (ii); Art. II.5, II.8), caught a priori by no discipline and silent even at contact. *It is an
error:* to declare it closed by strengthening CHECK, the apparatus or the safety net; to declare
faithfulness established without contact (Art. II.9).

**Art. III.2 (completeness — covering, not closed; three closures).** `[COVERING]` The five links
(Art. I.13; CA-Links, §5.3), the six-FM basis (Art. II.7; CA1, §8.2) and the three verification
levels (CA-Morris, §9.1 — the first two the a-priori FORM check of Art. II.11, the third the contact
axis, Art. II.9, III.1), each complete under its covering axiom at its own grade (§20.5). Outside the
articles stand two more covering principles, neither a Lean axiom: |Act| = 2 (§7.1) and the AI
layer's covering of the inference types (§17.2; §20.5). The representational branch holds modulo
REACHES-ternarity, START folded (§5.3). *It is an error:* to eliminate START as a separate role
(rejecting its fold breaks 3⊕2, §5.3); to pass off "the five links" as a completeness theorem beyond
the covering. Falsifiable two ways (§5.4).

**Art. III.3 (decomposition-method quality).** `[DERIVED]` The Pragmatic-level boundary's face on the
production of a split (§20.2): EXTERNALIZE formats and grades a seam but does not make it faithful
(§4.5). The engine's generator (bare-SEARCH ⊕ gfso-AUDIT, `auto_decompose()`) converges to a
completeness-audited reference and does not guarantee the seam's faithfulness to the real domain — a
permanent boundary, and a blocker under execution (E3, the engineering demo). *It is an error:* to
pass off the EXTERNALIZE form or convergence-to-a-reference as a guarantee of a faithful seam.

**Art. III.4 (the representational residue and the covering-axiom residue).** `[DERIVED]` (a) The
representational branch — a disclosed residue under the carve wall (§5.3, §20.7; Art. III.2). (b) The
CA1 residue (§8.2) lies around the theory, not at a boundary (§20.9). The single clock is not in it:
the count of the three phases is axiom-free, CA2 discharged, FM-5 generalizing under concurrency
(§8.2, §8.6, §20.5). *It is an error:* to pass off the operational trichotomy as depending on a single
clock.

**Art. III.5 (the irreducibly empirical loci).** `[DERIVED]` Two loci, both rooted in contact: whether
a goal lies inside the model (Art. I.15) and the faithfulness of Ŝ to S (Art. I.9, III.1) — §3.7; every
other load-bearing claim is typed in the falsifiability register (`docs/falsifiability.md`).
*It is an error:* to declare an empirical locus resolved by declaration; faithfulness is measured
**independently of the success itself** (§4.6) — otherwise a counterexample is re-explained after the
fact.

---

## SECTION IV. AMENDMENT

The meta-rule of this document's own extension. Every article of the section is `[ADDITION]`:
**where** — the procedure for changing the constitution; **why** — the canon contains no rule of this
document's extension, and without one amendment would be uncontrolled (an article without
derivability or consistency is a loophole). The criterion of derivability (Art. IV.1.1) carries the
canon's own requirement (§2.8); the procedural harness around it is a choice.

**Art. IV.1 (the rule of amendment).** `[ADDITION]` A new article (an entity of Section I, a law of
Section II or a boundary of Section III) is admissible iff three conditions hold together:
- **Art. IV.1.1 (derivability from the canon).** The article is derivable from
  `applied_gfso_v4_en.md`; an article with no canonical justification is inadmissible.
- **Art. IV.1.2 (no loophole).** The article creates no point at which two readers can diverge on what
  it requires, and opens no process step at which action in the domain remains ungoverned (Art. IV.3).
- **Art. IV.1.3 (preservation of consistency).** The article contradicts no article in force and
  closes no boundary of Section III (closing a boundary by a loophole is grounds for rejection, §4.6).

**Art. IV.2 (the priority of the boundaries).** `[ADDITION]` On a collision of a new article with a
boundary of Section III the boundary prevails: an article requiring the closure of a named boundary is
inadmissible whatever its other merits.

**Art. IV.3 (completeness of process coverage).** `[ADDITION]` An amendment is admissible only if
after it every step of directed action (goal-setting · building Ŝ · decomposition · the form check ·
execution · contact · repair) remains governed by some article. A discovered uncovered step is grounds
for a new amendment under Art. IV.1, not for a silent assumption.

**Art. IV.4 (repeal).** `[ADDITION]` Repealing or weakening an article in force is admissible only on
proof that its canonical ground has been withdrawn in the canon itself (through the canon's
Changelog); until then the article stays in force.
