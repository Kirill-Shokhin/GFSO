"""A small task in the everyday mode costs about what a bare agent costs, its checks fixed before the work: the person's
agent works as it would and repeats its acts through the system (the author, 2026-11-09/11-12). Under `solo` with
`perform="in_chat"` the canon's acts are six — the plan asked and handed in, the go on the person's words, DELIVER, the
validation, the person's PASS — and a call beyond them is the implementation's grouping, never a seventh act.

Measured (e2e5 G_3, 2026-11-19): 12 gfso calls and 3 tool searches for a small utility. The extras: the setup as three
calls (`use_project`, `register_agent` of the validator, `set_mode`), `next_step` after the go, `validate_result` after
DELIVER, and `get_verdict` read before asking the person. Every guarantee stands: the validator signs the observation,
not the chat (§10.2, §10.3); the root's PASS is the person's words (§10.1); the intent criterion is added at the go."""
from __future__ import annotations

import json
import subprocess

import pytest

import gfso.delegate as D
from gfso import config
import gfso.tools_llm as TL
from gfso.adapters.execution import LocalExecution
from gfso.core.protocol.invariants import INTENT
from gfso.core.types import State, TaskId
from gfso.engine.validation import heard_on
from gfso.mcp import server as S
from tests.support import a_repository, make_engine
from tests.test_projects import _call, _reg
import gfso.validate as VAL

pytestmark = pytest.mark.skipif(not LocalExecution().shell(), reason="no bash on this host: the pinned checks run here")

ASKED = "Write f.txt saying v1."
WORDS = "да, делай так"
ACCEPTED = "да, принимаю"


class _Validator:
    """The project's validator, stubbed: a read-only session that runs each pinned probe where it is started and reports
    every criterion of the root PASS on what it printed — a check in words cited by the line it saw."""

    def __init__(self, e, outside=(), evidence=None):
        self.e, self.calls, self.outside, self.evidence = e, [], list(outside), dict(evidence or {})

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        # …in the environment a model child of the product runs its probes in (a real validator's git has long paths)
        ran = lambda cmd: subprocess.run([LocalExecution().shell(), "-c", cmd], cwd=cwd, capture_output=True,
                                         text=True, env=config.subprocess_env()).stdout
        crits = self.e.graph.get_task(TaskId("root")).spec.criteria
        return "```json\n" + json.dumps({"verdict": "PASS", "failed_criteria": [], "per_criterion": [
            {"criterion": c.name, "verdict": "pass", "evidence": self.evidence.get(c.name, f"ran it: {c.name} holds"), "behaviours": [p.behaviour for p in c.check],
             "probe": [{"command": p.command, "behaviour": p.behaviour, "output": (out := ran(p.command)),
                        "expect": p.expect if p.exact else out.strip().splitlines()[0]} for p in c.check]}
            for c in crits], **({"outside": self.outside} if self.outside else {})}) + "\n```"

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


@pytest.fixture
def chat(tmp_path, monkeypatch):
    """A fresh project, the person's repository, and the door's verbs counted as a client calls them."""
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    repo = a_repository(tmp_path / "repo")
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    monkeypatch.setattr(VAL, "llm_factory", lambda *a, **k: _Validator(e))
    calls = []

    def call(verb, *a, **kw):
        calls.append(verb)
        return (TL.wait_for_the_customer if verb == "wait" else TL.TOOLS[verb])(e, *a, **kw)
    yield e, repo, call, calls
    D.ensure_dispatcher(e).stop()
    e.stop()


def _git(repo, *a) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


def _filled(text: str) -> str:
    for a, b in {'name = ""\n\n#': 'name = "f"\n\n#', 'name = ""\ndescription = ""': 'name = "says_v1"\ndescription = "f.txt says v1"',
                 'behaviour = ""': 'behaviour = "f.txt read"', 'command = ""': "command = 'cat f.txt'",
                 'expect = ""': 'expect = "v1"'}.items():
        assert a in text, a
        text = text.replace(a, b, 1)
    return text


def _set_up(call, repo) -> dict:
    """The setup in one call: the mode, and the validator registered where the work is."""
    return call("set_mode", "solo", perform="in_chat", workdir=str(repo), system_model="claude-haiku-5-5")


def _worked(repo) -> None:
    """The chat's own work, on the system's branch, committed."""
    _git(repo, "switch", "-q", "-c", "gfso/p/work")
    (repo / "f.txt").write_text("v1\n")
    _git(repo, "add", "f.txt")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "f.txt says v1")


def test_a_small_solo_chat_task_reaches_the_persons_pass_in_the_canons_acts(chat):
    e, repo, call, calls = chat
    assert not _set_up(call, repo).get("refused")
    filled = _filled(call("plan", ASKED)["text"])
    path = call("plan", plan=filled)["path"]
    go = call("auto_decompose", plan=path, user_said=WORDS)
    assert go["root_id"] == "root" and "DELIVER" in go["say"], go
    # …and its move named as every move's reply names it: with none, a fresh client asked `next_step` before DELIVER (s23g4)
    assert "'root'" in go.get("next", "") and "DELIVER" in go["next"], go.get("next")
    _worked(repo)
    delivered = call("signal", "root", "DELIVER", "user", result="f.txt written; `cat f.txt` printed v1",
                     self_validation="PASS")
    assert delivered["accepted"] and delivered["state"] == "VALIDATING", delivered
    ended = call("wait", seconds=60)
    assert ended.get("needs_you"), ended
    told = " ".join(s["directive"] for s in ended["steps"] if s.get("mine"))
    for c in ("says_v1", INTENT):
        assert f"{c}: pass" in told, f"the person is not told {c}'s verdict before their PASS is asked: {told}"
    passed = call("signal", "root", "PASS", "user", user_said=ACCEPTED)
    assert passed["accepted"] and e.graph.get_state(TaskId("root")) == State.DONE, passed
    assert len(calls) <= 7, f"{len(calls)} calls for the canon's six acts: {calls}"
    verdict = e.current_exec_verdict(TaskId("root"))
    assert verdict and verdict["validator"] == "p-val", "the observation is the validator's, not the chat's"
    assert [h["said"] for h in heard_on(e.graph, "root") if h["act"] == "verdict"] == [ACCEPTED], "the PASS is the person's"
    assert INTENT in [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria]


def test_the_setup_registers_the_validator_where_the_work_is(chat):
    e, repo, call, _ = chat
    out = _set_up(call, repo)
    assert out["mode"] == "solo" and out["validator"]["registered"] == "p-val", out
    role = TL.TOOLS["list_agents"](e)["agents"]["p-val"]
    assert role["kind"] == "llm-validator" and role["project"] == "p" and role["model"] == "claude-haiku-5-5", role


def test_a_refused_setup_registers_nothing(chat):
    e, repo, call, _ = chat
    out = call("set_mode", "semi", perform="in_chat", workdir=str(repo))
    assert out.get("refused") and "executor" in out["error"], out
    assert "p-val" not in TL.TOOLS["list_agents"](e)["agents"], "a refused mode left its validator on the roster"


def test_on_the_agent_door_the_setup_enters_its_project_and_says_its_page(monkeypatch, tmp_path):
    """`use_project` was a call of its own before the mode; `set_mode` naming its project enters it for the session, and
    says the page's link `use_project` would have said."""
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    reg, repo = _reg(monkeypatch, tmp_path), a_repository(tmp_path / "repo")

    class _Ctx:
        def __init__(self):
            class RC: session = object()
            self.request_context = RC()
    ctx = _Ctx()
    try:
        out = _call(S._bind(reg, TL.TOOLS["set_mode"]), "solo", perform="in_chat", workdir=str(repo), project="small",
                    ctx=ctx)
        assert out["mode"] == "solo" and out["validator"]["registered"] == "small-val", out
        assert "?project=small" in out["say"] and out["say"].startswith("The person does not see"), out
        assert S._resolver(reg)(None, ctx).project_name == "small", "the session does not stand in its project"
    finally:
        for e in list(reg._engines.values()):
            D.ensure_dispatcher(e).stop()
            e.stop()


def test_delivered_the_chat_hears_the_validator_runs_by_itself_and_how_its_end_is_learnt(chat):
    """The DELIVER's answer said "the project's validator observes this delivery by itself — or `validate_result root`
    observes it now", and its `next` said `validate_result('root')`: a client paid the same observation twice; and it sent
    the client to `get_verdict` for what the step its verdict opens says (e2e5 G_3)."""
    e, repo, call, _ = chat
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    out = call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    said = json.dumps(out)
    assert "validate_result" not in said and "get_verdict" not in said, out
    assert "gfso wait project=p" in said and "by itself" in said, out


def test_the_person_is_told_what_the_validator_saw_outside_the_criteria(chat, monkeypatch):
    """No criterion failed on it, so it is theirs to weigh before their PASS: shown the criteria alone, a fresh client
    signed over "x.tar.gz is counted as .gz" without a word to the person (s23g1)."""
    e, repo, call, _ = chat
    seen = "x.tar.gz is counted as .gz, not .tar.gz"
    monkeypatch.setattr(VAL, "llm_factory", lambda *a, **k: _Validator(e, [{"what": seen, "evidence": "ran it on x.tar.gz"}]))
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    ended = call("wait", seconds=60)
    told = " ".join(s["directive"] for s in ended["steps"] if s.get("mine"))
    assert seen in told, f"the sign-off step does not carry what the validator saw: {told}"


def test_the_verdict_read_serves_what_the_validator_saw_outside_the_criteria(chat, monkeypatch):
    """The page reads the verdict through `get_verdict`; the sign-off step told the person what it never served."""
    e, repo, call, _ = chat
    seen = "x.tar.gz is counted as .gz, not .tar.gz"
    monkeypatch.setattr(VAL, "llm_factory", lambda *a, **k: _Validator(e, [{"what": seen, "evidence": "ran it on x.tar.gz"}]))
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    call("wait", seconds=60)
    assert TL.TOOLS["get_verdict"](e, "root").get("outside") == [{"what": seen, "evidence": "ran it on x.tar.gz",
                                                                   "observed": "read, not observed"}]


def test_a_second_delivery_is_shown_only_what_its_own_validator_saw(chat, monkeypatch):
    """What the first delivery's validator saw beyond the criteria was told on the second before its validator had run
    (fresh client s23g3): the person weighs the delivery they sign."""
    e, repo, call, _ = chat
    first, second = "x.tar.gz is counted as .gz", "Z.TXT is counted apart from z.txt"
    said = [[{"what": first, "evidence": "ran it"}], [{"what": second, "evidence": "ran it"}]]
    monkeypatch.setattr(VAL, "llm_factory", lambda *a, **k: _Validator(e, said.pop(0) if said else []))
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    call("wait", seconds=60)
    assert [o["what"] for o in TL.TOOLS["get_verdict"](e, "root")["outside"]] == [first]
    call("signal", "root", "FAIL", "user", failed_criteria=["says_v1"], user_said="нет, переделай")
    call("signal", "root", "DELIVER", "user", result="f.txt written again", self_validation="PASS")
    assert first not in e.persons_verdict("root"), "the first delivery's observation told over the second"
    call("wait", seconds=60)
    assert [o["what"] for o in TL.TOOLS["get_verdict"](e, "root")["outside"]] == [second]
    assert second in e.persons_verdict("root") and first not in e.persons_verdict("root")


def _with_more_criteria(text: str, n: int) -> str:
    """The filled plan with `n` more criteria, each pinned the same way."""
    block = ('\n[[plan.root_criteria]]\nname = "says_v1_{i}"\ndescription = "f.txt says v1, read again {i}"\n\n'
             '[[plan.root_criteria.check]]\nbehaviour = "f.txt read"\ncommand = \'cat f.txt\'\nexpect = "v1"\nexact = true\n')
    head, tail = text.split("# Parts", 1)
    return head + "".join(block.format(i=i) for i in range(n)) + "\n# Parts" + tail


def test_the_sign_off_never_drops_the_reading_against_the_persons_words_and_says_what_it_cut(chat):
    """Added last at the go, the criterion read against the person's own words was the first a cap of twelve cut, and
    nothing said more stood (critic over a8c6035: 15 criteria, three silently dropped)."""
    e, repo, call, _ = chat
    _set_up(call, repo)
    path = call("plan", plan=_with_more_criteria(_filled(call("plan", ASKED)["text"]), 13))["path"]
    call("auto_decompose", plan=path, user_said=WORDS)
    _worked(repo)
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    call("wait", seconds=60)
    told = e.persons_verdict("root")
    assert len(e.graph.get_task(TaskId("root")).spec.criteria) == 15
    assert f"{INTENT}: pass" in told, told
    assert "and 3 more — `get_verdict root` reads them all" in told, told


def test_the_person_hears_the_whole_reading_and_what_it_rests_on(chat, monkeypatch):
    """Cut at 200 characters, the reading against the person's words lost the validator's own caveat on what its PASS
    rested on, and an observation outside the criteria lost what it was seen on (critic over 0bbc8b3, fresh client K_2)."""
    e, repo, call, _ = chat
    caveat = "the pinned check's expect is a paraphrase, so this verdict rests on my own probes, not on that expect"
    reading = "f.txt says v1 as the person asked; " * 12 + caveat
    seen = {"what": "v1 has no trailing newline in the spec", "evidence": "ran od -c f.txt\nit printed v 1 and a newline"}
    monkeypatch.setattr(VAL, "llm_factory", lambda *a, **k: _Validator(e, [seen], {INTENT: reading}))
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    ended = call("wait", seconds=60)
    told = " ".join(s["directive"] for s in ended["steps"] if s.get("mine"))
    assert reading in told, "the reading against the person's words reaches them cut"
    assert seen["what"] in told and "ran od -c f.txt | it printed v 1 and a newline" in told, \
        "an observation reaches them without what it was seen on, or split over lines a client's own cut parts"
    assert "\n" not in told, "a line cut of the step could part a reading from its signal line"


def test_a_reading_past_its_bound_says_where_it_is_whole(chat, monkeypatch):
    """Unbounded, a 50 KB reading made a 193 KB step a client's own `| tail` cut to the signal line (critic, 4708aa9)."""
    e, repo, call, _ = chat
    monkeypatch.setattr(VAL, "llm_factory", lambda *a, **k: _Validator(e, [], {INTENT: "x" * 50000}))
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    call("wait", seconds=60)
    told = e.persons_verdict("root")
    assert len(told) < 6000 and f"(cut: `get_verdict root criterion={INTENT}` reads it whole)" in told, told[-300:]
    assert "x" * 100 not in TL.TOOLS["get_verdict"](e, "root").get("say", ""), "the verdict read repeats its own lines"


def test_a_solo_chats_parts_self_verify_and_the_root_alone_is_observed(chat):
    """Under solo the person's agent holds every node; below the root's seam its parts self-verify (§10.3) and the
    root's validation runs their pinned checks. Read as a scope of the system's sessions, every part was observed apart
    (the author, 2026-11-20: «У соло все задачи кроме корня без шва»)."""
    e, repo, call, _ = chat
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    crit = e.graph.get_task(TaskId("root")).spec.criteria
    check = [{"behaviour": "f.txt read", "command": "cat f.txt", "expect": "v1"}]
    TL.TOOLS["decompose"](e, "root", [
        {"task_id": "root.a", "assignee": "user", "covers": [c.name for c in crit],
         "spec": {"description": "write f.txt", "criteria": [{"name": "a1", "description": "f.txt says v1", "check": check}]}}],
        accepted_risks=[{"item": "the split's claim", "justification": "one part", "p": 0.1, "impact": "re-split",
                         "invalidation_condition": "the root fails over it", "denial": True}])
    e.wait_idle()
    assert not e.observed_here(TaskId("root.a")) and e.observed_here(TaskId("root")), "a part of the chat's is observed apart"
    call("signal", "root.a", "ACCEPT", "user")
    _worked(repo)                         # …the part's work, committed once it is taken
    call("signal", "root.a", "DELIVER", "user", result="f.txt written; `cat f.txt` printed v1", self_validation="PASS")
    e.wait_idle()
    assert e.current_exec_verdict(TaskId("root.a")) is None or e.current_exec_verdict(TaskId("root.a"))["validator"] != "p-val"
    asked = call("signal", "root.a", "PASS", "user")       # …self-verified, reminded: no external check was made
    assert asked.get("confirm_needed") and not asked.get("accepted"), asked
    passed = call("signal", "root.a", "PASS", "user", confirm=True)
    assert passed["accepted"], passed
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    ended = call("wait", seconds=60)
    assert ended.get("needs_you") and e.current_exec_verdict(TaskId("root"))["validator"] == "p-val", ended
    assert call("signal", "root", "PASS", "user", user_said=ACCEPTED)["accepted"]


def test_the_chat_calls_the_check_of_its_own_part_whenever_it_wants(chat):
    """As the kit's critic is called on a piece of work: the chat's own check of a part with no seam (§10.2)."""
    e, repo, call, _ = chat
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    crit = e.graph.get_task(TaskId("root")).spec.criteria
    TL.TOOLS["decompose"](e, "root", [
        {"task_id": "root.a", "assignee": "user", "covers": [c.name for c in crit],
         "spec": {"description": "write f.txt", "criteria": [{"name": "a1", "description": "f.txt says v1",
                                                              "check": [{"behaviour": "f.txt read", "command": "cat f.txt", "expect": "v1"}]}]}}],
        accepted_risks=[{"item": "the split's claim", "justification": "one part", "p": 0.1, "impact": "re-split",
                         "invalidation_condition": "the root fails over it", "denial": True}])
    call("signal", "root.a", "ACCEPT", "user")
    _worked(repo)                         # …the part's work, committed once it is taken
    call("signal", "root.a", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    e.wait_idle()
    out = TL.TOOLS["validate_result"](e, "root.a")
    assert not out.get("internal") and (e.current_exec_verdict(TaskId("root.a")) or {}).get("validator"), out
