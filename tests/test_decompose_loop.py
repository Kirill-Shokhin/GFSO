"""The decompose/refine guarantees, driven deterministically (FakeLLM, no network):
- TOTAL MONADA: decompose(depth=N) ≡ init (search + fold over the empty state → spec) + build
  through the FSM + (N−1) × refine, where refine applies the SAME operation to the BUILT GRAPH as
  the state (search over the real projection → fold-patch → merge → rebuild as revision);
- early exits: ALREADY-COVERED (searcher) and empty-fold (auditor) — depth = upper bound;
- the ONE textual read of the state is the graph's own projection (Engine.project) — no separate renderer;
- extract_spec is the exact inverse of build (roundtrip); rebuild preserves existing children's Del;
- the build is verified: problems → bounded repair → clean list_holes, or an HONEST residue."""
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import TaskId, AgentId
import json

from gfso.decompose import decompose_into, decompose_spec, refine, extract_spec
from gfso.decompose.loop import SEARCH_PROMPT, FOLD_SCHEMA, _fold_merge, shape


class FakeLLM:
    """Queues per channel; records (kind, user) per call so the loop shape is assertable."""
    def __init__(self, texts, specs):
        self.texts, self.specs, self.calls = list(texts), list(specs), []

    def complete(self, prompt, context=""):
        assert context == SEARCH_PROMPT
        self.calls.append(("search", prompt))
        return self.texts.pop(0) if self.texts else ""

    def complete_structured(self, system, user, schema):
        kind = "fold" if schema is FOLD_SCHEMA else "repair"
        self.calls.append((kind, user))
        return self.specs.pop(0) if self.specs else {}


def _spec(mappings=None, accepted_risks=None):
    """The graph-form state after a successful first fold (also the shape build_graph_live consumes)."""
    return {
        "name": "Thing",
        "root_criteria": [{"name": "rc1", "description": "A done"}, {"name": "rc2", "description": "B done"}],
        "subtasks": [
            {"id": "a", "name": "A", "description": "do A", "criteria": [{"name": "a1", "description": "A ok"}]},
            {"id": "b", "name": "B", "description": "do B", "criteria": [{"name": "b1", "description": "B ok"}]},
        ],
        "mappings": mappings or [{"criterion": "rc1", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}],
        "deps": [{"from": "a", "to": "b", "glue": "B reads A's output"}],
        "accepted_risks": accepted_risks or [{"item": "provider outage", "predictability": "STATISTICAL",
                                    "justification": "P<1%", "invalidation": "outage seen"}],
    }


def _init_patch(mappings=None, accepted_risks=None):
    """The round-1 (empty-state) fold: the same content as _spec(), expressed as adds."""
    s = _spec(mappings=mappings, accepted_risks=accepted_risks)
    return {"name": s["name"], "add_root_criteria": s["root_criteria"], "add_subtasks": s["subtasks"],
            "add_mappings": s["mappings"], "add_deps": s["deps"], "add_accepted_risks": s["accepted_risks"]}


_ADD_C = {"add_subtasks": [{"id": "c", "name": "C", "description": "do C",
                            "criteria": [{"name": "c1", "description": "C ok"}]}],
          "add_mappings": [{"criterion": "rc2", "child_id": "c"}],
          "add_deps": [{"from": "b", "to": "c", "glue": "C reads B"}]}


def _eng():
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True)
    e.start()
    return e


# === init round (spec-space) ===

def test_init_round_is_one_search_plus_fold_over_empty_state():
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    out = decompose_spec("task", llm=fake)
    assert [k for k, _ in fake.calls] == ["search", "fold"]
    assert "(empty — first round)" in fake.calls[1][1]
    assert out["name"] == "Thing" and {c["id"] for c in out["subtasks"]} == {"a", "b"}


def test_failed_first_fold_returns_empty():
    """An empty round-1 fold (LLM failure) → {} — an honest nothing, not a phantom spec."""
    fake = FakeLLM(texts=["holes1"], specs=[{}])
    assert decompose_spec("task", llm=fake) == {}


def test_result_read_artifact_is_the_projection():
    """d_md = the built root's own projection (Engine.project) — the one canonical read, incl. the
    children's names/criteria and the seams' glue (what the next fold reads)."""
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    assert res.d_md == res.engine.project(TaskId("root"))
    assert "`root.a` — A:" in res.d_md                       # child NAME rides the projection now
    assert "B reads A's output" in res.d_md                  # seam glue present
    assert "Structural checks already run" in res.d_md


def test_fast_rides_init_round_user_content_only():
    from gfso.decompose.loop import SEARCH_FAST, AUDIT_FAST
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    decompose_spec("task", llm=fake, fast=True)
    assert fake.calls[0][1].endswith(SEARCH_FAST) and fake.calls[1][1].endswith(AUDIT_FAST)
    fake2 = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    decompose_spec("task", llm=fake2)
    assert not any("Pace note" in u for _, u in fake2.calls)


# === the total monada: depth>1 = refine over the BUILT graph ===

def test_depth2_refines_over_the_built_graph():
    """decompose_into(depth=2): init+build, then the refine searcher reads the REAL projection and the
    fold applies to the extracted graph state; the rebuild lands the new child in the live engine."""
    fake = FakeLLM(texts=["holes1", "holes2"], specs=[_init_patch(), _ADD_C])
    res = decompose_into(_eng(), "task", root_id="root", depth=2, llm=fake)
    kinds = [k for k, _ in fake.calls]
    assert kinds == ["search", "fold", "search", "fold"]
    # the refine searcher read the graph's REAL projection (checks section is unique to it)
    assert "Structural checks already run" in fake.calls[2][1]
    e = res.engine
    assert e.get_task(TaskId("root.c")) is not None            # fold landed in the LIVE graph
    assert res.holes == []
    assert {c["id"] for c in res.spec["subtasks"]} == {"a", "b", "c"}


def test_refine_already_covered_converges():
    fake = FakeLLM(texts=["holes1", "ALREADY-COVERED\nnothing new"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", depth=3, llm=fake)
    assert [k for k, _ in fake.calls] == ["search", "fold", "search"]   # no fold, round 3 never runs
    assert res.holes == []


def test_refine_empty_fold_converges():
    fake = FakeLLM(texts=["holes1", "restatements"], specs=[_init_patch(), {}])
    res = decompose_into(_eng(), "task", root_id="root", depth=3, llm=fake)
    assert [k for k, _ in fake.calls] == ["search", "fold", "search", "fold"]
    assert {c["id"] for c in res.spec["subtasks"]} == {"a", "b"}


def test_public_refine_applies_one_iteration_to_existing_graph():
    """refine() = "+1 итерация над тем, что есть": works on an already-built decomposition."""
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    fake2 = FakeLLM(texts=["found: C is missing"], specs=[_ADD_C])
    res2 = refine(e, root_id="root", llm=fake2)
    assert e.get_task(TaskId("root.c")) is not None
    assert res2.holes == []
    assert "Structural checks already run" in fake2.calls[0][1]   # searcher saw the real projection


def test_refine_preserves_existing_children_del():
    """A rebuild-as-revision must not stomp an existing child's Del (Inv-1: a Del change is the
    issuer's own act, not a refinement side effect)."""
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    e.reassign(TaskId("root.a"), AgentId("bob"))                  # issuer delegates a to bob
    fake2 = FakeLLM(texts=["found: C"], specs=[_ADD_C])
    refine(e, root_id="root", llm=fake2)
    assert e.get_task(TaskId("root.a")).assignee == AgentId("bob")   # Del survived the rebuild
    assert e.get_task(TaskId("root.c")) is not None


def test_one_verb_dispatches_to_refine_on_decomposed_node():
    """decompose_into IS the one verb: on an already-decomposed target it runs refine rounds over
    what exists (no init round; request optional — the node's contract is the request)."""
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    fake2 = FakeLLM(texts=["found: C"], specs=[_ADD_C])
    res2 = decompose_into(e, "", root_id="root", depth=1, llm=fake2)     # same verb, no request
    assert [k for k, _ in fake2.calls] == ["search", "fold"]             # refine path, not init
    assert "Structural checks already run" in fake2.calls[0][1]          # over the real projection
    assert e.get_task(TaskId("root.c")) is not None
    assert res2.holes == []


def test_rebuild_preserves_child_own_registers():
    """A child's OWN ACCEPTED_RISKS belongs to the CHILD'S decomposer (§13.1) — a parent-level rebuild
    must not wipe it (same class as Del preservation)."""
    from gfso.core.types import AcceptedRiskItem
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    e.edit_accepted_risks(TaskId("root.a"), (AcceptedRiskItem("a-risk"),), AgentId("human"))
    fake2 = FakeLLM(texts=["found: C"], specs=[_ADD_C])
    refine(e, root_id="root", llm=fake2)
    a = e.get_task(TaskId("root.a"))
    assert [n.item for n in a.spec.accepted_risks] == ["a-risk"]              # survived the rebuild


def test_refine_leaves_untouched_children_in_place():
    """Idempotent rebuild: a refine that doesn't touch a child emits ZERO signals for it — an
    EXECUTING child keeps executing (a live graph survives a replan; only changed contracts
    re-negotiate per Inv-1)."""
    from gfso.core.types import SignalData, Signal
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root.a"),
                                  source=AgentId("human")))
    e.wait_idle()
    from gfso.core.types import State
    assert e.get_state(TaskId("root.a")) == State.EXECUTING
    n_signals_a = len(e.audit_log(TaskId("root.a")))
    fake2 = FakeLLM(texts=["found: C"], specs=[_ADD_C])
    refine(e, root_id="root", llm=fake2)
    assert e.get_state(TaskId("root.a")) == State.EXECUTING          # untouched → still executing
    assert len(e.audit_log(TaskId("root.a"))) == n_signals_a         # zero signals on the child
    assert e.get_task(TaskId("root.c")) is not None                  # the change landed


def test_refine_frozen_terminal_children_surface_as_holes():
    """Completed work is FROZEN: a fold update targeting a DONE child cannot apply (a terminal node
    admits no revision, §14.3) — the intent must NOT vanish into rejected signals (observed live):
    the searcher sees the frozen list, the unapplied change surfaces as an honest hole, and the
    child's state/audit stay untouched."""
    from gfso.core.types import SignalData, Signal, State
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    # drive root.a to DONE: executor signals by its Del (human), verdict by an authorized validator
    for sig in (Signal.ACCEPT, Signal.DELIVER):
        e.send_signal_sync(SignalData(signal=sig, task_id=TaskId("root.a"), source=AgentId("human"),
                                      result="a done" if sig is Signal.DELIVER else None))
    e._graph.authorized_validators = {"vx"}
    e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("root.a"), source=AgentId("vx")))
    e.wait_idle()
    assert e.get_state(TaskId("root.a")) == State.DONE
    n_signals_a = len(e.audit_log(TaskId("root.a")))
    upd_a = {"update_subtasks": [{"id": "a", "name": "A", "description": "do A DIFFERENTLY",
                                  "criteria": [{"name": "a1", "description": "A ok"},
                                               {"name": "a9", "description": "new obligation"}]}]}
    fake2 = FakeLLM(texts=["found: a must also do a9"], specs=[upd_a, {}])   # repair fails → residue
    res2 = refine(e, root_id="root", llm=fake2)
    assert "COMPLETED SUBTASKS — contracts FROZEN" in fake2.calls[0][1]      # searcher saw the freeze
    assert "root.a" in fake2.calls[0][1]
    a = e.get_task(TaskId("root.a"))
    assert a.state == State.DONE and "DIFFERENTLY" not in a.spec.description  # untouched
    assert len(e.audit_log(TaskId("root.a"))) == n_signals_a                  # zero signals emitted
    assert any("terminal" in str(h) for h in res2.holes)                      # honest residue


def test_refine_on_terminal_target_refused():
    """A completed goal is frozen (terminal admits no revision; REOPEN is parked) — the one verb
    refuses loudly instead of crashing on the root's own re-author."""
    import pytest
    from gfso.core.types import SignalData, Signal, State
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    e._graph.authorized_validators = {"vx"}
    for tid in ("root.a", "root.b"):
        for sig in (Signal.ACCEPT, Signal.DELIVER):
            e.send_signal_sync(SignalData(signal=sig, task_id=TaskId(tid), source=AgentId("human"),
                                          result="done" if sig is Signal.DELIVER else None))
        e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId(tid), source=AgentId("vx")))
    e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("root"),
                                  source=AgentId("human"), result="aggregate"))
    e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("root"), source=AgentId("vx")))
    e.wait_idle()
    assert e.get_state(TaskId("root")) == State.DONE
    with pytest.raises(ValueError, match="terminal"):
        decompose_into(e, "", root_id="root", llm=FakeLLM(texts=[], specs=[]))


def test_refine_state_view_carries_blocked_children_with_reasons():
    """Runtime contact feeds the replan: a BLOCKED child + its BLOCK reason must reach the refine
    searcher/auditor (observed live: an inverted Dep direction deadlocked the graph and the fold,
    blind to the block, re-derived the same structure)."""
    from gfso.core.types import SignalData, Signal
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    # root.b consumes root.a (declared) — but its executor discovers the direction is wrong
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root.b"),
                                  source=AgentId("human")))
    e.send_signal_sync(SignalData(signal=Signal.BLOCK, task_id=TaskId("root.b"),
                                  source=AgentId("human"),
                                  reason="need A's real output first — the dep direction is inverted"))
    e.wait_idle()
    fake2 = FakeLLM(texts=["ALREADY-COVERED"], specs=[])
    refine(e, root_id="root", llm=fake2)
    view = fake2.calls[0][1]
    assert "BLOCKED SUBTASKS" in view and "root.b" in view
    assert "dep direction is inverted" in view          # the recorded reason reached the fold


def test_refine_note_when_request_ignored():
    """The one-verb dispatch on a decomposed node refines over the node's OWN contract; a caller's
    `request` text must never be swallowed silently — the result carries a loud note (goal changes
    are the revise verb)."""
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    fake2 = FakeLLM(texts=["ALREADY-COVERED"], specs=[])
    res2 = decompose_into(e, "ALSO add a linegrep module", root_id="root", llm=fake2)
    assert res2.note and "NOT applied" in res2.note
    fake3 = FakeLLM(texts=["ALREADY-COVERED"], specs=[])
    res3 = decompose_into(e, "", root_id="root", llm=fake3)                   # no request → no note
    assert res3.note is None


def test_fold_removal_unmaps_but_never_kills():
    """The auditor's removal opinion is RECORDED and VISIBLE, the kill is not its to make: a fold
    remove drops the child's coverage (reconciled on rebuild) → the node surfaces as an unmapped
    hole (non-redundancy guard) for the ISSUER to CANCEL or re-map — it is never destroyed and its
    state is untouched (surface-don't-destroy, the v3.7 revision guard-set)."""
    from gfso.core.types import State
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    e = res.engine
    drop_b = {"remove_subtask_ids": ["b"],
              "add_mappings": [{"criterion": "rc2", "child_id": "a"}]}   # coverage re-homed onto a
    fake2 = FakeLLM(texts=["found: b is ballast"], specs=[drop_b])
    res2 = refine(e, root_id="root", llm=fake2)
    b = e.get_task(TaskId("root.b"))
    assert b is not None and b.state == State.OFFERED                 # alive, state untouched
    root = e.get_task(TaskId("root"))
    assert all(m.child_id != TaskId("root.b") for m in root.criterion_mappings)   # unmapped
    assert any("b" in str(h) for h in res2.holes)                    # surfaced as an honest hole


def test_extract_spec_roundtrips_build():
    """extract_spec is the exact inverse of build_graph_live (ids de-namespaced, dep__ criteria back
    to seams, scope strings verbatim)."""
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    got = extract_spec(res.engine, "root")
    want = _spec()
    assert got["name"] == want["name"]
    assert {c["id"] for c in got["subtasks"]} == {"a", "b"}
    a = [c for c in got["subtasks"] if c["id"] == "a"][0]
    assert a["criteria"] == [{"name": "a1", "description": "A ok"}]      # dep__ criteria NOT here
    assert got["deps"] == [{"from": "a", "to": "b", "glue": "B reads A's output"}]
    assert sorted((m["criterion"], m["child_id"]) for m in got["mappings"]) == \
        [("rc1", "a"), ("rc2", "b")]
    assert got["accepted_risks"][0]["item"] == "provider outage"
    assert got["accepted_risks"][0]["predictability"] == "STATISTICAL"


# === _fold_merge: deterministic, referentially clean, dedup ===

def test_fold_merge_add_update_remove():
    spec = _spec()
    patch = {
        "remove_subtask_ids": ["b"],
        "update_subtasks": [{"id": "a", "name": "A+", "description": "do A better",
                             "criteria": [{"name": "a1", "description": "A ok"},
                                          {"name": "a2", "description": "A edge ok"}]}],
        "add_subtasks": [{"id": "c", "name": "C", "description": "do C",
                          "criteria": [{"name": "c1", "description": "C ok"}]}],
        "add_mappings": [{"criterion": "rc2", "child_id": "c"}],
        "add_deps": [{"from": "a", "to": "c", "glue": "C reads A"}],
    }
    s, ops = _fold_merge(spec, patch)
    assert {c["id"] for c in s["subtasks"]} == {"a", "c"}
    assert all(m["child_id"] != "b" for m in s["mappings"])        # removal cleaned b's mapping
    assert all("b" not in (d["from"], d["to"]) for d in s["deps"])  # ...and b's seam
    assert [c for c in s["subtasks"] if c["id"] == "a"][0]["name"] == "A+"
    assert {(d["from"], d["to"]) for d in s["deps"]} == {("a", "c")}
    assert ops


def test_fold_merge_dedup_and_noop():
    spec = _spec()
    patch = {"add_subtasks": [dict(spec["subtasks"][0])],
             "add_mappings": [dict(spec["mappings"][0])],
             "add_deps": [dict(spec["deps"][0])],
             "add_accepted_risks": [dict(spec["accepted_risks"][0])],
             "update_subtasks": [dict(spec["subtasks"][1])],       # identical update = no-op
             "name": "Thing"}                                      # same name = no-op
    s, ops = _fold_merge(spec, patch)
    assert ops == []
    assert s["subtasks"] == spec["subtasks"] and s["deps"] == spec["deps"]


def test_fold_merge_root_criteria_removal_cleans_mappings():
    spec = _spec()
    s, ops = _fold_merge(spec, {"remove_root_criteria_names": ["rc1"]})
    assert [c["name"] for c in s["root_criteria"]] == ["rc2"]
    assert all(m["criterion"] != "rc1" for m in s["mappings"])
    assert ops


def test_shape_counts():
    assert shape(_spec()) == (2, 1, 4)   # 2 subtasks · 1 seam · 2 root + 2 child criteria


# === build verification (unchanged guarantees) ===

def test_decompose_into_repairs_to_clean():
    bad_mappings = [{"criterion": "rc1_typo", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}]
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch(mappings=bad_mappings), _spec()])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    assert res.holes == []
    repair_user = [u for k, u in fake.calls if k == "repair"][0]
    assert "rc1_typo" in repair_user
    root = res.engine.get_task(TaskId("root"))
    assert {(m.criterion_name, m.child_id) for m in root.criterion_mappings} == \
        {("rc1", TaskId("root.a")), ("rc2", TaskId("root.b"))}


def test_decompose_into_reports_honest_residue():
    bad_mappings = [{"criterion": "rc1_typo", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}]
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch(mappings=bad_mappings)])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    assert res.holes
    assert any("rc1_typo" in h for h in res.holes)


def test_repair_is_a_field_patch():
    bad_mappings = [{"criterion": "rc1_typo", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}]
    patch = {"mappings": [{"criterion": "rc1", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}]}
    fake = FakeLLM(texts=["holes1"], specs=[_init_patch(mappings=bad_mappings), patch])
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    assert res.holes == []
    assert len(res.spec["subtasks"]) == 2
    assert res.spec["mappings"][0]["criterion"] == "rc1"


def test_a_silent_provider_is_reported_as_a_provider_fact(monkeypatch):
    """An LLM that never answers must not read as a goal that needs no subtasks.

    The LLM ports return "" / {} on transport failure by contract, so a provider that is unreachable
    or unauthenticated produced a *clean* run — 0 subtasks, 0 holes, "verified" — indistinguishable
    in the result from a goal that is genuinely atomic. That is the first thing a fresh install
    without credentials meets, on the verb it is told to start with.

    The transport is patched at `decompose._default_llm`, not on the Engine: `auto_decompose` builds
    its own from the environment (runtime.llm_factory) and never consults the engine's.
    """
    from gfso import decompose as D
    from gfso import tools_llm as T

    class Silent:
        """What a dead endpoint looks like through the port: nothing said, nothing recorded."""
        calls = ()

        def complete(self, prompt, context=""):
            return ""

        def complete_structured(self, system, user, schema):
            return {}

    monkeypatch.setattr(D, "_default_llm", lambda model: Silent())
    e = Engine(MemoryStorage(), HumanAgent(), Silent(), validate_signals=True)
    e.start()
    out = T.auto_decompose(e, "ship a hello world script", root_id="r", assignee="human")
    assert out["subtasks"] == []
    assert "provider" in out.get("error", "")
    e.stop()


def test_refine_sees_the_open_level_2_findings():
    """A refine straight after a review that left findings open returned the plan unchanged and
    charged for the round.

    The findings are the plan's known defects, in the caller's hand at that exact moment, and the one
    verb whose job is to repair the plan was the only reader that did not get them (measured on the
    agent door 2026-08-22). What the fold DOES with them is its own business — fold them in, or leave
    them for the issuer to dispute in writing — but it must see them."""
    fake = FakeLLM(texts=["holes1", "ALREADY-COVERED"], specs=[_init_patch()])
    e = _eng()
    res = decompose_into(e, "task", root_id="root", depth=1, llm=fake)
    eng = res.engine
    eng._graph._storage.store_critique(TaskId("root"), json.dumps({
        "node_id": "root", "gate_passed": True, "semantic_covered": False,
        "criteria_verdicts": [{"criterion": "c1", "verdict": "insufficient",
                               "why": "the children do not entail it"}],
        "conflicts": [], "undecided_obligations": [{"obligation": "the package imports"}],
        "iteration": 0, "reopens": 0, "revisions": 0,
    }))
    root = eng.get_task(TaskId("root")); root.verified = True; eng._graph.save_task(root)

    fake2 = FakeLLM(texts=["ALREADY-COVERED"], specs=[])
    refine(eng, root_id="root", rounds=1, llm=fake2)
    view = fake2.calls[0][1]
    assert "OPEN LEVEL-2 FINDINGS" in view
    assert "- c1" in view and "undecided: the package imports" in view
