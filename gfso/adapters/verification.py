"""Backward-compat shim. Use gfso.adapters.verifiers instead."""
from gfso.adapters.verifiers.subprocess_verifier import (
    SubprocessVerifier as CodeVerifier,
    run_code,
    ExecutionResult,
)

__all__ = ["CodeVerifier", "run_code", "ExecutionResult"]
