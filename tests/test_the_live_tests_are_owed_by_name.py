"""The table of what a change to the execution layer owes names what stands, and leaves no live file owed by nothing."""
import re
from pathlib import Path

import tests.conftest as C
from tests.conftest import LIVE_OWED, owed

ROOT = Path(__file__).parent.parent


def test_every_path_and_file_the_table_names_stands():
    assert not [p for p in LIVE_OWED if not (ROOT / p).exists()]
    assert not [f for f in owed(LIVE_OWED) if not (ROOT / "tests" / f"test_{f}.py").exists()]


def test_no_live_file_is_owed_by_nothing():
    live = {p.stem.removeprefix("test_") for p in (ROOT / "tests").glob("test_*.py")
            if re.search(r"^def test_live_|^@pytest.mark.live", p.read_text(encoding="utf-8"), re.M)}
    assert live - owed(LIVE_OWED) == set()


def test_a_path_outside_the_table_owes_nothing():
    assert owed(["gfso/web/app.js"]) == set() and owed(["gfso/adapters/egress.py"]) == {"the_way_out_is_a_switch_set_outside"}


def test_a_change_runs_what_it_owes_and_only_that():
    """Through the real hook: the owed file's live tests stay among all the others', the rest go."""
    class Item:
        def __init__(self, stem, live):
            self.path, self.live = Path(f"tests/test_{stem}.py"), live

        def get_closest_marker(self, name):
            return self.live or None

        def add_marker(self, mark):
            self.live = True
        name = "x"

    class Hook:
        @staticmethod
        def pytest_deselected(items):
            pass

    class Config:
        hook = Hook

        @staticmethod
        def getoption(opt):
            return "HEAD" if opt == "--live-owed" else False
    items = [Item("the_way_out_is_a_switch_set_outside", True), Item("a_judge_judges_what_was_delivered", True), Item("plain", False)]
    real, C.subprocess.run = C.subprocess.run, lambda *a, **k: type("R", (), {"stdout": "gfso/adapters/egress.py"})()
    try:
        C.pytest_collection_modifyitems(Config, items)
    finally:
        C.subprocess.run = real
    assert [i.path.stem for i in items] == ["test_the_way_out_is_a_switch_set_outside", "test_plain"]
