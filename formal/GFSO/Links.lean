/-
  GFSO — Tier 7b: the five links (Ch. 5). The 3 ⊕ 2 count is axiom-free; CA-Links (§5.3) is a named
  Lean `axiom` (`directed_action_completeness`) over the uninterpreted carrier `Directed`. The axiom
  bundles §5.3's three branches, of which the representational one, with START's fold, is the covering
  residue below CA1's grade (§5.3, §20.7).
-/

namespace GFSO.Links

/-- The five links (§5.1). -/
inductive Link
  | goal      -- Link-1  goal G ⊆ X            — directed
  | buildS    -- Link-2  build Ŝ               — informed
  | plan      -- Link-3  plan D over Ŝ         — structured
  | execute   -- Link-4  execution (rollout in S) — actual
  | contact   -- Link-5  contact (verdict from S) — real
deriving DecidableEq, Repr

/-- The two modal sides, REPRESENTATION (in Ŝ) and REALIZATION (in S) (§5.3). -/
inductive Modality | representation | realization
deriving DecidableEq, Repr

open Link Modality

/-- Each link's side (§5.3): Link-1–3 represent, Link-4–5 realize. -/
def side : Link → Modality
  | goal | buildS | plan => representation
  | execute | contact    => realization

def allLinks : List Link := [goal, buildS, plan, execute, contact]

theorem mem_allLinks (l : Link) : l ∈ allLinks := by cases l <;> decide

/-! ### The 3 ⊕ 2 = 5 count — axiom-free -/

/-- **Exactly five links.** -/
theorem five_links : allLinks.length = 5 := by decide

/-- **3 represent, 2 realize.** -/
theorem split_three_two :
    (allLinks.countP (fun l => side l == representation)) = 3 ∧
    (allLinks.countP (fun l => side l == realization)) = 2 := by
  decide

/-- Both sides are inhabited. -/
theorem side_surjective : ∀ m : Modality, ∃ l : Link, side l = m := by
  intro m; cases m
  · exact ⟨goal, rfl⟩
  · exact ⟨execute, rfl⟩

/-! ### CA-Links, made an explicit `axiom` -/

/-- A candidate act by its five links' presence. -/
structure Act where
  /-- Link-1, goal. -/
  hasGoal : Prop
  /-- Link-2, build-Ŝ. -/
  buildsModel : Prop
  /-- Link-3, plan. -/
  hasPlan : Prop
  /-- Link-4, execution. -/
  executes : Prop
  /-- Link-5, contact. -/
  contacts : Prop

/-- This act is directed action. Uninterpreted, so no literal refutes the axiom below. -/
axiom Directed : Act → Prop

/--
**CA-Links (§5.3)**, covering direction only: the five links suffice ("no sixth"). Each link's
necessity is §5.2's per-element counterexample, not postulated here.
-/
axiom directed_action_completeness (a : Act) :
    (a.hasGoal ∧ a.buildsModel ∧ a.hasPlan ∧ a.executes ∧ a.contacts) → Directed a

/-- If an act is not directed action, a link is missing: CA-Links by De Morgan. Minimality is §5.2's,
    not this theorem. -/
theorem missing_link_located (a : Act) (h : ¬ Directed a) :
    ¬a.hasGoal ∨ ¬a.buildsModel ∨ ¬a.hasPlan ∨ ¬a.executes ∨ ¬a.contacts := by
  apply Classical.byContradiction
  intro hc
  apply h
  apply directed_action_completeness a
  refine ⟨?_, ?_, ?_, ?_, ?_⟩
  · exact Classical.byContradiction (fun hn => hc (Or.inl hn))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inl hn)))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inl hn))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inl hn)))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inr hn)))))

/-- Contact (Link-5) is a realization link other than execution. That it alone reads S is SINGLE-SEAM
    (§3.5), not modelled here. -/
theorem contact_is_realization : side contact = realization ∧ contact ≠ execute := by
  exact ⟨rfl, by decide⟩

end GFSO.Links
