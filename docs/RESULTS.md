# GFSO: results, row by row

Every counted row of the benchmark comparison, what each leaves out, and the runs of the path a person actually takes. The short version is the table on the [product page](../README.md); the record behind it is [`e3_rows.csv`](e3_rows.csv) and [`EVIDENCE_LOG.md`](EVIDENCE_LOG.md).

## What was run

Three tasks of the public benchmark [SpecBench](https://arxiv.org/abs/2605.21384) — `coreutils`, `sql_database`, `c_compiler` — each with an explicit contract and a **held-out suite**: the benchmark's own tests, shown to no agent during the work and run only on what is delivered (who saw part of them before a run, to write a plan, is under "What each plan was"). Three models. **The agent alone** is the default Claude Code agent: it writes the code, its own checks and its own report. **GFSO** is its automatic mode: the same model plays every role and nobody holds the project, working on a **given plan**, whose checks were verified beforehand against the benchmark's oracle, or on a plan it writes itself.

"Done" means two different things here. The agent alone says it. Under GFSO it is the goal's `PASS`: every verdict below ran the checks pinned to it and was signed by a validator that is not the executor. The held-out score then says how complete the plan's checks were.

- **The agent's own "done" is often not the contract's.** Across the rows on one contract it said done 19 times, 8 of them with held-out tests failing (6 when `c_compiler` is read on its 293-test yardstick, below). On a given plan, on that contract, GFSO closed 14 goals, 4 of them with held-out tests failing, at 98.6–99.7%. Where it decides the outcome it costs 15–20 times the money and the time of the agent alone on `coreutils` · Haiku 4.5, and two to four times on `c_compiler` · Haiku 5.5.
- **Where the model needs no help, GFSO only adds cost.** In five cells the agent alone already reads 90% or more; there GFSO on a given plan reaches the same or a higher score in more time, and on Sonnet 5.5 at four to six times the money on a given plan, 25–30 times on its own. `c_compiler` · Sonnet is the exception: there GFSO took a third of the time and a quarter of the money and scored the same or 0.7 points lower.
- **Where it does not hold.** The oldest model, Haiku 4.5, on the two harder tasks: on `c_compiler` no goal closed in five runs; on `sql_database` goals closed only on a later plan run without the contract's addendum (the text writing the benchmark's hidden requirements into the statement, so both sides work to one contract), so not on one contract with the agent alone (100%, 81.8%). With GFSO writing its own plan there is no comparison yet: among the counted rows it closed four goals (three at 100%, one at 90.9%) only where the agent alone already reads 90% or more, and has no verdict on Haiku 4.5 or on `c_compiler`.

## The table

Only rows a pre-registration counts are here — a document fixing the question and its readings, with amendments, each written before its rows but one: the amendment that let the 100% final-plan row resume after an engine fix was written after that goal's verdict was seen. One row of a cell is one observation, not a rate. Each cell gives the verdict, the held-out score, the active time and the cost.

| task · model | the agent alone | GFSO, given plan | GFSO, own plan |
|---|---|---|---|
| `coreutils` · Haiku 4.5 | done 3/3 · 59–73% · 8–13 min · $1.3–2.3 | done 2/2 · 100% · 120–253 min · $21–40 | no verdict ¹ |
| `coreutils` · Haiku 5.5 | done 3/3 · 100% · 9–15 min · $0.3–1.0 | done 2/2 · 100% · 19–33 min · $0.8–0.9 | done · 100% · 53 min · $1.0 |
| `coreutils` · Sonnet 5.5 | done 3/3 · 100% · 4–5 min · $0.7–0.9 | done 2/2 · 100% · 7–10 min · $4.2–4.5 | done · 100% · 47 min · $24 |
| `sql_database` · Haiku 4.5 | done 2/3 · 9% · 10–12 min · $1.5–2.2 | not done 5/5 ² · final plan ³: done 2/2 · 100%, 81.8% · 5.8 h, 7.6 h · $73, $63 | no verdict ¹ |
| `sql_database` · Haiku 5.5 | done 3/3 · 100%, 100%, 90.9% · 16–21 min · $0.3–1.3 | done 2/2 · 100% · 56–57 min · $1.0–1.2 ⁴ | done · 90.9% · 4.4 h · $4.0 |
| `sql_database` · Sonnet 5.5 | done 3/3 · 100% · 6–8 min · $1.0–1.3 | done 2/2 · 100% · 13–17 min · $4.3–5.6 | done · 100% · 110 min · $29 |
| `c_compiler` · Haiku 4.5 | not done 3/3 · 12–15% · 7–10 min · $0.9–1.6 | no goal closed in 5 rows ⁵ | no verdict ($34) |
| `c_compiler` · Haiku 5.5 | not done 3/3 · 74–91% · 19–36 min · $1.4–4.4 | done 2/2 · 98.6%, 99.7% · 71–92 min · $5.5–9.3 | no verdict |
| `c_compiler` · Sonnet 5.5 | done 2/2 · 99.7% · 112–117 min · $48–52 ⁶ | done 2/2 · 99.7%, 99.0% · 35–43 min · $12–15 | no verdict, two attempts |

1. Stopped on spend with no ledger on disk: `coreutils` by hand at about $115, `sql_database` by the operator's spend limit at $60; `c_compiler`'s $34 is the spend limit's log.
2. The first plan: three rows, one ended by the issuer's cancel (the issuer is the party that handed the goal out), two cut at the 9-hour ceiling, 7.9–8.4 h, $68–92; then two on an amended build, $89 and $121. No score on record for any.
3. The final plan ran without the contract's addendum the agent alone ran on, so it is not on one contract with it and is read apart. The 100% row resumed once after an engine fix. The 81.8% row's gap is one `UPDATE … WHERE` defect no check of that plan could see; run on from that result with one probe added — chosen after the held-out suite had shown the failure, a continuation and not a fresh sample — it closed at 100% in another 52 min for $11.
4. The same final plan, polished on this model's own earlier runs and run without the addendum: done · 100% · 51 min · $2.4.
5. Two rows cut at the ceiling ($60, $65); two on the amended build, no score on record ($85, $126); one on the last plan, run without the addendum, stopped by the system after 8 h ($67).
6. A third row is void under the pre-registration's own rules.

## How to read the numbers

Time is active: the machine's sleep and the account's limit windows are measured off each row's own events and taken out. Cost is the CLI's reported cost, on the row's ledger under GFSO; a run cut before its report is priced by its model's measured factor. On the given-plan side the cost leaves out writing and verifying the plan. `sql_database`'s held-out suite has 11 coarse items, so one item is 9%.

On `c_compiler` the given-plan scores leave out the six held-out tests its probes were derived from, as pre-registered; the other sides here are over all 299, and on the shorter yardstick the agent alone with Sonnet 5.5 reads 100%: its one failing test is one of the six. The product page reads every `c_compiler` cell on the 293, which is why the agent alone on Haiku 5.5 shows 74–92% there and 74–91% here.

The task's starter code alone reads 13% on `coreutils`, 9% on `sql_database`, 20% on `c_compiler`, so a row left at the starter has no reading, and the agent alone on `c_compiler` · Haiku 4.5 ends below it.

## What each plan was

The **first plan** is the one the pre-registration named; an **amended build** is the engine changed by a later amendment; the **final** plan of `sql_database` and the **last** of `c_compiler` are later versions of the plan, made after those rows stopped.

For `c_compiler` some of the given plan's checks were derived from named held-out tests; `sql_database`'s plan was written by Sonnet 5.5 and repaired by hand, the areas of its probes chosen from what earlier runs failed on the held-out suite. So the given-plan side shows a good plan carried to the end — on `coreutils` · Haiku 4.5 and `c_compiler` · Haiku 5.5 — and the own-plan side is the system writing one. Two other kinds of value no row measures: a strong but imprecise plan repaired by contact during the work, and division of labour — a stronger model writing the plan, a cheap one executing — seen only inside `sql_database`'s given plan on the Haiku rows, and not priced, its cost charged to neither side.

## The builds

The builds are not one build. The agent alone is in no build's path. GFSO's rows ran on the pre-registered build `65cf516` and, where a row was re-run, on later builds, each change answering a defect measured on an earlier row; every row's build is in [`e3_rows.csv`](e3_rows.csv). No row of this table ran on the current code.

| rows | build | what differs from the one before |
|---|---|---|
| the agent alone; given plan, first plans | `65cf516` | the pre-registered build |
| own plan: `coreutils` and `sql_database` · Haiku, `coreutils` · Sonnet | `fb85648` | a criterion the system writes is read against its own checks before the plan is built |
| own plan: `sql_database` · Sonnet and `c_compiler`; given plan, amended, Haiku 4.5 | `9155db9` | pinned inputs kept through a repair; a leaf that keeps failing owes a split; a limit window no longer reads as an answer; a check cited by its directory counts as that check |
| given plan, final plan, `sql_database` | `9b405b4`; `0ecd3de` then `7981da9`; `50d7835`; the continuation `31a5e40` | a handed plan is the user's at every node; a run has a stopped state; a count of failures no longer stops a run |
| given plan, last plan, `c_compiler` · Haiku 4.5 | `7213607` | the same line |

The builds are development commits, kept as provenance and not published.

## Not counted here

Debugging rows — runs made to find defects — of `coreutils` · Haiku 5.5, own plan, with the addendum: on build `c5aa7ed` one stopped at its plan's review after 78 min and $1.08, no work started; on `7a8480c` one closed done at 100%, on the accepted result and the signed branch alike, in 77 min for $2.27, the plan 27 of them and $0.61 of it.

Own-plan rows of 2026-10-27…31 ran without the addendum, another contract: `coreutils` · Haiku 5.5 done at 89.1% and 87.4%, `sql_database` · Haiku 5.5 done at 81.8%, `c_compiler` · Haiku 5.5 not done in four rows at the starter's 20%. Rows of earlier builds on the same contract and plan: `coreutils` · Haiku 4.5 over five rows each reads 59–76% alone and 100% on the given plan; `c_compiler` · Haiku 5.5 alone has a best of 94.6%, not done.

Every counted row is in [`e3_rows.csv`](e3_rows.csv); the void rows and what is not shown are in [`EVIDENCE_LOG.md`](EVIDENCE_LOG.md), entries 13.46, 13.47 and 13.51.

## The path a person takes

Fresh Claude Code clients (Sonnet 5.5) on clean installs of the builds of 2026-11-04 to 11-09, the last two runs on this release's own tree, every role on Haiku 5.5. `system` is what gfso's own agents cost, `client` the person's Claude Code session:

| a task told in words | runs | goal's `PASS` | time | system | client |
|---|---|---|---|---|---|
| a small command-line utility | 18 | 18 | 9–27 min (one 54, on a stall since fixed) | $0.05–0.16 | $0.24–0.62 |
| a task of two to five parts | 5 | 4 (one stopped at 60 min, no verdict) | 27–45 min | $0.22–0.42 | $0.44–1.34 |
| `coreutils`, its held-out suite after, network `off` | 1 | 1, at 100% | 67.5 min | $1.82 | $0.93 |

Each result landed on a branch of its own, `main` untouched — one in an existing repository whose directory name holds a space. The latest runs had nothing allowed ahead and no git identity, in the client's default auto mode; a person answered the client's own first-run menus and, on the last of them, nothing else. With `claude -p` nobody is there to approve a prompt: one client's `git` commands for a new repository were refused until allowed in advance.

These runs show the path, not value: the small tasks have no held-out suite (their results were checked right on control data) and a bare Sonnet 5.5 did them as well in 10–30 seconds for $0.04–0.07; on `coreutils` a bare Haiku 5.5 also reads 100% ([`EVIDENCE_LOG.md`](EVIDENCE_LOG.md), entries 13.52–13.54).
