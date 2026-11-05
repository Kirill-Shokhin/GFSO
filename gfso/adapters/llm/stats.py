"""What a model call COST and which stage made it — the bookkeeping every LLM verb does.

These three lived in `decompose/loop.py`, and four modules that have nothing to do with decomposition
imported them from there: the critic, the dispatcher, the LLM verb surface and the loop itself. That
is an off-diagonal element in the plainest sense — a shared concern owned by one of its consumers —
and it finally bit as a circular import the day the decomposer needed something from the critic.

Duck-typed on purpose: only the stat-collecting adapter has `tag_last`/`calls`/`stage_hint`, and a
fake or a third-party provider must stay usable without growing them.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from gfso.core.types.ports import LLMProviderPort


def tag_stage(llm, stage: str) -> None:
    """Label the llm's last call with its stage (duck-typed: only stat-collecting adapters have tag_last)."""
    if hasattr(llm, "tag_last"):
        llm.tag_last(stage)


#: How an account's limit reads in a call's error — not a context window's "limit", which no wait lifts. The CLI's own
#: words for its five-hour window are "session limit" (`usage_limit_reached` in the envelope's `api_error`).
ACCOUNT_LIMIT = ("usage limit", "usage_limit", "session limit", "weekly limit", "spend limit", "rate_limit", "rate limit",
                 # …and an API key's own: its credit spent, read as a plain API error, the call failed on it while the
                 # provider's next credential stood unused (b-api, 2026-11-01) — an api credential's limit is its credit
                 "credit balance is too low")


#: How a refused authentication reads in a call's error: the account is signed out or its key refused — no call of any
#: role can answer until a person signs it in (the CLI's "403 Failed to authenticate", a chat API's HTTP 401/403).
UNAUTHORIZED = ("failed to authenticate", "authentication_error", "unauthorized", "api error: 401", "api error: 403",
                # …a token its organization refused: unread, the pointer stayed on it and every call failed (2026-11-04)
                "has disabled claude subscription access",
                "invalid api key", "invalid x-api-key",
                # …and a client with no login at all — a container's, where no credential is set (critic, the CLI's words)
                "not logged in", "authentication_failed")


def is_unauthorized(error) -> bool:
    """Was this call's error a refused authentication?"""
    e = str(error or "").lower()
    return any(m in e for m in UNAUTHORIZED)


def is_limit(error) -> bool:
    """Was this call's error the account's limit? The CLI says of a server's own 429 "(not your usage limit)": read as the account's,
    a door's or a provider's throttling marked the credential spent and moved every project off it (critic, ran)."""
    e = str(error or "").lower().replace("not your usage limit", "")
    return any(m in e for m in ACCOUNT_LIMIT)


#: the endings that stop the whole project: no role's call can answer until they lift (`Engine.record_llm_usage`)
STOPS = ("limit", "unavailable", "unauthorized")


def refused_by_limit(calls) -> bool:
    """Did what stops the whole project — the account's limit, or the execution place down (`ended == "unavailable"`)
    — end any call of this run? Such a run answered nothing — an executor's session, a validation, a consent — and is
    asked again when the system's stop lifts, spending none of the node's budget."""
    return any(isinstance(c, dict) and (c.get("ended") in STOPS or is_limit(c.get("error")))
               for c in calls or ())


def what_stopped(calls) -> "str | None":
    """WHAT stopped the project, named for the person who lifts it — the execution place down, or the account's limit —
    or None where nothing of the kind ended these calls. One sentence for every door: three of them said "the account's
    usage limit" of a Docker daemon that was down (critic over b5f7350), and the user would wait a window out."""
    for c in calls or ():
        if isinstance(c, dict) and c.get("ended") == "unavailable":
            return f"the execution place {c.get('place') or ''} is unavailable".replace("  ", " ")
        if isinstance(c, dict) and c.get("ended") == "unauthorized":
            # …what lifts it, the provider's to say: "sign it in" named a login no call runs on
            return c.get("remedy") or "the account refused authentication: set its credential again (`gfso credential <provider>`)"
        if isinstance(c, dict) and c.get("ended") == "uncopied":     # …no stop: nothing is down, and nothing ran
            return f"the delivery at {c.get('place') or '?'} could not be copied to be judged"
    return "the account's usage limit" if refused_by_limit(calls) else None


def calls_of(llm) -> tuple:
    """The stat dicts this provider recorded, or nothing — the ONE place that asks a provider for
    them. Duck-typed for the reason this module exists: only a stat-collecting adapter has `calls`,
    and a fake or a third-party provider has to stay usable without growing one."""
    calls = getattr(llm, "calls", None)
    return tuple(calls) if calls else ()


def the_call_was_cut(llm, said: str) -> bool:
    """Did the last call STOP, rather than answer badly? Asked of the provider, not of the text.

    The adapter that read the CLI's stream knows: it ended with no result event. The shape of what
    came back ("short, and no brace in it") is the same question answered by inference, kept only
    for a provider that cannot say — two answers to one question is how the two drift apart.
    """
    calls = calls_of(llm)
    # ANY torn call of this run, not the LAST one. A rich contract is validated in concurrent batches
    # that all push onto one `calls` list, in completion order — so asking the last entry made the
    # answer depend on which batch happened to finish first: the same severed call was recognised
    # as torn, or not, by a race. Unrecognised it is read as "answered badly", which spends the
    # node's ONE retry and then parks it. A run stops on a coin toss, and the doctrine this function
    # exists for — a cut call is not an answer, so it does not spend the answer's budget — held only
    # by luck. If any batch of this validation was severed, the validation was severed.
    torn = torn_among(calls)
    return torn if torn is not None else len(said) < 400 and "{" not in said


def torn_among(calls) -> "bool | None":
    """Was ANY of these calls severed — None where none of them could say (`the_call_was_cut`'s one rule, read by every
    door that holds the calls rather than the provider)."""
    typed = [c for c in calls if isinstance(c, dict) and "transport_torn" in c]
    return any(bool(c["transport_torn"]) for c in typed) if typed else None


def _stat_line(llm) -> str:
    """One-line cost readout of the llm's LAST call + the running total. Duck-typed on `calls`
    holding stat DICTS (the headless adapter); anything else (fakes, API adapter) → plain 'done'."""
    calls = calls_of(llm)
    if not calls or not isinstance(calls[-1], dict):
        return "done"
    c = calls[-1]
    dicts = [x for x in calls if isinstance(x, dict)]
    total = sum((x.get("output_tokens") or 0) for x in dicts)
    retries = sum(1 for x in dicts if x.get("parse_failed"))
    # THE WHOLE CHECK, not its last sub-call. A verb that makes several calls — the checker and its
    # sufficiency readings — reported the LAST one, so a review costing 57 seconds and 0.18 dollars
    # was announced as "done in 2s · 0.0k tokens": the sub-call's numbers, under-reporting the work
    # by thirty times (measured on the human door 2026-08-22).
    # …SAID AS THE SUM IT IS: one llm carries a whole verb, and `auto_decompose` reuses it across its stages, so
    # "done in 1466s · 13.9k tokens" read as one repairer's 25 minutes when that call took 95 s — the sum of every call
    # before it, parallel readings included (measured on GB_coreutils_tn73sy660, 2026-10-20)
    secs = sum((x.get("duration_ms") or 0) for x in dicts) / 1000
    line = (f"done · this call {(c.get('duration_ms') or 0) / 1000:.0f}s, {(c.get('output_tokens') or 0) / 1000:.1f}k "
            f"tokens · Σ {len(dicts)} call(s) {secs:.0f}s model time, {total / 1000:.1f}k tokens")
    return (line + (f" · ⚠ {retries} parse-retry" if retries else "")
            + (f" · ⚠ the call ended in error — {c['error']}" if c.get("error") else ""))


def _hint(llm, stage: str) -> None:
    """Tell the adapter which stage is about to run, so its live token ticks carry the stage name."""
    if hasattr(llm, "stage_hint"):
        llm.stage_hint = stage


def readings(llm, n: int, read, stage: str) -> list:
    """`read()` run n times — the independent readings of one question — and every call they made labelled `stage`.

    At once on a provider that says it may be called so (`parallel_safe`: each call its own process), one after
    another on any other: readings are independent by construction, and serially the authoring paid three of them
    back to back at each obligation check (~100 s, twice per plan) and the first plan review three more (AUTO haiku
    coreutils, 2026-10-12). Labelled after the fact, since "the last call" means nothing while several run."""
    return fan(llm, range(n), lambda _: read(), stage)


def fan(llm, items, each, stage: str) -> list:
    """`each(item)` over `items` — independent calls on one provider, at once where it says it may be called so
    (`parallel_safe`), in order otherwise; every call they made labelled `stage` (`readings` is n of the same)."""
    items, n0 = list(items), len(calls_of(llm))
    if len(items) > 1 and isinstance(llm, LLMProviderPort) and llm.parallel_safe:
        with ThreadPoolExecutor(len(items)) as pool:
            out = list(pool.map(each, items))
    else:
        out = [each(x) for x in items]
    for c in calls_of(llm)[n0:]:
        if isinstance(c, dict):
            c["stage"] = stage
    return out
