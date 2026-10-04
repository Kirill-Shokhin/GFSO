"""An executor who recorded a verdict without naming himself recorded it as "human".

`record_verdict` defaulted `reviewer="human"`, and the engine's refusal of a reviewer who IS the
node's executor compares names — so an honest executor calling the verb without a name settled the
seam on his own delivery under someone else's. The misattribution was the default path, not a
forgery (the theory stream's review of the root seam, 2026-09-24). An omitted reviewer is now the
door's standing identity, the same one every other act on this surface is signed with.

The control: a party who is NOT the executor, naming themselves, still records.
"""
from __future__ import annotations

import gfso.tools as T
from tests.support import criterion, make_engine


def _a_root_delivered_by_the_standing_agent():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "a goal", "criteria": [criterion("g", "G holds")]},
                  assignee="agent")
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="ran the check for g: it printed ok")
    return e


_SEEN = {"g": {"note": "ran the pinned check", "ran": ["check g"]}}


def test_the_executor_leaving_out_his_name_is_refused_as_himself():
    e = _a_root_delivered_by_the_standing_agent()
    out = T.record_verdict(e, "root", "PASS", observed=_SEEN)
    assert not out.get("recorded"), out
    assert "agent" in out["error"] and "executor" in out["error"], out["error"]
    assert e.current_exec_verdict("root") is None


def test_a_named_other_party_still_records():
    e = _a_root_delivered_by_the_standing_agent()
    out = T.record_verdict(e, "root", "PASS", reviewer="alice", observed=_SEEN)
    assert out.get("recorded"), out
