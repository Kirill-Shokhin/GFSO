"""A seam is wall time and a claim: the consumer's work reads the producer's output (§2.7).

Measured: the sql_database plan chained 12 parts into 8 waves because each part's probes ran the whole binary (its
glue: "SELECT checks need working CREATE/INSERT"); its three rows spent 9 h each. `seams` makes the chain's length
visible and the claim checkable against the files each part declares it writes — a finding, never a refusal."""
from gfso.decompose.loop import _spec_line
from gfso.decompose.seams import critical_path, seam_problems, waves


def _plan(deps, writes=None):
    w = writes or {"core": ["sql.h", "src/"], "dml": ["dml.c"], "sel": ["select.c"], "agg": ["group.c"]}
    return {"subtasks": [{"id": i, "writes": f} for i, f in w.items()],
            "deps": [{"from": f, "to": t, "reads": r, "glue": "g"} for f, t, r in deps]}


def test_waves_and_the_chain_they_wait_on():
    s = _plan([("core", "dml", ["sql.h"]), ("dml", "sel", ["dml.c"]), ("core", "agg", ["sql.h"])])
    assert waves(s) == [["core"], ["dml", "agg"], ["sel"]]
    assert critical_path(s) == ["core", "dml", "sel"]
    assert "3 waves (core → dml → sel)" in _spec_line(s)


def test_a_seam_its_producers_files_carry_is_no_finding():
    assert seam_problems(_plan([("core", "dml", ["sql.h"]), ("core", "sel", ["src/eval.c"])])) == []


def test_a_seam_for_a_check_is_a_finding():
    """Named nothing, or a file the producer does not write: the seam orders work only so a probe can run."""
    found = seam_problems(_plan([("dml", "sel", []), ("core", "agg", ["parser.c"])]))
    assert len(found) == 2
    assert found[0].startswith("seam dml → sel: names nothing") and "parser.c" in found[1]


def test_two_parts_writing_one_file_unordered_is_a_finding():
    w = {"core": ["sql.h"], "sel": ["select.c"], "agg": ["group.c", "select.c"]}
    assert any("sel and agg both write select.c" in p
               for p in seam_problems(_plan([("core", "sel", ["sql.h"]), ("core", "agg", ["sql.h"])], w)))
    assert not any("both write" in p
                   for p in seam_problems(_plan([("core", "sel", ["sql.h"]), ("sel", "agg", ["select.c"])], w)))


def test_a_plan_that_names_no_files_is_not_read():
    """A plan written before seams named their files (the verified E3 plans) is not re-judged by this."""
    s = _plan([("dml", "sel", [])])
    for k in s["subtasks"]:
        k.pop("writes")
    assert seam_problems(s) == []


def test_a_cycle_is_in_no_wave():
    s = _plan([("dml", "sel", ["dml.c"]), ("sel", "dml", ["select.c"])])
    assert all("dml" not in w and "sel" not in w for w in waves(s))


def test_a_part_that_declared_nothing_is_not_judged_and_silences_no_other():
    """A child an issuer's repair adds by hand carries no claim: it is not judged, and every part that declared stays
    judged (critic over the seam claim: one such child turned the whole split's findings off)."""
    w = {"core": ["sql.h"], "dml": ["dml.c"], "fix": []}
    s = _plan([("fix", "dml", ["fix.c"]), ("core", "sel", ["parser.c"])], {**w, "sel": ["select.c"]})
    found = seam_problems(s)
    assert len(found) == 1 and found[0].startswith("seam core → sel")


def test_two_parts_writing_into_one_directory_share_no_file():
    w = {"core": ["sql.h"], "sel": ["src/"], "agg": ["src/"]}
    assert not any("both write" in p for p in seam_problems(_plan([("core", "sel", ["sql.h"]), ("core", "agg", ["sql.h"])], w)))


def test_a_directory_named_without_its_slash_is_still_a_directory():
    w = {"core": ["sql.h", "tests/core_test.c"], "sel": ["tests"], "agg": ["tests"]}
    assert not any("both write" in p for p in seam_problems(_plan([("core", "sel", ["sql.h"]), ("core", "agg", ["sql.h"])], w)))


def _runs(runs: dict, deps=()):
    return {"subtasks": [{"id": i, "runs": r} for i, r in runs.items()],
            "deps": [{"from": f, "to": t, "glue": "g"} for f, t in deps]}


def test_a_probe_running_a_part_it_does_not_wait_on_is_a_finding():
    """§2.7: the sql lexer, in wave 1 beside the base, probed through `./sql_database` before any parser existed."""
    found = seam_problems(_runs({"base": [], "lexer": ["base", "parser"], "parser": ["base"]},
                                [("base", "lexer"), ("base", "parser")]))
    assert len(found) == 1 and found[0].startswith("lexer's probes run the code of parser")


def test_a_probe_running_what_it_waits_on_through_a_chain_is_none():
    assert seam_problems(_runs({"base": [], "lexer": ["base"], "parser": ["base", "lexer"]},
                               [("base", "lexer"), ("lexer", "parser")])) == []


def test_runs_is_judged_where_a_part_declares_it():
    s = _runs({"base": [], "lexer": ["parser"], "parser": []})
    del s["subtasks"][2]["runs"]
    assert len(seam_problems(s)) == 1
    del s["subtasks"][1]["runs"]
    assert seam_problems(s) == []
