"""The place a role works in is the system's to say, whatever directory the contract names.

A goal can carry a path — the E3 harness wrote "Working directory: <base>" into the request, and a user can write one
too. Under AUTO the root's executor read its contract's path, wrote into the user's base, and its uncommitted edits
refused the join while the signed branch lacked them (2026-10-07). The executor's packet, for a node or a scope, ends
with the system's place: write only here and below, read anything else. Where that place is a node's checkout — for
the executor, the validator and the machine issuer's contact alike — the base's committed paths are the same paths
here and the rest of the base is read there: a reader told only "not yours" disputes a contract it could fulfil, one
told "the same path here" looks for an ignored data file the checkout lacks. Nothing is asserted over a validator's
directory that may be the roster's guess (critics, 2026-10-08).

CONTROL: drop the rule's sentence for any role, put a packet back on a bare "Working directory: …" line, or break
`base_of` — and these go red.
"""
from pathlib import Path

from gfso import packets
from gfso.core.types import AgentId, Criteria, Spec, TaskId
from gfso.issuer import CONTACT
from gfso.workspaces import base_of
from tests.support import make_engine, pinned

BASE = str(Path("/home/user/project"))
PLACE = str(Path("/home/user/.gfso-nodes-project/p/root"))      # `_place_of`'s layout for base, project p, node root
SHARED = str(Path("/srv/shared"))                               # no git base: the roster's directory, no checkout


def _root():
    e = make_engine()
    e.start()
    e.assign_task(TaskId("root"), Spec(f"Implement uniq.\n\nWorking directory: {BASE}",
                                       (Criteria("u", "uniq works", check=pinned("u")),)), AgentId("w"))
    e.wait_idle()
    return e, e.graph.get_task(TaskId("root"))


def _last_place(packet: str) -> str:
    return packet.rsplit("Working directory: ", 1)[1].split("\n", 1)[0]


def test_a_node_place_reads_back_its_base():
    assert base_of(PLACE) == BASE
    assert base_of(SHARED) is None and base_of(None) is None


def test_the_executor_works_in_the_systems_place_and_reads_the_bases_paths_there():
    e, root = _root()
    for packet in (packets._executor_packet(e, root, PLACE), packets._scope_packet(e, root, [root], PLACE)):
        assert f"Working directory: {BASE}" in packet, "the contract is shown as written"
        assert _last_place(packet) == PLACE, "the system's place is the last word on where to work"
        assert "Write only here and below" in packet and "you may read, never write" in packet
        assert f"checkout of `{BASE}` as committed when it was made" in packet
        assert f"under `{BASE}` is the same path here" in packet and f"read in `{BASE}`" in packet
        assert "uncommitted edits, untracked or ignored files, later commits" in packet
    shared = packets._executor_packet(e, root, SHARED)
    assert "Write only here and below" in shared and "as committed" not in shared, "no git base, no checkout"
    e.stop()


def test_the_validator_checks_the_delivery_in_the_systems_place():
    e, root = _root()
    for packet in (packets._validator_packet(e, root, "delivered", PLACE),
                   packets._scope_validator_packet(e, [(root, "delivered", root.spec.criteria)], PLACE, None,
                                                   frozenset({"root"}))):
        assert f"Working directory for your tools: {PLACE}" in packet
        assert f"under `{BASE}` is the same path here" in packet
        assert "Write only here" not in packet, "the validator writes nothing anywhere; its rule is where to look"
    # where it stands may be the roster's guess (a registered validator's own directory): nothing asserted over it
    guess = packets._validator_packet(e, root, "delivered", SHARED)
    assert "as committed" not in guess and "whatever directory" not in guess
    e.stop()


def test_the_machine_issuer_in_contact_reads_the_nodes_place():
    """The issuer answering a dispute runs the checks in the node's workspace (its contact envelope); the same rule."""
    text = CONTACT.format(where=PLACE, checkout=packets.checkout_note(PLACE))
    assert f"under `{BASE}` is the same path here" in text and "nothing is ever written there" in text
