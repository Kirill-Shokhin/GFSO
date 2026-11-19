"""Under `solo` and `semi` the root's verdict is the person's (§10.1: its issuer is them). The line saying so stood on the
feed alone, while the DELIVER's `awaiting_verdict`, `next_steps` and `get_verdict` all told the client "you sign" — it
signed the root itself and was stopped as self-approval (fresh client s22). Every text the client reads says: show the
person the validator's verdict on each criterion, with what it observed, ask, sign with their words."""
from __future__ import annotations

from gfso import tools_llm as TL
from gfso.core.types import Mode, TaskId
from tests.test_a_solo_chat_writes_its_own_plan_and_the_person_gives_the_go import ASKED, _filled, _gone, no_model  # noqa: F401
from tests.test_the_mode_decides_who_holds_what import _engine

NOTE = "printed 2 for two lines"


def _validating():
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    delivered = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="wc2", self_validation="PASS")
    e.wait_idle()
    c = e.graph.get_task(TaskId("root")).spec.criteria[0]
    e.record_exec_verdict(TaskId("root"), "PASS", [], "val", per_criterion=[
        {"criterion": c.name, "verdict": "pass", "evidence": NOTE,
         "probe": [{"behaviour": p.behaviour, "command": p.command, "expect": p.expect} for p in c.check]}])
    return e, delivered


def _asks_the_person(said: str) -> None:
    assert "the person's" in said and "user_said" in said and "YOU sign" not in said, said


def test_the_deliver_answer_asks_the_person(no_model):
    _, delivered = _validating()
    _asks_the_person(delivered["awaiting_verdict"])


def test_next_steps_asks_the_person_with_what_the_validator_saw(no_model):
    e, _ = _validating()
    said = str(TL.TOOLS["next_steps"](e))
    _asks_the_person(said)
    assert NOTE in said, said


def test_get_verdict_says_it_too(no_model):
    e, _ = _validating()
    out = TL.TOOLS["get_verdict"](e, "root")
    _asks_the_person(out.get("say", ""))
    assert NOTE in out["say"]


def test_an_auto_root_is_not_the_persons_to_sign_here():
    e = _engine(Mode.AUTO)
    assert e.persons_verdict(TaskId("root")) == ""
