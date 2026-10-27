"""A worker's CONTEXT — handed over by the system before it outgrows what the resource should carry, whatever its provider
does (the author, 2026-10-27: «ставим 300к … точку. При достижении агент … должен получить инструкцию похожую на наш
close-open»; «именно эта штука должна быть авторской внутри конструктора»).

An agent run re-reads its whole context on every turn, so its bill follows the context it carries: on one sql_database
row (haiku 4.5) executors were 77% of the bill, cache reads 63% and writes 17% of theirs, at a median 55% of a 200k window
(`data/gb-sql-database-tnildb300.db`). A work session (`RecordingProvider.budgeted`) runs in rounds of a few turns, its
context read after each. Two lines (docs/notes/CONTEXT_HANDOVER_RESEARCH.md):
- the CEILING, always: the model's window less a margin. A session that reaches the window ends "prompt too long" with
  nothing handed on, so "no budget" is the ceiling at the window's edge, never none. There the session closes at once.
- the BUDGET, the resource's setting (`context_budget`): past it the session is asked once to bring its work to a point
  it has checked — a cut in the middle of a debugging leaves half-built, unrecorded work — and to write its note there.
The note is the session's own, under fixed sections, updating the note it started from; a fresh session OPENS on the
same packet, that note and the place's machine state (`machine_state`: what the checks print now, what changed) — the
note's word is not the state. Nothing in the packet counts down: a worker that knows its end is near cuts corners. One
clock bounds the run, its session cap (§12.2): no count of handovers stops it.

A MECHANISM: whether and where a budget pays is measured by paired rows, not assumed.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, replace

log = logging.getLogger(__name__)

#: the note's sections, every one present, written `none` where it has nothing (Factory's anchored summary; the research)
SECTIONS = ("plain text, at most 60 lines, every section below present, written `none` where it has nothing; name files "
            "and functions by their paths:\n"
            "1. Reading of the task — only where you read the contract other than literally, and why.\n"
            "2. Done and checked — what, where, and the command whose output showed it.\n"
            "3. Done, not checked.\n"
            "4. Refuted — each approach you dropped and the observation that ruled it out.\n"
            "5. Current hypothesis — what you believe is wrong now, and whether a command showed it or you suppose it.\n"
            "6. Constraints found on the way — what must not be touched, and why.\n"
            "7. Next step — the one action you were about to take.\n")
CLOSE = ("This session ends here, and a fresh session continues the same task from the note you write now. Do not call "
         "any tool. Write the note — " + SECTIONS
         + "Do not deliver the task and do not answer in its report format: the note only.")
PREVIOUS = ("\n\nThis session started from the note below. Update it — keep what still holds, correct what does not, add "
            "what this session learned — rather than writing it anew:\n")
#: the close keeps the round's tools — another tool set is another cached prefix, re-written whole at the write price —
#: and is given a turn to spare should the model reach for one anyway
CLOSE_TURNS = 2
#: seconds a close needs to be worth starting: with less, no fresh session would have time to continue from its note
CLOSE_MIN_S = 120
CONTINUE = "Continue the task."
#: how a round the system stopped at its context reading, and went on with, ended — not the role's cap
CONTINUED = "continued"
#: the first line of a note written at a checked point — what tells it from the task's own report
NOTE_MARK = "HANDOVER NOTE"
#: ONE round reaches the point and writes the note: a round that ends in an answer is not continued by some providers
#: (the CLI's clean-context rule, `headless._after_the_round`), so a separate close after it would write from nothing
BOUNDARY = ("Bring what you are doing to a point you have checked: finish the edit you are in, run the check that tells "
            "you where the work stands, and stop there. Do not deliver for this reason and do not cut the task short — it "
            "goes on in a fresh session that starts from the note you write at that point. Then stop calling tools and "
            f"write that note: its first line `{NOTE_MARK}`, then " + SECTIONS
            + "If the task is done instead, deliver it as the task says.")
HANDOVER = ("\n\n## Where an earlier session of this task stopped\nAn earlier session worked this task in your directory "
            "and handed it on in the note below. Read the note and the state under it, run the check that tells you "
            "where the work stands, then continue. The task goes on across as many sessions as it needs: do not stop "
            "early, and deliver only when the criteria hold.\n\n### Its note\n")
STATE = "\n\n### The place as the system sees it now (machine state, not the note's word)\n"
#: what stops the project, not the run: the conversation is kept for after the lift, as a capped round's is
STOPS = ("limit", "unavailable", "unauthorized")
#: the ceiling's margin below the window: the close itself, and a turn that reads a large file, must still fit
MARGIN, MARGIN_SHARE = 20_000, 0.1
#: the window ASSUMED where the provider reports none — the floor of today's models: a ceiling exists always, and a
#: server whose own window is smaller and unsaid truncates whatever the system assumes (provider-check warns of it)
DEFAULT_WINDOW = 128_000


def cut_at_turn_cap(rec: dict) -> bool:
    """Did the round stop at its turn cap — the one ending a run continues?"""
    return rec.get("stop_reason") == "max_turns"


def ceiling(window) -> int:
    """The context a session never carries past: its window — `DEFAULT_WINDOW` where none is reported — less the
    margin."""
    window = window or DEFAULT_WINDOW
    return int(window - max(MARGIN, window * MARGIN_SHARE))


def _left(timeout, t0):
    return None if timeout is None else int(timeout - (time.monotonic() - t0))


@dataclass
class _Session:
    """What a session's rounds say of its context — how full, how fast it grows, the line the next reading looks for —
    and what the reading of a cut round decides (`read`). A reopen is a new one carrying the budget and the note."""
    budget: int | None
    note: str = ""
    fresh: bool = True
    asked: bool = False
    peak: int | None = None
    grow: float | None = None
    line: int | None = None
    opening: int | None = None
    beyond: bool = False

    def step(self, p, used, max_turns) -> int:
        """Turns to the next reading: as many as half the distance to the line allows at the growth seen — a turn that
        reads a large file grows the context far past the mean, and on the CLI a round past the window loses its
        conversation — no more than five of the provider's steps (a round is a process on some providers), ONE for a
        fresh session under a budget (its opening size decides whether the budget can hold: `read`), two once a checked
        point is asked for (a round that does not reach it is cut as at the ceiling), and within the role's own cap."""
        step = (1 if self.fresh and self.budget else p.budget_step if not (self.peak and self.grow and self.line)
                else max(1, min(5 * p.budget_step, int((self.line - self.peak) / (2 * self.grow)))))
        step = min(step, 2 * p.budget_step) if self.asked else step
        # …leaving the fresh session a turn of the role's cap: its conversation, the note in it, is what the next round
        # continues
        return min(step, max(1, max_turns - used - (1 if self.asked else 0))) if max_turns else step

    def read(self, rec: dict, turns: int) -> tuple[str, "_Session"]:
        """`continue`, `boundary` (ask for a checked point) or `close`, from a cut round's record — and the session as
        that round leaves it. The budget's line is never under twice the session's own opening (its first turn's
        context): each session does at least as much work as it costs to open, where a budget just over a reopen's size
        handed over every two turns with nothing done between (critic over 069e91b) — and one opened past the budget
        still works, handing over at twice its opening, the ceiling over it."""
        peak, top = rec["peak_context"], ceiling(rec.get("context_window"))
        grow = max(1.0, (peak - (self.peak if self.peak is not None and not self.fresh else 0)) / max(turns, 1))
        opening = peak if self.fresh and not rec.get("resumed") else self.opening
        soft = max(self.budget, 2 * (opening or 0)) if self.budget else None
        # …a REOPENED session at its ceiling on its first reading is past what a handover can help: the next reopen would
        # open as large, and closing it again looped until the clock (critic over 9f36023). It works, or fails, as it
        # would without one.
        beyond = self.beyond or (self.fresh and bool(self.note) and peak >= top)
        over = bool(soft and peak >= soft) and not beyond
        word = ("continue" if beyond else "close" if peak >= top or (over and self.asked)
                else "boundary" if over else "continue")
        line = top if over or not soft or soft >= top else soft
        return word, replace(self, fresh=False, asked=over, peak=peak, grow=grow, line=line, opening=opening,
                             beyond=beyond)

    def previous(self) -> str:
        """The note this session started from, for the one it writes to update (anchored, not rewritten)."""
        return PREVIOUS + self.note if self.note else ""


def _as_note(p, text: str) -> str | None:
    """The note a round at its checked point wrote, or None where it answered the task itself: whatever is not the
    role's own report (`p.reads_as_report`, the frame's schema) is the note — a note in a fence, after a preamble or
    without its mark is still one, and read as a report it was lost with the conversation (critic over 542a3c0). The
    mark is cut from its head. Without the frame's reader the mark alone tells them."""
    body = (text or "").strip()
    if p.reads_as_report is not None:
        if not body or p.reads_as_report(body):
            return None
    elif NOTE_MARK not in body.upper():
        return None
    lines = body.splitlines()
    at = next((i for i, x in enumerate(lines[:4]) if NOTE_MARK in x.upper()), None)
    return "\n".join(lines[at + 1:] if at is not None else lines).strip().strip("`").strip() or body


def _ended(p, sid: str, session, text: str) -> str:
    """The run's answer; a conversation the caller did not name is not left behind."""
    if session is None:
        p.forget(sid)
    return text


def _reopen(p, user: str, s: _Session, written, handovers: int, sid: str) -> tuple[str, _Session]:
    """The fresh session's opening — the packet, the note just written and the place's machine state — and the fresh
    session; the round that wrote the note says it handed over, and which.

    A NAMED LIMIT: under a budget below the task's working set a reopen re-reads what the last one carried and reaches
    the line again — a 20k budget on four 14k reads handed over nine times in a row (probed live, haiku 5.5), each
    handover counted on the ledger. Three rules made against it each broke a budget that pays (a line raised after the
    predecessor's peak compounded; "no lower than the predecessor" fired on steady work — three critics' simulations):
    the budget is the resource's setting, chosen by measurement on the task."""
    p.calls[-1]["handover"] = handovers
    p.forget(sid)
    state = (p.machine_state() or "") if p.machine_state else ""
    fresh = _Session(s.budget, (written or "").strip() or "(the session left no note)")
    return user + HANDOVER + fresh.note + (STATE + state if state else ""), fresh


def run(p, system: str, user: str, allowed_tools, cwd, timeout, max_turns, session) -> str:
    """A work session's `run_agent`: the run's answer, its rounds, closes and handovers booked on `p` as any call is. The
    role's own turn cap counts every turn of every session; reached, the run ends as a capped round does — its
    conversation kept for the next round where one is named. A lost conversation reopens on what the session opened on,
    never on the bare "continue" (`p.resume_fallback`)."""
    sid = session or f"budget-{uuid.uuid4().hex}"
    t0, used, handovers, s = time.monotonic(), 0, 0, _Session(p.context_budget)
    prompt = p.resume_fallback = user
    try:
        while True:
            left = _left(timeout, t0)
            # …past the role's cap no round starts (a cap of 0 turns reads as none on a provider) — save a reopened
            # session's first: the note and its opening are the system's, as the close is, and that conversation, the
            # note in it, is what the next round continues (critic over 069e91b)
            if (left is not None and left <= 0) or (max_turns and used >= max_turns and not (s.fresh and handovers)):
                return ""
            step, n = s.step(p, used, max_turns), len(p.calls)
            text = p.agent_round(system, prompt, allowed_tools, cwd, left, step, sid)
            rec = p.calls[-1] if len(p.calls) > n else {}
            turns = min(rec.get("turns") or step, step)     # a cut round reports its cap + 1
            used += turns
            cut = cut_at_turn_cap(rec)
            written = _as_note(p, text) if s.asked and not cut else None
            # …at the role's cap the round ends as a capped one — save one at its ceiling: that conversation could not be
            # continued, so it closes, the system's turns, and the fresh one is what the next round continues
            at_top = (rec.get("peak_context") or 0) >= ceiling(rec.get("context_window"))
            if written is None and (not cut or (max_turns and used >= max_turns and not at_top)):
                return _ended(p, sid, session, text)
            if written is None and rec.get("peak_context") is None:      # nothing to read: one round to its end
                log.warning("context ceiling and budget off for this run: the provider does not report its context")
                return _ended(p, sid, session, p.agent_round(system, CONTINUE, allowed_tools, cwd, _left(timeout, t0),
                                                             max_turns - used if max_turns else None, sid))
            if written is None:
                # …a round the SYSTEM stopped at its reading and continues is no session out of turns: the CLI's word
                # read as one on the page — 4 of 15 executor rounds of a run marked "out of turns" (the author, 2026-10-27)
                rec["ended"] = CONTINUED
                word, s = s.read(rec, turns)
                if word == "boundary" and max_turns and max_turns - used < 2:
                    return ""                               # no turns to reach a point: kept as a capped round is
                if word != "close":
                    prompt = BOUNDARY + s.previous() if word == "boundary" else CONTINUE
                    continue
                left = _left(timeout, t0)
                if left is not None and left < CLOSE_MIN_S:
                    return ""                               # no fresh session could continue: the clock has the node
                p.resume_fallback = None                    # a close whose conversation is lost writes a note, no work
                written = p.close_session(system, CLOSE + s.previous(), allowed_tools, cwd, left, sid)
                if (p.calls[-1].get("ended") if p.calls else None) in STOPS:
                    return ""                               # the project stops; the conversation waits for the lift
            handovers += 1
            prompt, s = _reopen(p, user, s, written, handovers, sid)
            p.resume_fallback = prompt
    finally:
        p.resume_fallback = None


#: what a hooked session's system prompt says before the hook speaks: a note arriving with a tool's result reads as the
#: tool's output, and a model told nothing of it ignored one as foreign («isn't in the file or from you», probed)
SAYS = "GFSO SYSTEM:"
NOTICE = (f"\n\nWhile you work, the system running this task may add a note after one of your tool calls, beginning "
          f"`{SAYS}`. It is the system's, not the tool's output: follow it.")


def hooked(p, system: str, user: str, allowed_tools, cwd, timeout, max_turns, session) -> str:
    """A work session's `run_agent` where the provider reads its context after each tool call (`handover_hook`): ONE
    process a session, its hook asking for a checked point past the budget's line and stopping the session at the
    ceiling (`handover_hook.decide`), the note then asked for by its conversation as `run`'s close is. Every reading
    `run` makes between rounds is made after a tool call instead — no process per round, no blind first step, no large
    read overshooting the line unseen."""
    sid = session or f"budget-{uuid.uuid4().hex}"
    t0, used, handovers, s = time.monotonic(), 0, 0, _Session(p.context_budget)
    prompt, reopened = user, False
    p.resume_fallback = user
    system += NOTICE if s.budget else ""
    try:
        while True:
            left = _left(timeout, t0)
            # …past the role's cap no round starts — save a reopened session's first: its note is the system's, and that
            # conversation, the note in it, is what the next run continues (`run`'s same rule)
            if (left is not None and left <= 0) or (max_turns and used >= max_turns and not reopened):
                return ""
            p.arm(sid, {"budget": s.budget, "ceiling": ceiling(p.window()), "reopen": bool(handovers),
                        "boundary": f"{SAYS} {BOUNDARY}{s.previous()}"}, cwd)
            n = len(p.calls)
            text = p.agent_round(system, prompt, allowed_tools, cwd, left,
                                 max(1, max_turns - used) if max_turns else None, sid)
            rec, reopened = (p.calls[-1] if len(p.calls) > n else {}), False
            used += rec.get("turns") or 0
            hook = rec.get("hook") or {}
            if p.last_tool_calls and not hook.get("read"):
                # …a session that called tools and the hook never read: no ceiling held it (an image without python3,
                # a CLI that runs no hooks) — the provider's next sessions read their context between rounds
                log.warning("the handover hook did not run in a session that called tools: back to rounds")
                p.handover_hook = False
            written = _as_note(p, text) if hook.get("asked") and not hook.get("stopped") else None
            if hook.get("stopped"):
                left = _left(timeout, t0)
                if left is not None and left < CLOSE_MIN_S:
                    return ""
                p.resume_fallback = None
                written = p.close_session(system, CLOSE + s.previous(), allowed_tools, cwd, left, sid)
                if (p.calls[-1].get("ended") if p.calls else None) in STOPS:
                    return ""
            elif written is None:
                return _ended(p, sid, session, text)
            handovers, reopened = handovers + 1, True
            prompt, s = _reopen(p, user, replace(s, peak=hook.get("peak")), written, handovers, sid)
            p.resume_fallback = prompt
    finally:
        p.resume_fallback = None
