"""Whether a validation round still stands is the system's record, and the readers of the standing findings ask no
container to know it.

A finding naming a file in a pruned round is shown, not demanded (`unrerunnable`); which rounds stand the system
knows, for it alone makes and removes them. Asked of the round's container instead, every sweep of a root's findings
cost a `docker exec` per named path and started each old round's container (critic over 795ade5: 6 findings, 6.3 s
first, 1.5 s after; a real root holds 72) — on the path that records a verdict too. So the round is recorded as it is
made and removed, and what was read of its files (a program's header, a finding's digest) is kept until it goes.
"""
import subprocess
from types import SimpleNamespace

import gfso.adapters.execution as E
from gfso.adapters.execution import ContainerExecution
from gfso.core.protocol.procedure import finding_id, runs_a_past_build, unrerunnable
from gfso.core.types import hold_places
from gfso.engine.findings import record_round, round_stands


def _graph():
    kept = {}
    return SimpleNamespace(setting=kept.get, store_setting=kept.__setitem__)


def test_the_findings_over_rounds_are_read_with_no_container_asked(tmp_path, monkeypatch):
    base = tmp_path / "work" / "ws"
    base.mkdir(parents=True)
    ex = ContainerExecution("vol-v1", "img", None, str(tmp_path / "state"), str(base), "rounds")
    calls = []
    monkeypatch.setattr(E.ContainerFiles, "_run", lambda self, at, cwd, op, *a, **kw: calls.append(op) or
                        subprocess.CompletedProcess(a, 0, b"\x7fELF", b""))
    hold_places(ex.files)
    try:
        scratch, graph = tmp_path / "work" / ".gfso-nodes-ws" / "p" / ".gfso-scratch-a", _graph()
        kept, pruned = scratch / "a_1700000001", scratch / "a_1700000002"
        record_round(graph, str(kept), True)
        record_round(graph, str(pruned), True)
        record_round(graph, str(pruned), False)
        up = round_stands(graph)
        finding = lambda r: {"as_run": f"{(r / 'x' / 'chk').as_posix()} < {(r / 'in.txt').as_posix()}"}
        assert unrerunnable(finding(kept), None, str(base), standing=up) == ""
        assert "no longer exist" in unrerunnable(finding(pruned), None, str(base), standing=up)
        assert calls == [], "whether a round stands is the record's, asked of no container"
        assert runs_a_past_build(finding(kept)["as_run"]) and runs_a_past_build(finding(kept)["as_run"])
        assert calls.count("read_bytes") == 1, "a round's program header is read once while the round stands"
        finding_id("c", finding(kept)["as_run"]), finding_id("c", finding(kept)["as_run"])
        assert calls.count("read_bytes") == 3, "…and each file it names digested once for its finding's id"
        record_round(graph, str(kept), False)
        runs_a_past_build(finding(kept)["as_run"])
        assert calls.count("read_bytes") == 4, "…and read again once the system removed the round"
    finally:
        hold_places(ex.files, False)
