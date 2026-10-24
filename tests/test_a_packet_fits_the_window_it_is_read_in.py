"""A root's standing findings grew to 1,394 on two criteria, every one written into the executor's packet: ~250k tokens,
every executor and consent session ended `prompt_too_long`, and the issuer — told only "DID NOT PARSE" — re-issued the
root 38 times (GB_sql_database_tmxu0n436, 2026-10-15)."""
from __future__ import annotations

from pathlib import Path

from gfso import issuer as I, packets as P, tools_llm as TL
from gfso.adapters.llm import headless as H
from gfso.adapters.llm.stats import _stat_line
from gfso.core.protocol.procedure import admission_defects, merge_regression, refuting_probes
from gfso.core.types import Criteria, Mode, Probe, TaskId
from tests.test_the_mode_decides_who_holds_what import _engine, _goal


def test_a_list_past_the_shown_count_is_in_a_file_the_text_names_none_withheld():
    lines = [f"standing finding [f{i}]: `query {i} printed 1, not 1.000`" for i in range(P.SHOWN_FINDINGS + 30)]
    text = P.capped(lines, "standing findings", "root-Query execution-findings")
    assert text.count("standing finding [") == P.SHOWN_FINDINGS
    path = text.rsplit(" in ", 1)[1].split(": grep it", 1)[0]
    listed = Path(path).read_text(encoding="utf-8")
    assert all(f"[f{i}]" in listed for i in range(len(lines))), "a line past the shown count was withheld"
    assert "[f49]" not in text and "30 more standing findings" in text
    assert P.capped(lines, "standing findings", "root-Query execution-findings") == text, "one file per key"


def test_a_short_list_stays_inline():
    assert P.capped(["probe: `x`"], "refuting probes", "k") == "\n  probe: `x`"


class _Llm:
    def __init__(self, **call):
        self.calls = [dict({"duration_ms": 1000, "output_tokens": 0}, **call)]


def test_a_call_that_ended_in_error_says_why():
    assert "prompt_too_long: Prompt is too long" in _stat_line(_Llm(error="prompt_too_long: Prompt is too long"))
    assert "error" not in _stat_line(_Llm())


def test_only_what_the_report_says_refuted_enters_the_store():
    """One root FAIL listed 1,036 probes on one criterion — the union of its split runs, the passing ones' too — and every
    one was filed as a refutation; the store grew to 1,414 findings."""
    probe = lambda i, **k: dict({"id": f"p{i}", "behaviour": "b", "command": f"run {i}", "expect": "e"}, **k)
    passed = {"criterion": "q", "verdict": "pass", "evidence": "ok", "probe": [probe(1), probe(2)]}
    failed = {"criterion": "q", "verdict": "fail", "evidence": "run 3 printed 1", "probe": [probe(3), probe(4, held=True)]}
    (entry,) = TL._conjoined([passed, failed])
    assert len(entry["probe"]) == 4, "the union the record holds the criterion to is kept"
    assert [p["as_run"] for p in refuting_probes([entry])["q"]] == ["run 3"]

def test_the_issuer_reads_why_its_nodes_sessions_stopped():
    e = _engine(Mode.AUTO)
    _goal(e)
    e.emit_info("delegate", "root: executor report DID NOT PARSE — no signals sent · ⚠ the call ended in error — "
                            "prompt_too_long: Prompt is too long")
    e.wait_idle()
    assert "prompt_too_long" in I.issuer_context(e, TaskId("root"), "parked")


def test_a_reworded_rerun_of_a_standing_finding_is_that_finding():
    """605 of 1,467 stored findings were re-runs of a standing one under a reworded command, each a new id."""
    stored = {"q": [{"id": "q#aaaa1111", "as_run": "printf 'x' | ./db"}]}
    rerun = {"id": "q#bbbb2222", "as_run": "{ echo x; } | ./db", "cited": "q#aaaa1111"}
    fresh = {"id": "q#cccc3333", "as_run": "echo y | ./db", "cited": ""}
    assert [p["id"] for p in merge_regression(stored, {"q": [rerun, fresh]})["q"]] == ["q#aaaa1111", "q#cccc3333"]
    assert [p["id"] for p in merge_regression(stored, {"q": [dict(rerun, cited="aaaa1111")]})["q"]] == ["q#aaaa1111"]


def test_a_probe_that_leaves_its_nodes_directory_is_not_admitted():
    """A plan's author running where the server stands pinned `cd /home/agent/gfso_home && …` on all 72 probes, and a
    validator following one removed the project's own database (GB_sql_database_tmzgc0724, 2026-10-16). Any absolute
    directory a plan names is a guess: the probe runs in its node's own."""
    crit = lambda cmd: [Criteria("lex", "tokens", check=(Probe("b", cmd, "PASS"),))]
    left = lambda cmd: any("absolute directory" in d for d in admission_defects(crit(cmd)))
    for cmd in ("cd /home/agent/gfso_home && gcc lexer.c", "make && cd /tmp/gfso-noplace-x && ./a", "pushd ~/w; make",
                r"(cd C:\work && make)", "cd '/srv/w' && make"):
        assert left(cmd), cmd
    for cmd in ("gcc lexer.c -o lx && ./lx", "cd {inputs} && ./run.sh", "T=$(mktemp -d); cd $T && cp ../a .",
                "./sql_database < {inputs}/q.sql", "make -C build"):
        assert not left(cmd), cmd

def test_a_call_naming_no_place_runs_in_an_empty_one(monkeypatch):
    seen = []

    def popen(*a, **k):
        seen.append(k.get("cwd"))
        raise RuntimeError("not spawned in a test")
    monkeypatch.setattr(H.subprocess, "Popen", popen)
    llm = H.HeadlessClaudeLLM()
    llm._cmd = llm._cmd or "claude"
    llm.complete("x")
    assert seen and seen[0] and "gfso-noplace-" in seen[0], seen
