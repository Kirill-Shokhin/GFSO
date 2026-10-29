"""Every program the system hands an interpreter by `-c` runs isolated (`-I`): `python -c` imports from its cwd first,
and the system runs such programs in an agent's tree — a judge's copy of a delivery, a validator's place — where a
delivered `json.py` exiting 0 passed a changed copy as the delivery (the live case in
`test_a_judge_judges_what_was_delivered`)."""
import re
from pathlib import Path

import gfso

#: an interpreter of the system's — `.python`, `python3`, `sys.executable` — handed a program by `-c`
_CALL = re.compile(r'(?:\.python|"python3?"|sys\.executable)\s*,\s*((?:"-[A-Za-z]+"\s*,\s*)*)"-c"')


def test_every_program_the_system_hands_python_by_c_runs_isolated():
    root = Path(gfso.__file__).parent
    calls = [(p.relative_to(root), m) for p in root.rglob("*.py") for m in _CALL.finditer(p.read_text(encoding="utf-8"))]
    assert len(calls) >= 3, "the guard finds the calls it guards (`_OWN_GIT`, `_JUDGES_GIT`, `_FIND`)"
    assert not [str(p) for p, m in calls if '"-I"' not in m[1]], "a `-c` program run without `-I`"


def test_the_guard_reads_a_call_without_isolation():
    assert _CALL.search('ex.run([ex.python, "-c", _X])')[1] == ""
    assert '"-I"' in _CALL.search('ex.run([ex.python, "-I", "-c", _X])')[1]
