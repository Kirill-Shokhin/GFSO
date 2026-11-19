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
import gfso.tools_llm as TL
from gfso.adapters.execution import LocalExecution
from gfso.core.protocol.invariants import INTENT
from gfso.core.types import State, TaskId
from gfso.mcp import server as S
from tests.support import a_repository, make_engine
from tests.test_projects import _call, _reg

pytestmark = pytest.mark.skipif(not LocalExecution().shell(), reason="no bash on this host: the pinned checks run here")

ASKED = "Write f.txt saying v1."
WORDS = "да, делай так"
ACCEPTED = "да, принимаю"


class _Validator:
    """The project's validator, stubbed: a read-only session that runs each pinned probe where it is started and reports
    every criterion of the root PASS on what it printed — a check in words cited by the line it saw."""

    def __init__(self, e, outside=()):
        self.e, self.calls, self.outside = e, [], list(outside)

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        ran = lambda cmd: subprocess.run([LocalExecution().shell(), "-c", cmd], cwd=cwd, capture_output=True,
                                         text=True).stdout
        crits = self.e.graph.get_task(TaskId("root")).spec.criteria
        return "```json\n" + json.dumps({"verdict": "PASS", "failed_criteria": [], "per_criterion": [
            {"criterion": c.name, "verdict": "pass", "evidence": f"ran it: {c.name} holds", "behaviours": [p.behaviour for p in c.check],
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
    monkeypatch.setattr(TL, "llm_factory", lambda *a, **k: _Validator(e))
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
    assert [h["said"] for h in e.heard_on("root") if h["act"] == "verdict"] == [ACCEPTED], "the PASS is the person's"
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
    monkeypatch.setattr(TL, "llm_factory", lambda *a, **k: _Validator(e, [{"what": seen, "evidence": "ran it on x.tar.gz"}]))
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
    monkeypatch.setattr(TL, "llm_factory", lambda *a, **k: _Validator(e, [{"what": seen, "evidence": "ran it on x.tar.gz"}]))
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    call("wait", seconds=60)
    assert TL.TOOLS["get_verdict"](e, "root").get("outside") == [{"what": seen, "evidence": "ran it on x.tar.gz"}]


def test_a_second_delivery_is_shown_only_what_its_own_validator_saw(chat, monkeypatch):
    """What the first delivery's validator saw beyond the criteria was told on the second before its validator had run
    (fresh client s23g3): the person weighs the delivery they sign."""
    e, repo, call, _ = chat
    first, second = "x.tar.gz is counted as .gz", "Z.TXT is counted apart from z.txt"
    said = [[{"what": first, "evidence": "ran it"}], [{"what": second, "evidence": "ran it"}]]
    monkeypatch.setattr(TL, "llm_factory", lambda *a, **k: _Validator(e, said.pop(0) if said else []))
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
