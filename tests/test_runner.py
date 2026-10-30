"""L2 critic runner — the STRUCTURAL gate + the causal-correctness CHECKER + validate storage/dirty-flag.
The gate blocks the checker; a clean node with no usable LLM produces NO verdict (never read as clean);
with an LLM, ONE zero-tool call yields per-parent-criterion sufficient/insufficient/uncertain + FM-2
conflicts; an INCOMPLETE verdict (a parent criterion unchecked) is treated as NO verdict."""
import json

import pytest

from gfso.engine import Engine
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import (TaskId, AgentId, Spec, Criteria, CriterionMapping, AcceptedRiskItem, Predictability,
                             Register)
from gfso.critic.runner import critique_node, review_decomposition
from tests.support import DENIAL, criterion, make_engine, pinned
from gfso import tools as T, driver, serverctl


def _engine() -> Engine:
    e = make_engine(llm=StubLLM(), validate_signals=False)
    e.start()
    return e


def _decompose_clean(e: Engine):
    # genuinely L0/L1-clean: every child mapped, ACCEPTED_RISKS present (a classified RISK event — v3.7 §9.2:
    # a scope boundary would not belong here, and an unclassified record fails the STD-2 guard), seam has glue.
    # The register rides the split, its decomposer's (§9.2): a parent's pre-filled one is task data, not the split's.
    e.assign_task(
        TaskId("p"),
        Spec("p", (Criteria("c1", "x", check=pinned("c1")), Criteria("c2", "y", check=pinned("c2")))),
        AgentId("pm"),
    )
    e.wait_idle()
    e.decompose_task(TaskId("p"), [
        (TaskId("a"), Spec("a", (Criteria("a1", "A1", check=pinned("a1")),)), AgentId("d1")),
        (TaskId("b"), Spec("b", (Criteria("b1", "B1", check=pinned("b1")),)), AgentId("d2")),
    ], criterion_mappings=[CriterionMapping("c1", TaskId("a")), CriterionMapping("c2", TaskId("b"))],
        register=Register((AcceptedRiskItem("provider rate-limit spike", Predictability.STATISTICAL, "P<1%, off-peak run",
                                            "a spike is seen", 0.01, "the run waits for the provider"), DENIAL)))
    e.wait_idle()
    e.add_dependency(TaskId("a"), TaskId("b"), glue="b reads a's total")


def test_leaf_is_reviewed_by_the_atomicity_question():
    """A childless node is no longer "nothing to review": D(t)=∅ is itself a plan claim (one unit of
    work), checked by the atomicity question. With a stub LLM returning nothing usable, the verdict
    stays None — never read as clean (tests/test_l2_gate.py owns the gate that reads it)."""
    e = _engine()
    e.assign_task(TaskId("leaf"), Spec("x", (Criteria("c", "y", check=pinned("c")),)), AgentId("d"))
    e.wait_idle()
    crit = critique_node(e, TaskId("leaf"))
    assert crit.gate_passed and crit.semantic_covered is None


def test_gate_blocks_on_l0l1_failure():
    e = _engine()
    # parent with a criterion but NO mapping → CHECK-1 coverage FAIL
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "x", check=pinned("c")),)), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [(TaskId("a"), Spec("a", (Criteria("a1", "A1", check=pinned("a1")),)), AgentId("d1"))])
    e.wait_idle()
    crit = critique_node(e, TaskId("p"))
    assert not crit.gate_passed
    assert any("CHECK-1" in f for f in crit.l0l1_failures)


def test_clean_node_passes_gate_no_semantic_without_llm():
    """A structurally-clean non-leaf passes the gate; with no LLM (or a stub returning nothing) the
    semantic verdict stays None — an absent hunt is NEVER read as clean."""
    e = _engine()
    _decompose_clean(e)
    crit = critique_node(e, TaskId("p"))
    assert crit.gate_passed
    assert crit.semantic_covered is None and crit.semantic_findings == ""


class _CheckerLLM:
    """Fake checker: records the input, returns a scripted JSON verdict — and to the question about the
    GOAL, the goal's answer (no gaps): a plan verdict given to it is an unread goal, never a clean one."""
    def __init__(self, reply: str):
        self.reply, self.seen = reply, []

    def complete(self, prompt: str, context: str = "") -> str:
        self.seen.append((prompt, context))
        return '{"gaps": []}' if '"gaps"' in prompt else self.reply


def _verdict_json(criteria, conflicts=()):
    return "```json\n" + json.dumps({"criteria": list(criteria), "conflicts": list(conflicts)}) + "\n```"


def test_checker_all_sufficient_is_covered():
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM(_verdict_json([
        {"criterion": "c1", "verdict": "sufficient", "why": "a's pass carries it"},
        {"criterion": "c2", "verdict": "sufficient", "why": "b's pass carries it"}]))
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is True and crit.semantic_findings == ""
    assert len(crit.criteria_verdicts) == 2
    # the checker checks the node's ONE canonical read (the projection), under the checker role
    prompt, context = llm.seen[0]
    assert "DECOMPOSITION LEVEL UNDER CHECK" in prompt and "CHECKER, not a decomposer" in context


def test_checker_gap_and_conflict_are_advisory_findings():
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM(_verdict_json(
        [{"criterion": "c1", "verdict": "insufficient",
          "why": "a can pass with stale data and c1 still fails"},
         {"criterion": "c2", "verdict": "uncertain", "why": "depends on the retention policy"}],
        [{"between": ["a", "b"], "why": "a demands sync writes, b demands async-only"}]))
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is False
    assert "stale data" in crit.semantic_findings and "conflict" in crit.semantic_findings
    assert len(crit.conflicts) == 1


def test_checker_incomplete_verdict_is_no_verdict():
    """A parent criterion the checker did not check ⇒ semantic_covered=None — an incomplete
    certificate is NEVER read as clean."""
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM(_verdict_json([{"criterion": "c1", "verdict": "sufficient", "why": "ok"}]))
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is None
    assert "INCOMPLETE" in crit.semantic_findings and "c2" in crit.semantic_findings


def test_criteria_labelled_and_glossed_by_the_checker_are_read_by_their_text():
    """`V1 c1` / `V2 c2 (gloss)` / `c1: x`: a haiku checker labelled all 40 of a root's criteria so, every one read as
    unchecked, two reviews gave no verdict (GB_coreutils_tnq9d1176). A bare number names nothing by text.
    CONTROL: `_named` as an exact match only."""
    from gfso.critic.runner import _named
    got = [_named(s, ["c1", "c2"]) for s in ("V1 c1", "V2 c2 (b carries it)", "c1: x", "V2", "V3")]
    assert got == ["c1", "c2", "c1", "V2", "V3"]


def test_a_reading_is_keyed_by_its_numbers_only_where_its_own_text_bears_them_out():
    """Paraphrased, cut short or bare entries take their number when at least three entries' text is their n-th name
    and none carries ANOTHER criterion's exact name; one that does sends the whole reading back to its text — a number
    beating an exact name credited a doubt on one criterion to another and the gate passed (critic over e9e19d4).
    CONTROL: drop the `against` condition and the second case is credited by number."""
    from gfso.critic.runner import _numbered
    names = ["c1", "c2", "c3", "c4: the long one", "c4"]
    rows = [{"criterion": "V1 c1"}, {"criterion": "V2 c2 (gloss)"}, {"criterion": "V3 c3"},
            {"criterion": "V4 c4: the long"}, {"criterion": "V5"}]
    assert [r["criterion"] for r in _numbered(rows, names)] == names
    swapped = [{"criterion": "V1 c1"}, {"criterion": "V2 c2"}, {"criterion": "V3 c3"},
               {"criterion": "V4 c4", "why": "DOUBT about c4"}, {"criterion": "V5 c4: the long one"}]
    assert [r["criterion"] for r in _numbered(swapped, names)][3:] == ["c4", "c4: the long one"]
    assert [r["criterion"] for r in _numbered([{"criterion": "V1 c1"}, {"criterion": "V2 something else"}],
                                              names)] == ["c1", "V2 something else"]      # two agree: not borne out


def test_a_glossed_name_under_another_number_sends_the_reading_back_to_its_text():
    """`V1 beta (stderr)` insufficient under alpha's number, alpha settled: the doubt was keyed to alpha, skipped as
    decided, and the gate passed over beta (critic over 076abfb). CONTROL: `against` on exact names only."""
    from gfso.critic.runner import _numbered
    names = ["alpha", "beta", "gamma", "delta", "eps"]
    rows = [{"criterion": "V1 beta (stderr)"}, {"criterion": "V2 alpha (build)"}, {"criterion": "V3 gamma"},
            {"criterion": "V4 delta"}, {"criterion": "V5 eps"}]
    assert [r["criterion"] for r in _numbered(rows, names)][:2] == ["beta", "alpha"]


def test_an_entry_naming_a_criterion_in_another_word_form_is_that_criterion():
    """`invalid option or count exit 1` for `invalid option or count exits 1`, in every reading: INCOMPLETE round after
    round (GB_coreutils_tnqh4a016). Only where one name reads so and no other entry answered it.
    CONTROL: drop the word-form pass and the first case stays unmapped."""
    from gfso.critic.runner import _numbered
    names = ["build works", "invalid option or count exits 1"]
    got = _numbered([{"criterion": "build works"}, {"criterion": "Invalid option or count exit 1."}], names)
    assert [r["criterion"] for r in got] == names
    twice = _numbered([{"criterion": "invalid option or count exits 1"}, {"criterion": "invalid option or count exit 1"}],
                      names)
    assert [r["criterion"] for r in twice] == ["invalid option or count exits 1", "invalid option or count exit 1"]


def test_a_conflict_with_a_settled_child_is_reported_not_gated():
    """A new child contradicting a DONE one: no move of the decomposer drops or revises the DONE child, and a
    re-admission does not re-check what is settled (§11.5) — gated, the plan sat shut to the row's ceiling
    (GB_coreutils_tnql66996). The same conflict between two live children still gates.
    CONTROL: gate on every conflict and the first case stays shut."""
    import dataclasses
    from gfso.core.types import State
    conflict = [{"between": ["a (a1)", "b (b1)"], "why": "a counts 4, b pins 3"}]
    reply = _verdict_json([{"criterion": "c1", "verdict": "sufficient", "why": "a"},
                           {"criterion": "c2", "verdict": "sufficient", "why": "b"}], conflict)
    e = _engine()
    _decompose_clean(e)
    crit = critique_node(e, TaskId("p"), llm=_CheckerLLM(reply))
    assert crit.semantic_covered is False                                  # two live children: gated
    a = e.graph.get_task(TaskId("a"))
    e.graph.save_task(dataclasses.replace(a, state=State.DONE))
    crit = critique_node(e, TaskId("p"), llm=_CheckerLLM(reply))
    assert crit.semantic_covered is True and "reported, not gating" in crit.semantic_findings, crit.semantic_findings


def test_a_doubt_a_later_reading_raised_on_a_criterion_the_first_left_out_stands():
    """Reading 1 leaves c2 out, readings 2–3 doubt it: the doubt is a finding — the verdict is folded over every reading,
    not reading 1's list (critic over 184dff5)."""
    e = _engine()
    _decompose_clean(e)
    one = _verdict_json([{"criterion": "c1", "verdict": "sufficient", "why": "a"}])
    two = _verdict_json([{"criterion": "c1", "verdict": "sufficient", "why": "a"},
                         {"criterion": "c2", "verdict": "insufficient", "why": "REAL DOUBT"}])

    class _Readings(_CheckerLLM):
        n = 0
        def complete(self, prompt: str, context: str = "") -> str:
            if '"gaps"' in prompt:
                return '{"gaps": []}'
            self.n += 1
            return one if self.n == 1 else two

    crit = critique_node(e, TaskId("p"), llm=_Readings(""))
    assert crit.semantic_covered is False and "REAL DOUBT" in crit.semantic_findings, crit.semantic_findings


def test_checker_unparseable_is_no_verdict():
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM("I think it looks fine overall!")
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert crit.gate_passed and crit.semantic_covered is None


def test_checker_gated_by_structure():
    """L2 presupposes a structurally-complete graph: a failing gate must not spend the LLM."""
    e = _engine()
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c", "x", check=pinned("c")),)), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("p"), [(TaskId("a"), Spec("a", (Criteria("a1", "A1", check=pinned("a1")),)), AgentId("d1"))])
    e.wait_idle()
    llm = _CheckerLLM("should never be called")
    crit = critique_node(e, TaskId("p"), llm=llm)
    assert not crit.gate_passed and llm.seen == []


def test_validate_stores_and_sets_verified_then_dirties():
    e = _engine()
    _decompose_clean(e)
    assert e.graph.get_task(TaskId("p")).verified is False
    crit = review_decomposition(e, TaskId("p"))
    assert crit.gate_passed
    assert e.graph.get_task(TaskId("p")).verified is True            # validated → fresh
    assert e.get_critique(TaskId("p"))["gate_passed"] is True  # stored record
    e.remove_dependency(TaskId("a"), TaskId("b"))              # a decomposition change must dirty it
    assert e.graph.get_task(TaskId("p")).verified is False


def test_review_record_carries_provenance_and_get_review_reads_it():
    """Re-validation UX: the stored record says WHO reviewed (model) and WHEN (ts); get_review is the
    free read (no LLM) agents/UI consume; a shape change stales freshness but KEEPS the record
    (so a re-run has something to be compared against)."""
    e = _engine()
    _decompose_clean(e)
    llm = _CheckerLLM(_verdict_json([
        {"criterion": "c1", "verdict": "sufficient", "why": "ok"},
        {"criterion": "c2", "verdict": "sufficient", "why": "ok"}]))
    llm.model = "sonnet-test"
    review_decomposition(e, TaskId("p"), llm=llm)
    out = T.get_review(e, "p")
    assert out["verified"] is True
    assert out["review"]["model"] == "sonnet-test" and out["review"]["ts"]
    assert out["review"]["semantic_covered"] is True
    e.remove_dependency(TaskId("a"), TaskId("b"))
    out2 = T.get_review(e, "p")
    assert out2["verified"] is False                    # stale…
    assert out2["review"]["model"] == "sonnet-test"     # …but the record survives for comparison


def test_edit_criteria_on_child_stales_parent_review():
    """The freshness contract: ANY shape change — including a CHILD's criteria edit — stales the
    parent's stored review (the checker checked a mapping that no longer exists)."""
    e = _engine()
    _decompose_clean(e)
    review_decomposition(e, TaskId("p"))
    assert e.graph.get_task(TaskId("p")).verified is True
    T.edit_criteria(e, "a", [criterion("x2", "tighter")], "pm")
    assert e.graph.get_task(TaskId("p")).verified is False


def test_child_reassign_dirties_parent():
    """Cross-node invalidation: a re-assigned child changes the parent's CHECK-1/7 → parent recomputed
    and marked stale."""
    e = _engine()
    _decompose_clean(e)
    review_decomposition(e, TaskId("p"))
    assert e.graph.get_task(TaskId("p")).verified is True
    e.assign_task(TaskId("a"), Spec("a v2", (Criteria("c1", "x", check=pinned("c1")),)), AgentId("d1"), parent_id=TaskId("p"))
    e.wait_idle()
    assert e.graph.get_task(TaskId("p")).verified is False


def test_gfso_run_goes_through_the_live_server_when_there_is_one(monkeypatch):
    """One engine, one writer, one sequencer over the log.

    `gfso run` opened the database directly, always — a second engine over the same SQLite file
    while the server holds it. The log's guarantees rest on there being ONE sequencer (Inv-7's
    single non-branching history; §12.14 requires a consumption check and the edge it authorizes to
    be one log-serialized step), and two writers are two sequencers. The visible half was smaller
    and still wrong: a CLI write reached neither the UI, nor the dispatcher, nor the observation
    panel until something reloaded.
    """
    sent = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true}'

    def _urlopen(req, timeout=None):
        sent["url"] = req.full_url
        sent["body"] = json.loads(req.data)
        return _Resp()

    monkeypatch.setattr(serverctl, "runtime", lambda *a, **k: {"code_version": "x"})
    monkeypatch.setattr(driver.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(driver, "build_engine_from_env",
                        lambda *a, **k: pytest.fail("it opened the database behind a live server"))

    driver.run(["signal", "n1", "ACCEPT", "source=alice", "project=work"])

    assert sent["url"].endswith("/api/run/signal?project=work")
    assert sent["body"]["task_id"] == "n1"          # positionals named off the same signature
    assert sent["body"]["signal"] == "ACCEPT"
    assert sent["body"]["source"] == "alice"


def test_gfso_run_still_works_with_no_server(monkeypatch, tmp_path):
    """…and with nothing listening, the direct path is correct and is the only one there is."""
    monkeypatch.setattr(serverctl, "runtime", lambda *a, **k: None)
    monkeypatch.setenv("GFSO_DB_PATH", str(tmp_path / "g.db"))
    driver.run(["create_task", "n1", '{"description": "x", "criteria": [criterion("a", "A")]}'])
    driver.run(["get_task", "n1"])
