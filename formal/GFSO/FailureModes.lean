/-
  GFSO — the 7 FAILURE MODES as a complete independent basis (§12.2–§12.8). The centerpiece.

  Canon `docs/applied_gfso_v4_en.md`:
    §12.2 internal FM (function = arguments{membership,relations} · values · rule)  → FM-1,2,3,4
    §12.3 external FM (computation phases before/during/after)                     → FM-6,5,7
    §12.4 completeness-as-basis (exhaustive case split over the two axes)
    §12.5 independence (each FM realizable in isolation — 7 witnesses)
    §12.6 the summary table (locus → FM)
    §12.8 the theorem `CVC(t) ≡ the conjunction of the seven conditions`, modulo **CA1**
    (covering); CA2 (single clock) is discharged there, not assumed

  THE POINT of this module: the canon proves 7-FM completeness "modulo CA1". In prose that
  clause is a sentence a reader must trust. Here it becomes an **explicit, named Lean `axiom`**
  (`evaluation_completeness`) over an **uninterpreted** correctness predicate `correct` — so it is
  a genuine assumption (not refutable by any literal) and appears in `#print axioms` of every
  result that leans on it. Everything else (the 4+3 geometry, the case split, the 7 independence
  witnesses) is derived with no hidden gap. That is the honest translation of "modulo CA1".
-/

namespace GFSO.FailureModes

/-! ### The 4+3 geometry (§12.2–§12.6) — axiom-free -/

/-- The seven failure modes (§12.6). -/
inductive FM | fm1 | fm2 | fm3 | fm4 | fm5 | fm6 | fm7
deriving DecidableEq, Repr

/-- **Denotational axis (§12.2).** A function `V(parent)=f({V(tⱼ)})` has exactly three components —
    arguments, values, rule — and the argument set splits by its two set-properties (membership:
    which elements; relations: their compatibility). Four loci, no more (a set has only elements
    and relations; a function only args/values/rule — §12.2). -/
inductive DenotLocus | argsMembership | argsRelations | values | rule
deriving DecidableEq, Repr

/-- **Operational axis (§12.3).** The formula's *application* is a process in time with exactly
    three phases relative to the evaluation event: before, during, after (the trichotomy of
    a connected evaluation interval — §12.8: linearity of time is NOT needed for the phase
    count; Hoare pre/inv/post is naming, not source). -/
inductive OpPhase | before | during | after
deriving DecidableEq, Repr

/-- A failure locus is one axis or the other (§12.4: function ⊎ computation). -/
abbrev FailureLocus := DenotLocus ⊕ OpPhase

/-- **The §12.6 summary table: each locus → its failure mode.** Note the operational order:
    before→FM-6 (Feasibility), during→FM-5 (Freshness), after→FM-7 (Feedback). -/
def locusFM : FailureLocus → FM
  | .inl .argsMembership  => .fm1   -- args membership   → FM-1 Correspondence
  | .inl .argsRelations   => .fm2   -- args relations    → FM-2 Consistency
  | .inl .values          => .fm3   -- values            → FM-3 Veracity
  | .inl .rule            => .fm4   -- rule              → FM-4 Propagation
  | .inr .before          => .fm6   -- phase before      → FM-6 Feasibility
  | .inr .during          => .fm5   -- phase during      → FM-5 Freshness
  | .inr .after           => .fm7   -- phase after       → FM-7 Feedback

/-- **Completeness of the case split (§12.4, covering half).** Every one of the 7 failure modes is
    reached by some locus — the two axes together cover all seven. Axiom-free (`cases` + witness). -/
theorem locusFM_surjective : ∀ fm : FM, ∃ l : FailureLocus, locusFM l = fm := by
  intro fm; cases fm
  · exact ⟨.inl .argsMembership, rfl⟩
  · exact ⟨.inl .argsRelations, rfl⟩
  · exact ⟨.inl .values, rfl⟩
  · exact ⟨.inl .rule, rfl⟩
  · exact ⟨.inr .during, rfl⟩
  · exact ⟨.inr .before, rfl⟩
  · exact ⟨.inr .after, rfl⟩

/-- **The basis has dimension exactly 7 (§12.5, no collision).** Distinct loci give distinct FMs —
    so the 4+3 loci are not over-counting; there are genuinely seven. Axiom-free. -/
theorem locusFM_injective : ∀ l l' : FailureLocus, locusFM l = locusFM l' → l = l' := by
  intro l l' h
  cases l with
  | inl d => cases d <;> (cases l' with
      | inl d' => cases d' <;> simp_all [locusFM]
      | inr o' => cases o' <;> simp_all [locusFM])
  | inr o => cases o <;> (cases l' with
      | inl d' => cases d' <;> simp_all [locusFM]
      | inr o' => cases o' <;> simp_all [locusFM])

/-! ### The completeness theorem with CA1 made explicit (§12.8) -/

/--
A validation **computation** (§12.8), abstracted to its seven necessary conditions (`Cᵢ` holds ⟺
FM-`i` is absent). The canon states each condition BY THE FM whose violation it is and carries no
`C`-labels of its own (§12.8: "v4.0 drops the parallel labels … one taxonomy, not two") — `C1..C7`
below are this encoding's field names, not canon vocabulary. Their content (§12.8):
* `C1` joint sufficiency + non-redundancy (args↔criteria) — absence of FM-1
* `C2` compatibility of children's criteria — absence of FM-2
* `C3` truth of each `V(tⱼ)` (both sides) — absence of FM-3
* `C4` the rule computes AND (propagates fail) — absence of FM-4
* `C5` inputs not stale (during) — absence of FM-5
* `C6` D determinable when fixed (before) — absence of FM-6
* `C7` post-hoc defect is reportable (after) — absence of FM-7
-/
structure Computation where
  C1 : Prop
  C2 : Prop
  C3 : Prop
  C4 : Prop
  C5 : Prop
  C6 : Prop
  C7 : Prop

/-- The condition guarding each FM (§12.6 table), so failures can be named. -/
def Computation.cond (c : Computation) : FM → Prop
  | .fm1 => c.C1
  | .fm2 => c.C2
  | .fm3 => c.C3
  | .fm4 => c.C4
  | .fm5 => c.C5
  | .fm6 => c.C6
  | .fm7 => c.C7

/-- **Real correctness `CVC(t)` (§12.8):** computed `V(t)` = true `V*(t)`. This is DOMAIN TRUTH; by
    Lemma 1 (§2.5) it is NOT derivable from the apparatus. We therefore declare it as an
    **uninterpreted** predicate (a postulated constant) — crucially, this means no concrete
    computation literal can compute its value, so the covering axiom below cannot be refuted by
    construction (which would collapse the logic). It is the honest stand-in for "the world's
    verdict". -/
axiom correct : Computation → Prop

/--
**CA1 (Evaluation Completeness — covering, §12.8).**  Real correctness is *exactly* the
conjunction of the seven conditions. This axiom carries **one** covering premise: the denotational
⊕ operational axes exhaust the computation — no third independent axis. It does NOT bundle CA2:
the operational trichotomy needs no single clock (§12.8: "Assumptions: zero"), so CA2 lives as the
dischargeable hypothesis `Time.SingleClock`, not here, and under concurrency the trichotomy does
not weaken — it **generalizes** (FM-5 becomes the read/write race). CA1 is the ONLY assumption
behind 7-FM completeness — everything else is derived. It appears explicitly in `#print axioms` of
the results below: that visibility is the whole deliverable.
-/
axiom evaluation_completeness (c : Computation) :
    correct c ↔ (c.C1 ∧ c.C2 ∧ c.C3 ∧ c.C4 ∧ c.C5 ∧ c.C6 ∧ c.C7)

/-- **7-FM completeness (§12.4/§12.8).** Any failure of correctness violates **at least one** of the
    seven conditions — i.e. some FM is present. Derived from CA1 by (classical) De Morgan;
    no further assumption. -/
theorem fm_basis_covers (c : Computation) (h : ¬ correct c) :
    ¬c.C1 ∨ ¬c.C2 ∨ ¬c.C3 ∨ ¬c.C4 ∨ ¬c.C5 ∨ ¬c.C6 ∨ ¬c.C7 := by
  rw [evaluation_completeness] at h
  -- classical De Morgan over the 7-fold conjunction, by hand (no mathlib `tauto`):
  -- if none of the ¬Cᵢ held, every Cᵢ would hold, contradicting `h`.
  apply Classical.byContradiction
  intro hc
  apply h
  refine ⟨?_, ?_, ?_, ?_, ?_, ?_, ?_⟩
  · exact Classical.byContradiction (fun hn => hc (Or.inl hn))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inl hn)))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inl hn))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inl hn)))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inr (Or.inl hn))))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inl hn)))))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr hn)))))))

/-- The same, phrased with named FMs: a failure means **some FM is present** (its guard fails). -/
theorem seven_fm_complete (c : Computation) (h : ¬ correct c) :
    ∃ fm : FM, ¬ c.cond fm := by
  apply Classical.byContradiction
  intro hall
  apply h
  rw [evaluation_completeness]
  exact ⟨ Classical.byContradiction (fun hn => hall ⟨.fm1, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm2, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm3, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm4, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm5, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm6, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm7, hn⟩) ⟩

/-! ### Independence — the 7 witnesses (§12.5), axiom-free

For each FM there is a computation where *exactly that* condition fails and all others hold —
so the basis is irredundant (no FM follows from the others; the dimension is 7, not fewer). We
build the witness generically: set condition `k` to `(k ≠ fm)`. -/

/-- Witness computation isolating a single failing condition: `Cₖ := (k ≠ fm)`. -/
def isolatedFailure (fm : FM) : Computation where
  C1 := FM.fm1 ≠ fm
  C2 := FM.fm2 ≠ fm
  C3 := FM.fm3 ≠ fm
  C4 := FM.fm4 ≠ fm
  C5 := FM.fm5 ≠ fm
  C6 := FM.fm6 ≠ fm
  C7 := FM.fm7 ≠ fm

/-- **Independence (§12.5).** For every FM, its isolating computation violates *that* FM's guard
    and satisfies every *other* FM's guard. Hence each FM is realizable in isolation. -/
theorem fm_independent (fm : FM) :
    ¬ (isolatedFailure fm).cond fm ∧ ∀ fm', fm' ≠ fm → (isolatedFailure fm).cond fm' := by
  constructor
  · -- the fm-th guard is `fm ≠ fm`, which is false, so ¬ holds.
    cases fm <;> simp [isolatedFailure, Computation.cond]
  · -- any other guard is `fm' ≠ fm`, true by hypothesis.
    intro fm' hne
    cases fm' <;> simp_all [isolatedFailure, Computation.cond]

end GFSO.FailureModes
