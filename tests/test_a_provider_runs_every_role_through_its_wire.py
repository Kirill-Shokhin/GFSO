"""Any chat API that speaks the OpenAI-compatible wire runs every role on gfso: one-shots, structured answers, and agent
runs with the system's six work tools in a place of their own — and a model spec `provider/model` picks it per role.

Against a scripted local server that speaks the wire (no provider is installed or called): each test hands it the
replies a model would give and reads what the provider did with them."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from gfso.adapters.execution import LocalExecution
from gfso.adapters.llm import registry
from gfso.adapters.llm import chat
from gfso.adapters.llm.chat import ChatProvider, OpenAIWire, answers
from gfso.adapters.llm.conformance import assess
from gfso.adapters.llm.headless import ClaudeCodeProvider
from gfso.adapters.llm.stats import refused_by_limit
from gfso.adapters.llm.toolloop import transcript_path
from gfso.core.types import PlaceUnavailable
from gfso.llm import llm_factory
from tests.support import make_engine


class _Script(list):
    """The replies to POSTs, in order; `gets` the answers to GETs by path."""
    def __init__(self):
        super().__init__()
        self.gets = {}


@pytest.fixture()
def wire_server():
    """A /v1/chat/completions server answering from a script: each reply a dict (a message, or `{"status": 429}`), or a
    function of the request body."""
    script, seen = _Script(), []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if not self.path.endswith("/chat/completions"):      # another server's dialect (`/api/show`): not here
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            seen.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization")})
            r = script.pop(0) if script else {"content": "(script ran out)"}
            r = r(body) if callable(r) else r
            if "status" in r:
                data = json.dumps({"error": r.get("error", "refused")}).encode()
                self.send_response(r["status"])
                for k, v in r.get("headers", {}).items():
                    self.send_header(k, v)
            else:
                msg = {"role": "assistant", "content": r.get("content")}
                if r.get("tools"):
                    msg["tool_calls"] = [{"id": f"c{i}", "type": "function",
                                          "function": {"name": n, "arguments": json.dumps(a)}}
                                         for i, (n, a) in enumerate(r["tools"])]
                data = json.dumps({"model": "served-model", "choices": [{"message": msg, "finish_reason":
                                   r.get("finish", "tool_calls" if r.get("tools") else "stop")}],
                                   "usage": {"prompt_tokens": r.get("prompt", 100), "completion_tokens": 10,
                                             "prompt_tokens_details": {"cached_tokens": r.get("cached", 40)}}}).encode()
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):                      # /models and the servers' own reads of a model's window
            data = json.dumps(script.gets.get(self.path, {"data": []})).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", script, seen
    finally:
        server.shutdown()


@pytest.fixture(autouse=True)
def _no_waits(monkeypatch):
    monkeypatch.setattr(chat, "RETRY_DELAYS_S", (0, 0, 0))


def provider(url, **kw):
    return ChatProvider(OpenAIWire(url, "m", **kw), "m")


# ── the spec picks the provider ────────────────────────────────────────────────────────────────────────────────


def test_an_unprefixed_id_is_claude_through_its_cli(monkeypatch):
    monkeypatch.delenv("GFSO_PROVIDER", raising=False)
    assert isinstance(llm_factory("claude-haiku-4-5"), ClaudeCodeProvider)
    assert isinstance(llm_factory("claude/claude-haiku-4-5"), ClaudeCodeProvider)


def test_a_local_preset_needs_no_key_and_bills_nothing(wire_server, monkeypatch):
    url, script, seen = wire_server
    monkeypatch.setenv("GFSO_PROVIDER_OLLAMA_BASE_URL", url)
    llm = llm_factory("ollama/qwen3:32b")
    assert isinstance(llm, ChatProvider) and llm.runs_agents
    script.append({"content": "pong"})
    assert llm.complete("ping") == "pong"
    assert seen[-1]["body"]["model"] == "qwen3:32b" and seen[-1]["auth"] is None
    assert llm.calls[-1]["cost_usd"] == 0.0                     # local: no bill, said as 0 by the preset


def test_a_remote_preset_reads_its_key_and_refuses_without_one(wire_server, monkeypatch):
    url, script, seen = wire_server
    monkeypatch.setenv("GFSO_PROVIDER_DEEPSEEK_BASE_URL", url)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    keyless = llm_factory("deepseek/deepseek-chat")            # built: every call is the account's refusal, a stop
    assert keyless.complete("hi") == "" and keyless.calls[-1]["ended"] == "unauthorized"
    assert "DEEPSEEK_API_KEY" in keyless.calls[-1]["error"] and not seen   # nothing was sent anywhere
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k1")
    script.append({"content": "ok"})
    llm = llm_factory("deepseek/deepseek-chat")
    llm.complete("hi")
    assert seen[-1]["auth"] == "Bearer k1"
    assert llm.calls[-1]["cost_usd"] is None                    # no tariff declared: not reported, never 0


def test_a_users_own_provider_is_an_environment_entry(wire_server, monkeypatch):
    url, script, _ = wire_server
    monkeypatch.setenv("GFSO_PROVIDER_MYBOX_BASE_URL", url)
    monkeypatch.setenv("GFSO_PROVIDER_MYBOX_PRICE", "1,2")
    assert "mybox" in registry.names()
    script.append({"content": "ok", "prompt": 1_000_000, "cached": 0})
    llm = llm_factory("mybox/anything")
    llm.complete("hi")
    assert llm.calls[-1]["cost_usd"] == pytest.approx(1 + 10 * 2 / 1e6)   # the declared tariff, per million


def test_a_third_partys_class_plugs_in_by_entry_point(monkeypatch):
    made = []

    class EP:
        name = "acme"

        def load(self):
            return lambda model, execution: made.append(model) or "acme-provider"

    monkeypatch.setattr(registry, "_plugins", lambda: {"acme": EP()})
    assert llm_factory("acme/big-model") == "acme-provider" and made == ["big-model"]


def test_an_openrouter_id_keeps_its_own_slash():
    assert registry.split("openrouter/deepseek/deepseek-chat") == ("openrouter", "deepseek/deepseek-chat")


def test_the_generic_lever_still_swings_every_unprefixed_id(wire_server, monkeypatch):
    url, script, seen = wire_server
    monkeypatch.setenv("GFSO_PROVIDER", "generic")
    monkeypatch.setenv("GFSO_GENERIC_BASE_URL", url)
    monkeypatch.setenv("GFSO_GENERIC_MODEL", "fake-model")
    llm = llm_factory("sonnet")
    script.append({"content": '```json\n{"echo": "ok"}\n```'})
    assert llm.complete_structured("s", "u", {"type": "object", "properties": {"echo": {"type": "string"}},
                                              "required": ["echo"]}) == {"echo": "ok"}
    assert seen[-1]["body"]["model"] == "fake-model"


# ── the record ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_a_call_record_splits_the_cached_input_out(wire_server):
    url, script, _ = wire_server
    llm = provider(url)
    script.append({"content": "x", "prompt": 100, "cached": 40})
    llm.complete("hi")
    c = llm.calls[-1]
    assert (c["input_tokens"], c["cache_read_input_tokens"], c["output_tokens"]) == (60, 40, 10)
    assert c["model"] == "served-model" and c["ended"] == "answered"


def test_a_rate_limit_stops_like_the_accounts(wire_server):
    url, script, _ = wire_server
    llm = provider(url)
    script.append({"status": 429, "headers": {"Retry-After": "3600"}})      # long: a stop, not a wait
    assert llm.complete("hi") == ""
    c = llm.calls[-1]
    assert c["ended"] == "limit" and c["limit_resets_at"] and refused_by_limit(llm.calls)


def test_nothing_answering_at_the_address_is_the_place_down():
    llm = provider("http://127.0.0.1:9/v1")
    assert llm.complete("hi") == ""
    assert llm.calls[-1]["ended"] == "unavailable" and llm.calls[-1]["place"] == "http://127.0.0.1:9/v1"


def test_a_cut_at_the_output_limit_asks_again_shorter(wire_server):
    url, script, seen = wire_server
    llm = provider(url)
    script += [{"content": '```json\n{"a": ', "finish": "length"}, {"content": '```json\n{"a": 1}\n```'}]
    assert llm.complete_structured("s", "u", {"type": "object", "required": ["a"]}) == {"a": 1}
    assert "SHORTER" in seen[-1]["body"]["messages"][-1]["content"]


# ── the agent run ──────────────────────────────────────────────────────────────────────────────────────────────


def test_an_agent_run_writes_runs_and_reads_in_its_place(wire_server, tmp_path):
    url, script, seen = wire_server
    llm = provider(url)
    script += [{"tools": [("Write", {"file_path": "a.txt", "content": "41\n"})]},
               {"tools": [("Bash", {"command": "cat a.txt"})]},
               {"tools": [("Read", {"file_path": str(tmp_path / "a.txt")})]},
               {"content": "done: 41"}]
    out = llm.run_agent("sys", "do it", ("Read", "Write", "Bash"), cwd=str(tmp_path))
    assert out == "done: 41" and (tmp_path / "a.txt").read_text() == "41\n"
    tool_msgs = [m for m in seen[-1]["body"]["messages"] if m["role"] == "tool"]
    assert "41" in tool_msgs[1]["content"] and "[exit code 0]" in tool_msgs[1]["content"]
    assert "1\t41" in tool_msgs[2]["content"].replace(" ", "")
    assert llm.last_tool_calls == {"Write": 1, "Bash": 1, "Read": 1}       # the vocabulary the invariants read
    c = llm.calls[-1]
    assert c["turns"] == 4 and c["peak_context"] == 100 and c["ended"] == "answered"
    assert [x["function"]["name"] for x in seen[0]["body"]["tools"]] == ["Read", "Write", "Bash"]   # what the role offers


class _Scratched(LocalExecution):
    def __init__(self, root):
        self.root = root

    def temp_root(self):
        return str(self.root)


def test_a_run_reads_its_place_and_scratch_and_writes_only_its_place(wire_server, tmp_path):
    url, script, seen = wire_server
    for d in ("place", "scratch"):
        (tmp_path / d).mkdir()
    (tmp_path / "neighbour.txt").write_text("theirs")
    (tmp_path / "scratch" / "inputs.txt").write_text("given")
    script += [{"tools": [("Read", {"file_path": str(tmp_path / "neighbour.txt")}),
                          ("Read", {"file_path": str(tmp_path / "scratch" / "inputs.txt")}),
                          ("Write", {"file_path": str(tmp_path / "scratch" / "out.txt"), "content": "x"})]},
               {"content": "ok"}]
    ChatProvider(OpenAIWire(url, "m"), "m", execution=_Scratched(tmp_path / "scratch")).run_agent(
        "s", "u", ("Read", "Write"), cwd=str(tmp_path / "place"))
    said = [m["content"] for m in seen[-1]["body"]["messages"] if m["role"] == "tool"]
    assert "outside this run's place" in said[0] and "theirs" not in said[0]
    assert "given" in said[1]
    assert "writes only there" in said[2] and not (tmp_path / "scratch" / "out.txt").exists()


def test_a_tool_the_role_does_not_offer_is_not_run(wire_server, tmp_path):
    url, script, seen = wire_server
    script += [{"tools": [("Write", {"file_path": "x", "content": "y"})]}, {"content": "ok"}]
    provider(url).run_agent("s", "u", ("Read", "Bash", "Glob", "Grep"), cwd=str(tmp_path))
    assert not (tmp_path / "x").exists()


def test_a_round_cut_at_its_turn_cap_continues_and_no_other_does(wire_server, tmp_path):
    url, script, seen = wire_server
    llm = provider(url)
    script += [{"tools": [("Bash", {"command": "echo 1"})]}] * 2
    assert llm.run_agent("s", "first", ("Bash",), cwd=str(tmp_path), max_turns=2, session="s1") == ""
    assert llm.calls[-1]["stop_reason"] == "max_turns" and transcript_path(llm.execution, "s1").is_file()
    script.append({"content": "finished"})
    assert llm.run_agent("s", "go on", ("Bash",), cwd=str(tmp_path), max_turns=2, session="s1") == "finished"
    assert llm.calls[-1]["resumed"] is True
    sent = [m["content"] for m in seen[-1]["body"]["messages"] if m["role"] == "user"]
    assert sent == ["first", "go on"]                                    # the same conversation, continued
    assert not transcript_path(llm.execution, "s1").exists()                 # answered: the conversation ends


def test_old_outputs_are_elided_when_the_context_nears_the_window(wire_server, tmp_path):
    url, script, seen = wire_server
    llm = provider(url, context_window=1000)
    script += [{"tools": [("Bash", {"command": f"echo out{i}"})], "prompt": 700} for i in range(9)]
    script.append({"content": "ok"})
    llm.run_agent("s", "u", ("Bash",), cwd=str(tmp_path))
    tools = [m["content"] for m in seen[-1]["body"]["messages"] if m["role"] == "tool"]
    assert sum("elided" in t for t in tools) == len(tools) - 6 and "out8" in tools[-1]


def test_the_battery_names_the_roles_a_provider_can_hold(wire_server, tmp_path):
    url, script, _ = wire_server

    def agent(body):
        n = sum(1 for m in body["messages"] if m["role"] == "tool")
        if "probe.txt" in body["messages"][1]["content"]:
            return [{"tools": [("Write", {"file_path": "probe.txt", "content": "41"})]},
                    {"tools": [("Bash", {"command": "expr $(cat probe.txt) + 1"})]}, {"content": "42"}][n]
        assert "executor" in body["messages"][0]["content"].lower()       # the real executor prompt
        return [{"tools": [("Write", {"file_path": "sum.py", "content": "print(sum(range(1, 101)))\n"})]},
                {"tools": [("Bash", {"command": "python sum.py"})]},
                {"content": '```json\n{"status": "delivered", "printed": "5050"}\n```'}][n]

    script += [{"content": "pong"}, {"content": '```json\n{"answer": 5}\n```'}] + [agent] * 6
    found = assess(provider(url), "You are the EXECUTOR of a node.")
    assert all(c["pass"] for c in found["checks"].values()), found
    assert found["roles"] == ["decompose", "review", "issuer", "executor", "validator", "contact"]
    assert found["optional"]["cache split"] and not found["optional"]["window"]
    assert found["warnings"] and "OLLAMA_CONTEXT_LENGTH" in found["warnings"][0]


def test_the_window_is_asked_of_the_server(wire_server):
    url, script, _ = wire_server
    script.gets["/api/ps"] = {"models": [{"name": "m:latest", "context_length": 8192}]}
    wire = OpenAIWire(url, "m")
    assert wire.discover_window() == 8192 and wire.context_window == 8192
    del script.gets["/api/ps"]
    script.gets["/v1/models"] = {"data": [{"id": "m", "max_model_len": 32768}]}
    assert OpenAIWire(url, "m").discover_window() == 32768


def test_a_refused_key_is_the_account_refused(wire_server):
    url, script, _ = wire_server
    llm = provider(url)
    script.append({"status": 401})
    assert llm.complete("hi") == ""
    assert llm.calls[-1]["ended"] == "unauthorized" and refused_by_limit(llm.calls)


# ── what the CLI does and a loop of our own must too (critic over the factory, 2026-10-27) ─────────────────────


def test_what_passes_by_itself_is_waited_out(wire_server):
    url, script, seen = wire_server
    script += [{"status": 503}, {"status": 429}, {"content": "after the storm"}]
    assert provider(url).complete("hi") == "after the storm" and len(seen) == 3


def test_a_server_busy_past_its_retries_is_a_cut_call_not_an_answer(wire_server, tmp_path):
    url, script, _ = wire_server
    llm = provider(url)
    script += [{"tools": [("Bash", {"command": "echo 1"})]}] + [{"status": 502}] * 4
    assert llm.run_agent("s", "u", ("Bash",), cwd=str(tmp_path)) == ""
    assert llm.calls[-1]["ended"] == "cut" and llm.calls[-1]["transport_torn"] is True


def test_an_absolute_pattern_and_a_climbing_one_stay_in_the_place(wire_server, tmp_path):
    url, script, seen = wire_server
    for d in ("place", "scratch"):
        (tmp_path / d).mkdir()
    place = tmp_path / "place"
    (place / "a.py").write_text("x = 1\n")
    (tmp_path / "outside.py").write_text("secret = 1\n")
    script += [{"tools": [("Glob", {"pattern": str(place / "*.py")}),
                          ("Grep", {"pattern": "secret", "glob": "../*", "output_mode": "content"})]}, {"content": "ok"}]
    ChatProvider(OpenAIWire(url, "m"), "m", execution=_Scratched(tmp_path / "scratch")).run_agent(
        "s", "u", ("Glob", "Grep"), cwd=str(place))
    said = [m["content"] for m in seen[-1]["body"]["messages"] if m["role"] == "tool"]
    assert "a.py" in said[0] and "secret" not in said[1]


def test_a_node_place_reads_its_base(wire_server, tmp_path):
    url, script, seen = wire_server
    (base := tmp_path / "ws").mkdir()
    (base / "data.csv").write_text("a,b\n")
    (place := tmp_path / ".gfso-nodes-ws" / "proj" / "root.a").mkdir(parents=True)
    script += [{"tools": [("Read", {"file_path": str(base / "data.csv")}),
                          ("Write", {"file_path": str(base / "x.txt"), "content": "no"})]}, {"content": "ok"}]
    provider(url).run_agent("s", "u", ("Read", "Write"), cwd=str(place))
    said = [m["content"] for m in seen[-1]["body"]["messages"] if m["role"] == "tool"]
    assert "a,b" in said[0] and "writes only there" in said[1] and not (base / "x.txt").exists()


def test_a_command_gets_only_the_time_the_run_has_left(wire_server, tmp_path):
    url, script, _ = wire_server
    script += [{"tools": [("Bash", {"command": "python -c \"import time; time.sleep(8)\""})]}, {"content": "ok"}]
    t0 = time.monotonic()
    provider(url).run_agent("s", "u", ("Bash",), cwd=str(tmp_path), timeout=3)
    assert time.monotonic() - t0 < 7


class _Down(LocalExecution):
    def run(self, args, *, cwd, timeout, env=None):
        raise PlaceUnavailable("e3-linux", "docker does not answer")


def test_a_place_down_inside_a_command_ends_the_run_and_stops(wire_server, tmp_path):
    url, script, _ = wire_server
    script += [{"tools": [("Bash", {"command": "make"})]}, {"content": '{"status": "delivered"}'}]
    llm = ChatProvider(OpenAIWire(url, "m"), "m", execution=_Down())
    assert llm.run_agent("s", "u", ("Bash",), cwd=str(tmp_path)) == ""
    assert llm.calls[-1]["ended"] == "unavailable" and llm.calls[-1]["place"] == "e3-linux"


def test_an_edit_keeps_a_files_line_endings(wire_server, tmp_path):
    url, script, _ = wire_server
    (tmp_path / "f.txt").write_bytes(b"a\r\nb\r\nc\r\n")
    script += [{"tools": [("Edit", {"file_path": "f.txt", "old_string": "a\nb", "new_string": "a\nB"})]},
               {"content": "ok"}]
    provider(url).run_agent("s", "u", ("Edit",), cwd=str(tmp_path))
    assert (tmp_path / "f.txt").read_bytes() == b"a\r\nB\r\nc\r\n"


def test_a_run_cut_at_its_cap_reads_as_out_of_turns(wire_server, tmp_path):
    url, script, _ = wire_server
    llm = provider(url)
    script += [{"tools": [("Bash", {"command": "echo 1"})]}]
    llm.run_agent("s", "u", ("Bash",), cwd=str(tmp_path), max_turns=1)
    assert llm.calls[-1]["ended"] == "max_turns"


def test_a_model_server_down_is_lifted_only_when_it_answers(wire_server):
    url, _, _ = wire_server
    assert answers(url) is None and answers("http://127.0.0.1:9/v1")
    e = make_engine(llm=None)
    e.probe_the_place_with(lambda place: answers(place) if place.startswith("http") else None)
    e.stop_for_the_place("http://127.0.0.1:9/v1", "nothing answers")
    e.lift_the_system_stop(time.time())
    assert e.paused(), "lifted while the model server was still down"
    e.stop_for_the_place(url, "it came back")
    e.lift_the_system_stop(time.time())
    assert e.paused() is None


def test_an_agents_shell_holds_no_key_and_no_server_mark(monkeypatch, wire_server, tmp_path):
    url, script, seen = wire_server
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k-secret")
    monkeypatch.setenv("GFSO_SERVING", "1")
    script += [{"tools": [("Bash", {"command": "env"})]}, {"content": "ok"}]
    provider(url).run_agent("s", "u", ("Bash",), cwd=str(tmp_path))
    said = [m["content"] for m in seen[-1]["body"]["messages"] if m["role"] == "tool"][0]
    assert "k-secret" not in said and "GFSO_SERVING" not in said


def test_out_of_credit_is_the_accounts_stop(wire_server):
    url, script, _ = wire_server
    llm = provider(url)
    script.append({"status": 402, "error": "Insufficient Balance"})
    assert llm.complete("hi") == "" and llm.calls[-1]["ended"] == "limit" and refused_by_limit(llm.calls)


def test_a_malformed_call_is_not_counted_as_run(wire_server, tmp_path):
    url, script, _ = wire_server
    llm = provider(url)
    bad = {"tools": [("Bash", {"command": "x"})]}
    script += [lambda body: {**bad}, {"content": "ok"}]
    llm.run_agent("s", "u", ("Read",), cwd=str(tmp_path))         # Bash not offered: refused, not counted
    assert llm.last_tool_calls == {}


def test_a_place_down_mid_command_keeps_a_conversation_the_next_round_can_send(wire_server, tmp_path):
    """A chat server refuses a conversation leaving a tool call unanswered: the round cut by the place going down keeps
    its transcript with every call answered, or the next round died on an HTTP 400 as an unparsed report."""
    url, script, _ = wire_server
    script += [{"tools": [("Bash", {"command": "make"}), ("Bash", {"command": "make test"})]}]
    llm = ChatProvider(OpenAIWire(url, "m"), "m", execution=_Down())
    sid = f"down-{tmp_path.name}"                          # kept by the session's name, outside the run's place
    assert llm.run_agent("s", "u", ("Bash",), cwd=str(tmp_path), session=sid) == ""
    kept = transcript_path(llm.execution, sid)
    msgs = json.loads(kept.read_text(encoding="utf-8"))
    kept.unlink()
    asked = {c["id"] for m in msgs if m["role"] == "assistant" for c in m.get("tool_calls") or ()}
    assert asked and asked == {m["tool_call_id"] for m in msgs if m["role"] == "tool"}, msgs


def test_a_window_listed_only_once_the_model_is_loaded_is_learned_after_its_first_turn(wire_server, tmp_path):
    """Ollama lists a model's window only while it is loaded: a session opened on a cold model learned none, and the
    budget then assumed a window the server truncates below — silently, the packet first."""
    url, script, _ = wire_server
    def loads(body):
        script.gets["/api/ps"] = {"models": [{"name": "m:latest", "context_length": 32768}]}
        return {"content": "done"}
    script += [loads]
    llm = provider(url)
    assert llm.run_agent("s", "u", ("Read",), cwd=str(tmp_path)) == "done"
    assert llm.calls[-1]["context_window"] == 32768


def test_llama_cpps_overflow_is_read_as_one(wire_server, tmp_path):
    url, script, _ = wire_server
    script += [{"status": 400, "error": {"message": "the request exceeds the available context size",
                                         "type": "exceed_context_size_error"}}, {"content": "done"}]
    assert provider(url).run_agent("s", "u", ("Read",), cwd=str(tmp_path)) == "done"


def test_a_reasoning_models_inline_thinking_is_not_its_answer(wire_server):
    """A draft verdict in the thinking won the parse over the final one: a path to a false PASS on the validator."""
    url, script, _ = wire_server
    script += [{"content": '<think>draft: {"verdict": "PASS"}\nbut test 3 printed 41</think>\n{"verdict": "FAIL"}'}]
    t = OpenAIWire(url, "m").turn([{"role": "user", "content": "judge"}], [], timeout=10)
    assert t.text == '{"verdict": "FAIL"}' and "<think>" not in t.raw_assistant["content"]
