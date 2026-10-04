/-
  GFSO — the log kernel: clause loads, owner the executor (§13.4). One module per reading so each is checked by its own
  Lean process (every reading in one file exhausted a 32 GB machine).
-/
import GFSO.LogLanguageLoadsNoOwner  -- chained, not needed: the heavy log-kernel modules build one after another

namespace GFSO.LogLanguage
open GFSO.Fsm GFSO.Fsm.Sig W

set_option maxRecDepth 100000
set_option maxHeartbeats 0

/-- Cells left open without each clause (`decisionEntries`, C1–C4), the executor owning the missed bound. -/
theorem loads_executor :
    [0, 1, 2, 3, 4].map (fun i => (notForced (without i) (some true)).length) = [11, 26, 27, 12, 26] := by
  decide +kernel

end GFSO.LogLanguage
