# E2 — scoring protocol (neutral measurement)

> **[SUPERSEDED for the executed run — the convergence protocol + result are in [`CONVERGENCE.md`](CONVERGENCE.md).]**
> This document is the **A/B** scoring apparatus (bare vs GFSO candidate per task), which belongs to the
> retired twin framing. The blind §6.4 judge it describes is still the instrument used in the convergence run;
> only the "two candidates per task → A-vs-B report" framing is retired (the run scores one candidate's
> trajectory vs the frozen reference per iteration).
>
> Consumes the blind judge's §6.4 score blocks (`prompt_judge.md`), one per (task × candidate), and reports
> the measurement. The reference is frozen before any run; the judge is a separate blind agent; A/B agents are
> fresh and isolated. **This protocol presupposes NOTHING about which candidate populates or omits which
> category — that is what E2 MEASURES, not what it asserts** (README; the subset's `PLAN.md` §9). No directional
> expectation is built in anywhere.

## 0. What the run produces

Per task `T0X`, two candidates — **A** (control: `prompt_A_bare.md` + task) and **B** (`prompt_B_gfso.md` +
the Constitution `docs/method_gfso.md` + task) — are each scored by a fresh blind judge against the frozen
`<subset>/references/T0X.md`, yielding a §6.4 block: per-category coverage (D/Dep/V/N), per-FM coverage, and non-redundancy
(ballast, unmatched).

Report, per task, **A and B side by side**, per category and per FM tag, plus the measured difference
`Δ = coverage(B) − coverage(A)`. **Δ has no presupposed sign** — whatever it is, report it. Never a single
global number; report per category, never pooled.

## 1. Decidability — a confidence weight, NOT a task filter

Truth-maker decidability is bimodal across the set, so judge variance differs by task. This is a **confidence
annotation on the per-task numbers, not an evidence/non-evidence partition** — every task is reported, none is
excluded (README §Процедура: stratify by decidability, weight soft as noisier).

- **Objective truth-makers (lower judge variance):** arithmetic / formal / logical items (e.g. T04 balance,
  T08 well-typedness, T09 isolation). Per-category numbers here are the most reproducible.
- **Judgement-laden truth-makers (higher variance):** maintenance/control regimes (T05, T06, T10) whose items
  read "adequate / sufficient" even after the §1.3 concrete-coupling phrasing. Weight these as noisier.
- **Saturation-prone:** T01 (billing) is a heavily-documented decomposition a strong bare model may already
  saturate (PLAN §3 T01 calibration note). Note this when reading T01; **do not drop it**.

Report each task with its decidability annotation; do not pool judgement-laden and objective coverage into one
figure. The annotation weights *confidence in the number*, it does not weight *who should win*.

## 2. Reading the measurement (neutral)

- Report per-category coverage (D/Dep/V/N) and per-FM coverage for **both** candidates, and `Δ=B−A`, per task,
  with its decidability annotation.
- **Headline metric = silent-hole rate, NOT raw coverage.** A *silent hole* = a significant reference item the
  candidate **neither resolves NOR consciously declares** (declaring = a NEGLECTED entry / flagged hypothesis
  matching the item by truth-maker). Per candidate: `silent-holes = (#NOT-COVERED) − (#those the candidate
  explicitly declared/flagged)`, reported as a rate over the significant items. **Why this and not coverage:**
  raw coverage = content = the base model's K̂ (≈identical in A and B → it ties, by form≠content); the
  discipline's effect lives in *not silently dropping a link* — so silent-hole rate is what can discriminate.
  *(Operationalization gap: fully per-item silent-vs-declared needs a small `prompt_judge.md` extension — for
  each NOT-COVERED item, mark whether the candidate flagged it. Until then, derive it from the N-category
  coverage + the unmatched/flagged lists. This is a known to-do, not done.)*
- **Non-redundancy** (ballast, unmatched) is reported as separate counts per candidate, never folded into the
  coverage fraction.
- A **null** (B≈A) is a valid measurement, reported as-is — not a result to rescue or explain away. A
  **negative** (A>B on any category) is likewise reported as-is. The instrument has no stake in the direction.
- **Unmatched candidate points** (judge §6.3) → human review: may reveal genuine content the reference lacks
  (a finding about the reference, not about the candidate).
- Per-task numbers are **high-variance at N=1** (judge stochasticity + single rollout). Do not read a single
  task's Δ as a result; read the set, and require replication (§4.5).

## 3. Honest scope

The instrument measures, for ANY decomposition (bare agent / GFSO agent / human), its **per-category coverage
(joint sufficiency, §2.2.1) + non-redundancy (§2.2.2)** against a GFSO-built reference, **by meaning** (the
judge earns nothing for GFSO vocabulary — `prompt_judge.md` §2.2/§2.3). The arrow under test is
**`gfso → agent_gfso`**: does the Constitution, transferred via a system prompt, change a real agent's
decomposition quality, and by how much — **not** `reality → gfso`, and **not** presupposed positive.

It does **NOT** certify per-task content completeness — that is the agent's domain knowledge (Lemma 1), not
something GFSO supplies. The references carry exactly: failure-TYPE completeness (the §7 FM frame), the cycle's
anti-pruning criteria set, and the auditable NEGLECTED record. Read per category; presuppose nothing about
which categories any candidate populates or drops.

## 4. Run protocol (reproducibility)

1. **Freeze** the subset's `references/T0X.md` (the `complex` set = 10), this protocol, and `prompt_judge.md` before any run.
2. For each task, spawn **fresh isolated** A and B. **Isolation = read-from-frozen-file** — the reproducible
   analog of an API call with an explicit system prompt + user message. Each agent **reads its own frozen files**
   (A: `prompt_A_bare.md` + `<subset>/tasks/T0X.md`; B: `prompt_B_gfso.md` + the constitution `docs/method_gfso.md` +
   `<subset>/tasks/T0X.md`) under a **hard read-restriction** (only those files; nothing under `<subset>/references/`, no other task). The orchestrator injects **no content** — only paths — so the experimenter is out of the
   data path (closes the transcribe-hole; verifiable in the subagent transcript). The spawn wrapper is
   **byte-identical and role-neutral for A and B** (no role/method word from the orchestrator; role comes only
   from the system-prompt file). Sole variable = the system-prompt file.
3. Strip the A/B label; hand each candidate + the frozen `<subset>/references/T0X.md` to a **fresh blind judge**
   (`prompt_judge.md`), **one candidate per judge**, blind to origin.
4. Collect the §6.4 blocks; report A vs B per category + per FM tag, each task with its decidability annotation
   (§1). **No task excluded.**
5. **Replication:** re-run A/B/judge with fresh contexts; per-task numbers are high-variance at N=1, so a result
   must hold across runs — report the spread, not a single-run point.

**Orchestration (native subagents).** The orchestrator spawns A, B and judges as fresh native subagents, and
**routes and tallies only** — it does not itself decompose or judge, and injects **no content** beyond the
frozen files (verbatim). Outputs → `runs/e2_agent/<subset>/<task>/` (gitignored).

## 5. Tasks → decidability annotation (a confidence weight, NOT a filter)

```
Objective truth-maker (low judge variance):    T03  T04  T08  T09
Judgement-laden (higher variance):             T05  T06  T10
Mixed (report on its own):                     T02
Saturation-prone (note when reading, keep):    T01
```

All ten tasks are measured and reported. The annotation weights confidence in each number; it never excludes a
task and never presupposes a winner.
