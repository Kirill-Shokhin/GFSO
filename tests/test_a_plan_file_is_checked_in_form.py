"""A person edits a plan file by hand and learns of a slip when `parse` reads it — naming the field and the problem —
not when the build drops a mapping onto a part that is not there or dies on a missing key. Each defect is shown on a
file with that defect alone; the plans the system wrote read clean."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path

import pytest

from gfso.config import data_dir
from gfso.decompose import artifact as A
from tests.test_the_go_only_adds_to_the_plan import GOAL, _plan


def _bad(mut, goal=GOAL) -> str:
    spec = copy.deepcopy(_plan())
    mut(spec)
    return A.render(goal, spec)


DEFECTS = {
    "goal: missing or empty": lambda s: None,        # goal is the render argument, below
    "plan.root_criteria: none": lambda s: s.update(root_criteria=[], mappings=[]),
    "plan.root_criteria[1].name: missing": lambda s: (s["root_criteria"][1].pop("name"), s["mappings"].pop()),
    "plan.subtasks: id 'core' appears twice": lambda s: s["subtasks"].append(copy.deepcopy(s["subtasks"][0])),
    "plan.subtasks[0].criteria[0].name: missing": lambda s: s["subtasks"][0]["criteria"][0].pop("name"),
    "plan.subtasks[1].criteria[0].depends_on: 'gone' is no part": lambda s: s["subtasks"][1]["criteria"][0].update(depends_on="gone"),
    "plan.mappings[0].child_id: 'gone' is no part": lambda s: s["mappings"][0].update(child_id="gone"),
    "plan.mappings[1].criterion: 'gone' is no root criterion": lambda s: s["mappings"][1].update(criterion="gone"),
    "plan.mappings[0].criterion: missing": lambda s: s["mappings"][0].pop("criterion"),
    "plan.deps[0].from: 'gone' is no part": lambda s: s["deps"][0].update({"from": "gone"}),
    "plan.deps[0].to: 'gone' is no part": lambda s: s["deps"][0].update(to="gone"),
    "plan.scope[0].item: missing": lambda s: s["scope"][0].pop("item"),
    "plan.root_criteria: name": lambda s: s["root_criteria"].append(copy.deepcopy(s["root_criteria"][0])),
    "plan.subtasks[0].criteria: name": lambda s: s["subtasks"][0]["criteria"].append(
        copy.deepcopy(s["subtasks"][0]["criteria"][0])),
}


@pytest.mark.parametrize("want", DEFECTS)
def test_a_defect_is_named_by_its_field(want):
    text = _bad(DEFECTS[want], goal="" if want.startswith("goal") else GOAL)
    with pytest.raises(ValueError, match="malformed") as e:
        A.parse(text)
    assert want in str(e.value) and str(e.value).count(";") == 0, str(e.value)    # that defect, alone


def test_a_part_without_an_id_is_named():
    text = A.render(GOAL, _plan()).replace("id = \"io\"", "", 1)    # the first one: the part's own, before the fit marks'
    assert text != A.render(GOAL, _plan())
    with pytest.raises(ValueError, match=r"plan\.subtasks\[1\]\.id: missing"):
        A.parse(text)


def test_an_input_hash_with_no_file_is_named():
    text = A.render(GOAL, _plan())
    kept, _, files = text.partition("\n[inputs]")
    with pytest.raises(ValueError, match=r"check 'counts'\[0\]\.inputs\.a\.c: 'sha256-\w+' has no file under \[inputs\]"):
        A.parse(kept)


def test_a_fit_mark_of_no_part_is_named():
    text = A.render(GOAL, _plan()).replace('id = "io"\nvolume', 'id = "ghost"\nvolume')
    assert 'id = "ghost"' in text
    with pytest.raises(ValueError, match=r"fit\.parts\[1\]\.id: 'ghost' is no part"):
        A.parse(text)


def test_every_defect_of_a_file_is_told_at_once():
    spec = _plan()
    spec["mappings"][0]["child_id"] = "x"
    spec["deps"][0]["to"] = "y"
    with pytest.raises(ValueError) as e:
        A.parse(A.render(GOAL, spec))
    assert "mappings[0].child_id" in str(e.value) and "deps[0].to" in str(e.value)


def test_the_plans_the_system_wrote_read_clean():
    assert A.parse(A.render(GOAL, _plan()))["spec"] == _plan()
    files = sorted((data_dir() / "plans").glob("*.gfso"))
    if not files:
        pytest.skip("no kept plan files in this state directory")
    for f in files:
        assert A.form(tomllib.loads(f.read_text(encoding="utf-8"))) == [], f.name


def test_a_section_the_build_does_not_read_is_named_not_dropped():
    text = A.render(GOAL, copy.deepcopy(_plan())) + '\n[fits]\nexecutor = "x"\n'
    with pytest.raises(ValueError, match="malformed") as e:
        A.parse(text)
    assert "fits: no section" in str(e.value) and str(e.value).count(";") == 0, str(e.value)


@pytest.mark.parametrize("extra, want", [
    ('[[plan.mapping]]\ncriterion = "x"\nchild_id = "core"\n', "plan.mapping: no field"),
    ('[[plan.dep]]\nfrom = "core"\nto = "core"\n', "plan.dep: no field"),
    ('[fit.part]\nid = "core"\n', "fit.part: no field"),
])
def test_a_misspelled_table_one_level_down_is_named_not_dropped(extra, want):
    with pytest.raises(ValueError, match="malformed") as e:
        A.parse(A.render(GOAL, copy.deepcopy(_plan())) + "\n" + extra)
    assert want in str(e.value) and str(e.value).count(";") == 0, str(e.value)


def _slip(edit) -> str:
    """The rendered test plan, its TOML parsed, `edit`ed, and written back — a hand edit."""
    doc = tomllib.loads(A.render(GOAL, copy.deepcopy(_plan())))
    edit(doc["plan"])
    return A._emit(doc)


def _rename(row, old, new):
    row[new] = row.pop(old)


ROW_SLIPS = {
    "check[0].expcet: no field of a probe": lambda p: _rename(p["root_criteria"][0]["check"][0], "expect", "expcet"),
    "check[0].exact: 'true' is no true/false": lambda p: p["root_criteria"][0]["check"][0].update(exact="true"),
    "plan.deps[0].read: no field of a dep": lambda p: _rename(p["deps"][0], "reads", "read"),
    "plan.subtasks[0].write: no field of a part": lambda p: p["subtasks"][0].update(write=["x.c"]),
    "criteria[0].depend_on: no field of a criterion": lambda p: p["subtasks"][1]["criteria"][0].update(depend_on="core"),
    "plan.accepted_risks[0].factor: no field of a risk": lambda p: _rename(p["accepted_risks"][0], "item", "factor"),
}


@pytest.mark.parametrize("want", ROW_SLIPS)
def test_a_slip_in_a_row_below_is_named_not_built(want):
    with pytest.raises(ValueError, match="malformed") as e:
        A.parse(_slip(ROW_SLIPS[want]))
    assert want in str(e.value) and str(e.value).count(";") == 0, str(e.value)
