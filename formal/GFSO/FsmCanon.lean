/-
  GFSO — the CANON table of the protocol FSM (Ch. 14.3), as distinct from `Fsm.lean`.

  WHY A SECOND FILE. `Fsm.lean` states in its header that its transition table is `fsm.py`'s —
  a conformance mirror of the engine, deliberately encoding the code even where the code diverges
  from the canon ("Do not 'fix' it here"). Claims ABOUT THE CANON therefore cannot live there.
  This file transcribes the table from the canon's own prose and diagram (Ch. 14.3) and proves
  the canon-side facts; the divergence between the two tables is stated here as a theorem rather
  than left as prose, so that changing either side breaks a proof instead of drifting silently.

  SCOPE — the BASE machine. Ch. 14.3 draws two: the base protocol, and the R' extension
  (REOPEN: DONE -> OFFERED, ABANDONED -> OFFERED), which the canon marks "over the base; NOT part
  of the 12-signal minimum". R' is excluded, and the exclusion is load-bearing twice: R' is gated
  on CONSUMPTION, a graph fact (the parent staked the AND, or a Dep consumer read-and-built) and
  not a state-resident datum, so no finite (state, counters) composite is an automaton over the
  signal alphabet on the R' machine; and under R' the three terminals are no longer one block
  (ESCALATED is no longer one of them at all: it is the ISSUER's waiting state, §14.3-bis,
  and carries its own row in the BASE machine — ASSIGN, CANCEL and its own timeout).

  TRANSCRIPTION SOURCE, per row (Ch. 14.3): the diagram, plus the prose catch-alls -- universal
  CANCEL from any non-terminal except CANCELLING; re-ASSIGN (Inv-1) from the reassignable states;
  the system timeout with its three special targets (BLOCKED -> ESCALATED, CANCELLING -> ABANDONED,
  VALIDATING -> DONE(auto_pass)) and OVERDUE as the first-timeout target elsewhere; IDLE carries no
  clock of its own.
  NOTE on (REWORKING, BLOCK): Ch. 14.3's diagram omits it, but Ch. 14.2 FORCES it — BLOCK exists so
  that "the executor can report a blocker", and REWORKING is a work-active state under the same
  contract (Inv-1), so without the edge a blocker found during rework is unreportable (FM-7). The
  diagram's silence is a drafting gap, not a denial; `fsm.py` has the row and is right. Consequence
  proved below: the twelve states carry ELEVEN behaviour classes.
  The exhausted rework loop goes to ESCALATED (the canon's target; `formal/README.md` corner #3).
-/
import GFSO.Fsm

namespace GFSO.FsmCanon
open GFSO.Fsm GFSO.Fsm.St GFSO.Fsm.Sig

/-- The canon's transition table (Ch. 14.3, base machine). `canRework` = the retry guard. -/
def canonStep (s : St) (sig : Sig) (canRework : Bool) : Option St :=
  match s with
  | IDLE => match sig with
    | ASSIGN => some OFFERED
    | CANCEL => some CANCELLING
    | _ => none
  | OFFERED => match sig with
    | ACCEPT => some EXECUTING
    | CHALLENGE => some CHALLENGED
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | CHALLENGED => match sig with
    | ACCEPT_CHALLENGE => some OFFERED
    | REJECT_CHALLENGE => some EXECUTING
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | EXECUTING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | BLOCKED => match sig with
    | RESOLVE_BLOCK => some EXECUTING
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | VALIDATING => match sig with
    | PASS => some DONE
    | FAIL => some (if canRework then REWORKING else ESCALATED)   -- canon target (corner #3)
    | Sig.TIMEOUT => some DONE                                     -- auto_pass
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | REWORKING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED        -- FORCED by Ch. 14.2: without it a blocker found during
                                   -- rework is unreportable (the defect BLOCK exists to preclude; FM-7)
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | CANCELLING => match sig with
    | CONFIRM_CANCEL => some ABANDONED
    | Sig.TIMEOUT => some CANCELLING     -- silence IS his cancellation; the subtree goes too
    | _ => none
  | OVERDUE => match sig with
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | _ => none
  | DONE => none
  | ABANDONED => none
  -- The issuer's waiting state (§14.3-bis), mirror of OFFERED under Inv-4: raising the rework
  -- bound and changing the criteria are both packet fields, hence ONE act by Inv-1; closing it is
  -- the universal CANCEL; and the timeout keeps the wait finite by CLOSING, never by passing.
  | ESCALATED => match sig with
    | ASSIGN => some OFFERED
    | CANCEL => some CANCELLING
    | Sig.TIMEOUT => some CANCELLING     -- silence IS his cancellation; the subtree goes too
    | _ => none

/-- The settlement mode: the terminal label (Ch. 14.3). It is NOT the verdict V — under V both
    ABANDONED and a timeout-settled node carry ⊥ and would be indistinguishable.

    ESCALATED is `live` here, not a settlement mode of its own: nothing has settled while the issuer
    still owes an answer (§14.3-bis). The timeout attribution it used to carry now lands where the
    node actually comes to rest — ABANDONED, whether by the issuer's CANCEL or by his silence. -/
inductive Settle | pass | abandoned | timeout | live
deriving DecidableEq, Repr

def settle : St → Settle
  | DONE => Settle.pass | ABANDONED => Settle.abandoned
  | _ => Settle.live

/-! ### The canon-side facts -/

/-- EXECUTING and REWORKING agree on EVERY signal at BOTH guard values: with the forced BLOCK edge
    they are one behaviour class. REWORKING is an ATTRIBUTION label (a FAIL was consumed — a property
    of the log's last edge), not a behaviour. -/
theorem canon_exec_rework_same :
    (allSig.all (fun g => [false, true].all (fun b =>
      canonStep EXECUTING g b == canonStep REWORKING g b))) = true := by
  decide

/-- The OTHER eleven are pairwise separated by their transition rows alone (no output needed). -/
theorem canon_others_pairwise_distinct :
    (allSt.all (fun s => allSt.all (fun t =>
      (s == t) || isTerminal s || isTerminal t
      || ((s == EXECUTING) && (t == REWORKING)) || ((s == REWORKING) && (t == EXECUTING))
      || !(allSig.all (fun g => [false, true].all (fun b =>
             canonStep s g b == canonStep t g b)))))) = true := by
  decide

/-- The three terminals share the empty row: one behavioural block, separated by the settlement mode
    ALONE — so the observable must carry it; the verdict V does not suffice. -/
theorem canon_terminals_share_rows :
    (allSt.all (fun s => allSt.all (fun t =>
      !(isTerminal s && isTerminal t) ||
      allSig.all (fun g => [false, true].all (fun b => canonStep s g b == canonStep t g b))))) = true := by
  decide

theorem canon_settlement_separates_terminals :
    (allSt.all (fun s => allSt.all (fun t =>
      (s == t) || !(isTerminal s && isTerminal t) || (settle s != settle t)))) = true := by
  decide

/-- The FULL joint observable (settlement mode ⊕ transition row) distinguishes **every** pair among the
    eleven states other than REWORKING — covering all three categories in ONE check: nonterminal×
    nonterminal (by row), terminal×terminal (by settle), and the cross nonterminal×terminal pairs
    (a nonterminal has `settle = live` and a non-empty row; a terminal has neither). This backs the
    "eleven pairwise-distinct under the admissible-set ⊕ settlement-mode observable" claim in full,
    including the cross-pairs the row-only and settle-only lemmas each skip. -/
theorem canon_eleven_pairwise_distinct :
    (allSt.all (fun s => allSt.all (fun t =>
      (s == t) || (s == REWORKING) || (t == REWORKING)
      || (settle s != settle t)
      || !(allSig.all (fun g => [false, true].all (fun b =>
             canonStep s g b == canonStep t g b)))))) = true := by
  decide

/-- The engine mirror agrees with the corrected canon on this row: there is NO divergence here. -/
theorem engine_agrees_on_rework_row :
    (allSig.all (fun g => [false, true].all (fun b =>
      step EXECUTING g b == step REWORKING g b))) = true := by
  decide

/-- NEGATIVE CONTROL — the same shape of check is able to come out `false`, so the theorems
    above are not vacuously green. -/
theorem control_exec_blocked_differ :
    (allSig.all (fun g => [false, true].all (fun b =>
      canonStep EXECUTING g b == canonStep BLOCKED g b))) = false := by
  decide

/-! ### §26.9(b): adequacy does not determine the behaviour map — a machine-checked witness

Adequacy ("addresses the 7 FMs under the Ch. 14 invariants") forces, on the finiteness axis, that
every non-terminal has a timeout *exit* (deadlock-freedom / Inv-5). It does NOT force the exit's
*destination*: §14.2/§14.3 mark VALIDATING → DONE(auto_pass) as a "direct special target", and §24.7
lists auto-PASS in "Assumptions and limitations" with countermeasures — a design choice, not a
consequence of the FMs. The `variant` below routes VALIDATING-timeout to ESCALATED (escalate issuer
inaction rather than auto-accept) and is otherwise `canonStep`. It satisfies the SAME finiteness
condition, yet differs behaviourally on the VALIDATING-timeout history — so bare adequacy leaves the
behaviour map underdetermined, and the §26.9(b) closing lemma is FALSE over bare adequacy. -/

def variantStep (s : St) (sig : Sig) (canRework : Bool) : Option St :=
  match s, sig with
  | VALIDATING, Sig.TIMEOUT => some ESCALATED      -- the sole edit: escalate, not auto-pass
  | _, _ => canonStep s sig canRework

/-- Both tables satisfy the finiteness/deadlock-freedom adequacy condition (every non-terminal
    except IDLE has a defined timeout — the same condition `Fsm.timeout_defined` states of the
    engine): adequacy on this axis is shared. -/
theorem variant_and_canon_both_timeout_defined :
    (allSt.all (fun s => isTerminal s || (s == IDLE) ||
        ((canonStep s Sig.TIMEOUT false).isSome && (variantStep s Sig.TIMEOUT false).isSome))) = true := by
  decide

/-- Yet they disagree — on exactly the VALIDATING-timeout edge, and the disagreement is a
    settlement difference (canon DONE = pass; variant ESCALATED = timeout), hence a genuine
    behavioural difference under the settlement-mode observable. -/
theorem variant_differs_on_validating_timeout :
    canonStep VALIDATING Sig.TIMEOUT false = some DONE
    ∧ variantStep VALIDATING Sig.TIMEOUT false = some ESCALATED
    ∧ settle DONE ≠ settle ESCALATED := by
  decide

/-- ... and the difference is confined to that single edge — the variant is otherwise the canon,
    so it is not some wholesale different protocol but a minimal adequate perturbation. -/
theorem variant_agrees_off_validating_timeout :
    (allSt.all (fun s => allSig.all (fun g =>
      ((s == VALIDATING) && (g == Sig.TIMEOUT)) ||
      [false, true].all (fun b => canonStep s g b == variantStep s g b)))) = true := by
  decide

/-! ### §26.9(b): the skeleton/decoration cut — OVERDUE is a free decoration, not a forced state

Adequacy pins a minimality-forced SKELETON (the backbone every adequate protocol shares, grounded in
the four §14.2 defect types: initiation, accept→work, deliver→validate, pass→complete, block→report,
challenge→dispute, accept-challenge→re-offer, cancel→abandon, re-ASSIGN→offer — plus the
issuer's own waiting state, ESCALATED, forced by IC exactly as CANCELLING is: TEN forced states).
The design-freedom is confined to DECORATIONS on it. OVERDUE is one such: the timeout INTERMEDIATE, and
a protocol may route every first-timeout DIRECTLY to ESCALATED, omitting OVERDUE, and stay adequate
(deadlock-free + finite) — the `noOverdue` table below (a uniform relabeling of OVERDUE→ESCALATED over
the timeout cells; machine-checked on finiteness, full adequacy argued). With `variant` (the free
timeout destination) and the argued `max_iterations` (the rework-loop bound → REWORKING), this confines
the underdetermination to the decoration cells; the ten-state backbone is canonical up to behavioural
equivalence (a lower bound, argued — not machine-checked). NB ESCALATED is NOT itself a decoration (it is IC-forced, below) — it is a
forced state: it is separated from ABANDONED only by the settlement mode (both V=⊥), a free observable. -/

def noOverdueStep (s : St) (sig : Sig) (canRework : Bool) : Option St :=
  match canonStep s sig canRework with
  | some OVERDUE => some ESCALATED      -- first timeout goes direct to escalation; no intermediate
  | other => other

/-- The OVERDUE-free protocol is still adequate on the finiteness axis: every non-terminal except
    IDLE still times out. So OVERDUE is not forced by deadlock-freedom. -/
theorem noOverdue_still_timeout_defined :
    (allSt.all (fun s => isTerminal s || (s == IDLE) ||
        (noOverdueStep s Sig.TIMEOUT false).isSome)) = true := by
  decide

/-- ... and in it OVERDUE is never a target — no cell maps to it — so it is genuinely omitted, an
    unreachable (hence removable) state. The forced backbone cannot contain OVERDUE. -/
theorem noOverdue_omits_overdue :
    (allSt.all (fun s => allSig.all (fun g =>
      [false, true].all (fun b => noOverdueStep s g b != some OVERDUE)))) = true := by
  decide

/-- The canon, by contrast, DOES reach OVERDUE (e.g. from EXECUTING on timeout) — so OVERDUE is a
    decoration the canon adds, not a state adequacy forces: two adequate protocols, one with the
    intermediate and one without. -/
theorem canon_reaches_overdue :
    canonStep EXECUTING Sig.TIMEOUT false = some OVERDUE := by decide

/-! ### ESCALATED is NOT a decoration — forced by IC, the way CANCELLING is (§14.3-bis)

This section used to read the other way, and the reading was right about a machine in which the
ISSUER owes no answer. In that machine ESCALATED is separated from ABANDONED only by the settlement
mode (both carry V = ⊥), and folding it in gives up an *attribution* distinction, not a channel.

It is not that machine. ESCALATED is the issuer's waiting state: the executor stopped, and the
decision — raise the bound, change the criteria, or close it — is his. `noEscalatedStep` still
`decide`s deadlock-free, because deadlock-freedom is not the axis this state sits on. What the fold
removes is the CHANNEL through which the issuer answers: every act out of ESCALATED lands on
ABANDONED instead, so the exhausted-rework path settles with nobody asked. That is the *same*
grounding §26.9(b) gives CANCELLING — "forced by IC (Inv-4), not by deadlock; what holds it in the
skeleton is the executor's CONFIRM_CANCEL acknowledgment" — with the parties swapped. The theorems
below are kept because what they check is still true and still worth checking: the fold survives the
finiteness axis. They no longer witness REMOVABILITY, and the forced backbone is ten states, not
nine, with OVERDUE the one remaining free timeout-geometry decoration. -/

def noEscalatedStep (s : St) (sig : Sig) (canRework : Bool) : Option St :=
  match canonStep s sig canRework with
  | some ESCALATED => some ABANDONED     -- fold the attention terminal into the cancel terminal
  | other => other

theorem noEscalated_still_timeout_defined :
    (allSt.all (fun s => isTerminal s || (s == IDLE) ||
        (noEscalatedStep s Sig.TIMEOUT false).isSome)) = true := by
  decide

theorem noEscalated_omits_escalated :
    (allSt.all (fun s => allSig.all (fun g =>
      [false, true].all (fun b => noEscalatedStep s g b != some ESCALATED)))) = true := by
  decide

/-- The canon reaches ESCALATED (e.g. an exhausted validation loop, corner-#3 target) — so the fold
    above genuinely removes a state the canon has, rather than one it never reaches. What it removes
    is a CHANNEL, not a decoration: this is the twin of `canon_reaches_overdue`, and the two differ
    exactly where the section header says they do (§14.3-bis — OVERDUE carries no FM and no IC and
    is free; ESCALATED is held by IC, as CANCELLING is, with the parties swapped). -/
theorem canon_reaches_escalated :
    canonStep VALIDATING FAIL false = some ESCALATED := by decide

/-! ### §26.9(b): a forced skeleton exit is load-bearing — a canon-internal reachability witness

    SCOPE, honestly. The forcedness of the ten-state skeleton over *every* adequate protocol is an
    argued lower bound (a universal over an unbounded protocol class + semantic FM-hypotheses, outside
    `decide`) — this does NOT machine-check that. It checks the weaker **canon-internal necessary
    condition**: a forced exit is load-bearing for the canon's own success-reachability. Illustrated on
    the cleanest case, DELIVER (EXECUTING → VALIDATING): removing it leaves DONE unreachable from
    EXECUTING. It is NOT uniform — the catch-alls (timeout → DONE(auto_pass), re-ASSIGN → OFFERED) give
    alternate DONE-paths for some other exits (PASS, RESOLVE_BLOCK), so their load-bearingness is not a
    pure reachability fact. This witness corroborates the argued forcedness at one clean point; it is
    not the forcedness theorem. -/

def succsC (step : St → Sig → Bool → Option St) (s : St) : List St :=
  (allSig.filterMap (fun g => step s g false)) ++ (allSig.filterMap (fun g => step s g true))

def reachN (step : St → Sig → Bool → Option St) : Nat → List St → List St
  | 0, fr => fr
  | Nat.succ n, fr =>
      let nxt := (fr.flatMap (succsC step)).filter (fun t => !(fr.contains t))
      if nxt.isEmpty then fr else reachN step n (fr ++ nxt)

def reachesDONE (step : St → Sig → Bool → Option St) (s : St) : Bool :=
  (reachN step 12 [s]).contains DONE

/-- The canon table with EXECUTING's DELIVER exit removed. -/
def noDeliver (s : St) (g : Sig) (b : Bool) : Option St :=
  match s, g with | EXECUTING, DELIVER => none | _, _ => canonStep s g b

/-- In the canon, DONE is reachable from EXECUTING; removing the forced DELIVER exit strands it. So
    DELIVER is load-bearing for success-reachability (a necessary condition for its being a forced
    skeleton edge — not the over-all-protocols forcedness itself). -/
theorem canon_exec_reaches_done : reachesDONE canonStep EXECUTING = true := by decide
theorem nodeliver_strands_done : reachesDONE noDeliver EXECUTING = false := by decide

/-! ### §26.9(b) INNER: per-edge forced/free classification over the FIXED canonical alphabet

This upgrades the single `nodeliver_strands_done` witness to a per-edge classification. Each
signal-destination cell is graded on two axes (below): whether its EXISTENCE is forced (a non-timeout
adequacy source — an FM channel, an invariant, or the transaction role — vs. only exit-existence, the
free timeout/retry cells witnessed above: OVERDUE, `variant`, `max_iterations` — ESCALATED left
that list, §14.3-bis), and whether
its DESTINATION is forced (some are existence-forced but destination-FREE — the resume-vs-re-consent
decorations). Forced edges carry a canon-INTERNAL necessary-condition witness. This is the INNER
(fixed-alphabet, finite) statement; the OUTER frame (undelimited alphabets/observables) stays the
boundary of the first kind (§26.9 "the wall").

HONEST CEILING (held visible): each theorem below is a canon-INTERNAL necessary condition — removing the
edge degrades the CANON's own adequacy. The OUTER universal — "necessary ⟹ forced over EVERY adequate
protocol" — is a universal over an unbounded protocol class + semantic FM-hypotheses, outside `decide`;
it stays ARGUED, exactly as the ten-state forcedness does.

TWO STRENGTH TIERS (orthogonal to the a/b/c FUNCTION split — do not conflate them):
 • FATAL — removal makes the target UNREACHABLE (the strong witness): ASSIGN, BLOCK, CHALLENGE, CANCEL,
   DELIVER. These pin the initiation, the FM channels, and the terminals.
 • SOLE/GENUINE-PROVIDER — the target stays reachable via a catch-all, so removal is NOT fatal; the
   witness is only that the edge is the sole content/genuine provider of its function: ACCEPT, and all of
   kind (b) and kind (c). For kind (b) this means EXISTENCE-in-canon, with the DESTINATION free (the
   resume-vs-re-consent decoration). This weaker tier is the content, not a defect.
FAIL is FREE (destination), symmetric to kind (b): a revision (re-ASSIGN from VALIDATING) supplies a
reject-by-revision path, so adequacy does not pin FAIL's non-rework destination — unlike PASS, whose
kind-(c) genuineness witness has no non-degenerate substitute. "Free cells" is therefore LARGER than the
timeout geometry + retry bound: it also contains the kind-(b)/FAIL destination freedom — matching the
canon's own decoration hedge, not overriding it. -/

def dropEdge (f : St → Sig → Bool → Option St) (s0 : St) (sig0 : Sig) :
    St → Sig → Bool → Option St :=
  fun s sig b => if (s == s0) && (sig == sig0) then none else f s sig b

def dropSig (f : St → Sig → Bool → Option St) (sig0 : Sig) :
    St → Sig → Bool → Option St :=
  fun s sig b => if sig == sig0 then none else f s sig b

def reaches (f : St → Sig → Bool → Option St) (src tgt : St) : Bool :=
  (reachN f 12 [src]).contains tgt

/-- The three universal catch-alls (ASSIGN = re-ASSIGN/revision, CANCEL, TIMEOUT) are present on nearly
    every state and are NOT content recovery — they must be excluded when asking whether a CONTENT
    signal is the sole provider of a transition (else re-ASSIGN masks every in-contract edge, the
    non-uniformity the file's DELIVER note already flags). -/
def isCatchAll (g : Sig) : Bool := (g == ASSIGN) || (g == CANCEL) || (g == Sig.TIMEOUT)

/-! KIND (a) — channel-existence: the FM's target state goes UNREACHABLE when the edge is cut
    (reachability-fatal). ASSIGN (initiation), BLOCK (blocker channel), CHALLENGE (dispute channel);
    DELIVER is `nodeliver_strands_done` above. ACCEPT is NOT reachability-fatal (the
    CHALLENGE→REJECT_CHALLENGE detour reaches EXECUTING) — the file's non-uniformity — so its honest
    witness is sole-CONTENT-provider of the consent edge. -/

theorem canon_idle_reaches_validating : reaches canonStep IDLE VALIDATING = true := by decide
theorem noAssign_strands_start :
    reaches (dropEdge canonStep IDLE ASSIGN) IDLE VALIDATING = false := by decide

theorem canon_reaches_blocked : reaches canonStep IDLE BLOCKED = true := by decide
theorem noBlock_strands_blocked :
    reaches (dropSig canonStep BLOCK) IDLE BLOCKED = false := by decide

theorem canon_reaches_challenged : reaches canonStep IDLE CHALLENGED = true := by decide
theorem noChallenge_strands_challenged :
    reaches (dropSig canonStep CHALLENGE) IDLE CHALLENGED = false := by decide

/-- CANCEL used to be reachability-FATAL for the ABANDONED terminal — its only in-edges ran through
    CANCELLING, whose only in-edges were the CANCEL cells. It no longer is, and the reason is exactly
    §14.3-bis: ESCALATED is a live state, so Inv-5 gives it a timeout, and the issuer's silence
    settles the node in ABANDONED without any CANCEL. So CANCEL drops one tier — from *fatal* to
    *sole genuine provider*: what is lost by cutting it is not the terminal but the ACKNOWLEDGED and
    authoritative route to it (CONFIRM_CANCEL carries the in-flight state, Thm 11), leaving only the
    degenerate one where nobody answered. That is the same tier, and the same reason, §26.9(b)
    already records for PASS (DONE stays reachable by auto_pass) — the enumeration is unchanged in
    shape, and one cell moved within it. -/
theorem canon_reaches_abandoned : reaches canonStep IDLE ABANDONED = true := by decide
/-- …and what survives without CANCEL is the DEGENERATE route only: the issuer's silence, which is
    the single remaining cell that opens the handshake. Stated cell-wise rather than by reachability
    because that is the content — every OTHER state loses its way in. -/
theorem noCancel_keeps_the_silence :
    dropSig canonStep CANCEL ESCALATED Sig.TIMEOUT false = some CANCELLING := by decide

theorem noCancel_leaves_only_the_silence :
    (allSt.all (fun s => (s == ESCALATED) || (s == CANCELLING) || allSig.all (fun g =>
      [false, true].all (fun b =>
        dropSig canonStep CANCEL s g b != some CANCELLING)))) = true := by decide

/-- CONTRACT-CHANGE → OFFERED is Inv-1-FORCED (re-consent), over every adequate protocol — a changed
    contract may not silently bind a working node (§14.4). Two edges carry a contract change and are thus
    destination-FORCED, NOT free decorations: re-ASSIGN (revision — `Fsm.reassign_to_offered`) and
    ACCEPT_CHALLENGE (which by definition delivers `new_spec`, §14.2 — the unconditional instance of the
    same phenomenon that makes a contract-changing RESOLVE_BLOCK route to OFFERED). The *existence* of
    revision is a separate argued question; the *destination*, when the edge is present, is pinned. -/
theorem canon_reassign_to_offered :
    (allSt.all (fun s => !(isReassignable s) || (canonStep s ASSIGN false == some OFFERED))) = true := by
  decide
theorem acceptChallenge_dest_inv1_forced : canonStep CHALLENGED ACCEPT_CHALLENGE false = some OFFERED := by
  decide

/-- ACCEPT is the sole CONTENT edge taking OFFERED to work (catch-alls excluded). NOTE (strength): like
    every sole-content/genuine-provider witness below (kind b, kind c), this is NOT reachability-fatal —
    EXECUTING stays reachable via the CHALLENGE→REJECT_CHALLENGE detour. It witnesses that ACCEPT is the
    unique CONSENT edge, not that its removal is fatal. -/
theorem accept_sole_content_consent :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep OFFERED g b == some EXECUTING) || (g == ACCEPT)))) = true := by decide
-- ...and ACCEPT is NOT fatal: EXECUTING stays reachable after its removal, via the
-- CHALLENGE→REJECT_CHALLENGE detour — the positive half of the sole/genuine-provider strength tier
-- (measured, not asserted; the same non-fatality holds for kind (b)/(c) targets via their catch-alls).
set_option maxRecDepth 4000 in
theorem accept_not_fatal :
    reaches (dropEdge canonStep OFFERED ACCEPT) IDLE EXECUTING = true := by decide

/-! KIND (b) — resolution: the edge's EXISTENCE is forced (the source must have some resolution exit,
    else the FSM-deadlock defect "stuck in BLOCKED/CHALLENGED", §14.2). The DESTINATION splits: it is
    FREE — the resume-vs-re-consent decoration the canon names (§26.9(b) l.1773) — ONLY for the edges that
    carry NO contract change: **RESOLVE_BLOCK (pure-unblock)** and **REJECT_CHALLENGE** (the spec stands).
    ACCEPT_CHALLENGE is NOT here — it delivers a new spec ⟹ Inv-1-forced to OFFERED (above). What is
    machine-checked is the weaker, honest fact: each edge is the sole CONTENT provider of the source's
    progress transition IN THE FLAT CANON (catch-alls {ASSIGN, CANCEL, TIMEOUT} excluded — re-ASSIGN is a
    REVISION; excluding it is a STIPULATION whose lifting IS the destination-forcedness question). The
    sole-content witness for ACCEPT_CHALLENGE is kept as its EXISTENCE fact; its destination is pinned by
    `acceptChallenge_dest_inv1_forced`, not free. -/

theorem resolveBlock_sole_content_resume :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep BLOCKED g b == some EXECUTING) || (g == RESOLVE_BLOCK)))) = true := by
  decide

/-- ACCEPT_CHALLENGE is the sole content edge into OFFERED from CHALLENGED (its EXISTENCE fact); its
    DESTINATION is Inv-1-forced (`acceptChallenge_dest_inv1_forced`), NOT the free kind-(b) decoration. -/
theorem acceptChallenge_sole_content_reoffer :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep CHALLENGED g b == some OFFERED) || (g == ACCEPT_CHALLENGE)))) = true := by
  decide

theorem rejectChallenge_sole_content_resume :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep CHALLENGED g b == some EXECUTING) || (g == REJECT_CHALLENGE)))) = true := by
  decide

/-! KIND (c) — genuineness / IC: a catch-all keeps the terminal reachable (removal NOT fatal), so the
    witness is that only the DEGENERATE (timeout/inaction) route into the terminal survives removal. -/

/-- Cut PASS and the ONLY edge into DONE is the VALIDATING timeout (auto_pass, issuer inaction) — no
    GENUINE acceptance edge remains. -/
theorem noPass_only_autopass_into_done :
    (allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
      !((dropEdge canonStep VALIDATING PASS) s g b == some DONE)
      || ((s == VALIDATING) && (g == Sig.TIMEOUT)))))) = true := by decide
theorem canon_pass_is_genuine : canonStep VALIDATING PASS false = some DONE := by decide

/-- Cut CONFIRM_CANCEL and the ONLY edge into ABANDONED is the CANCELLING timeout — the in-flight report
    (Thm 11 provenance) and the executor's acknowledgment (IC, Inv-4) are lost. -/
theorem noConfirm_only_timeout_into_abandoned :
    (allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
      !((dropEdge canonStep CANCELLING CONFIRM_CANCEL) s g b == some ABANDONED)
      || (g == Sig.TIMEOUT))))) = true := by decide
theorem canon_confirm_is_genuine : canonStep CANCELLING CONFIRM_CANCEL false = some ABANDONED := by decide

/-! ### S1 — CANCELLING is forced by IC, NOT by deadlock (why it is skeleton and OVERDUE is not)

A ONE-STEP cancel (CANCEL → ABANDONED directly; no CANCELLING, no CONFIRM_CANCEL) is still deadlock-free
+ finite — so on the SAME finiteness axis on which the file witnesses OVERDUE removable,
CANCELLING is ALSO removable. Hence CANCELLING's forcedness is NOT deadlock: it is IC (the CONFIRM_CANCEL
kind-(c) witness above — the executor acknowledges and reports in-flight state). OVERDUE has
no FM/IC attached (pure timeout geometry) and are genuinely free; CANCELLING is grounded, so it is
skeleton. This makes precise the file's "grounded in the four defect types" as a PER-CELL basis. -/

def oneStepCancel (s : St) (sig : Sig) (canRework : Bool) : Option St :=
  match s, sig with
  | CANCELLING, _ => none                                       -- CANCELLING no longer exists
  | _, CANCEL => if isTerminal s then none else some ABANDONED  -- cancel settles in one step
  -- …and the issuer's silence settles in one step too, for the same reason: in a protocol with no
  -- handshake there is nothing for it to open, so it goes straight to the settlement.
  | ESCALATED, Sig.TIMEOUT => some ABANDONED
  | _, _ => canonStep s sig canRework

theorem oneStepCancel_still_timeout_defined :
    (allSt.all (fun s => isTerminal s || (s == IDLE) || (s == CANCELLING) ||
        (oneStepCancel s Sig.TIMEOUT false).isSome)) = true := by decide
theorem oneStepCancel_omits_cancelling :
    (allSt.all (fun s => allSig.all (fun g =>
      [false, true].all (fun b => oneStepCancel s g b != some CANCELLING)))) = true := by decide

/-! NEGATIVE CONTROLS — the classification shapes can come out the OTHER way, so the greens above are
    not vacuous. -/

theorem control_reaches_nonvacuous : reaches canonStep IDLE DONE = true := by decide
/-- The sole-content-provider shape with the WRONG signal (CHALLENGE, which goes to CHALLENGED not
    EXECUTING) is FALSE — the `.all` genuinely discriminates. -/
theorem control_sole_content_false :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep OFFERED g b == some EXECUTING) || (g == CHALLENGE)))) = false := by
  decide

end GFSO.FsmCanon
