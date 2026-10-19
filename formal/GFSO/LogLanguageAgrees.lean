/-
  GFSO — the log kernel, part 2: the readings give one machine, and it is the canon's table (§13.4). Split from
  `LogLanguage.lean` so each module is checked by its own Lean process (the kernel `decide` over all three readings
  in one file needs > 14 GB).
-/
import GFSO.LogLanguage

namespace GFSO.LogLanguage
open GFSO.Fsm GFSO.Fsm.Sig W

set_option maxRecDepth 100000
set_option maxHeartbeats 0

/-- The readings give one machine. -/
theorem readings_agree :
    machine full (some true) = machine full none ∧ machine full (some false) = machine full none := by
  decide +kernel

/-! ### The forced machine is the canon's table -/

/-- The canon state a record stands for: its open wait. The lapse (unreachable, `never_lapses`) is sent to
    OVERDUE, which `canonStep` never enters, so a lapse outcome cannot agree by accident. -/
def toSt : W → St
  | idle => St.IDLE | offer => St.OFFERED | work => St.EXECUTING | chal => St.CHALLENGED
  | W.block => St.BLOCKED | deliv => St.VALIDATING | hand => St.ESCALATED | lapse => St.OVERDUE
  | close => St.CANCELLING | done => St.DONE | aband => St.ABANDONED

/-- REWORKING folds to EXECUTING (`FsmCanon.canon_exec_rework_same`): the record does not carry the label
    (§13.4). -/
def foldRework : St → St
  | St.REWORKING => St.EXECUTING
  | s => s

/-- The table's bit: at REJECT_CHALLENGE it is the record's consent; elsewhere the input (FAIL's rounds remain). -/
def tableBit (r : Rec) (s : Sig) (b : Bool) : Bool := if s == REJECT_CHALLENGE then r.c else b

/-- **The forced machine is the canon's table**: on every reachable cell under every reading, the forced outcome
    mapped to its state is `FsmCanon.canonStep`'s. -/
theorem agrees_with_the_canon :
    readings.all (fun rd => (machine full rd).all (fun e =>
      e.2.map (fun x => toSt x.w)
        == (FsmCanon.canonStep (toSt e.1.1.w) e.1.2.1 (tableBit e.1.1 e.1.2.1 e.1.2.2)).map foldRework))
      = true := by
  decide +kernel

/-- **Authoritative cancellation added back changes no cell** under any reading: §12.12's three sentences carry it,
    here `pConfirm`, `decisionEntries`, `pReportsNeedVersion`. -/
theorem authority_is_derived :
    readings.all (fun rd => machine (full ++ [pClosingAuth]) rd == machine full rd &&
      (notForced (full ++ [pClosingAuth]) rd).length == 0) = true := by decide +kernel

end GFSO.LogLanguage
