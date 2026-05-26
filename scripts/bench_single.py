"""
LEGACY GFSO Benchmark runner (LiveCodeBench).

Superseded by `scripts/run_livecodebench.py` which uses the bench/ harness.
Kept for reference and as the import base for `scripts/bench_perfect.py`.

Usage:
  python scripts/bench_single.py 3          # run single problem
  python scripts/bench_single.py 3 10 14    # run multiple problems
  python scripts/bench_single.py all        # run all 168

Results: runs/bench_results.json (appended per problem)
Logs:    runs/bench_logs/{problem_index}.log
"""
import io
import sys
import os
import json
import base64
import zlib
import pickle
import re
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from huggingface_hub import hf_hub_download
from anthropic import Anthropic

from gfso.core.types import TaskId, AgentId, Spec, Criteria, CheckResult
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.verification import run_code, CodeVerifier
from gfso.adapters.agents.bench_agent import BenchAgent
from gfso.engine import Engine

import time
from anthropic import APIStatusError, APIConnectionError

_raw_client = Anthropic()


class RetryClient:
    """Wraps Anthropic client, retries on 529 Overloaded with exponential backoff."""
    def __init__(self, client):
        self._c = client
        self.messages = self

    def create(self, **kwargs):
        delay = 5
        for attempt in range(8):
            try:
                return self._c.messages.create(**kwargs)
            except (APIConnectionError, APIStatusError) as e:
                code = getattr(e, 'status_code', 'conn')
                retryable = isinstance(e, APIConnectionError) or code in (429, 529, 503)
                if retryable and attempt < 7:
                    logging.getLogger(__name__).warning(
                        f"[retry] {code} attempt {attempt+1}/8, sleeping {delay}s"
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 120)
                else:
                    raise


client = RetryClient(_raw_client)
MODEL = "claude-haiku-4-5-20251001"
RESULTS_FILE = "bench_results.json"
LOGS_DIR = "bench_logs"


# === Data ===

def load_problems(difficulty="medium"):
    f = hf_hub_download('livecodebench/code_generation_lite', 'test.jsonl', repo_type='dataset')
    out = []
    with open(f, encoding='utf-8') as fp:
        for line in fp:
            p = json.loads(line)
            if p['difficulty'] == difficulty:
                out.append(p)
    return out


def get_hidden_tests(problem):
    pub = json.loads(problem['public_test_cases'])
    raw = base64.b64decode(problem['private_test_cases'])
    priv = json.loads(pickle.loads(zlib.decompress(raw)))
    return pub + priv


def clean_content(problem):
    c = re.sub(r'<[^>]+>', '', problem['question_content'])
    return c.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')


def load_bench_inputs(path="data/bench_inputs.json"):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# === Logging per problem ===

def setup_problem_log(problem_index):
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, f"{problem_index}.log")
    root = logging.getLogger()
    # Remove old handlers
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.setLevel(logging.INFO)
    root.addHandler(logging.FileHandler(log_file, mode='w', encoding='utf-8'))
    root.addHandler(logging.StreamHandler(sys.stdout))
    for h in root.handlers:
        h.setFormatter(logging.Formatter('%(name)s | %(message)s'))
    return log_file


# === Hidden tests ===

def run_hidden_tests(code, tests, starter_code=""):
    """Run code against hidden tests. For LeetCode: wraps with harness."""
    method_name = ""
    if starter_code:
        m = re.search(r'def (\w+)\(self', starter_code)
        if m:
            method_name = m.group(1)

    results = []
    for i, tc in enumerate(tests):
        if method_name:
            args = ', '.join(tc['input'].rstrip('\n').split('\n'))
            runnable = f"from typing import *\n{code}\nsol = Solution()\nprint(sol.{method_name}({args}))\n"
            r = run_code(runnable, "")
        else:
            r = run_code(code, tc['input'])
        exp = tc['output'].rstrip('\n')
        act = r.stdout.rstrip('\n')
        ok = (act == exp) and r.returncode == 0 and not r.timed_out
        details = ""
        if not ok:
            if r.timed_out:
                details = "TIMEOUT"
            elif r.returncode != 0:
                details = f"CRASH: {r.stderr}"
            else:
                details = f"WRONG: expected={exp!r} actual={act!r}"
        results.append(CheckResult(check_name=f"hidden_{i}", passed=ok, details=details))
    return results


# === One-shot ===

def run_oneshot_single(problem, hidden_tests):
    """Single one-shot attempt. Returns (hidden_passed, hidden_total, tokens, failures)."""
    log = logging.getLogger(__name__)
    content = clean_content(problem)
    pub = json.loads(problem['public_test_cases'])
    examples = "\n".join(
        f"Input:\n{t['input'].strip()}\nOutput:\n{t['output'].strip()}" for t in pub
    )
    starter_code = problem.get('starter_code', '')
    if starter_code:
        prompt = f"{content}\n\nExamples:\n{examples}\n\nComplete this function:\n{starter_code}"
        system = "Complete the function. Output ONLY the complete class in a ```python block."
    else:
        prompt = f"{content}\n\nExamples:\n{examples}\n\nWrite a Python solution reading from stdin, printing to stdout."
        system = "Solve this. Output ONLY Python code in a ```python block."

    resp = client.messages.create(
        model=MODEL, max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.content[0].text
    tokens = resp.usage.input_tokens + resp.usage.output_tokens

    log.info(f"[OneShot] tokens: {tokens}")
    log.info(f"[OneShot] code:\n{raw}")

    blocks = re.findall(r'```(?:python)?\s*\n(.*?)```', raw, re.DOTALL)
    code = blocks[-1].strip() if blocks else raw.strip()

    hidden_results = run_hidden_tests(code, hidden_tests, problem.get('starter_code', ''))
    hidden_passed = sum(1 for r in hidden_results if r.passed)
    hidden_failures = [f"{r.check_name}: {r.details[:200]}" for r in hidden_results if not r.passed]
    return hidden_passed, len(hidden_tests), tokens, hidden_failures


def run_oneshot(problem, hidden_tests, attempts=1):
    """Run one-shot k times, return best result."""
    log = logging.getLogger(__name__)
    best = None
    total_tokens = 0
    for i in range(attempts):
        passed, total, tokens, failures = run_oneshot_single(problem, hidden_tests)
        total_tokens += tokens
        log.info(f"[OneShot] attempt {i+1}/{attempts}: {passed}/{total}")
        if best is None or passed > best[0]:
            best = (passed, total, failures)

    hidden_passed, hidden_total, hidden_failures = best

    return {
        "solved": hidden_passed == hidden_total,
        "hidden_passed": hidden_passed,
        "hidden_total": hidden_total,
        "tokens": total_tokens,
        "attempts": attempts,
        "hidden_failures": hidden_failures,
    }


# === GFSO ===

def run_gfso(problem, bench_input, hidden_tests):
    log = logging.getLogger(__name__)
    content = clean_content(problem)
    pub = json.loads(problem['public_test_cases'])
    examples = "\n".join(
        f"Input:\n{t['input'].strip()}\nOutput:\n{t['output'].strip()}" for t in pub
    )
    starter_code = problem.get('starter_code', '')
    if starter_code:
        problem_prompt = f"{content}\n\nExamples:\n{examples}\n\nComplete this function:\n{starter_code}"
    else:
        problem_prompt = f"{content}\n\nExamples:\n{examples}"

    criteria = tuple(Criteria(
        name=c['name'],
        description=c.get('description', ''),
        input=c.get('input'),
        expected=c.get('expected'),
        n=c.get('n'),
        timeout=c.get('timeout'),
    ) for c in bench_input['criteria'])

    def format_criterion(c):
        esc = lambda s: s.replace('\n', '\\n') if s else s
        if c.input and c.expected:
            return f"- {c.name}: Returns {esc(c.expected)} for input: {esc(c.input)}"
        if c.input:
            return f"- {c.name}: Does not crash on input: {esc(c.input)}"
        if c.n:
            return f"- {c.name}: Completes within {c.timeout or 10}s for n={c.n}"
        return f"- {c.name}: {c.description}"
    criteria_text = "\n".join(format_criterion(c) for c in criteria)
    neglected = tuple(bench_input.get('neglected', []))

    spec = Spec(description=problem_prompt, criteria=criteria, neglected=neglected)
    storage = MemoryStorage()
    example_input = pub[0]['input'] if pub else ""
    starter_code = problem.get('starter_code', '')
    verifier = CodeVerifier(storage, example_input, starter_code=starter_code)
    agent = BenchAgent(
        client=client, model=MODEL, verifier=verifier,
        problem_prompt=problem_prompt, criteria_text=criteria_text,
        is_function=bool(starter_code),
    )
    engine = Engine(storage=storage, agents=agent, llm=None, validate_signals=False)
    engine.start()

    task_id = TaskId("bench-0")
    engine.assign_task(task_id, spec, AgentId("haiku"), max_iterations=3)
    engine.wait_idle()

    final_state = engine.get_state(task_id)
    task = engine.get_task(task_id)

    # Pick best iteration by criteria pass count (symmetric to one-shot best-of-k)
    history = agent.code_history.get(task_id, [])
    cr = agent.criteria_results
    if history and cr and len(history) == len(cr):
        best_idx = max(range(len(cr)), key=lambda i: cr[i]['passed'])
        code = history[best_idx]
        log.info(f"[GFSO] best iteration: {best_idx} ({cr[best_idx]['passed']}/{cr[best_idx]['total']} criteria)")
    else:
        code = agent.code.get(task_id, "")

    log.info(f"[GFSO] Final state: {final_state.name if final_state else '?'}")
    log.info(f"[GFSO] Iterations: {task.iteration if task else '?'}")
    for e in engine.audit_log(task_id):
        old = e.old_state.name if e.old_state else "-"
        new = e.new_state.name if e.new_state else "-"
        log.info(f"[GFSO]   {e.signal.name}: {old} → {new}")

    hidden_results = run_hidden_tests(code, hidden_tests, problem.get('starter_code', ''))
    hidden_passed = sum(1 for r in hidden_results if r.passed)
    hidden_failures = [f"{r.check_name}: {r.details[:200]}" for r in hidden_results if not r.passed]

    engine.stop()

    return {
        "solved": hidden_passed == len(hidden_tests),
        "hidden_passed": hidden_passed,
        "hidden_total": len(hidden_tests),
        "tokens": agent.total_tokens,
        "tokens_per_call": agent.tokens_per_call,
        "iterations": task.iteration if task else 0,
        "final_state": final_state.name if final_state else "?",
        "criteria_results": agent.criteria_results,
        "hidden_failures": hidden_failures,
    }


# === Run one problem ===

def run_problem(problems, bench_input):
    idx = bench_input['problem_index']
    p = problems[idx]
    hidden = get_hidden_tests(p)
    log_file = setup_problem_log(idx)

    print(f"[{idx}] {p['question_title']} ({p['question_id']}) — {len(hidden)} hidden tests")

    # GFSO first — to know how many attempts it used
    gfso = run_gfso(p, bench_input, hidden)
    gfso_attempts = len(gfso['tokens_per_call'])  # total LLM calls = attempts

    # One-shot with same number of attempts (best-of-k)
    oneshot = run_oneshot(p, hidden, attempts=gfso_attempts)

    result = {
        "problem_index": idx,
        "problem_title": p['question_title'],
        "problem_id": p['question_id'],
        "platform": p['platform'],
        "oneshot": oneshot,
        "gfso": gfso,
        "delta": {
            "hidden_tests": gfso['hidden_passed'] - oneshot['hidden_passed'],
            "solved": gfso['solved'] and not oneshot['solved'],
        },
        "log_file": log_file,
    }

    print(f"  A: {oneshot['hidden_passed']}/{oneshot['hidden_total']} {'SOLVED' if oneshot['solved'] else 'FAIL'} | {oneshot['tokens']} tok | best-of-{gfso_attempts}")
    print(f"  B: {gfso['hidden_passed']}/{gfso['hidden_total']} {'SOLVED' if gfso['solved'] else 'FAIL'} | {gfso['tokens']} tok | {gfso['iterations']} reworks")
    print(f"  Delta: {result['delta']['hidden_tests']:+d} tests")

    return result


# === Results persistence ===

def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {"results": []}


def save_result(result):
    data = load_results()
    # Replace if problem already exists
    data['results'] = [r for r in data['results'] if r['problem_index'] != result['problem_index']]
    data['results'].append(result)
    data['results'].sort(key=lambda r: r['problem_index'])
    # Recompute summary
    results = data['results']
    os_solved = sum(1 for r in results if r['oneshot']['solved'])
    gs_solved = sum(1 for r in results if r['gfso']['solved'])
    n = len(results)
    data['summary'] = {
        "total_problems": n,
        "oneshot_solved": os_solved,
        "oneshot_solved_pct": round(100 * os_solved / n, 1) if n else 0,
        "gfso_solved": gs_solved,
        "gfso_solved_pct": round(100 * gs_solved / n, 1) if n else 0,
        "gfso_better": sum(1 for r in results if r['delta']['solved']),
        "gfso_same": sum(1 for r in results if r['gfso']['solved'] == r['oneshot']['solved']),
        "gfso_worse": sum(1 for r in results if not r['gfso']['solved'] and r['oneshot']['solved']),
        "oneshot_total_tokens": sum(r['oneshot']['tokens'] for r in results),
        "gfso_total_tokens": sum(r['gfso']['tokens'] for r in results),
    }
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# === Main ===

def main():
    problems = load_problems()
    all_inputs = load_bench_inputs()

    # Parse args
    args = sys.argv[1:]
    if not args:
        args = ['3']
    if args[0] == 'all':
        indices = [e['problem_index'] for e in all_inputs]
    else:
        indices = [int(a) for a in args]

    for idx in indices:
        bench_input = next(e for e in all_inputs if e['problem_index'] == idx)
        try:
            result = run_problem(problems, bench_input)
            save_result(result)
        except Exception as e:
            print(f"[idx={idx}] FAILED: {type(e).__name__}: {e}")
            logging.getLogger(__name__).exception(f"problem {idx} crashed")

    # Print summary
    data = load_results()
    s = data.get('summary', {})
    print("\n" + "=" * 70)
    print(f"SUMMARY ({s.get('total_problems', 0)} problems)")
    print("=" * 70)
    print(f"  One-shot solved: {s.get('oneshot_solved', 0)} ({s.get('oneshot_solved_pct', 0)}%)")
    print(f"  GFSO solved:     {s.get('gfso_solved', 0)} ({s.get('gfso_solved_pct', 0)}%)")
    print(f"  GFSO better:     {s.get('gfso_better', 0)}")
    print(f"  GFSO same:       {s.get('gfso_same', 0)}")
    print(f"  GFSO worse:      {s.get('gfso_worse', 0)}")
    print(f"  Tokens A/B:      {s.get('oneshot_total_tokens', 0)} / {s.get('gfso_total_tokens', 0)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
