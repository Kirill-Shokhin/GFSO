/-
  GFSO — the theoretic-model layer: why an AGENT is necessary (§3). The "ontological language".

  Canon `docs/applied_gfso_v4_en.md` §2–3. This is the layer that turns GFSO from a *standard* into a
  *model*: it does not add a primitive, it DERIVES that a domain-content-bearing agent is a
  necessary link. Two of its steps formalize cleanly with no external theory:

  * **Lemma 1 (SINGLE-SEAM, §2.5 / §2.3):** the real composition structure `S` is NOT definable from
    the formal data (A1+A2). We encode its FORM — exhibit two domains with identical formal view but
    different `S`. So the apparatus (`𝒜 : Ŝᵏ → Ŝ`, syntactically S-free) cannot produce `S`.
  * **Agent necessity (d1–d6, §3.2):** reliable knowledge of `S` has a source; the apparatus
    (Lemma 1), pure declaration (Lemma 2, regress), and luck (S contingent) are each ruled out; by
    excluded middle over the sources (d3), only **contact** remains. We PROVE this elimination.

  What we DON'T over-claim: Lemma 2 (declaration regress) and luck-instability are the canon's named
  premises; here they are the explicit *hypotheses* of `agent_necessary` (each cited to §3.2 d4),
  so the theorem exhibits the exact logical structure "these premises ⟹ contact" — nothing hidden.
-/

namespace GFSO.TheoryModel

/-- A **composition edge** `(t, {tⱼ})` (§9): a parent together with the children proposed to
    constitute it. The real question about it is whether the children *really* achieve the parent. -/
structure Composition where
  parent : Nat
  children : List Nat
deriving DecidableEq, Repr

instance : Inhabited Composition := ⟨⟨0, []⟩⟩

/-- The formal, **S-free** data the apparatus sees (§2.3 "SINGLE-SEAM: 𝒜 is syntactically S-free"):
    the formal graph, decidable criteria, the `V=AND` law — everything except the world's verdict.
    Abstracted to one opaque coordinate; its internal richness is irrelevant to Lemma 1. -/
structure FormalView where
  formal : Bool

/-- A **domain** = the formal view PLUS the real composition structure `S` (§9): for each proposed
    composition, whether `(t,{tⱼ}) ∈ S` — whether the children really achieve the parent. `S` is a
    *contingent fact about the world*, not given in advance (Lemma 1). Note it is a genuine
    predicate over compositions, not a token: the point is that it is a coordinate the formal view
    does not see. -/
structure Domain where
  view : FormalView
  S : Composition → Prop

/--
**Lemma 1 (SINGLE-SEAM, §2.5 / §2.3) — its logical FORM, encoded.**  `S` is not a function of the
formal view: two domains share the SAME `view` yet disagree about which compositions really hold.

**Honest reading — do not oversell this.** `S` is a field of `Domain` *independent* of `view`, and the
apparatus is *defined* to see only `view`. So the underdetermination is **definitional** once one
accepts SINGLE-SEAM (§2.3: "𝒜 is syntactically S-free"). This theorem does **not** derive S-freeness
from richer premises; it makes the dependency explicit. What it does buy is that the step
*"the apparatus is S-free" ⟹ "the apparatus cannot certify S"* is machine-checked and gap-free —
see `no_apparatus_yields_S`, which is the consequence that actually gets used (D4a).
-/
theorem lemma1_S_underdetermined :
    ∃ d₁ d₂ : Domain, d₁.view = d₂.view ∧ ∃ c : Composition, ¬ (d₁.S c ↔ d₂.S c) := by
  refine ⟨⟨⟨true⟩, fun _ => True⟩, ⟨⟨true⟩, fun _ => False⟩, rfl, default, ?_⟩
  intro h
  exact h.mp trivial

/-- Corollary — the sharper form: there is **no function** from the formal view to `S`. No apparatus
    `𝒜 : FormalView → (Composition → Prop)` can be right on every domain; the two Lemma-1 witnesses
    refute any candidate `f`. This *is* "the apparatus does not produce S". -/
theorem no_apparatus_yields_S :
    ¬ ∃ f : FormalView → (Composition → Prop), ∀ d : Domain, f d.view = d.S := by
  rintro ⟨f, hf⟩
  have h₁ := hf ⟨⟨true⟩, fun _ => True⟩
  have h₂ := hf ⟨⟨true⟩, fun _ => False⟩
  rw [h₁] at h₂
  have hTF : (True : Prop) = False := congrFun h₂ default
  exact hTF ▸ trivial

/-- The candidate sources of reliable knowledge of `S` (§3.2 d3, excluded middle over "did the
    grounding reach the world"): the apparatus, pure declaration, luck, or empirical **contact**. -/
inductive KnowledgeSource | apparatus | declaration | luck | contact
deriving DecidableEq, Repr

/--
**Agent necessity (d1–d6, §3.2).** Given that reliable knowledge of `S` has *some* source
(d3, excluded middle — here `src`), and that the three non-contact sources are each ruled out:

* `not_apparatus` — D4a: the apparatus is S-free (Lemma 1 / `no_apparatus_yields_S`);
* `not_declaration` — D4b: a declaration is itself a decomposition whose correctness regresses
  (Lemma 2, §2.5);
* `not_luck` — D4c: `S` is contingent (Lemma 1: many `S` per formal graph), so under a demand for
  *reliable* success, coincidence is eliminated (prob → 0);

the source is forced to be **contact**. This is the canon's "the derivation is pinned" (Lemma 1+2 +
luck-instability + excluded middle)": a genuine elimination, not a fresh axiom. The agent is
whatever bears this contact link (§4.1: the agent dissolves into {Link-2 build-Ŝ, Link-5 contact}).
-/
theorem agent_necessary
    (src : KnowledgeSource)
    (not_apparatus : src ≠ .apparatus)
    (not_declaration : src ≠ .declaration)
    (not_luck : src ≠ .luck) :
    src = .contact := by
  cases src <;> simp_all

end GFSO.TheoryModel
