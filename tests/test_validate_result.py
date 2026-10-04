"""validate_result — EXECUTION validation (≠ validate, the PLAN's L2): the read-only validator
INSTRUMENT produces per-criterion evidence; the ISSUER signals PASS/FAIL. Logic tested with a fake
agent-runner (the live run is a headless subprocess)."""
import asyncio
import json
from datetime import timedelta
import pathlib
import subprocess
import threading
from pathlib import Path

import pytest

import gfso.adapters.llm.headless as _headless
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.adapters.llm.headless import _tool_use_name, HeadlessClaudeLLM
from gfso.adapters.llm.stub import StubLLM
from gfso.core.protocol.invariants import verdict_report_defects
from tests.support import criterion, make_engine, pinned, REGISTER


def _eng():
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    return e


def _fenced(payload: dict) -> str:
    return "```json\n" + json.dumps(payload) + "\n```"


class _ValidatorLLM:
    """Fake agent-runner: records the packet, returns a canned final report."""
    def __init__(self, text):
        self._text = text
        self.calls = []
        self.seen = None

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.seen = {"system": system, "user": user, "tools": allowed_tools, "cwd": cwd}
        self.calls.append({"duration_ms": 1200, "input_tokens": 500, "output_tokens": 90})
        return self._text

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _delivered_node(e, tid="n1", extra_dep=False):
    nail = {"name": "Nail it", "description": "hammer a nail",
            "criteria": [criterion("flush", "nail head is flush"), criterion("holds", "picture hangs on it")]}
    if not extra_dep:
        T.create_task(e, tid, nail, "alice")
    else:
        # a seam joins two SIBLINGS, so the pair hangs under the project's one root: a second
        # parentless node would be a second verdict with nothing composing the two
        T.create_task(e, "goal", {"description": "hang the picture",
                                  "criteria": [criterion("hung", "the picture hangs")]}, "boss")
        T.decompose(e, "goal", [   # §11.5: the split is admitted whole, its register with it (§9.2)
            {"task_id": tid, "spec": nail, "assignee": "alice", "covers": ["hung"]},
            {"task_id": "prod", "spec": {"description": "buy nails", "criteria": [criterion("nails", "nails exist")]},
             "assignee": "alice", "covers": ["hung"]}], accepted_risks=REGISTER)
        T.add_dependency(e, "prod", tid, glue="uses the bought nails")
    assert T.signal(e, tid, "ACCEPT", "alice")["state"] == "EXECUTING"
    r = T.signal(e, tid, "DELIVER", "alice",
                 result="nail at wall.md:3; flush verified by touch; holds verified with 2kg frame")
    assert r["state"] == "VALIDATING"


def test_validate_result_happy_path_embeds_contract_and_deliver():
    e = _eng()
    _delivered_node(e, extra_dep=True)
    # the seam is criteria-content (§2 Dep): `dep__prod` is a CRITERION of this node, so a verdict
    # must speak to it too — a report silent on the seam is ⊥ over the seam (anti-mock has teeth)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "read wall.md", "behaviours": ["the criterion holds"], "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "ran check", "behaviours": ["the criterion holds"], "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "dep__prod", "verdict": "pass",
                                      "evidence": "grep: uses the real bought nails, no stub", "behaviours": ["the criterion holds"], "probe": [{"command": "check dep__prod", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}],
                                 "seams": "checked prod output", "failed_criteria": []}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] == "PASS" and out["failed_criteria"] == []
    assert len(out["per_criterion"]) == 3 and out["state"] == "VALIDATING"
    assert out["stats"][-1]["stage"] == "validate_result"
    # the packet is SELF-CONTAINED: contract + seam + the audit-log DELIVER result, read-only tool set
    assert "flush" in llm.seen["user"] and "holds verified with 2kg frame" in llm.seen["user"]
    assert "prod" in llm.seen["user"]                       # seam embedded
    assert "Write" not in llm.seen["tools"] and "Read" in llm.seen["tools"]
    e.stop()


def test_validate_result_fail_report_drives_issuer_fail_signal():
    """The tool never signals; its failed_criteria feed the ISSUER's FAIL → REWORKING (Inv-3)."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "FAIL",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "fail", "evidence": "nail bent", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "held", "behaviours": ["the criterion holds"], "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": ["flush"]}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["flush"]
    assert e.graph.get_state(T.TaskId("n1")).name == "VALIDATING"   # instrument did NOT mutate the graph
    r = T.signal(e, "n1", "FAIL", "alice", failed_criteria=out["failed_criteria"])
    assert r["accepted"] and r["state"] == "REWORKING"
    e.stop()


def test_validate_result_requires_a_deliverable():
    e = _eng()
    T.create_task(e, "n2", {"description": "x", "criteria": [criterion("a", "A")]}, "alice")
    out = TL.validate_result(e, "n2", _llm=_ValidatorLLM("irrelevant"))
    assert "error" in out and "DELIVER" in out["error"]
    # explicit deliverable unblocks it (the restart fallback)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "a", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check a", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
    out = TL.validate_result(e, "n2", deliverable="see out.txt", _llm=llm)
    assert out["verdict"] == "PASS" and "see out.txt" in llm.seen["user"]
    e.stop()


def test_validate_result_unparsed_report_is_never_pass():
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM("I looked at it and it seems fine!")   # no fenced json
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] is None and "seems fine" in out["report_text"]
    assert llm.calls[-1]["parse_failed"] is True
    e.stop()


def test_pass_contradicting_its_own_evidence_is_not_a_verdict():
    """THE false-PASS measured live (BCB/93, 2026-07-17): the validator ran the canonical suite
    correctly, reported `test_values: fail` WITH failing evidence, and still returned verdict PASS
    with empty failed_criteria — excusing the red criterion as "ACCEPTED_RISKS-declared, out of scope".
    A criterion is the obligation (§2 V=⋀cᵢ); ACCEPTED_RISKS (§9.2) holds risks of the decomposition and
    never retires one. The ENGINE refuses to record it (not the prompt): no verdict ⟹ no PASS."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "flush ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "holds", "verdict": "fail",
                                      "evidence": "fell off — but the plan ACCEPTED_RISKS this as an "
                                                  "impossible criterion, so out of scope", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": []}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] is None                      # ⊥, never read as pass
    assert "holds" in out["verdict_defects"] and "ACCEPTED_RISKS" in out["verdict_defects"]
    assert e.get_exec_verdict(T.TaskId("n1")) is None   # nothing recorded — the gate stays shut
    assert T.signal(e, "n1", "PASS", "alice")["accepted"] is False
    e.stop()


def test_report_leaving_a_criterion_unspoken_is_not_a_verdict():
    """V = AND over ALL criteria: an unevaluated conjunct is ⊥, not pass (§2). A PASS over a
    partially-evaluated contract would silently drop obligations."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": []}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] is None and "holds" in out["verdict_defects"]
    e.stop()


def test_failed_criteria_must_be_the_reports_own_red_set():
    """The issuer's FAIL payload IS the report's red set (Inv-3): a FAIL naming other criteria (or
    naming none) sends the executor to rework the wrong thing."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "FAIL",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "fail", "evidence": "bent", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "held", "behaviours": ["the criterion holds"], "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": ["holds"]}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] is None and "failed_criteria" in out["verdict_defects"]
    e.stop()


def test_a_nodes_own_report_that_names_no_verdict_is_not_a_verdict():
    """A node's own report is wholly its claim (§7.1: V is two-valued; Inv-3): `"verdict": null` decided nothing, so
    nothing is recorded — read as "derive it from the entries", it recorded PASS even beside a failed list (critic V2)."""
    for listed in ([], ["holds"]):
        e = _eng()
        _delivered_node(e)
        llm = _ValidatorLLM(_fenced({"verdict": None, "failed_criteria": listed, "per_criterion": [
            {"criterion": n, "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"],
             "probe": [{"command": f"check {n}", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}
            for n in ("flush", "holds")]}))
        out = TL.validate_result(e, "n1", _llm=llm)
        assert out["verdict"] is None and "neither PASS nor FAIL" in out["verdict_defects"]
        assert e.get_exec_verdict(T.TaskId("n1")) is None
        e.stop()


_GREEN_BATCH = {                       # the batch whose criterion passes, said five ways; its sibling says FAIL consistently
    "lowercase pass": ("pass", []), "null word": (None, []), "third word": ("PARTIAL", []),
    "FAIL naming nothing": ("FAIL", []), "FAIL naming the sibling's criterion": ("FAIL", "SIBLING"),
}


@pytest.mark.parametrize("red", ["flush", "holds"])        # which batch says FAIL: first or second
@pytest.mark.parametrize("shape", list(_GREEN_BATCH))
def test_each_batch_is_judged_whole_and_the_words_are_conjoined(monkeypatch, shape, red):
    """The batches of one node's contract are reports, each judged whole as a scope's report is (Inv-3, §7.1), and the
    node's verdict is their conjunction (§2): `pass` in any casing is PASS, so the sibling's FAIL is the verdict; a
    batch whose word decided nothing, or that its own entries contradict, leaves the node no verdict, before or after
    the FAIL. Read by rules of their own, a lowercase word refused a consistent FAIL (critic V2), an undecided word
    after a FAIL was ignored while one before it refused (critic V3), and an undecided word refused while a
    contradicting one was absorbed into the FAIL (critic V4)."""
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "1")
    e = _eng()
    _delivered_node(e)
    word, listed = _GREEN_BATCH[shape]

    class _Batched(_ValidatorLLM):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
            n = "flush" if "**flush**" in user else "holds"
            other = "holds" if n == "flush" else "flush"
            return _fenced({"verdict": "FAIL" if n == red else word,
                            "failed_criteria": [n] if n == red else ([other] if listed == "SIBLING" else listed),
                            "per_criterion": [{"criterion": n, "verdict": "fail" if n == red else "pass",
                                               "evidence": "ran it", "behaviours": ["the criterion holds"],
                                               "probe": [{"command": f"check {n}", "expect": "it holds"},
                                                         {"command": "pytest -q", "expect": "passed"}]}]})

    out = TL.validate_result(e, "n1", _llm=_Batched(""))
    if shape == "lowercase pass":
        assert out["verdict"] == "FAIL" and out["failed_criteria"] == [red]
    else:
        assert out["verdict"] is None and out["verdict_defects"]
        assert e.get_exec_verdict(T.TaskId("n1")) is None
    e.stop()


def test_a_report_over_several_nodes_that_names_no_verdict_decided_nothing():
    """The scope's reading of a report holds the record's rule (§7.1): a word that is neither PASS nor FAIL decided
    nothing for any node it covers, however green its entries (critic V3: it recorded PASS for every node)."""
    green = {"criterion": "a_ok", "verdict": "pass"}
    for word in (None, "", "PARTIAL"):
        assert TL._report_contradicts_itself({"verdict": word, "per_criterion": [green], "failed_criteria": []})
    assert TL._report_contradicts_itself({"verdict": "pass", "per_criterion": [green], "failed_criteria": []}) is None


def test_verdict_over_a_foreign_contract_is_not_a_verdict():
    """A report speaking of criteria this node does not have answers another contract."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "painted", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check painted", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": []}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] is None and "painted" in out["verdict_defects"]
    e.stop()


def test_an_empty_entry_about_a_non_criterion_observes_nothing():
    """A batch wrote `{criterion: 'No separate criterion for root.build parts', verdict: pass, evidence: placeholder}`
    and a root's whole validation was refused (GB_coreutils_tmsq57348): no probe, behaviour or divergence — no conjunct.
    The same entry carrying a probe still answers another contract."""
    own = {"criterion": "a", "verdict": "pass", "evidence": "ran", "behaviours": ["x"],
           "probe": [{"command": "c", "expect": "ok"}]}
    stray = {"criterion": "No separate criterion", "verdict": "pass", "evidence": "placeholder"}
    assert verdict_report_defects(["a"], "PASS", [own, stray], [], require_probe=True) == []
    assert verdict_report_defects(["a"], "PASS", [own, {**stray, "probe": own["probe"]}], [], require_probe=True)
    assert verdict_report_defects(["a"], "PASS", [own, {**stray, "verdict": "fail"}], [], require_probe=True)


def test_an_entry_naming_another_node_in_a_nodes_own_report_is_still_its_own():
    """A node validated on its own packet: every entry of its report is about it, whatever `task_id` an entry carries —
    one about a criterion it does not have is refused as an answer to another contract, not dropped into a PASS
    (critic V1 over the one validation pass)."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "zz", "task_id": "other", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check zz", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": []}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] is None and "zz" in out["verdict_defects"]
    e.stop()


def test_recorded_verdict_carries_the_evidence():
    """§15.8: the Thm 11 trail must show WHAT was verified — a bare verdict cannot be audited post-hoc
    (the live false-PASS could not be diagnosed from the record; the report was gone)."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "measured 0.2mm proud", "behaviours": ["the criterion holds"], "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "2kg for 24h", "behaviours": ["the criterion holds"], "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
    TL.validate_result(e, "n1", _llm=llm)
    rec = e.get_exec_verdict(T.TaskId("n1"))
    assert rec["verdict"] == "PASS"
    assert [p["criterion"] for p in rec["per_criterion"]] == ["flush", "holds"]
    assert "0.2mm" in rec["per_criterion"][0]["evidence"]
    e.stop()


def test_validate_result_noops_on_a_node_inside_one_session_s_scope(monkeypatch):
    """A node whose parent's whole was judged to fit one executor session is that executor's own work: the
    tool returns a self-verify directive and NEVER spawns the validator on it — the scope's validation at its
    top covers it (§3.7, §10.3)."""
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)
    e = _eng()
    T.create_task(e, "par", {"description": "parent", "criteria": [criterion("g", "G")]}, "alice")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "child", "criteria": [criterion("k", "K")]},
                            "assignee": "alice", "covers": ["g"]}], accepted_risks=REGISTER)   # §11.5: admitted whole
    for n in ("par", "kid"):
        e.record_session_fit(T.TaskId(n), "~100 lines", True)
    T.signal(e, "kid", "ACCEPT", "alice")
    T.signal(e, "kid", "DELIVER", "alice", result="done; k met")
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "k", "verdict": "pass", "evidence": "x", "behaviours": ["the criterion holds"], "probe": [{"command": "check k", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
    out = TL.validate_result(e, "kid", _llm=llm)
    assert out.get("internal") is True and out["verdict"] is None
    assert llm.seen is None                         # the validator was NEVER spawned
    assert e.get_exec_verdict(T.TaskId("kid")) is None
    # the internal node still PASSes directly (no INDEPENDENT verdict on a same-Del node) — once its
    # own decided self-check is on the record, which is what §10.3 asks it to carry
    e.record_reviewer_verdict(T.TaskId("kid"), "PASS", [], reviewer="alice",
                              observed={"k": "ran it, read the output"})
    assert T.signal(e, "kid", "PASS", "alice")["state"] == "DONE"
    e.stop()


def test_validate_result_still_validates_a_delegation_seam():
    """The counterpart: a child with a DIFFERENT Del is a seam — validation DOES run there."""
    e = _eng()
    T.create_task(e, "par2", {"description": "parent", "criteria": [criterion("g", "G")]}, "alice")
    T.decompose(e, "par2", [{"task_id": "kid2", "spec": {"description": "child", "criteria": [criterion("k", "K")]},
                             "assignee": "bob", "covers": ["g"]}], accepted_risks=REGISTER)
    T.signal(e, "kid2", "ACCEPT", "bob")
    T.signal(e, "kid2", "DELIVER", "bob", result="done; k met")
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "k", "verdict": "pass", "evidence": "x", "behaviours": ["the criterion holds"], "probe": [{"command": "check k", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
    out = TL.validate_result(e, "kid2", _llm=llm)
    assert out["verdict"] == "PASS" and llm.seen is not None   # seam → validator DID run
    e.stop()


def test_validate_result_unknown_task():
    e = _eng()
    out = TL.validate_result(e, "ghost", _llm=_ValidatorLLM(""))
    assert "error" in out
    e.stop()


def test_registry_exposes_validate_result():
    assert "validate_result" in TL.TOOLS   # the COMPLETE transport registry


def test_mcp_server_binds_validate_result_async():
    """The MCP surface exposes validate_result via the long-running async binding (progress notifications,
    no engine/_-params in the schema)."""
    pytest.importorskip("mcp")
    from gfso.mcp.server import create_server   # behind the skip: the module needs `mcp` installed

    e = _eng()
    server = create_server(e)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert "validate_result" in tools
    props = tools["validate_result"].inputSchema["properties"]
    assert "task_id" in props and "deliverable" in props
    assert "engine" not in props and "_llm" not in props and "_progress" not in props
    e.stop()


def test_self_pass_gate_requires_fresh_independent_verdict():
    """The guinea-pig hole (live 2026-07-04): with collapsed ids (executor == issuer == `agent`) the
    FSM couldn't tell an evidence-based PASS from a self-stamp — 6/8 nodes self-passed on the agent's
    own bash check. Now: PASS where source == Del requires a RECORDED validate_result verdict for the
    CURRENT delivery; a FAIL verdict blocks PASS; a rework stales the record; a DISTINCT issuer
    (source ≠ Del) keeps the canon default."""
    e = _eng()
    _delivered_node(e)                                            # n1, Del=alice, delivered by alice
    r = T.signal(e, "n1", "PASS", "alice")                        # self-stamp, no verdict
    assert r["accepted"] is False and "verifier" in r["error"]
    # a FAIL verdict on record does NOT unlock PASS (that override is the falsification q_V fears)
    llm_fail = _ValidatorLLM(_fenced({"verdict": "FAIL", "per_criterion": [
        {"criterion": "flush", "verdict": "fail", "evidence": "bent", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "held", "behaviours": ["the criterion holds"], "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": ["flush"]}))
    TL.validate_result(e, "n1", _llm=llm_fail)
    r = T.signal(e, "n1", "PASS", "alice")
    assert r["accepted"] is False and "FAIL" in r["error"]
    # the honest path: FAIL → REWORKING → re-deliver → the OLD verdict is stale → re-validate → PASS
    assert T.signal(e, "n1", "FAIL", "alice", failed_criteria=["flush"])["state"] == "REWORKING"
    assert T.signal(e, "n1", "DELIVER", "alice", result="fixed")["state"] == "VALIDATING"
    r = T.signal(e, "n1", "PASS", "alice")
    assert r["accepted"] is False and "STALE" in r["error"]
    llm_ok = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "held", "behaviours": ["the criterion holds"], "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
    TL.validate_result(e, "n1", _llm=llm_ok)
    assert T.signal(e, "n1", "PASS", "alice")["state"] == "DONE"
    e.stop()


def test_a_distinct_issuer_still_needs_the_verdict_on_the_record():
    """The separation of ids is not the evidence — §10.3 asks for independent VALIDATION at a seam.

    This test asserted the opposite ("a parent-issuer passes the executor's delivered node without
    the gate"), and that is exactly the false PASS the agent door walked into on 2026-08-22: a
    delegated child signed PASS by its issuer while a STALE FAIL stood on it and its validator was
    still running — accepted, DONE. Reproduced with nothing on the record at all. What opens the
    gate is a verdict for THIS delivery, from the instrument or from a person saying what they
    observed; who signs is a separate rule (the executor may not)."""
    e = _eng()
    T.create_task(e, "par", {"description": "parent", "criteria": [criterion("g", "G")]}, "boss")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "child", "criteria": [criterion("k", "K")]},
                            "assignee": "worker", "covers": ["g"]}], accepted_risks=REGISTER)   # §11.5
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="done")
    bare = T.signal(e, "kid", "PASS", "boss")                      # issuer=boss ≠ Del=worker…
    assert bare["accepted"] is False and "independent verdict" in bare["error"]
    T.record_verdict(e, "kid", "PASS", reviewer="boss",
                     observed={"k": {"note": "ran it, printed 42", "ran": ["check k"]}})
    assert T.signal(e, "kid", "PASS", "boss")["state"] == "DONE"   # …once the record exists
    e.stop()


def _seen(e, tid):
    """What a human reviewer says they observed — one line per criterion (the door now asks)."""
    t = e.graph.get_task(T.TaskId(tid))
    return {c.name: {"note": f"checked {c.name} by hand",
                     "ran": [p.command for p in (c.check or ())]}
            for c in t.spec.criteria if not c.depends_on}


def test_record_verdict_closes_the_solo_human_ux_cliff_without_weakening_the_gate():
    """The human counterpart of validate_result: a SELF-executed node's PASS stays rejected until an
    INDEPENDENT reviewer records a verdict (record_verdict) — and the engine REFUSES the executor
    recording one on their own work (the self-stamp would open the gate from the inside)."""
    e = _eng()
    T.create_task(e, "n9", {"description": "solo work",
                            "criteria": [criterion("a", "A")]}, "h1")
    T.signal(e, "n9", "ACCEPT", "h1")
    T.signal(e, "n9", "DELIVER", "h1", result="done; a met")
    assert e.graph.get_state(T.TaskId("n9")).name == "VALIDATING"
    assert T.signal(e, "n9", "PASS", "h1")["accepted"] is False      # gate: no recorded verdict

    out = T.record_verdict(e, "n9", "PASS", reviewer="h1", observed=_seen(e, "n9"))  # self-record
    assert out["recorded"] is False and "executor" in out["error"]   # the ENGINE refused

    assert T.record_verdict(e, "n9", "FAIL", reviewer="h2")["recorded"] is False  # Inv-3: criteria-less FAIL

    assert T.record_verdict(e, "n9", "PASS", reviewer="h2",
                            observed=_seen(e, "n9"))["recorded"] is True   # independent human
    assert T.signal(e, "n9", "PASS", "h1")["accepted"] is True       # gate opens on the RECORD
    assert e.graph.get_state(T.TaskId("n9")).name == "DONE"
    e.stop()



def test_validator_tool_use_is_counted_and_recorded():
    """What the validator DID, beside what it says it did.

    Its verdicts cite executions ("Executed: parse_blocks(...) -> ..."), and four of seven such
    claims in one measured run did not match the artefact they validated. Whether a run opened Bash at
    all is decidable structurally, from the stream, without parsing a word of the report — so it is
    recorded with the verdict and a claim of execution can be checked against it.
    """
    # the shapes stream-json uses for a tool call, and one that is not a tool call
    assert _tool_use_name({"type": "content_block_start",
                           "content_block": {"type": "tool_use", "name": "Bash"}}) == "Bash"
    assert _tool_use_name({"event": {"content_block": {"type": "tool_use", "name": "Read"}}}) == "Read"
    assert _tool_use_name({"message": {"content": [{"type": "text", "text": "hi"},
                                                   {"type": "tool_use", "name": "Grep"}]}}) == "Grep"
    assert _tool_use_name({"event": {"delta": {"text": "Executed: parse_blocks(...)"}}}) is None

    e = _eng()
    _delivered_node(e)
    e.record_exec_verdict("n1", "FAIL", ["flush"], "validate_result",
                          per_criterion=[{"criterion": "flush", "verdict": "fail",
                                          "evidence": "Executed: check() -> not flush", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
                                         {"criterion": "holds", "verdict": "pass", "evidence": "hangs", "behaviours": ["the criterion holds"], "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}],
                          tools_used={"Read": 2})
    rec = e.get_exec_verdict("n1")
    assert rec["tools_used"] == {"Read": 2}
    # WHAT THE LEDGER IS FOR, asserted as an effect and not as a stored string. This asked only that
    # the contradiction be KEPT — "Bash not in tools_used and 'Executed' in the evidence" — which is
    # true of a system that reads the field and of one that never looks at it, and this one never
    # did: `tools_used` had exactly one reader in the tree, this line. A test that pins a false
    # belief is part of the defect. The refutation itself, with its controls, is in
    # `test_a_probe_that_names_a_command_was_run.py`; here it is enough that the pass over an unrun
    # probe did not survive the record.
    assert {c["criterion"]: c["verdict"] for c in rec["per_criterion"]}["holds"] == "undecidable"


def test_a_verdict_with_no_reproducible_probe_is_refused():
    """The instrument must be re-runnable, and the engine — not a prompt — is what insists.

    Measured (`EVIDENCE_LOG` §13.5): replaying the checkable claims of one run against the exact
    snapshot they validated, four of seven described behaviour the artifact did not have. The
    validator's own contract already said "executed evidence outranks assessment"; nothing checked
    that an execution happened. Now a per-criterion entry without `probe: {command, expect}` is not
    a verdict — it is ⊥ — and the tool reports the defect instead of recording a claim no one can
    re-run. The refusal rides the SAME path as the other verdict defects, so the validator is
    re-spawned rather than the node silently stalling.
    """
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "measured 0.2mm proud"},
        {"criterion": "holds", "verdict": "pass", "evidence": "2kg for 24h"}], "failed_criteria": []}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] is None
    assert "no reproducible probe" in out["verdict_defects"]
    assert e.get_exec_verdict(T.TaskId("n1")) is None       # nothing recorded, so nothing unlocks a PASS


def test_the_probe_requirement_is_the_instrument_s_alone():
    """A human reviewer records a verdict WITHOUT a probe: `record_reviewer_verdict` is a person's
    assessment at the seam, not a machine's re-runnable observation, and holding it to the same rule
    would demand a command line from someone who inspected the thing by hand.

    No PROBE and no OBSERVATION are different absences, and only the first is a person's licence:
    what they saw is the entire weight of their record (the record says so itself, in its
    `independence` line), so it is prose here rather than a command — and not nothing.
    """
    e = _eng()
    _delivered_node(e)
    e.record_reviewer_verdict(T.TaskId("n1"), "PASS", [], "human-reviewer",
                              # no `probe` — prose is a person's licence — but they still say WHICH
                              # of the criterion's pinned commands they ran by hand
                              observed={c.name: {"note": "opened it and read it end to end; it holds",
                                                 "ran": [p.command for p in (c.check or ())]}
                                        for c in e.graph.get_task(T.TaskId("n1")).spec.criteria})
    assert e.get_exec_verdict(T.TaskId("n1"))["verdict"] == "PASS"


def test_the_validator_runs_where_the_delivery_IS(tmp_path):
    """The working directory it is given must be the one holding the work.

    The fresh-scratch-per-validation fix (a shared scratch had let one run validate another's
    leftovers) made that scratch the validator's working DIRECTORY — so it opened in an empty one,
    could not see the delivery, and failed correct work with "the working directory is empty" as
    its evidence. A false FAIL at the seam is worse than no validation: it returns good work to
    REWORKING and escalates a finished root at the iteration limit. The scratch still exists and is
    still per-validation; it is offered BY NAME, for copies.
    """
    project = tmp_path / "project"
    project.mkdir()
    (project / "sum.py").write_text("print(42)", encoding="utf-8")

    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "read wall.md",
         "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "python sum.py", "expect": "42"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "ran check",
         "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "python sum.py", "expect": "42"}]}]}))
    TL.validate_result(e, "n1", workdir=str(project), _llm=llm)

    assert llm.seen["cwd"] == str(project), "the validator was opened away from the delivery"
    assert (project / "sum.py").exists()
    # BESIDE the delivery, not inside it: a criterion like "every file under the target dir belongs
    # to this package" is otherwise false because of us (measured on the human door 2026-08-22).
    assert not (project / ".gfso-scratch").exists()
    scratch = list((project.parent / f".gfso-scratch-{project.name}").iterdir())
    assert len(scratch) == 1, "a fresh scratch per validation is still made"
    assert str(scratch[0]) in llm.seen["user"], "…and the validator is told where it is"
    assert str(project) in llm.seen["user"]
    e.stop()


def test_internal_model_calls_inherit_nothing_from_the_operators_console(monkeypatch):
    """Every internal call (decompose, the Level-2 review, the validator) is a `claude -p`, and a
    `claude -p` inherits the operator's whole console configuration. Two parts of it must not come
    along, for two different reasons.

    MCP: this installation registers its own door there, so each call started the gfso stdio bridge
    as a child process, each with its own console window — measured live, one extra bridge per call
    without the pin and none with it. The window is the visible half; the other half is why hiding
    it would have been the wrong fix — these calls need no gfso tools, and a VALIDATOR holding them
    could sign the graph it is validating (§10.3 verifier ≠ executor).

    HOOKS: the same fact one layer over. A hook written for a person's interactive console fires
    inside this child too — measured live: a session-lifecycle hook logged a start event for an
    internal call and injects its own instructions, so a run's context stops being the run's. On the
    Stop event it is worse than contamination: a hook may REFUSE the child's exit and buy extra
    generation rounds on a paid call. Neither is the operator's mistake; a child of ours is ours to
    keep clean.

    HISTORY: the reverse direction — the child must not leave anything IN the console either. Each
    call saved its transcript into the operator's session history; measured on one install, 10 459
    of them beside 18 of the person's own, and `claude --resume` took minutes to list them."""
    seen = {}

    class _P:
        def __init__(self, args, **kw):
            seen["args"] = args
            self.stdin, self.stdout, self.returncode = _W(), iter(()), 0

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

        def kill(self):
            pass

    class _W:
        def write(self, s):
            pass

        def close(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", _P)
    # The CLI's PRESENCE is not what is under test, and its absence must not decide the verdict:
    # `shutil.which` returning None degrades the provider to a stub that starts no process at all,
    # so no argv is ever built and the flag below is read off an empty list — the assertion then
    # reports a missing pin where the real defect is a missing binary. That is how this test read on
    # a machine with `claude` installed (green) and on a CI runner without it (red), for one and the
    # same correct code. Pinning `which` makes the argv real on both.
    monkeypatch.setattr(_headless.shutil, "which", lambda cmd: cmd)
    llm = HeadlessClaudeLLM(model="haiku", claude_cmd="claude")
    try:
        llm.complete("system", "user")
    except Exception:
        pass                      # the transport is faked; only the ARGV is under test
    assert seen.get("args"), \
        "no process was started at all: the argv this test checks was never built"
    assert "--strict-mcp-config" in seen["args"], \
        "an internal call would inherit the user's MCP servers and spawn the gfso bridge"
    args = seen["args"]
    assert "--settings" in args and \
        json.loads(args[args.index("--settings") + 1]).get("disableAllHooks") is True, \
        "an internal call would inherit the operator's hooks: injected instructions on start, and " \
        "a refused exit buying paid generation rounds on Stop"
    assert json.loads(args[args.index("--settings") + 1]).get("language") == "", \
        "an internal call would answer in the operator's configured language, whatever its goal's"
    assert "--no-session-persistence" in args, \
        "every internal call would save its transcript into the operator's session history, " \
        "burying their own sessions and stalling `claude --resume` for minutes"
    assert "--safe-mode" in args, \
        "an internal call would load the operator's CLAUDE.md: an executor or a validator of this " \
        "product would run under the personal instructions its user wrote for themselves"


def test_the_record_names_the_model_that_validated():
    """A verdict's row named the instrument's ROLE and not its tier.

    Two runs validated by different models produced the same-looking record, and the tier of a role has
    already been silently wrong twice in this project (a checker defaulting to sonnet under a haiku
    worker; the plan repair running on the executor's model). A reader of the record should not have
    to reconstruct who validated from what happened to be configured that day.
    """
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "ok",
                                      "behaviours": ["nail head is flush"],
                                      "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "ok",
                                      "behaviours": ["picture hangs on it"],
                                      "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": []}))
    TL.validate_result(e, "n1", model="haiku", _llm=llm)
    rec = e.get_exec_verdict(T.TaskId("n1"))
    assert rec["verdict"] == "PASS"
    assert rec.get("validator_model") == "haiku", "the record does not say which model validated"
    e.stop()


def test_what_the_validator_leaves_in_the_delivery_is_named(tmp_path):
    """A validator that writes into the tree it validates is reported, by name.

    Measured live across several runs: validators left fixtures in the delivery — `t1.csv`, a
    `_fixtures/` directory, once a 120 MB `big.txt` — and the next validator then saw them as part of
    the work. The packet now says to write only into the offered scratch; a prompt is not
    enforcement, so the difference is measured too. Nothing is deleted: the executor's tree is not
    this code's to prune, and a named stray is a fact its owner can act on."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "sum.py").write_text("print(42)", encoding="utf-8")

    e = _eng()
    _delivered_node(e)

    class _Littering(_ValidatorLLM):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            (project / "t1.csv").write_text("a,b\n", encoding="utf-8")
            (project / "_fixtures").mkdir()
            return super().run_agent(system, user, allowed_tools, cwd)

    llm = _Littering(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ran it",
         "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "python sum.py", "expect": "42"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "ran it",
         "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "python sum.py", "expect": "42"}]}]}))
    out = TL.validate_result(e, "n1", workdir=str(project), _llm=llm)

    assert out["validator_strays"] == ["_fixtures", "t1.csv"]
    assert (project / "t1.csv").exists()          # reported, never deleted
    assert "WRITE NOTHING INTO THE DELIVERY" in llm.seen["user"]
    e.stop()


def test_an_empty_working_directory_is_refused_not_failed(tmp_path, monkeypatch):
    """A validator opened where the work is not reports what it honestly sees — and that lands as a FAIL.

    Measured 2026-08-21 on a measurement run: a stale roster entry pointed the instrument at another
    experiment's scratch directory, its report read "no implementation exists", and the root took a
    false FAIL over SEVENTEEN criteria — on code that was sitting, complete, in the snapshot taken at
    that same delivery. The rework loop that followed ended the run.

    Refusing costs one comparison. The alternative costs a run, and it costs it in the direction
    that looks like a working instrument (§2.3: ⊥ is not a verdict, and it is not a FAIL either)."""
    e = _eng()
    _delivered_node(e)
    empty = tmp_path / "nothing"
    (empty / ".gfso-scratch").mkdir(parents=True)          # the scratch it makes itself does not count

    out = TL.validate_result(e, "n1", workdir=str(empty))
    assert out["verdict"] is None
    assert "empty" in out["error"] and "not the work" in out["error"]
    assert "do not send the node to rework" in out["error"]

    # …and with work present, whatever happens next, it is no longer THIS refusal. What it is
    # depends on the transport, which is not what this test is about — every other test here uses
    # a fake runner for exactly that reason, and so does this one.
    (empty / "sum.py").write_text("print(42)", encoding="utf-8")
    ok = _fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ran it",
         "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "python sum.py", "expect": "42"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "ran it",
         "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "python sum.py", "expect": "42"}]}]})
    out2 = TL.validate_result(e, "n1", workdir=str(empty), _llm=_ValidatorLLM(ok))
    assert "empty" not in (out2.get("error") or "")
    e.stop()


def test_a_refused_report_reaches_the_issuer_who_has_to_decide():
    """A parked node asks a person to decide, and handed them nothing to decide with.

    ⊥ is not a pass (§2.3), so a report the engine refuses ends the node's automatic progress and
    the issuer takes over. The observations that report DID contain lived in the tool's return value
    — which under delegation nobody reads — and in a text file whose path scrolled past in a log
    line. Measured 2026-08-21: with a 25-criterion contract the validator returned no verdict twice,
    the node parked, and seeing what it had managed to check meant going to find that file.

    It is stored beside the node under its own key, so nothing can mistake it for a verdict, and
    `get_verdict` shows it to whoever has to act."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "read it",
         "behaviours": ["the head sits flush", "and stays flush under load"],
         "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "python -c \"print('flush')\"", "expect": "flush"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "looked at it"}],
        "failed_criteria": []}))
    out = TL.validate_result(e, "n1", workdir=".", _llm=llm)
    assert out["verdict"] is None                       # refused: a criterion with no probe at all

    back = T.get_verdict(e, "n1")
    assert back["verdict"] is None                      # …still not a verdict, and says so
    assert "not a verdict" in back["refused_report"]["note"]
    seen = [p["criterion"] for p in back["refused_report"]["observed_anyway"]]
    assert "flush" in seen                              # …and what it DID observe is there
    assert back["refused_report"]["why_it_is_not_a_verdict"]
    e.stop()


@pytest.mark.parametrize("word, listed", [("FAIL", ["flush"]), ("PASS", [])])
def test_a_retry_that_speaks_a_kept_criterion_again_is_read_by_what_it_saw(monkeypatch, word, listed):
    """A retry after a refused report validates only what the refusal left, beside the entries kept from it; a report
    that speaks a kept criterion again saw it on the same delivery, and what it saw is read — the kept entry first, the
    fresh one over it, as main read them. Read the other way, a kept `pass` hid a fresh `fail`: a true FAIL was refused
    and a PASS over its own red entry closed the node DONE (critic V5)."""
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "0")
    e = _eng()
    _delivered_node(e)
    ent = lambda c, v="pass": {"criterion": c, "verdict": v, "evidence": "ran it", "behaviours": ["the criterion holds"],
                               "probe": [{"command": f"check {c}", "expect": "it holds"},
                                         {"command": "pytest -q", "expect": "passed"}]}

    class _Twice(_ValidatorLLM):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
            return _fenced({"verdict": "PASS", "per_criterion": [ent("flush")], "failed_criteria": []}
                           if len(self.calls) == 1 else       # skips `holds`: refused, `flush` kept
                           {"verdict": word, "per_criterion": [ent("flush", "fail"), ent("holds")],
                            "failed_criteria": listed})

    llm = _Twice("")
    assert TL.validate_result(e, "n1", _llm=llm)["verdict"] is None
    out = TL.validate_result(e, "n1", _llm=llm)
    if word == "FAIL":
        assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["flush"]
    else:
        assert out["verdict"] is None
        assert e.get_exec_verdict(T.TaskId("n1")) is None
        assert T.signal(e, "n1", "PASS", "alice")["accepted"] is False
    e.stop()


def test_a_long_contract_is_validated_in_batches_whose_conjunction_is_the_verdict(monkeypatch):
    """The coverage discipline is what a report fails on a rich contract.

    Measured 2026-08-21: the engine refuses a report that leaves any criterion unspoken or any named
    behaviour unobserved (§2.3), and on long contracts that is what reports do — 44 refused reports
    against 57 recorded verdicts, one node refused five times, and two E3 runs stalled at 25 and 42
    root criteria. V(t) = ⋀ cᵢ (§2), so validating the contract in disjoint batches and taking the
    conjunction is the SAME verdict: every criterion is validated exactly once, by a run that had room
    to probe it, and the merged report is refused on the same terms as any other."""
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "2")
    e = _eng()
    crits = [criterion(f"c{i}", f"criterion {i}") for i in range(5)]
    T.create_task(e, "big", {"description": "a rich contract", "criteria": crits}, "alice")
    T.signal(e, "big", "ACCEPT", "alice")
    T.signal(e, "big", "DELIVER", "alice", result="built it; see notes")

    seen = []

    class _Batched:
        calls = []

        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            validated = [c["name"] for c in crits if f"**{c['name']}**" in user]
            seen.append(validated)
            self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
            return _fenced({"verdict": "PASS", "failed_criteria": [],
                            "per_criterion": [{"criterion": n, "verdict": "pass", "evidence": "ran it",
                                               "behaviours": ["the criterion holds"],
                                               "probe": [{"command": f"check {n}", "expect": "it holds"},
                                                         {"command": "pytest -q", "expect": "passed"}]}
                                              for n in validated]})

        def tag_last(self, stage):
            self.calls[-1]["stage"] = stage

    out = TL.validate_result(e, "big", _llm=_Batched(), workdir=".")
    assert [len(b) for b in seen] == [2, 2, 1]                  # …three runs, disjoint
    assert sorted(sum(seen, [])) == sorted(c["name"] for c in crits)   # …every criterion once
    assert out["verdict"] == "PASS" and len(out["per_criterion"]) == 5
    e.stop()


def test_the_batches_of_one_verdict_run_at_the_same_time(monkeypatch, tmp_path):
    """Batching unblocked acceptance on a rich contract and left its LATENCY additive.

    Measured over 170 recorded validations (2026-08-22): a validation takes a median 46 s at ≤5
    criteria, 90 s at 6–12, 132 s at 13–24 and 312 s beyond — and a 25-minute wait for one is what
    ended the last `spreadsheet_engine` segment. The batches validate DISJOINT criteria over the same
    unchanging delivery, so the conjunction is the same whichever order they finish in; only the
    client and the scratch may not be shared."""
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "2")
    e = _eng()
    crits = [criterion(f"c{i}", f"criterion {i}") for i in range(5)]
    T.create_task(e, "big", {"description": "a rich contract", "criteria": crits}, "alice")
    T.signal(e, "big", "ACCEPT", "alice")
    T.signal(e, "big", "DELIVER", "alice", result="built it")
    project = tmp_path / "project"
    project.mkdir()
    (project / "sum.py").write_text("x = 1" + chr(10), encoding="utf-8")

    at_once = threading.Barrier(3, timeout=20)   # serial runs cannot clear it, and that IS the test
    places = []

    class _Slow:
        def __init__(self):
            self.calls, self.last_tool_calls, self.on_tick, self.stage_hint = [], {}, None, ""

        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            validated = [c["name"] for c in crits if f"**{c['name']}**" in user]
            places.append([ln for ln in user.splitlines() if "batch" in ln])
            at_once.wait()                          # …all three batches are inside at the same moment
            self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
            self.last_tool_calls["Bash"] = 1
            return _fenced({"verdict": "PASS", "failed_criteria": [],
                            "per_criterion": [{"criterion": n, "verdict": "pass", "evidence": "ran it",
                                               "behaviours": ["the criterion holds"],
                                               "probe": [{"command": f"check {n}", "expect": "it holds"},
                                                         {"command": "pytest -q", "expect": "passed"}]}
                                              for n in validated]})

        def tag_last(self, stage):
            self.calls[-1]["stage"] = stage

    primary = _Slow()
    out = TL.validate_result(e, "big", _llm=primary, workdir=str(project), _spawn=_Slow)
    assert out["verdict"] == "PASS" and len(out["per_criterion"]) == 5
    assert len(primary.calls) == 3, "every batch's spend is on the validation's own record"
    assert primary.last_tool_calls["Bash"] == 3
    assert all(p for p in places), "each batch gets its own scratch"
    e.stop()


def test_a_refuted_criterion_survives_the_under_probing_rule():
    """A rule against false passes threw away a true negative.

    Measured on the human door 2026-08-21: a deliberately garbage delivery — two tests, one of them
    `assert True`, no CLI coverage — was caught exactly right by the validator, and the engine
    discarded the FAIL because the probes behind it carried empty `expect` fields. The evidence for
    "this test does not exist" IS an absence; it has no expected output to show. Under-probing means
    an unobserved conjunct cannot carry a PASS (§2.3) and says nothing against a criterion the
    report refuted with evidence — a refutation is a decision, and suppressing it sent bad work back
    looking accepted."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({
        "verdict": "FAIL", "failed_criteria": ["flush"],
        "per_criterion": [
            {"criterion": "flush", "verdict": "fail",
             "evidence": "there is no test for it: `grep -r flush tests/` prints nothing",
             "behaviours": ["nail head is flush", "measured after driving"],
             "probe": [{"command": "grep -r flush tests/", "expect": ""}]},
            {"criterion": "holds", "verdict": "pass", "evidence": "held 2kg",
             "behaviours": ["picture hangs"],
             "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "pytest -q", "expect": "passed", "behaviour": "picture hangs"}]}]}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["flush"]
    assert T.get_verdict(e, "n1")["verdict"] == "FAIL"      # …and it is on the record, not discarded
    e.stop()


def _roster_of(monkeypatch, entries: dict):
    """The server-wide roster, stubbed — the suite never writes roles into a shared file."""
    class _Reg:
        """The roster as the instrument uses it — both questions, because a stub that answers only
        the easy one turns a real call into an AttributeError in the tests and nowhere else."""

        def get(self, agent_id):
            return entries.get(agent_id)

        def validator_for(self, executor_id, project=None):
            return next((aid for aid, cfg in entries.items()
                         if cfg.get("kind") == "llm-validator"), None)
    monkeypatch.setattr(TL, "_roster", lambda engine=None: _Reg())
    return _Reg()


def test_the_workdir_defaults_to_where_the_nodes_Del_is_registered(tmp_path, monkeypatch):
    """The instrument asked the CALLER for an answer the server already held.

    Measured on the human door 2026-08-22: `validate_result(<node>)` on a node whose Del is a
    registered role refused with "the working directory None is empty (or absent)" — and the refusal
    itself said to go read `list_agents`, i.e. to look up in the roster what the roster would have
    answered here. The tester copied the directory in by hand, and the hand-passed argument then hit
    a crash: the seam was unpassable for the length of one lookup nobody made."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "sum.py").write_text("print(42)", encoding="utf-8")

    e = _eng()
    _delivered_node(e)                                     # Del = alice
    _roster_of(monkeypatch, {"alice": {"kind": "llm-executor", "workdir": str(project)}})
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "failed_criteria": [], "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ran it", "behaviours": ["nail head is flush"],
         "probe": [{"command": "check flush", "expect": "it holds"}, {"command": "python sum.py", "expect": "42", "behaviour": "nail head is flush"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "ran it", "behaviours": ["picture hangs on it"],
         "probe": [{"command": "check holds", "expect": "it holds"}, {"command": "python sum.py", "expect": "42", "behaviour": "picture hangs on it"}]}]}))
    monkeypatch.setattr(TL, "llm_factory", lambda model: llm)

    out = TL.validate_result(e, "n1")                       # no workdir: the roster has it
    assert "error" not in out, out.get("error")
    assert out["verdict"] == "PASS"
    assert llm.seen["cwd"] == str(project), "the validator was opened away from the delivery"
    e.stop()


def test_the_refusal_stands_when_the_roster_has_no_answer_either(tmp_path, monkeypatch):
    """Defaulting is a lookup, not a guess: with nothing registered for the Del — or a role holding
    no workdir — there is genuinely nothing to point the validator at, and the refusal is the answer."""
    e = _eng()
    _delivered_node(e)
    _roster_of(monkeypatch, {})                             # alice is a person: unlisted
    out = TL.validate_result(e, "n1")
    assert out["verdict"] is None
    assert "empty" in out["error"] and "not the work" in out["error"]
    assert "do not send the node to rework" in out["error"]

    _roster_of(monkeypatch, {"alice": {"kind": "llm-executor"}})   # registered, no workdir
    assert TL.validate_result(e, "n1")["verdict"] is None
    e.stop()


def test_an_unreadable_delivery_accuses_nobody(monkeypatch, tmp_path):
    """No pre-image means NOTHING can be said about strays — not that there were none, and certainly
    not that every file present is one.

    The pre-image was an empty set on failure, so an unreadable directory turned every pre-existing
    file in the delivery into something "the validator left behind" — the exact false accusation this
    comparison exists to prevent, inverted (found while naming the swallowed failures, 2026-09-02).
    """
    (tmp_path / "already_here.py").write_text("x = 1", encoding="utf-8")
    _real = Path.iterdir
    monkeypatch.setattr(Path, "iterdir",
                        lambda self: (_ for _ in ()).throw(OSError("gone"))
                        if str(self) == str(tmp_path) else _real(self))
    scratch, before = TL._validation_place("n1", str(tmp_path))
    assert before is None, "an unreadable pre-image is UNKNOWN, not empty"

    monkeypatch.undo()
    out: dict = {}
    TL._strays_left_behind(None, "n1", str(tmp_path), None, out, lambda *_: None)
    assert "strays" not in out and not out, "with no pre-image, the honest answer about strays is silence"


def test_a_validator_that_wrote_nothing_is_not_a_validator_that_wrote_badly():
    """Fifteen minutes, 232 tokens, $0.00 — a transport that stopped, reported as a parse failure.

    Measured on a paid run (2026-09-06, `database_engine` under arm G): the validation call came back
    with one sentence — "I'll inspect the delivery and run real probes" — and nothing else. The
    engine refused it, correctly; what it SAID was "the validator's report did not parse", the same
    words a genuinely unreadable report gets. On the second such refusal the node parks and the run
    ends, so the reader has to tell a validator worth re-running from a validator worth replacing, and both
    facts wore one sentence. 51 minutes and $2.53 ended there.
    """
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM("I'll inspect the delivery and run real probes.")

    out = TL.validate_result(e, "n1", _llm=llm)

    assert out["verdict"] is None, "⊥ stays ⊥ — this changes what is SAID, never what is accepted"
    said = out["verdict_defects"]
    assert "produced NO REPORT" in said and "run that stopped" in said, said
    assert "did not parse" not in said, said


def test_an_unreadable_report_still_says_it_did_not_parse():
    """The negative control: a real report that cannot be read keeps its own diagnosis."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM('{"verdict": "PASS", "per_criterion": [ {"criterion": "flush"  '   # truncated JSON
                        + "x" * 500)

    out = TL.validate_result(e, "n1", _llm=llm)

    assert out["verdict"] is None
    assert "did not parse" in out["verdict_defects"], out["verdict_defects"]


def test_a_retry_after_a_refused_report_validates_only_what_it_left_undecided():
    """A report is refused WHOLE for one gap, and a retry that re-validated everything could fail on a
    gap the first run did not have (7 of 10 refused reports on a delegated `coreutils` run,
    2026-09-22). What the refused report decided on its own — a PASS with the pinned probe run and
    every named behaviour observed — is kept for the SAME delivery, and only the rest is validated
    again; the merged report is still checked whole."""
    e = _eng()
    crits = [criterion("c0", "criterion 0"), criterion("c1", "criterion 1")]
    T.create_task(e, "n", {"description": "two criteria", "criteria": crits}, "alice")
    T.signal(e, "n", "ACCEPT", "alice")
    T.signal(e, "n", "DELIVER", "alice", result="built it")
    seen = []

    def _entry(n, probed=True):
        return {"criterion": n, "verdict": "pass", "evidence": "ran it",
                "behaviours": ["the criterion holds"],
                **({"probe": [{"command": pinned(n)[0].command, "expect": "it holds",
                               "behaviour": "the criterion holds"}]} if probed else {})}

    class _Validator:
        calls = []

        def __init__(self, probe_c1):
            self.probe_c1 = probe_c1

        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            validated = [c["name"] for c in crits if f"**{c['name']}**" in user] or ["c0", "c1"]
            seen.append(validated)
            self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
            return _fenced({"verdict": "PASS", "failed_criteria": [],
                            "per_criterion": [_entry(n, n != "c1" or self.probe_c1) for n in validated]})

        def tag_last(self, stage):
            self.calls[-1]["stage"] = stage

    first = TL.validate_result(e, "n", _llm=_Validator(probe_c1=False), workdir=".")
    assert first["verdict"] is None, "c1 carried no probe: the first report must be ⊥"
    again = TL.validate_result(e, "n", _llm=_Validator(probe_c1=True), workdir=".")
    assert seen[-1] == ["c1"], f"the retry re-validated {seen[-1]}, not only what was left undecided"
    assert again["verdict"] == "PASS" and {p["criterion"] for p in again["per_criterion"]} == {"c0", "c1"}
    reused = [p for p in again["per_criterion"] if p.get("reused_from_refused")]
    assert [p["criterion"] for p in reused] == ["c0"], "the verdict must say which part it reused"
    e.stop()


def _refused_then_reusable(ledger, entries):
    """A delivered two-criterion node whose last report was refused with `entries` under `ledger`."""
    e = _eng()
    T.create_task(e, "n", {"description": "two criteria",
                           "criteria": [criterion("c0", "criterion 0"), criterion("c1", "criterion 1")]},
                  "alice")
    T.signal(e, "n", "ACCEPT", "alice")
    T.signal(e, "n", "DELIVER", "alice", result="built it")
    e.record_rejected_report("n", "refused", entries, tools_used=ledger)
    return e


def _probed(n, verdict="pass"):
    return {"criterion": n, "verdict": verdict, "evidence": "ran it", "behaviours": ["the criterion holds"],
            "probe": [{"command": pinned(n)[0].command, "expect": "it holds",
                       "behaviour": "the criterion holds"}]}


def test_a_kept_entry_is_held_to_its_own_runs_ledger():
    """A shell in the NEXT run must not vouch for a probe the refused run never executed: the ledger is
    per run, and a union of two ledgers passed a PASS nobody ran (found by an outside reviewer)."""
    e = _refused_then_reusable({"Read": 3}, [_probed("c0"), {"criterion": "c1", "verdict": "pass"}])
    assert e.reusable_from_refused("n") == [], "an entry whose run had no shell was kept"
    e.stop()
    e = _refused_then_reusable({"Bash": 2}, [_probed("c0"), {"criterion": "c1", "verdict": "pass"}])
    assert [x["criterion"] for x in e.reusable_from_refused("n")] == ["c0"]
    e.stop()


def test_a_report_that_refuted_something_is_not_mined():
    """Its refutation never reached the regression set, and half of a self-contradicting report is not
    evidence the other half is sound."""
    e = _refused_then_reusable({"Bash": 1}, [_probed("c0"), _probed("c1", verdict="fail")])
    assert e.reusable_from_refused("n") == []
    e.stop()


def test_a_reused_entry_keeps_the_stamp_of_the_run_that_validated_it_through_a_chain_of_refusals():
    """Refused, refused again, then passed: the entry kept from the FIRST run must still name that run
    and be held to that run's ledger, not to whichever run was refused last."""
    e = _refused_then_reusable({"Bash": 1}, [_probed("c0"), {"criterion": "c1", "verdict": "pass"}])
    first = e.reusable_from_refused("n")
    e.record_rejected_report("n", "refused again", first + [{"criterion": "c1", "verdict": "pass"}],
                             tools_used={"Read": 1}, validated_by={"model": "second"})
    again = e.reusable_from_refused("n")
    assert [x["criterion"] for x in again] == ["c0"], "a later shell-less run dropped a sound entry"
    assert again[0]["reused_from_refused"] == first[0]["reused_from_refused"]
    e.stop()


def test_the_validators_process_cap_is_t_validate(monkeypatch):
    """One clock: the validator's run is capped by VALIDATING's own bound, as the executor's is by its deadline.

    It was the adapter's fixed 900 s, and on the delegated `coreutils` run four validations of rich nodes
    were cut at it mid-stream and came back ⊥."""
    monkeypatch.setenv("GFSO_BOUND_VALIDATING", "4321")
    caps = []

    class _Capped(_ValidatorLLM):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            caps.append(timeout)
            return super().run_agent(system, user, allowed_tools, cwd)

    e = _eng()
    _delivered_node(e)
    TL.validate_result(e, "n1", _llm=_Capped("no report"))
    assert caps and all(4300 <= c <= 4321 for c in caps)
    # …and NO VALIDATOR OUTLIVES THE VISIT: a retry late in the same VALIDATING visit gets what is left
    t = e.graph.get_task(T.TaskId("n1"))
    t.state_entered_at = t.state_entered_at - timedelta(seconds=4000)
    caps.clear()
    TL.validate_result(e, "n1", _llm=_Capped("no report"))
    assert caps and all(c <= 321 for c in caps)
    e.stop()
