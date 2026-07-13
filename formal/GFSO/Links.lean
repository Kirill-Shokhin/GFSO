/-
  GFSO — TIER 7b: the five constitutive links of directed action (§18.10.1).

  Canon `docs/applied_gfso_v3.md` §18.10.1:
    Ⅰ цель · Ⅱ строить Ŝ · Ⅲ план D над Ŝ · Ⅳ исполнение · Ⅴ контакт.
    > **Аксиома (Полнота направленного действия — покрывающая).** …ровно два релята ⟹ ровно две
    > модальные стороны: REPRESENTATION (что в Ŝ) ⊕ REALIZATION (что в S). Сумма сторон = ровно пять.
    REPRESENTATION = {Ⅰ,Ⅱ,Ⅲ} = тернарная аргумент-структура `Reaches(route, target ; medium)`.
    REALIZATION   = {Ⅳ,Ⅴ} = ⟨исполнение (система→мир), контакт (мир→система)⟩.

  Honest grading, from the canon itself: two of the three closure branches are derived to full
  §4.8 strength (the modal split; the realization in/out split). The **representational branch is
  BELOW §4.8 grade** — it rests on the named `REACHES-ternarity` axiom, which carries a loaded
  residue: **START** (the source point) is a genuine constitutive relatum, *folded* — not
  eliminated — into "execution-anchored present" by a declared modelling choice. Reject the folding
  and the count 3⊕2=5 breaks. The canon says full parity is NOT achievable this way. We encode that
  honestly: one named covering axiom, documented as sub-§4.8.
-/

namespace GFSO.Links

/-- The five constitutive links (§18.10.1). Numbered Ⅰ–Ⅴ in the canon. -/
inductive Link
  | goal      -- Ⅰ  цель G ⊆ X          — направлено
  | buildS    -- Ⅱ  строить Ŝ           — информировано
  | plan      -- Ⅲ  план D над Ŝ        — структурно
  | execute   -- Ⅳ  исполнение (rollout в S) — актуально
  | contact   -- Ⅴ  контакт (вердикт от S)  — реально
deriving DecidableEq, Repr

/-- The two modal sides — the Ŝ-vs-S axis of the theory model itself. -/
inductive Modality | representation | realization
deriving DecidableEq, Repr

open Link Modality

/-- Which side each link belongs to: {Ⅰ,Ⅱ,Ⅲ} represent, {Ⅳ,Ⅴ} realize. -/
def side : Link → Modality
  | goal | buildS | plan => representation
  | execute | contact    => realization

def allLinks : List Link := [goal, buildS, plan, execute, contact]

theorem mem_allLinks (l : Link) : l ∈ allLinks := by cases l <;> decide

/-! ### The 3 ⊕ 2 = 5 arithmetic — axiom-free -/

/-- **Exactly five links.** -/
theorem five_links : allLinks.length = 5 := by decide

/-- **The split is 3 (representation) ⊕ 2 (realization).** Machine-checked count. -/
theorem split_three_two :
    (allLinks.countP (fun l => side l == representation)) = 3 ∧
    (allLinks.countP (fun l => side l == realization)) = 2 := by
  decide

/-- Both sides are inhabited (the modal split is not vacuous). -/
theorem side_surjective : ∀ m : Modality, ∃ l : Link, side l = m := by
  intro m; cases m
  · exact ⟨goal, rfl⟩
  · exact ⟨execute, rfl⟩

/-! ### The covering principle, made an explicit axiom -/

/-- A candidate act, decomposed into the five links' presence. -/
structure Act where
  /-- Ⅰ there is a goal (directedness). -/
  hasGoal : Prop
  /-- Ⅱ an estimate Ŝ is built (informedness). -/
  buildsModel : Prop
  /-- Ⅲ a route D over Ŝ is laid (structure). -/
  hasPlan : Prop
  /-- Ⅳ the plan is executed in S (actuality). -/
  executes : Prop
  /-- Ⅴ the world returns a verdict (reality). -/
  contacts : Prop

/-- "This act IS directed action." Uninterpreted: whether something really *is* directed action is
    not computable from the apparatus — so no literal may refute the covering axiom below. -/
axiom Directed : Act → Prop

/--
**Axiom (completeness of directed action — covering, §18.10.1).** Directed action is *exactly* the
conjunction of the five links. Removing any one yields a non-action (dynamics, blind reaction, no
route, an unexecuted plan, or an open-loop guess).

This bundles the canon's three closure branches. Two are derived to §4.8 strength (modal: two relata
⟹ two sides; realization: in/out, no third direction). The third — **REACHES-ternarity**, that the
representational side has exactly the three roles ⟨goal, medium Ŝ, route D⟩ — is *sub-§4.8*, with
the **START** residue folded by a declared modelling choice. That is why this is an `axiom` and not
a theorem, and why the canon calls full parity unreachable by this path.
-/
axiom directed_action_completeness (a : Act) :
    Directed a ↔ (a.hasGoal ∧ a.buildsModel ∧ a.hasPlan ∧ a.executes ∧ a.contacts)

/-- **Minimality of the five links (§18.10.1).** If an act fails to be directed action, at least one
    link is missing. (Per-element counterexamples — "remove any, get a non-action" — are the canon's
    §18.10.1 argument; here the covering axiom delivers the localization.) -/
theorem missing_link_located (a : Act) (h : ¬ Directed a) :
    ¬a.hasGoal ∨ ¬a.buildsModel ∨ ¬a.hasPlan ∨ ¬a.executes ∨ ¬a.contacts := by
  rw [directed_action_completeness] at h
  apply Classical.byContradiction
  intro hc
  apply h
  refine ⟨?_, ?_, ?_, ?_, ?_⟩
  · exact Classical.byContradiction (fun hn => hc (Or.inl hn))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inl hn)))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inl hn))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inl hn)))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inr hn)))))

/-- Contact (Ⅴ) is the *only* link on the realization side that reads the world — the SOLITUDE
    property named in §18.10.0. Here: contact is a realization link, and it is not execution. -/
theorem contact_is_realization : side contact = realization ∧ contact ≠ execute := by
  exact ⟨rfl, by decide⟩

end GFSO.Links
