"""A seam is wall time and a claim: the consumer's work reads the producer's output (§2.7).

Measured: the sql_database plan chained 12 parts into 8 waves because each part's probes ran the whole binary (its
glue: "SELECT checks need working CREATE/INSERT"); its three rows spent 9 h each. `seams` makes the chain's length
visible and the claim checkable against the files each part declares it writes — a finding, never a refusal."""
from gfso.decompose.loop import _spec_line
from gfso.decompose.seams import RUNS, critical_path, seam_problems, waves


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
    # …its kind and part are read beside its prose: the promote refusal reads these, so a rewording cannot disable it
    assert (found[0].kind, found[0].part) == (RUNS, "lexer")


def test_a_probe_running_what_it_waits_on_through_a_chain_is_none():
    assert seam_problems(_runs({"base": [], "lexer": ["base"], "parser": ["base", "lexer"]},
                               [("base", "lexer"), ("lexer", "parser")])) == []


def test_runs_is_judged_where_a_part_declares_it():
    s = _runs({"base": [], "lexer": ["parser"], "parser": []})
    del s["subtasks"][2]["runs"]
    assert len(seam_problems(s)) == 1
    del s["subtasks"][1]["runs"]
    assert seam_problems(s) == []


def _probing(parts: dict, deps=()):
    """Parts as {id: (writes, runs, command)}: one pinned check each, `runs` left out where None."""
    return {"subtasks": [{"id": i, "writes": w, **({} if r is None else {"runs": r}),
                          "criteria": [{"name": "c", "check": [{"command": cmd, "expect": "ok"}]}]}
                         for i, (w, r, cmd) in parts.items()],
            "deps": [{"from": f, "to": t, "glue": "g"} for f, t in deps]}


def test_a_check_running_what_another_part_writes_is_its_seam():
    """§2.7, read off the checks: B's probe runs `./c_compiler`, which A writes; `runs: []` does not hide it."""
    s = _probing({"a": (["c_compiler.c"], [], "make -s c_compiler && ./c_compiler -v"),
                  "b": (["Makefile"], [], "T=$(mktemp -d); ./c_compiler {inputs}/m.c -o $T/m && echo ok")})
    found = seam_problems(s)
    assert len(found) == 1 and found[0].startswith("b's probes run the code of a")
    assert seam_problems({**s, "deps": [{"from": "a", "to": "b", "glue": "g"}]}) == []


def test_the_whole_program_runs_what_every_other_part_probing_it_says():
    """GF_cc_full1: plumbing wrote the Makefile, said `runs: []` and probed `./c_compiler`, which no part writes and
    which codegen and float said runs the front end; it waited on none and stood BLOCKED five hours."""
    cc = "./c_compiler {inputs}/m.c -o $T/m"
    s = _probing({"lexer": (["lexer.c"], [], "make -s tests/lex && ./tests/lex x"),
                  "codegen": (["codegen.c"], ["lexer"], cc), "float": (["float.c"], ["root.lexer", "root.codegen"], cc),
                  "plumbing": (["Makefile"], [], cc)}, [("lexer", "codegen"), ("codegen", "float")])
    found = seam_problems(s)
    assert len(found) == 1 and found[0].startswith("plumbing's probes run the code of codegen, lexer,")
    assert seam_problems({**s, "deps": s["deps"] + [{"from": "codegen", "to": "plumbing", "glue": "g"}]}) == []


def test_the_first_of_a_chain_building_one_program_is_not_judged_by_its_successors():
    cc = "./cc -o x m.c"
    assert seam_problems(_probing({"s1": (["lex.c"], [], cc), "s2": (["expr.c"], ["s1"], cc),
                                   "s3": (["stmt.c"], ["s1", "s2"], cc)}, [("s1", "s2"), ("s2", "s3")])) == []


def test_a_program_no_part_claims_anything_of_is_not_judged():
    """The base may hold it: parts each extending a program the repository already has say `runs: []`."""
    assert seam_problems(_probing({"a": (["a.c"], [], "./prog a"), "b": (["b.c"], [], "./prog b")})) == []


def test_runs_named_by_its_namespaced_id_is_read():
    """The c_compiler plan's float-types said `runs: ["root.lexer", …]`; read as no part, it went unjudged."""
    assert seam_problems(_runs({"base": [], "lexer": ["root.parser"], "parser": []}))[0].startswith(
        "lexer's probes run the code of parser")


def _pinned(parts: dict, deps=()):
    """Parts as {id: (writes, runs, pin body)}: one check each running a pinned file."""
    return {"subtasks": [{"id": i, "writes": w, "runs": r, "criteria": [{"name": "c", "check": [
                {"command": "python {inputs}/pin.py", "expect": "ok", "inputs": {"pin.py": body}}]}]}
                         for i, (w, r, body) in parts.items()],
            "deps": [{"from": f, "to": t, "glue": "g"} for f, t in deps]}


def test_a_pin_importing_what_a_later_part_writes_is_a_finding_whatever_runs_says():
    """A regex engine's plan: the parser's pins ran `import myre; myre.compile`, the package api writes and api comes
    last (parser → engine → api); `runs: []` hid it and the plan read clean."""
    s = _pinned({"parser": (["myre/parser.py"], [], "import myre\nprint(myre.compile('a'))"),
                 "engine": (["myre/engine.py"], ["root.parser"], "from myre import search\nprint(search('a', 'a'))"),
                 "api": (["myre/__init__.py"], ["parser", "engine"], "import myre")},
                [("parser", "engine"), ("engine", "api")])
    found = seam_problems(s)
    assert [f.split("'")[0] for f in found] == ["parser", "engine"] and all("of api" in f for f in found)


def test_a_pin_importing_its_own_module_or_what_it_waits_on_is_none():
    s = _pinned({"parser": (["src/myre/parser.py"], [], "from myre.parser import parse\nimport re, sys"),
                 "engine": (["src/myre/engine.py"], ["parser"], "import myre.parser; import myre.engine")},
                [("parser", "engine")])
    assert seam_problems(s) == []
