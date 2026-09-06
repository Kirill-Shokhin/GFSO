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

import inspect
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gfso.adapters.llm.stub import StubLLM
from gfso.core.graph import DIAGNOSTIC_MEANS, Q_MEANS
from gfso.delegate import _replay_a_standing_verdict
from gfso.core.types import (AgentId, CriterionMapping, RevisionReason, Signal, SignalData, TaskId,
                             Verdict, passed)
from gfso.mcp.connect import USAGE, _argv_answer, main as connect_main
from gfso.tools import (_INDEPENDENCE, PARAM_CHOICES, _is_pure_assent, _self_check_verdict,
                        available_actions,
                        dispute_finding, edit_criteria, get_review, get_verdict, map_criterion,
                        record_verdict,
                        get_dependencies,
                        next_steps,
                        metrics as tool_metrics, reassign, record_verdict)
from gfso.api.server import create_app
from gfso.engine.validation import l2_gate_on
from gfso.runtime import ProjectRegistry
from gfso.tools_llm import validate_internal_on
from tests.support import make_engine, spec
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
    engine = make_engine(llm=StubLLM(), validate_signals=False)
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
    engine = make_engine(llm=StubLLM(), validate_signals=False)
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


def test_the_page_shows_who_judged_a_node_and_on_what(client):
    """The one thing this product promises is that nothing closes on impression.

    The page a person watches said nothing about who judged a node or on what: a tester answering
    "did anything close without proof" had to read `/api/tasks/{id}/verdict` by hand to find
    `by_hand`, `validator` and the per-criterion probe commands (HTTP door, 2026-09-02). This pins
    that the page asks the same question — the fields are the endpoint's, so if either side is
    renamed the other stops answering.
    """
    page = client.get("/").text
    assert "/verdict" in page, "the page reads the execution verdict, not only the plan review"
    for field in ("by_hand", "validator", "per_criterion", "failed_criteria", "refused_report"):
        assert field in page, f"the verdict block does not read `{field}`"
    assert "REFUSED as ⊥" in page, "…and a refused report is not shown as 'not validated'"


def test_the_pages_javascript_parses():
    """Nothing checked that the page is valid JavaScript.

    The UI is one inline script, edited from Python as text, and the tests around it grep for
    substrings — so a broken edit ships a blank page that every other check calls healthy (which is
    exactly how the ORCHESTRATOR file once shipped empty). A parse is the cheapest true statement
    available: it does not say the page WORKS, it says it can run at all.

    Skipped by name where no JS engine exists, rather than passing quietly.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("no JS engine on this machine — the page's syntax is unchecked here")
    html = (Path(__file__).resolve().parent.parent / "gfso" / "web" / "index.html").read_text(encoding="utf-8")
    inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    assert inline, "the page has no inline script — this test is measuring the wrong file"
    js = Path(tempfile.gettempdir()) / "gfso_ui_syntax_check.js"
    js.write_text("\n".join(inline), encoding="utf-8")
    r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, f"the page's script does not parse:\n{r.stderr[:800]}"


def test_the_runtime_panel_reports_the_acceptance_dial(monkeypatch, client):
    """Acceptance is 65–70% of a run's spend on every measurement taken, and one dial decides how
    much of it runs in parallel. A cost measured without it recorded is a cost measured against an
    unknown setting — the same "a role differed by ACCIDENT" defect the model tiers were fixed for,
    one layer down. Read from the owner, like the other two switches.
    """
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "4")
    assert client.get("/api/runtime").json()["validation_batch"] == 4


def test_the_page_says_so_when_its_graph_library_does_not_load(client):
    """A blank page is the worst failure this product can have on a first look.

    The graph library is a remote script and `init()`'s first statement calls it: with the CDN
    unreachable — an offline laptop, a proxy, unpkg down — that throws and NOTHING after it runs,
    including the "connection lost" banner wired further down. The user gets a toolbar over an empty
    page and no error at all (read as a user, 2026-09-02). Vendoring is a separate, parked decision;
    saying so is not.
    """
    page = client.get("/").text
    assert "!window.cytoscape" in page, "the page does not check whether its library arrived"
    assert "The graph library did not load" in page
    assert "gfso status" in page, "…and it names the door that needs no browser at all"


def test_the_page_offers_the_callers_real_identity(client):
    """It shipped a box reading `pm` — an id registered nowhere — so a person's first Pass/Fail was
    signed as a stranger and refused, correctly and uselessly."""
    assert "agent_id" in client.get("/api/runtime").json()
    page = client.get("/").text
    assert "rt.agent_id" in page and "box.value === 'pm'" in page


def test_working_does_not_look_like_dead(client):
    """`EXECUTING` shared the palest style with IDLE and ABANDONED, while an untouched OFFERED node
    was drawn more prominently — the colours answered "what is being worked on" backwards."""
    page = client.get("/").text
    assert "EXECUTING: 'busy'" in page and "busy:" in page
    assert "OFFERED:'Not started'" in page, "`OFFERED` is not 'In Review' — nobody has touched it"


def test_the_numbers_arrive_with_what_they_are_about(client):
    """A metric travels WITH its meaning, and the page keeps no copy of its own.

    Measured 2026-09-02 by looking at the rendered page: the stats bar showed a red `0%` for q_D,
    and the tooltip explaining it was WRONG — the page carried its own table of meanings that had
    drifted from the formulas. It called q_D "joint sufficiency + non-redundancy" (the formula
    counts parents that FAILED their own validation while every child passed) and gave q_Del an
    "iteration overflow" term that appears in no formula at all. The engine already owned this
    prose for the agent door, written because "two independent readers took a true number for a
    defect" — the door where a human reads the number was the one door it never reached.

    So the prose lives beside the computation, is served with the values, and a second writing of
    it anywhere is the defect this pins.
    """
    body = client.get("/api/metrics").json()
    means = body.get("means") or {}
    scores = {k: v for k, v in body.items() if k != "means"}
    assert scores, "the metrics read returned no numbers"
    assert set(means) == set(scores), "a number was served without what it is about"

    # …AND THE DOOR SERVES EVERYTHING THE ENGINE COMPUTES. `false_fail_share` was computed, promised
    # by this endpoint's own docstring, and silently dropped: pydantic ignores what the response
    # model does not declare. It is the one number the canon says to read BESIDE a low q_D (§24.5 —
    # an over-strict validator inflates q_D's numerator), so the door that shows q_D in red was the
    # door that could not answer why. Note the two sets above shrink together when a field is
    # dropped, which is why the comparison against the engine is the assertion that bites.
    assert set(make_engine().metrics()) <= set(scores), (
        "the engine computes a number this door does not serve — pydantic drops what the response "
        "model does not declare, so nothing else would have said so")
    owned = {**Q_MEANS, **DIAGNOSTIC_MEANS}
    for k, text in means.items():
        assert text == owned[k], f"{k}'s served meaning is not the computing module's writing"

    # …AND THE AGENT DOOR SAYS THE SAME. One rule, and both doors serve it, or the writing has
    # simply moved rather than been unified — which is the defect this whole test is about.
    tool = tool_metrics(make_engine())
    assert set(tool.get("means") or {}) == {k for k in tool if k != "means"}, (
        "the agent door serves a number without what it is about")

    page = (Path(__file__).resolve().parents[1] / "gfso" / "web" / "index.html").read_text("utf-8")
    for k in scores:
        assert f"{k} —" not in page, (
            f"the page writes its own definition of {k}; it must render the served `means` "
            f"instead, or this drifts again"
        )


def test_an_untyped_handoff_says_what_it_costs():
    """Delegating to a registered executor must not silently charge the delegation metric.

    Measured 2026-09-02 on a live delegated run: DEL read 25% in red, and the three "defects" were
    the run's own dispatcher handing its three leaves to its three executors — the product's
    headline feature scoring itself as a failure. The count is CORRECT and deliberately
    over-approximate (§24.5: a metric must never improve by leaving the reason out), so the repair
    is at the surface — the act reports its own cost, with the word to use, at the moment it is
    made rather than in help the caller was not reading.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("root"), spec("goal", "c1"), AgentId("worker"))
        e.wait_idle()

        untyped = reassign(e, "root", "other_worker")
        assert "counts_against_q_Del" in untyped, "an untyped Del change did not say what it costs"
        assert "reason='other'" in untyped["counts_against_q_Del"], "it did not name the word to use"

        typed = reassign(e, "root", "worker", reason="other")
        assert "counts_against_q_Del" not in typed, "a typed hand-off must not be lectured"
    finally:
        e.stop()


def test_a_read_does_not_author_the_project_it_names(tmp_path, monkeypatch):
    """A GET may not bring a project into existence, and a typo must say so.

    Measured 2026-09-02: `GET /api/graph?project=<typo>` answered 200 with an empty graph and left
    the project behind. To the person who mistyped, an empty graph under their own project name
    reads as their work having vanished — the worst thing a surface can say, because it is false and
    alarming at once. The registry has owned this rule since 315 projects accumulated out of typos
    (`create=False`), but every read on this door called the resolver with the permissive default,
    so the rule protected the agent door alone. One rule, two doors, and only one of them obeyed it.
    """
    # A REGISTRY-BACKED app, because the project branch does not exist without one. The `/api/usage`
    # 500 earlier the same day hid behind exactly this: the covering test used a registry-less app,
    # so the branch that broke was never executed by anything.
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    reg = ProjectRegistry()
    try:
        with TestClient(create_app(reg.engine(), registry=reg)) as c:
            before = c.get("/api/projects").json()
            missing = "zz_read_must_not_create_zz"

            r = c.get(f"/api/graph?project={missing}")
            assert r.status_code == 404, f"a read of an unknown project answered {r.status_code}"
            assert missing in r.text, "the refusal does not name the project that was not found"

            after = c.get("/api/projects").json()
            assert after == before, "the read created the project it was refusing to read"

            # THE SHAPE THE PAGE READS. The refusal is only worth anything if it reaches the person,
            # and the page renders `detail` from this body; a 404 swallowed into an empty canvas puts
            # the viewer back where the old behaviour left them — staring at nothing under their own
            # project name. The JS cannot be executed from here, so what is pinned is the contract
            # between them: the body carries `detail`, and `detail` names the project.
            body = r.json()
            assert missing in str(body.get("detail", "")), (
                "the 404 body does not carry a `detail` naming the project — the page renders that "
                "field, so without it the refusal never reaches the viewer")
    finally:
        for eng in list(reg._engines.values()):
            eng.stop()


def test_a_call_the_verb_cannot_take_creates_nothing(tmp_path, monkeypatch):
    """A refusal must not leave a project behind — the guard runs BEFORE the side effect.

    Measured 2026-09-02, one level below the read-authors-a-project defect: a malformed
    `create_task` answered 422 and left the project it named behind, because the engine was resolved
    (creating it) before the arguments were checked. The check itself already existed — it lived in
    the TypeError handler around the call, which is after. A caller getting a payload wrong three
    times accumulated three projects, which is the same mechanism that had put 315 of them on this
    installation. A guard that runs after the side effect is not a guard.
    """
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    reg = ProjectRegistry()
    try:
        with TestClient(create_app(reg.engine(), registry=reg)) as c:
            bad = c.post("/api/run/create_task", json={"project": "zz_bad_call", "nonsense": 1})
            assert bad.status_code == 422, "a call the verb cannot take was not refused"
            assert "nonsense" in bad.text, "the refusal does not name the argument it will not take"
            assert c.get("/api/graph?project=zz_bad_call").status_code == 404, (
                "the refused call created the project it was refusing to act on")

            # …and the authoring path still authors, which is what makes the guard a guard rather
            # than a wall: the SAME verb with a payload it takes creates the project as before.
            ok = c.post("/api/run/create_task", json={
                "project": "zz_good_call", "task_id": "root",
                "spec": {"description": "g", "accepted_risks": ["r"],
                         "criteria": [{"name": "c", "description": "c", "check": "c"}]}})
            assert ok.status_code == 200, ok.text
            assert c.get("/api/graph?project=zz_good_call").status_code == 200
    finally:
        for eng in list(reg._engines.values()):
            eng.stop()


def test_a_self_report_is_not_reported_as_an_instruments_work():
    """Three kinds of party produce a verdict, and the read must not collapse the middle one.

    Measured on the MCP door 2026-09-02: `get_verdict` on an internal node that had self-verified
    returned `independence: "produced by the registered instrument named in validator"` while the
    evidence line two rows below it read `SELF-REPORTED by agent — not an independent check`. The
    same record said opposite things about itself, and anything keying on the summary field read a
    self-stamp as an independent check — which is the exact belief this product exists to refuse.

    The distinction was already being drawn correctly by the dispatcher (it had to, to stop REUSING
    a self-report as the independent verdict that lets the instrument be skipped). It is one rule
    with one owner now, and this pins that the read and the dispatcher cannot disagree about a
    record again.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("root"), spec("goal", "c1"), AgentId("worker"))
        e.wait_idle()
        assert e.verdict_provenance(TaskId("root")) == "none", "a node with no verdict is not judged"

        e.record_exec_verdict(TaskId("root"), verdict=Verdict.PASS, failed_criteria=[],
                              validator_id=AgentId("worker"),
                              per_criterion=[{"criterion": "c1", "verdict": "pass",
                                              "evidence": "SELF-REPORTED by worker"}])
        assert e.verdict_provenance(TaskId("root")) == "self", (
            "a verdict signed by the node's own executor is a self-report, not an instrument's work")
        assert "SELF-REPORTED" in _INDEPENDENCE["self"], "the words do not say what the kind is"

        e.record_exec_verdict(TaskId("root"), verdict=Verdict.PASS, failed_criteria=[],
                              validator_id=AgentId("judge"),
                              per_criterion=[{"criterion": "c1", "verdict": "pass",
                                              "evidence": "ran it"}])
        assert e.verdict_provenance(TaskId("root")) == "instrument", (
            "a verdict signed by somebody other than the executor is an independent one")

        # …and every kind the engine can answer has a word for it, or the read renders a KeyError.
        for kind in ("none", "by_hand", "self", "instrument"):
            assert kind in _INDEPENDENCE, f"no wording for provenance {kind!r}"
    finally:
        e.stop()


def test_the_bridge_says_what_it_is_instead_of_hanging():
    """`python -m gfso.mcp.connect --help` must answer, not block on a stdin nobody will write to.

    Measured on the MCP door 2026-09-02: `main` never looked at argv, so `--help` fell straight
    through into the stdio server and waited forever with no output — the process was still alive
    hours later. That is the FIRST command a new user types against the documented entry point, and
    a door that cannot say what it is is indistinguishable from a dead one.

    The answer is a pure function of argv and is given BEFORE any server contact, so asking what
    this is neither costs a round trip nor reconciles anything.
    """
    assert _argv_answer(["prog"]) is None, "no arguments means go and bridge, not print"
    # …AND `main` READS NOTHING BY ITSELF. The first version of this fix took `sys.argv` from the
    # global, so `gfso connect` — the documented entry point, whose argv is `['gfso', 'connect']` —
    # would have seen its own subcommand as an unknown argument and exited 2. Fixing the door by
    # breaking it. The caller passes a command line or there is none to read.
    _sig = inspect.signature(connect_main)
    assert "argv" in _sig.parameters and _sig.parameters["argv"].default is None, (
        "main() must take argv explicitly, defaulting to none — reading the global makes it answer "
        "to whatever command line its caller happened to have")
    for flag in ("-h", "--help", "help"):
        assert _argv_answer(["prog", flag]) == USAGE, f"{flag} did not answer"
    assert "0" in _argv_answer(["prog", "--version"]), "the version answer carries no version"

    unknown = _argv_answer(["prog", "--nonsense"])
    assert "--nonsense" in unknown, "the refusal does not name the argument that was not understood"
    assert USAGE in unknown, "a refusal that does not then say what the thing IS leaves them stuck"

    # It must say the one thing that makes the silence make sense — that this is spoken to, not run.
    assert "stdin" in USAGE and "client" in USAGE, (
        "the usage text does not explain that this is a bridge a client starts, which is the whole "
        "reason running it by hand looks like a hang")


def test_complete_is_a_claim_about_every_root():
    """A forest is not finished because its first tree is.

    Measured on the MCP door 2026-09-02: a second root had been created in the project, and after
    signalling on it the reply still read `COMPLETE — root 'root' is DONE/PASS. Execution finished.`
    while that second root sat mid-flight with work owed on it. The frontier took the FIRST
    parentless node and answered about that one alone. A project is explicitly allowed to be a
    forest, and saying a graph is done while it is not is the single kind of wrong answer this
    product exists to make impossible.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("a"), spec("first goal", "c1"), AgentId("agent"))
        e.assign_task(TaskId("b"), spec("second goal", "c1"), AgentId("agent"))
        e.wait_idle()

        # Close root 'a' for real — accepted, delivered, judged by somebody who is not its executor,
        # then signed. Anything less leaves it in VALIDATING, where NEITHER reading of the rule calls
        # the graph complete and the test passes without touching what it is about.
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("a"),
                                      source=AgentId("agent")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("a"),
                                      source=AgentId("agent"),
                                      result="ran the check for a, it printed OK",
                                      self_validation=Verdict.PASS))
        e.wait_idle()
        e.record_exec_verdict(TaskId("a"), verdict=Verdict.PASS, failed_criteria=[],
                              validator_id=AgentId("judge"),
                              per_criterion=[{"criterion": "c1", "verdict": "pass",
                                              "evidence": "ran it"}])
        e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("a"),
                                      source=AgentId("agent")))
        e.wait_idle()
        assert passed(e.get_task(TaskId("a"))), "the first root did not actually close"
        assert not passed(e.get_task(TaskId("b"))), "the second root must still owe its work"

        out = e._frontier()
        if isinstance(out, dict) and out.get("complete"):
            raise AssertionError(
                f"the graph called itself finished with root 'b' still open: {out['directive']}")
    finally:
        e.stop()


def test_the_instructions_do_not_ask_for_what_the_engine_refuses():
    """What the server TELLS an agent to do must be what the engine accepts.

    Measured on the MCP door 2026-09-02: the shipped instructions said to "put the evidence in the
    DELIVER `self_validation`". A tester did exactly that and was refused — `self_validation` holds
    the WORD (`PASS`/`FAIL`, §14.2) and the evidence belongs in `result`. The refusal message was
    good; the document that sent them into it was the defect, and nothing compared the two.

    So: the engine's own rule about that field is asked here, and the instructions are read for the
    advice that contradicted it.
    """
    assert _self_check_verdict("PASS") == Verdict.PASS
    with pytest.raises(ValueError) as refused:
        _self_check_verdict("Self-check RUN before signalling: pytest 32 passed")
    assert "not a" in str(refused.value), "the refusal does not say what the field is not for"

    doc = (Path(__file__).resolve().parents[1] / "gfso" / "mcp" / "ORCHESTRATOR.md").read_text("utf-8")
    assert "evidence in the DELIVER\n   `self_validation`" not in doc, (
        "the instructions still send the evidence to the verdict field")
    assert "`result`" in doc, "the instructions never say where the evidence actually goes"


def test_an_observation_that_restates_the_verdict_records_nothing():
    """A PASS already says "pass" — an observation that only says it again is ⊥ wearing a mapping.

    Both stranger doors closed a root this way on the same afternoon (2026-09-02), independently,
    and both testers named THIS — not the reviewer's identity — as the step the product stops one
    short of. The engine already refuses a bare PASS on the grounds that a verdict with no check
    behind it is ⊥ (§11.2); `observed={"c1": "ok"}` is the same ⊥ with a shape the check accepted.

    Deliberately narrow, and not authentication: at a loopback door a person names themselves, and
    anyone determined to lie can write a sentence. What this closes is the case where nothing was
    written down at all.
    """
    # The exact strings the two testers used to close a root without evidence.
    for said in ("ok", "looks green", "LGTM.", "all good", "yes", "n/a", ""):
        assert _is_pure_assent(said), f"{said!r} restates the verdict and must not count as observed"
    # AND THE LIMIT, pinned rather than implied. These two also record nothing, and they are NOT
    # caught: separating a short false sentence from a short true one means judging content, and no
    # decidable rule does that. Saying so here keeps a later reader from believing the rule is a
    # guarantee. What remains open is a person choosing to write a false sentence under their name,
    # which is the boundary the human door has always declared (§14.5).
    for prose in ("looked at it, seems right", "dave says it works"):
        assert not _is_pure_assent(prose), (
            f"{prose!r} is now caught — good, but the docstring's stated limit is out of date")
    # …and a real observation, which names what was run and what it showed, must survive untouched.
    for said in ("ran `python -m pytest -q`: 20 passed",
                 "opened writer.py — it yields row by row, never builds a list",
                 "python -c 'from tokenbucket import TokenBucket' printed nothing, exit 0"):
        assert not _is_pure_assent(said), f"{said!r} is an observation and must be accepted"

    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("p"), spec("probe", "c1"), AgentId("agent"))
        e.wait_idle()
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("p"),
                                      source=AgentId("agent")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("p"),
                                      source=AgentId("agent"), result="I did it. Trust me."))
        e.wait_idle()

        refused = record_verdict(e, "p", "PASS", reviewer="dave-from-accounting",
                                 observed={"c1": "ok"})
        assert refused.get("recorded") is False, "the four-command path to a green root still works"
        assert "restates the verdict" in str(refused.get("error")), (
            "the refusal does not say WHY what they wrote is not an observation")

        ok = record_verdict(e, "p", "PASS", reviewer="dave-from-accounting",
                            observed={"c1": "ran `python -m pytest -q` in ./p: 3 passed, 0 failed"})
        assert ok.get("recorded") is True, "a real observation was refused — the rule is a wall"
    finally:
        e.stop()


def test_a_dependency_read_says_which_end_produces():
    """`from`/`to` carry no direction, so the read says which end is which in words.

    Measured on the HTTP door 2026-09-02: a competent tester read `from`/`to` as "waits on" — the
    exact opposite of what they mean — and reported a correctly-wired graph as three dependency
    edges pointing backwards. A probe showed the frontier gating correctly the whole time: given
    `core → tests`, it says `root.tests waits_on ['root.core']`.

    So the finding was refuted and something real was left behind. `add_dependency` explains the
    direction in its own help; the READ, which is where the direction is actually consumed, said
    nothing at all. A convention that has to be remembered is a convention that gets read backwards.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("root"), spec("goal", "c1"), AgentId("agent"))
        e.wait_idle()
        e.decompose_task(TaskId("root"),
                         [(TaskId("root.core"), spec("core", "k1"), AgentId("agent")),
                          (TaskId("root.tests"), spec("tests", "k2"), AgentId("agent"))],
                         criterion_mappings=[CriterionMapping("c1", TaskId("root.core"))])
        e.wait_idle()
        e.add_dependency(TaskId("root.core"), TaskId("root.tests"), glue="tests import core.join()")
        e.wait_idle()

        edge = get_dependencies(e)[0]
        assert edge["producer"] == "root.core" and edge["consumer"] == "root.tests", (
            "the read does not name which end produces and which consumes")
        assert "root.tests waits for root.core" in edge["means"], (
            "the read does not say the direction in words a reader cannot invert")

        # …and the FRONTIER agrees with the words — the half a probe had to establish, asserted on
        # the surface the tester actually quoted rather than on a private helper.
        waiting = {w["task_id"]: w.get("waits_on") or [] for w in (next_steps(e).get("waiting") or [])}
        assert "root.core" in waiting.get("root.tests", []), (
            "the consumer is not waiting for its producer — the gate reads the edge backwards")
        assert "root.tests" not in waiting.get("root.core", []), (
            "the producer is waiting for its consumer — the gate reads the edge backwards")
    finally:
        e.stop()


def test_q_V_says_what_a_reopen_does_to_it():
    """A reopen withdraws a verdict; the number that "means no PASS was taken back" did not move.

    Measured on the HTTP door 2026-09-02: a tester reopened two nodes, was told each time that "that
    verdict is GONE", saw `q_V` stay at 1.0, and reported the number as false about their graph.

    The NUMBER was right and the WORDS were wrong. A reopen takes the node out of the population
    rather than counting against it — reopening everything leaves ⊥ here, not 0.0 — and only a later
    independent check that CONTRADICTS a standing pass moves it. "No PASS was ever taken back" is
    exactly how a reopen reads in plain English, which is why a careful reader called it a lie.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("a"), spec("goal", "c1"), AgentId("agent"))
        e.wait_idle()
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("a"),
                                      source=AgentId("agent")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("a"),
                                      source=AgentId("agent"), result="r"))
        e.wait_idle()
        e.record_exec_verdict(TaskId("a"), verdict=Verdict.PASS, failed_criteria=[],
                              validator_id=AgentId("judge"),
                              per_criterion=[{"criterion": "c1", "verdict": "pass",
                                              "evidence": "ran it"}])
        e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("a"),
                                      source=AgentId("agent")))
        e.wait_idle()
        assert e.metrics()["q_V"] == 1.0, "a standing, uncontradicted pass should read 1.0"

        e.reopen(TaskId("a"), AgentId("agent"))
        e.wait_idle()
        assert e.metrics()["q_V"] is None, (
            "a reopened node must leave the population — ⊥, not a score")

        words = Q_MEANS["q_V"]
        assert "reopen" in words, "the wording never mentions the act that confused a reader"
        assert "no PASS was ever taken back" not in words, (
            "the wording still promises something a reopen visibly contradicts")
    finally:
        e.stop()


def test_a_refused_report_is_said_at_completion_without_withholding_it():
    """⊥ is not fail — so it is SAID beside "complete", never used to withhold it.

    Measured on the HTTP door 2026-09-02: a judge ran on a root that had closed by hand forty-six
    seconds earlier, the engine refused its report as ⊥ (§11.2), and `next_steps` went on answering
    "COMPLETE — the goal is met" with nothing anywhere recording that a judge had tried and failed
    to decide it.

    Both halves matter and they pull opposite ways. Withholding completion over a ⊥ would read it as
    a fail, which the canon forbids in those words; saying nothing leaves the one surface a person
    checks silent about the only thing that happened after they closed the node.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("a"), spec("goal", "c1"), AgentId("agent"))
        e.wait_idle()
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("a"),
                                      source=AgentId("agent")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("a"),
                                      source=AgentId("agent"), result="r"))
        e.wait_idle()
        e.record_exec_verdict(TaskId("a"), verdict=Verdict.PASS, failed_criteria=[],
                              validator_id=AgentId("judge"),
                              per_criterion=[{"criterion": "c1", "verdict": "pass",
                                              "evidence": "ran it"}])
        e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("a"),
                                      source=AgentId("agent")))
        e.wait_idle()
        assert e._frontier().get("complete") is True, "the node closed; this should read complete"
        assert not e.nodes_with_a_refused_report(), "nothing has been refused yet"

        # …now a judge reports and the engine refuses it as ⊥, AFTER the node is terminal.
        e.record_rejected_report(TaskId("a"), {"defects": ["decided no criterion"],
                                               "per_criterion": [], "refusals": 1})
        out = e._frontier()
        assert out.get("complete") is True, (
            "a ⊥ withheld completion — that reads 'could not decide' as 'decided against' (§11.2)")
        assert "a" in (out.get("unresolved_reports") or []), (
            "the refused report is invisible at the one place completion is announced")
    finally:
        e.stop()


def test_the_catalogue_serves_closed_sets_as_data_and_only_where_they_are_closed(client):
    """A caller should not have to parse prose, or be refused once, to learn a closed set.

    Measured on the HTTP door 2026-09-02: `reason` is a four-word enum whose refusal names the words
    perfectly and whose docstring spells them out — and both are English, so a tester silently
    no-op'd five criteria edits before a refusal told them.

    The trap this also pins: keying the sets by parameter NAME alone made the catalogue announce that
    `signal`'s `reason` must be one of those four words. It is free text there — why a node is
    blocked or cancelled — so that would have been the catalogue confidently asserting something
    false, which is the defect class the whole surface exists to stop emitting. Keyed by verb.
    """
    served = {t["tool"]: t.get("choices") or {} for t in client.get("/api/tools").json()["tools"]}

    assert served["revise"]["reason"] == [r.name.lower() for r in RevisionReason], (
        "the causal-typing enum is not served as data")
    assert served["record_verdict"]["verdict"] == ["PASS", "FAIL"]
    assert "reason" not in served["signal"], (
        "`signal`'s reason is FREE TEXT — offering the revision enum for it is a false claim")
    assert served["signal"]["self_validation"] == ["PASS", "FAIL"], (
        "the one closed set `signal` does have is missing")

    # …and the sets are DERIVED, so a member added to the vocabulary cannot fail to appear.
    for verb, params in PARAM_CHOICES.items():
        if "reason" in params:
            assert set(params["reason"]) == {r.name.lower() for r in RevisionReason}, (
                f"{verb}'s reason list has drifted from the enum that enforces it")


def test_a_dispute_that_says_nothing_discharges_nothing():
    """The Level-2 gate cost one word per finding to defeat, on both doors, independently.

    Measured 2026-09-02: the CLI door discharged EIGHT substantive checker findings with "nah", and
    the HTTP door discharged three at once with "nah, its fine" — after which execution was admitted
    and every quality metric read 1.0. Both testers named this verb and asked for the rule
    `record_verdict` already applies, in those words.

    The checker is an approximation and may be wrong (§13.5) — disputing is a legitimate discharge.
    What is refused is a dispute that restates the conclusion instead of giving a reason for it, and
    the other route needs no argument at all: fix the plan.
    """
    e = make_engine()
    e.start()
    try:
        for said in ("nah", "nah, its fine", "this is fine, trust me", "no", "whatever"):
            r = dispute_finding(e, "root", "undecided: touching intervals", said)
            assert r.get("refused"), f"{said!r} discharged a finding"
            assert "restates the conclusion" in str(r.get("error")), "the refusal does not say why"

        # …and the BATCH form, which is how three findings went at once.
        assert dispute_finding(e, "root", ["a", "b", "c"], "nah").get("refused"), (
            "a batch dispute skipped the check the single form applies")

        # A REAL reason must survive — this is a discharge route, not a wall. It gets past the
        # content check and on to the engine, which refuses it for its own reason (no such review),
        # and that is the boundary being asserted here.
        try:
            real = dispute_finding(e, "root", "undecided: touching intervals",
                                   "criterion ascii_only already decides it, and the register "
                                   "accepts unicode normalisation as out of scope")
            said = str(real.get("error", ""))
        except ValueError as engine_said:      # the single-key contract raises; the door wraps it
            said = str(engine_said)
        assert "restates the conclusion" not in said, (
            "a written reason was refused as contentless — the rule has become a wall")
    finally:
        e.stop()


def test_a_hand_asserted_verdict_is_not_replayed_under_an_instruments_name():
    """Reuse is for a JUDGE's ruling. Replaying a person's assertion as one is laundering.

    Measured on both stranger doors 2026-09-02. The CLI door recorded a PASS on the root naming a
    reviewer invented in the same second — `w22cli-reviewer-bob`, never registered, who ran nothing
    — and the dispatcher then reused it and signed the signal as `w22cli-validator`, so the log read
    `PASS by w22cli-validator`: a registered instrument passing a root it had never judged. The HTTP
    door hit the same shape from the other side.

    The exclusion already existed for a self-report, for exactly this reason. The engine names all
    three kinds of party now, so reuse asks for the one that qualifies — and says why when it
    declines, because from outside "declined to replay" and "no verdict here" look identical.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("n"), spec("goal", "c1"), AgentId("worker"))
        e.wait_idle()
        rec = {"verdict": Verdict.PASS, "validator": "bob-who-does-not-exist", "failed_criteria": []}

        for prov in ("by_hand", "self"):
            assert _replay_a_standing_verdict(e, TaskId("n"), rec, AgentId("the-instrument"),
                                              "llm-validator", True, prov, True) is None, (
                f"a {prov} verdict was replayed as though an instrument had ruled")

        # …and an instrument's ruling IS reused, or this stops being an optimisation and becomes a
        # wall that pays for every verdict twice.
        assert _replay_a_standing_verdict(e, TaskId("n"), rec, AgentId("the-instrument"),
                                          "llm-validator", True, "instrument", False) == "recorded"
    finally:
        e.stop()


def test_the_verdict_a_node_closed_on_is_not_overwritten_by_a_later_one():
    """The surface that answers "did anything close without proof" was rewritable after the close.

    Measured on the HTTP door 2026-09-02: a hand-asserted PASS containing false statements closed a
    node; an instrument reported 46 seconds later; its SIGNAL was correctly refused because the node
    was terminal — and its RECORD was written anyway, on top. Every surface then reported the node
    as judged by an instrument, `by_hand` was false, and the record that actually did the closing
    was reachable from nowhere. The two things this product offers as its guarantee are "the record"
    and "in writing", and that was both of them, in the closer's favour.

    A later record must still be ACCEPTED — that is q_V's discovery carrier, the whole mechanism by
    which a pass is found to have been wrong, and refusing it would blind the thing that catches
    false greens. So it is kept beside the closing one rather than instead of it.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("n"), spec("goal", "c1"), AgentId("agent"))
        e.wait_idle()
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("n"),
                                      source=AgentId("agent")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("n"),
                                      source=AgentId("agent"), result="r"))
        e.wait_idle()
        e.record_exec_verdict(TaskId("n"), verdict=Verdict.PASS, failed_criteria=[],
                              validator_id=AgentId("bob-who-ran-nothing"), by_hand=True,
                              per_criterion=[{"criterion": "c1", "verdict": "pass",
                                              "evidence": "I ran it and it printed 27 passed"}])
        e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("n"),
                                      source=AgentId("agent")))
        e.wait_idle()
        assert e.closing_verdict(TaskId("n")) is None, "nothing has overwritten it yet"

        e.record_exec_verdict(TaskId("n"), verdict=Verdict.PASS, failed_criteria=[],
                              validator_id=AgentId("val-1"),
                              per_criterion=[{"criterion": "c1", "verdict": "pass",
                                              "evidence": "ran the suite"}])

        closed_on = e.closing_verdict(TaskId("n"))
        assert closed_on and closed_on["validator"] == "bob-who-ran-nothing", (
            "the record the node actually closed on is gone")
        assert closed_on["by_hand"] is True, "its provenance was laundered into an instrument's"

        shown = get_verdict(e, "n")
        assert shown["closed_on"]["validator"] == "bob-who-ran-nothing", (
            "the read that answers 'did this close without proof' does not show what it closed on")
        assert shown["validator"] == "val-1", "the later record is still reported, as it must be"
    finally:
        e.stop()


def test_a_hand_verdict_is_refused_while_an_instrument_is_mid_judgement():
    """The reply that says "recording your own verdict here would race it" now has something behind it.

    Measured on the CLI door 2026-09-02: the DELIVER reply gave exactly that warning, nothing
    enforced it, and the race ran — a hand stamp closed the node 35 seconds before the instrument
    reported, the instrument's signal was then refused for arriving at a terminal node, and its
    record landed on top of the one that had done the closing.

    The claim this needs already existed (`begin_validation` takes it); what was missing was a way to
    ASK without taking it. Same TTL, so a leaked claim cannot make a node permanently unjudgeable.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("n"), spec("goal", "c1"), AgentId("agent"))
        e.wait_idle()
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("n"),
                                      source=AgentId("agent")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("n"),
                                      source=AgentId("agent"), result="r"))
        e.wait_idle()
        assert not e.validation_in_flight(TaskId("n")), "nothing is judging it yet"

        claim = e.begin_validation(TaskId("n"))
        assert claim is not None and e.validation_in_flight(TaskId("n"))
        raced = record_verdict(e, "n", "PASS", reviewer="someone",
                               observed={"c1": "ran `pytest -q`: 3 passed"})
        assert raced.get("recorded") is False, "a hand verdict raced a running instrument"
        assert raced.get("validation_in_flight") is True

        # …and once the run ends, the door opens again: this is a race guard, not a lockout.
        e.end_validation(claim)
        assert not e.validation_in_flight(TaskId("n"))
        assert record_verdict(e, "n", "PASS", reviewer="someone",
                              observed={"c1": "ran `pytest -q`: 3 passed"}).get("recorded") is True
    finally:
        e.stop()


def test_the_review_summary_says_how_its_findings_were_closed():
    """A finding leaves the open list two ways, and the summary showed neither.

    Measured on both wave-22 doors 2026-09-02, and both testers asked for this line in nearly the
    same words: one dismissed EIGHT substantive checker findings by argument and watched every
    surface stay green, because a gate discharged entirely by argument reads identically to one
    nobody had to argue with. The disputes were faithfully stored the whole time — nested where a
    reader had to already know to look.

    Disputing is a legitimate discharge (§13.5: the checker approximates and can be wrong). It is
    also the discharge nobody re-checks, which is exactly why it is named where the summary is read.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("root"), spec("goal", "c1", "c2"), AgentId("agent"))
        e.wait_idle()
        e.decompose_task(TaskId("root"),
                         [(TaskId("root.kid"), spec("kid", "k1"), AgentId("agent"))],
                         criterion_mappings=[CriterionMapping("c1", TaskId("root.kid")),
                                             CriterionMapping("c2", TaskId("root.kid"))])
        e.wait_idle()
        assert "discharged_by_dispute" not in get_review(e, "root"), (
            "nothing has been disputed — the line must not appear")

        e._graph._storage.store_critique(TaskId("root"), json.dumps({
            "semantic_findings": ["c1 is not entailed"],
            "disputes": {"c1": {"why": "k1's contract entails it", "by": "agent", "ts": "t"},
                         "c2": {"why": "the register puts it out of scope", "by": "agent",
                                "ts": "t"}}}))
        out = get_review(e, "root")
        assert out["discharged_by_dispute"] == ["c1", "c2"], (
            "the summary does not say which findings were argued away")
        assert "rather than by changing the plan" in out["discharged_by_dispute_note"], (
            "the note does not distinguish the two ways a finding can leave the list")
    finally:
        e.stop()


def test_binding_coverage_is_not_logged_as_revising_a_contract():
    """The human-facing strip must not claim a revision that never happened.

    Measured on the CLI door 2026-09-02: sixteen `map_criterion` calls wrote sixteen lines reading
    "contract revised by agent". No contract was revised — binding coverage re-ASSIGNs the child
    under the SAME spec, which is why it produces a same-state ASSIGN in the first place. The strip
    is the trail a person actually reads, and it was overstating what happened, sixteen times.

    The packet already distinguishes them: a coverage binding carries `covers`, a revision does not.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("root"), spec("goal", "c1", "c2"), AgentId("agent"))
        e.wait_idle()
        e.decompose_task(TaskId("root"),
                         [(TaskId("root.kid"), spec("kid", "k1"), AgentId("agent"))],
                         criterion_mappings=[CriterionMapping("c1", TaskId("root.kid"))])
        e.wait_idle()

        map_criterion(e, "root", "root.kid", "c2")
        e.wait_idle()
        bound = e._graph._storage.get_pipeline(50)[-1]["message"]
        assert "coverage bound" in bound, f"a mapping was logged as: {bound}"
        assert "revised" not in bound, "a mapping still claims to have revised the contract"

        edit_criteria(e, "root.kid", criteria=[{"name": "k1", "description": "k1", "check": "k1"},
                                               {"name": "k2", "description": "k2", "check": "k2"}])
        e.wait_idle()
        revised = e._graph._storage.get_pipeline(50)[-1]["message"]
        assert "contract revised" in revised, (
            f"a real revision is no longer called one: {revised}")
    finally:
        e.stop()


def test_recording_a_verdict_and_arguing_away_a_finding_leave_a_trace():
    """Two acts that close nodes and open gates left nothing in the trail a person reads.

    Measured on the HTTP door 2026-09-02: `/api/audit` carries 44 entries, all P2P signals plus
    ASSIGN, and grepping it for the verdict text or the dispute reason found nothing — while both
    verbs' own help sells durability ("it is what the log will carry"). The audit IS the signal trail
    by definition and neither of these is a signal, so the fact goes to the observation strip, which
    already carries non-signal events. The definition stays; the silence does not.
    """
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("n"), spec("goal", "c1"), AgentId("agent"))
        e.wait_idle()
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("n"),
                                      source=AgentId("agent")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("n"),
                                      source=AgentId("agent"), result="r"))
        e.wait_idle()

        record_verdict(e, "n", "PASS", reviewer="bob",
                       observed={"c1": "ran `pytest -q`: 3 passed"})
        line = e.pipeline_log(20)[-1]["message"]
        assert "bob" in line and "n:" in line, f"the verdict left no trace: {line}"
        assert "ASSERTED BY HAND" in line, (
            "the trace does not say the verdict is a person's word rather than an instrument's")
    finally:
        e.stop()


def test_the_affordance_surface_knows_a_validator_is_running(monkeypatch):
    """Two surfaces gave opposite advice about the same node in the same second.

    Measured on the MCP door 2026-09-02: `DELIVER` replied "an independent validator is bound to
    this node — wait for it… Recording your own verdict here would race it", while
    `available_actions` on that same node replied "PASS is not open yet… `record_verdict(…)` then
    signal". One says wait and do not record; the other says record. The affordance surface did not
    know a run was in flight.

    Signing an INTERNAL node is the executor's right (§14.5 D6), so this does not refuse it — it says
    what signing now costs, and names the field that will report the contradiction afterwards.
    """
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("root"), spec("goal", "c1"), AgentId("agent"))
        e.wait_idle()
        e.decompose_task(TaskId("root"),
                         [(TaskId("root.kid"), spec("kid", "k1"), AgentId("agent"))],
                         criterion_mappings=[CriterionMapping("c1", TaskId("root.kid"))])
        e.wait_idle()
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root.kid"),
                                      source=AgentId("agent")))
        e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("root.kid"),
                                      source=AgentId("agent"), result="r"))
        e.wait_idle()
        assert e.get_task(TaskId("root.kid")).state.name == "VALIDATING"

        assert "RIGHT NOW" not in str(available_actions(e, "root.kid", "agent")), (
            "the surface announces a run when none is in flight")

        claim = e.begin_validation(TaskId("root.kid"))
        try:
            said = str(available_actions(e, "root.kid", "agent"))
            assert "RIGHT NOW" in said, "the surface still invites a signature over a running judge"
            assert "refuted_passes" in said, (
                "it does not name what will report the contradiction if they sign anyway")
        finally:
            e.end_validation(claim)
    finally:
        e.stop()


def test_replacing_criteria_says_what_coverage_it_destroyed(monkeypatch):
    """Replacing the set takes the mappings with it, and once a child is DONE they never come back.

    Measured on the MCP door 2026-09-02: a caller replaced ten criteria with one, then restored the
    ten verbatim, and was left with a DONE/PASS root carrying a permanent `CHECK-1:coverage` failure
    — `map_criterion` refuses to re-map, because adding a `covers` to a finished node is a revision
    of a terminal contract (Inv-1). The reply had said what was newly UNCOVERED and never that
    anything had been LOST.

    Two traps this also pins. The loss is computed from the REQUEST, because the pruning rides the
    revision's ASSIGN through the event loop and reading the node back inside the verb still sees
    the old mappings. And the pre-state is COPIED OUT before the engine call, because `before` is the
    live Task the engine mutates in place — reading its mappings afterwards reads the post-edit
    state and reports no loss at all. Both of those returned a confident "nothing was dropped".
    """
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    try:
        e.assign_task(TaskId("root"), spec("goal", "c1"), AgentId("agent"))
        e.wait_idle()
        e.decompose_task(TaskId("root"),
                         [(TaskId("root.kid"), spec("kid", "k1"), AgentId("agent"))],
                         criterion_mappings=[CriterionMapping("c1", TaskId("root.kid"))])
        e.wait_idle()

        # while the child is still OPEN, the loss is recoverable and says so
        out = edit_criteria(e, "root", criteria=[{"name": "other", "description": "d",
                                                  "check": "d"}])
        assert out["coverage_dropped"] == ["c1 -> root.kid"], "the dropped mapping was not named"
        assert "can re-make them" in out["coverage_dropped_note"], "recoverable loss reads as final"
    finally:
        e.stop()

    e2 = make_engine()
    e2.start()
    try:
        e2.assign_task(TaskId("root"), spec("goal", "c1"), AgentId("agent"))
        e2.wait_idle()
        e2.decompose_task(TaskId("root"),
                          [(TaskId("root.kid"), spec("kid", "k1"), AgentId("agent"))],
                          criterion_mappings=[CriterionMapping("c1", TaskId("root.kid"))])
        e2.wait_idle()
        for sig, extra in ((Signal.ACCEPT, {}), (Signal.DELIVER, {"result": "ran the kid check, it printed OK",
                                                                  "self_validation": Verdict.PASS})):
            e2.send_signal_sync(SignalData(signal=sig, task_id=TaskId("root.kid"),
                                           source=AgentId("agent"), **extra))
        e2.wait_idle()
        e2.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("root.kid"),
                                       source=AgentId("agent")))
        e2.wait_idle()
        assert e2.get_task(TaskId("root.kid")).state.name == "DONE"

        # …AND NOW IT IS REFUSED BEFORE IT HAPPENS, not narrated after. The note below was written
        # while the loss was already made, which is the guard-after-the-side-effect shape this
        # codebase keeps finding in itself; a stranger reworded one criterion on a finished project
        # and read the explanation of why it could never close again in the reply that made it true
        # (MCP door, wave 23, 2026-09-03). The knowledge did not change — the moment did.
        refused = edit_criteria(e2, "root", criteria=[{"name": "other", "description": "d",
                                                      "check": "d"}])
        assert refused["refused"] is True and refused["would_destroy_coverage"] == ["root.kid"]
        assert [c.name for c in e2.get_task(TaskId("root")).spec.criteria] == ["c1"], (
            "the contract was replaced by the call that refused")

        out = edit_criteria(e2, "root", criteria=[{"name": "other", "description": "d",
                                                   "check": "d"}], accept_coverage_loss=True)
        assert "IRREVERSIBLE" in out["coverage_dropped_note"], (
            "a loss that cannot be undone reads the same as one that can")
        assert "root.kid" in out["coverage_dropped_note"], "it does not name the finished child"
    finally:
        e2.stop()

def test_the_page_draws_how_a_node_closed(client):
    """Every DONE node was drawn identically — the one an instrument proved and the one signed for.

    Wave 26 (2026-09-06), left open because `/api/graph` carried no provenance at all. It does now
    (`Engine.closure_of`), and the picture reads it: contested closures ringed in the accent, hand
    ones dashed, and the counts beside the state tally say how many of each.
    """
    page = client.get("/").text
    assert "closureStyle" in page and "n.closure" in page, (
        "the drawing has to read the node's own closure, not a second copy of the rule")
    assert "closed by hand" in page and "contested" in page, (
        "…and the header must not print one number for two different kinds of green")


def test_the_identity_the_page_signs_with_survives_a_reload(client):
    """The box SIGNS every signal this page sends, and it reset to the server's id on refresh."""
    page = client.get("/").text
    assert "rememberedRole" in page and "localStorage" in page
    assert "rememberRole(myRole())" in page, "…and it is written down when it is typed"


def test_one_edit_is_one_revision(client):
    """Each authoring verb is a re-ASSIGN (Inv-1); the form sent all of them on every submit."""
    page = client.get("/").text
    assert "critsMoved" in page and "risksMoved" in page, (
        "the form has to send what CHANGED — two identical ASSIGNs for one act is what wave 26 saw")


def test_the_graph_libraries_do_not_block_the_page(client):
    """Three parser-blocking tags in <head> held the whole interface behind unpkg answering."""
    page = client.get("/").text
    assert page.count("<script defer src=\"https://unpkg.com") == 3, (
        "the remote scripts must not block the first paint — vendoring them is a separate, parked "
        "decision")
    assert "DOMContentLoaded" in page, "…and init has to wait for them, or it reports them missing"
