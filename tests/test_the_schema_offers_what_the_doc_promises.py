"""A parameter's TYPE is part of its contract, and the MCP door generates the schema from it.

`dispute_finding`'s own description says `criterion` "also takes a LIST when one reason answers
several findings — a checker that names one obligation in three wordings costs three calls
otherwise". The body has handled a list since the day that was written. The annotation said `str`,
so the generated MCP schema said `{"type": "string"}`, and a stranger who did what the description
told them got their array stringified into one giant key and refused with a multi-kilobyte error
echoing their own JSON back (wave 23, 2026-09-03). Their words: eight calls instead of one, "exactly
the friction the description says was fixed".

The doc, the body and the wire have to agree, and the wire is generated — so the annotation is where
that agreement is written down.
"""
from __future__ import annotations

import asyncio
import typing

import pytest

from gfso import tools as T
from gfso.runtime import ProjectRegistry

mcp = pytest.importorskip("mcp")          # the SDK is optional at import; the door is not built without it
from gfso.mcp.server import create_server  # noqa: E402  — after the skip, or this module cannot load


def test_the_criterion_parameter_is_typed_as_both_shapes_it_accepts():
    assert typing.get_type_hints(T.dispute_finding)["criterion"] == typing.Union[str, list]


def test_and_the_generated_mcp_schema_offers_both(tmp_path, monkeypatch):
    """The door a stranger reads is the schema, not the docstring."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    reg = ProjectRegistry()
    try:
        listed = asyncio.run(create_server(reg).list_tools())
        schema = next(t for t in listed if t.name == "dispute_finding").inputSchema
        criterion = schema["properties"]["criterion"]
        offered = {b.get("type") for b in criterion.get("anyOf", [criterion])}
        assert {"string", "array"} <= offered, criterion
    finally:
        for e in list(reg._engines.values()):
            e.stop()
