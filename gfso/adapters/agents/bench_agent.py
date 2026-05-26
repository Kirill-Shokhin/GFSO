"""BenchAgent: dual-role agent for coding benchmark experiments.

Handles executor role (write/rework code) and verifier role (run TestPlan).
Closes the GFSO loop internally via Signal.DELIVER handling.

Responsibilities:
  - ACCEPT: write code (LLM call)
  - DELIVER: execute TestPlan, return PASS/FAIL
  - FAIL: rework code (LLM call with failure details)
"""
from __future__ import annotations

import logging
from typing import Optional

from gfso.core.types import (
    AgentId, Signal, SignalData, DispatchPayload, AgentPort,
    TaskId, StoragePort,
)
from gfso.core.types import VerifierPort

log = logging.getLogger(__name__)

def _format_failure(details: str, max_len: int = 500) -> str:
    """Extract signal from a test failure's details.

    Strips Traceback noise:
      - `Traceback (most recent call last):` header
      - `File "C:\\...temp..." line X, in test_Y` location lines
    Keeps:
      - The assertion call (e.g. `self.assertIn(...)`)
      - The error line (e.g. `AssertionError: ...`)
      - Any non-noise body of the traceback
    Returns the result indented by 4 spaces (so it nests under the test bullet).
    """
    if not details:
        return "    (no details)"
    lines = details.splitlines()
    kept = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("Traceback ("):
            continue
        if s.startswith('File "') and "line " in s:
            continue
        kept.append(s)
    out = "\n".join("    " + k for k in kept)
    if len(out) > max_len:
        out = out[:max_len] + "\n    ...[truncated]"
    return out


def _make_code_tool(is_function: bool) -> dict:
    desc = (
        "Complete Python module: include all imports and the full function definition with body. "
        "Do not include test code."
        if is_function
        else "Complete Python solution. Reads from stdin, prints to stdout."
    )
    return {
        "name": "deliver_code",
        "description": "Submit complete Python solution.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": desc}},
            "required": ["code"],
        },
    }


class BenchAgent(AgentPort):
    """Dual-role agent: executor + verifier.

    On DELIVER: uses a VerifierPort with spec.criteria (from GFSO) + test inputs.
    Criteria ARE the test plan — no separate abstraction needed.
    """

    def __init__(
        self,
        client,
        model: str,
        verifier: VerifierPort,
        problem_prompt: str,
        criteria_text: str,
        is_function: bool = False,
    ):
        self._client = client
        self._model = model
        self._verifier = verifier
        self._problem_prompt = problem_prompt
        self._criteria_text = criteria_text
        self._is_function = is_function
        self._tool = _make_code_tool(is_function)

        self.code: dict[TaskId, str] = {}
        self.code_history: dict[TaskId, list[str]] = {}  # per-task iteration code
        self.total_tokens: int = 0
        self.tokens_per_call: list[int] = []
        self.criteria_results: list[dict] = []  # per-iteration verification results

    def dispatch(self, agent_id: AgentId, payload: DispatchPayload) -> Optional[SignalData]:
        tid = payload.task.id

        match payload.signal:
            case Signal.ASSIGN:
                log.info(f"[BenchAgent] {tid}: ASSIGN → ACCEPT")
                return SignalData(signal=Signal.ACCEPT, task_id=tid, source=agent_id)

            case Signal.ACCEPT:
                log.info(f"[BenchAgent] {tid}: ACCEPT → writing code")
                code = self._write_code()
                self.code[tid] = code
                self.code_history.setdefault(tid, []).append(code)
                log.info(f"[BenchAgent] {tid}: DELIVER ({len(code.splitlines())} lines)")
                return SignalData(signal=Signal.DELIVER, task_id=tid, source=agent_id)

            case Signal.DELIVER:
                log.info(f"[BenchAgent] {tid}: DELIVER → running verification")
                return self._verify_and_respond(tid, agent_id, payload)

            case Signal.FAIL:
                # Don't rework if task is DONE (max iterations exhausted)
                if payload.task.state.name == "DONE":
                    log.info(f"[BenchAgent] {tid}: FAIL (terminal) → skip rework")
                    return None
                failed = [r for r in payload.check_results if not r.passed]
                log.info(f"[BenchAgent] {tid}: FAIL → reworking ({[r.check_name for r in failed]})")
                code = self._rework_code(payload)
                self.code[tid] = code
                self.code_history.setdefault(tid, []).append(code)
                log.info(f"[BenchAgent] {tid}: DELIVER rework ({len(code.splitlines())} lines)")
                return SignalData(signal=Signal.DELIVER, task_id=tid, source=agent_id)

            case _:
                return None

    def _verify_and_respond(self, tid: TaskId, agent_id: AgentId, payload: DispatchPayload) -> SignalData:
        """Run spec.criteria checks against current code, return PASS or FAIL."""
        code = self.code.get(tid, "")
        spec = payload.task.spec
        results = self._verifier.verify(tid, code, spec)

        iteration = len(self.criteria_results)
        failed = [r.check_name for r in results if not r.passed]
        self.criteria_results.append({
            "iteration": iteration,
            "passed": sum(1 for r in results if r.passed),
            "total": len(results),
            "failed": failed,
        })

        all_passed = all(r.passed for r in results)
        if all_passed:
            log.info(f"[BenchAgent] {tid}: All checks passed → PASS")
            return SignalData(signal=Signal.PASS, task_id=tid, source=agent_id)
        else:
            failed_names = tuple(r.check_name for r in results if not r.passed)
            log.info(f"[BenchAgent] {tid}: Failed {failed_names} → FAIL")
            return SignalData(
                signal=Signal.FAIL, task_id=tid, source=agent_id,
                failed_criteria=failed_names,
            )

    def _write_code(self) -> str:
        if self._is_function:
            system = (
                "Complete the given Python function. Return the COMPLETE module: "
                "all imports + the full function with body. Do NOT read from stdin "
                "and do NOT include test code. Must handle all stated constraints."
            )
        else:
            system = (
                "Write a Python solution. Read from stdin, print to stdout. "
                "Must handle all constraints efficiently."
            )
        prompt = (
            f"PROBLEM:\n{self._problem_prompt}\n\n"
            f"ACCEPTANCE CRITERIA (must satisfy ALL):\n{self._criteria_text}"
        )
        return self._llm_code(prompt, system)

    def _rework_code(self, payload: DispatchPayload) -> str:
        tid = payload.task.id
        failed = [r for r in payload.check_results if not r.passed]
        passed = [r for r in payload.check_results if r.passed]
        fail_text = "\n".join(f"- {r.check_name}:\n{_format_failure(r.details)}" for r in failed)
        pass_text = "\n".join(f"- {r.check_name}: ok" for r in passed)
        prev_code = self.code.get(tid, "")

        fmt_hint = (
            "Keep the function signature given in the task. Return the COMPLETE module with imports. "
            "Do NOT read from stdin and do NOT include test code. "
            if self._is_function else ""
        )
        system = (
            f"Fix the code to pass ALL property checks. {fmt_hint}"
            "Keep working parts intact. Any test currently passing must continue to pass — "
            "do not change logic of code paths used by passing tests. Focus on fixing failures."
        )
        # NOTE: problem prompt is omitted — the docstring inside prev_code already
        # carries the spec. Avoids duplicating the same description twice.
        prompt = (
            f"YOUR PREVIOUS CODE (its docstring is the spec):\n```python\n{prev_code}\n```\n\n"
            f"PROPERTY CHECK RESULTS:\n"
            f"FAILED:\n{fail_text}\n\n"
            f"PASSED:\n{pass_text}\n\n"
            f"Fix the code."
        )
        return self._llm_code(prompt, system)

    def _llm_code(self, prompt: str, system: str) -> str:
        log.info(f"[BenchAgent] LLM call | system: {system}")
        log.info(f"[BenchAgent] LLM call | prompt:\n{prompt}")

        resp = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            tools=[self._tool],
            tool_choice={"type": "tool", "name": "deliver_code"},
        )
        tokens = resp.usage.input_tokens + resp.usage.output_tokens
        self.total_tokens += tokens
        self.tokens_per_call.append(tokens)
        log.info(f"[BenchAgent] LLM tokens: {tokens} (total: {self.total_tokens}, calls: {self.tokens_per_call})")

        for block in resp.content:
            if block.type == "tool_use":
                code = block.input.get("code", "")
                if not code:
                    raise RuntimeError("LLM returned empty code in tool_use")
                log.info(f"[BenchAgent] LLM code:\n{code}")
                return code

        raise RuntimeError(f"LLM response has no tool_use block: {resp.content}")
