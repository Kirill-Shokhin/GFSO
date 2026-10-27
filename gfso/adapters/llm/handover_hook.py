"""The CLI's PostToolUse hook that hands a work session's context over from INSIDE its one process (`budget.hooked`):
after every tool call it reads how full the context got — the last turn's usage in the session's own transcript — and,
past the budget's line, asks once for a checked point; at the ceiling it stops the session, whose note the system then
asks for by its conversation. Rounds of a few turns did the same from outside, a process each (the author, 2026-10-27:
«это костыль?… хук нормальный нельзя сделать там? или по колву токенов смотреть»): every round re-read the context it
continued, a fresh session took one blind first step, and a large read inside a round overshot the line unseen.

Run where the CLI runs — on the host or in a project's container — so the standard library only. Its state is the file
`<session id>.hook` beside it, written by the system before the session starts (`budget`, `soft`, `ceiling`, `reopen`,
`boundary`) and kept up by this hook (`opening`, `peak`, `asked`, `stopped`, `beyond`); the system reads it back when
the session ends."""
import json
import os
import sys

TURN = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def context(transcript: str) -> int:
    """The last turn's context — what its message was read over, as the stream's reader counts it (`_turn_context`)."""
    last = 0
    try:
        with open(transcript, encoding="utf-8") as f:
            for line in f:
                msg = json.loads(line).get("message") if line.strip() else None
                if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
                    last = sum(int(msg["usage"].get(k) or 0) for k in TURN)
    except (OSError, ValueError):
        pass                                   # a transcript not yet written or cut mid-line: the turns read so far
    return last


def result(response) -> int:
    """The tool's result in tokens, about — the turn the transcript last reports was read BEFORE it, so a large read
    seen one result late overshot the ceiling's margin (20k on a 200k window, under one 25k read: critic over the hook)."""
    return len(response if isinstance(response, str) else json.dumps(response or "", default=str)) // 4


def decide(s: dict, ctx: int) -> tuple[dict, dict]:
    """(what the hook answers the CLI, the state it leaves) — the rounds' reading (`budget._Session.read`) made after
    every tool call: the line is never under twice the session's opening — a conversation continued from an earlier run
    (`resumed`) opened there, not here — and a reopen at its ceiling on its first reading works on, as without a
    handover (a reopen would open as large)."""
    first = not s.get("read")
    s = {**s, "read": True, "peak": max(ctx, s.get("peak") or 0),
         "opening": ctx if first and not s.get("resumed") else s.get("opening")}
    s["beyond"] = bool(s.get("beyond") or (first and s.get("reopen") and ctx >= s["ceiling"]))
    # …and silent once it has stopped the session: the close that asks for its note by the same conversation keeps the
    # turn it has to spare should the model reach for a tool (`budget.CLOSE_TURNS`; critic over the hook path)
    if s["beyond"] or s.get("stopped"):
        return {}, s
    if ctx >= s["ceiling"]:
        return {"continue": False, "stopReason": "the session's context reached its ceiling"}, {**s, "stopped": True}
    soft = max(s["budget"], 2 * (s["opening"] or 0)) if s.get("budget") else None
    if soft and ctx >= soft and not s.get("asked"):
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": s["boundary"]}}, \
            {**s, "asked": True}
    return {}, s


def main() -> None:
    """One PostToolUse run: the CLI's event on stdin, the session's state beside this file, `decide`'s answer out."""
    got = json.load(sys.stdin)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{got.get('session_id')}.hook")
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        return                                    # a session the system armed no handover for
    say, s = decide(s, context(got.get("transcript_path") or "") + result(got.get("tool_response")))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(s, f)
    if say:
        print(json.dumps(say))


if __name__ == "__main__":
    main()
