"""A move is signed by a name its credential carries, resolved by the server at every door and never typed by the caller
(docs/notes/SIGN_IN.md): a page session signs as any name its person owns, a token as its one name, a local client that
is no browser as the standing agent, and anything a front, a browser with no session where the page signs in
(`--protected`) or a bind past loopback sends moves nothing. The log keeps the credential (`via`) beside the name."""
import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from gfso import config, signin
from gfso.adapters.llm.stub import StubLLM
from gfso.api.server import create_app
from gfso.config import CALLER, data_dir
from gfso.core.types import Signal, TaskId
from gfso.driver import _locally
from gfso.runtime import ProjectRegistry
from gfso.mcp import connect as C
from gfso import tools_llm as T
from tests.support import a_repository, criterion, make_engine

SPEC = {"description": "node", "criteria": [criterion("k", "keep")]}
LOOPBACK = "http://127.0.0.1:8000"


@pytest.fixture
def door():
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    yield e, create_app(e)
    e.stop()


def _client(app, base=LOOPBACK, **headers) -> TestClient:
    c = TestClient(app, base_url=base, headers=headers)
    c.cookies.clear()                     # …no session: what a call carrying none is given
    return c


def _signed(e, task, sig):
    return [(str(a.source), a.via, a.rejected) for a in e.audit_log(TaskId(task)) if a.signal == sig]


def test_a_local_client_with_no_credential_reads_and_the_standing_agent_types_no_other(door):
    """A local client with no credential and no bridge reads and signs nothing; the standing agent — the person's own
    MCP connection, `config.STANDING` — signs as his name and types no other."""
    e, app = door
    c = _client(app)
    assert c.get("/api/whoami").json()["kind"] == "none"
    out = c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).json()
    assert out.get("refused") and "gfso agent" in out["error"], out
    token = config.CALLER.set(config.STANDING)
    try:
        assert not T.TOOLS["create_task"](e, "n", SPEC).get("refused")
        out = T.TOOLS["signal"](e, "n", "ACCEPT", source="dev")
        assert out.get("refused") and "signs only as user" in out["error"] and "gfso agent dev" in out["error"], out
        assert T.TOOLS["signal"](e, "n", "ACCEPT")["accepted"]
    finally:
        config.CALLER.reset(token)
    e.wait_idle()
    assert _signed(e, "n", Signal.ACCEPT) == [("user", "default", False)]


@pytest.mark.parametrize("base, headers, protected", [
    (LOOPBACK, {"Origin": LOOPBACK}, True),                 # a browser with no session, where the page signs in
    (LOOPBACK, {"Sec-Fetch-Site": "same-origin"}, True),
    ("http://testserver", {}, False),                       # a front's name
    (LOOPBACK, {"X-Forwarded-For": "100.64.0.7"}, False),   # a front that rewrote Host
    (LOOPBACK, {"Tailscale-User-Login": "a@b"}, False),
])
def test_a_call_no_credential_vouches_for_moves_nothing_and_reads(door, monkeypatch, base, headers, protected):
    e, app = door
    if protected:
        monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    c = _client(app, base, **headers)
    out = c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).json()
    assert out.get("refused") and "signed by no one" in out["error"] and "gfso ui" in out["error"], out
    assert e.graph.get_task(TaskId("n")) is None
    assert c.get("/api/graph").status_code == 200 and c.get("/api/whoami").json()["signs_as"] == []


def test_past_a_loopback_bind_a_loopback_host_vouches_for_no_one(door, monkeypatch):
    _, app = door
    monkeypatch.setenv("GFSO_BIND", "0.0.0.0")
    out = _client(app).post("/api/run/create_task", json={"task_id": "n", "spec": SPEC}).json()
    assert out.get("refused") and "front" in out["error"], out


def test_a_session_opened_on_a_spent_code_signs_as_its_persons_names_and_its_default_is_the_holder(door, monkeypatch):
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")                 # …where the page signs in: signed out, it is no one
    e, app = door
    signin.issue("ui-draft")
    c = _client(app, Origin=LOOPBACK)
    code = signin.code()
    r = c.get(f"/signin?code={code}", follow_redirects=False)
    assert r.status_code == 303 and "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert c.get(f"/signin?code={code}", follow_redirects=False).status_code == 403, "a code opens once"
    who = c.get("/api/whoami").json()
    assert who["how"] == "signed in" and who["kind"] == "person" and "ui-draft" in who["signs_as"], who
    c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC, "assignee": "ui-draft"})
    out = c.post("/api/run/signal", json={"task_id": "n", "signal": "ACCEPT", "source": "never-issued"}).json()
    assert out.get("refused") and "never-issued" in out["error"], out
    assert c.post("/api/run/signal", json={"task_id": "n", "signal": "ACCEPT"}).json()["accepted"]   # its Del, his
    e.wait_idle()
    assert _signed(e, "n", Signal.ACCEPT) == [("ui-draft", "session", False)]
    c.post("/api/signout")
    assert c.get("/api/whoami").json()["signs_as"] == []


def test_a_token_signs_as_its_one_name_through_every_door_and_the_log_names_it(door, monkeypatch):
    e, app = door
    tid, token = signin.issue("engineering")
    c = _client(app, Authorization=f"Bearer {token}")
    assert c.get("/api/whoami").json() == {"name": "engineering", "kind": "agent", "how": "token for engineering",
                                           "signs_as": ["engineering"]}
    c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC, "assignee": "engineering"})
    assert c.post("/api/run/signal", json={"task_id": "n", "signal": "ACCEPT", "source": "user"}).json().get("refused")
    assert c.post("/api/run/signal", json={"task_id": "n", "signal": "ACCEPT"}).json()["accepted"]
    e.wait_idle()
    assert _signed(e, "n", Signal.ACCEPT)[-1] == ("engineering", tid, False)
    # …the CLI with no server reads the same token, and a token not held is refused, not taken for the standing agent
    monkeypatch.setenv(config.TOKEN_ENV, token)
    assert _locally(lambda _e: config.caller_id(), None, [], {}) == "engineering"
    signin.revoke("engineering")
    assert _client(app, Authorization=f"Bearer {token}").get("/api/whoami").json()["signs_as"] == []


def _registered(e, name: str, place) -> None:
    """`name` on the roster as an executor in `place`, a repository of its own: a directory that is not one is refused
    (`no_repository`), and a test run in a copy of the tree with no `.git` would then lean on a role never registered."""
    assert not T.TOOLS["register_agent"](e, name, "llm-executor", workdir=str(a_repository(place))).get("refused")


def test_the_systems_names_are_issued_to_no_one(door, tmp_path):
    e, _ = door
    _registered(e, "exec-1", tmp_path / "work")
    for name in ("exec-1", "system", "a b"):
        with pytest.raises(ValueError):
            signin.issue(name)


def test_the_names_in_the_graphs_become_the_local_persons_on_first_start(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    with sqlite3.connect(tmp_path / "old.db") as g:
        g.execute("CREATE TABLE tasks (assignee TEXT)")
        g.executemany("INSERT INTO tasks VALUES (?)", [("author-draft",), ("person",)])
        g.execute("CREATE TABLE audit_log (source TEXT)")
        g.execute("INSERT INTO audit_log VALUES ('engineering')")
    g.close()
    signin.ready()
    assert signin.names_of(config.LOCAL_PERSON) == ("user", "author-draft", "engineering")
    assert (data_dir() / "signin" / "state.db").exists() and not (data_dir() / "signin.db").exists()


def test_the_launch_name_is_closed():
    """`GFSO_AGENT_ID` renames nothing and signs nothing: a console launched with it and no token is told what to run."""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("GFSO_AGENT_ID", "engineering")
        m.delenv(config.TOKEN_ENV, raising=False)
        assert config.agent_id() == "user" and CALLER.get() is None and config.caller_id() == "user"
        said = signin.launch_refusal()
        assert "gfso agent engineering" in said
        # …at every client door, not the bridge's alone: the CLI, `gfso wait` and a stdio server read these two
        assert signin.local_principal().signs_as == () and signin.local_principal().lift == said
        with pytest.raises(SystemExit, match="gfso agent engineering"):
            signin.credential_header()
        m.setenv(config.TOKEN_ENV, "x")
        assert signin.launch_refusal() is None


def test_a_person_never_signs_as_a_system_role_whatever_the_old_graphs_named(door, monkeypatch, tmp_path):
    """The graphs of a machine name its system's roles long gone from the roster (`exec-1`, `ck-val-1`, a flag taken for
    a name): none becomes the person's, none is issued, and one his state already holds signs nothing (§10.1)."""
    e, app = door
    old = tmp_path / "old.db"
    with sqlite3.connect(old) as g:
        g.execute("CREATE TABLE tasks (assignee TEXT)")
        g.executemany("INSERT INTO tasks VALUES (?)", [(n,) for n in (
            "exec-1", "val-1", "ck-val-1", "gb-sql-val-1", "ui-live-3-val", "p-exec-2", "ui-live-2-exec", "--assignee", "author-draft")])
    g.close()
    with pytest.MonkeyPatch.context() as m:
        m.setenv("GFSO_DATA_DIR", str(tmp_path))
        signin.ready()
        assert signin.names_of(config.LOCAL_PERSON) == ("user", "author-draft")
    for name in ("exec-1", "ck-val-1", "ui-live-3-val", "ui-live-2-exec"):
        with pytest.raises(ValueError, match="system"):
            signin.issue(name)
    signin.own("exec-1")                   # …a row an earlier build wrote: the resolution reads the role, not the row
    c = _client(app)
    c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC, "assignee": "exec-1"})
    c.cookies.set(signin.COOKIE, signin.redeem(signin.code()))
    assert "exec-1" not in c.get("/api/whoami").json()["signs_as"]
    c.post("/api/run/signal", json={"task_id": "n", "signal": "ACCEPT"})
    e.wait_idle()
    assert ("exec-1", "session") not in [(s, v) for s, v, _ in _signed(e, "n", Signal.ACCEPT)]
    # …and a token issued before its name became a role on the roster signs nothing now
    _, token = signin.issue("later-role")
    _registered(e, "later-role", tmp_path / "work")
    assert _client(app, Authorization=f"Bearer {token}").get("/api/whoami").json()["signs_as"] == []


def test_through_a_front_a_caller_signed_by_no_one_ends_no_lease_stops_no_server(door):
    e, app = door
    front, ended = _client(app, "http://testserver"), []
    app.state.exit_fn = lambda: ended.append(True)          # …a stop let through ends this test, not the process
    assert front.post("/api/shutdown", json={"force": True}).status_code == 403
    _client(app).post("/api/lease", json={"id": "mine"})
    assert front.delete("/api/lease/mine").status_code == 403 and "mine" in app.state.leases
    assert _client(app).delete("/api/lease/mine").status_code == 200      # …a local client still ends its own


def test_the_pages_switch_names_no_signer():
    """Under a mode the page's stop and start sent `by: 'person'`, a name nobody owns: refused, with a lift `gfso agent`
    refuses — the person's main move under AUTO. The session signs the switch."""
    text = (Path(config.__file__).parent / "web" / "js" / "header.js").read_text(encoding="utf-8")
    assert "by: 'person'" not in text and "switchRun('stop_project', {why})" in text and "switchRun('start_project', {})" in text


def test_the_sign_in_state_is_no_project_and_an_earlier_file_moves_once(tmp_path, monkeypatch):
    """Beside the graphs the state file was read as one: «signin» in the project list, its delete offered (ui).
    CONTROL: keep `_state` at `data/signin.db` and the registry lists it."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    with sqlite3.connect(tmp_path / "signin.db") as old:           # …what an earlier build left
        old.execute("CREATE TABLE marker (x)")
    old.close()
    signin.ready()
    assert not (tmp_path / "signin.db").exists() and (tmp_path / "signin" / "state.db").exists()
    with sqlite3.connect(tmp_path / "signin" / "state.db") as moved:
        assert moved.execute("SELECT name FROM sqlite_master WHERE name = 'marker'").fetchone()
    moved.close()
    assert "signin" not in ProjectRegistry().names()


def test_a_stop_and_a_start_carry_the_credential_they_came_through(door):
    """The run's events said «STOPPED by agent» for a page's stop and a console's alike (ui). CONTROL: drop `_via()`
    from `Stops.pause` and the record carries none."""
    e, app = door
    _, token = signin.issue("engineering")
    c = _client(app, Authorization=f"Bearer {token}")
    c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC, "assignee": "engineering"})
    c.post("/api/run/stop_project", json={"why": "lunch"})
    assert (e.stops.paused() or {}).get("via", "").startswith("tok-"), e.stops.paused()
    c.post("/api/run/start_project", json={})
    assert e.stops.paused() is None


def test_a_revision_through_a_door_is_signed_by_its_credential_not_refused_as_no_one(door):
    """`revise` defaults its signer (`agent=""`): the door fills only signers with no default, so the verb reads the caller
    itself, as its neighbours do — an omitted one went to the engine as '' and every credential's revision was refused."""
    e, app = door
    _, token = signin.issue("engineering")
    c = _client(app, Authorization=f"Bearer {token}")
    assert c.post("/api/run/create_task", json={"task_id": "n", "spec": SPEC, "assignee": "engineering"}).status_code == 200
    assert e.graph.get_task(TaskId("n")) is not None
    out = c.post("/api/run/revise", json={"task_id": "n", "spec": {**SPEC, "description": "node, revised"}}).json()
    assert not out.get("refused"), out
    assert e.graph.get_task(TaskId("n")).spec.description == "node, revised"
