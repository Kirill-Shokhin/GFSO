"""THE RECORD OF PLACES MADE: which node places the system made (`made`), kept with the project's settings by path —
written where a place is made or removed (`workspaces`) and where a copy-in carries places into the project's volume
(`carried`), read with no subprocess. Derived from no file system: a place may stand nowhere on this host."""
from __future__ import annotations

import os
from pathlib import Path

from gfso.core.protocol.procedure import round_of
from gfso.core.types import HOST, MADE, NODES, PLACES, VOLUME, base_named, base_of_nodes, nodes_root
from gfso.engine.findings import record_round


#: the places this process asked about where the record had none, and found not made (`made`)
_UNMADE: set = set()


def made(engine, place: str) -> bool:
    """Was `place` made? THE SYSTEM'S RECORD, not the file system: `workspaces._ensure_place` adds a place it made,
    `clear_workspaces` drops one it removed, kept with the project's settings (a restart reads it) and read with no
    subprocess — the transition bus asks it. A place may stand nowhere on this host, and what stands where an agent
    writes decides nothing of the protocol."""
    if (got := engine.graph.setting(MADE + place)) is not None or (
            got := engine.graph.setting(MADE + _spelled(place))) is not None or (   # …as a copy-in carried it
            got := engine.graph.setting(MADE + _named_as_before(place))) is not None or (
            got := engine.graph.setting(MADE + str(laid_out_before(place)))) is not None:   # …recorded beside its base
        return got == "1"
    # …a place made before the record was kept: asked once (once per process where it is not made), then recorded —
    # the record decides from there on. On this host, never by a call into a container from the transition bus: until
    # the places move into volumes they are host directories (a fallback that goes with that move)
    if place in _UNMADE or engine.graph.setting(VOLUME + "places"):     # …moved into a volume: the record alone
        return False
    if HOST.is_dir(place):
        record(engine, place, True)
        return True
    _UNMADE.add(place)
    return False


def record(engine, place: str, made: bool) -> None:
    """`place` recorded as made, or as removed — by the path it is asked by (`made`)."""
    engine.graph.store_setting(MADE + place, "1" if made else "0")


def _named_as_before(place: str) -> str:
    """A place of a base whose name holds what `place_name` escapes, as its record was written before it did."""
    return str(Path(*(NODES + base_named(x) if x.startswith(NODES) else x for x in Path(place).parts)))


def laid_out_before(place) -> Path:
    """A place under the installation's places (`nodes_root`) as it was named beside its base before 2026-11-15: the
    record of a project made then keys its places so; any other path as it is."""
    p = Path(place)
    nodes = next((a for a in p.parents if a.name.startswith(NODES)), None)
    if nodes is None or nodes.parent.parent.name != PLACES:
        return p
    return base_of_nodes(nodes).parent / nodes.name / p.relative_to(nodes)


def _laid_out_now(place) -> str:
    """A place or round laid out beside its base before 2026-11-15, as it is named now under the installation's places
    (`nodes_root`) — `laid_out_before` read the other way; any other path as it is."""
    p = Path(place)
    nodes = next((a for a in p.parents if a.name.startswith(NODES)), None)
    if nodes is None or nodes.parent.parent.name == PLACES:
        return str(p)
    return str(nodes_root(base_of_nodes(nodes)) / p.relative_to(nodes))


def _spelled(place) -> str:
    """One spelling of a place, whichever it arrived in — what a copy-in records it by (`carried`)."""
    return os.path.normcase(os.path.abspath(place))


def carried(engine, dirs) -> None:
    """The places and rounds a copy-in carried into the project's volume, recorded as made — before their host copy
    is consumed, which the record of places made before it was kept fell back on (`made`, `round_stands`)."""
    for d in map(_laid_out_now, dirs):        # …carried in from beside the base, recorded by the names they now stand by
        if round_of(d):
            record_round(engine.graph, d, True)
        elif not Path(d).parent.name.startswith("."):
            record(engine, _spelled(d), True)
