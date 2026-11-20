"""TECH REPORTS as a log of letters: each from its author to the one who can act on it, about a node, open until that
one or its author resolves it. Thirteen stood open on one project with nobody able to say who had sent each to whom,
and nothing could close one, so a year's project would press with every report it ever got (the author, 2026-11-20).
The records live in one setting (`TECH_KEY`), append-only: a report's place in it is its id, the same on every read,
which is what gives the reports stored before ids existed theirs."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from gfso.config import PERSON
from gfso.core.graph.model import Graph, party_kind
from gfso.core.types import TaskId

PREFIX = "tr-"


def report_id(place: int) -> str:
    """The id of the report at `place` (0-based) in the log."""
    return f"{PREFIX}{place + 1}"


def addressee(graph: Graph, node, registered: dict) -> str:
    """WHO CAN ACT ON A REPORT. A report says the system left its author no honest move on `node`; the party whose moves
    there can give one back — rule the finding, revise or reassign the contract, reopen — is the node's issuer (§10.1),
    so it goes to the issuer. Not where that issuer is a machine (a registered role, or the standing agent under AUTO):
    no packet reads a report back (§11.3), so a machine never would, and the report would stand open for ever — it goes
    to the person, who runs the machine and carries a defect of the system to its maker. With no node, or one no longer
    in the graph, nothing in the project moves for it: the person's too."""
    issuer = graph.issuer_of(TaskId(str(node))) if node else None
    return str(issuer) if issuer and party_kind(graph, str(issuer), registered) == "person" else PERSON


def read(records: list, graph: Graph, registered: dict) -> list[dict]:
    """The log as read: every report with its id and addressee, those stored without them given theirs by the same
    rule as a new one."""
    return [{**r, "id": r.get("id") or report_id(i),
             "addressee": r.get("addressee") or addressee(graph, r.get("node"), registered)}
            for i, r in enumerate(records)]


def resolution_refusal(rec: Optional[dict], rid, how: str, by: str) -> Optional[str]:
    """Why `by` may not resolve the report `rec` (`rid` asked) with `how`, or None. Only the one it is addressed to, who
    acts on it, or the one who wrote it, who knows when it no longer holds: anyone else closing it would close a letter
    that was not theirs to read as answered."""
    if rec is None:
        return f"no tech report {rid} — `tech_reports resolved=true` lists every id"
    if rec.get("resolved_at"):
        return f"{rid} was resolved at {rec['resolved_at']} by {rec.get('resolved_by')}: {rec.get('how')}"
    if not how:
        return f"a resolution says how {rid} was dealt with"
    if by not in (rec["addressee"], rec.get("actor")):
        return (f"{rid} is addressed to {rec['addressee']} and was written by {rec.get('actor')}: only they resolve it, "
                f"not {by}")
    return None


def resolved(rec: dict, how: str, by: str) -> dict:
    """`rec` as resolved now by `by`, `how` its reason."""
    return {**rec, "resolved_at": datetime.now().isoformat(timespec="seconds"), "resolved_by": by, "how": how[:4000]}
