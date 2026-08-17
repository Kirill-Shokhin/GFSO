# The entry doors — one working example per case

Each script is self-contained and runs against a throwaway database, so nothing here touches a
project of yours. The mode is the entry point, never a configuration: pick the script whose shape
matches how work actually flows in your case.

**Read `human_only.py` first.** It is the shortest thing in the repository that shows the mechanism
the rest is built around, and it needs no AI at all.

They ship inside the package, so they run wherever it is installed — `gfso demo` with no name lists
them, and `python -m gfso.examples.<name>` is the same thing spelled out.

```bash
gfso demo human_only       # deterministic, ~1 second
gfso demo async_precompute # deterministic, ~1 second
```

Both deterministic scripts are exercised by the test suite (`tests/test_examples.py`), which asserts
what they print — so if one of them stops behaving as described here, CI says so.

The two LLM scripts spawn real Claude Code processes and cost real tokens, so running them is a
deliberate act rather than a CI one; the suite only compiles them. Both exit with a message if the
`claude` CLI is not on your PATH.

```bash
gfso demo mixed_delegation  # ~1-2 min, one delegated node
gfso demo autonomous_org    # ~5-10 min, a whole graph
```

| Case | Example | What it demonstrates |
|---|---|---|
| Human-only | `human_only.py` | The full protocol with ZERO AI. `ann` executes a node and signs her own `PASS`; the engine refuses it; `bob` records an independent verdict; the same `PASS` then lands. The verifier ≠ executor gate (§14.5), printed by the engine rather than narrated by the script — and the same flow the UI drives with its Pass/Fail/Record-verdict buttons. |
| Async precompute | `async_precompute.py` | A decomposition computed OUTSIDE the process — by any external classifier, planner or batch job — applied to the live core as plain signals. The core neither knows nor cares where the structure came from: it lands through the same audited `ASSIGN`s, meets the same structural checks, and the script prints an empty hole list and the derived dependency edge. The embedding pattern for hosts that precompute structure. |
| Mixed | `mixed_delegation.py` | A human issuer with one node delegated to a REGISTERED LLM executor — assignment *is* delegation. The dispatcher spawns the executor with the packet, wraps its report into signals, and a registered validator signs the verdict. The human's own node stays untouched, waiting for the human. |
| Autonomous org | `autonomous_org.py` | No human in the loop: `auto_decompose` authors a verified graph from one request, the dispatcher spawns an executor per free leaf, an independent validator signs every delivery, and the root reaches `DONE/PASS` only through the whole tree. Ends by printing the quality vector. |
| MCP user-agent | *(no script — `gfso setup` writes it)* | `claude mcp add --scope user gfso -- "$(command -v gfso)" connect` — the agent door, registered by absolute path so it resolves from every directory. The protocol arrives as the session's instructions (`gfso/mcp/ORCHESTRATOR.md`) and the live UI shares the same engine. This is the door most people will use on real work: see [`docs/USING_GFSO.md`](../../docs/USING_GFSO.md). |

Embedding the pure core into your own host — your storage, your clock, your runtime, over
`process_signal` — is specified separately in [`docs/embeddability_acceptance.md`](../../docs/embeddability_acceptance.md).
