# T10 — Search pass 3

Input: D2.md (D×7, Dep×13, V×38, N×7). Surface only genuinely new content absent from D2.

---

## New holes

**H1 — HAF fan operational monitoring**
Mixing fans are declared a precondition for sensor representativeness (D5) but no component monitors their running state or raises an alarm on failure. D5's anomaly-detection logic is contingent on adequate airflow; a silent fan failure invalidates the spatial-sampling assumption with no alert.
*Falsifier*: One mixing-fan bank fails; D5 continues accepting single-point readings as representative; a 4 °C air-temperature gradient across spans goes undetected; V21 cannot be satisfied by sensor placement alone when airflow is absent.

**H2 — D4 → D3 safe-state command path (missing Dep seam)**
D4 "activates documented safe-state fallbacks" but there is no listed Dep from D4 to D3. Without an explicit enforcement channel, D4 can raise an alarm while D3 continues executing normal arbitration. The fallback activation mechanism — who writes the actuator override and how — is unspecified.
*Falsifier*: D4 fires a heating-saturation alarm (V12); D3, receiving no override signal, leaves a vent at 30 % aperture that was commanded by RH control; indoor T continues to fall below LTL.

**H3 — Outdoor sensor validation (stuck-but-communicating)**
V32 covers outdoor-station communication loss. D5 validates indoor sensors exhaustively. But a plausible-but-wrong outdoor reading — an anemometer iced over reading 2 m/s in a 15 m/s gust, or a pyranometer soiled to read zero on a sunny day — passes through D7 silently. D7 has no D5-equivalent for outdoor data quality.
*Falsifier*: Anemometer ices over at 2 m/s; D7 passes 2 m/s to D3; D3 allows full vent aperture; gusts cause uncontrolled cold infiltration and structural loading with no alarm. Alternatively: pyranometer reads 0; D1 treats it as night; CO₂ injection and supplemental lighting fire in full midday sun; V24 violated.

**H4 — VPD active control response strategy**
V1 requires VPD within bounds simultaneously; D5 derives VPD; D1 and D3 receive VPD as context. But no D component or V criterion defines the control action when VPD itself is out of bounds: which actuator is commanded (raise T, lower RH, or a defined combination), at what priority relative to other CV controllers, and under what interlock constraints. VPD is treated as a read-only derived signal with no closed-loop response path.
*Falsifier*: Air T is at setpoint, RH is at setpoint, but their combination yields VPD = 2.6 kPa (above crop limit). Neither D2's T controller nor its RH controller sees a deviation; no controller responds; V1 fails silently while all per-CV readings are "in range."

**H5 — pH dosing equilibration lag / oscillation (distinct from V16 anti-windup)**
V16 requires no unbounded integral accumulation during actuator saturation and no overshoot on saturation recovery. But pH dosing in a buffered substrate has a physical dead-time (minutes to tens of minutes) between dose delivery and sensor stabilization regardless of saturation. A controller sampling faster than this lag repeatedly overdoses — not because of windup during saturation, but because the next sample still shows deviation before the dose has equilibrated. No V criterion addresses this dosing-interval or hold-after-dose requirement.
*Falsifier*: pH controller issues acid dose; re-samples after 30 s; pH still reads high (dose not equilibrated); issues second dose; cycle repeats; pH crashes below 4.5 before sensor reflects the overdose — the system was never at saturation and V16 does not capture this.

**H6 — Acid/base dosing pump delivery confirmation**
V20 mandates irrigation delivery confirmation at or downstream of the emitter. No equivalent criterion exists for acid/base dosing pumps. A stuck acid-dosing pump delivers nothing; the pH controller accumulates maximum demand; when the pump is manually freed, the first delivery event runs at full commanded rate.
*Falsifier*: Acid pump fails closed; pH controller demands maximum acid for 2 hours; pump mechanically clears; next enabled cycle delivers full accumulated dose; pH crashes from 6.0 to < 4.0 in one event.

**H7 — Cold irrigation water → root-zone temperature disturbance (missing cross-channel Dep)**
D2 controls root-zone T (floor heating / substrate pipes) and irrigation (moisture + EC + pH) as separate channels. A large irrigation event with cold feed water (winter mains at 4–8 °C) constitutes a thermal disturbance directly into the root zone that D2's root-zone T controller must absorb reactively with no feedforward. No Dep seam captures this intra-D2 cross-channel coupling.
*Falsifier*: Large morning deficit irrigation event delivers 5 °C water to a substrate at 20 °C root-zone setpoint; substrate T drops 3 °C in 12 min below LTL; floor heating saturates trying to recover; V12-analogue for root-zone (no dedicated saturation criterion) fires nothing.

**H8 — Thermal screen partial-closure RH stratification**
V15 covers RH management when the screen is fully closed at night. But at intermediate screen positions (e.g., 40–70 % closed for partial energy saving), the screen creates a stratification boundary: high-RH air is trapped below the screen while the gutter-level sensor reads the drier zone above or alongside. Disease conditions can form on the canopy without the sensor detecting them.
*Falsifier*: Screen at 60 % closure; gutter sensor reads 76 % RH; stagnant below-screen air reaches 94 % RH at canopy level; Botrytis pressure accumulates; V1 shows RH within bounds because the representative sensor is not below the screen.

---

## Coverage assessment

The eight holes above have distinct falsifiers not captured by any existing V criterion, Dep seam, or D component description. The existing 65-item basis is thorough; remaining candidates beyond these eight — boiler water-circuit management, municipal supply pressure, irrigation run-to-waste volume tracking, supplemental-lighting dark-period enforcement for photoperiod-sensitive crops, setpoint ramp-rate vs. actuator response — are either arguable sub-requirements of already-present items or would pull in N-excluded concerns. They are not listed as holes.
