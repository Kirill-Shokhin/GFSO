"""A report the engine refuses as a verdict is KEPT, and its place is named in the log.

⊥ is not pass (§10): a refused report stops the node's automatic progress and hands the decision to
the issuer — so that report is precisely the evidence the issuer needs, and it was the one thing
thrown away. `validate_result` returned it to its caller; under delegation the caller is the
dispatcher, which reads a verdict and drops the rest, while its log line said the report was "kept in
the validate_result output" — a place nobody could look. Measured 2026-08-19: a run stopped at its
first delivery on a refused report, and reconstructing WHY cost a fresh paid validation.
"""
from __future__ import annotations

import json

import gfso.tools as T
import gfso.tools_llm as TL
from tests.test_validate_result import _ValidatorLLM, _delivered_node, _eng, _fenced


def _refusable_report() -> str:
    # A verdict contradicting its own evidence: PASS while a criterion is red. The engine refuses to
    # record it — which is the condition under test, not the defect under test.
    return _fenced({"verdict": "PASS",
                    "per_criterion": [
                        {"criterion": "flush", "verdict": "pass", "evidence": "flush ok",
                         "behaviours": ["the criterion holds"],
                         "probe": [{"command": "pytest -q", "expect": "passed"}]},
                        {"criterion": "holds", "verdict": "fail", "evidence": "fell off",
                         "behaviours": ["the criterion holds"],
                         "probe": [{"command": "pytest -q", "expect": "passed"}]}],
                    "failed_criteria": []})


def test_a_refused_report_is_written_beside_the_state(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    e = _eng()
    _delivered_node(e)
    out = TL.validate_result(e, "n1", _llm=_ValidatorLLM(_refusable_report()))
    assert out["verdict"] is None                       # the precondition: it was refused
    kept = out.get("report_kept_at")
    assert kept, "the refused report was not kept anywhere"
    body = open(kept, encoding="utf-8").read()
    # Both halves must survive: WHY it was refused, and WHAT was said — the defect line alone is a
    # summary of the evidence, not the evidence.
    assert "refused as a verdict" in body and out["verdict_defects"][:40] in body
    assert "fell off" in body
    e.stop()


def test_the_log_names_where_the_refused_report_went(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    e = _eng()
    _delivered_node(e)
    out = TL.validate_result(e, "n1", _llm=_ValidatorLLM(_refusable_report()))
    lines = [r.get("message", "") for r in e.pipeline_log(limit=50)]
    assert any("NOT a verdict" in m and out["report_kept_at"] in m for m in lines), \
        "the pipeline log does not say where the refused report was kept"
    e.stop()
