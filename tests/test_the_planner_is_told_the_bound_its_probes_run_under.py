"""The plan's author writes each probe knowing the bound the engine runs it under: a corpus loop past it decides nothing
(its criterion undecided), so the bound is said where probes are written — from the engine's one constant."""
from gfso import issuer, observe
from gfso.core.protocol import procedure
from gfso.decompose import loop


def test_the_authoring_prompt_names_the_engines_probe_bound():
    assert f"runs {observe.PROBE_S} seconds at most" in loop.AUDIT_PROMPT
    assert "<PROBE_S>" not in loop.AUDIT_PROMPT


def test_the_issuer_and_the_refusal_name_the_same_bound():
    """Whoever re-pins a check past its bound — the issuer, told so by the refusal — is told the number, from one owner."""
    assert observe.PROBE_S is procedure.PROBE_S and loop.PROBE_S is procedure.PROBE_S
    assert f"runs {procedure.PROBE_S} seconds at most" in issuer._prompt() and "<PROBE_S>" not in issuer._prompt()
    assert f"{procedure.PROBE_S} s with its build" in procedure.BOUND_SPENT
