"""A probe's inputs are laid down in its own directory, so a file its command names under `{inputs}` and that the probe
does not pin — pinned under a sibling probe, or nowhere — cannot be opened at validation: a false FAIL of every
delivery, correct ones included (V3_cc2's `builtins_memory_setjmp_va` on the oracle's good trees, 2026-10-31). Refused at
admission, which the plan's author lifts by pinning it. A glob or a shell variable names no one file and is left alone
(replayed over the 154 plans on disk: only the one real case refused)."""
from gfso.core.protocol.procedure import admission_defects, inputs_named_not_pinned
from gfso.core.types import Criteria, Probe


def _c(command, inputs):
    return Criteria("c", "d", check=(Probe("b", command, "ok", inputs=inputs),))


def test_a_file_named_and_pinned_elsewhere_is_refused():
    c = _c("./cc {inputs}/a.c && ./cc {inputs}/ab.c; echo ok", {"a.c": "int main(){}"})
    assert inputs_named_not_pinned([c]) == {"c": ["{inputs}/ab.c"]}
    assert any("does not pin it" in d for d in admission_defects([c]))


def test_globs_variables_and_pinned_directories_name_no_missing_file():
    for cmd in ("for f in {inputs}/bad_*.c; do ./cc $f; done; echo ok", "./cc {inputs}/$F; echo ok",
                "./cc {inputs}/sub/x.c; echo ok", "./cc {inputs}/sub; echo ok"):
        assert inputs_named_not_pinned([_c(cmd, {"sub/x.c": "int main(){}", "bad_1.c": "x"})]) == {}, cmd


def test_a_file_the_probe_itself_makes_there_is_no_input_to_pin():
    """A redirect's or an `-o`'s target under {inputs} is the probe's own output — refused as unpinned, a closed plan
    with `python {inputs}/t.py > {inputs}/got.txt && diff …` was refused outright (critic)."""
    c = Criteria("c", "d", check=(
        Probe("b", "python {inputs}/t.py > {inputs}/got.txt && diff {inputs}/got.txt {inputs}/want.txt", "",
              inputs={"t.py": "x", "want.txt": "y"}),
        Probe("g", "gcc -o {inputs}/out {inputs}/a.c && {inputs}/out", "x", inputs={"a.c": "int main(){}"}),
        Probe("r", "cat {inputs}/zz.c", "x")))
    assert inputs_named_not_pinned([c]) == {"c": ["{inputs}/zz.c"]}       # …a read nobody pinned still is
