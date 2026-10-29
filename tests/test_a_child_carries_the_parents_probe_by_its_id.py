"""A child carries the parent's very probe when the issuer names it by id (`carry`): the system copies its command,
expect and pinned inputs WITH their content. The plan gate judges a probe's inputs by content, and the issuer, shown them
by name and count only, could not write the copy where another child already pinned a same-named file (own-plan row 3:
5–8 of 18 root criteria open on "the parent's probe is carried by no child").

CONTROL: drop `_carry` from `_add_child`'s path and the first test goes red (the probe lands with no command)."""
from gfso import issuer as I
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import AgentId, Criteria, CriterionMapping, Probe, Signal, SignalData, Spec, TaskId
from tests.support import REGISTER_SPLIT, REGISTER_ITEMS, make_engine, pinned

PARENT = Probe("rejects bad.c", "./cc {inputs}/syntax.c && echo ACCEPTED", "ACCEPTED",
               inputs=(("syntax.c", "int main(void){ return 0; }\n"),))


def _split():
    e = make_engine()
    e.start()
    e.assign_task(TaskId("root"), Spec("a compiler", (Criteria("g", "compiles", check=(PARENT,)),),
                                       accepted_risks=REGISTER_ITEMS), AgentId("lead"))
    e.wait_idle()
    e.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=AgentId("lead")))
    e.wait_idle()
    other = Probe("its own", "./cc {inputs}/syntax.c && echo ACCEPTED", "ACCEPTED",
                  inputs=(("syntax.c", "int x;\n"),))        # the SAME name, another content: by name it is ambiguous
    e.decompose_task(TaskId("root"), [(TaskId("root.a"), Spec("part a", (Criteria("ga", "a", check=(other,)),)),
                                       AgentId("w"))],
                     criterion_mappings=[CriterionMapping("g", TaskId("root.a"))], register=REGISTER_SPLIT)
    e.wait_idle()
    return e


def test_a_named_probe_is_copied_with_its_inputs_content():
    e = _split()
    pid = probe_id("g", PARENT)
    ok, why = I._add_child(e, e.graph.get_task(TaskId("root")), AgentId("lead"),
                           {"child": {"name": "carrier", "covers": ["g"], "criteria": [
                               {"name": "g_carried", "description": "the parent's probe",
                                "check": [{"carry": pid, "behaviour": "x", "command": "x", "expect": "x"}]}]}},
                           "repair", None)
    assert ok, why
    got = e.graph.get_task(TaskId("root.carrier")).spec.criteria[0].check[0]
    assert (got.command, got.expect, dict(got.inputs)) == (PARENT.command, PARENT.expect, dict(PARENT.inputs))
    e.stop()


def test_an_id_naming_no_probe_of_the_node_is_refused_with_the_ids():
    e = _split()
    ok, why = I._add_child(e, e.graph.get_task(TaskId("root")), AgentId("lead"),
                           {"child": {"name": "carrier", "covers": ["g"], "criteria": [
                               {"name": "g_carried", "description": "x",
                                "check": [{"carry": "g#deadbeef", "behaviour": "x", "command": "x", "expect": "x"}]}]}},
                           "repair", None)
    assert not ok and probe_id("g", PARENT) in why, why
    e.stop()


def test_the_issuer_is_shown_each_probe_by_its_id():
    assert probe_id("g", PARENT) in I.crit_block(Criteria("g", "compiles", check=(PARENT,)))


def test_a_probe_kept_by_its_id_in_a_restated_contract_is_the_stored_one():
    """The same field reaches the node's own contract (an accepted dispute, a reassign): a placeholder command beside a
    `carry` was taken as the probe and the node re-pinned to nothing (critic over 8db23d6)."""
    e = _split()
    root = e.graph.get_task(TaskId("root"))
    spec = I.spec_with(root, [{"name": "g", "description": "compiles",
                               "check": [{"carry": probe_id("g", PARENT), "behaviour": "x", "command": "(carried)",
                                          "expect": "(carried)"}]}])
    got = spec.criteria[0].check[0]
    assert (got.command, dict(got.inputs)) == (PARENT.command, dict(PARENT.inputs))
    e.stop()
