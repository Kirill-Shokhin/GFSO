# The plan file: `gfso-plan/1`

A plan is an artifact of its own, handed between parties the way a config file is: one text file, readable whole in an
editor, that exists before any project does. The customer reads all of it, then either sends a note (the plan is refined
and a new file comes back) or gives the go (a project is built from the file exactly, or the go is refused naming why).
The system wrote it, so after the go contact may repair it: a check of its own that contact refutes is changed, on the
record with its reason. A plan handed in whole (`auto_decompose` with `spec`) stays closed: the system only adds to it.

The file is TOML (`gfso/decompose/artifact.py`). The module is the format's whole implementation: `render(goal, spec, review,
notes, executor)` writes it, `parse(text)` reads it back, and the contract is `parse(render(x)) == x`. A hand-edited file
is read by the same `parse`, which first checks its form (`form`, below).

The verbs: `plan(request, model)` authors and reviews a file with no project (`planning.author`); `refine_plan(file,
note, model)` answers a note (`planning.refine`); `auto_decompose(plan=file)` is the go (`tools_llm.auto_decompose`, which
reads the file with `tools_llm._the_go`). All three take a path or the text.

## What the plan is, and what is not the plan

The plan is the authority-free plane of the canon: tasks T with their criteria and pinned checks, the split's mappings,
the dependencies Dep, and the ACCEPTED_RISKS register, plus the goal they answer. It names nobody who executes it: Del is
absent from the file because it enters at the go, from the project's mode (`build_graph_live(..., assignee)`,
`gfso/decompose/build.py`). Two plans that differ only in who runs them are one file.

Three sections sit beside the plan because they are not it, and none is read by the build:

| section | what it is | why apart |
|---|---|---|
| `[fit]` | the decomposer's size judgement per part, against the executor's session | fit (kappa) is a property of the actor, not of the work (§3.7); the same plan fits one executor and not another |
| `[review]` | the Level-2 review run over the plan: what the criteria leave undecided | a verdict about the plan, produced by the system after the plan was written |
| `[[notes]]` | the customer's notes with the answer each got | the history of the file, not its content |

`[inputs]` is machinery, described below.

## The file

Top level, in the order `render` writes it:

| field | type | required | meaning |
|---|---|---|---|
| `format` | string | yes | exactly `"gfso-plan/1"`; anything else is refused (`parse`) |
| `goal` | string | yes, non-empty | the request the plan answers, as the customer worded it. It becomes the root's description at the go |
| `[plan]` | table | yes | the plan, below |
| `[fit]` | table | no | executor-relative marks, below |
| `[review]` | table | no | the Level-2 review, below |
| `[[notes]]` | array of tables | no | the customer's notes, below |
| `[inputs]` | table | no | the checks' input files, below |

TOML has no null: a field that is `None` is left out of the file (`_table`), and a missing field and an absent one read
the same.

### `[plan]`

| field | required | meaning |
|---|---|---|
| `name` | no | short label of the goal |
| `root_criteria` | yes, at least one | the goal's own criteria, the contract the whole is judged by |
| `subtasks` | no | the parts the goal is split into; `[]` or absent is a goal not split (the one root carries all its criteria) |
| `mappings` | no | the split's coverage: which part carries which root criterion |
| `deps` | no | the seams between parts |
| `accepted_risks` | no | the split's register of accepted risks |
| `denial` | no | the split's pre-registered denial, a register entry kept apart |
| `scope` | no | what the goal deliberately excludes |

**Criteria.** A criterion is `name` (required; unique within its part and among the root's — `form` refuses a repeated one, which the build would collapse)
and `description`, and `check`, an array of probes. A criterion with no `check` pins nothing: nothing would decide it but
a procedure improvised at validation time, and the admission refuses it (`procedure.admission_defects`; a bare `depends_on` entry is no
criterion but a Dep, below). The checks are
the criterion's decision procedure fixed before the work, so that validating it is running them, not forming an opinion.

**Pinned checks.** A probe is `behaviour` (the conjunct of the criterion it observes), `command` (how to observe it,
runnable by someone who was not the executor), `expect` (what the observation must show), `exact` (true: `expect` is the
whole output the command prints on correct work and the system decides it by running the command; false: `expect`
describes the output in words and a reader judges) and `inputs` (the files the command reads, `{relative path: content}`,
which the command finds under `{inputs}`). The fields are those of `Probe` (`gfso/core/types/primitives.py`); `exact` and
`inputs` are written only when set (`Probe.to_dict`).

**Parts** (`[[plan.subtasks]]`): `id` (required, unique; the name the file's other places refer to), `name`, `description`
(the part's contract text), `criteria` (as above; a part's criteria are what it must satisfy), and the claim of what its
work touches: `writes` (files it produces) and `runs` (the parts whose code its checks run), kept as the decomposer's
statement of what the seams carry (`Engine.record_seam_claim`). A criterion of a part may carry `depends_on`, the id of
the part it reads the result of.

**Split and mappings.** `[[plan.mappings]]` is `{criterion, child_id}`: the root criterion `criterion` is carried by the
part `child_id`. The mapping is the split's claim that the parent passes exactly when its children do; a root criterion no
part carries is a hole the review names. A mapping naming a root criterion or a part that does not exist is dropped by the
build (`_children_from_spec`), which is why `form` refuses it.

**Dep.** `[[plan.deps]]` is `{from, to, glue, reads}`: part `to` consumes what part `from` produces. `glue` says what
passes across the seam, and `reads` lists the files of the producer that the consumer's work reads. A criterion's
`depends_on` declares the same kind of edge (its description serves as the glue, `primitives.seams_apart`); when a pair
has both, the criterion's text is the edge's glue, so write them to agree.

**Register.** `accepted_risks` is a list of `{item, predictability, justification, invalidation_condition, p, impact,
component}`: an uncertain event the split accepts, with its probability `p`, what it costs and when to revisit it
(`AcceptedRiskItem`). `denial` is `{p, justification}`: the split's composition claim (the parent fails while every child
passes) with the author's estimate that it is refuted at contact. A scope exclusion is not a risk; it goes to `scope`.

**Scope.** `[[plan.scope]]` is `{item, why_out}`. Write the reason inside `item`; the build folds a non-empty `why_out`
into `item` as `item — why_out` and reads it back with `why_out` empty (`build._build_graph_live`, `extract.extract_spec`).

### `[fit]`

`executor` (the session the fit was judged against; empty when none), `whole_volume` and `whole_fits_one_session` (the
whole plan's size estimate in words and the judgement), and `parts`, an array of `{id, volume, fits_one_session}`, one per
part judged. The marks are put back on the parts by `parse` and recorded by the build (`_record_the_session_fit`).

### `[review]`

Written by `planning._review`: `by` (the reviewing model), `gate_passed`, `l0l1_failures`, `semantic_covered`,
`semantic_findings`, `conflicts`, `undecided_obligations` (each `{obligation, admits}`: what the goal requires that no
criterion decides) and `criteria_verdicts` (each `{criterion, verdict, why}`). The review is what the customer reads
to decide whether to send a note; `refine` hands its open `undecided_obligations` to the round with the note.

### `[[notes]]`

`{note, by, answer}`: the customer's note, the model that answered it, and the answer, which is what the round changed in
the plan stated mechanically (`planning.changes`), or that it changed nothing. A refine appends one; it never edits the
earlier ones.

### `[inputs]` and how input files are named

A check's input file would be repeated wherever a check uses it and would bury the plan in file contents. Each is
written once, at the end, under a name made of its content: `"sha256-"` plus the first 16 hex digits of the SHA-256 of
`json.dumps(content)` (`artifact._hoist`). In the plan the probe's `inputs` maps each relative path to that name:

```toml
[plan.root_criteria.check.inputs]
"a.c" = "sha256-7c1d0e3a9b42f5e8"

[inputs]
"sha256-7c1d0e3a9b42f5e8" = '''
int main(void) { return 0; }
'''
```

Equal content is one entry however many checks use it, and `parse` puts the contents back (`_lower`). The names are
derived: a person editing a file changes the content under `[inputs]` and leaves the name, or changes both consistently;
an input named in the plan with no entry under `[inputs]` is refused (`form`).

## Reading a hand-edited file: `form`

`parse` calls `artifact.form`, which returns every problem in the file's shape, each as `<field>: <problem>`, and raises one
`ValueError` listing them all. It checks what the build would otherwise lose or fail on: a non-empty `goal`; a `[plan]`
table; at least one root criterion; a `name` on every criterion, an `id` on every part, an `item` on every scope entry;
part ids unique; criterion names unique at the root and within each part (a mapping names its criterion); every mapping
naming a root criterion and a part that exist; every dep and every `depends_on` naming an existing part; every `[fit]` part
naming an existing part; every input hash having its file; no section, no field of `[plan]` or `[fit]` and no field of a
part, criterion, check, dep, mapping, scope entry or risk the build does not read (a misspelled `expect` or
`[[plan.mapping]]` would otherwise vanish); `exact` true or false, never a string. It does not judge whether the
plan is good: that is the review's.

## After the go

`auto_decompose(plan=file)` builds the project from the goal and plan the file holds, as they stand, and records the plan as the user's (`Engine.give_users_plan`). Everything in the file is then in
the graph exactly: the criteria with their pinned checks, the mappings, the Dep edges with glue and reads, the register
and the scope. What the build adds is what the file leaves out: each part's Del, from the mode, and the nodes' states. No
model is called: a plan the admission would refuse (`procedure.admission_defects`, for instance two probes of one criterion
running one command) is refused as it stands, naming why, before anything is built (`decompose._repaired_before_build`,
`_admitted_as_it_stands`), and repaired in the file (`refine_plan` with a note naming it) or handed in open
(`open_plan=true`) for the system to repair; a file that passes it is built untouched. The
plan read back off the graph (`extract_spec`) renders to the same file, and `tests/test_the_go_only_adds_to_the_plan.py`
holds that.

From then on, in a project run in AUTO, the system does not re-split the plan or rewrite any node's criteria; it may add
(`validation.users_plan`, `users_criteria`). A change to the plan is the customer's act on the project.

## Changing the format

The version in `format` names the reading of the file, not the date of the tool. `parse` accepts only the version it
knows and refuses every other, so a file is never read under a meaning it was not written for.

- A change that leaves every existing file meaning what it meant, such as a new optional field the build may ignore, keeps
  `gfso-plan/1`: older files read as before, and `parse(render(x)) == x` still holds for them. An older reader refuses a
  field it does not know (`form`), so a new field ships with the reader that knows it, and a file written with it is not
  read by an older one.
- A change that alters what an existing field or section means, makes a field required that was optional, removes or
  renames one, or changes how the input names are derived is a new version, `gfso-plan/2`, and ships with the reader for
  the old one or a conversion for its files.
- The contract `parse(render(x)) == x` and the line between the plan and the three sections that are not the plan hold for
  every version.
