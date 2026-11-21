"""A console already running takes a stream's name over its own gfso connection (`act_as`), no relaunch: the stream is a
name the person opened and assigned, never a console or a session (DEV_GRAPH_AND_TEAM §1). The connection is its
bridge's lease, so the name outlives a `/clear` and a rebuilt leg; one live connection holds a name (Del unique, §2.6);
the taking is recorded with who, which name and when, and every move after it carries the connection (Thm 11)."""
import contextlib
import json
import os
import subprocess
import sys
import uuid

import anyio
import psutil
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import Context, FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

import gfso.tools as T
from gfso import config, signin
from gfso.api.server import create_app
from gfso.core.types import Signal, TaskId
from gfso.mcp import connect as C, stdio
from gfso.mcp.server import create_server
from gfso.runtime import ProjectRegistry
from tests import test_a_connection_signs_as_its_principal as P
from tests.support import REGISTER, make_engine
from tests.test_a_connection_signs_as_its_principal import HUMAN, door  # noqa: F401 — the fixture


def _his_seam(e, name):
    """His root, and a seam he issues from it to `name`: a BLOCK of it is his to rule."""
    T.create_task(e, "root", {"description": "his goal", "criteria": [HUMAN]}, assignee="user", agent="user")
    T.decompose(e, "root", [{"task_id": f"root.{name}", "assignee": name, "covers": ["accepted"],
                             "spec": {"description": "a direction", "criteria": [HUMAN]}}],
                accepted_risks=REGISTER, agent="user")
    e.wait_idle()


def _lease():
    return uuid.uuid4().hex


async def _call(url, lease, verb, args):
    async with streamablehttp_client(url, headers={config.CLIENT_HEADER: "code", config.LEASE_HEADER: lease}) as (r, w, _), \
            ClientSession(r, w) as s:
        await s.initialize()
        out = await s.call_tool(verb, args)
    text = "".join(getattr(c, "text", "") for c in out.content)
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text}


@pytest.fixture
def go(door, monkeypatch):
    e, url = door
    # …a server whose bridges are known, none live: a holding left by an earlier test is no live connection's
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [])
    return e, lambda lease, verb, **a: anyio.run(_call, url, lease, verb, a)


def _him(go):
    """A connection logged in as the person (`act_as('user')`)."""
    lease = _lease()
    assert go(lease, "act_as", name="user")["signs_as"] == ["user"]
    return lease


def _stream(e, go, name):
    """A node the person assigns to `name`: the stream he opens, from a connection logged in as him."""
    out = go(_him(go), "create_task", task_id=f"{name}-root", spec={"description": "a stream", "criteria": [HUMAN]},
             assignee=name)
    e.wait_idle()
    assert e.graph.get_task(TaskId(f"{name}-root")) is not None, out


def test_a_connection_that_took_no_name_reads_and_signs_nothing(go):
    """Every Claude Code console connects its MCP by itself: a bare agent with access to MCP, not to the system. Taking a
    name is its log-in (the author, 2026-11-21: «взятие имени и есть логининг агента в системе»). CONTROL: an untaken
    connection read as the person (`STANDING` at the MCP door) — its move is accepted."""
    e, go = go
    one = _lease()
    who = go(one, "act_as")
    assert who["signs_as"] == [] and who["kind"] == "none" and "act_as('user')" in who["lift"], who
    out = go(one, "create_task", task_id="n0", spec={"description": "a goal", "criteria": [HUMAN]})
    assert e.graph.get_task(TaskId("n0")) is None and "act_as('user')" in str(out), out   # …the refusal its lift


def test_act_as_user_logs_the_connection_in_as_the_person_and_empty_logs_it_out(go):
    """Locally no token, his own default; one live connection holds his name as any other. CONTROL: `user` reserved at
    `take` — refused; `act_as('')` reading as a no-name read — still logged in."""
    e, go = go
    one = _him(go)
    go(one, "create_task", task_id="n1", spec={"description": "a goal", "criteria": [HUMAN]}, assignee="eng-n1")
    e.wait_idle()
    assert e.graph.get_task(TaskId("n1")) is not None, "his write refused"
    out = go(one, "act_as", name="")
    assert out["signs_as"] == [] and out["kind"] == "none", out
    assert go(one, "act_as")["signs_as"] == []
    assert go(_lease(), "act_as", name="user")["signs_as"] == ["user"], "his name freed at the log-out"


def test_a_name_owing_a_move_is_left_freely_with_the_moves_named_and_the_fact_recorded(go):
    """Leaving a name is voluntary, as taking it is (the author, 2026-11-21): never refused. Where the name owed moves of
    its own, the reply names them as they are — the next holder picks them up — and the system records the fact on the
    feed, no one's words; with nothing owed, no record. CONTROL: the advice unsaid, or the record unwritten — red; the
    move named by its action (`accept`) — red."""
    e, go = go
    _his_seam(e, "eng9")
    signin.issue("ui9")
    records = lambda: [r["message"] for r in e.pipeline_log() if "was left by its connection" in r["message"]]  # noqa
    one = _lease()
    assert go(one, "act_as", name="eng9")["name"] == "eng9"
    out = go(one, "act_as", name="")
    assert out["signs_as"] == [] and "root.eng9 ACCEPT" in out["advice"] and "next holder" in out["advice"], out
    assert records() == ["eng9 was left by its connection with 1 owed move(s): default/root.eng9 ACCEPT"], records()
    assert go(one, "act_as", name="eng9")["name"] == "eng9"
    go(one, "signal", task_id="root.eng9", signal="ACCEPT")
    e.wait_idle()
    out = go(one, "act_as", name="ui9")                  # …a log-in under another name leaves it as freely
    assert out["signs_as"] == ["ui9"] and "root.eng9 DELIVER" in out["advice"], out
    out = go(one, "act_as", name="")                     # …`ui9` owed nothing
    assert out["signs_as"] == [] and "advice" not in out and len(records()) == 2, (out, records())


def test_a_move_owed_in_any_project_is_read_wherever_the_log_out_is_asked(monkeypatch, tmp_path):
    """A name is held across every project: its move owed in P is named whatever project the call names or resolves
    to — none that exists, another owing nothing, none at all (a session's project is lost at a server restart) — and
    a project that cannot be read is named as unread. CONTROL: the owed moves read in the resolved project alone — no
    advice in the three; an unread project unsaid — red."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [])
    reg = ProjectRegistry()
    srv = create_server(reg)._mcp_server

    async def session(*calls):
        async with create_connected_server_and_client_session(srv) as s:
            return [json.loads((await s.call_tool(v, a)).content[0].text) for v, a in calls]
    try:
        anyio.run(session, ("act_as", {"name": "user"}), ("use_project", {"project": "pp"}),
                  ("create_task", {"task_id": "t", "spec": {"description": "a stream", "criteria": [HUMAN]},
                                   "assignee": "engz"}),
                  ("use_project", {"project": "qq"}), ("act_as", {"name": "engz", "project": "pp"}),
                  ("signal", {"task_id": "t", "signal": "ACCEPT", "project": "pp"}))
        reg.engine("pp").wait_idle()
        back = ("act_as", {"name": "engz", "project": "pp"})
        nope, _, q, _ = anyio.run(session, ("act_as", {"name": "", "project": "nope"}), back,
                                  ("act_as", {"name": "", "project": "qq"}), back)
        (bare,) = anyio.run(session, ("act_as", {"name": ""}))        # …a fresh session: no project of its own
        for out in (nope, q, bare):
            assert out["signs_as"] == [] and "pp/t DELIVER" in out.get("advice", ""), out
        anyio.run(session, back)
        (tmp_path / "broken.db").write_bytes(b"not a database")
        (broken,) = anyio.run(session, ("act_as", {"name": ""}))
        assert "broken" in broken.get("advice", ""), broken
    finally:
        signin.let_go(signin.PROCESS_LEASE)
        for n in ("pp", "qq", "default"):
            with contextlib.suppress(Exception):
                reg.engine(n, create=False).stop()


def test_a_lost_holding_frees_nothing_and_leaves_freely(go, monkeypatch):
    """Another connection took the name while this one was silent: what the name owes is that connection's now, and
    leaving the lost holding says nothing of it. CONTROL: a lost holding read as held — the new holder's move advised
    and recorded as this one's leaving."""
    e, go = go
    _stream(e, go, "pz")
    one, two = _lease(), _lease()
    assert go(one, "act_as", name="pz")["name"] == "pz"
    go(one, "signal", task_id="pz-root", signal="ACCEPT")
    e.wait_idle()
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [two])          # …its bridge's lease lapsed
    assert go(two, "act_as", name="pz")["name"] == "pz"
    out = go(one, "act_as", name="")
    assert out["signs_as"] == [] and "advice" not in out, out
    assert go(one, "act_as", name="user")["signs_as"] == ["user"]


def test_a_stdio_servers_connection_is_recorded_under_its_console_so_its_hook_signs_as_its_name(monkeypatch):
    """A standalone `gfso mcp` console: its Stop hook and its shell find the stdio server's own lease as a bridge's is
    found (`stdio.recorded`), and sign as the name it took. CONTROL: the stdio server recording nothing — its hook
    reads as no one, never held."""
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [])
    signin.take(signin.PROCESS_LEASE, "user")
    with stdio.recorded(console=psutil.Process()):
        assert _from_a_child() == signin.PROCESS_LEASE
    assert _from_a_child() == "None", "the record outlived the server"


def test_a_running_console_takes_the_stream_it_was_assigned_and_keeps_it(go):
    e, go = go
    _stream(e, go, "eng1")
    one = _lease()
    assert go(one, "act_as")["signs_as"] == []
    took = go(one, "act_as", name="eng1")
    assert took["name"] == "eng1" and took["signs_as"] == ["eng1"], took
    # …a fresh MCP session on the same bridge — a `/clear`, a rebuilt leg — is still the stream
    assert go(one, "act_as")["name"] == "eng1"
    go(one, "signal", task_id="eng1-root", signal="ACCEPT")
    e.wait_idle()
    accepted = [a for a in e.audit_log(TaskId("eng1-root")) if a.signal == Signal.ACCEPT and not a.rejected]
    assert [str(a.source) for a in accepted] == ["eng1"] and accepted[0].via.startswith("as:"), accepted
    # …recorded: who took which name when (Thm 11)
    assert signin._held("SELECT name, person, via FROM holds WHERE lease = ?", signin._hash(one)) == \
        [("eng1", "local", "claim")]


def test_a_second_connection_is_refused_the_name_a_live_one_holds(go, monkeypatch):
    e, go = go
    _stream(e, go, "eng2")
    one, two = _lease(), _lease()
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [one, two])
    assert go(one, "act_as", name="eng2")["name"] == "eng2"
    out = go(two, "act_as", name="eng2")
    assert out.get("refused") and "held by another connection" in out["error"] and "§2.6" in out["error"], out
    assert go(two, "act_as")["signs_as"] == []


def test_a_name_whose_holder_is_gone_passes_and_the_old_connection_signs_as_no_one(go, monkeypatch):
    e, go = go
    _stream(e, go, "eng3")
    one, two = _lease(), _lease()
    assert go(one, "act_as", name="eng3")["name"] == "eng3"
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [two])          # …its bridge's lease lapsed
    assert go(two, "act_as", name="eng3")["name"] == "eng3"
    back = go(one, "act_as")
    assert back["kind"] == "none" and "another connection took it" in back["lift"], back    # never the person


def test_a_connection_logs_in_again_under_another_name_and_the_first_is_freed(go):
    """The agent erred and the person tells it to change: the same door, another name (the author, 2026-11-21).
    CONTROL: one name for a connection's life — the re-log-in refused."""
    e, go = go
    _stream(e, go, "eng4")
    signin.issue("ui4")                 # …a name issued to him is his to take as well
    one = _lease()
    assert go(one, "act_as", name="ui4")["name"] == "ui4"          # …a name owing nothing: free to leave
    assert go(one, "act_as", name="eng4")["signs_as"] == ["eng4"]
    assert go(one, "act_as")["name"] == "eng4"
    assert go(_lease(), "act_as", name="ui4")["name"] == "ui4", "the first name stayed held"


@pytest.mark.parametrize("name, why", [("nobody-assigned-me", "not a name of yours"), ("agent", "reserved"),
                                       ("x-exec-1", "the system's")])
def test_a_name_the_person_did_not_issue_is_refused(go, name, why):
    _, go = go
    out = go(_lease(), "act_as", name=name)
    assert out.get("refused") and why in out["error"], out


def test_under_protected_the_claim_is_refused_and_the_names_token_takes_it(go, monkeypatch):
    e, go = go
    _stream(e, go, "eng5")
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    one = _lease()
    out = go(one, "act_as", name="eng5")
    assert out.get("refused") and "--protected" in out["error"], out
    out = go(one, "act_as", name="eng5", token=signin.issue("other5")[1])
    assert out.get("refused") and "does not sign as `eng5`" in out["error"], out
    assert go(one, "act_as", name="eng5", token=signin.issue("eng5")[1])["name"] == "eng5"
    his = _lease()
    assert go(his, "act_as", name="user").get("refused"), "his name claimed under --protected"
    assert go(his, "act_as", name="user", token=signin.issue("user")[1])["signs_as"] == ["user"]


def test_the_bridge_names_its_lease_on_every_leg(monkeypatch):
    """The relay sends this process's lease, so a rebuilt leg is the same connection."""
    seen = []
    srv = FastMCP("echo", host="127.0.0.1", port=0)

    @srv.tool()
    async def who(ctx: Context) -> str:
        seen.append(ctx.request_context.request.headers.get(config.LEASE_HEADER))
        return "ok"
    web, url = P._serve(srv.streamable_http_app())

    async def once():
        to_bridge, from_client = anyio.create_memory_object_stream(16)
        to_client, from_bridge = anyio.create_memory_object_stream(16)
        async with anyio.create_task_group() as tg:
            tg.start_soon(C._relay, url, from_client, to_client)
            async with ClientSession(from_bridge, to_bridge) as session:
                await session.initialize()
                await session.call_tool("who")
            tg.cancel_scope.cancel()
    try:
        anyio.run(once)
        anyio.run(once)
    finally:
        web.should_exit = True
    assert seen == [C.LEASE, C.LEASE] and len(C.LEASE) == 32


def test_a_claim_stranded_by_protected_is_mended_by_the_names_token(go, monkeypatch):
    e, go = go
    _stream(e, go, "eng6")
    one = _lease()
    assert go(one, "act_as", name="eng6")["name"] == "eng6"
    monkeypatch.setenv("GFSO_PAGE_AUTH", "key")
    assert go(one, "act_as")["kind"] == "none"
    assert go(one, "act_as", name="eng6", token=signin.issue("eng6")[1])["name"] == "eng6"


def test_a_server_just_up_counts_every_holding_live(go, monkeypatch):
    """After a restart the holdings survive and no bridge has beaten yet: none reads lapsed for one lease grace."""
    e, go = go
    _stream(e, go, "engR")
    one, two = _lease(), _lease()
    assert go(one, "act_as", name="engR")["name"] == "engR"
    monkeypatch.setattr(signin, "LIVE_LEASES", None)
    create_app(make_engine())               # …a server restarted: its lease list is empty
    out = go(two, "act_as", name="engR")
    assert out.get("refused") and "held by another connection" in out["error"], out
    assert go(one, "act_as")["name"] == "engR"


def test_a_gfso_call_from_the_consoles_shell_signs_as_its_connections_name(go, tmp_path):
    """One console is one Del: its shell's `gfso` finds its bridge by the parent chain and signs as the name taken."""
    e, go = go
    _stream(e, go, "eng7")
    one = _lease()
    assert go(one, "act_as", name="eng7")["name"] == "eng7"
    signin.record_console(one, console=psutil.Process())     # …as a bridge does, here under this very process
    try:
        probe = "from gfso import signin; p = signin.local_principal(); print(p.name, p.via)"
        out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=os.environ, timeout=60)
        assert out.stdout.split()[0] == "eng7" and out.stdout.split()[1].startswith("as:"), out
    finally:
        signin.forget_console(one)
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=os.environ, timeout=60)
    assert out.stdout.split()[0] == "user", out


_PROBE = "from gfso import signin; print(signin.console_lease())"


def _from_a_child() -> str:
    return subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True, env=os.environ,
                          timeout=60).stdout.strip()


def test_a_console_started_inside_another_is_its_own_the_nearest_record_wins():
    """A `claude` started from a console's shell: its shell's call is the inner console's, never the outer stream's."""
    outer, inner = _lease(), _lease()
    signin.record_console(outer, console=psutil.Process().parent())
    signin.record_console(inner, console=psutil.Process())
    try:
        assert _from_a_child() == inner
    finally:
        signin.forget_console(outer)
        signin.forget_console(inner)


def test_the_record_of_a_bridge_that_is_gone_is_dropped_not_read():
    """A bridge killed past its own cleanup leaves its record: its console's shell signs as no stream of it."""
    dead = _lease()
    gone = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        signin.record_console(dead, bridge=psutil.Process(gone.pid), console=psutil.Process())
    finally:
        gone.kill()
        gone.wait()
    assert list(signin._consoles().glob("*.json")), "recorded"
    assert _from_a_child() == "None"
    assert not (signin._consoles() / f"{signin._hash(dead)[:16]}.json").exists()
