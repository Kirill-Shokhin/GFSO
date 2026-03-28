"""Q = (q_T, q_D, q_V, q_Dep, q_Del). Self-measuring from graph (Th.10).

Formulas from paper §7.2:
  q_T   = 1 − |{n : challenged}| / |{n : DONE}|
  q_D   = |{n : all children pass ∧ n pass}| / |{n : all children pass, |children|>0, DONE}|
  q_V   = 1 − |{n : done_reason=AUTO}| / |{n : DONE(pass) ∨ DONE(auto)}|
  q_Dep = |declared| / |declared ∪ discovered|
  q_Del = 1 − |{n : was reassigned}| / |{n : DONE}|
"""
from __future__ import annotations

from gfso.core.types import State, DoneReason
from .model import Graph


def q_T(graph: Graph) -> float:
    """Task quality: 1 − (challenged specs / done tasks).

    High q_T = specs are clear. Low q_T = specs get challenged often.
    """
    all_tasks = graph._storage.get_all_tasks()
    done = [t for t in all_tasks if t.state == State.DONE]
    if not done:
        return 1.0
    challenged = sum(1 for t in done if t.was_challenged)
    return 1.0 - challenged / len(done)


def q_D(graph: Graph) -> float:
    """Decomposition quality: (all children pass ∧ task pass) / (all children pass, non-atomic, done).

    High q_D = good decompositions. Low = children pass but parent fails (decomposition missed something).
    """
    all_tasks = graph._storage.get_all_tasks()
    done_with_children = []
    for t in all_tasks:
        if t.state != State.DONE:
            continue
        children = graph._storage.get_children(t.id)
        if not children:
            continue  # atomic task, skip
        all_children_pass = all(
            c.state == State.DONE and c.done_reason == DoneReason.PASS
            for c in children
        )
        if all_children_pass:
            done_with_children.append(t)

    if not done_with_children:
        return 1.0
    good = sum(1 for t in done_with_children if t.done_reason == DoneReason.PASS)
    return good / len(done_with_children)


def q_V(graph: Graph) -> float:
    """Validation quality: 1 − |{t : V=pass, later found wrong}| / |{t : V=pass}|.

    Paper §7.2: measures false positive rate in validation.
    false_positive flag is set when a DONE(pass) task is later discovered to be wrong
    (e.g. parent fails despite all children passing, or post-completion audit).
    """
    all_tasks = graph._storage.get_all_tasks()
    passed = [t for t in all_tasks if t.state == State.DONE
              and t.done_reason in (DoneReason.PASS, DoneReason.AUTO)]
    if not passed:
        return 1.0
    false_positives = sum(1 for t in passed if t.false_positive)
    return 1.0 - false_positives / len(passed)


def q_Dep(graph: Graph) -> float:
    """Dependency health: declared / (declared ∪ discovered).

    High q_Dep = deps were known upfront. Low = surprise blocks from hidden deps.
    """
    edges = graph._storage.get_dep_edges()
    if not edges:
        return 1.0
    declared = sum(1 for e in edges if not e.discovered)
    total = len(edges)
    return declared / total


def q_Del(graph: Graph) -> float:
    """Delegation quality: 1 − (reassigned / done).

    High q_Del = right executor chosen first time. Low = capability mismatches.
    Paper §7.2: 1 − |{t : reassigned}| / |{t : DONE}|
    """
    all_tasks = graph._storage.get_all_tasks()
    done = [t for t in all_tasks if t.state == State.DONE]
    if not done:
        return 1.0
    reassigned = sum(1 for t in done if t.was_reassigned)
    return 1.0 - reassigned / len(done)
