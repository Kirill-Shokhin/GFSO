"""A node's own pinned check cited as the packet asks — `{id, held}` with its behaviour, never run again — observes that
behaviour at the record, as a part's citation does: written out with the pinned command and expectation there. Without
it, once a pin no longer carries a criterion by having run, the packet's own citation form was refused (critic over
2b6c6e2)."""
import pytest

from gfso.core.protocol.procedure import probe_id
from gfso.core.types import TaskId
from tests.support import DENIAL_ENTRY, UNMODELLED_FAULT, make_engine
import gfso.tools as T

_C = "parses"
_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
          "invalidation_condition": "one occurs", "p": 0.01, "impact": "x"}, DENIAL_ENTRY]


def _record(probe_of, monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    check = {"command": "python -c \"print('parsed', 1+1)\"", "expect": "parsed 2", "behaviour": "parses holds"}
    T.create_task(e, "root", {"description": "parse", "accepted_risks": _RISK,
                              "criteria": [{"name": _C, "description": "parses holds", "check": [check]}]},
                  assignee="me")
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result="built")
    e.wait_idle()
    entry = {"criterion": _C, "verdict": "pass", "evidence": "the system's run printed parsed 2",
             "behaviours": ["parses holds"], "probe": [probe_of(probe_id(_C, check))], "divergences": []}
    try:
        return e.record_exec_verdict(TaskId("root"), "PASS", [], "validator", per_criterion=[entry],
                                     require_probe=True, tools_used={"Bash": 1})["verdict"]
    finally:
        e.stop()


def test_an_own_pin_cited_by_its_id_alone_observes_its_behaviour(monkeypatch):
    assert str(_record(lambda pid: {"id": pid, "held": True, "behaviour": "parses holds"}, monkeypatch)).upper() \
        .endswith("PASS")


def test_control_an_unlabelled_behaviour_beside_the_citation_is_still_unobserved(monkeypatch):
    with pytest.raises(ValueError, match="unobserved"):
        _record(lambda pid: {"id": pid, "held": True, "behaviour": "something else"}, monkeypatch)
