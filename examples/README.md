# The entry doors — one working example per case

The mode is the entry point, never a configuration. Each script is self-contained and runs
against a throwaway database; the deterministic ones are exercised by the test suite
(`tests/test_examples.py`), the LLM ones spawn real Claude Code executors when you run them.

| Case | Example | What it shows |
|---|---|---|
| Human-only | `human_only.py` | The full protocol with ZERO AI: humans issue, execute, and validate; the verifier≠executor gate forces an independent recorded verdict before a self-executed PASS. Same flow the web UI drives (`gfso serve`, incl. the Record-verdict button). |
| Mixed | `mixed_delegation.py` | A human issuer delegates one node to a REGISTERED LLM executor (assignment IS delegation); an LLM validator signs the verdict; the human keeps the rest. |
| Autonomous org | `autonomous_org.py` | The fully autonomous org: `auto_decompose` authors the verified graph, the dispatcher spawns executors/validators to root DONE/PASS with no human in the loop. |
| MCP user-agent | (no script — it's a config line) | `claude mcp add gfso -- python -m gfso.mcp.connect` — the agent door; the protocol arrives as MCP instructions (`gfso/mcp/ORCHESTRATOR.md`), the live UI shares the same engine. |
| Async precompute | `async_precompute.py` | Decomposition computed OUTSIDE the process (any external classifier/planner) and applied to the live core as plain signals — the embedding pattern for hosts that precompute structure. |

The pure-core embedding host (own storage/clock/runtime over `process_signal`) is specified
separately in `docs/embeddability_acceptance.md`.
