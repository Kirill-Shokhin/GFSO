"""`gfso up` had a reason for every outcome and printed none of them.

`ensure_correct` decides whether to reconcile the one shared server, and every branch of that
decision composes a sentence: reconciled, restarted, already current, or left alone because somebody
is connected, because work is in flight, because the server refused to stop, or because
`GFSO_NO_RECONCILE` asked for a report rather than a reconciliation. The CLI branch read one key,
`action`, mapped it to an exit code and dropped the rest — so `gfso up` exited 1 in total silence.

Measured on this repository's own server, 2026-09-07: exit 1 with no output was read as "another
session is connected" when the truth was `GFSO_NO_RECONCILE is set — reporting, not reconciling`,
and the next command was chosen on that misreading. When the sentence was printed, the very next
invocation said something worth acting on — that the server was two fingerprints behind the tree AND
held one other session — which had been invisible until then.

Two halves, and the first draft of this file only had the second:

  1. the PRODUCT must carry the reason in what it RETURNS. Four of the five branches printed their
     sentence to stderr and returned a dict without it, so `why` existed on one return of five and
     the door had nothing to print for the rest. A first version of this test hand-authored
     `{"action", "drift", "why"}` for every case — the key the product did not set — and would have
     stayed green with the defect fully restored. That is the "fixture supplies what the defect
     removed" shape, so the cases below drive the real `ensure_correct` and the real `_left_alone`
     instead of a dict written here.
  2. the narration must come from ONE printer. Printing in the door as well said everything
     twice, and silencing the reconciler to stop that swallowed its progress lines — so the verb
     that makes the decision is the verb that narrates it, and the door owns only the exit code.

This is the rule `Engine.refusal_of` already keeps — "a caller who cannot tell them apart cannot
tell 'wrong button' from 'not yet' from 'not yours'" — applied to the verb that reconciles the
installation.
"""
from __future__ import annotations

import pytest

from gfso import cli
import gfso.mcp.connect as connect


# ---- half one: the product's own return shapes, exercised for real ----------------------------

def test_every_left_alone_branch_returns_the_sentence_it_prints(capsys) -> None:
    """`_left_alone` is the single owner of the three "somebody is on it" refusals.

    It exists because those three composed a reason, printed it, and returned a dict without it.
    Driving the real helper is what makes this test see the defect: nothing here supplies `why`."""
    out = connect._left_alone(["code aaaa != tree bbbb"], "bbbb",
                              "the server is not current, and 1 other session(s)")

    assert out["action"] == "left-alone"
    assert out["why"] == "the server is not current, and 1 other session(s)", out
    assert out["drift"] == ["code aaaa != tree bbbb"]
    assert "the server is not current" in capsys.readouterr().err   # …and it is still narrated


def test_the_reporting_only_branch_returns_its_sentence(monkeypatch) -> None:
    """The branch that actually misled a reader, driven end to end with no server involved."""
    monkeypatch.setenv("GFSO_NO_RECONCILE", "1")
    monkeypatch.delenv("GFSO_RECONCILE", raising=False)

    out = connect.ensure_correct(force=False)

    assert out["action"] == "left-alone"
    assert "GFSO_NO_RECONCILE" in (out.get("why") or ""), out


# ---- half two: the branch that was actually silent now speaks -------------------------------

def test_the_reporting_only_branch_is_narrated_too(monkeypatch, capsys) -> None:
    """It is the one a caller hits most, and it printed NOTHING — which is the whole defect.

    The other three left-alone branches always wrote to stderr; this one returned a bare dict, so
    `gfso up` under `GFSO_NO_RECONCILE` exited 1 with an empty terminal. Routing it through
    `_left_alone` gives it the same narration as its three siblings, from one owner.

    The door itself prints nothing extra ON PURPOSE, and that is worth a line here because the
    obvious repair was to print in the CLI: `ensure_correct(verbose=True)` already emits the same
    sentence, so a second print said everything twice, and passing `verbose=False` to stop it also
    swallowed the "the server did not come up (attempt N/3) — retrying" progress lines. One printer,
    inside the verb that makes the decision."""
    monkeypatch.setenv("GFSO_NO_RECONCILE", "1")
    monkeypatch.delenv("GFSO_RECONCILE", raising=False)

    out = connect.ensure_correct(force=False)

    assert "GFSO_NO_RECONCILE" in (out.get("why") or ""), out
    assert "GFSO_NO_RECONCILE" in capsys.readouterr().err, "the branch that was silent is still silent"


def test_up_exits_non_zero_exactly_when_it_left_the_server_alone(monkeypatch) -> None:
    """The exit code is the part a script reads, and it is the CLI's own contribution."""
    for action, code in (("left-alone", 1), ("restarted", 0), ("already-correct", 0)):
        monkeypatch.setattr(connect, "ensure_correct",
                            lambda force=False, verbose=True, _a=action: {
                                "action": _a, "drift": [], "why": f"the reason it {_a}"})
        monkeypatch.setattr("sys.argv", ["gfso", "up"])
        with pytest.raises(SystemExit) as exit_:
            cli.main()
        assert exit_.value.code == code, action


def test_up_narrates_exactly_once(capsys, monkeypatch) -> None:
    """ONE printer — asserted through the door, because that is where it went wrong twice.

    The reason is narrated by the verb that decides, and the door adds nothing. That was got wrong
    in both directions on the same day: first the door printed nothing at all (the branch a caller
    hits most returned silently), then the door printed what the reconciler had already printed, so
    `gfso up` said everything twice and the drift three times. The second was found by review, not
    by this file — because the only test that drove `cli.main()` asserted the exit code and captured
    no output at all. Zero narration was held; DOUBLE narration, the defect that actually recurred,
    was not.

    The real `ensure_correct` is used, on the one branch that needs no server, so the count is over
    the product's own output rather than over a stub's.
    """
    monkeypatch.setenv("GFSO_NO_RECONCILE", "1")
    monkeypatch.delenv("GFSO_RECONCILE", raising=False)
    monkeypatch.setattr("sys.argv", ["gfso", "up"])

    with pytest.raises(SystemExit) as exit_:
        cli.main()

    said = capsys.readouterr()
    lines = [ln for ln in (said.out + said.err).splitlines()
             if "GFSO_NO_RECONCILE" in ln]
    assert exit_.value.code == 1
    assert len(lines) == 1, (
        f"`gfso up` narrated its reason {len(lines)} times, not once: {lines}. One printer — the "
        f"verb that makes the decision; the door owns the exit code and nothing else."
    )
