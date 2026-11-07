"""The go on a plan file builds the project from the file as it stands (the author, 2026-10-31); contact may repair it
from then on, the system having written it (the author, 2026-10-27, 2026-11-03: `auto_decompose`). Every criterion, pinned check, mapping, Dep, register entry and scope line of the file is in
the built graph exactly, the go calls no model to repair it, and the plan read back off the graph renders to the
file. What the system adds at the go — Del, state, the root's consent — is not in the file and not asked of it."""
from __future__ import annotations

import tomllib

import pytest

from gfso import tools_llm as TL
from gfso.core.types import Mode, TaskId
from gfso.decompose import artifact as A, extract_spec
from tests.support import UNMODELLED_FAULT
from tests.test_the_mode_decides_who_holds_what import _engine

GOAL = "Build ./wc2.\nIt counts lines, words and bytes; a missing file exits 1.\n"
SRC = "int main(void) {\n\treturn 0;\n}\n"


def _probe(c, expect="OK", **kw):
    return {"behaviour": f"{c} behaves", "command": c, "expect": expect, **kw}


def _plan() -> dict:
    """A plan as a built graph reads back: a split into two parts with a seam, a register with its denial, a scope."""
    return {
        "name": "wc2",
        "root_criteria": [
            {"name": "counts", "description": "counts match wc", "check": [_probe("make && ./wc2 {inputs}/a.c", "1 3 29", exact=True, inputs={"a.c": SRC})]},
            {"name": "errors", "description": "a missing file exits 1", "check": [_probe("./wc2 nope; echo $?", "1")]}],
        "subtasks": [
            {"id": "core", "name": "counting", "description": "the counter",
             "criteria": [{"name": "c1", "description": "counts bytes", "check": [_probe("./core_test", exact=True)]}],
             "volume": "~200 lines", "fits_one_session": True, "writes": ["wc.c"], "runs": []},
            {"id": "io", "name": "files", "description": "opens files and stdin",
             "criteria": [{"name": "i1", "description": "opens", "depends_on": "core", "check": [_probe("./io_test {inputs}/a.c", inputs={"a.c": SRC})]}],
             "volume": "~80 lines", "fits_one_session": True, "writes": ["io.c"], "runs": ["root.core"]}],
        "mappings": [{"criterion": "counts", "child_id": "core"}, {"criterion": "errors", "child_id": "io"}],
        "deps": [{"from": "core", "to": "io", "glue": "opens", "reads": ["wc.c"]}],
        "accepted_risks": [UNMODELLED_FAULT.to_dict()],
        "denial": {"p": 0.1, "justification": "two parts may not compose"},
        "scope": [{"item": "options (-l, -w) — not asked", "why_out": ""}],
        "whole_volume": "~300 lines", "whole_fits_one_session": False}


def _file() -> str:
    """The file written by hand-equivalent means (`render` of the spec above), NOT through the build under test: a file
    the code under test also wrote cannot show that the code lost something."""
    return A.render(GOAL, _plan(), {"by": "m", "gate_passed": True})


@pytest.fixture
def go(monkeypatch):
    """The go on a file, with no model to call: a call to the planner is a failure — a plan handed in is not repaired."""
    class NoModel:
        calls: list = []             # the ledger the go reads; a plan handed in leaves it empty

        def __getattr__(self, name):
            raise AssertionError(f"the go called the model ({name})")
    monkeypatch.setattr(TL._decompose, "default_llm", lambda *a, **k: NoModel())

    def run(text):
        e = _engine(Mode.AUTO)
        out = TL.auto_decompose(e, plan=text)
        assert not out.get("error") and not out["holes"], out
        return e
    return run


def test_the_built_project_keeps_every_part_of_the_file(go):
    text = _file()
    built = extract_spec(go(text), "root")
    want = _plan()
    for key in ("root_criteria", "mappings", "deps", "accepted_risks", "denial", "scope", "name"):
        assert built[key] == want[key], key
    for w, b in zip(want["subtasks"], built["subtasks"]):
        assert b == w, w["id"]             # criteria, pinned checks (inputs by content), depends_on, contract text, claims
    assert [s["id"] for s in built["subtasks"]] == ["core", "io"] and built == want


def test_the_plan_read_back_off_the_built_project_renders_to_the_file(go):
    text = _file()
    e = go(text)
    p = A.parse(text)
    assert A.render(p["goal"], extract_spec(e, "root"), p["review"], p["notes"], p["executor"]) == text


def test_what_the_go_adds_is_not_in_the_file(go):
    e = go(_file())
    assert e.users_plan() is False                      # the system wrote it: contact may repair it
    assert all(str(t.assignee) for t in e.graph.get_active_children(TaskId("root")))   # Del enters here, at the go
    assert set(tomllib.loads(_file())) == {"format", "goal", "plan", "fit", "review", "notes", "inputs"}   # …not in the file


def test_a_plan_the_admission_refuses_is_refused_not_repaired(go, monkeypatch):
    """The go called a model and patched a handed-in plan the admission would refuse — a project ran a plan nobody had
    read. Closed, it is refused as it stands, naming why; the model is never asked (`go`'s NoModel)."""
    spec = _plan()
    spec["root_criteria"][0]["check"].append(_probe("make && ./wc2 {inputs}/a.c", "1 3 30", exact=True, inputs={"a.c": SRC}))
    e = _engine(Mode.AUTO)
    with pytest.raises(ValueError, match="refused as it stands"):
        TL.auto_decompose(e, plan=A.render(GOAL, spec, {"by": "m", "gate_passed": True}))


def test_a_plan_whose_split_the_admission_refuses_is_refused_before_anything_is_built(go):
    """One mapping gone, the split was refused at the build and the root handed to one executor as a leaf — the
    customer's two-part plan rewritten by removal (critic over the closed go). Refused, and the project stays empty."""
    spec = _plan()
    spec["mappings"] = spec["mappings"][:1]
    e = _engine(Mode.AUTO)
    with pytest.raises(ValueError, match="refused as it stands"):
        TL.auto_decompose(e, plan=A.render(GOAL, spec, {"by": "m", "gate_passed": True}))
    assert not e.all_tasks(), "nothing of the refused plan stands in the project"


def test_a_plan_handed_in_on_a_root_that_stands_unsplit_is_closed_too(go):
    """The go on a root someone created first, with no parts yet, called the model to repair a refused file and never
    recorded the plan as the user's (critic): the plan handed in is closed whatever stands of the project."""
    spec = _plan()
    spec["root_criteria"][0]["check"].append(_probe("make && ./wc {inputs}/zz.c", "1 3 30", exact=True))
    e = _engine(Mode.AUTO)
    made = TL.create_task(e, "root", {"name": "wc", "description": GOAL, "criteria": [
        {"name": "c", "description": "prints ok",
         "check": [{"behaviour": "ok", "command": "make -s && ./wc --ok", "expect": "ok"}]}]})
    assert not (made or {}).get("error") and e.graph.get_task(TaskId("root")), made     # …the root stands, unsplit
    with pytest.raises(ValueError, match="refused as it stands"):
        TL.auto_decompose(e, plan=A.render(GOAL, spec, {"by": "m", "gate_passed": True}), root_id="root")
