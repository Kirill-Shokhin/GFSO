"""Gaps found by driving the product as a user, pinned as executable facts rather than prose.

Four agents ran real tasks through the doors on 2026-08-20 and hit these; each was then confirmed
against the code. They are recorded here as `xfail(strict=True)` so the suite stays honest in both
directions: today they document what the product actually does, and the day one is repaired its test
turns RED as an XPASS, which is the signal to delete the marker and keep the assertion. A defect
written only in a plan is a defect nobody is holding.

Not included: gaps that need an LLM to reproduce (the rework-descent gate refusing a parent whose
validator returned ⊥ — it reads a RECORDED verdict, and a hand-signalled FAIL writes none).
"""
from __future__ import annotations

import inspect
import json
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso import driver, runtime as _rt
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.config import validator_retry_model
from gfso.core.types import (DoneReason, Signal, SignalData, State, TaskId, passed,
                             settled_positive)
from gfso.critic import runner as _runner
from gfso.decompose.build import build_graph_live
from gfso.delegate import AgentRegistry, Dispatcher
from gfso.driver import _as_list, _wants_list, run, run as _cli_run
from gfso.engine.loop import _CANCELLING_GRACE_S
from gfso.runtime import ProjectRegistry
from tests.support import make_engine
from tests.test_validate_result import _ValidatorLLM, _delivered_node, _eng, _fenced


def _engine(storage=None):
    e = make_engine(storage, llm=None,
                     validate_signals=True, state_timeout=0)
    e.start()
    return e


def _root(e, extra_criteria=()):
    T.create_task(e, "root", {
        "name": "root", "description": "a goal",
        "criteria": [{"name": "c1", "description": "the thing"}, *extra_criteria],
        "accepted_risks": [{"item": "fixture", "predictability": "extraordinary",
                            "justification": "accepted here", "invalidation_condition": "never"}]},
        "agent")


def test_a_revised_contract_can_be_read_back_from_the_log():
    """§14.4 Inv-7: 'every re-ASSIGN appends a version to the append-only log … past versions live
    in the log'; Thm 11: every decision has a record. Measured: `audit_log` carries the EVENT
    (signal, states, effects) and no spec, and `tasks.revisions` is a COUNTER, so a contract
    overwritten by a revision is unrecoverable. One agent overwrote another's root this way and the
    original was gone."""
    db = str(Path(tempfile.mkdtemp()) / "r.db")     # Windows will not unlink an open sqlite file
    e = _engine(SqliteStorage(db))
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "MATERIALLY DIFFERENT"}], "agent")
    e.stop()

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    blob = " ".join(json.dumps(dict(zip([d[0] for d in cur.description], row)))
                    for cur in [con.execute("select * from audit_log")] for row in cur)
    assert "the thing" in blob, "the pre-revision contract is not readable from the log"


def test_create_task_refuses_an_id_that_already_exists():
    """`create_task` desugars to ASSIGN, so on a live node it is a revision (canon-legal). But the
    door is named CREATE: an agent certain it is creating silently replaces someone's contract —
    exactly how a running project's root was destroyed. Creating and revising should not be the
    same call."""
    e = _engine()
    _root(e)
    out = T.create_task(e, "root", {"name": "other", "description": "other",
                                    "criteria": [{"name": "z", "description": "z"}],
                                    "accepted_risks": []}, "agent")
    kept = e.get_task("root")
    e.stop()
    assert out and out.get("error"), f"the existing node was overwritten: {out}"
    assert "revise" in out["error"] and "edit_criteria" in out["error"], (
        "the refusal does not say how to change a node on purpose")
    assert kept.spec.name == "root", "the contract was replaced despite the refusal"


def test_editing_criteria_keeps_the_dependency_edges():
    """Dep seams are stored AS criteria (`dep__{producer}` carrying `depends_on`), so replacing the
    whole set used to delete the graph's edges without a word — and restoring a staled plan gate
    forces the caller through this very verb, putting the trap on the recovery path. Editing what a
    node must ACHIEVE is not a request to sever what it WAITS FOR; removal stays explicit
    (`remove_dependency`, or passing the `dep__` criterion yourself)."""
    e = _engine()
    _root(e)
    for cid in ("prod", "cons"):
        T.create_task(e, cid, {"name": cid, "description": "part",
                               "criteria": [{"name": "k", "description": "d"}]},
                      "agent", parent_id="root")
    T.map_criterion(e, "root", "cons", "c1")
    T.add_dependency(e, "prod", "cons")
    before = T.get_dependencies(e)
    assert before, "precondition: the dependency was declared"

    T.edit_criteria(e, "cons", [{"name": "k", "description": "d"}], "agent")
    after = T.get_dependencies(e)
    e.stop()
    assert after == before, f"the edge vanished with the criteria: {before} → {after}"


def test_a_human_verdict_must_carry_evidence_like_a_machine_one():
    """The two acceptance doors are held to opposite standards.

    A validator's report is REFUSED unless every criterion carries a re-runnable probe ("a verdict
    states what it OBSERVED … judgment with no re-runnable observation is not evidence" —
    `core/protocol/invariants.py`). The human door asks for nothing: `record_reviewer_verdict`
    checks only that the reviewer's NAME differs from the executor's (`engine/__init__.py:588`),
    and records a PASS with an empty per-criterion list. A person alone therefore closes a root by
    typing any string that is not their own name — measured live: `reviewer=STAND-IN-not-a-real-
    reviewer` was accepted, the root went DONE/PASS, and every metric read 1.0.

    The canon's own answer is narrower than "a solo user must be blocked": §14.5's degenerate case
    says a graph with no seam has no IC guarantee at all, only making-explicit. What does NOT
    follow is that the same door should accept a verdict carrying ZERO observations while the
    machine door is refused one. That asymmetry is what this pins.
    """
    e = _engine()
    _root(e)
    T.create_task(e, "leaf", {"name": "leaf", "description": "part",
                              "criteria": [{"name": "k", "description": "d"}]}, "kirill",
                  parent_id="root")
    T.map_criterion(e, "root", "leaf", "c1")
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "leaf", "ACCEPT", "kirill")
    T.signal(e, "leaf", "DELIVER", "kirill", result="done")

    out = T.record_verdict(e, "leaf", "PASS", reviewer="STAND-IN-not-a-real-reviewer")
    assert not out.get("recorded"), f"a PASS was recorded with no observation at all: {out}"
    assert "OBSERVED" in out["error"] and "k" in out["error"], out["error"]

    # …and it is a demand for EVIDENCE, not a ban: a reviewer who says what they checked is recorded,
    # and what they said is what the log carries (§14.5 — with no seam, the explicit record IS the
    # guarantee; refusing the solo user outright would be a different claim than the canon makes).
    ok = T.record_verdict(e, "leaf", "PASS", reviewer="a-colleague",
                          observed={"k": "ran it on the sample and read the output"})
    rec = e.get_exec_verdict(T.TaskId("leaf"))
    e.stop()
    assert ok.get("recorded"), ok
    assert any("read the output" in str(x.get("evidence")) for x in rec["per_criterion"]), rec


def test_the_frontier_names_the_node_that_blocks_the_root():
    """`next_steps` is THE driver — the protocol says loop it until `complete=True`. When a child
    escalates the root can never complete, and the frontier must say WHICH node did it.

    Correcting my own first reading of this: the frontier was never silent — it already returned
    `stuck: true` with a directive. What it did not do is NAME the node, and "inspect node states"
    is true and useless to a caller in a loop. Measured live: two escalated leaves blocked a root
    while the driving agent hunted the cause through the raw graph and tried four recovery verbs
    against a terminal node. `available_actions` there is empty and every recovery verb refuses it
    (reopen takes DONE/ABANDONED only, CANCEL is not admissible from ESCALATED), so naming it — and
    saying the repair is re-decomposition, not a reopen — is the whole of what the caller needs."""
    e = _engine()
    _root(e)
    T.create_task(e, "leaf", {"name": "leaf", "description": "part",
                              "criteria": [{"name": "k", "description": "d"}]},
                  "agent", parent_id="root")
    T.map_criterion(e, "root", "leaf", "c1")
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "leaf", "ACCEPT", "agent")
    for i in range(6):
        if e.get_task("leaf").state.name == "ESCALATED":
            break
        T.signal(e, "leaf", "DELIVER", "agent", result=f"v{i}")
        T.signal(e, "leaf", "FAIL", "agent", failed_criteria=["k"])
    assert e.get_task("leaf").state.name == "ESCALATED", "precondition: the leaf escalated"

    steps = T.next_steps(e, "root")
    e.stop()
    assert steps.get("stuck"), "the frontier did not say the graph cannot move"
    assert "leaf" in (steps.get("blocked_by") or []), (
        f"the blocking node is not named: {steps}")
    assert "leaf" in steps["directive"] and "ESCALATED" in steps["directive"], (
        f"the directive does not say which node or what state: {steps['directive']}")


def test_a_delegated_node_is_visibly_executing_while_its_executor_works():
    """§14.2 gives ACCEPT one job: 'fixes the START of the obligation'. Under delegation the
    dispatcher spawns the executor and only wraps its finished report into signals
    (`delegate.py:294-296`), so ACCEPT and DELIVER land together at the END: the node sits in
    OFFERED for the whole working life and crosses EXECUTING in an instant. Measured live on three
    leaves — ACCEPT and DELIVER carried the IDENTICAL timestamp on every first delivery, and files
    were on disk 25-53 s before the graph admitted the node had started.

    This is what 'trust, but see' costs: no view, UI included, can ever show work in progress,
    because there is no interval in which the graph holds that fact.
    """
    e = _engine()
    _root(e)
    T.create_task(e, "leaf", {"name": "leaf", "description": "part",
                              "criteria": [{"name": "k", "description": "d"}]},
                  "worker", parent_id="root")
    T.map_criterion(e, "root", "leaf", "c1")
    T.signal(e, "root", "ACCEPT", "agent")

    with tempfile.TemporaryDirectory() as td:
        reg = AgentRegistry(path=str(Path(td) / "agents.json"))
        reg.register("worker", "llm-executor", workdir=td)
        seen: list[str] = []

        def runner(engine, task_id, executor_id, _agents):
            # what the graph says WHILE the executor is working
            seen.append(engine.get_task(task_id).state.name)
            T.signal(engine, str(task_id), "DELIVER", executor_id, result="done")

        d = Dispatcher(e, reg, runner=runner)
        d.dispatch_once()
        for _ in range(50):
            if seen:
                break
            time.sleep(0.1)
    e.stop()
    assert seen and seen[0] == "EXECUTING", (
        f"while the executor worked the graph showed {seen or ['nothing']}, not EXECUTING")


def test_the_time_a_node_entered_its_state_survives_a_restart():
    """`state_entered_at` is written on every transition and stored NOWHERE — it is re-created by
    `default_factory=datetime.now` at load. After a restart every node claims to have just entered
    its state, which (a) resets Inv-5's per-state age and (b) makes the rework gate's
    `child.state_entered_at <= task.state_entered_at` a comparison of near-equal values, so a
    freshly added child that PASSED reads as 'untouched'. Caught live by an agent it blocked."""
    # NOT a TemporaryDirectory: Windows refuses to unlink an open sqlite file, and the teardown
    # then fails a test whose assertion passed.
    db = str(Path(tempfile.mkdtemp()) / "r.db")
    e = _engine(SqliteStorage(db))
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    before = e.get_task("root").state_entered_at
    e.stop()

    e2 = _engine(SqliteStorage(db))
    after = e2.get_task("root").state_entered_at
    e2.stop()
    assert after == before, f"the clock restarted with the process: {before} → {after}"


def test_the_verdict_directive_is_read_against_the_current_state():
    """A `next` built from the verdict alone told agents to act on a graph that had moved.

    Measured live: `validate_result` on a node already DONE/PASS answered `signal('n','FAIL', …)`,
    and on another `signal('n','PASS')` — which the FSM refused outright. Under delegation this is
    the normal case, not an edge: the dispatcher's validator signs on delivery, so a caller reading
    the verdict afterwards is reading a record of something already settled. Obeying it drops
    accepted work.
    """
    e = _eng()
    _delivered_node(e)
    honest = _fenced({
        "verdict": "PASS",
        "per_criterion": [
            {"criterion": "flush", "verdict": "pass", "evidence": "ok",
             "behaviours": ["nail head is flush"],
             "probe": [{"command": "pytest -q", "expect": "passed"}]},
            {"criterion": "holds", "verdict": "pass", "evidence": "hung a 2kg frame",
             "behaviours": ["it holds a 2kg frame"],
             "probe": [{"command": "pytest -q", "expect": "passed"}]}],
        "failed_criteria": []})
    TL.validate_result(e, "n1", _llm=_ValidatorLLM(honest))
    T.signal(e, "n1", "PASS", "alice")                       # the ISSUER settles it
    assert e.get_task(T.TaskId("n1")).state.name == "DONE"

    again = TL.validate_result(e, "n1", _llm=_ValidatorLLM(honest))
    e.stop()
    assert "Nothing to sign" in again["next"] and "DONE" in again["next"], (
        f"the directive still instructs against a settled node: {again['next']}")
    assert "signal(" not in again["next"], "it still hands the caller a signal to send"


def test_a_wrong_predictability_names_the_three_categories():
    """`Predictability[p.upper()]` raised a bare KeyError whose entire message was the offending
    word: `'HIGH'`. Three agents reached for high/medium/low on the same day — the parameter is
    described as a "materialization probability", which points straight at that ladder — and each
    had to grep `core/types/enums.py` to continue. STD-2's scale is about the burden of proof for
    OMITTING a factor, not about magnitude, so the refusal has to say that much."""
    e = _engine()
    with pytest.raises(Exception) as ex:
        T.create_task(e, "n", {"name": "n", "description": "d",
                               "criteria": [{"name": "k", "description": "d"}],
                               "accepted_risks": [{"item": "vendor outage",
                                                   "predictability": "high",
                                                   "justification": "j",
                                                   "invalidation_condition": "i"}]}, "agent")
    e.stop()
    msg = str(ex.value)
    assert "ORDINARY" in msg and "STATISTICAL" in msg and "EXTRAORDINARY" in msg, (
        f"the refusal does not name the admissible values: {msg}")
    assert "§13.2" in msg, "it does not say where the scale comes from"


def test_a_bare_word_where_a_list_is_expected_is_one_item():
    """`failed_criteria=exact_duplicate_grouping` from the CLI arrived as a string, the engine
    iterated it, and the node came back failed on 24 one-letter "criteria". A person driving from
    the human door could not fail a node by its criterion name at all."""
    sig = inspect.signature(T.signal).parameters
    assert _wants_list(sig.get("failed_criteria")), "the parameter is not seen as a list"
    assert _as_list("exact_duplicate_grouping") == ["exact_duplicate_grouping"]
    assert _as_list("a, b") == ["a", "b"], "a comma-separated pair is two items"
    assert _as_list('["x","y"]') == ["x", "y"], "JSON must keep working for scripts"
    assert not _wants_list(sig.get("source")), "a plain string parameter must stay a string"


def test_delegating_a_child_does_not_stale_the_plan_verdict():
    """Delegation IS a re-ASSIGN, and a re-ASSIGN staled the parent's Level-2 verdict — so naming
    executors destroyed the very gate that had to pass before they could start.

    Measured 2026-08-20: a run spent 50 minutes and $2.71 in `review_decomposition → assign
    executors → verdict stale → review_decomposition`, and an executor that had already worked 157 seconds had its ACCEPT refused
    ("its parent's plan has no CURRENT Level-2 verdict") with the work discarded. The Level-2
    question is whether the mapped children's criteria carry the parent's; who executes a child is
    not part of that claim. Changing the CONTRACT still stales it — that half is the point.
    """
    e = _engine()
    _root(e)
    T.create_task(e, "leaf", {"name": "leaf", "description": "part",
                              "criteria": [{"name": "k", "description": "d"}]},
                  "agent", parent_id="root")
    T.map_criterion(e, "root", "leaf", "c1")

    root = e.get_task("root")
    root.verified = True                       # a Level-2 verdict has just been obtained
    e._graph.save_task(root)

    T.reassign(e, "leaf", "worker-7")          # delegation: same contract, new owner
    assert e.get_task("root").verified, "naming an executor threw away the plan verdict"

    T.edit_criteria(e, "leaf", [{"name": "k", "description": "MATERIALLY DIFFERENT"}], "agent")
    e.stop()
    assert not e.get_task("root").verified, "a real contract change must still stale the verdict"


def test_a_validator_in_the_same_workspace_beats_a_stranger_registered_earlier():
    """The roster is server-wide; the work is not.

    "The first registered llm-validator" meant the oldest entry on a shared server, so one run's
    node was judged by another run's validator pointed at another run's workspace. Measured twice on
    2026-08-20 — once by a judge whose `workdir` was an experiment's scratch directory. Naming
    `validator=` at registration still wins; this only fixes the DEFAULT.
    """
    reg = AgentRegistry(path=str(Path(tempfile.mkdtemp()) / "agents.json"))
    reg.register("old-val", "llm-validator", workdir="C:/somebody/elses/run")
    reg.register("mine-exec", "llm-executor", workdir="C:/my/project")
    reg.register("mine-val", "llm-validator", workdir="C:/my/project")

    assert reg.validator_for("mine-exec") == "mine-val", (
        f"a stranger's validator was chosen: {reg.validator_for('mine-exec')}")

    reg.register("pinned-exec", "llm-executor", workdir="C:/my/project", validator="old-val")
    assert reg.validator_for("pinned-exec") == "old-val", "an explicit override must still win"


def test_a_typo_in_a_parameter_name_is_refused_not_swallowed(capsys):
    """`key=value` whose key is not a parameter fell through as a POSITIONAL argument, so a typo
    silently filled the next slot with the literal text. Measured: three typos in a row, no warning
    of any kind, and no way to tell "no such parameter" from "the parameter did not work"."""
    run(["get_task", "assigne=kirill"])
    out = capsys.readouterr().out
    assert "has no parameter 'assigne'" in out, f"the typo was swallowed: {out}"
    assert "task_id" in out, "the refusal does not name the parameters that do exist"


def test_the_observation_log_carries_the_humans_own_signals():
    """`gfso log` and the UI panel read the pipeline log, which only ever carried AI-side progress.
    A person who drove a whole graph by hand saw two lines about a model and none of their own
    fourteen signals — the panel showed the one thing they did not do."""
    db = str(Path(tempfile.mkdtemp()) / "r.db")
    e = _engine(SqliteStorage(db))
    T.create_task(e, "root", {"name": "root", "description": "a goal",
                              "criteria": [{"name": "c1", "description": "the thing"}],
                              "accepted_risks": []}, "kirill")     # the human owns it
    T.signal(e, "root", "ACCEPT", "kirill")
    e.wait_idle()
    lines = [r["message"] for r in e.pipeline_log()]
    e.stop()
    assert any("ACCEPT" in m and "kirill" in m for m in lines), (
        f"the human's signal is absent from the observation log: {lines}")


def test_the_human_door_hands_out_the_ui_link_too(capsys):
    """The agent door attaches `ui` to its entry verbs and repeats it; the CLI/HTTP door never did,
    so the person the UI exists for was the one never told its address (measured: fourteen calls,
    no link anywhere). One list of verbs now serves both doors."""
    assert "use_project" in T.UI_LINK_VERBS and "create_task" in T.UI_LINK_VERBS
    assert "?project=demo" in T.ui_link("demo"), T.ui_link("demo")

    run(["create_task", "ui-probe-node",
         '{"name":"p","description":"d","criteria":[{"name":"k","description":"d"}]}',
         "agent", "project=ui-link-probe"])
    out = capsys.readouterr().out
    assert '"ui"' in out and "project=ui-link-probe" in out, f"no link on the human door: {out}"


def test_a_hand_resolved_block_puts_the_executor_back_in_the_queue(tmp_path):
    """RESOLVE_BLOCK sent BY HAND must re-queue the delegate, exactly as the auto-sweep does.

    Measured live 2026-08-20: `root.tests` was BLOCKED, the issuer sent RESOLVE_BLOCK, the transition
    was accepted (BLOCKED → EXECUTING) — and the node then sat in EXECUTING for THIRTEEN MINUTES with
    nothing inside it, not one `executor spawned` line; only a `reassign` moved it. The auto path
    re-queued because it dropped the node's dedup key itself (`producers DONE — RESOLVE_BLOCK
    (auto), executor re-queued`); the hand path goes through the FSM, where the key is untouched, and
    the round was already spent. A cleared block does not move the node's generation (no iteration,
    no reopen, no revision), so its key stays spent forever and the dispatcher never looks at it
    again — a graph that stops in a state which reads as running.

    Second half, same sweep: a node that blocks TWICE under one contract was auto-resolved only the
    first time — the sweep's guard key was `rb:<id>#<iteration>`, and the second episode found it
    spent. The guard exists to stop a double signal inside ONE blocked episode, so it is keyed on the
    episode, not on the round.
    """
    e = _engine()
    _root(e)
    T.create_task(e, "prod", {"description": "producer", "criteria": [{"name": "p", "description": "P"}]},
                  assignee="exec-1", parent_id="root")
    T.create_task(e, "cons", {"description": "consumer", "criteria": [{"name": "c", "description": "C"}]},
                  assignee="exec-1", parent_id="root")
    T.map_criterion(e, "root", "prod", "c1")
    T.map_criterion(e, "root", "cons", "c1")

    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(tmp_path))
    d = Dispatcher(e, agents, runner=lambda *a: None)
    d.dispatch_once()                                   # both children claim their first round
    e.wait_idle()

    T.signal(e, "cons", "BLOCK", "exec-1", reason="need prod", blocker_task_id="prod")
    e.wait_idle()
    assert e.get_state(TaskId("cons")).name == "BLOCKED"

    # The issuer clears it by hand, retracting the edge (`external` — it worked around the blocker).
    # A payload-free RESOLVE_BLOCK instead CONFIRMS the discovered Dep, and then the node waiting for
    # its producer is correct, not a defect — which is why this half uses the retracting form.
    T.signal(e, "cons", "RESOLVE_BLOCK", "agent", external=True)
    e.wait_idle()
    assert e.get_state(TaskId("cons")).name == "EXECUTING"
    assert "cons" in d.dispatch_once()                  # …and the delegate is back in the queue

    # A SECOND block episode under the same contract still auto-resolves once the producer is DONE.
    T.signal(e, "cons", "BLOCK", "exec-1", reason="need prod after all", blocker_task_id="prod")
    T.signal(e, "prod", "DELIVER", "exec-1", result="prod out")
    # a SEAM node needs a verdict for THIS delivery whoever signs it (§14.5): the issuer's signature
    # is not the validation — pinned by `test_a_seam_pass_needs_a_verdict_whoever_signs_it`
    T.record_verdict(e, "prod", "PASS", reviewer="agent", observed={"p": "ran it, printed the output"})
    T.signal(e, "prod", "PASS", "agent")
    e.wait_idle()
    assert e.get_state(TaskId("prod")).name == "DONE"
    started = d.dispatch_once()
    assert e.get_state(TaskId("cons")).name == "EXECUTING"
    assert "cons" in started
    e.stop()


def test_the_recorded_verdict_can_be_read_back():
    """There was no verb for "show me what the validator said".

    `validate_result` hands its report to whoever called it, once. Everyone else — the issuer who
    must sign PASS or FAIL, a person returning to the graph, a second agent picking the node up —
    had the verdict sitting in the database with no way to reach it, and `get_review` reads the
    Level-2 verdict on the PLAN, not on the work (measured live: an agent signed on its own summary
    of a report it could not re-read). `get_verdict` is that door: the per-criterion probes, what
    they printed, the judge and its tier, and — the part a summary always loses — which criteria
    were UNDECIDABLE rather than failed.
    """
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="built it")
    assert T.get_verdict(e, "root")["verdict"] is None            # nothing judged it yet
    assert "not been validated" in T.get_verdict(e, "root")["note"]

    e.record_exec_verdict(
        TaskId("root"), "FAIL", ["c1"], "val-1",
        per_criterion=[{"criterion": "c1", "verdict": "fail", "evidence": "ran it, printed 3",
                        "probe": "python -c 'print(2)'", "expect": "2"}])
    got = T.get_verdict(e, "root")
    assert got["verdict"] == "FAIL" and got["failed_criteria"] == ["c1"]
    assert got["validator"] == "val-1"
    assert got["per_criterion"][0]["probe"] == "python -c 'print(2)'"   # the probe, not a paraphrase
    assert got["undecidable"] == []
    assert T.get_verdict(e, "nope")["error"]
    e.stop()


def test_a_refused_reopen_says_which_gate_refused_it():
    """`reopen` refused with the wrong verb's name and a disjunction of three possible reasons.

    Measured live on the human door: the refusal came back as JSON quoted inside JSON with a 422,
    told the person to use `revise` (a different verb, which would not have worked either) and left
    them to guess which of consumed / exhausted / wrong-state was true of THEIR node. The two gates
    are cheap to ask directly, and each has a different recovery — a consumed terminal is locked for
    good and re-decomposition is the only way past it, while a spent counter is about this node
    alone."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "kid", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")

    assert "is OFFERED" in T.reopen(e, "kid", "agent")["error"]        # not finished at all

    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="wrote kid.py; ran its check, it printed OK", self_validation="PASS")
    T.signal(e, "kid", "PASS", "agent")
    assert e.get_state(TaskId("kid")).name == "DONE"
    assert T.reopen(e, "kid", "agent")["state"] == "OFFERED"           # first reopen is granted
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="done it again", self_validation="PASS")
    T.signal(e, "kid", "PASS", "agent")
    out = T.reopen(e, "kid", "agent")                                   # …the second is not
    assert out.get("max_reopens") == 1 and "spent its reopens" in out["error"]
    assert "revise" not in out["error"]                                 # never the wrong verb again
    e.stop()


def test_the_human_door_prints_prose_as_prose(capsys):
    """The CLI printed its directives as one long line of escaped newlines.

    Every directive this door hands out is prose, and JSON escapes it — so the field a person is
    meant to ACT on arrived as `\n`-separated text to decode by eye. A pipe still gets exact JSON
    (scripts and `jq` keep working); only an interactive terminal gets the rendering, which is why
    the renderer is tested directly here rather than through a fake tty."""
    text = driver._render({"task_id": "root", "state": "EXECUTING",
                           "directive": "EXECUTE leaf 'root':\ndo the work, then DELIVER.",
                           "steps": [{"task_id": "kid", "action": "accept"}]})
    assert chr(92) + "n" not in text                      # no escapes left for the reader to decode
    assert "    do the work, then DELIVER." in text   # the second line is a line
    assert "task_id: \"kid\"" in text                 # nested structure survives

    driver._emit({"a": 1})                        # not a tty under pytest → exact JSON
    assert json.loads(capsys.readouterr().out) == {"a": 1}


def test_a_person_can_ask_the_frontier_as_themselves():
    """`next_step` was written for the agent and pushed a person off their own work.

    The verb had no actor: it always asked as the standing agent identity, so a human driving their
    own graph from the CLI got `NOT YOURS (Del=kirill) — do NOT execute or signal for it` on every
    node of it, with the real instruction glued on after a `|` as "contract was: …". Measured live:
    the person read it literally and stopped at the first node. Identity stays transport-derived —
    `actor` is the human door naming itself, exactly as the UI has always done."""
    e = _engine()
    T.create_task(e, "mine", {"description": "the human's own node",
                              "criteria": [{"name": "c", "description": "C"}]}, assignee="kirill")

    as_agent = T.next_step(e)
    assert as_agent["mine"] is False and "NOT YOURS" in as_agent["directive"]

    as_person = T.next_step(e, actor="kirill")
    assert as_person["mine"] is True
    assert "NOT YOURS" not in as_person["directive"]
    assert as_person["directive"].startswith("TAKE 'mine'")      # the real instruction, not a suffix
    assert T.next_steps(e, actor="kirill")["steps"][0]["mine"] is True
    e.stop()


def test_a_spec_that_is_a_sentence_is_refused_in_the_verbs_own_terms():
    """`create_task(spec="build me a parser")` crashed inside the parser and came back over HTTP as
    a 500 with an empty body. The caller learnt nothing — least of all the thing that matters: a
    node is defined by its CRITERIA, and a bare sentence names none."""
    e = _engine()
    out = T.create_task(e, "x", spec="build me a parser")
    assert "criteria" in out["error"] and "not str" in out["error"]
    assert e.get_task(TaskId("x")) is None                        # …and nothing was created
    e.stop()


def test_a_frontier_held_by_the_dependency_order_names_the_pair():
    """When nothing is actionable because everything waits on a producer, say which waits on which.

    The frontier gates OFFERED and REWORKING on their producers now (handing out a leaf whose input
    does not exist yet can only end in a BLOCK), so "no steps" is reachable with every node simply
    waiting its turn. The old fallback said "check the nodes' Dep producers" and left the reader to
    work out which — the same defect the ESCALATED case had, in a second place. A producer that does
    not exist YET is the sharpest form of it: the consumer waits on a name, and the name is the
    whole answer."""
    e = _engine()
    _root(e)
    T.create_task(e, "cons", {"description": "consumer", "criteria": [{"name": "c", "description": "C"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "cons", "c1")
    T.add_dependency(e, "not-built-yet", "cons")
    T.signal(e, "root", "ACCEPT", "agent")

    out = e.next_steps()
    assert out.get("stuck") is True
    assert not out.get("steps")
    assert "'cons' waits on 'not-built-yet'" in out["directive"]
    assert "remove_dependency" in out["directive"]      # …and how to undo a mis-declared edge
    e.stop()


def test_no_available_action_says_why_not():
    """`available_actions` answered a person with a bare `[]`.

    Measured live: someone delivered their own root, asked what they could do with it, and got
    nothing — while `signal` on the same node explained in full that a node's own executor cannot
    sign its verdict (§14.5). The empty list was TRUE; the silence around it was the defect. It is
    also the ordinary SOLO case: one person is both executor and issuer, the role resolves as
    executor first, and every signal open in VALIDATING belongs to the issuer."""
    e = _engine()
    _root(e)                                   # root's Del is `agent`
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="did it")

    out = T.available_actions(e, "root", agent="agent")
    assert out["state"] == "VALIDATING"
    assert "PASS" not in out["actions"]                  # the seam gate would refuse it…
    assert "verifier ≠ executor" in out["gate"]          # …and it says so, with the way through
    assert "record_verdict" in out["gate"]

    # And the genuinely empty case still explains itself: a stranger holds no role on a child.
    T.create_task(e, "kid", {"description": "kid", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="someone", parent_id="root")
    none = T.available_actions(e, "kid", agent="a-stranger")
    assert none["actions"] == []
    assert "holds no role" in none["why_none"] and "someone" in none["why_none"]
    e.stop()


def test_the_rework_directive_does_not_ask_for_a_delivery_the_gate_refuses():
    """The step said "fix exactly what failed, then DELIVER again" where the engine refuses exactly
    that.

    When a parent criterion fails while every mapped child passes its own, contact refuted the
    DECOMPOSITION (§15.2 q_D, FM-1.d/f): the repair is a revision of the parent, and a re-DELIVER
    over an untouched subtree is rejected on arrival. The frontier did not know, so it kept issuing
    the rework directive. Measured 2026-08-20 on a measurement run: three full rounds against that
    wall — an executor call each, ~13 minutes — and the run ended `redelivery_refused` with the
    graph exactly where it had started. The engine already computes the repair; the directive now
    carries it, before the work rather than after."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "the covering child",
                             "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="the child's own criterion holds",
             self_validation="PASS")
    T.signal(e, "kid", "PASS", "agent")

    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="integrated")
    # the recorded verdict is what the gate reads — a hand FAIL writes none
    e.record_exec_verdict(TaskId("root"), "FAIL", ["c1"], "val-1",
                          per_criterion=[{"criterion": "c1", "verdict": "fail",
                                          "evidence": "ran the whole, c1 does not hold"}])
    T.signal(e, "root", "FAIL", "agent", failed_criteria=["c1"])
    assert e.get_state(TaskId("root")).name == "REWORKING"

    step = T.next_step(e)
    assert step["task_id"] == "root"
    assert step["action"] == "revise"                       # not "rework"
    assert "REFUSED" in step["directive"]
    assert "kid" in step["directive"]                       # …and which child covers the criterion
    assert "map_criterion" in step["directive"] or "covering child" in step["directive"]
    e.stop()


def test_the_affordance_surface_agrees_with_the_machine_in_both_directions():
    """`available_actions` said `[]` where `signal` said yes, and explained the refusal with a rule
    that does not apply.

    Measured 2026-08-20, a person driving their own graph: on their INTERNAL node (its Del is its
    parent's Del) the verb answered "no actions — a node's own executor cannot sign its verdict",
    while `signal PASS` on that same node was accepted, correctly — §14.5 D6 licenses exactly that
    self-verification, and the seam gate bites only on PUBLIC nodes. Two failures in one answer: the
    roles were resolved to the FIRST match (one person is routinely both executor and issuer), and
    the explanation named a rule the node is not under.

    The other direction has to hold too: on a PUBLIC node PASS must NOT be listed, because the gate
    would refuse it. An affordance surface that disagrees with the machine either way is worse than
    none — the person believes it."""
    e = _engine()
    T.create_task(e, "root", {
        "name": "root", "description": "a goal",
        "criteria": [{"name": "c1", "description": "the thing"}],
        "accepted_risks": [{"item": "fixture", "predictability": "extraordinary",
                            "justification": "accepted here", "invalidation_condition": "never"}]},
        "kirill")
    T.create_task(e, "kid", {"description": "internal child",
                             "criteria": [{"name": "k", "description": "K"}]},
                  assignee="kirill", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "kirill")
    T.signal(e, "kid", "DELIVER", "kirill", result="did it")

    # An internal node whose delivery said nothing about what was checked: PASS is NOT offered, and
    # the machine refuses it too (§14.5 D6 self-verification is through the check, and ⊥ is not a
    # pass, §11.2). The surface names the two ways to say what was checked.
    unchecked = T.available_actions(e, "kid", agent="kirill")
    assert "PASS" not in unchecked["actions"] and "self_validation" in unchecked["gate"]
    assert T.signal(e, "kid", "PASS", "kirill")["accepted"] is False

    T.record_verdict(e, "kid", "PASS", reviewer="kirill", observed={"k": "ran it, read the output"})
    internal = T.available_actions(e, "kid", agent="kirill")
    assert "PASS" in internal["actions"]                    # D6: an internal node self-verifies
    assert T.signal(e, "kid", "PASS", "kirill")["accepted"] is True     # …and the FSM agrees

    T.signal(e, "root", "ACCEPT", "kirill")
    T.signal(e, "root", "DELIVER", "kirill", result="integrated")
    public = T.available_actions(e, "root", agent="kirill")
    assert "PASS" not in public["actions"]                  # the seam gate would refuse it
    assert "FAIL" in public["actions"]                      # …refusing your own work needs no second
    assert "verifier ≠ executor" in public["gate"]
    assert T.signal(e, "root", "PASS", "kirill")["accepted"] is False
    e.stop()


def test_reopen_says_what_it_destroyed():
    """`reopen` on a finished root put it back to OFFERED and answered with a plain task dump.

    Measured 2026-08-20: a person ran it to SEE whether it would be refused, and found their
    DONE/PASS root reopened, one of its reopens spent, with nothing in the reply saying so — they
    read `"state": "OFFERED"` out of the middle of a node dump. Dropping the verdict is correct
    (§14.3: it is re-earned by fresh contact); saying nothing about it is not."""
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="did it")
    e.record_exec_verdict(TaskId("root"), "PASS", [], "val-1",
                          per_criterion=[{"criterion": "c1", "verdict": "pass",
                                          "evidence": "ran it", "probe": "x", "expect": "y"}])
    T.signal(e, "root", "PASS", "agent")
    assert e.get_state(TaskId("root")).name == "DONE"

    out = T.reopen(e, "root", "agent")
    assert out["state"] == "OFFERED"
    assert "was DONE" in out["reopened"] and "GONE" in out["reopened"]
    assert "1/1" in out["reopened"]                          # the reopen it spent, and of how many
    e.stop()


def test_a_signals_reply_names_the_node_its_next_step_is_about():
    """The step returned with a signal is often on ANOTHER node, and read as a claim about this one.

    Measured 2026-08-20: accepting one leaf answered with `EXECUTE leaf 'other-leaf'`, and the
    person read it as the tool losing track of what they had just done. It was the honest next move
    on the frontier — it simply never said whose."""
    e = _engine()
    _root(e)
    T.create_task(e, "a", {"description": "a", "criteria": [{"name": "x", "description": "X"}]},
                  assignee="agent", parent_id="root")
    T.create_task(e, "b", {"description": "b", "criteria": [{"name": "y", "description": "Y"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "a", "c1")
    T.map_criterion(e, "root", "b", "c1")
    T.add_dependency(e, "a", "b")                 # b waits for a
    out = T.signal(e, "b", "ACCEPT", "agent")
    if out.get("next"):
        assert ("'b'" in out["next"]) or ("not b" in out["next"])
    e.stop()


def test_an_observation_that_is_not_a_mapping_is_refused_not_crashed():
    """`record_verdict(observed="ran the tests, exit 0")` died with `'str' object has no attribute
    'items'`. The verb needs one line PER CRITERION — a single sentence settles none of them — and
    the help never said so. (The registry wrapper stopped it reaching the door as a traceback; that
    is the floor, not the answer.)"""
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="did it")
    out = T.record_verdict(e, "root", "PASS", reviewer="someone-else",
                           observed="ran the tests, exit 0")
    assert out["recorded"] is False
    assert "mapping from CRITERION NAME" in out["error"]
    assert "not str" in out["error"]
    e.stop()


def test_the_validate_directive_names_the_instrument_on_a_seam():
    """"Signal PASS if every criterion holds" was said to everyone — including the executor whose
    PASS the seam gate refuses (§14.5). A person following it literally walked into the refusal.
    On an INTERNAL node the sentence is true as it stands (D6: it self-verifies), so the addition is
    conditional, like the rule it reports."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "delegated child",
                             "criteria": [{"name": "k", "description": "K"}]},
                  assignee="someone-else", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "someone-else")
    T.signal(e, "kid", "DELIVER", "someone-else", result="did it")

    seam = next(s for s in T.next_steps(e)["steps"] if s["task_id"] == "kid")
    assert seam["action"] == "validate"
    assert "SEAM" in seam["directive"] and "validate_result" in seam["directive"]
    assert "someone-else" in seam["directive"]           # …and who cannot sign it
    e.stop()


def test_a_refused_revision_names_the_branch_that_refused_it():
    """The refusal printed the node's state and then asserted it was in three OTHER states.

    Verbatim, measured 2026-08-20: `revise rejected at re-ASSIGN (state=State.OFFERED): the node is
    in OVERDUE/CANCELLING/ESCALATED …, a quasi-terminal that is FINAL …, or the agent is not its
    issuer.` — a disjunction the reader has to solve, over a node that was in none of the states
    named, with a Python repr leaked into it. Each branch is one cheap question, and each has a
    different answer."""
    e = _engine()
    T.create_task(e, "root", {
        "name": "root", "description": "a goal",
        "criteria": [{"name": "c1", "description": "the thing"}],
        "accepted_risks": [{"item": "fixture", "predictability": "extraordinary",
                            "justification": "accepted here", "invalidation_condition": "never"}]},
        "owner")
    T.create_task(e, "kid", {"description": "kid", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")

    # Through the DOOR surface (the registry), where a refusal is data rather than an exception.
    out = TL.TOOLS["edit_criteria"](e, "kid", [{"name": "k", "description": "K, sharper"}],
                                    agent="stranger")
    err = out["error"]
    assert "'stranger' is not the issuer" in err and "'owner'" in err
    assert "OVERDUE/CANCELLING" not in err          # no disjunction to solve
    assert "State." not in err                      # …and no interpreter repr
    e.stop()


def test_the_frontier_says_what_is_waiting_even_when_something_else_can_run():
    """A dep-blocked node is absent from the steps — correct, and unreadable.

    Measured 2026-08-20 through the MCP door: two of three children were held by the dependency
    order and appeared NOWHERE in `next_steps`, so the caller saw one step and no reason for the
    rest of the graph's silence. `get_dependencies` had every edge and glue note; the frontier
    surfaced none of it. (The stuck branch names the pairs when NOTHING can run — this is the same
    fact when something can.)"""
    e = _engine()
    _root(e)
    for tid in ("a", "b", "c"):
        T.create_task(e, tid, {"description": tid, "criteria": [{"name": tid, "description": tid.upper()}]},
                      assignee="agent", parent_id="root")
        T.map_criterion(e, "root", tid, "c1")
    T.add_dependency(e, "a", "b", glue="b consumes a's output")
    T.add_dependency(e, "b", "c", glue="c consumes b's output")

    out = T.next_steps(e)
    shown = {s["task_id"] for s in out["steps"]}
    assert "b" not in shown and "c" not in shown         # held by the dependency order
    waiting = {w["task_id"]: w["waits_on"] for w in out["waiting"]}
    assert waiting["b"] == ["a"] and waiting["c"] == ["b"]
    e.stop()


def test_the_plan_review_says_whether_the_children_may_start(monkeypatch):
    """`gate_passed: true` was read as "the plan is good" while the checker was saying otherwise.

    The field is about Level 0/1 alone; execution is gated on the Level-2 findings being discharged
    as well (§13.4). Measured 2026-08-20: two review rounds came back `gate_passed: true` with
    `semantic_covered: false`, and the caller took the plan as passed. The question anyone actually
    has is whether the children may start, so the answer carries it — in words, not in a field name
    the reader has to already understand."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")      # the suite runs with the gate off by default
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "kid", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")

    # The checker itself is an LLM; what is under test is the REPLY the verb builds around it.

    @dataclass
    class _Out:
        gate_passed: bool = True
        semantic_covered: bool = False
        findings: tuple = ()

    monkeypatch.setattr(_rt, "llm_factory", lambda m: type("L", (), {"calls": [], "on_tick": None,
                                                                     "stage_hint": None})())
    monkeypatch.setattr(_runner, "review_decomposition", lambda *a, **k: _Out())
    out = TL.review_decomposition(e, "root")
    assert out["gate_passed"] is True and out["semantic_covered"] is False
    assert out["execution_admitted"] is False
    assert "may NOT start" in out["what_this_means"]
    e.stop()


def test_declaring_a_dependency_keeps_the_nodes_declared_scope():
    """Drawing a Dep edge silently emptied the consumer's `scope`.

    A dependency desugars to a re-author of the CONSUMER (§10: Dep is criteria-content), and that
    rebuild constructed the Spec positionally without the scope field — so the node's declared
    boundary, the thing that tells a user what the goal deliberately does NOT include (§13.1),
    vanished the moment anyone drew an edge into it. Nothing failed; the field just defaulted to
    empty. Found by the code-orthogonality sweep as D-23 and confirmed here."""
    e = _engine()
    _root(e)
    T.create_task(e, "prod", {"description": "producer", "criteria": [{"name": "p", "description": "P"}]},
                  assignee="agent", parent_id="root")
    T.create_task(e, "cons", {"description": "consumer",
                              "criteria": [{"name": "c", "description": "C"}],
                              "scope": ["no retries", "no caching"]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "prod", "c1")
    T.map_criterion(e, "root", "cons", "c1")
    assert T.get_task(e, "cons")["scope"] == ["no retries", "no caching"]

    T.add_dependency(e, "prod", "cons", glue="cons reads prod's output")
    assert T.get_task(e, "cons")["scope"] == ["no retries", "no caching"]
    T.remove_dependency(e, "prod", "cons")
    assert T.get_task(e, "cons")["scope"] == ["no retries", "no caching"]
    e.stop()


def test_a_step_that_is_not_yours_names_the_side_it_actually_waits_on():
    """The explanation named the wrong actor — the reader's own name.

    Measured 2026-08-21 by a person cleaning up a mistyped node: `available_actions` on a CANCELLING
    node told dana "dana is the issuer of k1, and in CANCELLING the open signals (CONFIRM_CANCEL)
    belong to the other side of the seam. Drive your own nodes; this one moves on dana's signal."
    The other side was `agent`. The sentence was built from the issuer regardless of which role the
    asker held, so an issuer was always told the node waits on themselves."""
    e = _engine()
    _root(e)                                        # root's Del is `agent`; issuer of a root is itself
    T.create_task(e, "kid", {"description": "kid", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "worker")

    # The issuer asking about a node whose turn belongs to its EXECUTOR. Its own signals (CANCEL,
    # ASSIGN) stay open — the sentence under test is the one about the side that has to move.
    out = T.available_actions(e, "kid", agent="agent")
    assert "DELIVER" not in out["actions"] and "BLOCK" not in out["actions"]
    T.signal(e, "kid", "BLOCK", "worker", reason="stuck")
    T.signal(e, "kid", "CANCEL", "agent", reason="dropping it")
    settle = T.available_actions(e, "kid", agent="agent")   # CANCELLING: only CONFIRM_CANCEL is open
    assert settle["actions"] == []
    assert "moves on worker's signal" in settle["why_none"]   # the other side, not the asker
    assert "moves on agent's signal" not in settle["why_none"]
    e.stop()


def test_a_cancellation_nobody_confirms_still_settles():
    """CANCELLING had no bottom with the age clock off, which is its default.

    §14.3 gives the state exactly two exits — the executor's CONFIRM_CANCEL, or the timeout — and
    Inv-5 requires every non-terminal state to be finite. The per-state age clock is opt-in and off
    by default, so a node whose executor never answers stayed in CANCELLING for good. Measured
    2026-08-21: a person cancelled a mistyped node assigned to nobody, could not confirm it (not
    their role), could not revise it ("a node in CANCELLING takes no revision"), and escaped only by
    signing as the executor — impersonation as the documented way out of a stuck graph.

    The handshake keeps its window; what it may not have is no bottom."""
    e = _engine()
    _root(e)
    T.create_task(e, "junk", {"description": "a mistyped node", "criteria": [{"name": "j", "description": "J"}]},
                  parent_id="root")                    # no assignee → `agent`, whom nobody drives
    T.signal(e, "junk", "CANCEL", "agent", reason="mistyped")
    assert e.get_state(TaskId("junk")).name == "CANCELLING"

    t = e.get_task(TaskId("junk"))                     # age it past the grace, as the clock would
    t.state_entered_at = datetime.now() - timedelta(seconds=_CANCELLING_GRACE_S + 1)
    e._graph.save_task(t)
    e.send_signal_sync(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("junk")))
    e.wait_idle()
    assert e.get_state(TaskId("junk")).name == "ABANDONED"
    e.stop()


def test_the_frontier_does_not_offer_a_validation_already_under_way():
    """"VALIDATE this" was said while an instrument was already validating it.

    Measured 2026-08-21 through the MCP door: a root sat in VALIDATING for four minutes with the
    registered validator working on it, while `next_step` kept telling the caller the verdict was
    theirs to produce. Obeying that either spends a second instrument on the same delivery — which
    the in-flight guard then refuses, after the model has been paid — or leaves the caller unable to
    tell silence from nobody coming. The claim is keyed by generation, so a run against an EARLIER
    delivery never masks a node that needs judging again."""
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="built it")
    assert any(s["action"] == "validate" for s in T.next_steps(e)["steps"])

    key = e.begin_validation(TaskId("root"))                  # an instrument takes it
    assert e.validation_in_flight(TaskId("root")) is True
    assert not any(s["action"] == "validate" for s in T.next_steps(e)["steps"])

    e.end_validation(key)
    assert any(s["action"] == "validate" for s in T.next_steps(e)["steps"])   # …and back on offer
    e.stop()


def test_the_metrics_say_what_they_are_about():
    """Two readers took a TRUE number for a defect, and both readings were reasonable.

    One drove the plan gate to convergence, honestly recording each criteria fix as `spec_defect`,
    and read `q_T = 0.0` as the system punishing obedience. It is not: §15.2 counts a criteria
    change for a spec defect against the contracts AS ISSUED — fixing bad criteria is exactly what
    lowers it, and the score is about the authoring, never about the fixer. Another read `q_V = 1.0`
    on a graph holding one unverified node as a false all-clear; q_V counts passes later reversed,
    and there had been none.

    Both numbers were right. A right number read as a wrong one is a defect of the surface, so the
    surface now carries what each one is about."""
    e = _engine()
    _root(e)
    out = T.metrics(e)
    assert "means" in out
    assert "AS ISSUED" in out["means"]["q_T"] and "never about the fixer" in out["means"]["q_T"]
    assert "NOT that everything was independently verified" in out["means"]["q_V"]
    assert set(out["means"]) <= set(out)                 # …one line per number actually reported
    e.stop()


def test_a_missing_payload_key_is_named_as_missing_not_as_unknown():
    """"unknown key 'task_id'" was said to someone who had never written `task_id`.

    A KeyError from inside a verb means the caller's payload is missing a key the verb needs — the
    opposite of passing one it does not know. Measured 2026-08-21: a person reverse-engineered three
    payload shapes by feeding wrong ones and reading which key the error named next, and called it
    ~40% of their session."""
    e = _engine()
    out = TL.TOOLS["decompose"](e, "root", [{"id": "kid"}])
    assert "missing a required key" in out["error"] and "task_id" in out["error"]
    assert "unknown key" not in out["error"]
    assert "--help" in out["error"]                      # …and where the shape is written down
    e.stop()


def test_the_ledger_keeps_the_label_the_caller_put_on_the_call():
    """`tag_last` existed so a caller could say which stage a particular call belonged to, and the
    ledger threw every one of them away — writing the argument `record_llm_usage` was given instead.

    Two sides of one accounting said different words for the same spend (`tag_last("validate_result")`
    against `record_llm_usage("validator", …)`), and a stage nobody passed as the argument — the
    undecided-obligations check, which shares the reviewer's client — never appeared in the ledger at
    all. That is how a check that HAD run looked like one that had not."""
    e = _engine()
    _root(e)

    class _LLM:
        def __init__(self):
            self.calls = [{"model": "sonnet", "output_tokens": 10, "cost_usd": 0.01},
                          {"model": "opus", "output_tokens": 20, "cost_usd": 0.02,
                           "stage": "its-own"}]

    e.record_llm_usage("the-argument", _LLM(), TaskId("root"))
    stages = sorted(r["stage"] for r in e._graph._storage.get_usage())
    assert stages == ["its-own", "the-argument"], stages
    e.stop()


def test_did_this_node_pass_has_one_owner_and_two_honest_answers():
    """The question was written in nine places and three spellings, and they disagreed.

    An enum compare, a `.name` string compare, a `getattr(…, "name", "")` compare — and some of
    them counted AUTO_PASS while others did not, which is a difference in MEANING carried by an
    accident of style. §21 records the timeout close apart from a pass precisely because it is not
    one, so there are two predicates and a caller says which question it is asking."""
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="did it")
    t = e.get_task(TaskId("root"))
    assert passed(t) is False and settled_positive(t) is False      # VALIDATING is neither

    t.state, t.done_reason = State.DONE, DoneReason.AUTO_PASS       # the timeout's close
    assert passed(t) is False                                       # …nobody gave that verdict
    assert settled_positive(t) is True                              # …and nobody refused it either

    t.done_reason = DoneReason.PASS
    assert passed(t) is True and settled_positive(t) is True
    assert passed(None) is False and settled_positive(None) is False
    e.stop()


def test_a_parent_with_an_escalated_child_does_not_buy_a_validator_run():
    """The pre-check and the gate spelled one rule two ways, and the looser one spent the money.

    `validate_result` refuses to run a model on a parent whose children have not settled — because
    the PASS gate would refuse the verdict anyway (Thm 1: the parent is the AND over its children).
    But it counted an ESCALATED child as settled, while the gate counts only a PASSED one. So a
    parent with an escalated child bought the full validator run and had the verdict refused after
    it was paid for: exactly the waste the pre-check exists to prevent, in the one case it let
    through."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "kid", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="tried")
    for _ in range(4):                                  # exhaust the rework bound → ESCALATED
        T.signal(e, "kid", "FAIL", "agent", failed_criteria=["k"])
        if e.get_state(TaskId("kid")).name == "ESCALATED":
            break
        T.signal(e, "kid", "DELIVER", "agent", result="again")
    assert e.get_state(TaskId("kid")).name == "ESCALATED"

    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="aggregated")
    out = TL.validate_result(e, "root")
    assert out["waiting_on"] == ["kid"]                  # refused BEFORE any model is spawned
    assert "would be refused at the gate" in out["error"]
    e.stop()


def test_a_revision_that_would_delete_the_contract_is_refused():
    """`revise` with a partial spec silently destroyed the rest of the node.

    Measured 2026-08-21 on the human door: passing `{description: …}` alone wiped the name, all five
    criteria, the ACCEPTED_RISKS, the scope and every criterion→child mapping — and the reply looked
    like an ordinary success. The loss surfaced minutes later as two failing checks, and the contract
    had to be reconstructed from scrollback. `edit_criteria` is documented as carrying the rest,
    which is exactly what lures you in.

    Whole means whole; what changes is that an omission which would DESTROY something is refused and
    named, instead of being performed silently."""
    e = _engine()
    _root(e)
    out = T.revise(e, "root", {"description": "a new description"}, agent="agent")
    assert out["would_delete"] == ["criteria", "ACCEPTED_RISKS"]
    assert "edit_criteria" in out["error"]
    assert e.get_task(TaskId("root")).spec.criteria                # …and nothing was lost

    ok = T.revise(e, "root", {"description": "a new description",
                              "criteria": [{"name": "c1", "description": "the thing, sharper"}],
                              "accepted_risks": [{"item": "fixture", "predictability": "extraordinary",
                                                  "justification": "accepted", "invalidation_condition": "never"}]},
                  agent="agent")
    assert ok["description"] == "a new description"                # …and meaning it works
    e.stop()


def test_an_internal_node_can_carry_its_own_recorded_verdict():
    """The two doors disagreed about one act, and the honest one was the closed one.

    `record_verdict` refused the executor's own verdict everywhere, while `signal PASS` accepted it
    on an INTERNAL node — correctly, since §14.5 D6 says such a node self-verifies and the FSM
    applies the seam gate to PUBLIC nodes only. Measured 2026-08-21 on the human door: a lone
    person's node reached DONE/PASS with no evidence anywhere, because the door that would have LEFT
    A RECORD was the one that said no.

    On a seam this still refuses. On an internal node the self-verdict is recorded WITH what was
    observed — which is exactly what the canon asks a self-verifying node to carry."""
    e = _engine()
    T.create_task(e, "root", {
        "name": "root", "description": "a goal",
        "criteria": [{"name": "c1", "description": "the thing"}],
        "accepted_risks": [{"item": "fixture", "predictability": "extraordinary",
                            "justification": "accepted here", "invalidation_condition": "never"}]},
        "sam")
    T.create_task(e, "kid", {"description": "internal child",
                             "criteria": [{"name": "k", "description": "K"}]},
                  assignee="sam", parent_id="root")            # same Del as its parent → INTERNAL
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "sam")
    T.signal(e, "kid", "DELIVER", "sam", result="wrote kid.py; ran its check, it printed OK", self_validation="PASS")

    rec = T.record_verdict(e, "kid", "PASS", reviewer="sam",
                           observed={"k": "ran it and read the output: K holds"})
    assert rec["recorded"] is True
    assert T.get_verdict(e, "kid")["per_criterion"][0]["evidence"].startswith("ran it")

    T.signal(e, "root", "ACCEPT", "sam")
    T.signal(e, "root", "DELIVER", "sam", result="integrated")
    seam = T.record_verdict(e, "root", "PASS", reviewer="sam", observed={"c1": "looked at it"})
    assert seam["recorded"] is False and "SEAM" in seam["error"]   # …the seam still refuses
    e.stop()


def test_a_mapping_call_says_what_it_bound_and_what_is_still_uncovered():
    """`map_criterion` echoed the whole parent, so eleven successive calls looked like eleven no-ops.

    Measured 2026-08-21 on the human door: the person could not tell a mapping that landed from one
    that did nothing, and fell back to reading `get_checks` to infer that the coverage check had
    moved. A verb whose whole job is to bind one criterion to one child should say which two."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "one"},
                                {"name": "c2", "description": "two"}], agent="agent")
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    out = T.map_criterion(e, "root", "kid", "c1")
    assert out["mapped"] == "root.c1 is covered by kid"
    assert out["covers_now"] == ["c1"] and out["still_uncovered"] == ["c2"]
    e.stop()


def test_the_graph_read_names_who_holds_each_node():
    """`get_graph` answered `assignee: null` for every node while `get_task` named the executor.

    Measured 2026-08-21: the bird's-eye view is where you look to see who is holding what, and it
    was the one view that would not say."""
    e = _engine()
    _root(e)
    node = [n for n in T.get_graph(e)["nodes"] if n["id"] == "root"][0]
    assert node["assignee"] == "agent"
    e.stop()


def test_the_review_hands_back_the_exact_string_a_dispute_takes():
    """The dispute key is not always the finding's own text, and no reader could see the difference.

    A conflict is disputed as "conflict: <a>, <b>" and an undecided obligation as
    "undecided: <obligation>" — neither prefix appeared in the findings list or in the help, so the
    first dispute of each kind was REJECTED and the error message was what taught the form
    (measured 2026-08-21). `get_review` now hands back the exact strings that are open."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    e._graph._storage.store_critique(TaskId("root"), json.dumps({
        "node_id": "root", "gate_passed": True, "semantic_covered": False,
        "criteria_verdicts": [{"criterion": "c1", "verdict": "insufficient",
                               "why": "the children do not carry it"}],
        "undecided_obligations": [{"obligation": "the package is importable", "why": "no criterion says so"}],
        "conflicts": [], "iteration": 0, "reopens": 0, "revisions": 0,
    }))
    root = e.get_task(TaskId("root")); root.verified = True; e._graph.save_task(root)
    keys = T.get_review(e, "root")["dispute_keys"]
    assert "undecided: the package is importable" in keys and "c1" in keys
    T.dispute_finding(e, "root", "undecided: the package is importable", why="the criterion c1 carries it")
    assert "undecided: the package is importable" not in T.get_review(e, "root")["dispute_keys"]
    e.stop()


def test_a_second_refused_report_says_not_to_run_it_again():
    """Three ⊥ in a row on one node cost four paid runs and nothing anywhere said that was abnormal.

    Measured 2026-08-21 on the human door: ~3 minutes and ~$0.5, each refusal naming a DIFFERENT
    undecided criterion, with no cap, no count and no line about how many attempts is reasonable. A
    ⊥ is not a transient error: the second one on a node is evidence about the CONTRACT, and the
    move at that point is a stronger model or your own verdict, not a third run."""
    e = _engine()
    _root(e)
    e.record_rejected_report(TaskId("root"), "criterion c1 was never decided")
    assert T.get_verdict(e, "root")["refused_report"]["refusals_on_this_node"] == 1
    e.record_rejected_report(TaskId("root"), "criterion c2 was never decided")
    rej = T.get_verdict(e, "root")["refused_report"]
    assert rej["refusals_on_this_node"] == 2
    assert rej["why_it_is_not_a_verdict"] == "criterion c2 was never decided"   # the last one stands
    e.stop()


def test_a_signal_reply_does_not_tell_you_to_do_someone_elses_work():
    """The `next` a signal hands back skipped the ownership filter the frontier applies.

    Measured on the MCP door 2026-08-21: signalling on the parent answered "EXECUTE leaf 'X' … do
    the actual work", where X's Del was a running executor — while `next_steps` on the same node
    said "NOT YOURS (Del=…) — do NOT execute or signal for it". The tester nearly duplicated an
    executor's work on it. Del is load-bearing in every surface that speaks about a node, or in
    none."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="someone-else", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    out = T.signal(e, "root", "ACCEPT", "agent")
    assert out["accepted"] is True
    assert "NOT YOURS (Del=someone-else)" in out["next"] and out["next_is_mine"] is False
    e.stop()


def test_the_frontier_does_not_offer_an_accept_the_plan_gate_refuses(monkeypatch):
    """`next_steps` listed a child as takeable, `mine: true`, while the engine refused its ACCEPT.

    Measured on the MCP door 2026-08-21: step 1 said the children could not start and step 2 told
    the caller to TAKE one; `signal(ACCEPT)` answered "cannot execute … its parent's plan has no
    CURRENT Level-2 verdict". The parent's plan step is the real one. The child is not silently
    dropped either — it moves to `waiting`, with what it waits on and what opens it."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    steps = T.next_steps(e)
    assert not [s for s in steps["steps"] if s["task_id"] == "kid" and s["action"] == "accept"]
    held = [w for w in steps.get("waiting", []) if w["task_id"] == "kid"]
    assert held and "review_decomposition('root')" in held[0]["opens_with"]
    # …and the engine agrees in the other direction: the offer would have been refused
    refused = T.signal(e, "kid", "ACCEPT", "agent")
    assert refused["accepted"] is False and "Level-2" in refused["error"]
    e.stop()


def test_the_verdict_record_names_the_validator_role_not_the_verb():
    """`register_agent` promised `will_be_judged_by: w5-val-1`, and nothing could confirm it after.

    Measured on the MCP door 2026-08-21: every verdict in the run read `validator:
    "validate_result"` — the verb — and the role's id appeared nowhere in the record or the log, so
    the tester could not tell whether their own instrument or an inherited stale one had judged.
    When a registered role drives the validation, its id is what goes on the record."""
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="did it")
    e.record_exec_verdict(TaskId("root"), "PASS", [], "w5-val-1",
                          per_criterion=[{"criterion": "c1", "verdict": "pass",
                                          "evidence": "ran it", "probe": "python -c ..."}],
                          generation=e.generation_of(TaskId("root")))
    assert T.get_verdict(e, "root")["validator"] == "w5-val-1"
    e.stop()


def test_auto_decompose_can_delegate_the_work_without_handing_over_the_plan():
    """Passing an executor's id as `assignee` handed them the whole graph, issuer rights included.

    Measured 2026-08-21: a caller who meant "delegate this to X" spent fifteen minutes locked out of
    their own plan — their `edit_criteria`, `map_criterion` and PASS on the children were refused,
    because the root's Del is the children's ISSUER (§14.1) — and got out by reassigning the root
    back. The parameter was right about what it does; what was missing was a name for the other
    thing, which is what a caller almost always means: the children go to them, the root stays
    with you."""
    e = _engine()
    spec = {"name": "goal", "root_criteria": [{"name": "c1", "description": "one"}],
            "accepted_risks": [{"item": "fixture", "predictability": "EXTRAORDINARY",
                                "justification": "accepted", "invalidation": "never"}],
            "subtasks": [{"id": "kid", "description": "the work",
                          "criteria": [{"name": "k", "description": "K"}]}],
            "mappings": [{"criterion": "c1", "child_id": "kid"}], "deps": []}
    build_graph_live(spec, "a goal", e, root_id="root", assignee="coordinator",
                     child_assignee="worker-1")
    assert e.get_task(TaskId("root")).assignee == "coordinator"     # …the plan stays with its author
    assert e.get_task(TaskId("root.kid")).assignee == "worker-1"    # …and the work is delegated
    e.stop()


def test_a_self_executed_leaf_cannot_close_on_nothing():
    """DELIVER → PASS eight seconds apart, DONE, and no evidence anywhere.

    Measured on the human door 2026-08-21, and it is the product's headline claim failing: a leaf
    whose Del equals its parent's went `DELIVER` then its own `PASS`, reached DONE, and `get_verdict`
    answered "no execution verdict recorded — it has not been validated" about that same node. The
    canon does say such a node self-verifies rather than being judged independently (§14.5 D6) — but
    it self-verifies THROUGH the check its DELIVER carries, and a verdict with nothing behind it is
    ⊥, not a pass (§11.2). Either door leaves a record; neither may be skipped."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "internal child",
                             "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="wrote the code")     # …and checked nothing
    refused = T.signal(e, "kid", "PASS", "agent")
    assert refused["accepted"] is False and "self-check" in refused["error"]
    assert e.get_state(TaskId("kid")).name == "VALIDATING"

    # …and the two ways to say it. From VALIDATING the node is past delivering, so the record is the
    # door: `record_verdict` with what was observed.
    T.record_verdict(e, "kid", "PASS", reviewer="agent", observed={"k": "ran it: K holds"})
    assert T.signal(e, "kid", "PASS", "agent")["accepted"] is True
    rec = T.get_verdict(e, "kid")
    assert rec["verdict"] == "PASS" and rec["validator"] == "agent"      # …and DONE has a record now
    assert "ran it" in rec["per_criterion"][0]["evidence"]

    # The other door: a DELIVER that carries its self-check needs nothing else afterwards.
    T.create_task(e, "kid2", {"description": "another internal child",
                              "criteria": [{"name": "k2", "description": "K2"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid2", "c1")
    T.signal(e, "kid2", "ACCEPT", "agent")
    T.signal(e, "kid2", "DELIVER", "agent", result="ran it: K2 holds", self_validation="PASS")
    assert T.signal(e, "kid2", "PASS", "agent")["accepted"] is True
    assert T.get_verdict(e, "kid2")["verdict"] == "PASS"
    e.stop()


def test_the_roster_verbs_are_on_every_door(tmp_path, monkeypatch):
    """`register_agent` lived on the AGENT door alone, so a person could not delegate at all.

    Measured on the human door 2026-08-21: the log repeatedly told the tester to `reassign` the node
    to a registered role, `gfso run` had no such verb, and `POST /api/run/register_agent` answered
    `unknown tool 'register_agent'`. Delegation, parallel execution and an independent validator were
    all unreachable from the CLI and the HTTP API — the whole half of the product that the graph is
    for. One roster, one implementation, every door."""
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    assert "register_agent" in TL.TOOLS and "list_agents" in TL.TOOLS
    e = _engine()
    out = TL.TOOLS["register_agent"](e, "w-exec-1", "llm-executor", workdir=str(tmp_path))
    assert out["will_be_judged_by"]                      # …and it says who would judge its work
    assert "w-exec-1" in TL.TOOLS["list_agents"](e)["agents"]
    e.stop()


def test_the_signal_that_finishes_a_node_still_answers_with_a_next():
    """The one signal in the protocol whose reply carried nothing.

    Measured on the human door 2026-08-21: `PASS` on a leaf came back as
    `{"accepted": true, "state": "DONE"}` — every other signal hands back the next step — and the
    person had to call `next_steps` to find out where they were. A node finishing is exactly the
    moment to say where the work goes on."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "internal child",
                             "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="ran it: K holds", self_validation="PASS")
    done = T.signal(e, "kid", "PASS", "agent")
    assert done["state"] == "DONE" and done["next"]          # …it says something
    assert "next_steps" in done["next"] or "root" in done["next"]
    e.stop()


def test_an_edit_that_sends_the_node_back_to_offered_says_so():
    """`edit_criteria` moved a node from EXECUTING to OFFERED with nothing in the reply about it.

    Measured on the human door 2026-08-21. Both effects are canon — a contract change is a REVISION
    and the executor consents again (Inv-1 §14.4), and the edit stales the plan's Level-2 verdict
    (§13.4) — and both were silent, so the node looked like it had moved on its own."""
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    out = T.edit_criteria(e, "root", [{"name": "c1", "description": "the thing, sharper"}],
                          agent="agent")
    assert out["state"] == "OFFERED"
    assert "EXECUTING → OFFERED" in out["state_changed"] and "ACCEPT" in out["state_changed"]
    assert "review_decomposition" in out["state_changed"]      # …it has children, so the plan stales
    e.stop()


def test_the_log_names_a_reopen_as_a_reopen():
    """The log said `ASSIGN … DONE → OFFERED` to a person who had called `reopen`.

    Protocol-correct — R′ is restoration through a re-ASSIGN under the standing contract, not a 13th
    signal (§14.3) — and it showed a verb they never used (measured 2026-08-21). The signal keeps its
    name; the line says what it was."""
    e = _engine()
    T.create_task(e, "solo", {"name": "solo", "description": "a goal",
                              "criteria": [{"name": "c1", "description": "the thing"}]}, "agent")
    T.signal(e, "solo", "ACCEPT", "agent")
    T.signal(e, "solo", "DELIVER", "agent", result="did it")
    # a ROOT is a seam, so its PASS needs a verdict from someone else (§14.5) — that is not what this
    # test is about, so an independent reviewer records one
    T.record_verdict(e, "solo", "PASS", reviewer="someone-else", observed={"c1": "ran it"})
    T.signal(e, "solo", "PASS", "agent")
    T.reopen(e, "solo", "agent")
    line = e._graph._storage.get_pipeline()[-1]["message"]
    assert "DONE → OFFERED" in line and "reopen" in line
    e.stop()


def test_a_parent_in_validating_whose_children_wait_on_its_plan_still_has_a_step(monkeypatch):
    """The frontier went EMPTY on a live run, for fifty-one minutes, and said nothing.

    Measured on the E3 arm 2026-08-21: the root was FAILed, repaired its plan from REWORKING (which
    stales the Level-2 verdict, §13.4) and re-DELIVERED, so it sat in VALIDATING with its children
    re-opened to OFFERED. The children could not start — the gate correctly holds them until the
    repaired plan is checked — the root's own validation is skipped while its children are unsettled
    (Thm 1), and the step that would have opened everything was written to fire only on an EXECUTING
    parent. Nothing was actionable anywhere in the graph. The plan step is about the PLAN, not about
    where the parent happens to stand."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "root", "DELIVER", "agent", result="aggregated")     # …parent now VALIDATING
    assert e.get_state(TaskId("root")).name == "VALIDATING"

    steps = T.next_steps(e)
    plan = [s for s in steps["steps"] if s["action"] == "review"]
    assert plan and plan[0]["task_id"] == "root"                      # …there IS a step
    assert "review_decomposition" in plan[0]["directive"]
    e.stop()


def test_the_plan_gate_holds_every_door_into_execution(monkeypatch):
    """A child got into EXECUTING by disputing its contract and being told no.

    The gate asked its question on ACCEPT alone, and CHALLENGE → REJECT_CHALLENGE lands the node in
    EXECUTING too (§14.3). Walking the protocol as a person would on 2026-08-21: the ACCEPT was
    refused for want of a current Level-2 verdict, and the node was already executing."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "CHALLENGE", "worker", justification="the criterion names a missing file")
    refused = T.signal(e, "kid", "REJECT_CHALLENGE", "agent",
                       justification="the file is created by the build")
    assert refused["accepted"] is False and "Level-2" in refused["error"]
    assert e.get_state(TaskId("kid")).name == "CHALLENGED"        # …not executing
    e.stop()


def test_the_step_for_a_blocked_node_belongs_to_the_side_that_can_send_it():
    """The frontier offered `resolve` to the BLOCKED node's own executor, who was then refused.

    RESOLVE_BLOCK is the ISSUER's signal (§14.3 role table) — "worker is not issuer for kid" is what
    the FSM said to whoever took the step. The affordance and the machine disagreeing about one act
    is the defect this surface exists to prevent (found by walking the protocol 2026-08-21)."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "BLOCK", "worker", reason="waiting on a decision")
    steps = T.next_steps(e, actor="worker")
    mine = [s for s in steps["steps"] if s["task_id"] == "kid"]
    assert mine and mine[0]["action"] == "resolve" and mine[0]["mine"] is False   # …not the worker's
    theirs = T.next_steps(e, actor="agent")
    assert [s for s in theirs["steps"] if s["task_id"] == "kid"][0]["mine"] is True
    e.stop()


def test_a_cancelled_child_says_which_parent_criteria_it_was_carrying():
    """The plan quietly became a different plan and every surface read clean.

    Walked by hand 2026-08-21: the only child covering a root criterion was cancelled, and with no
    children left the parent reads as a LEAF — so the coverage checks stop applying, `list_holes`
    comes back empty, and the graph looks exactly as it does when nothing happened. Structurally
    correct, and indistinguishable from "nothing changed" to the person who just cancelled. They are
    the one who has to decide what carries those criteria now."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "CANCEL", "agent", reason="the goal changed")
    gone = T.signal(e, "kid", "CONFIRM_CANCEL", "worker")
    assert gone["state"] == "ABANDONED"
    lost = gone["coverage_lost"]
    assert lost["parent_id"] == "root" and lost["criteria_it_carried"] == ["c1"]
    assert lost["children_left"] == [] and "leaf" in lost["what_now"]
    e.stop()


def test_both_kinds_of_waiting_explain_themselves_the_same_way():
    """One answer carried two waits and only one of them said anything.

    Measured on the human door 2026-08-21: the plan-gated entry carried `assignee`, `why` and
    `opens_with`; the dependency-gated ones carried a bare list of producer ids. Same list, same
    reader, same question — why is this node not moving."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "one"},
                                {"name": "c2", "description": "two"}], agent="agent")
    for kid, crit in (("parser", "p"), ("cli", "c")):
        T.create_task(e, kid, {"description": kid,
                               "criteria": [{"name": crit, "description": crit.upper()}]},
                      assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "parser", "c1")
    T.map_criterion(e, "root", "cli", "c2")
    T.add_dependency(e, "parser", "cli", glue="cli imports parse()")
    waiting = {w["task_id"]: w for w in T.next_steps(e).get("waiting", [])}
    assert waiting["cli"]["waits_on"] == ["parser"]
    assert waiting["cli"]["why"] and waiting["cli"]["opens_with"] and waiting["cli"]["assignee"]
    e.stop()


def test_a_refused_cycle_names_the_path_and_the_two_ways_out():
    """"would create a cycle" left the person guessing which end they had backwards.

    A Dep says the CONSUMER waits for its PRODUCER (§10), and the path that already exists is right
    there to be named — along with the honest second possibility: two nodes that really need each
    other are one node."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "one"},
                                {"name": "c2", "description": "two"}], agent="agent")
    for kid, crit in (("a", "p"), ("b", "q")):
        T.create_task(e, kid, {"description": kid,
                               "criteria": [{"name": crit, "description": crit.upper()}]},
                      assignee="agent", parent_id="root")
    T.add_dependency(e, "a", "b", glue="b uses a")
    out = TL.TOOLS["add_dependency"](e, "b", "a", glue="circular")
    assert out["refused"] is True
    assert "remove_dependency" in out["error"] and "one node" in out["error"]


def test_a_node_the_graph_cannot_move_past_is_named_even_when_something_else_is_actionable(
        monkeypatch):
    """An escalated child was invisible while a sibling step existed.

    The frontier names stranded nodes only when NOTHING is actionable — so a root with one escalated
    child and one takeable sibling reported the sibling and said nothing about the child that had
    already made the root impossible (walked by hand 2026-08-21). A parent's PASS is the AND over its
    children: one settled FAIL below and nothing above it can ever complete. And on the node itself,
    "the state is terminal" sent a person hunting through four verbs for one that was not refused —
    each terminal has its own recovery in §14.3, so the answer names it."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")   # this walk is about the terminal, not the plan gate
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "worker")
    for _ in range(4):     # the default rework budget, spent to its end (§14.3)
        T.signal(e, "kid", "DELIVER", "worker", result="attempt")
        T.signal(e, "kid", "FAIL", "agent", failed_criteria=["k"])
    assert e.get_state(TaskId("kid")).name == "ESCALATED"

    out = T.next_steps(e)
    assert out.get("steps")                                        # …something else IS actionable
    stranded = {s["task_id"]: s for s in out.get("stranded", [])}
    assert "kid" in stranded and "re-decompose" in stranded["kid"]["opens_with"]

    acts = T.available_actions(e, "kid", agent="agent")
    assert acts["actions"] == [] and "re-decompose" in acts["recovery"]
    e.stop()


def test_a_read_does_not_bring_a_project_into_existence(tmp_path, monkeypatch):
    """`get_task root project=beta` answered "unknown task" and left a beta.db behind.

    Measured 2026-08-21 on the CLI: every typo in a `project=` became a permanent project, and the
    installation had accumulated 315 of them — one per mistake, indistinguishable in the list from
    the ones that hold real work. Only the verbs that AUTHOR create; everything else says there is no
    such project and names the two that do."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    reg = ProjectRegistry()
    with pytest.raises(KeyError):
        reg.engine("beta", create=False)
    assert not list(tmp_path.glob("beta.db"))               # …and nothing was left behind
    reg.engine("beta")                                      # the authoring path still creates
    assert reg.engine("beta", create=False) is not None      # …and afterwards a read finds it


def test_a_locked_terminal_does_not_offer_the_signal_that_would_reopen_it():
    """`reopen` explained itself perfectly and the affordance list beside it still said ASSIGN.

    A terminal node lists ASSIGN because §14.3's R′ edge rides on it — but that edge is double-gated
    (not consumed, reopens left), and with the gate shut the FSM answers "its transition GUARD
    refused it — the precondition does not hold", which names nothing. Walked by hand 2026-08-21 on a
    consumed child. One owner for the gate's reason: the verb refuses in those words and the
    affordance surface removes the act and gives the same sentence."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="wrote kid.py; ran its check, it printed OK", self_validation="PASS")
    T.signal(e, "kid", "PASS", "agent")
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="integrated")      # …the parent stakes on it

    assert T.reopen(e, "kid", "agent")["consumed"] is True
    acts = T.available_actions(e, "kid", agent="agent")
    assert "ASSIGN" not in acts["actions"] and "CONSUMED" in acts["gate"]
    assert acts["why_none"] == acts["gate"]              # …and not a general lecture about roles
    e.stop()


def test_the_risk_register_answers_with_what_it_recorded():
    """A classified risk came back as its bare sentence.

    CHECK-4 demands a predictability verdict per factor, with a justification and an invalidation
    condition (§13.1) — and the node projection carries each risk's `item` alone, so a person who
    typed all four fields got the first one back and no way to see whether the rest landed (walked by
    hand 2026-08-21)."""
    e = _engine()
    _root(e)
    out = T.edit_accepted_risks(e, "root", [
        {"item": "the terminal may not support colour", "predictability": "STATISTICAL",
         "justification": "common, and the fallback is plain text",
         "invalidation_condition": "a user reports garbled output"}], agent="agent")
    rec = out["accepted_risks_recorded"][0]
    assert rec["predictability"] == "STATISTICAL" and rec["justification"].startswith("common")
    assert rec["invalidation_condition"] == "a user reports garbled output"
    e.stop()


def test_a_dispute_key_that_differs_only_in_mangled_punctuation_still_lands(monkeypatch):
    """The refusal said the key was not open and listed that same key as open.

    A finding's text carries the em-dashes a model writes; copied back through a console with a
    legacy code page it becomes a string that looks identical and is not ("—" arrives as "вЂ”").
    Measured on the human door 2026-08-21: twenty minutes lost, and the caller was locked out of the
    only exit from the plan gate, because `dispute_finding` is what discharges a finding you believe
    is wrong. One unambiguous near-match is accepted; the answer says which key it landed on."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    e._graph._storage.store_critique(TaskId("root"), json.dumps({
        "node_id": "root", "gate_passed": True, "semantic_covered": False,
        "criteria_verdicts": [], "conflicts": [],
        "undecided_obligations": [{"obligation": "the package is importable — as a module",
                                   "why": "no criterion says so"}],
        "iteration": 0, "reopens": 0, "revisions": 0}))
    root = e.get_task(TaskId("root")); root.verified = True; e._graph.save_task(root)

    mangled = "undecided: the package is importable вЂ” as a module"
    out = T.dispute_finding(e, "root", mangled, why="the criterion c1 carries it")
    assert out["disputed"] == "undecided: the package is importable — as a module"
    assert T.get_review(e, "root")["dispute_keys"] == []
    e.stop()


def test_a_parent_delivered_too_early_is_not_offered_and_not_hidden():
    """Offered by one surface, accepted by the FSM, then invisible for an hour.

    Measured on the human door 2026-08-21: `available_actions` listed DELIVER on a root whose five
    children were unfinished; the FSM took it; no validator could judge it (a verdict would be
    refused at the gate, Thm 1); its own PASS was refused; and the node then appeared in NEITHER
    `steps` nor `waiting` — the frontier that exists to say what to do never mentioned it again. The
    signal stays admissible where §14.3 admits it; what stops is recommending it, and what starts is
    saying where the node went."""
    e = _engine()
    _root(e)
    T.signal(e, "root", "ACCEPT", "agent")
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")

    acts = T.available_actions(e, "root", agent="agent")
    assert "DELIVER" not in acts["actions"] and "Thm 1" in acts["gate"]

    T.signal(e, "root", "DELIVER", "agent", result="probe")           # …still admissible by hand
    assert e.get_state(TaskId("root")).name == "VALIDATING"
    out = T.next_steps(e)
    assert not [s for s in out["steps"] if s["task_id"] == "root"]
    parked = [w for w in out.get("waiting", []) if w["task_id"] == "root"]
    assert parked and "kid" in parked[0]["waits_on"] and "Thm 1" in parked[0]["why"]
    e.stop()


def test_what_the_run_cost_is_answerable_from_the_graphs_own_doors():
    """The money lived on one door, so delegated execution cost was invisible.

    Measured on the agent door 2026-08-21, in the tester's own words: "for a system whose whole pitch
    is that the graph is the truth, the graph cannot tell me what the run cost". `/api/usage` existed;
    an agent or a person at the shell had no verb for it, and `metrics` speaks only of quality."""
    e = _engine()
    _root(e)
    e.record_llm_usage("executor", [{"cost_usd": 0.25, "output_tokens": 100, "duration_ms": 900,
                                     "model": "sonnet"}], TaskId("root"))
    out = TL.TOOLS["usage"](e)
    assert out["cost_usd"] == 0.25 and out["by_stage"]["executor"]["calls"] == 1
    assert out["costed_calls"] == 1        # …"free" and "not reported" stay distinguishable
    assert TL.TOOLS["usage"](e, detail=True)["calls_detail"][0]["stage"] == "executor"
    e.stop()


def test_the_roster_verbs_do_not_ask_for_a_project_that_has_no_graph_yet(tmp_path, monkeypatch):
    """A newcomer's first command was refused for a project that did not exist yet.

    `register_agent`'s own help says the roster is one server-wide fact — and the call was gated on a
    graph existing, so registering a role before authoring anything answered "no such project"
    (measured on a cold start 2026-08-21). The roster verbs are about the roster."""
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    assert {"register_agent", "list_agents"} == set(T.PROJECTLESS_VERBS)
    e = _engine()
    out = TL.TOOLS["register_agent"](e, "w-val-1", "llm-validator", workdir=str(tmp_path))
    assert out["registered"] == "w-val-1"
    e.stop()


def test_an_edit_does_not_demand_a_name_the_door_never_asked_for():
    """"edit_criteria needs agent" — and nothing anywhere names a default.

    There is no `whoami` on this door; a person guessed a name that happened to work, and had no
    second guess if it had not (measured on a cold start 2026-08-21). The caller's standing identity
    is what the agent door has always used, and naming yourself still overrides it."""
    e = _engine()
    _root(e)
    out = T.edit_criteria(e, "root", [{"name": "c1", "description": "the thing, sharper"}])
    assert out["criteria"][0]["description"] == "the thing, sharper"
    risks = T.edit_accepted_risks(e, "root", [{"item": "x", "predictability": "EXTRAORDINARY",
                                               "justification": "j", "invalidation_condition": "i"}])
    assert risks["accepted_risks_recorded"][0]["predictability"] == "EXTRAORDINARY"
    e.stop()


def test_a_cancelled_childs_coverage_mapping_does_not_lock_the_parent_forever():
    """One refusal in the whole run had no way forward, and it was this one.

    Cancel a child and the parent still points at it, so CHECK-1 reads an invalid mapping — correctly,
    and permanently: measured on the human door 2026-08-21, `map_criterion` could only add a second
    mapping beside the dead one, `edit_criteria` did not touch it, `revise` and `create_task` refused,
    and the person escaped by guessing an undocumented rebuild that wiped every other mapping in the
    graph. A re-author is the node's own act on its own coverage, so it prunes what no longer exists —
    the criterion becomes an honest CHECK-1 hole a person can actually close."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "one"},
                                {"name": "c2", "description": "two"}])
    for kid, crit in (("kid", "c1"), ("other", "c2")):
        T.create_task(e, kid, {"description": kid, "criteria": [{"name": "k", "description": "K"}]},
                      assignee="worker", parent_id="root")
        T.map_criterion(e, "root", kid, crit)
    T.signal(e, "kid", "CANCEL", "agent", reason="the goal changed")
    T.signal(e, "kid", "CONFIRM_CANCEL", "worker")
    assert [h for h in T.list_holes(e, "root")["holes"] if "invalid mappings" in h["details"]]   # …a hole

    T.edit_criteria(e, "root", [{"name": "c1", "description": "one, restated"},
                                {"name": "c2", "description": "two"}])
    assert not [h for h in T.list_holes(e, "root")["holes"]
                if "invalid mappings" in h["details"]]              # …and a re-author clears it
    assert [h for h in T.list_holes(e, "root")["holes"] if "uncovered criteria" in h["details"]]
    e.stop()


def test_a_mapping_call_does_not_throw_away_a_delivery_in_flight():
    """A coverage repair re-opened a node mid-validation and said nothing.

    `covers` is contract content, so binding it REVISES the child (Inv-1, §14.4) and sends it back to
    OFFERED for consent. Measured on the human door 2026-08-21: a node in VALIDATING with a validator
    running was re-opened by a `map_criterion` call, the delivery and the validation were both lost,
    and the reply was a coverage summary that mentioned no state change at all."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "one"},
                                {"name": "c2", "description": "two"}])
    for kid, crit in (("kid", "c1"), ("other", "c2")):
        T.create_task(e, kid, {"description": kid, "criteria": [{"name": "k", "description": "K"}]},
                      assignee="worker", parent_id="root")
        T.map_criterion(e, "root", kid, crit)
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="did it")       # …now VALIDATING

    refused = T.map_criterion(e, "root", "kid", "c2")
    assert refused["refused"] is True and refused["child_state"] == "VALIDATING"
    assert e.get_state(TaskId("kid")).name == "VALIDATING"          # …nothing was thrown away
    e.stop()


def test_a_cancel_says_what_is_at_stake_before_the_point_of_no_return():
    """The coverage loss was reported one step too late.

    CANCELLING admits only CONFIRM_CANCEL, so by the time the answer named what the node was
    carrying, the decision had been made (measured on the human door 2026-08-21: "that is exactly the
    information I needed one step earlier")."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    out = T.signal(e, "kid", "CANCEL", "agent", reason="the goal changed")
    assert out["state"] == "CANCELLING"
    assert out["coverage_at_stake"]["criteria_it_carried"] == ["c1"]
    e.stop()


def test_editing_a_finished_node_says_the_verdict_is_gone():
    """An edit dropped a PASSED child back to OFFERED and the reply read like any other edit.

    Editing the contract of a settled node is a reopen with a new one (R′, §14.3): it spends a reopen
    and the verdict is gone, re-earned by fresh contact. `reopen` says exactly that; the edit that
    does the same thing said only that the executor consents again. Measured on the human door
    2026-08-21: recovering cost a plan review, seven disputes, a re-delivery and two validations."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="ran it: K holds", self_validation="PASS")
    T.signal(e, "kid", "PASS", "agent")
    assert e.get_state(TaskId("kid")).name == "DONE"

    out = T.edit_criteria(e, "kid", [{"name": "k", "description": "K, sharper"}])
    assert out["state"] == "OFFERED"
    assert "verdict is GONE" in out["state_changed"] and "reopen is spent" in out["state_changed"]
    e.stop()


def test_a_self_report_is_recorded_once_not_copied_per_criterion():
    """Eight criteria, eight identical blobs, in the field a reader trusts for per-criterion evidence.

    A DELIVER carrying `self_validation` records the executor's own verdict (§14.5 D6) — and it was
    written into a slot for EVERY criterion, so the record read like a per-criterion attestation
    nobody had made. The tester's words on 2026-08-22: "that is the shape of a false green". What is
    true is what is stored: one self-report, marked as self-reported, with the delivery beside it."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "internal child",
                             "criteria": [{"name": "k1", "description": "K1"},
                                          {"name": "k2", "description": "K2"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="built it; ran the suite", self_validation="PASS")
    rec = T.get_verdict(e, "kid")
    assert len(rec["per_criterion"]) == 1                      # …one report, not one per criterion
    assert "SELF-REPORTED by agent" in rec["per_criterion"][0]["evidence"]
    assert rec["delivered"] == "built it; ran the suite"
    e.stop()


def test_assign_on_a_finished_node_says_it_is_a_reopen():
    """The only action offered on a finished root was the word ASSIGN, and taking it destroyed DONE.

    Measured on the human door 2026-08-22: a self-assignment that changed nothing — `agent` → `agent`
    — reverted DONE to OFFERED, dropped the verdict and spent a reopen; recovering cost a re-delivery
    and a $0.60 opus re-validation. The signal IS legitimately open there (R′ rides on it, §14.3);
    what its name does not say is what it does to a node that has finished."""
    e = _engine()
    T.create_task(e, "solo", {"name": "solo", "description": "a goal",
                              "criteria": [{"name": "c1", "description": "the thing"}]}, "agent")
    T.signal(e, "solo", "ACCEPT", "agent")
    T.signal(e, "solo", "DELIVER", "agent", result="did it")
    T.record_verdict(e, "solo", "PASS", reviewer="someone-else", observed={"c1": "ran it"})
    T.signal(e, "solo", "PASS", "agent")
    assert e.get_state(TaskId("solo")).name == "DONE"

    acts = T.available_actions(e, "solo", agent="agent")
    assert "ASSIGN" in acts["actions"]                       # …still open, and now explained
    assert "REOPEN" in acts["gate"] and "verdict is GONE" in acts["gate"]
    e.stop()


def test_a_rebuild_leaves_one_criterion_per_name():
    """A refine left two criteria with one name and contradictory text.

    Measured on the human door 2026-08-22: `dep__D1_scaffold` appeared twice on a child — one naming
    a package the decomposer had invented and since renamed away, one naming the real one. Worse than
    confusing: `record_verdict` takes its evidence as a mapping keyed BY CRITERION NAME, so two
    criteria of one name cannot be judged separately at all — one silently overwrites the other."""
    e = _engine()
    spec = {"name": "goal", "root_criteria": [{"name": "c1", "description": "one"}],
            "accepted_risks": [{"item": "fixture", "predictability": "EXTRAORDINARY",
                                "justification": "accepted", "invalidation": "never"}],
            "subtasks": [{"id": "kid", "description": "the work",
                          "criteria": [{"name": "k", "description": "the first statement"},
                                       {"name": "k", "description": "the restatement"}]}],
            "mappings": [{"criterion": "c1", "child_id": "kid"}], "deps": []}
    build_graph_live(spec, "a goal", e, root_id="root", assignee="agent")
    crits = e.get_task(TaskId("root.kid")).spec.criteria
    assert [c.name for c in crits] == ["k"]                  # …one per name
    assert crits[0].description == "the restatement"          # …the current statement wins
    e.stop()


def test_the_directive_lists_every_criterion_the_record_will_demand():
    """A person judged exactly the criteria the directive printed and was refused for missing one.

    V is the conjunction over ALL criteria (§10) — seams included, since a `dep__` criterion IS a
    criterion of the consumer — and `record_verdict` enforces exactly that. The directive listed only
    the node's own, dropping the seams, so following the instruction was an error (measured on the
    human door 2026-08-22, two round-trips)."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "one"},
                                {"name": "c2", "description": "two"}])
    T.create_task(e, "producer", {"description": "producer",
                                  "criteria": [{"name": "k", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.create_task(e, "consumer", {"description": "consumer",
                                  "criteria": [{"name": "own", "description": "its own work"},
                                               {"name": "dep__producer", "depends_on": "producer",
                                                "description": "uses the real producer output"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "producer", "c1")
    T.map_criterion(e, "root", "consumer", "c2")
    T.signal(e, "producer", "ACCEPT", "agent")
    T.signal(e, "producer", "DELIVER", "agent", result="made it", self_validation="PASS")
    T.signal(e, "producer", "PASS", "agent")
    T.signal(e, "consumer", "ACCEPT", "agent")
    T.signal(e, "consumer", "DELIVER", "agent", result="used it")
    step = [s for s in T.next_steps(e)["steps"] if s["task_id"] == "consumer"]
    assert step and set(step[0]["criteria"]) == {"own", "dep__producer"}
    e.stop()


def test_a_blocked_node_says_what_it_is_blocked_on():
    """"Clear the blocker, then RESOLVE_BLOCK" — which blocker?

    Measured on the human door 2026-08-22: `get_task` carried no reason and no blocker,
    `available_actions` listed the signal, and the only full text lived in a discovered Dep edge
    nobody had been pointed at (the log had it, truncated mid-word). BLOCK records both — the reason
    the executor gave and the nodes it named (§14.2) — so the node's own answer carries them."""
    e = _engine()
    _root(e)
    T.create_task(e, "producer", {"description": "producer",
                                  "criteria": [{"name": "p", "description": "P"}]},
                  assignee="worker", parent_id="root")
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.map_criterion(e, "root", "producer", "c1")
    assert T.signal(e, "kid", "ACCEPT", "worker")["accepted"] is True
    T.signal(e, "kid", "BLOCK", "worker", reason="needs the parser that producer is writing",
             blocker_task_ids=["producer"])
    out = T.get_task(e, "kid")
    assert out["state"] == "BLOCKED"
    assert out["blocked_by"]["waits_on"] == ["producer"]
    assert "parser" in out["blocked_by"]["reason"] and "producer" in out["blocked_by"]["what_now"]
    e.stop()


def test_a_block_is_not_cleared_by_saying_so():
    """RESOLVE_BLOCK returned a node to EXECUTING with nothing able to run, for eleven minutes.

    The node waited on producers that had not passed; the dispatcher then correctly refused to spawn
    against an input that does not exist, and the frontier filed the node under `waiting` while its
    own state said EXECUTING (measured on the human door 2026-08-22). "EXECUTING" has to mean someone
    can execute."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "one"},
                                {"name": "c2", "description": "two"}])
    for kid, crit in (("producer", "c1"), ("consumer", "c2")):
        T.create_task(e, kid, {"description": kid, "criteria": [{"name": "k", "description": "K"}]},
                      assignee="worker", parent_id="root")
        T.map_criterion(e, "root", kid, crit)
    T.add_dependency(e, "producer", "consumer", glue="consumer uses it")
    T.signal(e, "consumer", "ACCEPT", "worker")
    T.signal(e, "consumer", "BLOCK", "worker", reason="needs the producer",
             blocker_task_ids=["producer"])

    refused = T.signal(e, "consumer", "RESOLVE_BLOCK", "agent", reason="I think it is fine now")
    assert refused["accepted"] is False and "producer" in refused["error"]
    assert e.get_state(TaskId("consumer")).name == "BLOCKED"

    T.signal(e, "producer", "ACCEPT", "worker")
    T.signal(e, "producer", "DELIVER", "worker", result="made it")
    T.record_verdict(e, "producer", "PASS", reviewer="agent", observed={"k": "ran it"})
    T.signal(e, "producer", "PASS", "agent")                  # the issuer signs across the seam
    assert e.get_state(TaskId("producer")).name == "DONE"
    assert T.signal(e, "consumer", "RESOLVE_BLOCK", "agent")["accepted"] is True
    e.stop()


def test_the_step_asks_for_a_signature_when_the_judging_is_done():
    """The frontier told an issuer to VALIDATE a node whose verdict was already on the record.

    A validator had reported on THIS delivery; the directive still read "check the deliverable
    against criteria …", so the reader either paid for a second judgement over the same artifact or
    waited for a report that had already arrived (measured on the human door 2026-08-22). What is
    owed at that point is the signal, not the judging."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="made it")

    step = [s for s in T.next_steps(e)["steps"] if s["task_id"] == "kid"][0]
    assert "VALIDATE" in step["directive"]

    T.record_verdict(e, "kid", "FAIL", reviewer="agent", failed_criteria=["k"],
                     observed={"k": "ran it, wrong output"})
    step = [s for s in T.next_steps(e)["steps"] if s["task_id"] == "kid"][0]
    assert "SIGN THE VERDICT" in step["directive"], step["directive"]
    assert "FAIL on k" in step["directive"] and "get_verdict" in step["directive"]
    assert "check the deliverable" not in step["directive"]
    e.stop()


def test_the_delivery_says_what_becomes_of_it():
    """DELIVER answered with a directive about another node, and said nothing about the delivery.

    The executor could not tell whether a verdict was already coming or whether it had to ask for
    one: one tester waited, another ran a second instrument over the artifact an in-flight validator
    was already judging (measured on the human door 2026-08-22)."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "worker")
    out = T.signal(e, "kid", "DELIVER", "worker", result="made it")
    assert "validate_result kid" in out["awaiting_verdict"]

    T.record_verdict(e, "kid", "PASS", reviewer="agent", observed={"k": "ran it"})
    T.signal(e, "kid", "FAIL", "agent", failed_criteria=["k"])       # back to REWORKING…
    out = T.signal(e, "kid", "DELIVER", "worker", result="fixed it")  # …and delivered again
    assert "waits for a verdict" in out["awaiting_verdict"]
    e.stop()


def test_a_verb_that_lives_on_another_door_says_which_one(capsys):
    """`gfso run delete_project` answered "unknown command" with thirty others to search.

    The project-lifecycle verbs are on the MCP door (they say WHICH graph a session stands in, not
    anything about a graph), and a person who learnt them there was told the verb does not exist —
    measured on the human door 2026-08-22."""
    assert _cli_run(["delete_project", "x"]) == 1
    said = json.loads(capsys.readouterr().out)
    assert "gfso projects --delete" in said["use"] and "unknown command" not in said["error"]

    assert _cli_run(["no_such_verb"]) == 1                       # …and a real unknown is still unknown
    assert "unknown command" in json.loads(capsys.readouterr().out)["error"]


def test_the_validator_escalation_can_be_refused(monkeypatch):
    """A ⊥ report escalated the retry to opus with nothing able to stop it.

    Registering a validator as `sonnet` bought an opus run on every node that refused once, and no
    door said so or offered a way to say no (measured on the human door 2026-08-22). The escalation
    stays the default — it is what closes a coverage gap — but it is now a term of the installation
    (`GFSO_VALIDATOR_RETRY_MODEL`, `off` for the node's own tier)."""
    monkeypatch.delenv("GFSO_VALIDATOR_RETRY_MODEL", raising=False)
    assert validator_retry_model() == "opus"
    monkeypatch.setenv("GFSO_VALIDATOR_RETRY_MODEL", "sonnet")
    assert validator_retry_model() == "sonnet"
    for said_no in ("off", "none", ""):
        monkeypatch.setenv("GFSO_VALIDATOR_RETRY_MODEL", said_no)
        assert validator_retry_model() is None


def test_a_root_validate_step_is_not_everybodys():
    """`next_steps` told every caller that a root's VALIDATE step was theirs.

    Ownership of that step was read off the PARENT alone, and a root has none — so the surface said
    `mine: true` to whoever asked while the gate refuses any source but the root's own assignee
    (§14.1: the issuer forms the task and validates the result). Measured on the human door
    2026-08-22."""
    e = _engine()
    _root(e)                                    # …a root whose Del is `agent`
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="built it")
    step = [s for s in T.next_steps(e, actor="somebody-else")["steps"]
            if s["task_id"] == "root"][0]
    assert step["mine"] is False, step
    mine = [s for s in T.next_steps(e, actor="agent")["steps"] if s["task_id"] == "root"][0]
    assert mine["mine"] is True
    e.stop()


def test_a_seam_pass_needs_a_verdict_whoever_signs_it():
    """The seam gate fired only against a SELF-stamp, so an ISSUER could pass on nothing.

    §14.5 asks for an independent verdict on THIS delivery at a seam — the condition read
    `source == task.assignee` as well, so the identity check passed vacuously whenever the signer
    was not the executor and nothing else was consulted. Measured on the agent door 2026-08-22 (a
    delegated child PASSed while a STALE FAIL stood on it and its validator was still running), then
    reproduced with nothing on the record at all: accepted, DONE. A false PASS reachable in one call
    from the ordinary door, in the product whose claim is that nothing completes by impression."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")           # …Del ≠ its parent's ⟹ a SEAM
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="built it")

    blocked = T.signal(e, "kid", "PASS", "agent")                # the ISSUER, not the executor
    assert blocked["accepted"] is False and "independent verdict" in blocked["error"]
    assert "record_verdict" in blocked["error"] and "validate_result" in blocked["error"]
    assert e.get_state(TaskId("kid")).name == "VALIDATING"

    # …and a STALE verdict does not open it either (the wave's own case)
    T.record_verdict(e, "kid", "FAIL", reviewer="agent", failed_criteria=["k"],
                     observed={"k": "ran it, wrong output"})
    T.signal(e, "kid", "FAIL", "agent", failed_criteria=["k"])   # → REWORKING, verdict now stale
    T.signal(e, "kid", "DELIVER", "worker", result="fixed it")
    stale = T.signal(e, "kid", "PASS", "agent")
    assert stale["accepted"] is False and "STALE" in stale["error"]

    # A person judging by hand is still free to: the record is what is required, not the instrument.
    T.record_verdict(e, "kid", "PASS", reviewer="agent", observed={"k": "re-ran it, printed 42"})
    assert T.signal(e, "kid", "PASS", "agent")["accepted"] is True
    assert e.get_state(TaskId("kid")).name == "DONE"
    e.stop()


def test_a_criterion_that_keeps_failing_is_named_to_both_sides():
    """An executor obeyed "fix exactly what failed" five times against a criterion nobody could meet.

    `unicode_and_surrogate_policy` asked for a round-trip of lone surrogates — unsatisfiable with
    strict UTF-8. The executor re-delivered five times, then reached for CHALLENGE (refused: after
    ACCEPT the contract is disputed through BLOCK, §14.3) and the run stalled with the artifact
    scoring 0.972 on the held-out suite. Nothing on either door said "this has failed three rounds
    running", though the count is a fact in the log."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "imp", "description": "I"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "worker")
    for _ in range(3):
        T.signal(e, "kid", "DELIVER", "worker", result="tried again")
        T.record_verdict(e, "kid", "FAIL", reviewer="agent", failed_criteria=["imp"],
                         observed={"imp": "ran it; the criterion cannot hold"})
        T.signal(e, "kid", "FAIL", "agent", failed_criteria=["imp"])
    assert e.stuck_on(TaskId("kid")) == ["imp"]

    step = [s for s in T.next_steps(e)["steps"] if s["task_id"] == "kid"][0]
    assert "failed 3 rounds running" in step["directive"], step["directive"]
    assert "BLOCK(" in step["directive"]                      # …the route, named where they are

    # …and the same fact reaches the ISSUER, whose repair is the contract
    T.signal(e, "kid", "DELIVER", "worker", result="tried once more")
    step = [s for s in T.next_steps(e)["steps"] if s["task_id"] == "kid"][0]
    assert "the repair is the CONTRACT" in step["directive"] and "edit_criteria" in step["directive"]
    e.stop()


def test_a_refused_signal_says_where_the_intent_goes():
    """The FSM's own refusal was logged with no reason at all, and the executor was left guessing.

    Measured 2026-08-22: the rejected CHALLENGE row in a live run carried `error: None`, so the log —
    the one thing that carries provenance (Inv-7) — recorded that something was refused and not a
    word about what is admissible instead."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="v1")
    T.record_verdict(e, "kid", "FAIL", reviewer="agent", failed_criteria=["k"], observed={"k": "no"})
    T.signal(e, "kid", "FAIL", "agent", failed_criteria=["k"])

    out = T.signal(e, "kid", "CHALLENGE", "worker", reason="the criterion cannot hold")
    assert out["accepted"] is False
    assert "BLOCK(" in out["error"] and "§14.3" in out["error"]
    logged = [a for a in e.audit_log(TaskId("kid")) if a.rejected][-1]
    assert logged.error and "BLOCK(" in logged.error, "the refusal reached the log without its reason"
    e.stop()


def test_a_working_graph_is_not_reported_stuck():
    """`stuck: true` on a healthy graph, four times in one run, prescribing `remove_dependency`.

    A node being judged and an executor working are the graph doing exactly what it should — the
    frontier had no name for that state, so an empty step list read as a dead graph and the
    directive blamed the dependency order, whose remedy on a correct edge is destructive. Measured
    on both doors 2026-08-22; on the human door it cost ten minutes of polling while the verdict was
    already on the record."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "root", "ACCEPT", "agent")           # the parent is in hand, its child is the work
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="built it")
    e.begin_validation(TaskId("kid"))                # …an instrument is judging it right now

    out = T.next_steps(e)
    assert out.get("stuck") is not True, out.get("directive")
    assert out["steps"] == [] and any(w["task_id"] == "kid" for w in out.get("in_flight", []))
    assert "remove_dependency" not in str(out.get("directive"))
    assert "is being judged" in str(out["directive"]) and "arrive by themselves" in str(out["directive"])
    e.stop()


def test_one_delivery_leaves_one_self_report():
    """The same self-check was written twice, and which record survived depended on the route.

    A DELIVER carrying `self_validation` is recorded by the engine as ONE self-report — one word
    about the delivery as a whole, which is what the executor actually said. The dispatcher's
    internal-node path then re-recorded it as a row per criterion, a stronger claim than the
    evidence, over the truthful one (register 2026-08-22, finding 3)."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf",
                             "criteria": [{"name": "a", "description": "A"},
                                          {"name": "b", "description": "B"}]},
                  assignee="agent", parent_id="root")          # same Del as its parent ⟹ INTERNAL
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="built it", self_validation="PASS")

    rec = T.get_verdict(e, "kid")
    assert rec["verdict"] == "PASS"
    assert len(rec["per_criterion"]) == 1, "one word said once, not fanned out over the criteria"
    assert "SELF-REPORTED" in rec["per_criterion"][0]["evidence"]
    e.stop()


def test_replacing_a_contract_says_what_it_replaced():
    """Five authored criteria vanished in one call whose reply said nothing about them.

    `edit_criteria` REPLACES the set — that is its contract — but the answer showed only the new
    one, and with no history verb the caller had to invent the old criteria back from the node's
    description (measured on the human door 2026-08-22)."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "a", "description": "A"},
                                {"name": "b", "description": "B"}], agent="agent")
    out = T.edit_criteria(e, "root", [{"name": "a", "description": "A"}], agent="agent")
    assert out["removed"] == ["b: B"] and "REPLACES the set" in out["removed_note"]

    same = T.edit_criteria(e, "root", [{"name": "a", "description": "A (sharpened)"}], agent="agent")
    assert "removed" not in same, "editing a description is not a removal"
    e.stop()


def test_the_node_says_whether_its_children_may_start():
    """`plan_verified: true` was read as "the plan is admitted" while the checker said otherwise.

    The two facts are different — the structural levels being current, and the Level-2 findings
    being discharged — and only `review_decomposition`'s own payload carried the disclaimer. A
    reader had `plan_verified: true` from `get_task` and `execution_admitted: false` from the review
    in the same minute (measured on the human door 2026-08-22)."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    e._graph._storage.store_critique(TaskId("root"), json.dumps({
        "node_id": "root", "gate_passed": True, "semantic_covered": False,
        "criteria_verdicts": [{"criterion": "c1", "verdict": "insufficient",
                               "why": "the child does not carry it"}],
        "conflicts": [], "undecided_obligations": [], "iteration": 0, "reopens": 0, "revisions": 0,
    }))
    root = e.get_task(TaskId("root")); root.verified = True; e._graph.save_task(root)
    out = T.get_task(e, "root")
    assert out["execution_admitted"] is False and out["l2_open"] == ["c1"]
    e.stop()


def test_the_graph_says_who_it_waits_for_on_a_validating_node():
    """Ten minutes of polling on a node whose verdict was already on the record.

    "Being judged" and "judged, waiting for your signature" are one state name and opposite
    situations — one costs nothing to wait out, the other waits for YOU — and only `next_steps` told
    them apart (measured on the human door 2026-08-22)."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="built it")

    node = {n["id"]: n for n in T.get_graph(e)["nodes"]}["kid"]
    assert node["awaiting"] == "verdict"                     # …nobody is judging it yet

    _key = e.begin_validation(TaskId("kid"))          # …the key is what releases it
    assert {n["id"]: n for n in T.get_graph(e)["nodes"]}["kid"]["awaiting"] == "validator"
    e.end_validation(_key)
    T.record_verdict(e, "kid", "PASS", reviewer="agent", observed={"k": "ran it"})
    assert {n["id"]: n for n in T.get_graph(e)["nodes"]}["kid"]["awaiting"] == "issuer"
    e.stop()


def test_a_pass_on_an_undelivered_node_is_refused_for_the_real_reason():
    """The seam rule answered before the FSM had said the signal moves nothing here.

    A PASS on a node that had delivered NOTHING came back "no independent verdict is recorded …
    `record_verdict(…)` and then signal PASS" — advice that records a verdict about work which does
    not exist, or fails again for the reason nobody named. Measured on the human door 2026-08-22, on
    a rule I had added the same day; outside VALIDATING the FSM's own answer is the true one."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")

    early = T.signal(e, "kid", "PASS", "agent")               # nothing delivered yet
    assert early["accepted"] is False
    assert "not admitted by state OFFERED" in early["error"] and early["refused_by"] == "state"
    assert "record_verdict" not in early["error"]             # …no invitation to a false close

    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="built it")
    late = T.signal(e, "kid", "PASS", "agent")                # …and there the seam rule speaks
    assert late["accepted"] is False and late["refused_by"] == "rule"
    assert "independent verdict" in late["error"]
    e.stop()


def test_a_block_that_closes_a_cycle_says_the_plan_is_now_red():
    """A BLOCK recorded a dependency that closed a cycle, froze six children, and said nothing.

    The edge is recorded on purpose — the cycle IS the finding (§14.2: the world's verdict on the
    declared seams) — but the consequence was silent: the parent's plan fails the Syntactic level,
    no child is admitted to execution, and the only surface that said so was the frontier. The same
    shape had been REFUSED by hand minutes earlier through `add_dependency` (measured on the human
    door 2026-08-22)."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "one"},
                                {"name": "c2", "description": "two"}])
    for kid, crit in (("a", "c1"), ("b", "c2")):
        T.create_task(e, kid, {"description": kid, "criteria": [{"name": "k", "description": "K"}]},
                      assignee="worker", parent_id="root")
        T.map_criterion(e, "root", kid, crit)
    T.add_dependency(e, "a", "b", glue="b consumes a")        # …declared: b waits for a
    T.signal(e, "b", "ACCEPT", "worker")
    T.signal(e, "a", "ACCEPT", "worker")
    out = T.signal(e, "a", "BLOCK", "worker", reason="I need b first", blocker_task_ids=["b"])

    assert out["accepted"] is True                            # the edge is recorded, not refused
    assert "closes a cycle" in out["plan_now_red"]
    assert "remove_dependency" in out["plan_now_red"]
    e.stop()


def test_removing_a_dependency_says_it_staled_the_plan():
    """`{"ok": true}` — and then the graph would not move.

    Removing an edge re-authors the consumer (the glue criterion goes with it), which is a revision
    and stales the plan's Level-2 verdict: the children stop being admitted until the check runs
    again. Canon, and silent (measured on the human door 2026-08-22)."""
    e = _engine()
    _root(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "one"},
                                {"name": "c2", "description": "two"}])
    for kid, crit in (("a", "c1"), ("b", "c2")):
        T.create_task(e, kid, {"description": kid, "criteria": [{"name": "k", "description": "K"}]},
                      assignee="worker", parent_id="root")
        T.map_criterion(e, "root", kid, crit)
    T.add_dependency(e, "a", "b", glue="b consumes a")
    root = e.get_task(TaskId("root")); root.verified = True; e._graph.save_task(root)

    out = T.remove_dependency(e, "a", "b")
    assert out["removed"] == "a -> b"
    assert "review_decomposition" in out["plan_verdict_staled"]
    e.stop()


def test_the_state_answers_before_the_identity_does():
    """A signal the state does not admit came back "X is not issuer for Y".

    The caller fixed their identity, sent it again, and only then learnt the state had been wrong all
    along — one wasted call to find the real reason (measured on the human door 2026-08-22). Where a
    signal moves nothing whoever sends it, that is the honest answer, and it carries the route."""
    e = _engine()
    _root(e)
    T.create_task(e, "kid", {"description": "leaf", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="worker", parent_id="root")
    T.map_criterion(e, "root", "kid", "c1")

    wrong_both = T.signal(e, "kid", "RESOLVE_BLOCK", "worker")   # not the issuer AND not admitted
    assert "not admitted by state OFFERED" in wrong_both["error"]
    assert "is not issuer" not in wrong_both["error"]
    e.stop()
