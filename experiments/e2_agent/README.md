# E2 — decomposition convergence: how to reach a verified plan reliably and cheaply

> **CLOSED 2026-06-30. Current framing + result: [`CONVERGENCE.md`](CONVERGENCE.md) + `docs/EVIDENCE_LOG.md`
> §11.** The original "bare agent vs GFSO agent" A/B framing below is **RETIRED** (coverage = content = the
> model's → A ≈ B structurally); E2 became an **optimality** study of which cycle / continuation-prompt
> converges to the completeness-audited reference cheapest. This file is the historical experimenter overview.
> **Subject agents never read this, nor any `*/references/`.** **E2 is DECOMPOSITION only** — execution is E3.

Measures whether the GFSO discipline, given to a real agent **via a system prompt**, changes its
**decomposition**, and by how much. Control **A** = bare agent (task only); treatment **B** = same agent +
the Constitution (`docs/method_gfso.md`). Same model, same role, **sole variable = the system prompt**.
Arrow: `gfso → agent_gfso`, not `reality → gfso`. **Nothing about who-covers-what is presupposed** — measured.

**Why E2 matters (value-lens, not a result):** E2 is, in essence, an *ablation toward a future GFSO agent* —
isolating which factor carries the contribution: (a) using the gfso-core code service, (b) the discipline
itself, or (c) context-based understanding. Which dominates is open; E2 informs it. ("Ablation" is this lens,
**not** a label for any current finding.)

## Shared apparatus (both subsets are decomposition → common, at top level)
`prompt_A_bare.md` · `prompt_B_gfso.md` (+ constitution at spawn) · `prompt_judge.md` (blind, meaning-match,
vocabulary-neutral) · `SCORING.md` (neutral coverage + non-redundancy + silent-holes; no predicted winner).

## Two subsets — differ by interaction-COMPLEXITY (≈ whether one pass saturates)
| | `complex/` | `simple/` |
|---|---|---|
| task | high-level, interaction-dense decomposition (current 10) | small everyday, interaction-sparse decomposition (scaffold; pending) |
| regime | one pass **does not saturate** → single-pass A≈B (divergence is the iterative arm) | one pass **saturates** → differentiator would be in-the-moment **structure** (series of often-skipped small links) |
| reference | frozen GFSO-built gold | same — but simple refs are **human-auditable** (smallness relaxes Lemma 1: holes a-priori-assessable) |
| metric | identical — coverage + non-redundancy + silent-holes vs reference, blind judge | identical |

(`complex`/`simple` names the real axis — interaction-complexity — not size. No code runs.)

## Open arms (none finished)
1. **`complex` — single-pass** = the **original E2 plan** (kept). This session: on a complex task, one
   iteration shows **no A-vs-B difference** (B's only delta = the audit layer: declared NEGLECTED +
   non-redundancy). That observation is the **premise** for the next two arms — not a verdict of "no value".
2. **`complex` — iterative** (neutral "continue your previous work"): does a difference emerge across
   iterations (where one pass showed none)?
3. **`simple` — single-pass**: does a difference show on saturating, interaction-sparse tasks?

## Isolation (read-from-file = the reproducible analog of an API system+user call)
Each agent **reads its own frozen files**; the orchestrator passes **only paths**, no content (out of the
data path — verifiable in `…/subagents/agent-<id>.jsonl`). Hard read-restriction: only the listed files;
never `*/references/` or another task. Spawn wrapper **byte-identical + role-neutral** for A and B (role only
from the system-prompt file). Sole variable = the system-prompt file.

## Layout
```
experiments/e2_agent/
  README.md  SCORING.md  prompt_A_bare.md  prompt_B_gfso.md  prompt_judge.md   # shared apparatus
  complex/  PLAN.md  tasks/T01..T10.md  references/T01..T10.md  _provenance/    # SUBSET 1 (current 10)
  simple/   PLAN.md  README.md  tasks/  references/  _provenance/               # SUBSET 2 (scaffold)
  (runs → /runs/e2_agent/{complex,simple}/<task>/  — repo-root, gitignored)
```
Shared apparatus at top (both subsets are the same decomposition test); each subset holds only its dataset
(PLAN + `tasks/` inputs + `references/` gold + gitignored `_provenance/` build-trail). Inputs separate from
gold → leak-resistant read-restriction. No `tasks.md` (per-task file is the canonical input). Constitution
`docs/method_gfso.md` shared.
