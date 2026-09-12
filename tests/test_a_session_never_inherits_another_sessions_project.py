"""One session's project must never be reachable from a different session.

The session→project map was keyed by `id(session)`. CPython reuses an address once the object behind
it is collected, and the MCP SDK drops the transport when a session ends — so successive sessions,
which are the same type and size and therefore the likeliest reuse candidates, could land on one key.
A session that had never called `use_project` then inherited another one's project and its verbs
wrote into THAT graph, silently, while the registry reported a different active project in the same
second. Writing into the wrong graph is not a degraded answer; it is the wrong answer, unnoticed.

The key is now the session OBJECT — weakly where the object allows it, so the entry dies with the
session, and strongly where it does not, which keeps the object alive and its address unre-usable.
Either way an entry cannot be reached by a session that did not make it.

Control: key `_SESSION_PROJECTS` by `id(session)` again and `test_a_recycled_address_resolves_to_no_project`
goes red.
"""
import gc

from gfso.mcp.server import _SESSION_PROJECTS, _SessionProjects


class _Session:
    """A stand-in with the one property that matters: it is an ordinary object with an address."""


def test_two_live_sessions_do_not_share_an_entry():
    a, b = _Session(), _Session()
    m = _SessionProjects()
    m[a] = "alice"
    assert m.get(a) == "alice"
    assert m.get(b) is None, "a session that never chose a project must resolve to none"


def test_the_entry_dies_with_the_session():
    """The discriminating assertion: nothing keyed on a DEAD session may still be in the map.

    An earlier version of this test tried to catch the defect by allocating until CPython handed
    back the freed address. It never fired — pymalloc gives a different block every time — so the
    case fell through to a check that is trivially true under the old code as well, and the whole
    file passed with `id(key)` restored. Measured. What discriminates without depending on the
    allocator is the property itself: the entry must not OUTLIVE its session, because an entry that
    outlives one can be found again by an address that is handed out again.
    """
    m = _SessionProjects()
    s = _Session()
    m[s] = "alice"
    assert m.get(s) == "alice"
    del s
    gc.collect()
    assert list(m.items()) == [],         "the mapping outlived its session — an address handed out again would find alice's project"


def test_an_object_that_refuses_a_weak_reference_is_still_keyed_safely():
    m = _SessionProjects()
    unweakrefable = object()          # `object()` instances take no weak reference
    m[unweakrefable] = "alice"
    assert m.get(unweakrefable) == "alice"
    assert m.get(object()) is None


def test_the_module_level_map_is_the_same_kind():
    assert isinstance(_SESSION_PROJECTS, _SessionProjects)
