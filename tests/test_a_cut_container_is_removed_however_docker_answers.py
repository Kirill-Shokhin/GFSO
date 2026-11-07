"""A container cut while Docker makes it appears after a removal: each repeat is owed, and a removal that itself ran out of
time, on the slow Docker cuts happen under, left the loop before any of them."""
import subprocess

import pytest

import gfso.adapters.execution as E


def _docker(monkeypatch, answers):
    asked = []

    def run(args, **kw):
        asked.append(args)
        if isinstance(a := answers[min(len(asked), len(answers)) - 1], Exception):
            raise a
        return subprocess.CompletedProcess(args, a)

    monkeypatch.setattr(E, "run", run)
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    return asked


def test_every_repeat_is_attempted_whatever_a_removal_raised(monkeypatch):
    asked = _docker(monkeypatch, [subprocess.TimeoutExpired("docker", 60), OSError("no docker"), 1, 0])
    E._end_cut("cut")
    assert asked == [["docker", "rm", "-f", "cut"]] * 4


def test_its_caller_still_raises_the_cut_itself(monkeypatch):
    cut = subprocess.TimeoutExpired("docker run", 60)

    def run(args, **kw):
        raise cut if args[1] == "run" else subprocess.TimeoutExpired("docker other", 60)

    monkeypatch.setattr(E, "run", run)
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        E._files_changed("vol", {"sub": "new"}, "image")
    assert raised.value is cut
