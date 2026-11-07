"""A rework round starts clean and is handed its last delivery's own report — a note, not the conversation.

A fresh session re-read the code it had written to find where it stood: 32% of its tool calls before the first edit
(three sql_database rows, 2026-10-21); continuing the whole conversation instead cost more than every fresh round
together (GB_sql_database_tn9nii608)."""
import pytest

import gfso.tools as T
from gfso.packets import HANDOVER_LINES, _executor_packet
from tests.support import DENIAL_ENTRY, UNMODELLED_FAULT, criterion, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
          "invalidation_condition": "one occurs", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY]


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _failed_after(report: str):
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("conf")], "accepted_risks": _RISK},
                  assignee="me")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result=report)
    e.wait_idle()
    T.signal(e, "root", "FAIL", "me", failed_criteria=["conf"])
    e.wait_idle()
    return e


def test_the_rework_packet_carries_the_last_report():
    e = _failed_after("built parser.c and parser_stmt.c\nchecked: make && ./t < stmts.txt -> OK")
    packet = _executor_packet(e, e.graph.get_task("root"), "ws")
    assert "## Your last delivery, as you reported it" in packet
    assert "built parser.c and parser_stmt.c" in packet and "./t < stmts.txt" in packet
    e.stop()


def test_a_long_report_is_handed_as_a_note():
    e = _failed_after("\n".join(f"line {i}" for i in range(HANDOVER_LINES + 25)))
    packet = _executor_packet(e, e.graph.get_task("root"), "ws")
    assert f"line {HANDOVER_LINES - 1}" in packet and f"line {HANDOVER_LINES}\n" not in packet
    assert "(25 more lines of that report)" in packet
    e.stop()
