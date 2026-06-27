# BLIND JUDGE VERDICT — T10 / candidate D3

Reference: `complex/references/T10.md` (frozen gold). Candidate: one decomposition, origin stripped.
Scored categories: D (10), Dep (17), V (20), N (5). `Del`/authority not scored.

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Maintains all CV setpoints (air T, root-zone T, RH, CO₂, PAR, moisture/EC/pH) as functions of time-of-day and crop growth stage" | per-variable setpoints, day/night-differentiated target envelope |
| D2 | D | — | COVERED | "One closed-loop controller (PID or equivalent…) per controlled variable — air temperature, root-zone temperature…, RH, CO₂, PAR/DLI…, root-zone moisture + EC + pH" + D5 "drift-prone classes (RH, CO₂ NDIR, PAR quantum, soil EC, pH probe)" | the controlled variables are sensed/instrumented |
| D3 | D | — | COVERED | "root-zone temperature (floor heating or substrate pipes, independently sensed and separately actuated)" | heating actuator named (also air-heating plant in V12/V27) |
| D4 | D | — | COVERED | "When full vent aperture combined with full shading cannot maintain UTL" (V13); "Vent aperture is hard-constrained (in D3) by an outdoor anemometer threshold" (V23) | ventilation/cooling actuator |
| D5 | D | — | PARTIAL | "it switches to an alternative (heating-assisted drying, or temporary RH tolerance)" (V14); "calibrated minimum vent gap, heating-based drying" (V15) | dehumidify leg met (heat-vent drying). **Missing leg: a humidify actuator (fog/mist to raise RH when too dry)** — no humidifier named |
| D6 | D | — | COVERED | "CO₂ injection is active only when PAR exceeds the photosynthetic compensation point" (V24) | CO₂ enrichment actuator |
| D7 | D | — | COVERED | "The irrigation strategy maintains substrate moisture and EC within crop bounds" (V5); D2 "root-zone moisture + EC + pH (jointly…)" | irrigation/fertigation actuator |
| D8 | D | — | COVERED | "supplemental lighting extension is gated on DLI completion state for the day" (V29) | supplemental-lighting actuator |
| D9 | D | — | COVERED | "When the thermal screen is at an intermediate position (nominally 20–80% closed)" (V45); D3 "screen position vs. vent operability" | shade/thermal-screen actuator |
| D10 | D | — | COVERED | "The arbitration layer above individual controllers… providing a total priority ordering under combined stress" (D3) | distinct coordination/arbitration pass (Appendix scorer rule satisfied) |
| Dep-X1 | Dep | FM-2 | COVERED | "ventilation for RH drives T below LTL with no interlock" (Dep5) + D3 override of controller outputs | vent↔temperature coordinated by D3 interlock; borderline (no explicit heat+vent deadband, but the temp-actuator conflict + arbiter is named) |
| Dep-X2 | Dep | FM-2 | COVERED | "the design explicitly quantifies the vent-state at which CO₂ injection becomes ineffective and defines the fallback" (V4) | venting purges CO₂ + coordination rule |
| Dep-X3 | Dep | FM-2 | COVERED | "When outdoor dewpoint ≥ indoor dewpoint, the humidity strategy does not open vents for RH reduction; it switches to an alternative" (V14) | vent↔RH side-effect + rule |
| Dep-X3b | Dep | FM-2 | NOT-COVERED | | no night-thermal-screen↔heating radiative-retention coupling (screen lowers heating demand / don't over-fire under closed screen) |
| Dep-X4 | Dep | FM-2 | COVERED | "the design specifies an effective alternative (calibrated minimum vent gap, heating-based drying)" (V15) | heat→RH coupling acknowledged via deliberate heating-based drying |
| Dep-X5 | Dep | FM-2 | COVERED | "nighttime threshold exceedance does not fire the drip system and spike nocturnal RH" (V26) | irrigation→RH + interlock |
| Dep-X6 | Dep | FM-2 | COVERED | "the T control channel receives a feedforward offset or gain adjustment reflecting the thermal load from lighting (HPS ≈ 60% convective heat)" (V28) | lamp-heat↔temperature + feedforward |
| Dep-X7 | Dep | FM-2 | COVERED | "shading curtailment of natural light. A design where full shade closure shortens the photoperiod without supplemental compensation fails" (V6) | shade cuts the crop's light + compensation rule |
| Dep-X8 | Dep | FM-2 | COVERED | "injection during darkness, under heavy shading (>95% screen closure), or in empty-greenhouse mode is blocked" (V24) | CO₂ gated off without light (gate-off arc) |
| Dep-X9 | Dep | FM-1 | COVERED | "Each controller reads D5-validated sensor values and drives its primary actuator" (D2) | per-variable closed sensor→actuator binding |
| Dep-X10 | Dep | FM-1, FM-5 | COVERED | "All setpoint transitions (day/night, crop-stage advance, empty-greenhouse mode entry/exit) are governed by a single, DST-aware, leap-second-aware clock source shared across D1–D4" (Dep8) | coordinated multi-actuator transition regime |
| Dep-X11 | Dep | FM-2 | NOT-COVERED | | no evaporative/fog/pad cooling actuator, hence no latent-cooler RH-headroom gate |
| Dep-X12 | Dep | FM-2 | NOT-COVERED | | no evap/fog cooling → no "fog also humidifies / never co-run with humidifier" seam |
| Dep-X13 | Dep | FM-2 | NOT-COVERED | | CO₂ gated on light (Dep-X8) but no enable arc (raise/track CO₂ target when supplemental light on) — Appendix: no shared credit with Dep-X8 |
| Dep-X14 | Dep | FM-2 | COVERED | "When the thermal screen is fully closed at night, RH is managed without relying on full roof ventilation; the design specifies an effective alternative (calibrated minimum vent gap…)" (V15) | closed-screen trapped-RH + screen/vent-gap rule |
| Dep-X15 | Dep | FM-2 | NOT-COVERED | | no named humidify↔dehumidify deadband/mutual-exclusion (generic no-oscillation → V-I3, not Dep-X15) |
| Dep-X16 | Dep | FM-2 | COVERED | "Horizontal airflow fans must be operational as a precondition for sensor representativeness" (V21) + V39 "a 4°C cross-span temperature gradient to go undetected" | HAF mixing homogenizes the volume / single-point control invalid without it |
| V-I1 | V | FM-1 | COVERED | "At all sampled instants, all seven CVs… and derived VPD are within crop bounds simultaneously" (V1) | every variable continuously in-band |
| V-I2 | V | FM-2 | COVERED | "Prevents one controller's output from violating another CV's bounds" (D3) | global cross-coupling do-no-harm |
| V-I3 | V | FM-4 | COVERED | "no combination results in undefined behavior or oscillation" (V2) | aggregate stability / no hunt |
| V-I4 | V | FM-1 | COVERED | "An interlock independent of the crop control software… cuts CO₂ injection… when concentration exceeds 5 000 ppm" (V11) | inviolable hard-safety layer over comfort control |
| V-I5 | V | FM-2 | NOT-COVERED | | no energy/resource-waste-by-opposition predicate (no "don't waste energy on fighting actuators"); conflicts handled as out-of-band harm (V-I2)/stability (V-I3) only |
| V-I6 | V | FM-3 | COVERED | "the design specifies either a canopy-temperature sensor or a radiation-load correction model; control declared compliant while the canopy surface is 3–8°C above air T fails" (V30) | control on the canopy-experienced/representative value |
| V-I7 | V | FM-1 | COVERED | "tracks both instantaneous flux… and daily accumulated light integral… gated on DLI completion state for the day" (V29) | integrated DLI/photoperiod held over the day |
| V-I8 | V | FM-7 | NOT-COVERED | | no loop-liveness/watchdog/stall-detection predicate; D4's "remain operational when a controller fails" is safety-layer redundancy (V-E5-type), not a cycle watchdog |
| V-I9 | V | FM-2 | COVERED | "D3 resolves the conflict via a single, explicit aggregation rule (priority order, min-wins, or weighted blend) — last-write-wins is not acceptable" (D3) | single-writer/arbiter per shared actuator |
| V-E1 | V | FM-6 | COVERED | "When full vent aperture combined with full shading cannot maintain UTL, an overtemperature alarm fires with a documented crop-heat-stress threshold" (V13) | weather beyond actuator authority → declared response |
| V-E2 | V | FM-5 | COVERED | "using ramps (not steps) at transitions" (D1) | dawn/dusk transition handled with ramped setpoints |
| V-E3 | V | FM-4 | NOT-COVERED | | no fast-transient damping/rate-limit ("don't chase a passing cloud / gust / open door"); anti-windup (V16) is recovery overshoot, not transient filtering |
| V-E4 | V | FM-3 | COVERED | "The heating pipe temperature setpoint specifies a minimum pipe surface T relative to local air dewpoint during high-humidity conditions… condensation drip onto canopy from pipes below dewpoint fails" (V27) | dew-point/condensation-onset boundary + pre-emptive rule (also VPD control V41) |
| V-E5 | V | FM-6, FM-7 | COVERED | "All actuators have specified, tested, and documented fail-safe positions for power loss that prevent immediate crop loss" (V10) | power/equipment failure → fail-safe + alarm (V32, Dep15) |
| V-E6 | V | FM-5 | COVERED | "advances crop stage on schedule or operator confirmation" (D1); Dep11 crop-stage thresholds | bands change mid-run; regime ingests updated setpoints |
| V-E7 | V | FM-6 | COVERED | "On restoration of power following an outage, actuator re-energization follows a defined sequencing protocol preventing simultaneous conflicting demands" (V33) | cold-start/restart sequencing, ramp not step |
| V-F1 | V | FM-3, FM-1 | COVERED | "A single sensor failure (stuck, out-of-range, dropout) triggers a switch to a defined safe fallback value in D2 without propagating the faulty reading" (V9) | sensor fault/drift → guard (also V17, V38) |
| V-F2 | V | FM-3, FM-7 | COVERED | "When the CO₂ injection valve has been at maximum for a configurable hold period without the setpoint being reached, an 'injection saturation' alarm fires… the valve does not simply remain open indefinitely" (V25) | maxed actuator = fault, not steady state (also V12/V31/V36/V44) |
| V-F3 | V | FM-2 | COVERED | "providing a total priority ordering under combined stress" + "including the cold × humid × CO₂-depleted conflict" (D3) | multi-variable target conflict on one actuator → variable-priority order (Appendix scorer rule) |
| V-F4 | V | FM-1, FM-7 | COVERED | "allowing disease-enabling conditions to accumulate below the screen while the monitored reading shows compliance — fails" (V45); VPD control (V1/V41) | sustained in-band humidity → condensation/disease + VPD guard |
| N1 | N | — | NOT-COVERED | | no declaration that the crop climate recipe/setpoint envelope is a *given upstream input* (deriving the agronomy out of scope). cand N4 is recipe-adjacent but excludes crop scheduling, not recipe derivation |
| N2 | N | — | COVERED | "Pest and disease management: Biological control agents and pesticide application are out of scope. IN scope: any CV setpoint defined (partly) to prevent enabling conditions for disease" (cand N1) | pest/disease management excluded; climate owns only abiotic disease-prevention |
| N3 | N | — | NOT-COVERED | | no declaration that HVAC/actuator hardware is assumed installed/working (building/sizing out). cand N6 excludes only CO₂-source generation, not the actuator hardware plane |
| N4 | N | — | COVERED | "Grid / energy market optimization: Tariff-based demand-curtailment and peak-shifting are out of scope for the core regime" (cand N5) | grid/cost optimization excluded with invalidation trigger |
| N5 | N | — | COVERED | "Greenhouse structural design: Frame, glazing, and screen structural integrity are out of scope" (cand N3) | structure/glazing fixed given; in-scope mechanical limits retained |

## 6.2 Ballast list (distinct candidate points collapsing onto one reference item)

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| V-F2 | 10 | 9 | V25 (CO₂ sat), V12 (heating sat), V36 (lamp sat), V44 (root-zone sat), V31 (heating efficiency), V19 (CO₂ supply fail), V20 (emitter clog), V37 (under-leaching), Dep12 (trend→degradation alarms), Dep13 (CO₂ sat→D4) |
| V-F1 | 7 | 6 | V9 (fault isolation), V17 (calibration drift), V38 (NDIR positive-drift), V40 (outdoor plausibility), Dep3 (validated→controllers), Dep4 (validated→alarms), D5 (validation layer) |
| Dep-X16 | 4 | 3 | V21 (HAF precondition), V39 (HAF fan alarm/validity flag), Dep14 (HAF state→D5), D5 ("Requires adequate horizontal airflow … precondition") |
| V-E5 | 4 | 3 | V10 (fail-safe positions), V32 (outdoor-station comms fallback), Dep15 (D4→D3 safe-state override), D4 (alarm/safety layer) |
| V-I6 | 3 | 2 | V30 (canopy-temp correction), V21 (spatial sensing coverage), V22 (rain/soiling PAR cross-check) |
| Dep-X10 | 3 | 2 | Dep8 (single clock for transitions), Dep1 (setpoint propagation), Dep2 (astronomical day boundary) |
| V-E6 | 3 | 2 | D1 (crop-stage advance), Dep11 (crop-stage thresholds), V8 (schedule continuity at crop-stage transitions) |
| Dep-X6 | 2 | 1 | V28 (lighting heat in T control), Dep10 (lighting state→D2 T feedforward) |
| V-E2 | 2 | 1 | D1 (ramps at transitions), V7 (DIF constraint) |
| V-I4 | 2 | 1 | V11 (CO₂ worker-safety cut-off), V23 (wind-speed vent hard limit) |
| D7 | 2 | 1 | D2 (root-zone moisture+EC+pH controller), V5 (water/EC balance) |
| D2 | 2 | 1 | D2 (per-CV controllers), D7 (weather-station outdoor sensing) |

**Total ballast = 32.**

## 6.3 Unmatched candidate points (map to no reference item — human review, not scored)

| candidate phrase (verbatim) | flag |
|---|---|
| V3 "Heating and cooling setpoints are demonstrably achievable by installed plant on the site's design-day outdoor conditions; the design includes a capacity calculation" | UNMATCHED — human review |
| V18 "Screen position, vent aperture, valve states, and acid/base dosing pump delivery are independently verified against end-stops, torque sensors, secondary encoders, or flow confirmation" | UNMATCHED — human review |
| V34 "When the independently verified actuator position persistently diverges from the commanded position… the affected channel is flagged as manually overridden… automatic control on that channel is suspended" | UNMATCHED — human review |
| V35 "D3 evaluates and enforces interlocks against intermediate actuator positions throughout the full travel stroke, not only at the commanded final position" | UNMATCHED — human review |
| V42 "The pH controller enforces a minimum inter-dose interval or explicit hold-after-dose period sufficient for substrate equilibration… before issuing a subsequent dose command" | UNMATCHED — human review |
| V43 "Dosing pump delivery is independently confirmed by a flow sensor or by a pH rate-of-change cross-check… a stuck pump that accumulates maximum demand without confirmed delivery triggers an alarm" | UNMATCHED — human review |
| Dep7 "Actuator-state bus → D3 (real-time positions): D3 receives current vent aperture, screen position (verified, not commanded)… from independent position feedback" | UNMATCHED — human review |
| Dep16 "D2 irrigation channel → D2 root-zone T channel (cold-water disturbance feedforward)… so the root-zone T controller can pre-compensate" | UNMATCHED — human review |
| D6 "Logging / historian: Time-series storage of all sensor readings, actuator states, and derived metrics… at ≥ 1 min resolution" (as a standalone component) | UNMATCHED — human review |
| cand N2 "Fertilizer chemistry (N:P:K recipe): Nutrient formulation is out of scope. IN scope: EC and pH as irrigation control targets" | UNMATCHED — human review |
| cand N4 "Long-term crop scheduling and harvest planning… out of scope. IN scope: current crop-stage setpoints and their automatic advancement" | UNMATCHED — human review |
| cand N6 "CO₂ source generation: Boiler management, cylinder logistics, and flue-gas treatment are out of scope. IN scope: supply availability monitoring" | UNMATCHED — human review |
| cand N7 "Worker access and building management… out of scope. IN scope: the CO₂ worker-safety cut-off interlock (V11)" | UNMATCHED — human review |

**Total unmatched candidate points = 13.**

## 6.4 Score block

```
COVERAGE (fully-COVERED / total):
  by category:   D = 9/10   Dep = 12/17   V = 17/20   N = 3/5
  by FM tag:     FM-1 = 7/7   FM-2 = 13/19   FM-3 = 4/4   FM-4 = 1/2   FM-5 = 3/3   FM-6 = 3/3   FM-7 = 3/4
  PARTIAL counts: D = 1   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 32
  unmatched candidate points (human-review flag):    total = 13
```
