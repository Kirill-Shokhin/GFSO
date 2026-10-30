"""A child carries the parent's very probe when the issuer names it by id (`carry`): the system copies its command,
expect and pinned inputs WITH their content. The plan gate judges a probe's inputs by content, and the issuer, shown them
by name and count only, could not write the copy where another child already pinned a same-named file (own-plan row 3:
5–8 of 18 root criteria open on "the parent's probe is carried by no child").

CONTROL: drop `_carry` from `_add_child`'s path and the first test goes red (the probe lands with no command)."""
import dataclasses

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


def _carried_by(e, ref):
    return I._carry(e.graph.get_task(TaskId("root")),
                    [{"name": "c", "description": "x", "check": [{"carry": ref, "command": "x", "expect": "x"}]}])


def test_a_probe_named_by_its_hash_alone_or_under_another_name_is_found():
    """The id's identity is its command's hash: a haiku issuer wrote it bare or under a sibling criterion's name and was
    refused 7 times in an hour, the plan held at admission (GB_coreutils_tnq9d1176).
    CONTROL: resolve by the exact id only and both forms are refused."""
    e = _split()
    h = probe_id("g", PARENT).split("#")[1]
    for ref in (f"#{h}", h, f"exit status for every utility#{h}"):
        out, why = _carried_by(e, ref)
        assert not why and out[0]["check"][0]["command"] == PARENT.command, (ref, why)
    e.stop()


def test_a_hash_two_different_probes_share_is_refused():
    """One command pinned under two criteria with different inputs: the hash names neither — refused, the ids listed."""
    e = _split()
    root = e.graph.get_task(TaskId("root"))
    twin = Probe("same command, other corpus", PARENT.command, PARENT.expect, inputs=(("syntax.c", "int y;\n"),))
    e.graph.save_task(dataclasses.replace(root, spec=dataclasses.replace(
        root.spec, criteria=(*root.spec.criteria, Criteria("g2", "again", check=(twin,))))))
    out, why = _carried_by(e, "#" + probe_id("g", PARENT).split("#")[1])
    assert why and probe_id("g2", twin) in why, why
    e.stop()


def test_a_new_criterion_over_checks_already_pinned_is_refused():
    """Ten root criteria over the same probes, each a new name, none deciding more (GB_coreutils_tnq9d1176)."""
    e = _split()
    root = e.graph.get_task(TaskId("root"))
    ok, why = I._add_criterion(e, root, AgentId("lead"), {"criteria": [
        {"name": "g again", "description": "x", "check": [{"carry": probe_id("g", PARENT)}]}]}, "plan", None)
    assert not ok and "already pinned" in why, why
    e.stop()


def test_a_probe_of_a_child_of_the_split_is_carried_by_its_id():
    """A reshape moving `root.head`'s probes onto the child replacing it, by their ids, was refused as "not a probe of
    root" (GB_coreutils_tnqh4a016). CONTROL: `_carry` without `split` and it is refused."""
    e = _split()
    root = e.graph.get_task(TaskId("root"))
    kid = e.graph.get_task(TaskId("root.a")).spec.criteria[0]
    out, why = I._carry(root, [{"name": "moved", "check": [{"carry": probe_id(kid.name, kid.check[0])}]}],
                        I._split_of(e, root))
    got = out[0]["check"][0] if not why else {}
    assert got.get("command") == kid.check[0].command and dict(got.get("inputs") or {}) == dict(kid.check[0].inputs), why
    e.stop()
