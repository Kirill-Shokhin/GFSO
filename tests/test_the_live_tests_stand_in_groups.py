"""Every live test file stands in exactly one group, by what it checks, and a group runs alone (the author, 2026-11-02: «я
изначально просил разделить тесты на группы да которые можно гонять целевым путем»)."""
import re
from pathlib import Path

import pytest

import tests.conftest as C
from tests.conftest import LIVE_GROUPS

ROOT = Path(__file__).parent.parent


def test_every_live_file_stands_in_one_group_and_every_named_file_stands():
    named = [f for files in LIVE_GROUPS.values() for f in files]
    assert len(named) == len(set(named)), "a file in two groups: the groups are no split"
    assert not [f for f in named if not (ROOT / "tests" / f"test_{f}.py").exists()]
    live = {p.stem.removeprefix("test_") for p in (ROOT / "tests").glob("test_*.py")
            if re.search(r"^def test_live_|^@pytest.mark.live", p.read_text(encoding="utf-8"), re.M)}
    assert live == set(named)


class _Item:
    name = "x"

    def __init__(self, stem, live):
        self.path, self.live = Path(f"tests/test_{stem}.py"), live

    def get_closest_marker(self, name):
        return self.live or None

    def add_marker(self, mark):
        self.live = True


def _config(group):
    class Config:
        class hook:
            pytest_deselected = staticmethod(lambda items: None)

        @staticmethod
        def getoption(opt):
            return group if opt == "--live-group" else False
    return Config


def test_a_group_runs_alone_and_a_name_no_group_has_is_refused():
    items = [_Item("the_way_out_is_a_switch_set_outside", True), _Item("a_judge_judges_what_was_delivered", True), _Item("plain", False)]
    C.pytest_collection_modifyitems(_config("network"), items)
    assert [i.path.stem for i in items] == ["test_the_way_out_is_a_switch_set_outside"]
    with pytest.raises(pytest.UsageError):
        C.pytest_collection_modifyitems(_config("nothing"), [_Item("plain", False)])
