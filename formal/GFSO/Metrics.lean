/-
  GFSO — Tier 6: the structural spine of Thm 10 (§15.6) and Thm 11 (§11.6) over an abstract log, and the
  index bijection metrics ↔ tuple components (§15.4). `state = fold(log)` gives Thm 11's shape, not its
  content — every decision's record, §11.6 (§20.4); a count over the log gives a q-metric's shape, not
  its definition. The rest of Ch. 15–16 rests on ℝ and probability, outside this mathlib-free scope
  (§20.4); the claim ↔ status map is `formal/README.md`.
-/

namespace GFSO.Metrics

variable {State Event : Type}

/-- **state = fold(log) (§15.1, Inv-7)**: the state is the left fold of the append-only log over an
    initial state; replay rebuilds it from the log alone. -/
def replay (init : State) (step : State → Event → State) : List Event → State :=
  fun log => log.foldl step init

/-- **The fold identity — Thm 11's shape (§20.4).** The state after an event is a function of the
    previous state and the event. -/
theorem replay_append (init : State) (step : State → Event → State) (log : List Event) (e : Event) :
    replay init step (log ++ [e]) = step (replay init step log) e := by
  simp [replay, List.foldl_append]

/-- **Append-only (Inv-7, §12.11).** The past is a prefix of the present. -/
theorem log_append_only (log : List Event) (e : Event) : log <+: (log ++ [e]) :=
  ⟨[e], rfl⟩

/-- Same log, same state: the state takes no input beyond the trace. -/
theorem replay_determined (init : State) (step : State → Event → State) {l₁ l₂ : List Event}
    (h : l₁ = l₂) : replay init step l₁ = replay init step l₂ := by rw [h]

/-- **A q-metric's numerator shape (§15.6)**: the count of events satisfying `p`, a total function of
    the log. Not modelled: q_D's state-conditional event, the ratios and ⊥ (§15.4). -/
def Q (p : Event → Bool) : List Event → Nat := fun log => log.countP p

/-- **Online update (§15.6).** `Q` of an extended log is `Q` of the log plus the new event's
    contribution. -/
theorem Q_self_measuring (p : Event → Bool) (log : List Event) (e : Event) :
    Q p (log ++ [e]) = Q p log + (if p e then 1 else 0) := by
  simp [Q, List.countP_append, List.countP_cons, List.countP_nil]

/-! ### §15.4 — metrics ↔ tuple components

§15.4: "The five metrics are in bijection with the tuple's five components (T, D, Dep, Del, and V
derived), and removing any leaves a blind zone." -/

/-- The canonical tuple's five components (§2.8). -/
inductive Component | T | D | Dep | Del | V
deriving DecidableEq, Repr

/-- The five metrics (§15.4). -/
inductive Metric | qT | qD | qDep | qDel | qV
deriving DecidableEq, Repr

/-- Each component's metric (§15.4's table). -/
def metricOf : Component → Metric
  | .T => .qT | .D => .qD | .Dep => .qDep | .Del => .qDel | .V => .qV

/-- …and back. -/
def componentOf : Metric → Component
  | .qT => .T | .qD => .D | .qDep => .Dep | .qDel => .Del | .qV => .V

/--
**Metrics ↔ components is a bijection (§15.4): the index sets only.**

**Honest reading.** Two hand-drawn 5-element enums with inverse maps defined to match, so
`cases <;> rfl`. It checks that the indexing is well-formed — one metric per component, none missing,
none doubled — not that each metric reads its own data or that removing one opens its blind zone
(§15.4), which need the graph semantics this module does not model.
-/
theorem metrics_components_bijection :
    (∀ c : Component, componentOf (metricOf c) = c) ∧
    (∀ m : Metric, metricOf (componentOf m) = m) := by
  constructor
  · intro c; cases c <;> rfl
  · intro m; cases m <;> rfl

/-- Distinct components never share a metric (`metricOf` injective) — the index form of §15.4's
    blind-zone clause. -/
theorem no_shared_metric (c₁ c₂ : Component) (h : metricOf c₁ = metricOf c₂) : c₁ = c₂ := by
  have := metrics_components_bijection.1
  rw [← this c₁, ← this c₂, h]

end GFSO.Metrics
