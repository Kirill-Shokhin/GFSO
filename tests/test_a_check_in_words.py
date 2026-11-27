"""A criterion's check is a COMMAND the system runs or a PROCEDURE in words a reader performs, its issuer stating which by
the field he fills (`Probe.procedure`). Before it every check was a command: an issuer whose decision procedure is a
reading wrote words into `command`, the system ran `read the delivery against prompt.md …` as bash, recorded the shell's
error as the pin's run, and no observation of the validator could carry the criterion — every such node ⊥.

CONTROLS (each breaks its test): `criteria_without_procedure` back to `_norm(p.command)` — the admission test; drop the
`misformed_checks` rung — the refusal tests; `_observe_pins`' filter `p.command.strip()` → `p.pins` — the no-run test;
drop `_in_words` from `_probe_line` — the packet test; `performed` → False — the pass test; `unrun_pinned` skipping
reader's checks — the undecided test; `probe_id` seeding the procedure first — the identity test."""
from __future__ import annotations

import json
import shutil
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from gfso.packets import _criteria_text
from tests.support import FakeSpec, committed, criterion, make_engine
from tests.test_the_mode_decides_who_holds_what import _FakeLLM, _admit, _engine, _kid

from gfso import tools as T, tools_llm as TL
from gfso.core.protocol.procedure import admission_defects, probe_id, procedure_digest
from gfso import issuer as I
from gfso.core.protocol.accounting import coverage, unrun_parts, unrun_pinned, with_part_observations
from gfso.core.types import Criteria, Mode, Probe, TaskId
from tests.test_validate_result import _eng, _fenced
import gfso.validate as VAL

BEH = "every behaviour prompt.md states holds"
WORDS = "read the delivery's table against prompt.md and say which behaviour it states is missing"
READ = {"behaviour": BEH, "procedure": WORDS}     # as a door hands it over


def test_a_check_in_words_is_admitted_and_one_of_both_forms_or_with_a_command_s_fields_is_refused():
    assert admission_defects([Criteria("c", "the table covers the prompt", check=(Probe.of(READ),))]) == []
    both = admission_defects([Criteria("c", "d", check=(Probe(BEH, "cat t.md", "x", procedure=WORDS),))])
    assert len(both) == 1 and "both a `command` and a `procedure`" in both[0], both
    fields = admission_defects([Criteria("c", "d", check=(Probe(BEH, "", "ok", procedure=WORDS),))])
    assert len(fields) == 1 and "is a procedure in words and carries expect" in fields[0], fields
    neither = admission_defects([Criteria("c", "d", check=(Probe(BEH, "cat t.md", "x"), Probe("b")))])
    assert len(neither) == 1 and "neither a `command` nor a `procedure`" in neither[0], neither


class _Reader:
    """A validator that passes `c` on `probes` and keeps the packet it was handed."""
    def __init__(self, probes):
        self.probes, self.user = probes, None
        self.calls, self.last_tool_calls, self.on_tick, self.stage_hint = [], {"Bash": 1}, None, ""

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.user = user
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        return _fenced({"verdict": "PASS", "failed_criteria": [], "per_criterion": [
            {"criterion": "c", "verdict": "pass", "evidence": "read the table against the prompt",
             "behaviours": [p["behaviour"] for p in self.probes], "divergences": [], "probe": self.probes}]})

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _validated(tmp_path, monkeypatch, probes) -> tuple[dict, _Reader, list]:
    place = tmp_path / ".gfso-nodes-p" / "n"
    place.mkdir(parents=True)
    (place / "table.md").write_text("| a | b |\n")
    (place / "prompt.md").write_text("a and b\n")
    ran = []
    real = VAL.run_checks

    def _seen(ex, probes, *a, **k):
        ran.extend(p for _, _, p in probes)
        return real(ex, probes, *a, **k)
    monkeypatch.setattr(VAL, "run_checks", _seen)
    e = _eng()
    T.create_task(e, "n", {"description": "a table of the prompt", "criteria": [
        {"name": "c", "description": "the table covers the prompt", "check": [READ]}]}, "alice")
    T.signal(e, "n", "ACCEPT", "alice")
    T.signal(e, "n", "DELIVER", "alice", result="table.md", _recorded=committed(place))
    llm = _Reader(probes)
    try:
        return VAL.validate_result(e, "n", _llm=llm, workdir=str(place)), llm, ran
    finally:
        e.stop()


#: the validator's own probe of the check in words, cited under ITS id — the only observation that performs it
OWN = [{"id": probe_id("c", READ), "behaviour": BEH, "command": "grep -c '|' table.md && cat prompt.md", "expect": "1",
        "held": True}]


def test_the_system_never_runs_a_check_in_words_and_hands_it_as_a_procedure_to_perform(tmp_path, monkeypatch):
    _, llm, ran = _validated(tmp_path, monkeypatch, OWN)
    assert ran == [], ran
    pid = probe_id("c", READ)
    assert f"PINNED PROCEDURE [{pid}] — {BEH}: {WORDS} → perform it" in llm.user, llm.user
    assert f"PINNED CHECK [{pid}]" not in llm.user and "the system RAN" not in llm.user


def test_a_report_citing_it_on_its_own_probe_passes(tmp_path, monkeypatch):
    out, _, _ = _validated(tmp_path, monkeypatch, OWN)
    assert out["verdict"] == "PASS", out


def test_a_report_observing_nothing_of_it_leaves_it_undecided(tmp_path, monkeypatch):
    """…its probe labelled with the behaviour and citing no id: the pinned procedure was not performed."""
    out, _, _ = _validated(tmp_path, monkeypatch, [{"behaviour": BEH, "command": "cat table.md", "expect": "|",
                                                    "held": True}])
    assert out["verdict"] is None and "not performed" in str(out.get("verdict_defects")), out


_OLD = [Criteria("out", "prints hi", check=(Probe("greets", "echo hi", "hi"),
                                            Probe("files", "cat {inputs}/a", "x", (("a", "x"),))))]


def test_a_mechanical_check_keeps_its_id_digest_and_form_and_one_in_words_is_named_by_its_words():
    """The values computed on main before `exact` existed (98ea31f, `test_the_system_runs_an_exact_check_itself`)."""
    assert procedure_digest(_OLD) == "22e254cd570381c8"
    assert [probe_id("out", p) for p in _OLD[0].check] == ["out#56a79f3b", "out#f1e846c3"]
    assert _OLD[0].check[0].to_dict() == {"behaviour": "greets", "command": "echo hi", "expect": "hi"}
    other = Probe(BEH, procedure="read the table against the prompt the other way")
    assert probe_id("c", READ) != probe_id("c", other) != probe_id("c", Probe(BEH))
    assert Probe.of(READ).to_dict() == {"behaviour": BEH, "command": "", "expect": "", "procedure": WORDS}
    assert procedure_digest([Criteria("c", "d", check=(Probe.of(READ),))]) != procedure_digest([Criteria("c", "d", check=(other,))])


@pytest.mark.parametrize("note, recorded", [("read the table against prompt.md: both behaviours stated, both there", True),
                                            ("", False)])
def test_a_hand_verdict_citing_it_with_what_was_seen_is_its_performance(note, recorded):
    """A verdict recorded by hand (`record_verdict`) is its recorder's own observation (§10.2, §10.3): citing the reader's
    check by id with evidence is that check performed; with no evidence it is a name, not an observation."""
    e = make_engine(check_interval=10_000)
    e.start()
    try:
        T.create_task(e, "n", {"description": "a table of the prompt", "criteria": [
            {"name": "c", "description": "the table covers the prompt", "check": [READ]}]}, "alice")
        T.signal(e, "n", "ACCEPT", "alice")
        T.signal(e, "n", "DELIVER", "alice", result="table.md")
        out = T.record_verdict(e, "n", "PASS", reviewer="bob",
                               observed={"c": {"note": note, "ran": [probe_id("c", READ)]}})
        assert bool(out.get("recorded")) is recorded and (recorded or "not performed" in str(out)), out
    finally:
        e.stop()


def _entry(criterion, *probes, evidence="read it"):
    return {"criterion": criterion, "verdict": "pass", "evidence": evidence, "behaviours": [], "probe": list(probes)}


LABELLED = {"behaviour": BEH, "command": "grep -c '|' table.md", "expect": "1"}


def test_a_part_s_check_in_words_performed_once_serves_every_criterion_of_the_whole_resting_on_it():
    """One observation, as a part's command is credited (`part_credit`) and the packet says: performed under `g1`, it is
    owed under `g2` no more."""
    part = Criteria("kid/k", "k holds", check=(Probe.of(READ),))
    parts = {"g1": (part,), "g2": (part,)}
    report = [_entry("g1", {**LABELLED, "id": probe_id(part.name, part.check[0])}),
              _entry("g2", {"behaviour": "other", "command": "cat table.md", "expect": "|"})]
    assert unrun_parts(parts, report) == {}


def test_a_constant_citing_it_performs_nothing_and_a_label_alone_performs_nothing():
    c, pid = Criteria("c", "d", check=(Probe.of(READ),)), probe_id("c", READ)
    assert unrun_pinned([c], [_entry("c", {"id": pid, "behaviour": BEH, "command": "echo ok", "expect": "ok"})]) == {
        "c": [pid]}
    assert unrun_pinned([c], [_entry("c", LABELLED)]) == {"c": [pid]}
    assert unrun_pinned([c], [_entry("c", {**LABELLED, "id": pid})]) == {}


def test_one_label_two_checks_in_words_carry_is_no_word_on_which_was_performed():
    twin = {"behaviour": BEH, "procedure": "read it the other way round"}
    c = Criteria("c", "d", check=(Probe.of(READ), Probe.of(twin)))
    assert sorted(unrun_pinned([c], [_entry("c", LABELLED)])["c"]) == sorted([probe_id("c", READ), probe_id("c", twin)])
    assert unrun_pinned([c], [_entry("c", {**LABELLED, "id": probe_id("c", READ)},
                                     {**LABELLED, "command": "wc -l table.md", "id": probe_id("c", twin)})]) == {}


def test_a_hand_verdict_s_record_counts_the_check_in_words_it_performed_as_run():
    c = Criteria("c", "d", check=(Probe.of(READ),))
    cited = [_entry("c", {"id": probe_id("c", READ)}, evidence="read the table against prompt.md: both there")]
    assert coverage([c], cited, by_hand=True)["pinned_probes_run"] == 1
    assert coverage([c], cited)["pinned_probes_run"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="the page's modules run under node")
def test_the_page_s_forms_keep_a_check_in_words(tmp_path):
    """Every authoring form reads its checks back through one filter; a reader's check dropped there left the contract the
    server admitted narrower than the one on the screen."""
    rows = [READ, LABELLED, {"behaviour": BEH, "command": "cat t.md"}, {"procedure": WORDS}]
    script = tmp_path / "case.mjs"
    here = Path(__file__).resolve().parent
    script.write_text("\n".join([f"import {{page, say}} from {json.dumps((here / 'page_in_node.mjs').as_uri())};",
                                 "const {keptProbe} = await import(page('forms.js'));",
                                 f"say({json.dumps(rows)}.map(keptProbe));"]), encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == [True, True, False, False]


def test_the_plan_door_teaches_the_check_in_words_beside_the_command():
    from_repo = (Path(__file__).resolve().parent.parent / "docs" / "PLAN_FORMAT.md").read_text(encoding="utf-8")
    assert "`procedure`" in from_repo and "procedure = " in TL.YOURS, "the plan door teaches commands only"


# === the outside critic over 6ab2a458: a check in words is performed only under its own id ===

def test_a_command_pin_s_run_sharing_the_behaviour_s_words_performs_no_check_in_words():
    """The packet asks a validator to cite a command pin from the system's run (`{id, held}`); filled in with the pin's
    behaviour (`with_part_observations`), that citation decided the check in words sharing the label — a false PASS."""
    pin = Probe(BEH, "grep -c '|' table.md", "1")
    c = Criteria("c", "d", check=(pin, Probe.of(READ)))
    cited = with_part_observations({}, [_entry("c", {"id": probe_id("c", pin), "held": True})], [c])
    assert unrun_pinned([c], cited) == {"c": [probe_id("c", READ)]}, cited
    rerun = [_entry("c", {"id": probe_id("c", READ), "behaviour": BEH, "command": pin.command, "expect": "1"})]
    assert unrun_pinned([c], rerun) == {"c": [probe_id("c", READ)]}, "the pin's command cited under its id is the pin's run"


def test_a_whole_restating_its_part_s_check_in_words_owes_one_check_under_one_id():
    """The packet shows the whole's copy and hides the part's (`same_probe`); performed under the shown id, the part's
    copy the gate demands is performed too."""
    part = Criteria("kid/k", "k holds", check=(Probe.of(READ),))
    whole = Criteria("g", "g holds", check=(Probe.of(READ),))
    report = [_entry("g", {**LABELLED, "id": probe_id("g", READ)})]
    assert unrun_parts({"g": (part,)}, report, own=[whole]) == {} and unrun_pinned([whole], report) == {}


def test_an_auto_root_keeps_the_person_s_check_in_words_against_any_derivable_command():
    """No derivation shows a reading wrong, so «the probe it replaces must be shown wrong» is never met for one."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [
        {"name": "g", "description": "the table covers the prompt", "check": [READ]}, criterion("h", "H holds")]})
    _admit(e, "root", _kid("kid", ["g", "h"], criterion("k", "K holds"), description="a part"))
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "CHALLENGE", "exec-1", reason="g's check cannot be decided by running anything")
    e.wait_idle()
    swap = {"behaviour": BEH, "command": "printf yes", "expect": "yes"}
    llm = _FakeLLM({"decision": "accept", "justification": "a command decides it",
                    "criteria": [{"name": "g", "description": "the table covers the prompt", "check": [swap]}],
                    "derivations": [{"criterion": "g", "probe": swap["command"], "derived_by": "printf yes"}]})
    out = I.answer_the_challenge(e, TaskId("root"), "user", _llm=llm)
    e.wait_idle()
    assert out["status"] == "would_narrow" and "checks in words on the goal stay" in out["why"], out
    assert [p.procedure for p in e.graph.get_task(TaskId("root")).spec.criteria[0].check] == [WORDS]


class _Restated:
    """The reads the packet makes of a whole that restates its done part's check in words."""
    def __init__(self):
        self.crits = [Criteria("g", "g holds", check=(Probe.of(READ),))]
        self.graph = SimpleNamespace(setting=lambda k: None, store_setting=lambda k, v: None)

    def parts_procedure(self, _):
        return {"g": [Criteria("kid/k", "k holds", check=(Probe.of(READ),))]}

    def regression_probes(self, _):
        return {}

    def retired_findings(self, _):
        return []

    def validation_procedure(self, _):
        return self.crits


def test_the_packet_hands_a_restated_check_in_words_once_as_this_run_s_own():
    eng = _Restated()
    text = _criteria_text(eng, SimpleNamespace(id="root", spec=FakeSpec(criteria=eng.crits)), eng.crits, None)
    assert f"PINNED PROCEDURE [{probe_id('g', READ)}]" in text and "ANOTHER run" not in text, text


# === the outside critic over a71c876d ===

def test_one_reading_under_two_behaviours_is_two_checks():
    """«every speed … in the table» and «every unit … in the table», one procedure: a report citing a's passed b."""
    a = Criteria("a", "speeds", check=(Probe("every speed prompt.md states is in the table", procedure=WORDS),))
    b = Criteria("b", "units", check=(Probe("every unit prompt.md states is in the table", procedure=WORDS),))
    report = [_entry("a", {**LABELLED, "id": probe_id("a", a.check[0])}), _entry("b", {**LABELLED, "command": "wc -l t"})]
    assert unrun_pinned([a, b], report) == {"b": [probe_id("b", b.check[0])]}


def test_a_probe_its_report_says_did_not_hold_performs_nothing():
    c, pid = Criteria("c", "d", check=(Probe.of(READ),)), probe_id("c", READ)
    assert unrun_pinned([c], [_entry("c", {**LABELLED, "id": pid, "held": False})]) == {"c": [pid]}


def test_an_auto_root_re_pin_of_a_command_s_input_alone_is_derived_as_before():
    """As on main (1f3e2092): the command and its expectation stand, the input it reads is repaired."""
    def pin(lines):
        return {"behaviour": "b", "command": "wc -l < {inputs}/a.txt", "expect": "2",
                "inputs": [{"path": "a.txt", "content": "x\n" * lines}]}
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [
        {"name": "g", "description": "two lines", "check": [pin(3)]}, criterion("h", "H holds")]})
    _admit(e, "root", _kid("kid", ["g", "h"], criterion("k", "K holds"), description="a part"))
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "CHALLENGE", "exec-1", reason="g's pinned a.txt has three lines, so no delivery prints 2")
    e.wait_idle()
    llm = _FakeLLM({"decision": "accept", "justification": "the pinned input had a stray line",
                    "criteria": [{"name": "g", "description": "two lines", "check": [pin(2)]}],
                    "derivations": [{"criterion": "g", "probe": pin(2)["command"], "derived_by": "printf 2"}]})
    out = I.answer_the_challenge(e, TaskId("root"), "user", _llm=llm)
    e.wait_idle()
    assert out["status"] == "accepted", out
