"""In a delegated graph the issuer is a machine, so somebody has to make his move.

v4.1 admits CHALLENGE after consent (§12.4), which is where the spec defects the a-priori battery
cannot see actually arrive. That gives the dispute its two closures back — and puts them in the
hands of a party the driver had never called: CHALLENGED is the ISSUER's state, and nothing in a
delegated run answered it. The node would wait out its bound and escalate, which is the stall this
loop has already been measured paying for (2026-08-21, before the edge existed: a leaf contested
mid-rework at 01:27 and the run ended `graph_stalled` twenty-five minutes later).

Whether a contract can be met as written is a DECISION, so the answer costs a call — unlike a
blocker, which resolves by a rule. What the tests pin is that both answers land as the protocol's
own signals, and that an accepted dispute cannot quietly shrink the goal.
"""
from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

import pytest

import gfso.tools as T
from gfso.delegate import ISSUER_VERBS
from gfso.issuer import Unavailable, Verbs, answer_the_challenge, settle
from gfso.core.types import State, TaskId
from tests.support import criterion, make_engine, REGISTER

_RISK = REGISTER


class _IssuerLLM:
    def __init__(self, payload):
        self._text = "```json\n" + json.dumps(payload) + "\n```"
        self.calls = []
        self.packets = []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.packets.append(user)
        self.calls.append({"duration_ms": 400, "output_tokens": 40})
        return self._text

    def complete(self, prompt, context=""):
        return self.run_agent(context, prompt, ())

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _disputed(e):
    T.create_task(e, "leaf", {"description": "a leaf", "criteria": [criterion("c", "C")],
                              "accepted_risks": _RISK}, assignee="worker")
    e.wait_idle()
    T.signal(e, "leaf", "ACCEPT", "worker")
    T.signal(e, "leaf", "CHALLENGE", "worker", reason="criterion c contradicts the goal's own scope")
    e.wait_idle()
    assert e.graph.get_state(TaskId("leaf")) == State.CHALLENGED


def test_a_rejected_dispute_returns_the_work_with_its_justification():
    e = make_engine()
    e.start()
    try:
        _disputed(e)
        llm = _IssuerLLM({"decision": "reject",
                          "justification": "c is satisfiable: the goal's scope includes the parser"})
        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=llm)
        e.wait_idle()
        assert out["status"] == "rejected"
        assert e.graph.get_state(TaskId("leaf")) == State.EXECUTING, "the contract stands, so work resumes"
        assert e.graph.get_task("leaf").iteration == 0, "a rejection spends no rework round"
        assert "criterion c contradicts" in llm.packets[0], "the issuer decided without the dispute"
    finally:
        e.stop()


def test_an_accepted_dispute_re_authors_the_contract_and_asks_for_consent():
    e = make_engine()
    e.start()
    try:
        _disputed(e)
        fixed = dict(criterion("c", "C, stated so it can be met"))
        llm = _IssuerLLM({"decision": "accept", "justification": "c was undecidable as written",
                          "criteria": [fixed]})
        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=llm)
        e.wait_idle()
        assert out["status"] == "accepted"
        t = e.graph.get_task("leaf")
        assert t.state == State.OFFERED, "a new contract binds only once its executor consents"
        assert t.spec.criteria[0].description == "C, stated so it can be met"
        assert t.spec.criteria[0].check, "the re-authored criterion must still pin its procedure"
    finally:
        e.stop()


def _two_criteria_disputed(e, reason):
    T.create_task(e, "leaf", {"description": "a leaf",
                              "criteria": [criterion("c", "C"), criterion("d", "D")],
                              "accepted_risks": _RISK}, assignee="worker")
    e.wait_idle()
    T.signal(e, "leaf", "ACCEPT", "worker")
    T.signal(e, "leaf", "CHALLENGE", "worker", reason=reason)
    e.wait_idle()


def test_an_accepted_dispute_may_not_shrink_the_goal_around_itself():
    """The failure `issuer.md` warns against, with nothing between it and the graph: the dispute is
    the EXECUTOR's and the replacement is written by a machine issuer, so dropping a criterion
    NOBODY questioned is the cheapest way to end the argument — a promise abandoned in silence."""
    e = make_engine()
    e.start()
    try:
        _two_criteria_disputed(e, reason="d cannot be met as written")
        llm = _IssuerLLM({"decision": "accept", "justification": "while I am here, c goes too",
                          "criteria": [criterion("d", "D, reworded")]})
        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=llm)
        e.wait_idle()
        assert out["status"] == "would_narrow" and out["dropped"] == ["c"]
        assert e.graph.get_state(TaskId("leaf")) == State.CHALLENGED, "the dispute still stands"
        assert {x.name for x in e.graph.get_task("leaf").spec.criteria} == {"c", "d"}
    finally:
        e.stop()


def test_it_may_drop_the_criterion_the_dispute_itself_questioned():
    """The control, and the canon's own worked answer: where two criteria cannot both hold, §14.3
    resolves the dispute by ACCEPT_CHALLENGE REMOVING one. A blanket refusal would take the
    positive closure away from an automatic issuer altogether (§16.12) — which is a lost channel,
    not strictness."""
    e = make_engine()
    e.start()
    try:
        _two_criteria_disputed(e, reason="c and d contradict: d forbids what c requires")
        llm = _IssuerLLM({"decision": "accept",
                          "justification": "d contradicts c; the goal keeps c",
                          "criteria": [criterion("c", "C")]})
        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=llm)
        e.wait_idle()
        assert out["status"] == "accepted"
        assert {x.name for x in e.graph.get_task("leaf").spec.criteria} == {"c"}
        assert e.graph.get_state(TaskId("leaf")) == State.OFFERED
    finally:
        e.stop()


def test_an_accept_that_names_no_contract_is_not_a_rejection():
    """It fell through to REJECT_CHALLENGE carrying the ACCEPTANCE's justification — the executor
    sent back under the disputed contract with a text saying the issuer agreed with him."""
    e = make_engine()
    e.start()
    try:
        _disputed(e)
        out = answer_the_challenge(e, TaskId("leaf"), "worker",
                                   _llm=_IssuerLLM({"decision": "accept",
                                                    "justification": "you are right"}))
        e.wait_idle()
        assert out["status"] == "unparsed"
        assert e.graph.get_state(TaskId("leaf")) == State.CHALLENGED
    finally:
        e.stop()


def test_an_unparsable_adjudication_forges_no_signal():
    """The executor path's rule, for its reason: a broken report is not a decision. The node stays
    where it is and its own bound carries it to the issuer's attention."""
    e = make_engine()
    e.start()
    try:
        _disputed(e)

        class _Broken(_IssuerLLM):
            def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
                self.calls.append({"duration_ms": 10, "output_tokens": 1})
                return "I think the contract is fine, honestly"

        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=_Broken({}))
        e.wait_idle()
        assert out["status"] == "unparsed"
        assert e.graph.get_state(TaskId("leaf")) == State.CHALLENGED
    finally:
        e.stop()


def test_the_issuer_answers_through_the_zero_tool_port():
    """`run_agent` without a working directory is refused by the real transport, and the issuer asked
    through it — so no machine issuer ever answered a real dispute; the fakes accepted the missing
    argument. The issuer needs no tools, and its call now goes where no directory is asked for."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    try:
        _disputed(e)

        class _StrictLLM(_IssuerLLM):
            def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
                if not cwd:
                    raise ValueError("an agent run needs a working directory")
                return super().run_agent(system, user, allowed_tools, cwd, timeout)

            def complete(self, prompt, context=""):
                self.packets.append(prompt)
                self.calls.append({"duration_ms": 1, "output_tokens": 1})
                return self._text

        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=_StrictLLM(
            {"decision": "reject", "justification": "c reads as written"}))
        assert out["status"] == "rejected", out
    finally:
        e.stop()


class _ContactLLM(_IssuerLLM):
    """The real transport's shape where the issuer is given the workspace: an agent run in a directory, its
    tool ledger kept beside the answer (`last_tool_calls`, reset per run)."""

    def __init__(self, payload, ran):
        super().__init__(payload)
        self._ran, self.last_tool_calls, self.where = ran, {}, []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.where.append((cwd, tuple(allowed_tools)))
        self.last_tool_calls = dict(self._ran)
        return super().run_agent(system, user, allowed_tools, cwd, timeout)


def test_a_rejection_that_ran_nothing_is_not_an_answer(tmp_path):
    """GB_coreutils_tmiy4m001, 2026-10-07: the machine issuer rejected a true challenge — "the oracle prints its own
    path, so this cmp can never pass" — twelve times on a belief about GNU `head` that one run refutes, and the
    node was cancelled for it. A dispute says what a check does in the world; with the workspace in hand, a
    rejection that touched nothing is refused and the dispute stands."""
    e = make_engine()
    e.start()
    try:
        _disputed(e)
        llm = _ContactLLM({"decision": "reject", "justification": "gnulib strips the directory"}, ran={"Read": 2})
        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=llm, where=str(tmp_path))
        e.wait_idle()
        assert out["status"] == "uncontacted" and "ran nothing" in out["why"], out
        assert e.graph.get_state(TaskId("leaf")) == State.CHALLENGED, "the dispute still stands"
        assert llm.where == [(str(tmp_path), ("Read", "Bash", "Glob", "Grep"))], "it stood in the node's workspace"
        assert str(tmp_path) in llm.packets[0], "and was told where it stands"
    finally:
        e.stop()


def test_a_rejection_that_ran_the_check_lands(tmp_path):
    """The control: the same rejection, its run having used the shell, returns the work."""
    e = make_engine()
    e.start()
    try:
        _disputed(e)
        llm = _ContactLLM({"decision": "reject", "justification": "ran `c`'s check: it passes on the reference"},
                          ran={"Bash": 3, "Read": 1})
        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=llm, where=str(tmp_path))
        e.wait_idle()
        assert out["status"] == "rejected", out
        assert e.graph.get_state(TaskId("leaf")) == State.EXECUTING
    finally:
        e.stop()


def test_an_acceptance_needs_no_run(tmp_path):
    """Accepting is bounded otherwise — the narrowing rules and the executor's fresh consent — so contact is asked
    of the rejection only; an acceptance from a run that touched nothing installs its contract."""
    e = make_engine()
    e.start()
    try:
        _disputed(e)
        llm = _ContactLLM({"decision": "accept", "justification": "c was undecidable as written",
                           "criteria": [dict(criterion("c", "C, stated so it can be met"))]}, ran={})
        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=llm, where=str(tmp_path))
        e.wait_idle()
        assert out["status"] == "accepted", out
    finally:
        e.stop()


def test_the_sweep_hands_the_dispute_its_workspace(tmp_path):
    """The wiring the rule stands on: `settle` asks the dispatcher's `place` where the node's work is and the issuer
    is run there — twice, the second time told why the first was refused — and a rejection that never ran a
    shell leaves the dispute standing."""
    assert ISSUER_VERBS.place is not None, "the product's dispatcher hands the issuer a place"
    e = make_engine()
    e.start()
    try:
        _disputed(e)
        llm = _ContactLLM({"decision": "reject", "justification": "it stands"}, ran={"Grep": 1})
        verbs = Verbs(llm=lambda model: llm, busy=lambda *a: contextlib.nullcontext(), review=None, refine=None,
                      place=lambda engine, agents, node: str(tmp_path))
        out = settle(e, {}, TaskId("leaf"), "dispute", "worker", verbs)
        e.wait_idle()
        assert out["status"] == "uncontacted", out
        assert [w for w, _ in llm.where] == [str(tmp_path)] * 2
        assert "ran nothing" in llm.packets[1], "the retry is told why the first answer was refused"
        assert e.graph.get_state(TaskId("leaf")) == State.CHALLENGED
    finally:
        e.stop()


def test_an_accepted_dispute_that_rewrites_a_probe_keeps_its_pinned_inputs(tmp_path):
    """The issuer sees only that a probe's inputs exist, never their contents; a corrected command dropped them and
    `{inputs}/opts.txt` stayed unresolved — a probe that prints "No such file" and then its `ok` (critic over session
    a597fc08). A rewritten command that still reads `{inputs}` carries the criterion's pinned files."""
    old = "while read l; do cmp <(/usr/bin/head $l) <(./head $l) || echo DIFF $l; done < {inputs}/opts.txt; echo ok"
    new = old.replace("/usr/bin/head $l)", "/usr/bin/head $l 2>&1 | sed 's#^/usr/bin/head#head#')")
    crit = lambda cmd, **kw: {"name": "c", "description": "head matches the oracle on every option form",
                              "check": [{"behaviour": "forms", "command": cmd, "expect": "ok", **kw}]}
    e = make_engine()
    e.start()
    try:
        T.create_task(e, "leaf", {"description": "a leaf", "accepted_risks": _RISK,
                                  "criteria": [crit(old, inputs={"opts.txt": "-n 2\n-n abc\n"})]}, assignee="worker")
        e.wait_idle()
        pinned = e.graph.get_task("leaf").spec.criteria[0].check[0].inputs
        assert pinned
        T.signal(e, "leaf", "ACCEPT", "worker")
        T.signal(e, "leaf", "CHALLENGE", "worker", reason="criterion c: the oracle prints /usr/bin/head as its name")
        e.wait_idle()
        llm = _ContactLLM({"decision": "accept", "justification": "ran it", "criteria": [crit(new)]}, ran={"Bash": 2})
        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=llm, where=str(tmp_path))
        e.wait_idle()
        probe = e.graph.get_task("leaf").spec.criteria[0].check[0]
        assert out["status"] == "accepted" and probe.command == new, out
        assert probe.inputs == pinned, "the corrected command still reads the files it was pinned with"
    finally:
        e.stop()


def test_the_issuer_runs_a_probe_over_its_pinned_inputs_and_answers_in_the_contracts_terms(tmp_path):
    """Its packet showed `{inputs}` literal and no file was written: run as shown, a probe printed "No such file" and
    then its `ok`, and a rejection on that passed the shell rule having checked nothing (critic over session
    a597fc08). The inputs are laid down as a validator's are, the command shown runnable; an answer naming that
    directory is stored with `{inputs}`, the pinned files kept."""
    cmd = "while read l; do ./head $l; done < {inputs}/opts.txt; echo ok"
    crit = {"name": "c", "description": "head handles every option form",
            "check": [{"behaviour": "forms", "command": cmd, "expect": "ok", "inputs": {"opts.txt": "-n 2\n"}}]}
    e = make_engine()
    e.start()
    try:
        T.create_task(e, "leaf", {"description": "a leaf", "accepted_risks": _RISK, "criteria": [crit]},
                      assignee="worker")
        e.wait_idle()
        T.signal(e, "leaf", "ACCEPT", "worker")
        T.signal(e, "leaf", "CHALLENGE", "worker", reason="criterion c cannot pass as written")
        e.wait_idle()
        seen = {}

        class _Runs(_ContactLLM):
            def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
                d = re.search(r"< (\S+)/opts\.txt", user).group(1)
                seen["file"] = (Path(d) / "opts.txt").read_text()
                super().run_agent(system, user, allowed_tools, cwd, timeout)
                return "```json\n" + json.dumps({"decision": "accept", "justification": "ran it", "criteria": [
                    {**crit, "check": [{"behaviour": "forms", "expect": "ok",
                                        "command": f"while read l; do ./head $l 2>&1; done < {d}/opts.txt; echo ok"}]}]}) \
                    + "\n```"

        out = answer_the_challenge(e, TaskId("leaf"), "worker", _llm=_Runs({}, ran={"Bash": 1}), where=str(tmp_path))
        e.wait_idle()
        probe = e.graph.get_task("leaf").spec.criteria[0].check[0]
        assert seen["file"] == "-n 2\n", "the issuer's run read the pinned file"
        assert out["status"] == "accepted" and probe.command.endswith("< {inputs}/opts.txt; echo ok"), probe.command
        assert dict(probe.inputs) == {"opts.txt": "-n 2\n"}
    finally:
        e.stop()


def test_a_cut_contact_run_is_not_the_issuers_answer(tmp_path):
    """An agent run of minutes is where calls are severed; read as an unparsed answer, three of them closed the node by
    its issuer (critic over session a597fc08). A cut run is no answer: nothing is counted, the question is asked
    again later."""
    e = make_engine()
    e.start()
    try:
        _disputed(e)

        class _Cut(_ContactLLM):
            def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
                super().run_agent(system, user, allowed_tools, cwd, timeout)
                self.calls[-1]["transport_torn"] = True
                return "Let me run the disputed check first"

        with pytest.raises(Unavailable):
            answer_the_challenge(e, TaskId("leaf"), "worker", _llm=_Cut({}, ran={"Bash": 1}), where=str(tmp_path))
        assert e.graph.get_state(TaskId("leaf")) == State.CHALLENGED
    finally:
        e.stop()
