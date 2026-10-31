"""The model door (`adapters/door.py`): the one place of a project that holds its provider's credential. A client
inside holds the door's key; the door answers that key alone, and under a closed switch passes the model and nothing
the provider would reach elsewhere for it."""
import gzip
import http.client
import json
import subprocess
import threading

import pytest

from gfso.adapters import door as D
from gfso.adapters import execution as E
from gfso.adapters.execution import PLACEHOLDER, LocalExecution
from gfso.adapters.llm.credentials import Credential
from gfso.adapters.llm.headless import ClaudeCodeProvider, client_env


_IMG = {"type": "image", "source": {"type": "url", "url": "https://example.com/?d=secret"}}


@pytest.mark.parametrize("body, alone", [
    ({"tools": [{"name": "Bash", "input_schema": {"properties": {"url": {"type": "string"}}}}]}, True),
    ({"tools": [{"type": "custom", "name": "Read"}],
      "messages": [{"role": "user", "content": [{"type": "image", "source": {"type": "base64", "data": "x"}}]}]}, True),
    ({"tools": [{"type": "web_search_20250305", "name": "web_search"}]}, False),
    ({"tools": [{"type": "web_browser_20990101", "name": "a_tool_not_yet_named"}]}, False),
    ({"tools": {"type": "custom"}}, False),
    ({"mcp_servers": [{"type": "url", "url": "https://example.com/sse"}]}, False),
    ({"container": "c_1"}, False),
    ({"messages": [{"role": "user", "content": [_IMG]}]}, False),
    ({"messages": [{"role": "user", "content": [{"type": "tool_result", "content": [_IMG]}]}]}, False),
    ([{"messages": []}], False),
])
def test_under_a_closed_switch_only_what_the_model_answers_alone_passes(body, alone):
    """The client's own tools and the content it carries; never a tool the provider runs, a URL it would fetch, an MCP
    server it would call — by kind, not by a list of the provider's tools (critic over the door v2)."""
    assert D.model_alone(json.dumps(body).encode()) is alone
    assert D.model_alone(b"not json") is False


@pytest.fixture
def served(tmp_path):
    log = tmp_path / "door.log"

    def serve(closed: bool):
        s = D._Server(("127.0.0.1", 0), D.handler("127.0.0.1", {"kind": "token", "value": "V", "key": "K"}, str(log),
                                                     closed))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        return s, log
    yield serve


def _ask(s, path="/v1/messages", key="K", body=b"{}", method="POST"):
    c = http.client.HTTPConnection("127.0.0.1", s.server_address[1], timeout=10)
    c.request(method, path, body=body, headers={"authorization": f"Bearer {key}"})
    return c.getresponse().status


def test_a_request_without_the_doors_key_is_refused_and_said(served):
    """Another container on the bridge — another project's session, any other software — spends nothing through it."""
    s, log = served(False)
    assert _ask(s, key="other") == 403
    assert "refused: not this door's key" in log.read_text(encoding="utf-8")
    s.shutdown()


@pytest.mark.parametrize("path, body, method", [
    ("/api/oauth/profile", b"{}", "GET"),
    ("/v1/models", b"", "GET"),
    ("/v1/messages", json.dumps({"tools": [{"type": "web_fetch_20250910", "name": "web_fetch"}]}).encode(), "POST"),
])
def test_under_a_closed_switch_the_door_passes_the_model_alone(served, path, body, method):
    """No way out of its own: a server tool would fetch for the session what the switch shuts (critic over the door)."""
    s, log = served(True)
    assert _ask(s, path, body=body, method=method) == 403
    assert "refused: " in log.read_text(encoding="utf-8")
    s.shutdown()


def test_a_flood_of_refusals_neither_erases_nor_crowds_out_what_was_passed(tmp_path, monkeypatch):
    """Past the cap refusals are dropped, passed requests — spend — still written (critic over the door v2: a rotation
    let free refusals erase the record)."""
    monkeypatch.setattr(D, "LOG_CAP", 100)
    monkeypatch.setattr(D, "_full", [])
    log = tmp_path / "door.log"
    D._say(str(log), "passed first", passed=True)
    for i in range(30):
        D._say(str(log), f"refused {i}")
    D._say(str(log), "passed last", passed=True)
    text = log.read_text(encoding="utf-8")
    assert "passed first" in text and "passed last" in text and "refused 29" not in text and "log is full" in text


def test_the_client_holds_the_doors_key_and_never_the_credential():
    cred = Credential("token", "the-real-token")
    env = client_env(cred, False, ("http://gfso-x-door-abc:8080", PLACEHOLDER + "k"))
    assert "the-real-token" not in json.dumps(env)
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == PLACEHOLDER + "k" and env["ANTHROPIC_BASE_URL"] == "http://gfso-x-door-abc:8080"
    assert env["NO_PROXY"] == "gfso-x-door-abc"
    assert LocalExecution().door(cred, "api.anthropic.com") is None                 # …on the host, as before
    assert client_env(cred, True) == {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1", "CLAUDE_CODE_OAUTH_TOKEN": "the-real-token"}


def test_under_every_switch_the_door_passes_the_models_messages_alone(served):
    """The credential opens the whole account — its files, batches, profile; the door, its model (critic over the door
    v3)."""
    s, log = served(False)
    assert _ask(s, "/v1/files", method="GET") == 403 and _ask(s, "/api/oauth/profile", method="GET") == 403
    assert "refused: not the model's messages" in log.read_text(encoding="utf-8")
    s.shutdown()


def test_what_a_models_tool_call_said_is_the_clients_to_run_and_no_fetch():
    asked = {"messages": [{"role": "assistant", "content": [
        {"type": "tool_use", "name": "fetch_it", "input": {"source": {"type": "url", "url": "https://example.com"}}}]}]}
    assert D.model_alone(json.dumps(asked).encode()) is True


@pytest.mark.parametrize("asked", [
    {"type": "tool_use", "messages": [{"role": "user", "content": [_IMG]}]},
    {"messages": [{"role": "user", "type": "tool_use", "content": [_IMG]}]},
    {"messages": [{"role": "assistant", "content": [{"type": "tool_use", "name": "x", "input": {}, "content": [_IMG]}]}]},
])
def test_what_is_typed_a_tool_call_carries_no_fetch_beside_its_input(asked):
    """Only a tool call's `input` is the client's: typing a request, a message or a call so let a URL under it pass a
    closed switch (critic over the door v4)."""
    assert D.model_alone(json.dumps(asked).encode()) is False


def test_a_door_reads_no_body_before_its_key_nor_past_its_cap(served, monkeypatch):
    """Keyless 400 MB bodies, four at once, killed a door read before its key was (critic over the door v4): its body is
    never read, and a keyed one past the cap is refused unread."""
    monkeypatch.setattr(D, "MAX_BODY", 64)
    read = []
    real = D.model_alone
    monkeypatch.setattr(D, "model_alone", lambda b: read.append(b) or real(b))
    s, log = served(True)
    assert _ask(s, key="other", body=b"x" * 1000) == 403 and _ask(s, body=b"{" + b" " * 100 + b"}") == 403
    assert read == []
    text = log.read_text(encoding="utf-8")
    assert "refused: not this door's key" in text and "refused: the body is over its cap" in text
    s.shutdown()


def test_a_place_down_at_its_door_is_the_calls_own_ending(tmp_path, monkeypatch):
    """With a credential the door starts the project first; a Docker that does not answer is the place down — the stop
    a booked call makes — not an exception out of the call (critic over the door v3)."""
    monkeypatch.setattr(E, "run", lambda args, **kw: subprocess.CompletedProcess(args, 1, "", "daemon down"))
    monkeypatch.setattr(E, "_STARTED", {})
    (base := tmp_path / "ws").mkdir()
    ex = E.ContainerExecution("e3-linux", "img", None, str(tmp_path / "state"), str(base), "p")
    llm = ClaudeCodeProvider("haiku", execution=ex, credential=Credential("api", "sk-ant-x"))
    assert llm.run_agent("sys", "packet", ("Read",), cwd=str(base)) == ""
    assert llm.calls[-1]["ended"] == "unavailable"


@pytest.mark.parametrize("closed", [True, False])
def test_no_switch_lets_a_session_read_a_file_the_account_holds(closed):
    """A file the account stores is read by the door's credential for whoever names it: no switch passes one (critic F5).
    A model's own tool call naming one is the client's to run, not the provider's."""
    msg = lambda block: json.dumps({"model": "m", "messages": [{"role": "user", "content": [block]}]}).encode()
    for block in ({"type": "document", "source": {"type": "file", "file_id": "file_abc"}},
                  {"type": "container_upload", "file_id": "file_abc"}):
        assert D.refused(True, "POST", "/v1/messages", msg(block), closed) == "refused: a file the account holds"
    own = {"type": "tool_use", "id": "t", "name": "Read", "input": {"file_id": "x"}}
    assert D.refused(True, "POST", "/v1/messages", msg(own), closed) is None
    assert D.refused(True, "POST", "/v1/messages", msg({"type": "text", "text": "hi"}), closed) is None


@pytest.mark.parametrize("closed", [True, False])
def test_the_door_reads_a_body_one_way_and_passes_a_tools_own_file_parameter(closed):
    """A body the door cannot read as one JSON object — compressed, invalid text, a key given twice — passed unread under
    the open switch, a stored file inside it (critic B6); and a client tool declaring a `file_id` parameter was refused."""
    doc = {"model": "m", "messages": [{"role": "user", "content": [{"type": "document",
                                                                    "source": {"type": "file", "file_id": "f"}}]}]}
    for body in (gzip.compress(json.dumps(doc).encode()), json.dumps(doc).encode().replace(b'"m"', b'"\xff"'),
                 b'{"model": "m", "messages": [], "messages": []}', b"[]"):
        assert D.refused(True, "POST", "/v1/messages", body, closed) == "refused: no JSON object", body[:30]
    tool = {"model": "m", "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"name": "get_doc", "input_schema": {"type": "object", "properties": {"file_id": {"type": "string"}}}}]}
    assert D.refused(True, "POST", "/v1/messages", json.dumps(tool).encode(), closed) is None


@pytest.mark.parametrize("closed", [True, False])
def test_no_switch_lets_a_session_reuse_a_container_the_account_holds(closed):
    """A container named at the top of a request — reused by its id, or carrying the account's custom skills — opens
    what the account stores to whoever names it (critic B7)."""
    for container in ("container_abc", {"skills": [{"type": "custom", "skill_id": "s"}]}):
        body = json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}], "container": container})
        assert D.refused(True, "POST", "/v1/messages", body.encode(), closed) == "refused: a file the account holds"
