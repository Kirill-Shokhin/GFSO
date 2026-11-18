"""A plan's pins run once over the base before the go, where the checks run: one that can run on no work as the tool
itself says it — bash, and `bash -n`, refuse its text; the place refuses its own fixture by its name — decides nothing
on any work (form item (1), §20.10). s16b lost ~7 min to two such, found only by the executor's dispute. Each goes to
the planner's repair with bash's own words (§12.16 (ii)); what stays is said in the plan file's review and is open in
the plan's answer. On a host project bash only reads them (`bash -n`), nothing of them runs before the go, and the
review says they were not run; with no execution, that none was. Nothing is read into a pin's output:
three critics' rounds found sound pins flagged by every such reading. A program missing over no work is said, never
repaired. Never a gate.

CONTROLS: make `cannot_run` return None for a syntax error and the first classification test goes red; drop its
`rc == 2` and the syntax line of a program the pin ran is flagged; drop its `bash_n == 2` and the nested shell's words
are flagged; drop the `bash -n` run from `on_the_base` and s16b is no longer flagged live; read any OSError laying a
pin alone as its own and "No space left on device" is flagged; drop `pins.flags` from `_repaired_before_build`'s list
and the repair is never told; run a host project's pins over the base (`on_the_base` for `parsed`) and they run
before the go; drop `rc`'s default in `cannot_run` and a host's refused pin is not flagged; leave the path of a host's
bash in its words and none is flagged; read a `PlaceUnavailable` laying inputs as the pin's own and the place's pins are flagged; keep a not-run row in `seen` and the
later round never runs it; drop "did not finish" from `observe.ran` and a pin that hit its own limit is run again; latch
a base-copy failure and the later round's pins never run; pass `None` for the pins in `planning.author`, in
`planning.refine`, in `_pin_by_part` or in the sufficiency round and that path's repair is never told; drop the
`cannot` count from `_after_the_plan` and the answer says "Nothing is undecided" over a pin no work can run; invite
a note after the spent round and the stand-flagged test goes red."""
import contextlib
import dataclasses
import subprocess
import time
from types import SimpleNamespace

import pytest

import gfso.adapters.execution as E
import gfso.decompose as D
import gfso.observe as O
import gfso.tools_llm as TL
from gfso.core.types import HOST, PlaceUnavailable
from gfso.decompose import artifact, planning
from gfso.observe import cannot_run, missing_program
from tests.support import a_repository, make_engine
from tests.test_a_session_holds_only_its_own_place import IMAGE, _docker

S16B = "D=$(mktemp -d) && touch $D/z $D/y.(none)"
SYNTAX = {"rc": 2, "stdout": "", "stderr": "bash: -c: line 1: syntax error near unexpected token `('\n"
                                           f"bash: -c: line 1: `{S16B}'", "bash_n": 2}
LONG = "bash: line 1: aaaa: File name too long"

#: the critic's pins and s16b's, as bash said them in the product's image (e3-linux-agent:2): over no work
#: (`none`) and over a program that runs (`work`), with `bash -n`'s exit over the same text
IMAGE_PINS = {
    "cat_then": "L=$(printf 'a%.0s' {1..300}); cat in.txt > $L; ./wordtop in.txt 2>/dev/null | grep -qx a",
    "colon": "L=$(printf 'a%.0s' {1..300}); : > $L; ./mycat $L 2>&1 | grep -q 'too long'",
    "echo": "L=$(printf 'a%.0s' {1..300}); echo hi > $L 2>/dev/null; ./mycat $L 2>&1 | grep -q 'File name too long'",
    "extglob": "shopt -s extglob\nls !(x)",
    "nested": "timeout 10 bash -c \"[[ $(./wordtop in.txt) == a ]]\"",
    "extglob_nested": "shopt -s extglob\nls !(in.txt|wordtop) >/dev/null\ntimeout 10 bash -c \"[[ $(./wordtop in.txt) == a ]]\"",
    "or_cat": "L=$(printf 'a%.0s' {1..300}); ./wordtop in.txt || cat in.txt > $L",
    "s16b": "D=$(mktemp -d) && touch $D/z $D/y.(none)",
}
IMAGE_ROWS = {
    "cat_then/none": {
        "bash_n": 0,
        "rc": 1,
        "stderr": "bash: line 1: <L>: File name too long\n",
        "stdout": "",
    },
    "cat_then/work": {
        "bash_n": 0,
        "rc": 1,
        "stderr": "bash: line 1: <L>: File name too long\n",
        "stdout": "",
    },
    "colon/none": {
        "bash_n": 0,
        "rc": 1,
        "stderr": "bash: line 1: <L>: File name too long\n",
        "stdout": "",
    },
    "colon/work": {
        "bash_n": 0,
        "rc": 0,
        "stderr": "bash: line 1: <L>: File name too long\n",
        "stdout": "",
    },
    "echo/none": {
        "bash_n": 0,
        "rc": 1,
        "stderr": "bash: line 1: <L>: File name too long\n",
        "stdout": "",
    },
    "echo/work": {
        "bash_n": 0,
        "rc": 0,
        "stderr": "bash: line 1: <L>: File name too long\n",
        "stdout": "",
    },
    "extglob/none": {
        "bash_n": 2,
        "rc": 0,
        "stderr": "",
        "stdout": "in.txt\n\ncc-socks:\n",
    },
    "extglob/work": {
        "bash_n": 2,
        "rc": 0,
        "stderr": "",
        "stdout": "in.txt\nmycat\nwordtop\n\ncc-socks:\n",
    },
    "nested/none": {
        "bash_n": 0,
        "rc": 2,
        "stderr": "bash: line 1: ./wordtop: No such file or directory\n"
                  "bash: -c: line 1: conditional binary operator expected\n"
                  "bash: -c: line 1: syntax error near `a'\nbash: -c: line 1: `[[  == a ]]'\n",
        "stdout": "",
    },
    "nested/work": {
        "bash_n": 0,
        "rc": 2,
        "stderr": "bash: -c: line 1: conditional binary operator expected\n"
                  "bash: -c: line 1: syntax error near `a'\nbash: -c: line 1: `[[  == a ]]'\n",
        "stdout": "",
    },
    "or_cat/none": {
        "bash_n": 0,
        "rc": 1,
        "stderr": "bash: line 1: ./wordtop: No such file or directory\nbash: line 1: <L>: File name too long\n",
        "stdout": "",
    },
    "or_cat/work": {
        "bash_n": 0,
        "rc": 0,
        "stderr": "",
        "stdout": "\n",
    },
    "s16b/none": {
        "bash_n": 2,
        "rc": 2,
        "stderr": "bash: -c: line 1: syntax error near unexpected token `('\n"
                  "bash: -c: line 1: `D=$(mktemp -d) && touch $D/z $D/y.(none)'\n",
        "stdout": "",
    },
    "s16b/work": {
        "bash_n": 2,
        "rc": 2,
        "stderr": "bash: -c: line 1: syntax error near unexpected token `('\n"
                  "bash: -c: line 1: `D=$(mktemp -d) && touch $D/z $D/y.(none)'\n",
        "stdout": "",
    },
}


@pytest.mark.parametrize("row,flagged", [
    (SYNTAX, True),
    # …the same words from a program the pin ran, the pin itself going on: not bash refusing the pin's text
    ({"rc": 0, "stdout": "", "stderr": SYNTAX["stderr"], "bash_n": 2}, False),
    # …bash's syntax words where `bash -n` takes the pin's text: a shell the pin started said them
    ({**SYNTAX, "bash_n": 0}, False),
    ({**SYNTAX, "bash_n": None}, False),
    ({"rc": 2, "stdout": "", "stderr": "make: *** No targets specified and no makefile found.  Stop."}, False),
    # …a program missing is never this: a pin may put it where programs are found (`missing_program`)
    ({"rc": 127, "stdout": "", "stderr": "bash: line 1: jq: command not found"}, False),
    ({"rc": 127, "stdout": "", "stderr": "bash: line 1: ./wordtop: No such file or directory"}, False),
    ({"note": "its inputs could not be laid (File name too long)"}, True),
    ({"note": "not run: the place could not lay its inputs (the execution place p is unavailable)"}, False),
    # …a failed redirect is no run that cannot go on: the pin may test for it, or go past it (critics, three rounds)
    ({"rc": 1, "stdout": "", "stderr": LONG}, False),
    ({"rc": 127, "stdout": "", "stderr": f"{LONG}\nbash: line 1: ./wordtop: No such file or directory"}, False),
    # …a program that RAN says it of a name the work may never pass it: `ls L 2>&1; ./myls L`, `rm L | sed …; ./myrm L`
    ({"rc": 1, "stdout": "", "stderr": "touch: cannot touch 'aaaa': File name too long"}, False),
    ({"rc": 127, "stdout": "ls: cannot access 'aaaa': File name too long\n",
      "stderr": "bash: line 1: ./myls: No such file or directory"}, False),
    ({"rc": 127, "stdout": "", "stderr": "rm: cannot remove 'aaaa': File name too long\n"
                                         "bash: line 1: ./myrm: No such file or directory"}, False),
    ({"rc": 1, "stdout": "3\n", "stderr": "diff: expected.out: differs"}, False),
    ({"note": "did not finish in 20 s"}, False),
])
def test_only_a_failure_before_the_program_could_matter_is_read_as_a_pin_that_cannot_run(row, flagged):
    assert bool(cannot_run(row)) is flagged, cannot_run(row)


@pytest.mark.parametrize("name", sorted(IMAGE_ROWS))
def test_as_bash_said_it_in_the_image_only_s16bs_text_is_flagged(name):
    """The critic's sound pins — a redirect the pin tests for or goes past, a shell the pin starts refusing its own
    text, extglob `bash -n` refuses and the run takes — are not flagged; s16b's `(` is, over no work and work alike."""
    assert bool(cannot_run(IMAGE_ROWS[name])) is name.startswith("s16b/"), (IMAGE_PINS[name.split("/")[0]],
                                                                            IMAGE_ROWS[name])


def test_bash_s_own_message_is_what_the_repair_is_handed():
    msg = cannot_run(SYNTAX)
    assert "syntax error near unexpected token" in msg and "y.(none)" in msg


@pytest.mark.parametrize("row,program", [
    ({"rc": 127, "stdout": "", "stderr": "bash: line 1: jq: command not found"}, "jq"),
    ({"rc": 127, "stdout": "", "stderr": "bash: line 1: ./wordtop: No such file or directory"}, None),
    ({"rc": 1, "stdout": "", "stderr": "bash: line 1: jq: command not found"}, None),
])
def test_a_program_bash_found_missing_is_named_bare(row, program):
    assert missing_program(row) == program


def _crit(name, cmd, **probe):
    return {"name": name, "description": name, "check": [{"behaviour": "b", "command": cmd, "expect": "x", **probe}]}


def _plan_of(*crits):
    return {"name": "wordtop", "root_criteria": list(crits), "subtasks": [], "mappings": [], "deps": [],
            "accepted_risks": []}


def _names_of(flags):
    return [f.split(" / criterion ")[1].split(":")[0] for f in flags]


GOAL = "Write wordtop, a program printing the most frequent words of a text."
#: a program a pin puts where programs are found in ways no reading of its text sees (critic over the 127 rule)
ON_PATH = ["jq . x.json || python3 -m json.tool x.json; ./wordtop", "sudo true; ./wordtop",
           "cc -o ~/.local/bin/wt2 wt.c && wt2 in.txt", "PATH+=:$PWD/bin; wc2 in.txt",
           "export PATH=$PWD/node_modules/.bin:$PATH; eslint src", ". .venv/bin/activate; tool"]
ROWS = {S16B: SYNTAX,
        "wordtop < x": {"rc": 127, "stdout": "", "stderr": "bash: line 1: wordtop: command not found"},
        "jq . out.json": {"rc": 127, "stdout": "", "stderr": "bash: line 1: jq: command not found"},
        "./wordtop x": {"rc": 127, "stdout": "", "stderr": "bash: line 1: ./wordtop: No such file or directory"},
        "slow": {"note": "did not finish in 20 s"},
        **{c: {"rc": 127, "stdout": "", "stderr": f"bash: line 1: {c.split()[0]}: command not found"} for c in ON_PATH}}
FIXED = "D=$(mktemp -d) && touch $D/z \"$D/y.(none)\""
ROWS[FIXED] = {"rc": 0, "stdout": "", "stderr": ""}


@pytest.fixture
def ran(monkeypatch):
    """Every pin the fake execution ran over the base, in order."""
    out = []

    def on_the_base(ex, probes):
        out.extend(p.command for _, p in probes)
        return {(p.command, p.inputs): ROWS[p.command] for _, p in probes}
    monkeypatch.setattr(D, "on_the_base", on_the_base)
    return out


APART = SimpleNamespace(files=object())       # an execution apart from this host: its files are not HOST's


def test_a_pin_no_work_can_run_is_flagged_and_a_missing_program_is_said_never_flagged(ran):
    pins = D.PinsOnTheBase(APART)
    spec = _plan_of(_crit("a", S16B), _crit("b", "wordtop < x"), _crit("c", "jq . out.json"), _crit("d", "./wordtop x"),
                    *(_crit(f"p{n}", c) for n, c in enumerate(ON_PATH)))
    assert _names_of(pins.flags(spec)) == ["a"]
    review = pins.review(spec)
    assert _names_of(review["cannot_run"]) == ["a"]
    assert {(m["pin"], m["program"]) for m in review["programs_missing"]} >= {("root / b", "wordtop"), ("root / c", "jq")}
    assert "root / d" not in {m["pin"] for m in review["programs_missing"]}, "a path is the work's to build"


def test_the_repair_round_is_told_with_bashs_words_and_a_pin_run_once_is_not_run_again(monkeypatch, ran):
    told = []
    patches = iter([{"root_criteria": [_crit("a", FIXED)]}])
    monkeypatch.setattr(D, "_audit_fix", lambda llm, req, sp, problems, ex: told.append(problems) or next(patches, {}))
    pins = D.PinsOnTheBase(APART)
    e = make_engine()
    e.start()
    try:
        _, spec, _ = D._build_verified(_plan_of(_crit("a", S16B), _crit("b", "jq . out.json")), GOAL, e, "root", "user",
                                       llm=None, pins=pins)
    finally:
        e.stop()
    assert len(told) == 1 and len(told[0]) == 1 and "y.(none)" in told[0][0] and "syntax error" in told[0][0], told
    assert spec["root_criteria"][0]["check"][0]["command"] == FIXED
    assert ran == [S16B, "jq . out.json", FIXED], "each distinct pin ran once"
    review = pins.review(spec)
    assert review["run"] == 2 and review["cannot_run"] == [], review


def test_a_pin_that_hit_its_own_limit_ran_and_is_not_run_again(ran):
    pins, spec = D.PinsOnTheBase(APART), _plan_of(_crit("a", "slow"))
    assert pins.flags(spec) == [] and pins.flags(spec) == []
    assert ran == ["slow"] and pins.review(spec)["run"] == 1


def test_what_the_rounds_leave_is_in_the_review_never_a_gate(monkeypatch, ran):
    monkeypatch.setattr(D, "_audit_fix", lambda *a, **k: {})
    pins = D.PinsOnTheBase(APART)
    e = make_engine()
    e.start()
    try:
        rid, spec, _ = D._build_verified(_plan_of(_crit("a", S16B)), GOAL, e, "root", "user", llm=None, pins=pins)
    finally:
        e.stop()
    assert e.graph.get_task(rid) is not None, "built: the pin's flag gated nothing"
    (line,) = pins.review(spec)["cannot_run"]
    assert "root / criterion a" in line and "syntax error" in line


def test_a_closed_plan_is_not_refused_for_a_pin_its_flags_are_said(monkeypatch, ran):
    monkeypatch.setattr(D, "_audit_fix", lambda *a, **k: pytest.fail("a closed plan was repaired"))
    pins = D.PinsOnTheBase(APART)
    agree = D._Agreement(None, make_engine(), "root", GOAL, False, False)
    spec = D._repaired_before_build(_plan_of(_crit("a", S16B)), GOAL, None, "", None, False, agree, closed=True, pins=pins)
    assert len(pins.review(spec)["cannot_run"]) == 1


def test_with_no_execution_the_plan_says_its_pins_were_not_run(monkeypatch):
    monkeypatch.setattr(D, "on_the_base", lambda *a: pytest.fail("a plan's pins ran on this host"))
    monkeypatch.setattr(D, "parsed", lambda *a: pytest.fail("no execution names a bash to read them"))
    pins = D.PinsOnTheBase(None)
    assert pins.flags(_plan_of(_crit("a", S16B))) == []
    assert pins.review(_plan_of(_crit("a", S16B)))["not_run"][0].startswith("pins not run before the go")


HOST_BASH = E.LocalExecution().shell()


@pytest.mark.skipif(not HOST_BASH, reason="no bash on this host")
def test_a_host_projects_pin_bash_refuses_is_flagged_before_the_go_and_nothing_of_any_pin_runs(monkeypatch, tmp_path):
    """The author's own path (solo in_chat, executor on this machine): a pin no work can pass reaches the repair as in a
    container, read by bash and never run — not one command of any pin, however it is written."""
    monkeypatch.setattr(D, "on_the_base", lambda *a: pytest.fail("a plan's pins ran on this host before the go"))
    mark = tmp_path / "ran"
    pins = D.PinsOnTheBase(E.LocalExecution())
    spec = _plan_of(_crit("a", S16B), _crit("b", f"touch '{mark.as_posix()}' && ./wordtop x"),
                    *(_crit(k, v) for k, v in IMAGE_PINS.items() if k != "s16b"))
    assert _names_of(pins.flags(spec)) == ["a"]
    assert not mark.exists(), "a pin's command ran before the go"
    review = pins.review(spec)
    assert _names_of(review["cannot_run"]) == ["a"] and "syntax error" in review["cannot_run"][0], review
    assert review["parsed"] == len(IMAGE_PINS) + 1 and "run" not in review, review
    assert review["not_run"] == [f"pins not run before the go: {D.HERE}"], review


def test_a_host_bash_naming_itself_by_its_path_is_read_as_bash():
    said = "/usr/bin/bash: -c: line 1: syntax error near unexpected token `('\n/usr/bin/bash: -c: line 1: `x (y'\n"
    host = SimpleNamespace(files=HOST, shell=lambda: "C:/Program Files/Git/bin/bash.exe", temp_root=lambda: ".",
                           run=lambda *a, **k: subprocess.CompletedProcess(a, 2, "", said))
    (row,) = O.parsed(host, [(None, SimpleNamespace(command="x (y", inputs=()))]).values()
    assert cannot_run(row).startswith("bash: -c: line 1: syntax error"), row


def test_a_base_that_cannot_be_copied_is_said_not_passed(monkeypatch):
    monkeypatch.setattr(D, "on_the_base", lambda *a: (_ for _ in ()).throw(OSError("cp -a failed")))
    pins = D.PinsOnTheBase(APART)
    assert pins.flags(_plan_of(_crit("a", S16B))) == []
    assert "cp -a failed" in pins.review(_plan_of(_crit("a", S16B)))["not_run"][0]


def test_a_later_rounds_copy_failure_keeps_what_earlier_rounds_ran_and_the_next_round_copies_again(monkeypatch):
    fails = iter([False, True, False])

    def on_the_base(ex, probes):
        if next(fails):
            raise OSError("cp -a failed")
        return {(p.command, p.inputs): ROWS[p.command] for _, p in probes}
    monkeypatch.setattr(D, "on_the_base", on_the_base)
    pins = D.PinsOnTheBase(APART)
    assert _names_of(pins.flags(_plan_of(_crit("a", S16B)))) == ["a"]
    both = _plan_of(_crit("a", S16B), _crit("c", "jq . out.json"))
    assert _names_of(pins.flags(both)) == ["a"], "the earlier round's result stands"
    assert ("jq . out.json", ()) in pins.skipped and pins.not_run is None
    review = pins.review(both)       # …the next round copies the base again
    assert review["run"] == 2 and "not_run" not in review and review["programs_missing"][0]["program"] == "jq", review


class _Place:
    """An execution apart from this host whose writes `seal` decides."""

    def __init__(self, seal, tmp):
        self.base, self.files = str(tmp / "base"), SimpleNamespace(seal_files=seal)
        self.scratch = lambda prefix, system=False: contextlib.nullcontext(str(tmp))
        self.system_writes = lambda root: contextlib.nullcontext()

    shell = staticmethod(lambda: "/bin/bash")
    copy_tree = release = staticmethod(lambda *a: None)


def test_a_place_that_cannot_lay_inputs_is_no_pins_fault_its_pins_are_said_not_run(tmp_path):
    def seal(base, files):
        raise PlaceUnavailable("p", "the daemon does not answer")
    pins = D.PinsOnTheBase(_Place(seal, tmp_path))
    spec = _plan_of(_crit("a", "./wordtop {inputs}/in.txt", inputs={"in.txt": "a\n"}))
    assert pins.flags(spec) == [] and pins.seen == {}
    review = pins.review(spec)
    assert review["run"] == 0 and "the daemon does not answer" in review["not_run"][0], review


LONG_ = "b" * 300
#: what the container's `seal_files` raised laying s16b's 300-byte fixture (`ContainerFiles._wrote`, the live test)
NAME_REFUSED = (f"/w/inputs could not be written in gfso-p: tar: {LONG_}: Cannot open: File name too long\n"
                "tar: Exiting with failure status due to previous errors")


@pytest.mark.parametrize("raised,flagged", [
    (NAME_REFUSED, True),
    # …the place's, whatever pin it met: retried, never the pin's
    ("/w/inputs could not be written in gfso-p: tar: in.txt: Cannot write: No space left on device", False),
    ("/w/inputs could not be written in gfso-p: OCI runtime exec failed: unable to start container process", False),
])
def test_only_the_places_word_on_a_pins_own_file_name_flags_it(monkeypatch, tmp_path, raised, flagged):
    def seal(base, files):
        if any(LONG_ in k for k in files):
            raise OSError(raised)
    monkeypatch.setattr(O, "_run", lambda *a: {"rc": 1, "stdout": "", "stderr": "wordtop: no such file"})
    pins = D.PinsOnTheBase(_Place(seal, tmp_path))
    spec = _plan_of(_crit("ok", "./wordtop {inputs}/in.txt", inputs={"in.txt": "a\n"}),
                    _crit("long", "cat {inputs}/" + LONG_, inputs={LONG_: "x\n"}))
    assert _names_of(pins.flags(spec)) == (["long"] if flagged else []), pins.skipped
    review = pins.review(spec)
    assert ("not_run" in review) is not flagged and review["run"] == (2 if flagged else 1), review


def test_a_pin_not_run_for_the_rounds_reasons_is_not_counted_run_and_a_later_round_runs_it(monkeypatch):
    calls = []

    def on_the_base(ex, probes):
        calls.append([p.command for _, p in probes])
        return {(p.command, p.inputs): {"note": "not run: the time for the plan's pins ran out"}
                if len(calls) == 1 and p.command == S16B else ROWS[p.command] for _, p in probes}
    monkeypatch.setattr(D, "on_the_base", on_the_base)
    pins, spec = D.PinsOnTheBase(APART), _plan_of(_crit("a", "./wordtop x"), _crit("c", S16B))
    assert pins.flags(spec) == []
    assert (S16B, ()) not in pins.seen
    review = pins.review(spec)     # …the review's own pass is the later round
    assert calls == [["./wordtop x", S16B], [S16B]], calls
    assert review["run"] == 2 and len(review["cannot_run"]) == 1 and "not_run" not in review, review


def test_a_pin_the_time_left_unrun_is_said_with_why(monkeypatch):
    monkeypatch.setattr(D, "on_the_base", lambda ex, probes: {(p.command, p.inputs): {
        "note": "not run: the time for the plan's pins ran out"} if p.command == S16B else ROWS[p.command]
        for _, p in probes})
    review = D.PinsOnTheBase(APART).review(_plan_of(_crit("a", "./wordtop x"), _crit("c", S16B)))
    assert review["run"] == 1 and review["cannot_run"] == [], review
    (line,) = review["not_run"]
    assert "y.(none)" in line and "time for the plan's pins ran out" in line


_Review = dataclasses.make_dataclass("_Review", [(k, object, None) for k in planning._REVIEW_KEYS])


@pytest.fixture
def no_model(monkeypatch):
    """The authoring verbs with no model behind them: every call a model would answer, answered empty."""
    monkeypatch.setattr(planning._decompose, "default_llm", lambda *a, **k: None)
    monkeypatch.setattr(planning, "llm_factory", lambda *a, **k: None)
    monkeypatch.setattr(planning.runner, "review_decomposition", lambda *a, **k: _Review())
    monkeypatch.setattr(planning.runner, "goal_obligations", lambda *a, **k: [])
    monkeypatch.setattr(D, "sufficiency_at_authoring", lambda: False)


def test_the_plan_file_carries_what_its_pins_did_and_the_answer_holds_it_open(monkeypatch, ran, no_model):
    """Through the authoring verb: the pins object reaches the build, the file's review says the pin left unrepaired,
    and the plan's answer holds it open — never "nothing is undecided" over it."""
    told = []
    monkeypatch.setattr(D, "_audit_fix", lambda llm, req, sp, problems, ex: told.append(problems) or {})
    monkeypatch.setattr(D, "decompose_spec", lambda *a, **k: _plan_of(_crit("a", S16B), _crit("b", "./wordtop x")))
    text = planning.author(GOAL, "m", execution=APART)
    assert told and any("syntax error" in x and "y.(none)" in x for x in told[0]), "the authoring's repair was told"
    pins = artifact.parse(text)["review"][planning.PINS]
    assert len(pins["cannot_run"]) == 1 and "y.(none)" in pins["cannot_run"][0], pins
    out = TL._plan_written(text)
    assert out[planning.PINS]["cannot_run"] == 1 and "1 pinned check(s) cannot run on any work" in out["say"]
    assert "Nothing is undecided" not in out["say"] and "refine_plan" in out["say"], out["say"]


def test_the_customers_note_round_runs_the_pins_and_says_what_they_did(monkeypatch, ran, no_model):
    """`refine_plan`, the customer's path: its repair before the build is told the pin, and the new file says it."""
    told = []
    monkeypatch.setattr(D, "_audit_fix", lambda llm, req, sp, problems, ex: told.append(problems) or {
        "root_criteria": [_crit("a", FIXED)]})
    rounds = []
    monkeypatch.setattr(D, "refine_with", lambda *a, **k: rounds.append(k.get("pins")) or (False, {}, []))
    text = artifact.render(GOAL, _plan_of(_crit("a", S16B)), {"by": "m"})
    pins = artifact.parse(planning.refine(text, "the check of a", "m", execution=APART))["review"][planning.PINS]
    assert told and "syntax error" in told[0][0], told
    assert len(rounds) == 1 and isinstance(rounds[0], D.PinsOnTheBase) and rounds[0].seen, "the note's round has them"
    assert pins["run"] == 1 and pins["cannot_run"] == [], pins


def test_the_part_by_part_round_builds_with_the_pins(monkeypatch):
    built = []
    part = {"id": "p1", "name": "p1", "description": "p1", "writes": ["a.c"], "criteria": [_crit("c1", "./a")]}
    monkeypatch.setattr(D, "extract_spec", lambda *a: {**_plan_of(), "subtasks": [part]})
    monkeypatch.setattr(D, "fan", lambda llm, items, each, stage: [each(x) for x in items])
    monkeypatch.setattr(D, "_build_verified", lambda *a, **k: built.append(k.get("pins")) or ("root", {}, []))
    llm = SimpleNamespace(complete_structured=lambda *a: {"add_criteria": [_crit("c2", "./a -n 2")]})
    pins = D.PinsOnTheBase(APART)
    D._pin_by_part(None, GOAL, "root", "user", llm, [{"obligation": "o", "admits": "x"}], None, "", None, pins)
    assert built == [pins]


def test_the_sufficiency_rounds_repair_with_the_pins(monkeypatch):
    got = []
    monkeypatch.setattr(D, "_undecided_obligations", lambda *a, **k: [{"obligation": "o", "admits": "x"}])
    monkeypatch.setattr(D, "record_goal_reading", lambda *a: None)
    monkeypatch.setattr(D, "checker_at_authoring", lambda: False)
    monkeypatch.setattr(D, "_pin_by_part", lambda *a: got.append(("by part", a[-1])) or (True, {}, []))
    monkeypatch.setattr(D, "_refine_round", lambda *a, **k: got.append(("round", k.get("pins"))) or (True, {}, []))
    engine = SimpleNamespace(graph=SimpleNamespace(get_task=lambda rid: object(), get_active_children=lambda rid: [1]))
    pins = D.PinsOnTheBase(APART)
    D._close_the_goals_obligations(engine, GOAL, "root", "user", None, {}, [], None, "", None, pins)
    assert got == [("by part", pins), ("round", pins)], got


@pytest.mark.parametrize("notes", [[], [{"note": "n", "answer": "what changed\nNOT ANSWERED — still open: x"}]])
def test_a_pin_no_work_can_run_is_open_in_the_answer_never_nothing_undecided(notes):
    said = TL._after_the_plan(0, notes, cannot=2)
    assert "2 pinned check(s) cannot run on any work" in said and "Nothing is undecided" not in said
    assert "a note naming them repairs them" in said and "auto_decompose" in said, "never a gate: the go stays theirs"


def test_once_the_note_round_is_spent_the_pins_stand_flagged_and_no_second_note_is_invited():
    said = TL._after_the_plan(0, [{"note": "n", "answer": "what changed"}], cannot=2)
    assert "2 pinned check(s) still cannot run on any work" in said and "CHALLENGE" in said, said
    assert "a note naming them" not in said and "refine_plan" not in said and "auto_decompose" in said, said


@pytest.fixture
def a_project(tmp_path, monkeypatch):
    """A project in a real container over a base whose HEAD holds README.md: the person's committed tree."""
    if not _docker():
        pytest.skip(f"needs docker and {IMAGE}")
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_SWITCH", {})
    a_repository(base := tmp_path / "work" / "ws")
    (base / "README.md").write_text("hello\n")
    for a in (["add", "README.md"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "readme"]):
        subprocess.run(["git", "-C", str(base), *a], check=True, capture_output=True)
    (tmp_path / "e.env").write_text("NOTHING=1\n")
    x = E.ContainerExecution(f"t{time.time_ns()}", IMAGE, str(tmp_path / "e.env"), str(tmp_path / "state"), str(base), "p")
    try:
        yield x
    finally:
        x.stop()
        x.volume.remove()


def test_live_a_plans_pins_run_on_the_base_in_its_container(a_project):
    """s16b's pin comes back refused by bash and `bash -n`, its 300-byte fixture refused by the place by its name — both
    flagged; the critic's sound pins — a redirect the pin tests for or goes past, a shell the pin starts refusing its
    own text, extglob — are not; a program no image has is said, not flagged; the work's own program not yet built is
    neither; a sound pin reads the committed tree."""
    i = {"in.txt": "a b a\n"}
    sound = [_crit(f"critic_{k}", IMAGE_PINS[k]) for k in ("colon", "echo", "cat_then", "or_cat", "nested", "extglob", "extglob_nested")]
    spec = _plan_of(_crit("s16b", S16B), _crit("built", "./wordtop {inputs}/in.txt", inputs=i),
                    _crit("named", "wordtop < {inputs}/in.txt", inputs=i),
                    _crit("absent", "gfso-no-such-tool --version"), *sound, _crit("sound", "grep -c hello README.md"),
                    _crit("fixture", "cat {inputs}/" + "b" * 300, inputs={"b" * 300: "x\n"}))
    assert len(D.PinsOnTheBase._pins(spec)) == 6 + len(sound), "every pin is one the admission takes"
    pins, t0 = D.PinsOnTheBase(a_project), time.monotonic()
    flags = pins.flags(spec)
    print(f"\n{len(pins.seen)} pins over the base: {time.monotonic() - t0:.1f} s (container start included)")
    assert pins.not_run is None and not pins.skipped, pins.skipped
    assert _names_of(flags) == ["s16b", "fixture"], flags
    assert "syntax error near unexpected token" in flags[0] and "y.(none)" in flags[0], flags[0]
    assert "inputs could not be laid" in flags[1] and "File name too long" in flags[1], flags[1]
    assert pins.seen[(IMAGE_PINS["nested"], ())].get("bash_n") == 0, "the nested shell's words were checked, not taken"
    assert pins.seen[("grep -c hello README.md", ())]["stdout"].strip() == "1", "the pins ran over the committed tree"
    missing = {m["pin"]: m["program"] for m in pins.review(spec)["programs_missing"]}
    assert missing.get("root / absent") == "gfso-no-such-tool" and "root / built" not in missing, missing
    t0 = time.monotonic()
    more = [_crit(f"m{n}", f"./wordtop -n {n} {{inputs}}/in.txt", inputs=i) for n in range(20)]
    assert len(pins.flags({**spec, "root_criteria": spec["root_criteria"] + more})) == 2
    print(f"20 more pins, the container up: {time.monotonic() - t0:.1f} s")


def test_a_plan_whose_pins_did_not_run_says_so_in_its_answer(monkeypatch):
    text = artifact.render(GOAL, _plan_of(_crit("a", "./wordtop x")),
                           {"by": "m", planning.PINS: {"not_run": ["pins not run before the go: no execution"]}})
    assert "pins not run before the go" in TL._plan_written(text)["say"]
