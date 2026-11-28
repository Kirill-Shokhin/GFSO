"""A validation is two acts, two calls: the contact reading (B), the kit critic's question on the critic's inputs, made
by the system BEFORE the check (A), in its own copy of the delivery — not built — on its own client; then the check,
shown B's claims on criteria as claims to test, never owed (design §B.1–B.3).

What B claims of a criterion reaches the verdict only through A: A's `refuting` answer is an observed divergence on
that criterion, its fail (Inv-2, §12.8), and nothing of B gates V otherwise, not even through ⊥ — a report that leaves
a claim unanswered is recorded as it is, the claim beside the verdict «not answered». What B finds that no criterion
writes is the issuer's `outside` row (§8.3 FM-1.f), as before. B's record is kept per delivery beside the node, apart
from A's report: a re-validation of the same delivery reuses it, a new delivery is read again. B that failed twice
leaves A asked both questions, the role whole. The switch is the person's, on by default (B is adopted, owed nowhere)."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import gfso
import gfso.tools_llm as TL
import gfso.validate as VAL
import tests.test_one_session_carries_a_scope as S
from gfso import config
from gfso.adapters.execution import LocalExecution
from gfso.adapters.snapshots import BuildFailed, snapshot
from gfso.core.protocol.invariants import INTENT
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import Stage, TaskId
from gfso.engine.validation import contact_on
from gfso.packets import CONTACT_ROW, scope_validator_packet
from tests.support import committed
from tests.test_a_small_task_takes_the_canons_acts import (ASKED, WORDS, _Validator, _filled, _git, _set_up, _worked,
                                                          chat, pytestmark)
from tests.test_a_validation_is_cut_by_what_it_owes import _measured
from tests.test_the_contact_reading_is_handed_the_critics_inputs import OUTSIDE_LINE, QUESTION_1

__all__ = ["chat", "pytestmark"]

CONTACT_PROMPT = (Path(gfso.__file__).parent / "mcp" / "prompts" / "contact.md").read_text(encoding="utf-8")
CMD = "cat f.txt"
RID = probe_id("says_v1", {"command": CMD})


def _fenced(d) -> str:
    return "```json\n" + json.dumps(d) + "\n```"


def _find(bears_on="criterion: says_v1", what="f.txt is not what the goal asks", probe=True, **kw) -> dict:
    return {"what": what, "bears_on": bears_on, "evidence": f"ran `{CMD}`",
            **({"probe": {"command": CMD, "expect": "v1"}} if probe else {}), **kw}


class _Script:
    """What the validation's clients do, shared by every client the factory makes: B answers `finds(cwd)` with
    `b_tools` (or raises), A the stubbed validator's report passed through `a(report, packet)` with `a_tools`."""

    def __init__(self, e):
        self.e, self.order, self.b_users, self.a_users, self.a_systems, self.b_cwds = e, [], [], [], [], []
        self.finds, self.a = (lambda cwd: [_find()]), (lambda d, user: d)
        self.b_tools, self.a_tools, self.b_raise = {"Bash": 3, "Read": 2}, {"Bash": 1}, False
        # …how each B call ends, in turn, past which it reports: `cut` at its timeout, `nothing` (no report)
        self.b_ends, self.b_asked, self.forgotten = [], [], []
        self.cut_sessions, self.resume_refused = set(), False   # …a turn on a cut session resumes it, unless refused


class _Role(_Validator):
    """One client of the validation — B where it is handed the contact prompt, else A."""

    def __init__(self, s: _Script):
        super().__init__(s.e)
        self.s, self.last_tool_calls = s, {}

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None, session=None, keep_cut=False):
        s = self.s
        if system == CONTACT_PROMPT:
            s.order.append("B")
            s.b_users.append(user)
            s.b_cwds.append(cwd)
            s.b_asked.append({"session": session, "keep_cut": keep_cut, "timeout": timeout})
            self.calls.append({"duration_ms": 1, "output_tokens": 1,
                               "resumed": session in s.cut_sessions and not s.resume_refused})
            if s.b_raise:
                raise RuntimeError("the contact reader fell over")
            self.last_tool_calls = dict(s.b_tools)
            if (ends := s.b_ends.pop(0) if s.b_ends else "report") == "cut":
                self.calls[-1].update(ended="cut", stop_reason="timeout")
                s.cut_sessions.add(session)
            return "" if ends in ("cut", "nothing") else _fenced({"finds": s.finds(cwd)})
        s.order.append("A")
        s.a_users.append(user)
        s.a_cwd = cwd
        s.a_systems.append(system)
        self.last_tool_calls = dict(s.a_tools)
        text = super().run_agent(system, user, allowed_tools, cwd, timeout)
        return _fenced(s.a(json.loads(text.split("```json\n", 1)[1].rsplit("\n```", 1)[0]), user))

    def forget(self, session):
        self.s.forgotten.append(session)


@pytest.fixture
def contact(chat, monkeypatch):
    """The chat's project with the contact reading on and every client of a validation scripted."""
    e, repo, call, _ = chat
    monkeypatch.setenv("GFSO_CONTACT", "1")
    s = _Script(e)
    monkeypatch.setattr(VAL, "llm_factory", lambda *a, **k: _Role(s))
    return e, repo, call, s


def _delivered(e, repo, call, **kw) -> dict:
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    return _again(e, call, **kw)


def _again(e, call, **kw) -> dict:
    """The root delivered (again) and its validation waited out: the verdict on record."""
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS", **kw)
    call("wait", seconds=60)
    return e.current_exec_verdict(TaskId("root")) or {}


def _failed_and_delivered_again(e, call) -> dict:
    call("signal", "root", "FAIL", "user", failed_criteria=["says_v1"], user_said="нет, переделай")
    return _again(e, call)


def _contact_rows(rec) -> list:
    return [o for o in rec.get("outside") or () if o.get("by") == "contact"]


def _answering(answer, **kw):
    def a(d, user):
        if answer is not None:
            d["contact"] = [{"id": RID, "answer": answer, "why": "what it printed decides it", **kw}]
        return d
    return a


def _entry(d, name) -> dict:
    return next(x for x in d["per_criterion"] if x["criterion"] == name)


# ── (a) (b) one reading per delivery, before the check ───────────────────────────────────────────────────────────────

def test_a_delivery_is_read_at_contact_before_its_check_with_the_critics_prompt(contact):
    e, repo, call, s = contact
    _delivered(e, repo, call)
    assert s.order == ["B", "A"], s.order
    assert "f.txt written" not in s.b_users[0], "the executor's report reached the contact reading"


def test_the_same_delivery_is_read_once_and_a_new_delivery_of_the_same_tree_again(contact):
    e, repo, call, s = contact
    _delivered(e, repo, call)
    call("validate_result", "root")
    call("wait", seconds=60)
    assert s.order == ["B", "A", "A"], s.order
    _failed_and_delivered_again(e, call)
    assert s.order == ["B", "A", "A", "B", "A"], s.order


# ── (c) (r) a claim A observes refuting is that criterion's fail ─────────────────────────────────────────────────────

def test_a_shown_claim_the_check_fails_its_criterion_on_is_a_recorded_fail(contact):
    e, repo, call, s = contact

    def a(d, user):
        _entry(d, "says_v1").update(verdict="fail", evidence=f"CONTACT [{RID}]: `{CMD}` printed v1, the goal says v2",
                                    divergences=["f.txt says v1"])
        _entry(d, "says_v1")["probe"][0]["held"] = False
        return d
    s.a = a
    rec = _delivered(e, repo, call)
    assert f"CONTACT [{RID}]" in s.a_users[0], s.a_users[0]
    assert rec.get("verdict") == "FAIL" and rec.get("failed_criteria") == ["says_v1"], rec


def test_a_refuting_answer_beside_a_pass_entry_is_its_criterions_fail(contact):
    e, repo, call, s = contact
    s.a = _answering("refuting", command=CMD, printed="v1")
    rec = _delivered(e, repo, call)
    assert rec.get("verdict") == "FAIL" and rec.get("failed_criteria") == ["says_v1"], rec
    assert f"CONTACT [{RID}]" in _entry(rec, "says_v1")["evidence"], _entry(rec, "says_v1")
    assert e.refused_report_for_this_delivery(TaskId("root")) is None, "the report was refused, not folded"


# ── (d) (e) a claim unanswered or answered short of refuting, an outside find: no gate ───────────────────────────────

@pytest.mark.parametrize("answer", [None, "held", "not_refuting", "not_run"])
def test_a_claim_left_unanswered_or_not_refuted_leaves_the_pass_with_the_claim_beside_it(contact, answer):
    e, repo, call, s = contact
    s.a = _answering(answer)
    rec = _delivered(e, repo, call)
    assert rec.get("verdict") == "PASS", rec
    (row,) = _contact_rows(rec)
    assert row["bears_on"] == "says_v1" and (answer or "not answered") in row["observed"], row


def test_an_outside_find_even_observed_fails_nothing_and_is_not_shown_to_the_check(contact):
    e, repo, call, s = contact
    s.finds = lambda cwd: [_find(bears_on="outside", what="f.txt has no trailing newline")]
    rec = _delivered(e, repo, call)
    assert rec.get("verdict") == "PASS" and not rec.get("failed_criteria"), rec
    assert "CONTACT [" not in s.a_users[0]
    (row,) = _contact_rows(rec)
    assert not row.get("bears_on") and row["what"] == "f.txt has no trailing newline", row


def test_a_find_naming_no_criterion_reads_as_outside(contact):
    e, repo, call, s = contact
    s.finds = lambda cwd: [_find(bears_on="criterion: speed_is_fine")]
    rec = _delivered(e, repo, call)
    assert "CONTACT [" not in s.a_users[0] and rec.get("verdict") == "PASS"
    (row,) = _contact_rows(rec)
    assert not row.get("bears_on"), row


def test_the_person_reads_which_criterion_a_claim_contradicts(contact):
    e, repo, call, s = contact
    _delivered(e, repo, call)
    assert any(o["what"].startswith("contradicts `says_v1`") for o in e.outside_of_this_delivery("root")), \
        e.outside_of_this_delivery("root")


# ── (f) (g) a reading not done leaves the check whole ────────────────────────────────────────────────────────────────

def test_a_contact_reading_that_fails_twice_leaves_the_check_asked_both_questions(contact):
    e, repo, call, s = contact
    s.b_raise = True
    _delivered(e, repo, call)
    assert s.order == ["B", "B", "A"], s.order
    assert QUESTION_1 in s.a_systems[0] and OUTSIDE_LINE in s.a_systems[0]
    rec = e.contact_reading("root")
    assert rec and not rec["done"] and "fell over" in rec["reason"], rec


def test_with_a_reading_done_the_check_is_not_asked_question_1(contact):
    e, repo, call, s = contact
    _delivered(e, repo, call)
    assert QUESTION_1 not in s.a_systems[0] and OUTSIDE_LINE not in s.a_systems[0]


@pytest.mark.parametrize("tools, done", [({}, False), ({"Read": 2, "Grep": 1}, True)])
def test_a_reading_is_done_by_its_own_calls_tools_never_the_checks(contact, tools, done):
    e, repo, call, s = contact
    s.b_tools, s.a_tools = tools, {"Bash": 4}
    _delivered(e, repo, call)
    rec = e.contact_reading("root")
    assert rec["done"] is done, rec
    assert s.order == (["B", "A"] if done else ["B", "B", "A"]), s.order
    if done:
        assert rec["tools"] == tools, "the check's tools were credited to the contact reading"


# ── (f′) shown again on every delivery; a ruling's parity; no standing finding ───────────────────────────────────────

def test_a_claim_answered_not_refuting_is_shown_again_on_the_next_delivery_and_never_a_finding(contact):
    e, repo, call, s = contact
    s.a = _answering("not_refuting")
    _delivered(e, repo, call)
    assert e.regression_probes(TaskId("root")) == {}
    _failed_and_delivered_again(e, call)
    assert f"CONTACT [{RID}]" in s.a_users[-1], "a dismissal once made hid the claim on the next delivery"
    assert e.regression_probes(TaskId("root")) == {}, "a claim that refuted nothing became a standing finding"


def test_a_claim_a_ruling_in_force_covers_is_not_shown_and_is_marked_ruled(contact, monkeypatch):
    e, repo, call, s = contact
    monkeypatch.setattr(e, "retired_findings", lambda tid: [{"criterion": "says_v1", "id": RID, "command": CMD}])
    rec = _delivered(e, repo, call)
    assert f"CONTACT [{RID}]" not in s.a_users[0]
    (row,) = _contact_rows(rec)
    assert row["observed"].startswith("ruled"), row


def test_two_claims_with_no_command_on_one_criterion_are_both_shown(contact):
    e, repo, call, s = contact
    s.finds = lambda cwd: [_find(probe=False, what="one reading"), _find(probe=False, what="another reading")]
    _delivered(e, repo, call)
    assert s.a_users[0].count("CONTACT [") == 2 and "read, no command" in s.a_users[0], s.a_users[0]


# ── (f″) a claim on the person's words ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("quoted", [True, False])
def test_a_claim_on_the_persons_words_is_shown_and_decided_as_any_fail_of_them(contact, quoted):
    e, repo, call, s = contact
    s.finds = lambda cwd: [_find(bears_on=f"criterion: {INTENT}", what="the person asked for something else")]

    def a(d, user):
        if quoted:
            _entry(d, INTENT).update(verdict="fail", quote=ASKED, evidence="the result misses what they asked",
                                     divergences=["the result misses what they asked"])
        else:
            d["outside"] = [{"what": "they may also want v2", "evidence": "read"}]
        return d
    s.a = a
    rec = _delivered(e, repo, call)
    assert f"CONTACT [{probe_id(INTENT, {'command': CMD})}]" in s.a_users[0]
    assert (rec.get("verdict"), rec.get("failed_criteria")) == (("FAIL", [INTENT]) if quoted else ("PASS", [])), rec


# ── (f‴) a refused report: the same reading, the claim shown again ───────────────────────────────────────────────────

def test_a_refused_report_is_retried_on_the_same_reading_with_the_claim_shown_again(contact):
    e, repo, call, s = contact

    def a(d, user):
        if s.order.count("A") == 1:                     # …the first report names a behaviour it observed nothing of
            _entry(d, "says_v1")["behaviours"].append("a behaviour nothing observed")
        return d
    s.a = a
    _delivered(e, repo, call)
    if s.order.count("A") < 2:
        call("validate_result", "root")
        call("wait", seconds=60)
    assert s.order == ["B", "A", "A"], s.order
    assert all(f"CONTACT [{RID}]" in u for u in s.a_users), "the retry was not shown the claim"


# ── (bt) a batched check: each claim in the one batch of its criterion ───────────────────────────────────────────────

@pytest.mark.parametrize("size", [16, 7])
def test_each_claim_goes_to_the_one_batch_of_its_criterion_and_counts_in_its_size(size):
    eng, task, parts = _measured()
    shown = {("root", "F"): [CONTACT_ROW + "r1"], ("root", "B"): [CONTACT_ROW + "r2", CONTACT_ROW + "r3"]}
    runs = VAL._scope_batches(eng, parts, size, shown)
    for (_, crit), tokens in shown.items():
        for t in tokens:
            (holder,) = [carry for run in runs for *_, carry in run if t in carry]
            assert holder[t] == crit
    assert all(sum(len(carry) for *_, carry in run) <= size for run in runs)


# ── (s) a scope ──────────────────────────────────────────────────────────────────────────────────────────────────────

def test_in_a_scope_a_claim_goes_under_its_member_and_one_naming_none_to_the_top(tmp_path):
    e, _ = S._project(tmp_path)
    parts = [(e.graph.get_task(TaskId(t)), "d", list(e.graph.get_task(TaskId(t)).spec.criteria))
             for t in ("root.a", "root.b", "root")]
    rows = VAL._contact_rows([_find(bears_on="criterion: a_ok", node="root.a"), _find(bears_on="criterion: a_ok")],
                             parts, "root")
    assert [(r["node"], r["bears_on"]) for r in rows] == [("root.a", "a_ok"), ("root", None)], rows
    text = scope_validator_packet(e, parts, None, None, frozenset(S._NODES), contact={"root.a": rows[:1]})
    under = text.split("## Node `root.a`")[1].split("## Node `")[0]
    assert f"CONTACT [{rows[0]['id']}]" in under, text
    e.stop()


# ── (p) B's place ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_an_unbuilt_copy_runs_no_build_and_raises_no_build_failure(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "f").write_text("x")
    tree, commit, _ = committed(a)
    x, broken = LocalExecution(), (tree, commit, "touch built; exit 3")
    with pytest.raises(BuildFailed):
        with snapshot(a, tmp_path / "r1" / "delivery", x, delivered=broken):
            pass
    built: list = []
    with snapshot(a, tmp_path / "r2" / "delivery", x, delivered=broken, built=built, build=False) as at:
        assert not (Path(at) / "built").exists() and (Path(at) / "f").read_text() == "x"
    assert built and "not built" in built[0], built


def test_the_readers_copy_is_not_built_and_its_scratch_probe_is_laid_for_the_check_under_a_stable_id(contact):
    e, repo, call, s = contact
    seen: dict = {}

    def finds(cwd):
        seen.setdefault("b_built", []).append((Path(cwd) / "built.txt").exists())
        probe = Path(cwd).parent / "probe.sh"
        probe.write_text(f"{CMD}\n")
        return [_find(probe=False) | {"probe": {"command": f"sh {probe.as_posix()}", "expect": "v1"}}]

    def a(d, user):
        line = next(x for x in user.splitlines() if x.startswith("- CONTACT ["))
        cmd = re.search(r"run `(.*)` \(it showed", line).group(1)
        seen.setdefault("a_built", []).append("built" if "/regression/" in cmd else "not laid")
        seen.setdefault("ran", []).append(subprocess.run([LocalExecution().shell(), "-c", cmd], cwd=s.a_cwd,
                                                         capture_output=True, text=True,
                                                         env=config.subprocess_env()).stdout)
        return d
    s.finds, s.a = finds, a
    _delivered(e, repo, call, build="touch built.txt")
    first = [r["id"] for r in e.contact_reading("root")["rows"]]
    _failed_and_delivered_again(e, call)
    second = [r["id"] for r in e.contact_reading("root")["rows"]]
    assert seen["b_built"] == [False, False], "the contact reader's copy was built by the system"
    assert seen["a_built"] == ["built", "built"] and all("v1" in x for x in seen["ran"]), seen
    assert first == second and len(first) == 1, (first, second)


# ── Stage.CONTACT, the person's switch ───────────────────────────────────────────────────────────────────────────────

def test_the_readings_spend_is_booked_apart_from_the_checks(contact):
    e, repo, call, s = contact
    _delivered(e, repo, call)
    stages = [u["stage"] for u in e._storage.get_usage() if u.get("node_id") == "root"]
    assert Stage.CONTACT in stages and any(x in stages for x in (Stage.VALIDATOR, Stage.VALIDATE_RESULT)), stages


def test_the_switch_is_on_by_default_and_the_persons_to_turn(contact, monkeypatch):
    e, repo, call, s = contact
    monkeypatch.delenv("GFSO_CONTACT")
    assert contact_on(e.graph), "the contact reading is not on by default"
    _set_up(call, repo)
    assert call("set_mode", contact=False).get("refused"), "an agent turned the person's switch without their words"
    assert contact_on(e.graph)
    assert not call("set_mode", contact=False, user_said="без внешнего чтения").get("refused")
    assert not contact_on(e.graph)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    _again(e, call)
    assert s.order == ["A"], s.order


# ── an answer as the check spells it ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cid, word", [(f"CONTACT [{RID}]", "refuting"), (f"[{RID}]", "refuting"), (f"`{RID}`", "refuting"),
                                       (RID, "Refuting"), (RID, "**refuting**"), (RID, "REFUTING."),
                                       (RID, "is refuting"), (RID, "refuting (reproduced)")])
def test_a_refuting_answer_is_read_however_the_check_spells_its_id_or_its_word(contact, cid, word):
    e, repo, call, s = contact

    def a(d, user):
        d["contact"] = [{"id": cid, "answer": word, "why": "it prints v1", "command": CMD, "printed": "v1"}]
        return d
    s.a = a
    rec = _delivered(e, repo, call)
    assert rec.get("verdict") == "FAIL" and rec.get("failed_criteria") == ["says_v1"], (cid, word, rec)


def test_an_answer_to_no_claim_shown_decides_nothing_and_is_said_beside_the_verdict(contact):
    e, repo, call, s = contact

    def a(d, user):
        d["contact"] = [{"id": "says_v1#deadbeef", "answer": "refuting", "why": "a claim nobody made"}]
        return d
    s.a = a
    rec = _delivered(e, repo, call)
    assert rec.get("verdict") == "PASS", rec
    assert any("an answer to no claim shown" in o["what"] and "says_v1#deadbeef" in o["what"]
               for o in _contact_rows(rec)), _contact_rows(rec)


def test_in_a_scope_a_find_naming_no_member_is_outside_on_the_top_whatever_it_names(tmp_path):
    e, _ = S._project(tmp_path)
    parts = [(e.graph.get_task(TaskId(t)), "d", list(e.graph.get_task(TaskId(t)).spec.criteria))
             for t in ("root.a", "root.b", "root")]
    (row,) = VAL._contact_rows([_find(bears_on="criterion: g")], parts, "root")    # …g is the top's own criterion
    assert (row["node"], row["bears_on"]) == ("root", None), row
    e.stop()


def test_the_system_runs_no_contact_claim_on_a_criterion(monkeypatch):
    ran, seen = [], {}
    monkeypatch.setattr(VAL, "_on_the_delivery", lambda engine, parts, workdir, probes, ex=None, **k:
                        ran.extend(k for k, _, _ in probes) or {})
    engine = SimpleNamespace(see_outside=lambda tid, rows: seen.update(rows))
    claim = {"what": "c", "bears_on": "says_v1", "by": "contact", "row": "r1", "observed": "the check answered: held",
             "probe": {"command": CMD, "expect": "v1"}}
    find = {"what": "o", "by": "contact", "row": "r2", "observed": "being observed", "probe": {"command": CMD, "expect": "v1"}}
    said = {"root": {"outside": [claim, find]}}
    VAL._observe_outside(engine, [], "w", said)
    assert ran == [("root", 0)] and "r1" not in seen and claim["observed"] == "the check answered: held", (ran, seen)


# ── G1: a reading cut at its time reports what it has ────────────────────────────────────────────────────────────────

def test_a_reading_cut_at_its_time_is_asked_once_for_its_report_and_that_report_is_recorded(contact):
    """Measured on the gate (SET.md attempts 8–9): 3 of 4 B tries cut by their half of T_validate, each having run the
    whole suite, returned nothing — every probe B had made was lost, and A was sent the whole role."""
    e, repo, call, s = contact
    s.b_ends = ["cut"]
    _delivered(e, repo, call)
    assert s.order == ["B", "B", "A"], s.order
    first, report = s.b_asked
    assert first["session"] and first["keep_cut"] and report["session"] == first["session"], s.b_asked
    assert report["timeout"] <= 60 and not report["keep_cut"], report
    assert "Your time for this reading is over" in s.b_users[1], s.b_users[1]
    rec = e.contact_reading("root")
    assert rec["done"] and rec["rows"] and rec["tools"] == {"Bash": 6, "Read": 4}, rec
    assert f"CONTACT [{RID}]" in s.a_users[0] and first["session"] in s.forgotten


def test_a_report_turn_that_did_not_continue_the_reading_is_no_report(contact):
    """Outside critic over G1: a report turn that opened FRESH (no transcript kept, or `--resume` refused and the cold
    retry sent «Your time is over» to a model that saw none of the work) answered «nothing found», recorded as a done
    reading with no finds — the check spared question 1 over a reading that never reported."""
    e, repo, call, s = contact
    s.b_ends, s.resume_refused = ["cut", "report"], True
    _delivered(e, repo, call)
    assert s.order == ["B", "B", "B", "A"], f"a report turn that opened fresh was taken as the reading: {s.order}"
    assert s.b_asked[2]["session"] != s.b_asked[0]["session"], "the fresh try continued the cut conversation"


def test_a_reading_whose_report_turn_fails_is_read_once_more_afresh(contact):
    e, repo, call, s = contact
    s.b_ends = ["cut", "nothing"]
    _delivered(e, repo, call)
    assert s.order == ["B", "B", "B", "A"], s.order
    assert s.b_asked[2]["session"] != s.b_asked[0]["session"], "the fresh try continued the cut conversation"
    assert e.contact_reading("root")["done"]


def test_a_reading_that_ended_on_its_own_is_asked_for_no_report(contact):
    e, repo, call, s = contact
    s.b_ends = ["nothing", "report"]
    _delivered(e, repo, call)
    assert s.order == ["B", "B", "A"] and "Your time for this reading is over" not in s.b_users[1], s.b_users
