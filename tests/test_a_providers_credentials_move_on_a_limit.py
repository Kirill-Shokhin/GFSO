"""A provider holds many credentials in its one place: every call starts on the one in force, and a limit moves it on.

The author, 2026-10-28: «внутри провайдера можно делать несколько или даже много разных токенов … все это … должно
заворачиваться в один канал в систему»; «просто чтобы ты нажал новый указатель и бесшовно все новые запросы пошли с него
… а старые дорабатывали на старом». So: the store before this shape reads into it, one value under two names being one
credential; a moved pointer reaches the next call of a provider made before the move; a call its credential's limit
refused runs again on the next one, its refused attempt stopping nothing; only with every one spent does the limit stand,
until the first of them lifts; and the ledger says which credential each call ran on.
"""
import json
import threading
import time

from gfso.adapters.llm import credentials
from gfso.adapters.llm.stats import refused_by_limit
from gfso.llm import llm_factory
from tests.support import make_engine
from tests.test_a_session_is_launched_the_same_through_its_provider import ANSWER, seen  # noqa: F401 — the fake CLI

T0 = int(time.time())


def _limited(seen, refused: dict):  # noqa: F811
    """The fake CLI refuses every call made on a token of `refused` ({value: when its limit lifts})."""
    def answer(self):
        tok = seen[-1]["env"].get("CLAUDE_CODE_OAUTH_TOKEN")
        return ANSWER if tok not in refused else {
            "type": "result", "is_error": True, "api_error": "usage_limit_reached", "result": "You've hit your limit",
            "total_cost_usd": 0, "usage": {}, "rate_limit_info": {"status": "rejected", "resetsAt": refused[tok]}}
    seen.Proc.answer = property(answer)


def _two():
    credentials.put("claude", "token", "t-a", name="a")
    credentials.put("claude", "token", "t-b", name="b")


def test_the_store_before_this_shape_reads_as_named_credentials(seen, tmp_path):  # noqa: F811
    path = tmp_path / "data" / "credentials.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"claude": {"kind": "token", "value": "B"}, "claude@a-token": {"kind": "token", "value": "A"},
                                "claude@b-token": {"kind": "token", "value": "B"}, "claude@b-api": {"kind": "api", "value": "K"}}))
    got = credentials.listing()["claude"]
    assert got["held"] == {"a-token": "token", "b-token": "token", "b-api": "api"} and got["active"] == "b-token"
    assert credentials.get("claude") == credentials.Credential("token", "B")


def test_every_call_starts_on_the_pointer_as_it_stands(seen):  # noqa: F811
    _two()
    llm = llm_factory("m")
    llm.complete("x", "SYS")
    credentials.use("claude", "b")
    llm.complete("x", "SYS")
    assert [c["env"]["CLAUDE_CODE_OAUTH_TOKEN"] for c in seen] == ["t-a", "t-b"]
    assert [c["credential"] for c in llm.calls] == ["a", "b"]


def test_a_limit_moves_the_pointer_and_the_call_runs_on(seen):  # noqa: F811
    _two()
    _limited(seen, {"t-a": T0 + 3600})
    llm = llm_factory("m")
    assert llm.complete("x", "SYS") == "OK"
    assert [c["env"]["CLAUDE_CODE_OAUTH_TOKEN"] for c in seen] == ["t-a", "t-b"]
    assert [c["ended"] for c in llm.calls] == ["moved", "answered"] and not refused_by_limit(llm.calls)
    now = credentials.listing()["claude"]
    assert now["active"] == "b" and now["spent"] == {"a": T0 + 3600}
    llm.complete("x", "SYS")
    assert seen[-1]["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "t-b", "a spent credential was tried again before it lifted"


def test_every_one_spent_stands_as_the_limit_until_the_first_lifts(seen):  # noqa: F811
    _two()
    _limited(seen, {"t-a": T0 + 7200, "t-b": T0 + 3600})
    llm = llm_factory("m")
    llm.complete("x", "SYS")
    assert [c["ended"] for c in llm.calls] == ["moved", "limit"] and refused_by_limit(llm.calls)
    assert llm.calls[-1]["limit_resets_at"] == T0 + 3600


def test_the_ledger_says_which_credential_each_call_ran_on_and_a_move_stops_nothing(seen):  # noqa: F811
    _two()
    _limited(seen, {"t-a": T0 + 3600})
    llm = llm_factory("m")
    llm.complete("x", "SYS")
    engine = make_engine()
    engine.record_llm_usage("validator", llm)
    rows = engine._storage.get_usage()
    assert [(r["ended"], r["credential"]) for r in rows] == [("moved", "a"), ("answered", "b")]
    assert engine.paused() is None, "a refused attempt the next credential carried stopped the project"


def test_a_persons_switch_stands_when_an_old_call_is_refused(seen):  # noqa: F811
    """A call still on `a` refused after the person moved to `c`: the pointer stays on `c` (critic F3)."""
    _two()
    credentials.put("claude", "token", "t-c", name="c")
    credentials.use("claude", "c")
    assert credentials.spend("claude", "a", T0 + 3600) == "c" and credentials.listing()["claude"]["active"] == "c"


def test_a_credential_removed_mid_flight_hands_its_call_to_the_one_in_force(seen):  # noqa: F811
    _two()
    credentials.put("claude", "token", None, name="a")
    assert credentials.spend("claude", "a", T0 + 3600) == "b", "a removed credential's refusal stopped the project"


def test_parallel_calls_each_decide_on_their_own_record(seen):  # noqa: F811
    """One provider serves parallel calls: a refused one moves on, an answered one is not re-run, and each record names
    the credential its own call ran on (critic F1)."""
    _two()
    llm = llm_factory("m")
    both, ran = threading.Barrier(2), []

    def attempt(cred, *a):
        ran.append(cred.value)
        refused = cred.value == "t-a" and len(ran) <= 2
        both.wait() if len(ran) <= 2 else None
        llm._booked({"ended": "limit" if refused else "answered", "limit_resets_at": T0 + 3600 if refused else None})
        return "" if refused else "OK"
    llm._attempt = attempt
    out = []
    ts = [threading.Thread(target=lambda: out.append(llm.complete("x", "SYS"))) for _ in range(2)]
    [t.start() for t in ts]
    [t.join(10) for t in ts]
    assert out == ["OK", "OK"] and sorted(ran) == ["t-a", "t-a", "t-b", "t-b"]
    assert sorted((c["ended"], c["credential"]) for c in llm.calls) == [
        ("answered", "b"), ("answered", "b"), ("moved", "a"), ("moved", "a")]


def test_a_store_that_does_not_read_stops_the_project_and_parks_no_node(seen, tmp_path):  # noqa: F811
    """Not the node's failure and never the host's login: a refused sign-in, naming the file (critic)."""
    path = tmp_path / "data" / "credentials.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"claude": {"kind": "tok')
    llm = llm_factory("m")
    assert llm.complete("x", "SYS") == "" and not seen, "a call ran without knowing its credential"
    assert llm.calls[-1]["ended"] == "unauthorized" and "credentials.json" in llm.calls[-1]["error"]


def test_an_api_keys_spent_credit_moves_the_call_to_the_next(seen):  # noqa: F811
    """An API key's limit is its credit: "Credit balance is too low" failed the call as a plain API error while the next
    credential in the order stood unused (b-api, 2026-11-01) — it is that key's limit, and the call moves on."""
    credentials.put("claude", "api", "k-b", name="b-api")
    credentials.put("claude", "api", "k-a", name="a-api")

    def answer(self):
        spent = seen[-1]["env"].get("ANTHROPIC_API_KEY") == "k-b"
        return ANSWER if not spent else {"type": "result", "is_error": True, "result": "Credit balance is too low",
                                         "api_error": "Credit balance is too low", "total_cost_usd": 0, "usage": {}}
    seen.Proc.answer = property(answer)
    llm = llm_factory("m")
    assert llm.complete("x", "SYS") == "OK"
    assert [c["ended"] for c in llm.calls] == ["moved", "answered"]
    assert credentials.listing()["claude"]["active"] == "a-api"
