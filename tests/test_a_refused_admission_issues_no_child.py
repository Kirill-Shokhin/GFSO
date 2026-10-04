"""A split is admitted whole or not at all (§11.5), and the issuer's pre-fill reaches whoever works and validates.

Critic r5 over the corner-9 branch: (1) a later child's packet refused INSIDE the issuing loop left the earlier ones
issued under a split no battery had admitted; (2) with the register read off the split alone, an issuer's pre-filled
ACCEPTED_RISKS on a leaf — a packet field it forms (§10.1) — reached no executor and no validator.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import TaskId
from gfso.packets import _executor_packet
from gfso.packets import _validator_packet
from tests.support import REGISTER, criterion, make_engine

_EXCLUSION = {"item": "IE11 is not supported", "predictability": "EXTRAORDINARY",
              "justification": "out of the goal", "invalidation_condition": "the goal names IE11"}


def test_a_later_childs_refused_packet_leaves_no_earlier_child_issued():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")]}, "me")
    e.wait_idle()
    with pytest.raises(ValueError):
        T.decompose(e, "root", [
            {"task_id": "g", "spec": {"description": "pinned", "criteria": [criterion("g_ok", "G")]},
             "assignee": "me", "covers": ["a"]},
            {"task_id": "u", "spec": {"description": "pins nothing", "criteria": [{"name": "u_ok", "description": "U"}]},
             "assignee": "me", "covers": ["b"]}], accepted_risks=REGISTER)
    e.wait_idle()
    assert e.graph.get_task(TaskId("g")) is None and not e.graph.get_active_children(TaskId("root"))
    e.stop()


def test_the_issuers_pre_fill_on_a_leaf_reaches_its_executor_and_its_validator():
    e = make_engine()
    e.start()
    T.create_task(e, "leaf", {"description": "a page", "criteria": [criterion("renders", "it renders")],
                              "accepted_risks": [_EXCLUSION]}, "me")
    e.wait_idle()
    task = e.graph.get_task(TaskId("leaf"))
    assert "IE11 is not supported" in _executor_packet(e, task, None)
    assert "IE11 is not supported" in _validator_packet(e, task, "it renders", None)
    e.stop()
