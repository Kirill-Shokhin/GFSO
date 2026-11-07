"""A finding is demanded of every later round only if it can see what that round delivered.

GB_sql_database_tn9kf3836 (2026-10-22): the validator filed `printf 'SELECT 1 + FROM t' | <scratch>/<round>/x/chk` — a
binary it had built from the source of THAT round — and every later round ran that old build as given: root.parse_stmt
failed 7 times in 33 minutes while its pinned check passed. Told by the FILE, not the shell's syntax: a wrapper, a second
line or a test would hide it from a parse, and a script or a Makefile there runs the delivery."""
import pytest

from gfso.core.protocol.procedure import refuting_probes, runs_a_past_build, without_past_builds


@pytest.fixture
def scratch(tmp_path):
    rnd = tmp_path / ".gfso-scratch-root.p" / "root.p_1792597828"
    (rnd / "x").mkdir(parents=True)
    (rnd / "x" / "chk").write_bytes(b"\x7fELF\x02\x01\x01\x00\x00built")
    (rnd / "t.c").write_text("int main(void) { return 0; }\n")
    (rnd / "t.sh").write_text("#!/bin/sh\n./sql_database < q.sql\n")
    (rnd / "t.db").write_bytes(b"SQLite format 3\x00\x10\x00\x01\x01")
    (rnd / "nul.in").write_bytes(b"SELECT 1;\x00\n")
    return rnd.as_posix()


@pytest.mark.parametrize("command", [
    "printf x | {s}/x/chk", "printf x | timeout 5 {s}/x/chk", "env LC_ALL=C {s}/x/chk < in", "valgrind {s}/x/chk",
    "printf x > in\n{s}/x/chk < in", "if {s}/x/chk < in; then echo y; fi", "! {s}/x/chk < in",
    "gcc -o {s}/x/chk2 a.c && {s}/x/chk"])
def test_a_past_round_s_build_is_seen_in_any_shape(scratch, command):
    assert runs_a_past_build(command.format(s=scratch))


@pytest.mark.parametrize("command", [
    "gcc -o {s}/x/chk a.c && {s}/x/chk", "make -C {s}/x && {s}/x/chk", "cp ./sql_database {s}/x/chk && {s}/x/chk",
    "cc a.c --output={s}/x/chk && {s}/x/chk", "{s}/t.sh", "gcc -I. {s}/t.c lexer.c -o $T/x && $T/x",
    "printf x | {s}/gone/chk", "printf x | ./sql_database",
    # data the delivery reads, not a build: its own database file, an input of NUL bytes
    "rm -f {s}/t.db; ./sql_database {s}/t.db < a.sql && ./sql_database {s}/t.db < b.sql", "./sql_database < {s}/nul.in",
    "cd {s}/x && gcc -o chk ../t.c src/*.c && {s}/x/chk"])
def test_what_runs_the_delivery_stays_a_finding(scratch, command):
    assert not runs_a_past_build(command.format(s=scratch))


def test_it_is_neither_filed_nor_demanded(scratch):
    """Not filed while the round's files stand; and one filed before the rule is not demanded either."""
    report = [{"criterion": "conf", "verdict": "fail", "probe": [
        {"command": f"printf x | {scratch}/x/chk", "expect": "ERR"},
        {"command": f"gcc -I. {scratch}/t.c lexer.c -o $T/x && $T/x", "expect": "ERR"}]}]
    assert [p["as_run"] for p in refuting_probes(report)["conf"]] == [f"gcc -I. {scratch}/t.c lexer.c -o $T/x && $T/x"]
    stored = {"conf": [{"id": "conf#1", "as_run": f"printf x | {scratch}/x/chk"}, {"id": "conf#2", "command": "./t"}],
              "other": [{"id": "other#1", "as_run": f"valgrind {scratch}/x/chk"}]}
    assert without_past_builds(stored) == {"conf": [{"id": "conf#2", "command": "./t"}]}
