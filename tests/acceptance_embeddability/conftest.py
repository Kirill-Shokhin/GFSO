"""The embedding-acceptance suite (docs/embeddability_acceptance.md) — the pre-registered JUDGE.

The suite drives an EMBEDDER-PROVIDED host through the contract below. Without a host it skips
with the named reason (capability-honest; CI stays green); against an embedder's attempt it is
the pass/fail verdict — never an impression.

THE HOST CONTRACT (what the embedder builds, working only from the public docs):
set `GFSO_EMBED_HOST` to a python file defining `make_host(workdir: str) -> host`, where host is
an object with:

- `send(signal_data) -> None` — feed one SignalData into the host's OWN runtime (its own queue
  pump over `gfso.engine.loop.process_signal`; no Engine.start, no engine threads) and process
  it TO QUIESCENCE (including follow-up signals it produces) before returning.
- `state(task_id: str) -> str | None` — the node's current state name.
- `graph_holes() -> list[dict]` — the unmet structural checks ({task_id, check, details}).
- `record_verdict(task_id: str, verdict: str, failed: list, reviewer: str) -> None` — record an
  independent reviewer's verdict (the verifier≠executor gate refuses a self-executed PASS
  without one; requires the storage's exec-verdict extension — part of the point).
- `advance_clock(seconds: float) -> None` — move the host's OWN ClockPort forward (virtual
  time) and let its timeout machinery run once.
- `audit_rows() -> list[dict]` — the append-only signal log rows from the host's OWN storage
  (a JSON-lines file store — not sqlite, not the in-memory adapter).
- `restart() -> host` — a NEW host instance over the SAME persistent store (fresh process
  semantics: everything in memory is gone; the log hydrates).

The host processes signals with validation ON (process_signal's default) and must not modify
anything under gfso/core or gfso/engine (the layer gate stays green).
"""
import importlib.util
import os

import pytest


@pytest.fixture()
def host(tmp_path):
    path = os.environ.get("GFSO_EMBED_HOST")
    if not path or not os.path.exists(path):
        pytest.skip("no embedding host present (set GFSO_EMBED_HOST to the embedder's host "
                    "module — the fresh-agent acceptance run provides one)")
    spec = importlib.util.spec_from_file_location("embed_host", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.make_host(str(tmp_path))
