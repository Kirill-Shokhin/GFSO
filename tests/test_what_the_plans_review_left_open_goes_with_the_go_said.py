"""The go on a plan file runs it as it stands (its review in the file, the gate off): each criterion the review found
the children do not secure goes in carrying its FM-1.d (§11.5). Said at the go, never silent — a tester's run
started on two such root criteria with nothing said, and its failures pointed to no part."""
from gfso.decompose.artifact import render
from gfso.tools_llm import open_at_the_go


def _plan(findings: str) -> str:
    return render("a regex engine", {"root_criteria": [{"name": "basic", "description": "matches as re does"}],
                                         "subtasks": [{"id": "parser", "description": "parse",
                                                       "criteria": [{"name": "p", "description": "parses"}]}],
                                         "mappings": [{"criterion": "basic", "child_id": "parser"}]},
                  review={"gate_passed": True, "semantic_covered": not findings, "semantic_findings": findings})


def test_each_open_criterion_is_named_and_a_clean_review_names_none():
    left = open_at_the_go(_plan("[insufficient] extended-syntax — no part pins lookbehind\n"
                                "[sufficient] basic — parser and engine carry it\n"
                                "[uncertain] unicode-case — the probe is not in the packet"))
    assert left == ["[insufficient] extended-syntax — no part pins lookbehind",
                    "[uncertain] unicode-case — the probe is not in the packet"]
    assert open_at_the_go(_plan("")) == []
