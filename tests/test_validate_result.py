"""validate_result — EXECUTION validation (≠ validate, the PLAN's L2): the read-only validator
INSTRUMENT produces per-criterion evidence; the ISSUER signals PASS/FAIL. Logic tested with a fake
agent-runner (the live run is a headless subprocess)."""
import json

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso import tools as T
from gfso import tools_llm as TL


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


def test_validate_result_happy_path_embeds_contract_and_deliver():
    e = _eng()
    _delivered_node(e, extra_dep=True)
    # the seam is criteria-content (§10 Dep): `dep__prod` is a CRITERION of this node, so a verdict
    # must speak to it too — a report silent on the seam is ⊥ over the seam (anti-mock has teeth)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "read wall.md", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "ran check", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "dep__prod", "verdict": "pass",
                                      "evidence": "grep: uses the real bought nails, no stub", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}],
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
                                     {"criterion": "holds", "verdict": "pass", "evidence": "held", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": ["flush"]}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["flush"]
    assert e.get_state(T.TaskId("n1")).name == "VALIDATING"   # instrument did NOT mutate the graph
    r = T.signal(e, "n1", "FAIL", "alice", failed_criteria=out["failed_criteria"])
    assert r["accepted"] and r["state"] == "REWORKING"
    e.stop()


def test_validate_result_requires_a_deliverable():
    e = _eng()
    T.create_task(e, "n2", {"description": "x", "criteria": [{"name": "a", "description": "A"}]}, "alice")
    out = TL.validate_result(e, "n2", _llm=_ValidatorLLM("irrelevant"))
    assert "error" in out and "DELIVER" in out["error"]
    # explicit deliverable unblocks it (the restart fallback)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "a", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
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
    A criterion is the obligation (§10 V=⋀cᵢ); ACCEPTED_RISKS (§13.1) holds risks of the decomposition and
    never retires one. The ENGINE refuses to record it (not the prompt): no verdict ⟹ no PASS."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "flush ok", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
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
    """V = AND over ALL criteria: an unevaluated conjunct is ⊥, not pass (§10). A PASS over a
    partially-evaluated contract would silently drop obligations."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}],
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
                                     {"criterion": "holds", "verdict": "pass", "evidence": "held", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": ["holds"]}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] is None and "failed_criteria" in out["verdict_defects"]
    e.stop()


def test_verdict_over_a_foreign_contract_is_not_a_verdict():
    """A report speaking of criteria this node does not have answers another contract."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS",
                                 "per_criterion": [
                                     {"criterion": "flush", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "holds", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
                                     {"criterion": "painted", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}],
                                 "failed_criteria": []}))
    out = TL.validate_result(e, "n1", _llm=llm)
    assert out["verdict"] is None and "painted" in out["verdict_defects"]
    e.stop()


def test_recorded_verdict_carries_the_evidence():
    """§24.5: the Thm 11 trail must show WHAT was verified — a bare verdict cannot be audited post-hoc
    (the live false-PASS could not be diagnosed from the record; the report was gone)."""
    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "measured 0.2mm proud", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "2kg for 24h", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
    TL.validate_result(e, "n1", _llm=llm)
    rec = e.get_exec_verdict(T.TaskId("n1"))
    assert rec["verdict"] == "PASS"
    assert [p["criterion"] for p in rec["per_criterion"]] == ["flush", "holds"]
    assert "0.2mm" in rec["per_criterion"][0]["evidence"]
    e.stop()


def test_validate_result_noops_on_internal_node():
    """D6 (§14.5): independent validation is a SEAM concept. An internal node (same Del as its parent)
    self-verifies — spawning a validator there is pure overhead. Enforced in the engine, not the
    prompt (measured live: a Haiku agent validated every internal child despite being told not to).
    The tool returns a self-verify directive and NEVER spawns the validator."""
    e = _eng()
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]}, "alice")
    T.create_task(e, "kid", {"description": "child",
                             "criteria": [{"name": "k", "description": "K"}]}, "alice", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")   # §13.4: L0-complete plan before executing
    T.signal(e, "kid", "ACCEPT", "alice")
    T.signal(e, "kid", "DELIVER", "alice", result="done; k met")
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "k", "verdict": "pass", "evidence": "x", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
    out = TL.validate_result(e, "kid", _llm=llm)
    assert out.get("internal") is True and out["verdict"] is None
    assert llm.seen is None                         # the validator was NEVER spawned
    assert e.get_exec_verdict(T.TaskId("kid")) is None
    # the internal node still PASSes directly (no gate on a same-Del node)
    assert T.signal(e, "kid", "PASS", "alice")["state"] == "DONE"
    e.stop()


def test_validate_result_still_validates_a_delegation_seam():
    """The counterpart: a child with a DIFFERENT Del is a seam — validation DOES run there."""
    e = _eng()
    T.create_task(e, "par2", {"description": "parent",
                              "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]}, "alice")
    T.create_task(e, "kid2", {"description": "child",
                              "criteria": [{"name": "k", "description": "K"}]}, "bob", parent_id="par2")
    T.map_criterion(e, "par2", "kid2", "g")
    T.signal(e, "kid2", "ACCEPT", "bob")
    T.signal(e, "kid2", "DELIVER", "bob", result="done; k met")
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "k", "verdict": "pass", "evidence": "x", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
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
    import pytest
    pytest.importorskip("mcp")
    import asyncio
    from gfso.mcp.server import create_server

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
        {"criterion": "holds", "verdict": "pass", "evidence": "held", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": ["flush"]}))
    TL.validate_result(e, "n1", _llm=llm_fail)
    r = T.signal(e, "n1", "PASS", "alice")
    assert r["accepted"] is False and "FAIL" in r["error"]
    # the honest path: FAIL → REWORKING → re-deliver → the OLD verdict is stale → re-validate → PASS
    assert T.signal(e, "n1", "FAIL", "alice", failed_criteria=["flush"])["state"] == "REWORKING"
    assert T.signal(e, "n1", "DELIVER", "alice", result="fixed")["state"] == "VALIDATING"
    r = T.signal(e, "n1", "PASS", "alice")
    assert r["accepted"] is False and "STALE" in r["error"]
    llm_ok = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]},
        {"criterion": "holds", "verdict": "pass", "evidence": "held", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
    TL.validate_result(e, "n1", _llm=llm_ok)
    assert T.signal(e, "n1", "PASS", "alice")["state"] == "DONE"
    e.stop()


def test_distinct_issuer_pass_needs_no_verdict_record():
    """source ≠ Del = the separation already exists (canon default): a parent-issuer passes the
    executor's delivered node without the gate."""
    e = _eng()
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]}, "boss")
    T.create_task(e, "kid", {"description": "child",
                             "criteria": [{"name": "k", "description": "K"}]}, "worker",
                  parent_id="par")
    T.map_criterion(e, "par", "kid", "g")   # §13.4: L0-complete plan before executing
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="done")
    assert T.signal(e, "kid", "PASS", "boss")["state"] == "DONE"   # issuer=boss ≠ Del=worker
    e.stop()


def test_record_verdict_closes_the_solo_human_ux_cliff_without_weakening_the_gate():
    """The human counterpart of validate_result: a SELF-executed node's PASS stays rejected until an
    INDEPENDENT reviewer records a verdict (record_verdict) — and the engine REFUSES the executor
    recording one on their own work (the self-stamp would open the gate from the inside)."""
    e = _eng()
    T.create_task(e, "n9", {"description": "solo work",
                            "criteria": [{"name": "a", "description": "A"}]}, "h1")
    T.signal(e, "n9", "ACCEPT", "h1")
    T.signal(e, "n9", "DELIVER", "h1", result="done; a met")
    assert e.get_state(T.TaskId("n9")).name == "VALIDATING"
    assert T.signal(e, "n9", "PASS", "h1")["accepted"] is False      # gate: no recorded verdict

    out = T.record_verdict(e, "n9", "PASS", reviewer="h1")           # executor tries to self-record
    assert out["recorded"] is False and "executor" in out["error"]   # the ENGINE refused

    assert T.record_verdict(e, "n9", "FAIL", reviewer="h2")["recorded"] is False  # Inv-3: criteria-less FAIL

    assert T.record_verdict(e, "n9", "PASS", reviewer="h2")["recorded"] is True   # independent human
    assert T.signal(e, "n9", "PASS", "h1")["accepted"] is True       # gate opens on the RECORD
    assert e.get_state(T.TaskId("n9")).name == "DONE"
    e.stop()



def test_validator_tool_use_is_counted_and_recorded():
    """What the validator DID, beside what it says it did.

    Its verdicts cite executions ("Executed: parse_blocks(...) -> ..."), and four of seven such
    claims in one measured run did not match the artefact they judged. Whether a run opened Bash at
    all is decidable structurally, from the stream, without parsing a word of the report — so it is
    recorded with the verdict and a claim of execution can be checked against it.
    """
    from gfso.adapters.llm.headless import _tool_use_name

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
                                         {"criterion": "holds", "verdict": "pass", "evidence": "hangs", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}],
                          tools_used={"Read": 2})
    rec = e.get_exec_verdict("n1")
    assert rec["tools_used"] == {"Read": 2}
    # the point of recording it: a cited execution with no Bash in the trace is refuted by the trace
    assert "Bash" not in rec["tools_used"] and "Executed" in rec["per_criterion"][0]["evidence"]


def test_a_verdict_with_no_reproducible_probe_is_refused():
    """The instrument must be re-runnable, and the engine — not a prompt — is what insists.

    Measured (`EVIDENCE_LOG` §13.5): replaying the checkable claims of one run against the exact
    snapshot they judged, four of seven described behaviour the artifact did not have. The
    validator's own contract already said "executed evidence outranks judgment"; nothing checked
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
    judgement at the seam, not a machine's re-runnable observation, and holding it to the same rule
    would demand a command line from someone who inspected the thing by hand."""
    e = _eng()
    _delivered_node(e)
    e.record_reviewer_verdict(T.TaskId("n1"), "PASS", [], "human-reviewer")
    assert e.get_exec_verdict(T.TaskId("n1"))["verdict"] == "PASS"


def test_the_validator_runs_where_the_delivery_IS(tmp_path):
    """The working directory it is given must be the one holding the work.

    The fresh-scratch-per-validation fix (a shared scratch had let one run judge another's
    leftovers) made that scratch the validator's working DIRECTORY — so it opened in an empty one,
    could not see the delivery, and failed correct work with "the working directory is empty" as
    its evidence. A false FAIL at the seam is worse than no validation: it returns good work to
    REWORKING and escalates a finished root at the iteration limit. The scratch still exists and is
    still per-validation; it is offered BY NAME, for copies.
    """
    import pathlib

    project = tmp_path / "project"
    project.mkdir()
    (project / "sum.py").write_text("print(42)", encoding="utf-8")

    e = _eng()
    _delivered_node(e)
    llm = _ValidatorLLM(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "read wall.md",
         "probe": {"command": "python sum.py", "expect": "42"}},
        {"criterion": "holds", "verdict": "pass", "evidence": "ran check",
         "probe": {"command": "python sum.py", "expect": "42"}}]}))
    TL.validate_result(e, "n1", workdir=str(project), _llm=llm)

    assert llm.seen["cwd"] == str(project), "the validator was opened away from the delivery"
    assert (project / "sum.py").exists()
    scratch = list((project / ".gfso-scratch").iterdir())
    assert len(scratch) == 1, "a fresh scratch per validation is still made"
    assert str(scratch[0]) in llm.seen["user"], "…and the validator is told where it is"
    assert str(project) in llm.seen["user"]
    e.stop()


def test_internal_model_calls_start_no_mcp_server(monkeypatch):
    """Every internal call (decompose, the Level-2 review, the validator) is a `claude -p` that
    INHERITS the user's MCP configuration — and this installation registers its own door there. Each
    call therefore started the gfso stdio bridge as a child process, each with its own console
    window: measured live, one extra bridge per call without the pin and none with it.

    The window is the visible half. The other half is why hiding it would have been the wrong fix:
    these calls need no gfso tools, and a VALIDATOR holding them could sign the graph it is judging
    (§14.5 verifier ≠ executor). `--strict-mcp-config` with no `--mcp-config` starts nothing."""
    from gfso.adapters.llm.headless import HeadlessClaudeLLM

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

    import subprocess as _sp
    monkeypatch.setattr(_sp, "Popen", _P)
    # The CLI's PRESENCE is not what is under test, and its absence must not decide the verdict:
    # `shutil.which` returning None degrades the provider to a stub that starts no process at all,
    # so no argv is ever built and the flag below is read off an empty list — the assertion then
    # reports a missing pin where the real defect is a missing binary. That is how this test read on
    # a machine with `claude` installed (green) and on a CI runner without it (red), for one and the
    # same correct code. Pinning `which` makes the argv real on both.
    import gfso.adapters.llm.headless as _headless
    monkeypatch.setattr(_headless.shutil, "which", lambda cmd: cmd)
    llm = HeadlessClaudeLLM(model="haiku", claude_cmd="claude")
    try:
        llm.complete("system", "user")
    except Exception:
        pass                      # the transport is faked; only the ARGV is under test
    assert seen.get("args"), \
        "no process was started at all: the argv this test judges was never built"
    assert "--strict-mcp-config" in seen["args"], \
        "an internal call would inherit the user's MCP servers and spawn the gfso bridge"
