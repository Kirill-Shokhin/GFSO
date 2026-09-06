"""One policy for the declared server configuration, in both places that apply it.

`data/serve.json` declares what the installation's server should be; an operator who EXPORTS a
variable is saying something about this run. `gfso serve` has always let the export win — the reason
is written beside it: the measurement arm turns `GFSO_L2_GATE` off deliberately, and the gate is the
mechanism being measured. The spawn path in the MCP reconciler did the opposite (`os.environ.update`),
so the same session could get a server with the gate switched back on, silently — one rule, two
spellings, and the louder one overrode the operator.
"""
from gfso.config import fill_env_gaps


def test_a_declaration_fills_gaps_and_does_not_overrule_an_export(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")                 # …what this run means to measure
    applied = fill_env_gaps({"GFSO_L2_GATE": "1", "GFSO_AGENTS_PATH": "R"})
    assert applied["GFSO_L2_GATE"] == "0", "an explicit export outranks the declaration"
    assert applied["GFSO_AGENTS_PATH"] == "R", "…and what the operator did NOT say still applies"
