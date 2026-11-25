"""A part whose split depends on another part's result is split after that result, not guessed before it (FM-6, §8.6:
«Defer the split until contact has made it definable»).

The engine already deferred a split — a part marked larger than a session is owed one (`split_owed`), made by the
machine issuer's refine round — but asked for it at the part's issue, before any contact: the deferral was spent at
once, the same guess. Now a part may name the producers whose results its split needs (`split_after`); the `split`
question waits until they are accepted, and the round is handed what they delivered. A deferral is admitted only on a
producer the part consumes, of the same split, not yet settled — so no chain of deferrals grows without work between
its links (§12.16 (ii): the decomposer lifts the refusal by naming one, or splitting now).

CONTROLS: drop `not engine.split_waits_on(t.id)` from `open_questions` and the waiting test goes red; drop the
`deferral_refused` call from `record_session_fit` and the admission test goes red.
"""
import subprocess

import pytest

import gfso.decompose as D
import gfso.decompose.loop as L
from gfso.decompose import _dens_patch
from gfso.decompose.loop import fold_merge
from gfso import delegate as DG
from gfso import issuer as I
from gfso import tools as T
from gfso import workspaces as WS
from gfso.tools_llm import _no_deferral_nobody_makes, auto_decompose
from gfso.core.types import AgentId, Mode, Signal, SignalData, TaskId
from gfso.decompose import artifact
from gfso.decompose.build import _record_the_session_fit
from gfso.decompose.extract import extract_spec
from gfso.decompose.planning import changes
from gfso.decompose.seams import DEFERRED, deferral_problems, with_deferrals
from gfso.engine.validation import session_fit
from gfso.roster import AgentRegistry
from tests.support import REGISTER, criterion, instrument_passes, make_engine, declare, undeclare

WHY = "how the checker is split depends on the AST the parser delivers"


def _plan():
    """root -> {parser, checker, docs}; the checker consumes the parser, under AUTO."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.workforce.publish_executor_pool({"exec-1": None, "exec-2": None})
    e.set_mode(Mode.AUTO, None, AgentId("user"))
    T.create_task(e, "root", {"description": "a compiler", "criteria": [criterion("g", "G"), criterion("h", "H"),
                                                                         criterion("d", "D")]})
    T.decompose(e, "root", [{"task_id": f"root.{k}", "covers": [c], "spec": {
        "description": k, "criteria": [criterion(f"{k}_ok", k)]}} for k, c in (("parser", "g"), ("checker", "h"),
                                                                                  ("docs", "d"))],
                accepted_risks=REGISTER)
    declare(e, "root.parser", "root.checker", glue="the checker walks the parser's AST")
    e.wait_idle()
    return e


def _defer(e, *producers, why=WHY):
    e.record_session_fit(TaskId("root.checker"), "four passes", False, {"producers": list(producers), "why": why})


def _pass(e, k):
    who = str(e.graph.get_task(TaskId(k)).assignee)
    T.signal(e, k, "ACCEPT", who)
    T.signal(e, k, "DELIVER", who, result=f"{k} done")
    instrument_passes(e, TaskId(k))
    T.signal(e, k, "PASS", str(e.graph.issuer_of(TaskId(k))))
    e.wait_idle()


def _asked(e, k):
    return dict(I.open_questions(e)).get(TaskId(k))


def test_the_split_is_asked_only_once_the_result_it_waits_on_is_accepted():
    e = _plan()
    _defer(e, "root.parser")
    assert e.split_owed(TaskId("root.checker")) is not None          # deferred is owed its split, not a leaf
    assert e.split_waits_on(TaskId("root.checker")) == ["root.parser"]
    assert _asked(e, "root.checker") != "split"                       # asked now, it would be the guess
    assert e.split_owed(TaskId("root.checker"))["opens_with"].startswith("nothing yet — once root.parser is accepted")
    _pass(e, "root.parser")
    assert e.split_waits_on(TaskId("root.checker")) == []
    assert _asked(e, "root.checker") == "split"


def test_a_part_judged_only_too_big_with_no_producer_is_asked_at_once_as_before():
    e = _plan()
    e.record_session_fit(TaskId("root.docs"), "four chapters", False)
    assert e.split_waits_on(TaskId("root.docs")) == [] and _asked(e, "root.docs") == "split"


def _three_parts(**checker):
    part = lambda i, **kw: {"id": i, "criteria": [{"name": f"{i}_ok"}], "fits_one_session": True, **kw}
    return {"subtasks": [part("parser"), part("docs"), part("checker", **checker)],
            "deps": [{"from": "parser", "to": "checker"}, {"from": "docs", "to": "checker"}]}


def test_a_part_too_big_for_a_session_is_deferred_on_its_producers_in_the_plan():
    """Its parts would wait for the parser and the docs anyway (φ, `start_waits`): split before they stand, it guesses.
    The system writes the deferral into the plan, where the customer reads it. Measured: Haiku 5.5's own c_compiler
    plan judged nine parts larger than a session and deferred none (2026-11-11).
    CONTROL: drop the `with_deferrals` call from `decompose_into` and the wiring test goes red."""
    out = {k["id"]: k for k in with_deferrals(_three_parts(fits_one_session=False))["subtasks"]}
    assert out["checker"]["split_after"] == {"after": ["docs", "parser"], "why": DEFERRED}
    assert "split_after" not in out["parser"] and not deferral_problems(with_deferrals(_three_parts(fits_one_session=False)))


def test_a_producer_a_criterion_names_is_not_waited_on_nor_a_part_that_fits_nor_its_own_deferral():
    named = _three_parts(fits_one_session=False, criteria=[{"name": "c", "depends_on": "parser"}])
    assert with_deferrals(named)["subtasks"][2]["split_after"]["after"] == ["docs"]
    assert "split_after" not in with_deferrals(_three_parts())["subtasks"][2]
    own = {"after": ["parser"], "why": "the AST"}
    assert with_deferrals(_three_parts(fits_one_session=False, split_after=own))["subtasks"][2]["split_after"] == own


def test_the_authoring_round_writes_the_deferral_and_a_given_plan_keeps_its_own(monkeypatch):
    seen = []
    monkeypatch.setattr(D, "decompose_spec", lambda *a, **k: _three_parts(fits_one_session=False))
    monkeypatch.setattr(D, "_build_verified", lambda spec, *a, **k: seen.append(spec) or (_ for _ in ()).throw(
        RuntimeError("stop")))
    for given in (None, _three_parts(fits_one_session=False)):
        with pytest.raises(RuntimeError):
            D.decompose_into(make_engine(), "goal", llm=object(), spec=given)
    assert seen[0]["subtasks"][2].get("split_after") and not seen[1]["subtasks"][2].get("split_after")


@pytest.mark.parametrize("producers, why, said", [
    (("root.docs",), WHY, "root.docs is not such a part"),           # no seam: its result is not what the part reads
    (("root",), WHY, "root is not such a part"),                     # not of the same split
    ((), WHY, "names no part"),
    (("root.parser",), " ", "names no reason"),
])
def test_a_deferral_waits_only_on_a_producer_of_the_same_split(producers, why, said):
    e = _plan()
    with pytest.raises(ValueError, match=said):
        _defer(e, *producers, why=why)
    assert e.split_waits_on(TaskId("root.checker"), standing=True) == []


def test_a_deferral_on_a_settled_producer_is_refused_and_one_read_back_is_not():
    e = _plan()
    _defer(e, "root.parser")
    _pass(e, "root.parser")
    _defer(e, "root.parser")                                           # the same fixing read back by a rebuild
    e.record_session_fit(TaskId("root.checker"), "", False)            # …and a fresh one is a new fixing
    with pytest.raises(ValueError, match="only parts already in"):
        _defer(e, "root.parser")


def test_a_repair_adding_a_second_producer_keeps_the_deferral_and_the_first_is_contact_in_hand():
    """A standing deferral re-read with one producer settled and a new one named still waits — on the new one alone —
    and is asked once that one is in (critic: the rebuild cancelled it and asked the split at once, the FM-6 guess)."""
    e = _plan()
    _defer(e, "root.parser")
    _pass(e, "root.parser")
    declare(e, "root.docs", "root.checker", glue="the checker's messages follow the docs")
    e.wait_idle()
    _defer(e, "root.parser", "root.docs")
    assert e.split_waits_on(TaskId("root.checker")) == ["root.docs"] and _asked(e, "root.checker") != "split"
    _pass(e, "root.docs")
    assert _asked(e, "root.checker") == "split"
    assert e.split_waits_on(TaskId("root.checker"), standing=True) == ["root.parser", "root.docs"]


def test_a_plan_handed_in_whole_under_auto_cannot_defer_a_split_the_system_never_makes():
    """Under AUTO only: there a plan handed in whole is the user's (`users_plan`); elsewhere it is still split."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    spec = {"name": "c", "root_criteria": [criterion("g", "G")], "subtasks": [
        {"id": "a", "name": "a", "description": "a", "criteria": [criterion("a_ok", "a")],
         "split_after": {"after": ["b"], "why": WHY}}], "mappings": [{"criterion": "g", "child_id": "a"}], "deps": []}
    assert _no_deferral_nobody_makes(spec, splittable=True) is spec
    e.workforce.publish_executor_pool({"exec-1": None, "exec-2": None})
    e.set_mode(Mode.AUTO, None, AgentId("user"))
    with pytest.raises(ValueError, match="never split by the system"):
        auto_decompose(e, request="c", spec=spec)
    assert e.graph.get_task(TaskId("root")) is None                     # refused before anything is built


def test_a_fold_keeps_a_deferral_it_does_not_mention_and_reads_its_ids_as_the_plan_names_them():
    """A refine or repair round over a deferred part neither erases its deferral nor names its producers by the
    projection's prefixed ids (critic: both dropped it silently and the part was split blind)."""
    held = {"subtasks": [{"id": "parser"}, {"id": "checker", "criteria": [], "split_after": {"after": ["parser"],
                                                                                            "why": WHY}}],
            "deps": [{"from": "parser", "to": "checker"}], "mappings": [], "root_criteria": []}
    merged, _ = fold_merge(held, {"update_subtasks": [{"id": "checker", "criteria": [criterion("sharper", "x")]}]})
    assert next(s for s in merged["subtasks"] if s["id"] == "checker")["split_after"]["after"] == ["parser"]
    echoed = _dens_patch({"update_subtasks": [{"id": "root.checker", "split_after": {"after": ["root.parser"],
                                                                                     "why": WHY}}]}, "root")
    assert echoed["update_subtasks"][0]["split_after"]["after"] == ["parser"]


def test_the_plan_file_carries_the_deferral_both_ways():
    e = _plan()
    _defer(e, "root.parser")
    spec = extract_spec(e, "root")
    part = next(s for s in spec["subtasks"] if s["id"] == "checker")
    assert part["split_after"] == {"after": ["parser"], "why": WHY}
    back = artifact.parse(artifact.render("a compiler", spec))["spec"]
    assert next(s for s in back["subtasks"] if s["id"] == "checker")["split_after"] == part["split_after"]
    assert deferral_problems(spec) == []


def test_a_plan_deferring_on_what_no_seam_brings_is_repaired_before_the_build():
    spec = {"subtasks": [{"id": "parser"}, {"id": "checker", "split_after": {"after": ["parser"], "why": WHY}},
                         {"id": "docs", "split_after": {"after": ["parser"], "why": WHY}}],
            "deps": [{"from": "parser", "to": "checker"}]}
    assert [p.split(" ")[0] for p in deferral_problems(spec)] == ["docs"]


def test_the_round_that_splits_is_handed_what_its_producer_delivered(tmp_path, monkeypatch):
    """The parser's own file at the commit its accepted DELIVER carried, not the tree as it stands after: a later edit on
    the branch is not what was accepted (§11.3, the after phase)."""
    repo = tmp_path / "parser"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo,  # noqa: E731
                                    check=True, capture_output=True, text=True).stdout.strip()
    git("init", "-q")
    (repo / "ast.py").write_text("class Node:  # the AST the parser delivers\n    kind: str\n")
    (repo / "my file.py").write_text("SPACED = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "parser")
    sha = git("rev-parse", "HEAD")
    (repo / "ast.py").write_text("class Changed: ...\n")
    git("commit", "-qam", "after the delivery")
    e = _plan()
    e.record_seam_claim(TaskId("root.parser"), {"writes": ["ast.py", "my file.py"]})
    _defer(e, "root.parser")
    who = str(e.graph.get_task(TaskId("root.parser")).assignee)
    T.signal(e, "root.parser", "ACCEPT", who)
    e.send_signal_sync(SignalData(task_id=TaskId("root.parser"), signal=Signal.DELIVER, source=AgentId(who),
                                  result="parser done", commit=sha))
    instrument_passes(e, TaskId("root.parser"))
    T.signal(e, "root.parser", "PASS", str(e.graph.issuer_of(TaskId("root.parser"))))
    e.wait_idle()
    monkeypatch.setattr(WS, "node_workspace", lambda engine, agents, tid: str(repo) if str(tid) == "root.parser" else None)
    said = WS.results_a_split_waits_on(e, AgentRegistry(path=str(tmp_path / "agents.json")), "root.checker")
    assert "class Node:" in said and "Changed" not in said
    assert "SPACED = 1" in said                                          # a name with a space is read too
    assert any("its split is made with what root.parser delivered — 2 file(s)" in r["message"]
               for r in e.pipeline_log()), "the person reads that the split waited and on what"
    assert f"commit {sha}" in said and "parser_ok: pass" in said
    assert WS.results_a_split_waits_on(e, AgentRegistry(path=str(tmp_path / "agents.json")), "root.docs") == ""


def test_the_issuers_split_round_authors_over_that_contact(monkeypatch):
    """Through the real verb and the real authoring: the search and the fold read the contact in a section of its own,
    and the goal's obligations read the node's contract alone — none mined from a producer's source (critic, twice: the
    contact was appended to the task, and the obligations reader took the parser's code for the goal)."""
    seen = {}
    monkeypatch.setattr(DG, "results_a_split_waits_on", lambda engine, agents, node: "# THE RESULTS — AST of Node")
    monkeypatch.setattr(L, "search", lambda llm, request, prev, fast=False, ground="": seen.setdefault(
        "search", (request, ground)) and "")
    monkeypatch.setattr(L, "_obligations_first", lambda llm, request: seen.setdefault("obligations", request) and "")
    monkeypatch.setattr(L, "audit_fold", lambda llm, request, state, holes, fast=False, executor="", ground="":
                        seen.setdefault("fold", (request, ground)) and {})
    e = _plan()
    _defer(e, "root.parser")
    DG.ISSUER_VERBS.refine(e, "root.checker")
    for stage in ("search", "fold"):
        task, ground = seen[stage]
        assert "checker" in task and "AST of Node" not in task and ground == "# THE RESULTS — AST of Node", stage
    assert "checker" in seen["obligations"] and "AST of Node" not in seen["obligations"]


def test_a_producer_no_longer_seamed_into_the_part_is_no_ground_to_wait_on():
    """A repair that replaced or dropped the named producer leaves the split asked, not waiting on nobody (critic: a
    reshape replacing the parser left the checker OFFERED to its bound)."""
    e = _plan()
    _defer(e, "root.parser")
    undeclare(e, "root.parser", "root.checker")
    e.wait_idle()
    assert e.split_waits_on(TaskId("root.checker")) == [] and _asked(e, "root.checker") == "split"


def test_a_rebuild_over_a_settled_producer_records_every_part_and_owes_the_split_now():
    """A fold re-wording the reason of a standing deferral is the same fixing; a NEW deferral on a producer that has
    settled is taken back to "owed now", said, and the parts after it are still recorded (critic: it raised mid-build)."""
    e = _plan()
    _defer(e, "root.parser")
    _pass(e, "root.parser")
    _defer(e, "root.parser", why=WHY + ".")                            # re-worded: the same fixing read back
    e.record_session_fit(TaskId("root.checker"), "", True)
    ns = lambda i: f"root.{i}"                                           # noqa: E731
    _record_the_session_fit(e, {"subtasks": [
        {"id": "checker", "volume": "v", "fits_one_session": True, "split_after": {"after": ["parser"], "why": WHY}},
        {"id": "docs", "volume": "v", "fits_one_session": False}]}, TaskId("root"), ns)
    assert session_fit(e.graph, TaskId("root.checker")) == {"volume": "v", "fits": False}
    assert session_fit(e.graph, TaskId("root.docs"))["fits"] is False


def test_the_review_and_the_customer_read_each_deferral():
    e = _plan()
    _defer(e, "root.parser")
    assert f"- root.checker: split after root.parser — {WHY}" in e.project(TaskId("root"))
    before = extract_spec(e, "root")
    after = {**before, "subtasks": [{k: v for k, v in s.items() if k != "split_after"} for s in before["subtasks"]]}
    assert "checker: split deferred until parser deliver" in changes(after, before)
    assert "checker: no longer deferred — split now" in changes(before, after)



def test_a_deferral_is_taken_back_by_saying_so_and_kept_by_silence():
    """A refine's fold carries a deferral over an update that does not mention it; `after: []` takes it back (critic:
    `refine_plan` could not remove a system-written deferral)."""
    spec = with_deferrals(_three_parts(fits_one_session=False))
    silent = {k: v for k, v in spec["subtasks"][2].items() if k != "split_after"} | {"name": "c2"}
    kept, _ = fold_merge(spec, {"update_subtasks": [silent]})
    gone, _ = fold_merge(spec, {"update_subtasks": [{**spec["subtasks"][2], "split_after": {"after": [], "why": ""}}]})
    assert kept["subtasks"][2].get("split_after") and "split_after" not in gone["subtasks"][2]
    prefixed = _three_parts(fits_one_session=False, criteria=[{"name": "c", "depends_on": "root.parser"}])
    assert with_deferrals(prefixed)["subtasks"][2]["split_after"]["after"] == ["docs"]
