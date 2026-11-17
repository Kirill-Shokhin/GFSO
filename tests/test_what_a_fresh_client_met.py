"""What real user-agents met on a clean install, kept: each of these stopped one, or told it something untrue."""
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from gfso import cli as C, config, serverctl, tools_llm as TL
from gfso.adapters import children as CH, execution as E
from gfso.adapters.llm.stats import is_limit, is_unauthorized
from gfso.adapters.records import hold_the_home
from gfso.decompose.loop import FOLD_SCHEMA, _audit_fold
import gfso.mcp.server as MS
from gfso.mcp.server import _with_ui_link


class _Fold:
    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def complete_structured(self, system, user, schema):
        assert schema is FOLD_SCHEMA
        self.asked.append(user)
        return self.answers.pop(0)


PART = {"id": "a", "name": "a", "description": "d", "criteria": [{"name": "c", "description": "d", "check": []}]}


def test_a_fold_whose_parts_name_nothing_is_asked_again_once():
    """No repair round can address a part with no id: the plan was refused minutes later as "left None, None"."""
    llm = _Fold({"add_subtasks": [{"name": "n", "check": []}]}, {"add_subtasks": [PART]})
    assert _audit_fold(llm, "goal", "", "findings") == {"add_subtasks": [PART]}
    assert len(llm.asked) == 2 and "no `id`" in llm.asked[1]


def test_a_fold_with_named_parts_costs_one_call():
    llm = _Fold({"add_subtasks": [PART]})
    assert _audit_fold(llm, "goal", "", "findings") == {"add_subtasks": [PART]}
    assert len(llm.asked) == 1


def test_a_ruling_the_person_may_make_does_not_end_a_wait():
    """Told "nothing moves until you close it", a client stopped the run to ask what the system closed a minute later."""
    step = {"mine": True, "optional": True}
    assert not TL.needs_its_customer({"steps": [step]})
    assert TL.needs_its_customer({"steps": [{**step, "optional": False}]})
    assert TL.needs_its_customer({"steps": [step], "complete": True})


def test_a_wait_reports_what_it_waited(monkeypatch):
    """Every wait read 600 s, whatever it was."""
    clock = iter([100.0, 100.0, 101.0, 101.0, 107.5, 107.5])
    answers = iter([{"steps": []}, {"steps": []}, {"complete": True}])
    monkeypatch.setattr(TL, "next_steps", lambda *a: next(answers))
    monkeypatch.setattr(TL.time, "sleep", lambda s: None)
    out = TL.wait_for_the_customer(SimpleNamespace(now=lambda: next(clock), project_name="p"), None, "user", 600)
    assert out["waited_seconds"] == 7.5 and out["needs_you"] == "the root is settled"


def _engine(landed=None, mode="auto", not_rerun=()):
    return SimpleNamespace(graph=SimpleNamespace(setting=lambda key: landed and json.dumps(landed), get_parent=lambda tid: None),
                           all_tasks=lambda: [SimpleNamespace(id="root")], checks_no_longer_run=lambda tid: list(not_rerun),
                           findings_not_reproduced=lambda tid: [], project_name="no-record-here",
                           mode=lambda: {"mode": mode} if mode else None)


BRANCH = {"branch": "gfso/p/accepted", "sha": "s", "path": "/r"}


def test_the_end_says_what_the_person_is_told():
    """A run ended in one sentence: no verdict, no branch, no link, no way to see the result."""
    said = _with_ui_link("next_steps", {"complete": True}, "p", _engine(BRANCH))["say"]
    assert "get_verdict" in said and "gfso/p/accepted" in said and "git worktree add" in said


def test_the_end_shows_the_program_working_after_it_is_read():
    """The person wants to see it work, and it must be read before it runs on this machine: in that order, and first."""
    for where in (BRANCH, {"path": "/r/.gfso-accepted-p"}):
        said = _with_ui_link("next_steps", {"complete": True}, "p", _engine(where))["say"]
        assert said.index("read what the result runs") < said.index("run it on a small example") < said.index("show the person its output first") < said.index("get_verdict")
        assert "do not run it" in said


@pytest.mark.parametrize("kind", ["code", "chat"])
def test_the_go_says_its_two_lines_before_the_wait_and_a_wake_only_to_a_client_that_has_one(kind):
    """A client went from the go straight to `next_steps`, the link unsaid (e2e1, 2026-11-09). A chat client has no
    background command: nothing it is told waits, and nothing tells it how to wait (the author, 2026-11-15)."""
    token = config.CLIENT.set(kind)
    try:
        said = _with_ui_link("auto_decompose", {"root_id": "root"}, "p", _engine())["say"]
    finally:
        config.CLIENT.reset(token)
    assert ("gfso wait project=no-record-here" in said) is (kind == "code"), said
    assert said.index("BEFORE any other call") < (said.index("gfso wait") if kind == "code" else len(said))
    assert ("Hand the turn back to the person now" in said) is (kind == "chat"), said
    assert not any(w in said for w in ("next_steps", "never waiting", "stay free")), said


@pytest.mark.parametrize("kind", ["code", "chat", None])
def test_what_works_without_the_caller_says_how_it_learns_a_move_is_its(kind):
    """solo and semi lost their way of waiting with the held call: the frontier at work, a dispatched node, the go and a
    plan being written say it by the client's kind — a wake for code (and a person at the CLI), the turn handed back
    for chat, whose polling in its own turn is the one free move no mechanism holds."""
    token = config.CLIENT.set(kind)
    try:
        said = config.how_it_is_waited("p", "one is yours")
    finally:
        config.CLIENT.reset(token)
    assert said == ("Hand the turn back to the person now: read the run again when they ask." if kind == "chat" else "`gfso wait project=p` in the background exits when one is yours.")


def test_the_end_says_what_the_pass_did_not_re_run_only_where_it_did_not():
    """A person in chat got a plain PASS over a check no longer run: the verdict said it, the end did not (critic)."""
    plain = _with_ui_link("next_steps", {"complete": True}, "p", _engine(BRANCH))["say"]
    assert "checks_no_longer_run" not in plain
    assert "checks_no_longer_run" in _with_ui_link("next_steps", {"complete": True}, "p", _engine(BRANCH, not_rerun=[{}]))["say"]


def test_the_end_says_only_where_the_result_landed():
    """`complete` of a part mid-run, or a run with no container, told the person a branch that was not there."""
    assert "say" not in _with_ui_link("next_steps", {"complete": True}, "p", _engine())
    said = _with_ui_link("next_steps", {"complete": True}, "p", _engine({"path": "/r/.gfso-accepted-p"}))["say"]
    assert ".gfso-accepted-p" in said and "branch" not in said


def test_a_go_says_it_runs_only_where_it_does():
    """A go that built nothing, its error beside `root_id`, told a client to wait; `solo` is no unattended run."""
    assert "unattended" in _with_ui_link("auto_decompose", {"root_id": "root"}, "p", _engine())["say"]
    assert "say" not in _with_ui_link("auto_decompose", {"root_id": "root", "error": "no answer"}, "p", _engine())
    assert "say" not in _with_ui_link("auto_decompose", {"root_id": "root"}, "p", _engine(mode="solo"))


def test_a_new_project_says_the_scheme_and_the_branch():
    said = _with_ui_link("use_project", {"active": "p"}, "p")["say"]
    assert "claude-haiku-5-5" in said and "gfso/p/accepted" in said


def test_what_is_said_stands_first_in_the_answer():
    """Last in a long answer, it went unsaid: nothing on the plan before a go in 6 runs of 6."""
    assert next(iter(_with_ui_link("auto_decompose", {"root_id": "root", "log": "long"}, "p", _engine()))) == "say"
    assert next(iter(_with_ui_link("next_steps", {"steps": [], "complete": True}, "p", _engine(BRANCH)))) == "say"


def test_a_token_its_organization_refused_is_a_refusal_the_pointer_moves_past():
    """Every refusal the four credentials answer on one day, read: the limit, the credit, the organization's."""
    assert is_limit("API Error: 400 You have reached your specified API usage limits.")
    assert is_limit("Credit balance is too low")
    assert is_unauthorized("Your organization has disabled Claude subscription access")


def test_a_docker_slow_to_answer_still_ends_the_host_side_of_a_call(monkeypatch):
    """`docker exec`'s client stood after its call was gone, and `plan` waited on it for 24 min (F3): ended either way."""
    ended = []
    monkeypatch.setattr(E.LocalExecution, "end", lambda self, proc: ended.append(proc))
    me = E.ContainerExecution.__new__(E.ContainerExecution)

    def slow(call):
        raise subprocess.TimeoutExpired("docker", 60)
    monkeypatch.setattr(me, "_end_inside", slow, raising=False)
    call = E._Call.__new__(E._Call)
    call.client, call.call, call.execution = object(), "c", me
    with pytest.raises(subprocess.TimeoutExpired):
        me.end(call)
    assert ended == [call.client]


def test_a_home_is_held_by_one_process_until_it_ends(tmp_path):
    """On another port a second `serve` ended this home's containers all the same. Told apart by a lock the OS drops."""
    code = "import sys; from gfso.adapters.records import hold_the_home as h; print(h(sys.argv[1]))"
    assert hold_the_home(tmp_path) is True
    held = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, check=True)
    assert held.stdout.strip() == "False"
    free = tmp_path / "other"
    free.mkdir()
    gone = subprocess.run([sys.executable, "-c", code, str(free)], capture_output=True, text=True, check=True)
    assert gone.stdout.strip() == "True" and hold_the_home(free) is True, "a dead holder's lock stood"


def test_a_second_serve_on_another_port_ends_nothing(monkeypatch):
    monkeypatch.setattr(C.serverctl, "port_open", lambda host, port: False)
    monkeypatch.setattr(C, "hold_the_home", lambda home: False)
    monkeypatch.setattr(C, "end_leftovers", lambda: pytest.fail("the standing server's work was ended"))
    with pytest.raises(SystemExit) as out:
        C._serve(SimpleNamespace(log_level="info", host="127.0.0.1", port=18000))
    assert "is running" in str(out.value) and "--port" not in str(out.value)


def test_a_second_serve_ends_nothing_of_the_one_that_stands(monkeypatch):
    """`end_leftovers` ran before the bind: a `gfso serve` typed beside a live server ended every project's containers."""
    monkeypatch.setattr(C.serverctl, "port_open", lambda host, port: True)
    monkeypatch.setattr(C, "end_leftovers", lambda: pytest.fail("the standing server's work was ended"))
    with pytest.raises(SystemExit) as out:
        C._serve(SimpleNamespace(log_level="info", host="127.0.0.1", port=8000))
    assert "already served" in str(out.value)


def test_the_go_opens_the_project_s_page_where_the_server_is_the_person_s(monkeypatch):
    """Told twice in one run to write the project's link in text, at `use_project` and at the go, the fresh client
    wrote neither and said it only at the end (s16a, 2026-11-16) — and the person was to «просто тыкнул … и сразу начал
    смотреть». A loopback server is on the person's machine: the go opens the page itself, once, the link kept in text."""
    opened = []
    monkeypatch.setattr(serverctl, "open_outside", opened.append)
    monkeypatch.setattr(serverctl, "_OPENED", set())
    monkeypatch.setenv("GFSO_OPEN_PAGE", "1")
    monkeypatch.delenv("GFSO_NO_WINDOWS", raising=False)
    out = _with_ui_link("auto_decompose", {"root_id": "root"}, "p", _engine())
    assert opened == [out["ui"]] and out["page_opened"] is True and "open in their browser" in out["say"]
    _with_ui_link("auto_decompose", {"root_id": "root", "error": "no answer"}, "p", _engine())
    _with_ui_link("auto_decompose", {"root_id": "root"}, "p", _engine(mode="solo"))
    assert len(opened) == 1, "only a go that started unattended work opens it"
    monkeypatch.setenv("GFSO_BIND", "0.0.0.0")
    assert "page_opened" not in _with_ui_link("auto_decompose", {"root_id": "root"}, "p", _engine()), \
        "a server past loopback is not on the person's machine"
    monkeypatch.delenv("GFSO_BIND")
    monkeypatch.setenv("GFSO_OPEN_PAGE", "0")
    assert "page_opened" not in _with_ui_link("auto_decompose", {"root_id": "root"}, "p", _engine())


def test_the_page_opened_at_the_go_goes_through_the_persons_browser(monkeypatch):
    """The go opens the project's page; it went through `start`, past the `BROWSER` the person had set, onto a screen
    whose owner had said where links go (2026-11-16). CONTROL: drop the `BROWSER` branch of `open_outside` and it is red."""
    ran = []
    monkeypatch.setenv("GFSO_NO_WINDOWS", "0")              # …nothing is opened: every start is a fake
    monkeypatch.setenv("BROWSER", "my-browser")
    monkeypatch.setattr(CH.subprocess, "Popen", lambda args, **k: ran.append(list(args)))
    monkeypatch.setattr(CH.webbrowser, "open", lambda url: ran.append(["webbrowser", url]))
    CH.open_outside("http://127.0.0.1:8000/?project=p")
    assert ran == [["webbrowser", "http://127.0.0.1:8000/?project=p"]], ran
