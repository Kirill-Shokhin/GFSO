"""What a judge compares the delivery with — a pinned probe's inputs, its expected output among them — is laid by the
system as its own: the judged code run beside them may add files of its own, never change, move or remove the pinned
ones, nor any directory above them up to the root its container writes. Laid as the agent's, the code rewrote the
expected file inside the very command that compared it with its output, or renamed the batch away and laid a forged one
in its place (probe, image f400b818). The system's own exact checks each start from what it laid: what an earlier one
left — a process, a `GNUmakefile` beside a pinned `Makefile` — is gone before the next.

Not held, named in SECURITY.md: inside ONE command, a file the code adds beside the inputs before a later step of that
command reads the directory."""
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import gfso.adapters.execution as E
import gfso.observe as O
from gfso.adapters.execution import ContainerExecution, LocalExecution
from gfso.core.protocol.procedure import inputs_dir_name, materialize_inputs, probe_id
from gfso.core.types import Criteria, Probe
from gfso.observe import run_checks
from tests.test_a_session_holds_only_its_own_place import IMAGE, _docker, made

docker = pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")
PIN = Criteria("c", check=(Probe("prints what is pinned", "cd {inputs} && ./run", "OK",
                                 inputs=(("expected.out", "OK\n"), ("Makefile", "all:\n\t@echo pinned\n"))),))


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_SWITCH", {})
    (base := tmp_path / "work" / "ws").mkdir(parents=True)
    (tmp_path / "e.env").write_text("NOTHING=1\n")
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, str(tmp_path / "e.env"), str(tmp_path / "state"), str(base),
                           "p")
    yield x
    x.stop()
    x.volume.remove()


@docker
def test_live_the_judged_code_moves_nothing_the_system_laid_for_its_judge(project):
    batch = project.parent / ".gfso-nodes-ws/p/.gfso-scratch-.ws/root_1/batch1"
    made(project, ".gfso-scratch-.ws/root_1/batch1/delivery")
    d = materialize_inputs((PIN,), batch / "probe_inputs", project.files)[probe_id("c", PIN.check[0])].as_posix()
    v, b = project.session(str(batch / "delivery")), batch.as_posix()
    tries = {"overwrite": f"printf FORGED > {d}/expected.out", "remove": f"rm -f {d}/expected.out",
             "chmod": f"chmod 666 {d}/expected.out", "rename the probe's": f"mv {d} {d}.x",
             "rename probe_inputs": f"mv {b}/probe_inputs {b}/pi",
             "rename the batch": f"mv {b} {b}.x && mkdir -p {d} && echo FORGED > {d}/expected.out"}
    try:
        for what, cmd in tries.items():
            r = v.run(["sh", "-c", cmd], cwd=str(batch / "delivery"), timeout=60)
            assert r.returncode != 0, f"the judged code could {what}"
        honest = v.run(["sh", "-c", f"cd {d} && echo mine > a.out && cat a.out expected.out"],
                       cwd=str(batch / "delivery"), timeout=60)
        assert honest.stdout.split() == ["mine", "OK"], honest
    finally:
        project.stop()


@docker
def test_live_what_one_system_check_leaves_reaches_no_later_one(project):
    read = Probe("runs the pinned makefile", "cd {inputs} && make -s && test ! -e again", "pinned", inputs=PIN.check[0].inputs,
                 exact=True)
    there = f"{{inputs}}/../{inputs_dir_name(probe_id('c', read))}"
    # …everywhere it can reach: beside the reader's inputs where they stood, a file in the inputs' own base and above it
    # (a check that tidied after it was turned off by one, critic B6), and a process copying its makefile on
    plant = Probe("leaves a makefile, files and a process",
                  f"mkdir -p {there} && cd {there} && printf 'all:\\n\\t@echo forged\\n' > GNUmakefile && touch {{inputs}}/../planted "
                  "{inputs}/../../planted && (setsid sh -c 'while :; do for d in ../../inputs-*/*/; do "
                  "cp GNUmakefile $d 2>/dev/null; done; sleep 0.1; done' >/dev/null 2>&1 </dev/null &) && echo LEFT",
                  "LEFT", inputs=PIN.check[0].inputs, exact=True)
    c = Criteria("c", check=(plant, read))
    made(project, "a")
    try:
        with project.scratch("gfso-exact-", system=True) as tmp:
            project.files.mkdir(str(tree := Path(tmp) / "exact" / "delivery"))
            rows = dict(run_checks(project, [("p", c, plant), ("r", c, read)], str(project.parent / ".gfso-nodes-ws/p/a"),
                                   str(tree), tmp, 120))
        assert rows["p"].get("matched"), rows["p"]
        assert rows["r"].get("matched"), rows["r"]
    finally:
        project.stop()


@docker
def test_live_a_program_one_check_lays_on_the_path_runs_in_no_later_one(project):
    """The image's PATH starts in the agent's home: a `diff` an earlier check laid there turned the system's own
    comparison into a PASS (critic F5). Each check starts in a container of its own."""
    lie = Probe("lays a diff that agrees with anything", "mkdir -p ~/.local/bin && printf '#!/bin/sh\nexit 0\n' > "
                "~/.local/bin/diff && chmod +x ~/.local/bin/diff && echo LAID", "LAID", exact=True)
    cmp = Probe("compares", "printf 'WRONG\n' | diff - {inputs}/expected.out >/dev/null && echo SAME || echo DIFFERS",
                "DIFFERS", inputs=(("expected.out", "OK\n"),), exact=True)
    c = Criteria("c", check=(lie, cmp))
    made(project, "a")
    try:
        with project.scratch("gfso-exact-", system=True) as tmp:
            project.files.mkdir(str(tree := Path(tmp) / "exact" / "delivery"))
            rows = dict(run_checks(project, [("l", c, lie), ("c", c, cmp)], str(project.parent / ".gfso-nodes-ws/p/a"),
                                   str(tree), tmp, 120))
        assert rows["l"].get("matched"), rows["l"]
        assert rows["c"].get("matched"), rows["c"]
    finally:
        project.stop()


def test_an_exact_check_the_memory_watch_ended_observed_nothing(monkeypatch, tmp_path):
    """The watch ends the work furthest over its share; an exact check of the system's own ended so printed what the
    kill left and forced its delivery's FAIL — a neighbour's pressure steering another node's verdict (critic B7)."""
    (box := ContainerExecution.__new__(ContainerExecution)).container = "check.gfso-exact-x"
    files = SimpleNamespace(seal_files=lambda base, laid: None)
    ex = SimpleNamespace(release=lambda tree: None, files=files, session=lambda tree: box,
                         copy_tree=lambda src, dst: None, remove_tree=lambda path: None)
    monkeypatch.setattr(O, "_run", lambda *a, **k: {"rc": 128, "out": "cannot exec in a stopped state", "stdout": "",
                                                     "stderr": "cannot exec in a stopped state"})
    p = PIN.check[0]
    monkeypatch.setattr(E, "_WATCH_ENDED", {"check.gfso-exact-x"})
    got = O._fresh_run(ex, "bash", PIN, p, str(tmp_path), tmp_path, 10, str(tmp_path), [])
    assert "stdout" not in got and "memory watch" in got["note"], got
    monkeypatch.setattr(E, "_WATCH_ENDED", set())
    assert "stdout" in O._fresh_run(ex, "bash", PIN, p, str(tmp_path), tmp_path, 10, str(tmp_path), []), \
        "a check its own code ended is observed as it ended"


@docker
@pytest.mark.parametrize("order", ["the selftest first", "the read first"])
def test_live_no_exact_check_changes_the_delivery_a_later_one_reads(project, order):
    """Over one shared copy, a check running the delivered code rewrote what a later check read: its order turned a
    forced FAIL into the judge's word (critic B7). Each check reads the delivery as delivered, in either order."""
    selftest = Probe("selftest", "sh selftest.sh", "SELFTEST OK", exact=True)
    status = Probe("status", "cat status.txt", "ok", exact=True)
    c = Criteria("c", check=(selftest, status))
    made(project, "a")
    try:
        with project.scratch("gfso-exact-", system=True) as tmp:
            project.files.mkdir(str(tree := Path(tmp) / "exact" / "delivery"))
            project.files.write_files(str(tree), {"status.txt": b"bad\n",
                                                  "selftest.sh": b"echo ok > status.txt; echo SELFTEST OK\n"})
            runs = [("s", c, selftest), ("r", c, status)]
            rows = dict(run_checks(project, runs if order == "the selftest first" else runs[::-1],
                                   str(project.parent / ".gfso-nodes-ws/p/a"), str(tree), tmp, 120))
        assert rows["s"].get("matched") and rows["r"].get("matched") is False, rows
    finally:
        project.stop()


def test_one_command_pinned_over_two_inputs_is_run_over_each(tmp_path):
    """Keyed by the command alone, a second criterion pinning it over other inputs read the first one's output: a false
    FAIL on correct work, a lost one on wrong work (critic B8). On this host: what is run, not where."""
    small = Criteria("small", check=(Probe("sorts", "sort -n {inputs}/in.txt", "1 2 3", inputs=(("in.txt", "3\n1\n2\n"),),
                                           exact=True),))
    big = Criteria("big", check=(Probe("sorts", "sort -n {inputs}/in.txt", "7 8 9", inputs=(("in.txt", "9\n8\n7\n"),),
                                       exact=True),))
    (tree := tmp_path / "tree").mkdir()
    rows = dict(run_checks(LocalExecution(), [("s", small, small.check[0]), ("b", big, big.check[0])], str(tree),
                           str(tree), tmp_path, 60))
    assert rows["s"]["matched"] and rows["b"]["matched"], rows


@docker
def test_live_a_delivery_that_cannot_be_copied_for_a_check_fails_it(project):
    """A built delivery holding a path no copy can make left every exact check "not observed", the judge's word
    deciding (critic B9): it is the delivery's FAIL, its cause said, as a checkout it makes impossible is."""
    deep = Probe("answers", "echo RIGHT", "RIGHT", exact=True)
    c = Criteria("c", check=(deep,))
    made(project, "a")
    try:
        with project.scratch("gfso-exact-", system=True) as tmp:
            project.files.mkdir(str(tree := Path(tmp) / "exact" / "delivery"))
            r = project.session(str(tree)).run(["sh", "-c", 'for i in $(seq 1 20); do d=$(printf "d%.0s" $(seq 1 200)); '
                                                'mkdir "$d" && cd "$d"; done; echo x > f'], cwd=str(tree), timeout=60)
            assert r.returncode == 0, r.stderr
            rows = dict(run_checks(project, [("d", c, deep)], str(project.parent / ".gfso-nodes-ws/p/a"), str(tree),
                                   tmp, 120))
        assert rows["d"].get("matched") is False and "could not be copied" in rows["d"]["out"], rows
    finally:
        project.stop()
