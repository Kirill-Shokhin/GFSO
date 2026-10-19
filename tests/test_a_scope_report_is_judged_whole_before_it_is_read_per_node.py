"""A report over several nodes is judged WHOLE before it is read per node; each node's failed list is its own entries'.

Critic V1 over the one validation pass (D-F2): reading a scope report node by node, a report that said FAIL while every
entry passed — naming nothing, or naming what is no criterion — gave every node a PASS claim, and the project closed
DONE on a report that decided nothing (Inv-3: a FAIL names its failed criteria; §2.3: ⊥ is not pass). And taking a
node's failed list from the report's bare names refused a correct PASS wherever two nodes share a criterion name —
two consumers of one producer both carry `dep__<producer>`.
"""
from __future__ import annotations

import pytest

import gfso.delegate as D
import gfso.tools as T
import gfso.tools_llm as TL
import tests.test_one_session_carries_a_scope as S
from gfso.core.types import AgentId, Mode, State, TaskId
from gfso.decompose.build import build_graph_live
from gfso.roster import AgentRegistry
from tests.support import REGISTER, criterion, make_engine


class _Says(S._LLM):
    """A scope validator answering with `report()` over whatever waits in VALIDATING."""

    def __init__(self, report):
        super().__init__()
        self._report = report

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.packets.append(user)
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return self._report()


@pytest.mark.parametrize("listed", [[], ["zz"]])
def test_a_fail_naming_nothing_any_entry_failed_decides_nothing_for_every_node(tmp_path, listed):
    e, agents = S._project(tmp_path)

    def report():
        ents = [x for t in e.all_tasks() if t.state == State.VALIDATING for x in S._entries(e, t)]
        return S._fenced({"verdict": "FAIL", "per_criterion": ents, "failed_criteria": listed,
                          "seams": "b does not read what a wrote"})
    validator = _Says(report)
    S._drive(e, S._dispatcher(e, agents, S._LLM(*[S._delivered("root.a", "root.b", "root")] * 4), validator, []),
             lambda: (e.rejected_report(TaskId("root")) or {}).get("defects"), rounds=150)
    assert {t: e.graph.get_state(TaskId(t)).name for t in S._NODES} == {t: "VALIDATING" for t in S._NODES}
    e.stop()


def _two_consumers_of_one_producer(tmp_path):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid, kind in (("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("val-1", "llm-validator")):
        agents.register(aid, kind, workdir=str(tmp_path), project="p")
    D.publish_the_workforce(e, agents.list())
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    T.create_task(e, "root", {"description": "the goal", "accepted_risks": REGISTER, "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    kid = lambda i: {"id": i, "name": i, "description": f"part {i}", "volume": "~40 lines, 2 checks",
                     "fits_one_session": True, "criteria": [criterion(f"{i}_ok", f"{i} holds")]}
    build_graph_live({"name": "g", "root_criteria": [criterion("g", "G holds")], "subtasks": [kid("a"), kid("b"), kid("c")],
                      "mappings": [{"criterion": "g", "child_id": x} for x in "abc"],
                      "deps": [{"from": "a", "to": "b", "glue": "b reads a"}, {"from": "a", "to": "c", "glue": "c reads a"}],
                      "accepted_risks": REGISTER, "scope": [], "whole_volume": "~120 lines", "whole_fits_one_session": True},
                     "the goal", e, assignee=str(e.graph.get_task(TaskId("root")).assignee))
    e.wait_idle()
    return e, agents


def test_a_shared_criterion_name_fails_only_the_node_whose_entry_failed(tmp_path):
    e, agents = _two_consumers_of_one_producer(tmp_path)
    S._drive(e, S._dispatcher(e, agents, S._LLM(S._delivered("root.a", "root.b", "root.c", "root")), S._NeverAnswers(), []),
             lambda: e.graph.get_state(TaskId("root")) == State.VALIDATING, rounds=60)
    for tid in ("root", "root.a", "root.b", "root.c"):
        e.claims.end_validation(S._free_claim(e, tid))

    def report():
        ents = [x for t in e.all_tasks() if t.state == State.VALIDATING for x in S._entries(e, t, {("root.b", "dep__a")})]
        return S._fenced({"verdict": "FAIL", "per_criterion": ents, "failed_criteria": ["dep__a"]})
    out = TL.validate_scope(e, "root", None, "val-1", _llm=_Says(report))
    assert (out["verdicts"]["root.b"]["verdict"], out["verdicts"]["root.c"]["verdict"]) == ("FAIL", "PASS")
    e.stop()
