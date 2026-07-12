"""GenericLLM smoke against a LOCAL OpenAI-compatible endpoint — the provider lever is not
fictional (G3): `GFSO_PROVIDER=generic` + the base-URL env swings the WHOLE system to a foreign
chat/completions server, the adapter speaks the real wire format, stats land in the shared
shape, and the structured machinery works over any text-returning provider. Third-party
IMPLEMENTATIONS stay out of scope (N3) — this proves the seam, not a vendor."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


@pytest.fixture()
def fake_openai():
    """A minimal /v1/chat/completions server: 'ping' → 'pong'; anything else → a fenced json
    object (what the structured machinery asks any provider for)."""
    requests: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "body": body})
            user = body["messages"][-1]["content"]
            content = "pong" if "ping" in user else '```json\n{"echo": "ok"}\n```'
            out = {"choices": [{"message": {"role": "assistant", "content": content}}],
                   "usage": {"prompt_tokens": 7, "completion_tokens": 2}}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):  # keep the test output quiet
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", requests
    finally:
        server.shutdown()


def test_provider_lever_swings_the_factory_to_a_foreign_endpoint(fake_openai, monkeypatch):
    base_url, requests = fake_openai
    monkeypatch.setenv("GFSO_PROVIDER", "generic")
    monkeypatch.setenv("GFSO_GENERIC_BASE_URL", base_url)
    monkeypatch.setenv("GFSO_GENERIC_MODEL", "fake-model")
    from gfso.runtime import llm_factory
    from gfso.adapters.llm.generic import GenericLLM

    llm = llm_factory("sonnet")
    assert isinstance(llm, GenericLLM)                      # the ONE switch moved the system

    assert llm.complete("ping") == "pong"                   # real wire roundtrip
    assert requests[-1]["path"].endswith("/chat/completions")
    assert requests[-1]["body"]["model"] == "fake-model"
    assert llm.calls[-1]["input_tokens"] == 7               # stats in the shared shape

    out = llm.complete_structured("sys", "fill the schema", {
        "type": "object", "properties": {"echo": {"type": "string"}}, "required": ["echo"]})
    assert out == {"echo": "ok"}                            # our structured machinery, their text


def test_lever_swings_back_by_removing_the_env(fake_openai, monkeypatch):
    monkeypatch.delenv("GFSO_PROVIDER", raising=False)
    from gfso.runtime import llm_factory
    from gfso.adapters.llm.generic import GenericLLM
    assert not isinstance(llm_factory("sonnet"), GenericLLM)   # default = the Anthropic harness
