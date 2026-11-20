"""A TECH REPORT says from whom, to whom and about what, and it can be resolved.

Thirteen reports stood open on the dev graph with nobody able to tell who had sent each to whom and why, and nothing
could close one: a project that runs a year would carry every report it ever got as an open count. So each report
names its author (the signer), its ADDRESSEE (who can act on it), its node and an id; the addressee or the author
resolves it with a reason, and the resolved one stays in the log but leaves every open count and default listing.
Reports stored before this (no id, no addressee) read through the same rule and stay open until resolved."""
from __future__ import annotations

import json

import gfso.tools_llm as TL
from gfso.config import PERSON
from gfso.core.graph.model import TECH_KEY
from gfso.core.types import TaskId
from gfso.engine.moves import SIGNERS
from tests.support import criterion, make_engine


def _graph():
    """root held by exec-1 and issued by alice — a party no registry names, so her own moves are hers to make."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    TL.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("r", "R")]}, "exec-1",
                            agent="alice")
    e.wait_idle()
    assert e.graph.issuer_of(TaskId("root")) == "alice"
    return e


def _stored(e):
    return e.graph.setting(TECH_KEY)


def test_a_report_names_its_author_its_addressee_its_node_and_an_id():
    """On a node, the report goes to the node's issuer — the party whose moves (a ruling, a revise, a reassign, a
    reopen) can give the reporter its move back; with no node, to the person who runs the system."""
    e = _graph()
    on_root = TL.TOOLS["tech_report"](e, "a finding shows no id to dispute it by", task_id="root", actor="exec-2")["filed"]
    loose = TL.TOOLS["tech_report"](e, "a tool cannot run", actor="exec-2")["filed"]
    assert (on_root["actor"], on_root["addressee"], on_root["node"]) == ("exec-2", "alice", "root"), on_root
    assert loose["addressee"] == PERSON and loose["node"] is None, loose
    assert on_root["id"] != loose["id"] and all(r["id"] for r in (on_root, loose))
    e.stop()


def test_a_report_whose_issuer_is_a_machine_goes_to_the_person():
    """A machine role reads no report — no packet carries one back — so addressed to it a report would stand open
    forever; the person, who runs the machine, is the one who can act."""
    e = _graph()
    e.workforce.publish_roster({"alice": "llm-executor"})
    got = TL.TOOLS["tech_report"](e, "the ruling contradicts itself", task_id="root", actor="exec-2")["filed"]
    assert got["addressee"] == PERSON, got
    e.stop()


def test_only_the_addressee_or_the_author_resolves_and_a_refusal_writes_nothing():
    e = _graph()
    rid = TL.TOOLS["tech_report"](e, "an answer ignored what I showed", task_id="root", actor="exec-2")["filed"]["id"]
    before = _stored(e)
    for args in ({"actor": "stranger", "how": "looked at it"}, {"actor": "alice", "how": "  "},
                 {"actor": "alice", "how": "fixed", "report_id": "tr-999"}):
        out = TL.TOOLS["resolve_report"](e, **{"report_id": rid, **args})
        assert out.get("error"), (args, out)
        assert _stored(e) == before, f"a refused resolution wrote: {args}"
    done = TL.TOOLS["resolve_report"](e, rid, "the issuer answered the finding by id", actor="alice")["resolved"]
    assert (done["resolved_by"], done["how"]) == ("alice", "the issuer answered the finding by id") and done["resolved_at"]
    again = _stored(e)
    assert TL.TOOLS["resolve_report"](e, rid, "twice", actor="alice").get("error") and _stored(e) == again
    e.stop()


def test_a_resolved_report_leaves_the_open_count_and_stays_in_the_log():
    e = _graph()
    a = TL.TOOLS["tech_report"](e, "one", task_id="root", actor="exec-2")["filed"]["id"]
    TL.TOOLS["tech_report"](e, "two", actor="exec-2")
    TL.TOOLS["resolve_report"](e, a, "a plan change took the case away", actor="exec-2")    # its own author
    listed = TL.TOOLS["tech_reports"](e)
    assert listed["count"] == 1 and [r["text"] for r in listed["reports"]] == ["two"], listed
    assert listed["resolved_count"] == 1
    whole = TL.TOOLS["tech_reports"](e, resolved=True)
    assert [r["text"] for r in whole["reports"]] == ["one", "two"] and whole["reports"][0]["how"]
    assert len(e.tech_reports()) == 1 and len(e.tech_reports(resolved=True)) == 2
    e.stop()


def test_reports_stored_before_ids_read_whole_open_and_resolvable():
    """The log is append-only, so a report's place in it is its id: the same on every read, old or new."""
    e = _graph()
    old = [{"at": "2026-11-01T10:00:00", "node": "root", "role": "system", "actor": "liveness", "text": "stuck"},
           {"at": "2026-11-01T10:05:00", "node": None, "role": "executor", "actor": "exec-2", "text": "no pytest"}]
    e.graph.store_setting(TECH_KEY, json.dumps(old))
    first, second = e.tech_reports()
    assert (first["id"], first["addressee"]) == ("tr-1", "alice") and (second["id"], second["addressee"]) == ("tr-2", PERSON)
    assert [r["id"] for r in e.tech_reports()] == ["tr-1", "tr-2"], "an id moved between reads"
    new = TL.TOOLS["tech_report"](e, "three", actor="exec-2")["filed"]
    assert new["id"] == "tr-3"
    assert TL.TOOLS["resolve_report"](e, "tr-1", "the question was answered", actor="alice")["resolved"]["id"] == "tr-1"
    assert [r["id"] for r in e.tech_reports()] == ["tr-2", "tr-3"]
    e.stop()


def test_resolving_is_a_signed_move():
    """Who resolves is the call's credential, never its word — as who files (`tech_report.actor`)."""
    assert SIGNERS["resolve_report"] == ("actor",)
