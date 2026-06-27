# T10 — Search Pass 2 (gap analysis against D1)

Source: D1.md reviewed against the task statement. Only genuinely new content
is listed — items already covered by D, Dep, V, or N in D1 are not restated.

---

## Missing Components / Sub-goals

**pH control loop** — pH sensing and acid/base dosing form a distinct irrigation
control loop; N2 explicitly declares EC and pH as in-scope irrigation targets yet
no D component defines a pH sensor, a dosing actuator, or a pH feedback
controller. *Falsifier: design names pH as in-scope but produces no pH sensor
placement, no acid/base actuator, and no control law for it.*

**VPD computation node** — VPD is a first-class crop variable required by V1 and
used in humidity-inversion decisions, yet no component is assigned responsibility
for computing VPD from validated T and RH and routing it to D1 or D3. *Falsifier:
V1 checks VPD at runtime but the value is either absent or derived from raw
(unvalidated) readings because no named subsystem produces it.*

**ET-based irrigation feedforward** — Commercial irrigation triggering typically
uses a cumulative radiation-sum (or ET model) to anticipate root-zone deficit
before sensors detect it; D7 already carries outdoor radiation data but no
component consumes it for irrigation timing; D2 covers only sensor-reactive
irrigation. *Falsifier: on a high-radiation day, the moisture sensor detects
deficit only after the root zone has already stressed; ET-anticipatory triggering
would have fired 20–30 min earlier.*

**Root-zone temperature** — Many crops specify a root-zone temperature bound
distinct from air temperature (floor heating, in-substrate pipes); D2 covers air T
only; root-zone T is neither sensed, controlled, nor listed as an exclusion.
*Falsifier: concrete floor keeps root-zone T 8 °C below air T while air T is
on-setpoint; crop development is stunted with no alarm.*

**Empty-greenhouse (harvest/transition) control mode** — Between crop removal and
replanting, transpiration load and photosynthetic CO₂ sink disappear; the active
crop control regime drives incorrect actuator behavior (CO₂ injection with no
sink, irrigation on dry sensors). No D component, schedule state, or exclusion
covers this mode. *Falsifier: at crop removal, CO₂ injection runs continuously
with no canopy uptake; moisture sensors fire drip irrigation into bare substrate.*

---

## Missing Cross-Component Dependency Seams

**Lighting actuator state → D2 T controller (indoor disturbance feedforward)** —
V28 requires that T control receive a compensation signal when supplemental lights
activate (HPS ≈ 60 % convective heat), but no Dep links the lighting on/off and
dimming state to D2's T controller. D7 provides outdoor feedforward; the indoor
lighting disturbance has no named signal path. *Falsifier: lights turn on; T rises
above UTL before the PID reacts; no feedforward is wired in, so the T alarm fires
on every light-on event.*

**D5 validated outputs → VPD computation → D1/D3** — D5 produces validated T and
RH; VPD must be derived from those validated values before D1 uses it for
setpoint context and D3 uses it for humidity-inversion checks; the two-hop seam
(D5 → VPD node → D1/D3) is absent. *Falsifier: D3 evaluates humidity-inversion
strategy using VPD computed from raw sensor reads; a temporarily faulty RH sensor
causes D3 to open vents on a foggy morning.*

**D1 crop stage → D5 anomaly thresholds** — D5 detects out-of-range and
rate-of-change anomalies; valid ranges differ between seedling and mature-canopy
stages; no Dep carries D1's current stage to D5 to update its expected bands.
*Falsifier: at a crop-stage advance, a CO₂ reading valid for the new stage
triggers a false fault because D5 still uses the seedling expected range.*

**D6 historian → trend analysis consumer (for V31)** — V31 requires that heating
efficiency be logged, trended, and alarmed for ≥ 10 % drift; D6 stores the data
but no named D component or Dep connects D6 to a trending / alert function.
*Falsifier: D6 accumulates thermal logs for six months; no consumer reads them;
progressive pipe fouling degrades heating output by 20 % before the T setpoint
becomes unreachable.*

**CO₂ controller saturation state → D4 (for V25)** — V25 requires an
injection-saturation alarm when the valve is at maximum for a configurable hold
period; no Dep assigns which component monitors this state or routes it to D4; the
signal path from D2's CO₂ controller to D4's alarm logic is unspecified.
*Falsifier: CO₂ valve stays fully open for 36 hours without reaching setpoint; no
alarm fires because D2 and D4 each expect the other to detect saturation.*

**Single-actuator demand aggregation in D3** — Multiple D2 controllers can
simultaneously command conflicting positions on one physical actuator (T controller:
vents 60 %, CO₂ controller: vents 0 %); D3 enforces hard limits (wind, screen) but
defines no aggregation rule (priority vote, min-wins, weighted blend) for
simultaneous competing demands on the same actuator. *Falsifier: T and CO₂
controllers each write to the vent driver; last-write-wins causes oscillation at
2-second intervals; D3's interlocks are never triggered because neither demand
individually violates a hard bound.*

---

## Missing Global Invariants

**Outdoor station communication failure fallback** — D7 is declared a "hard system
dependency" but no fallback behavior is defined for its communication loss; D3
would lose vent-limit, humidity-inversion, and heating-margin inputs. *Falsifier:
anemometer comms fail silently; D3 drops the wind-speed vent limit; vents open
fully in a storm; structural damage or an uncontrolled cold front penetrates the
greenhouse.*

**Startup / power-restoration sequencing** — When power returns after an outage,
all actuators attempt to re-energize simultaneously (heating, vents, CO₂ injection,
supplemental lights); no sequencing protocol prevents simultaneous conflicting
demands and thermal spikes in the first minutes. *Falsifier: on power return,
heaters fire at max, lights fire at max heat load, vents open for T control, and
CO₂ injects; T overshoots UTL within 10 minutes; the interlock is reactive, not
anticipatory.*

**Manual operator override and return-to-auto** — An operator who physically
overrides an actuator (opens a vent, disables a pump) leaves the control loop
commanding a position it cannot achieve; no component detects the discrepancy
between commanded and actual position beyond actuator verification (V18), halts
the affected channel, or specifies a condition to restore automatic control.
*Falsifier: operator opens a vent manually; D3 sees commanded position (closed)
matching encoder (still closed, due to local override); T crashes; no alarm
differentiates mechanical failure from manual override.*

---

## Missing Edge / Boundary Cases

**Actuator travel time and transient exposure** — Vent and screen actuators have
finite travel speeds (1–4 min full stroke); during a large setpoint step the
intermediate partially-open position is neither the starting state nor the target;
D3 evaluates interlocks against target positions, not against intermediate ones,
leaving a transient window with no constraint enforcement. *Falsifier: T spike
demands full vent open from 10 % closed; during 3-minute travel, D3 applies no
vent-limit interlocks because the actuator has not yet reached the commanded
position; a wind gust at minute 2 causes uncontrolled cold infiltration.*

**Harvest-transition sensor behavior** — At crop removal, substrate sensors may
read anomalously (dry slab, absent transpiration, no root uptake); D5's anomaly
detection will fire false faults on valid post-harvest readings if its thresholds
are calibrated for an active crop. *Falsifier: after harvest, the irrigation
controller reads the dry substrate as a sensor fault and disables irrigation
fallback rather than recognizing it as an expected empty-greenhouse state.*

---

## Missing Silent Failure Modes

**Supplemental lamp bank failure** — If a lamp bank fails completely, the PAR
controller demands maximum on-time indefinitely without reaching DLI; no
lamp-failure alarm or saturation timeout equivalent to V12 (heating) or V25 (CO₂)
exists. *Falsifier: ballast failure; controller stays at full dimming demand; DLI
accumulates at half-rate for a full week with no alarm.*

**Drain-water EC vs. root-zone EC divergence** — V5 mentions EC trend monitoring
but covers only root-zone (in-substrate) EC; feed EC and drain EC must be measured
separately (drain EC ÷ feed EC = leaching fraction); monitoring only in-slab EC
misses EC accumulation from under-leaching because in-slab reads a mix of fed and
accumulated salts. *Falsifier: leaching fraction drops below target; in-slab EC
reads within normal range (averaging fed and accumulated); osmotic stress develops
with no alarm.*

**CO₂ sensor positive drift (silent under-injection)** — V17 covers drift
detection for CO₂ NDIR sensors but the specific failure mode of upward drift is
a silent agronomic loss: the sensor reads above setpoint while actual concentration
is below it; the controller under-injects indefinitely without triggering any
saturation alarm. *Falsifier: NDIR sensor drifts +200 ppm high; controller
concludes setpoint is reached and closes injection valve; photosynthesis is
CO₂-limited for weeks before a calibration check reveals the drift.*

---

## Wrong Scope Decisions

**pH control is declared in-scope (N2) but has no D coverage** — N2 correctly
identifies EC and pH as in-scope irrigation control targets, yet the component set
(D1–D7) contains no pH sensor, no dosing actuator, and no pH control loop. This is
not a narrow-exclusion defensible choice; pH excursions (< 5.5 or > 6.5) cause
nutrient lockout and are a primary irrigation control function in commercial
substrate culture. The scope declaration and the component set are inconsistent.
*Falsifier: a design that names pH as in-scope passes D-completeness review because
no V criterion checks for a pH controller.*

---

## Summary

| Category | New items |
|----------|-----------|
| Missing components | 5 |
| Missing Dep seams | 6 |
| Missing global invariants | 3 |
| Missing edge / boundary cases | 2 |
| Missing silent failure modes | 3 |
| Wrong scope decisions | 1 |
| **Total new holes** | **20** |
