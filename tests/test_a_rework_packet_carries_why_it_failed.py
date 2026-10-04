"""A delegated executor sent back to rework is told WHY: the validator's evidence, not the criterion's name alone.

Measured live (AUTO json_parser, 2026-09-27): the packet named the failed criteria and nothing else, so the
executor re-ran its packet's own checks, found them green and re-delivered the unchanged file three rounds in a
row — the validator's refuting probe never reached it. The engine's `rework_findings` is the one owner; the
human door's directive already read it.

CONTROL: drop `rework_findings` from the packet, or render the stored (one-lined) command, and these go red.
"""
import pytest

from gfso import packets
from gfso.core.protocol.procedure import probe_id
from gfso.issuer import _what_happened
from gfso.issuer import _what_happened
from gfso.core.types import AgentId, Criteria, CriterionMapping, Signal, SignalData, Spec, TaskId
from tests.support import REGISTER_SPLIT, make_engine, pinned, REGISTER_ITEMS


PROBE = "python - <<'EOF'\nfrom json_parser import parse\nprint(parse('1' * 5000))\nEOF"


def _failed_leaf():
    """leaf delivered and FAILED on number_grammar, the refuting probe a multi-line heredoc."""
    e = make_engine()
    e.start()
    e.assign_task(TaskId("root"), Spec("a parser", (Criteria("g", "parses", check=pinned("g")),),
                                       accepted_risks=REGISTER_ITEMS), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("leaf"), Spec("parse numbers", (Criteria(
        "number_grammar", "RFC 8259 numbers", check=pinned("number_grammar")),)), AgentId("w"))],
        criterion_mappings=[CriterionMapping("g", TaskId("leaf"))], register=REGISTER_SPLIT)
    e.wait_idle()
    for sd in (SignalData(signal=Signal.ACCEPT, task_id=TaskId("leaf"), source=AgentId("w")),
               SignalData(signal=Signal.DELIVER, task_id=TaskId("leaf"), source=AgentId("w"), result="done")):
        e.send_signal(sd)
        e.wait_idle()
    e.record_exec_verdict(TaskId("leaf"), "FAIL", ["number_grammar"], "validate_result",
                          per_criterion=[{"criterion": "number_grammar", "verdict": "fail",
                                          "evidence": "int(text) rejects a 5000-digit integer",
                                          "probe": [{"behaviour": "arbitrary precision", "command": PROBE,
                                                     "expect": "ValueError: Exceeds the limit"}]}])
    e.send_signal(SignalData(signal=Signal.FAIL, task_id=TaskId("leaf"), source=AgentId("pm"),
                             failed_criteria=("number_grammar",)))
    e.wait_idle()
    return e


def test_the_rework_packet_carries_what_the_validator_observed_and_the_probe_as_written():
    """A multi-line probe reaches the executor as it was written — the regression store keeps it one-lined, which
    no shell runs (critic, 2026-09-27)."""
    e = _failed_leaf()
    packet = packets._executor_packet(e, e.graph.get_task(TaskId("leaf")), "ws")
    assert "## REWORKING" in packet and "int(text) rejects a 5000-digit integer" in packet, packet
    assert "from json_parser import parse\n" in packet and "print(parse('1' * 5000))" in packet, packet
    e.stop()


def test_a_new_contract_after_a_fail_carries_why_the_earlier_one_failed():
    """A re-ASSIGN (an escalation's, a raised bound) starts a new version: the FAIL is history, but the next PASS
    re-runs every probe that refuted it — the packet named the criteria alone (critic, 2026-09-27)."""
    e = _failed_leaf()
    leaf = e.graph.get_task(TaskId("leaf"))
    e.revise(TaskId("leaf"), leaf.spec, AgentId("pm"), reason=None)
    e.wait_idle()
    e.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId("leaf"), source=AgentId("w")))
    e.wait_idle()
    packet = packets._executor_packet(e, e.graph.get_task(TaskId("leaf")), "ws")
    assert "An earlier version of this contract was FAILED" in packet
    assert "int(text) rejects a 5000-digit integer" in packet and "print(parse('1' * 5000))" in packet, packet
    e.stop()



def _failed_then_revised(probe, evidence: str, check: tuple):
    """leaf FAILED on number_grammar by `probe`, then its issuer revised that criterion to pin `check`; re-ACCEPTed."""
    e = make_engine()
    e.start()
    e.assign_task(TaskId("root"), Spec("a parser", (Criteria("g", "parses", check=pinned("g")),),
                                       accepted_risks=REGISTER_ITEMS), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("leaf"), Spec("parse numbers", (Criteria(
        "number_grammar", "RFC 8259 numbers", check=pinned("number_grammar")),)), AgentId("w"))],
        criterion_mappings=[CriterionMapping("g", TaskId("leaf"))], register=REGISTER_SPLIT)
    e.wait_idle()
    for sd in (SignalData(signal=Signal.ACCEPT, task_id=TaskId("leaf"), source=AgentId("w")),
               SignalData(signal=Signal.DELIVER, task_id=TaskId("leaf"), source=AgentId("w"), result="done")):
        e.send_signal(sd)
        e.wait_idle()
    e.record_exec_verdict(TaskId("leaf"), "FAIL", ["number_grammar"], "validate_result",
                          per_criterion=[{"criterion": "number_grammar", "verdict": "fail", "evidence": evidence,
                                          "probe": probe if isinstance(probe, list) else [probe]}])
    e.send_signal(SignalData(signal=Signal.FAIL, task_id=TaskId("leaf"), source=AgentId("pm"),
                             failed_criteria=("number_grammar",)))
    e.wait_idle()
    leaf = e.graph.get_task(TaskId("leaf"))
    e.revise(TaskId("leaf"), Spec(leaf.spec.name, (Criteria("number_grammar", "RFC 8259 numbers, reworded",
                                                            check=check),)), AgentId("pm"), reason=None)
    e.wait_idle()
    e.send_signal(SignalData(signal=Signal.ACCEPT, task_id=TaskId("leaf"), source=AgentId("w")))
    e.wait_idle()
    return e, packets._executor_packet(e, e.graph.get_task(TaskId("leaf")), "ws")


#: the run of the pinned probe as a verdict files it: under the probe's bare hash
PINNED_RUN = {"id": probe_id("number_grammar", pinned("number_grammar")[0]).rsplit("#", 1)[-1],
              "behaviour": "number_grammar holds", "command": "check number_grammar", "expect": "it holds"}


def test_a_fail_by_a_pinned_probe_the_revision_withdrew_is_no_order():
    """FAILED by its pinned probe, then the issuer replaced that probe: its refutation was of the probe
    (`without_pinned_runs`), and no ruling can retire a withdrawn probe's run. Shown as an order, it was disputed a dozen
    times per row (AUTO haiku coreutils, root.build, 2026-10-12). CONTROL: keep withdrawn runs in `rework_findings` —
    the old evidence is back."""
    e, packet = _failed_then_revised(PINNED_RUN, "DIFF: the old pinned check failed", pinned("number_grammar_on_stubs"))
    assert "DIFF: the old pinned check failed" not in packet and "An earlier version" not in packet, packet
    assert "check number_grammar_on_stubs" in packet, packet
    said = "\n".join(_what_happened(e, e.graph.get_task(TaskId("leaf"))))
    assert "DIFF: the old pinned check failed" not in said and "binds the next PASS" in said, said
    e.stop()


def test_a_reworded_criterion_keeps_why_its_pinned_probe_failed():
    """Only the description changed, the pinned probe stands: what it observed still binds the delivery — dropped, the
    executor re-delivered the unchanged file on its green checks (2026-09-27; critic over the first cut of this fix,
    which keyed on the criterion's text)."""
    e, packet = _failed_then_revised(PINNED_RUN, "DIFF: the pinned check failed", pinned("number_grammar"))
    assert "An earlier version" in packet and "DIFF: the pinned check failed" in packet, packet
    e.stop()


def test_a_finding_of_the_validator_outlives_the_withdrawn_probe():
    """The validator's own probe stands — the next PASS re-runs it — so its observation and command stay."""
    e, packet = _failed_then_revised({"behaviour": "arbitrary precision", "command": PROBE,
                                      "expect": "ValueError: Exceeds the limit"},
                                     "int(text) rejects a 5000-digit integer", pinned("number_grammar_on_stubs"))
    assert "An earlier version" in packet and "int(text) rejects a 5000-digit integer" in packet, packet
    assert "print(parse('1' * 5000))" in packet, packet
    e.stop()


def test_a_failure_mixing_a_withdrawn_run_with_a_finding_of_its_own_keeps_what_binds():
    """The rows' real FAIL: the withdrawn pinned probe AND the validator's own probe. The own one still binds, so what
    was observed stays, and the issuer is not told "not demanded" (critic over the second cut of this fix)."""
    e, packet = _failed_then_revised([PINNED_RUN, {"behaviour": "arbitrary precision", "command": PROBE,
                                                   "expect": "ValueError: Exceeds the limit"}],
                                     "int(text) rejects a 5000-digit integer", pinned("number_grammar_on_stubs"))
    assert "int(text) rejects a 5000-digit integer" in packet and "print(parse('1' * 5000))" in packet, packet
    assert "  check number_grammar\n" not in packet, packet
    assert "settled, NOT demanded" in packet and PINNED_RUN["id"] in packet, packet
    said = "\n".join(_what_happened(e, e.graph.get_task(TaskId("leaf"))))
    assert "not demanded" not in said and "int(text) rejects" in said, said
    e.stop()


@pytest.mark.parametrize("probe", [{"behaviour": "number_grammar holds", "command": "check number_grammar",
                                    "expect": "it holds"},
                                   {"behaviour": "number_grammar holds", "command": "check number_grammar", "id": "p1",
                                    "expect": "it holds"},
                                   {"behaviour": "number_grammar holds"}])
def test_a_probe_matched_by_nothing_still_binds(probe):
    """A pinned probe of the version in force reported without our id, or a probe with no command: nothing identifies
    it as released, so it binds as the gate reads it — hidden, the executor got a bare name (critic r4: 4 of 5 shapes)."""
    e, packet = _failed_then_revised(probe, "DIFF: the pinned check failed", pinned("number_grammar"))
    assert "An earlier version" in packet and "DIFF: the pinned check failed" in packet, packet
    said = "\n".join(_what_happened(e, e.graph.get_task(TaskId("leaf"))))
    assert "not demanded" not in said, said
    e.stop()
