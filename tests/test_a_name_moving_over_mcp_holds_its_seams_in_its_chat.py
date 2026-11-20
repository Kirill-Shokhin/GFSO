"""A stream's name that moves over its own MCP connection works in a chat — the executor's own fact, recorded by the
door its move comes through (§10.4: autonomy per task and role): each seam the person issues to it then reads as a top
held solo in that chat, with nothing set at any node. Taken on a running console (`act_as`) or launched with the
name's token, the record is the same. Through the real door: an MCP client, its lease, the server's own resolver."""
import uuid

import anyio
import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso import config
from gfso.core.types import TaskId
from tests import test_a_connection_signs_as_its_principal as P
from tests.test_a_connection_signs_as_its_principal import HUMAN, door  # noqa: F401 — the fixture
from tests.test_a_running_console_takes_a_streams_name import _call
from tests.support import REGISTER


def _his_seam(e, name):
    """His root, and a seam he issues from it to `name`."""
    T.create_task(e, "root", {"description": "his goal", "criteria": [HUMAN]}, assignee="user", agent="user")
    T.decompose(e, "root", [{"task_id": f"root.{name}", "assignee": name, "covers": ["accepted"],
                             "spec": {"description": "a direction", "criteria": [HUMAN]}}],
                accepted_risks=REGISTER, agent="user")
    e.wait_idle()
    assert e.scope_at(f"root.{name}") is None, "a top before its holder moved in a chat"


def _top(e, name):
    s = e.scope_at(f"root.{name}") or {}
    return s.get("top"), s.get("holder"), s.get("perform")


def test_a_name_taken_on_a_running_console_moves_and_its_seam_is_a_top_in_its_chat(door):
    e, url = door
    _his_seam(e, "eng7")
    lease, go = uuid.uuid4().hex, lambda lease, verb, **a: anyio.run(_call, url, lease, verb, a)
    assert go(lease, "act_as", name="eng7")["name"] == "eng7"
    go(lease, "signal", task_id="root.eng7", signal="ACCEPT")
    e.wait_idle()
    assert _top(e, "eng7") == ("root.eng7", "eng7", "in_chat")


def test_a_console_launched_with_the_names_token_moves_and_its_seam_is_a_top_in_its_chat(door):
    e, url = door
    _his_seam(e, "eng8")
    err, text = anyio.run(P._call, url, "eng8", "signal", {"task_id": "root.eng8", "signal": "ACCEPT"})
    assert not err, text
    e.wait_idle()
    assert _top(e, "eng8") == ("root.eng8", "eng8", "in_chat")


def test_a_move_off_the_mcp_door_records_no_chat(door):
    """The same name's move in process, no connection between: no chat is said of it."""
    e, _ = door
    _his_seam(e, "eng9")
    token = config.CALLER.set(config.Principal("eng9", ("eng9",), "tok", "token"))
    try:
        TL.TOOLS["signal"](e, "root.eng9", "ACCEPT")
    finally:
        config.CALLER.reset(token)
    e.wait_idle()
    assert e.scope_at("root.eng9") is None
