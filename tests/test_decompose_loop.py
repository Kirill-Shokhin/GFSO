"""The decompose function's guarantees, driven deterministically (FakeLLM, no network):
- the structured spec is emitted ONLY on the final search↔audit round (intermediate rounds carry prose);
- ALREADY-COVERED early exit shortens the loop (depth = upper bound, not padding);
- the build is verified: problems → bounded repair (corrective audit call + wholesale re-build as
  revision) → clean list_holes, or an HONEST residue in `holes` (never a silent partial)."""
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.types import TaskId
from gfso.decompose import decompose_into, decompose_spec
from gfso.decompose.loop import SEARCH_PROMPT, AUDIT_PROMPT


class FakeLLM:
    """Queues per channel; records (kind, system) per call so the loop shape is assertable."""
    def __init__(self, texts, specs):
        self.texts, self.specs, self.calls = list(texts), list(specs), []

    def complete(self, prompt, context=""):
        kind = "search" if context == SEARCH_PROMPT else "audit_text"
        self.calls.append((kind, prompt))
        return self.texts.pop(0) if self.texts else ""

    def complete_structured(self, system, user, schema):
        self.calls.append(("structured", user))
        return self.specs.pop(0) if self.specs else {}


def _spec(mappings=None, neglected=None):
    return {
        "name": "Thing", "basis_markdown": "## basis",
        "root_criteria": [{"name": "rc1", "description": "A done"}, {"name": "rc2", "description": "B done"}],
        "subtasks": [
            {"id": "a", "name": "A", "description": "do A", "criteria": [{"name": "a1", "description": "A ok"}]},
            {"id": "b", "name": "B", "description": "do B", "criteria": [{"name": "b1", "description": "B ok"}]},
        ],
        "mappings": mappings or [{"criterion": "rc1", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}],
        "deps": [{"from": "a", "to": "b", "glue": "B reads A's output"}],
        "neglected": neglected or [{"item": "provider outage", "predictability": "STATISTICAL",
                                    "justification": "P<1%", "invalidation": "outage seen"}],
    }


def test_spec_emitted_only_on_final_round():
    """depth=3 → 3 searches, 2 prose-only audits, ONE structured audit (the last)."""
    fake = FakeLLM(texts=["holes1", "md1", "holes2", "md2", "holes3"], specs=[_spec()])
    decompose_spec("task", depth=3, llm=fake)
    kinds = [k for k, _ in fake.calls]
    assert kinds == ["search", "audit_text", "search", "audit_text", "search", "structured"]


def test_already_covered_exits_early():
    """depth=3 but the pass-2 searcher reports ALREADY-COVERED → the loop finalizes immediately."""
    fake = FakeLLM(texts=["holes1", "md1", "ALREADY-COVERED\nnothing new"], specs=[_spec()])
    decompose_spec("task", depth=3, llm=fake)
    kinds = [k for k, _ in fake.calls]
    assert kinds == ["search", "audit_text", "search", "structured"]   # rounds 3 skipped


def test_first_pass_never_early_exits():
    """A pass-1 'ALREADY-COVERED' cannot trigger the exit (there is no basis yet to be covered by)."""
    fake = FakeLLM(texts=["ALREADY-COVERED", "md1", "holes2"], specs=[_spec()])
    decompose_spec("task", depth=2, llm=fake)
    kinds = [k for k, _ in fake.calls]
    assert kinds == ["search", "audit_text", "search", "structured"]


def _eng():
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True)
    e.start()
    return e


def test_decompose_into_repairs_to_clean():
    """A spec with a drifted mapping name builds with problems → ONE corrective audit call returns the
    fixed spec → wholesale re-build (revision, same ids) → holes == [] (the guarantee)."""
    bad = _spec(mappings=[{"criterion": "rc1_typo", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}])
    fake = FakeLLM(texts=["holes1"], specs=[bad, _spec()])   # audit → bad; repair → fixed
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    assert res.holes == []
    assert ("structured",) == tuple(k for k, _ in fake.calls if k == "structured")[:1]
    # the repair call received the exposed problems
    repair_user = [u for k, u in fake.calls if k == "structured"][1]
    assert "rc1_typo" in repair_user
    e = res.engine
    root = e.get_task(TaskId("root"))
    assert {(m.criterion_name, m.child_id) for m in root.criterion_mappings} == \
        {("rc1", TaskId("root.a")), ("rc2", TaskId("root.b"))}


def test_decompose_into_reports_honest_residue():
    """If repair cannot fix the problems (fix call returns {}), the result carries them — no silent success."""
    bad = _spec(mappings=[{"criterion": "rc1_typo", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}])
    fake = FakeLLM(texts=["holes1"], specs=[bad])            # repair queue empty → {}
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    assert res.holes                                          # honest residue
    assert any("rc1_typo" in h for h in res.holes)


def test_repair_is_a_field_patch():
    """The corrective audit emits ONLY the fields it changes; the caller merges them into the spec —
    omitted fields (subtasks, deps, …) are kept as-is, a re-emitted field replaces wholesale."""
    bad = _spec(mappings=[{"criterion": "rc1_typo", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}])
    patch = {"mappings": [{"criterion": "rc1", "child_id": "a"}, {"criterion": "rc2", "child_id": "b"}]}
    fake = FakeLLM(texts=["holes1"], specs=[bad, patch])     # audit → bad; repair → PATCH (mappings only)
    res = decompose_into(_eng(), "task", root_id="root", llm=fake)
    assert res.holes == []                                    # patched to clean
    assert len(res.spec["subtasks"]) == 2                     # untouched fields survived the merge
    assert res.spec["mappings"][0]["criterion"] == "rc1"


def test_lean_final_carries_intermediate_basis():
    """LEAN default: the final audit emits structure only; at depth≥2 the carried intermediate prose is
    returned as basis_markdown (emit_basis=True restores prose emission in the final call itself)."""
    spec_no_basis = {k: v for k, v in _spec().items() if k != "basis_markdown"}
    fake = FakeLLM(texts=["holes1", "md-carried", "holes2"], specs=[spec_no_basis])
    out = decompose_spec("task", depth=2, llm=fake)
    assert out["basis_markdown"] == "md-carried"
    # lean is asked of the auditor explicitly (structured-fields-only instruction in user content)
    final_user = [u for k, u in fake.calls if k == "structured"][0]
    assert "structured fields ONLY" in final_user


def test_fast_appends_pace_suffixes_to_user_content_only():
    """fast=True rides the USER content of search + final audit (frozen cores untouched — the system
    prompts are byte-identical); fast=False leaves everything as before; the PATCH repair is never
    suffixed (it must stay minimal)."""
    from gfso.decompose.loop import SEARCH_FAST, AUDIT_FAST
    fake = FakeLLM(texts=["holes1"], specs=[_spec()])
    decompose_spec("task", depth=1, llm=fake, fast=True)
    search_user = [u for k, u in fake.calls if k == "search"][0]
    audit_user = [u for k, u in fake.calls if k == "structured"][0]
    assert search_user.endswith(SEARCH_FAST) and audit_user.endswith(AUDIT_FAST)

    fake2 = FakeLLM(texts=["holes1"], specs=[_spec()])
    decompose_spec("task", depth=1, llm=fake2)
    assert not any("Pace note" in u for _, u in fake2.calls)


def test_prose_to_spec_count_check_conservative():
    """The count-check flags STRONG basis→spec transcription loss (deficit ≥2 in an explicit D/Dep
    section) and stays silent otherwise (free prose — a misfire would trigger repairs on clean runs)."""
    from gfso.decompose import _count_problems
    md = ("# Basis\n## D — Components\n" + "\n".join(f"{i}. comp_{i} — text" for i in range(1, 8))
          + "\n\n## Dep — Seams\n- a → b: glue\n- b → c: glue\n- c → d: glue\n- d → e: glue\n\n## V\n")
    lossy = {"basis_markdown": md,
             "subtasks": [{"id": f"s{i}"} for i in range(4)],       # 7 enumerated vs 4 carried
             "deps": [{"from": "a", "to": "b"}]}                     # 4 vs 1
    probs = _count_problems(lossy)
    assert len(probs) == 2 and "7 components" in probs[0] and "4 seams" in probs[1]
    clean = {"basis_markdown": md, "subtasks": [{"id": f"s{i}"} for i in range(6)],  # deficit 1 → silent
             "deps": [{"from": "a", "to": "b"}, {}, {}]}
    assert _count_problems(clean) == []
    assert _count_problems({"basis_markdown": "", "subtasks": []}) == []             # no basis → silent
    assert _count_problems({"basis_markdown": "prose without sections", "subtasks": []}) == []
