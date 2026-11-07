"""A session that ran is booked to the ledger whatever its frame does after it, and a handover note quoting a phrase
before a colon is read as a note. Four dispatches of one row raised "list index out of range" right after an executor's
session: its note (`4. Refuted\\n- "Probes only fail at assembly": refuted …`) was asked whether it reads as the report,
the closer repair took the quoted phrase for an object key outside any object, and the raise skipped the booking — eight
sessions, $1.63, never reached `llm_usage`, and the retry restarted the handover chain (GB_c_compiler_ctx3b1285_10301332).
"""
import types

import pytest

from gfso import sessions as S
from gfso.adapters.llm.structured import parse_structured
from tests.support import make_engine

NOTE = ("HANDOVER NOTE\n1. Reading of the task: none.\n4. Refuted\n"
        '- "Probes only fail at assembly": refuted by the z_mix.c run.\n7. Next step: rebuild.\n')


def test_a_quoted_phrase_before_a_colon_in_prose_is_no_misplaced_key():
    assert parse_structured(NOTE, S.EXECUTOR_SCHEMA) is None


def test_a_session_whose_frame_fails_after_it_is_still_booked(monkeypatch):
    e, booked = make_engine(), []
    monkeypatch.setattr(e, "record_llm_usage", lambda stage, llm, node: booked.extend(llm.calls))
    ran = {"cost_usd": 0.22, "ended": "answered"}

    def run_agent(*a, **k):
        llm.calls.append(ran)
        raise IndexError("list index out of range")

    llm = types.SimpleNamespace(calls=[], run_agent=run_agent)
    with pytest.raises(IndexError):
        S._spawn(e, "kid", "exec-1", {}, llm, "executor", "executor.md", "packet", {"type": "object"},
                 "delegated_execution", None, work=False)
    assert booked == [ran]
