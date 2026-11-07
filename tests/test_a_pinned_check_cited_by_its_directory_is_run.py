"""A validator that ran a pinned check and cited it by a spelling the system itself gave the probe — the directory its
inputs were laid down in — ran it: 65 truthful PASS reports over 7 E3 rows were refused as not having run their pinned
checks (`root.wc` five times running), each a validation bought again (2026-10-22)."""
from gfso.core.protocol.procedure import (canonical_citations, inputs_dir_name, pinned_run, probe_id, refuting_probes,
                                         unrun_parts, unrun_pinned)
from gfso.core.types import Criteria, Probe

CRIT = "Statements and control flow"


def _criteria():
    return [Criteria(name=CRIT, description="statements compile and run",
                     check=(Probe(command=". {inputs}/h.sh; r {inputs}/b_stmt.c; echo ok", expect="ok", behaviour="statements run"),))]


def _report(cited: str, crit: str = CRIT):
    return [{"criterion": crit, "verdict": "pass", "evidence": "ran b_stmt.c: ok",
             "probe": [{"id": cited, "command": "cd /tmp/w && . /x/h.sh; r /x/b_stmt.c", "expect": "ok"}]}]


def _pid():
    c = _criteria()[0]
    return probe_id(c.name, c.check[0])


def test_cited_by_its_inputs_directory_or_its_name_with_underscores_it_ran():
    pid = _pid()
    for cited in (inputs_dir_name(pid), f"{inputs_dir_name(CRIT)}#{pid.rsplit('#', 1)[1]}", pid, pid.rsplit("#", 1)[1]):
        assert unrun_pinned(_criteria(), _report(cited)) == {}, cited


def test_another_criterions_directory_is_not_this_ones_run():
    pid = _pid()
    other = inputs_dir_name("Functions and calls#" + pid.rsplit("#", 1)[1])
    assert unrun_pinned(_criteria(), _report(other)) == {CRIT: [pid]}
    assert unrun_pinned(_criteria(), _report("Functions_and_calls#" + pid.rsplit("#", 1)[1])) == {CRIT: [pid]}


PART = "Build and symlinks"


def _parts():
    return {"W": [Criteria(name=f"root.build/{PART}", description="it builds",
                           check=(Probe(command="make -C {inputs} all", expect="ok", behaviour="it builds"),))]}


def _part_pid():
    c = _parts()["W"][0]
    return probe_id(c.name, c.check[0])


def test_a_part_probe_cited_as_its_directory_holds_at_the_whole():
    pid, h = _part_pid(), _part_pid().rsplit("#", 1)[1]
    for cited in (inputs_dir_name(pid), f"root.build/{inputs_dir_name(PART)}_{h}", f"root.build/{inputs_dir_name(PART)}#{h}"):
        report = [{"criterion": "W", "verdict": "pass", "evidence": "built",
                   "probe": [{"id": cited, "held": True, "command": "cd /w && make all", "expect": "ok"}]}]
        assert unrun_parts(_parts(), report) == {"W": [pid]}, "the old reading credits it — the test no longer tests"
        assert unrun_parts(_parts(), canonical_citations(report, [], _parts())) == {}, cited


def test_a_fails_run_of_a_pinned_check_cited_as_its_directory_is_that_check_not_a_finding():
    pid = _pid()
    report = [{"criterion": CRIT, "verdict": "fail", "evidence": "crashed",
               "probe": [{"id": inputs_dir_name(pid), "command": "cd /w && . /x/h.sh; r /x/b_stmt.c", "expect": "ok"}]}]
    found = refuting_probes(canonical_citations(report, _criteria()))[CRIT][0]
    assert pinned_run(found, {pid: _criteria()[0].check[0].command}, CRIT) == pid


def test_a_spelling_two_probes_share_is_left_as_it_came():
    two = [Criteria(name="a, b", description="x", check=(Probe(command="echo 1", expect="1", behaviour="b"),)),
           Criteria(name="a; b", description="y", check=(Probe(command="echo 1", expect="1", behaviour="b"),))]
    shared = inputs_dir_name(probe_id(two[0].name, two[0].check[0]))
    assert shared == inputs_dir_name(probe_id(two[1].name, two[1].check[0]))
    report = [{"criterion": "a, b", "verdict": "pass", "probe": [{"id": shared, "command": "echo 1", "expect": "1"}]}]
    assert canonical_citations(report, two) == report


# …and the doors: the reading lands where a report is recorded, not only in the function (critic, mutation: without
# the calls in `record_exec_verdict` the function's own tests stayed green)
from gfso.core.types import TaskId  # noqa: E402
from tests.test_a_part_is_checked_again_inside_its_whole import (  # noqa: E402
    _entry, _part_pid as _whole_part_pid, _whole_delivered_over_a_passed_part)


def test_at_the_record_a_part_probe_cited_by_its_directory_alone_holds(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _whole_delivered_over_a_passed_part()
    ent = _entry(e, with_part=True, held=True)
    ent["probe"][1] = {"id": inputs_dir_name(_whole_part_pid(e)), "held": True}
    assert e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=[ent])["verdict"] == "PASS"


def test_at_the_record_a_fails_run_of_its_own_pinned_check_cited_by_its_directory_is_no_finding(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _whole_delivered_over_a_passed_part()
    c = e.graph.get_task(TaskId("root")).spec.criteria[0]
    ent = _entry(e, verdict="fail", with_part=True, held=True)
    ent["probe"][0]["id"] = inputs_dir_name(probe_id(c.name, c.check[0]))
    ent["probe"][0]["command"] = "cd /w && " + ent["probe"][0]["command"]
    e.record_exec_verdict("root", "FAIL", [c.name], "validator", per_criterion=[ent])
    assert not e.regression_probes(TaskId("root"))
