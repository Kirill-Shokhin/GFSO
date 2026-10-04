/-
  GFSO — the missed bound as a channel admits no second machine (§13.4).

  `LogLanguage.the_lapse_as_a_channel_leaves_cells_open` counts the cells `listed` leaves without exactly one outcome;
  the count mixes cells with several outcomes and cells with none. Here, under every owner reading: outside the
  lapse, the outcomes not entering it are exactly `full`'s, and the lapse's timeout admits none. The routes into the
  decision are read as `isPartyWait` reads them — the alternative reading (§12.12).
-/
import GFSO.LogLanguageReopen  -- chained, not needed: the heavy log-kernel modules build one after another

namespace GFSO.LogLanguage.Lapse
open GFSO.Fsm GFSO.Fsm.Sig GFSO.LogLanguage W

set_option maxRecDepth 100000
set_option maxHeartbeats 0

def intoLapse (o : Option Rec) : Bool := (o.map (·.w)) == some lapse

/-- Outside the lapse, dropping the outcomes that enter it leaves exactly `full`'s forced outcome. -/
theorem the_lapse_as_a_channel_admits_no_second_machine :
    readings.all (fun rd => (cells listed rd).all (fun ⟨r, s, b⟩ =>
      r.w == lapse || ((cellOuts listed rd r s b).filter (fun o => !intoLapse o)) == cellOuts full rd r s b))
      = true := by decide +kernel

/-- …and the lapse's timeout admits no outcome: a machine reaching the lapse breaks Inv-5's first clause. -/
theorem the_lapse_has_no_timeout :
    readings.all (fun rd => (cells listed rd).all (fun ⟨r, s, b⟩ =>
      !(r.w == lapse && s == Sig.TIMEOUT) || (cellOuts listed rd r s b).isEmpty)) = true := by decide +kernel

end GFSO.LogLanguage.Lapse
