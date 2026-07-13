/-
  GFSO — Tier B: self-measuring metrics (T10, §13) and structural transparency (T11, §14).

  These need a modelling layer (a trace), so they are lighter than the Tier-A theorems — but the
  CONSTRUCTIVE CORE is genuinely provable and faithful:

  * **T11 (structural transparency, §14 / Инв-7):** the record is the append-only **LOG**, and the
    current state is `state = fold(log)` (event-sourcing). So every state has a recorded provenance
    (it is a pure function of the log) and history is never rewritten (the log only extends).

  * **T10 (self-measuring, §13):** each quality metric `Q` is computable *from the trace alone* —
    a total function of the log, updatable online as events arrive (no external input).

  The deeper temporal metric semantics (calibration §18.2, the α/time monotonicities §10, IC §11)
  rest on external analysis/probability (ℝ, Blackwell) and are OUT of this mathlib-free Lean scope
  — see the claim↔status map in `README.md`. Here we lock the structural spine only.
-/

namespace GFSO.Metrics

variable {State Event : Type}

/-- **state = fold(log) (§7.1, Инв-7).** The current graph state is the left fold of the
    append-only event log over an initial state — event sourcing. Each P2P signal is a
    deterministic graph mutation (§7.1); replay reconstructs the state from the log alone. -/
def replay (init : State) (step : State → Event → State) : List Event → State :=
  fun log => log.foldl step init

/-- **T11 (structural transparency, §14).** Every event's effect is recorded: the state after a new
    event is a pure function of the previous state and that event — so the log fully determines the
    state, and every decision has a record. -/
theorem replay_append (init : State) (step : State → Event → State) (log : List Event) (e : Event) :
    replay init step (log ++ [e]) = step (replay init step log) e := by
  simp [replay, List.foldl_append]

/-- **Append-only (Инв-7).** The log only ever extends: the past is a prefix of the present, never
    rewritten. Provenance is immutable. -/
theorem log_append_only (log : List Event) (e : Event) : log <+: (log ++ [e]) :=
  ⟨[e], rfl⟩

/-- Two runs with the same log reach the same state — the state carries no hidden input beyond the
    trace (the essence of "structural transparency"). Immediate from `replay` being a function. -/
theorem replay_determined (init : State) (step : State → Event → State) {l₁ l₂ : List Event}
    (h : l₁ = l₂) : replay init step l₁ = replay init step l₂ := by rw [h]

/-- **T10 (self-measuring, §13).** A quality metric is a count over the trace — here a generic
    `Q` counting the events satisfying a predicate `p` (each of q_T, q_D, q_V, q_Dep, q_Del is such
    a count of its characteristic events, §7.2). It is a total function of the log: computable from
    the trace alone. -/
def Q (p : Event → Bool) : List Event → Nat := fun log => log.countP p

/-- **Self-measuring / online-updatable (§13).** `Q` of an extended log is `Q` of the log plus the
    new event's contribution — the metric maintains itself incrementally from the trace, needing no
    external data. This is exactly what "self-measuring" means. -/
theorem Q_self_measuring (p : Event → Bool) (log : List Event) (e : Event) :
    Q p (log ++ [e]) = Q p log + (if p e then 1 else 0) := by
  simp [Q, List.countP_append, List.countP_cons, List.countP_nil]

/-! ### §7.2 — minimality and completeness of Q: the bijection metrics ↔ tuple components

Canon §7.2: *«5 метрик ↔ 5 компонентов кортежа (T, D, Dep, Del, V; базис — 4 примитива, V производна)
— биекция. Удаление любой → слепая зона.»* The claim is precisely that the metric family is indexed
by the components of the canonical tuple — one metric per component, no component unwatched and no
metric without a component. That is a bijection, and it is provable. -/

/-- The five components of the canonical HBP tuple (§2.3): the four primitives plus derived `V`. -/
inductive Component | T | D | Dep | Del | V
deriving DecidableEq, Repr

/-- The five self-measuring metrics (§7.2). -/
inductive Metric | qT | qD | qDep | qDel | qV
deriving DecidableEq, Repr

/-- Each component's metric (§7.2 table): q_T watches criteria, q_D watches decomposition,
    q_Dep watches declared dependencies, q_Del watches delegation, q_V watches validation. -/
def metricOf : Component → Metric
  | .T => .qT | .D => .qD | .Dep => .qDep | .Del => .qDel | .V => .qV

/-- …and back. -/
def componentOf : Metric → Component
  | .qT => .T | .qD => .D | .qDep => .Dep | .qDel => .Del | .qV => .V

/--
**metrics ↔ tuple components is a bijection (§7.2) — the INDEX SETS, nothing more.**

**Honest reading.** `Component` and `Metric` are two hand-drawn 5-element enums and `metricOf` /
`componentOf` are inverse relabelings *defined to match*, so the bijection is `cases <;> rfl`. This
certifies only that the canon's indexing is well-formed: one metric per component, none missing, none
doubled. It does **not** formalize §7.2's substantive claims — that each metric is a function of
*unique graph data* (q_T ← CHALLENGE events, q_D ← child/parent pass patterns, …) and that deleting
one opens a specific blind zone. Those need the graph semantics, which this module does not model.
-/
theorem metrics_components_bijection :
    (∀ c : Component, componentOf (metricOf c) = c) ∧
    (∀ m : Metric, metricOf (componentOf m) = m) := by
  constructor
  · intro c; cases c <;> rfl
  · intro m; cases m <;> rfl

/-- Corollary (§7.2 "Удаление любой → слепая зона"): drop a metric and its component is unwatched —
    formally, `metricOf` is injective, so distinct components never share a metric. -/
theorem no_shared_metric (c₁ c₂ : Component) (h : metricOf c₁ = metricOf c₂) : c₁ = c₂ := by
  have := metrics_components_bijection.1
  rw [← this c₁, ← this c₂, h]

end GFSO.Metrics
