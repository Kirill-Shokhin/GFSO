/-
  GFSO — the log kernel: what the missed-bound reading and the general sentences carry (§13.4). One module per
  reading so each is checked by its own Lean process (every reading in one file exhausted a 32 GB machine).
-/
import GFSO.LogLanguageAgrees  -- chained, not needed: the heavy log-kernel modules build one after another

namespace GFSO.LogLanguage
open GFSO.Fsm GFSO.Fsm.Sig W

set_option maxRecDepth 100000
set_option maxHeartbeats 0

/-- With the lapse counted as a channel (`listed`), cells without exactly one outcome per reading — cells, not
    machines (`LogLanguageLapse`); ownerless, the edge clause `pInv8Edges` still bars the lapse. -/
theorem the_lapse_as_a_channel_leaves_cells_open :
    readings.map (fun rd => (notForced listed rd).length) = [0, 26, 19] := by decide +kernel
/-- The old reassignable set (`pRevision41`) forces the same: the lapse is unreachable. -/
theorem the_old_exception_is_idle : readings.all (fun rd => (notForced oldSet rd).length == 0) = true := by
  decide +kernel

/-- `base` alone — the signals' meanings, the general sentences, the reassignable set — leaves the machine open. -/
theorem general_sentences_leave_it_open :
    (notForced base none).length = 107 ∧ (reachable base none).length = 37 := by decide +kernel

end GFSO.LogLanguage
