"""The page a human is pointed at is actually served — proven by request, not by packaging.

The UI is how a non-agent watches the graph ("trust, but see" — the third mode of the control
dilemma), and it is the only door in the product that no test had ever opened. It was covered
sideways — `test_packaging`/`test_distribution` prove the files ship, and `test_canon_check_map`
reads `index.html` off disk as text — and neither of those is a request. A page that ships and 404s
is shipped and broken, and the first person to find out would be the stranger the whole install
path exists for.

What is asserted is the door, not the design: the page comes back, it is HTML, and the assets it
names come back too and are CSS — a stylesheet served as `text/plain` or missing leaves the viewer
staring at unstyled markup, which is exactly the "raw dump is unreadable" complaint the UI was
rebuilt to answer.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso.adapters.storage.memory import MemoryStorage
from gfso.api.server import create_app
from gfso.engine import Engine
from gfso.engine.validation import l2_gate_on
from gfso.runtime import ProjectRegistry
from gfso.tools_llm import validate_internal_on
from tests.test_integration import _engine


@pytest.fixture()
def client():
    with TestClient(create_app(_engine())) as c:
        yield c


def test_the_page_itself_is_served(client):
    r = client.get("/")
    assert r.status_code == 200, "the UI root did not answer"
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "<title>GFSO</title>" in body
    # The graph canvas is the page's reason to exist; an empty shell would still be 200.
    assert 'id="graph"' in body or 'id="cy"' in body, "the served page carries no graph container"


@pytest.mark.parametrize("path", ["/gfso.css", "/tokens.css"])
def test_the_stylesheets_the_page_names_are_served_as_css(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"{path} is referenced by the page and not served"
    assert "css" in r.headers["content-type"], f"{path} came back as {r.headers['content-type']}"
    assert r.text.strip(), f"{path} is empty"


def test_the_page_only_names_assets_the_server_serves(client):
    """Every local asset the page references must resolve — a 404 here is a broken page for a
    viewer and invisible to any test that only reads the file."""
    import re
    body = client.get("/").text
    refs = {m for m in re.findall(r'(?:href|src)="(/[^":]*?)"', body)}
    missing = {p for p in refs if client.get(p).status_code != 200}
    assert not missing, f"the page references assets the server does not serve: {sorted(missing)}"


def test_the_link_a_user_is_given_reaches_a_live_graph(client):
    """The link handed to a human carries the project; following it must reach that project's
    graph, not merely a page. The page is one document and selects the project client-side, so the
    door is the pair: the document answers, and the project's graph answers behind it."""
    assert client.get("/?project=demo").status_code == 200
    graph = client.get("/api/graph")
    assert graph.status_code == 200, "the page loads but the graph endpoint behind it does not"
    assert "nodes" in graph.json()


def test_the_http_door_takes_project_where_every_other_argument_goes():
    """One grammar for `project`, on all three doors.

    `gfso run` takes `project=<name>`, `gfso log` took only `--project`, and the HTTP door took it
    only as a query parameter — so a caller who put it in the body, where every other argument of
    the verb goes, had it forwarded to the verb as an unknown keyword and got back a TypeError about
    the verb's signature. Three spellings of one thing, each refusing the others."""
    reg = ProjectRegistry(default_storage="memory", default_llm="stub", seed=False)
    app = create_app(reg.engine(None), with_mcp=False, registry=reg)
    with TestClient(app) as c:
        made = c.post("/api/run/create_task", json={
            "project": "bodyscope", "task_id": "root",
            "spec": {"name": "root", "description": "a goal",
                     "criteria": [{"name": "c1", "description": "the thing"}],
                     "accepted_risks": [{"item": "fixture", "predictability": "extraordinary",
                                         "justification": "accepted", "invalidation_condition": "never"}]},
            "assignee": "agent"})
        assert made.status_code == 200, made.text
        assert made.json()["id"] == "root"
        # …and it landed in THAT project, not in the active one
        got = c.post("/api/run/get_task", json={"project": "bodyscope", "task_id": "root"})
        assert got.json()["id"] == "root"
        stray = c.post("/api/run/get_task", json={"task_id": "root"})
        assert "unknown task" in stray.json()["error"]


def test_a_refusal_over_http_keeps_its_status_and_its_shape():
    """The verbs answer rather than raise, and HTTP still says "no" in its own vocabulary.

    Two things had to be true at once. Agents on MCP and people on the CLI need the refusal as
    DATA — an exception at the MCP boundary is what made an agent stop mid-task. HTTP needs a status
    code, or every refusal reads as a success to anything checking the code alone. And the body must
    be the verb's dict: the old path re-encoded a JSON message inside a JSON envelope, and a person
    got quoted braces to unpick."""
    from fastapi.testclient import TestClient
    from gfso.adapters.agents.human import HumanAgent
    from gfso.adapters.llm.stub import StubLLM
    from gfso.adapters.storage.memory import MemoryStorage
    from gfso.api.server import create_app
    from gfso.engine import Engine

    engine = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    engine.start()
    with TestClient(create_app(engine)) as c:
        made = c.post("/api/run/create_task", json={"task_id": "a", "spec": {"description": "x"},
                                                    "assignee": "dev"})
        assert made.status_code == 200 and made.json()["id"] == "a", made.text
        r = c.post("/api/run/add_dependency", json={"from_id": "a", "to_id": "a"})
        assert r.status_code == 422                       # a cycle: the verb could not act
        body = r.json()
        assert isinstance(body, dict) and "cycle" in body["error"]   # the dict, not a quoted string
        assert "unexpected" not in body                              # a refusal, not a defect
        # …and a verb that DID act and reports a negative outcome is a 200: `signal` reaching the
        # FSM and being told no is a successful call, not a broken request.
        neg = c.post("/api/run/signal", json={"task_id": "a", "signal": "PASS", "source": "dev"})
        assert neg.status_code == 200 and neg.json()["accepted"] is False


def test_the_runtime_panel_reports_the_switches_the_code_actually_obeys(monkeypatch):
    """`/api/runtime` is the measurement arm's only preflight, and it read the environment itself.

    Two dials decide what a run measures: whether the plan gate is enforced, and whether internal
    nodes are independently validated. The panel asked the environment as the SERVER process saw it,
    while the code that obeys them asks at its own point of enforcement — so a declared `true` over a
    mechanism that was not running would let a run record stalling as acceptance, and nothing would
    say otherwise. Asking the enforcement point makes the report and the behaviour inseparable."""
    engine = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    engine.start()
    with TestClient(create_app(engine)) as c:
        monkeypatch.setenv("GFSO_L2_GATE", "0")
        monkeypatch.setenv("GFSO_VALIDATE_INTERNAL", "1")
        rt = c.get("/api/runtime").json()
        assert rt["l2_gate"] is l2_gate_on() is False
        assert rt["validate_internal"] is validate_internal_on() is True

        monkeypatch.setenv("GFSO_L2_GATE", "1")
        monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)
        rt = c.get("/api/runtime").json()
        assert rt["l2_gate"] is True and rt["validate_internal"] is False
