"""validate_node — EXECUTION validation (≠ validate, the PLAN's L2): the read-only validator
INSTRUMENT produces per-criterion evidence; the ISSUER signals PASS/FAIL. Logic tested with a fake
agent-runner (the live run is a headless subprocess)."""
import json

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso import tools as T


def _eng():
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=True)
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

    def run_agent(self, system, user, allowed_tools, cwd=None):
        self.seen = {"system": system, "user": user, "tools": allowed_tools, "cwd": cwd}
        self.calls.append({"duration_ms": 1200, "input_tokens": 500, "output_tokens": 90})
        return self._text

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _delivered_node(e, tid="n1", extra_dep=False):
    T.create_task(e, tid, {"name": "Nail it", "description": "hammer a nail",
                           "criteria": [{"name": "flush", "description": "nail head is flush"},
                                        {"name": "holds", "description": "picture hangs on it"}]}, "alice")
    if extra_dep:
        T.create_task(e, "prod", {"description": "buy nails",
                                  "criteria": [{"name": "nails", "description": "nails exist"}]}, "alice")
        T.add_dependency(e, "prod", tid, glue="uses the bought nails")
    assert T.signal(e, tid, "ACCEPT", "alice")["state"] == "EXECUTING"
    r = T.signal(e, tid, "DELIVER", "alice",
                 result="nail at wall.md:3; flush verified by touch; holds verified with 2kg frame")
    assert r["state"] == "VALIDATING"


def test_validate_node_happy_path_embeds_contract_and_deliver():
    e = _eng()
    _delivered_node(e, extra_dep=True)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "read wall.md"},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "ran check"}],
                                 "seams": "checked prod output", "failed_criteria": []}))
    out = T.validate_node(e, "n1", _llm=llm)
    assert out["verdict"] == "PASS" and out["failed_criteria"] == []
    assert len(out["per_criterion"]) == 2 and out["state"] == "VALIDATING"
    assert out["stats"][-1]["stage"] == "validate_node"
    # the packet is SELF-CONTAINED: contract + seam + the audit-log DELIVER result, read-only tool set
    assert "flush" in llm.seen["user"] and "holds verified with 2kg frame" in llm.seen["user"]
    assert "prod" in llm.seen["user"]                       # seam embedded
    assert "Write" not in llm.seen["tools"] and "Read" in llm.seen["tools"]
    e.stop()


def test_validate_node_fail_report_drives_issuer_fail_signal():
    """The tool never signals; its failed_criteria feed the ISSUER's FAIL → REWORK (Inv-3)."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "FAIL",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "fail", "evidence": "nail bent"},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "held"}],
                                 "failed_criteria": ["flush"]}))
    out = T.validate_node(e, "n1", _llm=llm)
    assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["flush"]
    assert e.get_state(T.TaskId("n1")).name == "VALIDATING"   # instrument did NOT mutate the graph
    r = T.signal(e, "n1", "FAIL", "alice", failed_criteria=out["failed_criteria"])
    assert r["accepted"] and r["state"] == "REWORK"
    e.stop()


def test_validate_node_requires_a_deliverable():
    e = _eng()
    T.create_task(e, "n2", {"description": "x", "criteria": [{"name": "a", "description": "A"}]}, "alice")
    out = T.validate_node(e, "n2", _llm=_ValidatorLLM("irrelevant"))
    assert "error" in out and "DELIVER" in out["error"]
    # explicit deliverable unblocks it (the restart fallback)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "a", "verdict": "pass", "evidence": "ok"}], "failed_criteria": []}))
    out = T.validate_node(e, "n2", deliverable="see out.txt", _llm=llm)
    assert out["verdict"] == "PASS" and "see out.txt" in llm.seen["user"]
    e.stop()


def test_validate_node_unparsed_report_is_never_pass():
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM("I looked at it and it seems fine!")   # no fenced json
    out = T.validate_node(e, "n1", _llm=llm)
    assert out["verdict"] is None and "seems fine" in out["report_text"]
    assert llm.calls[-1]["parse_failed"] is True
    e.stop()


def test_validate_node_unknown_task():
    e = _eng()
    out = T.validate_node(e, "ghost", _llm=_ValidatorLLM(""))
    assert "error" in out
    e.stop()


def test_registry_exposes_validate_node():
    assert "validate_node" in T.TOOLS


def test_mcp_server_binds_validate_node_async():
    """The MCP surface exposes validate_node via the long-running async binding (progress notifications,
    no engine/_-params in the schema)."""
    import pytest
    pytest.importorskip("mcp")
    import asyncio
    from gfso.mcp.server import create_server

    e = _eng()
    server = create_server(e)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert "validate_node" in tools
    props = tools["validate_node"].inputSchema["properties"]
    assert "task_id" in props and "deliverable" in props
    assert "engine" not in props and "_llm" not in props and "_progress" not in props
    e.stop()


def test_self_pass_gate_requires_fresh_independent_verdict():
    """The guinea-pig hole (live 2026-07-04): with collapsed ids (executor == issuer == `agent`) the
    FSM couldn't tell an evidence-based PASS from a self-stamp — 6/8 nodes self-passed on the agent's
    own bash check. Now: PASS where source == Del requires a RECORDED validate_node verdict for the
    CURRENT delivery; a FAIL verdict blocks PASS; a rework stales the record; a DISTINCT issuer
    (source ≠ Del) keeps the canon default."""
    e = _eng()
    _delivered_node(e)                                            # n1, Del=alice, delivered by alice
    r = T.signal(e, "n1", "PASS", "alice")                        # self-stamp, no verdict
    assert r["accepted"] is False and "verifier" in r["error"]
    # a FAIL verdict on record does NOT unlock PASS (that override is the falsification q_V fears)
    llm_fail = _ValidatorLLM(_fenced({"verdict": "FAIL", "per_criterion": [
        {"criterion": "flush", "verdict": "fail", "evidence": "bent"}], "failed_criteria": ["flush"]}))
    T.validate_node(e, "n1", _llm=llm_fail)
    r = T.signal(e, "n1", "PASS", "alice")
    assert r["accepted"] is False and "FAIL" in r["error"]
    # the honest path: FAIL → REWORK → re-deliver → the OLD verdict is stale → re-validate → PASS
    assert T.signal(e, "n1", "FAIL", "alice", failed_criteria=["flush"])["state"] == "REWORK"
    assert T.signal(e, "n1", "DELIVER", "alice", result="fixed")["state"] == "VALIDATING"
    r = T.signal(e, "n1", "PASS", "alice")
    assert r["accepted"] is False and "STALE" in r["error"]
    llm_ok = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ok"}], "failed_criteria": []}))
    T.validate_node(e, "n1", _llm=llm_ok)
    assert T.signal(e, "n1", "PASS", "alice")["state"] == "DONE"
    e.stop()


def test_distinct_issuer_pass_needs_no_verdict_record():
    """source ≠ Del = the separation already exists (canon default): a parent-issuer passes the
    executor's delivered node without the gate."""
    e = _eng()
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [{"name": "g", "description": "G"}]}, "boss")
    T.create_task(e, "kid", {"description": "child",
                             "criteria": [{"name": "k", "description": "K"}]}, "worker",
                  parent_id="par")
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="done")
    assert T.signal(e, "kid", "PASS", "boss")["state"] == "DONE"   # issuer=boss ≠ Del=worker
    e.stop()
