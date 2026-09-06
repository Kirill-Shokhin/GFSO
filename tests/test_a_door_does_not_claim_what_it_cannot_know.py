"""Two surfaces asserted facts they had no way to hold, and both cost real money.

**The bridge.** When the shared server restarts, the MCP bridge answers the calls left in flight. It
said: *"the call was not answered and no work of yours was lost by it; send it again"* -- a claim
about the FAR SIDE of a connection that had just broken. Wave 26 (2026-09-06) hit it three times in
one run and it was wrong in both directions: once the `auto_decompose` HAD run and built the whole
subtree, so obeying the advice bought a second refine round; twice a `validate_result` HAD started,
and the resend was suppressed as a duplicate with its `model=opus` silently dropped.

**The parameter hint.** `revise` takes a `reason` from a closed set, and the refusal listed it as
though it were free text -- *"(it also takes reason)"*. A caller wrote a sentence explaining their
revision and was refused by an enum they had no way to know existed. The words were already owned
once, in `PARAM_CHOICES`, which that door imports for its own schema: the refusal simply did not use
what the schema knew.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import gfso.mcp.connect as connect
import gfso.tools as T
from gfso.api import server
from gfso.api.server import _named


def test_the_bridge_reports_the_break_not_a_verdict_on_the_call():
    src = Path(inspect.getfile(connect)).read_text(encoding="utf-8")
    # The sentence survives ONLY as the comment recording why it went. What must be gone is the
    # claim itself, which the reader was given.
    assert '"the shared server restarted and this bridge is rebuilding — the call was not "' not in src, (
        "the bridge is asserting what happened on the other side of a broken connection")
    assert "not knowable from here" in src
    for where_to_look in ("get_graph", "get_verdict", "usage"):
        assert where_to_look in src, f"the reader is not told to check {where_to_look}"


def test_a_closed_set_is_spelled_where_the_parameter_is_named():
    reason = next(p for p in list(inspect.signature(T.TOOLS["revise"]).parameters.values())[1:]
                  if p.name == "reason")
    printed = _named("revise", reason)
    assert printed.startswith("reason: ")
    for word in ("spec_defect", "scope_expansion", "capability_mismatch", "other"):
        assert word in printed, printed


def test_a_free_parameter_is_still_printed_plainly():
    """The control: a rule that decorated every parameter would make the hint unreadable."""
    agent = next(p for p in list(inspect.signature(T.TOOLS["revise"]).parameters.values())[1:]
                 if p.name == "agent")
    assert _named("revise", agent) == "agent"


def test_the_choices_have_one_owner():
    """`PARAM_CHOICES` already existed and this door already imported it. A second table here would
    have been the same defect in a new place -- which is what the first cut of this fix built."""
    assert "PARAM_CHOICES" in Path(inspect.getfile(server)).read_text(encoding="utf-8")
    assert not any(n.startswith("_CHOICES") for n in dir(server))
