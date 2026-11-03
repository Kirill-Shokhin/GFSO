"""The directories beside a base are named by the system, and a shell reads those names: a pinned check's `{inputs}` lies
under them and is replaced unquoted into its command. A work directory `word top` gave `python3 wordtop.py {inputs}/many.txt
-n 3` six arguments, so no delivery could pass any check with inputs (a fresh user's first task, critic); a comma ended a
`--mount`'s field. A name with nothing unsafe stands byte for byte: no place of an existing project moves."""
import csv
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from gfso import workspaces as WS
from gfso.adapters import execution as E
from gfso.adapters.execution import ContainerExecution, LocalExecution, scratch_of
from gfso.adapters.worktrees import base_of
from gfso.core.protocol.procedure import INPUTS_TOKEN, materialize_inputs, probe_id
from gfso.core.types import VOLUME, Criteria, Probe, nodes_dir
from gfso.packets import checkout_note

IMAGE = "gfso-test-image"
UNSAFE = ["word top", "частые слова", "a,b", "a'b$c(d)", "tilde~1", "100%", " lead"]
PIN = Criteria("c", check=(Probe("counts words", "wordtop {inputs}/many.txt -n 3", "5",
                                 inputs=(("many.txt", "a b c\n"),)),))


def _inputs(base: Path, files) -> Path:
    """Where a validation's round lays the check's inputs for a delivery standing in `base`."""
    at = scratch_of(base, "p") / "root_1" / "probe_inputs"
    return materialize_inputs((PIN,), at, files)[probe_id("c", PIN.check[0])]


def _command(d: str, program: str) -> str:
    return PIN.check[0].command.replace(INPUTS_TOKEN, d).replace("wordtop", program)


@pytest.mark.parametrize("name", ["word top", "частые слова"])
def test_a_real_command_keeps_its_argv_under_a_spaced_directory_on_this_host(tmp_path, name):
    (w := tmp_path / name).mkdir()
    (w / "wordtop.py").write_text("import sys\nprint(len(sys.argv) + 1, open(sys.argv[1]).read().split())\n")
    d = _inputs(w, LocalExecution().files)
    cmd = _command(d.as_posix(), f'"{Path(sys.executable).as_posix()}" wordtop.py')
    got = subprocess.run([LocalExecution().shell(), "-c", cmd], cwd=w, capture_output=True, text=True)
    assert got.stdout.startswith("5 ") and "'a'" in got.stdout, (cmd, got.stdout, got.stderr)


@pytest.mark.parametrize("name", UNSAFE)
def test_the_command_a_container_reads_keeps_its_argv(tmp_path, name):
    (w := tmp_path / name).mkdir()
    x = ContainerExecution("e", IMAGE, None, str(tmp_path / "state"), str(w), "p")
    inside = x.to_inside((scratch_of(x.base, "p") / "root_1" / "probe_inputs" / "c").as_posix())
    assert inside.startswith(E.INSIDE + "/" + nodes_dir(name)), inside
    cmd = _command(inside, "python3 wordtop.py")
    got = subprocess.run([LocalExecution().shell(), "-c", f"set -- {cmd}; echo $#"], capture_output=True, text=True)
    assert got.stdout.strip() == "5", (cmd, got.stdout, got.stderr)


@pytest.mark.parametrize("name", UNSAFE)
def test_a_node_place_is_named_once_and_read_back_to_its_base(tmp_path, name):
    w = tmp_path / name
    engine = SimpleNamespace(project_name="p", scope_top=lambda i: None, hands_of=lambda p: None)
    agents = SimpleNamespace(get=lambda k: {"workdir": str(w)})
    base, place, branch = WS._place_of(engine, agents, SimpleNamespace(id="root", assignee="x"))
    assert re.fullmatch(r"\.gfso-nodes-[\w.~+@=-]+", Path(place).parents[1].name), place
    assert Path(place).parent == scratch_of(w, "p").parent, "the place and its rounds under one project's directory"
    assert base_of(place) == str(w) and str(w) in checkout_note(place), "a packet names the base by its own name"
    x = ContainerExecution("e", IMAGE, None, str(tmp_path / "state"), str(w), "p")
    assert Path(place).parent == x.own, "the host's name of it and the execution's are one"
    assert E._base_of_places({f"place-made:{place}": "1"}) == str(w)


def test_two_bases_never_share_a_directory():
    names = [*UNSAFE, "word_top", "word-top", "word~20top", "word%20top", "a_b", "a-b"]
    assert len({nodes_dir(n) for n in names}) == len(names)


@pytest.mark.parametrize("name", ["ws", "base", "my-proj.v2", "word_top", "c++", "a=b", "me@home", "частые_слова", "词频"])
def test_a_name_with_nothing_unsafe_stands_byte_for_byte(tmp_path, name):
    (w := tmp_path / name).mkdir()
    assert nodes_dir(name) == f".gfso-nodes-{name}"
    assert scratch_of(w, "p") == tmp_path / f".gfso-nodes-{name}" / "p" / f".gfso-scratch-.{name}"
    assert ContainerExecution("e", IMAGE, None, str(tmp_path / "s"), str(w), "p").mounts == [name, f".gfso-nodes-{name}/p"]


def test_a_place_recorded_under_the_old_name_still_reads_its_base(tmp_path):
    assert base_of(str(tmp_path / ".gfso-nodes-word top" / "p" / "a")) == str(tmp_path / "word top")


def test_an_export_finds_the_directory_the_execution_named(tmp_path, monkeypatch):
    """`export-places` stands on the project's record alone, naming the directory again from the base it keeps."""
    (w := tmp_path / "word top, two").mkdir()
    x = ContainerExecution("e", IMAGE, None, str(tmp_path / "state"), str(w), "p")
    monkeypatch.setattr(E.Volume, "_labels", staticmethod(lambda v: {E.LABEL: "e"}))
    v, _ = E.Volume.of_record("p", {VOLUME + "places": "v", VOLUME + "base": str(x.base), VOLUME + "image": IMAGE})
    assert v.own == x.own


def test_a_comma_in_the_base_stays_inside_its_mount_field(tmp_path):
    """Docker reads a `--mount` as CSV; the base's own name is the user's, and it is where it stands inside."""
    (w := tmp_path / "a,b").mkdir()
    x = ContainerExecution("e", IMAGE, None, str(tmp_path / "state"), str(w), "p")
    for src in (x.base, x.own):
        flag, spec = x._mount(src, False)
        fields = dict(f.split("=", 1) for f in next(csv.reader([spec])) if "=" in f)
        assert flag == "--mount" and fields["dst"] == x.to_inside(str(src)), spec
        assert all("=" in f for f in next(csv.reader([spec]))), spec


def test_a_place_recorded_under_its_raw_name_is_still_made_after_the_name_was_made_safe(tmp_path):
    """Else a delivered node of such a base, waiting on its validator through an upgrade, is validated away from its delivery."""
    old = str(tmp_path / ".gfso-nodes-word top" / "p" / "root")
    new = str(tmp_path / ".gfso-nodes-word~20top" / "p" / "root")
    held = {WS.MADE + old: "1"}
    engine = SimpleNamespace(graph=SimpleNamespace(setting=held.get))
    assert WS.made(engine, new) is True
