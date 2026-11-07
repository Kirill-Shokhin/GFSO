<div align="center">

# GFSO

**Make a plan falsifiable, then have agents carry it out.** GFSO (General Framework for Structured Operations) takes a plan with its checks fixed first, your own, or one it writes from your description, runs it with agents in Docker, and counts a result only when someone other than its executor has signed it.

[![PyPI](https://img.shields.io/pypi/v/gfso)](https://pypi.org/project/gfso/)
[![tests](https://github.com/Kirill-Shokhin/GFSO/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Kirill-Shokhin/GFSO/actions/workflows/tests.yml)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.11%20%E2%80%93%203.13-blue)

[Results][results] · [Usage][using] · [Security][security] · [Theory][theory] · [Documents][docs]

<img src="https://raw.githubusercontent.com/Kirill-Shokhin/GFSO/main/docs/hero.gif" alt="A recorded run replayed in the web UI: parts of the plan run in parallel, each session on the timeline, a part and then the whole sent back and reworked, the goal delivered" width="860">
<br>
<sub>A recorded run, replayed: a goal's parts run in parallel; a part, then the whole, goes back until its checks pass.</sub>

</div>

---

Your agent reports its task done; the engine does not take its word. A separate session runs the checks fixed before the work, on the commit actually delivered. One fails, and that part goes back with the failure attached. When every check has passed, the result waits on its own branch.

Running alone on three tasks from a public benchmark, three models said "done" 19 times, and 6 of those deliveries scored 9–91% on the benchmark's hidden tests. Given a finished plan and the same task description, the same models under GFSO completed 14 goals, none below 98.6%.

## Results

Three tasks of a public benchmark, three models, each with hidden tests no one sees during the work; the score is the share of them the delivery passes. Three of the nine cells, GFSO on a finished plan:

| task · model | | verdict | score | minutes | cost |
|---|---|---|---|---|---|
| `coreutils` · Haiku 4.5 | alone | done | 59–73% | 8–13 | $1.3–2.3 |
| | GFSO | `PASS` | **100%** | 120–253 | $21–40 |
| `c_compiler` · Haiku 5.5 | alone | not done | 74–92% | 19–36 | $1.4–4.4 |
| | GFSO | **`PASS`** | **98.6–99.7%** | 71–92 | $5.5–9.3 |
| `c_compiler` · Sonnet 5.5 | alone | done | 100% | 112–117 | $48–52 |
| | GFSO | `PASS` | 99.0–99.7% | **35–43** | **$12–15** |

<sub>n = 2–3 per cell, earlier builds. The plan's checks were verified against the benchmark's oracle before the run; the cost excludes writing it, and how it was prepared is in the full results. `c_compiler` is counted on 293 of its 299 tests, here and above. Every row: [`docs/RESULTS.md`][results].</sub>

<p align="center"><img src="https://raw.githubusercontent.com/Kirill-Shokhin/GFSO/main/docs/ui-panel.png" alt="A node's panel: state, last verdict, and each criterion with its rounds — crosses where a round failed it, a dot where it passed" width="820"></p>

One part of a SQL engine on Haiku 4.5: its validator refused `ordering, ties, LIMIT` ten rounds running (×), then it passed (●). Executor and validator were the same model, in separate sessions, on a copy of the delivered commit, against a check fixed before the work.

**Where it does not help.** Haiku 4.5 is too weak for the harder tasks (`c_compiler` and `sql_database`: no goal closed in five runs each, on this contract), and a strong model on work it can already do just costs more (Sonnet 5.5 on `coreutils`: 100% alone in minutes, four to six times the cost under GFSO). Writing its own plan from your description, on the same terms, GFSO completed `coreutils` and SQL at 91–100% on Haiku 5.5 and Sonnet 5.5. With the benchmark's hidden requirements left out of the task description, the same path on Haiku 5.5 reads 82–89%. It has no verdict yet on `c_compiler`.

## The idea

A plan is usually an unfalsifiable story: it fails, and no one can say which part was wrong. GFSO turns it into separately refutable claims: every part a decidable criterion with a named owner, every join a claim that these parts, together, make up the whole. In operation it is a loop against checks fixed before the work, and the engine enforces it: no executor can skip, move or sign its own check, only whoever issued the work can change a check, and the change is logged, and a failure comes back to the one part it belongs to. Two properties carry the promise.

**Failure localizes.** Under a correct split a parent passes exactly when every child passes: `V(parent) = AND(V(children))`. One false part cannot hide behind a green whole; the failure has one address.

**A claim cannot pass on its author's word.** At every handoff the verdict belongs to whoever issued the work, over a check that is not the executor's, and the engine refuses a `PASS` until a separate validator has run every criterion against the real delivery:

<p align="center"><img src="https://raw.githubusercontent.com/Kirill-Shokhin/GFSO/main/docs/gate.png" alt="The engine rejecting a self-signed PASS: verifier ≠ executor" width="760"></p>

Neither is a design choice. Both follow from two axioms: goals are verifiable, complex tasks decompose. Require of an aggregation that it be commutative and associative, that a failed necessary part fail the whole, and that it not be constant, and of the sixteen binary Boolean functions only `AND` remains. The ways a decomposition breaks form a basis of six failure modes; of 216 public post-mortems, none needed a seventh.

Where the guarantee stops: none of this proves your plan is the right plan. It proves the plan is checkable and that a failure points at the part that broke. Whether those parts truly make up the whole only contact with the domain can tell, and that part stays with the agent doing the work.

**[The theory, derived in full →][theory]**

## Install

You need Python 3.11–3.13, [pipx](https://pipx.pypa.io), [Claude Code][cc] and [Docker](https://docs.docker.com/get-docker/). Without Docker nothing unattended runs. Tested on Windows and Linux; on macOS only installation is tested. Claude is the model provider in live use; the provider layer accepts others (`ollama/…` and the like), so far tested only against a stand-in.

1. `pipx install gfso`, then `gfso setup`. It registers the tools with Claude Code, starts Docker Desktop if it is installed, and tells you what remains. `gfso demo human_only` needs no model: one person signs off her own work, the engine refuses, a second signs, and the `PASS` is recorded.
2. `gfso credential claude --sign-in`. A window opens where you sign in and paste a token (on Linux it prints the two commands instead). gfso's agents run separately from your Claude Code login, on their own token; they spend your subscription's usage, as Claude Code does.
3. Restart Claude Code, which loads the tools at its start: inside a session `/exit`, then `claude -c`, and the conversation resumes; otherwise just `claude`.
4. Describe the task and say "use gfso". Your agent reads the plan the system writes, gives the go-ahead, and hands you a link to watch. The verdict and the branch come back in the chat.

Or let your agent do it:

> Install gfso: `pipx install gfso`, then `gfso setup`, then `gfso credential claude --sign-in` (I will sign in in the window it opens). Do it all without asking me. Then tell me to restart with `/exit` and `claude -c`.

A first small task takes about 10–27 minutes, much of it spent on the plan, and costs about $0.1 for the system and $0.3–0.6 for your own Claude Code session. If something is wrong later, `gfso doctor` tells you what.

## Security

Agents here run unattended, with no one to approve a command, so the work runs in Docker:

- **None of your disk is mounted** where an agent or a check runs. Your repository goes in as its committed history.
- **No agent holds your credential.** One small container holds the key and passes only the model's messages.
- **Each validation runs in its own container**, on a copy of the delivered commit. No one validates their own delivery.
- **Network `off` or `open`, per project.** `off` reaches only the model.
- **The result is its own branch**, `gfso/<project>/accepted`. Your branches and working tree stay as they were.

There is no per-task VM, your repository's full history goes in, and the model's provider reads what the agents send it. What is and is not guaranteed: [`SECURITY.md`][security].

## Formal status

The axiomatic surface is audited in Lean 4 (no mathlib, no `sorry`), and the protocol is model-checked in TLA+.

## Citation

```bibtex
@misc{shokhin2026gfso,
  title  = {GFSO: Formal Guarantees for Compositional Task Validation
            in Hierarchical Organizations},
  author = {Shokhin, Kirill},
  year   = {2026},
  url    = {https://github.com/Kirill-Shokhin/GFSO},
  note   = {Preprint in preparation}
}
```

## License

MIT

<!-- mcp-name: io.github.Kirill-Shokhin/gfso -->

<!-- Absolute URLs: this file is also the package's PyPI description, where relative links do not
     resolve. Reference style keeps the prose readable and the addresses in one place. -->
[theory]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/THEORY.md
[results]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/RESULTS.md
[using]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/USING_GFSO.md
[security]: https://github.com/Kirill-Shokhin/GFSO/blob/main/SECURITY.md
[docs]: https://github.com/Kirill-Shokhin/GFSO/blob/main/docs/README.md
[cc]: https://claude.com/claude-code
