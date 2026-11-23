"""The person's name signs from two places only: his page, and a connection logged in as him — an MCP connection that
took his name (`act_as('user')`). Any other call with no credential — a script, curl, `gfso run` from any shell, an MCP
connection that took no name — reads, and its move is refused naming how to sign (the author, 2026-11-20: «только агент
который залогинился под именем user может писать в граф»; 2026-11-21: «взятие имени и есть логининг агента в системе»).

His seams keep his word by default: in a project with no mode, a node he issues to another is his to move (§10.1,
§10.2) — from an agent's connection signing as his name only with his words, from his page as it is — and the criterion
read against his words comes with his act of issuing it. What a seam's holder does in its chat follows from the name
taken (`act_as`), the executor's own fact, with no button set by anyone."""
from __future__ import annotations

import contextlib
import uuid
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

import gfso.tools as T
import gfso.tools_llm as TL
from gfso import config, driver, signin
from gfso.adapters.llm.stub import StubLLM
from gfso.api.server import create_app
from gfso.config import CALLER, LEASE_HEADER, Principal
from gfso.core.protocol.invariants import INTENT
from gfso.core.types import TaskId
from gfso.engine import validation as V
from tests.support import REGISTER, criterion, instrument_passes, make_engine

SPEC = {"description": "node", "criteria": [criterion("k", "keep")]}
LOOPBACK = "http://127.0.0.1:8000"
#: his own agent's connection: signs as his name, and is no page
AGENT = config.STANDING
PAGE = signin.PAGE
WORDS = "да, принимаю"


@pytest.fixture
def door():
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    yield e, create_app(e)
    e.stop()


def _client(app, **headers) -> TestClient:
    c = TestClient(app, base_url=LOOPBACK, headers=headers)
    c.cookies.clear()
    return c


@contextlib.contextmanager
def _as(p: Principal):
    token = CALLER.set(p)
    try:
        yield
    finally:
        CALLER.reset(token)


def _call(p, verb, e, *a, **kw):
    with _as(p):
        return TL.TOOLS[verb](e, *a, **kw)


# ── 1. who may write as `user` ────────────────────────────────────────────────

@pytest.mark.parametrize("headers", [{}, {LEASE_HEADER: uuid.uuid4().hex}], ids=["a script", "the CLI in a console"])
def test_a_call_with_no_credential_and_no_bridge_reads_and_its_move_is_refused_naming_the_lift(door, headers):
    e, app = door
    c = _client(app, **headers)
    assert c.get("/api/graph").status_code == 200
    assert c.get("/api/whoami").json()["kind"] == "none"
    out = c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).json()
    assert out.get("refused") and "gfso ui" in out["error"] and "gfso agent" in out["error"] \
        and "MCP" in out["error"], out
    assert e.graph.get_task(TaskId("n")) is None


def test_the_servers_life_is_still_a_consoles_own_with_no_credential(door):
    """A bridge's heartbeat signs no name: it goes before the bridge has recorded its console."""
    assert _client(door[1]).post("/api/lease", json={"id": "x"}).json()["ok"]


def _conn(path, **headers):
    """A connection to this server from the person's own process at loopback, asking `path`."""
    return SimpleNamespace(headers=headers, cookies={}, client=("127.0.0.1", 50000),
                           scope={"path": path, "server": ("127.0.0.1", 8000)})


def test_an_mcp_connection_that_took_no_name_reads_and_one_logged_in_as_him_signs(monkeypatch):
    """Every console connects its MCP by itself — a bare agent with access to MCP, not to the system (the author,
    2026-11-21): a bridge's connection or a stdio server that took no name reads (`UNTAKEN`); logged in as him
    (`act_as('user')`, `signin.take`) it signs as `user`, his page apart. CONTROL: an untaken MCP connection read as the
    standing agent — it signs."""
    monkeypatch.delenv(config.TOKEN_ENV, raising=False)
    monkeypatch.setattr(signin, "console_lease", lambda: None)
    lease = uuid.uuid4().hex
    at = {"host": "127.0.0.1:8000", LEASE_HEADER: lease}
    assert signin.principal_of(_conn("/mcp", **at)) is signin.UNTAKEN
    assert signin.local_principal(mcp=True) is signin.UNTAKEN
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [])       # …no earlier test's holding of his name is live
    signin.take(lease, "user")
    assert signin.principal_of(_conn("/mcp", **at)).signs_as == ("user",)
    assert signin.principal_of(_conn("/api/run/signal", **at)).signs_as == ("user",), "his hook and shell sign too"
    signin.let_go(lease)
    assert not signin.principal_of(_conn("/mcp", **at)).signs_as, "logged out"
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    assert not signin.principal_of(_conn("/mcp", host="127.0.0.1:8000", origin=LOOPBACK)).signs_as, "the page signs in"


def test_a_lost_holding_logs_in_again_by_the_same_door():
    """A connection whose name another took logs in again, under it or another name, or out — never the person."""
    lease = uuid.uuid4().hex
    with signin._db() as db:
        db.execute("INSERT INTO holds VALUES (?, ?, ?, ?, ?, ?)", (signin._hash(lease), "eng-lost", "local", "claim",
                                                                   1.0, 2.0))
    p = signin.held(lease)
    assert not p.signs_as and "act_as('eng-lost')" in p.lift and "act_as('')" in p.lift, p.lift


def test_the_cli_with_no_server_reads_and_signs_nothing(door, monkeypatch):
    e, _ = door
    monkeypatch.delenv(config.TOKEN_ENV, raising=False)
    monkeypatch.setattr(signin, "console_lease", lambda: None)
    assert signin.local_principal() is signin.BARE
    assert signin.local_principal(mcp=True) is signin.UNTAKEN      # …a stdio server that has taken no name
    monkeypatch.setattr(driver, "build_engine_from_env", lambda project=None: e)
    monkeypatch.setattr(driver, "select_project", lambda p: None)
    out = driver._locally(TL.TOOLS["create_task"], None, [], {"task_id": "n", "spec": SPEC})
    assert out.get("refused") and "gfso agent" in out["error"], out
    assert e.graph.get_task(TaskId("n")) is None


# ── 2. his seams, protected by default ────────────────────────────────────────

def _his_seam(e):
    """His root, and a seam he issues from it to `engineering` from his page — no mode, no scope — delivered, and
    observed by him."""
    _call(PAGE, "create_task", e, "root", {"description": "his goal", "criteria": [criterion("g")]}, assignee="user")
    _call(PAGE, "decompose", e, "root", [{"task_id": "root.eng", "assignee": "engineering", "covers": ["g"],
                                          "spec": {"description": "a direction", "criteria": [criterion("d")]}}],
          accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "root.eng", "ACCEPT", "engineering")
    T.signal(e, "root.eng", "DELIVER", "engineering", result="it holds", self_validation="PASS")
    e.wait_idle()
    instrument_passes(e, TaskId("root.eng"))


def test_an_agent_signing_as_him_passes_a_seam_he_issued_only_on_his_words(door):
    e, _ = door
    _his_seam(e)
    out = _call(AGENT, "signal", e, "root.eng", "PASS")
    assert out.get("refused") and "user_said" in out["error"], out
    out = _call(AGENT, "signal", e, "root.eng", "PASS", user_said=WORDS)
    assert not out.get("refused"), out
    e.wait_idle()
    assert str(e.graph.get_state(TaskId("root.eng"))).endswith("DONE")


def test_his_page_passes_a_seam_he_issued_as_it_is(door):
    e, _ = door
    _his_seam(e)
    assert not _call(PAGE, "signal", e, "root.eng", "PASS").get("refused")


# ── 3. no button ──────────────────────────────────────────────────────────────

def test_his_issue_of_a_seam_installs_the_criterion_read_against_his_words(door):
    e, _ = door
    e.workforce.publish_roster({"engineering": "llm-executor"})      # …a role: a human's node gets none (`_by_an_agent`)
    _his_seam(e)
    assert any(c.name == INTENT for c in e.graph.get_task(TaskId("root.eng")).spec.criteria)
    assert all(c.name != INTENT for c in e.graph.get_task(TaskId("root")).spec.criteria)


def test_the_page_switch_turns_the_criterion_off_at_his_next_issue(door):
    e, _ = door
    assert not _call(PAGE, "set_mode", e, intent_check=False).get("refused")
    _his_seam(e)
    assert all(c.name != INTENT for c in e.graph.get_task(TaskId("root.eng")).spec.criteria)


def test_a_name_taken_in_a_chat_holds_each_seam_he_issues_to_it_with_no_scope_set(door):
    e, _ = door
    _his_seam(e)
    assert e.scope_at("root.eng") is None
    e.performs_in_chat("engineering")              # …what its connection's `act_as` records
    s = e.scope_at("root.eng")
    assert s and (s["top"], s["holder"], s["mode"], s["perform"]) == ("root.eng", "engineering", "solo", "in_chat"), s
    e.performs_in_chat("user")                     # …never a name of his
    assert "user" not in V.in_chat_names(e.graph)


def test_a_scope_is_no_longer_set_at_a_node(door):
    e, _ = door
    _his_seam(e)
    out = _call(PAGE, "set_mode", e, "solo", perform="in_chat", node="root")
    assert out.get("refused") and "act_as" in out["error"], out
