"""What a person's page needs from the engine to be their door: the graph's PARTIES — every holder and every issuer, with
who makes its moves (`party_kind`) — so it offers a person their own name and knows whether the system holds anything;
and, on a whole, the pinned checks of the DONE parts each criterion rests on, which a verdict by hand must name as run
or the engine refuses it (ui critic, 2026-11-14: a decomposed root could not be closed by hand from the page).

CONTROLS: drop `parties` from `graph_read` and the first test goes red; drop `part_probes` from `task_out` and the
second does."""
from gfso import tools as T
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import TaskId
from tests.support import REGISTER, criterion, instrument_passes, make_engine


def test_the_graph_read_names_every_holder_and_issuer_with_who_moves_for_it():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]}, assignee="alice")
    T.decompose(e, "root", [{"task_id": "root.a", "assignee": "bob", "covers": ["g"],
                             "spec": {"description": "a", "criteria": [criterion("a")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    got = {p["name"]: p["kind"] for p in T.graph_read(e)["parties"]}
    assert {"alice", "bob"} <= set(got) and got["bob"] == "person", got
    assert str(e.graph.issuer_of(TaskId("root"))) in got          # the goal's issuer is a party too


def test_a_whole_names_the_pinned_checks_of_its_done_parts():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]}, assignee="alice")
    T.decompose(e, "root", [{"task_id": "root.a", "assignee": "bob", "covers": ["g"],
                             "spec": {"description": "a", "criteria": [criterion("a")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "root.a", "ACCEPT", "bob")
    T.signal(e, "root.a", "DELIVER", "bob", result="done")
    instrument_passes(e, TaskId("root.a"))
    T.signal(e, "root.a", "PASS", str(e.graph.issuer_of(TaskId("root.a"))))
    e.wait_idle()
    part = e.graph.get_task(TaskId("root.a")).spec.criteria[0]
    crit = T.task_out(e.graph.get_task(TaskId("root")), e)["criteria"][0]
    # the engine names a part's probe under the part (`root.a/a#…`), the name its refusal asks a verdict to account for
    assert [p["id"] for p in crit.get("part_probes", [])] == [probe_id(f"root.a/{part.name}", p) for p in part.check], crit
