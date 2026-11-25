"""The suite's construction kit — one owner for the objects the tests keep building by hand.

Fifty-four test bodies built an `Engine` themselves, in five drifting spellings of the same three
decisions (which storage, whether signals are validated, how often the monitor wakes). That is the
off-diagonal element the FORM ratchet counts as `T1_engine_built_by_hand`: a constructor argument
that gains a meaning — as `state_timeout` and `runner` both did — has to be found in fifty-four
places, and the ones that are only *nearly* the same are exactly where a test stops testing what its
name says. The same happened to the Spec builder: `_spec` existed six times with four signatures.

The defaults here are the ENGINE's own defaults, deliberately: this module owns the *spelling* of
construction, not the policy of any test. A test that wants a non-default engine still says so, and
now says so in one vocabulary.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import subprocess
import tarfile
import threading
import time
from pathlib import Path
from typing import Optional

import gfso.adapters.execution as E
import gfso.adapters.hostrepo as H
from gfso import issuer
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm import credentials
from gfso.adapters.storage.memory import MemoryStorage
from gfso.core.types.ports import ClockPort, RunnerPort, StoragePort
from gfso import tools as T
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import TaskId, Probe, AcceptedRiskItem, Criteria, Predictability, Register, Spec
from gfso.engine import Engine
from types import SimpleNamespace

#: What a decomposition declares it knowingly does not cover. Every split the engine admits carries a register
#: with each entry's estimate and its own denial by S (STD-1, CHECK-4, §9.5), so the suite carries one rather than
#: inventing it per file: `REGISTER` in the written form the doors take, `REGISTER_ITEMS` as the engine holds it.
UNMODELLED_FAULT = AcceptedRiskItem("an unmodelled environment fault", Predictability.EXTRAORDINARY,
                                    "no precedent in this environment", "one occurs", 0.01,
                                    "the run stops and is resumed")
DENIAL = AcceptedRiskItem.denial_of(0.1, "the suite's stated estimate for a fixture split")
REGISTER_ITEMS = (UNMODELLED_FAULT, DENIAL)
REGISTER = [n.to_dict() for n in REGISTER_ITEMS]
#: the same register as the split's own carrier, for the engine's admission (`decompose_task(register=…)`)
REGISTER_SPLIT = Register(REGISTER_ITEMS)
DENIAL_ENTRY = DENIAL.to_dict()


def declare(e, producer: str, consumer: str, **kw) -> dict:
    """`add_dependency` as the consumer's issuer makes it (§11.5) — a fixture staging an edge in a split another party
    holds (an AUTO executor, a delegate) stages that holder's act, not the person's."""
    return T.add_dependency(e, producer, consumer, agent=str(e.graph.issuer_of(TaskId(consumer))), **kw)


def undeclare(e, producer: str, consumer: str) -> dict:
    """`remove_dependency` as the consumer's issuer makes it."""
    return T.remove_dependency(e, producer, consumer, agent=str(e.graph.issuer_of(TaskId(consumer))))


def a_repository(base: Path) -> Path:
    """`base` made the top of a git repository with a commit: the only base a container carries in (`hostrepo.carried_in`)."""
    base.mkdir(parents=True, exist_ok=True)
    for a in (["init", "-q"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "start"]):
        subprocess.run(["git", "-C", str(base), *a], check=True, capture_output=True)
    return base


def committed(place) -> tuple:
    """(tree, commit, None) of everything in `place` committed — a git of its own made where it has none —: what a
    DELIVER records (`_recorded`), and what every judge reads by its id: a directory is never judged as it stands."""
    git = lambda *a: subprocess.run(["git", "-C", str(place), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                    check=True, capture_output=True, text=True).stdout.strip()
    if not (Path(place) / ".git").exists():
        git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", "delivery")
    return git("rev-parse", "HEAD^{tree}"), git("rev-parse", "HEAD"), None


def a_place(place) -> str:
    """`place` as a reader by id reads it — what stands there committed (`committed`) — named as a contact names it."""
    committed(place)
    return str(place)


def carry_nothing_in(monkeypatch) -> None:
    """For a fake of the docker client, whose host git is no git: an empty bundle carried in (`hostrepo.carried_in`), and no base
    refused for what that git cannot say (`_refused_over` keeps its own record's refusal)."""
    def carried(base, project, d):
        tarfile.open(d / "in.tar", "w").close()
        return "c0ffee", d / "in.tar", []
    monkeypatch.setattr(H, "carried_in", carried)
    monkeypatch.setattr(E, "_refused_over", E.held_as_tree)


def imports_of(py: Path, repo: Path) -> list:
    """Every import a file makes, RESOLVED: (line, module, name). `from gfso import tools` is ("gfso", "tools"),
    `from .loop import x` inside `gfso/engine` is ("gfso.engine.loop", "x"), `import a.b` is ("a.b", None). Read as
    written, a relative import did not start with `gfso` and `from gfso import X` reduced to `gfso`: the layer gate, the
    core dist's closure and the private-import ratchet were each blind to both (D-F17) — one reading for all three."""
    package = py.relative_to(repo).with_suffix("").parts[:-1]   # a module's own package; an __init__'s is its directory
    out = []
    for n in ast.walk(ast.parse(py.read_text(encoding="utf-8-sig"))):
        if isinstance(n, ast.Import):
            out += [(n.lineno, a.name, None) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = ".".join(package[:len(package) - n.level + 1]) if n.level else ""
            out += [(n.lineno, ".".join(x for x in (base, n.module or "") if x), a.name) for a in n.names]
    return out


def module_reached(repo: Path, module: str, name: Optional[str]) -> str:
    """The module an import reaches: `module.name` where that name is itself a module or package of `module`."""
    sub = repo / module.replace(".", "/") / (name or "")
    return f"{module}.{name}" if name and (sub.with_suffix(".py").exists() or sub.is_dir()) else module


def hold_a_credential(monkeypatch, root: Path) -> None:
    """The Claude provider's one place, under `root`, holding the credential a test's calls run on: with none in force
    no call runs (`headless._in_force`), so a test of what a call does gives it one — never in the suite's shared home."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(root / "data"))
    credentials.put("claude", "token", "t-held", name="held")


def issuer_sweep(*args, **kw) -> list:
    """`answer_open_questions` with every issuer turn it started waited out. A turn cut at a 5 s bound left its ledger
    unwritten under a loaded suite: the next sweep asked the same question again and the counts went off (51 of 72)."""
    before = set(threading.enumerate())
    started = issuer.answer_open_questions(*args, **kw)
    for th in set(threading.enumerate()) - before:
        if th.name.endswith("(_run)"):          # the turn's own thread; another test's leftovers are not ours to wait
            th.join(120)
            assert not th.is_alive(), "an issuer turn did not end"
    return started


def written(verb, *a, **kw) -> dict:
    """A plan verb's written answer: it answers `{writing}` at once, and its same call again the plan once written."""
    while "writing" in (out := verb(*a, **kw)):
        time.sleep(0.01)
    return out


def carried_by_the_system(engine: Engine) -> Engine:
    """The engine under AUTO, as the user's path sets one before `plan`: a project the system's roles carry, where a
    refused account, a limit or a dead place stops it (a graph people hold alone is not stopped)."""
    engine._graph._storage.store_setting("mode", json.dumps({"mode": "auto"}))
    return engine


def make_engine(
    storage: Optional[StoragePort] = None,
    *,
    agents=None,
    llm=None,
    check_interval: float = 10.0,
    validate_signals: bool = True,
    critique_log_path: Optional[str] = None,
    state_timeout: Optional[float] = None,
    clock: Optional[ClockPort] = None,
    runner: Optional[RunnerPort] = None,
) -> Engine:
    """An engine over in-memory storage and a human agent port, unless told otherwise.

    `storage=None` means MemoryStorage and `agents=None` means HumanAgent: each is what a test
    overrides when the test is ABOUT that port — persistence, or an agent that answers by itself —
    and passing them everywhere else only hid which tests those were.
    """
    return Engine(
        storage if storage is not None else MemoryStorage(),
        agents if agents is not None else HumanAgent(),
        llm=llm,
        check_interval=check_interval,
        validate_signals=validate_signals,
        critique_log_path=critique_log_path,
        state_timeout=state_timeout,
        clock=clock,
        runner=runner,
    )


def pinned(name: str) -> tuple:
    """The procedure a criterion of this name pins — the scaffolding twin of a real contract's.

    Every criterion the product accepts must say what will be run to decide it (A1, §2); a test
    fixture whose criteria pin nothing is not a smaller contract, it is the pre-fix one, and it
    would quietly exempt the suite from the rule the suite exists to hold.
    """
    return (Probe(f"{name} holds", f"check {name}", "it holds"),)


def criterion(name: str, description: str = "", **kw) -> dict:
    """A criterion as a door receives it, procedure included. For tests that post raw dicts."""
    return {"name": name, "description": description or f"{name} description",
            "check": [{"behaviour": p.behaviour, "command": p.command, "expect": p.expect}
                      for p in pinned(name)], **kw}


def spec(description: str = "goal", *criteria: str, risks: bool = True) -> Spec:
    """A contract with one decidable criterion per name given, and the standard risk register.

    `risks=False` builds the register-less spec the CHECK-4 tests need — the one shape that must
    stay expressible, since a missing register is a defect the suite has to be able to construct.
    """
    return Spec(
        description=description,
        criteria=tuple(Criteria(c, f"{c} description", check=pinned(c))
                       for c in (criteria or ("c1",))),
        accepted_risks=REGISTER_ITEMS if risks else (),
    )


def reviewer_passes(engine, task_id, reviewer: str = "reviewer") -> None:
    """Record an honest reviewer PASS: one observation line per criterion the node actually has.

    Scaffolding, not a subject — a great many tests need a node past its seam before they can look
    at what they are really about (REOPEN, the FM-1 repair, the D6 gate). They used to reach for
    `record_reviewer_verdict(id, "PASS", [], "reviewer")`, whose empty observation set is precisely
    the evidence-free PASS the engine now refuses (§2.3: a conjunct nobody spoke to is ⊥, and ⊥
    does not carry a pass). Written once and reading the criteria off the node, so the scaffolding
    cannot drift away from a contract a test changes. At a seam the person issues no hand record stands for the
    validator's observation, so there the scaffolding is the validator's record (`instrument_passes`).
    """
    if engine.persons_seam(task_id):
        instrument_passes(engine, TaskId(str(task_id)), validator=reviewer)
        return
    task = engine.graph.get_task(task_id)
    engine.record_reviewer_verdict(
        task_id, "PASS", [], reviewer,
        observed={c.name: {"note": f"checked `{c.name}` by hand against the delivery: it holds",
                           "ran": [p.command for p in procedure_under(engine, task_id, c)]}
                  for c in task.spec.criteria})


def procedure_under(engine, task_id, c) -> list:
    """The pinned probes a validation of the node runs under criterion `c`: its own, and those of the DONE parts
    mapped to it — a part's PASS was on its own delivery, and the whole's may have rewritten it."""
    return list(c.check or ()) + [p for pc in engine.parts_procedure(task_id).get(c.name, ()) for p in pc.check]


def parts_held(engine, task_id, criterion: str) -> list:
    """The DONE parts' pinned probes under `criterion`, reported holding, as the packet hands them — what shows every
    child passing on the delivered result (the q_D pattern a refused re-delivery rests on)."""
    return [{"id": probe_id(pc.name, p), "behaviour": p.behaviour, "command": p.command, "expect": p.expect,
             "held": True}
            for pc in engine.parts_procedure(TaskId(str(task_id))).get(criterion, ()) for p in (pc.check or ())]


def instrument_passes(engine, task_id, validator: str = "validate_result", **kw) -> dict:
    """Record an instrument PASS that speaks to every criterion — the engine-level twin of
    `reviewer_passes`, for the many tests that need a node validated before they can look at what they
    are about. Written once and reading the contract off the node, so it cannot fall behind a test
    that changes the criteria."""
    task = engine.graph.get_task(task_id)
    return engine.record_exec_verdict(
        task_id, "PASS", [], validator,
        per_criterion=[{"criterion": c.name, "verdict": "pass",
                        "evidence": f"ran the check for `{c.name}`: it holds",
                        # …INCLUDING THE PROCEDURE THE CONTRACT PINNED. A PASS that skips it is
                        # demoted to ⊥ by the engine, so scaffolding that omitted it would stop
                        # every test that merely needs a validated node — and would do it for the
                        # right reason, which is why the fixture reports the pinned run instead
                        # of the rule being relaxed for tests.
                        "probe": [{"behaviour": p.behaviour, "command": p.command, "expect": p.expect}
                                  for p in (c.check or ())]
                        # …the parts' under their own ids, as the packet hands them (`unrun_parts`)
                        + parts_held(engine, task_id, c.name)}
                       for c in task.spec.criteria], **kw)


def emptied(engine, task_id, seams: bool = False) -> None:
    """The node's contract emptied in storage of every criterion (`seams` keeps those whose check reads a producer; its
    Dep edges, no criteria, stand) — the node no door makes since the admission held §2.2, standing as one stored
    before it, for the rules downstream that must still meet it — its checks recomputed."""
    t = engine.graph.get_task(TaskId(task_id))
    kept = tuple(c for c in t.spec.criteria if seams and c.depends_on)
    engine._graph.save_task(dataclasses.replace(t, spec=dataclasses.replace(t.spec, criteria=kept)))
    for n in (t.id, t.parent_id):
        if n is not None:
            engine._recompute_checks(n)


def assert_the_graph_can_still_move(engine, root="root"):
    """No node may sit in a state nothing can move while the graph reports itself healthy.

    THE CLASS, not another instance of it. Two locks were found and fixed on 2026-09-07 — a child
    accepted by the clock whose parent's conjunction refused it forever, and a `criteria: []`
    contract nothing could validate — and the author's note on the first was that it had been reported
    and promised closed across about ten sessions. Instances get patched; what was missing every
    time is a rule that fails on the SHAPE, so the eleventh cannot arrive quietly.

    The shape is not "a node is stuck" — a graph waiting for a person is healthy and says so. It is
    the DISAGREEMENT: the run is unfinished, nothing anywhere has an admissible move, and the
    surface still answers `stuck: false` ("the graph is working — poll again in a minute"). That is
    what both locks looked like from outside, and it is decidable from two reads.
    """
    step = T.next_step(engine, root)
    if step.get("complete") or step.get("stuck"):
        return step
    states = {str(t.id): t.state.name for t in engine.all_tasks()}
    terminal = {"DONE", "ABANDONED", "ESCALATED"}

    # (1) SOMETHING must admit a move. The coarse half.
    movable = {str(t.id): acts for t in engine.all_tasks()
               if (acts := (T.available_actions(engine, str(t.id)) or {}).get("actions"))}
    assert movable, (
        "the graph is neither complete nor stuck, and NO node admits a move from any role — "
        f"the frontier says {step.get('directive', '')!r} over a graph that cannot advance. "
        f"States: {states}")

    # (2) …AND WHAT IT SAYS IT IS WAITING FOR MUST BE ABLE TO ARRIVE. The sharp half, and the one
    # that catches a lock: a node advertising a move it will be refused still counts as "movable"
    # above, so the coarse half stayed green through the very defect it was written for (measured
    # while writing it — eleven cases green with the lock deliberately restored). What no lock can
    # fake is the object of the wait. In the 2026-09-07 case the root waited on two children that
    # were already DONE, under `stuck: false` and the directive "finish those children".
    for wait in (step.get("waiting") or []):
        finished = [w for w in (wait.get("waits_on") or []) if states.get(str(w)) in terminal]
        assert not finished, (
            f"{wait.get('task_id')} is said to be waiting for {finished}, and they are already "
            f"{[states[str(w)] for w in finished]} — nothing further can arrive from them, so this "
            f"is a wait that cannot end. The graph reports `stuck: false` and says "
            f"{wait.get('opens_with', '')!r}. States: {states}")
    return step


def round_over(dispatcher, task_id: str, ran) -> None:
    """Wait until the dispatcher's round on `task_id` has RUN and ENDED — `ran()` says the runner was called.

    A round still running is skipped by design, so a test that asks for the next round must first let this one end.
    Waiting on `_running` alone is not that: the spawn thread enters it only once scheduled, so on a loaded runner the
    set is empty before the round has begun and the wait passes straight into the race (ubuntu 3.11, 2026-10-18)."""
    for _ in range(1000):
        if ran() and task_id not in dispatcher._running:
            return
        time.sleep(0.01)
    raise AssertionError(f"the round on {task_id} did not run and end within 10 s")


def workdir(base, *parts) -> str:
    """A registrable working directory, created — a repository with a commit, as every directory a role is named in.

    The roster refuses a `workdir` that is not an existing directory — a role registered against a
    place that is not there is spawned into nothing, and a validator sent to one validates an empty
    tree. Tests that use directory NAMES as identity tokens ("theirs" vs "mine") still need those
    directories to exist, and this is the one line that says so.
    """
    p = Path(base).joinpath(*parts)
    if not (p / ".git").exists():
        a_repository(p)
    return str(p)


class FakeSpec(SimpleNamespace):
    """A spec stand-in for tests that build nodes by hand."""
