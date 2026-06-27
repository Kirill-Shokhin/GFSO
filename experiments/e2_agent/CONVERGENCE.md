# E2 — iterative search→audit convergence (the final variant)

> The operative E2 experiment. Measures whether a fixed **search → audit** loop, iterated, converges a
> decomposition to a verified-plan-level target. Subagents only (no API calls); this is semantic-level
> reproducibility (explicit frozen prompts + protocol), not code-level.

## What it tests
Given a task, can two role-fixed agents — a **SEARCH** agent (exhaustive recall) and an **AUDIT** agent
(canonical-basis precision) — iterated K=3 times, converge a decomposition toward a frozen, completeness-audited
**reference** (`complex/references/T0X.md`)? The reference is the convergence **target**, not an absolute:
content-completeness is not a-priori derivable (there is no "100%"). The reference itself was built by exactly
this shape — one exhaustive enumeration + one audit + a reaudit/patch — so the loop is reproducing its own
construction method and measuring how far it gets, and how the basis grows beyond it.

## Roles (frozen prompts)
- `prompt_search.md` — RECALL. Exhaustive, over-inclusive, domain-generic. First pass: enumerate from the task.
  Later passes: find what the current decomposition is still missing / wrongly scoped. Never canonicalizes.
- `prompt_audit.md` — PRECISION. Reduces the enumeration to a canonical non-redundant **basis** (D / Dep / V /
  N), preserving every **distinct falsifier** (no over-merge), correcting wrong scope. Never hunts new content.
- `prompt_judge.md` — the existing blind meaning-match judge. Scores ONE candidate against the frozen reference
  (coverage per category D/Dep/V/N + per FM tag, ballast, unmatched). Blind to origin. Used as a measurement
  probe only; the loop never sees the judge or the reference.

**All three prompts are DOMAIN-GENERIC** — they carry zero task-specific content. The only domain input is the
task file. This is what lets the same prompts run all 10 tasks unchanged.

## The loop (per task), K = 3 iterations
```
iter 1:  search(task)                  -> search_1.md   ;  audit(task, search_1)        -> D1.md
iter 2:  search(task, D1)              -> search_2.md   ;  audit(task, D2-in=D1+search_2)-> D2.md
iter 3:  search(task, D2)              -> search_3.md   ;  audit(task, D3-in=D2+search_3)-> D3.md
judge(reference, D1) -> judge_D1.md      (the single-pass DRAFT level)
judge(reference, D3) -> judge_D3.md      (the converged level)
```
Judge only iter 1 and iter 3 (cost): iter 1 = the draft a single search+audit reaches; iter 3 = after the loop.
Intermediate completeness is read for free from the **basis width** the audit reports each iteration.

## The wrapper (isolation — identical for every agent of a role)
The orchestrator **passes only file paths, never content**, and each agent is told to read **only** its listed
files and nothing else (in particular never anything under `complex/references/` — that would leak the target).
Role and method come solely from the prompt file the agent reads; the spawn wrapper is byte-identical and
role-neutral across tasks. This keeps the experimenter out of the data path (verifiable in the subagent
transcript). Concretely, a spawn message is:

> Read these files, and only these: `<prompt_file>`, `complex/tasks/T0X.md`[, `<current D>`/`<search output>`].
> Do not read any other file (nothing under `complex/references/`). Follow `<prompt_file>`. Write your output
> to `<out path>`.

## Metrics (per task)
- **reference-coverage** (judge, iter1 & iter3): COVERED / total per category (D, Dep, V, N) + per FM tag.
  iter1 = draft; iter3 = converged. The headline is the iter1→iter3 climb.
- **basis width** (audit, every iter): |D|, |Dep|, |V|, |N|, total — its growth then deceleration is the
  convergence signal, read without the judge.
- **beyond-reference** (judge unmatched count): candidate basis items matching no reference item — the content
  the loop raises above the reference.

## Artifact layout (committed; one folder per task)
```
complex/runs/T0X/
  search_1.md  D1.md  judge_D1.md
  search_2.md  D2.md
  search_3.md  D3.md  judge_D3.md
  trajectory.md     # table: iter | basis width (D/Dep/V/N/total) | new holes found | ref-coverage | unmatched
```

## What E2 establishes

E2 asks an **optimality** question, not "does X help": *what practice reliably and **cheaply** (fewest
tokens/cycles) converges a decomposition to a verified plan?* That a critic or iteration helps is not in doubt;
the open question is whether a given loop is the *optimal* way to spend tokens on convergence — the kind of
claim GFSO is built from. The yardstick is a frozen **reference**: a well-worked, completeness-audited
decomposition — **not an ideal and not "100%"** (content-completeness is not a-priori derivable, so "100%" is
not a concept here). Its true ancestor is the method that builds it (see *How the references were built*).

**Finding 1 — the cycle works.** Iterating SEARCH (exhaustive recall) + AUDIT (reduce to the canonical
D/Dep/V/N basis, preserving distinct falsifiers) raises coverage of the reference and decelerates (78%→96%
Opus, 74%→81% Sonnet; new holes taper). One pass is a draft; iteration is the re-audit that closes it.

**Finding 2 — how you frame the pass beats how many passes you run.** The continuation prompt is a first-class
variable: an open "what's missing" content hunt **strictly dominates** a methodology-policing critic, which
drives the agent over *form* not *content* at higher cost. Unlike the iteration climb (whose absolute numbers
mean little), here the effect is carried by the numbers — the regime gap on one task is large and prompt-driven.

**The architecture this forces — bare SEARCH ⊕ gfso AUDIT.** "Bare vs GFSO" is a false dichotomy. Recall is
*content* — the model's domain knowledge — and GFSO adds nothing to it and in fact *taxes* it (a
methodology-framed continuation recalls less per token). Casting into the canonical basis is something only the
GFSO discipline does (a bare hunt yields a flat, redundant list). Neither monolith is optimal, so the dominant
design splits the roles: **bare for search, gfso for audit, iterated.** The audit's value to the *next* search
is not an explicit handoff — it re-sorts the verbose enumeration into a **minimal canonical basis**, and on
that terse structure the **remaining holes become visible** as absent seams/slots; the next search then hunts
those instead of re-padding.

**Why this is not circular — ansatz-and-verify.** The reference was itself built (intuitively) by this same
search+audit method; we then tested whether *other* methods reproduce it — and only search+audit does
(alternatives: a methodology critic, a plain redo, single-agent self-review — cannot). Among many candidates
with equal opportunity, only one reproduces the target, so the reference's provenance is irrelevant to the
discrimination (the pattern of guessing a solution and proving it is the one that satisfies). **Honest
caveat:** the reference's own completeness is *cycle-internal* ("the cycle vouching for itself"), partially
offset by the reaudit's blind re-derivation and by a cross-model run (a different model reproduces it).

**Confound (kept separate):** because the reference's *content* came from a bare enumeration,
coverage-to-reference rewards content-similarity to a bare artifact. So E2 is the **wrong** instrument for the
*value of the GFSO method* (which needs execution — E3) but the **right** instrument for *ranking convergence
strategies*. (The cross-model run reduces the same-agent confound; the bare-content confound it does not.)

**Payoff:** the SEARCH+AUDIT pair *is* the reference-building method — so it is productized as
**`gfso/decompose/`** (`decompose(request)` → a CORE graph): an agent **calls** a full decomposition from a
short request rather than building the graph by hand. GFSO's irreducible role is the audit-into-basis.

## How the references were built (uniform across all 10)

One exhaustive over-inclusive enumeration from domain expertise (GFSO-free, no solution consulted) → cast into
the canonical basis → **audit** (find holes, matched by truth-maker/meaning, not wording) → patch → **reaudit**
(a fresh verifier that re-derives the requirements *blind*, before reading the reference, then confirms closure
and non-regression) → canon re-expression with no content changed. I.e. **one bare enumeration + a GFSO cast +
two audits** — the same bare-enum ⊕ gfso-audit pattern `decompose()` automates. (Authoring model not recorded.)

## Result — 10 complex tasks

**Two complementary runs.** **Opus = depth** (T01: the regime screen + reference-method) verifies the
mechanism and Findings 1–2. **Sonnet = breadth** (all 10 tasks × 3 iterations of search+audit, **+ two Opus
judges per candidate** — draft and converged — judging strictly on Opus to stay aligned with the Opus runs):
the completable public artifact (Opus is unaffordable at this scale) and a cross-model check. **Conclusions are
model-invariant; only the numbers differ** (Sonnet writes and audits slightly weaker — ceiling 81% vs 96%).

Reference-coverage (covered / reference-item-total), DRAFT (one search+audit) → CONVERGED (3 iters):

| task | domain | ref | draft | converged | climb |
|---|---|---|---|---|---|
| T01 | billing | 45 | 32 (71%) | 36 (80%) | +9 |
| T02 | ML pipeline | 48 | 36 (75%) | 40 (83%) | +8 |
| T03 | DB migration | 43 | 29 (67%) | 37 (86%) | +19 |
| T04 | financial close | 48 | 36 (75%) | 35 (73%) | −2 |
| T05 | SRE / SLO | 44 | 33 (75%) | 34 (77%) | +2 |
| T06 | backup / DR | 45 | 31 (69%) | 35 (78%) | +9 |
| T07 | concurrent cache | 53 | 39 (74%) | 42 (79%) | +5 |
| T08 | compiler front-end | 44 | 42 (95%) | 43 (98%) | +3 |
| T09 | multi-tenant authz | 50 | 33 (66%) | 40 (80%) | +14 |
| T10 | greenhouse control | 52 | 38 (73%) | 41 (79%) | +6 |
| **avg** | | | **74%** | **81%** | **+7** |

**This table is finding 1 (the cycle works), not the headline.** The **74% draft** is the cheap first pass and
already carries most of the decomposition; iterating to convergence (**81%**, basis growing past the reference)
is real but the *weakest* signal here — on Sonnet only +7. The climb and the absolute level are both larger on
**Opus** (T01 78%→96%, basis 49→72→84), where the story is how fully the loop reconstructs the
completeness-audited reference. Generalizes across all 10 domains; sole non-climb T04 (financial close, the
largest task); T08 (compiler) highest at 98%. Model-dependent quality (Sonnet ~81% / Opus ~96%) is a measured
boundary, not a defect. The *decisive* lever is finding 2 — how the pass is framed — not these absolute numbers.

## To reproduce with a fresh agent
Freeze nothing new: use `prompt_search.md`, `prompt_audit.md`, `prompt_judge.md` and the per-task
`complex/tasks/T0X.md` + `complex/references/T0X.md` verbatim. Run the loop above (subagents, ≤5 in parallel),
honor the wrapper/isolation, and emit the artifact layout. Same prompts + same task ⇒ the same trajectory shape.
