"""No verb at a door holds its call for a model run: a validator ran minutes inside `validate_result`, and its caller's
console was held until its client moved the call to the background (the author, 2026-11-24). The run goes on in the
server (`tools_llm._off_the_call`); the call answers what it started and where its result lands."""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future

import pytest

import gfso.decompose as _dec
import gfso.decompose.loop as _loop
import gfso.decompose.planning as _pl
import gfso.delegate as _dl
import gfso.runtime as _rt
import gfso.workspaces as _ws
import gfso.llm as _llm
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import TaskId
from gfso.engine import CheckRunning
from gfso.mcp import server as M
from gfso.runtime import ProjectRegistry
from tests.test_every_verb_answers import _GOOD, _engine, _seeded
from tests.test_validate_result import _delivered_node, _eng, _fenced
from tests.support import REGISTER, a_repository, criterion
import tests.test_a_seam_he_issues_is_checked_by_the_validator as S
import tests.test_the_go_only_adds_to_the_plan as Go


#: the threads a model was called on
CALLED: list = []
#: a model call waits on it: cleared, a model runs until it is set again
OPEN = threading.Event()
OPEN.set()


class _Model(StubLLM):
    """A model that notes the thread each call is made on and answers nothing."""
    runs_agents = True

    def __init__(self, *a, **k):
        self.calls = []

    def complete(self, prompt, context=""):
        CALLED.append(threading.get_ident())
        assert OPEN.wait(30)
        return ""

    def complete_structured(self, system, user, schema):
        CALLED.append(threading.get_ident())
        assert OPEN.wait(30)
        return {}

    def run_agent(self, *a, **k):
        CALLED.append(threading.get_ident())
        return ""


@pytest.fixture(autouse=True)
def _models(monkeypatch):
    """Every way a verb reaches a model gives it `_Model`: the provider switch and each module's name for it."""
    made = lambda *a, **k: _Model()
    monkeypatch.setattr(_llm, "provider_for", made)
    for m in (TL, _dec, _loop, _pl, _dl, _rt, _ws):
        monkeypatch.setattr(m, "llm_factory", made)
    monkeypatch.setattr(_dec, "_default_llm", made)
    CALLED.clear()


def _reaching_its_validator():
    """A delivered node `validate_result` runs its validator on: the registry's own row stops at a refusal."""
    e = _eng()
    _delivered_node(e)
    return e, {"task_id": "n1", "_llm": _Model()}


#: The verbs that still run their model in their call, and why. Listed, one must still run in its call — one moved off
#: it leaves this list.
STILL_IN_THE_CALL: dict = {}


@pytest.mark.parametrize("verb", sorted(_GOOD) + ["validate_result (delivered)"])
def test_no_verb_runs_a_model_in_its_call(verb):
    """Every verb of the registry, as every door binds it: a model it calls is called in a thread of the server's,
    never in the call (red on a `validate_result` that ran its validator in the call). It bites where a verb's row in
    `test_every_verb_answers._GOOD` reaches its model: that row is a verb's plausible call, and a verb whose model
    stands behind a state no row reaches is given a row of its own here (`validate_result (delivered)`). A verb in
    `STILL_IN_THE_CALL` is held to the reverse, so the list says what is true."""
    if verb == "validate_result (delivered)":
        e, args = _reaching_its_validator()
        verb = "validate_result"
    else:
        e, args = _seeded(_engine()), _GOOD[verb]
        e._llm = _Model()
    try:
        TL.TOOLS[verb](e, **args)
    finally:
        e.stop()
    if verb in STILL_IN_THE_CALL:
        assert threading.get_ident() in CALLED, f"`{verb}` no longer runs its model in its call: take it off the list"
    else:
        assert threading.get_ident() not in CALLED, f"`{verb}` ran a model inside its call"


class _SlowValidator:
    """A validator that runs until released, then reports a PASS over the node's two criteria."""

    def __init__(self, fails=False, entries=None):
        self.go, self.started, self.fails, self.calls = threading.Event(), threading.Event(), fails, []
        self.entries = entries

    def run_agent(self, *a, **k):
        self.started.set()
        assert self.go.wait(30)
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        if self.fails:
            raise RuntimeError("the validator's process died")
        return _fenced({"verdict": "PASS", "failed_criteria": [], "per_criterion": self.entries or [
            {"criterion": c, "verdict": "pass", "evidence": "ran it", "behaviours": ["the criterion holds"],
             "probe": [{"command": f"check {c}", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}
            for c in ("flush", "holds")]})

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _settled(pred, s=20.0):
    end = time.monotonic() + s
    while not pred():
        assert time.monotonic() < end, "did not settle"
        time.sleep(0.02)


def test_validate_result_answers_before_its_validator_ends(monkeypatch):
    """The call answers in its bound with what it started; the node is in flight on the frontier, a second call starts
    no other, and the verdict lands on the record when the validator ends, the claim let go."""
    monkeypatch.setattr(TL, "ANSWER_WITHIN_SECONDS", 2.0)    # …past the thread reaching its validator, under a loaded suite too
    e = _eng()
    _delivered_node(e)
    slow = _SlowValidator()
    try:
        t0 = time.monotonic()
        out = TL.TOOLS["validate_result"](e, "n1", _llm=slow)
        assert time.monotonic() - t0 < 5 and slow.started.is_set() and not slow.go.is_set()
        assert out["running"] == "validate_result" and out["task_id"] == "n1" and "verdict" not in out, out
        assert "get_verdict('n1')" in out["say"] and "checks" in out, out
        assert e.claims.validation_in_flight(TaskId("n1"))
        assert any(w["task_id"] == "n1" for w in T.next_steps(e).get("in_flight") or ()), T.next_steps(e)
        again = TL.TOOLS["validate_result"](e, "n1", _llm=_SlowValidator())
        assert again.get("inflight") and again["verdict"] is None, again
        slow.go.set()
        _settled(lambda: (e.current_exec_verdict(TaskId("n1")) or {}).get("verdict") == "PASS")
        _settled(lambda: not e.claims.validation_in_flight(TaskId("n1")))
    finally:
        slow.go.set()
        e.stop()


def test_a_validation_that_dies_past_its_call_leaves_no_node_being_checked(monkeypatch):
    """A run that raises after its call answered frees its claim and says so on the feed: nothing reads as checked."""
    monkeypatch.setattr(TL, "ANSWER_WITHIN_SECONDS", 0.3)
    e = _eng()
    _delivered_node(e)
    said = []
    e.on_info(lambda source, msg: said.append(msg))
    slow = _SlowValidator(fails=True)
    try:
        assert TL.TOOLS["validate_result"](e, "n1", _llm=slow)["running"] == "validate_result"
        slow.go.set()
        _settled(lambda: not e.claims.validation_in_flight(TaskId("n1")))
        _settled(lambda: any("validate_result ended with no result" in m for m in said))
        assert not e.current_exec_verdict(TaskId("n1"))
    finally:
        slow.go.set()
        e.stop()


def test_in_process_the_validation_answers_its_verdict():
    """The system's own call (the dispatcher's, `SYSTEM_TOOLS`) still answers the verdict it ran for."""
    e = _eng()
    _delivered_node(e)
    slow = _SlowValidator()
    slow.go.set()
    try:
        assert TL.SYSTEM_TOOLS["validate_result"](e, "n1", _llm=slow)["verdict"] == "PASS"
    finally:
        e.stop()


# ── a check before the delivery, at a seam the person issues ───────────────────────────────────────────────────────

def test_a_check_before_the_delivery_holds_its_holders_step_while_it_runs(tmp_path, monkeypatch):
    """The holder's check of its committed tree runs past its call: its step is held on the frontier (no DELIVER lands
    meanwhile), so the server's wait waits on the verdict; a second call starts nothing and says so; the refused DELIVER
    names how the verdict is read; the check ends and the step is back."""
    for k, v in (("GFSO_AGENTS_PATH", str(tmp_path / "agents.json")), ("GFSO_L2_GATE", "0")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)
    monkeypatch.setattr(TL, "ANSWER_WITHIN_SECONDS", 2.0)    # …past the thread reaching its validator, under a loaded suite too
    e, _ = S._issued(tmp_path)
    repo = str(a_repository(tmp_path / "repo"))
    slow = _SlowValidator(entries=S._entries(e))
    try:
        out = S._call(S.CONSOLE, "validate_result", e, S.SEAM, workdir=repo, _llm=slow)
        assert out["running"] == "validate_result" and out["checks"]["commit"], out
        with S._as(S.CONSOLE):
            seen = T.next_steps(e, actor=S.HOLDER)
            assert not [s for s in seen.get("steps") or () if s["task_id"] == S.SEAM], seen
            assert any(w["task_id"] == S.SEAM for w in seen.get("waiting") or ()), seen
            waited = TL.wait_for_the_customer(e, actor=S.HOLDER, seconds=0.5)
        assert not waited.get("needs_you") and waited["waited_seconds"] >= 0.4, waited
        again = S._call(S.CONSOLE, "validate_result", e, S.SEAM, workdir=repo, _llm=_SlowValidator())
        assert again.get("inflight") and again["verdict"] is None and "get_verdict" in again["note"], again
        refused = S._delivers(e, out["checks"]["tree"])
        assert not refused.get("accepted") and "get_verdict" in refused["error"], refused
        slow.go.set()
        _settled(lambda: not e.judges_before_delivery(S.SEAM))
        with S._as(S.CONSOLE):
            back = [s for s in T.next_steps(e, actor=S.HOLDER)["steps"] if s["task_id"] == S.SEAM]
        assert back and "The last check, of tree" in back[0]["directive"], back     # …the wait woken by it says it
    finally:
        slow.go.set()
        e.stop()


# ── one check before a delivery at a time ──────────────────────────────────────────────────────────────────────────

def test_a_check_before_the_delivery_is_a_claim_its_taker_alone_lets_go(tmp_path, monkeypatch):
    """Two checks of the holder's tree started together: the second is refused at the claim, says the first runs and
    takes nothing from it — its tree stays judged until the first ends, and the first's verdict lands."""
    for k, v in (("GFSO_AGENTS_PATH", str(tmp_path / "agents.json")), ("GFSO_L2_GATE", "0")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)
    e, _ = S._issued(tmp_path)
    repo = str(a_repository(tmp_path / "repo"))
    slow = _SlowValidator(entries=S._entries(e))
    first = threading.Thread(target=lambda: TL.validate_result(e, S.SEAM, workdir=repo, _llm=slow), daemon=True)
    try:
        first.start()
        assert slow.started.wait(20)
        with pytest.raises(CheckRunning), e.judging_before_delivery(S.SEAM, "another", "c-another"):
            pass
        # …and the door's second check, past the read that let it through, meets the claim
        monkeypatch.setattr(e, "judges_before_delivery", lambda task_id: False)
        again = TL.validate_result(e, S.SEAM, workdir=repo, _llm=_SlowValidator())
        monkeypatch.undo()
        assert again.get("inflight") and again["verdict"] is None, again
        assert e.judges_before_delivery(S.SEAM)
        slow.go.set()
        first.join(20)
        assert not e.judges_before_delivery(S.SEAM)
        assert (e.current_exec_verdict(TaskId(S.SEAM)) or {}).get("verdict") == "PASS"
    finally:
        slow.go.set()
        e.stop()


# ── an authoring ───────────────────────────────────────────────────────────────────────────────────────────────────

def _split(parts=("root.core",)):
    """A root split into `parts` (`root.core` alone by default), none split itself."""
    e = _engine()
    TL.TOOLS["create_task"](e, "root", {"name": "root", "description": "the goal", "criteria": [criterion("c1", "it")]},
                            "user")
    out = TL.TOOLS["decompose"](e, "root", [{"task_id": p, "assignee": "user", "covers": ["c1"],
                                             "spec": {"description": f"the part {p}", "criteria": [criterion("k", "K")]}}
                                            for p in parts], accepted_risks=REGISTER)
    assert not out.get("error") if isinstance(out, dict) else out, out
    return e


def _asked(e, **args) -> dict:
    """`auto_decompose` at a door, its answer asserted within seconds: a call held by its authoring fails here."""
    got = Future()
    threading.Thread(target=lambda: got.set_result(TL.TOOLS["auto_decompose"](e, **args)), daemon=True).start()
    return got.result(timeout=10)


@pytest.fixture
def writing(monkeypatch):
    """An authoring of `root.core` asked at a door and kept writing (its model waits on OPEN): (the engine, its handle)."""
    monkeypatch.setattr(TL, "ANSWER_WITHIN_SECONDS", 0.3)
    e = _split()
    OPEN.clear()
    try:
        out = _asked(e, request="the core", root_id="root.core")
        assert out.get("writing") and out["running"] == "auto_decompose" and out["root_id"] == "root.core", out
        yield e, out["writing"]
    finally:
        OPEN.set()
        _settled(lambda: not e.authorings.held())
        e.stop()


def test_one_authoring_per_subtree_on_every_path(writing):
    """While one authoring writes `root.core`, another on it, on the root above it, the go on a plan file, and the
    system's own split are refused naming it — the authoring's own entry is the one owner; once it has ended, one may
    be asked."""
    e, h = writing
    assert e.authorings.held() == {"root.core": h}
    for args in ({"request": "again", "root_id": "root.core"}, {"request": "the whole", "root_id": "root"},
                 {"plan": Go._file()}):
        out = _asked(e, **args)
        assert out.get("refused") and out["being_rewritten"] == h and "an authoring is writing root.core now" in \
            out["error"], (args, out)
    assert TL.SYSTEM_TOOLS["auto_decompose"](e, request="the system's split", root_id="root").get("refused")
    OPEN.set()
    _settled(lambda: not e.authorings.held())


def test_the_wait_waits_on_an_authoring_and_wakes_with_its_whole_answer(writing):
    """The server's wait does not end while the authoring writes — its owner has no move, the graph is working — and
    wakes with its whole answer once it ends, the one its handle reads."""
    e, h = writing
    waited = TL.wait_for_the_customer(e, seconds=0.5)
    assert not waited.get("needs_you") and waited["waited_seconds"] >= 0.4 and waited["plans"] == {"writing": [h]}, waited
    OPEN.set()
    woke = TL.wait_for_the_customer(e, seconds=30)
    assert h in woke["needs_you"] and woke["answers"][h] == TL.TOOLS["auto_decompose"](e, writing=h), woke
    assert woke["answers"][h]["root_id"] == "root.core" and "holes" in woke["answers"][h], woke


def test_the_frontier_holds_the_subtree_being_written_in_flight(writing):
    """`next_steps` names the authoring in flight with its handle and holds every step in its subtree, saying what it
    waits on; the steps come back once it ends."""
    e, h = writing
    seen = TL.next_steps(e)
    assert any(w["task_id"] == "root.core" and w.get("writing") == h for w in seen.get("in_flight") or ()), seen
    assert not [s for s in seen.get("steps") or () if s["task_id"] == "root.core"], seen
    assert any(w["task_id"] == "root.core" and w["kind"] == "authoring" for w in seen.get("waiting") or ()), seen
    OPEN.set()
    _settled(lambda: not e.authorings.held())
    assert not any(w.get("writing") for w in TL.next_steps(e).get("in_flight") or ())


def test_a_move_in_the_subtree_being_written_is_refused_naming_it(writing):
    """A move on the node being written, and a split of the node above it, are refused naming the authoring they wait
    on; once it ends the same move is the node's own state's to take or refuse (it lands where nothing else moved it:
    `test_an_authoring_that_dies_…`)."""
    e, h = writing
    accept = lambda: TL.TOOLS["signal"](e, "root.core", "ACCEPT", "user")
    for out in (accept(), TL.TOOLS["decompose"](e, "root", [], accepted_risks=REGISTER)):
        assert out.get("refused") and out["being_rewritten"] == h and "being_rewritten" in out["error"], out
    assert e.graph.get_task(TaskId("root.core")).state.name == "OFFERED"
    OPEN.set()
    _settled(lambda: not e.authorings.held())
    assert "being_rewritten" not in accept()


def test_an_authoring_that_dies_leaves_its_error_on_its_handle_and_frees_its_subtree(monkeypatch):
    """A run that raises past its call: its handle answers the error, the feed says it, and its subtree is free."""
    monkeypatch.setattr(TL, "ANSWER_WITHIN_SECONDS", 0.3)
    go = threading.Event()

    def dies(*a, **k):
        assert go.wait(30)
        raise RuntimeError("the planner's process died")
    monkeypatch.setattr(TL, "decompose_into", dies)
    e = _split()
    said = []
    e.on_info(lambda source, msg: said.append(msg))
    try:
        h = _asked(e, request="the core", root_id="root.core")["writing"]
        go.set()
        _settled(lambda: not e.authorings.held())
        _settled(lambda: TL.next_steps(e).get("plans") == {"failed": [h]})
        assert "the planner's process died" in TL.TOOLS["auto_decompose"](e, writing=h)["error"]
        assert any(h in m and "ended with no plan" in m for m in said), said
        assert TL.TOOLS["signal"](e, "root.core", "ACCEPT", "user").get("accepted")
    finally:
        go.set()
        e.stop()


def test_the_go_keeps_its_root(writing, monkeypatch):
    """An authoring past its call names the root it writes, and its answer the root it built; the go on a plan file runs
    no model and answers its root in its call, however short the door's bound."""
    e, h = writing
    OPEN.set()
    _settled(lambda: not e.authorings.held())
    assert TL.TOOLS["auto_decompose"](e, writing=h)["root_id"] == "root.core"
    monkeypatch.setattr(TL, "ANSWER_WITHIN_SECONDS", 0.0)
    fresh = _engine()
    try:
        assert _asked(fresh, plan=Go._file())["root_id"] == "root"
    finally:
        fresh.stop()


def test_a_root_being_written_is_in_flight_before_the_graph_exists(monkeypatch):
    """On an empty project the frontier names the root's authoring in flight, not «no graph yet — plan it»."""
    monkeypatch.setattr(TL, "ANSWER_WITHIN_SECONDS", 0.3)
    e = _engine()
    OPEN.clear()
    try:
        h = _asked(e, request="a goal")["writing"]
        seen = TL.next_steps(e)
        assert [w.get("writing") for w in seen["in_flight"]] == [h] and "No graph yet" not in seen["directive"], seen
    finally:
        OPEN.set()
        _settled(lambda: not e.authorings.held())
        e.stop()


# ── every writing of a project waited on, none held by nothing ─────────────────────────────────────────────────────

def _dying_at(monkeypatch, *nodes) -> dict:
    """An authoring of each of `nodes` that dies when its gate is set: {node: gate}."""
    gates = {n: threading.Event() for n in nodes}

    def dies(engine, request, root_id, **k):
        assert gates[root_id].wait(30)
        raise RuntimeError(f"{root_id} died")
    monkeypatch.setattr(TL, "decompose_into", dies)
    monkeypatch.setattr(TL, "ANSWER_WITHIN_SECONDS", 0.3)
    return gates


def test_two_authorings_of_one_project_are_each_listed_and_each_wakes_the_wait(monkeypatch):
    """Two authorings on sibling nodes write at once: `next_steps` lists both, the wait wakes on the first's end with
    its answer while the other is still listed writing, and again on the second's — one record per project lost one."""
    gates = _dying_at(monkeypatch, "root.a", "root.b")
    e = _split(("root.a", "root.b"))
    try:
        ha, hb = (_asked(e, request=n, root_id=n)["writing"] for n in ("root.a", "root.b"))
        assert sorted(TL.next_steps(e)["plans"]["writing"]) == sorted([ha, hb])
        gates["root.a"].set()
        woke = TL.wait_for_the_customer(e, seconds=20)
        assert ha in woke["needs_you"] and "root.a died" in woke["answers"][ha]["error"], woke
        assert woke["plans"].get("writing") == [hb], woke
        gates["root.b"].set()
        assert hb in TL.wait_for_the_customer(e, seconds=20)["needs_you"]
    finally:
        for g in gates.values():
            g.set()
        e.stop()


def test_a_writing_ending_between_the_waits_two_reads_is_not_said_writing(monkeypatch):
    """The wait reads the steps, then the writings' ends: one ending between the two wakes it, and its reply must not
    list it writing beside its answer (1 in 7 runs of the test above, before)."""
    gates = _dying_at(monkeypatch, "root.a", "root.b")
    e = _split(("root.a", "root.b"))
    ends, first = TL._ends, []

    def ended_meanwhile(project, handles):
        if not first:
            first.append(1)
            gates["root.a"].set()
            deadline = time.time() + 20
            while TL._kept.record(project, ha).get("state") != "failed" and time.time() < deadline:
                time.sleep(0.02)
        return ends(project, handles)
    try:
        ha, hb = (_asked(e, request=n, root_id=n)["writing"] for n in ("root.a", "root.b"))
        monkeypatch.setattr(TL, "_ends", ended_meanwhile)
        woke = TL.wait_for_the_customer(e, seconds=20)
        assert ha in woke["answers"] and woke["plans"].get("writing") == [hb], woke
    finally:
        for g in gates.values():
            g.set()
        e.stop()


def test_a_writing_ending_as_a_wait_runs_out_still_wakes_the_next_wait(monkeypatch):
    """A writing ending after the wait read the ends, at its deadline: that reply wakes nobody, so it must not mark the
    writing told — the next wait wakes on it (critic over f3b81dd: said and marked at the deadline, it woke none)."""
    gates = _dying_at(monkeypatch, "root.a")
    e = _split(("root.a",))
    ends = TL._ends

    def ending_after_the_read(project, handles):
        got = ends(project, handles)
        if not gates["root.a"].is_set():
            gates["root.a"].set()
            deadline = time.time() + 20
            while TL._kept.record(project, ha).get("state") != "failed" and time.time() < deadline:
                time.sleep(0.02)
        return got
    try:
        ha = _asked(e, request="root.a", root_id="root.a")["writing"]
        monkeypatch.setattr(TL, "_ends", ending_after_the_read)
        first = TL.wait_for_the_customer(e, seconds=0)
        assert not first.get("needs_you"), first
        monkeypatch.setattr(TL, "_ends", ends)
        again = TL.wait_for_the_customer(e, seconds=5)
        assert ha in again.get("needs_you", ""), again
    finally:
        gates["root.a"].set()
        e.stop()


def test_a_short_authoring_beside_a_plan_being_written_leaves_the_wait_on_the_plan(monkeypatch):
    """A `plan` writes; an authoring of the same project refused in its call meanwhile must not take the plan off the
    record: the wait still wakes on the plan's end."""
    gate = threading.Event()

    def author(*a, **k):
        assert gate.wait(30)
        raise ValueError("the planner gave up")
    monkeypatch.setattr(TL._planning, "author", author)
    monkeypatch.setattr(TL, "ANSWER_WITHIN_SECONDS", 0.3)
    monkeypatch.setattr(TL, "decompose_into", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no plan")))
    e = _split()
    try:
        h = TL.TOOLS["plan"](e, request="another goal")["writing"]
        assert _asked(e, request="the core", root_id="root.core").get("error")
        gate.set()
        woke = TL.wait_for_the_customer(e, seconds=20)
        assert h in woke.get("needs_you", ""), woke
    finally:
        gate.set()
        e.stop()


def test_a_claim_with_no_writing_behind_it_is_let_go(monkeypatch):
    """The channel refusing to start the writing (a store that cannot be written) leaves no subtree held by nothing."""
    def cannot(*a, **k):
        raise PermissionError("the plans' store is locked")
    monkeypatch.setattr(TL, "_once", cannot)
    e = _split()
    try:
        assert "the plans' store is locked" in _asked(e, request="the core", root_id="root.core")["error"]
        assert not e.authorings.held()
    finally:
        e.stop()


def test_every_node_a_move_names_is_held_and_a_switch_of_mode_waits(monkeypatch):
    """An edge from the node being written to a sibling names it as its producer: refused; a switch of mode, which hands
    roots between the person and the system party, waits for the authoring too."""
    gates = _dying_at(monkeypatch, "root.core")
    e = _split(("root.core", "root.side"))
    try:
        h = _asked(e, request="the core", root_id="root.core")["writing"]
        edge = TL.TOOLS["add_dependency"](e, "root.core", "root.side", glue="its output")
        assert edge.get("refused") and edge["being_rewritten"] == h, edge
        switch = TL.TOOLS["set_mode"](e, "solo", user_said="solo, please")
        assert switch.get("refused") and switch["being_rewritten"] == [h] and h in switch["error"], switch
        gates["root.core"].set()
        _settled(lambda: not e.authorings.held())
        assert "being_rewritten" not in TL.TOOLS["add_dependency"](e, "root.core", "root.side", glue="its output")
    finally:
        gates["root.core"].set()
        e.stop()


def test_a_new_project_whose_authoring_fails_past_its_call_stays_and_its_failure_says_how_to_remove_it(
        monkeypatch, tmp_path):
    """A project made by a call answered `{writing}` stays — its writing may still fill it, another may write there, a
    wait may read it —; its failure, the project holding nothing, names how it is removed."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    gates = _dying_at(monkeypatch, "root")
    reg = ProjectRegistry()
    e = reg.engine("brand_new")
    try:
        h = reg.kept_if_done(True, e, lambda: TL.TOOLS["auto_decompose"](e, request="a goal"))["writing"]
        gates["root"].set()
        _settled(lambda: not e.authorings.held())
        assert reg.exists("brand_new")
        said = TL.TOOLS["auto_decompose"](e, writing=h)["error"]
        assert "project brand_new holds nothing: `delete_project('brand_new')` removes it" in said, said
    finally:
        gates["root"].set()
        e.stop()


def _waiting(e) -> tuple:
    """The server's wait on `e`, run in a thread: (its thread, its answer to come)."""
    got = Future()
    t = threading.Thread(target=lambda: got.set_result(TL.wait_for_the_customer(e, seconds=20)), daemon=True)
    t.start()
    return t, got


def test_a_plan_asked_anew_supersedes_the_one_before_and_its_end_wakes_no_wait(monkeypatch):
    """A wait on a plan being written; the plan asked anew: the first is superseded, kept, and its end — written — is no
    news; the wait wakes on the second's."""
    gates = {r: threading.Event() for r in ("one", "two")}

    def author(request, *a, **k):
        assert gates[request.split()[0]].wait(30)
        return Go._file()
    monkeypatch.setattr(TL._planning, "author", author)
    e = _engine()
    try:
        first = TL.TOOLS["plan"](e, request="one goal")["writing"]
        t, woke = _waiting(e)
        time.sleep(0.5)
        second = TL.TOOLS["plan"](e, request="two goal")["writing"]
        gates["one"].set()
        time.sleep(3)
        assert not woke.done(), woke.result()
        gates["two"].set()
        t.join(30)
        assert second in woke.result()["needs_you"] and first not in woke.result()["needs_you"], woke.result()
    finally:
        for g in gates.values():
            g.set()
        e.stop()


def test_a_failed_writing_someone_else_read_wakes_the_wait_as_not_written(monkeypatch):
    """The wait's writing fails and another caller reads it before the wait looks again: it wakes as not written."""
    gates = _dying_at(monkeypatch, "root.core")
    e = _split()
    try:
        h = _asked(e, request="the core", root_id="root.core")["writing"]
        t, woke = _waiting(e)
        time.sleep(0.5)
        gates["root.core"].set()
        _settled(lambda: not e.authorings.held())
        assert TL.TOOLS["auto_decompose"](e, writing=h).get("error")
        t.join(30)
        assert woke.result()["needs_you"].startswith("a plan asked for was not written") and h in \
            woke.result()["needs_you"], woke.result()
    finally:
        gates["root.core"].set()
        e.stop()


def test_under_auto_the_writings_say_names_its_handle_at_the_mcp_door(monkeypatch):
    """The MCP door's say for the go under `auto` must not replace an authoring's `{writing}` say: its handle is the one
    way to its answer."""
    e = _engine()
    monkeypatch.setattr(e, "mode", lambda *a: {"mode": "auto"})
    out = {"writing": "auto_decompose-0123456789", "root_id": "root", "running": "auto_decompose",
           "say": 'The plan is being written: `auto_decompose(writing="auto_decompose-0123456789")` answers it'}
    try:
        said = M._with_ui_link("auto_decompose", dict(out), "p", e)["say"]
        assert 'auto_decompose(writing="auto_decompose-0123456789")' in said, said
    finally:
        e.stop()
