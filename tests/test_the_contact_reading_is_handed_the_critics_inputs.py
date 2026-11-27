"""The contact reading (B) is handed the kit critic's inputs and nothing of the check's bookkeeping, and what it claims
is shown to the check (A) as a claim to test (design §B.1, §B.4).

Measured (replay r3, sonnet): the critic, handed the goal, the delivery and its diff, found and probed the defect 2/2 in
8–9 tool calls; the validator, handed the same plus a per-criterion form, the system's green pin runs and the report
schema, named it 2/4 and never probed — it cited the runs into the form and stopped. So B gets the goal, the person's
words, the criteria as prose and the change, and not the form, the pins, their runs or the executor's report; A loses
question 1 and the bold `outside` line wherever B's reading stands, and keeps both where none does."""
from __future__ import annotations

import gfso.packets as P
import gfso.validate as VAL
from gfso.core.protocol.invariants import INTENT
from gfso.core.types import TaskId
from tests.test_a_small_task_takes_the_canons_acts import ASKED, WORDS, _filled, _set_up, chat, pytestmark

__all__ = ["chat", "pytestmark"]

QUESTION_1 = "Does the delivery answer the goal?"
OUTSIDE_LINE = "What the goal needs that no criterion writes fails nothing"


def test_with_a_contact_reading_the_check_is_asked_neither_question_1_nor_the_outside_line():
    with_b, alone = VAL._validator_prompt(whole=False), VAL._validator_prompt(whole=True)
    assert QUESTION_1 not in with_b and OUTSIDE_LINE not in with_b, with_b
    assert QUESTION_1 in alone and OUTSIDE_LINE in alone, alone
    for kept in ("per written criterion", "Pinned checks are the system's"):
        assert kept in with_b and kept in alone, kept
    assert "<!--" not in with_b + alone, "a marker of the block reached the prompt"


def _the_go(call, repo):
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)


def test_the_contact_packet_holds_the_critics_inputs_and_none_of_the_checks(chat):
    e, repo, call, _ = chat
    _the_go(call, repo)
    task = e.graph.get_task(TaskId("root"))
    assert INTENT in [c.name for c in task.spec.criteria]
    changed = P.change_text("c" * 40, "b" * 40, ("f.txt | 1 +", "+v1"))
    text = P.contact_packet(e, [task], str(repo), str(repo.parent / "scratch"), {"root": changed})
    for held in (task.spec.description, ASKED, WORDS, "+v1", *(c.description for c in task.spec.criteria)):
        assert held in text, held
    pins = [p.command for c in task.spec.criteria for p in c.check or () if p.command]
    assert pins and not any(f"`{p}`" in text for p in pins), "a pinned check reached the contact reading"
    for absent in ("the system ran", "DELIVER report", "RULED OUT", "per_criterion", "ACCEPTED_RISKS", "`quote`"):
        assert absent not in text, absent


def _row(**kw) -> dict:
    return {"row": "r1", "id": "says_v1#0badc0de", "what": "f.txt holds v2", "evidence": "cat f.txt printed v2",
            "by": "contact", "bears_on": "says_v1", "node": "root", "probe": {"command": "cat f.txt", "expect": "v2"},
            **kw}


def test_the_checks_packet_shows_a_contact_claim_under_its_id_never_as_owed(chat):
    e, repo, call, _ = chat
    _the_go(call, repo)
    task = e.graph.get_task(TaskId("root"))
    text = P.validator_packet(e, task, "f.txt written", str(repo), contact=[_row()])
    assert "CONTACT [says_v1#0badc0de]" in text and "not demanded" in text, text
    assert "cat f.txt" in text.split("CONTACT [says_v1#0badc0de]")[1].split("\n")[0]
    owed = [pid for _, items in P.owed_probes(e, task, task.spec.criteria) for pid, _ in items]
    assert "says_v1#0badc0de" not in owed and not any("r1" in str(p) for p in owed), owed
    assert "CONTACT [" not in P.validator_packet(e, task, "f.txt written", str(repo)), "a claim shown with none filed"
