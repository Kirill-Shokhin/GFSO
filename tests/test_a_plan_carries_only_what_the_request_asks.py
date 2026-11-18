"""A goal's criteria are the person's: a capability outside the goal's scope is absent from it, and extending the scope
means giving the goal new criteria (§2.2); a demand beyond what the goal needs lies in the goal's setting (§6.7). Every
criterion the plan writes says in `asked` which words of the request it states, and the system reads them against the
request word for word, no model: one whose words are not there is the system's own. Where the system writes from the
request alone, the plan's repair is told (its own move, §12.16 (ii)); what stays is said in the plan file and in the
plan's answer, as the system's, for the person to keep or strike. Never a gate. Measured 2026-11-17 (in_chat, Haiku): a
task with three asked criteria came back with nine; 2026-11-16 (s16b) invented label escaping and encoding cost a
stranger's run 57 min.

CONTROLS: make `beyond_the_request` return [] and the rule tests go red; read `asked` without `_words` and the quote
with other quotes and spacing is flagged; drop `_beyond` from `_repaired_before_build`'s list and the repair is never
told; drop `agree.on` from it and a customer's plan is repaired against the request alone; drop `_asked_kept` in
`planning.author` and the file says nothing; drop `unasked` from the answer and the person is not told."""
from types import SimpleNamespace

import pytest

import gfso.decompose as D
import gfso.tools_llm as TL
from gfso.decompose import artifact, planning
from gfso.decompose.loop import AUDIT_PROMPT, AUDIT_SCHEMA
from tests.support import make_engine
from tests.test_a_pin_that_cannot_run_is_repaired_before_the_go import _Review  # noqa: F401 — the shared stub
from tests.test_a_pin_that_cannot_run_is_repaired_before_the_go import no_model  # noqa: F401 — a fixture

GOAL = 'Write wordtop: it reads a text file and prints the "10" most frequent words with their counts.'


def _crit(name, asked=None):
    return {"name": name, "description": f"{name} holds", **({} if asked is None else {"asked": asked}),
            "check": [{"behaviour": "b", "command": f"./wordtop {name}.txt", "expect": "x"}]}


def _plan_of(*crits, parts=()):
    return {"name": "wordtop", "root_criteria": list(crits), "subtasks": list(parts), "mappings": [], "deps": [],
            "accepted_risks": []}


ASKED = _crit("top", "prints the “10” most   frequent WORDS")
UTF8 = _crit("utf8", "")                                       # …the encoding nobody named: the model's own word
INVENTED = _crit("labels", "escapes labels as \\xHH")         # …words the request never says


@pytest.mark.parametrize("crit,beyond", [
    (ASKED, False), (UTF8, True), (INVENTED, True),
    (_crit("parts", "reads a text file … with their counts"), False),
    (_crit("parts_wrong", "reads a text file … sorted by label"), True),
    (_crit("word_inside", "wordto"), True),                   # …a word, not a piece of one
    (_crit("before", None), False),                           # …a criterion of a plan written before `asked`
])
def test_a_criterion_is_the_persons_only_where_its_words_are_the_requests(crit, beyond):
    assert bool(D.beyond_the_request(_plan_of(crit), GOAL)) is beyond


def test_a_childs_finer_criterion_is_read_as_the_roots_are():
    part = {"id": "count", "name": "count", "description": "d", "criteria": [_crit("tie", "most frequent words"),
                                                                          _crit("locale", "")]}
    assert [(n, c["name"]) for n, c in D.beyond_the_request(_plan_of(ASKED, parts=[part]), GOAL)] == [("count", "locale")]


def _built(monkeypatch, spec, on):
    told = []
    monkeypatch.setattr(D, "_audit_fix", lambda llm, req, sp, problems, ex: told.append(problems) or {
        "root_criteria": [ASKED]})
    e = make_engine()
    e.start()
    try:
        agree = D._Agreement(None, e, "root", GOAL, on, False)
        monkeypatch.setattr(agree, "judge", lambda s: None)
        _, out, _ = D._build_verified(spec, GOAL, e, "root", "user", llm=None, agree=agree)
    finally:
        e.stop()
    return told, out


def test_where_the_system_writes_from_the_request_its_repair_is_told_and_never_gated(monkeypatch):
    told, spec = _built(monkeypatch, _plan_of(ASKED, UTF8), True)
    assert len(told) == 1 and len(told[0]) == 1 and "criterion utf8" in told[0][0], told
    assert "states nothing the request asks" in told[0][0]
    assert [c["name"] for c in spec["root_criteria"]] == ["top"]


def test_a_plan_the_system_did_not_write_from_the_request_alone_is_not_repaired_for_it(monkeypatch):
    told, spec = _built(monkeypatch, _plan_of(ASKED, UTF8), False)
    assert told == [] and [c["name"] for c in spec["root_criteria"]] == ["top", "utf8"]


def test_what_the_rounds_leave_is_in_the_plan_file_and_the_answer_says_it_as_the_systems(monkeypatch, no_model):
    """Through the authoring verb: the repair left the invented criterion, the file keeps each `asked`, its review names
    the criterion as the system's own, and the plan's answer tells the client to name it to the person."""
    monkeypatch.setattr(D, "_audit_fix", lambda *a, **k: {})
    monkeypatch.setattr(D, "decompose_spec", lambda *a, **k: _plan_of(ASKED, UTF8))
    text = planning.author(GOAL, "m")
    p = artifact.parse(text)
    assert {c["name"]: c.get("asked") for c in p["spec"]["root_criteria"]} == {"top": ASKED["asked"], "utf8": ""}
    (line,) = p["review"][planning.BEYOND]
    assert line.startswith("root / utf8"), line
    out = TL._plan_written(text)
    assert out[planning.BEYOND] == [line]
    assert "1 criterion(s) state nothing their request asks" in out["say"] and "system's own" in out["say"], out["say"]


def test_a_customers_note_asks_too(monkeypatch, no_model):
    """`refine_plan`: a criterion quoting the customer's note is theirs; the file of before keeps its words."""
    noted = _crit("empty", "an empty file prints 0")
    monkeypatch.setattr(D, "refine_with", lambda *a, **k: (True, _plan_of(ASKED, noted), []))
    monkeypatch.setattr(planning, "extract_spec", lambda *a, **k: _plan_of(_crit("top"), _crit("empty")))
    monkeypatch.setattr(D, "repaired_before_build", lambda spec, *a, **k: spec)
    monkeypatch.setattr(planning, "build_graph_live", lambda *a, **k: (None, "root", []))
    text = planning.refine(artifact.render(GOAL, _plan_of(ASKED), {"by": "m"}), "an empty file prints 0", "m")
    p = artifact.parse(text)
    assert {c["name"]: c.get("asked") for c in p["spec"]["root_criteria"]} == {"top": ASKED["asked"],
                                                                                 "empty": noted["asked"]}
    assert planning.BEYOND not in p["review"], p["review"]


def test_the_planner_is_told_to_name_the_words_it_states():
    assert "asked" in AUDIT_SCHEMA["properties"]["root_criteria"]["items"]["properties"]
    assert "`asked`" in AUDIT_PROMPT and "absent from it" in AUDIT_PROMPT
