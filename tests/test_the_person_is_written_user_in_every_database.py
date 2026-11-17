"""The local person is written `user` (the author, 2026-11-16: (M) in docs/notes/PERSON_NAME.md). A database written
before 0.4.0 says `agent` in its party fields; it is rewritten once, the rewrite recorded in it, so one person has one
spelling. After it, a graph from before answers every door exactly as a graph written today: the same moves taken or
refused, the same log, the person's hand FAIL at a seam still binding, his node marked his. `agent` and `user` are born
as no role, console or token name."""
import json
import shutil
import sqlite3
from pathlib import Path

import anyio
import pytest
from starlette.testclient import TestClient

from gfso import config, signin
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.adapters.storage import person
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.api.server import create_app
from gfso.config import CALLER
from gfso.core.types import AgentId, Mode, TaskId
from gfso.engine import validation
from gfso.mcp import server as MS
from tests.support import REGISTER, criterion, make_engine

LOOPBACK = "http://127.0.0.1:8000"
PAGE = {"Origin": LOOPBACK, "Sec-Fetch-Site": "same-origin"}
PASS_K = [{"criterion": "k", "verdict": "pass", "evidence": "ran the check, it printed OK", "behaviours": ["K holds"],
           "probe": [{"command": "check k", "expect": "OK", "behaviour": "K holds"}]}]
#: the real databases a scan of this box found `agent` in, read as copies where they stand (a developer's machine)
REAL = Path(r"C:\Users\butte\Working\GFSO\data")
REAL_GRAPHS = ("gfso-dev-draft", "inchat-live-1113-201030", "ui-live-3", "otf-smoke-4")


def _build(path: Path, me: str, mode) -> None:
    """A graph as 0.3.0's code wrote it when `me` is `agent`: root and its issuer the person's, a kid at a seam (bob's)
    delivered, the person's hand FAIL on it, and the mode set by the person."""
    storage = SqliteStorage(str(path))
    e = make_engine(storage)
    e.start()
    e.record_root_issuer(TaskId("root"), AgentId(me))
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g", "G holds")],
                              "accepted_risks": REGISTER}, assignee=me)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", me)
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "k", "criteria": [criterion("k", "K holds")]},
                             "assignee": "bob", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "kid", "ACCEPT", "bob")
    T.signal(e, "kid", "DELIVER", "bob", result="built k")
    e.wait_idle()
    T.record_verdict(e, "kid", "FAIL", failed_criteria=["k"], reviewer=me, observed={"k": "ran check k: no output"})
    if mode is not None:
        e.set_mode(mode, None, AgentId(me))
    e.stop()
    storage.close()


def _legacy(path: Path, mode, monkeypatch) -> None:
    with monkeypatch.context() as m:          # …the person's name as 0.3.0 spelt it
        m.setattr(config, "PERSON", "agent")
        m.setattr(validation, "PERSON", "agent")
        _build(path, "agent", mode)


def _agents(path: Path) -> int:
    """Every value `agent` in the database: a column's whole value, or a leaf of a JSON one (the scan's rule)."""
    def leaves(v):
        if isinstance(v, dict):
            return sum(leaves(x) for x in v.values())
        if isinstance(v, list):
            return sum(leaves(x) for x in v)
        return v == person.OLD
    n = 0
    with sqlite3.connect(path) as c:
        for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            for row in c.execute(f'SELECT * FROM "{t}"'):
                for v in row:
                    if v == person.OLD:
                        n += 1
                    elif isinstance(v, str) and v[:1] in "[{" and f'"{person.OLD}"' in v:
                        try:
                            n += leaves(json.loads(v))
                        except ValueError:          # …not JSON: every quoted `agent` in it counts
                            n += v.count(f'"{person.OLD}"')
    return n


def _as(principal, fn):
    token = CALLER.set(principal)
    try:
        return fn()
    finally:
        CALLER.reset(token)


def _instrument_pass(e) -> str:
    """The instrument's PASS on the kid's delivery recorded, or why it was not."""
    try:
        e.record_exec_verdict(TaskId("kid"), "PASS", [], "val-1", per_criterion=PASS_K)
        return ""
    except ValueError as ex:
        return str(ex)


def _drive(path: Path) -> dict:
    """The person's moves on the graph, door by door, and what each left: the page FAILs the kid, the MCP client with
    no token signs its PASS over the redelivery, the CLI delivers the root."""
    storage = SqliteStorage(str(path))
    e = make_engine(storage)
    e.start()
    kid, out = TaskId("kid"), {}
    try:
        refused = _instrument_pass(e)                 # …an instrument's PASS over the person's hand FAIL
        blocked = e.pass_blocked_by(kid) or {}
        out["hand_fail_binds"] = ("recorded this delivery FAIL on k" in refused and blocked.get("kind") == "observed_fail"
                                  and "k" in blocked.get("fails", ()))
        out["mine"] = {s["task_id"]: s["mine"] for s in T.next_steps(e, actor=config.PERSON).get("steps", ())}
        page = TestClient(create_app(e), base_url=LOOPBACK, headers=PAGE)
        page.cookies.clear()
        out["page_whoami"] = page.get("/api/whoami").json()["name"]
        page.post("/api/run/signal", json={"task_id": "kid", "signal": "FAIL", "failed_criteria": ["k"]})
        e.wait_idle()
        T.signal(e, "kid", "DELIVER", "bob", result="built k again")
        e.wait_idle()
        out["second_pass"] = _instrument_pass(e)
        anyio.run(MS.create_server(e).call_tool, "signal", {"task_id": "kid", "signal": "PASS"})
        e.wait_idle()
        _as(signin.local_principal(), lambda: TL.TOOLS["signal"](e, "root", "DELIVER", result="the aggregate"))
        e.wait_idle()
        out["states"] = {t: str(e.graph.get_task(TaskId(t)).state) for t in ("root", "kid")}
        out["log"] = [(str(a.task_id), a.signal.name, str(a.source or ""), bool(a.rejected)) for a in e.audit_log()]
        out["issuer"] = str(e.graph.issuer_of(TaskId("root")))
        out["mode_by"] = (e.mode() or {}).get("by")
    finally:
        e.stop()
        storage.close()
    return out


@pytest.mark.parametrize("mode", [None, Mode.SOLO, Mode.SEMI, Mode.AUTO], ids=["no mode", "solo", "semi", "auto"])
def test_a_graph_from_before_answers_every_door_as_a_graph_written_today(tmp_path, monkeypatch, mode):
    old, new = tmp_path / "old.db", tmp_path / "new.db"
    _legacy(old, mode, monkeypatch)
    _build(new, config.PERSON, mode)
    assert _agents(old) > 0 and _agents(new) == 0
    then, now = _drive(old), _drive(new)
    assert _agents(old) == 0
    assert then == now, (then, now)
    assert then["hand_fail_binds"] and then["issuer"] == "user" and then["page_whoami"] == "user", then
    assert then["mode_by"] == ("user" if mode else None), then
    if mode is None:
        assert then["mine"].get("kid") is True, then
        moved = [x for x in then["log"] if x[3] is False and x[2] == "user"]
        assert {("kid", "FAIL"), ("kid", "PASS"), ("root", "DELIVER")} <= {x[:2] for x in moved}, then["log"]


def test_the_rewrite_is_recorded_and_runs_once(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    _legacy(old, Mode.SEMI, monkeypatch)
    SqliteStorage(str(old)).close()
    with sqlite3.connect(old) as c:
        mark = json.loads(c.execute("SELECT value FROM settings WHERE key = ?", (person.MARK,)).fetchone()[0])
        assert mark["rewrote"] == {"agent": "user"} and mark["at"], mark
        rows = mark["rows"]
        assert rows["tasks.assignee"] == 1 and rows["settings.value"] == 1 and rows["audit_log.source"] > 0, rows
        assert rows["settings.value.by"] == 1 and rows["critiques.critique_json[].validator"] == 1, rows
        assert person.rename(c) == {} and person.pending(c) == {}
    SqliteStorage(str(old)).close()
    with sqlite3.connect(old) as c:
        again = json.loads(c.execute("SELECT value FROM settings WHERE key = ?", (person.MARK,)).fetchone()[0])
    assert again == mark, "a second open changes nothing"


def test_a_graph_that_already_holds_a_user_party_is_not_merged_into_the_person(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    _legacy(old, None, monkeypatch)
    with sqlite3.connect(old) as c:
        c.execute("UPDATE tasks SET assignee = 'user' WHERE id = 'kid'")
    with pytest.raises(person.TwoParties, match="already names a party `user`"):
        SqliteStorage(str(old))
    with sqlite3.connect(old) as c:
        assert c.execute("SELECT assignee FROM tasks WHERE id = 'root'").fetchone()[0] == "agent", "nothing written"


def test_the_home_is_not_rewritten_where_a_role_or_token_is_named_user(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    _legacy(tmp_path / "old.db", None, monkeypatch)
    signin.ready()
    with signin._db() as db:
        db.execute("INSERT INTO tokens VALUES ('h', 'tok-1', 'local', 'user', 0)")
    with pytest.raises(person.TwoParties, match="a token for `user`"):
        signin.rename_the_person()
    assert _agents(tmp_path / "old.db") > 0, "nothing written"


@pytest.mark.parametrize("name", ["agent", "user"])
def test_the_persons_names_are_born_as_no_one_elses(name):
    e = make_engine()
    out = TL.register_agent(e, name, "llm-validator", workdir=".")
    assert out.get("refused") and "reserved" in out["error"], out
    for born in (signin.issue, signin.own):
        with pytest.raises(ValueError, match="reserved"):
            born(name)


def test_a_node_is_not_assigned_to_the_name_of_before():
    e = make_engine()
    e.start()
    out = T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g", "G holds")],
                                    "accepted_risks": REGISTER}, assignee="agent")
    assert "reserved" in str(out) and e.graph.get_task(TaskId("root")) is None, out
    e.stop()


@pytest.mark.skipif(not (REAL / "gfso-dev-draft.db").exists(), reason="the developer's databases are not on this machine")
def test_the_real_databases_hold_no_agent_after_the_rewrite(tmp_path, monkeypatch):
    home = tmp_path / "data"
    (home / "signin").mkdir(parents=True)
    for name in REAL_GRAPHS:
        for tail in ("", "-wal"):
            if (src := REAL / f"{name}.db{tail}").exists():
                shutil.copy2(src, home / src.name)
    for tail in ("", "-wal"):
        if (src := REAL / "signin" / f"state.db{tail}").exists():
            shutil.copy2(src, home / "signin" / src.name)
    monkeypatch.setenv("GFSO_DATA_DIR", str(home))
    files = sorted(home.glob("*.db")) + [home / "signin" / "state.db"]
    before = {f.name: _agents(f) for f in files}
    if not sum(before.values()):
        # the live data/ was already rewritten (the server's own start ran the migration): nothing left to prove here,
        # the migration's own tests cover the rewrite — never a red on a machine that has upgraded
        pytest.skip("this machine's databases are already written `user`")
    done = signin.rename_the_person()
    after = {f.name: _agents(f) for f in files}
    print("before", before, "\nrewritten", json.dumps(done, indent=1), "\nafter", after)
    assert sum(before.values()) > 0 and not any(after.values()), (before, after)
    assert signin.rename_the_person() == {}, "a second run changes nothing"


def test_one_graphs_conflict_refuses_that_graph_and_the_others_are_rewritten(tmp_path, monkeypatch):
    # the server stopped whole on one graph's `user`, its clean neighbour left unrewritten (critic over 2b8e97f)
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    _legacy(tmp_path / "bad.db", None, monkeypatch)
    _legacy(tmp_path / "good.db", None, monkeypatch)
    with sqlite3.connect(tmp_path / "bad.db") as c:
        c.execute("UPDATE tasks SET assignee = 'user' WHERE id = 'kid'")
    done = signin.rename_the_person()
    assert "already names a party `user`" in done["bad.db"]["refused"], done
    assert _agents(tmp_path / "good.db") == 0 and _agents(tmp_path / "bad.db") > 0, done


def test_a_graph_that_cannot_be_written_is_refused_alone(tmp_path, monkeypatch):
    # serve crashed with a traceback on a read-only legacy graph (critic over 2b8e97f)
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    _legacy(tmp_path / "ro.db", None, monkeypatch)
    _legacy(tmp_path / "rw.db", None, monkeypatch)
    real = sqlite3.connect

    def connect(path, *a, **kw):
        return real(f"file:{path}?mode=ro", *a, uri=True, **kw) if str(path).endswith("ro.db") else real(path, *a, **kw)
    monkeypatch.setattr(signin.sqlite3, "connect", connect)
    done = signin.rename_the_person()
    assert "not rewritten" in done["ro.db"]["refused"] and "rw.db" in done and "refused" not in done["rw.db"], done


def test_a_graph_with_nothing_to_rewrite_is_opened_without_a_write_lock(tmp_path):
    db = tmp_path / "new.db"
    SqliteStorage(str(db))                     # born today: nothing to rewrite
    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    assert person.rename(ro) == {}, "a read-only open of a graph with nothing pending takes no lock"
    ro.close()
