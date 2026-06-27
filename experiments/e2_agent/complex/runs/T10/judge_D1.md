# BLIND JUDGE VERDICT — T10 / candidate D1

> Methodology note (auditable): FM-tag denominators are built from each reference V item's FM tag, the §2
> Dep FM-mapping note (Dep-X9/X10 = FM-1; Dep-X10 also FM-5; actuator-couplings Dep-X1–X8, X11–X16 = FM-2),
> and the §7 FM table (which places NEGLECTED N1–N5 in the FM-1 preclusion set). N1–N5 therefore count toward
> the FM-1 denominator.

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Maintains all CV setpoints (T, RH, CO₂, PAR, moisture/EC) as functions of time-of-day and crop growth stage" | per-variable bands, day/night differentiated |
| D2 | D | — | COVERED | "One closed-loop controller (PID or equivalent...) per controlled variable — air temperature, RH, CO₂, PAR/DLI..., root-zone moisture + EC... Each controller reads validated sensor values" | sensing of all variables present (also D5 sensor classes, D7 outdoor weather) |
| D3 | D | — | COVERED | "When the heating plant reaches maximum rated output and indoor T remains below LTL" (V12) | heating named as the actuator raising T below band |
| D4 | D | — | COVERED | "When full vent aperture combined with full shading cannot maintain UTL, an overtemperature alarm fires" (V13) | ventilation/cooling actuator (vents) named |
| D5 | D | — | PARTIAL | "the design specifies an effective alternative (calibrated minimum vent gap, heating-based drying)" (V15) | dehumidify leg met; MISSING humidify leg (raise RH when too dry — fog/mist); RH controller (D2) is generic, no humidification actuator named |
| D6 | D | — | COVERED | "CO₂ injection is active only when PAR exceeds the photosynthetic compensation point" (V24) | CO₂ enrichment actuator |
| D7 | D | — | COVERED | "The irrigation strategy maintains substrate moisture and EC within crop bounds... includes a drainage-fraction target" (V5) | irrigation/fertigation actuator to root-zone target |
| D8 | D | — | COVERED | "supplemental lighting extension is gated on DLI completion state for the day" (V29) | supplemental lighting actuator |
| D9 | D | — | COVERED | "When the thermal screen is closed at night" (V15); "shading curtailment of natural light" (V6) | shade/thermal screen actuator |
| D10 | D | — | COVERED | "The arbitration layer above individual controllers... providing a total priority ordering under combined stress" (D3) | coordination/arbitration logic named distinctly |
| Dep-X1 | Dep | FM-2 | NOT-COVERED | | no named heat↔vent temperature deadband/sequencing; only the aggregate coupling-completeness (V2) and combined-stress priority (V-F3) |
| Dep-X2 | Dep | FM-2 | COVERED | "the design explicitly quantifies the vent-state at which CO₂ injection becomes ineffective and defines the fallback. A design that sets 1 200 ppm with vents fully open fails" (V4) | venting purges/leaks CO₂ + coordination rule |
| Dep-X3 | Dep | FM-2 | COVERED | "the humidity strategy does not open vents for RH reduction; it switches to an alternative" (V14) | vent↔RH coupling + rule coupling vent to humidity target |
| Dep-X3b | Dep | FM-2 | NOT-COVERED | | no night-screen radiative-retention↔heating coupling |
| Dep-X4 | Dep | FM-2 | NOT-COVERED | | no heat→RH coupling named |
| Dep-X5 | Dep | FM-2 | COVERED | "the interlock is in the control execution path (not advisory) so nighttime threshold exceedance does not fire the drip system and spike nocturnal RH" (V26) | irrigation→RH + timing rule against humidity state |
| Dep-X6 | Dep | FM-2 | COVERED | "the T control channel receives a feedforward offset or gain adjustment reflecting the thermal load from lighting (HPS ≈ 60 % convective heat)" (V28) | lamp heat coupled into temperature loop |
| Dep-X7 | Dep | FM-2 | COVERED | "accounting for both supplemental-lighting extension and shading curtailment of natural light. A design where full shade closure shortens the photoperiod without supplemental compensation fails" (V6) | shade cuts needed light + compensation rule |
| Dep-X8 | Dep | FM-2 | COVERED | "injection during darkness or under heavy shading (> 95 % screen closure) is blocked" (V24) | CO₂ gated off without light |
| Dep-X9 | Dep | FM-1 | COVERED | "Each controller reads validated sensor values and drives its primary actuator" (D2) | closed sensor→actuator loop per variable |
| Dep-X10 | Dep | FM-1, FM-5 | COVERED | "using ramps (not steps) at transitions" (D1) | all CV setpoints reconfigure together through the swing via ramped setpoints |
| Dep-X11 | Dep | FM-2 | NOT-COVERED | | no evaporative/fog cooling actuator named at all |
| Dep-X12 | Dep | FM-2 | NOT-COVERED | | no evap/fog→RH coupling (no fog actuator) |
| Dep-X13 | Dep | FM-2 | NOT-COVERED | | only the gate-off arc (Dep-X8); no light-on raises/enables-CO₂-target enable arc |
| Dep-X14 | Dep | FM-2 | COVERED | "When the thermal screen is closed at night, RH is managed without relying on full roof ventilation; the design specifies... (calibrated minimum vent gap, heating-based drying)" (V15) | closed-screen humidity + screen-gap rule |
| Dep-X15 | Dep | FM-2 | NOT-COVERED | | humidify side not named; no humidify↔dehumidify deadband/mutual-exclusion |
| Dep-X16 | Dep | FM-2 | COVERED | "Requires adequate horizontal airflow (mixing fans) as a precondition for sensor representativeness; design must include HAF fan operation" (D5) | homogenizing-circulation seam named (mechanism), not merely the V-I6 outcome |
| V-I1 | V | FM-1 | COVERED | "At all sampled instants, all five CVs... and the derived VPD are within crop bounds simultaneously" (V1) | every-variable-in-band |
| V-I2 | V | FM-2 | COVERED | "Prevents one controller's output from violating another CV's bounds" (D3) | global cross-coupling do-no-harm |
| V-I3 | V | FM-4 | COVERED | "no combination results in undefined behavior or oscillation" (V2) | aggregate stability |
| V-I4 | V | FM-1 | COVERED | "An interlock independent of the crop control software and its sensors cuts CO₂ injection and triggers an audible alarm when concentration exceeds 5 000 ppm" (V11) | inviolable hard safety limit overriding control |
| V-I5 | V | FM-2 | NOT-COVERED | | no aggregate "don't waste energy/resource on opposing actions" predicate (CO₂-vs-vent waste is scored on Dep-X2) |
| V-I6 | V | FM-3 | COVERED | "control declared compliant while the canopy surface is 3–8 °C above air T fails this criterion" (V30) | control on the canopy-experienced/true value |
| V-I7 | V | FM-1 | COVERED | "tracks both instantaneous flux... and daily accumulated light integral (mol m⁻² d⁻¹); supplemental lighting extension is gated on DLI completion state for the day" (V29) | integrated DLI/photoperiod budget |
| V-I8 | V | FM-7 | NOT-COVERED | | no loop-liveness/watchdog/stall-detection of the control loop (D4 ensures alarm-layer independence, not loop-cycle liveness) |
| V-I9 | V | FM-2 | COVERED | "D3 can override, limit, or blend individual D2 controller outputs before they reach actuators" (Dep5) | single arbiter merges demands before the shared actuator |
| V-E1 | V | FM-6 | COVERED | "When full vent aperture combined with full shading cannot maintain UTL, an overtemperature alarm fires with a documented crop-heat-stress threshold" (V13) | weather beyond actuator authority + degraded-band defense |
| V-E2 | V | FM-5 | COVERED | "Broken: on an overcast day with supplemental lights on all day, the night T setback never fires; DIF is lost" (Dep2); "Day and night T setpoints jointly satisfy the DIF" (V7) | dawn/dusk transition handled as a boundary |
| V-E3 | V | FM-4 | NOT-COVERED | | no damp/filter rule for a fast external transient (passing cloud / gust / open door); V16 anti-windup is saturation-recovery, not external-transient damping |
| V-E4 | V | FM-3 | COVERED | "The heating pipe temperature setpoint specifies a minimum pipe surface T relative to local air dewpoint... condensation drip onto canopy from pipes below dewpoint fails" (V27) | dew-point/condensation-onset boundary + prevention rule |
| V-E5 | V | FM-6, FM-7 | COVERED | "All actuators have specified, tested, and documented fail-safe positions for power loss that prevent immediate crop loss" (V10) | power/equipment failure → fail-safe |
| V-E6 | V | FM-5 | COVERED | "advances crop stage on schedule or operator confirmation" (D1) | bands change mid-run + ingested |
| V-E7 | V | FM-6 | NOT-COVERED | | no controller cold-start/restart-from-unknown-actuator-state sequence |
| V-F1 | V | FM-3, FM-1 | COVERED | "A single sensor failure (stuck, out-of-range, dropout) triggers a switch to a defined safe fallback value in D2... The system must not continue on bad data silently" (V9) | sensor fault/drift guard |
| V-F2 | V | FM-3, FM-7 | COVERED | "When the CO₂ injection valve has been at maximum... without the setpoint being reached, an 'injection saturation' alarm fires (indicating structural infiltration leak or supply issue); the valve does not simply remain open indefinitely" (V25) | persistent-maxed actuator raised as a fault |
| V-F3 | V | FM-2 | COVERED | "every identified two-way and three-way combination of conflicting actuator demands has exactly one defined resolution rule with a total priority ordering... A design without a cold × humid × CO₂-depleted three-way rule fails" (V2) | multi-variable target conflict + priority order |
| V-F4 | V | FM-1, FM-7 | COVERED | "any CV setpoint defined (partly) to prevent enabling conditions for disease (RH < 90 %, condensation avoidance)" (cand N1); "the derived VPD are within crop bounds" (V1) | uncorrected humidity→condensation→disease guarded via VPD/condensation control |
| N1 | N | FM-1 | NOT-COVERED | | candidate does not declare the crop climate recipe/setpoint envelope as a given upstream-agronomy input (cand N4 is scheduling, cand N2 is fertilizer chemistry) |
| N2 | N | FM-1 | COVERED | "Biological control agents and pesticide application are out of scope. IN scope: any CV setpoint defined (partly) to prevent enabling conditions for disease" (cand N1) | pest/disease management excluded; abiotic conditions in |
| N3 | N | FM-1 | NOT-COVERED | | no declared exclusion that the HVAC/actuator hardware is assumed installed/functioning (cand N3 is the building shell → ref N5; cand N6 is CO₂ source only) |
| N4 | N | FM-1 | COVERED | "Tariff-based demand-curtailment and peak-shifting are out of scope for the core regime" (cand N5) | grid/energy-cost optimization excluded |
| N5 | N | FM-1 | COVERED | "Frame, glazing, and screen structural integrity are out of scope. IN scope: mechanical limits on vent aperture and screen travel speed" (cand N3) | structure/glazing fixed given |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| V-F1 | 6 | 5 | V9 (primary); V17 "sensor calibration drift detection"; Dep3 "Controllers receive D5-validated readings"; Dep4 "Alarm comparisons use D5-validated readings"; D5 "Detects stuck readings, out-of-range values, and rate-of-change anomalies"; V22 "a false-low reading from rain droplets or sensor soiling does not cause unnecessary lighting" |
| V-E1 | 3 | 2 | V13 (primary); V12 "heating plant reaches maximum rated output... saturation alarm... minimum-T fallback"; V3 "Actuator capacity feasibility at design conditions" |
| V-F2 | 3 | 2 | V25 (primary); V31 "≥ 10 % progressive drop in delivery efficiency... triggers a maintenance alert"; V20 "a partial or full emitter clog does not result in the controller silently continuing to demand irrigation" |
| V-E5 | 3 | 2 | V10 (primary); D4 "activates documented safe-state fallbacks. Must remain operational when any individual controller fails"; V19 "injection-valve open with zero confirmed flow triggers a supply-failure alarm" |
| V-E2 | 3 | 2 | Dep2 (primary); V7 "DIF constraint satisfaction"; V8 "zero gaps or double-execution events at midnight boundaries, crop-stage transitions, DST changes" |
| V-I6 | 2 | 1 | V30 (primary); V21 "Sensor placement spans the greenhouse zone variation... single-point sensing is rejected" |
| Dep-X16 | 2 | 1 | D5-HAF (primary); V21 "Horizontal airflow fans must be operational as a precondition for sensor representativeness" |
| V-I3 | 2 | 1 | V2 (primary); V16 "No D2 controller allows unbounded integral accumulation during actuator saturation" |
| D2 | 2 | 1 | D2-cand (primary); D7 "Processes outdoor-station data (T, RH, wind speed/direction, global radiation...)" |

Ballast total = 17.

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| D6 "Logging / historian: Time-series storage of all sensor readings and actuator states at ≥ 1 min resolution; prerequisite for post-hoc diagnosis" | UNMATCHED — human review |
| V18 "Actuator position verification... reported (encoder) position is not taken as authoritative without confirmation" | UNMATCHED — human review |
| V23 "Wind-speed vent limit: Vent aperture is hard-constrained... by an outdoor anemometer threshold to protect against structural damage" | UNMATCHED — human review |
| Dep1 "D1 → D2 (setpoint propagation): All controller setpoints originate from D1 and propagate to D2" | UNMATCHED — human review |
| Dep6 "D7 → D3 (outdoor conditions to interlock)... a cold front or fog event is not anticipated; T crashes before heating can compensate" | UNMATCHED — human review |
| Dep7 "Actuator-state bus → D3 (real-time positions)... screen encoder slip or vent obstruction is invisible to arbitration logic" | UNMATCHED — human review |
| Dep8 "D1 clock → all timed transitions... a single, DST-aware, leap-second-aware clock source shared across D1–D4" | UNMATCHED — human review |
| cand N2 "Fertilizer chemistry (N:P:K recipe): Nutrient formulation is out of scope" | UNMATCHED — human review |
| cand N4 "Long-term crop scheduling and harvest planning... out of scope" | UNMATCHED — human review |
| cand N6 "CO₂ source generation: Boiler management, cylinder logistics, and flue-gas treatment are out of scope" | UNMATCHED — human review |
| cand N7 "Worker access and building management... out of scope" | UNMATCHED — human review |

Unmatched total = 11.

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 9/10   Dep = 10/17   V = 16/20   N = 3/5
  by FM tag:     FM-1 = 10/12   FM-2 = 11/19   FM-3 = 4/4   FM-4 = 1/2   FM-5 = 3/3   FM-6 = 2/3   FM-7 = 3/4
  PARTIAL counts: D = 1   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 17
  unmatched candidate points (human-review flag):    total = 11
```
