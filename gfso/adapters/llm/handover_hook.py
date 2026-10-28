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
import time

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


def locked(path: str):
    """The state's one writer at a time: runs of this hook for parallel tool calls each read, decided and rewrote it in
    place, and a torn file read as "no handover armed" — the session ran on to 169k with no ask (GB_sql_database_tnl5do036,
    root.select; probed: 13 of 150 three-at-once runs tore it)."""
    lock = path + ".lock"
    for _ in range(400):                          # 10 ms apart: a run holds it for a read and a write
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return lock
        except FileExistsError:
            try:
                if time.time() - os.stat(lock).st_mtime > 10:     # left by a run that died holding it
                    os.unlink(lock)
            except FileNotFoundError:
                continue
        except PermissionError:                   # Windows: the last holder's delete still pending
            pass
        time.sleep(0.01)
    return None


def main() -> None:
    """One PostToolUse run: the CLI's event on stdin, the session's state beside this file, `decide`'s answer out."""
    got = json.load(sys.stdin)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{got.get('session_id')}.hook")
    if not os.path.exists(path):
        return                                    # a session the system armed no handover for
    lock = locked(path)
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
        say, s = decide(s, context(got.get("transcript_path") or "") + result(got.get("tool_response")))
        tmp = f"{path}.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:   # …whole or not at all: a new file renamed over the old
            json.dump(s, f)
        for left in range(200, -1, -1):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:               # Windows: a reader holds the old one open for an instant
                if not left:
                    raise
                time.sleep(0.01)
    finally:
        if lock:
            os.unlink(lock)
    if say:
        print(json.dumps(say))


if __name__ == "__main__":
    main()
