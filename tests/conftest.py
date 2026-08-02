"""Suite-wide defaults.

The Level-2 execution gate (§5.4, gfso/engine/validation.py) is ON in a running system: a child may
not start work while its parent's decomposition has no current causal review. That review is an
LLM-layer instrument, and this suite is substrate-free by design (no model runs) — so the suite
takes the canon's own EXPLORE branch (§5.4-bis) and turns the gate off, exactly as a deployment
without a checker would. `tests/test_l2_gate.py` turns it back ON and owns that behavior end to end.
"""
import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _l2_gate_off():
    prior = os.environ.get("GFSO_L2_GATE")
    os.environ["GFSO_L2_GATE"] = "0"
    yield
    if prior is None:
        os.environ.pop("GFSO_L2_GATE", None)
    else:
        os.environ["GFSO_L2_GATE"] = prior
