"""Can this provider run on gfso, and in which roles — measured on the provider itself, not read off its declarations.

The criteria a provider meets to work on gfso no worse, as a battery of small real calls:
- REQUIRED for the one-shot roles (decomposition, its review, the issuer's answers): a completion comes back, a
  structured answer comes back schema-valid, and each call's record carries its input and output tokens;
- REQUIRED for the agent roles (executor, validator, contact): in a place of its own the model writes a file, runs a
  command over it and reports what the command printed — the round trip every agent role is — and, under the
  executor's real system prompt, ends its run with a report that parses against a schema, as every agent role must;
- OPTIONAL, reported: the cached part of the input split out, the cost, the window (asked of the server where it says:
  a local server that truncates past its window silently would pass a small battery and fail real work), the peak, and
  whether a context budget can run on it (a round cut at its cap says so and reports its peak).
What is optional and absent stays absent: "not reported", never zero.
"""
from __future__ import annotations

from pathlib import Path

from gfso.adapters.execution import LocalExecution
from .stats import calls_of
from .structured import parse_structured, schema_instruction

ONE_SHOT_ROLES = ("decompose", "review", "issuer")
AGENT_ROLES = ("executor", "validator", "contact")
#: the least window an agent role runs in: the validator's prompt alone is ~3.5k tokens, a packet and a turn's tools more
MIN_WINDOW = 32_000
TOOLS = ("Read", "Write", "Edit", "Bash", "Glob", "Grep")
AGENT_TASK = ("Create a file named probe.txt in the working directory whose whole content is the number 41. Then run a "
              "shell command that prints that number plus one, computed from the file (for example "
              "`expr $(cat probe.txt) + 1`). Reply with only the number the command printed.")
REPORT_TASK = ("# The task\nIn the working directory, write `sum.py` that prints the sum of the integers 1 to 100, run it, "
               "and deliver.\n")
REPORT_SCHEMA = {"type": "object", "properties": {"status": {"type": "string", "enum": ["delivered", "blocked"]},
                                                  "printed": {"type": "string"}},
                 "required": ["status", "printed"]}


def _filled(calls, key) -> bool:
    return any(isinstance(c, dict) and c.get(key) is not None for c in calls)


def _agent_checks(provider, out: dict, agent_prompt: str) -> bool:
    """The two agent cases; True where both pass."""
    with (provider.execution or LocalExecution()).scratch("gfso-conformance-") as place:
        answer = provider.run_agent("You are a careful agent working with tools.", AGENT_TASK, TOOLS, cwd=place,
                                    timeout=600, max_turns=20)
        f = Path(place) / "probe.txt"
        wrote = f.is_file() and f.read_text(encoding="utf-8", errors="replace").strip() == "41"
        used = dict(provider.last_tool_calls)
        out["checks"]["agent run"] = {"pass": wrote and "42" in answer and bool(used.get("Bash")),
                                      "wrote": wrote, "answer": answer.strip()[:80], "tools": used}
    with (provider.execution or LocalExecution()).scratch("gfso-conformance-") as place:
        said = provider.run_agent(agent_prompt,
                                  REPORT_TASK + schema_instruction(REPORT_SCHEMA), TOOLS, cwd=place, timeout=900,
                                  max_turns=40)
        report = parse_structured(said, REPORT_SCHEMA) or {}
        out["checks"]["agent report"] = {"pass": report.get("status") == "delivered" and "5050" in
                                         str(report.get("printed")), "saw": report or said.strip()[-120:]}
    return out["checks"]["agent run"]["pass"] and out["checks"]["agent report"]["pass"]


def _holds_a_budget(provider) -> bool:
    """Can a context budget run on it (`budget.run`)? A round cut at a cap of one turn must say so — `stop_reason`
    "max_turns" — and how full its context got; without either a budget would stop or never fire, silently."""
    with (provider.execution or LocalExecution()).scratch("gfso-conformance-") as place:
        provider.run_agent("You are a careful agent working with tools.", AGENT_TASK, TOOLS, cwd=place, timeout=300,
                           max_turns=1)
    rec = (calls_of(provider) or [{}])[-1]
    return isinstance(rec, dict) and rec.get("stop_reason") == "max_turns" and bool(rec.get("peak_context"))


def assess(provider, agent_prompt: str = "You are the executor of a task: do it with your tools, then deliver.") -> dict:
    """The battery's findings: each check pass/fail with what it saw, the optional fields reported, the roles held —
    the report case asked under `agent_prompt`, a real executor's system prompt where the caller has it."""
    out: dict = {"checks": {}, "optional": {}, "roles": [], "warnings": []}
    said = provider.complete("Reply with the single word: pong")
    out["checks"]["completion"] = {"pass": bool(said.strip()), "saw": said.strip()[:80]}
    got = provider.complete_structured("You answer arithmetic.", "What is 2 + 3?",
                                       {"type": "object", "properties": {"answer": {"type": "integer"}},
                                        "required": ["answer"]})
    out["checks"]["structured"] = {"pass": isinstance(got, dict) and "answer" in got, "saw": got,
                                   "right": isinstance(got, dict) and got.get("answer") == 5}
    out["checks"]["tokens"] = {"pass": _filled(calls_of(provider), "input_tokens")
                               and _filled(calls_of(provider), "output_tokens")}
    one_shot = all(out["checks"][k]["pass"] for k in ("completion", "structured", "tokens"))
    if one_shot:
        out["roles"] += ONE_SHOT_ROLES
    if provider.runs_agents:
        if _agent_checks(provider, out, agent_prompt) and one_shot:
            out["roles"] += AGENT_ROLES
    else:
        out["checks"]["agent run"] = {"pass": False, "saw": "the provider runs no agents (no tool calling)"}
    calls = calls_of(provider)
    out["optional"] = {"cache split": _filled(calls, "cache_read_input_tokens"), "cost": _filled(calls, "cost_usd"),
                       "window": _filled(calls, "context_window"), "peak context": _filled(calls, "peak_context")}
    if provider.runs_agents:
        out["optional"]["context budget"] = _holds_a_budget(provider)
    window = max((c.get("context_window") or 0 for c in calls if isinstance(c, dict)), default=0)
    if provider.runs_agents and window and window < MIN_WINDOW:
        out["warnings"].append(f"the model's window is {window} tokens: a role's prompt and packet need about "
                               f"{MIN_WINDOW} — real runs would be cut; raise the server's context")
        out["roles"] = [r for r in out["roles"] if r not in AGENT_ROLES]
    if provider.runs_agents and not out["optional"]["window"]:
        out["warnings"].append("the model's window is not known (the server did not say): a local server may cut a "
                               "long run's context silently — declare it (GFSO_PROVIDER_<NAME>_CONTEXT), and for "
                               "Ollama set OLLAMA_CONTEXT_LENGTH or the model file's num_ctx (the default is small)")
    return out


def report(spec: str, found: dict) -> str:
    """The battery's findings as a person reads them."""
    lines = [f"provider check — {spec}"]
    for name, c in found["checks"].items():
        lines.append(f"  {'ok ' if c['pass'] else 'NO '}  {name}  "
                     + ", ".join(f"{k}={v}" for k, v in c.items() if k != "pass"))
    lines.append("  optional: " + ", ".join(f"{k} {'reported' if v else 'not reported'}"
                                            for k, v in found["optional"].items()))
    lines += [f"  warning: {w}" for w in found["warnings"]]
    lines.append("  roles it can hold: " + (", ".join(found["roles"]) or "none"))
    return "\n".join(lines)
