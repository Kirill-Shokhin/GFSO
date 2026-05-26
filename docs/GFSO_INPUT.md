# .gfso Input Standard

Derived from `gfso/core/types/primitives.py` (Spec, Criteria, Task).

## Format

```json
{
  "spec": {
    "description": "Full task description",
    "criteria": [
      {"name": "example_1", "input": "[12, 9]\n1", "expected": "30"},
      {"name": "edge_min", "input": "[1]\n1"},
      {"name": "performance", "n": 100000, "timeout": 10}
    ],
    "neglected": ["memory optimization"],
    "risk_components": []
  },
  "assignee": "agent_id",
  "max_iterations": 3
}
```

## Criteria Fields

| Field | Type | Description |
|-------|------|-------------|
| name | string | Label for reporting |
| description | string | Optional human comment |
| input | string | stdin to feed the program (newlines as `\n` in JSON) |
| expected | string | Expected stdout (exact match) |
| n | int | Input size for performance generation |
| timeout | int | Seconds limit for performance check |

## Criterion Types (determined by fields present)

| Fields | Type | Verification |
|--------|------|-------------|
| `input` + `expected` | Exact output | Run code with input, compare stdout to expected |
| `input` only | Crash check | Run code with input, check returncode == 0 |
| `n` + `timeout` | Performance | Generate large input (n elements), check completes within timeout |

## Criteria Sources

Criteria are extracted from the problem description:
- **Examples**: public test cases (input/output given in problem)
- **Performance**: size constraints from problem text (n <= 10^5 → n=100000)
- **Edge cases**: minimal valid inputs from constraints (n=1, min values)

## Batch Format (for benchmarks)

```json
[
  {
    "problem_index": 0,
    "criteria": [
      {"name": "example_1", "input": "1\n1 0\na", "expected": "YES"},
      {"name": "performance", "n": 10000, "timeout": 10},
      {"name": "edge_min", "input": "1\n1 0\na"}
    ],
    "neglected": []
  }
]
```

`problem_index` is benchmark metadata. `spec.description` loaded from dataset by index.
Global settings (`assignee`, `max_iterations`) set in benchmark runner, not per-task.
