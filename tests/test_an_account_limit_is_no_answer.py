"""A call the account's limit refused answered nothing, at every door: it spends no retry, parks no node, and is asked
again when the limit can have lifted.

Measured on GB_c_compiler_tncfs1160 (haiku 4.5, 2026-10-23): token b's five-hour window closed at 08:00 UTC, the CLI came
back with "api_error: You've hit your session limit · resets 10:30am (UTC)", and the dispatcher read two such sessions as
an unreadable executor report — retried once, then PARKED `root.base.semantic.sem_analyzer`, which no answer of the
machine issuer unparked; the validator door re-asked every 30 s and the node's VALIDATING bound ran out on errors. The
words "session limit" were in none of the readers' lists, and the envelope's own `api_error: usage_limit_reached` was
dropped before any reader saw it."""
from __future__ import annotations

import io
import time
import types

import json

import pytest

import gfso.decompose as DEC
import gfso.tools as T
import gfso.tools_llm as TL
from gfso import delegate as D
from gfso import sessions as S
from gfso.adapters import execution as E
from gfso.adapters.llm import headless as H
from gfso.adapters.llm.stats import is_limit, refused_by_limit
from gfso.delegate import Dispatcher
from gfso.core.types import TaskId
from gfso.critic.runner import _already_decided, _criterion_stamps
from gfso.issuer import Unavailable, Verbs, _what_happened, settle, unanswered
from tests.test_a_cut_call_does_not_spend_the_nodes_retry import _a_delivery, _an_offer
from tests.support import hold_a_credential, make_engine
from tests.test_equal_fails_do_not_measure_kappa import _leaf, _leaves
from tests.test_one_session_carries_a_scope import _project
from tests.test_delegate import _agents

#: The envelope the CLI wrote for that session (agent trace 20261023T080135-8dd47b36, `result` event).
LIMIT_ENVELOPE = {"is_error": True, "subtype": "success", "terminal_reason": "api_error", "api_error_status": 429,
                  "api_error": "usage_limit_reached", "result": "You've hit your session limit · resets 10:30am (UTC)"}


class _Proc:
    stdin = io.StringIO()

    def wait(self, timeout=None):
        return 0


def test_the_adapter_records_the_limit_where_its_readers_look(monkeypatch, tmp_path):
    monkeypatch.setattr(H.subprocess, "Popen", lambda args, **kw: _Proc())
    monkeypatch.setattr(H.ClaudeCodeProvider, "_read_stream", lambda self, p, t0, cap: (dict(LIMIT_ENVELOPE), [], 0))
    for name in ("adopt", "kill_tree", "release"):
        monkeypatch.setattr(E, name, lambda p: p)
    hold_a_credential(monkeypatch, tmp_path)
    llm = H.ClaudeCodeProvider()
    llm._cmd = "claude"
    assert llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp_path)) == ""
    assert "usage_limit_reached" in llm.calls[-1]["error"], llm.calls[-1]
    assert refused_by_limit(llm.calls)


def test_the_cli_words_for_its_window_are_a_limit_and_other_errors_are_not():
    assert is_limit("api_error: You've hit your session limit · resets 10:30am (UTC)")   # before the adapter kept api_error
    assert unanswered([{"error": "api_error: You've hit your session limit · resets 10:30am (UTC)"}]).limit
    for other in ("max_turns: ", "error_during_execution: Prompt is too long", "api_error: Overloaded",
                  "context limit reached", None):
        assert not is_limit(other), other


def test_an_executor_session_the_limit_ended_is_asked_again_not_parked(tmp_path, monkeypatch):
    """The pair: the same unparsed session, with and without the limit — only the limit is spared the park."""
    monkeypatch.setattr(D, "LIMIT_RETRY_S", 0)
    for limit, want_parked in ((True, False), (False, True)):
        e = make_engine(validate_signals=True, state_timeout=0)
        e.start()
        agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
        _an_offer(e)
        said, runs = [], []
        e.emit_info = lambda src, msg, _s=said: _s.append(msg)
        d = Dispatcher(e, agents, runner=lambda *a, _l=limit: runs.append(1) or {"status": "unparsed", "limit": _l})
        for _ in range(4):
            d.dispatch_once()
            time.sleep(0.6)
        parked = "kid" in {str(x) for x in e.parking.parked_executions()}
        e.stop()
        assert parked == want_parked, (limit, said)
        assert limit == any("usage limit" in m for m in said), said
        if limit:
            assert len(runs) >= 3, f"the round was not given back after the limit: {len(runs)} run(s)"


def test_a_validation_the_limit_refused_spends_no_retry_and_buys_no_tier(tmp_path, monkeypatch):
    """The dispatcher's reading of the validator door's answer: two verdict-less validations park where no re-ask
    applies — the control; two limit-refused ones do not, and no stronger tier is bought for a refusal no model saw."""
    monkeypatch.setattr(D, "LIMIT_RETRY_S", 0)
    monkeypatch.setenv("GFSO_VALIDATOR_RETRY_MODEL", "opus")
    for ret, want_parked in (("no-verdict:limit", False), ("no-verdict", True)):
        e = make_engine(validate_signals=True, state_timeout=0)
        e.start()
        agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
        _a_delivery(e)
        tiers = []
        d = Dispatcher(e, agents, runner=lambda *a: None,
                       validator_runner=lambda en, t, ag, model_override=None, sign=True, _r=ret:
                       tiers.append(model_override) or _r)
        for _ in range(4):
            d.dispatch_once()
            time.sleep(0.6)
        parked = "kid" in {str(x) for x in e.parking.parked_validations()}
        e.stop()
        assert parked == want_parked, (ret, tiers)
        if ret == "no-verdict:limit":
            assert len(tiers) >= 3 and all(t is None for t in tiers), tiers


def test_the_validator_door_reads_the_limit_off_the_calls():
    """`_auto_validate`'s classification: a run any of whose calls the limit refused is `no-verdict:limit`."""
    e = make_engine()
    ret = D._classify_no_verdict(e, "kid", {"verdict": None, "stats": [
        {"error": "api_error: usage_limit_reached: You've hit your session limit"}]})
    assert ret == "no-verdict:limit"
    assert D._classify_no_verdict(e, "kid", {"verdict": None, "stats": [{"error": None, "cost_usd": 0.1}]}) == "no-verdict"


def test_the_runners_say_which_session_the_limit_ended(monkeypatch, tmp_path):
    """The wire between the session and the dispatcher: `run_executor`, `run_scope_executor` and `run_consent` mark a
    session the limit ended — and only such a session."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _an_offer(e)
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.signal(e, "kid", "ACCEPT", "exec-1")
    monkeypatch.setattr(S, "_enter_workspace", lambda engine, agents_, task, order: (str(tmp_path), [], None))
    monkeypatch.setattr(S, "_executor_packet", lambda *a, **k: "packet")
    monkeypatch.setattr(S, "_scope_packet", lambda *a, **k: "packet")
    for err, want in (("api_error: usage_limit_reached: You've hit your session limit", True), (None, False)):
        llm = types.SimpleNamespace(calls=[{"error": err}])
        monkeypatch.setattr(S, "_spawn", lambda *a, _l=llm, **k: (None, "", [], _l, lambda m: None))
        assert S.run_executor(e, "kid", "exec-1", agents)["limit"] is want
        assert S.run_scope_executor(e, "kid", "exec-1", agents)["limit"] is want
    e.stop()


_LIMITED = {"verdict": None, "stats": [{"error": "api_error: usage_limit_reached: You've hit your session limit"}]}


def test_an_unsigned_validation_reads_the_limit_too(tmp_path, monkeypatch):
    """A person's node (or a holder's under SOLO/SEMI) is validated without the signature; that path returned a bare
    `no-verdict` before the classification was reached, so a limit-refused run spent the retry and parked (critic)."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _a_delivery(e)
    monkeypatch.setattr(D, "_validate_with", lambda *a, **k: dict(_LIMITED))
    assert D._auto_validate(e, "kid", agents, sign=False) == "no-verdict:limit"
    e.stop()


def test_the_scope_validation_door_reads_the_limit(monkeypatch):
    """The door every split one session carries is validated through (critic): a scope run the limit refused is
    `no-verdict:limit`, and the dispatcher waits it out instead of re-asking every 30 s."""
    e = make_engine()
    member = types.SimpleNamespace(id="kid", state=types.SimpleNamespace(name="VALIDATING"))
    monkeypatch.setattr(D, "_which_instrument_validates", lambda *a: "val-1")
    monkeypatch.setattr(D, "_standing_verdicts", lambda *a: {})
    monkeypatch.setattr(D, "validator_workdir", lambda *a, **k: None)
    monkeypatch.setattr(e, "scope_members", lambda top: [member])
    agents = types.SimpleNamespace(get=lambda k: {}, list=lambda: {})
    for stats, want in ((_LIMITED["stats"], "no-verdict:limit"), ([{"error": None}], "no-verdict")):
        monkeypatch.setattr(D.T, "validate_scope", lambda *a, _s=stats, **k: {"verdicts": {}, "stats": _s})
        assert D._auto_validate_scope(e, "root", agents) == want
    waits = []
    monkeypatch.setattr(D, "LIMIT_RETRY_S", 0)
    d = D.Dispatcher(e, agents, scope_validator=lambda *a, **k: "no-verdict:limit")
    monkeypatch.setattr(d._engine, "scope_members", lambda top: [])
    monkeypatch.setattr(d, "_scope_key", lambda members: "K")
    monkeypatch.setattr(d, "_give_back", lambda key, delay: waits.append(delay))
    d._validate_scope_guarded("root", "K")
    d._validate_scope_guarded("root", "K")
    assert waits == [0, 0] and not d._retried, (waits, d._retried)


class _LimitedProvider:
    """A provider every call of which the account's limit refuses, recording the error as the headless adapter does."""
    def __init__(self, *a, **k):
        self.calls, self.last_tool_calls, self.on_tick, self.stage_hint = [], {}, None, ""

    def run_agent(self, *a, **k):
        self.calls.append({"error": "api_error: usage_limit_reached: You've hit your session limit", "cost_usd": None,
                           "transport_torn": False, "duration_ms": 5})
        return ""

    def tag_last(self, stage):
        if self.calls:
            self.calls[-1]["stage"] = stage


def test_a_limit_refused_validation_leaves_no_refused_report(tmp_path):
    """The real door, no return value injected: a limit-refused validation is `no-verdict:limit` on both paths and
    books NO refused report — booked, each probe of a window raised the node's refusal count, so the next validation
    ran on the retry tier, the issuer was told to narrow the contract and the validator "attempt 16" (critic)."""
    (tmp_path / "work.py").write_text("x = 1\n")
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _a_delivery(e)
    for sign in (True, False, True):
        assert D._auto_validate(e, "kid", agents, _llm=_LimitedProvider(), sign=sign) == "no-verdict:limit", sign
    assert e.rejected_report("kid") is None, e.rejected_report("kid")
    e.stop()


class _LimitedModel(_LimitedProvider):
    """The same refusal on the one-shot doors the decomposer and the reviewer use."""
    def complete(self, *a, **k):
        self.run_agent()
        return ""

    def complete_structured(self, *a, **k):
        self.run_agent()
        return {}


def test_a_split_the_limit_refused_keeps_it_owed(tmp_path, monkeypatch):
    """A split its plan's author owes, asked of a model that hit its limit window: the round is unanswered, not "no split
    can be built" (critic r3), so the split stays owed."""
    e, agents, d = _leaves(tmp_path, monkeypatch)
    e.record_session_fit(TaskId("root.a"), "too big for one session", False)
    assert d._split_owed_said(_leaf(e))
    owed = e.split_owed(TaskId("root.a"))
    assert owed is not None
    monkeypatch.setattr(DEC, "_default_llm", lambda m, **_: _LimitedModel())
    verbs = Verbs(llm=lambda m: _LimitedModel(), busy=None, review=None, refine=D.ISSUER_VERBS.refine)
    with pytest.raises(Unavailable) as ex:
        settle(e, agents, TaskId("root.a"), "split", "exec-2", verbs)
    assert ex.value.limit and e.split_owed(TaskId("root.a")) == owed
    e.stop()


def test_a_review_the_limit_refused_keeps_the_verdicts_carried(tmp_path, monkeypatch):
    """Stored, a limit-refused review erased the verdicts an unchanged plan carries — the next readable round
    re-checked what was certified (critic r3)."""
    e, agents = _project(tmp_path)
    t = e.graph.get_task(TaskId("root"))
    e._graph._storage.store_critique(TaskId("root"), json.dumps({
        "node_id": "root", "gate_passed": True, "semantic_covered": False, "measured": True,
        "criteria_verdicts": [{"criterion": "g", "verdict": "sufficient"}], "criteria_stamps": _criterion_stamps(e, t)}))
    monkeypatch.setattr(TL, "llm_factory", lambda m=None, **_: _LimitedModel())
    TL.review_decomposition(e, "root")
    assert list(_already_decided(json.loads(e._graph._storage.get_critique(TaskId("root"))), t, e)) == ["g"]
    e.stop()


def test_the_issuers_packet_keeps_the_real_stop_reasons(tmp_path, monkeypatch):
    """A limit window's probes are not why the node's sessions stopped: kept, three of them evicted the reasons the
    section exists for (`prompt_too_long`, GB_sql_database_tmxu0n436); an unreadable report is still said — the pair."""
    monkeypatch.setattr(S, "_enter_workspace", lambda engine, agents_, task, order: (str(tmp_path), [], None))
    monkeypatch.setattr(S, "_executor_packet", lambda *a, **k: "packet")
    garbled = type("Garbled", (_LimitedProvider,), {"run_agent": lambda self, *a, **k: (
        self.calls.append({"error": None, "cost_usd": 0.01, "transport_torn": False}), "no report")[1]})
    for provider, said in ((_LimitedProvider, False), (garbled, True)):
        e = make_engine(validate_signals=True, state_timeout=0)
        e.start()
        _an_offer(e)
        agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
        T.signal(e, "kid", "ACCEPT", "exec-1")
        for _ in range(3):
            S.run_executor(e, "kid", "exec-1", agents, _llm=provider())
        section = [p for p in _what_happened(e, e.graph.get_task("kid")) if "stopped without a signal" in p]
        assert bool(section) == said, (provider.__name__, section)
        e.stop()
