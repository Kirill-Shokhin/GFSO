"""Who checks a node is said before any check, and its issuer appoints the checker from the page (the author, 11-24:
«надо понимать кто проверяющий еще до проверки … назначать через интерфейс — для общего случая»): the engine's own
choices for the caller (get_task `checker_choices`), anyone else by name, sent as the engine's `set_checker`; the verdict
shown is the appointee's record, others' records beside it. The page's modules run under node on recorded data
(tests/page_in_node.mjs); how the list looks and a press on it are the person's acceptance, not this."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
WEB = HERE.parent / "gfso" / "web" / "js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="the page's modules run under node")


def run(tmp_path, body):
    script = tmp_path / "case.mjs"
    script.write_text(f"import {{page, say}} from {json.dumps((HERE / 'page_in_node.mjs').as_uri())};\n{body}\n",
                      encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def panel(tmp_path, node, signs_as=("user",), moves=None, vr=None):
    """The panel's appointment and Checker row for `node` (its issuer `user`), signed as `signs_as`."""
    moves = {"set_checker": "user"} if moves is None else moves
    return run(tmp_path, f"""const {{S}} = await import(page('state.js'));
const {{checkSetting, checkRow, besideTheRecord}} = await import(page('panel.js'));
const node = {json.dumps(node)};
S.tasks = [{{id: 'top', assignee: 'user'}}, node]; S.graph = {{nodes: [], parties: []}};
S.me = {{signs_as: {json.dumps(list(signs_as))}}}; S.validatorModel = {{model: 'claude-haiku-5-5'}};
say({{html: checkSetting({{d: node, acts: {{moves: {json.dumps(moves)}}}}}), row: checkRow(node, null)[1],
      beside: besideTheRecord({json.dumps(vr)})}});""")


def options(html):
    return re.findall(r'<option value="([^"]*)"( selected)?>([^<]*)</option>', html)


def test_who_checks_is_said_before_any_check(tmp_path):
    node = {"id": "n", "parent_id": "top", "assignee": "ex", "state": "EXECUTING", "checker": "rev"}
    assert panel(tmp_path, node)["row"] == "rev"
    node["checker"] = "validator"
    assert panel(tmp_path, node)["row"] == "the validator, haiku 5.5"


def test_its_issuer_appoints_from_the_engines_choices_or_anyone_by_name(tmp_path):
    node = {"id": "n", "parent_id": "top", "assignee": "ex", "state": "EXECUTING", "checker": "validator",
            "checker_choices": ["validator", "self", "engineering"]}
    html = panel(tmp_path, node)["html"]
    assert options(html) == [("validator", " selected", "the validator, haiku 5.5"), ("self", "", "you, its issuer"),
                             ("engineering", "", "engineering"), ("", "", "someone else, by name…")]
    assert 'data-change="set-checker"' in html and 'data-id="n"' in html and 'data-was="validator"' in html
    # …the standing appointment kept in the list where the engine no longer offers it
    node.update(checker="rev")
    assert [v for v, *_ in options(panel(tmp_path, node)["html"])] == ["validator", "self", "engineering", "rev", ""]


def test_no_list_where_the_page_does_not_sign_the_move_or_the_engine_offers_none(tmp_path):
    node = {"id": "n", "parent_id": "top", "assignee": "ex", "state": "EXECUTING", "checker_choices": ["validator", "self"]}
    assert panel(tmp_path, node, signs_as=("ex",))["html"] == ""             # the executor never appoints its checker
    assert panel(tmp_path, node, moves={})["html"] == ""                     # the engine names no such move here
    assert panel(tmp_path, {**node, "checker_choices": []})["html"] == ""    # a seam: no choice (get_task omits it)
    assert panel(tmp_path, {**node, "parent_id": None})["html"] == ""        # the goal has no issuer in the graph


def verdict_line(tmp_path, vr):
    """The panel's verdict line as it draws it (`verdict`), the project's validator registered as `p-val`."""
    return run(tmp_path, f"""const {{S, takeRoster}} = await import(page('state.js'));
const {{verdict}} = await import(page('panel.js'));
S.tasks = []; S.graph = {{nodes: [], parties: []}}; S.me = {{signs_as: []}};
takeRoster({{'p-val': {{kind: 'llm-validator', project: 'p'}}, 'p-oracle': {{kind: 'unittest-checker', project: 'p'}},
             rev: {{kind: 'human'}}}}, 'claude-sonnet-5-5');
say(verdict({{vr: {json.dumps(vr)}}}));""")


def test_others_records_stand_beside_the_appointees(tmp_path):
    others = [{"validator": "p-val", "verdict": "FAIL", "failed_criteria": ["d", "e"], "by_hand": False, "ts": None},
              {"validator": "validate_result", "verdict": "PASS", "by_hand": False, "ts": None},
              {"validator": "ex", "verdict": "PASS", "by_hand": True, "ts": None}]
    beside = ["Beside it: FAIL on d, e — the validator", "Beside it: PASS — the validator", "Beside it: PASS — ex, by hand"]
    # …under the appointee's own record, which alone is the verdict
    html = verdict_line(tmp_path, {"verdict": "PASS", "validator": "rev", "checker": "rev", "others": others})
    assert re.findall(r"<b>(PASS|FAIL)</b>", html) == ["PASS"] and re.findall(r"Beside it: [^<]*", html) == beside
    # …and before the appointee recorded: no verdict, the validator's FAIL standing beside nothing
    html = verdict_line(tmp_path, {"verdict": None, "validator": None, "checker": "rev", "others": others})
    assert "<b>" not in html and re.findall(r"Beside it: [^<]*", html) == beside
    assert "Beside it" not in verdict_line(tmp_path, {"verdict": "PASS", "validator": "p-val"})


def test_the_systems_validator_is_named_as_such_on_every_line(tmp_path):
    # …whatever role it signed under: the verdict of record when it is the appointee, and a record beside another's
    for who in ("p-val", "p-oracle", "validate_result"):
        html = verdict_line(tmp_path, {"verdict": "FAIL", "validator": who, "checker": "validator",
                                       "others": [{"validator": who, "verdict": "PASS", "by_hand": False, "ts": None}]})
        assert "validated by the validator" in html and "Beside it: PASS — the validator" in html, who
    assert "validated by rev" in verdict_line(tmp_path, {"verdict": "PASS", "validator": "rev"})


def test_the_roster_is_read_before_a_panel_and_again_at_each_reload():
    main, panel = ((WEB / f).read_text(encoding="utf-8") for f in ("main.js", "panel.js"))
    assert ".then(([r, a]) => takeRoster(a.agents, r.system_model))" in main
    assert "S.reload = async () => { await Promise.all([refreshAll(), readRoster()]);" in main
    assert main.count("readRoster()") == 2                             # …at load and at each reload
    assert "await S.roster;" in panel[panel.index("async function readPanel"):][:200]


def test_a_choice_sends_what_was_chosen_and_nothing_else(tmp_path):
    said = run(tmp_path, """const {appointed} = await import(page('panel.js'));
say([appointed('engineering', 'validator', () => 'x'), appointed('validator', 'validator', () => 'x'),
     appointed('', 'validator', () => '  ann  '), appointed('', 'validator', () => null), appointed('', 'validator', () => ' '),
     appointed('', 'ann', () => 'ann')]);""")
    assert said == ["engineering", "", "ann", "", "", ""]


def test_the_choice_is_sent_as_the_engines_set_checker():
    main = (WEB / "main.js").read_text(encoding="utf-8")
    assert "document.addEventListener('change', e => { const b = e.target.closest('[data-change]'); " \
           "if (b) ACT[b.dataset.change](b.dataset, b); });" in main
    move = main[main.index("'set-checker':"):][:400]
    assert "appointed(b.value, d.was, () => prompt(PANEL.askName))" in move
    assert "if (checker) await act(post('/api/run/set_checker', {task_id: d.id, checker})" in move
    assert "await S.reload(); point('select', d.id);" in move    # re-read either way: a refusal leaves the engine's
