"""The twelve-signal machine: the transition table, the invariants, and what makes a report a
VERDICT rather than ⊥. Pure functions over state — no storage, no clock, no model.
"""
from .fsm import transition
from .invariants import validate_fail_has_criteria
