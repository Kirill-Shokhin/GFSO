"""Where the person holds the root's work (solo or semi, `in_chat`), the go of a plan adds a root criterion of the
system's own, `answers_the_persons_words`: the validator reads the result against the person's recorded words — the goal
as given, their words at the go and on later acts, the agreed plan — and its FAIL stands only on a span of them, quoted,
matched as `beyond_the_request` matches (case, ё/е, punctuation folded). The author, 2026-11-19: «почему для соло
инчат нельзя добавлять критерий соответствует замыслу юзера? галочкой блин в ui и по умолчанию». Switchable
(`set_mode(intent_check=)`); the person's disagreement with a FAIL is their revision of this criterion's text."""
from __future__ import annotations

import pytest

from gfso import tools_llm as TL
from gfso.core.protocol.invariants import verdict_report_defects
from gfso.core.types import AgentId, Mode, TaskId
from gfso.decompose import artifact as A
from gfso.packets import _validator_packet
from tests.test_a_solo_chat_writes_its_own_plan_and_the_person_gives_the_go import ASKED, _filled, no_model  # noqa: F401
from tests.test_the_go_only_adds_to_the_plan import GOAL, _plan
from tests.test_the_mode_decides_who_holds_what import _engine

INTENT = "answers_the_persons_words"
SAID = "да, всё так — и пусть ещё считает пустые строки"


def _gone(intent=None, text=None, said=SAID):
    e = _engine(Mode.SOLO)
    if intent is not None:
        assert not TL.set_mode(e, intent_check=intent, user_said="переключи проверку замысла").get("refused")
    out = TL.auto_decompose(e, plan=text or _filled(TL.plan(e, ASKED)["text"]), user_said=said)
    return e, e.graph.get_task(TaskId(out["root_id"]))


def _names(task):
    return [c.name for c in task.spec.criteria]


def test_a_solo_chats_go_adds_the_persons_words_by_default(no_model):
    e, root = _gone()
    assert _names(root) == ["counts", INTENT], _names(root)
    assert root.spec.criteria[1].description == TL.INTENT_CRITERION["description"], "the system's text, not the plan's"
    assert not root.spec.criteria[1].check[0].exact, "judged by the validator"


def test_the_switch_off_leaves_it_out(no_model):
    _, root = _gone(intent=False)
    assert _names(root) == ["counts"]


def test_off_where_the_system_holds_the_root_unless_set(no_model):
    e = _engine(Mode.AUTO)
    assert not TL.intent_check(e)
    TL.set_mode(e, intent_check=True, user_said="проверяй замысел")
    assert TL.intent_check(e)


def test_the_mode_read_says_the_switch_in_force_set_or_not(no_model):
    """The page reads the mode: a key left unset must still say what the go will do (ui, 11-19)."""
    solo, auto = _engine(Mode.SOLO), _engine(Mode.AUTO)
    assert solo.mode()["intent_check"] is TL.intent_check(solo) is True, solo.mode()
    assert auto.mode()["intent_check"] is False and "intent_check" not in (auto.mode().get("settings") or {})
    TL.set_mode(solo, intent_check=False, user_said="не проверяй замысел")
    assert solo.mode()["intent_check"] is False


def test_the_switch_turns_only_on_the_persons_words(no_model):
    e = _engine(Mode.SOLO)
    out = TL.set_mode(e, intent_check=False)
    assert out.get("refused") and "user_said" in out["error"] and TL.intent_check(e), out


def test_a_plan_cannot_own_the_criterion(no_model):
    e = _engine(Mode.SOLO)
    own = {"name": INTENT, "description": "always holds",
           "check": [{"behaviour": "a commit", "command": "git log -1", "expect": "a commit", "exact": False}]}
    text = A.render(ASKED, {**A.parse(_filled(TL.plan(e, ASKED)["text"]))["spec"],
                            "root_criteria": [*A.parse(_filled(TL.plan(e, ASKED)["text"]))["spec"]["root_criteria"], own]},
                    {})
    shown = TL.plan(e, plan=text)
    assert [c["description"] for c in shown["added_at_the_go"]] == [TL.INTENT_CRITERION["description"]], shown
    root = e.graph.get_task(TaskId(TL.auto_decompose(e, plan=text, user_said=SAID)["root_id"]))
    mine = [c for c in root.spec.criteria if c.name == INTENT]
    assert len(mine) == 1 and mine[0].description == TL.INTENT_CRITERION["description"], root.spec.criteria
    assert mine[0].check[0].command == TL.INTENT_CRITERION["check"][0]["command"]


def test_nothing_is_said_added_where_it_is_off(no_model):
    e = _engine(Mode.SOLO)
    TL.set_mode(e, intent_check=False, user_said="без проверки замысла")
    assert "added_at_the_go" not in TL.plan(e, plan=_filled(TL.plan(e, ASKED)["text"]))


def test_with_parts_the_go_admits_it_mapped_to_every_part(no_model):
    e, root = _gone(text=A.render(GOAL, _plan(), {}))
    kids = {str(c.id) for c in e.graph.get_active_children(root.id)}
    assert INTENT in _names(root) and kids
    assert {str(m.child_id) for m in root.criterion_mappings if m.criterion_name == INTENT} == kids
    assert all(INTENT not in _names(e.graph.get_task(TaskId(k))) for k in kids), "the parts get no copy"


def test_the_plans_answer_before_the_go_shows_it(no_model):
    e = _engine(Mode.SOLO)
    out = TL.plan(e, plan=_filled(TL.plan(e, ASKED)["text"]))
    assert [c["name"] for c in out["added_at_the_go"]] == [INTENT] and INTENT in out["say"], out
    shown = TL.written_plan(e.project_name, e)["root_criteria"]
    assert [(c["name"], c.get("added_at_the_go", False)) for c in shown] == [("counts", False), (INTENT, True)], shown


def test_the_validators_packet_carries_the_go_and_the_plan(no_model):
    e, root = _gone()
    packet = _validator_packet(e, root, "delivered", None)
    assert SAID in packet and 'name = "counts"' in packet and "recorded words" in packet, packet
    assert "not quotable" in packet, "the plan is the agent's text: context, never a quote's source"
    assert "# One criterion per thing" not in packet, "the template's comments are the system's, not the agreement"


def _report(quote=None, word="fail"):
    fail = {"criterion": INTENT, "verdict": word, "evidence": "no empty-line count",
            **({"quote": quote} if quote is not None else {})}
    return [{"criterion": "counts", "verdict": "pass", "evidence": "2"}, fail]


@pytest.mark.parametrize("quote", [None, "", "and count words too", "да", "the", "counts", "format gfso plan 1",
                                   "the … the … the", "lines … the … prints", "все так … еще считает пустые строки",
                                   "the number ... of lines", "number lines prints",
                                   'name = "counts"', "prints the line count"])
def test_a_fail_on_the_persons_words_without_their_words_is_refused(no_model, quote):
    e, root = _gone()
    with pytest.raises(ValueError, match="quote"):
        e.record_exec_verdict(root.id, "FAIL", [INTENT], "val", per_criterion=_report(quote))


@pytest.mark.parametrize("quote", ["Ещё считает ПУСТЫЕ строки", "еще считает, пустые строки!",
                                   "IT PRINTS the number of lines", "the number of"])
def test_a_fail_quoting_their_words_is_a_verdict(no_model, quote):
    e, root = _gone()
    rec = e.record_exec_verdict(root.id, "FAIL", [INTENT], "val", per_criterion=_report(quote))
    assert rec["verdict"] == "FAIL" and rec["failed_criteria"] == [INTENT], rec


@pytest.mark.parametrize("word", ["undecidable", "partial", "not met"])
def test_any_word_short_of_pass_on_it_needs_the_quote(no_model, word):
    e, root = _gone()
    with pytest.raises(ValueError, match="quote"):
        e.record_exec_verdict(root.id, "FAIL", [INTENT], "val", per_criterion=_report(word=word))
    rec = e.record_exec_verdict(root.id, "FAIL", [INTENT], "val", per_criterion=_report("ещё считает пустые строки", word))
    assert rec["failed_criteria"] == [INTENT], rec


@pytest.mark.parametrize("mark", ["past_bound", "on_no_delivery", "over_a_pass"])
def test_the_systems_own_word_on_it_needs_no_quote(mark):
    e = {"criterion": INTENT, "verdict": "undecidable", "evidence": "the system's run", mark: ["x"]}
    assert verdict_report_defects([INTENT], "FAIL", [e], [INTENT], persons_words=["count lines"]) == []
    assert verdict_report_defects([INTENT], "FAIL", [{**e, mark: None}], [INTENT], persons_words=["count lines"])


def test_the_spec_route_of_the_go_gets_it(no_model):
    e = _engine(Mode.SOLO)
    spec = A.parse(_filled(TL.plan(e, ASKED)["text"]))["spec"]
    root = e.graph.get_task(TaskId(TL.auto_decompose(e, ASKED, spec=spec, user_said=SAID)["root_id"]))
    assert _names(root) == ["counts", INTENT], _names(root)


def test_the_request_route_of_the_go_gets_it(no_model, monkeypatch):
    e = _engine(Mode.SOLO)
    spec = A.parse(_filled(TL.plan(e, ASKED)["text"]))["spec"]
    monkeypatch.setattr(TL._decompose, "decompose_spec", lambda *a, **k: spec)
    agrees = type("Agrees", (), {"calls": [], "complete_structured": lambda self, *a, **k: {"contradictions": []}})
    monkeypatch.setattr(TL._decompose, "default_llm", lambda *a, **k: agrees())
    monkeypatch.setenv("GFSO_SUFFICIENCY_AT_AUTHORING", "0")
    root = e.graph.get_task(TaskId(TL.auto_decompose(e, ASKED, model="m", user_said=SAID)["root_id"]))
    assert _names(root) == ["counts", INTENT], _names(root)
    assert root.spec.criteria[1].description == TL.INTENT_CRITERION["description"]


def test_a_whole_short_utterance_is_quotable(no_model):
    e, root = _gone(said="Да, делай!")
    rec = e.record_exec_verdict(root.id, "FAIL", [INTENT], "val", per_criterion=_report("да делай"))
    assert rec["failed_criteria"] == [INTENT], rec
    with pytest.raises(ValueError, match="quote"):
        e.record_exec_verdict(root.id, "FAIL", [INTENT], "val", per_criterion=_report("делай"))


def test_a_fail_on_it_with_no_report_is_refused_at_any_door(no_model):
    e, root = _gone()
    with pytest.raises(ValueError, match="quote"):
        e.record_exec_verdict(root.id, "FAIL", [INTENT], "val")


def test_the_rule_reads_this_criterion_alone():
    other = [{"criterion": "counts", "verdict": "fail", "evidence": "1"}]
    assert verdict_report_defects(["counts"], "FAIL", other, ["counts"], persons_words=["x"]) == []


def test_the_persons_revision_of_it_is_read_by_the_next_validation(no_model):
    e, root = _gone()
    meant = "Not meant: empty lines — the person said so after the FAIL."
    crits = [{"name": c.name, "description": c.description + (f" {meant}" if c.name == INTENT else ""),
              "check": [p.to_dict() for p in c.check]} for c in root.spec.criteria]
    out = TL.TOOLS["edit_criteria"](e, "root", crits, user_said="нет, пустые строки я не имел в виду")
    assert not (out or {}).get("refused"), out
    packet = _validator_packet(e, e.graph.get_task(root.id), "again", None)
    assert meant in packet and "пустые строки я не имел в виду" in packet, packet


def test_a_parts_packet_is_as_it_was(no_model):
    packets = []
    for intent in (True, False):
        e, root = _gone(intent=intent, text=A.render(GOAL, _plan(), {}))
        packets.append(_validator_packet(e, e.graph.get_task(TaskId("root.core")), "built", None))
    assert packets[0] == packets[1] and INTENT not in packets[0]


def _crits(task):
    return [{"name": c.name, "description": c.description, "check": [p.to_dict() for p in c.check]}
            for c in task.spec.criteria]


def test_a_second_go_by_spec_on_the_root_keeps_it(no_model):
    e, root = _gone()
    spec = A.parse(_filled(TL.plan(e, ASKED)["text"]))["spec"]
    spec["root_criteria"][0]["description"] = "prints the count of lines"
    TL.TOOLS["auto_decompose"](e, root_id="root", spec=spec, user_said="да, уточни описание")
    assert _names(e.graph.get_task(root.id)) == ["counts", INTENT], _names(e.graph.get_task(root.id))


def test_a_second_go_by_plan_on_the_root_keeps_it(no_model):
    e = _engine(Mode.SOLO)
    text = _filled(TL.plan(e, ASKED)["text"])
    TL.auto_decompose(e, plan=text, user_said=SAID)
    assert [c["name"] for c in TL.plan(e, plan=text)["added_at_the_go"]] == [INTENT]
    TL.TOOLS["auto_decompose"](e, plan=text, user_said="да, ещё раз")
    assert _names(e.graph.get_task(TaskId("root"))) == ["counts", INTENT]


def test_a_resplit_of_the_atomic_root_maps_it_to_every_part(no_model):
    whole = {k: v for k, v in _plan().items() if k not in ("subtasks", "mappings", "deps")}
    e, root = _gone(text=A.render(GOAL, whole, {}))
    assert not e.graph.get_active_children(root.id) and INTENT in _names(root)
    TL.TOOLS["auto_decompose"](e, root_id="root", spec=_plan(), user_said="да, раздели на части")
    root = e.graph.get_task(root.id)
    kids = {str(c.id) for c in e.graph.get_active_children(root.id)}
    assert INTENT in _names(root) and kids, _names(root)
    assert {str(m.child_id) for m in root.criterion_mappings if m.criterion_name == INTENT} == kids


def test_a_second_go_keeps_the_persons_revision_of_it(no_model):
    e, root = _gone()
    meant = "Not meant: empty lines."
    crits = [{**c, "description": c["description"] + (f" {meant}" if c["name"] == INTENT else "")} for c in _crits(root)]
    TL.TOOLS["edit_criteria"](e, "root", crits, user_said="пустые строки я не имел в виду")
    TL.TOOLS["auto_decompose"](e, root_id="root", spec=A.parse(_filled(TL.plan(e, ASKED)["text"]))["spec"], user_said="да")
    mine = [c for c in e.graph.get_task(root.id).spec.criteria if c.name == INTENT]
    assert len(mine) == 1 and meant in mine[0].description, mine


def test_a_root_made_by_hand_carries_it(no_model):
    e = _engine(Mode.SOLO)
    TL.TOOLS["create_task"](e, "root", {"description": ASKED, "criteria": [
        {"name": "counts", "description": "prints the line count",
         "check": [{"behaviour": "two lines", "command": "seq 2 | ./wc2", "expect": "2", "exact": True}]}]})
    assert _names(e.graph.get_task(TaskId("root"))) == ["counts", INTENT]


def test_a_second_gos_words_are_quotable(no_model):
    e = _engine(Mode.SOLO)
    text = _filled(TL.plan(e, ASKED)["text"])
    TL.auto_decompose(e, plan=text, user_said=SAID)
    TL.TOOLS["auto_decompose"](e, plan=text, user_said="да, ещё раз, и пусть считает слова тоже")
    rec = e.record_exec_verdict(TaskId("root"), "FAIL", [INTENT], "val", per_criterion=_report("пусть считает слова тоже"))
    assert rec["failed_criteria"] == [INTENT], rec


def test_an_agents_own_text_of_it_does_not_survive_a_go(no_model):
    e = _engine(Mode.SOLO)
    TL.set_mode(e, intent_check=False, user_said="без проверки замысла")
    own = {"name": INTENT, "description": "always holds",
           "check": [{"behaviour": "a commit", "command": "git log -1", "expect": "a commit", "exact": False}]}
    spec = A.parse(_filled(TL.plan(e, ASKED)["text"]))["spec"]
    text = A.render(ASKED, {**spec, "root_criteria": [*spec["root_criteria"], own]}, {})
    TL.auto_decompose(e, plan=text, user_said=SAID)
    TL.set_mode(e, intent_check=True, user_said="проверяй замысел")
    TL.TOOLS["auto_decompose"](e, plan=text, user_said="да, ещё раз")
    mine = [c for c in e.graph.get_task(TaskId("root")).spec.criteria if c.name == INTENT]
    assert len(mine) == 1 and mine[0].description == TL.INTENT_CRITERION["description"], mine


def test_the_persons_request_stays_quotable_under_a_narrowed_goal(no_model):
    e = _engine(Mode.SOLO)
    asked = "Build ./wc2: it counts lines and words of what it reads."
    text = _filled(TL.plan(e, asked)["text"]).replace(f'goal = "{asked}"', f'goal = "{ASKED}"')
    assert A.parse(text)["goal"] == ASKED
    TL.auto_decompose(e, plan=text, user_said="да")
    rec = e.record_exec_verdict(TaskId("root"), "FAIL", [INTENT], "val", per_criterion=_report("counts lines and words"))
    assert rec["failed_criteria"] == [INTENT], rec
