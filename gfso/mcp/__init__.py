"""MCP surface (track-b): the agent operates the CORE through the SAME upper API the UI rides.

Two pieces:
- `tools.py` — pure tool functions `(engine, args) -> JSON-able dict`. Authoring tools desugar to the
  12-signal FSM (no bypass); testable without the MCP transport.
- `server.py` — a thin FastMCP shell that registers the tools (the MCP SDK is a required dependency).
"""
