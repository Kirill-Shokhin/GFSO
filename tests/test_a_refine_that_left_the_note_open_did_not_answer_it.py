"""A note asked the parts to carry the checks a root criterion needs; the round added one more root criterion, which
the review marked insufficient, and the one note was spent (a tester's regex run, 2026-11-13). A round whose review
still finds open what the note named — or what the round itself added — has not answered it."""
from gfso.decompose.planning import still_open

BEFORE = {"root_criteria": [{"name": "basic"}, {"name": "unicode-case"}]}
AFTER = {"root_criteria": [{"name": "basic"}, {"name": "unicode-case"}, {"name": "extended-syntax"}]}


def _review(*lines):
    return {"semantic_findings": "\n".join(lines)}


def test_what_the_note_names_or_the_round_added_still_open_is_said():
    r = _review("[insufficient] extended-syntax — no part pins lookbehind",
                "[insufficient] unicode-case — no part folds case", "[sufficient] basic — carried")
    assert still_open("give the parts the checks basic.py needs", BEFORE, AFTER, r) == [
        "[insufficient] extended-syntax — no part pins lookbehind"]
    assert len(still_open("unicode-case: give the parts pins", BEFORE, AFTER, r)) == 2


def test_a_round_whose_review_closed_them_answered_the_note():
    assert still_open("extended-syntax to the parts", BEFORE, AFTER, _review("[sufficient] extended-syntax — c")) == []
