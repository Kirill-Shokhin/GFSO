# Missing API surface — required for full UI translation of Applied-v3

Endpoints / engine extensions referenced by the web UI but not yet present in
`gfso/api/server.py` + `gfso/engine/__init__.py`. UI sends the payloads
documented below; backend currently drops the fields silently or returns 404.

Format per item: `purpose · request · response · engine touch`. Theory ref
in §-notation. Severity: `crit` (blocks correctness), `high` (blocks key UX),
`med` (degrades clarity).

---

## 1. Deadline on `assign_task` — **crit · §2.2**

T = (spec, criteria, **deadline**) — primitive is incomplete without it.
CHECK-3 (deadlines consistency) silently passes for all tasks because
`task.deadline` is always `None`.

- **Endpoint** — `POST /api/tasks` already accepts `deadline: str | None` in
  `CreateTaskRequest` (ISO 8601). Server currently does **not** forward it.
- **Engine** — extend `Engine.assign_task(..., deadline: datetime | None = None)`;
  set `Task(..., deadline=deadline)` instead of leaving the default `None`.
- **Server stitch** — in `create_task` handler:
  `deadline = datetime.fromisoformat(req.deadline) if req.deadline else None`,
  pass through. Same for `decompose_task` (per-child deadline).
- **DecomposeRequest** — add `deadline: str | None` to each `CreateTaskRequest`
  child (already accepted as part of the same model).

---

## 2. Dependency CRUD — **high · §2.2 primitive Dep**

Engine has `DepEdge` type and `get_dependencies()`. No write API.
Currently Deps appear only as `discovered=True` from BLOCK signals.

- `POST /api/dependencies` — `{ from_id: TaskId, to_id: TaskId }` →
  `DepEdge` (201). Engine: `add_dependency(from_id, to_id)` →
  `storage.upsert_dep(DepEdge(from, to, discovered=False))` + invariant
  checks (CHECK-2 DAG runs synchronously, rejects cycle with 422).
- `DELETE /api/dependencies/{from_id}/{to_id}` → 204. Engine:
  `remove_dependency(from_id, to_id)`.
- UI affordance: drag-from-node-to-node in Cytoscape, or button in sidebar
  "Add dependency on…". Currently the UI shows existing edges but has no
  way to declare a new one.

---

## 3. Audit entry source / reason serialization — **high · §11 (T11)**

`AuditEntry` carries `source`, `reason`, `justification`, `result`,
`failed_criteria` via `SignalData`, but `AuditEntryOut` only exposes
`signal / old_state / new_state / effects / rejected / error`. UI shows
`12:34:56 ACCEPT REVIEW→EXECUTING` without **who** or **why**.

- Extend `AuditEntry` to retain the `SignalData` payload (or flatten the
  fields onto `AuditEntry` at write time).
- Add to `AuditEntryOut`: `source: str | None`, `reason: str | None`,
  `justification: str | None`, `result: str | None`,
  `failed_criteria: list[str] = []`.
- UI then renders `12:34:56 · pm · ACCEPT · "looks good"` per row.

---

## 4. Predictability classification — **med · §5.2 STD-2**

Neither `Spec` nor `Criteria` carries a predictability tag. STD-2 is
unenforceable.

- Add to `Criteria` (or a new `Factor` field on `Spec`):
  `predictability: Literal['ordinary','statistical','extraordinary'] = 'ordinary'`.
- Add `CHECK-7 predictability`: `extraordinary` requires explicit
  justification string; absence → fail; `statistical` must appear either in
  `criteria` (addressed) or `neglected` (explicitly waived).
- UI extension: predictability select per criterion in create form +
  `justification: str | None` text field for extraordinary.

---

## 5. Per-role action affordances — **med · §6 FSM roles**

Engine does not expose which signals are valid for a given (state, role)
pair. UI currently shows all action buttons regardless of `current-role`.
Without role gating, the FSM's role-based access is decorative.

- `GET /api/tasks/{task_id}/actions?role={agent_id}` → list of `{signal,
  label, requires_payload: list[str]}` valid for this role in this state.
- Alternative — bundle into `TaskDetailOut.available_actions` per role.
- UI then renders only the allowed buttons, with role-correct prompts.

---

## 6. Solver — explicit separation from LLM — **med · §7.3**

§7.3 distinguishes Solver (deterministic checks, minimality, dominance) from
LLM (suggestions). Current `engine._llm` is used as both. UI's "AI
Recommendations" panel cannot distinguish a Solver-derived recommendation
("non-redundancy violated: child X has no criterion in parent") from an
LLM-style soft suggestion.

- `GET /api/tasks/{task_id}/solver` → `{ recommendations: [{kind: 'solver'
  |'llm', text, severity}] }`.
- Backend: split `handlers/recommend.py` into `solver_recommend.py`
  (CHECK-derived) + `llm_recommend.py` (free-form).
- UI: render solver items with hard-warning style (acc icon), llm items
  as soft suggestions (current style).

---

## 7. CHECK-levels Level-1 / Level-2 — **med · §5.4**

Engine implements only Level-0 (structural) checks. §5.4 defines Level-1
(semantic — `decidable predicates`) and Level-2 (pragmatic — `Δ vs c`).
UI already groups checks by FM and could group by Level too, but there's
nothing to display until engine adds them.

- Engine: `handlers/semantic.py` with `CHECK-7:resolvability` (each
  criterion is a `Result → {pass,fail}` predicate parseable into AST or
  callable), `CHECK-8:non_redundancy` (each child addresses at least one
  parent criterion via `criterion_mappings`).
- Engine: `handlers/pragmatic.py` with `CHECK-9:cost_benefit`
  (constraint improvement Δ > cost, §1.2 P4).
- UI: add Level-1 / Level-2 sub-groups inside the FM panel.

---

## Format note

All endpoints follow existing conventions: 
- pydantic models in `gfso/api/models.py`
- handler in `gfso/api/server.py` 
- engine call in `gfso/engine/__init__.py`
- response uses existing `*Out` model where possible
- 404 if task not found, 422 on invariant violation, 201 on create, 204 on delete
