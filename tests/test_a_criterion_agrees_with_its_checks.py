"""A criterion the system writes may not say what its own checks deny: the authoring catches it before the build, where
the system is still the plan's author (GB_coreutils_tn9t9u320: a root criterion named stdin `-` in headers while its
probe diffed against GNU's `standard input`; the root failed five times on it). What is judged is the text written now;
a plan the caller brings, a contract held as issued and a settled child are not read, and the TASK it is judged by is the
contract as it stood before the authoring."""
import gfso.decompose as DEC
from gfso.decompose.loop import AGREE_SCHEMA, FOLD_SCHEMA
from tests.test_decompose_loop import _graph_state, _eng

SAYS = "headers ==> NAME <== with - named as -"
FIXED = "headers ==> NAME <==, standard input named as GNU names it"
CHECK = {"behaviour": "stdin under -v is headed as GNU heads it",
         "command": "diff <(./head -v -n 1 - < s) <(/usr/bin/head -v -n 1 - < s) && echo ok", "expect": "ok"}


def _dash_named_plan(description=SAYS, check=(CHECK,)):
    s = _graph_state()
    s["root_criteria"][0] = dict(s["root_criteria"][0], description=description, check=list(check))
    return s


def _hit(takes="open"):
    return {"contradictions": [{"node": "root", "criterion": "rc1", "description_says": "- is named -",
                                "check_requires": "standard input", "task_says": "…", "task_takes": takes}]}


class _LLM:
    """Names the contradiction while the judged criteria carry SAYS beside the GNU check; the repair writes `repair`."""
    def __init__(self, takes="open", repair=FIXED, agree_fails_after=None):
        self.agree, self.repairs, self.takes, self.repair = [], [], takes, repair
        self.agree_fails_after = agree_fails_after

    def complete_structured(self, system, user, schema):
        if schema is AGREE_SCHEMA:
            self.agree.append(user)
            if self.agree_fails_after is not None and len(self.agree) > self.agree_fails_after:
                return {}
            judged = user.split("# CRITERIA AND THEIR CHECKS", 1)[1]
            return _hit(self.takes) if SAYS in judged else {"contradictions": []}
        assert schema is not FOLD_SCHEMA
        self.repairs.append(user)
        return {"root_criteria": _dash_named_plan(self.repair)["root_criteria"]} if self.repair else {}


def _agreed(llm, e, kw):
    """`authored` / `task` as the authoring passes them: one `_Agreement` for the whole act."""
    on, task = kw.pop("authored", False), kw.pop("task", "ship head")
    return {**kw, "agree": kw.pop("agree", None) or DEC._Agreement(llm, e, "root", task, on, kw.get("contract_fixed", False))}


def _build(llm, spec=None, **kw):
    e = _eng()
    try:
        return DEC._build_verified(spec or _dash_named_plan(), "ship head", e, "root", "exec-1", llm, **_agreed(llm, e, kw))
    finally:
        e.stop()


def test_a_criterion_contradicting_its_check_is_repaired_before_the_build():
    llm = _LLM()
    _, spec, problems = _build(llm, authored=True)
    assert len(llm.repairs) == 1 and "its own check requires standard input" in llm.repairs[0]
    assert SAYS not in str(spec["root_criteria"]) and problems == [] and len(llm.agree) == 2


def test_a_plan_the_caller_brings_is_not_read_against_its_checks():
    llm = _LLM()
    _build(llm)
    assert llm.agree == [] and llm.repairs == []


def test_a_contradiction_the_repair_left_is_the_builds_residue_not_silence():
    llm = _LLM(repair=None)
    _, _, problems = _build(llm, authored=True)
    assert any("the repair left it" in p for p in problems), problems


def test_a_failed_re_ask_does_not_erase_a_contradiction_already_found():
    llm = _LLM(repair=SAYS + " ", agree_fails_after=1)          # the repair rewrites the text, the re-ask answers ⊥
    _, _, problems = _build(llm, authored=True)
    assert any("its own check requires standard input" in p for p in problems), problems


def test_a_contradiction_the_task_demands_is_reported_never_reworded():
    llm = _LLM(takes="both")
    _, _, problems = _build(llm, authored=True)
    assert llm.repairs == [] and any("the TASK demands both" in p for p in problems), (llm.repairs, problems)


def test_a_repair_that_writes_the_contradiction_is_judged():
    """Entered for an admission refusal (a criterion pinning no check), the repairer pins the GNU check beside the
    prose that denies it — where the pair is born; the patch is judged, and the next round repairs it."""
    class _Pins(_LLM):
        def complete_structured(self, system, user, schema):
            if schema is not AGREE_SCHEMA and not self.repairs:
                self.repairs.append(user)
                return {"root_criteria": _dash_named_plan()["root_criteria"]}
            return super().complete_structured(system, user, schema)
    llm = _Pins()
    _, spec, problems = _build(llm, spec=_dash_named_plan(check=()), authored=True)
    assert SAYS not in str(spec["root_criteria"]) and problems == [], (spec["root_criteria"], problems)


def test_only_the_text_written_now_is_judged_and_never_as_its_own_task():
    """A rebuild over a standing plan judges only what changed; the standing root criterion is neither re-judged nor the
    TASK — the TASK is the contract as it stood before the authoring."""
    e = _eng()
    DEC._build_verified(_dash_named_plan(), "ship head", e, "root", "exec-1", _LLM(repair=None))     # stands, unjudged
    spec = _dash_named_plan()
    spec["subtasks"][0]["criteria"] = [dict(spec["subtasks"][0]["criteria"][0], description="MARK", check=[CHECK])]
    llm = _LLM()
    DEC._build_verified(spec, "ship head", e, "root", "exec-1", llm, **_agreed(llm, e, {"authored": True}))
    e.stop()
    assert len(llm.agree) == 1 and "MARK" in llm.agree[0] and SAYS not in llm.agree[0], llm.agree


def test_a_held_contract_and_a_settled_child_are_not_read():
    class _T:
        def __init__(self, state):
            self.state, self.spec = type("S", (), {"name": state})(), type("P", (), {"criteria": ()})()
    graph = type("G", (), {"get_task": lambda self, tid: _T("DONE") if str(tid) == "root.a" else None})()
    agree = DEC._Agreement(_LLM(), type("E", (), {"graph": graph})(), "root", "ship head", True, contract_fixed=True)
    spec = _dash_named_plan()
    spec["subtasks"][0]["criteria"] = [dict(spec["subtasks"][0]["criteria"][0], check=[CHECK])]
    assert all(n not in ("root", "a") for n, _ in agree._judged(spec)), agree._judged(spec)


def test_a_finding_outlives_the_round_that_found_it():
    """The first build flags what the TASK demands both ways; a later round of the same authoring rewrites something
    else — the finding still stands in what that round returns."""
    e, llm = _eng(), _LLM(takes="both")
    agree = DEC._Agreement(llm, e, "root", "ship head", True, False)
    DEC._build_verified(_dash_named_plan(), "ship head", e, "root", "exec-1", llm, agree=agree)
    spec = _dash_named_plan()
    spec["subtasks"][0]["criteria"] = [dict(spec["subtasks"][0]["criteria"][0], description="other", check=[CHECK])]
    _, _, problems = DEC._build_verified(spec, "ship head", e, "root", "exec-1", llm, agree=agree)
    e.stop()
    assert any("the TASK demands both" in p for p in problems), problems


def test_a_renamed_criterion_leaves_no_stale_finding():
    class _Renames(_LLM):
        def complete_structured(self, system, user, schema):
            if schema is AGREE_SCHEMA:
                return super().complete_structured(system, user, schema)
            self.repairs.append(user)
            rc = _dash_named_plan(FIXED)["root_criteria"]
            rc[0] = dict(rc[0], name="head-forms")
            return {"root_criteria": rc, "mappings": [{"criterion": "head-forms", "child_id": "a"},
                                                      {"criterion": "rc2", "child_id": "b"}]}
    llm = _Renames()
    _, _, problems = _build(llm, authored=True)
    assert len(llm.repairs) == 1 and not any("rc1" in p for p in problems), (len(llm.repairs), problems)


def test_the_repairer_is_told_which_side_the_task_takes():
    llm = _LLM(takes="description")
    _build(llm, authored=True)
    assert "Change the check so it decides what the description says" in llm.repairs[0], llm.repairs[0]


def test_a_check_that_could_not_run_is_said_not_read_as_agreement():
    llm = _LLM(agree_fails_after=0)
    _, _, problems = _build(llm, authored=True)
    assert any("undecided" in p and "rc1" in p for p in problems), problems


def test_a_finding_named_by_the_graphs_id_is_placed():
    class _Namespaced(_LLM):
        def complete_structured(self, system, user, schema):
            out = super().complete_structured(system, user, schema)
            if schema is AGREE_SCHEMA and out.get("contradictions"):
                out["contradictions"][0]["node"] = "root"          # the graph's id of the root, not the spec's
            return out
    llm = _Namespaced(repair=None)
    _, _, problems = _build(llm, authored=True)
    assert any("the repair left it" in p for p in problems), problems
