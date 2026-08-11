/-
  GFSO — TIER 7b: the five constitutive links of directed action (§4).

  Canon `docs/applied_gfso_v4_en.md` §4:
    Link-1 goal · Link-2 build-Ŝ · Link-3 plan D over Ŝ · Link-4 execution · Link-5 contact.
    > **Axiom (completeness of directed action — covering).** …exactly two relata ⟹ exactly two
    > modal sides by excluded middle on map/territory: REPRESENTATION (what is in Ŝ) ⊕ REALIZATION
    > (what is in S). The sum of the sides = exactly five links.
    REPRESENTATION = {Link-1,Link-2,Link-3} = the ternary argument structure of `Reaches(route, target ; medium)`.
    REALIZATION   = {Link-4,Link-5} = ⟨execution (system→world), contact (world→system)⟩.

  Honest grading, from the canon itself: two of the three closure branches are derived to full
  §12.8 strength (the modal split; the realization in/out split). The **representational branch is
  BELOW §12.8 grade** — it rests on the named `REACHES-ternarity` axiom, which carries a loaded
  residue: **START** (the source point) is a genuine constitutive relatum, *folded* — not
  eliminated — into "execution-anchored present" by a declared modelling choice. Reject the folding
  and the count 3⊕2=5 breaks. The canon says full parity is NOT achievable this way. We encode that
  honestly: one named covering axiom, documented as sub-§12.8.
-/

namespace GFSO.Links

/-- The five constitutive links (§4). Numbered Link-1–Link-5 in the canon. -/
inductive Link
  | goal      -- Link-1  goal G ⊆ X            — directed
  | buildS    -- Link-2  build Ŝ               — informed
  | plan      -- Link-3  plan D over Ŝ         — structured
  | execute   -- Link-4  execution (rollout in S) — actual
  | contact   -- Link-5  contact (verdict from S) — real
deriving DecidableEq, Repr

/-- The two modal sides — the Ŝ-vs-S axis of the theory model itself. -/
inductive Modality | representation | realization
deriving DecidableEq, Repr

open Link Modality

/-- Which side each link belongs to: {Link-1,Link-2,Link-3} represent, {Link-4,Link-5} realize. -/
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
  /-- Link-1 there is a goal (directedness). -/
  hasGoal : Prop
  /-- Link-2 an estimate Ŝ is built (informedness). -/
  buildsModel : Prop
  /-- Link-3 a route D over Ŝ is laid (structure). -/
  hasPlan : Prop
  /-- Link-4 the plan is executed in S (actuality). -/
  executes : Prop
  /-- Link-5 the world returns a verdict (reality). -/
  contacts : Prop

/-- "This act IS directed action." Uninterpreted: whether something really *is* directed action is
    not computable from the apparatus — so no literal may refute the covering axiom below. -/
axiom Directed : Act → Prop

/--
**Axiom (completeness of directed action — covering, §4).** Directed action is *exactly* the
conjunction of the five links. Removing any one yields a non-action (dynamics, blind reaction, no
route, an unexecuted plan, or an open-loop guess).

This bundles the canon's three closure branches. Two are derived to §12.8 strength (modal: two relata
⟹ two sides; realization: in/out, no third direction). The third — **REACHES-ternarity**, that the
representational side has exactly the three roles ⟨goal, medium Ŝ, route D⟩ — is *sub-§12.8*, with
the **START** residue folded by a declared modelling choice. That is why this is an `axiom` and not
a theorem, and why the canon calls full parity unreachable by this path.
-/
axiom directed_action_completeness (a : Act) :
    Directed a ↔ (a.hasGoal ∧ a.buildsModel ∧ a.hasPlan ∧ a.executes ∧ a.contacts)

/-- **Minimality of the five links (§4).** If an act fails to be directed action, at least one
    link is missing. (Per-element counterexamples — "remove any, get a non-action" — are the canon's
    §4 argument; here the covering axiom delivers the localization.) -/
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

/-- Contact (Link-5) is the *only* link on the realization side that reads the world — the SINGLE-SEAM
    property named in §2.4. Here: contact is a realization link, and it is not execution. -/
theorem contact_is_realization : side contact = realization ∧ contact ≠ execute := by
  exact ⟨rfl, by decide⟩

end GFSO.Links
