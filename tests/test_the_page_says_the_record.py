"""What the page says of a node is the record's, in words: who checks it and on which model, why no move is offered, how a
move was signed, and how many events a filter holds. The page's own modules are run under node on recorded data
(tests/page_in_node.mjs) — no browser runs in the suite, so what only a look judges (the frame, a press) is the person's
acceptance, not this."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="the page's modules run under node")


def run(tmp_path, body):
    """`body`: module code after the stubs are in place; it ends by `say(<value>)`."""
    script = tmp_path / "case.mjs"
    script.write_text(f"import {{page, say}} from {json.dumps((HERE / 'page_in_node.mjs').as_uri())};\n{body}\n",
                      encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


# ── who checks, and on which model ──

def checker(tmp_path, node, vr=None, validator_model=None):
    return run(tmp_path, f"""
const {{S}} = await import(page('state.js'));
const {{checkRow}} = await import(page('panel.js'));
const node = {json.dumps(node)};
S.tasks = [{{id: 'top', assignee: 'issuer'}}, node]; S.graph = {{nodes: [], parties: []}}; S.me = {{signs_as: []}};
S.validatorModel = {json.dumps(validator_model)};
say(checkRow(node, {json.dumps(vr)}));""")


def test_an_open_node_the_validator_checks_names_the_model_it_will_run_on(tmp_path):
    node = {"id": "n", "parent_id": "top", "assignee": "ex", "state": "EXECUTING", "checker": "validator"}
    assert checker(tmp_path, node, validator_model={"model": "claude-haiku-5-5"}) == ["Checker", "the validator, haiku 5.5"]
    assert checker(tmp_path, node, validator_model={"model": "claude-sonnet-5-5", "byDefault": True}) \
        == ["Checker", "the validator, sonnet 5.5 by default"]


def test_a_closed_node_names_the_model_of_the_verdict_that_closed_it(tmp_path):
    node = {"id": "n", "parent_id": "top", "assignee": "ex", "state": "DONE",
            "closure": {"validator": "validate_result", "provenance": "instrument"}}
    assert checker(tmp_path, node, vr={"validator_model": "claude-sonnet-5-5"}) == ["Checker", "the validator, sonnet 5.5"]
    # …the closing verdict, where a later record landed on top of it: a self-report carries no model, so none is named
    assert checker(tmp_path, node, vr={"validator_model": "claude-sonnet-5-5", "closed_on": {"validator": "ex"}}) \
        == ["Checker", "the validator"]


def test_the_validators_model_is_the_one_the_engine_picks(tmp_path):
    def of(agents, server="claude-sonnet-5-5"):
        return run(tmp_path, f"""const {{validatorModelOf}} = await import(page('state.js'));
say(validatorModelOf({json.dumps(agents)}, 'p', {json.dumps(server)}));""")
    assert of({}) == {"model": "claude-sonnet-5-5", "byDefault": True}
    assert of({"p-val": {"kind": "llm-validator", "model": "claude-haiku-5-5", "project": "p"}}) == {"model": "claude-haiku-5-5"}
    assert of({"shared": {"kind": "llm-validator", "model": "claude-haiku-5-5"}}) == {"model": "claude-haiku-5-5"}
    assert of({"other": {"kind": "llm-validator", "model": "claude-haiku-5-5", "project": "q"}})["byDefault"] is True
    assert of({"p-val": {"kind": "llm-validator", "project": "p"}}) == {"model": "claude-sonnet-5-5"}
    assert of({"p-ut": {"kind": "unittest-checker", "project": "p"}}) == {"model": None}


# ── why no move, each reason once ──

def test_a_closed_node_says_its_refusal_once(tmp_path):
    refusal = "ASSIGN is refused here: the node is CONSUMED."
    said = run(tmp_path, f"""const {{refusals}} = await import(page('panel.js'));
say([refusals({{withheld: {{ASSIGN: {json.dumps(refusal)}}}, why_none: {json.dumps(refusal)}}}, false),
     refusals({{withheld: {{ASSIGN: 'a'}}, why_none: 'b'}}, false),
     refusals({{withheld: {{}}, why_none: 'b'}}, true)]);""")
    assert said == [[refusal], ["a", "b"], []]


# ── how a move was signed ──

def test_how_a_move_signed_is_said_in_words(tmp_path):
    said = run(tmp_path, """const {viaWord} = await import(page('state.js'));
say(['as:13b1ecacc30f', 'tok9', 'session', 'local-peer', 'default', ''].map(viaWord));""")
    assert said == ["by its connection", "by its token", "on the page", "on the page", "by a local client", ""]
    assert not any("as:" in w for w in said)


# ── what the Events filter holds ──

def test_an_events_chip_counts_what_the_search_finds(tmp_path):
    said = run(tmp_path, """const {kindCount} = await import(page('events.js'));
const by = {a: [{kind: 'verdict', a: {signal: 'PASS', task_id: 'checker one'}}, {kind: 'verdict', a: {signal: 'FAIL', task_id: 'other'}}],
            b: [{kind: 'assignment', a: {signal: 'ASSIGN', task_id: 'checker two'}}]};
say([kindCount(by, 'verdict', null, ''), kindCount(by, 'verdict', null, 'checker'), kindCount(by, 'assignment', 'a', ''),
     kindCount(by, 'assignment', null, 'checker')]);""")
    assert said == [2, 1, 0, 1]
