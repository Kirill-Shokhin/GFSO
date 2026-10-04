"""The frontier: what the graph owes next, and to whom — the engine's answer to "what now?" (`next_step(s)`).

One reader over the engine's state, never a writer: every step it names is a move some party makes through the
engine's doors, and every wait it names is read off the graph and the log. It was ~1100 lines inside `Engine`, a
second concern in the class that applies the signals (sync audit 2026-10-04, D-F10)."""
from __future__ import annotations

from typing import Optional

from gfso.config import agent_id as _config_agent_id
from gfso.core.graph.model import root_of
from gfso.core.types import (Action, DoneReason, Mode, Signal, State, TERMINAL_STATES, Task, TaskId, Verdict, Wait,
                             settled_positive)
from .validation import _l0_holes, _l2_undischarged, hole_kind, l2_gate_on, observation_blocker

#: Actions whose signal is the ISSUER's to give (§11.2) — everything else is the executor's.
_ISSUER_ACTIONS = frozenset({Action.VALIDATE, Action.RESOLVE, Action.REVISE, Action.CHECK_PLAN})


class NodeSteps:
    """The move one node owes now, and its words: whose it is, which verb, what the directive says — read off the node,
    its children and its record. The frontier asks it per node; it walks nothing."""

    def __init__(self, engine):
        self.engine = engine

    def _fails_through_parts(self, t) -> dict:
        """{criterion of this whole: [its parts that FAILed on their current version]} — the criteria its FAIL through
        them names (Inv-3), empty where no part mapped to a criterion is in rework."""
        failing = {str(k.id) for k in self.engine.graph.get_active_children(t.id) if self.engine.in_rework(k)}
        out: dict = {}
        for m in t.criterion_mappings:
            if str(m.child_id) in failing:
                out.setdefault(m.criterion_name, []).append(str(m.child_id))
        return out

    def _plan_repair_before_signing(self, t, nm):
        """The step for a delivered node whose PASS is refused by rule — or None if none is.

        `pass_blocked_by` is the one owner of "why a PASS here is refused whoever signs it", and the
        VALIDATING branch — the only branch that ever advises a PASS — did not consult it. A parent
        whose children have all settled but whose own plan has since gone red (a covering child
        CANCELled, a criterion added) was told "signal PASS if every criterion holds" and had every
        PASS refused: `cannot PASS root: its own decomposition does not pass the Syntactic level NOW
        (§9.5)`. The repair is the step, exactly as it is for a re-delivery a plan cannot save.
        """
        # an observation ground is not a plan repair (`_observation_step`), and a verdict on the record is signed
        # before one; a split owed is the step whatever is recorded — observing the delivery first was paid for
        # and then refused, and after a FAIL the re-delivery is refused until the split (critic, 2026-09-28)
        blocked = self.engine.pass_blocked_by(t.id)
        if blocked is None or blocked.get("kind") in ("observed_fail", "unobserved") or (
                blocked.get("kind") != "split_owed" and self.engine.current_exec_verdict(t.id) is not None):
            return None
        return (1, t, Action.VALIDATE,
                f"REPAIR THE PLAN of '{t.id}' ({nm}) before signing anything: {blocked['why']} "
                f"A PASS here is refused by rule whoever signs it. {blocked['opens_with']}")

    def _step_for_a_delivered_node(self, t, nm, crits):
        """What is owed on a node whose delivery is waiting for a verdict — or None.

        The largest of `_step_for`'s seven answers, and the only one that ever advises a
        PASS: sign a verdict already on the record, repair a plan that refuses one, or validate
        a delivery nothing has validated yet. It sat inside the seven-way body and made that
        function answer more than one question at a time.
        """
        # …AND IF A PASS HERE IS REFUSED BY RULE, SAY THAT FIRST. `pass_blocked_by` is the one
        # owner of "why a PASS on this node would be refused whoever signs it", and this branch
        # — the only branch that ever advises a PASS — did not consult it. A parent whose
        # children have all settled but whose own plan has since gone red (a covering child
        # CANCELled, a criterion added) was told "signal PASS if every criterion holds" and had
        # every PASS refused: `cannot PASS root: its own decomposition does not pass the
        # Syntactic level NOW (§9.5)`. The repair is the step, exactly as it is for a
        # re-delivery a plan cannot save.
        # …BUT NOT AHEAD OF A VERDICT ALREADY ON THE RECORD. `pass_blocked_by` answers about a PASS,
        # and a FAIL is not gated by it — so this step, put first, replaced "advising a signal the
        # engine refuses" with something worse: it hid the FAIL the engine ACCEPTS behind a repair
        # the engine refuses. Measured: a root with a recorded FAIL and a cancelled coverer was told
        # to map the criterion (refused then — the child was DONE and a `covers` read as its revision), or to
        # edit the contract (refused then — `would_destroy_coverage`), while `signal FAIL` was accepted
        # and moved the node to REWORKING. The recorded verdict is the step whenever there is one.
        # …AND A WHOLE OVER A PART THAT FAILED HAS ITS VERDICT ALREADY: a whole is not attained while a part fails
        # (Thm 1). Listed as a wait for the part's rework, it waited in VALIDATING across that rework past T_validate
        # and escalated, its holder never told the move (critic, 2026-09-28, SEMI).
        if (through := self._fails_through_parts(t)):
            _parts = sorted({k for ks in through.values() for k in ks})
            return (1, t, Action.VALIDATE,
                    f"SIGN THE VERDICT on '{t.id}' ({nm}) — FAIL on {', '.join(through)}: its part(s) "
                    f"{', '.join(_parts)} failed their own criteria, and a whole is not attained while a part fails "
                    f"(Thm 1). `signal('{t.id}', 'FAIL', failed_criteria={list(through)})`; it is re-delivered "
                    f"once those parts have passed.")
        if (_repair := self._plan_repair_before_signing(t, nm)) is not None:
            return _repair
        # …AND WHAT THE OBSERVATION OF THIS DELIVERY ALLOWS, from the same predicate the PASS gate reads:
        # a record on file is not always one a PASS may stand on (the executor's self-check, a passer-by's
        # hand), and an appointed observer's FAIL stands whatever was recorded after it.
        _cur = self.engine.current_exec_verdict(t.id)
        if (_ob := observation_blocker(self.engine.graph, t, self.engine._audit)) is not None and (
                (_ob["kind"] == "observed_fail" and str((_cur or {}).get("verdict")) != Verdict.FAIL)
                or _ob["kind"] == "unobserved"):
            return (1, t, Action.VALIDATE,
                    (f"SIGN THE VERDICT on '{t.id}' ({nm}) — FAIL: " if _ob["kind"] == "observed_fail"
                     else f"OBSERVE THIS DELIVERY of '{t.id}' ({nm}) before any PASS: ")
                    + f"{_ob['why']}. {_ob['opens_with'][:1].upper()}{_ob['opens_with'][1:]}.")
        # On a SEAM, say what a PASS costs before it is refused. The directive read "signal
        # PASS if every criterion holds" to everyone, including the very executor whose PASS
        # the gate rejects (§10.3) — so a person following it literally walked into the
        # refusal, and one who happened to hold both roles walked into the belief that they
        # had signed something. The instrument is named here, where the reader already is.
        seam = self.engine.graph.is_public(t)
        if (_rec := self.engine.current_exec_verdict(t.id)) is not None:
            # THE VALIDATION IS DONE; ONLY THE SIGNATURE IS MISSING. The step still read "check
            # the deliverable against criteria …" after the validator had reported on THIS
            # delivery, so the reader either ran a second instrument over the same artifact
            # or waited for a report already on the record (measured on the human door
            # 2026-08-22). What is owed here is the signal, and the record is what it is
            # signed on — `get_verdict` reads it in full.
            _f = _rec.get("failed_criteria") or []
            cand = (1, t, Action.VALIDATE,
                    # …AND CALL IT WHAT IT IS. On an internal node the record is legitimately
                    # the executor's own self-check (§10.3) — and this sentence called that
                    # "an independent verdict … by agent", where `agent` was the executor who
                    # had just delivered it (agent door, 2026-09-02). The record says which kind
                    # of party produced it; the directive has to read the same field.
                    f"SIGN THE VERDICT on '{t.id}' ({nm}): "
                    + ("the executor's own self-check for THIS delivery is on the record "
                       "(§10.3 lets an internal node self-verify)"
                       if str(_rec.get("validator") or "") == str(t.assignee or "")
                       else "an independent verdict for THIS delivery is already on the record")
                    + (f" by {_rec['validator']}" if _rec.get("validator") else "")
                    + " — " + (f"{Verdict.FAIL} on {', '.join(map(str, _f))}" if _f
                                else str(Verdict.PASS))
                    + f". Read it with `get_verdict {t.id}`, then signal "
                    + (f"{Verdict.FAIL} with those criteria." if _f else f"{Verdict.PASS}.")
                    + " Validating it again would validate the same artifact twice.")
            return cand
        # …and the ISSUER's own share of the same fact: a criterion that has failed round
        # after round is a criterion to re-read, not only a delivery to validate. The engine
        # knows the count; whoever holds the verdict was never told it.
        _stuck_note = (f" NOTE: {', '.join(_st)} has failed {self.engine.CONTRACT_SUSPECT_ROUNDS} "
                       f"rounds running here. If the criterion cannot be met as written, the "
                       f"repair is the CONTRACT — `edit_criteria('{t.id}', …)` (a revision, "
                       f"Inv-1) — not another FAIL."
                       if (_st := self.engine.stuck_on(t.id)) else "")
        # …AND WHETHER AN INSTRUMENT HAS ALREADY TRIED AND COME BACK WITH NOTHING. The engine
        # stores every refused report on the node, with a count, and tells the CALLER of
        # `validate_result` what it means — but the caller of a hand-driven validation is not
        # the person who comes back to the graph later, and the step they read said "VALIDATE
        # this" as though nothing had happened. Three doors measured the consequence as the same
        # symptom: a node sitting in VALIDATING for twelve minutes, forty-five minutes, or
        # "forever", with the frontier cheerfully naming a step that was never going to
        # complete (wave 23, 2026-09-03). The dispatcher's own path has said this since August
        # (`_validation_parked`); the hand-driven one had the fact and no reader.
        _bot = self._bottom_attempts(t)
        _bot_note = (f" NOTE: {_bot} instrument report(s) on THIS delivery produced no verdict "
                     f"(⊥ is not a pass, §2.3) — `get_verdict {t.id}` shows what they did "
                     f"manage to check. "
                     + ("Re-running the same tier usually returns the same gap: try a stronger "
                        "model, or record your own verdict with what you observed."
                        if _bot < 2 else
                        "Do NOT run the same tier again: repeated ⊥ on one node is about the "
                        "CONTRACT, not the run — narrow what this node promises "
                        f"(`edit_criteria('{t.id}', …)`), escalate the model, or record your "
                        "own verdict.") if _bot else "")
        cand = (1, t, Action.VALIDATE,
                f"VALIDATE '{t.id}' ({nm}): check the deliverable against criteria {crits}; signal "
                f"PASS if every criterion holds, else FAIL with the failed criteria."
                + _bot_note
                + _stuck_note
                + (f" This node is a SEAM, so its own executor ({t.assignee}) cannot sign a "
                   f"PASS until an INDEPENDENT verdict is on the record for this delivery — "
                   f"`validate_result` (a fresh read-only agent that RUNS the criteria) or "
                   f"`record_verdict` by another person. With one recorded, the signal is "
                   f"accepted from them as usual." if seam else ""))
        return cand

    def _held_step_verb(self, t, kids) -> str:
        """What the mode's refusal on a node the user-agent names asks for: cover the split, split, or hand over."""
        if not self.engine.held_by_the_user_agent(self.engine.depth_of(t.id)):
            return "HAND OVER"                  # below the boundary, whatever it has under it (critic round 19)
        return "COVER THE PLAN of" if kids else "SPLIT"

    def _held_reaggregate_step(self, t, nm, failed) -> Optional[tuple]:
        """IN SEMI THE HOLDER DOES NOT FIX THE WORK BY HAND. A held node in rework whose children passed (else the
        mode's rule gave no step) answers its FAIL through the split — a repair child — and re-aggregates;
        "Fix exactly that" told it to write the fix itself (critic round 17). None outside that case."""
        if not (self.engine.mode_kind() == Mode.SEMI and str(t.assignee) == str(_config_agent_id())
                and self.engine.held_by_the_user_agent(self.engine.depth_of(t.id))):
            return None
        return (2, t, Action.DELIVER,
                f"RE-AGGREGATE '{t.id}' ({nm}): the validator FAILED it on "
                f"{', '.join(map(str, failed)) or 'its criteria'}. In semi the fix is not yours to write: if a "
                f"child below now carries it and passed, integrate and DELIVER again; if none does, add or "
                f"revise the child that will (`revise`, `auto_decompose` on it).")

    def _step_for(self, t, kids, crits, nm, cands, held, _deps_ready, _passed):
        """What the holder of this node is asked to do next — one answer per state.

        Sign a verdict already on the record · validate one that is not · repair a plan a
        re-delivery cannot save · fix what failed · take the node · aggregate · confirm a
        cancellation. Seven answers to one question, which is not the question the plan gate
        answers, and they shared a body with it. None = nothing to offer for this node."""
        if not kids and t.state in (State.OFFERED, State.EXECUTING, State.REWORKING) and (
                owed := self.engine.split_owed(t.id)):
            # ITS SPLIT IS OWED — its DELIVER as a leaf is refused and no session is spent on it, so the step is the
            # split; said as such, where the parked directive blamed a crash and offered moves that bought two more
            # refused sessions each (critic, 2026-09-28)
            return (2, t, Action.REVISE,
                    f"ITS SPLIT IS OWED on '{t.id}' ({nm}): {owed['why']}. It is not delivered as a leaf and no "
                    f"executor session is started on it. The step: {owed['opens_with']}.")
        if self.engine.parking.is_execution_parked(t):
            # ITS EXECUTOR STOPPED — the step is the ISSUER's, not a wait on the executor: the door
            # otherwise showed "NOT YOURS … in hand, not stuck" and a waiting issuer never returned.
            cand = (2, t, Action.REVISE,
                    f"ITS EXECUTOR STOPPED WITHOUT A SIGNAL on '{t.id}' ({nm}), twice: each run ended "
                    f"with no readable report (a run cut at its turn cap, a crash, a malformed answer), "
                    f"so nothing was signalled and nothing will be — only the deadline would move it. "
                    f"Its work so far is on disk. The moves are YOURS as its issuer: `revise` it (a new "
                    f"packet version starts a fresh run over what is already there — narrow or split "
                    f"the contract if one run cannot carry it), `reassign` it, or CANCEL it.")
        elif t.state == State.VALIDATING:
            return self._step_for_a_delivered_node(t, nm, crits)
        elif t.state in (State.OFFERED, State.EXECUTING, State.REWORKING) and                 (_held := self.engine.held_node_refusal(t.id, Signal.ACCEPT if t.state == State.OFFERED
                                                 else Signal.DELIVER)):
            # THE STEP MUST NOT ASK FOR A MOVE THE ENGINE REFUSES: in SEMI a node the user-agent holds is
            # taken and handed in only with a split, and handed in only once that split has worked — so
            # "TAKE" / "EXECUTE" / "FIX AND RE-DELIVER" here cost a refused call and, worse, tell the holder
            # to do the work by hand (critic rounds 8, 9, 16). With children the step is on them; without,
            # it is the split, the holder's own act (§11.5).
            return (None if kids and not all(_passed(k) for k in kids) else
                    (2, t, Action.REVISE, f"{self._held_step_verb(t, kids)} '{t.id}' ({nm}) — {_held}"))
        elif self.engine.in_rework(t) and (_refusal := self.engine._redelivery_refusal(t)):
            # THE DIRECTIVE MUST NOT ASK FOR A DELIVERY THE GATE WILL REFUSE. When the failed
            # criteria are covered by children nobody touched, contact refuted the DECOMPOSITION
            # and a re-DELIVER is rejected on arrival (§15.4 q_D, FM-1.d/f) — but the step still
            # read "fix exactly what failed, then DELIVER again". Measured 2026-08-20 on a
            # measurement run: three full rework rounds against that wall, ~13 minutes and two
            # executor calls each, and the run ended `redelivery_refused` with the graph exactly
            # where it started. The engine already knows the repair; this is it, said BEFORE the
            # work rather than after.
            cand = (2, t, Action.REVISE,
                    f"REPAIR THE PLAN of '{t.id}' ({nm}) — a re-DELIVER here is REFUSED, and "
                    f"redoing the aggregate cannot help: {_refusal}")
        elif self.engine.in_rework(t):
            if not _deps_ready(t.id):
                return None  # same dep order as EXECUTING: a rework against an input that does not
                          # exist yet can only re-BLOCK (the directive used to send it anyway)
            # …AND THE OTHER ROUTE, WHEN IT IS THE CONTRACT THAT CANNOT HOLD. The directive said
            # "fix exactly what failed, then DELIVER again" and nothing else, so an executor
            # facing an unsatisfiable criterion obeyed it five times over (measured 2026-08-22).
            # The channel for "this criterion is wrong" is CHALLENGE, admitted from REWORKING
            # since v4.1 (§12.4) precisely because that is where such a defect is met — and it
            # carries the dispute's own two closures, which BLOCK does not.
            _stuck = self.engine.stuck_on(t.id)
            # …AND NAME WHAT FAILED, or stop claiming a failure. "Fix exactly what failed" is
            # unfollowable when nothing on the record says what did — and a wave read exactly that
            # on a node whose reports carried an empty `failed_criteria` (agent door, 2026-09-02).
            # Inv-3 makes a FAIL name its criteria, so a rework with none named is a state to
            # explain, not a verdict to relay.
            _failed = list((self.engine.current_exec_verdict(t.id) or {}).get("failed_criteria") or ())
            cand = (kids and self._held_reaggregate_step(t, nm, _failed)) or (2, t, Action.FIX,
                    (f"FIX AND RE-DELIVER '{t.id}' ({nm}): the validator FAILED it on "
                     f"{', '.join(map(str, _failed))}. Fix exactly that, then DELIVER again."
                     if _failed else
                     f"RE-DELIVER '{t.id}' ({nm}): it is in rework, and no current verdict names "
                     f"a failed criterion — read `get_verdict {t.id}` before changing anything, "
                     f"because there may be nothing here to fix.")
                    + f"{self._rework_feedback(t.id)}"
                    + (f" | {', '.join(_stuck)} has now failed {self.engine.CONTRACT_SUSPECT_ROUNDS} "
                       f"rounds running. If it cannot be met AS WRITTEN, do not deliver against "
                       f"it a fourth time — send "
                       f"CHALLENGE(reason=\"<why the criterion cannot hold>\"), naming that "
                       f"criterion: the issuer answers it either by ACCEPT_CHALLENGE, which "
                       f"changes the contract and returns this node to OFFERED for your consent "
                       f"(Inv-1), or by REJECT_CHALLENGE with his justification. BLOCK is for a "
                       f"blocker outside the contract; it has neither of those closures."
                       if _stuck else ""))
        elif t.state == State.EXECUTING and not kids:
            if not _deps_ready(t.id):
                return None  # a consumer waits until its producers PASS — do them first (dep order)
            cand = (3, t, Action.EXECUTE,
                    f"EXECUTE leaf '{t.id}' ({nm}): do the actual work so criteria {crits} hold. Then "
                    f"BEFORE you DELIVER, self-check by RUNNING: for each criterion write a tiny check, "
                    f"run it, read the ACTUAL output, and signal from what you OBSERVED — not from "
                    f"'I implemented it' (an optimistic self-pass the root later fails drops q_D). "
                    f"DELIVER with, per criterion, the check you ran and what it printed.")
        elif t.state == State.OFFERED and kids:
            # a re-authored parent dropped back to OFFERED — re-ACCEPT it BEFORE driving its subtree, so the
            # graph doesn't finish all children while the parent still shows 'accept' (obs: odd ordering).
            cand = (0, t, Action.ACCEPT,
                    f"RE-ACCEPT '{t.id}' ({nm}): it was re-authored → signal ACCEPT to put it back to work "
                    f"(its existing subtree is retained). Then its children proceed.")
        elif t.state == State.OFFERED:
            if not _deps_ready(t.id):
                return None  # a leaf whose producers have not passed is not takeable yet — the
                          # frontier used to hand it out anyway, and whoever took it discovered
                          # the missing input by BLOCKing on it. (The re-ACCEPT of a PARENT above
                          # is deliberately not gated: consent to resume is what lets its subtree
                          # run at all.)
            if self.engine._validate and (_shut := self.engine.execution_blocked_by(t.id)) is not None:
                # THE FRONTIER MUST NOT OFFER WHAT THE ENGINE REFUSES. This node's ACCEPT is
                # gated on its PARENT's plan being checked (§11.5), and the step above says so —
                # but the child was still listed as takeable, `mine: true`, with a directive to
                # signal ACCEPT. Whoever obeyed spent the call to be told no (measured on the MCP
                # door 2026-08-21). The parent's plan step is the real one; this reappears the
                # moment it is discharged.
                held.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                                 kind="plan",
                                 waits_on=(_shut.get("waits_on") or f"the plan of '{_shut['parent_id']}'",),
                                 why=_shut["why"], opens_with=_shut["opens_with"]).as_dict())
                return None
            cand = (4, t, Action.ACCEPT,
                    f"TAKE '{t.id}' ({nm}): signal ACCEPT (or CHALLENGE if its spec is wrong). Then "
                    f"decide by the criteria {crits}: DECOMPOSE it into subtasks if that fits the goal "
                    f"(their number is YOUR call — then review_decomposition checks the split for "
                    f"causal gaps), or execute it directly as a leaf.")
        elif t.state == State.BLOCKED:
            # …AND THE MOVES NAMED HERE ARE THE OWNER'S OWN. BLOCKED's owner is the ISSUER (Inv-8),
            # and this line said only "clear the blocker" — an act of another executor and another
            # issuer, which §12.16's conformance clause (ii) excludes as a lift ("never only by the
            # counterparty"). The refusal inside `RESOLVE_BLOCK` was repaired first and is read only
            # AFTER someone has sent the signal and been told no; this is the text a driving agent
            # reads on every `next_steps` loop, so the stale sentence sat at the door that matters.
            # Found by an outside review of that very repair (2026-09-23) — a rule fixed at one door
            # and not the next, which is this repository's own recurring class.
            _bl = sorted({str(e.from_id) for e in self.engine.graph.dep_edges()
                          if str(e.to_id) == str(t.id)
                          and not settled_positive(self.engine.graph.get_task(e.from_id))})
            cand = (5, t, Action.RESOLVE,
                    f"'{t.id}' ({nm}) is BLOCKED"
                    + (f" on {', '.join(_bl)}" if _bl else "")
                    + ". It is YOURS to move (Inv-8: BLOCKED's owner is the issuer). If the "
                      "blocker is genuinely gone: RESOLVE_BLOCK. If you worked around it: "
                      "RESOLVE_BLOCK(external=true). If the edge was misattributed: RESOLVE_BLOCK "
                      "with a corrected `blocker_task_ids`. If the contract no longer needs that "
                      "input: `remove_dependency` and then revise it. If the goal is off: CANCEL. "
                      "Otherwise this is an honest wait — the state is bounded and hands you the "
                      "decision at ESCALATED."
                    + (f" But no wait ends this one: {_order} — answer the block (refute what it names "
                       f"with RESOLVE_BLOCK external=true, re-issue it, or CANCEL), or reshape the split." if (
                        _order := self.engine.order_refuted_by(t.id)) else ""))
        elif t.state == State.CHALLENGED:
            # The dispute is the ISSUER's to close (Inv-8, §12.13), and it has exactly two closures.
            # Before v4.1 this state was reachable only before consent, so the frontier never listed
            # it and a post-consent challenge would now stop the subtree with nobody told whose move
            # it was — the ownerless gap this whole revision exists against, one state over.
            cand = (2, t, Action.RESOLVE,
                    f"'{t.id}' ({nm}) is CHALLENGED — its executor disputes the contract: "
                    f"\"{(self.engine.challenge_reason(t.id) or '')[:400]}\". This is YOURS and nothing "
                    f"moves until you close it: ACCEPT_CHALLENGE with the new spec if the dispute is "
                    f"right (the node returns to OFFERED and its executor consents afresh), or "
                    f"REJECT_CHALLENGE with the justification if the contract stands."
                    # …AND AT AN AUTO ROOT, A RULING ON A FINDING IS THE USER'S ALONE: the system makes no move on it
                    + (f" | THE USER'S QUESTION: it asks to rule {', '.join(_asked)} outside the user's goal, and "
                       f"under AUTO the system makes no move on it — ask the user, and send their answer: "
                       f"ACCEPT_CHALLENGE with `retire_findings` naming what they rule out, or REJECT_CHALLENGE "
                       f"with why the goal asks for it. Unanswered, the clock escalates it."
                       if (_asked := self.engine.users_dispute(t.id)) else ""))
        elif t.state == State.EXECUTING and kids and all(_passed(k) for k in kids):
            cand = self._aggregate_or_repair(t, nm, crits)
        elif t.state == State.CANCELLING:
            # settlement of the cancellation handshake (§12.6) — never preempts real work (lowest priority)
            cand = (7, t, Action.CONFIRM_CANCEL,
                    f"CONFIRM cancellation of '{t.id}' ({nm}): signal CONFIRM_CANCEL, reporting the in-flight "
                    f"state at cancellation (what was done/undone) via `in_flight`.")
        else:
            return None  # EXECUTING with unfinished children, terminal, or IDLE → its frontier is elsewhere

        return cand

    def _plan_gate_step(self, t, kids, crits, nm, cands, held, _passed) -> bool:
        """Whether this node's PLAN, not its own state, decides what happens here (§11.5).

        A parent whose decomposition has an open Syntactic hole or an undischarged Level-2
        finding gates its children's ACCEPT, so the repair is the step ITSELF; a check already
        in flight is not a step at all. Appends to `cands`/`held` exactly as the frontier would
        and answers whether the node is accounted for — the frontier asks nothing else of it.
        """
        # A plan whose causal check is not discharged is the actionable step ITSELF, ahead of the
        # work it gates (§11.5): the engine will refuse those children's ACCEPT, so an agent driving
        # the frontier must be TOLD to review — a gate that only refuses is a wall to walk into.
        # Ordered after validate/rework (finishing delivered work is never blocked by a plan check)
        # and before execute/accept (which it gates). Only while it still gates something: some
        # active child sitting in OFFERED, waiting to start.
        # THE PLAN STEP IS ABOUT THE PLAN, NOT ABOUT WHERE THE PARENT STANDS. This asked for
        # EXECUTING, and a parent that has DELIVERED sits in VALIDATING — so a repair made from
        # REWORKING (revise the plan, re-open the children, re-deliver) landed in exactly the
        # state where no step existed at all: the children were held by the gate, the parent's
        # own validation is skipped while they are unsettled, and the frontier went empty.
        # Measured on the E3 arm 2026-08-21: 51 minutes of a live run with nothing to do and
        # nothing said. Any non-terminal parent whose children wait on its plan gets the step.
        # …AND A NODE WAITING FOR ITS ISSUER IS NOT ASKING FOR ITS PLAN TO BE CHECKED. An ESCALATED parent
        # was told to `review_decomposition`, an act its state does not admit at all (CANCEL and
        # ASSIGN are), while the decision that would actually move it went unnamed — and precisely
        # when the node HAS a subtree, which is the delegated case this whole rule is for. A door
        # may not name an act the FSM refuses; the first thing here is whose move it is.
        if t.state == State.ESCALATED:
            cands.append((0.5, t, Action.REVISE,
                          f"DECIDE on '{t.id}' ({nm}): {self.engine.issuer_moves_on(t.id)}"))
            return True
        # …where the plan gate HOLDS a child — the decomposer's own, or one the system would start (C9-L2): a child
        # another party takes may ACCEPT, so a step "its children cannot start" there says more than the gate (r13)
        _gating = (kids and self.engine._validate and not _passed(t)
                   and any(k.state == State.OFFERED and self.engine.execution_blocked_by(k.id) is not None
                           for k in kids))
        if kids and not _passed(t) and (_holes := _l0_holes(self.engine.graph, t)):
            # A HOLE OPENED AFTER THE ADMISSION — a revision of the contract, a child cancelled — is a flag on the plan
            # for its decomposer (§12.10), not a hold on work already issued: the Syntactic level gates the admission,
            # where he can lift it (corner 9). The repair is named. With the Level-2 gate on, his OWN children still
            # wait for a current review, which runs once these are repaired (C9-L2); another executor's child goes on.
            cands.append((2.5, t, Action.CHECK_PLAN,
                          f"REPAIR THE PLAN of '{t.id}' ({nm}): its decomposition no longer passes the Syntactic "
                          f"level (§9.5) — " + "; ".join(f"{h.check_name}: {h.details}" for h in _holes)
                          + f". `list_holes` shows them across the graph."))
        if _gating and l2_gate_on() and self.engine.claims.review_in_flight(t.id):
            # A CHECK ALREADY RUNNING IS NOT A STEP. The frontier kept saying "call
            # review_decomposition" while one was mid-flight — a duplicate paid round over a
            # plan that had not changed, and the other in-flight surface (`validate_result`)
            # already knew better.
            held.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                             kind="plan", waits_on=("the Level-2 check already running on this "
                                                    "version of the plan",),
                             why=("its causal check is in flight — a second one would validate the "
                                  "same plan twice and cost twice"),
                             opens_with="nothing: its verdict arrives by itself").as_dict())
            return True
        if _gating and l2_gate_on() and not _l0_holes(self.engine.graph, t):
            open_l2 = _l2_undischarged(self.engine.graph, t)
            if open_l2 is None:
                cands.append((2.5, t, Action.CHECK_PLAN,
                              f"CHECK THE PLAN of '{t.id}' ({nm}): its children cannot start until the "
                              f"decomposition has a current Level-2 verdict — call "
                              f"review_decomposition('{t.id}') (do the mapped children's criteria "
                              f"causally carry {crits}?)."))
                return True
            if open_l2:
                _own = [g for g in open_l2 if str(g).startswith("undecided: ")]
                cands.append((2.5, t, Action.CHECK_PLAN,
                              # …AS A COUNT AND A LIST, not as a paragraph of interpolated
                              # findings. Eleven were pasted into one wall of text and a reader
                              # counted eleven problems where there were five — the checker's own
                              # fold had already marked some as one obligation in several
                              # wordings (agent door, 2026-09-02).
                              f"CLOSE THE PLAN GAPS of '{t.id}' ({nm}): the Level-2 review named "
                              f"{len(open_l2)} finding(s) not carried by the mapped children — "
                              + "; ".join(f"({i + 1}) {g}" for i, g in enumerate(open_l2))
                              + f". One reason can answer several: `dispute_finding('{t.id}', "
                                f"[<keys>], '<why>')`. Fix the plan "
                              f"(edit_criteria / map_criterion / add a child) and re-run "
                              f"review_decomposition('{t.id}'), or record why the finding is wrong "
                              f"(dispute_finding). Reasons: get_review('{t.id}')."
                              + (f" NOTE — the `undecided` findings ({len(_own)}) are about "
                                 f"'{t.id}'s OWN criteria, not its children's: a criterion added "
                                 f"to a CHILD does not close one, and the finding comes back word "
                                 f"for word. `edit_criteria('{t.id}', …)` is what closes them."
                                 if _own else "")))
                return True
        return False

    def _bottom_attempts(self, task) -> int:
        """How many instrument reports on THIS delivery were refused as ⊥, or 0.

        One reader for a fact three surfaces need: the frontier's directive, `get_verdict`, and
        whoever comes back to a node that has been sitting in VALIDATING. Scoped to the current
        generation, because a count carried across a rework is advice about a delivery nobody made.
        """
        return int((self.engine.refused_report_for_this_delivery(task.id) or {}).get("refusals", 0))

    def _aggregate_or_repair(self, t, nm: str, crits) -> tuple:
        """The step for a parent whose children have all passed: integrate them, or repair the plan.

        The second half exists because the two answers were given at once. When contact refuted the
        DECOMPOSITION — the parent's criteria failed while the children covering them are untouched
        since that FAIL — a re-DELIVER is refused on arrival, and this branch was telling the
        executor to aggregate and deliver anyway. Measured on a live run (2026-09-06,
        `http2_protocol`): the refusal and the "AGGREGATE … DELIVER" directive were emitted in the
        same second, the executor obeyed the directive, was refused twice, and the run ended with
        the root still EXECUTING after 93 minutes. The REWORKING branch had learnt this a fortnight
        earlier; the rule has one owner and both branches ask it.
        """
        if (wall := self.engine._redelivery_refusal(t)) is not None:
            return (6, t, Action.REVISE,
                    f"REPAIR THE PLAN of '{t.id}' ({nm}) — do NOT re-deliver it: {wall}")
        left = self.engine.joins.unjoined_parts(t)
        return (6, t, Action.DELIVER,
                f"AGGREGATE '{t.id}' ({nm}): all its children PASSED — integrate them. "
                + (f"These did NOT merge where it works — merge each and resolve, that is this whole's work: "
                   + "; ".join(f"'{k}': {why}" for k, why in left) + ". " if left else "")
                + f"Before you DELIVER, self-check the WHOLE by running: each parent criterion {crits} must hold "
                f"over the REAL integrated result (not mocks, not the children's word for it). "
                f"Signal from what the run actually shows.")

    def _rework_feedback(self, task_id: TaskId) -> str:
        """The validator's failure detail for the current REWORKING, short, for a directive (`rework_findings`)."""
        lines = []
        for c, ev, _ in self.engine.rework_findings(task_id):
            ev = ev.replace("\n", " ")
            # …CUT AT A WORD, AND SAID SO. This sliced at 300 characters mid-token — a directive
            # ending `On column name = ['Al` — so a reader could not tell a truncation from a
            # garbled record, and the rest was reachable only through a verb nobody named it
            # (measured on the agent door 2026-08-22).
            if ev and ev != "passed":
                _short = (ev if len(ev) <= 300 else ev[:300].rsplit(" ", 1)[0]
                          + f"… (the rest: `get_verdict('{task_id}')`)")
                lines.append(f"\n  - {c}: {_short}")
            else:
                lines.append(f"\n  - {c}")
        return " Failed:" + "".join(lines) if lines else ""

    def _step_out(self, t: Task, action: str, directive: str) -> dict:
        # Surface unmet checks, split by what the engine actually does with them. The Syntactic level gates the
        # ADMISSION (§11.5); one met after it — a revision, a child cancelled — is a flag on the decomposer's plan that
        # holds no issued work (§12.10), his to repair by a re-admission. CHECK-3 past the admission that
        # set the deadlines is a FLAG for the consumer's issuer (§12.10) — this node's holder, the issuer of the
        # children its checks read — and says so with his two moves. What stays advisory is what the canon puts on
        # no level: the anti-mock CHECK-1c, an engineering addition with no canon row (see the gate's own note).
        allc = [c for c in self.engine.get_checks(t.id) if not c.passed and not c.skipped]
        unmet, flags, advisory = ([f"{c.check_name}: {c.details}" for c in allc if hole_kind(c.check_name) == k]
                                  for k in ("gate", "flag", "advisory"))
        if str(t.id) in self.engine.parking.parked_validations():
            directive += (" | AUTOMATIC VALIDATION GAVE UP here: two validator reports carried no "
                          "verdict, so no automatic verdict is coming, and when VALIDATING's own bound "
                          "passes the delivery is handed to you in ESCALATED unvalidated (§2.3: ⊥ is not "
                          "pass; §16.14). Act before that: run `validate_result` "
                          "yourself, or record a verdict and sign as the issuer."
                          + (" What the validator DID observe before it gave up is on the record: "
                             "`get_verdict` shows it under `refused_report` — evidence, not a "
                             "verdict." if self.engine.rejected_report(t.id) else ""))
        if (_why := self.engine.parking.contested_reason(t.id)):
            directive += (f" | ITS EXECUTOR DISPUTES THE CONTRACT and could not say so in a signal "
                          f"(the state does not admit CHALLENGE — §12.4 admits it from OFFERED and, "
                          f"after consent, from EXECUTING and REWORKING): "
                          f"\"{_why}\". This is YOURS — nothing will move until you settle it. "
                          f"`revise` the node if the dispute is right (that returns it to OFFERED, "
                          f"where its executor takes it again under the new contract), or "
                          f"`reassign` it if the contract stands and this executor cannot do it. "
                          f"Re-running the same executor under the same contract reproduces the "
                          f"dispute and pays for it.")
        if unmet:
            directive += (f" | PLAN HOLES since its admission (§12.10 — a flag, no refusal of the children's "
                          f"moves): {unmet} — the decomposer repairs them by re-admitting the split (`decompose` with the "
                          f"new or changed children and their `covers`, `accepted_risks` and `drops`; a child named "
                          f"unchanged keeps working)"
                          + ("; until then no Level-2 review runs, and children the decomposer executes himself "
                             "wait for one" if l2_gate_on() else ""))
        if flags:
            directive += (f" | DEADLINE FLAG for the consumer's issuer (§12.10): {flags} — re-ASSIGN the consumer "
                          f"with a deadline after its producer's, or let it run on its own; nothing is refused")
        if advisory:
            directive += f" | advisory (optional): {advisory}"
        # …AND WHO THE SIGNAL WOULD BE SIGNED BY. A directive names the exact next command — "signal
        # ACCEPT to put it back to work" — and on a door where `source` is required that command is
        # incomplete: the caller sent it, got "signal needs source", and had to go read the help
        # (CLI door, 2026-09-02). The engine knows whose move it is; the step says so, and a door
        # that takes the signer as an argument can copy it.
        return {"complete": False, "task_id": str(t.id), "name": t.spec.name or str(t.id),
                "state": t.state.name, "action": action, "assignee": t.assignee, "unmet_checks": unmet,
                "signed_by": str(self.engine.graph.issuer_of(t.id)) if action in _ISSUER_ACTIONS else str(t.assignee or ""),
                # ALL of them, seams included: a `dep__` criterion is a criterion of this node, V
                # is the conjunction over the whole contract (§2.3), and `record_verdict` enforces
                # that — so a step that lists fewer is a step whose instruction cannot be followed.
                "criteria": [c.name for c in t.spec.criteria], "directive": directive}


class Frontier:
    """The walk over the graph: every node that owes a move, in order, and — when none does — why nothing is open, how
    the root closed, or what holds it (`next_step(s)`)."""

    def __init__(self, engine):
        self.engine = engine
        self.steps = NodeSteps(engine)
        self._held_by_plan: list = []     # the last walk's plan-gated nodes (not steps, not silence)

    def _never_passes(self, task_id) -> list:
        """The node's ACTIVE children that are terminal and did not settle positive.

        The one predicate for "this child will never satisfy its parent's AND (Thm 1)", because
        two guards spelled it two ways and BOTH were wrong at the edges. They asked
        `not passed(k) and k.state in TERMINAL_STATES` over `get_children`:

        * `passed` refuses `AUTO_PASS`, and the canon counts the timeout close AS acceptance
          (§16.14) — the PASS gate itself uses `settled_positive`. So a child accepted
          by the clock was read as "settled WITHOUT passing", and the frontier told the operator the
          run could never close and prescribed FAIL + re-decompose over a node whose very next PASS
          the engine accepts. A destructive instruction, minted by the guard that exists to prevent
          a silent stall.
        * `get_children` includes ABANDONED tombstones, which §11.5 keeps as provenance and which
          have LEFT the decomposition — its sibling guard reads `get_active_children` and does not
          see them. One cancelled child therefore turned a live `validate` step into "stuck, FAIL
          the parent" one second later, while an independent verdict was mid-flight.
        """
        return [k for k in self.engine.graph.get_active_children(task_id)
                if not settled_positive(k) and k.state in TERMINAL_STATES]

    def _nothing_to_take(self, tasks, deps, _deps_ready, _passed) -> dict:
        """The answer when no node is takeable: working, blocked by dep order, or stuck.

        Three different facts share one silence — an instrument is running, a producer has
        not passed, or a settled-negative node has stopped the graph — and telling them
        apart is the whole value of this branch. It lived inside `_frontier`, which made
        that function answer two unrelated questions in ninety statements."""
        # NAME WHAT IS IN THE WAY. "Inspect node states" is true and useless: the caller is
        # looping `next_steps` under an instruction that says loop until complete, and the one
        # thing it needs — which node made completion impossible — is the thing it was not
        # told. Measured live (2026-08-20): two leaves escalated under a root, the frontier
        # returned no steps, and the driving agent tried four recovery verbs against a node it
        # had to find by reading the raw graph. A settled-negative node is exactly where the
        # canon sends the issuer (§12.5: exhausting the bounded FAIL↔REWORKING loop IS the
        # escalation trigger, and ESCALATED means "this needs attention"), so the frontier says
        # so by name rather than making the reader look.
        # NOTHING TO TAKE IS NOT THE SAME AS STUCK. A node being validated, or an executor
        # working, is the graph doing exactly what it should — and this branch called it a
        # block, told the reader the dependency order was at fault, and prescribed
        # `remove_dependency` on a correct edge. Measured on BOTH doors 2026-08-22: four
        # occurrences in one run with a validator mid-flight (`list_holes` empty, producers
        # DONE), and ten minutes of polling on the other while the verdict was already on the
        # record. What is running is a fact the engine holds; it is said here first.
        # A WAIT WHOSE OBJECT HAS ALREADY SETTLED WITHOUT PASSING IS NOT "THE GRAPH WORKING".
        # A delivered parent counts as in-flight below — correctly, its verdict normally arrives by
        # itself — but when one of its children is ESCALATED or ABANDONED, the AND over the children
        # (Thm 1) can never be satisfied and that verdict will never come. Answered as "poll again
        # in a minute", this is a run that polls for ever: measured on a root delivered over one
        # ESCALATED child and one DONE one, where the only move — the issuer's own FAIL — was named
        # nowhere. Asked BEFORE the in-flight branch, because that branch is what hid it.
        _dead_waits = []
        for t in tasks:
            if t.state != State.VALIDATING:
                continue
            _gone = self._never_passes(t.id)
            if _gone:
                _dead_waits.append(
                    f"'{t.id}' is delivered and waits on "
                    + ", ".join(f"'{k.id}' ({k.state.name})" for k in _gone)
                    + " — settled WITHOUT passing")
            # …and a child in ESCALATED is NOT that case, though it stops the parent just as hard.
            # It is not settled: it is waiting for its issuer, and saying "settled without passing"
            # there prescribed FAIL-and-re-decompose over a node one revision away from running.
            for k in self.engine.graph.get_active_children(t.id):
                if k.state == State.ESCALATED:
                    _dead_waits.append(
                        f"'{t.id}' is delivered and waits on '{k.id}', which is ESCALATED — "
                        + self.engine.issuer_moves_on(k.id))
        if _dead_waits:
            return {"complete": False, "stuck": True, "steps": [],
                    "directive": (
                        "; ".join(_dead_waits)
                        + ". The AND over a node's children (Thm 1) can never be satisfied while "
                          "one of them is settled and not passed, so no verdict will arrive here "
                          "on its own — this is not a wait that ends. Either FAIL the delivered "
                          "node and re-decompose around the hole, or REOPEN the settled child if "
                          "it still has reopens left (§12.14).")}
        # A STRANDED NODE IS A FACT NO RUNNING WORK CAN CHANGE, so it is asked BEFORE what is in
        # flight — the in-flight branch was what hid it. That branch's own test is `state in
        # (EXECUTING, REWORKING) and the roster calls the assignee an executor`, which is a property
        # of Del rather than of anything actually running: a parent merely ASSIGNED to a registered
        # executor made every settled-negative node in the graph invisible, and the answer was
        # `stuck: false`, "poll again in a minute", for ever — over a node `stranded_nodes()` names
        # one call away. What is in flight is still reported, because both facts are true at once.
        stranded = self._blocking_stranded_nodes()
        _running = self.engine.in_flight_nodes()
        # …AND ONLY A NODE THAT CAN ACTUALLY BLOCK PRE-EMPTS LIVE WORK. `stranded_nodes` also names
        # ABANDONED ones, and cancellation is an ORDINARY event — a child refused after the goal was
        # revised leaves a tombstone that §11.5 keeps as provenance and `get_active_children` does
        # not see. Letting a tombstone pre-empt the in-flight branch made every poll for the rest of
        # a healthy run answer `stuck: true` and advise re-decomposing around a node somebody had
        # deliberately cancelled — while an independent verdict was arriving. It is the same reading
        # `_never_passes` was corrected for one screen above, and it has to hold in both places.
        if _running and not stranded:
            return {"complete": False, "stuck": False, "steps": [], "in_flight": _running,
                    **({"waiting": list(self._held_by_plan)} if self._held_by_plan else {}),
                    "directive": (
                        "Nothing to take right now — the graph is working: "
                        + "; ".join(f"'{w['task_id']}' {w['why']}" for w in _running)
                        + ". Those arrive by themselves; a second instrument on the same "
                          "delivery would validate it twice. Wait for them here: call `next_steps` with "
                          "`wait` (seconds) — it returns as soon as something is yours. Do not end your work "
                          "on this: what lands may be yours to sign.")}
        where = "; ".join(f"'{t.id}' ({t.spec.name or t.id}) is {t.state.name}"
                          for t in stranded)
        waiting = [
            f"'{t.id}' waits on " + ", ".join(
                sorted(f"'{e.from_id}'" for e in deps if e.to_id == t.id
                       and not (self.engine.graph.get_task(e.from_id) is not None
                                and _passed(self.engine.graph.get_task(e.from_id)))))
            for t in tasks
            if t.state in (State.OFFERED, State.EXECUTING, State.REWORKING)
            and not _deps_ready(t.id)]
        return {"complete": False, "stuck": True,
                "blocked_by": [str(t.id) for t in stranded],
                **({"in_flight": _running} if _running else {}),
                "directive": (
                    f"Stuck: no actionable node, and the root is not DONE/PASS. {where} — a "
                    f"node the graph cannot move past, and the canon hands that to the "
                    f"ISSUER (§12.5). "
                    + "; ".join(f"on '{t.id}' {self.engine.issuer_moves_on(t.id)}"
                                for t in stranded if t.state == State.ESCALATED)
                    + (" For a node settled for good, re-decompose around it (revise the parent so "
                       "another child carries the criteria it left uncovered)."
                       if any(t.state != State.ESCALATED for t in stranded) else "")
                    if stranded else
                    # …and when the hold IS the dependency order, name the pair. The frontier
                    # now gates OFFERED and REWORKING on producers too (a leaf handed out before
                    # its input exists can only BLOCK), so this branch is reachable with every
                    # node simply waiting — and "check the Dep producers" would leave the reader
                    # to work out which, exactly as the ESCALATED case used to.
                    (f"Stuck: no actionable node, and the root is not DONE/PASS. What is waiting "
                     f"is the dependency order: " + "; ".join(waiting) + ". Those producers are "
                     f"not PASSED, and nothing else can run meanwhile — drive them, or drop the "
                     f"edge (`remove_dependency`) if it was declared in error."
                     if waiting else
                     self._why_nothing_is_open()))}

    def _why_nothing_is_open(self) -> str:
        """The LAST answer, when no node is takeable and no dependency explains it.

        It used to assert "nothing is settled-negative either, so the block is structural: check
        `list_holes` and the nodes' Dep producers" — and it said that over a deliberately CLOSED
        root, where `list_holes` answers empty, the claim is false, and the act that exists
        (`reopen`, which `available_actions` names) went unmentioned. A door that gives no act and
        no owner is the hole this release is about; the last branch is where one hides.
        """
        root = root_of(self.engine.all_tasks())
        if root is not None and root.state in (State.ABANDONED, State.DONE):
            what = ("abandoned" if root.state == State.ABANDONED else
                    "closed on a FAIL" if root.done_reason == DoneReason.FAIL else "done")
            if root.state == State.DONE and root.done_reason != DoneReason.FAIL:
                return (f"Nothing is open because the goal is finished: '{root.id}' is DONE. "
                        f"If it should not be, `reopen('{root.id}')` puts it back to OFFERED while "
                        f"nothing has been staked on it and reopens remain (§12.14).")
            left = max(0, root.max_reopens - root.reopens)
            return (f"Nothing is open, and that is not a block: the goal itself is settled — "
                    f"'{root.id}' is {root.state.name} ({what}). Nothing below a settled root can "
                    + (f"move it. To take the goal up again: `reopen('{root.id}')` "
                       f"({left} of {root.max_reopens} reopens left), which returns it to OFFERED "
                       f"to be re-earned by fresh contact. To start a different goal, open another "
                       f"project (`use_project`)." if left else
                       f"move it, and its reopens are spent ({root.reopens}/{root.max_reopens}) — "
                       f"this goal is over. A different goal belongs in another project "
                       f"(`use_project`)."))
        return ("Stuck: no actionable node, and no dependency explains it. The usual cause is a "
                "plan that does not admit its own children — `list_holes` names any open structural "
                "hole, and `available_actions(<node>)` says, for one node, what its state admits "
                "and who may send it.")

    def _not_complete_because_refuted(self, refuted: list[str]) -> dict:
        """The one answer given about nodes standing at PASS over their own FAIL.

        Written twice — once for the whole graph, once for a named root — is how the scoped door came
        to answer COMPLETE about a node the unscoped one called contradicted."""
        return {"complete": False,
                # named as DATA as well as prose: the CLI marks these nodes in its tree, and
                # parsing them back out of a sentence is a second spelling of one fact.
                "refuted_passes": refuted,
                "directive": (f"NOT COMPLETE — {', '.join(refuted)} stand(s) at PASS while the "
                              f"current recorded verdict for it is FAIL. A signature landed "
                              f"before the instrument's verdict did, and the graph is showing "
                              f"the signature. Read `get_verdict` on it; recovery is `reopen` "
                              f"if it is not consumed, and re-decomposition around it if it is.")}

    def _how_this_closed(self, root_id: "Optional[TaskId]" = None) -> dict:
        """The facts a reader must weigh about a graph that answers COMPLETE.

        ONE owner, because there are TWO completion answers — the whole-graph one and the per-root
        one — and only the first carried them. Asking about a root BY NAME is what `next_step(<id>)`
        does, what every signal reply calls, and what the documentation's own loop runs; it answered
        a bare `complete: true` while the unscoped call carried the contradiction (HTTP door, wave
        26, 2026-09-06). The comment on the refutation check ten lines above says the same lesson
        about the same pair of paths, written when THAT rule was found missing from this one: a rule
        that holds at one door and not at the next is the class this product keeps finding in itself.
        None of these withholds COMPLETE. Overruling an instrument is the issuer's act (§10.2) and no
        check can establish that a self-named reviewer is independent (§15.7) — so a correct override
        must stay finishable. What must not happen is that it finishes SILENTLY.
        """
        extra: dict = {}
        if _open_plan := self.engine.closed_over_an_open_plan_review(root_id):
            extra |= {"closed_over_an_open_plan_review": _open_plan,
                      "closed_over_an_open_plan_review_note":
                          (f"{', '.join(_open_plan)} passed while its own Level-2 review still "
                           f"names findings nobody answered \u2014 `get_review` lists them. On a node "
                           f"with children the gate would have held them; on a leaf there is "
                           f"nothing to hold, so the review is advice and this is the only place "
                           f"it is said. The checker is an approximation (\u00a79.9) and contact is "
                           f"the real verdict \u2014 read both.")}
        if _auto := self.engine.auto_accepted_closures(root_id):
            extra |= {"auto_accepted_closures": _auto,
                      "auto_accepted_note":
                          (f"{', '.join(_auto)} reached DONE on the CLOCK — the issuer did not "
                           f"answer in time, so the protocol accepted the delivery for them "
                           f"(§16.14 records it apart from a pass). Nobody validated it. "
                           f"The conjunction above stands on it as on any accepted child (§16.14), "
                           f"which is exactly why it is named here: the one thing to weigh about "
                           f"this result is that a part of it was never checked.")}
        if _over := self.engine.passes_over_open_parts(root_id):
            extra |= {"passes_over_open_parts": _over,
                      "passes_over_open_parts_note":
                          (f"{', '.join(_over)} passed while a part of it was not accepted: its issuer's check "
                           f"read the delivered result, not its children (§12.8), so the departure from AND is "
                           f"on the record, not refused. If the PASS is untrue it is FM-4's; if the check showed "
                           f"the part unneeded, the split's denial goes to its decomposer.")}
        if _byhand := self.engine.closures_by_hand(root_id):
            extra |= {"closures_by_hand": _byhand,
                      "closures_by_hand_note":
                          (f"{', '.join(_byhand)} closed on a verdict ASSERTED BY HAND. That is a "
                           f"legitimate path \u2014 \u00a710.2 keeps the verdict the issuer's act, and the "
                           f"solo human door has no one else to ask \u2014 and it is the one thing "
                           f"here no check can establish (\u00a715.7): the engine cannot tell whether "
                           f"the reviewer was independent or whether the observations happened. "
                           f"`get_verdict` carries who asserted it and what they said they saw.")}
        if _hand := self.engine.hand_overruled_closures(root_id):
            extra |= {"hand_overruled_closures": _hand,
                      "hand_overruled_note":
                          (f"{', '.join(_hand)} closed on a verdict ASSERTED BY HAND that "
                           f"replaced an instrument's opposite verdict on the same delivery. "
                           f"That is a legitimate act \u2014 the verdict is the issuer's (\u00a710.2) \u2014 "
                           f"and it is the one thing here nothing can check (\u00a715.7): read both "
                           f"with `get_verdict`, which carries the displaced one under "
                           f"`overruled`.")}
        return extra

    def _frontier_terminal(self, tasks, root_id):
        """The whole-graph answers that are not steps: no graph at all, or a finished root.

        Returns (terminal_dict, root). Both answers are about the WHOLE graph rather than about
        any candidate, and keeping them inside the collecting loop made that loop look as though
        it might return a terminal from anywhere in its body.
        """
        # SETTLED POSITIVE, not `passed`. A root closed by the clock (§16.14's auto_pass, which
        # §16.14 counts AS acceptance and which `_how_this_closed` below already annotates as
        # such) failed the strict test, so a FINISHED run was answered `stuck: true`, "the block is
        # structural: check `list_holes`" — with `blocked_by: []`, an empty `list_holes`, and no
        # signal any party could send except a REOPEN the finality gate may refuse. The completion
        # answer says HOW it closed; it must not deny that it did.
        _passed = settled_positive
        if not tasks:
            # …AND THE MODE BEFORE THE PLAN, as the protocol orders it: who holds the work is the user's choice, and
            # once there is work `set_mode` needs the user's own words. Entering a project now says this first, so a
            # directive naming only `auto_decompose` sent the plan ahead of the choice (critic, 2026-10-09).
            first = ("" if self.engine.mode() else
                     "No mode set — explain solo / semi-auto / auto to the user, ask which, and `set_mode` with "
                     "their words; then: ")
            return ({"complete": False,
                    # The protocol handed to an agent says `auto_decompose` authors the root from
                    # the request itself, with no hand-made `create_task` — so this directive, the
                    # first thing a session is told on an empty project, contradicted it.
                    # …AND UNDER AUTO ONLY THE ONE ACT: the manual path offered there is refused at its door, and an AUTO
                    # customer that took it, refused, set about writing the code itself and quit (GB_spreadsheet_engine_
                    # tmpekc132, 2026-10-11)
                    "directive": first + ("No graph yet — state the goal: `auto_decompose(request)` with the user's "
                                          "request is your one act under AUTO; the system plans the work, does it and "
                                          "validates it, and you read its status."
                                          if self.engine.mode_kind() == Mode.AUTO else
                                          "No graph yet — `auto_decompose(request)` authors the root and its "
                                          "subtree from your goal; `create_task` + `decompose` is the manual "
                                          "path when you want to build the structure yourself.")}, None)
        if root_id:
            root = self.engine.graph.get_task(root_id)
            if root is not None and _passed(root):
                # …UNLESS THAT ROOT IS A GREEN THAT IS NOT GREEN. The refutation test below was
                # installed on the WHOLE-GRAPH answer only, so asking about a node BY NAME — which is
                # what `next_step(<id>)` does, and what every signal reply calls — walked past it:
                # `gfso status` printed `[X] PASS CONTRADICTED` and `next_steps <id>` answered
                # `complete: true` about the same node in the same second, with no `refuted_passes`
                # key at all (CLI door, wave 23, 2026-09-03; reproduced directly). One question, one
                # predicate, both ways of asking it — a rule that holds at one door and not at the
                # next is the class this product keeps finding in itself.
                if refuted := self.engine.refuted_passes(root_id):
                    return (self._not_complete_because_refuted(refuted), None)
                if not self.engine.joins.root_landed(root):
                    return (self._not_complete_while_joining(root), None)
                return ({"complete": True,
                         "directive": f"COMPLETE — root '{root.id}' is DONE/PASS. "
                                      f"Execution finished.",
                         **self._how_this_closed(root_id)}, None)
            return None, root
        # A PROJECT MAY BE A FOREST, and "complete" is a claim about ALL of it. This took the FIRST
        # parentless node and, if that one had passed, announced that execution was finished — while
        # another root sat mid-flight with work owed on it (measured on the MCP door 2026-09-02,
        # where a second root had been created deliberately). Saying a graph is done while it is not
        # is the one kind of wrong answer this product exists to make impossible.
        roots = [t for t in tasks if t.parent_id is None] or [tasks[0]]
        # A GREEN THAT IS NOT GREEN IS NOT COMPLETE. A node can stand at PASS while its own current
        # record says FAIL — the signature landed first and the instrument's verdict was refused on a
        # node already terminal. Answering COMPLETE over that is the false green this product exists
        # to refuse, and it is the one answer a person cannot check for themselves.
        if refuted := self.engine.refuted_passes():
            return (self._not_complete_because_refuted(refuted), None)
        if all(_passed(r) for r in roots):
            # …AND NOT WHILE ANYTHING IS STILL OPEN. A child can be attached to a node that has
            # already closed — which the canon's own recovery path needs, since re-decomposition
            # AROUND a consumed terminal is how a defect found later is repaired — and the roots
            # stay passed, so this answered COMPLETE over a graph with an unstarted node visibly in
            # it (HTTP door, 2026-09-02: "5 Done · 1 Not started · root DONE — the goal is met" on
            # one line). V(parent) is the AND over its children (Thm 1), so a passed parent with an
            # unsettled child is a claim that no longer holds; the honest answer is what is open.
            if open_now := [str(t.id) for t in tasks if t.state not in TERMINAL_STATES]:
                return ({"complete": False,
                         "open_nodes": open_now,
                         "directive": (f"NOT COMPLETE — the root(s) passed, but {', '.join(open_now)} "
                                       f"{'is' if len(open_now) == 1 else 'are'} still open. A "
                                       f"parent's result is the AND over its children (Thm 1), so a "
                                       f"node attached after its parent closed leaves that parent's "
                                       f"verdict standing on work nobody has done.")}, None)
            # …and a ⊥ that landed anyway is SAID, never used to withhold the answer. A validator that
            # could not decide is not a validator that decided against: withholding COMPLETE over one
            # would be reading ⊥ as fail, which §2.3 forbids in those words.
            unresolved = self.engine.nodes_with_a_refused_report()
            extra = ({"unresolved_reports": unresolved,
                      # …AND THE MACHINE-READABLE HALF OF THE SAME SENTENCE. The note below says
                      # this does not make the graph unfinished; a dashboard keying on the LIST
                      # still painted a finished root red (HTTP door, wave 27, 2026-09-06). The
                      # answer to "does this block completion" is a boolean, not a paragraph.
                      "unresolved_reports_block_completion": False,
                      "unresolved_reports_note":
                          (f"a validator ran on {', '.join(unresolved)} and the engine REFUSED its "
                           f"report as ⊥ — evidence, not a verdict, and NOT a reason this is "
                           f"unfinished (§2.3: ⊥ is not fail). `get_verdict` shows what it managed "
                           f"to observe, if you want to decide it yourself.")}
                     if unresolved else {})
            # …and a delivery two parties validated in OPPOSITE directions, where the one left standing
            # was asserted by hand. Beside the answer, never instead of it: overruling an instrument
            # is the issuer's right (§10.2) and no check can establish that a self-named reviewer is
            # independent (§15.7), so withholding COMPLETE would make a correct override unfinishable.
            # What the reader must not be able to miss is that the closure was contested at all —
            # measured on the CLI door (wave 24, 2026-09-04): a hand PASS displaced an instrument's
            # FAIL on a node where nothing had been built, and four of the five surfaces a person
            # reads showed an earned green.
            # …AND HOW THE PASSED ROOTS WERE VALIDATED AT ALL. Three doors asked for this line in two
            # waves: a hand-asserted verdict and an instrument's produce the same `[x]` and the same
            # `complete: true`, and the difference is the whole of what this product measures.
            # SCOPED TO THE ROOT THE CALLER ASKED ABOUT. These three facts were computed over the
            # WHOLE graph while the answer around them is about one root — so `next_steps(root_id=X)`,
            # the loop the documentation tells you to run, carried none of them for X. Measured on
            # the HTTP door (wave 26, 2026-09-06): a hand PASS displaced an instrument's FAIL, and
            # the per-root call answered a bare `complete: true` while the unscoped one carried the
            # contradiction. The documented call was the one that hid it.
            extra = {**extra, **self._how_this_closed(root_id)}
            if len(roots) == 1 and not self.engine.joins.root_landed(roots[0]):
                return (self._not_complete_while_joining(roots[0]), None)
            if len(roots) == 1:
                return ({"complete": True,
                         "directive": f"COMPLETE — root '{roots[0].id}' is DONE/PASS. "
                                      f"Execution finished.", **extra}, None)
            # SEVERAL ROOTS IS NOT A SHAPE THIS PROJECT HAS ANY MORE, so "every root is DONE/PASS"
            # is not a verdict on a goal — there is no object saying what the PROJECT achieved when
            # nothing composes them (V(parent) = AND(children) needs a parent). Such a graph can only
            # predate the rule; the measured run that motivated it left exactly this on disk, with
            # the real work under a dead root and the green on a childless one. Say what it is
            # instead of reporting a completion no rule backs.
            named = ", ".join(f"'{r.id}'" for r in roots)
            return ({"complete": False, "multi_root": [str(r.id) for r in roots],
                     "directive": (
                         f"{len(roots)} parentless nodes ({named}) are all DONE/PASS, and that is "
                         f"NOT a completed goal: a project has exactly one root, because the root "
                         f"carries the goal's criteria and V(root) is the project's verdict — with "
                         f"several there is no rule composing them and nothing says what was "
                         f"achieved. This graph predates that rule. Decide which of them is the "
                         f"goal and hang the others under it (`revise`/`map_criterion`), or move "
                         f"the separate goals into their own projects (`use_project`)."),
                     **extra}, None)
        # …and the root handed on is one with work LEFT, never a finished one, or the step search
        # below starts from a node whose subtree is already closed.
        return None, next((r for r in roots if not _passed(r)), roots[0])

    def _frontier(self, root_id: Optional[TaskId] = None):
        """Collect ALL currently actionable candidates, priority-ordered (children before parents,
        dep order respected). Returns either a terminal dict ({complete}/{stuck}/empty-graph) or a list of
        (priority, task, action, directive) tuples. Shared by next_step (v1 single directive) and
        next_steps (v2 parallel frontier)."""
        _passed = self.engine.joins.landed     # one owner for "did this node earn a pass" — and does it stand where it is read
        # …and the nodes the PLAN GATE holds back: not steps, but not silence either. Kept beside the
        # frontier so `next_steps` can say what they wait on and the dispatcher can say it once per
        # node, without either of them offering an ACCEPT the engine would refuse. Reset per call.
        self._held_by_plan = held = []

        tasks = self.engine.all_tasks()
        terminal, root = self._frontier_terminal(tasks, root_id)
        if terminal is not None:
            return terminal

        deps = self.engine.graph.dep_edges(adopted=True)
        def _deps_ready(tid: TaskId) -> bool:
            """A consumer is executable only once every producer it depends on has PASSED (dep order)."""
            # A producer that does not EXIST yet counts as not ready (mid-build a consumer's ASSIGN
            # can land before its producer's) — `_passed(None)` would have raised here instead.
            return all(self.engine.graph.get_task(e.from_id) is not None
                       and _passed(self.engine.graph.get_task(e.from_id))
                       for e in deps if e.to_id == tid)

        cands = []  # (priority, task, action, directive); lower priority acts first
        for t in tasks:
            kids = self.engine.graph.get_active_children(t.id)
            # EVERY criterion, seams included. The directive listed only the node's OWN criteria and
            # dropped the `dep__` ones — and V is the conjunction over ALL of them (§2.3), which is
            # what `record_verdict` enforces: a person who validated exactly the printed list was
            # refused for "criterion 'dep__x' has no verdict" (measured on the human door
            # 2026-08-22, two round-trips). Following the instruction has to be enough.
            crits = [c.name for c in t.spec.criteria]
            nm = t.spec.name or str(t.id)
            if self.steps._plan_gate_step(t, kids, crits, nm, cands, held, _passed):
                continue
            if self._waits_on_work_in_progress(t, kids, held, _passed):
                continue
            _c = self.steps._step_for(t, kids, crits, nm, cands, held, _deps_ready, _passed)
            if _c is not None:
                cands.append(_c)

        if not cands:
            return self._nothing_to_take(tasks, deps, _deps_ready, _passed)
        cands.sort(key=lambda c: (c[0], str(c[1].id)))
        return cands

    def _waits_on_work_in_progress(self, t, kids, held, _passed) -> bool:
        """Whether this node can take no step because something else must finish first.

        Two cases, both of which a verdict here would be refused for: children of its own have
        not passed (a parent's result is the AND over them, Thm 1), or an independent validator
        is already validating THIS delivery. Both are recorded in `held` with what they wait on,
        because a node in neither list is a node the frontier never mentions."""
        if t.state == State.VALIDATING and kids and not all(_passed(k) for k in kids):
            # …AND SAY WHERE IT WENT. Skipping the parent is right — a verdict on it would be
            # refused (Thm 1) — but it left the node in NO list at all: a person who delivered a
            # parent early watched it sit in VALIDATING for an hour, absent from `steps` and from
            # `waiting`, with the frontier that exists to say what to do never mentioning it
            # (measured on the human door 2026-08-21).
            _open = [k for k in kids if not _passed(k)]
            if self.steps._fails_through_parts(t):
                return False           # not a wait: its FAIL is true now and is the step (`_step_for_a_delivered_node`)
            # A WAIT WHOSE OBJECT CAN NEVER ARRIVE IS NOT A WAIT. A child that settled without
            # passing — ESCALATED (its rework bound spent) or ABANDONED (cancelled) — is terminal,
            # so the parent's AND (Thm 1) can never be satisfied and no verdict will ever become
            # possible here. Reported as an ordinary wait, that is a run which polls "the graph is
            # working, poll again in a minute" for ever: measured on a root delivered over one
            # ESCALATED child and one DONE one. The move that exists is the issuer's own FAIL, and
            # nothing named it.
            _dead = self._never_passes(t.id)
            if _dead:
                _names = ", ".join(f"'{k.id}' is {k.state.name}" for k in _dead)
                held.append(Wait(
                    task_id=str(t.id), state=t.state.name, assignee=t.assignee, kind="children",
                    waits_on=tuple(str(k.id) for k in _dead),
                    why=(f"it was delivered while {_names} — settled WITHOUT passing, so the AND "
                         f"over its children (Thm 1) can never be satisfied and no verdict can "
                         f"ever be given here. This is not a wait that ends by itself"),
                    opens_with=(f"FAIL('{t.id}') and re-decompose around the hole, or REOPEN the "
                                f"settled child if it still has reopens left (§12.14)")).as_dict())
                return True
            held.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                             kind="children",
                             waits_on=tuple(str(k.id) for k in _open),
                             why=("it was delivered while children of its own have not passed, "
                                  "and a parent's verdict is the AND over them (Thm 1) — so no "
                                  "verdict can be given here yet"),
                             opens_with="finish those children; validation follows by itself").as_dict())
            # A VERDICT NOW WOULD BE REFUSED, so this is not the step. The parent's result is
            # the AND over its children (Thm 1) and the PASS gate knows it; offering `validate`
            # here put the highest-priority step on the one node that cannot move, and whoever
            # took it waited on a verdict nobody could give. Measured 2026-08-20 on a live run:
            # a root sat nineteen minutes in VALIDATING after its own plan repair added a child,
            # while that child's `accept` step sat below it on the same frontier. Skipping the
            # parent surfaces the children — and if they cannot move either, the stuck branch
            # below names them.
            return True
        if t.state == State.VALIDATING and self.engine.claims.validation_in_flight(t.id):
            held.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                             kind="validator",
                             waits_on=("the validator already running on this delivery",),
                             why=("an independent validation of THIS generation is in flight — a "
                                  "second one would validate the same delivery twice and cost twice"),
                             opens_with="nothing: its verdict arrives by itself").as_dict())
            # A VALIDATOR IS ALREADY RUNNING on this delivery. The step said "VALIDATE this" to
            # whoever asked, so a caller who obeyed either spent a second instrument on the same
            # generation or waited four minutes not knowing whether silence meant work or
            # nobody (measured 2026-08-21). It is not an actionable step while the instrument
            # holds it; the frontier says so and moves on.
            return True
        return False

    def next_step(self, root_id: Optional[TaskId] = None) -> dict:
        """The execution forcing-point (v1, single-agent form). From the graph's CURRENT state, return the
        ONE next required action — or `complete=True`. Children before parents (a parent only DELIVERs once
        its children PASS); completion is GATED on the root being DONE/PASS, so the agent cannot stop early.

        Returns a dict: {complete, [task_id, name, state, action, criteria], directive}. `action` ∈
        {accept, execute, deliver, validate, resolve, rework, confirm_cancel}. For parallel delegation use
        next_steps (the full frontier)."""
        result = self._frontier(root_id)
        if isinstance(result, dict):
            return result
        _, t, action, directive = result[0]
        return self.steps._step_out(t, action, directive)

    def next_steps(self, root_id: Optional[TaskId] = None) -> dict:
        """The PARALLEL frontier (v2): every currently actionable node, priority-ordered, with a
        `parallel_ok` marker on the execute-class steps.

        All returned `execute` steps are pairwise independent by construction: each is a leaf whose Dep
        producers have PASSED (§2.7 dep order), and distinct ready leaves share no unresolved edge — so the
        orchestrator may delegate them to executors CONCURRENTLY. Non-execute steps (accept / validate /
        rework / resolve / deliver / confirm_cancel) are issuer-side and cheap — do them in the returned order
        before/between delegations. Returns {complete, steps: [step...]} (each step shaped like next_step's
        output + `parallel_ok`)."""
        result = self._frontier(root_id)
        if isinstance(result, dict):
            return result if result.get("complete") or "steps" in result else {**result, "steps": []}
        steps = []
        for _, t, action, directive in result:
            step = self.steps._step_out(t, action, directive)
            step["parallel_ok"] = action == "execute"
            steps.append(step)
        # …AND WHAT IS WAITING, which the list alone never showed. A node held by the dependency
        # order is simply ABSENT from the steps — correct, it is not actionable — so a reader saw
        # one step and no reason for the rest of the graph's silence. Measured 2026-08-20 through
        # the MCP door: two of three children were dep-blocked and appeared nowhere, while
        # `get_dependencies` had every edge and glue note. The pairs go in the answer, not in a
        # second verb the reader has to know about.
        out = {"complete": False, "steps": steps, **self._waiting_on(steps)}
        if self._held_by_plan:
            out["waiting"] = list(out.get("waiting", ())) + self._held_by_plan
        if stranded := [t for t in self.engine.stranded_nodes() if t.state != State.ABANDONED]:
            # …AND WHAT THE GRAPH CANNOT MOVE PAST, whether or not something else is actionable.
            out["stranded"] = [
                {"task_id": str(t.id), "state": t.state.name,
                 "why": (self.engine.why_escalated(t.id) if t.state == State.ESCALATED else
                         f"its rework loop was exhausted (§12.5) — a settled FAIL, and a parent's "
                         f"PASS is the AND over its children, so nothing above it can complete"),
                 "opens_with": (self.engine.issuer_moves_on(t.id) if t.state == State.ESCALATED else
                                f"re-decompose around it: add a child that carries what "
                                f"'{t.id}' left uncovered and map it (`map_criterion`). A terminal "
                                f"node is not reopened and takes no revision.")}
                for t in stranded]
        return out

    def _not_complete_while_joining(self, root) -> dict:
        """The root has passed and its result does not yet stand in the base: refused (the base must take it — the
        host retries the join, backing off, and a hand merge of the branch counts), or being joined (poll)."""
        if (why := self.engine.joins.unjoined_roots().get(str(root.id))) is not None:
            return {"complete": False, "stuck": True, "steps": [],
                    "directive": f"The root '{root.id}' has passed, but its result did not land in the base: "
                                 f"{why}. Make the base take it — clear what blocks the merge (an untracked or "
                                 f"edited file it would overwrite), or merge the named branch by hand; the join is "
                                 f"tried again, less often each time it is refused."}
        return {"complete": False, "stuck": False, "steps": [], "in_flight": self.engine.in_flight_nodes(),
                "directive": f"The root '{root.id}' has passed; its result is being joined into the base. Poll "
                             f"again — complete follows the join."}

    def _blocking_stranded_nodes(self) -> list:
        """The stranded nodes that can actually stop the graph — every one except a tombstone.

        `stranded_nodes` also names ABANDONED ones, and cancellation is an ORDINARY event: the node
        leaves the decomposition (§12.6) and `get_active_children` stops seeing it, so it satisfies
        no conjunction and blocks nothing. Read as a blocker it made the frontier answer
        `stuck: true` for the rest of a healthy run and advise re-decomposing around a node somebody
        had deliberately cancelled. This is the same reading `_never_passes` carries one screen
        above, and it has to hold everywhere the stuck answer is BUILT — the first repair put it
        only on the pre-emption test, and the directive and `blocked_by` beside it went on naming
        the tombstone.
        """
        return [t for t in self.engine.stranded_nodes() if t.state is not State.ABANDONED]

    def _waiting_on(self, steps: list) -> dict:
        """`waiting`: the nodes not on the frontier because a producer of theirs has not passed."""
        shown = {s["task_id"] for s in steps}
        deps = self.engine.graph.dep_edges(adopted=True)
        out = []
        for t in self.engine.graph._storage.get_all_tasks():
            if str(t.id) in shown or t.state.name in ("DONE", "ABANDONED", "ESCALATED"):
                continue
            open_prod = sorted({str(e.from_id) for e in deps if str(e.to_id) == str(t.id)
                                and not settled_positive(self.engine.graph.get_task(e.from_id))})
            if open_prod:
                # The SAME shape as a plan-gated wait, because the two sat side by side in one answer
                # with only one of them explaining itself (measured on the human door 2026-08-21).
                out.append(Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee,
                                kind="dependency", waits_on=tuple(open_prod),
                                why=("it consumes what those nodes produce (§2.7: a Dep is criteria "
                                     "content — this node's criteria name their result), and they "
                                     "have not passed"),
                                # …AND THE NODE'S OWN ISSUER HAS MOVES BESIDES WAITING. "finish X"
                                # is another party's act; where the consumer's contract no longer
                                # needs that input, its issuer retracts the edge and revises rather
                                # than waiting on work nobody is doing (§12.16(ii): a lift held only
                                # by the counterparty is not a lift).
                                opens_with=(
                                    f"finish {', '.join(open_prod)} — or, if this node's contract "
                                    f"does not really need what they produce, its ISSUER can "
                                    f"`remove_dependency` and revise it")).as_dict())
        return {"waiting": out} if out else {}
