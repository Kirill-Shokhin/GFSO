"""Per-task logging setup: each task writes its full trace to its own file."""
from __future__ import annotations

import logging
import os
import sys


def setup_task_log(logs_dir: str, task_id: str) -> str:
    """Redirect root logger to per-task file + stdout. Returns log path."""
    os.makedirs(logs_dir, exist_ok=True)
    safe = task_id.replace("/", "_").replace("\\", "_")
    log_file = os.path.join(logs_dir, f"{safe}.log")
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.setLevel(logging.INFO)
    root.addHandler(logging.FileHandler(log_file, mode="w", encoding="utf-8"))
    root.addHandler(logging.StreamHandler(sys.stdout))
    for h in root.handlers:
        h.setFormatter(logging.Formatter("%(name)s | %(message)s"))
    return log_file
