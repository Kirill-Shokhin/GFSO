"""A mode holds on a subtree: "autonomy is a per-task, per-role property, not a global mode" (§10.4). The person holds a
node Y of the author's one shared graph — his root above, other streams beside, no project mode — and sets, once, on
his signed-in page, that the work he issues below Y runs solo `in_chat`: every node he issues there to another (a
direction, Del `engineering`) is a mode top, its Del holding and working it as a person's solo `in_chat` agent works his
own project. Y itself, his own work, lies under no mode; the stream's own console never sets it.

At each top the person's word keeps its four protections, as at the root of his own project: he is its issuer (§10.1),
every node below is issued by its holder, Del(parent), so his words there would sign a role he does not hold. The top's
packet changes only on his words (his asks are revisions of its criteria), the criterion read against his words comes
with his own act on it, the validator observes it, and it closes on his verdict. A go anywhere below it — or onto it —
is the holder's own split: no words, no criterion of his, self-verified below the seam (§10.3), the checker the holder's
choice. Nothing switches the person's branch: the checkout is shared with the other streams.

Outside it NOTHING changes, though the scope's validator is registered in the project: what the system starts, binds
and says, and what a restart stops, read as in a project with no mode — what can be asked stays askable."""
from __future__ import annotations

import contextlib
import json

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.adapters.execution import LocalExecution
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.config import CALLER, SERVES_ENV, Principal
from gfso.core.protocol.invariants import INTENT
from gfso.core.types import AgentId, Mode, TaskId
from gfso.delegate import AgentRegistry, ensure_dispatcher
from gfso.engine.validation import MODE_SCOPES, in_chat_names, observation_binds, owed_observer
from gfso.runtime import ProjectRegistry
from tests.support import REGISTER, a_repository, criterion, instrument_passes, make_engine
from tests.test_delegate import _dispatch_validate

AUTHOR, HOLDER = "author-draft", "engineering"
#: the node he holds, a top he issues below it, and a task of its holder's under that
Y, X, ASK = "root.stream", "root.stream.engineering", "root.stream.engineering.t"
#: the person's page: every name he owns, the standing agent first (`signin.names_of`)
PAGE = Principal("user", ("user", AUTHOR, HOLDER), "session", "signed in", "local")
#: the stream's own console: a token naming it alone
CONSOLE = Principal(HOLDER, (HOLDER,), "tok-eng", "token")
#: an agent's connection with no credential: it signs as the person's name, and is no page (config.STANDING)
ISSUER = Principal("user", ("user",), "default", "default", "local")
WORDS, ACCEPTED = "да, делай так", "да, принимаю"
FILLED = {'name = ""\n\n#': 'name = "t"\n\n#', 'name = ""\ndescription = ""': 'name = "says"\ndescription = "f.txt says v1"',
          'behaviour = ""': 'behaviour = "f.txt read"', 'command = ""': "command = 'cat f.txt'",
          'expect = ""': 'expect = "v1"'}
#: a holder's file whose root criteria are its own, not the top's contract
YOURS_FILLED = TL.YOURS.format(goal='"Write f.txt saying v1."')
for _a, _b in FILLED.items():
    YOURS_FILLED = YOURS_FILLED.replace(_a, _b, 1)
bash = pytest.mark.skipif(not LocalExecution().shell(), reason="no bash on this host: a go reads its checks here")


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)


@pytest.fixture
def no_model(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the system's planner was asked")
    monkeypatch.setattr(TL._planning, "author", refuse)
    monkeypatch.setattr(TL._decompose, "default_llm", lambda *a, **k: type("NoModel", (), {"calls": []})())


@contextlib.contextmanager
def _as(p: Principal):
    token = CALLER.set(p)
    try:
        yield
    finally:
        CALLER.reset(token)


def _call(p: Principal, verb: str, e, *a, **kw) -> dict:
    """A verb at a door on `e`, signed by `p`'s credential."""
    with _as(p):
        return TL.TOOLS[verb](e, *a, **kw)


def _in_its_chat(e, workdir):
    """`engineering`'s own connection took its name (`act_as`): it performs in a chat here — what the scope recorded
    for it, now its own fact — and the project's validator is registered at the repository, for a check he chooses."""
    e.performs_in_chat(HOLDER)
    assert not TL.register_agent(e, "p-val", "llm-validator", workdir=str(workdir)).get("refused")


def _shared(tmp_path, scoped: bool = True, workdir=None):
    """The author's one graph: his root, the node he holds beside the other streams' tops and a node of the standing
    agent's, `engineering`'s direction issued by him from his page under it — and, where `scoped`, `engineering`
    working in its chat (`_in_its_chat`)."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    T.create_task(e, "root", {"description": "the author's goal", "criteria": [criterion("g")]}, assignee=AUTHOR,
                  agent=AUTHOR)
    T.decompose(e, "root", [{"task_id": n, "spec": {"description": n, "criteria": [criterion(n.split(".")[1])]},
                             "assignee": a, "covers": ["g"]}
                            for n, a in ((Y, "user"), ("root.ui", "ui"), ("root.mine", "user"))],
                accepted_risks=REGISTER, agent=AUTHOR)
    e.wait_idle()
    if scoped:
        _in_its_chat(e, workdir or tmp_path)
    _call(PAGE, "decompose", e, Y, [{"task_id": X, "spec": {"description": X, "criteria": [criterion(HOLDER)]},
                                     "assignee": HOLDER, "covers": ["stream"]}], accepted_risks=REGISTER, agent="user")
    e.wait_idle()
    # …the live dispatcher the registration starts is stopped: a test's own round is the one that dispatches
    ensure_dispatcher(e).stop()
    return e


def _split(e, parent, kid, holder, agent):
    T.decompose(e, parent, [{"task_id": kid, "spec": {"description": kid, "criteria": [criterion("k")]},
                             **({"assignee": holder} if holder else {}), "covers": [c.name for c in
                                                                                    e.graph.get_task(TaskId(parent)).spec.criteria]}],
                accepted_risks=REGISTER, agent=agent)
    e.wait_idle()


def _delivered(e, tid, by):
    T.signal(e, tid, "ACCEPT", by)
    T.signal(e, tid, "DELIVER", by, result=f"ran the checks of {tid}: they hold", self_validation="PASS")
    e.wait_idle()


def _the_go(e, node=ASK, said="") -> dict:
    """The holder asks for its plan, fills it, hands it in and gives the go — `said` the words it passes with it."""
    text = _call(CONSOLE, "plan", e, "Write f.txt saying v1.", root_id=node)["text"]
    for a, b in FILLED.items():
        text = text.replace(a, b, 1)
    _call(CONSOLE, "plan", e, plan=text, root_id=node)
    return _call(CONSOLE, "auto_decompose", e, plan=text, root_id=node, user_said=said)


# ── setting it ────────────────────────────────────────────────────────────────

def test_the_name_taken_in_a_chat_makes_each_seam_he_issues_to_it_a_top_and_the_project_keeps_no_mode(tmp_path):
    """The level is the executor's own fact for one task and role (§10.4): its connection took its name, so each seam
    he issues to it is a top, read by the page per node with the node above it; the project itself stays modeless for
    the other streams, and nothing is set at any node."""
    e = _shared(tmp_path)
    rec = e.mode_scopes()[Y]
    assert (rec["mode"], rec["perform"], rec["by"]) == ("solo", "in_chat", HOLDER), rec
    assert e.mode() is None and e.mode_at(TaskId("root.ui")) is None
    graph = T.get_graph(e)
    assert list(graph["scopes"]) == [Y]
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert (nodes[X]["scope"], nodes[X]["mode_top"]) == (Y, X), nodes[X]
    assert "scope" not in nodes["root.ui"] and "scope" not in nodes[Y], nodes


def test_no_one_sets_a_mode_at_a_node_his_page_included(tmp_path):
    """No button: what the scope did for the executor follows from the name it took."""
    e = _shared(tmp_path, scoped=False)
    for p in (PAGE, CONSOLE, ISSUER):
        out = _call(p, "set_mode", e, "solo", perform="in_chat", node=Y, workdir=str(tmp_path))
        assert out.get("refused") and "act_as" in out["error"], out
    assert not e.mode_scopes()


def test_a_project_mode_is_refused_while_a_top_stands_and_answers_alone_where_set(tmp_path):
    """Two carriers of who holds a node would answer it twice: a project mode is refused over a standing top; set
    before, it answers alone and no seam is a top."""
    e = _shared(tmp_path)
    assert _call(PAGE, "set_mode", e, "solo", perform="in_chat").get("refused"), "a project mode over a standing top"
    with pytest.raises(ValueError):
        e.set_mode(Mode.SOLO, None, AgentId("user"))
    bare = _shared(tmp_path / "bare", scoped=False)
    bare.set_mode(Mode.SOLO, None, AgentId("user"))
    bare.performs_in_chat(HOLDER)
    assert bare.scope_at(X) is None and not bare.mode_scopes()


# ── inside the scope ──────────────────────────────────────────────────────────

def test_inside_the_scope_a_node_goes_to_its_holder_and_a_third_party_is_refused(tmp_path):
    """The holder is the scope record's, not the standing agent's: with the standing agent read, every node under the
    stream's top went to `user` or was refused. A third party under it would be a seam inside solo."""
    e = _shared(tmp_path)
    _split(e, X, ASK, None, HOLDER)
    assert str(e.graph.get_task(TaskId(ASK)).assignee) == HOLDER
    with pytest.raises(ValueError):
        T.del_by_mode(e, X, "ui")


def test_inside_the_scope_the_holders_parts_self_verify_and_its_top_is_checked_by_the_validator(tmp_path):
    """Solo in_chat below the seam: the holder's own nodes self-verify (§10.3). Its top — a seam he issued — is
    observed by the project's validator on every delivery, and he cannot turn it off (the author, 2026-11-20: «на шве
    … должен стоять обязательный»)."""
    e = _shared(tmp_path)
    _split(e, X, ASK, HOLDER, HOLDER)
    assert e.held_in_chat(TaskId(ASK)) and not e.observed_here(TaskId(ASK))
    assert e.observes_by_itself(TaskId(X)) and e.checker(TaskId(X)) == "validator"
    assert _call(PAGE, "set_checker", e, X, "self", agent="user").get("refused")
    assert e.observes_by_itself(TaskId(X)) and e.checker(TaskId(X)) == "validator"


@bash
def test_inside_the_scope_a_go_anywhere_is_the_holders_own_split(tmp_path, no_model):
    """Below the top every node is issued by the holder (§10.1: a child's issuer is Del(parent)): a go there is its own
    split, as a part's later split in the person's own solo project — no words owed, no criterion of his added, nothing
    heard as his, self-verified. Taken for his, his words would sign a role he does not hold."""
    e = _shared(tmp_path)
    _split(e, X, ASK, HOLDER, HOLDER)
    plan = _call(CONSOLE, "plan", e, "Write f.txt saying v1.", root_id=ASK)
    assert plan.get("yours"), "the holder writes its plan itself: no model"
    go = _the_go(e)
    assert not go.get("refused") and "gfso/p/work" not in go["say"], go
    assert INTENT not in [c.name for c in e.graph.get_task(TaskId(ASK)).spec.criteria]
    assert not e.observed_here(TaskId(ASK)) and not e.persons_verdict(ASK)
    assert not [h for h in e.heard_on(ASK) if h["act"] in ("go", "request")], "the holder's words heard as the person's"
    assert not _call(CONSOLE, "signal", e, ASK, "ACCEPT", HOLDER).get("refused")


@bash
def test_a_go_onto_the_top_is_the_holders_split_and_leaves_the_persons_contract(tmp_path, no_model):
    """The top's contract is its issuer's (§10.1): the holder's go on it maps onto the criteria he was given and
    re-authors none — they move only by his revision."""
    e = _shared(tmp_path)
    before = e.graph.get_task(TaskId(X)).spec.criteria
    go = _the_go(e, X)
    assert not go.get("refused"), go
    assert e.graph.get_task(TaskId(X)).spec.criteria == before
    assert "maps onto" in go["say"] and "fixed in the graph" not in go["say"], go["say"]


@bash
def test_a_plan_at_the_top_is_checked_and_gone_on_its_contract_as_issued(tmp_path, no_model):
    """At the top the go maps the split onto the person's contract (§10.1): a file whose root criteria are anything
    else was checked against one contract and gone on another, its own criteria dropped in silence. So the file handed
    is that contract, and a file off it is refused at the plan and at the go alike."""
    e = _shared(tmp_path)
    handed = _call(CONSOLE, "plan", e, "Write f.txt saying v1.", root_id=X)
    assert handed.get("yours") and 'name = "engineering"' in handed["text"] and f'name = "{INTENT}"' in handed["text"]
    assert not _call(CONSOLE, "plan", e, plan=handed["text"].replace('name = ""', 'name = "t"', 1),
                     root_id=X).get("refused_by_the_go")
    off = "\n".join(x for x in YOURS_FILLED.splitlines())
    shown = _call(CONSOLE, "plan", e, plan=off, root_id=X)
    assert any("revision" in r for r in shown["refused_by_the_go"]), shown
    went = _call(CONSOLE, "auto_decompose", e, plan=off, root_id=X)
    assert went.get("refused") and "revision" in went["error"], went
    assert not shown.get("added_at_the_go"), "the go at the top adds nothing: it maps onto the contract"


def test_his_issue_of_a_seam_installs_the_criterion_whoever_holds_it(tmp_path):
    """His ASSIGN of a seam is his own act on it, the counterpart of his go in his own project: the criterion read
    against his words is on by default (the author, 2026-11-19), whether its holder works in a chat or not."""
    e, bare = _shared(tmp_path), _shared(tmp_path / "bare", scoped=False)
    assert INTENT in [c.name for c in e.graph.get_task(TaskId(X)).spec.criteria]
    assert INTENT in [c.name for c in bare.graph.get_task(TaskId(X)).spec.criteria]


def test_the_tops_packet_changes_only_on_the_persons_words(tmp_path):
    """His asks of the stream are revisions of its top's criteria — the contract his words agreed is the one that
    stands, as on his own root under solo."""
    e = _shared(tmp_path)
    refused = _call(ISSUER, "edit_criteria", e, X, [criterion("asked")])
    assert refused.get("refused") and "user_said" in refused["error"], refused
    assert [c.name for c in e.graph.get_task(TaskId(X)).spec.criteria] == ["engineering", INTENT]
    assert not _call(ISSUER, "edit_criteria", e, X, [criterion("asked")], user_said=WORDS).get("refused")
    assert [h["said"] for h in e.heard_on(X) if h["act"] == "revise"][-1] == WORDS


def test_the_top_is_observed_and_closes_on_the_persons_verdict(tmp_path):
    """The verdict is the issuer's (§10.2), and its issuer is the person: signed by an agent's connection it carries his
    words, on the validator's record — never on the holder's own check."""
    e = _shared(tmp_path)
    _delivered(e, X, HOLDER)
    early = _call(ISSUER, "signal", e, X, "PASS", "user", user_said=ACCEPTED)
    assert not early.get("accepted"), "the top closed with no observer's record"
    instrument_passes(e, TaskId(X), validator="p-val")
    with _as(ISSUER):
        assert "is the person's" in e.persons_verdict(X)
    assert _call(ISSUER, "signal", e, X, "PASS", "user").get("refused"), "the top signed without his words"
    assert _call(ISSUER, "signal", e, X, "PASS", "user", user_said=ACCEPTED)["state"] == "DONE"
    assert [h["said"] for h in e.heard_on(X) if h["act"] == "verdict"] == [ACCEPTED]


def test_the_criterion_read_against_his_words_stands_at_the_top(tmp_path):
    """Where the person holds the work in a chat the root carries `answers_the_persons_words` by default; in a scope
    its top stands for the root, and nothing below it is his."""
    e = _shared(tmp_path)
    _split(e, X, ASK, HOLDER, HOLDER)
    spec = {"root_criteria": [criterion("asked")]}
    assert e.intent_check(node=X) and not e.intent_check(node="root.ui")
    assert INTENT in [c["name"] for c in TL.with_the_intent(e, spec, X)["root_criteria"]]
    assert INTENT not in [c["name"] for c in TL.with_the_intent(e, spec, ASK)["root_criteria"]]


def test_who_checks_a_part_is_heard_over_the_scopes_top(tmp_path):
    """The choice is heard where the person's words are read — over the top of the mode the node lies under, which in a
    shared graph is the stream's, never the author's root."""
    e = _shared(tmp_path)
    _split(e, X, ASK, HOLDER, HOLDER)
    assert TL.set_checker(e, ASK, user_said="проверяй", agent=HOLDER)["checker"] == "validator"
    assert [h["checker"] for h in e.heard_on(X) if h["act"] == "checker"] == ["validator"]
    assert not [h for h in e.heard_on("root") if h["act"] == "checker"]


def test_a_delivery_inside_the_scope_names_no_branch_of_the_shared_checkout(tmp_path):
    """Branch switching is off in a checkout the streams share: a delivery with nothing committed is told to commit
    where it works, not on the system's work branch."""
    repo = a_repository(tmp_path / "repo")
    e = _shared(tmp_path, workdir=repo)
    _split(e, X, ASK, HOLDER, HOLDER)
    assert not _call(CONSOLE, "signal", e, ASK, "ACCEPT", HOLDER).get("refused")
    (repo / "f.txt").write_text("v1\n")
    out = _call(CONSOLE, "signal", e, ASK, "DELIVER", HOLDER, result="f.txt written", self_validation="PASS")
    assert out.get("refused") and "where you work" in out["error"] and "gfso/p/work" not in out["error"], out


@pytest.mark.parametrize("asked", [False, True], ids=["by default", "asked again"])
def test_a_top_is_validated_by_the_projects_validator_whatever_he_chose(tmp_path, asked):
    """The project's validator observes a top he issued by itself on every delivery: by default, and where he asks
    for it again, which adds nothing to what is owed."""
    e = _shared(tmp_path)
    if asked:
        assert _call(PAGE, "set_checker", e, X, agent="user").get("checker") == "validator"
    _delivered(e, X, HOLDER)
    started, _ = _dispatch_validate(e, AgentRegistry(path=str(tmp_path / "agents.json")), {
        "verdict": "PASS", "failed_criteria": [], "per_criterion": []})
    assert f"validate:{X}" in started, started


# ── outside the scope: nothing changes ────────────────────────────────────────

def test_outside_the_scope_the_validator_starts_on_no_delivery(tmp_path):
    """The scope's validator is the project's: read project-wide, it validated every other stream's delivery unasked."""
    e = _shared(tmp_path)
    _delivered(e, "root.ui", "ui")
    started, _ = _dispatch_validate(e, AgentRegistry(path=str(tmp_path / "agents.json")), {
        "verdict": "PASS", "failed_criteria": [], "per_criterion": []})
    assert not any("root.ui" in s for s in started), started


def _readings(e) -> dict:
    """What each node outside the scope reads of who observes it and whether an observation binds."""
    return {n: (owed_observer(e.graph, t), e.observed_here(t.id), observation_binds(e.graph, t))
            for n in ("root", Y, "root.ui", "root.ui.k", "root.mine") if (t := e.graph.get_task(TaskId(n)))}


def test_outside_the_scope_every_reading_is_as_with_no_scope(tmp_path):
    """Outside, who observes a node and whether an observation binds read exactly as in the same graph unscoped: only
    what the system does by itself there is cut. Read through the scope, 86 nodes of the author's graph lost their
    observation and 87 their binding (critic over 0d46e7c)."""
    scoped, bare = _shared(tmp_path), _shared(tmp_path / "bare", scoped=False)
    for e in (scoped, bare):
        _split(e, "root.ui", "root.ui.k", "ui", "ui")
    assert _readings(scoped) == _readings(bare)


def test_outside_the_scope_a_validation_the_stream_asks_for_is_taken(tmp_path):
    """A stream's own request is answered as today: its node is the top of a scope no one session carries (§3.7), so
    `validate_result` observes it — never refused as "inside the scope of one executor session"."""
    e = _shared(tmp_path)
    _split(e, "root.ui", "root.ui.k", "ui", "ui")
    assert e.observed_here(TaskId("root.ui.k")) and e.observed_here(TaskId("root.ui"))
    assert not e.observes_by_itself(TaskId("root.ui.k")), "and nothing starts it unasked"
    assert e.checker(TaskId("root.ui")) == "independent" and e.checker(TaskId("root.ui.k")) == "self"


def test_outside_the_scope_an_observation_the_stream_asked_for_binds(tmp_path):
    """Nothing starts by itself outside, so every observation there was asked by the stream: an instrument FAIL on its
    own node is that criterion's value, as today (Inv-2), and its holder's hand PASS does not overrule it."""
    e = _shared(tmp_path)
    _split(e, "root.ui", "root.ui.k", "ui", "ui")
    T.signal(e, "root.ui", "ACCEPT", "ui")
    _delivered(e, "root.ui.k", "ui")
    e.record_exec_verdict(TaskId("root.ui.k"), "FAIL", ["k"], "p-val", per_criterion=[
        {"criterion": "k", "verdict": "fail", "evidence": "ran check k: it printed NO", "divergences": ["printed NO"]}])
    with contextlib.suppress(ValueError):        # …refused at the record door where the FAIL binds
        T.record_verdict(e, "root.ui.k", "PASS", reviewer="ui",
                         observed={"k": {"note": "ran check k myself: it printed OK", "ran": ["check k"]}})
    assert not T.signal(e, "root.ui.k", "PASS", "ui").get("accepted"), "the holder's own record overruled the FAIL"


def test_outside_the_scope_an_internal_node_closes_on_its_holders_self_check(tmp_path):
    """As with no mode: the executor's word is the only record there is (§10.3), the scope's validator notwithstanding."""
    e = _shared(tmp_path)
    _split(e, "root.ui", "root.ui.k", "ui", "ui")
    T.signal(e, "root.ui", "ACCEPT", "ui")
    _delivered(e, "root.ui.k", "ui")
    assert T.signal(e, "root.ui.k", "PASS", "ui")["state"] == "DONE"


def test_outside_the_scope_no_instrument_is_bound_to_a_node_the_standing_agent_issues(tmp_path):
    """A registered instrument signs for an automated issuer (`validated_by_instrument`): outside the scope its
    validator is no hand of the standing agent's, or the node would read "an independent validator is bound … wait"."""
    e = _shared(tmp_path)
    _split(e, "root.mine", "root.mine.k", "bob", "user")
    assert not e.validated_by_instrument(TaskId("root.mine.k"))


def test_outside_the_scope_a_restart_stops_nothing(tmp_path):
    """«перезапуск ничего ломать не может»: a solo in_chat scope starts no session, and its validator — the instrument
    of no one outside it — is no hands of the system's there, so the author's graph runs on after a restart."""
    e = _shared(tmp_path)
    T.signal(e, "root.mine", "ACCEPT", "user")
    assert e.workforce.has_an_instrument()
    assert not e.system_starts_sessions()


def test_outside_the_scope_the_go_and_the_verdict_read_as_with_no_mode(tmp_path):
    """No person's-word guard reaches the other streams: their tops ask no words and close on their issuer's signature."""
    e = _shared(tmp_path)
    assert not e.issued_by_the_person(TaskId("root.ui")) and not e.persons_verdict("root.ui")
    assert not TL.TOOLS["edit_criteria"](e, "root.ui", [criterion("ui2")], agent=AUTHOR).get("refused"), \
        "another stream's packet asked the person's words"
    _split(e, "root.ui", "root.ui.k", "ui", "ui")
    assert not e.issued_by_the_person(TaskId("root.ui.k")) and not e.issued_by_the_person(TaskId("root"))


# ── the person's stream: one scope at the node he holds, a top at every seam he issues below it ─────────────────────

DIRS, TASK = ("root.stream.a", "root.stream.b", "root.stream.c"), "root.stream.a.t"


def _stream(tmp_path, scoped: bool = True, storage=None):
    """The dev graph's shape: the author's root → the stream node Y, its Del moved to the person by a re-ASSIGN → three
    directions held by `engineering`, tasks under the first two — and, where `scoped`, `engineering` working in its
    chat (`_in_its_chat`)."""
    e = make_engine(validate_signals=True, state_timeout=0, **({"storage": storage} if storage else {}))
    e.start()
    e.project_name = "p"
    T.create_task(e, "root", {"description": "the author's goal", "criteria": [criterion("g")]}, assignee=AUTHOR,
                  agent=AUTHOR)
    _split(e, "root", Y, HOLDER, AUTHOR)
    T.decompose(e, Y, [{"task_id": d, "spec": {"description": d, "criteria": [criterion(d[-1])]}, "assignee": HOLDER,
                        "covers": ["k"]} for d in DIRS], accepted_risks=REGISTER, agent=HOLDER)
    e.wait_idle()
    for d in DIRS[:2]:
        _split(e, d, f"{d}.t", HOLDER, HOLDER)
    assert not T.reassign(e, Y, "user", agent=AUTHOR).get("error")
    e.wait_idle()
    if scoped:
        _in_its_chat(e, tmp_path)
    ensure_dispatcher(e).stop()
    return e


def _top(e, n):
    at = e.scope_at(n)
    return at and at.get("top")


def test_each_seam_he_issues_under_the_node_is_a_top_and_his_node_has_none(tmp_path):
    """`mode_at(t)` = (record, the nearest node at or above t under Y issued by him to another): every direction is
    its own top, a task under it lies under its direction, and Y — his own work — lies under no mode."""
    e = _stream(tmp_path)
    assert [_top(e, d) for d in DIRS] == list(DIRS)
    assert _top(e, TASK) == DIRS[0]
    assert e.mode_at(TaskId(Y)) is None and e.scope_at(Y) is None
    assert [e.issued_by_the_person(TaskId(d)) for d in DIRS] == [True] * 3
    assert not e.issued_by_the_person(TaskId(Y)) and not e.issued_by_the_person(TaskId(TASK))


def test_the_holder_of_each_top_is_its_del(tmp_path):
    """The holder is Del(top) as its ASSIGN gave it, not Y's: read off Y, every task of the stream went to the person."""
    e = _stream(tmp_path)
    assert str(e.del_for(TaskId(DIRS[2]))) == HOLDER and str(e.del_for(TaskId(TASK))) == HOLDER
    _split(e, DIRS[2], f"{DIRS[2]}.t", None, HOLDER)
    assert str(e.graph.get_task(TaskId(f"{DIRS[2]}.t")).assignee) == HOLDER


def test_the_name_taken_in_a_chat_changes_no_packet(tmp_path):
    """Its record is no revision of anyone's contract (§6.1 point 3): no criterion is installed, no version issued."""
    e = _stream(tmp_path, scoped=False)
    packets = {str(t.id): (t.spec, len(e.audit_log(t.id))) for t in e.all_tasks()}
    e.performs_in_chat(HOLDER)
    assert {str(t.id): (t.spec, len(e.audit_log(t.id))) for t in e.all_tasks()} == packets
    assert [_top(e, d) for d in DIRS] == list(DIRS)


def test_his_pass_at_a_direction_is_his_page_or_his_words(tmp_path):
    """The verdict at a top is its issuer's (§10.2), and its issuer is him: a connection signing as his name with no
    words of his is refused; his page signs as itself."""
    e = _stream(tmp_path)
    d = DIRS[2]
    _delivered(e, d, HOLDER)
    instrument_passes(e, TaskId(d), validator="p-val")
    refused = _call(ISSUER, "signal", e, d, "PASS", "user")
    assert refused.get("refused") and "user_said" in refused["error"], refused
    assert _call(PAGE, "signal", e, d, "PASS", "user")["state"] == "DONE"


def test_an_issuer_move_at_a_top_needs_his_words(tmp_path):
    """Every issuer move at a top is his (b03ce19's guard, keyed on the tops): its packet and its re-issue too."""
    e = _stream(tmp_path)
    no = _call(ISSUER, "edit_criteria", e, DIRS[2], [criterion("asked")])
    assert no.get("refused") and "user_said" in no["error"], no
    assert _call(ISSUER, "reassign", e, DIRS[2], "ui").get("refused")


def test_inside_a_top_the_checker_is_the_holders_choice_and_its_pass_needs_no_words_of_his(tmp_path):
    """Below a top the issuer is its holder (§10.3): who checks an inner task is engineering's choice, no words of the
    person's, and its PASS on the validator's record is its own."""
    e = _stream(tmp_path)
    T.signal(e, DIRS[0], "ACCEPT", HOLDER)
    out = _call(CONSOLE, "set_checker", e, TASK, agent=HOLDER)
    assert out.get("checker") == "validator", out
    _delivered(e, TASK, HOLDER)
    instrument_passes(e, TaskId(TASK), validator="p-val")
    assert _call(CONSOLE, "signal", e, TASK, "PASS", HOLDER)["state"] == "DONE"


def test_a_direction_he_adds_later_is_a_top_carrying_the_criterion_his_act_installs(tmp_path):
    """His ASSIGN of a new direction is his act on it: it becomes a top, and the criterion read against his words comes
    with that ASSIGN where `intent_check` holds — never by a move of the system's afterwards."""
    e = _stream(tmp_path)
    d = "root.stream.d"
    out = _call(PAGE, "decompose", e, Y, [{"task_id": d, "spec": {"description": d, "criteria": [criterion("d")]},
                                           "assignee": HOLDER, "covers": ["k"]}], accepted_risks=REGISTER, agent="user")
    assert not (isinstance(out, dict) and out.get("error")), out
    assert _top(e, d) == d and e.issued_by_the_person(TaskId(d))
    assert INTENT in [c.name for c in e.graph.get_task(TaskId(d)).spec.criteria]


def test_his_revision_of_a_top_installs_the_criterion_and_its_holder_maps_it(tmp_path):
    """A revision he makes of a direction is his act on it: the criterion comes with it, unmapped — CHECK-1 flags it at
    the revision (§12.10), and the direction's holder maps it by its own re-admission."""
    e = _stream(tmp_path)
    d = e.graph.get_task(TaskId(DIRS[0]))
    _call(PAGE, "edit_criteria", e, DIRS[0], TL.its_criteria(d) + [criterion("asked")], agent="user",
          user_said=WORDS)
    d = e.graph.get_task(TaskId(DIRS[0]))
    assert INTENT in [c.name for c in d.spec.criteria]
    assert INTENT not in {m.criterion_name for m in d.criterion_mappings}, "the system mapped it in the holder's name"


def test_the_persons_words_at_a_top_are_its_packet_and_what_he_said_over_his_stream(tmp_path):
    """`persons_words(top)` = the top's packet as issued + the words heard over Y and above it (§6.1 point 3)."""
    e = _stream(tmp_path)
    e.hear(Y, "revise", "сначала инженерка")
    e.hear("root", "request", "весь проект")
    d = e.graph.get_task(TaskId(DIRS[2]))
    _call(PAGE, "edit_criteria", e, DIRS[2], TL.its_criteria(d), agent="user", user_said=WORDS)
    words = e.persons_words(e.graph.get_task(TaskId(DIRS[2])))
    assert words and {"сначала инженерка", "весь проект", DIRS[2]} <= set(words), words


def _his(e, n, held):
    """A node he issues under Y from his page, to `held`."""
    return _call(PAGE, "decompose", e, Y, [{"task_id": n, "spec": {"description": n, "criteria": [criterion(n[-1])]},
                                            "assignee": held, "covers": ["k"]}], accepted_risks=REGISTER, agent="user")


def test_his_revision_of_the_node_he_holds_is_heard_there_and_read_at_each_top(tmp_path):
    """His redirections are revisions of Y's criteria (his decision of 11-12): made from his page, or with his words,
    they are heard over Y, so the criterion read against his words at a top quotes them (§6.1 point 3)."""
    e = _stream(tmp_path)
    _his(e, "root.stream.d", HOLDER)
    y = e.graph.get_task(TaskId(Y))
    out = _call(PAGE, "edit_criteria", e, Y, TL.its_criteria(y) + [criterion("first", "сначала инженерка, потом ui")],
                agent=AUTHOR)
    assert not out.get("refused"), out
    assert "сначала инженерка, потом ui" in e.persons_words(e.graph.get_task(TaskId("root.stream.d")))
    y = e.graph.get_task(TaskId(Y))
    authors = Principal(AUTHOR, (AUTHOR,), "tok-author", "token")
    assert not _call(authors, "edit_criteria", e, Y, TL.its_criteria(y) + [criterion("second")], agent=AUTHOR,
                     user_said="и тесты зелёные").get("refused")
    assert "и тесты зелёные" in e.persons_words(e.graph.get_task(TaskId("root.stream.d")))


def test_a_reassign_that_makes_a_top_installs_the_criterion_as_the_other_doors_do(tmp_path):
    """Moving a node of his under Y to another makes it a top by his act (a revision he makes, §12.3): the criterion
    read against his words comes with it, as with a first ASSIGN."""
    e = _stream(tmp_path)
    n = "root.stream.mine"
    _his(e, n, "user")
    assert INTENT not in [c.name for c in e.graph.get_task(TaskId(n)).spec.criteria] and not e.scope_at(n)
    out = _call(PAGE, "reassign", e, n, HOLDER, agent="user")
    assert not (isinstance(out, dict) and (out.get("refused") or out.get("error"))), out
    assert _top(e, n) == n and INTENT in [c.name for c in e.graph.get_task(TaskId(n)).spec.criteria]


def test_a_seam_issued_to_a_registered_machine_is_no_top(tmp_path):
    """`in_chat` performs in a chat; a machine executes by dispatch, and takes no name in one (`signin.take`): a seam he
    issues to it is his seam, held by no chat."""
    e = _stream(tmp_path)
    assert not TL.register_agent(e, "p-exec", "llm-executor", workdir=str(tmp_path)).get("refused")
    _his(e, "root.stream.m", "p-exec")
    assert e.issued_by_the_person(TaskId("root.stream.m")) and not e.scope_at("root.stream.m")


def test_a_server_start_leaves_a_scoped_project_running_beside_a_registered_executor(tmp_path, monkeypatch):
    """«перезапуск ничего ломать не может»: with a scope, a live node whose Del or issuer is the person's name is his,
    never the system's, whatever executors the project has — so Y, held by `user`, does not stop the project."""
    data = tmp_path / "data"
    data.mkdir()
    e = _stream(tmp_path, storage=SqliteStorage(str(data / "p.db")))
    assert not TL.register_agent(e, "p-exec", "llm-executor", workdir=str(tmp_path)).get("refused")
    assert e.workforce.executor_pool()
    e.stop()
    monkeypatch.setenv("GFSO_DATA_DIR", str(data))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv(SERVES_ENV, "1")
    assert ProjectRegistry().engine("p").paused() is None


# ── his page, by the bodies it sends ──────────────────────────────────────────

def _page(e, verb, **body) -> dict:
    """`POST /api/run/<verb>` from his signed-in page: the body as the page writes it, no name and no `user_said` —
    the door signs it as the session (`server.run_tool`)."""
    out = _call(PAGE, verb, e, **body)
    return out if isinstance(out, dict) else {"answer": out}


def _took(out):
    assert not (out.get("refused") or out.get("error")), out


def test_his_page_revises_a_tops_criteria_as_its_edit_form_sends_them(tmp_path):
    """author.js `submitEdit`: `{task_id, criteria}`. The page signed in as him is his act, his words what he typed
    there: heard at the top as the criteria he wrote."""
    e = _stream(tmp_path)
    d = e.graph.get_task(TaskId(DIRS[0]))
    _took(_page(e, "edit_criteria", task_id=DIRS[0],
                criteria=TL.its_criteria(d) + [criterion("logs", "и логи пишутся в файл")]))
    assert "и логи пишутся в файл" in e.persons_words(e.graph.get_task(TaskId(DIRS[0])))


def test_his_page_moves_a_tops_deadline(tmp_path):
    """A deadline is a packet field (Inv-1): his page revising it is his act, as for the criteria — the time as the
    page writes every deadline (forms.js `iso`: `toISOString()`, UTC)."""
    e = _stream(tmp_path)
    at = "2099-01-01T12:00:00.000Z"
    _took(_page(e, "revise", task_id=DIRS[2], deadline=at))
    assert e.graph.get_task(TaskId(DIRS[2])).deadline.year == 2099


def test_his_page_revises_his_solo_root_as_its_edit_form_sends_it(tmp_path):
    """The same guard at the root of his solo project: the page is his act there too."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.set_mode(Mode.SOLO, None, AgentId("user"))
    _took(_page(e, "create_task", spec={"name": "g", "description": "the goal", "criteria": [criterion("g")],
                                        "scope": [], "accepted_risks": []}, deadline=None))
    root = e.all_tasks()[0]
    _took(_page(e, "edit_criteria", task_id=str(root.id),
                criteria=TL.its_criteria(root) + [criterion("more", "и ещё README")]))
    assert "more" in [c.name for c in e.graph.get_task(root.id).spec.criteria]


def test_his_stream_level_criterion_reaches_a_direction_from_his_page(tmp_path):
    """§12.10, §11.5: he adds a criterion to Y from his page → CHECK-1 flags it uncovered at Y → his frontier names
    that as his step at Y → his page re-admits Y's split mapping it onto a standing direction → the direction is
    re-issued once with it in its packet, its holder consenting again, and the words read at it carry his."""
    e = _stream(tmp_path)
    y = e.graph.get_task(TaskId(Y))
    _took(_page(e, "edit_criteria", task_id=Y, criteria=TL.its_criteria(y) + [criterion("first", "сначала логи")]))
    steps = [s for s in _page(e, "next_steps")["steps"] if s.get("task_id") == Y]
    assert any("first" in str(s) and str(s.get("performed_by")) in PAGE.signs_as for s in steps), steps
    assigns = len([x for x in e.audit_log(TaskId(DIRS[0])) if x.signal.name == "ASSIGN" and not x.rejected])
    # author.js `submitDecompose`: no new child, every criterion's select sent — the standing mapping preselected
    _took(_page(e, "decompose", parent_id=Y, children=[],
                accepted_risks=[{"denial": True, "p": 0.1, "justification": "the directions stand as split"}],
                mappings=[{"criterion_name": "k", "child_id": DIRS[0]}, {"criterion_name": "first", "child_id": DIRS[0]}]))
    e.wait_idle()
    d = e.graph.get_task(TaskId(DIRS[0]))
    assert "сначала логи" in [c.description for c in d.spec.criteria], d.spec.criteria
    assert len([x for x in e.audit_log(d.id) if x.signal.name == "ASSIGN" and not x.rejected]) == assigns + 1
    assert d.state.name == "OFFERED", d.state
    assert "сначала логи" in e.persons_words(d)
    assert not [s for s in _page(e, "next_steps")["steps"] if s.get("task_id") == Y and "first" in str(s)]


# ── a scope an earlier build recorded ─────────────────────────────────────────

def test_a_scope_an_earlier_build_recorded_reads_its_holders_as_working_in_a_chat(tmp_path):
    """A graph scoped before the button was retired keeps its tops: the scope said its seams' holders work in a chat."""
    e = _stream(tmp_path, scoped=False)
    e._storage.store_setting(MODE_SCOPES, json.dumps({Y: {"node": Y, "mode": "solo", "perform": "in_chat",
                                                          "by": "user", "at": "2026-11-20T17:00:00"}}))
    assert [_top(e, d) for d in DIRS] == list(DIRS) and HOLDER in in_chat_names(e.graph)
