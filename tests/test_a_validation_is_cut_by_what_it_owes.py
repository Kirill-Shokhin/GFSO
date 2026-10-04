"""A validation is cut into runs by what it OWES, and a criterion cut between runs is their conjunction.

Measured on the c_compiler root (GB_c_compiler_tmqn88552, every role on claude-haiku-5-5): 4 criteria, so one run under
a dial that counted criteria — and that run owed 75 probes (4 pinned, 33 distinct part probes re-run over the whole's
delivery, 38 regression lines), per criterion 47/42/14/36. Seventeen reports in 55 minutes were not a verdict, fifteen
of them for probes left out. A run now owes at most `GFSO_VALIDATION_BATCH` probes, a part's probe is carried by
exactly one run, and a criterion owing more than one run holds is split — its value the conjunction of the runs'
words on it, never the word of whichever run finished last.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from gfso import tools as T
from gfso import tools_llm as TL
from gfso.core.protocol.procedure import part_criteria, probe_id
from gfso.core.types import Criteria, Probe
from gfso.packets import _criteria_text, owed_probes
from tests.support import criterion
from tests.test_validate_result import _eng, _fenced

# ── the measured shape ────────────────────────────────────────────────────────────────────────────────────────────────

_POOL = [part_criteria(f"root.p{i}", [Criteria("c", check=(Probe(f"part {i}", f"run part {i}", "ok"),))])[0]
         for i in range(33)]
_SHAPE = {"F": (_POOL[:22], 24), "C": (_POOL[4:], 12), "B": (_POOL[10:23], 0), "I": (_POOL, 2)}   # 47/42/14/36


class _Owed:
    """The four reads `owed_probes` and the packet make — the measured root's procedure, nothing else."""
    def __init__(self):
        self.crits = [Criteria(n, f"{n} holds", check=(Probe(f"{n} own", f"own {n}", "ok"),)) for n in _SHAPE]

    def parts_procedure(self, _):
        return {n: parts for n, (parts, _) in _SHAPE.items()}

    def regression_probes(self, _):
        return {n: [{"id": f"{n}#r{k}", "command": f"again {n} {k}", "behaviour": "refuted once", "expect": "ok"}
                    for k in range(r)] for n, (_, r) in _SHAPE.items()}

    def retired_findings(self, _):
        return []

    def validation_procedure(self, _):
        return self.crits


def _measured():
    eng = _Owed()
    task = SimpleNamespace(id="root", spec=SimpleNamespace(criteria=eng.crits))
    return eng, task, [(task, "delivered", eng.crits)]


def test_the_measured_shape_owes_what_was_measured():
    eng, task, _ = _measured()
    owed = {c.name: len(items) for c, items in owed_probes(eng, task, eng.crits)}
    raw = {n: 1 + len(p) + r for n, (p, r) in _SHAPE.items()}
    assert raw == {"F": 47, "C": 42, "B": 14, "I": 36}
    assert sum(owed.values()) == 75 == 4 + 33 + 38          # …each part probe owed once, under its first criterion


@pytest.mark.parametrize("size", [16, 7, 40])
def test_each_run_owes_at_most_the_dial_and_each_probe_is_carried_once(size):
    eng, task, parts = _measured()
    runs = TL._scope_batches(eng, parts, size)
    carried = [pid for run in runs for *_, carry in run for pid in carry]
    assert all(sum(len(carry) for *_, carry in run) <= size for run in runs)
    assert sorted(carried) == sorted(pid for _, items in owed_probes(eng, task, eng.crits) for pid, _ in items)
    assert len(carried) == len(set(carried)) == 75
    # …and the packets write each part's probe out ONCE across the whole validation, every other criterion resting
    # on it pointed at it
    texts = [_criteria_text(eng, t, crits, None, None, carry) for run in runs for t, _, crits, carry in run]
    for c in _POOL:
        pid = probe_id(c.name, c.check[0])
        assert sum(f"PINNED CHECK [{pid}]" in x for x in texts) == 1, pid
    # …and a criterion owing more than a run holds says, in every run that speaks of it, that it is split
    split = {c.name for c, items in owed_probes(eng, task, eng.crits) if len(items) > size}
    for run in runs:
        for t, _, crits, carry in run:
            text = _criteria_text(eng, t, crits, None, None, carry)
            for c in crits:
                if c.name in split:
                    assert "SPLIT between runs" in text.split(f"**{c.name}**")[1].split("\n- **")[0]


def test_the_dial_at_zero_is_one_run_carrying_everything():
    eng, _, parts = _measured()
    (run,) = TL._scope_batches(eng, parts, 0)
    assert sum(len(carry) for *_, carry in run) == 75


# ── the fold: a criterion split between runs of ONE validation ───────────────────────────────────────────────────────

_LINE = re.compile(r"PINNED CHECK \[([^\]]+)\] — ([^:]+): run `([^`]+)`")


def _split_node(e):
    probes = [{"behaviour": f"wide {k}", "command": f"check wide {k}", "expect": "it holds"} for k in range(3)]
    T.create_task(e, "big", {"description": "a contract one criterion of which owes more than a run holds",
                             "criteria": [criterion("wide", check=probes), criterion("small")]}, "alice")
    T.signal(e, "big", "ACCEPT", "alice")
    T.signal(e, "big", "DELIVER", "alice", result="built it")


class _Runs:
    """Speaks of every criterion its packet lists, over the probes the packet carries; `word` on `wide` in the run that
    carries `bad`, `pass` elsewhere — the report's own verdict and failed list consistent with its entries."""
    def __init__(self, word, bad):
        self.word, self.bad, self.calls, self.packets = word, bad, [], []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        self.packets.append(user)
        lines = _LINE.findall(user)
        entries = []
        for name in ("wide", "small"):
            if f"**{name}**" not in user:
                continue
            mine = [(i, b, c) for i, b, c in lines if i.startswith(f"{name}#") or i.startswith(f"big/{name}#")
                    or c.startswith(f"check {name}")]
            word = self.word if name == "wide" and any(c == self.bad for _, _, c in mine) else "pass"
            entries.append({"criterion": name, "verdict": word,
                            "evidence": "ran it" if word == "pass" else f"{word}: {self.bad} printed nothing",
                            "behaviours": [b for _, b, _ in mine],
                            "probe": [{"id": i, "behaviour": b, "command": c, "expect": "it holds"}
                                      for i, b, c in mine]})
        red = [x["criterion"] for x in entries if x["verdict"] != "pass"]
        return _fenced({"verdict": "FAIL" if red else "PASS", "failed_criteria": red, "per_criterion": entries})

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


@pytest.mark.parametrize("bad", ["check wide 0", "check wide 2"])       # the word in the first run, or the last
@pytest.mark.parametrize("word", ["fail", "undecidable", "pass"])
def test_a_split_criterion_is_the_conjunction_of_its_runs(monkeypatch, word, bad):
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "2")
    e = _eng()
    _split_node(e)
    llm = _Runs(word, bad)
    out = TL.validate_result(e, "big", _llm=llm, workdir=".")
    assert len(llm.packets) == 2 and all("**wide**" in p and "SPLIT between runs" in p for p in llm.packets)
    record = e.get_exec_verdict(T.TaskId("big"))
    wide = [x for x in (record or {}).get("per_criterion") or () if x.get("criterion") == "wide"]
    if record:                                                     # …ONE value of the criterion, over every probe
        assert len(wide) == 1 and len(wide[0]["probe"]) == 3, wide
    if word == "pass":                                             # …every run passed, the union covers it: PASS
        assert out["verdict"] == "PASS" and record["verdict"] == "PASS"
    elif word == "fail":                                           # …one run refuted it: FAIL, the criterion cited
        assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["wide"]
        assert record["verdict"] == "FAIL" and record["failed_criteria"] == ["wide"]
        assert wide[0]["verdict"] == "fail"
        # …and the WHY that reaches the executor is the refutation, not the word of the run that passed its share
        ((c, why, _),) = e.rework_findings(T.TaskId("big"))
        assert c == "wide" and why.startswith(f"fail: {bad} printed nothing"), why
    else:                                                          # …one run left it undecided: no PASS — a FAIL
        assert out["verdict"] == "FAIL" and record["failed_criteria"] == ["wide"]   # (the report says so, validator.md)
        assert wide[0]["verdict"] == "undecidable"
    e.stop()


def test_a_split_run_that_left_the_criterion_out_does_not_pass_it(monkeypatch):
    """The union must cover what the criterion owes: a run silent on its share leaves those probes unobserved."""
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "2")
    e = _eng()
    _split_node(e)

    class _Silent(_Runs):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            text = super().run_agent(system, user, allowed_tools, cwd, timeout)
            if "check wide 0" not in user:
                return text
            return _fenced({"verdict": "PASS", "failed_criteria": [], "per_criterion": []})

    out = TL.validate_result(e, "big", _llm=_Silent("pass", None), workdir=".")
    assert out["verdict"] != "PASS"
    assert (e.get_exec_verdict(T.TaskId("big")) or {}).get("verdict") != "PASS"
    e.stop()
