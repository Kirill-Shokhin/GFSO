# The task packet — what a node must carry, and in what shape

A GFSO node is a contract (canon §10: `T = (spec, criteria, deadline)`, plus `Del` and `Dep`). This
page fixes the **content** an authoring call must supply and the **keys** the engine reads, so that
two agents authoring the same graph produce the same object. It is derived from `gfso/tools.py` —
the single action surface behind all three doors — and pinned by `tests/`.

It is not the theory. What a criterion IS, and why the register is mandatory, is the canon
(`applied_gfso_v4_en.md` §10, §13.1); how to work the loop is [`USING_GFSO.md`](USING_GFSO.md).

## The spec object

```json
{
  "name": "Short title",
  "description": "the full text of the obligation",
  "criteria": [{"name": "c1", "description": "what must be observably true",
                "depends_on": "<producer task id>"}],
  "accepted_risks": [{"item": "what is being accepted",
                      "predictability": "STATISTICAL | EXTRAORDINARY",
                      "justification": "why carrying it is acceptable",
                      "invalidation_condition": "what would flip it back in scope"}],
  "scope": ["a capability this goal deliberately does NOT include — and why"]
}
```

| Key | Required | What it is |
|---|---|---|
| `description` | yes | the obligation in full; `name` is only the UI label (≤6 words) |
| `criteria` | yes, non-empty | the WHOLE obligation: decidable pass/fail conditions on the result. A node with children and no criteria of its own is a hole, not a covered node |
| `criteria[].depends_on` | when it applies | the ONE producer node this criterion consumes. It is what creates the Dep edge — a seam is criteria-content, not a separate declaration. A list is refused |
| `accepted_risks` | **on any node you decompose** | risk EVENTS with a materialization probability, each with a predictability verdict. Empty on a decomposed node blocks execution (CHECK-4, §13.1: without the register the decomposition is incomplete by definition). A leaf carries none |
| `scope` | when the exclusion is not obvious | capabilities the goal deliberately excludes. These have NO probability, so they do **not** belong in the register — CHECK-4 refuses them there |
| `deadline` | optional | ISO-8601, passed beside the spec. A child's deadline must fall before its parent's |

**Predictability decides where a factor may live.** `ORDINARY` is refused in the register — an
ordinary event belongs in the decomposition as work. `STATISTICAL` requires a justification.
`EXTRAORDINARY` (no precedent, not derivable from known models) needs none.

**A criterion of the node itself may never appear in the register.** Accepting your own criterion as
a risk retires an obligation by writing prose; the canon's path for a criterion believed defective is
`CHALLENGE` (a spec defect, counted in q_T) or the issuer's revision. The engine refuses the record.

## Authoring calls

```
create_task(task_id, spec, assignee=…, parent_id=…, deadline=…)
decompose(parent_id, children=[{task_id, spec, assignee, covers: [parent criterion names]}],
          mappings=[{criterion, child_id}])
edit_criteria(task_id, criteria)        # replaces criteria, carries the rest
edit_accepted_risks(task_id, items)     # replaces the register
map_criterion(parent_id, child_id, criterion)
add_dependency(from_id, to_id, glue=…)
```

Every parent criterion must be mapped to the child that delivers it — `covers` on the child and the
flat `mappings` list are the same claim, and either is accepted.

## What the door decides for you

On the **MCP** door the actor is the session, not a parameter: `source` on `signal` and `agent` on
`revise` / `edit_criteria` / `edit_accepted_risks` / `reopen`, and `reviewer` on `record_verdict`,
are removed from the schema and filled with the caller's own identity. Everything arriving over MCP
*is* the agent, so it cannot sign an act as someone else. The CLI (`gfso run …`) is the unpinned
door and names the actor explicitly.

## What is NOT part of this contract

`Criteria` also carries `input`, `expected`, `n` and `timeout`. Those belong to one mechanical
verifier used by the benchmark harness (`gfso/adapters/verifiers/subprocess_verifier.py`, which
documents them), they are **not read by these calls**, and a criterion authored through a door
carries none of them. Do not write them here.
