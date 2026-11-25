"""What the page says of the graph is its record's, nothing it does not hold: what is in work (taken by the log, its
holder, since when), who a node waits on and why (a producer, its open parts, and on a delivered node the engine's own
`awaiting`), and who checks a node (the record's `checker`). The page's modules run under node on recorded graphs and
logs (tests/page_in_node.mjs); what only a look judges is the person's acceptance, not this."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="the page's modules run under node")


def run(tmp_path, body):
    script = tmp_path / "case.mjs"
    script.write_text(f"import {{page, say}} from {json.dumps((HERE / 'page_in_node.mjs').as_uri())};\n{body}\n",
                      encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def waits(tmp_path, nodes, edges=(), steps=None):
    """`steps`: {node: role} as next_steps sends them — None: as the engine does, the issuer's role on every delivered
    node not being checked now (a check in course has no step: the page gives it the validator's, model.js)."""
    if steps is None:
        steps = {n["id"]: "validator" if n.get("awaiting") == "validator" else "issuer"
                 for n in nodes if n.get("state") == "VALIDATING"}
    return run(tmp_path, f"""const {{waitsOf}} = await import(page('run.js'));
const {{waitWords}} = await import(page('hints.js'));
const steps = new Map(Object.entries({json.dumps(steps)}).map(([id, role]) => [id, {{task_id: id, role}}]));
const w = waitsOf({json.dumps(nodes)}, {json.dumps(list(edges))}, null, steps);
say(Object.fromEntries(Object.entries(w).map(([id, x]) => [id, {{owes: x.owes, decides: x.decides, who: x.who || '',
    words: waitWords(x, d => d, x.who || '')}}])));""")


# ── who a delivered node waits on: the engine's word ──

def test_a_delivered_node_waits_on_whom_the_engine_says(tmp_path):
    v = lambda i, a: {"id": i, "parent_id": "top", "state": "VALIDATING", "awaiting": a}
    said = waits(tmp_path, [{"id": "top", "state": "EXECUTING"}, v("run", "validator"), v("none", "verdict"),
                            v("his", "issuer"), v("named", "rdl-checker")])
    assert said["run"] == {"owes": "validator", "decides": None, "who": "", "words": "the validator"}
    # «verdict» names no one: the step's role stands, and whether it is his to have checked is the strip's reading below
    assert said["none"] == {"owes": "issuer", "decides": None, "who": "", "words": "the issuer"}
    assert said["his"] == {"owes": "issuer", "decides": "issuer", "who": "", "words": "the issuer"}
    assert said["named"] == {"owes": "checker", "decides": "checker", "who": "rdl-checker",
                             "words": "the checker (rdl-checker)"}


def test_an_older_engine_that_says_nothing_leaves_the_states_owner(tmp_path):
    said = waits(tmp_path, [{"id": "top", "state": "EXECUTING"}, {"id": "n", "parent_id": "top", "state": "VALIDATING"}],
                 steps={})
    assert said["n"]["owes"] == "issuer" and said["n"]["decides"] is None       # a verdict in course, not his decision


# ── the deck's two lists: in work, and on the issuer — never both ──

def lists(tmp_path, mode, top_holder):
    """The deck's two lists (deck.js reads `inWorkOf` and `isOnTheIssuer`, naming by `onTheIssuer`), on every word the
    engine says of a delivered node and the steps next_steps lists beside them."""
    nodes = [{"id": "top", "state": "EXECUTING", "assignee": top_holder},
             *({"id": i, "parent_id": "top", "state": "VALIDATING", "assignee": "ex", "awaiting": a}
               for i, a in [("run", "validator"), ("none", "verdict"), ("his", "issuer"), ("named", "rev")])]
    steps = {"none": "issuer", "his": "issuer", "named": "issuer"}
    return run(tmp_path, f"""const {{S, inWorkOf, isOnTheIssuer, onTheIssuer}} = await import(page('state.js'));
const {{waitsOf}} = await import(page('run.js'));
const nodes = {json.dumps(nodes)};
const steps = new Map(Object.entries({json.dumps(steps)}).map(([id, role]) => [id, {{task_id: id, role}}]));
S.tasks = nodes; S.graph = {{nodes, edges: [], parties: [], mode: {json.dumps(mode)}}};
const at = {{lit: () => false, carrier: () => [], work: new Set(), on: () => null}};
S.run = {{audit: [], now: at}};
const w = waitsOf(nodes, [], null, steps);
say({{work: inWorkOf(nodes).map(h => h.t.id),
      issuer: nodes.filter(t => isOnTheIssuer(t, w[t.id], at)).map(t => [t.id, onTheIssuer(t, w[t.id])])}});""")


def test_a_delivered_node_is_in_work_or_on_someone_never_both(tmp_path):
    # a person's graph: a delivery no check runs on is his to have checked (no validator may be registered: the engine's
    # «verdict» says the same either way), his own check and an appointed party's are on them; a running check is work
    said = lists(tmp_path, None, "user")
    assert said["work"] == ["run"]
    assert said["issuer"] == [["none", "user"], ["his", "user"], ["named", "rev"]]
    # …under AUTO the system starts the check: that delivery is the system's work, on no one
    said = lists(tmp_path, {"mode": "auto"}, "user")
    assert said["work"] == ["run", "none"]
    assert [i for i, _ in said["issuer"]] == ["his", "named"]
    assert not set(said["work"]) & {i for i, _ in said["issuer"]}


def test_a_producer_and_open_parts_come_before_any_owner(tmp_path):
    nodes = [{"id": "top", "state": "EXECUTING"}, {"id": "a", "parent_id": "top", "state": "EXECUTING"},
             {"id": "b", "parent_id": "top", "state": "OFFERED"}, {"id": "a1", "parent_id": "a", "state": "OFFERED"}]
    said = waits(tmp_path, nodes, [{"source": "a", "target": "b", "type": "dep"}])
    assert said["b"]["words"] == "a" and said["a"]["words"] == "its 1 open part"


def test_a_delivery_owed_to_a_person_or_a_named_party_is_on_them(tmp_path):
    said = run(tmp_path, """const {owedTo} = await import(page('run.js'));
say(['issuer', 'rdl-checker', 'validator', 'verdict', null].map(a => owedTo({state: 'VALIDATING', awaiting: a}))
    .concat([owedTo({state: 'VALIDATING'}), owedTo({state: 'EXECUTING', awaiting: 'executor'})]));""")
    assert said == [True, True, False, None, None, None, None]


def test_every_view_says_it_through_the_one_reading():
    """The views are drawn, not run here: read as text, each says who waits through the readings tested above and keeps
    no rule of its own — the strip's lists by `isOnTheIssuer`/`onTheIssuer`, the tip and the panel by the wait's role."""
    js = lambda f: (HERE.parent / "gfso" / "web" / "js" / f).read_text(encoding="utf-8")
    deck, graph, panel = js("deck.js"), js("graph.js"), js("panel.js")
    assert "isOnTheIssuer(t, run?.waits[t.id], at)" in deck and "onTheIssuer(t, run?.waits[t.id])" in deck
    assert "whoOwes(t, w.owes)" in graph and "whoOwes(taskOf(d.id), w?.owes)" in panel
    for name, text in [("deck.js", deck), ("graph.js", graph), ("panel.js", panel)]:
        assert "decides === 'issuer'" not in text and "whoOwes(t, 'issuer')" not in text, name


# ── what is in work: the log's ──

def test_in_work_is_the_log_its_holder_and_since_when(tmp_path):
    said = run(tmp_path, """const {inWork} = await import(page('run.js'));
const tasks = [{id: 'top', state: 'EXECUTING', assignee: 'user'},
               {id: 'a', parent_id: 'top', state: 'EXECUTING', assignee: 'ui-draft'},
               {id: 'b', parent_id: 'top', state: 'VALIDATING', assignee: 'engineering'},
               {id: 'c', parent_id: 'top', state: 'OFFERED', assignee: 'ui-draft'}];
const audit = [{task_id: 'a', new_state: 'OFFERED', t: 1}, {task_id: 'a', new_state: 'EXECUTING', t: 5},
               {task_id: 'b', new_state: 'VALIDATING', t: 7}];
const at = {lit: () => false};
say([inWork(tasks, audit, at).map(h => [h.t.id, h.holder, h.since]),
     inWork(tasks, audit, at, t => t.id === 'b').map(h => h.t.id)]);""")
    # the top waits on its parts, so the parts say it; a delivery owed to a person's verdict is on him, not in work
    assert said == [[["a", "ui-draft", 5], ["b", "engineering", 7]], ["a"]]


# ── who checks: the record's checker ──

def test_who_checks_is_the_records_checker_in_words(tmp_path):
    said = run(tmp_path, """const {S} = await import(page('state.js'));
const {checkRow} = await import(page('panel.js'));
const at = checker => { const node = {id: 'n', parent_id: 'top', assignee: 'ex', state: 'EXECUTING', checker};
    S.tasks = [{id: 'top', assignee: 'user'}, node]; S.graph = {nodes: [], parties: []}; S.me = {signs_as: []};
    S.validatorModel = {model: 'claude-haiku-5-5'}; return checkRow(node)[1]; };
say([at('validator'), at('rdl-checker')]);""")
    assert said == ["the validator, haiku 5.5", "rdl-checker"]
