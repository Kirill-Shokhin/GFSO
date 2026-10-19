"""An LLM role's structured report turned into the protocol's signals: what its self-check and status decided
(`_decided_self_check`, `_decided_status`), the internal node it may settle itself (`_settle_internal`), and the
signals one node's report or one scope's report sends (`_report_into_signals`, `_scope_report_into_signals`). An
undecided report sends no delivery."""
from __future__ import annotations

import logging
from gfso.adapters import worktrees as W
from gfso.adapters.llm.stats import _stat_line
from gfso.core.protocol.invariants import verdict_word
from gfso.core.graph.model import generation_of_task
from gfso.core.types import TaskId, Signal, Verdict
from gfso.issuer import signal_ok as _signal
from gfso.packets import _EXECUTOR_STATES

log = logging.getLogger(__name__)


def _decided_self_check(raw) -> "Verdict | None":
    """The executor's OWN verdict from its report — PASS, FAIL, or nothing decided.

    §11.2 puts a WORD here and the human door has always insisted on it (`_self_check_verdict` in
    `gfso/tools.py` raises on anything else). The delegated door took a free string and asked only
    whether it was empty, which is not the same question and gave the opposite answer: probed
    2026-09-05, an executor whose `self_validation` read `FAIL` reached DONE with a recorded verdict
    of PASS, and so did `checked`.

    Prose that decides nothing is ⊥, not a pass (§2.3): the node waits for its issuer, exactly as an
    empty field already did. A leading verdict word with a reason after it (`PASS — all green`) is a
    decision and is read as one; anything else is not guessed at.
    """
    return verdict_word(raw, lenient=True)


def _decided_status(raw) -> "str | None":
    """Which of the three the executor reported — or nothing, when it reported something else.

    §11.2 gives an executor three moves after it has worked: it delivered, it is blocked, or it
    disputes the contract. The schema says so (`EXECUTOR_SCHEMA`'s `enum`) and the schema is not
    enforced: `parse_structured` validates the presence of KEYS, never their types or their
    enumerations — so the declaration reads as a guarantee and is a comment.

    Six of the seven `enum`s in this package fail CLOSED when a model answers outside them (an
    unknown word becomes not-SUFFICIENT, not-`atomic`, not-PASS). This one failed OPEN, because the
    dispatch below is `if challenge / elif blocked / else`, and `else` is DELIVERED. Probed
    2026-09-08: `{"status": "failed", "summary": "could not do it"}` parses, takes the else, and
    sends DELIVER — an executor saying it could not do the work moves its node to VALIDATING as a
    delivery, where a validator is then paid to validate an artifact its own author disclaimed.

    A word the contract does not define decides nothing, and ⊥ is not a delivery (§2.3). The caller
    routes `None` into the branch that already exists for a report that did not parse: no signal is
    forged, the node stays where it is, and the issuer is told. `"DELIVERED"`, `" blocked "` and the
    like are the same three words and are read as such — what is refused is a fourth meaning.
    """
    word = str(raw or "").strip().lower()
    return word if word in ("delivered", "blocked", "challenge") else None


def _settle_internal(engine, task_id: TaskId, self_check, _cb, observed: bool = False) -> None:
    """An INTERNAL node completes on its own self-check — §10.3, read literally.

    The canon does not leave this open. An internal node is one whose Del equals its parent's, and
    of it §10.3 says: it "**self-verifies** — DELIVER carries `self_validation`" — and is "**not**
    independently validated", because "the guarantee for the whole internal decomposition is carried
    by the validation of the agent's public result" (Thm 1, non-redundancy). The agent "stakes all
    internal work on one public validation". There is no second party owed a verdict here: the
    issuer of an internal node IS the same scope as its executor, by the definition that makes the
    node internal. So the PASS the FSM needs is not the system inventing a verdict — it is the
    executor's own verdict, already in the delivery packet, arriving as the signal.

    Without it a subtree delegated to ONE role deadlocks: nothing independent fires (correctly), and
    nothing signs (measured 2026-08-20 on the shipped autonomous demo — a delivery in 57 seconds,
    then half an hour of stillness). Making it wait invents a seam §10.3 says is not there.

    THE THREE CONDITIONS, each from the same passage and none of them negotiable:
      · INTERNAL only. A public node — any root, or any Del ≠ parent's Del — is the seam where the
        independent verdict is the whole point (§10.3: "self-delegation is legitimate iff the
        validating Issuer is independent"). Never relayed there.
      · A DECIDED self-check only. `self_validation` empty ⇒ nothing was checked, and ⊥ is not a
        pass (§2.3). The node then waits for its issuer, and the dispatcher says so.
      · Not when an observer IS bound to it (`observed`: the system observes every delivery by
        default, `GFSO_VALIDATE_INTERNAL`) — there the verdict stands on the instrument's record, and
        relaying the executor's own word would race it. With no instrument in the roster, the
        self-check is still the only record there is.
    """
    task = engine.graph.get_task(task_id)
    if task is None or engine.graph.is_public(task):
        return
    if observed:
        return
    if self_check is None:
        return
    issuer = str(engine.graph.issuer_of(task_id))
    # …AND IT GOES ON THE RECORD, because a verdict nobody can read afterwards is not evidence that
    # anything was checked. The executor's own words per criterion are what §10.3 asks an internal
    # node to carry, and what the PASS gate below now looks for (measured on the human door
    # 2026-08-21: DELIVER → PASS eight seconds apart, DONE, and `get_verdict` answering "it has not
    # been validated" about the same node).
    # …ONCE. The DELIVER that carried `self_validation` is already recorded by the engine as ONE
    # self-report (`engine/loop.py`), which is what the executor actually said: one word about the
    # delivery as a whole. Re-recording it here fanned that word out into a row per criterion — a
    # stronger claim than the evidence, written over the truthful record, with which of the two
    # survived decided by the route the delivery took (register 2026-08-22, finding 3). So this
    # writes only when nothing is on the record for this delivery.
    if engine.current_exec_verdict(task_id) is None:
        try:
            engine.record_reviewer_verdict(task_id, self_check, [], reviewer=str(task.assignee),
                                           observed={c.name: str(self_check)
                                                     for c in task.spec.criteria})
        except Exception:
            log.warning(f"could not record the internal self-check on {task_id}", exc_info=True)
    # BOTH DECISIONS, or this is not a relay of the executor's verdict but a filter on it. §10.3
    # rests an internal node's completion on the self-check; reading only the affirmative half meant
    # a node whose executor said its own work had FAILED was closed DONE anyway (probed 2026-09-05).
    if self_check != Verdict.PASS:
        # AND THE NEGATIVE HALF STOPS HERE, DELIBERATELY. A self-FAIL is one word about the delivery
        # as a whole and names no criteria, while Inv-3 (§12.8) requires a FAIL to say WHICH — so
        # relaying it would mean inventing that set on the executor's behalf, which is the same
        # manufacture-a-verdict move in the other direction. The refusal is on the record and the
        # node waits for the party who can name them.
        _cb(f"{task_id}: its executor FAILED its own delivery (§11.2 self_validation). The node "
            f"stays in VALIDATING and its ISSUER decides: a FAIL must name the criteria it is "
            f"about (Inv-3), and a one-word self-check names none. The report is on the record "
            f"(`get_verdict {task_id}`).")
        return
    if _signal(engine, task_id, Signal.PASS, issuer):
        _cb(f"{task_id}: internal node — PASSED on its own self-check (§10.3: its guarantee is "
            f"carried by the validation of the public result above it)")


def _report_into_signals(engine, task_id, executor_id, task, report: dict, status: str,
                         llm, _cb, observed: bool = False, workspace: tuple | None = None,
                         started_on: tuple | None = None) -> None:
    """The executor's report, wrapped into the protocol: challenge · block · deliver.

    `started_on`: the node's generation when the session began. A contract revised while it worked (Inv-1: a new
    version, binding only by its executor's ACCEPT) is not the one the report answers: nothing is signalled — an ACCEPT
    sent here would consent for its executor to a contract no session saw, and a delivery would answer the old one.

    A delegated round is two jobs — spawn the agent with its packet and account for what it
    cost, then turn what it says into signals the FSM admits. The second is where the
    protocol is actually enforced on a machine executor, and it read as a tail of the first."""
    if started_on is not None and (now := engine.graph.get_task(task_id)) is not None             and tuple(generation_of_task(now)) != tuple(started_on):
        _cb(f"{task_id}: the report answers a contract revised while the session worked - nothing signalled; the "
            f"node waits under its new version · {_stat_line(llm)}")
        if workspace is not None:   # what it wrote is the old version's, on the record as such — never in a later delivery
            W.commit_all(workspace[0], workspace[1], f"gfso: {task_id} work under a superseded version", executor_id)
        return
    if status == "challenge":
        # The dispute travels as the signal wherever the state admits it — OFFERED, and, since
        # v4.1, EXECUTING and REWORKING, where most spec defects are actually met (§12.4): the
        # issuer then owes ACCEPT_CHALLENGE or REJECT_CHALLENGE, which are the dispute's own two
        # closures. Where it is NOT admissible (a delivery already with its issuer), the reason is
        # still not lost: it is recorded where the issuer reads and the node stays with its
        # executor. Measured 2026-08-21, before the post-consent edge existed — a run's leaf
        # challenged during rework at 01:27, the signal was refused, and the graph never moved
        # again; the run ended `graph_stalled` twenty-five minutes later.
        if not _signal(engine, task_id, Signal.CHALLENGE, executor_id,
                       reason=report.get("reason", "")):
            _cb(f"{task_id}: the executor disputes the contract, and a CHALLENGE is not admissible "
                f"in {task.state.name} (§12.4 admits it from OFFERED) — its reason is on the record "
                f"for the ISSUER: {report.get('reason', '')[:400]}. The node stays with its "
                f"executor; to renegotiate, `revise` it (which returns it to OFFERED) — a node "
                f"whose executor has stopped believing in its contract will keep failing it.")
            engine.emit_info("delegate", f"{task_id}: contested during {task.state.name} — "
                                         f"{report.get('reason', '')[:200]}")
            # Not re-spawned: the same executor under the same contract will dispute it again, and
            # that is a paid loop. Recorded as CONTESTED instead, which the frontier hands to the
            # ISSUER as a step of their own — the party who can actually change a contract.
            engine.parking.contest(task_id, report.get("reason", ""))
        else:
            _cb(f"{task_id}: executor CHALLENGED the spec — issuer resolves · {_stat_line(llm)}")
    elif status == "blocked":
        if task.state.name == "OFFERED":  # consent happened (it worked far enough to find the block)
            _signal(engine, task_id, Signal.ACCEPT, executor_id)
        blocker = report.get("blocker_task_id")
        blockers = tuple(TaskId(b) for b in (report.get("blocker_task_ids") or []) if b)
        _signal(engine, task_id, Signal.BLOCK, executor_id, reason=report.get("reason", ""),
                blocker_task_id=TaskId(blocker) if blocker else None,
                blocker_task_ids=blockers)
        _cb(f"{task_id}: executor BLOCKED ({report.get('reason', '')[:80]}) · {_stat_line(llm)}")
    elif status != "delivered":
        # THE GUARD SITS WITH THE DISPATCH IT GUARDS. This was `else:` — every word that is neither
        # `challenge` nor `blocked` was read as a delivery — and the first repair put the check in
        # the CALLER, where a probe calling this function directly walked straight past it. A guard
        # a caller can step around is the shape this repository has already paid for twice.
        _cb(f"{task_id}: executor reported status {status!r}, which is none of delivered / blocked "
            f"/ challenge (§11.2) — no signal sent, the node stays where it is; issuer attention "
            f"needed · {_stat_line(llm)}")
        engine.emit_info("delegate", f"{task_id}: undecided status {status!r} — no signal forged")
    else:  # delivered — the DISPATCHER picks the VALIDATING node up and auto-validates (one path
        # for every delivery, delegated or self-executed; natural node×iteration dedup)
        if task.state.name == "OFFERED":
            _signal(engine, task_id, Signal.ACCEPT, executor_id)
        # THE SELF-CHECK RIDES THE DELIVERY, as §11.2 writes the packet: DELIVER carries
        # `self_validation`. The field was asked for in the report schema, typed in `SignalData`,
        # and then dropped on the floor here — so the one thing §10.3 makes an internal node's
        # completion rest on never reached the graph at all.
        # WHAT IT SAID, not whether it said anything. This read the field for EMPTINESS and mapped
        # every non-empty string to PASS — so an executor reporting "FAIL" on its own work closed the
        # node DONE with a recorded verdict of PASS. Probed directly 2026-09-05: `FAIL`, `the tests
        # do not pass` and `checked` all reached DONE/PASS; only the empty string was refused. A
        # gate that accepts the good news and cannot hear the bad one is not a gate.
        _self = _decided_self_check(report.get("self_validation"))
        # THE RESULT AS IT STANDS AT DELIVER (§11.3), fixed before the signal: a PASS can land the node DONE and
        # its branch joins the whole at once, and a join ahead of this commit would carry the tree without it
        if workspace is not None:
            W.commit_all(workspace[0], workspace[1], f"gfso: {task_id} delivery", executor_id)
        _signal(engine, task_id, Signal.DELIVER, executor_id, result=report["summary"],
                self_validation=_self)
        _cb(f"{task_id}: executor DELIVERED · {_stat_line(llm)}")
        _settle_internal(engine, task_id, _self, _cb, observed)


def _scope_report_into_signals(engine, order: list, executor_id: str, report: dict, llm, _cb,
                               workspace: tuple | None = None, started_on: dict | None = None) -> None:
    """The scope session's report, wrapped into each node's own signals in build order, parts first. The
    deliveries are not self-settled: they wait in VALIDATING for the scope's one validation. A whole is
    delivered only over parts that are delivered or done — never over a part that blocked, disputed, or was
    not reported on."""
    by = {str(e.get("task_id")): e for e in report.get("nodes") or () if isinstance(e, dict)}
    for t in order:
        t = engine.graph.get_task(t.id)
        if t is None or t.state.name not in _EXECUTOR_STATES:
            continue
        entry = by.get(str(t.id))
        # a whole is handed in with its parts — in rework too, in the same session that reworks them. Waiting for
        # the parts to pass first cost one more session and one more validation per failed round than the same
        # task posed as a leaf, and one task must cost the same wherever the seam falls (the author's honesty
        # condition). A part that fails again fails the whole again and spends the whole's rounds: so does the
        # leaf's every failing round — the whole's budget is its issuer's forecast of rounds, and a round of the
        # whole is one session of the scope.
        short = [str(k.id) for k in engine.graph.get_active_children(t.id) if k.state.name not in ("VALIDATING", "DONE")]
        status = _decided_status(entry.get("status")) if entry is not None else None
        if entry is None or (short and status == "delivered"):
            _cb(f"{t.id}: not signalled — " + (f"its part(s) {', '.join(short)} were not delivered, and a whole "
                                                f"is handed in with its parts" if entry is not None else
                                                "the scope session reported nothing on it"))
            continue
        if status == "blocked":
            # A BLOCK ON A NODE OF THE SAME SCOPE IS NOT A BLOCK: that node is this session's own work, and a
            # block resolves only when its blocker is DONE — which inside the scope waits on the scope's own
            # validation, which waits on this node. Measured: the whole BLOCKED on its part, the part on its
            # sibling, and the scope stood with nothing to run. Only blockers outside the scope are signalled;
            # a node blocked on its own scope alone stays open for the scope's next session.
            inside = {str(m.id) for m in order}
            outside = [b for b in (entry.get("blocker_task_ids") or ()) if b and str(b) not in inside]
            one = entry.get("blocker_task_id")
            if one and str(one) in inside:
                one = None
            if not outside and not one and ((entry.get("blocker_task_ids") or ())
                                            or entry.get("blocker_task_id")):
                _cb(f"{t.id}: not signalled — it named only nodes of its own scope as blockers, which this "
                    f"scope's sessions build; it stays open for the next one")
                continue
            entry = {**entry, "blocker_task_ids": outside, "blocker_task_id": one}
        _report_into_signals(engine, t.id, executor_id, t, {**entry, "summary": str(entry.get("summary") or "")},
                             _decided_status(entry.get("status")) or str(entry.get("status")), llm, _cb,
                             observed=True, workspace=workspace,
                             started_on=(started_on or {}).get(str(t.id)))
